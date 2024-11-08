import os
import time
import threading
import json
from flask import Flask, request
from slack_bolt import App as SlackBoltApp
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.web import WebClient
from dotenv import load_dotenv
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime
from pytz import utc
from threading import Lock

load_dotenv()

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Slack Bolt app
bolt_app = SlackBoltApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Initialize the Flask app
app = Flask(__name__)

# Create the Slack request handler
handler = SlackRequestHandler(bolt_app)

# List of team members' Slack user IDs
team_members = [
    "U07GAGKL6SY",  # User 1
    "U04JZU760AD",  # User 2
    "U06Q83GFMNW",  # User 3
    "U07H9H7L7K8",  # User 4
    "U041EHKCD3K",  # User 5
    "U062AK6DQP9",  # User 6
]

# File to store the current index
STATE_FILE = 'rotation_state.json'
state_lock = Lock()

# Channel where the reminders will be posted
channel_id = "C06T98W9VQQ"  # Replace with your channel ID

def get_message_blocks(message_text, assigned_user_id):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message_text
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Confirm"
                    },
                    "style": "primary",
                    "action_id": "confirm_action",
                    "value": assigned_user_id  # Pass the assigned user's ID here
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Skip"
                    },
                    "style": "danger",
                    "action_id": "skip_action",
                    "value": "skip"
                }
            ]
        }
    ]

def load_state():
    with state_lock:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                return state.get('current_index', 0)
        else:
            return 0

def save_state(current_index):
    with state_lock:
        with open(STATE_FILE, 'w') as f:
            json.dump({'current_index': current_index}, f)

def send_reminder():
    try:
        # Load current index
        current_index = load_state()
        user_id = team_members[current_index]
        client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

        message_text = f"<@{user_id}> is responsible for #devops_support today."

        # Message with Confirm and Skip buttons
        client.chat_postMessage(
            channel=channel_id,
            text=message_text,
            blocks=get_message_blocks(message_text, user_id)
        )
        logger.info(f"Sent reminder to {user_id}")

        # Advance to the next index for testing purposes
        next_index = (current_index + 1) % len(team_members)
        save_state(next_index)

    except Exception as e:
        logger.error(f"Error in send_reminder: {e}")

# Handle the Confirm button action
@bolt_app.action("confirm_action")
def handle_confirm_action(ack, body, client, logger):
    ack()
    try:
        user_id_clicked = body["user"]["id"]
        assigned_user_id = body["actions"][0]["value"]  # The assigned user's ID from the button value

        if user_id_clicked == assigned_user_id:
            # Update the message to indicate confirmation
            message_text = f"<@{user_id_clicked}> has confirmed #devops_support for today :meow_salute:"

            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=message_text,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message_text
                        }
                    }
                ]
            )
            logger.info(f"{user_id_clicked} confirmed responsibility.")
        else:
            # Send an ephemeral message to the user who tried to confirm
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_id_clicked,
                text="Sorry, only the assigned user can confirm this task."
            )
            logger.info(f"{user_id_clicked} attempted to confirm but is not the assigned user.")
    except Exception as e:
        logger.error(f"Error in handle_confirm_action: {e}")

# Handle the Skip button action
@bolt_app.action("skip_action")
def handle_skip_action(ack, body, client, logger):
    ack()
    try:
        # Load current index
        current_index = load_state()
        current_user_id = team_members[current_index]

        # Move to the next person
        next_index = (current_index + 1) % len(team_members)
        next_user_id = team_members[next_index]

        # Save the new index
        save_state(next_index)

        # Create the updated message text
        message_text = f"<@{current_user_id}> is unavailable. <@{next_user_id}> is now responsible for #devops_support today."

        # Update the original message to indicate skipping
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=message_text,
            blocks=get_message_blocks(message_text, next_user_id)
        )
        logger.info(f"{current_user_id} skipped. Assigned to {next_user_id}.")
    except Exception as e:
        logger.error(f"Error in handle_skip_action: {e}")

# Flask route to handle Slack requests
@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    # Start the scheduler
    scheduler.start()

    # Run the Flask app
    app.run(host="0.0.0.0", port=3000)

