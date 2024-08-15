from functools import cached_property
from typing import List, Optional, TYPE_CHECKING, Union

import aliasing.api.combat
import aliasing.api.statblock
import aliasing.evaluators
import cogs5e.initiative.combatant as init
from cogs5e.models import character as character_api, embeds
from utils.enums import AdvantageType, CritDamageType
from .errors import AutomationEvaluationException, AutomationException, InvalidIntExpression
from .utils import maybe_alias_statblock

__all__ = ("AutomationContext", "AutomationTarget")

if TYPE_CHECKING:
    import disnake
    from cogs5e.models.sheet.statblock import StatBlock
    from cogs5e.initiative import Combat, InitiativeEffect
    from utils.argparser import ParsedArguments
    from utils.context import AvraeContext
    from gamedata import Spell


class AutomationContext:
    def __init__(
        self,
        ctx: Union["AvraeContext", "disnake.Interaction"],
        embed: "disnake.Embed",
        caster: "StatBlock",
        targets: List[Optional[Union["StatBlock", str]]],
        args: "ParsedArguments",
        combat: Optional["Combat"],
        spell: Optional["Spell"] = None,
        conc_effect: Optional["InitiativeEffect"] = None,
        ab_override: Optional[int] = None,
        dc_override: Optional[int] = None,
        spell_override: Optional[int] = None,
        spell_level_override: Optional[int] = None,
        crit_type: CritDamageType = CritDamageType.NORMAL,
        ieffect: Optional["InitiativeEffect"] = None,
        allow_caster_ieffects: bool = True,
        allow_target_ieffects: bool = True,
        from_button: bool = False,
        original_choice: str = "",
    ):
        # runtime options
        self.ctx = ctx
        self.embed = embed
        self.caster = caster
        self.targets = targets
        self.args = args
        self.combat = combat
        self.crit_type = crit_type

        # runtime internals
        self.caster_needs_commit = False
        self.evaluator = aliasing.evaluators.AutomationEvaluator.with_caster(caster)
        self.metavars = {
            # caster, targets as default (#1335)
            "caster": aliasing.api.statblock.AliasStatBlock(caster),
            "targets": [maybe_alias_statblock(t) for t in targets],
            "choice": self.args.last("choice", original_choice).lower(),
        }

        # spellcasting utils
        self.spell = spell
        self.ab_override = ab_override
        self.dc_override = dc_override
        if spell_override is not None:
            self.evaluator.builtins["spell"] = spell_override
        self.spell_level_override = spell_level_override  # used in Cast Spell effect
        self.conc_effect = conc_effect

        self.metavars["spell_attack_bonus"] = self.ab_override or self.caster.spellbook.sab
        self.metavars["spell_dc"] = self.dc_override or self.caster.spellbook.dc
        self.metavars["spell_level"] = self.spell_level_override

        # InitiativeEffect utils
        self.ieffect = ieffect
        if ieffect is not None:
            self.metavars["ieffect"] = aliasing.api.combat.SimpleEffect(ieffect)
        self.from_button = from_button
        self.allow_caster_ieffects = allow_caster_ieffects
        self.allow_target_ieffects = allow_target_ieffects

        # node-specific behaviour
        self.target: Optional[AutomationTarget] = None
        self.in_crit = False
        self.in_save = False

        # embed text fields, in order
        self._meta_queue = []
        self._embed_queue = []
        self._effect_queue = []
        self._footer_queue = []
        self._postflight_queue = []

        # used internally by embed builder
        self._field_queue = []
        self.pm_queue = {}

        # type helpers
        self.character: Optional[character_api.Character] = None
        if isinstance(caster, init.PlayerCombatant):
            self.character = caster.character
        elif isinstance(caster, character_api.Character):
            self.character: character_api.Character = caster  # type annotation to narrow type here

        self.combatant: Optional[init.Combatant] = None
        if isinstance(caster, init.Combatant):
            self.combatant: init.Combatant = caster  # type annotation to narrow type here

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

    def effect_queue(self, text, title="Effect"):
        """Adds a line of text to the Effect field (lines are unique)."""
        if (title, text) not in self._effect_queue:
            self._effect_queue.append((title, text))

    def postflight_queue_field(self, name, value, merge=True):
        """
        Adds a field to the queue that will appear after all other fields (but before user-supplied -f fields).
        If *merge* is true, adds a line to a field that might already have the same name.
        """
        if merge:
            existing_field = next((f for f in self._postflight_queue if f["name"] == name), None)
            if existing_field and value != existing_field["value"]:
                existing_field["value"] = f"{existing_field['value']}\n{value}"
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
            chunks = embeds.get_long_field_args("\n".join(self._embed_queue), title)
            self._field_queue.extend(chunks)
        self._embed_queue = []

    def _insert_meta_field(self):
        if not self._meta_queue:
            return
        self._field_queue.insert(0, {"name": "Meta", "value": "\n".join(self._meta_queue), "inline": False})
        self._meta_queue = []

    def build_embed(self):
        """Consumes all items in queues and creates the final embed."""

        # description
        phrase = self.args.join("phrase", "\n")

        if phrase:
            # blockquote phrase to specify it is a phrase
            self.embed.description = f">>> *{phrase}*"

        # add meta field (any lingering items in field queue that were not closed added to meta)
        self._meta_queue.extend(t for t in self._embed_queue if t not in self._meta_queue)
        self._insert_meta_field()

        # add fields
        for field in self._field_queue:
            self.embed.add_field(**field)
        for title, effect in self._effect_queue:
            self.embed.add_field(name=title, value=effect, inline=False)
        for field in self._postflight_queue:
            self.embed.add_field(**field)
        self.embed.set_footer(text="\n".join(self._footer_queue))

    def add_pm(self, user, message):
        if user not in self.pm_queue:
            self.pm_queue[user] = []
        self.pm_queue[user].append(message)

    # ===== spell utils =====
    @property
    def is_spell(self):
        return self.spell is not None

    def get_cast_level(self):
        """
        Returns the casting level of the origin spell (which may be None for nested automation in homebrew spells).
        """
        default = self.spell_level_override or 0
        if self.spell:
            default = default or self.spell.level
        return self.args.last("l", default, int)

    # ===== init utils =====
    def caster_active_effects(self, mapper, reducer=lambda mapped: mapped, default=None):
        if not self.allow_caster_ieffects:
            return default
        if self.combatant is None:
            return default
        return self.combatant.active_effects(mapper, reducer, default)

    def target_active_effects(self, mapper, reducer=lambda mapped: mapped, default=None):
        if not self.allow_target_ieffects:
            return default
        if self.target.combatant is None:
            return default
        return self.target.combatant.active_effects(mapper, reducer, default)

    # ===== scripting utils =====
    def parse_annostr(self, annostr, is_full_expression=False):
        """
        Parses an AnnotatedString.

        :param str annostr: The string to parse.
        :param bool is_full_expression: Whether to evaluate the result rather than running interpolation.
        """
        if not isinstance(annostr, str):
            raise AutomationException(f"Expected an AnnotatedString, got {type(annostr).__name__}")
        if not is_full_expression:
            return self.evaluator.transformed_str(annostr, extra_names=self.metavars)

        original_names = self.evaluator.builtins.copy()
        self.evaluator.builtins.update(self.metavars)
        expr = annostr.strip("{}")
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
        # optimization: our str can be directly cast to int, or is already an int/float
        try:
            return int(intexpression)
        except (TypeError, ValueError):
            pass

        eval_result = self.parse_annostr(intexpression, is_full_expression=True)
        try:
            return int(eval_result)
        except (TypeError, ValueError):
            raise InvalidIntExpression(f"{intexpression!r} cannot be interpreted as an IntExpression.")


