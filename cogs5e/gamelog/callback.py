import abc
import functools
import inspect
from types import MappingProxyType
from typing import Callable, Coroutine, Protocol, Type, TypeVar, Union

from ddb.gamelog import GameLogEventContext


class GameLogCallbackHandler(abc.ABC):
    """Base class for Game Log callback groups."""

    def __init__(self, bot):
        self.bot = bot

        # find all registered callbacks and save them
        callbacks = {}
        for name, member in inspect.getmembers(self, predicate=inspect.ismethod):
            if (event_type := getattr(member, "__callback_type", None)) is None:
                continue
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


# ==== callback handler decorator ====
T = TypeVar("T")


class SupportsFromDict(Protocol):
    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T: ...


SelfT = TypeVar("SelfT", bound=GameLogCallbackHandler)
F1 = Callable[[SelfT, GameLogEventContext], Coroutine]
F2 = Callable[[SelfT, GameLogEventContext, SupportsFromDict], Coroutine]


def callback(event_name: str) -> Callable[[Union[F1, F2]], F1]:
    """
    A function that returns a decorator that marks the decorated function as a callback for the provided event name.

    The decorated function must take at least one argument of type GameLogEventContext. If the decorated function takes
    a second argument, the value passed to that argument will be the event's data (optionally cast to a type provided by
    the argument's type annotation, which must support *cls.from_dict(d)*).
    """

    def decorator(inner: Union[F1, F2]) -> F1:
        if not inspect.iscoroutinefunction(inner):
            raise TypeError(f"Callback must be a coroutine ({inner.__name__})")

        # if the inner is of form F2, create a wrapper function of type F1 that pulls out the data for DI
        sig = inspect.signature(inner)
        nparams = len(sig.parameters)

        # account for self param, since this is in a class
        if nparams == 2:  # 1 param: no modification
            inner.__callback_type = event_name
            return inner
        elif nparams == 3:  # 2 params
            data_param = list(sig.parameters.values())[-1]

            if data_param.annotation is inspect.Parameter.empty:  # if no annotation, just passthru the data
                cast = lambda data: data  # noqa: E731
            else:  # otherwise the annotation is a type which supports cls.from_dict(d)
                if not hasattr(data_param.annotation, "from_dict"):
                    raise TypeError(f"Expected annotation type to support .from_dict ({inner.__name__})")
                cast = lambda data: data_param.annotation.from_dict(data)  # noqa: E731

            @functools.wraps(inner)
            async def wrapped(self, gctx: GameLogEventContext):
                data = cast(gctx.event.data)
                return await inner(self, gctx, data)

            wrapped.__callback_type = event_name
            return wrapped
        else:
            raise ValueError(f"Event callback must have either 1 or 2 parameters ({inner.__name__})")

    return decorator
