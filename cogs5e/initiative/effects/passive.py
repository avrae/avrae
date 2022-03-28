from typing import Callable, Iterable, List, Optional, Set, Tuple, Type, TypeVar, Union

from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.resistance import Resistance
from utils.argparser import ParsedArguments
from utils.constants import STAT_ABBREVIATIONS
from utils.enums import AdvantageType
from utils.functions import verbose_stat

_OwnerT = TypeVar("_OwnerT")
_DT = TypeVar("_DT")
_DefaultT = TypeVar("_DefaultT")
_SerializedT = TypeVar("_SerializedT")


def noop(x):
    return x


class _PassiveEffect:
    """A descriptor to reduce code repetition when defining passive effects."""

    def __init__(
        self,
        datatype: Type[_DT],
        stringifier: Callable[[_DT], str],
        deserializer: Callable[[_SerializedT], _DT] = noop,
        serializer: Callable[[_DT], _SerializedT] = noop,
        default: _DefaultT = None,
    ):
        self.datatype = datatype
        self.stringifier = stringifier
        self.deserializer = deserializer
        self.serializer = serializer
        self.default = default

    def __set_name__(self, owner: Type[_OwnerT], name: str):
        if not hasattr(owner, "__effect_attrs"):
            owner.__effect_attrs = set()
        if not hasattr(owner, "__effect_deserializers"):
            owner.__effect_deserializers = {}
        if not hasattr(owner, "__effect_serializers"):
            owner.__effect_serializers = {}
        if not hasattr(owner, "__effect_stringifiers"):
            owner.__effect_stringifiers = {}

        owner.__effect_attrs.add(name)
        owner.__effect_deserializers[name] = self.deserializer
        owner.__effect_serializers[name] = self.serializer
        owner.__effect_stringifiers[name] = self.stringifier
        self.private_name = "_" + name

    def __get__(self, obj: _OwnerT, objtype: Type[_OwnerT] = None) -> Union[_DT, _DefaultT]:
        value = getattr(obj, self.private_name, self.default)
        return value

    def __set__(self, obj: _OwnerT, value: _DT):
        if value is None:
            value = self.default
        if not isinstance(value, self.datatype):
            raise ValueError(f"{self.private_name} must be {self.datatype.__name__} but got {type(value).__name__}")
        setattr(obj, self.private_name, value)


# ==== impl ====
# ---- stringifiers ----
def _abstract_str_attr(attr_title: str):
    def impl(value):
        return f"{attr_title}: {value}"

    return impl


def _abstract_bool_attr(value_if_present: str):
    return lambda *_: value_if_present


def _abstract_list_attr(attr_title: str):
    def impl(value: Iterable):
        values = ", ".join(str(v) for v in value)
        return f"{attr_title}: {values}"

    return impl


def _str_attack_advantage(value: AdvantageType):
    if value == AdvantageType.ADV:
        return "Attack Advantage"
    elif value == AdvantageType.DIS:
        return "Attack Disadvantage"
    elif value == AdvantageType.ELVEN:
        return "Attack Advantage: Elven Accuracy"


def _str_save_adv(value: Set[str]):
    if value.issuperset(STAT_ABBREVIATIONS):
        return "Save Advantage: All"
    saves = ", ".join(verbose_stat(s) for s in value)
    return f"Save Advantage: {saves}"


def _str_save_dis(value: Set[str]):
    if value.issuperset(STAT_ABBREVIATIONS):
        return "Save Disadvantage: All"
    saves = ", ".join(verbose_stat(s) for s in value)
    return f"Save Disadvantage: {saves}"


