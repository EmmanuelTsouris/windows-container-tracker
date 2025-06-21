# Windows Container Tracker

A Python utility to monitor official Microsoft Windows container images on [MCR](https://mcr.microsoft.com/) (Microsoft Container Registry).  
It tracks the latest tags and digests for selected images, making it easy to see when a new Windows base image (such as `servercore` or `nanoserver`) is published.

## Features

- Tracks a customizable list of Microsoft Windows container images.
- Compares current and previous state to detect new tags or updated images.
- Stores state in a local JSON file (`windows_container_state.json`).
- Reports changes between runs.
- Easy to schedule for daily or periodic checks.

## Requirements

- Python 3.7+
- [requests](https://pypi.org/project/requests/) library

Install requirements with:

```bash
pip install requests
```

## Usage

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/windows-container-tracker.git
   cd windows-container-tracker
   ```

2. (Optional) Edit the list of tracked container images in the script (`WINDOWS_REPOS`).

3. Run the tracker:
   ```bash
   python check_windows_containers.py
   ```

   - On first run, it initializes the state file.
   - On subsequent runs, it reports any new or updated images.

4. Schedule the script for regular checks (e.g., with [Windows Task Scheduler](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page) or `cron` on Linux).

## Example Output

```
Checking Microsoft Windows container images at 2025-06-21T07:07:09Z
Changes detected:
  [UPDATED] windows/servercore: tag=latest, new digest=sha256:abcd1234 (was sha256:old5678)
  [NEW] windows/nanoserver: tag=2025-06-20, digest=sha256:efgh5678
```

## Customization

- To add or remove tracked images, edit the `WINDOWS_REPOS` list in `check_windows_containers.py`.
- To track all tags (not just the latest), extend the script as needed.

## License

MIT License

---

*Inspired by the need to stay up-to-date with Windows container base image releases.*