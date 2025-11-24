import os
import json
import logging
import sys
import signal
from typing import List, Dict, Any, Optional
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
DEFAULT_TEAM_MEMBERS = [
    "U07GAGKL6SY",  # Damian
    "U04JZU760AD",  # Sopio
    "U06Q83GFMNW",  # Phil
    "U07H9H7L7K8",  # Rafa
    "U041EHKCD3K",  # Martin
    "U062AK6DQP9",  # Akash
]


def parse_team_members_env() -> List[str]:
    """Parse TEAM_MEMBERS env var (comma-separated Slack user IDs)."""
    raw = os.getenv("TEAM_MEMBERS", "")
    if not raw:
        return []
    members = [member.strip() for member in raw.split(",") if member.strip()]
    return members


team_members: List[str] = parse_team_members_env() or DEFAULT_TEAM_MEMBERS

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
state_loaded = False

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


def _read_state_locked() -> Dict[str, Any]:
    """Read state file contents. Caller must hold state_lock."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as fp:
            return json.load(fp)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        logger.warning("State file invalid; resetting rotation to defaults (%s)", exc)
        return {}


def _write_state_locked(idx: int) -> None:
    """Persist rotation index and current team members. Caller must hold state_lock."""
    with open(STATE_FILE, "w") as fp:
        json.dump({"current_index": idx, "team_members": team_members}, fp)


def get_team_members(force_reload: bool = False) -> List[str]:
    """Thread-safe accessor for team_members, with optional refresh from disk."""
    if force_reload or not state_loaded:
        load_state()
    with state_lock:
        return list(team_members)


def load_state() -> int:
    """
    Load the current rotation index from persistent state file.
    
    Returns:
        The current rotation index (0-based)
    """
    global state_loaded

    with state_lock:
        if not team_members:
            logger.warning("No team members configured; defaulting rotation index to 0")
            return 0

        data = _read_state_locked()
        stored_members = data.get("team_members")
        if stored_members:
            team_members.clear()
            team_members.extend(stored_members)

        try:
            idx = int(data.get("current_index", 0))
        except (TypeError, ValueError):
            logger.warning(
                "State index %s is invalid; resetting to 0", data.get("current_index")
            )
            idx = 0
            _write_state_locked(idx)

        if idx < 0 or idx >= len(team_members):
            logger.warning(
                "State index %s out of bounds for %d members; resetting to 0",
                idx,
                len(team_members),
            )
            idx = 0
            _write_state_locked(idx)

        state_loaded = True
        return idx


def save_state(idx: int) -> None:
    """
    Save the rotation index to persistent state file.
    
    Args:
        idx: The rotation index to save
    """
    with state_lock:
        _write_state_locked(idx)


def advance_rotation() -> int:
    """
    Advance to the next person in the rotation.
    
    Returns:
        The new rotation index
    """
    members = get_team_members(force_reload=True)
    if not members:
        logger.error("Team members list is empty; cannot advance rotation")
        return 0

    idx = load_state()
    next_idx = (idx + 1) % len(members)
    save_state(next_idx)
    logger.info("Rotation advanced from index %d to %d", idx, next_idx)
    return next_idx


def update_team_members(new_members: List[str], removed_index: Optional[int] = None) -> int:
    """
    Replace the roster with a new list and persist state.
    
    Args:
        new_members: new ordered list of Slack user IDs
        removed_index: optional index that was removed (used to adjust pointer)
    Returns:
        The persisted rotation index after adjustment
    """
    ensure_state_loaded()

    cleaned: List[str] = []
    seen = set()
    for user_id in new_members:
        if user_id and user_id not in seen:
            cleaned.append(user_id)
            seen.add(user_id)

    if not cleaned:
        raise ValueError("Team members list cannot be empty")

    with state_lock:
        global team_members
        data = _read_state_locked()
        try:
            current_idx = int(data.get("current_index", 0))
        except (TypeError, ValueError):
            logger.warning(
                "State index %s is invalid during roster update; resetting to 0",
                data.get("current_index"),
            )
            current_idx = 0

        if removed_index is not None and removed_index < current_idx:
            current_idx -= 1

        if current_idx < 0 or current_idx >= len(cleaned):
            current_idx = 0

        team_members.clear()
        team_members.extend(cleaned)
        _write_state_locked(current_idx)
        return current_idx


def extract_user_id(raw: str) -> str:
    """Strip Slack mention wrappers and whitespace."""
    cleaned = raw.strip()
    if cleaned.startswith("<@") and cleaned.endswith(">"):
        cleaned = cleaned[2:-1]
    return cleaned


def ensure_state_loaded() -> None:
    """Ensure state (including roster) is loaded once per process."""
    global state_loaded
    if state_loaded:
        return
    load_state()

# ---------------------------------------------------------------------------
# Reminder job (APS)
# ---------------------------------------------------------------------------

def send_reminder() -> None:
    """
    Send the daily reminder message to the Slack channel with the assigned user.
    This function is called by the scheduler.
    """
    try:
        members = get_team_members(force_reload=True)
        if not members:
            logger.error("No team members configured; skipping reminder send")
            return
    
        idx = load_state()
        members = get_team_members()
        user_id = members[idx]
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

_scheduler_started = False
_shutdown_registered = False

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


def should_start_scheduler() -> bool:
    """
    Determine whether the scheduler should start in this process/pod.
    This allows us to limit the scheduler to a single instance when scaling.
    """
    enabled = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
    if not enabled:
        logger.info("Scheduler disabled via ENABLE_SCHEDULER=false")
        return False

    primary_pod = os.getenv("SCHEDULER_POD_NAME")
    hostname = os.getenv("HOSTNAME")
    if primary_pod and hostname and hostname != primary_pod:
        logger.info(
            "Skipping scheduler on pod %s (primary pod set to %s)",
            hostname,
            primary_pod,
        )
        return False

    return True


def start_scheduler_once() -> None:
    """
    Start the APS scheduler if it hasn't been started yet in this process.
    """
    global _scheduler_started
    if _scheduler_started:
        return

    if not should_start_scheduler():
        return

    scheduler.start()
    _scheduler_started = True
    logger.info("Scheduler started successfully")


def shutdown_scheduler(signum, frame) -> None:
    """Handle termination signals for graceful shutdown."""
    global _scheduler_started
    if not _scheduler_started:
        return
    logger.info("Signal %s received; shutting down scheduler", signum)
    try:
        scheduler.shutdown(wait=False)
    except Exception as exc:
        logger.warning("Error during scheduler shutdown: %s", exc)
    _scheduler_started = False


def register_signal_handlers() -> None:
    """Register graceful shutdown handlers once."""
    global _shutdown_registered
    if _shutdown_registered:
        return
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, shutdown_scheduler)
        except Exception as exc:
            logger.warning("Could not register handler for signal %s: %s", sig, exc)
    _shutdown_registered = True

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
        members = get_team_members(force_reload=True)
        if not members:
            logger.error("No team members configured; cannot skip rotation")
            return

        idx = load_state()
        members = get_team_members(force_reload=True)
        current_user = members[idx]
        next_idx = advance_rotation()
        members = get_team_members(force_reload=True)
        next_user = members[next_idx]
        
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
# Slash commands
# ---------------------------------------------------------------------------
@bolt_app.command("/rotation")
def handle_rotation_command(ack, body, respond, logger) -> None:
    """
    Manage rotation roster via Slack slash command.
    
    Usage:
      /rotation list
      /rotation add <@user>
      /rotation remove <@user>
    """
    ack()
    try:
        text = (body.get("text") or "").strip()
        parts = text.split()
        subcommand = parts[0].lower() if parts else "list"

        if subcommand in ("list", "ls"):
            idx = load_state()
            members = get_team_members(force_reload=True)
            if not members:
                respond("No team members configured.")
                return
            lines = []
            for i, user_id in enumerate(members, start=1):
                marker = " (current)" if i - 1 == idx else ""
                lines.append(f"{i}. <@{user_id}>{marker}")
            respond("\n".join(lines))
            return

        if subcommand == "add":
            if len(parts) < 2:
                respond("Usage: /rotation add <@user>")
                return
            user_id = extract_user_id(parts[1])
            members = get_team_members(force_reload=True)
            if user_id in members:
                respond(f"<@{user_id}> is already in the rotation.")
                return
            members.append(user_id)
            update_team_members(members)
            respond(f"Added <@{user_id}> to the rotation.")
            return

        if subcommand in ("remove", "rm", "delete"):
            if len(parts) < 2:
                respond("Usage: /rotation remove <@user>")
                return
            user_id = extract_user_id(parts[1])
            members = get_team_members(force_reload=True)
            if user_id not in members:
                respond(f"<@{user_id}> is not in the rotation.")
                return
            removed_index = members.index(user_id)
            members = [m for m in members if m != user_id]
            try:
                update_team_members(members, removed_index=removed_index)
            except ValueError:
                respond("Cannot remove the last member; rotation would be empty.")
                return
            respond(f"Removed <@{user_id}> from the rotation.")
            return

        respond("Unsupported subcommand. Try: list, add, remove.")
    except Exception as exc:
        logger.error("Error handling /rotation command: %s", exc, exc_info=True)
        respond("Something went wrong handling that command.")

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
    register_signal_handlers()
    # Ensure roster is available; seed from state if present
    current_idx = load_state()
    save_state(current_idx)
    if not get_team_members():
        logger.error("No team members configured via TEAM_MEMBERS or defaults; exiting")
        sys.exit(1)

    logger.info("=== TeamSchedulerBot Configuration ===")
    logger.info("Team members: %d", len(get_team_members()))
    logger.info("Channel ID: %s", CHANNEL_ID)
    logger.info("Reminder schedule: %02d:%02d %s (Mon-Fri)", REMINDER_HOUR, REMINDER_MINUTE, REMINDER_TIMEZONE)
    logger.info("State directory: %s", STATE_DIR)
    logger.info("=====================================")
    
    start_scheduler_once()
    
    logger.info("Starting Flask app on 0.0.0.0:3000")
    app.run(host="0.0.0.0", port=3000)
