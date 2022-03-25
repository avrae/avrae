from typing import Iterable, List, Optional, Set, Tuple

from cogs5e.models.errors import InvalidArgument
from cogs5e.models.sheet.resistance import Resistance
from utils.argparser import ParsedArguments
from utils.constants import STAT_ABBREVIATIONS
from utils.enums import AdvantageType
from utils.functions import verbose_stat


def _abstract_str_attr(attr_title: str):
    def impl(_, value):
        return f"{attr_title}: {value}"

    return impl


def _abstract_bool_attr(value_if_present: str):
    return lambda *_: value_if_present


def _abstract_list_attr(attr_title: str):
    def impl(_, value: Iterable):
        values = ", ".join(str(v) for v in value)
        return f"{attr_title}: {values}"

    return impl


class InitPassiveEffect:
    """
    Represents all the passive effects granted by an Initiative effect.
    If adding new passive effects, you need to make 4 updates: __slots__, __init__, from_args, and _str_attr
    (and possibly to/from dict depending on your serialization logic).
    """

    # it might be worth using some kind of descriptor here, because this is a lot of repetition
    __slots__ = (
        "attack_advantage",
        "to_hit_bonus",
        "damage_bonus",
        "magical_damage",
        "silvered_damage",
        "resistances",
        "immunities",
        "vulnerabilities",
        "ignored_resistances",
        "ac_value",
        "ac_bonus",
        "max_hp_value",
        "max_hp_bonus",
        "save_bonus",
        "save_adv",
        "save_dis",
        "check_bonus",
    )

    def __init__(
        self,
        # attacks
        attack_advantage: Optional[AdvantageType] = None,
        to_hit_bonus: Optional[str] = None,
        damage_bonus: Optional[str] = None,
        magical_damage: bool = False,
        silvered_damage: bool = False,
        # resists,
        resistances: List[Resistance] = None,
        immunities: List[Resistance] = None,
        vulnerabilities: List[Resistance] = None,
        ignored_resistances: List[Resistance] = None,
        # general,
        ac_value: Optional[int] = None,
        ac_bonus: Optional[int] = None,
        max_hp_value: Optional[int] = None,
        max_hp_bonus: Optional[int] = None,
        save_bonus: Optional[str] = None,
        save_adv: Set[str] = None,
        save_dis: Set[str] = None,
        check_bonus: Optional[str] = None,
    ):
        if resistances is None:
            resistances = []
        if immunities is None:
            immunities = []
        if vulnerabilities is None:
            vulnerabilities = []
        if ignored_resistances is None:
            ignored_resistances = []
        if save_adv is None:
            save_adv = set()
        if save_dis is None:
            save_dis = set()
        self.attack_advantage = attack_advantage
        self.to_hit_bonus = to_hit_bonus
        self.damage_bonus = damage_bonus
        self.magical_damage = magical_damage
        self.silvered_damage = silvered_damage
        self.resistances = resistances
        self.immunities = immunities
        self.vulnerabilities = vulnerabilities
        self.ignored_resistances = ignored_resistances
        self.ac_value = ac_value
        self.ac_bonus = ac_bonus
        self.max_hp_value = max_hp_value
        self.max_hp_bonus = max_hp_bonus
        self.save_bonus = save_bonus
        self.save_adv = save_adv
        self.save_dis = save_dis
        self.check_bonus = check_bonus

    @classmethod
    def from_dict(cls, d):
        # special deserialization logic
        if "attack_advantage" in d:
            d["attack_advantage"] = AdvantageType(d["attack_advantage"])
        if "resistances" in d:
            d["resistances"] = [Resistance.from_dict(r) for r in d["resistances"]]
        if "immunities" in d:
            d["immunities"] = [Resistance.from_dict(r) for r in d["immunities"]]
        if "vulnerabilities" in d:
            d["vulnerabilities"] = [Resistance.from_dict(r) for r in d["vulnerabilities"]]
        if "ignored_resistances" in d:
            d["ignored_resistances"] = [Resistance.from_dict(r) for r in d["ignored_resistances"]]
        if "save_adv" in d:
            d["save_adv"] = set(d["save_adv"])
        if "save_dis" in d:
            d["save_dis"] = set(d["save_dis"])
        return cls(**d)

    def to_dict(self):
        out = {}
        for attr in self.__slots__:
            if value := getattr(self, attr):
                out[attr] = value

        # special serialization logic
        if "attack_advantage" in out:
            out["attack_advantage"] = self.attack_advantage.value
        if "resistances" in out:
            out["resistances"] = [r.to_dict() for r in self.resistances]
        if "immunities" in out:
            out["immunities"] = [r.to_dict() for r in self.immunities]
        if "vulnerabilities" in out:
            out["vulnerabilities"] = [r.to_dict() for r in self.vulnerabilities]
        if "ignored_resistances" in out:
            out["ignored_resistances"] = [r.to_dict() for r in self.ignored_resistances]
        if "save_adv" in out:
            out["save_adv"] = list(out["save_adv"])
        if "save_dis" in out:
            out["save_dis"] = list(out["save_dis"])

        return out

    def __str__(self):
        values = []
        for attr in self.__slots__:
            value = self._str_attr(attr)
            if value:
                values.append(value)
        return "; ".join(values)

    def __bool__(self):
        """True if there are any passive effects."""
        return any(getattr(self, attr) for attr in self.__slots__)

    # ==== construction ====
    @classmethod
    def from_args(cls, args: ParsedArguments):
        ac_value, ac_bonus = resolve_value_or_bonus(args.get("ac"))
        max_hp_value, max_hp_bonus = resolve_value_or_bonus(args.get("maxhp"))
        return cls(
            attack_advantage=args.adv(ea=True),
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

        value_handler = getattr(self, f"_str_{attr}")
        return value_handler(value)

    _str_to_hit_bonus = _abstract_str_attr("Attack Bonus")
    _str_damage_bonus = _abstract_str_attr("Damage Bonus")
    _str_magical_damage = _abstract_bool_attr("Magical Damage")
    _str_silvered_damage = _abstract_bool_attr("Silvered Damage")
    _str_resistances = _abstract_list_attr("Resistance")
    _str_immunities = _abstract_list_attr("Immunity")
    _str_vulnerabilities = _abstract_list_attr("Vulnerability")
    _str_ignored_resistances = _abstract_list_attr("Neutral")
    _str_ac_value = _abstract_str_attr("AC")
    _str_ac_bonus = _abstract_str_attr("AC Bonus")
    _str_max_hp_value = _abstract_str_attr("Max HP")
    _str_max_hp_bonus = _abstract_str_attr("Max HP Bonus")
    _str_save_bonus = _abstract_str_attr("Save Bonus")
    _str_check_bonus = _abstract_str_attr("Check Bonus")

    @staticmethod
    def _str_attack_advantage(value: AdvantageType):
        if value == AdvantageType.ADV:
            return "Attack Advantage"
        elif value == AdvantageType.DIS:
            return "Attack Disadvantage"
        elif value == AdvantageType.ELVEN:
            return "Attack Advantage: Elven Accuracy"

    @staticmethod
    def _str_save_adv(value: Set[str]):
        if value.issuperset(STAT_ABBREVIATIONS):
            return "Save Advantage: All"
        saves = ", ".join(verbose_stat(s) for s in value)
        return f"Save Advantage: {saves}"

    @staticmethod
    def _str_save_dis(value: Set[str]):
        if value.issuperset(STAT_ABBREVIATIONS):
            return "Save Disadvantage: All"
        saves = ", ".join(verbose_stat(s) for s in value)
        return f"Save Disadvantage: {saves}"


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
