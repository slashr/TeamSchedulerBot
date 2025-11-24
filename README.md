# TeamSchedulerBot

Slack bot that posts a daily rotation reminder with confirm/skip buttons.

## Run locally
1) Install deps: `pip install -r requirements.txt`
2) Set env vars: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
3) Optional env vars:
   - `TEAM_MEMBERS` comma-separated Slack user IDs (defaults to baked-in list)
   - `DEVOPS_SUPPORT_CHANNEL` Slack channel ID for reminders
   - `STATE_DIR` (defaults to `/state` for Kubernetes PVC; use `./state` locally)
   - `ENABLE_SCHEDULER=false` to disable APS scheduler
   - `SCHEDULER_POD_NAME` to pin scheduler to a specific pod name when scaling
4) Start the server: `gunicorn -c gunicorn.conf.py app:app` (or `python app.py` for a simple local run)

## Slack slash command
- Configure `/rotation` (requires the `commands` scope).
- Usage: `/rotation list`, `/rotation add <@user>`, `/rotation remove <@user>`.
- Roster changes are persisted to the rotation state file so they survive restarts.

## Health
- `/health` liveness, `/ready` readiness (requires roster + scheduler), `/metrics` basic text metrics.
