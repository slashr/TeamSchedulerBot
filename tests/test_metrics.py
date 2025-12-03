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


def test_metrics_includes_current_and_next_indexes(tmp_path, monkeypatch):
    app = reload_app(monkeypatch, tmp_path)
    with open(app.STATE_FILE, "w") as fp:
        json.dump(
            {
                "current_index": 1,
                "current_assignee_index": 0,
                "team_members": ["U1", "U2", "U3"],
            },
            fp,
        )
    app.load_state()

    resp = app.metrics()
    body = resp.get_data(as_text=True)

    lines = dict(line.split() for line in body.strip().splitlines())

    assert lines["rotation_index"] == "1"
    assert lines["current_assignee_index"] == "0"
    assert lines["next_rotation_index"] == "2"
