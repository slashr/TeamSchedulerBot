import importlib
import json
import os
import sys
from pathlib import Path


def reload_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "dummy")
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "slack_sdk.web.client.WebClient.auth_test",
        lambda self, **kwargs: {"ok": True},
        raising=False,
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_load_state_clamps_and_persists_invalid_index(tmp_path, monkeypatch):
    app = reload_app(monkeypatch, tmp_path)
    state_file = os.path.join(tmp_path, "rotation_state.json")
    # Write invalid index to state
    with open(state_file, "w") as fp:
        json.dump({"current_index": "not-a-number", "team_members": ["U1", "U2"]}, fp)

    idx = app.load_state()
    assert idx == 0

    # Ensure it was persisted as numeric 0
    with open(state_file, "r") as fp:
        data = json.load(fp)
    assert data["current_index"] == 0
    assert data["current_assignee_index"] == 0
    assert data["team_members"] == ["U1", "U2"]


def test_rotation_list_marks_current_and_next(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAM_MEMBERS", "U1,U2,U3")
    app = reload_app(monkeypatch, tmp_path)
    state_file = os.path.join(tmp_path, "rotation_state.json")
    with open(state_file, "w") as fp:
        json.dump(
            {
                "current_index": 1,
                "current_assignee_index": 0,
                "team_members": ["U1", "U2", "U3"],
            },
            fp,
        )

    responses = []
    app.handle_rotation_command(
        lambda: None,
        {"text": "list"},
        responses.append,
        app.logger,
    )

    assert responses
    assert responses[0] == "1. <@U1> (current)\n2. <@U2> (next)\n3. <@U3>"
