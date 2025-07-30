# Watchpoint

![Unit Tests](https://github.com/luocfprime/watchpoint/actions/workflows/unit-test-matrix.yml/badge.svg)
![Python Versions](https://img.shields.io/pypi/pyversions/watchpoint)
![PyPI](https://img.shields.io/pypi/v/watchpoint)

**A lightweight Python utility for running an action when a specific condition is met.**

Watchpoint runs a monitoring task in the background and executes your callback when its condition becomes true.

## Features

*   **Fluent API**: Configure watchers with a clean, chainable syntax: `on(condition).do(action)`.
*   **Built-in Conditions**: Includes a library of common conditions for timers, file system events, and network checks.
*   **Context Manager Safety**: The `with` statement ensures your monitoring task is always started and stopped correctly.

## Installation

```bash
pip install watchpoint
```

## Usage

The easiest way to use `Watchpoint` is with the pre-built handlers from the `watchpoint.conditions` module.

### Example 1: Run a Task Every 5 Seconds

```python
import time
from watchpoint import on, conditions

def perform_backup():
    """This is the action we want to run periodically."""
    print(f"[{time.ctime()}] Performing backup... DONE.")

print("Starting periodic backup. This will run for 12 seconds.")

# The `with` block ensures the background thread is stopped on exit.
with on(conditions.every_n_seconds, seconds=5).do(perform_backup) as wp:
    time.sleep(12)

print("Periodic backup has finished.")
```

### Example 2: Monitor a Directory for New Files

```python
import time
import tempfile
import pathlib
from watchpoint import on, conditions

def process_new_file():
    """This action is triggered when a new file appears."""
    print("-> New file detected! Starting processing task.")

# Create a temporary directory to monitor for this example.
with tempfile.TemporaryDirectory() as tmpdir:
    print(f"Monitoring directory: {tmpdir}")

    with on(conditions.new_file_in_directory, tmpdir).do(process_new_file) as wp:
        # Simulate work and file creation.
        time.sleep(2)
        (pathlib.Path(tmpdir) / "report-1.csv").touch()
        time.sleep(2)

print("Monitoring has stopped.")
```

### Example 3: Check for Stalled Log Files

Use `conditions.file_not_modified_for` to get an alert if an application stops writing to its log file, which could indicate a crash or a hang.

```python
import time
import tempfile
from pathlib import Path
from watchpoint import Watchpoint
from watchpoint import conditions

def alert_stalled_log(log_path):
    """Action to run when a log file is detected as stalled."""
    print(f"\nALERT: Log file '{log_path.name}' has not been updated for too long. The app may have stalled!\n")

# Create a temporary file to simulate a log file.
with tempfile.NamedTemporaryFile("w") as tmp_log:
    log_path = Path(tmp_log.name)
    print(f"Monitoring log file: {log_path.name}")
    print("Application is running and writing to the log...")

    # Monitor the log file. Trigger if it's not modified for 2 seconds.
    # We'll check its status every second.
    with Watchpoint().on(
        conditions.file_not_modified_for,
        file_path=log_path,
        duration_seconds=2,
        check_interval_seconds=1,
    ).do(alert_stalled_log, log_path=log_path):

        # 1. Simulate active logging for 3 seconds
        for i in range(3):
            time.sleep(1)
            tmp_log.write(f"Log entry {i+1}\n")
            tmp_log.flush() # Ensure the modification time is updated on disk
            print(f"  - Wrote log entry {i+1}")

        # 2. Simulate the application hanging
        print("\nApplication has stalled. No more logs will be written...")
        time.sleep(4) # Wait long enough for the watchpoint to trigger

print("Monitoring has stopped.")
```

Watchpoint includes more pre-built conditions for checking if files exist, if network ports are open, and more. See the `watchpoint/conditions.py` module for the full list.

## How It Works

1.  **`.on(condition, *args)`**: You provide a function that checks for a condition. This can be a pre-built one from `watchpoint.conditions` or your own custom function.
2.  **`.do(action, *args)`**: You provide the function to run when the condition is met.
3.  **`with Watchpoint()...`**: Placing the setup inside a `with` statement handles the lifecycle automatically: it starts the background thread on entry and safely stops it on exit.

## Advanced Usage and Custom Conditions

For more advanced use cases, such as writing your own condition handlers, graceful shutdowns, or manual start/stop control, please refer to the full documentation or the source code for examples.

## Development

To contribute, clone the repository, set up a virtual environment, and run the tests.

```bash
# Clone the repository
git clone https://github.com/your-username/watchpoint.git
cd watchpoint

# Install dependencies and testing tools
pip install -e .[dev]

# Run tests
pytest
```

## License

This project is licensed under the MIT License.
