from discord.ext.commands import BadArgument
from discord.ext.commands.view import StringView

from cogs5e.models.errors import InvalidArgument
from utils.functions import list_get


def argsplit(args: str):
    view = StringView(args.strip())
    args = []
    while not view.eof:
        view.skip_ws()
        args.append(quoted_word(view))
    return args


def argparse(args, character=None, splitter=argsplit):
    """
    Parses arguments.
    :param args: A list of arguments to parse.
    :param character: A Character object, if args should have cvars parsed.
    :param splitter: A function to use to split a string into a list of arguments.
    :return: The parsed arguments (ParsedArguments).
    :rtype ParsedArguments
    """
    if isinstance(args, str):
        args = splitter(args)
    if character:
        from cogs5e.funcs.scripting import MathEvaluator
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


def argquote(arg: str):
    if ' ' in arg:
        arg = arg.replace("\"", "\\\"")  # re.sub(r'(?<!\\)"', r'\"', arg)
        arg = f'"{arg}"'
    return arg


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
        :raises InvalidArgument if the arg cannot be cast to the type
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

    def adv(self, ea=False, boolwise=False):
        """
        Determines whether to roll with advantage, disadvantage, Elven Accuracy, or no special effect.
        :param ea: Whether to parse for elven accuracy.
        :param boolwise: Whether to return an integer or tribool representation.
        :return: -1 for dis, 0 for normal, 1 for adv, 2 for ea
        """
        adv = 0
        if self.last("adv", type_=bool):
            adv += 1
        if self.last("dis", type_=bool):
            adv += -1
        if ea and self.last("ea", type_=bool) and adv > -1:
            return 2
        if not boolwise:
            return adv
        else:
            return {-1: False, 0: None, 1: True}.get(adv)

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

    def __str__(self):
        return str(self.parsed)


def quoted_word(view):
    QUOTES = '"\''
    current = view.current

    if current is None:
        return None

    quote = current if current in QUOTES else None
    result = [] if quote else [current]

    while not view.eof:
        current = view.get()
        if not current:
            if quote:
                # unexpected EOF
                raise BadArgument('Expected closing quote')
            return ''.join(result)

        # start of a quoted block
        if current in QUOTES and not quote:
            quote = current
            continue

        # currently we accept strings in the format of "hello world"
        # to embed a quote inside the string you must escape it: "a \"world\""
        if current == '\\':
            next_char = view.get()
            if not next_char:
                # string ends with \ and no character after it
                if quote:
                    # if we're quoted then we're expecting a closing quote
                    raise BadArgument('Expected closing quote')
                # if we aren't then we just let it through
                return ''.join(result)

            if next_char in QUOTES:
                # escaped quote
                result.append(next_char)
            else:
                # different escape character, ignore it
                view.undo()
                result.append(current)
            continue

        # closing quote
        if current == quote:
            next_char = view.get()
            valid_eof = not next_char or next_char.isspace()
            if not valid_eof:  # there's still more in this argument
                view.undo()
                quote = None
                continue

            # we're quoted so it's okay
            return ''.join(result)

        if current.isspace() and not quote:
            # end of word found
            return ''.join(result)

        result.append(current)


if __name__ == '__main__':
    while True:
        try:
            print(argsplit(input('>>> ')))
        except BadArgument as e:
            print(e)
