import os
import json
import boto3

S3_BUCKET = os.environ["S3_BUCKET"]                  # Must be set in Lambda environment variables
STATE_KEY = os.environ.get("STATE_KEY", "windows_container_state.json")  # Optional, defaults to file name

def load_state():
    """
    Load state from S3 as a JSON object.
    Returns an empty dict if the object does not exist.
    """
    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=STATE_KEY)
        return json.loads(obj["Body"].read())
    except s3.exceptions.NoSuchKey:
        # State file does not exist yet
        return {}
    except Exception as e:
        print(f"Error loading state from S3: {e}")
        return {}

def save_state(state):
    """
    Save state as a JSON object to S3.
    """
    s3 = boto3.client("s3")
    try:
        s3.put_object(Bucket=S3_BUCKET, Key=STATE_KEY, Body=json.dumps(state, indent=2).encode("utf-8"))
    except Exception as e:
        print(f"Error saving state to S3: {e}")