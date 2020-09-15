class Attack:
    """
    Actually an automation script.
    """

    def __init__(self, name, automation, verb=None, proper=False):
        self.name = name
        self.automation = automation
        self.verb = verb
        self.proper = proper

    @classmethod
    def from_dict(cls, d):
        if 'attackBonus' in d:
            return cls.from_old(d)
        elif 'bonus' in d or d.get('_v', 0) < 2:
            return cls.from_v1(d)

        from cogs5e.models import automation
        return cls(name=d['name'], automation=automation.Automation.from_data(d['automation']),
                   verb=d.get('verb'), proper=d.get('proper'))

    @classmethod
    def from_old(cls, d):
        if 'attackBonus' in d and d['attackBonus']:
            bonus = d['attackBonus']
        else:
            bonus = None
        damage = d.get('damage')
        details = d.get('details')
        return cls(d['name'], old_to_automation(bonus, damage, details))

    @classmethod
    def from_v1(cls, d):
        bonus = d.get('bonus_calc') or d['bonus']
        damage = d.get('damage_calc') or d['damage']
        return cls(d['name'], old_to_automation(bonus, damage, d['details']))

    def to_dict(self):
        return {"name": self.name, "automation": self.automation.to_dict(), "verb": self.verb, "proper": self.proper,
                "_v": 2}

    # ---------- main funcs ----------
    @classmethod
    def new(cls, name, bonus_calc: str = None, damage_calc: str = None, details: str = None):
        """Creates a new attack for a character."""
        if bonus_calc is not None:
            bonus_calc = str(bonus_calc)

        return cls(name, old_to_automation(bonus_calc, damage_calc, details))

    @classmethod
    def copy(cls, other):
        """Returns a shallow copy of an attack."""
        return cls(other.name, other.automation, other.verb, other.proper)

    def build_str(self, caster):
        return f"**{self.name}**: {self.automation.build_str(caster)}"

    def __str__(self):
        return f"**{self.name}**: {str(self.automation)}"


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
        return '\n'.join(sorted((atk.build_str(caster) for atk in self.attacks), key=str.lower))

    def __str__(self):
        return '\n'.join(str(atk) for atk in self.attacks)

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


def old_to_automation(bonus=None, damage=None, details=None):
    """Returns an Automation instance representing an old attack."""
    from cogs5e.models import automation

    if damage is not None:
        damage = automation.Damage(damage)

    if bonus is not None:
        hit = [damage] if damage else []
        attack_eff = [automation.Attack(hit=hit, miss=[], attackBonus=str(bonus).strip('{}<>'))]
    else:
        attack_eff = [damage] if damage else []

    effects = [automation.Target('each', attack_eff)] if attack_eff else []
    if details:
        # noinspection PyTypeChecker
        # PyCharm thinks this should be a list of Target instead of a list of Effect
        effects.append(automation.Text(details))

    return automation.Automation(effects)
