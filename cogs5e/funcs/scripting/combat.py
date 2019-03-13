from cogs5e.funcs.dice import roll
from cogs5e.funcs.scripting.functions import SimpleRollResult
from cogs5e.funcs.sheetFuncs import sheet_damage
from cogs5e.models.errors import CombatNotFound, InvalidSaveType
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup, Effect
from utils.argparser import ParsedArguments


class SimpleCombat:
    def __init__(self, combat, me):
        self._combat: Combat = combat

        self.combatants = [SimpleCombatant(c) for c in self._combat.get_combatants()]
        if me:
            self.me = SimpleCombatant(me, False)
        else:
            self.me = None
        self.round_num = self._combat.round_num
        self.turn_num = self._combat.turn_num
        current = self._combat.current_combatant
        if current:
            if isinstance(current, CombatantGroup):
                self.current = SimpleGroup(current)
            else:
                self.current = SimpleCombatant(current)
        else:
            self.current = None

    @classmethod
    async def from_ctx(cls, ctx):
        try:
            combat = await Combat.from_ctx(ctx)
        except CombatNotFound:
            return None
        return cls(combat, None)

    # public methods
    def get_combatant(self, name):
        combatant = self._combat.get_combatant(name, False)
        if combatant:
            return SimpleCombatant(combatant)
        return None

    def get_group(self, name):
        group = self._combat.get_group(name, strict=False)
        if group:
            return SimpleGroup(group)
        return None

    # private functions
    def func_set_character(self, character):
        me = next((c for c in self._combat.get_combatants() if getattr(c, 'character_id', None) == character.id), None)
        if not me:
            return
        me._character = character  # set combatant character instance
        self.me = me

    async def func_commit(self):
        await self._combat.commit()

    def __str__(self):
        return str(self._combat)


class SimpleCombatant:
    def __init__(self, combatant: Combatant, hidestats=True):
        self._combatant = combatant
        self._hidden = hidestats and self._combatant.isPrivate
        self.type = "combatant"

        if not self._hidden:
            self.ac = self._combatant.ac
            if self._combatant.hp is not None:
                self.hp = self._combatant.hp - (self._combatant.temphp or 0)
            else:
                self.hp = None
            self.maxhp = self._combatant.hpMax
            self.initmod = self._combatant.initMod
            self.temphp = self._combatant.temphp
            self.resists = self._combatant.resists
        else:
            self.ac = None
            self.hp = None
            self.maxhp = None
            self.initmod = None
            self.temphp = None
            self.resists = None
        self.init = self._combatant.init
        self.name = self._combatant.name
        self.note = self._combatant.notes
        self.effects = [SimpleEffect(e) for e in self._combatant.get_effects()]
        if self._combatant.hp is not None and self._combatant.hpMax:
            self.ratio = (self._combatant.hp - (self._combatant.temphp or 0)) / self._combatant.hpMax
        else:
            self.ratio = 0
        self.level = self._combatant.spellcasting.casterLevel

    def set_hp(self, newhp: int):
        self._combatant.set_hp(int(newhp))

    def mod_hp(self, mod: int, overheal: bool = False):
        self._combatant.mod_hp(mod, overheal)

    def hp_str(self):
        return self._combatant.get_hp_str()

    def save(self, ability: str, adv: bool = None):
        try:
            save_skill = next(s for s in ('strengthSave', 'dexteritySave', 'constitutionSave',
                                          'intelligenceSave', 'wisdomSave', 'charismaSave') if
                              ability.lower() in s.lower())
        except StopIteration:
            raise InvalidSaveType

        mod = self._combatant.saves.get(save_skill, 0)
        sb = self._combatant.active_effects('sb')
        if sb:
            saveroll = '1d20{:+}+{}'.format(mod, '+'.join(sb))
        else:
            saveroll = '1d20{:+}'.format(mod)
        adv = 0 if adv is None else 1 if adv else -1

        save_roll = roll(saveroll, adv=adv,
                         rollFor='{} Save'.format(save_skill[:3].upper()), inline=True, show_blurbs=False)
        return SimpleRollResult(save_roll.rolled, save_roll.total, save_roll.skeleton,
                                [part.to_dict() for part in save_roll.raw_dice.parts], save_roll)

    def wouldhit(self, to_hit: int):
        if self._combatant.ac:
            return to_hit >= self._combatant.ac
        return None

    def damage(self, dice_str: str, crit=False, d=None, c=None, critdice=0, overheal=False):
        args = ParsedArguments(None, {
            'critdice': [critdice],
            'resist': self._combatant.resists['resist'],
            'immune': self._combatant.resists['immune'],
            'vuln': self._combatant.resists['vuln']
        })
        if d:
            args['d'] = d
        if c:
            args['c'] = c
        result = sheet_damage(dice_str, args, 1 if crit else 0)
        result['damage'] = result['damage'].strip()
        self.mod_hp(-result['total'], overheal=overheal)
        return result

    def set_ac(self, ac: int):
        if not isinstance(ac, int) and ac is not None:
            raise ValueError("AC must be an integer or None.")
        self._combatant.ac = ac

    def set_maxhp(self, maxhp: int):
        if not isinstance(maxhp, int) and maxhp is not None:
            raise ValueError("Max HP must be an integer or None.")
        self._combatant.hpMax = maxhp

    def set_thp(self, thp: int):
        if not isinstance(thp, int):
            raise ValueError("Temp HP must be an integer.")
        self._combatant.temphp = thp

    def set_init(self, init: int):
        if not isinstance(init, int):
            raise ValueError("Initiative must be an integer.")
        self._combatant.init = init

    def set_name(self, name: str):
        if not name:
            raise ValueError("Combatants must have a name.")
        self._combatant.name = str(name)

    def set_note(self, note: str):
        if note is not None:
            note = str(note)
        self._combatant.notes = note

    def get_effect(self, name: str):
        effect = self._combatant.get_effect(name)
        if effect:
            return SimpleEffect(effect)
        return None

    def add_effect(self, name: str, args: str, duration: int = -1, concentration: bool = False, parent=None):
        existing = self._combatant.get_effect(name, True)
        if existing:
            existing.remove()
        effectObj = Effect.new(self._combatant.combat, self._combatant, duration=duration, name=name, effect_args=args,
                               concentration=concentration)
        if parent:
            effectObj.set_parent(parent._effect)
        self._combatant.add_effect(effectObj)

    def remove_effect(self, name: str):
        effect = self._combatant.get_effect(name)
        if effect:
            effect.remove()

    def __str__(self):
        return str(self._combatant)


class SimpleGroup:
    def __init__(self, group: CombatantGroup):
        self._group = group
        self.type = "group"
        self.combatants = [SimpleCombatant(c) for c in self._group.get_combatants()]

    def get_combatant(self, name):
        combatant = next((c for c in self.combatants if name.lower() in c.name.lower()), None)
        if combatant:
            return combatant
        return None

    def __str__(self):
        return str(self._group)


class SimpleEffect:
    def __init__(self, effect: Effect):
        self._effect = effect

        self.name = self._effect.name
        self.duration = self._effect.duration
        self.remaining = self._effect.remaining
        self.effect = self._effect.effect
        self.conc = self._effect.concentration

    def __str__(self):
        return str(self._effect)

    def set_parent(self, parent):
        self._effect.set_parent(parent._effect)
