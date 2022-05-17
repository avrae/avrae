from typing import Callable, Iterable, List, Optional, Set, Tuple, Type, TypeVar, Union

from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.resistance import Resistance
from utils.argparser import ParsedArguments
from utils.constants import SKILL_NAMES, STAT_ABBREVIATIONS, STAT_NAMES
from utils.enums import AdvantageType
from utils.functions import camel_to_title, exactly_one, verbose_stat

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
        stringifier: Callable[[_DT], str],
        deserializer: Callable[[_SerializedT], _DT] = noop,
        serializer: Callable[[_DT], _SerializedT] = noop,
        default: _DefaultT = None,
    ):
        self.stringifier = stringifier
        self.deserializer = deserializer
        self.serializer = serializer
        self.default = default

    def __set_name__(self, owner: Type[_OwnerT], name: str):
        if not hasattr(owner, "__effect_attrs__"):
            owner.__effect_attrs__ = set()
        if not hasattr(owner, "__effect_deserializers__"):
            owner.__effect_deserializers__ = {}
        if not hasattr(owner, "__effect_serializers__"):
            owner.__effect_serializers__ = {}
        if not hasattr(owner, "__effect_stringifiers__"):
            owner.__effect_stringifiers__ = {}

        owner.__effect_attrs__.add(name)
        owner.__effect_deserializers__[name] = self.deserializer
        owner.__effect_serializers__[name] = self.serializer
        owner.__effect_stringifiers__[name] = self.stringifier
        self.private_name = "_" + name

    def __get__(self, obj: _OwnerT, objtype: Type[_OwnerT] = None) -> Union[_DT, _DefaultT]:
        value = getattr(obj, self.private_name, self.default)
        return value

    def __set__(self, obj: _OwnerT, value: _DT):
        if value is None:
            value = self.default
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
    saves = ", ".join(verbose_stat(s) for s in value if s in STAT_ABBREVIATIONS)
    # ^ if s...: temp fix for SENTRY-22D, happens when migrating old ieffect with -sadv all
    return f"Save Advantage: {saves}"


def _str_save_dis(value: Set[str]):
    if value.issuperset(STAT_ABBREVIATIONS):
        return "Save Disadvantage: All"
    saves = ", ".join(verbose_stat(s) for s in value if s in STAT_ABBREVIATIONS)
    return f"Save Disadvantage: {saves}"


def _str_check_adv(value: Set[str]):
    if value.issuperset(STAT_NAMES):
        return "Check Advantage: All"
    saves = ", ".join(camel_to_title(s) for s in value)
    return f"Check Advantage: {saves}"


def _str_check_dis(value: Set[str]):
    if value.issuperset(STAT_NAMES):
        return "Check Disadvantage: All"
    saves = ", ".join(camel_to_title(s) for s in value)
    return f"Check Disadvantage: {saves}"


