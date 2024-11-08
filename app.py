import os
import time
import threading
import schedule
from flask import Flask, request
from slack_bolt import App as SlackBoltApp
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.web import WebClient
from dotenv import load_dotenv
import logging

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

# Index to keep track of the current person responsible
current_index = 0

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

def send_reminder():
    global current_index
    user_id = team_members[current_index]
    client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

    message_text = f"<@{user_id}> is responsible for #devops_support today."

    # Message with Confirm and Skip buttons
    client.chat_postMessage(
        channel=channel_id,
        text=message_text,
        blocks=get_message_blocks(message_text, user_id)
    )

# Schedule the send_reminder function to run every 5 minutes
schedule.every(5).minutes.do(send_reminder)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Handle the Confirm button action
@bolt_app.action("confirm_action")
def handle_confirm_action(ack, body, client, logger):
    ack()

    user_id_clicked = body["user"]["id"]
    assigned_user_id = body["actions"][0]["value"]  # The assigned user's ID from the button value

    if user_id_clicked == assigned_user_id:
        # Update the message to indicate confirmation
        try:
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
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
    else:
        # Send an ephemeral message to the user who tried to confirm
        try:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_id_clicked,
                text="Sorry, only the assigned user can confirm this task."
            )
        except Exception as e:
            logger.error(f"Failed to send ephemeral message: {e}")

# Handle the Skip button action
@bolt_app.action("skip_action")
def handle_skip_action(ack, body, client, logger):
    ack()

    global current_index

    # Get the current user before skipping
    current_user_id = team_members[current_index]

    # Move to the next person
    current_index = (current_index + 1) % len(team_members)
    next_user_id = team_members[current_index]

    # Create the updated message text
    message_text = f"<@{current_user_id}> is unavailable. <@{next_user_id}> is now responsible for #devops_support today."

    # Update the original message to indicate skipping
    try:
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=message_text,
            blocks=get_message_blocks(message_text, next_user_id)
        )
    except Exception as e:
        logger.error(f"Failed to update message: {e}")

# Flask route to handle Slack requests
@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    # Add this check to prevent starting the scheduler in the reloader process
    from werkzeug.serving import is_running_from_reloader
    if not is_running_from_reloader():
        # Start the scheduler in a separate thread
        threading.Thread(target=run_schedule).start()
    app.run(host="0.0.0.0", port=3000)

