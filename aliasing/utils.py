import enum
UNSET = object()  # special sentinel value


class ExecutionScope(enum.IntEnum):
    # note: all values must be within [0..7] to fit in signature()
    UNKNOWN = 0
    PERSONAL_ALIAS = 1
    SERVER_ALIAS = 2
    PERSONAL_SNIPPET = 3
    SERVER_SNIPPET = 4
    COMMAND_TEST = 5


def optional_cast_arg_or_default(argument, arg_t=str, default=None, unset_sentinel=UNSET):
    """
    Given a passed argument, returns that argument cast to *arg_t* (or None if the arg is None), 
    unless the argument is *unset_sentinel*, in which case returns *default*.

    Used to cast aliasing args to the expected optional type while handling the unset case.
    """
    if argument is unset_sentinel:
        return default  # this is where it returns DefaultT, since default is of type DefaultT
    elif argument is None:
        return None  # this is why it's Optional[...]
    return arg_t(argument)  # this is where it returns T, since arg_t casts Any -> T
