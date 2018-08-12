from cogs5e.models.errors import InvalidArgument
from utils.functions import list_get


def argparse(args):
    """
    Parses arguments.
    :param args: A list of arguments to parse.
    :return: The parsed arguments (ParsedArguments).
    """
    parsed = {}
    index = 0
    for a in args:
        if a.startswith('-'):
            if parsed.get(a.lstrip('-')) is None:
                parsed[a.lstrip('-')] = [list_get(index + 1, True, args)]
            else:
                parsed[a.lstrip('-')].append(list_get(index + 1, True, args))
        else:
            if parsed.get(a) is None:
                parsed[a] = [True]
            else:
                parsed[a].append(True)
        index += 1
    return ParsedArguments(args, parsed)


class ParsedArguments:
    def __init__(self, raw, parsed):
        self._raw = raw
        self.parsed = parsed

    def get(self, arg, default=None, type_=str):
        """
        Gets a list of all values of an argument.
        :param arg: The name of the arg to get.
        :param default: The default value to return if the arg is not found. Not cast to type.
        :param type_: The type that each value in the list should be returned as.
        :return: The relevant argument.
        """
        if default is None:
            default = []
        if arg not in self.parsed:
            return default  # not cast to type
        parsed = self.parsed[arg]
        try:
            return [type_(v) for v in parsed]
        except (ValueError, TypeError):
            raise InvalidArgument(f"One or more arguments cannot be cast to {type_.__name__} (in `{arg}`)")

    def last(self, arg, default=None, type_=str):
        """
        Gets the last value of an arg.
        :param arg: The name of the arg to get.
        :param default: The default value to return if the arg is not found. Not cast to type.
        :param type_: The type that the arg should be returned as.
        :return: The relevant argument.
        """
        if arg not in self.parsed:
            return default  # not cast to type
        parsed_arg = self.parsed[arg]
        last_arg = parsed_arg[-1]
        try:
            return type_(last_arg)
        except (ValueError, TypeError):
            raise InvalidArgument(f"{last_arg} cannot be cast to {type_.__name__} (in `{arg}`)")

    def __contains__(self, item):
        return item in self.parsed
