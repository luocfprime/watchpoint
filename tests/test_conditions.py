import socket
import threading
import time
from pathlib import Path

import pytest

import watchpoint.conditions as conditions

# --- Pytest Fixtures ---


@pytest.fixture
def stop_event():
    """Provides a new, cleared threading.Event for each test function."""
    return threading.Event()


@pytest.fixture
def free_port():
    """
    Finds and provides a free TCP port for network tests by binding to port 0
    and letting the OS choose an available port. [8]
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# --- Tests for Time-Based Conditions ---


def test_every_n_seconds(stop_event):
    """
    Tests that `every_n_seconds` yields True at the correct interval and
    respects the stop_event.
    """
    interval = 0.1  # Use a short interval for quick testing
    handler = conditions.every_n_seconds(interval, stop_event)

    # Check that it yields True after the specified interval
    start_time = time.monotonic()
    result = next(handler)
    end_time = time.monotonic()

    assert result is True
    assert (end_time - start_time) >= interval

    # Verify the behavior for a second iteration
    start_time = time.monotonic()
    result = next(handler)
    end_time = time.monotonic()

    assert result is True
    assert (end_time - start_time) >= interval

    # Verify that setting the stop_event terminates the generator
    stop_event.set()
    with pytest.raises(StopIteration):
        next(handler)


# --- Tests for File System Conditions ---


def test_new_file_in_directory(tmp_path, stop_event):
    """
    Tests that `new_file_in_directory` correctly detects new files.
    It uses the `tmp_path` fixture for a clean test environment. [1, 2]
    """
    check_interval = 0.01
    handler = conditions.new_file_in_directory(tmp_path, stop_event, check_interval)

    # Initially, no new files are present, so it should yield False
    time.sleep(check_interval * 2)
    assert next(handler) is False

    # Create a new file in the temporary directory
    (tmp_path / "test_file.txt").touch()

    # The handler should now detect the new file and yield True
    time.sleep(check_interval * 2)
    assert next(handler) is True

    # On the next check, the file is "known", so it should yield False again
    time.sleep(check_interval * 2)
    assert next(handler) is False

    # Verify that the generator stops when the event is set
    stop_event.set()
    with pytest.raises(StopIteration):
        next(handler)


def test_new_file_in_directory_non_existent(stop_event):
    """
    Tests that `new_file_in_directory` raises FileNotFoundError
    for a non-existent directory path.
    """
    handler = conditions.new_file_in_directory(
        Path("/this/path/absolutely/does/not/exist"), stop_event
    )

    with pytest.raises(FileNotFoundError):
        # next() attempts to execute the generator's code for the first time,
        # which immediately hits the p.is_dir() check and raises the error.
        next(handler)


def test_file_not_modified_for(tmp_path, stop_event):
    """
    Tests that `file_not_modified_for` correctly detects file inactivity.
    """
    file_path = tmp_path / "test.log"
    file_path.touch()

    duration = 0.2
    interval = 0.05
    handler = conditions.file_not_modified_for(
        file_path, stop_event, duration, interval
    )

    # Immediately after creation, the file has been modified recently, so yield False
    assert next(handler) is False

    # Wait for a period longer than the specified duration
    time.sleep(duration + 0.1)

    # Now, the file should be considered unmodified, yielding True
    assert next(handler) is True

    # Modify the file again to reset its modification time
    file_path.touch()

    # The handler should now revert to yielding False
    assert next(handler) is False

    # Verify graceful shutdown
    stop_event.set()
    with pytest.raises(StopIteration):
        next(handler)


def test_file_not_modified_for_non_existent_file(tmp_path, stop_event):
    """
    Tests that `file_not_modified_for` yields False for a non-existent file.
    """
    file_path = tmp_path / "non_existent.txt"
    handler = conditions.file_not_modified_for(file_path, stop_event, 1, 0.1)

    # A non-existent file is not "unmodified"; the condition should be False
    assert next(handler) is False


def test_file_exists(tmp_path, stop_event):
    """
    Tests that `file_exists` correctly tracks the existence of a file.
    """
    file_path = tmp_path / "watched_file.txt"
    interval = 0.01
    handler = conditions.file_exists(file_path, stop_event, interval)

    # File does not exist initially, should yield False
    assert next(handler) is False

    # Create the file
    file_path.touch()
    time.sleep(interval * 2)  # Wait for the next check
    # File now exists, should yield True
    assert next(handler) is True

    # Delete the file
    file_path.unlink()
    time.sleep(interval * 2)  # Wait for the next check
    # File is gone, should yield False
    assert next(handler) is False

    # Verify graceful shutdown
    stop_event.set()
    with pytest.raises(StopIteration):
        next(handler)


# --- Tests for Network Conditions ---


def test_is_port_open(stop_event, free_port):
    """
    Tests the `is_port_open` generator by starting a temporary server
    on a free port. [6, 13, 14]
    """
    host = "127.0.0.1"
    port = free_port
    interval = 0.05
    handler = conditions.is_port_open(host, port, stop_event, interval)

    # Port is not open yet, should yield False
    assert next(handler) is False

    # Set up and start a server socket in a separate thread to open the port
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(1)

    # This thread will accept one connection and then exit
    def server_thread():
        try:
            conn, _ = server_socket.accept()
            conn.close()
        except OSError:
            # This can happen if the socket is closed while accept() is blocking
            pass

    st = threading.Thread(target=server_thread, daemon=True)
    st.start()

    time.sleep(0.1)  # Give the server thread a moment to start listening

    # Now the port should be detected as open, yielding True
    assert next(handler) is True

    # Close the server socket to free the port
    server_socket.close()
    st.join()

    time.sleep(0.1)  # Give the OS a moment to register the port as closed

    # Now the port should be detected as closed again, yielding False
    assert next(handler) is False

    # Verify graceful shutdown
    stop_event.set()
    with pytest.raises(StopIteration):
        next(handler)
