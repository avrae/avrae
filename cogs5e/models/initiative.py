from cogs5e.models.errors import CombatException, CombatNotFound, RequiresContext, ChannelInCombat

COMBAT_TTL = 60 * 60 * 24 * 7  # 1 week TTL


class Combat:
    def __init__(self, channelId, summaryMsgId, dmId, options, ctx, combatants=None, roundNum=0, turnNum=0,
                 currentIndex=None):
        if combatants is None:
            combatants = []
        self._channel = channelId  # readonly
        self._summary = summaryMsgId  # readonly
        self._dm = dmId
        self._options = options  # readonly (?)
        self._combatants = combatants
        self._round = roundNum
        self._turn = turnNum
        self._current_index = currentIndex
        self.ctx = ctx
        self.sort_combatants()

    @classmethod
    def new(cls, channelId, summaryMsgId, dmId, options, ctx):
        return cls(channelId, summaryMsgId, dmId, options, ctx)

    @classmethod
    def from_ctx(cls, ctx):
        raw = ctx.bot.db.jget(f"{ctx.message.channel.id}.combat")
        if raw is None:
            raise CombatNotFound  # TODO
        return cls.from_dict(raw, ctx)

    @classmethod
    def from_dict(cls, raw, ctx):
        combatants = []
        for c in raw['combatants']:
            if c['type'] == 'common':
                combatants.append(Combatant.from_dict(c, ctx))
            else:
                raise CombatException("Unknown combatant type")
        return cls(raw['channel'], raw['summary'], raw['dm'], raw['options'], ctx, combatants, raw['round'],
                   raw['turn'], raw['current'])

    def to_dict(self):
        return {'channel': self.channel, 'summary': self.summary, 'dm': self.dm, 'options': self.options,
                'combatants': [c.to_dict() for c in self.get_combatants()], 'turn': self.turn_num,
                'round': self.round_num, 'current': self.index}

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

    @property  # private write
    def round_num(self):
        return self._round

    @property  # private write
    def turn_num(self):
        return self._turn

    @property  # private write
    def index(self):
        return self._current_index

    @index.setter
    def index(self, new_index):
        self._current_index = new_index

    @property
    def current_combatant(self):
        return self.get_combatants()[self.index] if self.index is not None else None

    def get_combatants(self):
        return self._combatants

    def add_combatant(self, combatant):
        self._combatants.append(combatant)
        self.sort_combatants()

    def sort_combatants(self):
        current = self.current_combatant
        self._combatants = sorted(self._combatants, key=lambda k: (k.init, k.initMod), reverse=True)
        for n, c in enumerate(self._combatants):
            c.index = n
        self.index = current.index if current is not None else None

    def get_combatant(self, name):
        return next((c for c in self.get_combatants() if c.name == name), None)

    @staticmethod
    def ensure_unique_chan(ctx):
        if ctx.bot.db.exists(f"{ctx.message.channel.id}.combat"):
            raise ChannelInCombat

    def get_db_key(self):
        return f"{self.channel}.combat"

    def commit(self):
        if not self.ctx:
            raise RequiresContext
        self.ctx.bot.db.jsetex(self.get_db_key(), self.to_dict(), COMBAT_TTL)

    def get_summary(self):
        combatants = sorted(self.get_combatants(), key=lambda k: (k.init, k.initMod), reverse=True)
        outStr = "```markdown\n{}: {} (round {})\n".format(
            self.options.get('name') if self.options.get('name') else "Current initiative",
            self.turn_num, self.round_num)
        outStr += '=' * (len(outStr) - 13)
        outStr += '\n'
        for c in combatants:
            outStr += ("# " if self.index == c.index else "  ") + c.get_summary() + "\n"
        outStr += "```"
        return outStr

    async def update_summary(self, msg):
        await self.ctx.bot.edit_message(msg, self.get_summary())

    async def final(self, summary_msg):
        self.commit()
        await self.update_summary(summary_msg)


class Combatant:
    def __init__(self, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, ctx, index=None):
        if resists is None:
            resists = {}
        if attacks is None:
            attacks = {}
        self._name = name
        self._controller = controllerId
        self._init = init
        self._mod = initMod  # readonly
        self._hpMax = hpMax  # optional
        self._hp = hp  # optional
        self._ac = ac  # optional
        self._private = private
        self._resists = resists
        self._attacks = attacks
        self._index = index  # combat write only; position in combat
        self.ctx = ctx

    @classmethod
    def new(cls, name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, ctx):
        return cls(name, controllerId, init, initMod, hpMax, hp, ac, private, resists, attacks, ctx)

    @classmethod
    def from_dict(cls, raw, ctx):
        return cls(raw['name'], raw['controller'], raw['init'], raw['mod'], raw['hpMax'], raw['hp'], raw['ac'],
                   raw['private'], raw['resists'], raw['attacks'], ctx, raw['index'])

    @property
    def name(self):
        return self._name

    @property
    def controller(self):
        return self._controller

    @property
    def init(self):
        return self._init

    @property
    def initMod(self):
        return self._mod

    @property
    def hpMax(self):
        return self._hpMax

    @property
    def hp(self):
        return self._hp

    @property
    def ac(self):
        return self._ac

    @property
    def isPrivate(self):
        return self._private

    @property
    def resists(self):
        return self._resists

    @property
    def attacks(self):
        return self._attacks

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    def get_summary(self):  # TODO
        """
        Gets a short summary of a combatant's status.
        :return: A string describing the combatant.
        """
        return self.name

    def to_dict(self):
        return {'name': self.name, 'controller': self.controller, 'init': self.init, 'mod': self.initMod,
                'hpMax': self.hpMax, 'hp': self.hp, 'ac': self.ac, 'private': self.isPrivate, 'resists': self.resists,
                'attacks': self.attacks, 'index': self.index, 'type': 'common'}


class MonsterCombatant(Combatant):
    def __init__(self, monster):
        super(MonsterCombatant, self).__init__()


class PlayerCombatant(Combatant):
    def __init__(self, character):
        super(PlayerCombatant, self).__init__()


class CombatantGroup:
    pass
