"""
Misc data models for tutorials.
"""

import abc
import asyncio
import textwrap

from cogs5e.models.embeds import EmbedWithAuthor


class Tutorial(abc.ABC):
    """
    Base class for all tutorials. Each tutorial should subclass this class, and use the @state decorator to
    register states.
    """

    name = None
    description = None

    def __init__(self, name=None, description=None):
        members = dir(self)  # don't include name, desc, etc

        self.name = name or self.name
        self.description = description or self.description

        if self.name is None:
            raise ValueError(f"Name not supplied in tutorial {type(self).__name__} or constructor")
        if self.description is None:
            raise ValueError(f"Description not supplied in tutorial {type(self).__name__} or constructor")
        else:
            self.description = textwrap.dedent(self.description).strip()

        self.states = {}
        self.first_state = None

        # iterate over members to find state registrations
        # what do you mean, 'hack'? :)
        for member in members:
            value = getattr(self, member)
            if isinstance(value, TutorialState):
                self.states[value.key] = value
                value.tutorial = self
                if value.first:
                    if self.first_state is not None:
                        raise ValueError(
                            f"Found 2 first states in tutorial {self.name!r}: ({self.first_state.key}, {value.key})"
                        )
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

    async def setup(self, ctx, state_map):
        """
        Called once the first time this state becomes active.

        :type ctx: utils.context.AvraeContext
        :type state_map: TutorialStateMap
        """
        pass

    async def objective(self, ctx, state_map):
        """
        Displays the current objective.

        :type ctx: utils.context.AvraeContext
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError

    async def listener(self, ctx, state_map):
        """
        Called after a user in this state runs any bot command. Check against objectives and run transition if necessary

        :type ctx: utils.context.AvraeContext
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError

    async def transition(self, ctx, state_map):
        """
        Should display any necessary text before a transition, then call state_map.transition() to transition or
        state_map.end_tutorial() to end.

        :type ctx: utils.context.AvraeContext
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError


class TutorialStateMap:
    """
    The tutorial and state a given user is in, along with any user-specific data that state might need.
    """

    def __init__(self, user_id, tutorial_key, state_key, data, persist_data=None, **_):
        if persist_data is None:
            persist_data = {}

        self.user_id = user_id
        self.tutorial_key = tutorial_key
        self.state_key = state_key
        self.data = data  # state-specific data
        self.persist_data = persist_data  # sticks around the whole tutorial

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
            "user_id": self.user_id,
            "tutorial_key": self.tutorial_key,
            "state_key": self.state_key,
            "data": self.data,
            "persist_data": self.persist_data,
        }

    async def commit(self, ctx):
        await ctx.bot.mdb.tutorial_map.update_one({"user_id": self.user_id}, {"$set": self.to_dict()}, upsert=True)

    @classmethod
    def new(cls, ctx, tutorial_key, tutorial):
        return cls(ctx.author.id, tutorial_key, tutorial.first_state.key, {}, {})

    # state transitions
    async def transition(self, ctx, new_state):
        self.state_key = new_state.key
        self.data = {}
        await self.commit(ctx)
        await new_state.setup(ctx, self)
        await new_state.objective(ctx, self)

    async def transition_with_delay(self, ctx, new_state, secs):
        """Triggers typing, then calls transition after ``secs`` seconds."""
        await ctx.trigger_typing()
        await asyncio.sleep(secs)
        await self.transition(ctx, new_state)

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


class TutorialEmbed(EmbedWithAuthor):
    """Embed with author avatar, nick, color, and tutorial footer set."""

    def __init__(self, tstate: TutorialState, ctx, footer=True, **kwargs):
        super().__init__(ctx, **kwargs)
        if footer:
            self.set_footer(
                text=f"{tstate.tutorial.name} | {ctx.prefix}tutorial skip to skip | {ctx.prefix}tutorial end to end"
            )

        self._description = None

    # custom description handler that strips/dedents so we can use triple-quoted strings in our code
    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value):
        if not isinstance(value, str):
            self._description = value
        else:
            self._description = textwrap.dedent(value).strip()


def checklist(items):
    """Generates a checklist from a list of pairs of (item, complete)."""
    out = []
    for item, complete in items:
        if complete:
            out.append(f":small_blue_diamond: ~~{item}~~")
        else:
            out.append(f":small_orange_diamond: {item}")
    return "\n".join(out)