# ---- main class ----
class InitPassiveEffect:
    """
    Represents all the passive effects granted by an Initiative effect.
    If adding new passive effects, add a new classvar below.
    """

    __effect_attrs = set()
    __effect_stringifiers = {}
    __effect_deserializers = {}
    __effect_serializers = {}

    attack_advantage = _PassiveEffect(
        AdvantageType,
        stringifier=_str_attack_advantage,
        deserializer=lambda data: AdvantageType(data),
        serializer=lambda data: data.value,
    )
    to_hit_bonus = _PassiveEffect(str, stringifier=_abstract_str_attr("Attack Bonus"))
    damage_bonus = _PassiveEffect(str, stringifier=_abstract_str_attr("Damage Bonus"))
    magical_damage = _PassiveEffect(bool, stringifier=_abstract_bool_attr("Magical Damage"))
    silvered_damage = _PassiveEffect(bool, stringifier=_abstract_bool_attr("Silvered Damage"))
    resistances = _PassiveEffect(
        List[Resistance],
        default=[],
        stringifier=_abstract_list_attr("Resistance"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    immunities = _PassiveEffect(
        List[Resistance],
        default=[],
        stringifier=_abstract_list_attr("Immunity"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    vulnerabilities = _PassiveEffect(
        List[Resistance],
        default=[],
        stringifier=_abstract_list_attr("Vulnerability"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    ignored_resistances = _PassiveEffect(
        List[Resistance],
        default=[],
        stringifier=_abstract_list_attr("Neutral"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    ac_value = _PassiveEffect(int, stringifier=_abstract_str_attr("AC"))
    ac_bonus = _PassiveEffect(int, stringifier=_abstract_str_attr("AC Bonus"))
    max_hp_value = _PassiveEffect(int, stringifier=_abstract_str_attr("Max HP"))
    max_hp_bonus = _PassiveEffect(int, stringifier=_abstract_str_attr("Max HP Bonus"))
    save_bonus = _PassiveEffect(str, stringifier=_abstract_str_attr("Save Bonus"))
    save_adv = _PassiveEffect(
        Set[str],
        default=set(),
        stringifier=_str_save_adv,
        deserializer=lambda data: set(data),
        serializer=lambda data: list(data),
    )
    save_dis = _PassiveEffect(
        Set[str],
        default=set(),
        stringifier=_str_save_adv,
        deserializer=lambda data: set(data),
        serializer=lambda data: list(data),
    )
    check_bonus = _PassiveEffect(str, stringifier=_abstract_str_attr("Check Bonus"))

    def __init__(self, **kwargs):
        for attr in kwargs:
            if attr not in self.__effect_attrs:
                raise ValueError(f"{attr!r} is not a valid effect attribute.")
            setattr(self, attr, kwargs[attr])

    @classmethod
    def from_dict(cls, d):
        for attr in d:
            if attr not in cls.__effect_attrs:
                raise ValueError(f"{attr!r} is not a valid effect attribute.")
        return cls(**{k: cls.__effect_deserializers[k](v) for k, v in d.items()})

    def to_dict(self):
        out = {}
        for attr in self.__effect_attrs:
            if value := getattr(self, attr):
                out[attr] = self.__effect_serializers[attr](value)
        return out

    def __str__(self):
        values = []
        for attr in self.__effect_attrs:
            value = self._str_attr(attr)
            if value:
                values.append(value)
        return "; ".join(values)

    def __bool__(self):
        """True if there are any passive effects."""
        return any(getattr(self, attr) for attr in self.__effect_attrs)

    # ==== construction ====
    @classmethod
    def from_args(cls, args: ParsedArguments):
        ac_value, ac_bonus = resolve_value_or_bonus(args.get("ac"))
        max_hp_value, max_hp_bonus = resolve_value_or_bonus(args.get("maxhp"))
        return cls(
            attack_advantage=AdvantageType(args.adv(ea=True)),
            to_hit_bonus=args.join("b", "+"),
            damage_bonus=args.join("d", "+"),
            magical_damage="magical" in args,
            silvered_damage="silvered" in args,
            resistances=[Resistance.from_str(v) for v in args.get("resist")],
            immunities=[Resistance.from_str(v) for v in args.get("immune")],
            vulnerabilities=[Resistance.from_str(v) for v in args.get("vuln")],
            ignored_resistances=[Resistance.from_str(v) for v in args.get("neutral")],
            ac_value=ac_value,
            ac_bonus=ac_bonus,
            max_hp_value=max_hp_value,
            max_hp_bonus=max_hp_bonus,
            save_bonus=args.join("sb", "+"),
            save_adv=resolve_save_advs(args.get("sadv")),
            save_dis=resolve_save_advs(args.get("sdis")),
            check_bonus=args.join("cb", "+"),
        )

    # ==== stringification ====
    def _str_attr(self, attr: str) -> Optional[str]:
        """
        Given an attribute name, return the stringification of that attribute.

        Raises AttributeError if either the attribute or `_str_{attribute_name}` does not exist.
        """
        value = getattr(self, attr)
        if not value:
            return

        value_handler = self.__effect_stringifiers[attr]
        return value_handler(value)


def resolve_value_or_bonus(values: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    Takes a list of arguments, which are strings that may start with + or -, and returns the pair of
    (max of values, sum of bonuses).
    """
    set_value = None
    bonus = None

    for value in values:
        try:
            if value.startswith(("+", "-")):
                bonus = (bonus or 0) + int(value)
            else:
                set_value = max(set_value or 0, int(value))
        except (ValueError, TypeError):
            continue
    return set_value, bonus


def resolve_save_advs(values: List[str]) -> Set[str]:
    out = set()
    for arg in values:
        if arg is True or arg.lower() == "all":
            return set(STAT_ABBREVIATIONS)
        stat_abbr = arg[:3].lower()  # only check first three arg characters against STAT_ABBREVIATIONS
        if stat_abbr not in STAT_ABBREVIATIONS:
            raise InvalidArgument(f"{arg} is not a valid stat")
        out.add(stat_abbr)
    return out
