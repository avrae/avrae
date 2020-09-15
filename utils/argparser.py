import collections
import re

from discord.ext.commands import BadArgument, ExpectedClosingQuoteError
from discord.ext.commands.view import StringView

from cogs5e.models.errors import InvalidArgument
from utils.functions import list_get

EPHEMERAL_ARG_RE = re.compile(r'([^\s]+)(\d+)')
QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "‘": "’",
    "‚": "‛",
    "“": "”",
    "„": "‟",
    "⹂": "⹂",
    "「": "」",
    "『": "』",
    "〝": "〞",
    "﹁": "﹂",
    "﹃": "﹄",
    "＂": "＂",
    "｢": "｣",
    "«": "»",
    "‹": "›",
    "《": "》",
    "〈": "〉",
}
ALL_QUOTES = set(QUOTE_PAIRS.keys()) | set(QUOTE_PAIRS.values())


def argsplit(args: str):
    view = CustomStringView(args.strip())
    args = []
    while not view.eof:
        view.skip_ws()
        args.append(view.get_quoted_word())  # _quoted_word(view))
    return args


def argparse(args, character=None, splitter=argsplit):
    """
    Parses arguments.

    :param args: A list of arguments to parse.
    :type args: str or Iterable
    :return: The parsed arguments.
    :rtype: :class:`~utils.argparser.ParsedArguments`
    """
    if isinstance(args, str):
        args = splitter(args)
    if character:
        from aliasing.evaluators import MathEvaluator
        evaluator = MathEvaluator.with_character(character)
        args = [evaluator.transformed_str(a) for a in args]

    parsed = collections.defaultdict(lambda: [])
    index = 0
    for a in args:
        if a.startswith('-'):
            parsed[a.lstrip('-')].append(list_get(index + 1, True, args))
        else:
            parsed[a].append(True)
        index += 1
    return ParsedArguments(parsed)


def argquote(arg: str):
    if ' ' in arg:
        arg = arg.replace("\"", "\\\"")  # re.sub(r'(?<!\\)"', r'\"', arg)
        arg = f'"{arg}"'
    return arg


