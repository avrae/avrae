import collections
import itertools
import re
import string
from typing import Iterator

from disnake.ext.commands import BadArgument, ExpectedClosingQuoteError
from disnake.ext.commands.view import StringView

from cogs5e.models.errors import InvalidArgument

EPHEMERAL_ARG_RE = re.compile(r"(\S+)(\d+)")
SINGLE_ARG_RE = re.compile(r"([a-zA-Z]\S*(?<!\d))(\d+)?")  # g1: flag name g2: ephem?
FLAG_ARG_RE = re.compile(r"-+([a-zA-Z]\S*(?<!\d))(\d+)?")  # g1: flag name g2: ephem?
SINGLE_ARG_EXCEPTIONS = {"-i", "-h", "-v"}


def argsplit(args: str):
    view = CustomStringView(args.strip())
    args = []
    while not view.eof:
        view.skip_ws()
        args.append(view.get_quoted_word())  # _quoted_word(view))
    return args


# ==== argparse ====
class Argument:
    def __init__(self, name: str, value, pos: int):
        self.name = name
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"<{type(self).__name__} name={self.name!r} value={self.value!r} pos={self.pos}>"

    def __eq__(self, other):
        return self.name == other.name and self.value == other.value and self.pos == other.pos


class EphemeralArgument(Argument):
    def __init__(self, name: str, value, pos: int, uses: int):
        super().__init__(name, value, pos)
        self.uses = uses
        self.used = 0

    def has_remaining_uses(self):
        return self.used < self.uses

    def __repr__(self):
        return (
            f"<{type(self).__name__} name={self.name!r} value={self.value!r} pos={self.pos} uses={self.uses} "
            f"used={self.used}>"
        )

    def __eq__(self, other):
        return (
            self.name == other.name and self.value == other.value and self.pos == other.pos and self.uses == other.uses
        )


def _argparse_arg(name: str, ephem: str | None, value, idx: int, parse_ephem: bool) -> Argument:
    if ephem and parse_ephem:
        return EphemeralArgument(name=name, value=value, pos=idx, uses=int(ephem))
    elif ephem:
        return Argument(name=name + ephem, value=value, pos=idx)
    else:
        return Argument(name=name, value=value, pos=idx)


def _argparse_iterator(args: list[str], parse_ephem: bool) -> Iterator[Argument]:
    flag_arg_state = None  # state: name, ephem?
    idx = 0
    for idx, arg in enumerate(args):
        # prio: single arg exceptions, flag args, values, single args
        if arg in SINGLE_ARG_EXCEPTIONS:
            if flag_arg_state is not None:
                name, ephem = flag_arg_state
                yield _argparse_arg(name, ephem, True, idx - 1, parse_ephem)
                flag_arg_state = None
            yield Argument(name=arg.lstrip("-"), value=True, pos=idx)
        elif match := FLAG_ARG_RE.fullmatch(arg):
            if flag_arg_state is not None:
                name, ephem = flag_arg_state
                yield _argparse_arg(name, ephem, True, idx - 1, parse_ephem)
            flag_arg_state = match.group(1), match.group(2)
        elif flag_arg_state is not None:
            name, ephem = flag_arg_state
            yield _argparse_arg(name, ephem, arg, idx - 1, parse_ephem)
            flag_arg_state = None
        elif match := SINGLE_ARG_RE.fullmatch(arg):
            name = match.group(1)
            ephem = match.group(2)
            yield _argparse_arg(name, ephem, True, idx, parse_ephem)
        # else: the current element at the head is junk

    if flag_arg_state is not None:
        name, ephem = flag_arg_state
        yield _argparse_arg(name, ephem, True, idx, parse_ephem)


# --- main entrypoint ---
def argparse(args, character=None, splitter=argsplit, parse_ephem=True) -> "ParsedArguments":
    """
    Given an argument string, returns the parsed arguments using the argument nondeterministic finite automaton.
    If *character* is given, evaluates {}-style math inside the string before parsing.
    If the argument is a string, uses *splitter* to split the string into args.
    If *parse_ephem* is False, arguments like ``-d1`` are saved literally rather than as an ephemeral argument.

    Draconic docs for this are not linked, and will have to be manually updated if this function changes.

    .. note::

        Arguments must begin with a letter and not end with a number (e.g. ``d``, ``e12s``, ``a!!``). Values immediately
        following a flag argument (i.e. one that starts with ``-``) will not be parsed as arguments unless they are also
        a flag argument.

        There are three exceptions to this rule: ``-i``, ``-h``, and ``-v``, none of which take additional values.
    """
    if isinstance(args, str):
        args = splitter(args)

    if character:
        from aliasing.evaluators import MathEvaluator

        evaluator = MathEvaluator.with_character(character)
        args = [evaluator.transformed_str(a) for a in args]

    parsed_args = list(_argparse_iterator(args, parse_ephem))
    return ParsedArguments(parsed_args)


