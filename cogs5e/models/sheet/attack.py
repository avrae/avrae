from typing import Optional, TYPE_CHECKING

from utils import enums

if TYPE_CHECKING:
    from cogs5e.models.automation import Automation


class Attack:
    """
    Actually an automation script.
    """

    def __init__(
        self,
        name: str,
        automation: "Automation",
        verb: str = None,
        proper: bool = False,
        criton: int = None,
        phrase: str = None,
        thumb: str = None,
        extra_crit_damage: str = None,
        activation_type: enums.ActivationType = None,
        **_,
    ):
        self.name = name
        self.automation = automation
        self.verb = verb
        self.proper = proper
        self.criton = criton
        self.phrase = phrase
        self.thumb = thumb
        self.extra_crit_damage = extra_crit_damage
        self.activation_type = activation_type

    # ==== ser / deser ====
    @classmethod
    def from_dict(cls, d):
        if "attackBonus" in d:
            return cls.from_old(d)
        elif "bonus" in d or d.get("_v", 0) < 2:
            return cls.from_v1(d)

        from cogs5e.models import automation

        the_automation = automation.Automation.from_data(d["automation"])
        activation_type = enums.ActivationType(d["activation_type"]) if d.get("activation_type") is not None else None

        return cls(
            name=d["name"],
            automation=the_automation,
            verb=d.get("verb"),
            proper=d.get("proper", False),
            criton=d.get("criton"),
            phrase=d.get("phrase"),
            thumb=d.get("thumb"),
            extra_crit_damage=d.get("extra_crit_damage"),
            activation_type=activation_type,
        )

    @classmethod
    def from_old(cls, d):
        if "attackBonus" in d and d["attackBonus"]:
            bonus = d["attackBonus"]
        else:
            bonus = None
        damage = d.get("damage")
        details = d.get("details")
        return cls(d["name"], old_to_automation(bonus, damage, details))

    @classmethod
    def from_v1(cls, d):
        bonus = d.get("bonus_calc") or d["bonus"]
        damage = d.get("damage_calc") or d["damage"]
        return cls(d["name"], old_to_automation(bonus, damage, d["details"]))

    def to_dict(self):
        base = {"name": self.name, "automation": self.automation.to_dict(), "_v": 2}
        if self.proper:
            base["proper"] = True

        for optattr in ("verb", "criton", "phrase", "thumb", "extra_crit_damage"):
            if (val := getattr(self, optattr)) is not None:
                base[optattr] = val

        if self.activation_type is not None:
            base["activation_type"] = self.activation_type.value
        return base

    # ==== main ====
    @classmethod
    def new(
        cls,
        name: str,
        bonus_calc: str = None,
        damage_calc: str = None,
        details: str = None,
        verb: Optional[str] = None,
        proper: bool = False,
        criton: Optional[int] = None,
        phrase: Optional[str] = None,
        thumb: Optional[str] = None,
        extra_crit_damage: Optional[str] = None,
        activation_type: Optional[enums.ActivationType] = None,
    ):
        """Creates a new attack for a character."""
        if bonus_calc is not None:
            bonus_calc = str(bonus_calc)

        return cls(
            name,
            old_to_automation(bonus_calc, damage_calc, details),
            verb=verb,
            proper=proper,
            criton=criton,
            phrase=phrase,
            thumb=thumb,
            extra_crit_damage=extra_crit_damage,
            activation_type=activation_type,
        )

    @classmethod
    def copy(cls, other: "Attack"):
        """Returns a shallow copy of an attack."""
        return cls(
            other.name,
            other.automation,
            other.verb,
            other.proper,
            other.criton,
            other.phrase,
            other.thumb,
            other.extra_crit_damage,
            other.activation_type,
        )

    def build_str(self, caster):
        return f"**{self.name}**: {self.automation.build_str(caster)}"

    def __str__(self):
        return f"**{self.name}**: {str(self.automation)}"

    # ==== helpers ====
    # for custom behaviour defined by wrappers, passed to the automation context when run
    __run_automation_kwargs__ = {}