class ParsedArguments:
    def __init__(self, parsed):
        self._parsed = parsed
        self._ephemeral = collections.defaultdict(lambda: [])
        self._parse_ephemeral(parsed)

        # contextual support
        self._original_parsed = collections.defaultdict(lambda: [])
        self._original_ephemeral = collections.defaultdict(lambda: [])
        self._setup_originals()
        self._contexts = collections.defaultdict(lambda: ParsedArguments.empty_args())

    @classmethod
    def from_dict(cls, d):
        inst = cls(collections.defaultdict(lambda: []))
        for key, value in d.items():
            inst[key] = value
        return inst

    @classmethod
    def empty_args(cls):
        return cls(collections.defaultdict(lambda: []))

    # basic argument getting
    def get(self, arg, default=None, type_=str, ephem=False):
        """
        Gets a list of all values of an argument.

        :param str arg: The name of the arg to get.
        :param default: The default value to return if the arg is not found. Not cast to type.
        :param type_: The type that each value in the list should be returned as.
        :param bool ephem: Whether to add applicable ephemeral arguments to the returned list.
        :return: The relevant argument list.
        :rtype: list
        """
        if default is None:
            default = []
        parsed = self._get_values(arg, ephem=ephem)
        if not parsed:
            return default
        try:
            return [type_(v) for v in parsed]
        except (ValueError, TypeError):
            raise InvalidArgument(f"One or more arguments cannot be cast to {type_.__name__} (in `{arg}`)")

    def last(self, arg, default=None, type_: type = str, ephem=False):
        """
        Gets the last value of an arg.

        :param str arg: The name of the arg to get.
        :param default: The default value to return if the arg is not found. Not cast to type.
        :param type_: The type that the arg should be returned as.
        :param ephem: Whether to return an ephemeral argument if such exists.
        :raises: InvalidArgument if the arg cannot be cast to the type
        :return: The relevant argument.
        """
        last_arg = self._get_last(arg, ephem=ephem)
        if last_arg is None:
            return default
        try:
            return type_(last_arg)
        except (ValueError, TypeError):
            raise InvalidArgument(f"{last_arg} cannot be cast to {type_.__name__} (in `{arg}`)")

    def adv(self, ea=False, boolwise=False, ephem=False):
        """
        Determines whether to roll with advantage, disadvantage, Elven Accuracy, or no special effect.

        :param ea: Whether to parse for elven accuracy.
        :param boolwise: Whether to return an integer or tribool representation.
        :param ephem: Whether to return an ephemeral argument if such exists.
        :return: -1 for dis, 0 for normal, 1 for adv, 2 for ea
        """
        adv = 0
        if self.last("adv", type_=bool, ephem=ephem):
            adv += 1
        if self.last("dis", type_=bool, ephem=ephem):
            adv += -1
        if ea and self.last("ea", type_=bool, ephem=ephem) and adv > -1:
            return 2
        if not boolwise:
            return adv
        else:
            return {-1: False, 0: None, 1: True}.get(adv)

    def join(self, arg, connector: str, default=None, ephem=False):
        """
        Returns a str formed from all of one arg, joined by a connector.

        :param arg: The arg to join.
        :param connector: What to join the arg by.
        :param default: What to return if the arg does not exist.
        :param ephem: Whether to return an ephemeral argument if such exists.
        :return: The joined str, or default.
        """
        return connector.join(self.get(arg, ephem=ephem)) or default

    def ignore(self, arg):
        """
        Removes any instances of an argument from the result in all contexts (ephemeral included).

        :param arg: The argument to ignore.
        """
        del self[arg]
        for context in self._contexts.values():
            del context[arg]

    # ephemeral setup
    def _parse_ephemeral(self, argdict):
        for key in argdict:
            match = EPHEMERAL_ARG_RE.match(key)
            if match:
                arg, num = match.group(1), match.group(2)
                self._ephemeral[arg].extend([EphemeralValue(int(num), val) for val in argdict[key]])

    # get helpers
    def _get_values(self, arg, ephem=False):
        """Returns a list of arguments."""
        if not ephem:
            return self._parsed[arg]

        out = self._parsed[arg].copy()
        for ephem_val in self._ephemeral[arg]:
            if ephem_val.remaining:
                out.append(ephem_val.value)

        return out

    def _get_last(self, arg, ephem=False):
        """Returns the last argument."""
        if ephem:
            if arg in self._ephemeral:
                for ev in reversed(self._ephemeral[arg]):
                    if ev.remaining:
                        return ev.value
        if arg in self._parsed and self._parsed[arg]:  # intentionally not elif - handles when ephem exhausted
            return self._parsed[arg][-1]
        return None

    # context helpers
    def _setup_originals(self):
        for arg, values in self._parsed.items():
            self._original_parsed[arg] = values.copy()

        for arg, values in self._ephemeral.items():
            self._original_ephemeral[arg] = values.copy()

    def set_context(self, context):
        """
        Sets the current argument parsing context.

        :param context: Any hashable context.
        """
        if context is None:
            self._parsed = self._original_parsed
            self._ephemeral = self._original_ephemeral
        else:
            # build a new parsed and ephemeral list
            new_parsed = collections.defaultdict(lambda: [])
            for arg, values in self._original_parsed.items():
                new_parsed[arg].extend(values)

            for arg, values in self._contexts[context]._parsed.items():
                new_parsed[arg].extend(values)

            new_ephem = collections.defaultdict(lambda: [])
            for arg, values in self._original_ephemeral.items():
                # new_ephem[arg] and original_ephemeral[arg] don't point to the same list
                # but new_ephem[arg][i] and original_ephemeral[arg][i] point to the same value
                # so that changes to the ephemeral state in a context bubble up to the global context
                new_ephem[arg] = values.copy()

            for arg, values in self._contexts[context]._ephemeral.items():
                new_ephem[arg].extend(values.copy())

            self._parsed = new_parsed
            self._ephemeral = new_ephem

    def add_context(self, context, args):
        """
        Adds contextual parsed arguments (arguments that only apply in a given context)

        :param context: The context to add arguments to.
        :param args: The arguments to add.
        :type args: :class:`~utils.argparser.ParsedArguments`
        """
        self._contexts[context] = args

    # builtins
    def __contains__(self, item):
        return (item in self._parsed and self._parsed[item]) or item in self._ephemeral

    def __len__(self):
        return len(self._parsed)

    def __setitem__(self, key, value):
        if not isinstance(value, list):
            value = [value]
        self._parsed[key] = value
        self._original_parsed[key] = value.copy()
        # add it to ephem dict if it matches
        match = EPHEMERAL_ARG_RE.match(key)
        if match:
            arg, num = match.group(1), match.group(2)
            evals = [EphemeralValue(int(num), val) for val in value]
            self._ephemeral[arg].extend(evals)
            self._original_ephemeral[arg].extend(evals.copy())

    def __delitem__(self, arg):
        """
        Removes any instances of an argument from the result in the current context (ephemeral included).

        :param arg: The argument to ignore.
        """
        for container in (self._parsed, self._original_parsed, self._ephemeral, self._original_ephemeral):
            if arg in container:
                del container[arg]

    def __iter__(self):
        return iter(self._parsed.keys())

    def __repr__(self):
        return f"<ParsedArguments parsed={self._parsed.items()} ephemeral={self._ephemeral.items()}>"


class EphemeralValue:
    def __init__(self, num, value):
        self.num = num
        self.remaining = num
        self._value = value

    @property
    def value(self):
        self.remaining -= 1
        return self._value


class CustomStringView(StringView):
    def get_quoted_word(self):
        current = self.current
        if current is None:
            return None

        close_quote = QUOTE_PAIRS.get(current)
        is_quoted = bool(close_quote)
        if is_quoted:
            result = []
            _escaped_quotes = (current, close_quote)
        else:
            result = [current]
            _escaped_quotes = ALL_QUOTES

        while not self.eof:
            current = self.get()
            if not current:
                if is_quoted:
                    # unexpected EOF
                    raise ExpectedClosingQuoteError(close_quote)
                return ''.join(result)

            # currently we accept strings in the format of "hello world"
            # to embed a quote inside the string you must escape it: "a \"world\""
            if current == '\\':
                next_char = self.get()
                if next_char in _escaped_quotes:
                    # escaped quote
                    result.append(next_char)
                else:
                    # different escape character, ignore it
                    self.undo()
                    result.append(current)
                continue

            # opening quote
            if not is_quoted and current in ALL_QUOTES and current != "'":  # special case: apostrophes in mid-string
                close_quote = QUOTE_PAIRS.get(current)
                is_quoted = True
                _escaped_quotes = (current, close_quote)
                continue

            # closing quote
            if is_quoted and current == close_quote:
                next_char = self.get()
                valid_eof = not next_char or next_char.isspace()
                if not valid_eof:  # there's still more in this argument
                    self.undo()
                    close_quote = None
                    is_quoted = False
                    _escaped_quotes = ALL_QUOTES
                    continue

                # we're quoted so it's okay
                return ''.join(result)

            if current.isspace() and not is_quoted:
                # end of word found
                return ''.join(result)

            result.append(current)


if __name__ == '__main__':
    while True:
        try:
            print(argsplit(input('>>> ')))
        except BadArgument as e:
            print(e)
