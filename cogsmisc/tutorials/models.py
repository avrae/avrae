"""
Misc data models for tutorials.
"""
import abc


class Tutorial:
    """
    Base class for all tutorials. Each tutorial should subclass this class, and use the @state decorator to
    register states.
    """

    def __init__(self):
        self.states = {}

        # iterate over members to find state registrations
        for name in dir(self):
            if not name.startswith('_'):
                value = getattr(self, name)
                if isinstance(value, TutorialState):
                    self.states[value.key] = value
                    value.tutorial = self


class TutorialState(abc.ABC):
    """
    Base class for all tutorial states. Each state should subclass and implement these methods.
    """

    def __init__(self, key=None):
        self.key = key or type(self).__name__
        self.tutorial = None

    async def listener(self, ctx, state_map):
        """
        Called after a user in this state runs any bot command.

        :type ctx: discord.ext.commands.Context
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError

    async def objective(self, ctx, state_map):
        """
        Displays the current objective.

        :type ctx: discord.ext.commands.Context
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError

    async def transition(self, ctx, state_map):
        """
        Returns the key of the new TutorialState to transition to, or None to end the tutorial.

        :type ctx: discord.ext.commands.Context
        :type state_map: TutorialStateMap
        """
        raise NotImplementedError


class TutorialStateMap:
    """
    The tutorial and state a given user is in, along with any user-specific data that state might need.
    """

    def __init__(self, user_id, tutorial_key, state_key, data):
        self.user_id = user_id
        self.tutorial_key = tutorial_key
        self.state_key = state_key
        self.data = data


# registration decorators
# use @state to register states inside a Tutorial class
# then register the Tutorial in the cog

def state(key=None):
    """Registers the class as a TutorialState in the Tutorial."""

    def deco(cls):
        return cls(key=key)

    return deco
