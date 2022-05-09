from typing import Optional, TYPE_CHECKING, Union

import aliasing.api.statblock
import aliasing.evaluators
from utils.enums import CritDamageType
from utils.functions import get_guild_member
from .effects import *
from .errors import *
from .results import *
from .runtime import *

if TYPE_CHECKING:
    from cogs5e.models.sheet.statblock import StatBlock
    from utils.argparser import ParsedArguments
    from cogs5e.initiative import Combat, InitiativeEffect
    from gamedata.spell import Spell


class Automation:
    def __init__(self, effects: list):
        self.effects = effects

    @classmethod
    def from_data(cls, data: list):
        if data is not None:
            automation_effects = Effect.deserialize(data)
            return cls(automation_effects)
        return None

    def to_dict(self):
        return [e.to_dict() for e in self.effects]

    async def run(
        self,
        ctx,
        embed,
        caster: "StatBlock",
        targets: list[Union[str, "StatBlock"]],
        args: "ParsedArguments",
        combat: Optional["Combat"] = None,
        spell: Optional["Spell"] = None,
        conc_effect: Optional["InitiativeEffect"] = None,
        ab_override: Optional[int] = None,
        dc_override: Optional[int] = None,
        spell_override: Optional[int] = None,
        title: Optional[str] = None,
        crit_type: CritDamageType = None,
        ieffect: Optional["InitiativeEffect"] = None,
        allow_caster_ieffects: bool = True,
        allow_target_ieffects: bool = True,
    ) -> AutomationResult:
        """
        Runs automation.

        :param ctx: The discord context the automation is being run in.
        :type ctx: discord.ext.commands.Context
        :param embed: The embed to add automation fields to.
        :type embed: discord.Embed
        :param caster: The StatBlock casting this automation.
        :param targets: A list of str or StatBlock or None hit by this automation.
        :param args: ParsedArguments.
        :param combat: The combat this automation is being run in.
        :param spell: The spell being cast that is running this automation.
        :param conc_effect: The initiative effect that is used to track concentration caused by running this.
        :param ab_override: Forces a default attack bonus.
        :param dc_override: Forces a default DC.
        :param spell_override: Forces a default spell modifier.
        :param title: The title of the action, used when sending private messages after execution.
        :param crit_type: The method of adding critical damage
        :param ieffect: If the automation is running as an effect of an InitiativeEffect, the InitiativeEffect that has
                        the interaction that triggered this run (used for the Remove IEffect automation effect).
        :param allow_caster_ieffects: Whether effects granted by ieffects on the caster (usually offensive like
                                      -d, adv, magical, etc) are considered during execution.
        :param allow_target_ieffects: Whether effects granted by ieffects on a target (usually defensive like
                                      -sb, sadv, -ac, -resist, etc) are considered during execution.
        """
        if not targets:
            targets = []
        autoctx = AutomationContext(
            ctx,
            embed,
            caster,
            targets,
            args,
            combat,
            spell=spell,
            conc_effect=conc_effect,
            ab_override=ab_override,
            dc_override=dc_override,
            spell_override=spell_override,
            crit_type=crit_type,
            ieffect=ieffect,
            allow_caster_ieffects=allow_caster_ieffects,
            allow_target_ieffects=allow_target_ieffects,
        )

        automation_results = []

        for effect in self.effects:
            await effect.preflight(autoctx)

        for effect in self.effects:
            automation_results.append(effect.run(autoctx))

        autoctx.build_embed()
        for user, msgs in autoctx.pm_queue.items():
            try:
                member = await get_guild_member(ctx.guild, int(user))
                if title:
                    await member.send(f"{title}\n" + "\n".join(msgs))
                else:
                    await member.send("\n".join(msgs))
            except:
                pass

        return AutomationResult(
            children=automation_results, is_spell=autoctx.is_spell, caster_needs_commit=autoctx.caster_needs_commit
        )

    def build_str(self, caster):
        """
        :type caster: :class:`~cogs5e.models.sheet.statblock.StatBlock
        """
        if not self.effects:
            return "No effects."
        evaluator = aliasing.evaluators.AutomationEvaluator.with_caster(caster)
        evaluator.builtins["caster"] = aliasing.api.statblock.AliasStatBlock(caster)
        inner = Effect.build_child_str(self.effects, caster, evaluator)
        if not inner:
            inner = ", ".join(e.type for e in self.effects)
        return f"{inner[0].upper()}{inner[1:]}."

    def __str__(self):
        return f"Automation ({len(self.effects)} effects)"
