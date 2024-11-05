# app.py
import os
import time
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.web import WebClient
from flask import Flask, request
import threading
import schedule

# Load environment variables from .env file (if using dotenv)
from dotenv import load_dotenv
load_dotenv()

# Initialize the Flask app
flask_app = Flask(__name__)

# Initialize the Slack app with your bot token and signing secret
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

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
channel_id = "C04AR90JPED"  # Replace with your channel ID

def send_reminder():
    global current_index
    user_id = team_members[current_index]
    client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

    # Message with a Skip button
    client.chat_postMessage(
        channel=channel_id,
        text=f"<@{user_id}> is responsible for today's task.",
        attachments=[
            {
                "text": "If you're unavailable, you can skip to the next person.",
                "fallback": "You are unable to skip",
                "callback_id": "skip_responsibility",
                "color": "#3AA3E3",
                "attachment_type": "default",
                "actions": [
                    {
                        "name": "skip",
                        "text": "Skip",
                        "type": "button",
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
@app.action("skip")
def handle_skip(ack, body, client):
    global current_index
    ack()

    # Move to the next person
    current_index = (current_index + 1) % len(team_members)
    next_user_id = team_members[current_index]

    # Update the message to mention the next person
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"<@{next_user_id}> is now responsible for today's task.",
        attachments=[]  # Remove the attachments (buttons)
    )

# Flask route to handle Slack requests
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    handler = SlackRequestHandler(app)
    return handler.handle(request)

if __name__ == "__main__":
    # Run the Flask app
    flask_app.run(host="0.0.0.0", port=3000)