class AutomationTarget:
    def __init__(self, autoctx: AutomationContext, target: Optional[Union["StatBlock", str]]):
        self.autoctx = autoctx
        self.target = target
        self.is_simple = isinstance(target, str) or target is None

    @property
    def name(self) -> str:
        if isinstance(self.target, str):
            return self.target
        return self.target.name

    # ==== defensive ieffect helpers ====
    @property
    def ac(self) -> Optional[int]:
        if self.is_simple:
            return None
        if not self.autoctx.allow_target_ieffects and self.combatant is not None:
            return self.combatant.base_ac
        return self.target.ac

    def get_resists(self):
        if not self.autoctx.allow_target_ieffects and self.combatant is not None:
            return self.combatant.base_resistances
        return self.target.resistances

    def get_save_dice(self, save_skill: str, adv: AdvantageType = None, sb: list[str] = None) -> str:
        """Gets the save roll's dice string for the current target in the automation context."""
        if self.is_simple:
            raise ValueError("Cannot get the save dice of a simple (string/null) target")
        elif self.autoctx.target is not self:
            raise ValueError("Cannot get save dice of target when it is not active in context")

        save_obj = self.target.saves.get(save_skill)

        # combatant
        combatant = self.combatant
        if combatant and self.autoctx.allow_target_ieffects:
            if sb:
                sb.extend(combatant.active_effects(mapper=lambda effect: effect.effects.save_bonus, default=[]))
            else:
                sb = combatant.active_effects(mapper=lambda effect: effect.effects.save_bonus, default=[])

        # character-specific arguments (#1443)
        reroll = None
        if self.character:
            reroll = self.character.options.reroll

        boolwise_adv = {-1: False, 0: None, 1: True}.get(adv)
        save_dice = save_obj.d20(base_adv=boolwise_adv, reroll=reroll)

        if sb:
            save_dice = f"{save_dice}+{'+'.join(sb)}"

        return save_dice

    # ==== helpers ====
    def damage(self, autoctx: AutomationContext, amount: int, allow_overheal: bool = True):
        # add damage footer when we attack a Combatant
        if not self.is_simple:
            initial_hp = self.target.hp or 0
            initial_temp_hp = self.target.temp_hp or 0
            result = self.target.modify_hp(-amount, overflow=allow_overheal)
            result_str = f"{self.target.name}: {result}"

            deltas = []
            if self.target.temp_hp != initial_temp_hp:
                deltas.append(f"{self.target.temp_hp - initial_temp_hp:+} temp")

            if self.target.hp is None:
                autoctx.footer_queue(f"{self.target or '<No Target>'}: Dealt {amount} damage!")
                return

            if self.target.hp != initial_hp:
                deltas.append(f"{self.target.hp - initial_hp:+} HP")

            total_delta = self.target.temp_hp + self.target.hp - initial_temp_hp - initial_hp
            if -amount != total_delta:
                deltas.append(f"{abs(amount + total_delta)} overflow")

            if deltas:
                delta_str = f" ({', '.join(deltas)})"
            else:
                delta_str = ""

            if isinstance(self.target, init.Combatant):
                if self.target.is_private:
                    autoctx.add_pm(
                        self.target.controller_id, f"{self.target.name}'s HP: {self.target.hp_str(True)}{delta_str}"
                    )
                    # don't reveal HP/temp delta breakdown in the footer.
                    if delta_str:
                        delta_str = f" ({total_delta:+})"

                if self.target.is_concentrating() and amount > 0:
                    autoctx.queue(f"**Concentration**: DC {int(max(amount / 2, 10))}")

            autoctx.footer_queue(result_str + delta_str)

        # for a non-init target, we still want to display that a damage node was run in the footer.
        else:
            autoctx.footer_queue(f"{self.target or '<No Target>'}: Dealt {amount} damage!")

    # ==== target base class helpers ====
    @cached_property
    def combatant(self) -> Optional[init.Combatant]:
        if isinstance(self.target, init.Combatant):
            return self.target
        return None

    @cached_property
    def character(self) -> Optional[character_api.Character]:
        if isinstance(self.target, init.PlayerCombatant):
            return self.target.character
        elif isinstance(self.target, character_api.Character):
            return self.target
        return None
