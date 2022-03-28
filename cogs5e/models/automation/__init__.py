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
            automation_effects = Effect.deserialize(data)
            return cls(automation_effects)
        return None

    def to_dict(self):
        return [e.to_dict() for e in self.effects]

    async def run(
        self,
        ctx,
        embed,
        caster,
        targets,
        args,
        combat=None,
        title=None,
        before=None,
        after=None,
        autoctx=None,
    ):
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
        :param title: The title of the action.
        :type title: str
        :param before: A function, taking in the AutomationContext, to run before automation runs.
        :type before: Callable[[AutomationContext], Any]
        :param after: A function, taking in the AutomationContext, to run after automation runs.
        :type after: Callable[[AutomationContext], Any]
        :type autoctx: AutomationContext
        :rtype: AutomationResult
        """
        if not targets:
            targets = []
        if autoctx is None:
            autoctx = AutomationContext(ctx, embed, caster, targets, args, combat)

        automation_results = []

        if before is not None:
            before(autoctx)

        for effect in self.effects:
            await effect.preflight(autoctx)

        for effect in self.effects:
            automation_results.append(effect.run(autoctx))

        if after is not None:
            after(autoctx)

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
