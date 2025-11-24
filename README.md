# TeamSchedulerBot

Slack bot that posts a daily rotation reminder with confirm/skip buttons.

## Quick start
1) Install deps: `pip install -r requirements.txt`
2) Set env vars: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
3) Optional: set `STATE_DIR` (defaults to `/state` for Kubernetes PVC; use `./state` locally)
4) Run locally: `python app.py`
