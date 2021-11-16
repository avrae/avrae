import random
import re
import time

import d20
import discord
from discord.ext import commands

import utils.settings
from aliasing import helpers
from cogs5e.models import embeds
from cogs5e.models.errors import NoSelectionElements
from cogs5e.utils import actionutils, checkutils, targetutils
from cogs5e.utils.help_constants import *
from cogsmisc.stats import Stats
from gamedata import Monster
from gamedata.lookuputils import handle_source_footer, select_monster_full, select_spell_full
from utils.aldclient import discord_user_to_dict
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.dice import PersistentRollContext, VerboseMDStringifier
from utils.functions import search_and_select, try_delete

INLINE_ROLLING_EMOJI = '\U0001f3b2'  # :game_die:
INLINE_ROLLING_RE = re.compile(r'\[\[(.+?]?)]]')


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
        await self.handle_message_inline_rolls(message)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        await self.handle_reaction_inline_rolls(reaction, user)

    async def handle_message_inline_rolls(self, message):
        # find roll expressions
        if not INLINE_ROLLING_RE.search(message.content):
            return

        # inline rolling feature flag
        if not await self.bot.ldclient.variation(
                "cog.dice.inline_rolling.enabled",
                user=discord_user_to_dict(message.author),
                default=False):
            return

        if message.guild is not None:  # (always enabled in pms)
            guild_settings = await utils.settings.ServerSettings.for_guild(self.bot.mdb, message.guild.id)

            # if inline rolling is disabled on this server, skip
            if guild_settings.inline_enabled is utils.settings.guild.InlineRollingType.DISABLED:
                return

            # if inline rolling is set to react only, pop a reaction on it and return (we re-enter from on_reaction)
            if guild_settings.inline_enabled is utils.settings.guild.InlineRollingType.REACTION:
                try:
                    await message.add_reaction(INLINE_ROLLING_EMOJI)
                except discord.HTTPException:
                    return  # if we can't react, just skip
                await self.inline_rolling_reaction_onboarding(message.author)
                return

        # if this is the user's first interaction with inline rolling, send an onboarding message
        await self.inline_rolling_message_onboarding(message.author)

        # otherwise do the rolls
        await self.do_inline_rolls(message)

    async def handle_reaction_inline_rolls(self, reaction, user):
        if user.id != reaction.message.author.id:
            return
        if reaction.emoji != INLINE_ROLLING_EMOJI:
            return
        message = reaction.message

        # find roll expressions
        if not INLINE_ROLLING_RE.search(message.content):
            return

        # if the reaction is in PMs (inline rolling always enabled), skip
        if message.guild is None:
            return

        # inline rolling feature flag
        if not await self.bot.ldclient.variation(
                "cog.dice.inline_rolling.enabled",
                user=discord_user_to_dict(message.author),
                default=False):
            return

        # if inline rolling is not set to reactions, skip
        guild_settings = await utils.settings.ServerSettings.for_guild(self.bot.mdb, message.guild.id)
        if guild_settings.inline_enabled is not utils.settings.guild.InlineRollingType.REACTION:
            return

        # if this message has already been processed, skip
        if await self.bot.rdb.get(f"cog.dice.inline_rolling.messages.{message.id}.processed"):
            return

        # otherwise save that this message has been processed, remove reactions, and do the rolls
        await self.bot.rdb.setex(
            f"cog.dice.inline_rolling.messages.{message.id}.processed",
            str(time.time()),
            60 * 60 * 24
        )
        await self.do_inline_rolls(message)
        try:
            await reaction.clear()
        except discord.HTTPException:
            pass

    @staticmethod
    async def do_inline_rolls(message):
        roll_exprs = _find_inline_exprs(message.content)

        out = []
        roller = d20.Roller(context=PersistentRollContext())
        for expr, context_before, context_after in roll_exprs:
            context_before = context_before.replace('\n', ' ')
            context_after = context_after.replace('\n', ' ')

            try:
                result = roller.roll(expr, allow_comments=True)
            except d20.RollSyntaxError:
                continue
            except d20.RollError as e:
                out.append(f"{context_before}({e!s}){context_after}")
            else:
                if not result.comment:
                    out.append(f"{context_before}({result.result}){context_after}")
                else:
                    out.append(f"{result.comment}: {result.result}")

        if not out:
            return

        await message.reply('\n'.join(out))

    async def inline_rolling_message_onboarding(self, user):
        if await self.bot.rdb.get(f"cog.dice.inline_rolling.users.{user.id}.onboarded.message"):
            return

        embed = embeds.EmbedWithColor()
        embed.title = "Inline Rolling"
        embed.description = f"Hi {user.mention}, it looks like this is your first time using inline rolling with me!"
        embed.add_field(
            name="What is Inline Rolling?",
            value="Whenever you send a message with some dice in between double brackets (e.g. `[[1d20]]`), I'll reply "
                  "to it with a roll for each one. You can send messages with multiple, too, like this: ```\n"
                  "I attack the goblin with my shortsword [[1d20 + 6]] for a total of [[1d6 + 3]] piercing damage.\n"
                  "```"
        )
        embed.set_footer(text="You won't see this message again.")

        try:
            await user.send(embed=embed)
        except discord.HTTPException:
            return
        await self.bot.rdb.set(f"cog.dice.inline_rolling.users.{user.id}.onboarded.message", str(time.time()))

    async def inline_rolling_reaction_onboarding(self, user):
        if await self.bot.rdb.get(f"cog.dice.inline_rolling.users.{user.id}.onboarded.reaction"):
            return

        embed = embeds.EmbedWithColor()
        embed.title = "Inline Rolling - Reactions"
        embed.description = f"Hi {user.mention}, it looks like this is your first time using inline rolling with me!"
        embed.add_field(
            name="What is Inline Rolling?",
            value="Whenever you send a message with some dice in between double brackets (e.g. `[[1d20]]`), I'll react "
                  f"with the {INLINE_ROLLING_EMOJI} emoji. You can click it to have me roll all of the dice in your "
                  "message, and I'll reply with my own message!"
        )
        embed.set_footer(text="You won't see this message again.")

        try:
            await user.send(embed=embed)
        except discord.HTTPException:
            return
        await self.bot.rdb.set(f"cog.dice.inline_rolling.users.{user.id}.onboarded.reaction", str(time.time()))


