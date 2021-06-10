from typing import Optional

from utils.enums import ActivationType


class Actions:
    def __init__(self, actions=None):
        if actions is None:
            actions = []
        self.actions = actions

    @classmethod
    def from_dict(cls, l):
        return cls([Action.from_dict(atk) for atk in l])

    def to_dict(self):
        return [a.to_dict() for a in self.actions]

    def __iter__(self):
        return iter(self.actions)

    def __getitem__(self, item):
        return self.actions[item]

    def __len__(self):
        return len(self.actions)


class Action:
    def __init__(self, name: str, uid: Optional[str], id: int, type_id: int,
                 activation_type: ActivationType = None, snippet: str = None):
        self.name = name
        self.uid = uid
        self.id = id
        self.type_id = type_id
        self.activation_type = activation_type
        self.snippet = snippet

    @classmethod
    def from_dict(cls, d):
        activation_type = ActivationType(at) if (at := d.pop('activation_type')) is not None else None
        return cls(activation_type=activation_type, **d)

    def to_dict(self):
        activation_type = self.activation_type.value if self.activation_type is not None else None
        return {
            "name": self.name, "uid": self.uid, "id": self.id, "type_id": self.type_id,
            "activation_type": activation_type, "snippet": self.snippet
        }

    @property
    def gamedata(self):
        if self.uid is None:
            return None
        import gamedata
        return gamedata.compendium.lookup_action(self.uid)

    def __repr__(self):
        return f"<Action name={self.name!r} uid={self.uid!r} id={self.id!r} type_id={self.type_id!r} " \
               f"activation_type={self.activation_type!r} gamedata={self.gamedata!r}>"
