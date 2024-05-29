import random

import d20
import disnake
from disnake.ext import commands

from aliasing import helpers
from cogs5e.models.errors import NoSelectionElements
from cogs5e.utils import actionutils, checkutils, targetutils
from cogs5e.utils.help_constants import *
from cogsmisc.stats import Stats
from gamedata import Monster
from gamedata.lookuputils import handle_source_footer, select_monster_full, select_spell_full
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.dice import PersistentRollContext, VerboseMDStringifier
from utils.functions import search_and_select, try_delete, camel_to_title
from .inline import InlineRoller
from .utils import string_search_adv


class Dice(commands.Cog):
    """Dice and math related commands."""

    def __init__(self, bot):
        self.bot = bot
        self.inline = InlineRoller(bot)

    # ==== commands ====
    @commands.command(name="2", hidden=True)
    async def quick_roll(self, ctx, *, mod: str = "0"):
        """Quickly rolls a d20."""
        dice = "1d20+" + mod
        await self.roll_cmd(ctx, dice=dice)

    @commands.command(name="roll", aliases=["r"])
    async def roll_cmd(self, ctx, *, dice: str = "1d20"):
        """Roll is used to roll any combination of dice in the `XdY` format. (`1d6`, `2d8`, etc)

        Multiple rolls can be added together as an equation. Standard Math operators and Parentheses can be used: `() + - / *`

        Roll also accepts `adv` and `dis` for Advantage and Disadvantage. Rolls can also be tagged with `[text]` for informational purposes. Any text after the roll will assign the name of the roll.

        ___Examples___
        `!r` or `!r 1d20` - Roll a single d20, just like at the table
        `!r 1d20+4` - A skill check or attack roll
        `!r 1d8+2+1d6` - Longbow damage with Hunter’s Mark

        `!r 1d20+1 adv` - A skill check or attack roll with Advantage
        `!r 1d20-3 dis` - A skill check or attack roll with Disadvantage

        `!r (1d8+4)*2` - Warhammer damage against bludgeoning vulnerability

        `!r 1d10[piercing]+2d6[cold] Ice Knife` - The Ice Knife Spell does cold and piercing damage

        **Advanced Options**
        __Operators__
        Operators are always followed by a selector, and operate on the items in the set that match the selector.
        A set can be made of a single or multiple entries i.e. `1d20` or `(1d6,1d8,1d10)`

        These operations work on dice and sets of numbers
        `k` - keep - Keeps all matched values.
        `p` - drop - Drops all matched values.

        These operators only work on dice rolls.
        `rr` - reroll - Rerolls all matched die values until none match.
        `ro` - reroll - once - Rerolls all matched die values once.
        `ra` - reroll and add - Rerolls up to one matched die value once, add to the roll.
        `mi` - minimum - Sets the minimum value of each die.
        `ma` - maximum - Sets the maximum value of each die.
        `e` - explode on - Rolls an additional die for each matched die value. Exploded dice can explode.

        __Selectors__
        Selectors select from the remaining kept values in a set.
        `X`  | literal X
        `lX` | lowest X
        `hX` | highest X
        `>X` | greater than X
        `<X` | less than X

        __Examples__
        `!r 2d20kh1+4` - Advantage roll, using Keep Highest format
        `!r 2d20kl1-2` - Disadvantage roll, using Keep Lowest format
        `!r 4d6mi2[fire]` - Elemental Adept, Fire
        `!r 10d6ra6` - Wild Magic Sorcerer Spell Bombardment
        `!r 4d6ro<3` - Great Weapon Fighting
        `!r 2d6e6` - Explode on 6
        `!r (1d6,1d8,1d10)kh2` - Keep 2 highest rolls of a set of dice

        **Additional Information can be found at:**
        https://d20.readthedocs.io/en/latest/start.html#dice-syntax"""  # noqa: E501

        if dice == "0/0":  # easter eggs
            return await ctx.send("What do you expect me to do, destroy the universe?")

        dice, adv = string_search_adv(dice)

        res = d20.roll(dice, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier())
        out = f"{ctx.author.mention}  :game_die:\n{str(res)}"
        if len(out) > 1999:
            out = f"{ctx.author.mention}  :game_die:\n{str(res)[:100]}...\n**Total**: {res.total}"

        await try_delete(ctx.message)
        await ctx.send(out, allowed_mentions=disnake.AllowedMentions(users=[ctx.author]))
        await Stats.increase_stat(ctx, "dice_rolled_life")
        if gamelog := self.bot.get_cog("GameLog"):
            await gamelog.send_roll(ctx, res)

    @commands.command(name="multiroll", aliases=["rr"])
    async def rr(self, ctx, iterations: int, *, dice):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <dice>"""
        dice, adv = string_search_adv(dice)
        await self._roll_many(ctx, iterations, dice, adv=adv)

    @commands.command(name="iterroll", aliases=["rrr"])
    async def rrr(self, ctx, iterations: int, dice, dc: int = None, *, args=""):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        _, adv = string_search_adv(args)
        await self._roll_many(ctx, iterations, dice, dc, adv)

    @staticmethod
    async def _roll_many(ctx, iterations, roll_str, dc=None, adv=None):
        if iterations < 1 or iterations > 100:
            return await ctx.send("Too many or too few iterations.")
        if adv is None:
            adv = d20.AdvType.NONE
        results = []
        successes = 0
        ast = d20.parse(roll_str, allow_comments=True)
        roller = d20.Roller(context=PersistentRollContext())

        for _ in range(iterations):
            res = roller.roll(ast, advantage=adv)
            if dc is not None and res.total >= dc:
                successes += 1
            results.append(res)

        if dc is None:
            header = f"Rolling {iterations} iterations..."
            footer = f"{sum(o.total for o in results)} total."
        else:
            header = f"Rolling {iterations} iterations, DC {dc}..."
            footer = f"{successes} successes, {sum(o.total for o in results)} total."

        if ast.comment:
            header = f"{ast.comment}: {header}"

        result_strs = "\n".join(str(o) for o in results)

        out = f"{header}\n{result_strs}\n{footer}"

        if len(out) > 1500:
            one_result = str(results[0])
            out = f"{header}\n{one_result}\n[{len(results) - 1} results omitted for output size.]\n{footer}"

        await try_delete(ctx.message)
        await ctx.send(f"{ctx.author.mention}\n{out}", allowed_mentions=disnake.AllowedMentions(users=[ctx.author]))
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.group(
        name="monattack",
        aliases=["ma", "monster_attack"],
        invoke_without_command=True,
        help=f"""
        Rolls a monster's attack.
        __**Valid Arguments**__
        {VALID_AUTOMATION_ARGS}
        """,
    )
    async def monster_atk(self, ctx, monster_name, atk_name=None, *, args=""):
        if atk_name is None or atk_name == "list":
            return await self.monster_atk_list(ctx, monster_name)

        await try_delete(ctx.message)

        monster = await select_monster_full(ctx, monster_name)
        attacks = monster.attacks

        attack = await search_and_select(ctx, attacks, atk_name, lambda a: a.name)
        args = await helpers.parse_snippets(args, ctx, statblock=monster, base_args=[monster_name, atk_name])
        args = argparse(args)

        embed = embed_for_monster(monster, args)

        caster, targets, combat = await targetutils.maybe_combat(ctx, monster, args)
        await actionutils.run_attack(ctx, embed, args, caster, attack, targets, combat)

        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)

    @monster_atk.command(name="list")
    async def monster_atk_list(self, ctx, monster_name):
        """Lists a monster's attacks."""
        await try_delete(ctx.message)
        monster = await select_monster_full(ctx, monster_name)
        await actionutils.send_action_list(ctx, caster=monster, attacks=monster.attacks)

    @commands.command(
        name="moncheck",
        aliases=["mc", "monster_check"],
        help=f"""
        Rolls a check for a monster.
        {VALID_CHECK_ARGS}
        """,
    )
    async def monster_check(self, ctx, monster_name, check, *, args=""):
        await try_delete(ctx.message)
        monster: Monster = await select_monster_full(ctx, monster_name)
        args = await helpers.parse_snippets(args, ctx, statblock=monster, base_args=[monster_name, check])
        args = argparse(args)
        skill_key = await search_and_select(ctx, SKILL_NAMES, check, camel_to_title)

        embed = embed_for_monster(monster, args)

        checkutils.run_check(skill_key, monster, args, embed)

        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)

    @commands.command(
        name="monsave",
        aliases=["ms", "monster_save"],
        help=f"""
        Rolls a save for a monster.
        {VALID_SAVE_ARGS}
        """,
    )
    async def monster_save(self, ctx, monster_name, save_stat, *, args=""):
        await try_delete(ctx.message)
        monster: Monster = await select_monster_full(ctx, monster_name)
        args = await helpers.parse_snippets(args, ctx, statblock=monster, base_args=[monster_name, save_stat])
        args = argparse(args)

        embed = embed_for_monster(monster, args)

        checkutils.run_save(save_stat, monster, args, embed)

        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)

    @commands.command(
        name="moncast",
        aliases=["mcast", "monster_cast"],
        help=f"""
        Casts a spell as a monster.
        __**Valid Arguments**__
        {VALID_SPELLCASTING_ARGS}
        
        {VALID_AUTOMATION_ARGS}
        """,
    )
    async def monster_cast(self, ctx, monster_name, spell_name, *, args=""):
        await try_delete(ctx.message)
        monster: Monster = await select_monster_full(ctx, monster_name)
        args = await helpers.parse_snippets(args, ctx, statblock=monster, base_args=[monster_name, spell_name])
        args = argparse(args)

        if not args.last("i", type_=bool):
            try:
                spell = await select_spell_full(ctx, spell_name, list_filter=lambda s: s.name in monster.spellbook)
            except NoSelectionElements:
                return await ctx.send(
                    "No matching spells found in the creature's spellbook. Cast again "
                    "with the `-i` argument to ignore restrictions!"
                )
        else:
            spell = await select_spell_full(ctx, spell_name)

        caster, targets, combat = await targetutils.maybe_combat(ctx, monster, args)
        result = await actionutils.cast_spell(spell, ctx, caster, targets, args, combat=combat)

        # embed display
        embed = embed_for_monster(monster, args, result.embed)
        handle_source_footer(embed, monster, add_source_str=False)
        await ctx.send(embed=embed)

    # ==== inline rolling ====
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        await self.inline.handle_message_inline_rolls(message)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        await self.inline.handle_reaction_inline_rolls(reaction, user)


def embed_for_monster(monster, args, embed=None):
    if not embed:
        embed = disnake.Embed()
    embed.colour = random.randint(0, 0xFFFFFF)
    if not args.last("h", type_=bool) and "thumb" not in args:
        embed.set_thumbnail(url=monster.get_image_url())
    return embed
