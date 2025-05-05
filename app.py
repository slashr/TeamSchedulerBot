import os
import json
import logging
from flask import Flask, request
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

CHANNEL_ID = os.getenv("DEVOPS_SUPPORT_CHANNEL", "C087GGL7EMT") #main channel
#CHANNEL_ID = "C06T98W9VQQ" #test channel

# Persistent state location (backed by a PVC in Kubernetes)
STATE_DIR = os.getenv("STATE_DIR", "./state")
os.makedirs(STATE_DIR, exist_ok=True)
STATE_FILE = os.path.join(STATE_DIR, "rotation_state.json")
state_lock = Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_message_blocks(text: str, assigned_user_id: str):
    """Slack Block Kit blocks with Confirm/Skip actions."""
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
    with state_lock:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as fp:
                return json.load(fp).get("current_index", 0)
        return 0


def save_state(idx: int):
    with state_lock:
        with open(STATE_FILE, "w") as fp:
            json.dump({"current_index": idx}, fp)


def advance_rotation() -> int:
    idx = load_state()
    next_idx = (idx + 1) % len(team_members)
    save_state(next_idx)
    return next_idx

# ---------------------------------------------------------------------------
# Reminder job (APS)
# ---------------------------------------------------------------------------

def send_reminder():
    try:
        idx = load_state()
        user_id = team_members[idx]
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        text = f"<@{user_id}> is responsible for #devops_support today."
        client.chat_postMessage(
            channel=CHANNEL_ID,
            text=text,
            blocks=get_message_blocks(text, user_id),
        )
        logger.info("Sent reminder to %s", user_id)
    except Exception as exc:
        logger.error("send_reminder error: %s", exc)

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=1)},
    timezone=utc,
)

#Main schedule
scheduler.add_job(send_reminder, "cron", minute=0, hour=8, day_of_week='mon-fri')

#Test schedule
#scheduler.add_job(send_reminder, "cron", minute="*")

# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------
@bolt_app.action("confirm_action")
def handle_confirm(ack, body, client, logger):
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
            logger.info("%s confirmed.", user_clicked)
            advance_rotation()
        else:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_clicked,
                text="Sorry, only the assigned user can confirm this task.",
            )
    except Exception as exc:
        logger.error("confirm_action error: %s", exc)


@bolt_app.action("skip_action")
def handle_skip(ack, body, client, logger):
    ack()
    try:
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
        logger.info("%s skipped; reassigned to %s", current_user, next_user)
    except Exception as exc:
        logger.error("skip_action error: %s", exc)

# ---------------------------------------------------------------------------
# Flask endpoint
# ---------------------------------------------------------------------------
@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    scheduler.start()
    app.run(host="0.0.0.0", port=3000)

