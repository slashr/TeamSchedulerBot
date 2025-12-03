import json
import importlib
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


def test_state_write_creates_backup(tmp_path, monkeypatch):
    app = reload_app(monkeypatch, tmp_path)
    original = {"current_index": 0, "current_assignee_index": 0, "team_members": ["U1", "U2", "U3"]}
    with open(app.STATE_FILE, "w") as fp:
        json.dump(original, fp)

    with app.state_lock:
        app._write_state_locked(1, assignee_idx=1)

    with open(f"{app.STATE_FILE}.bak", "r") as fp:
        backup_data = json.load(fp)

    with open(app.STATE_FILE, "r") as fp:
        new_data = json.load(fp)

    assert backup_data == original
    assert new_data["current_index"] == 1
    assert new_data["current_assignee_index"] == 1


def test_state_write_restores_backup_on_failure(tmp_path, monkeypatch):
    app = reload_app(monkeypatch, tmp_path)
    original = {"current_index": 0, "current_assignee_index": 0, "team_members": ["U1", "U2", "U3"]}
    with open(app.STATE_FILE, "w") as fp:
        json.dump(original, fp)

    replace_calls = {"count": 0}
    real_replace = app.os.replace

    def flaky_replace(src, dst):
        replace_calls["count"] += 1
        # Fail when replacing the temp file, succeed when restoring from .bak
        if not src.endswith(".bak"):
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(app.os, "replace", flaky_replace)

    try:
        with app.state_lock:
            app._write_state_locked(2, assignee_idx=2)
    except OSError:
        pass

    with open(app.STATE_FILE, "r") as fp:
        restored = json.load(fp)

    assert restored == original
    assert replace_calls["count"] >= 1
