import json
import importlib
import os
import sys
from pathlib import Path


def reload_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "dummy")
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("TEAM_MEMBERS", "U1,U2,U3")
    monkeypatch.setattr(
        "slack_sdk.web.client.WebClient.auth_test",
        lambda self, **kwargs: {"ok": True},
        raising=False,
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_confirm_keeps_current_assignee(tmp_path, monkeypatch):
    app = reload_app(monkeypatch, tmp_path)

    # Seed state: current index 0, assignee also 0
    with open(app.STATE_FILE, "w") as fp:
        json.dump(
            {
                "current_index": 0,
                "current_assignee_index": 0,
                "team_members": ["U1", "U2", "U3"],
            },
            fp,
        )
    app.load_state()

    calls = []

    def fake_slack_api_call(func, logger, max_attempts=3, **kwargs):
        calls.append(("confirm", func.__name__, kwargs))
        return func(**kwargs)

    class FakeClient:
        def chat_update(self, **kwargs):
            return {"ok": True, **kwargs}

    ack = lambda: None  # noqa: E731
    body = {
        "user": {"id": "U1"},
        "actions": [{"value": "U1"}],
        "channel": {"id": "C1"},
        "message": {"ts": "123"},
    }

    monkeypatch.setattr(app, "slack_api_call", fake_slack_api_call)
    app.handle_confirm(ack, body, FakeClient(), app.logger)

    with open(app.STATE_FILE, "r") as fp:
        data = json.load(fp)

    assert data["current_index"] == 1
    assert data["current_assignee_index"] == 0
    # Ensure Slack update was attempted
    assert any(call[1] == "chat_update" for call in calls)


def test_skip_advances_assignee(tmp_path, monkeypatch):
    app = reload_app(monkeypatch, tmp_path)
    with open(app.STATE_FILE, "w") as fp:
        json.dump(
            {
                "current_index": 0,
                "current_assignee_index": 0,
                "team_members": ["U1", "U2", "U3"],
            },
            fp,
        )
    app.load_state()

    calls = []

    def fake_slack_api_call(func, logger, max_attempts=3, **kwargs):
        calls.append(("skip", func.__name__, kwargs))
        return func(**kwargs)

    class FakeClient:
        def chat_update(self, **kwargs):
            return {"ok": True, **kwargs}

    ack = lambda: None  # noqa: E731
    body = {
        "user": {"id": "U1"},
        "actions": [{"value": "skip"}],
        "channel": {"id": "C1"},
        "message": {"ts": "123"},
    }

    monkeypatch.setattr(app, "slack_api_call", fake_slack_api_call)
    app.handle_skip(ack, body, FakeClient(), app.logger)

    with open(app.STATE_FILE, "r") as fp:
        data = json.load(fp)

    assert data["current_index"] == 1
    assert data["current_assignee_index"] == 1
    assert any(call[1] == "chat_update" for call in calls)
