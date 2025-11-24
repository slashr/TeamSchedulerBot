import os
import json
import logging
import sys
from typing import List, Dict, Any
from flask import Flask, request, Response
from slack_bolt import App as SlackBoltApp
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.web import WebClient
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from pytz import utc
from threading import Lock

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration Validation
# ---------------------------------------------------------------------------
def validate_environment() -> None:
    """
    Validate that all required environment variables are set.
    Exits with error code 1 if any required variables are missing.
    """
    required_vars = ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Please set these variables in your .env file or environment")
        sys.exit(1)
    
    logger.info("Environment validation passed")

# Validate environment before initializing any services
validate_environment()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
team_members = [
    "U07GAGKL6SY",  # Damian
    "U04JZU760AD",  # Sopio
    "U06Q83GFMNW",  # Phil
    "U07H9H7L7K8",  # Rafa
    "U041EHKCD3K",  # Martin
    "U062AK6DQP9",  # Akash
]

CHANNEL_ID = os.getenv("DEVOPS_SUPPORT_CHANNEL", "C087GGL7EMT")
REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "9"))
REMINDER_MINUTE = int(os.getenv("REMINDER_MINUTE", "0"))
REMINDER_TIMEZONE = os.getenv("REMINDER_TIMEZONE", "Europe/Berlin")

# Persistent state location (backed by a PVC in Kubernetes)
STATE_DIR = os.getenv("STATE_DIR", "/state")
try:
    os.makedirs(STATE_DIR, exist_ok=True)
except Exception as exc:  # Fall back to local path if PVC is unavailable
    logger.warning("Failed to create state dir '%s' (%s); falling back to ./state", STATE_DIR, exc)
    STATE_DIR = "./state"
    os.makedirs(STATE_DIR, exist_ok=True)

STATE_FILE = os.path.join(STATE_DIR, "rotation_state.json")
state_lock = Lock()

# ---------------------------------------------------------------------------
# Slack Bolt / Flask setup
# ---------------------------------------------------------------------------
bolt_app = SlackBoltApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)
app = Flask(__name__)
handler = SlackRequestHandler(bolt_app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_message_blocks(text: str, assigned_user_id: str) -> List[Dict[str, Any]]:
    """
    Build Slack Block Kit blocks with Confirm/Skip action buttons.
    
    Args:
        text: The message text to display
        assigned_user_id: The Slack user ID of the assigned person
        
    Returns:
        List of Slack Block Kit block dictionaries
    """
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirm"},
                    "style": "primary",
                    "action_id": "confirm_action",
                    "value": assigned_user_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Skip"},
                    "style": "danger",
                    "action_id": "skip_action",
                    "value": "skip",
                },
            ],
        },
    ]


def load_state() -> int:
    """
    Load the current rotation index from persistent state file.
    
    Returns:
        The current rotation index (0-based)
    """
    if not team_members:
        logger.warning("No team members configured; defaulting rotation index to 0")
        return 0

    with state_lock:
        if not os.path.exists(STATE_FILE):
            return 0

        try:
            with open(STATE_FILE, "r") as fp:
                data = json.load(fp)
            idx = int(data.get("current_index", 0))
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            logger.warning("State file invalid; resetting rotation to 0 (%s)", exc)
            return 0

        if idx < 0 or idx >= len(team_members):
            logger.warning(
                "State index %s out of bounds for %d members; resetting to 0",
                idx,
                len(team_members),
            )
            return 0

        return idx


def save_state(idx: int) -> None:
    """
    Save the rotation index to persistent state file.
    
    Args:
        idx: The rotation index to save
    """
    with state_lock:
        with open(STATE_FILE, "w") as fp:
            json.dump({"current_index": idx}, fp)


def advance_rotation() -> int:
    """
    Advance to the next person in the rotation.
    
    Returns:
        The new rotation index
    """
    if not team_members:
        logger.error("Team members list is empty; cannot advance rotation")
        return 0

    idx = load_state()
    next_idx = (idx + 1) % len(team_members)
    save_state(next_idx)
    logger.info("Rotation advanced from index %d to %d", idx, next_idx)
    return next_idx

