import abc
import inspect
from types import MappingProxyType
from typing import Any, Callable, Coroutine, TypeVar

from ddb.gamelog.context import GameLogEventContext


class GameLogCallbackHandler(abc.ABC):
    """Base class for Game Log callback groups."""

    def __init__(self, bot):
        self.bot = bot

        # find all registered callbacks and save them
        callbacks = {}
        for name, member in inspect.getmembers(self, predicate=inspect.ismethod):
            if (event_type := getattr(member, '__callback_type', None)) is None:
                continue
            if not inspect.iscoroutinefunction(member):
                raise TypeError(f"Callback must be a coroutine ({type(self).__name__}.{name})")
            if event_type in callbacks:
                raise ValueError(f"Callback for {event_type} is already registered in ({type(self).__name__})")
            callbacks[event_type] = member

        self.callbacks = MappingProxyType(callbacks)  # save an immutable copy of this mapping to avoid foot-guns

    def register(self):
        """Registers this handler's registered callbacks in the game log client."""
        for event_type, the_callback in self.callbacks.items():
            self.bot.glclient.register_callback(event_type, the_callback)

    def deregister(self):
        """Deregisters this handler's registered callbacks in the game log client."""
        for event_type in self.callbacks:
            self.bot.glclient.deregister_callback(event_type)


F1 = Callable[[GameLogEventContext], Coroutine[Any]]
F2 = Callable[[GameLogEventContext, Any], Coroutine[Any]]
F = TypeVar('F', F1, F2)


def callback(event_name: str) -> Callable[[F], F]:
    """
    A function that returns a decorator that marks the decorated function as a callback for the provided event name.

    The decorated function must take at least one argument of type GameLogEventContext. If the decorated function takes
    a second argument, the value passed to that argument will be the event's data (optionally cast to a type provided by
    the argument's type annotation).
    """

    def decorator(func: F) -> F:
        func.__callback_type = event_name
        return func

    return decorator
