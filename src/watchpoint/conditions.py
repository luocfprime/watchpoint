"""
A collection of pre-built, common condition handlers for use with Watchpoint.

This module provides a set of ready-to-use functions that can be passed to
the `on()` or `watch()` Watchpoint factories. They cover common use cases like
time-based triggers, file system monitoring, and network checks.

Generator-based handlers are designed for continuous monitoring and gracefully
handle shutdown by accepting a `stop_event`.
"""

import os
import socket
import time
from pathlib import Path
from threading import Event
from typing import Generator, Union

# --- Time-Based Conditions (Generators) ---


def every_n_seconds(seconds: float, stop_event: Event) -> Generator[bool, None, None]:
    """
    Yields `True` at a specified interval in seconds.

    This is a generator-based condition for creating periodic tasks. It uses
    `stop_event.wait()` for efficient waiting that can be interrupted
    immediately by `watchpoint.stop()`.

    Args:
        seconds: The interval in seconds between each trigger.
        stop_event: A threading.Event provided by the Watchpoint to signal shutdown.

    Yields:
        `True` after each interval.
    """
    while not stop_event.is_set():
        # wait() returns True if the event was set, False on timeout.
        # We want to continue on timeout, so we check the event again.
        stop_event.wait(seconds)
        if not stop_event.is_set():
            yield True


# --- File System Conditions ---
def new_file_in_directory(
    directory_path: os.PathLike,
    stop_event: Event,
    check_interval_seconds: float = 5.0,
) -> Generator[bool, None, None]:
    """
    Yields `True` whenever a new file is detected in a directory.

    This generator maintains a state of known files and triggers when the
    set of files in the directory changes. It's ideal for "dropbox" style
    monitoring where an action should be taken on newly arrived files.

    Args:
        directory_path: The absolute path to the directory to watch.
        stop_event: A threading.Event provided by the Watchpoint to signal shutdown.
        check_interval_seconds: The time to wait between checking the directory.

    Yields:
        `True` when one or more new files are found, otherwise `False`.
    """
    p = Path(directory_path)
    if not p.is_dir():
        raise FileNotFoundError(f"Directory not found at: {directory_path}")

    known_files = set(p.iterdir())
    while not stop_event.is_set():
        if stop_event.wait(check_interval_seconds):
            # Stop event was set during wait
            break

        current_files = set(p.iterdir())
        if current_files - known_files:  # Check for any new files
            yield True
        else:
            yield False

        known_files = current_files


def file_not_modified_for(
    file_path: Union[str, os.PathLike],
    stop_event: Event,
    duration_seconds: float = 300.0,  # Default to 5 minutes
    check_interval_seconds: float = 60.0,  # Default to check every minute
) -> Generator[bool, None, None]:
    """
    Continuously checks if a file has not been modified for a given duration.

    This is a self-contained generator that monitors any file. At each
    interval (`check_interval_seconds`), it checks if the file's last
    modification time is older than the specified `duration_seconds`.

    Args:
        file_path: The path to the file to monitor.
        stop_event: A threading.Event provided by the Watchpoint to signal shutdown.
        duration_seconds: The duration of inactivity in seconds.
        check_interval_seconds: The time in seconds to wait between each check.

    Yields:
        `True` if the file has not been modified for the specified duration,
        otherwise `False`.
    """
    path_to_check = Path(file_path)

    while not stop_event.is_set():
        is_unmodified = False
        try:
            last_modified_time = path_to_check.stat().st_mtime
            current_time = time.time()
            if (current_time - last_modified_time) > duration_seconds:
                is_unmodified = True
        except FileNotFoundError:
            # A non-existent file is not considered "unmodified" in this context.
            # It simply doesn't exist to be checked. We yield False.
            pass

        yield is_unmodified

        # Wait for the next check interval in an interruptible way
        if stop_event.wait(check_interval_seconds):
            break


def file_exists(
    file_path: Union[str, os.PathLike],
    stop_event: Event,
    check_interval_seconds: float = 2.0,
) -> Generator[bool, None, None]:
    """
    Continuously checks if a file exists, yielding the result.

    This generator checks for the existence of a path at a given interval.
    It is ideal for waiting for a file to be created or for monitoring that
    a file remains in place.

    Args:
        file_path: The path to the file or directory to check.
        stop_event: A threading.Event provided by the Watchpoint to signal shutdown.
        check_interval_seconds: The time in seconds to wait between checks.

    Yields:
        `True` if the path exists during a check, otherwise `False`.
    """
    path_to_check = Path(file_path)

    while not stop_event.is_set():
        yield path_to_check.exists()

        # Wait for the next check, breaking early if the stop event is set.
        if stop_event.wait(check_interval_seconds):
            break


# --- Network Conditions ---


def is_port_open(
    host: str,
    port: int,
    stop_event: Event,
    check_interval_seconds: float = 5.0,
    timeout: float = 2.0,
) -> Generator[bool, None, None]:
    """
    Continuously checks if a TCP port is open, yielding the result.

    This generator monitors a network port at a regular interval. It's useful
    for waiting for a service to start or for monitoring its health.

    Args:
        host: The hostname or IP address to check.
        port: The port number to check.
        stop_event: A threading.Event provided by the Watchpoint to signal shutdown.
        check_interval_seconds: The time in seconds to wait between each check.
        timeout: The connection timeout in seconds for each check.

    Yields:
        `True` if the port is open during a check, otherwise `False`.
    """
    while not stop_event.is_set():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            # connect_ex returns 0 on success.
            port_is_currently_open = s.connect_ex((host, port)) == 0

        yield port_is_currently_open

        # Wait for the next check interval.
        if stop_event.wait(check_interval_seconds):
            break