class ParsedArguments:
    def __init__(self, args: list[Argument]):
        self._parsed = collections.defaultdict(lambda: [])
        for arg in args:
            self._parsed[arg.name].append(arg)
        self._current_context = None
        self._contexts = {}  # type: dict[..., ParsedArguments]

    @classmethod
    def from_dict(cls, d):
        inst = cls([])
        for key, value in d.items():
            inst[key] = value
        return inst

    @classmethod
    def empty_args(cls):
        return cls([])

    # basic argument getting

    # Have to escape the _ in the type_ parameter for docs
    # noinspection PyIncorrectDocstring
    def get(self, arg, default=None, type_=str, ephem=False):
        """
        Gets a list of all values of an argument.

        :param str arg: The name of the arg to get.
        :param default: The default value to return if the arg is not found. Not cast to type.
        :param type type\_: The type that each value in the list should be returned as.
        :param bool ephem: Whether to add applicable ephemeral arguments to the returned list.
        :return: The relevant argument list.
        :rtype: list
        """
        if default is None:
            default = []
        parsed = list(self._get_values(arg, ephem=ephem))
        if not parsed:
            return default
        try:
            return [type_(v) for v in parsed]
        except (ValueError, TypeError):
            raise InvalidArgument(f"One or more arguments cannot be cast to {type_.__name__} (in `{arg}`)")

    # Have to escape the _ in the type_ parameter for docs
    # noinspection PyIncorrectDocstring
    def last(self, arg, default=None, type_=str, ephem=False):
        """
        Gets the last value of an arg.

        :param str arg: The name of the arg to get.
        :param default: The default value to return if the arg is not found. Not cast to type.
        :param type type\_: The type that the arg should be returned as.
        :param bool ephem: Whether to return an ephemeral argument if such exists.
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

    def adv(self, eadv=False, boolwise=False, ephem=False, custom: dict = None):
        """
        Determines whether to roll with advantage, disadvantage, Elven Accuracy, or no special effect.

        :param eadv: Whether to parse for elven accuracy.
        :param boolwise: Whether to return an integer or tribool representation.
        :param ephem: Whether to return an ephemeral argument if such exists.
        :param custom: Dictionary of custom values to parse for. There should be a key for each value you want to
                       overwrite. ``custom={'adv': 'custom_adv'}`` would allow you to parse for advantage if the
                       ``custom_adv`` argument is found.

        :return: -1 for dis, 0 for normal, 1 for adv, 2 for eadv
        """
        adv_str, dis_str, ea_str = "adv", "dis", "eadv"
        if custom is not None:
            if "adv" in custom:
                adv_str = custom["adv"]
            if "dis" in custom:
                dis_str = custom["dis"]
            if "eadv" in custom:
                ea_str = custom["eadv"]

        adv_arg = self.last(adv_str, default=False, type_=bool, ephem=ephem)
        dis_arg = self.last(dis_str, default=False, type_=bool, ephem=ephem)
        ea_arg = eadv and self.last(ea_str, default=False, type_=bool, ephem=ephem)

        if ea_arg and not dis_arg:
            out = 2
        elif dis_arg and not (adv_arg or ea_arg):
            out = -1
        elif adv_arg and not dis_arg:
            out = 1
        else:
            out = 0

        if not boolwise:
            return out
        else:
            return {-1: False, 0: None, 1: True}.get(out)

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

    def update(self, new):
        """
        Updates the arguments in this argument list from a dict.

        :param new: The new values for each argument.
        :type new: dict[str, str] or dict[str, list[str]]
        """
        for k, v in new.items():
            self[k] = v

    def update_nx(self, new):
        """
        Like ``.update()``, but only fills in arguments that were not already parsed. Ignores the argument if the
        value is None.

        :param new: The new values for each argument.
        :type new: dict[str, str] or dict[str, list[str]] or dict[str, None]
        """
        for k, v in new.items():
            if k not in self and v is not None:
                self[k] = v

    # get helpers
    @staticmethod
    def _yield_from_iterable(iterable: Iterator[Argument], ephem: bool):
        for value in iterable:
            if not ephem and isinstance(value, EphemeralArgument):
                continue
            elif isinstance(value, EphemeralArgument):
                if not value.has_remaining_uses():
                    continue
                value.used += 1
            yield value.value

    def _get_values(self, arg, ephem=False):
        """Returns an iterator of arguments."""
        iterable = self._parsed[arg]
        if self._current_context in self._contexts:
            iterable = itertools.chain(self._parsed[arg], self._contexts[self._current_context]._parsed[arg])
        yield from self._yield_from_iterable(iterable, ephem)

    def _get_last(self, arg, ephem=False):
        """Returns the last argument, or None if no valid argument is found."""
        iterable = reversed(self._parsed[arg])
        if self._current_context in self._contexts:
            iterable = itertools.chain(
                reversed(self._contexts[self._current_context]._parsed[arg]), reversed(self._parsed[arg])
            )
        return next((self._yield_from_iterable(iterable, ephem)), None)

    # context helpers
    def set_context(self, context):
        """
        Sets the current argument parsing context.

        :param context: Any hashable context.
        """
        self._current_context = context

    def add_context(self, context, args):
        """
        Adds contextual parsed arguments (arguments that only apply in a given context)

        :param context: The context to add arguments to.
        :param args: The arguments to add.
        :type args: :class:`~utils.argparser.ParsedArguments`, or dict[str, list[str]]
        """
        if isinstance(args, dict):
            if all(
                isinstance(k, (collections.UserString, str))
                and isinstance(v, (collections.UserList, list))
                and all(isinstance(i, (collections.UserString, str)) for i in v)
                for k, v in args.items()
            ):
                args = ParsedArguments.from_dict(args)
            else:
                raise InvalidArgument(f"Argument is not in the format dict[str, list[str]] (in {args})")
        elif not isinstance(args, ParsedArguments):
            raise InvalidArgument(f"Argument is not a dict or ParsedArguments (in {args})")

        self._contexts[context] = args

    # builtins
    def __contains__(self, item):
        return item in self._parsed and self._parsed[item]

    def __len__(self):
        return len(self._parsed)

    def __setitem__(self, key, value):
        """
        :type key: str
        :type value: str or bool or list[str or bool]
        """
        if isinstance(value, (collections.UserList, list)):
            true_val = [Argument(key, v, idx) for idx, v in enumerate(value)]
        else:
            true_val = [Argument(key, value, 0)]
        self._parsed[key] = true_val
        # also parse for ephem arg
        if match := EPHEMERAL_ARG_RE.fullmatch(key):
            arg, num = match.group(1), match.group(2)
            ephem_val = [EphemeralArgument(arg, v.value, v.pos, int(num)) for v in true_val]
            self._parsed[arg] = ephem_val

    def __delitem__(self, arg):
        """
        Removes any instances of an argument from the result in the current context (ephemeral included).

        :param arg: The argument to ignore.
        """
        if arg in self._parsed:
            del self._parsed[arg]

    def __iter__(self):
        return iter(self._parsed.keys())

    def __repr__(self):
        # please ignore this hack to make the repr prettier
        return f"<ParsedArguments parsed={dict.__repr__(self._parsed)} context={self._current_context}>"


# ==== other helpers ====
def argquote(arg: str):
    if any(char in arg for char in string.whitespace):
        arg = arg.replace('"', '\\"')  # re.sub(r'(?<!\\)"', r'\"', arg)
        arg = f'"{arg}"'
    return arg


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
                return "".join(result)

            # currently we accept strings in the format of "hello world"
            # to embed a quote inside the string you must escape it: "a \"world\""
            if current == "\\":
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
            if (
                not is_quoted and current in ALL_QUOTES and current != "'" and current != "’"
            ):  # special case: apostrophes in mid-string
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
                return "".join(result)

            if current.isspace() and not is_quoted:
                # end of word found
                return "".join(result)

            result.append(current)


if __name__ == "__main__":
    while True:
        try:
            print(argsplit(input(">>> ")))
        except BadArgument as e:
            print(e)