class AttackList:
    def __init__(self, attacks=None):
        if attacks is None:
            attacks = []
        self.attacks = attacks

    @classmethod
    def from_dict(cls, l):  # technicaly from_list, but consistency
        return cls([Attack.from_dict(atk) for atk in l])

    def to_dict(self):  # technically to_list
        return [a.to_dict() for a in self.attacks]

    # utils
    def build_str(self, caster):
        return "\n".join(atk.build_str(caster) for atk in sorted(self.attacks, key=lambda atk: atk.name))

    def __str__(self):
        return "\n".join(str(atk) for atk in self.attacks)

    @property
    def no_activation_types(self):
        """Returns an AttackList of attacks that have no defined activation type."""
        return AttackList([a for a in self.attacks if a.activation_type is None])

    @property
    def full_actions(self):
        """Returns an AttackList of attacks that require a full action to activate."""
        return AttackList([a for a in self.attacks if a.activation_type == enums.ActivationType.ACTION])

    @property
    def bonus_actions(self):
        """Returns an AttackList of attacks that require a bonus action to activate."""
        return AttackList([a for a in self.attacks if a.activation_type == enums.ActivationType.BONUS_ACTION])

    @property
    def reactions(self):
        """Returns an AttackList of attacks that require a reaction to activate."""
        return AttackList([a for a in self.attacks if a.activation_type == enums.ActivationType.REACTION])

    @property
    def legendary_actions(self):
        """Returns an AttackList that require a legendary action to activate."""
        return AttackList([a for a in self.attacks if a.activation_type == enums.ActivationType.LEGENDARY])

    @property
    def mythic_actions(self):
        """Returns an AttackList that require a legendary action to activate."""
        return AttackList([a for a in self.attacks if a.activation_type == enums.ActivationType.MYTHIC])

    @property
    def lair_actions(self):
        """Returns a AttackList of actions that require a lair action to activate."""
        return AttackList([a for a in self.attacks if a.activation_type == enums.ActivationType.LAIR])

    @property
    def other_attacks(self):
        """Returns an AttackList of attacks that do not fall into the other action categories."""
        return AttackList([
            a
            for a in self.attacks
            if a.activation_type
            not in (
                enums.ActivationType.ACTION,
                enums.ActivationType.BONUS_ACTION,
                enums.ActivationType.REACTION,
                enums.ActivationType.LEGENDARY,
                enums.ActivationType.MYTHIC,
                enums.ActivationType.LAIR,
                None,
            )
        ])

    # list compat
    def append(self, attack):
        self.attacks.append(attack)

    def extend(self, attacks):
        self.attacks.extend(attacks)

    def remove(self, attack):
        self.attacks.remove(attack)

    def __iter__(self):
        return iter(self.attacks)

    def __getitem__(self, item):
        return self.attacks[item]

    def __add__(self, other):
        return AttackList(self.attacks + other.attacks)

    def __len__(self):
        return len(self.attacks)

    def __bool__(self):
        return bool(self.attacks)


def old_to_automation(bonus: str | None = None, damage: str | None = None, details: str | None = None):
    """Returns an Automation instance representing an old attack."""
    from cogs5e.models import automation

    if damage:
        damage = automation.Damage(damage)

    if bonus:
        hit = [damage] if damage else []
        attack_eff = [automation.Attack(hit=hit, miss=[], attackBonus=str(bonus).strip("{}<>"))]
    else:
        attack_eff = [damage] if damage else []

    effects = [automation.Target("each", attack_eff)] if attack_eff else []
    if details:
        # noinspection PyTypeChecker
        # PyCharm thinks this should be a list of Target instead of a list of Effect
        effects.append(automation.Text(details))

    return automation.Automation(effects)
