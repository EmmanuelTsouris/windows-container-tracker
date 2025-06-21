import pytest
import json
import os
import sys
from unittest.mock import patch, MagicMock

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

def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError):
        check_windows_containers.load_config("nonexistent.json")

def test_load_config_bad_json(tmp_path):
    config_file = tmp_path / "bad.json"
    config_file.write_text("{bad json}")
    with pytest.raises(Exception):
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
    mock_get.side_effect = [
        type("resp", (), {
            "json": lambda self=None: {"tags": ["latest"]},
            "raise_for_status": lambda self=None: None,
            "status_code": 200,
        })(),
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

def test_check_images_no_tags(monkeypatch, capsys):
    repos = ["repo3"]
    old_state = {}
    def fake_get_latest_tag_info(repo):
        return None
    monkeypatch.setattr(check_windows_containers, "get_latest_tag_info", fake_get_latest_tag_info)
    new_state, updates = check_windows_containers.check_images(repos, old_state)
    out = capsys.readouterr()
    assert "No tags found for repo3" in out.out

def test_main_runs(monkeypatch, tmp_path, capsys):
    # Set up a config file
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"
    # Patch to return the same state, so no updates
    monkeypatch.setattr("check_windows_containers.get_latest_tag_info",
                        lambda repo: {"tag": "latest", "digest": "abc", "last_modified": "now"})
    # Write existing state to match output
    state_file.write_text(json.dumps({"repo1": {"tag": "latest", "digest": "abc", "last_modified": "now"}}))
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "No changes detected." in out.out

def test_main_detects_changes(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"
    # Existing state to force an update
    state_file.write_text(json.dumps({"repo1": {"tag": "latest", "digest": "old", "last_modified": "yesterday"}}))
    monkeypatch.setattr("check_windows_containers.get_latest_tag_info",
                        lambda repo: {"tag": "latest", "digest": "new", "last_modified": "now"})
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "Changes detected:" in out.out

def test_main_config_load_failure(tmp_path, capsys):
    config_file = tmp_path / "missing.json"
    state_file = tmp_path / "state.json"
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "Failed to load config" in out.out

def test_main_save_state_failure(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"
    monkeypatch.setattr("check_windows_containers.get_latest_tag_info",
                        lambda repo: {"tag": "latest", "digest": "abc", "last_modified": "now"})
    # Patch save_state to throw
    def fail(*args, **kwargs):
        raise Exception("save error")
    monkeypatch.setattr("check_windows_containers.save_state", fail)
    with pytest.raises(Exception):
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

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_load_state_s3_success(mock_boto):
    # Setup S3 mock with get_object returning json
    mock_s3 = MagicMock()
    # Simulate boto3's NoSuchKey
    class NoSuchKey(Exception): pass
    mock_s3.exceptions = MagicMock()
    mock_s3.exceptions.NoSuchKey = NoSuchKey
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b'{"foo": "bar"}')}
    mock_boto.return_value = mock_s3
    state = check_windows_containers.load_state("windows_container_state.json")
    assert state == {"foo": "bar"}

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_load_state_s3_nosuchkey(mock_boto):
    # Setup S3 mock with get_object raising NoSuchKey
    mock_s3 = MagicMock()
    class NoSuchKey(Exception): pass
    mock_s3.exceptions = MagicMock()
    mock_s3.exceptions.NoSuchKey = NoSuchKey
    mock_s3.get_object.side_effect = NoSuchKey
    mock_boto.return_value = mock_s3
    state = check_windows_containers.load_state("windows_container_state.json")
    assert state == {}

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_load_state_s3_other_exception(mock_boto):
    # Setup S3 mock with get_object raising generic Exception
    mock_s3 = MagicMock()
    class NoSuchKey(Exception): pass
    mock_s3.exceptions = MagicMock()
    mock_s3.exceptions.NoSuchKey = NoSuchKey
    mock_s3.get_object.side_effect = Exception("Some other error")
    mock_boto.return_value = mock_s3
    state = check_windows_containers.load_state("windows_container_state.json")
    assert state == {}

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_save_state_s3_success(mock_boto):
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3
    state = {"foo": "bar"}
    check_windows_containers.save_state(state, "windows_container_state.json")
    assert mock_s3.put_object.called

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_save_state_s3_error(mock_boto):
    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = Exception("fail")
    mock_boto.return_value = mock_s3
    state = {"foo": "bar"}
    check_windows_containers.save_state(state, "windows_container_state.json")

def test_main_entrypoint(monkeypatch, tmp_path):
    # This test spawns the script as a subprocess to exercise __main__ block (line 148)
    import subprocess
    test_file = os.path.abspath(check_windows_containers.__file__)
    config_file = tmp_path / "config.json"
    state_file = tmp_path / "state.json"
    config_file.write_text('{"repos": []}')
    result = subprocess.run([sys.executable, test_file, str(config_file), str(state_file)], capture_output=True, text=True)
    assert "Checking Microsoft Windows container images" in result.stdout

@patch("check_windows_containers.requests.get")
def test_get_latest_tag_info_no_tags(mock_get):
    # First call: tags API returns empty list
    mock_get.side_effect = [
        type("resp", (), {
            "json": lambda self=None: {"tags": []},
            "raise_for_status": lambda self=None: None,
            "status_code": 200,
        })()
    ]
    info = check_windows_containers.get_latest_tag_info("repo_no_tags")
    assert info is None

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_load_state_s3_outage(mock_boto, capsys):
    # Simulate S3 client raising a connection error
    mock_s3 = MagicMock()
    class NoSuchKey(Exception): pass
    mock_s3.exceptions = MagicMock()
    mock_s3.exceptions.NoSuchKey = NoSuchKey
    mock_s3.get_object.side_effect = Exception("S3 outage")
    mock_boto.return_value = mock_s3

    state = check_windows_containers.load_state("windows_container_state.json")
    assert state == {}
    captured = capsys.readouterr()
    assert "Error loading state from S3" in captured.out or "S3 outage" in captured.out

@patch.dict(os.environ, {"STATE_BACKEND": "s3", "S3_BUCKET": "the-bucket"})
@patch("boto3.client")
def test_save_state_s3_outage(mock_boto, capsys):
    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = Exception("S3 outage")
    mock_boto.return_value = mock_s3

    state = {"foo": "bar"}
    check_windows_containers.save_state(state, "windows_container_state.json")
    captured = capsys.readouterr()
    assert "Error saving state to S3" in captured.out or "S3 outage" in captured.out
