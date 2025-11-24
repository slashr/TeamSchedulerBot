# TeamSchedulerBot

Slack bot that posts a daily rotation reminder with confirm/skip buttons.

## Run locally
1) Install deps: `pip install -r requirements.txt`
2) Set `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET`
3) Optional: `ENABLE_SCHEDULER=false` to disable APS scheduler, or `SCHEDULER_POD_NAME` to pin scheduler to a single pod/host
4) Start the server: `gunicorn -c gunicorn.conf.py app:app` (or `python app.py` for simple local runs)
