class Combat:
    def __init__(self, channelId, summaryMsgId, dmId, options):
        self._channel = channelId
        self._summary = summaryMsgId
        self._dm = dmId
        self._options = options
        self._combatants = []
        self._round = 0
        self._current_combatant = None

    @property
    def channel(self):
        return self._channel

    @property
    def summary(self):
        return self._summary

    @property
    def dm(self):
        return self._dm

    @property
    def options(self):
        return self._options

    @property
    def round_num(self):
        return self._round


class Combatant:
    pass


class MonsterCombatant(Combatant):
    pass


class PlayerCombatant(Combatant):
    pass


class CombatantGroup:
    pass
