import random
import re

import d20
import discord
from discord.ext import commands

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
from utils.functions import search_and_select, try_delete


class Dice(commands.Cog):
    """Dice and math related commands."""

    def __init__(self, bot):
        self.bot = bot

    # ==== commands ====
    @commands.command(name='2', hidden=True)
    async def quick_roll(self, ctx, *, mod: str = '0'):
        """Quickly rolls a d20."""
        rollStr = '1d20+' + mod
        await self.rollCmd(ctx, rollStr=rollStr)

    @commands.command(name='roll', aliases=['r'])
    async def rollCmd(self, ctx, *, rollStr: str = '1d20'):
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

        `!r 1d10[cold]+2d6[piercing] Ice Knife` - The Ice Knife Spell does cold and piercing damage

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
        `!r 4d6ro<3` - Great Weapon Master
        `!r 2d6e6` - Explode on 6
        `!r (1d6,1d8,1d10)kh2` - Keep 2 highest rolls of a set of dice

        **Additional Information can be found at:**
        https://d20.readthedocs.io/en/latest/start.html#dice-syntax"""

        if rollStr == '0/0':  # easter eggs
            return await ctx.send("What do you expect me to do, destroy the universe?")

        rollStr, adv = _string_search_adv(rollStr)

        res = d20.roll(rollStr, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier())
        out = f"{ctx.author.mention}  :game_die:\n" \
              f"{str(res)}"
        if len(out) > 1999:
            out = f"{ctx.author.mention}  :game_die:\n" \
                  f"{str(res)[:100]}...\n" \
                  f"**Total**: {res.total}"

        await try_delete(ctx.message)
        await ctx.send(out, allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        await Stats.increase_stat(ctx, "dice_rolled_life")
        if gamelog := self.bot.get_cog('GameLog'):
            await gamelog.send_roll(ctx, res)

    @commands.command(name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations: int, *, rollStr):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <dice>"""
        rollStr, adv = _string_search_adv(rollStr)
        await self._roll_many(ctx, iterations, rollStr, adv=adv)

    @commands.command(name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations: int, rollStr, dc: int = None, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        _, adv = _string_search_adv(args)
        await self._roll_many(ctx, iterations, rollStr, dc, adv)

    async def _roll_many(self, ctx, iterations, roll_str, dc=None, adv=None):
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

        result_strs = '\n'.join(str(o) for o in results)

        out = f"{header}\n{result_strs}\n{footer}"

        if len(out) > 1500:
            one_result = str(results[0])
            out = f"{header}\n{one_result}\n[{len(results) - 1} results omitted for output size.]\n{footer}"

        await try_delete(ctx.message)
        await ctx.send(f"{ctx.author.mention}\n{out}", allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.group(name='monattack', aliases=['ma', 'monster_attack'], invoke_without_command=True, help=f"""
    Rolls a monster's attack.
    __**Valid Arguments**__
    {VALID_AUTOMATION_ARGS}
    """)
    async def monster_atk(self, ctx, monster_name, atk_name=None, *, args=''):
        if atk_name is None or atk_name == 'list':
            return await self.monster_atk_list(ctx, monster_name)

        await try_delete(ctx.message)

        monster = await select_monster_full(ctx, monster_name)
        attacks = monster.attacks

        attack = await search_and_select(ctx, attacks, atk_name, lambda a: a.name)
        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_statblock(ctx, monster, args)
        args = argparse(args)

        embed = discord.Embed()
        if not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        caster, targets, combat = await targetutils.maybe_combat(ctx, monster, args)
        await actionutils.run_attack(ctx, embed, args, caster, attack, targets, combat)

        embed.colour = random.randint(0, 0xffffff)
        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)

    @monster_atk.command(name="list")
    async def monster_atk_list(self, ctx, monster_name):
        """Lists a monster's attacks."""
        await try_delete(ctx.message)
        monster = await select_monster_full(ctx, monster_name)
        await actionutils.send_action_list(ctx, caster=monster, attacks=monster.attacks)

    @commands.command(name='moncheck', aliases=['mc', 'monster_check'], help=f"""
    Rolls a check for a monster.
    {VALID_CHECK_ARGS}
    """)
    async def monster_check(self, ctx, monster_name, check, *args):
        monster: Monster = await select_monster_full(ctx, monster_name)

        skill_key = await search_and_select(ctx, SKILL_NAMES, check, lambda s: s)

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_statblock(ctx, monster, args)
        args = argparse(args)

        if not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        checkutils.run_check(skill_key, monster, args, embed)

        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @commands.command(name='monsave', aliases=['ms', 'monster_save'], help=f"""
    Rolls a save for a monster.
    {VALID_SAVE_ARGS}
    """)
    async def monster_save(self, ctx, monster_name, save_stat, *args):
        monster: Monster = await select_monster_full(ctx, monster_name)

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_statblock(ctx, monster, args)
        args = argparse(args)

        if not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        checkutils.run_save(save_stat, monster, args, embed)

        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @commands.command(name='moncast', aliases=['mcast', 'monster_cast'], help=f"""
    Casts a spell as a monster.
    __**Valid Arguments**__
    {VALID_SPELLCASTING_ARGS}
    
    {VALID_AUTOMATION_ARGS}
    """)
    async def monster_cast(self, ctx, monster_name, spell_name, *args):
        await try_delete(ctx.message)
        monster: Monster = await select_monster_full(ctx, monster_name)

        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_statblock(ctx, monster, args)
        args = argparse(args)

        if not args.last('i', type_=bool):
            try:
                spell = await select_spell_full(ctx, spell_name, list_filter=lambda s: s.name in monster.spellbook)
            except NoSelectionElements:
                return await ctx.send(f"No matching spells found in the creature's spellbook. Cast again "
                                      f"with the `-i` argument to ignore restrictions!")
        else:
            spell = await select_spell_full(ctx, spell_name)

        caster, targets, combat = await targetutils.maybe_combat(ctx, monster, args)
        result = await spell.cast(ctx, caster, targets, args, combat=combat)

        # embed display
        embed = result.embed
        embed.colour = random.randint(0, 0xffffff)

        if not args.last('h', type_=bool) and 'thumb' not in args:
            embed.set_thumbnail(url=monster.get_image_url())

        handle_source_footer(embed, monster, add_source_str=False)

        # save changes: combat state
        if combat:
            await combat.final()
        await ctx.send(embed=embed)

    # ==== inline rolling ====
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        await self.handle_inline_rolls(message)

    @staticmethod
    async def handle_inline_rolls(message):
        out = []
        roller = d20.Roller(context=PersistentRollContext())
        for expr, context_before, context_after in _find_inline_exprs(message.content):
            context_before = context_before.replace('\n', ' ')
            context_after = context_after.replace('\n', ' ')

            try:
                result = roller.roll(expr, allow_comments=True)
            except d20.RollSyntaxError:
                continue
            except d20.RollError as e:
                out.append(f"{context_before}({e!s}){context_after}")
            else:
                out.append(f"{context_before}({result.result}){context_after}")

        if not out:
            return

        await message.reply('\n'.join(out))


# ==== helpers ====
def _string_search_adv(rollstr):
    adv = d20.AdvType.NONE
    if re.search(r'(^|\s+)(adv|dis)(\s+|$)', rollstr) is not None:
        adv = d20.AdvType.ADV if re.search(r'(^|\s+)adv(\s+|$)', rollstr) is not None else d20.AdvType.DIS
        rollstr = re.sub(r'(adv|dis)(\s+|$)', '', rollstr)
    return rollstr, adv


def _find_inline_exprs(content, context_before=5, context_after=2, max_context_len=128):
    """Returns an iterator of tuples (expr, context_before, context_after)."""
    content_len = len(content)

    # all content indexes
    idxs = []
    for start, expr_start, expr_end, end in _find_roll_expr_indices(content):
        before_idx = max(0, start - max_context_len)
        before_fragment = content[before_idx:start]
        before_bits = before_fragment.rsplit(maxsplit=context_before)
        if len(before_bits) > context_before:
            before_idx += len(before_bits[0])

        after_idx = min(content_len, end + max_context_len)
        after_fragment = content[end:after_idx]
        after_bits = after_fragment.split(maxsplit=context_after)
        if len(after_bits) > context_after:
            after_idx -= len(after_bits[-1])

        idxs.append(((before_idx, start), (expr_start, expr_end), (end, after_idx)))

    # start boundaries
    for i, ((before_idx, start), (expr_start, expr_end), (end, after_idx)) in enumerate(idxs[1:], start=1):
        clamped_before_idx = max(before_idx, idxs[i - 1][2][0])
        idxs[i] = (clamped_before_idx, start), (expr_start, expr_end), (end, after_idx)

    # end boundaries
    for i, ((before_idx, start), (expr_start, expr_end), (end, after_idx)) in enumerate(idxs[:-1]):
        clamped_after_idx = min(after_idx, idxs[i + 1][0][0])
        idxs[i] = (before_idx, start), (expr_start, expr_end), (end, clamped_after_idx)

    # turn into the exprs
    for ((before_idx, start), (expr_start, expr_end), (end, after_idx)) in idxs:
        context_before = content[before_idx:start].lstrip()
        expr = content[expr_start:expr_end].strip()
        context_after = content[end:after_idx].rstrip()

        # ellipsis handling
        if before_idx > 0:
            context_before = f"...{context_before}"
        if after_idx < content_len:
            context_after = f"{context_after}..."

        yield expr, context_before, context_after


def _find_roll_expr_indices(content):
    """
    Returns an iterator of tuples (start, expr_start, expr_end, end) representing the indices of the roll exprs found
    (outside and inside the braces).
    """
    end = 0
    while (start := content.find('[[', end)) != -1:
        end = content.find(']]', start)
        if end == -1:
            break
        yield start, start + 2, end, end + 2


# ==== d.py ====
def setup(bot):
    bot.add_cog(Dice(bot))
