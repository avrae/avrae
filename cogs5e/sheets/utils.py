import collections

from cogs5e.models.sheet.action import Action
from gamedata import compendium


# ==== Name => Action Discovery ====
class ActionDiscoverer:
    """Used to discover appropriate actions from a given name quickly, caching gamedata and updating when necessary."""

    def __init__(self):
        self.latest_compendium_epoch = -1
        self.actions_granted_by_name = collections.defaultdict(lambda: set())
        self._is_reloading = False

    def _reload(self):
        if self._is_reloading:
            # potentially this could allow a thread to discover using old data, unless we weakref'd, but that should not
            # be an issue, worst case it blocks a couple of actions from getting gc'ed for a few seconds
            return
        self._is_reloading = True

        # do this on the side and then replace it in case of any thread safety issues
        new_name_map = collections.defaultdict(lambda: set())
        for action in compendium.actions:
            new_name_map[action.name].add(action)
            if action.grantor:
                new_name_map[action.grantor.name].add(action)
            if action.source_feature:
                new_name_map[action.source_feature.name].add(action)

        self.actions_granted_by_name = new_name_map
        self.latest_compendium_epoch = compendium.epoch
        self._is_reloading = False

    def discover(self, name: str):
        """
        :rtype: set[gamedata.action.Action]
        """
        if self.latest_compendium_epoch < compendium.epoch:
            self._reload()
        return self.actions_granted_by_name[name]


discoverer = ActionDiscoverer()


def get_actions_for_name(name):
    """
    For Dicecloud/GSheet sheets: search for any gamedata actions by name.
    Returns a set of actions that match the name.
    Generally pretty quick except the first run after a compendium reload.
    """
    return discoverer.discover(name)


def get_actions_for_names(names):
    """Returns a list of actions granted by the list of feature names. Will filter out any duplicates."""
    actions = []
    seen_action_names = set()

    for name in names:
        g_actions = get_actions_for_name(name)
        # in some cases, a very generic feature name (e.g. "Channel Divinity") will grant far more actions than we want
        # code snippet to determine this threshold:
        # bleps = [(name, len(actions), actions) for name, actions in discoverer.actions_granted_by_name.items()]
        # bleps = sorted(bleps, key=lambda blep: blep[1], reverse=True)
        if len(g_actions) > 20:
            continue

        for g_action in g_actions:
            if g_action.name in seen_action_names:
                continue
            seen_action_names.add(g_action.name)
            actions.append(
                Action(
                    name=g_action.name,
                    uid=g_action.uid,
                    id=g_action.id,
                    type_id=g_action.type_id,
                    activation_type=g_action.activation_type,
                )
            )

    return actions