# ==== helpers ====
def _string_search_adv(rollstr):
    adv = d20.AdvType.NONE
    if re.search(r'(^|\s+)(adv|dis)(\s+|$)', rollstr) is not None:
        adv = d20.AdvType.ADV if re.search(r'(^|\s+)adv(\s+|$)', rollstr) is not None else d20.AdvType.DIS
        rollstr = re.sub(r'(adv|dis)(\s+|$)', '', rollstr)
    return rollstr, adv


def _find_inline_exprs(content, context_before=5, context_after=2, max_context_len=128):
    """Returns an iterator of tuples (expr, context_before, context_after)."""

    # create list alternating (before, expr; text, expr; ...; text, expr; after)
    segments = INLINE_ROLLING_RE.split(content)

    # want (before, expr, after; ...; before, expr, after)
    # so split up each pair of (text, expr) by trimming the text into (last_after, before, expr)
    # with priority on before
    trimmed_segments = []
    for text, expr in zip(a := iter(segments), a):  # fun way to take pairs from a list!
        text_len = len(text)

        # before is always text[before_idx:len(text)]
        before_idx = 0
        before_bits = text.rsplit(maxsplit=context_before)
        if len(before_bits) > context_before:
            before_idx += len(before_bits[0])
        before_idx = max(before_idx, text_len - max_context_len)
        before = text[before_idx:text_len]

        # last_after is always text[0:last_after_end_idx]
        last_after_end_idx = text_len
        after_bits = text.split(maxsplit=context_after)
        if len(after_bits) > context_after:
            last_after_end_idx -= len(after_bits[-1])
        last_after_end_idx = min(last_after_end_idx, before_idx)
        last_after = text[0:last_after_end_idx]

        trimmed_segments.extend((last_after, before, expr))

    if not trimmed_segments:
        return

    # now we have (junk, before, expr; after, before, expr; ...; after, before, expr)
    # discard the first junk
    discarded_before = trimmed_segments.pop(0)
    # and clean up the last after
    discarded_after = False
    last_after = segments[-1]
    last_after_end_idx = len(last_after)
    after_bits = last_after.split(maxsplit=context_after)
    if len(after_bits) > context_after:
        last_after_end_idx -= len(after_bits[-1])
        discarded_after = True
    trimmed_segments.append(last_after[0:last_after_end_idx])
    # we also use whether or not the chopped-off bits at the very start and end exist for ellipses

    # now we have (before, expr, after; ...)
    # do ellipses and yield triples (expr, context_before, context_after)
    num_triples = len(trimmed_segments) // 3
    for idx, (before, expr, after) in enumerate(zip(a := iter(trimmed_segments), a, a)):
        context_before = before.lstrip()
        context_after = after.rstrip()

        if idx or discarded_before:  # not the first or something was discarded before first
            context_before = f"...{context_before}"

        if idx + 1 < num_triples or discarded_after:  # not the last or something was discarded after last
            context_after = f"{context_after}..."

        yield expr.strip(), context_before, context_after


# ==== d.py ====
def setup(bot):
    bot.add_cog(Dice(bot))
