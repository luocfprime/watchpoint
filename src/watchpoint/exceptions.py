class WatchpointError(Exception):
    """Base class for all exceptions raised by the Watchpoint library."""

    pass


class WatchpointConfigurationError(WatchpointError):
    """Raised when the Watchpoint is configured incorrectly (e.g., a handler is set twice)."""

    pass


class WatchpointQuit(WatchpointError):
    """Raised when the 'do' handler wants to quit gracefully."""

    pass
