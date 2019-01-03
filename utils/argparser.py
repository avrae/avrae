import shlex

from cogs5e.funcs.scripting import MathEvaluator
from cogs5e.models.errors import InvalidArgument
from utils.functions import list_get


def argsplit(args):
    return shlex.split(args)


def argparse(args, character=None):
    """
    Parses arguments.
    :param args: A list of arguments to parse.
    :param character: A Character object, if args should have cvars parsed.
    :return: The parsed arguments (ParsedArguments).
    :rtype ParsedArguments
    """
    if isinstance(args, str):
        args = argsplit(args)
    if character:
        evaluator = MathEvaluator.with_character(character)
        args = [evaluator.parse(a) for a in args]

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

    def last(self, arg, default=None, type_: type = str):
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
        if not parsed_arg:
            return default
        last_arg = parsed_arg[-1]
        try:
            return type_(last_arg)
        except (ValueError, TypeError):
            raise InvalidArgument(f"{last_arg} cannot be cast to {type_.__name__} (in `{arg}`)")

    def adv(self, ea=False):
        """
        Determines whether to roll with advantage, disadvantage, Elven Accuracy, or no special effect.
        :param ea: Whether to parse for elven accuracy.
        :return: -1 for dis, 0 for normal, 1 for adv, 2 for ea
        """
        adv = 0
        if self.last("adv", type_=bool):
            adv += 1
        if self.last("dis", type_=bool):
            adv += -1
        if ea and self.last("ea", type_=bool) and adv > -1:
            return 2
        return adv

    def join(self, arg, connector: str, default=None):
        """
        Returns a str formed from all of one arg, joined by a connector.
        :param arg: The arg to join.
        :param connector: What to join the arg by.
        :param default: What to return if the arg does not exist.
        :return: The joined str, or default.
        """
        if arg not in self.parsed:
            return default
        return connector.join(self.get(arg))

    def __contains__(self, item):
        return item in self.parsed

    def __len__(self):
        return len(self.parsed)

    def __setitem__(self, key, value):
        if not isinstance(value, list):
            value = [value]
        self.parsed[key] = value

    def __iter__(self):
        return iter(self.parsed.keys())
