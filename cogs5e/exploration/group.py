from .explorer import Explorer
from .types import ExplorerType
from .utils import create_explorer_id


class ExplorerGroup(Explorer):
    type = ExplorerType.GROUP

    def __init__(self, ctx, exploration, id, explorers, name, init, index=None, **_):
        super().__init__(
            ctx, exploration, id, name=name, controller_id=str(ctx.author.id), private=False, init=init, index=index
        )
        self._explorers = explorers

    # noinspection PyMethodOverriding
    @classmethod
    def new(cls, exploration, name, init, ctx=None):
        id = create_explorer_id()
        return cls(ctx, exploration, id, [], name, init)

    @classmethod
    async def from_dict(cls, raw, ctx, exploration):
        # this import is here because Explore imports ExplorerGroup - it's a 1-time cost on first call but
        # practically free afterwards
        from .explore import deserialize_explorer

        explorers = []
        for c in raw.pop("explorers"):
            explorer = await deserialize_explorer(c, ctx, exploration)
            explorers.append(explorer)

        return cls(ctx, exploration, explorers=explorers, **raw)

    @classmethod
    def from_dict_sync(cls, raw, ctx, exploration):
        from .explore import deserialize_explorer_sync

        explorers = []
        for c in raw.pop("explorers"):
            explorer = deserialize_explorer_sync(c, ctx, exploration)
            explorers.append(explorer)

        return cls(ctx, exploration, explorers=explorers, **raw)

    def to_dict(self):
        return {
            "name": self._name,
            "init": self._init,
            "explorers": [c.to_dict() for c in self.get_explorers()],
            "index": self._index,
            "type": "group",
            "id": self.id,
        }

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
    def index(self):
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    @property
    def controller(self):
        return str(self.ctx.author.id)  # workaround

    def get_explorers(self):
        return self._explorers

    def add_explorer(self, explorer):
        self._explorers.append(explorer)
        explorer.group = self.id
        explorer.init = self.init

    def remove_explorer(self, explorer):
        self._explorers.remove(explorer)
        explorer.group = None

    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of an explorer's status.
        :return: A string describing the explorer.
        """
        if len(self._explorers) > 7 and not private:
            status = f"{self.init:>2}: {self.name} ({len(self.get_explorers())} explorers)"
        else:
            status = f"{self.init:>2}: {self.name}"
            for c in self.get_explorers():
                status += f'\n     - {": ".join(c.get_summary(private, no_notes).split(": ")[1:])}'
        return status

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of an explorer.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the explorer.
        """
        return "\n".join(c.get_status(private) for c in self.get_explorers())

    def on_turn(self, num_turns=1):
        for c in self.get_explorers():
            c.on_turn(num_turns)

    def on_turn_end(self, num_turns=1):
        for c in self.get_explorers():
            c.on_turn_end(num_turns)

    def on_remove(self):
        for c in self.get_explorers():
            c.on_remove()

    def controller_mention(self):
        return ", ".join({c.controller_mention() for c in self.get_explorers()})

    def __str__(self):
        return f"{self.name} ({len(self.get_explorers())} explorers)"

    def __contains__(self, item):
        return item in self._explorers

    def __len__(self):
        return len(self._explorers)
