import enum


class ExecutionScope(enum.IntEnum):
    # note: all values must be within [0..7] to fit in signature()
    UNKNOWN = 0
    PERSONAL_ALIAS = 1
    SERVER_ALIAS = 2
    PERSONAL_SNIPPET = 3
    SERVER_SNIPPET = 4
