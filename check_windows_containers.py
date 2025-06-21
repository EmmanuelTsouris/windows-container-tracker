import requests
import json
import os
from datetime import datetime

def load_config(config_path="config.json"):
    """
    Load the list of repositories from the config file.
    Raises an error if the file is missing or invalid.
    """
    with open(config_path, "r") as f:
        data = json.load(f)
        repos = data.get("repos")
        if not repos or not isinstance(repos, list):
            raise ValueError("Config file must contain a 'repos' key with a list of repository names.")
        return repos

def get_latest_tag_info(repo):
    """
    Fetch the latest tag, digest, and last-modified headers for a given repo.
    Returns None if no tags are found or an error occurs.
    """
    tags_url = f"https://mcr.microsoft.com/v2/{repo}/tags/list"
    try:
        tags_resp = requests.get(tags_url, timeout=10)
        tags_resp.raise_for_status()
        tags_data = tags_resp.json()
        tags = tags_data.get("tags", [])
        if not tags:
            return None
        # Sort tags to get the latest (highest) one
        sorted_tags = sorted(tags, reverse=True)
        tag = sorted_tags[0]
        manifest_url = f"https://mcr.microsoft.com/v2/{repo}/manifests/{tag}"
        headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
        manifest_resp = requests.get(manifest_url, headers=headers, timeout=10)
        manifest_resp.raise_for_status()
        digest = manifest_resp.headers.get("Docker-Content-Digest")
        last_modified = manifest_resp.headers.get("Last-Modified")
        return {"tag": tag, "digest": digest, "last_modified": last_modified}
    except Exception as e:
        print(f"Error fetching {repo}: {e}")
        return None

# State backend supporting local file (default) and S3 (for Lambda/deployment)
def load_state(state_file="windows_container_state.json"):
    """
    Load the previous state from local disk or S3, depending on environment variable STATE_BACKEND.
    """
    backend = os.environ.get("STATE_BACKEND", "local")
    if backend == "s3":
        import boto3
        s3 = boto3.client("s3")
        bucket = os.environ["S3_BUCKET"]
        key = os.environ.get("STATE_KEY", state_file)
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(obj["Body"].read())
        except s3.exceptions.NoSuchKey:
            return {}
        except Exception as e:
            print(f"Error loading state from S3: {e}")
            return {}
    else:
        # Local file fallback (dev/test)
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                return json.load(f)
        return {}

def save_state(state, state_file="windows_container_state.json"):
    """
    Save state to local disk or S3, depending on environment variable STATE_BACKEND.
    """
    backend = os.environ.get("STATE_BACKEND", "local")
    if backend == "s3":
        import boto3
        s3 = boto3.client("s3")
        bucket = os.environ["S3_BUCKET"]
        key = os.environ.get("STATE_KEY", state_file)
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(state, indent=2).encode("utf-8"))
        except Exception as e:
            print(f"Error saving state to S3: {e}")
    else:
        # Write to local JSON file
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

def check_images(repos, old_state):
    """
    For each repo, get latest info and compare with previous state.
    Returns new_state and any updates found.
    """
    new_state = {}
    updates = []
    for repo in repos:
        info = get_latest_tag_info(repo)
        if info:
            new_state[repo] = info
            old_info = old_state.get(repo)
            if not old_info:
                # New repository detected (not seen before)
                updates.append(f"[NEW] {repo}: tag={info['tag']}, digest={info['digest']}")
            elif info["digest"] != old_info.get("digest"):
                # Digest has changed for this repo
                updates.append(f"[UPDATED] {repo}: tag={info['tag']}, new digest={info['digest']} (was {old_info.get('digest')})")
        else:
            print(f"  - No tags found for {repo} or error occurred.")
    return new_state, updates

def main(config_path="config.json", state_file="windows_container_state.json"):
    """
    Main entrypoint for local execution.
    Loads config, loads previous state, checks for image updates, saves new state.
    """
    print(f"Checking Microsoft Windows container images at {datetime.utcnow().isoformat()}Z")
    try:
        repos = load_config(config_path)
    except Exception as e:
        print(f"Failed to load config: {e}")
        return

    old_state = load_state(state_file)
    new_state, updates = check_images(repos, old_state)

    if updates:
        print("Changes detected:")
        for update in updates:
            print(" ", update)
    else:
        print("No changes detected.")

    save_state(new_state, state_file)

# Lambda entry point
def lambda_handler(event, context):
    """
    Lambda-compatible entrypoint.
    Uses environment variables for config and state paths.
    """
    config_path = os.environ.get("CONFIG_PATH", "config.json")
    state_file = os.environ.get("STATE_FILE", "windows_container_state.json")
    main(config_path, state_file)
    return {"status": "completed"}

if __name__ == "__main__":
    main()
