import requests
import json
import os
from datetime import datetime
import fnmatch

def load_config(config_path="config.json"):
    with open(config_path, "r") as f:
        data = json.load(f)
        repos = data.get("repos")
        if not repos or not isinstance(repos, list):
            raise ValueError("Config file must contain a 'repos' key with a list of repository names or objects.")
        normalized = []
        for entry in repos:
            if isinstance(entry, str):
                normalized.append({"name": entry, "tags": None})
            elif isinstance(entry, dict) and "name" in entry:
                normalized.append({"name": entry["name"], "tags": entry.get("tags")})
            else:
                raise ValueError("Each repo entry must be a string or a dict with at least a 'name' key.")
        return normalized

def get_tag_info(repo, tag):
    manifest_url = f"https://mcr.microsoft.com/v2/{repo}/manifests/{tag}"
    headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    try:
        resp = requests.get(manifest_url, headers=headers, timeout=10)
        resp.raise_for_status()
        digest = resp.headers.get("Docker-Content-Digest")
        last_modified = resp.headers.get("Last-Modified")
        return {"digest": digest, "last_modified": last_modified}
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 404:
            return "NOT_FOUND"
        print(f"Error fetching {repo}:{tag}: {e}")
        return None
    except Exception as e:
        print(f"Error fetching {repo}:{tag}: {e}")
        return None

def get_latest_tag_info(repo, pattern="*"):
    """
    Returns info for the latest tag matching the pattern for the given repo.
    """
    tags = get_tags(repo)
    import fnmatch
    matching = sorted([t for t in tags if fnmatch.fnmatch(t, pattern)])
    if not matching:
        print(f"No tags found for {repo} matching pattern '{pattern}'")
        return None
    latest_tag = matching[-1]
    info = get_tag_info(repo, latest_tag)
    if not info or info == "NOT_FOUND":
        print(f"Could not fetch info for latest tag {latest_tag} in {repo}")
        return None
    return {"tag": latest_tag, "digest": info["digest"], "last_modified": info["last_modified"]}

def get_tags(repo):
    tags_url = f"https://mcr.microsoft.com/v2/{repo}/tags/list"
    try:
        resp = requests.get(tags_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("tags", [])
    except Exception as e:
        print(f"Error fetching tags for {repo}: {e}")
        return []

def expand_wildcard_tags(available_tags, patterns):
    if not patterns:
        return available_tags
    selected = set()
    for pat in patterns:
        if "*" in pat or "?" in pat:
            selected.update(t for t in available_tags if fnmatch.fnmatch(t, pat))
        else:
            if pat in available_tags:
                selected.add(pat)
    return list(selected)

def load_state(state_file="windows_container_state.json"):
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
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                return json.load(f)
        return {}

def save_state(state, state_file="windows_container_state.json"):
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
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

def check_images(repos, old_state):
    """
    For each repo, check user-specified tags (including wildcards) if present; else, all tags.
    Avoid rechecking tags that previously returned 404 (stored in not_found).
    Returns new_state and any updates found.
    """
    new_state = {}
    updates = []
    for repo_entry in repos:
        repo_name = repo_entry["name"]
        specified_tags = repo_entry.get("tags")
        repo_state = old_state.get(repo_name, {})
        try:
            available_tags = get_tags(repo_name)
        except Exception as e:
            print(f"Error fetching tags for {repo_name}: {e}")
            available_tags = []
        not_found = set(repo_state.get("not_found", []))  # tags previously found to be 404

        tags_to_check = expand_wildcard_tags(available_tags, specified_tags) if specified_tags else available_tags
        tags_to_check = [t for t in tags_to_check if t not in not_found]

        new_repo_state = {k: v for k, v in repo_state.items() if k != "not_found"}  # Copy old state except not_found
        new_not_found = set(not_found)
        found_this_run = set()

        for tag in tags_to_check:
            old_tag = repo_state.get(tag)
            info = get_tag_info(repo_name, tag)
            if info and info != "NOT_FOUND":
                # If it was previously in not_found but is now available, remove from not_found
                found_this_run.add(tag)
                if tag in new_not_found:
                    new_not_found.remove(tag)
                if not old_tag:
                    updates.append(f"[NEW TAG] {repo_name}:{tag} digest={info['digest']}")
                elif info["digest"] != old_tag.get("digest"):
                    updates.append(f"[UPDATED DIGEST] {repo_name}:{tag} new digest={info['digest']} (was {old_tag.get('digest')})")
                new_repo_state[tag] = info
            elif info == "NOT_FOUND":
                # Only log the first time we see the 404 for this tag
                if tag not in not_found:
                    print(f"404 NOT FOUND: {repo_name}:{tag}")
                new_not_found.add(tag)

        # Always remove any tags from not_found that are no longer in the expanded tag list (i.e., they've been deleted upstream)
        new_not_found = {t for t in new_not_found if t in available_tags}
        # Save the updated not_found list
        new_repo_state["not_found"] = sorted(list(new_not_found))
        new_state[repo_name] = new_repo_state
    return new_state, updates

def main(config_path="config.json", state_file="windows_container_state.json"):
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

    try:
        save_state(new_state, state_file)
    except Exception as e:
        print(f"Error saving state: {e}")

def lambda_handler(event, context):
    config_path = os.environ.get("CONFIG_PATH", "config.json")
    state_file = os.environ.get("STATE_FILE", "windows_container_state.json")
    main(config_path, state_file)
    return {"status": "completed"}

if __name__ == "__main__":
    main()
