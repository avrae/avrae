class Parent:
    def __init__(self, _id, collection, group=None):
        self.id = _id
        self.collection = collection
        self.group = group

    @classmethod
    def character(cls, charId):
        return cls(charId, 'Characters')

    @classmethod
    def race(cls, charId):
        return cls(charId, 'Characters', 'racial')

    @classmethod
    def class_(cls, classId):
        return cls(classId, 'Classes')

    @classmethod
    def feature(cls, featId):
        return cls(featId, 'Features')

    @classmethod
    def background(cls, charId):
        return cls(charId, 'Characters', 'background')

    def to_dict(self):
        d = {'id': self.id, 'collection': self.collection}
        if self.group is not None:
            d['group'] = self.group
        return d


class Feature:
    def __init__(self, name: str = "New Feature", description: str = None, uses: str = None, used: int = 0,
                 reset: str = 'manual', enabled: bool = True, alwaysEnabled: bool = True):
        if not reset in ('shortRest', 'longRest', 'manual'):
            raise ValueError("Reset must be shortRest, longRest, or manual")
        self.used = used
        self.reset = reset
        self.enabled = enabled
        self.always_enabled = alwaysEnabled
        self.name = name
        self.desc = description
        self.uses = uses

    def to_dict(self):
        data = {'used': self.used, 'reset': self.reset, 'enabled': self.enabled, 'alwaysEnabled': self.always_enabled}
        if self.name is not None:
            data['name'] = self.name
        if self.desc is not None:
            data['description'] = self.desc
        if self.uses is not None:
            data['uses'] = self.uses
        return data


class Effect:
    def __init__(self, parent: Parent, operation: str, value: float = None, calculation: str = None, stat: str = None,
                 enabled: bool = True, name: str = None):
        if not operation in (
                "base", "proficiency", "add", "mul", "min", "max", "advantage", "disadvantage", "passiveAdd", "fail",
                "conditional"):
            raise ValueError("Invalid operation")
        self.parent = parent
        self.operation = operation
        self.value = value
        self.calculation = calculation
        self.stat = stat
        self.enabled = enabled
        self.name = name

    def to_dict(self):
        data = {'parent': self.parent.to_dict(), 'operation': self.operation}
        if self.name is not None:
            data['name'] = self.name
        if self.value is not None:
            data['value'] = self.value
        if self.calculation is not None:
            data['calculation'] = self.calculation
        if self.stat is not None:
            data['stat'] = self.stat
        if self.enabled is not None:
            data['enabled'] = self.enabled
        return data


class Proficiency:
    def __init__(self, parent: Parent, name: str = None, value: float = 1, type_: str = 'skill', enabled: bool = True):
        if not value in (0, 0.5, 1, 2):
            raise ValueError("Value must be 0, 0.5, 1, or 2")
        if not type_ in ("skill", "save", "weapon", "armor", "tool", "language"):
            raise ValueError("Invalid proficiency type")
        self.parent = parent
        self.value = value
        self.type = type_
        self.enabled = enabled
        self.name = name

    def to_dict(self):
        data = {'parent': self.parent.to_dict(), 'value': self.value, 'type': self.type, 'enabled': self.enabled}
        if self.name is not None:
            data['name'] = self.name
        return data


class Class:  # this feels wrong
    def __init__(self, level: int, name: str = "New Level"):
        self.level = level
        self.name = name

    def to_dict(self):
        data = {'level': self.level}
        if self.name is not None:
            data['name'] = self.name
        return data