# ---- main class ----
class InitPassiveEffect:
    """
    Represents all the passive effects granted by an Initiative effect.
    If adding new passive effects, add a new classvar below.

    Other places to touch:
    - cogs5e.models.initiative.cog.effect (docs)
    - cogs5e.models.automation.effects.ieffect
    - docs.automation_ref#ieffect (docs)
    - any consumers of the new passive effect
    - the automation-common library: validation.models.PassiveEffects (otherwise the norm step of !a import eats keys)
    """

    __effect_attrs__ = set()
    __effect_stringifiers__ = {}
    __effect_deserializers__ = {}
    __effect_serializers__ = {}

    attack_advantage: AdvantageType = _PassiveEffect(
        stringifier=_str_attack_advantage,
        deserializer=lambda data: AdvantageType(data),
        serializer=lambda data: data.value,
    )
    to_hit_bonus: str = _PassiveEffect(stringifier=_abstract_str_attr("Attack Bonus"))
    damage_bonus: str = _PassiveEffect(stringifier=_abstract_str_attr("Damage Bonus"))
    magical_damage: bool = _PassiveEffect(stringifier=_abstract_bool_attr("Magical Damage"))
    silvered_damage: bool = _PassiveEffect(stringifier=_abstract_bool_attr("Silvered Damage"))
    resistances: List[Resistance] = _PassiveEffect(
        default=[],
        stringifier=_abstract_list_attr("Resistance"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    immunities: List[Resistance] = _PassiveEffect(
        default=[],
        stringifier=_abstract_list_attr("Immunity"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    vulnerabilities: List[Resistance] = _PassiveEffect(
        default=[],
        stringifier=_abstract_list_attr("Vulnerability"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    ignored_resistances: List[Resistance] = _PassiveEffect(
        default=[],
        stringifier=_abstract_list_attr("Neutral"),
        deserializer=lambda data: [Resistance.from_dict(r) for r in data],
        serializer=lambda data: [r.to_dict() for r in data],
    )
    ac_value: int = _PassiveEffect(stringifier=_abstract_str_attr("AC"))
    ac_bonus: int = _PassiveEffect(stringifier=_abstract_str_attr("AC Bonus"))
    max_hp_value: int = _PassiveEffect(stringifier=_abstract_str_attr("Max HP"))
    max_hp_bonus: int = _PassiveEffect(stringifier=_abstract_str_attr("Max HP Bonus"))
    save_bonus: str = _PassiveEffect(stringifier=_abstract_str_attr("Save Bonus"))
    save_adv: Set[str] = _PassiveEffect(
        default=set(),
        stringifier=_str_save_adv,
        deserializer=lambda data: set(data),
        serializer=lambda data: list(data),
    )
    save_dis: Set[str] = _PassiveEffect(
        default=set(),
        stringifier=_str_save_dis,
        deserializer=lambda data: set(data),
        serializer=lambda data: list(data),
    )
    check_bonus: str = _PassiveEffect(stringifier=_abstract_str_attr("Check Bonus"))
    check_adv: Set[str] = _PassiveEffect(
        default=set(),
        stringifier=_str_check_adv,
        deserializer=lambda data: set(data),
        serializer=lambda data: list(data),
    )
    check_dis: Set[str] = _PassiveEffect(
        default=set(),
        stringifier=_str_check_dis,
        deserializer=lambda data: set(data),
        serializer=lambda data: list(data),
    )

    def __init__(self, **kwargs):
        for attr in kwargs:
            if attr not in self.__effect_attrs__:
                raise ValueError(f"{attr!r} is not a valid effect attribute.")
            setattr(self, attr, kwargs[attr])

    @classmethod
    def from_dict(cls, d):
        for attr in d:
            if attr not in cls.__effect_attrs__:
                raise ValueError(f"{attr!r} is not a valid effect attribute.")
        return cls(**{k: cls.__effect_deserializers__[k](v) for k, v in d.items()})

    def to_dict(self):
        out = {}
        for attr in self.__effect_attrs__:
            if value := getattr(self, attr):
                out[attr] = self.__effect_serializers__[attr](value)
        return out

    def __str__(self):
        values = []
        for attr in self.__effect_attrs__:
            value = self._str_attr(attr)
            if value:
                values.append(value)
        return "; ".join(values)

    def __bool__(self):
        """True if there are any passive effects."""
        return any(getattr(self, attr) for attr in self.__effect_attrs__)

    # ==== construction ====
    @classmethod
    def from_args(cls, args: ParsedArguments):
        ac_value, ac_bonus = resolve_value_or_bonus(args.get("ac"))
        max_hp_value, max_hp_bonus = resolve_value_or_bonus(args.get("maxhp"))
        return cls(
            attack_advantage=AdvantageType(args.adv(eadv=True)),
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
            check_adv=resolve_check_advs(args.get("cadv")),
            check_dis=resolve_check_advs(args.get("cdis")),
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

        value_handler = self.__effect_stringifiers__[attr]
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
        if arg is True or arg.lower() == "all" or arg == "True":
            return set(STAT_ABBREVIATIONS)
        stat_abbr = arg[:3].lower()  # only check first three arg characters against STAT_ABBREVIATIONS
        if stat_abbr not in STAT_ABBREVIATIONS:
            raise InvalidArgument(f"{arg} is not a valid stat")
        out.add(stat_abbr)
    return out


def resolve_check_advs(values: List[str]) -> Set[str]:
    out = set()
    for arg in values:
        if arg is True or arg.lower() == "all" or arg == "True":
            return set(SKILL_NAMES)
        skill_options = [k for k in SKILL_NAMES if k.lower().startswith(arg)]
        if not skill_options:
            raise InvalidArgument(f"`{arg}` is not a valid skill")
        elif len(skill_options) > 1:
            raise InvalidArgument(
                f"`{arg}` could be multiple skills: {', '.join(skill_options)}. Please use a more precise skill key."
            )
        out.add(skill_options[0])
    return out
