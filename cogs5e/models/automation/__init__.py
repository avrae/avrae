import aliasing.api.statblock
import aliasing.evaluators
from utils.functions import get_guild_member
from .effects import *
from .errors import *
from .results import *
from .runtime import *


class Automation:
    def __init__(self, effects: list):
        self.effects = effects

    @classmethod
    def from_data(cls, data: list):
        if data is not None:
            effects = Effect.deserialize(data)
            return cls(effects)
        return None

    def to_dict(self):
        return [e.to_dict() for e in self.effects]

    async def run(self, ctx, embed, caster, targets, args, combat=None, spell=None, conc_effect=None, ab_override=None,
                  dc_override=None, spell_override=None, title=None, before=None, after=None):
        """
        Runs automation.

        :param ctx: The discord context the automation is being run in.
        :type ctx: discord.ext.commands.Context
        :param embed: The embed to add automation fields to.
        :type embed: discord.Embed
        :param caster: The StatBlock casting this automation.
        :type caster: cogs5e.models.sheet.statblock.StatBlock
        :param targets: A list of str or StatBlock or None hit by this automation.
        :type targets: list of str or list of cogs5e.models.sheet.statblock.StatBlock
        :param args: ParsedArguments.
        :type args: utils.argparser.ParsedArguments
        :param combat: The combat this automation is being run in.
        :type combat: cogs5e.models.initiative.Combat
        :param spell: The spell being cast that is running this automation.
        :type spell: cogs5e.models.spell.Spell
        :param conc_effect: The initiative effect that is used to track concentration caused by running this.
        :type conc_effect: cogs5e.models.initiative.Effect
        :param ab_override: Forces a default attack bonus.
        :type ab_override: int
        :param dc_override: Forces a default DC.
        :type dc_override: int
        :param spell_override: Forces a default spell modifier.
        :type spell_override: int
        :param title: The title of the action.
        :type title: str
        :param before: A function, taking in the AutomationContext, to run before automation runs.
        :type before: function
        :param after: A function, taking in the AutomationContext, to run after automation runs.
        :type after: function
        :rtype: AutomationResult
        """
        if not targets:
            targets = [None]  # outputs a single iteration of effects in a generic meta field
        autoctx = AutomationContext(ctx, embed, caster, targets, args, combat, spell, conc_effect, ab_override,
                                    dc_override, spell_override)

        results = []

        if before is not None:
            before(autoctx)

        for effect in self.effects:
            await effect.preflight(autoctx)

        for effect in self.effects:
            results.append(effect.run(autoctx))

        if after is not None:
            after(autoctx)

        autoctx.build_embed()
        for user, msgs in autoctx.pm_queue.items():
            try:
                member = await get_guild_member(ctx.guild, int(user))
                if title:
                    await member.send(f"{title}\n" + '\n'.join(msgs))
                else:
                    await member.send('\n'.join(msgs))
            except:
                pass

        return AutomationResult(children=results, is_spell=spell is not None,
                                caster_needs_commit=autoctx.caster_needs_commit)

    def build_str(self, caster):
        """
        :type caster: :class:`~cogs5e.models.sheet.statblock.StatBlock
        """
        if not self.effects:
            return "No effects."
        evaluator = aliasing.evaluators.AutomationEvaluator.with_caster(caster)
        evaluator.builtins['caster'] = aliasing.api.statblock.AliasStatBlock(caster)
        inner = Effect.build_child_str(self.effects, caster, evaluator)
        if not inner:
            inner = ', '.join(e.type for e in self.effects)
        return f"{inner[0].upper()}{inner[1:]}."

    def __str__(self):
        return f"Automation ({len(self.effects)} effects)"
