import aliasing.api
import aliasing.api.statblock
import aliasing.evaluators
import cogs5e.models.initiative.combatant as init
from cogs5e.models import character as character_api, embeds
from .errors import AutomationEvaluationException, InvalidIntExpression
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

        # spellcasting utils
        self.spell = spell
        self.ab_override = ab_override
        self.dc_override = dc_override
        self.spell_level_override = None  # used in Cast Spell effect
        self.conc_effect = conc_effect

        self.metavars = {
            # caster, targets as default (#1335)
            "caster": aliasing.api.statblock.AliasStatBlock(caster),
            "targets": [maybe_alias_statblock(t) for t in targets]
        }
        self.target = None
        self.in_crit = False

        self.caster_needs_commit = False

        # embed text fields, in order
        self._meta_queue = []
        self._embed_queue = []
        self._effect_queue = []
        self._footer_queue = []
        self._postflight_queue = []

        # used internally by embed builder
        self._field_queue = []
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

    # ===== embed builder =====
    def queue(self, text):
        """Adds a line of text to the current field."""
        self._embed_queue.append(text)

    def meta_queue(self, text):
        """Adds a line of text to the cast-wide meta field (lines are unique)."""
        if text not in self._meta_queue:
            self._meta_queue.append(text)

    def footer_queue(self, text):
        """Adds a line of text to the embed footer."""
        self._footer_queue.append(text)

    def effect_queue(self, text):
        """Adds a line of text to the Effect field (lines are unique)."""
        if text not in self._effect_queue:
            self._effect_queue.append(text)

    def postflight_queue_field(self, name, value, merge=True):
        """
        Adds a field to the queue that will appear after all other fields (but before user-supplied -f fields).
        If *merge* is true, adds a line to a field that might already have the same name.
        """
        if merge:
            existing_field = next((f for f in self._postflight_queue if f['name'] == name), None)
            if existing_field and value != existing_field['value']:
                existing_field['value'] = f"{existing_field['value']}\n{value}"
                return
        field = {"name": name, "value": value, "inline": False}
        if field not in self._postflight_queue:
            self._postflight_queue.append(field)

    def push_embed_field(self, title, inline=False, to_meta=False):
        """Pushes all lines currently in the embed queue to a new field."""
        if not self._embed_queue:
            return
        if to_meta:
            self._meta_queue.extend(self._embed_queue)
        else:
            chunks = embeds.get_long_field_args('\n'.join(self._embed_queue), title)
            self._field_queue.extend(chunks)
        self._embed_queue = []

    def _insert_meta_field(self):
        if not self._meta_queue:
            return
        self._field_queue.insert(0, {"name": "Meta", "value": '\n'.join(self._meta_queue), "inline": False})
        self._meta_queue = []

    def build_embed(self):
        """Consumes all items in queues and creates the final embed."""

        # description
        phrase = self.args.join('phrase', '\n')
        if phrase:
            self.embed.description = f"*{phrase}*"

        # add meta field (any lingering items in field queue that were not closed added to meta)
        self._meta_queue.extend(t for t in self._embed_queue if t not in self._meta_queue)
        self._insert_meta_field()

        # add fields
        for field in self._field_queue:
            self.embed.add_field(**field)
        for effect in self._effect_queue:
            self.embed.add_field(name="Effect", value=effect, inline=False)
        for field in self._postflight_queue:
            self.embed.add_field(**field)
        self.embed.set_footer(text='\n'.join(self._footer_queue))

    def add_pm(self, user, message):
        if user not in self.pm_queue:
            self.pm_queue[user] = []
        self.pm_queue[user].append(message)

    # ===== utils =====
    @property
    def is_spell(self):
        return self.spell is not None

    def get_cast_level(self):
        default = self.spell_level_override or 0
        if self.spell:
            default = default or self.spell.level
        return self.args.last('l', default, int)

    def parse_annostr(self, annostr, is_full_expression=False):
        """
        Parses an AnnotatedString.

        :param str annostr: The string to parse.
        :param bool is_full_expression: Whether to evaluate the result rather than running interpolation.
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

    def parse_intexpression(self, intexpression):
        """
        Parses an IntExpression.

        :param intexpression: The string to parse.
        :rtype: int
        """
        eval_result = self.parse_annostr(intexpression, is_full_expression=True)
        try:
            return int(eval_result)
        except (TypeError, ValueError):
            raise InvalidIntExpression(f"{intexpression!r} cannot be interpreted as an IntExpression.")


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
        if self.combatant:
            sb = self.combatant.active_effects('sb')

        # character-specific arguments (#1443)
        reroll = None
        if self.character:
            reroll = self.character.get_setting('reroll', 0)

        boolwise_adv = {-1: False, 0: None, 1: True}.get(adv)
        saveroll = save_obj.d20(base_adv=boolwise_adv, reroll=reroll)

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
