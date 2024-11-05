# app.py
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
    "U01...",  # User 1
    "U02...",  # User 2
    "U03...",  # User 3
    "U04...",  # User 4
    "U05...",  # User 5
    "U06...",  # User 6
]

# Index to keep track of the current person responsible
current_index = 0

# Channel where the reminders will be posted
channel_id = "C01..."  # Replace with your channel ID

def send_reminder():
    global current_index
    user_id = team_members[current_index]
    client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

    # Message with a Skip button using Block Kit
    client.chat_postMessage(
        channel=channel_id,
        text=f"<@{user_id}> is responsible for today's task.",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<@{user_id}> is responsible for today's task."
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Skip"
                        },
                        "action_id": "skip_action",
                        "value": "skip"
                    }
                ]
            }
        ]
    )

# Schedule the send_reminder function to run every weekday at 9:00 AM
schedule.every().monday.at("09:00").do(send_reminder)
schedule.every().tuesday.at("09:00").do(send_reminder)
schedule.every().wednesday.at("09:00").do(send_reminder)
schedule.every().thursday.at("09:00").do(send_reminder)
schedule.every().friday.at("09:00").do(send_reminder)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start the scheduler in a separate thread
threading.Thread(target=run_schedule).start()

# Handle the Skip button action
@bolt_app.action("skip_action")
def handle_skip_action(ack, body, client, logger):
    ack()

    global current_index

    # Move to the next person
    current_index = (current_index + 1) % len(team_members)
    next_user_id = team_members[current_index]

    # Update the original message to mention the next person
    try:
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=f"<@{next_user_id}> is now responsible for today's task.",
            blocks=[]  # Remove the blocks to remove the button
        )
    except Exception as e:
        logger.error(f"Failed to update message: {e}")

# Flask route to handle Slack requests
@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

