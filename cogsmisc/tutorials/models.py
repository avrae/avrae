"""
Misc data models for tutorials.
"""
import abc


class Tutorial:
    """
    Base class for all tutorials. Each tutorial should subclass this class, and use the @state decorator to
    register states.
    """

    def __init__(self, name, description):
        self.name = name
        self.description = description

        self.states = {}
        self.first_state = None

        # iterate over members to find state registrations
        # what do you mean, 'hack'? :)
        for member in dir(self):
            value = getattr(self, member)
            if isinstance(value, TutorialState):
                self.states[value.key] = value
                value.tutorial = self
                if value.first:
                    if self.first_state is not None:
                        raise ValueError(f"Found 2 first states in tutorial {self.name!r}: "
                                         f"({self.first_state.key}, {value.key})")
                    self.first_state = value
        if self.first_state is None:
            self.first_state = list(self.states.values())[0]  # just get the first state


class TutorialState(abc.ABC):
    """
    Base class for all tutorial states. Each state should subclass and implement these methods.
    """

    def __init__(self, key=None, first=False):
        self.key = key or type(self).__name__
        self.tutorial = None
        self.first = first

    async def objective(self, ctx, state_map):
        """
        Displays the current objective.

        :type ctx: discord.ext.commands.Context
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError

    async def listener(self, ctx, state_map):
        """
        Called after a user in this state runs any bot command. Check against objectives and run transition if necessary

        :type ctx: discord.ext.commands.Context
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError

    async def transition(self, ctx, state_map):
        """
        Should display any necessary text before a transition, then call state_map.transition() to transition or
        state_map.end_tutorial() to end.

        :type ctx: discord.ext.commands.Context
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError


class TutorialStateMap:
    """
    The tutorial and state a given user is in, along with any user-specific data that state might need.
    """

    def __init__(self, user_id, tutorial_key, state_key, data, **_):
        self.user_id = user_id
        self.tutorial_key = tutorial_key
        self.state_key = state_key
        self.data = data

    # db/ser
    @classmethod
    async def from_ctx(cls, ctx):
        d = await ctx.bot.mdb.tutorial_map.find_one({"user_id": ctx.author.id})
        if d is None:
            return None
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {
            "user_id": self.user_id, "tutorial_key": self.tutorial_key, "state_key": self.state_key, "data": self.data
        }

    async def commit(self, ctx):
        await ctx.bot.mdb.tutorial_map.update_one(
            {"user_id": self.user_id},
            {"$set": self.to_dict()},
            upsert=True
        )

    @classmethod
    def new(cls, ctx, tutorial_key, tutorial):
        return cls(ctx.author.id, tutorial_key, tutorial.first_state.key, {})

    # state transitions
    async def transition(self, ctx, new_state):
        self.state_key = new_state.key
        self.data = {}
        await self.commit(ctx)
        await new_state.objective(ctx, self)

    async def end_tutorial(self, ctx):
        await ctx.bot.mdb.tutorial_map.delete_one({"user_id": self.user_id})


# registration decorators
# use @state to register states inside a Tutorial class
# then register the Tutorial in the cog

def state(key=None, first=False):
    """Registers the class as a TutorialState in the Tutorial."""

    def deco(cls):
        return cls(key=key, first=first)

    return deco
