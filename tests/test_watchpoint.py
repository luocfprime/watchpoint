import logging
import threading
import time
from functools import partial
from typing import Generator

import pytest

from watchpoint import (
    Watchpoint,
    WatchpointConfigurationError,
    WatchpointQuit,
    on,
    watch,
)

# --- Test Setup and Helper Handlers ---

# A shared list to track calls from the 'do' handler across threads
# This is a simple way to verify if and how many times an action was executed.
call_tracker = []


def on_returns_true() -> bool:
    """Simple one-shot handler that always triggers."""
    return True


def on_returns_false() -> bool:
    """Simple one-shot handler that never triggers."""
    return False


def do_action_marker(marker: str = "called"):
    """A 'do' handler that appends a marker to the global tracker list."""
    call_tracker.append(marker)


def do_action_once(marker: str = "called"):
    """A 'do' handler that only run once and exits gracefully"""
    call_tracker.append(marker)
    raise WatchpointQuit("Manual exit.")


def on_generator(
    stop_event: threading.Event, yields: int = 3, initial_delay: float = 0
) -> Generator[bool, None, None]:
    """
    A generator 'on' handler that yields `True` a specific number of times.
    It respects the stop_event to allow for clean shutdown.
    """
    time.sleep(initial_delay)  # Allow time for the test to start the watchpoint
    count = 0
    while count < yields and not stop_event.is_set():
        yield True
        count += 1
        time.sleep(0.02)  # Simulate work/delay between yields


def on_generator_with_false_yields(
    stop_event: threading.Event,
) -> Generator[bool, None, None]:
    """A generator that mixes True and False yields."""
    yields = [True, False, True, False, True]
    for y in yields:
        if stop_event.is_set():
            break
        yield y
        time.sleep(0.02)


def on_handler_with_invalid_return():
    """An 'on' handler that returns a type Watchpoint doesn't support."""
    return "invalid_string"


@pytest.fixture(autouse=True)
def reset_call_tracker():
    """
    A pytest fixture that automatically runs before each test.
    It clears the global call_tracker list to ensure tests are isolated.
    """
    call_tracker.clear()


# --- Test Cases ---


class TestWatchpointConfiguration:
    """Tests for Watchpoint's configuration and setup validation."""

    def test_fluent_api_chaining(self):
        """Ensures .on() and .do() can be chained and return a Watchpoint instance."""
        watchpoint = Watchpoint().on(on_returns_true).do(do_action_marker)
        assert isinstance(watchpoint, Watchpoint)
        assert watchpoint._on_handler is not None
        assert watchpoint._do_handler is not None

    def test_setting_on_handler_twice_raises_error(self):
        """Verifies that re-configuring the 'on' handler raises an exception."""
        watchpoint = Watchpoint().on(on_returns_true)
        with pytest.raises(
            WatchpointConfigurationError,
            match="Watchpoint 'on' handler has already been set",
        ):
            watchpoint.on(on_returns_false)

    def test_setting_do_handler_twice_raises_error(self):
        """Verifies that re-configuring the 'do' handler raises an exception."""
        watchpoint = Watchpoint().do(do_action_marker)
        with pytest.raises(
            WatchpointConfigurationError,
            match="Watchpoint 'do' handler has already been set",
        ):
            watchpoint.do(do_action_marker)

    def test_start_without_on_handler_raises_error(self):
        """Checks that starting is blocked if 'on' handler is missing."""
        watchpoint = Watchpoint().do(do_action_marker)
        with pytest.raises(WatchpointConfigurationError, match="must be configured"):
            watchpoint.start()

    def test_start_without_do_handler_raises_error(self):
        """Checks that starting is blocked if 'do' handler is missing."""
        watchpoint = Watchpoint().on(on_returns_true)
        with pytest.raises(WatchpointConfigurationError, match="must be configured"):
            watchpoint.start()


