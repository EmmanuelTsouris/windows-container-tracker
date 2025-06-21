import pytest
import json
import os
import sys
from unittest.mock import patch, MagicMock

import check_windows_containers
import requests

def test_load_config_valid(tmp_path):
    config_content = {"repos": ["repo1", "repo2"]}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_content))
    repos = check_windows_containers.load_config(str(config_file))
    assert repos == [
        {"name": "repo1", "tags": None},
        {"name": "repo2", "tags": None}
    ]

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

def test_load_config_invalid_entry(tmp_path):
    config_content = {"repos": [123, {"foo": "bar"}]}
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
    repos = [{"name": "windows/server", "tags": ["ltsc2022-*"]}]
    old_state = {
        "windows/server": {
            "ltsc2022-KB5060526-amd64": {
                "digest": "sha256:fbf703c0efa6803f9625e654aec6b337aecb3cac8280a0c4549db383d206f6cb",
                "last_modified": None,
            },
            "ltsc2022-KB5022842-amd64": {
                "digest": "sha256:99e777ead9061f5568a2280cc91787c9494e64e8d40f6af8035b73c86de3bbcd",
                "last_modified": None,
            },
            "not_found": ["ltsc2022-KB404404-amd64"]
        }
    }
    current_tags = [
        "ltsc2022-KB5060526-amd64",
        "ltsc2022-KB5022842-amd64",
        "ltsc2022-KB5077777-amd64",
        "ltsc2022-KB404404-amd64",
    ]
    monkeypatch.setattr("check_windows_containers.get_tags", lambda repo: current_tags)
    def fake_get_tag_info(repo, tag):
        if tag == "ltsc2022-KB5060526-amd64":
            return {"digest": "sha256:fbf703c0efa6803f9625e654aec6b337aecb3cac8280a0c4549db383d206f6cb", "last_modified": "2025-01-01"}
        if tag == "ltsc2022-KB5022842-amd64":
            return {"digest": "sha256:UPDATEDdigest", "last_modified": "2025-06-21"}
        if tag == "ltsc2022-KB5077777-amd64":
            return {"digest": "sha256:NEWdigest", "last_modified": "2025-06-21"}
        if tag == "ltsc2022-KB404404-amd64":
            return "NOT_FOUND"
        return None
    monkeypatch.setattr("check_windows_containers.get_tag_info", fake_get_tag_info)
    new_state, updates = check_windows_containers.check_images(repos, old_state)
    assert any("[NEW TAG] windows/server:ltsc2022-KB5077777-amd64" in u for u in updates)
    assert any("[UPDATED DIGEST] windows/server:ltsc2022-KB5022842-amd64" in u for u in updates)
    assert not any("[UPDATED DIGEST] windows/server:ltsc2022-KB5060526-amd64" in u for u in updates)
    assert "ltsc2022-KB404404-amd64" in new_state["windows/server"]["not_found"]
    assert new_state["windows/server"]["ltsc2022-KB5077777-amd64"]["digest"] == "sha256:NEWdigest"
    assert new_state["windows/server"]["ltsc2022-KB5022842-amd64"]["digest"] == "sha256:UPDATEDdigest"

def test_check_images_no_tags(monkeypatch, capsys):
    repos = [{"name": "repo3", "tags": None}]
    old_state = {}
    # Patch get_tags to raise Exception to simulate error
    def fake_get_tags(repo):
        raise Exception("Something went wrong with tags")
    monkeypatch.setattr(check_windows_containers, "get_tags", fake_get_tags)
    new_state, updates = check_windows_containers.check_images(repos, old_state)
    out = capsys.readouterr()
    assert "Error fetching tags for repo3" in out.out

def test_get_tag_info_http_error_not_404(monkeypatch):
    class MockResponse:
        status_code = 500
        def raise_for_status(self):
            raise requests.exceptions.HTTPError("500 error")
        headers = {}
    monkeypatch.setattr("check_windows_containers.requests.get", lambda *a, **kw: MockResponse())
    assert check_windows_containers.get_tag_info("repo", "tag") is None

def test_get_tag_info_generic_exception(monkeypatch):
    def raise_exc(*a, **kw):
        raise Exception("unexpected")
    monkeypatch.setattr("check_windows_containers.requests.get", raise_exc)
    assert check_windows_containers.get_tag_info("repo", "tag") is None

def test_get_latest_tag_info_no_matching(monkeypatch, capsys):
    monkeypatch.setattr(check_windows_containers, "get_tags", lambda repo: [])
    info = check_windows_containers.get_latest_tag_info("repo", "pattern*")
    captured = capsys.readouterr()
    assert "No tags found" in captured.out
    assert info is None

def test_get_latest_tag_info_tag_info_missing(monkeypatch, capsys):
    monkeypatch.setattr(check_windows_containers, "get_tags", lambda repo: ["foo"])
    monkeypatch.setattr(check_windows_containers, "get_tag_info", lambda repo, tag: None)
    info = check_windows_containers.get_latest_tag_info("repo", "*")
    captured = capsys.readouterr()
    assert "Could not fetch info" in captured.out
    assert info is None

def test_get_tags_exception(monkeypatch, capsys):
    def raise_exc(*a, **kw):
        raise Exception("fail")
    monkeypatch.setattr("check_windows_containers.requests.get", raise_exc)
    tags = check_windows_containers.get_tags("repo")
    captured = capsys.readouterr()
    assert "Error fetching tags" in captured.out
    assert tags == []

def test_expand_wildcard_tags_exact():
    available = ["foo", "bar"]
    patterns = ["foo"]
    res = check_windows_containers.expand_wildcard_tags(available, patterns)
    assert "foo" in res and len(res) == 1

def test_main_save_state_exception(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"
    monkeypatch.setattr("check_windows_containers.check_images",
                        lambda repos, state: (state, ["[UPDATED DIGEST] repo1:latest new digest=new (was old)"]))
    monkeypatch.setattr("check_windows_containers.save_state", lambda *a, **kw: (_ for _ in ()).throw(Exception("fail")))
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "Error saving state" in out.out

def test_main_runs(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(check_windows_containers, "check_images", lambda repos, state: (state, []))
    state_file.write_text(json.dumps({"repo1": {"tag": "latest", "digest": "abc", "last_modified": "now"}}))
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "No changes detected." in out.out

def test_main_detects_changes(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"repos": ["repo1"]}')
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"repo1": {"tag": "latest", "digest": "old", "last_modified": "yesterday"}}))
    def fake_check_images(repos, state):
        return ({"repo1": {"tag": "latest", "digest": "new", "last_modified": "now"}}, ["[UPDATED DIGEST] repo1:latest new digest=new (was old)"])
    monkeypatch.setattr(check_windows_containers, "check_images", fake_check_images)
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "Changes detected:" in out.out

def test_main_config_load_failure(tmp_path, capsys):
    config_file = tmp_path / "missing.json"
    state_file = tmp_path / "state.json"
    check_windows_containers.main(str(config_file), str(state_file))
    out = capsys.readouterr()
    assert "Failed to load config" in out.out

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
    mock_s3 = MagicMock()
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
    import subprocess
    test_file = os.path.abspath(check_windows_containers.__file__)
    config_file = tmp_path / "config.json"
    state_file = tmp_path / "state.json"
    config_file.write_text('{"repos": []}')
    result = subprocess.run([sys.executable, test_file, str(config_file), str(state_file)], capture_output=True, text=True)
    assert "Checking Microsoft Windows container images" in result.stdout

@patch("check_windows_containers.requests.get")
def test_get_latest_tag_info_no_tags(mock_get):
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
