import requests
import json
import os
from datetime import datetime

CONFIG_FILE = "config.json"
STATE_FILE = "windows_container_state.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Config file '{CONFIG_FILE}' not found. Please create it with a 'repos' key.")
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
        repos = data.get("repos")
        if not repos or not isinstance(repos, list):
            raise ValueError("Config file must contain a 'repos' key with a list of repository names.")
        return repos

def get_latest_tag_info(repo):
    """
    Get the latest tag and its digest for a given Microsoft Container Registry repo.
    Uses the Docker Registry HTTP API v2.
    """
    tags_url = f"https://mcr.microsoft.com/v2/{repo}/tags/list"
    try:
        tags_resp = requests.get(tags_url, timeout=10)
        tags_resp.raise_for_status()
        tags_data = tags_resp.json()
        tags = tags_data.get("tags", [])
        if not tags:
            return None
        # Sort tags, try to get 'latest' or highest version
        sorted_tags = sorted(tags, reverse=True)
        tag = sorted_tags[0]
        manifest_url = f"https://mcr.microsoft.com/v2/{repo}/manifests/{tag}"
        headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
        manifest_resp = requests.get(manifest_url, headers=headers, timeout=10)
        manifest_resp.raise_for_status()
        digest = manifest_resp.headers.get("Docker-Content-Digest")
        last_modified = manifest_resp.headers.get("Last-Modified")
        return {
            "tag": tag,
            "digest": digest,
            "last_modified": last_modified
        }
    except Exception as e:
        print(f"Error fetching {repo}: {e}")
        return None

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def main():
    print(f"Checking Microsoft Windows container images at {datetime.utcnow().isoformat()}Z")
    try:
        repos = load_config()
    except Exception as e:
        print(f"Failed to load config: {e}")
        return

    old_state = load_state()
    new_state = {}
    updates = []

    for repo in repos:
        info = get_latest_tag_info(repo)
        if info:
            new_state[repo] = info
            old_info = old_state.get(repo)
            if not old_info:
                updates.append(f"[NEW] {repo}: tag={info['tag']}, digest={info['digest']}")
            elif info["digest"] != old_info.get("digest"):
                updates.append(f"[UPDATED] {repo}: tag={info['tag']}, new digest={info['digest']} (was {old_info.get('digest')})")
        else:
            print(f"  - No tags found for {repo} or error occurred.")

    if updates:
        print("Changes detected:")
        for update in updates:
            print(" ", update)
    else:
        print("No changes detected.")

    save_state(new_state)

if __name__ == "__main__":
    main()