class TestWatchpointOneShotMode:
    """Tests for the one-shot (boolean return) execution mode."""

    def test_on_true_triggers_do_handler(self):
        """When on_handler returns True, do_handler must be executed."""
        watchpoint = Watchpoint().on(on_returns_true).do(do_action_marker)
        watchpoint.start()
        time.sleep(0.1)  # Allow thread time to execute

        assert call_tracker == ["called"]
        # The thread should be finished after a one-shot execution
        assert watchpoint._thread is not None and not watchpoint._thread.is_alive()

    def test_on_false_does_not_trigger_do_handler(self):
        """When on_handler returns False, do_handler must NOT be executed."""
        watchpoint = Watchpoint().on(on_returns_false).do(do_action_marker)
        watchpoint.start()
        time.sleep(0.1)  # Allow thread time to execute

        assert not call_tracker
        assert watchpoint._thread is not None and not watchpoint._thread.is_alive()

    def test_handlers_with_arguments(self):
        """Ensures arguments are correctly passed to handlers via partial."""
        watchpoint = (
            Watchpoint().on(on_returns_true).do(do_action_marker, marker="custom")
        )
        watchpoint.start()
        time.sleep(0.1)

        assert call_tracker == ["custom"]

    def test_do_action_once(self):
        """Ensures the do_handler is called once and exits gracefully"""
        watchpoint = Watchpoint().on(on_generator).do(do_action_once)
        watchpoint.start()
        time.sleep(0.1)

        assert call_tracker == ["called"]
        assert watchpoint._thread is not None and not watchpoint._thread.is_alive()


class TestWatchpointGeneratorMode:
    """Tests for the continuous (generator) execution mode."""

    def test_generator_triggers_do_handler_multiple_times(self):
        """Verifies the do_handler is called for each `True` yield."""
        watchpoint = Watchpoint().on(on_generator, yields=4).do(do_action_marker)
        watchpoint.start()
        time.sleep(0.2)  # Allow enough time for all yields
        watchpoint.stop()

        assert len(call_tracker) == 4
        assert watchpoint._thread is not None and not watchpoint._thread.is_alive()

    def test_stop_terminates_generator_loop(self):
        """Ensures the stop() method effectively halts a running generator."""
        watchpoint = (
            Watchpoint()
            .on(on_generator, yields=10, initial_delay=0.05)
            .do(do_action_marker)
        )
        watchpoint.start()

        # Let it run briefly, then stop it
        time.sleep(0.1)
        watchpoint.stop(timeout=1)

        # It should have run a few times but not all 10 times
        assert 1 < len(call_tracker) < 10
        assert watchpoint._thread is not None and not watchpoint._thread.is_alive()

    def test_generator_with_mixed_yields(self):
        """Tests that do_handler is only called on truthy yields."""
        watchpoint = (
            Watchpoint().on(on_generator_with_false_yields).do(do_action_marker)
        )
        watchpoint.start()
        time.sleep(0.3)  # Allow generator to complete
        watchpoint.stop()

        # The generator yields [True, False, True, False, True]
        assert len(call_tracker) == 3


