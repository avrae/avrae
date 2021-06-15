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

    @property
    def full_actions(self):
        """Returns a list of actions that require a full action to activate."""
        return [a for a in self.actions if a.activation_type == ActivationType.ACTION]

    @property
    def bonus_actions(self):
        """Returns a list of actions that require a bonus action to activate."""
        return [a for a in self.actions if a.activation_type == ActivationType.BONUS_ACTION]

    @property
    def reactions(self):
        """Returns a list of actions that require a reaction to activate."""
        return [a for a in self.actions if a.activation_type == ActivationType.REACTION]

    @property
    def other_actions(self):
        """Returns a list of actions that do not fall into the other action categories."""
        return [a for a in self.actions if a.activation_type not in (ActivationType.ACTION,
                                                                     ActivationType.BONUS_ACTION,
                                                                     ActivationType.REACTION)]

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

    def build_str(self, caster=None):
        if self.snippet:
            return self.snippet
        if self.gamedata and self.gamedata.automation:
            if caster is None:
                return str(self.gamedata.automation)
            return self.gamedata.automation.build_str(caster)
        return "Unknown action."

    def __str__(self):
        return self.build_str(caster=None)

    def __repr__(self):
        return f"<Action name={self.name!r} uid={self.uid!r} id={self.id!r} type_id={self.type_id!r} " \
               f"activation_type={self.activation_type!r} gamedata={self.gamedata!r}>"
