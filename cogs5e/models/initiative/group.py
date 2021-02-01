from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.models.sheet.base import Skill
from .combatant import Combatant, MonsterCombatant, PlayerCombatant
from .errors import CombatException
from .utils import CombatantType, create_combatant_id


class CombatantGroup(Combatant):
    type = CombatantType.GROUP

    def __init__(self, ctx, combat, id, combatants, name, init, index=None, **_):
        super(CombatantGroup, self).__init__(
            ctx, combat, id, name=name, controller_id=str(ctx.author.id), private=False, init=init, index=index)
        self._combatants = combatants

    # noinspection PyMethodOverriding
    @classmethod
    def new(cls, combat, name, init, ctx=None):
        id = create_combatant_id()
        return cls(ctx, combat, id, [], name, init)

    @classmethod
    async def from_dict(cls, raw, ctx, combat):
        if 'id' not in raw:  # fixme id translation, remove apr 2021
            raw['id'] = create_combatant_id()

        combatants = []
        for c in raw.pop('combatants'):
            ctype = CombatantType(c['type'])
            if ctype == CombatantType.GENERIC:
                combatant = Combatant.from_dict(c, ctx, combat)
            elif ctype == CombatantType.MONSTER:
                combatant = MonsterCombatant.from_dict(c, ctx, combat)
            elif ctype == CombatantType.PLAYER:
                combatant = await PlayerCombatant.from_dict(c, ctx, combat)
            else:
                raise CombatException(f"Unknown combatant type when deserializing group: {c['type']}")
            combatant.group = raw['id']  # fixme id translation, remove apr 2021
            combatants.append(combatant)

        return cls(ctx, combat, combatants=combatants, **raw)

    @classmethod
    def from_dict_sync(cls, raw, ctx, combat):
        if 'id' not in raw:  # fixme id translation, remove apr 2021
            raw['id'] = create_combatant_id()

        combatants = []
        for c in raw.pop('combatants'):
            ctype = CombatantType(c['type'])
            if ctype == CombatantType.GENERIC:
                combatant = Combatant.from_dict(c, ctx, combat)
            elif ctype == CombatantType.MONSTER:
                combatant = MonsterCombatant.from_dict(c, ctx, combat)
            elif ctype == CombatantType.PLAYER:
                combatant = PlayerCombatant.from_dict_sync(c, ctx, combat)
            else:
                raise CombatException("Unknown combatant type")
            combatant.group = raw['id']  # fixme id translation, remove apr 2021
            combatants.append(combatant)

        return cls(ctx, combat, combatants=combatants, **raw)

    def to_dict(self):
        return {'name': self._name, 'init': self._init, 'combatants': [c.to_dict() for c in self.get_combatants()],
                'index': self._index, 'type': 'group', 'id': self.id}

    # members
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = new_name

    def get_name(self):
        return self.name

    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, new_init):
        self._init = new_init

    @property
    def init_skill(self):
        # groups: if all combatants are the same type, return the first one's skill, otherwise +0
        if all(isinstance(c, MonsterCombatant) for c in self._combatants) \
                and len(set(c.monster_name for c in self._combatants)) == 1:
            return self._combatants[0].init_skill
        return Skill(0)

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    @property
    def controller(self):
        return str(self.ctx.author.id)  # workaround

    @property
    def attacks(self):
        a = AttackList()
        seen = set()
        for c in self.get_combatants():
            for atk in c.attacks:
                if atk in seen:
                    continue
                seen.add(atk)
                atk_copy = Attack.copy(atk)
                atk_copy.name = f"{atk.name} ({c.name})"
                a.append(atk_copy)
        return a

    def get_combatants(self):
        return self._combatants

    def add_combatant(self, combatant):
        self._combatants.append(combatant)
        combatant.group = self.id
        combatant.init = self.init

    def remove_combatant(self, combatant):
        self._combatants.remove(combatant)
        combatant.group = None

    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        if len(self._combatants) > 7 and not private:
            status = f"{self.init:>2}: {self.name} ({len(self.get_combatants())} combatants)"
        else:
            status = f"{self.init:>2}: {self.name}"
            for c in self.get_combatants():
                status += f'\n     - {": ".join(c.get_summary(private, no_notes).split(": ")[1:])}'
        return status

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of a combatant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the combatant.
        """
        return '\n'.join(c.get_status(private) for c in self.get_combatants())

    def on_turn(self, num_turns=1):
        for c in self.get_combatants():
            c.on_turn(num_turns)

    def on_turn_end(self, num_turns=1):
        for c in self.get_combatants():
            c.on_turn_end(num_turns)

    def on_remove(self):
        for c in self.get_combatants():
            c.on_remove()

    def controller_mention(self):
        return ", ".join({c.controller_mention() for c in self.get_combatants()})

    def __str__(self):
        return f"{self.name} ({len(self.get_combatants())} combatants)"

    def __contains__(self, item):
        return item in self._combatants

    def __len__(self):
        return len(self._combatants)