class TestWatchpointErrorHandling:
    """Tests for robust error handling within the Watchpoint thread."""

    def test_invalid_return_type_from_on_handler_is_logged(self, caplog):
        """
        An 'on' handler returning a non-bool/non-generator type should log an
        error and terminate the thread gracefully.
        """
        # Set the logging level to capture INFO and ERROR messages
        with caplog.at_level(logging.INFO):
            # 1. Configure the Watchpoint with the faulty handler
            watchpoint = (
                Watchpoint().on(on_handler_with_invalid_return).do(do_action_marker)
            )

            # 2. Start the Watchpoint. This will create a new thread that will
            # immediately encounter the error and raise it internally.
            watchpoint.start()

            # 3. Wait for the background thread to run and terminate due to the error
            time.sleep(0.1)

            # 4. The thread should have finished its execution because of the unhandled error type
            assert watchpoint._thread is not None
            assert (
                not watchpoint._thread.is_alive()
            ), "Thread should have terminated after the error."

            # 5. The 'do' action should never have been called
            assert (
                not call_tracker
            ), "'do_handler' should not be called when 'on_handler' fails."

            # 6. Check the logs to confirm the specific error was caught and logged
            # This is the correct way to verify an exception in a background thread.
            assert "Invalid return type from 'on' handler" in caplog.text
            assert (
                "Watchpoint thread finished." in caplog.text
            ), "The finally block in _run should always execute."

    def test_exception_in_do_handler_is_logged(self, caplog):
        """
        An exception inside the 'do' handler should be caught and logged,
        and not crash the Watchpoint in generator mode.
        """

        def faulty_do_handler():
            call_tracker.append("called")
            raise ValueError("Something went wrong in the action!")

        with caplog.at_level(logging.INFO):
            watchpoint = Watchpoint().on(on_generator, yields=3).do(faulty_do_handler)
            watchpoint.start()
            time.sleep(0.2)
            watchpoint.stop()

            # The handler should have been attempted 3 times
            assert len(call_tracker) == 3
            # The error log should appear 3 times
            assert caplog.text.count("Error executing 'do' handler") == 3
            assert "Something went wrong in the action!" in caplog.text


class TestWatchpointContextManager:
    """Tests for the context manager (__enter__/__exit__) protocol."""

    def test_context_manager_starts_and_stops_thread(self):
        """Verifies `with` statement starts and stops the monitor thread."""

        with on(on_generator, yields=10).do(do_action_marker) as watchpoint:
            assert watchpoint._thread is not None
            assert watchpoint._thread.is_alive()
            time.sleep(0.05)  # Allow it to run and make some calls

        # After exiting the 'with' block, the thread should be stopped.
        assert not watchpoint._thread.is_alive()
        # It should have run a few times but been stopped before all 10 yields
        assert 1 < len(call_tracker) < 10

    def test_one_shot_handler_in_context_manager(self):
        """Verifies a one-shot handler runs correctly within a `with` block."""
        watchpoint = on(on_returns_true).do(do_action_marker)

        with watchpoint:
            time.sleep(0.1)  # Give thread time to execute
            # The thread is likely already finished, which is correct for one-shot
            assert not watchpoint._thread.is_alive()
            assert call_tracker == ["called"]

        # Double-check state after exiting
        assert not watchpoint._thread.is_alive()
        assert call_tracker == ["called"]

    def test_generator_handler_in_context_manager(self):
        """Verifies a generator is active inside `with` and stops on exit."""
        with watch(
            on_handler=partial(on_generator, yields=20), do_handler=do_action_marker
        ) as watchpoint:
            time.sleep(0.1)  # Let the generator run for a short period

        # It should have been called a few times, but stopped by __exit__
        # 0.1s sleep / 0.02s per yield = ~5 calls
        assert 3 < len(call_tracker) < 7
        assert not watchpoint._thread.is_alive()

    def test_exception_in_with_block_stops_thread(self):
        """Ensures __exit__ stops the thread even if the block has an error."""
        watchpoint = Watchpoint().on(on_generator, yields=20).do(do_action_marker)

        with pytest.raises(ValueError, match="Test exception"):
            with watchpoint:
                assert watchpoint._thread.is_alive()
                time.sleep(0.05)
                raise ValueError("Test exception")

        # The thread must be stopped by __exit__ despite the exception
        assert not watchpoint._thread.is_alive()
        assert len(call_tracker) > 0  # It had time to run at least once

    def test_context_manager_raises_config_error(self):
        """
        Checks that entering a `with` block with an incomplete configuration
        raises the appropriate error.
        """
        # Missing a 'do' handler
        watchpoint = Watchpoint().on(on_returns_true)

        with pytest.raises(WatchpointConfigurationError, match="must be configured"):
            with watchpoint:
                # This code should not be reached
                pytest.fail("Context manager should not have started.")
