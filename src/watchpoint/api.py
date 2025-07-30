from typing import Callable, Generator, Union

from watchpoint.core import Watchpoint


def on(func: Callable, /, *args, **kwargs) -> Watchpoint:
    """
    Creates a Watchpoint instance to start a fluent API chain.

    This function serves as a convenient starting point for building a Watchpoint monitor
    using a method-chaining (fluent) style. It initializes a `Watchpoint` object
    and configures its condition handler (`on_handler`) in a single step.

    Example:
        >>> from watchpoint import on
        >>>
        >>> def is_file_present(filename):
        ...     # In a real scenario, this would check the filesystem.
        ...     print(f"Checking for {filename}...")
        ...     return True
        >>>
        >>> def process_file():
        ...     print(f"File found! Processing it.")
        >>>
        >>> # Build the monitor using the fluent API
        >>> monitor = on(is_file_present, "my_data.csv").do(process_file)
        >>> # The monitor can now be started with monitor.start()

    Args:
        func: The function that defines the condition to monitor.
              It can be a simple function returning a boolean or a generator
              that yields when the condition is met.
        *args: Positional arguments to be passed to the `func`.
        **kwargs: Keyword arguments to be passed to the `func`.

    Returns:
        A new `Watchpoint` instance with the 'on' handler configured,
        ready for the `.do()` method to be chained.
    """
    return Watchpoint().on(func, *args, **kwargs)


def watch(
    *,
    on_handler: Callable[[], Union[bool, Generator[bool, None, None]]],
    do_handler: Callable[[], None],
) -> Watchpoint:
    """
    Creates a fully configured Watchpoint instance from pre-defined handlers.

    This factory provides a more explicit, declarative way to create a Watchpoint
    monitor. It is ideal when you have already prepared the exact,
    zero-argument callables for the condition and the action, for instance by
    using `functools.partial`.

    Example:
        >>> from functools import partial
        >>> from watchpoint import watch
        >>>
        >>> def check_service_status(service_name, expected_status):
        ...     print(f"Checking if {service_name} is {expected_status}...")
        ...     # In a real scenario, this would check a service.
        ...     return True
        >>>
        >>> def restart_service(service_name):
        ...     print(f"Service {service_name} status is not as expected. Restarting.")
        >>>
        >>> # Use functools.partial to create zero-argument callables
        >>> on_check = partial(check_service_status, "database", "running")
        >>> do_restart = partial(restart_service, "database")
        >>>
        >>> # Create a fully configured monitor
        >>> monitor = watch(on_handler=on_check, do_handler=do_restart)
        >>> # The monitor is now ready to be started with monitor.start()

    Args:
        on_handler: A complete, zero-argument callable that checks for the
                    condition. It should return a truthy value or yield to
                    trigger the `do_handler`.
        do_handler: A complete, zero-argument callable that executes the
                    desired action when the condition is met.

    Returns:
        A new `Watchpoint` instance, fully configured and ready to be
        started with the `.start()` method.
    """
    return Watchpoint(on_handler=on_handler, do_handler=do_handler)
