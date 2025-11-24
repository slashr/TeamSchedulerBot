import importlib
import json
import os
import sys


def reload_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "dummy")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "dummy")
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
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
    assert data["team_members"] == ["U1", "U2"]
