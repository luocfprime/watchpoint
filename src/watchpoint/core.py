import inspect
import logging
import threading
from functools import partial
from typing import Callable, Generator, Optional, Union

from watchpoint.exceptions import WatchpointConfigurationError, WatchpointQuit

logger = logging.getLogger(__name__)


class Watchpoint:
    """
    Executes an action in response to a condition.
    It intelligently handles two types of 'on' handlers:
    1.  One-Shot Function: Returns a truthy value. The Watchpoint runs 'do_handler' once and stops.
    2.  Generator Function: Yields to signal the condition is met, allowing for continuous monitoring.
    """

    def __init__(
        self,
        on_handler: Optional[
            Callable[[], Union[bool, Generator[bool, None, None]]]
        ] = None,
        do_handler: Optional[Callable] = None,
    ):
        self._on_handler = on_handler
        self._do_handler = do_handler
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def __enter__(self) -> "Watchpoint":
        """
        Start the watchpoint when entering a context manager block.

        Returns:
            self: The watchpoint instance for further configuration if needed

        Raises:
            WatchpointConfigurationError: If required handlers aren't configured
        """
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Stop the watchpoint when exiting a context manager block.

        Args:
            exc_type: The exception type if an exception was raised in the with block
            exc_val: The exception value if an exception was raised
            exc_tb: The traceback if an exception was raised
        """
        self.stop()

    def on(self, func: Callable, /, *args, **kwargs) -> "Watchpoint":
        """
        Configures the condition handler.

        Args:
            func: The function to be called to check for the condition.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
        """
        if self._on_handler:
            raise WatchpointConfigurationError(
                "Watchpoint 'on' handler has already been set."
            )
        self._on_handler = partial(func, *args, **kwargs)
        return self

    def do(self, func: Callable, /, *args, **kwargs) -> "Watchpoint":
        """
        Configures the action to be executed when the condition is met.

        Args:
            func: The function to execute.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
        """
        if self._do_handler:
            raise WatchpointConfigurationError(
                "Watchpoint 'do' handler has already been set."
            )
        self._do_handler = partial(func, *args, **kwargs)
        return self

    def _run(self):
        """
        The core loop. It inspects the 'on' handler's return type to determine
        whether to run in one-shot mode or continuous generator mode.
        """
        try:
            if not self._on_handler or not self._do_handler:
                raise WatchpointConfigurationError(
                    "Cannot run Watchpoint without 'on' and 'do' handlers."
                )

            handler_to_call = self._on_handler
            try:
                sig = inspect.signature(handler_to_call)
                if "stop_event" in sig.parameters:
                    handler_to_call = partial(
                        self._on_handler, stop_event=self._stop_event
                    )
            except (AttributeError, TypeError):
                # Handles cases where the handler is a built-in or not a standard function.
                pass

            ret = handler_to_call()

            # --- Smart Handler Logic ---
            try:
                if isinstance(ret, Generator):
                    # Generator Mode: For continuous monitoring.
                    logger.debug(
                        "Handler returned a generator. Entering continuous mode."
                    )
                    for result in ret:  # We iterate but don't use the yielded value.
                        if self._stop_event.is_set():
                            break
                        if result:
                            self._execute_do_handler()
                elif isinstance(ret, bool):
                    # One-Shot Mode: For simple, single checks.
                    logger.debug("Handler returned a value. Entering one-shot mode.")
                    if ret:  # Check if the result is "truthy" to trigger the action.
                        self._execute_do_handler()
                else:
                    logger.error(
                        f"Invalid return type from 'on' handler. Expected bool or generator. Got {type(ret)} instead."
                    )
                    raise WatchpointConfigurationError(
                        f"Invalid return type from 'on' handler. Expected bool or generator. Got {type(ret)} instead."
                    )
            except WatchpointQuit:
                logger.info("Watchpoint stopped.")

        finally:
            logger.info("Watchpoint thread finished.")

    def _execute_do_handler(self):
        """Executes the 'do' handler and handles any potential errors."""
        logger.info("Condition met. Executing 'do' handler.")
        try:
            if not self._do_handler:
                return
            self._do_handler()
        except WatchpointQuit as e:  # propagate
            raise e
        except Exception as e:
            logger.error(f"Error executing 'do' handler: {e}", exc_info=True)

    def start(self) -> "Watchpoint":
        """Starts the Watchpoint monitor in a background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Watchpoint is already running.")
            return self
        if not self._on_handler or not self._do_handler:
            raise WatchpointConfigurationError(
                "Cannot start Watchpoint: 'on' and 'do' handlers must be configured."
            )
        logger.info("Starting Watchpoint...")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="WatchpointThread"
        )
        self._thread.start()
        return self

    def stop(self, timeout: Optional[float] = 10.0) -> "Watchpoint":
        """
        Signals the monitoring thread to stop and waits for it to terminate.

        Args:
            timeout: Maximum time in seconds to wait for the thread to join.
                     If None, it will wait indefinitely.
        """
        if self._thread and self._thread.is_alive():
            logger.info("Stopping Watchpoint...")
            self._stop_event.set()
            self._thread.join(timeout=timeout)

            if self._thread.is_alive():
                logger.error(
                    f"Watchpoint thread did not stop within the {timeout}s timeout. "
                    "The 'on_handler' may have a blocking operation or is not checking the stop_event."
                )
        else:
            logger.debug("Watchpoint is not running or has already stopped.")

        return self