# ---------------------------------------------------------------------------
# Reminder job (APS)
# ---------------------------------------------------------------------------

def send_reminder() -> None:
    """
    Send the daily reminder message to the Slack channel with the assigned user.
    This function is called by the scheduler.
    """
    try:
        if not team_members:
            logger.error("No team members configured; skipping reminder send")
            return

        idx = load_state()
        user_id = team_members[idx]
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        text = f"<@{user_id}> is responsible for #devops_support today."
        
        logger.info("Sending reminder to user %s (index %d)", user_id, idx)
        
        client.chat_postMessage(
            channel=CHANNEL_ID,
            text=text,
            blocks=get_message_blocks(text, user_id),
        )
        logger.info("Successfully sent reminder to %s", user_id)
    except Exception as exc:
        logger.error("Failed to send reminder: %s", exc, exc_info=True)

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=1)},
    timezone=REMINDER_TIMEZONE,
)

# Schedule daily reminder (configurable via environment variables)
scheduler.add_job(
    send_reminder,
    "cron",
    minute=REMINDER_MINUTE,
    hour=REMINDER_HOUR,
    day_of_week='mon-fri'
)

#Test schedule
#scheduler.add_job(send_reminder, "cron", minute="*")

# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------
@bolt_app.action("confirm_action")
def handle_confirm(ack, body, client, logger) -> None:
    """
    Handle the Confirm button action.
    Only the assigned user can confirm their assignment.
    """
    ack()
    try:
        user_clicked = body["user"]["id"]
        assigned = body["actions"][0]["value"]
        
        if user_clicked == assigned:
            msg = f"<@{user_clicked}> has confirmed #devops_support for today :meow_salute:"
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=msg,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": msg}}],
            )
            logger.info("User %s confirmed assignment", user_clicked)
            advance_rotation()
        else:
            logger.warning(
                "User %s attempted to confirm assignment meant for %s",
                user_clicked,
                assigned
            )
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_clicked,
                text="Sorry, only the assigned user can confirm this task.",
            )
    except Exception as exc:
        logger.error("Error handling confirm action: %s", exc, exc_info=True)


@bolt_app.action("skip_action")
def handle_skip(ack, body, client, logger) -> None:
    """
    Handle the Skip button action.
    Advances rotation to the next person and updates the message.
    """
    ack()
    try:
        if not team_members:
            logger.error("No team members configured; cannot skip rotation")
            return

        idx = load_state()
        current_user = team_members[idx]
        next_idx = advance_rotation()
        next_user = team_members[next_idx]
        
        msg = (
            f"<@{current_user}> is unavailable. <@{next_user}> is now responsible for #devops_support today."
        )
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=msg,
            blocks=get_message_blocks(msg, next_user),
        )
        logger.info("User %s skipped; reassigned to %s", current_user, next_user)
    except Exception as exc:
        logger.error("Error handling skip action: %s", exc, exc_info=True)

# ---------------------------------------------------------------------------
# Flask endpoint
# ---------------------------------------------------------------------------
@app.route("/slack/events", methods=["POST"])
def slack_events() -> Response:
    """
    Main Flask endpoint for handling Slack events.
    
    Returns:
        Flask Response object from the Slack handler
    """
    return handler.handle(request)

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("=== TeamSchedulerBot Configuration ===")
    logger.info("Team members: %d", len(team_members))
    logger.info("Channel ID: %s", CHANNEL_ID)
    logger.info("Reminder schedule: %02d:%02d %s (Mon-Fri)", REMINDER_HOUR, REMINDER_MINUTE, REMINDER_TIMEZONE)
    logger.info("State directory: %s", STATE_DIR)
    logger.info("=====================================")
    
    scheduler.start()
    logger.info("Scheduler started successfully")
    
    logger.info("Starting Flask app on 0.0.0.0:3000")
    app.run(host="0.0.0.0", port=3000)
