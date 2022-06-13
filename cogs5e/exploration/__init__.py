from .explore import Explore
from .explorer import Explorer, PlayerExplorer
from .effect import Effect
from .errors import *
from .group import ExplorerGroup
from .types import ExplorerType

pass  # don't move my imports, pycharm - the cog has to be imported last

from .cog import ExplorationTracker  # noqa E402


def setup(bot):
    bot.add_cog(ExplorationTracker(bot))

