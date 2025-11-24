# TeamSchedulerBot

Slack bot that posts a daily rotation reminder with confirm/skip buttons.

## Run locally
1) Install deps: `pip install -r requirements.txt`
2) Set env vars: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
3) Optional: set `STATE_DIR` (defaults to `/state` for Kubernetes PVC; use `./state` locally)
4) Optional: `ENABLE_SCHEDULER=false` to disable APS scheduler, or `SCHEDULER_POD_NAME` to pin scheduler to a single pod/host
5) Start the server: `gunicorn -c gunicorn.conf.py app:app` (or `python app.py` for a simple local run)
