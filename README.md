# Windows Container Tracker

This project tracks Microsoft Windows container images (from MCR) and checks for updates based on tags and digests. The script is structured to be AWS Lambda compatible and is fully unit tested.

## Features

- Loads a list of repos from `config.json`
- Fetches latest tags and digests for each repo from MCR
- Compares current state to previous run, reporting new or updated images
- Easily deployable as an AWS Lambda function
- Includes unit tests and code coverage support

---

## Getting Started

### Prerequisites

- Python 3.7+
- [pip](https://pip.pypa.io/en/stable/installation/)

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/windows-container-tracker.git
   cd windows-container-tracker
   ```

2. (Optional but recommended) Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   For development and testing, also install:

   ```bash
   pip install pytest pytest-cov
   ```

---

## Usage

### Run the Tracker Locally

```bash
python check_windows_containers.py
```

- The script reads repositories from `config.json` and maintains state in `windows_container_state.json`.

### AWS Lambda

The main script includes a `lambda_handler(event, context)` entrypoint for easy AWS Lambda deployment.
Configure your Lambda environment variables for custom config or state file locations if needed.

---

## Configuration

Edit `config.json` to specify which repositories to track:

```json
{
  "repos": [
    "windows/servercore",
    "windows/nanoserver"
  ]
}
```

---

## Testing

### Run Unit Tests

All tests are in the `tests/` directory and use `pytest`.

```bash
pytest
```

### Run Tests with Coverage

To see which code is covered by tests:

```bash
pytest --cov=check_windows_containers --cov-report=term-missing
```

- This shows a summary and missing lines in the terminal.

#### Generate an HTML coverage report:

```bash
pytest --cov=check_windows_containers --cov-report=html
```

- Open `htmlcov/index.html` in your browser for a detailed, color-coded report.

---

## Tips

- Run `pytest` from the project root to ensure imports work correctly.
- If you add new dependencies for testing, update `requirements.txt` or create a `requirements-dev.txt`.
- To increase coverage, test edge cases and error handling (e.g., missing config, failed network calls).
- Use the HTML coverage report to identify untested code paths visually.

---

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

---

## License

[MIT](LICENSE)
