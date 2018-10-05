class Automation:
    def __init__(self, effects: list):
        self.effects = effects

    @classmethod
    def from_data(cls, data: list):
        if data is not None:
            effects = Effect.deserialize(data)
            return cls(effects)
        return None


class Effect:
    def __init__(self, type_, meta=None):
        self.type = type_
        self.meta = meta

    @staticmethod
    def deserialize(data):
        return [EFFECT_MAP[e['type']].from_data(e) for e in data]

    @classmethod
    def from_data(cls, data):  # catch-all
        data.pop('type')
        return cls(**data)


class Target(Effect):
    def __init__(self, target, effects: list, **kwargs):
        super(Target, self).__init__("target", **kwargs)
        self.target = target
        self.effects = effects

    @classmethod
    def from_data(cls, data):
        data['effects'] = Effect.deserialize(data['effects'])
        return super(Target, cls).from_data(data)


class Attack(Effect):
    def __init__(self, hit: list, miss: list, **kwargs):
        super(Attack, self).__init__("attack", **kwargs)
        self.hit = hit
        self.miss = miss

    @classmethod
    def from_data(cls, data):
        data['hit'] = Effect.deserialize(data['hit'])
        data['miss'] = Effect.deserialize(data['miss'])
        return super(Attack, cls).from_data(data)


class Save(Effect):
    def __init__(self, stat: str, fail: list, success: list, **kwargs):
        super(Save, self).__init__("save", **kwargs)
        self.stat = stat
        self.fail = fail
        self.success = success

    @classmethod
    def from_data(cls, data):
        data['fail'] = Effect.deserialize(data['fail'])
        data['success'] = Effect.deserialize(data['success'])
        return super(Save, cls).from_data(data)


class Damage(Effect):
    def __init__(self, damage: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Damage, self).__init__("damage", **kwargs)
        self.damage = damage
        self.higher = higher
        self.cantripScale = cantripScale


class IEffect(Effect):
    def __init__(self, name: str, duration: int, effects: str, **kwargs):
        super(IEffect, self).__init__("ieffect", **kwargs)
        self.name = name
        self.duration = duration
        self.effects = effects


class Roll(Effect):
    def __init__(self, dice: str, name: str, higher: dict = None, cantripScale: bool = None, **kwargs):
        super(Roll, self).__init__("roll", **kwargs)
        self.dice = dice
        self.name = name
        self.higher = higher
        self.cantripScale = cantripScale


class Text(Effect):
    def __init__(self, text: str, **kwargs):
        super(Text, self).__init__("text", **kwargs)
        self.text = text


EFFECT_MAP = {
    "target": Target,
    "attack": Attack,
    "save": Save,
    "damage": Damage,
    "ieffect": IEffect,
    "roll": Roll,
    "text": Text
}


class Spell:
    def __init__(self, name: str, level: int, school: str, casttime: str, range_: str, components: str, duration: str,
                 description: str, classes: list = None, subclasses: list = None, ritual: bool = False,
                 higherlevels: str = None, source: str = "homebrew", page: int = None, concentration: bool = False,
                 automation: Automation = None, srd: bool = False):
        if classes is None:
            classes = []
        if subclasses is None:
            subclasses = []
        self.name = name
        self.level = level
        self.school = school
        self.classes = classes
        self.subclasses = subclasses
        self.time = casttime
        self.range = range_
        self.components = components
        self.duration = duration
        self.ritual = ritual
        self.description = description
        self.higherlevels = higherlevels
        self.source = source
        self.page = page
        self.concentration = concentration
        self.automation = automation
        self.srd = srd

    @classmethod
    def from_data(cls, data):
        data["range_"] = data.pop("range")  # ignore this
        data["automation"] = Automation.from_data(data["automation"])
        return cls(**data)

    def get_school(self):
        return {
            "A": "Abjuration",
            "EV": "Evocation",
            "EN": "Enchantment",
            "I": "Illusion",
            "D": "Divination",
            "N": "Necromancy",
            "T": "Transmutation",
            "C": "Conjuration"
        }.get(self.school, self.school)

    def get_level(self):
        if self.level == 0:
            return "cantrip"
        if self.level == 1:
            return "1st level"
        if self.level == 2:
            return "2nd level"
        if self.level == 3:
            return "3rd level"
        return f"{self.level}th level"
