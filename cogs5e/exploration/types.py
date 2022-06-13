import enum


class BaseExplorer:
    __slots__ = ()


class ExplorerType(enum.Enum):
    GENERIC = "common"
    PLAYER = "player"
    GROUP = "group"
