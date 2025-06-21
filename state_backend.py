import os
import json

def load_state(state_file="windows_container_state.json"):
    """
    Load state from local file (for dev/test) or S3 (for Lambda/prod).
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
    else:
        # Fallback: Local file
        if not os.path.exists(state_file):
            return {}
        with open(state_file, "r") as f:
            return json.load(f)

def save_state(state, state_file="windows_container_state.json"):
    """
    Save state to local file (for dev/test) or S3 (for Lambda/prod).
    """
    backend = os.environ.get("STATE_BACKEND", "local")
    if backend == "s3":
        import boto3
        s3 = boto3.client("s3")
        bucket = os.environ["S3_BUCKET"]
        key = os.environ.get("STATE_KEY", state_file)
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(state).encode("utf-8"))
    else:
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)