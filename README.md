# Windows Container Image Checker

![Python package](https://github.com/EmmanuelTsouris/windows-container-tracker/actions/workflows/python-tests.yml/badge.svg)

A script and AWS Lambda function to monitor Microsoft Windows container images on MCR, compare tags/digests, and report new or updated images.

---

## Features

- Checks a list of Windows container image repositories for updates
- Compares latest tags and digests
- Reports new images or updates since last run
- Can run locally (for development/testing) or as a scheduled AWS Lambda function (for production)
- Robust error handling and state persistence (local or S3)

---

## Architecture

Below is the architecture for both local development and AWS Lambda production deployments:

```mermaid
flowchart TD
  subgraph AWS_Production
    EventBridge(("EventBridge
(CloudWatch Events)"))
    LambdaFunction([Lambda Function])
    S3(("S3 Bucket
State Storage"))
    EventBridge --> LambdaFunction
    LambdaFunction -- load/save state --> S3
  end
  subgraph Local_Dev
    Script([Local Script])
    StateFile(("Local JSON State File"))
    Script -- load/save state --> StateFile
  end
```

- **Production:**
  EventBridge triggers the Lambda function on a schedule. Lambda loads the previous state from S3, checks for image updates, and saves the new state back to S3.
- **Development:**
  The script can be run locally, reading and writing state from a local JSON file.

---

## Configuration

1. **Configuration File:**
   Define the repositories to track in `config.json`:

   ```json
   {
     "repos": [
       "windows/servercore",
       "windows/nanoserver"
     ]
   }
   ```

   You may also specify tag patterns to track (wildcards supported):

   ```json
   {
     "repos": [
       { "name": "windows/servercore", "tags": ["ltsc2022-*"] },
       "windows/nanoserver"
     ]
   }
   ```

2. **State Storage:**
   - **Local/Dev:** State (i.e., previous check results) is stored as a JSON file (`windows_container_state.json`) in the working directory.
   - **Production (Lambda):** State is stored in an S3 bucket as an object. The backend is switched using the `STATE_BACKEND` environment variable.

---

## Running Locally (Development / Testing)

- By default, the script will load/save state to a local JSON file.
- No AWS setup is required.
- Run with:
  ```sh
  python check_windows_containers.py
  ```

### Sample Output

When new container images are available:

```text
Checking Microsoft Windows container images at 2025-06-21T06:42:42.901613Z
Changes detected:
  [NEW TAG] windows/server:some-tag digest=sha256:d0b929fbf30696db7cfa6af63cbfaa54964c2c583b6a77c934f015b5f3117fd1
```

When there are no changes:

```text
Checking Microsoft Windows container images at 2025-06-21T06:42:42.842400Z
No changes detected.
```

---

## Running in AWS Lambda (Production)

### 1. **Switch to S3 State Backend**

For production/Lambda deployments, use the S3 backend for state storage by setting the `STATE_BACKEND` environment variable to `s3`.

- The script will automatically use S3 if the `STATE_BACKEND` environment variable is set to `s3` (and required S3 variables are set).
- Do not leave local JSON-based state code in your Lambda deployment unless you need it for debugging.

### 2. **Environment Variables**

Set these Lambda environment variables:

| Name           | Description                               | Example                        |
|----------------|-------------------------------------------|--------------------------------|
| `STATE_BACKEND`| Must be `s3` to use S3 for state          | `s3`                           |
| `S3_BUCKET`    | Name of the S3 bucket for state storage   | `my-container-state-bucket`    |
| `STATE_KEY`    | (Optional) S3 object key for the state    | `windows_container_state.json` |

### 3. **IAM Permissions**

The Lambda execution role must have permissions for:
- `s3:GetObject`
- `s3:PutObject`
- (optionally) `s3:ListBucket`
for your chosen S3 bucket.

### 4. **Scheduling**

- Use Amazon EventBridge (CloudWatch Events) to trigger the Lambda on a schedule (e.g., every 4 hours).

### 5. **Lambda Handler Example**

Your Lambda function entry point is:
```python
def lambda_handler(event, context):
    # config_path and state_file are set from environment or defaults
    main()
    return {"status": "completed"}
```
**Make sure to set the environment variables as above for S3 state.**

---

## Notes

- The script and Lambda function are designed for both local and production use-cases. **Production should use S3 for state.**
- When testing new features or debugging, use the local backend and then switch to S3 before deploying.

---

## Versioning

- See [Releases](https://github.com/EmmanuelTsouris/windows-container-tracker/releases) for tagged versions.
- Latest patch release: **v1.0.1** (bugfixes, improved error handling, and complete test coverage).

---

## License

[MIT](LICENSE)
