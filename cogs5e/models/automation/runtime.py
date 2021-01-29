import aliasing.api
import aliasing.runtime.statblock
import aliasing.evaluators
import cogs5e.models.initiative.combatant as init
from cogs5e.models import character as character_api, embeds
from .errors import AutomationEvaluationException
from .utils import maybe_alias_statblock

__all__ = (
    'AutomationContext', 'AutomationTarget'
)


class AutomationContext:
    def __init__(self, ctx, embed, caster, targets, args, combat, spell=None, conc_effect=None, ab_override=None,
                 dc_override=None, spell_override=None):
        self.ctx = ctx
        self.embed = embed
        self.caster = caster
        self.targets = targets
        self.args = args
        self.combat = combat

        self.spell = spell
        self.is_spell = spell is not None
        self.conc_effect = conc_effect
        self.ab_override = ab_override
        self.dc_override = dc_override

        self.metavars = {
            # caster, targets as default (#1335)
            "caster": aliasing.runtime.statblock.AliasStatBlock(caster),
            "targets": [maybe_alias_statblock(t) for t in targets]
        }
        self.target = None
        self.in_crit = False

        self._embed_queue = []
        self._meta_queue = []
        self._effect_queue = []
        self._field_queue = []
        self._footer_queue = []
        self.pm_queue = {}

        self.character = None
        if isinstance(caster, init.PlayerCombatant):
            self.character = caster.character
        elif isinstance(caster, character_api.Character):
            self.character = caster

        self.evaluator = aliasing.evaluators.SpellEvaluator.with_caster(caster, spell_override=spell_override)

        self.combatant = None
        if isinstance(caster, init.Combatant):
            self.combatant = caster

    def queue(self, text):
        self._embed_queue.append(text)

    def meta_queue(self, text):
        if text not in self._meta_queue:
            self._meta_queue.append(text)

    def footer_queue(self, text):
        self._footer_queue.append(text)

    def effect_queue(self, text):
        if text not in self._effect_queue:
            self._effect_queue.append(text)

    def push_embed_field(self, title, inline=False, to_meta=False):
        if not self._embed_queue:
            return
        if to_meta:
            self._meta_queue.extend(self._embed_queue)
        else:
            chunks = embeds.get_long_field_args('\n'.join(self._embed_queue), title)
            self._field_queue.extend(chunks)
        self._embed_queue = []

    def insert_meta_field(self):
        if not self._meta_queue:
            return
        self._field_queue.insert(0, {"name": "Meta", "value": '\n'.join(self._meta_queue), "inline": False})
        self._meta_queue = []

    def build_embed(self):
        # description
        phrase = self.args.join('phrase', '\n')
        if phrase:
            self.embed.description = f"*{phrase}*"

        # add fields
        self._meta_queue.extend(t for t in self._embed_queue if t not in self._meta_queue)
        self.insert_meta_field()
        for field in self._field_queue:
            self.embed.add_field(**field)
        for effect in self._effect_queue:
            self.embed.add_field(name="Effect", value=effect, inline=False)
        self.embed.set_footer(text='\n'.join(self._footer_queue))

    def add_pm(self, user, message):
        if user not in self.pm_queue:
            self.pm_queue[user] = []
        self.pm_queue[user].append(message)

    def get_cast_level(self):
        if self.is_spell:
            return self.args.last('l', self.spell.level, int)
        return 0

    def parse_annostr(self, annostr, is_full_expression=False):
        """
        Parses an AnnotatedString or IntExpression.

        :param str annostr: The string to parse.
        :param bool is_full_expression: Whether the string is an IntExpression.
        """
        if not is_full_expression:
            return self.evaluator.transformed_str(annostr, extra_names=self.metavars)

        original_names = self.evaluator.builtins.copy()
        self.evaluator.builtins.update(self.metavars)
        expr = annostr.strip('{}')
        try:
            out = self.evaluator.eval(expr)
        except Exception as ex:
            raise AutomationEvaluationException(ex, expr)
        self.evaluator.builtins = original_names
        return out


class AutomationTarget:
    def __init__(self, target):
        #: :type: :class:`~cogs5e.models.sheet.statblock.StatBlock`
        self.target = target
        self.is_simple = isinstance(target, str) or target is None

    @property
    def name(self):
        if isinstance(self.target, str):
            return self.target
        return self.target.name

    @property
    def ac(self):
        return self.target.ac

    def get_save_dice(self, save, adv=None):
        sb = None
        save_obj = self.target.saves.get(save)

        # combatant
        if isinstance(self.target, init.Combatant):
            sb = self.target.active_effects('sb')

        saveroll = save_obj.d20(base_adv=adv)

        if sb:
            saveroll = f"{saveroll}+{'+'.join(sb)}"

        return saveroll

    def get_resists(self):
        return self.target.resistances

    def damage(self, autoctx, amount, allow_overheal=True):
        if not self.is_simple:
            result = self.target.modify_hp(-amount, overflow=allow_overheal)
            autoctx.footer_queue(f"{self.target.name}: {result}")

            if isinstance(self.target, init.Combatant):
                if self.target.is_private:
                    autoctx.add_pm(self.target.controller, f"{self.target.name}'s HP: {self.target.hp_str(True)}")

                if self.target.is_concentrating() and amount > 0:
                    autoctx.queue(f"**Concentration**: DC {int(max(amount / 2, 10))}")

    @property
    def combatant(self):
        if isinstance(self.target, init.Combatant):
            return self.target
        return None

    @property
    def character(self):
        if isinstance(self.target, init.PlayerCombatant):
            return self.target.character
        elif isinstance(self.target, character_api.Character):
            return self.target
        return None
