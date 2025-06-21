import pytest
import json
import os
from unittest.mock import patch, mock_open

import check_windows_containers

def test_load_config_valid(tmp_path):
    config_content = {"repos": ["repo1", "repo2"]}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_content))
    repos = check_windows_containers.load_config(str(config_file))
    assert repos == ["repo1", "repo2"]

def test_load_config_missing_key(tmp_path):
    config_content = {}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_content))
    with pytest.raises(ValueError):
        check_windows_containers.load_config(str(config_file))

def test_load_state_nonexistent(tmp_path):
    state_file = tmp_path / "nonexistent.json"
    state = check_windows_containers.load_state(str(state_file))
    assert state == {}

def test_load_state_existing(tmp_path):
    state_content = {"repo1": {"tag": "latest", "digest": "abc"}}
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state_content))
    state = check_windows_containers.load_state(str(state_file))
    assert state == state_content

def test_save_state(tmp_path):
    state = {"repo1": {"tag": "latest", "digest": "abc"}}
    state_file = tmp_path / "state.json"
    check_windows_containers.save_state(state, str(state_file))
    loaded = json.loads(state_file.read_text())
    assert loaded == state

@patch("check_windows_containers.requests.get")
def test_get_latest_tag_info_success(mock_get):
    # Mock tags response then manifest response
    mock_get.side_effect = [
        # tags response
        type("resp", (), {
            "json": lambda self=None: {"tags": ["latest"]},
            "raise_for_status": lambda self=None: None,
            "status_code": 200,
        })(),
        # manifest response
        type("resp", (), {
            "headers": {"Docker-Content-Digest": "digest123", "Last-Modified": "yesterday"},
            "raise_for_status": lambda self=None: None,
            "status_code": 200,
        })()
    ]
    info = check_windows_containers.get_latest_tag_info("repo1")
    assert info["tag"] == "latest"
    assert info["digest"] == "digest123"
    assert info["last_modified"] == "yesterday"

@patch("check_windows_containers.requests.get")
def test_get_latest_tag_info_failure(mock_get):
    # Simulate 404 error
    class MockResponse:
        def raise_for_status(self): raise Exception("404")
    mock_get.return_value = MockResponse()
    info = check_windows_containers.get_latest_tag_info("repo404")
    assert info is None

def test_check_images_new_and_updated(monkeypatch):
    repos = ["repo1", "repo2"]
    old_state = {"repo2": {"tag": "old", "digest": "digestA"}}

    def fake_get_latest_tag_info(repo):
        if repo == "repo1":
            return {"tag": "latest", "digest": "digestB", "last_modified": "now"}
        if repo == "repo2":
            return {"tag": "latest", "digest": "digestC", "last_modified": "now"}
        return None

    monkeypatch.setattr(check_windows_containers, "get_latest_tag_info", fake_get_latest_tag_info)
    new_state, updates = check_windows_containers.check_images(repos, old_state)
    assert any("[NEW] repo1:" in u for u in updates)
    assert any("[UPDATED] repo2:" in u for u in updates)
    assert "repo1" in new_state and "repo2" in new_state

def test_main_runs(monkeypatch, tmp_path):
    # Set up a config file
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"

    # Patch functions to not actually call network
    monkeypatch.setattr("check_windows_containers.get_latest_tag_info", lambda repo: {"tag": "latest", "digest": "abc", "last_modified": "now"})
    check_windows_containers.main(str(config_file), str(state_file))

def test_lambda_handler(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"

    monkeypatch.setenv("CONFIG_PATH", str(config_file))
    monkeypatch.setenv("STATE_FILE", str(state_file))
    monkeypatch.setattr("check_windows_containers.main", lambda config, state: None)
    result = check_windows_containers.lambda_handler({}, {})
    assert result == {"status": "completed"}
