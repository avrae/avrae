import random
import re

import d20
import discord
from discord.ext import commands

from aliasing import helpers
from cogs5e.funcs import attackutils, checkutils, targetutils
from cogs5e.models.errors import NoSelectionElements
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

    @commands.command(name='2', hidden=True)
    async def quick_roll(self, ctx, *, mod: str = '0'):
        """Quickly rolls a d20."""
        rollStr = '1d20+' + mod
        await self.rollCmd(ctx, rollStr=rollStr)

    @commands.command(name='roll', aliases=['r'])
    async def rollCmd(self, ctx, *, rollStr: str = '1d20'):
        """Rolls dice in xdy format.
        __Examples__
        !r xdy Attack!
        !r xdy+z adv Attack with Advantage!
        !r xdy-z dis Hide with Heavy Armor!
        !r xdy+xdy*z
        !r XdYkhZ
        !r 4d6mi2[fire] Elemental Adept, Fire
        !r 2d6e6 Explode on 6
        !r 10d6ra6 Spell Bombardment
        !r 4d6ro<3 Great Weapon Master
        __Supported Operators__
        k (keep)
        p (drop)
        ro (reroll once)
        rr (reroll infinitely)
        mi/ma (min/max result)
        e (explode dice of value)
        ra (reroll and add)
        __Supported Selectors__
        X (literal X)
        lX (lowest X)
        hX (highest X)
        >X (greater than X)
        <X (less than X)"""

        if rollStr == '0/0':  # easter eggs
            return await ctx.send("What do you expect me to do, destroy the universe?")

        rollStr, adv = self._string_search_adv(rollStr)

        res = d20.roll(rollStr, advantage=adv, allow_comments=True, stringifier=VerboseMDStringifier())
        out = f"{ctx.author.mention}  :game_die:\n" \
              f"{str(res)}"
        if len(out) > 1999:
            out = f"{ctx.author.mention}  :game_die:\n" \
                  f"{str(res)[:100]}...\n" \
                  f"**Total:** {res.total}"

        await try_delete(ctx.message)
        await ctx.send(out, allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.command(name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations: int, *, rollStr):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <dice>"""
        rollStr, adv = self._string_search_adv(rollStr)
        await self._roll_many(ctx, iterations, rollStr, adv=adv)

    @commands.command(name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations: int, rollStr, dc: int = None, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        _, adv = self._string_search_adv(args)
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

        result_strs = '\n'.join([str(o) for o in results])

        out = f"{header}\n{result_strs}\n{footer}"

        if len(out) > 1500:
            one_result = str(results[0])[:100]
            one_result = f"{one_result}..." if len(one_result) > 100 else one_result
            out = f"{header}\n{one_result}\n{footer}"

        await try_delete(ctx.message)
        await ctx.send(f"{ctx.author.mention}\n{out}", allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.group(aliases=['ma', 'monster_attack'], invoke_without_command=True)
    async def monster_atk(self, ctx, monster_name, atk_name=None, *, args=''):
        """Rolls a monster's attack.
        __Valid Arguments__
        -t "<target>" - Sets targets for the attack. You can pass as many as needed. Will target combatants if channel is in initiative.
        -t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        *adv/dis* - Advantage or Disadvantage
        *ea* - Elven Accuracy double advantage

        -ac <target ac> - overrides target AC
        *-b* <to hit bonus> - adds a bonus to hit
        -criton <num> - a number to crit on if rolled on or above
        *-d* <damage bonus> - adds a bonus to damage
        *-c* <damage bonus on crit> - adds a bonus to crit damage
        -rr <times> - number of times to roll the attack against each target
        *-mi <value>* - minimum value of each die on the damage roll

        *-resist* <damage resistance>
        *-immune* <damage immunity>
        *-vuln* <damage vulnerability>
        *-neutral* <damage type> - ignores this damage type in resistance calculations
        *-dtype <damage type>* - replaces all damage types with this damage type
        *-dtype <old>new>* - replaces all of one damage type with another (e.g. `-dtype fire>cold`)

        *hit* - automatically hits
        *miss* - automatically misses
        *crit* - automatically crits if hit
        *max* - deals max damage
        *magical* - makes the damage type magical

        -h - hides name, rolled values, and monster details
        -phrase <text> - adds flavour text
        -title <title> - changes the result title *note: `[name]` and `[aname]` will be replaced automatically*
        -thumb <url> - adds flavour image
        -f "Field Title|Field Text" - see `!help embed`
        <user snippet> - see `!help snippet`

        An italicized argument means the argument supports ephemeral arguments - e.g. `-d1` applies damage to the first hit, `-b1` applies a bonus to one attack, and so on.
        """
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
        await attackutils.run_attack(ctx, embed, args, caster, attack, targets, combat)

        embed.colour = random.randint(0, 0xffffff)
        handle_source_footer(embed, monster, add_source_str=False)

        await ctx.send(embed=embed)

    @monster_atk.command(name="list")
    async def monster_atk_list(self, ctx, monster_name):
        """Lists a monster's attacks."""
        await try_delete(ctx.message)

        monster = await select_monster_full(ctx, monster_name)
        monster_name = monster.get_title_name()
        return await ctx.send(f"{monster_name}'s attacks:\n{monster.attacks.build_str(monster)}")

    @commands.command(aliases=['mc'])
    async def monster_check(self, ctx, monster_name, check, *args):
        """Rolls a check for a monster.
        __Valid Arguments__
        *adv/dis*
        *-b [conditional bonus]*
        -phrase [flavor text]
        -title [title] *note: [name] and [cname] will be replaced automatically*
        -thumb [thumbnail URL]
        -dc [dc]
        -rr [iterations]
        str/dex/con/int/wis/cha (different skill base; e.g. Strength (Intimidation))
        -h (hides name and image of monster)

        An italicized argument means the argument supports ephemeral arguments - e.g. `-b1` applies a bonus to one check.
        """

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

    @commands.command(aliases=['ms'])
    async def monster_save(self, ctx, monster_name, save_stat, *args):
        """Rolls a save for a monster.
        __Valid Arguments__
        adv/dis
        -b [conditional bonus]
        -phrase [flavor text]
        -title [title] *note: [name] and [cname] will be replaced automatically*
        -thumb [thumbnail URL]
        -dc [dc]
        -rr [iterations]
        -h (hides name and image of monster)"""

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

    @commands.command(aliases=['mcast'])
    async def monster_cast(self, ctx, monster_name, spell_name, *args):
        """
        Casts a spell as a monster.
        __Valid Arguments__
        -i - Ignores Spellbook restrictions, for demonstrations or rituals.
        -l <level> - Specifies the level to cast the spell at.
        noconc - Ignores concentration requirements.
        -h - Hides rolled values.
        **__Save Spells__**
        -dc <Save DC> - Overrides the spell save DC.
        -save <Save type> - Overrides the spell save type.
        -d <damage> - Adds additional damage.
        pass - Target automatically succeeds save.
        fail - Target automatically fails save.
        adv/dis - Target makes save at advantage/disadvantage.
        **__Attack Spells__**
        See `!a`.
        **__All Spells__**
        -phrase <phrase> - adds flavor text.
        -title <title> - changes the title of the cast. Replaces [sname] with spell name.
        -thumb <url> - adds an image to the cast.
        -dur <duration> - changes the duration of any effect applied by the spell.
        -mod <spellcasting mod> - sets the value of the spellcasting ability modifier.
        int/wis/cha - different skill base for DC/AB (will not account for extra bonuses)
        """
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
        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff)

        if not args.last('h', type_=bool) and 'thumb' not in args:
            embed.set_thumbnail(url=monster.get_image_url())

        handle_source_footer(embed, monster, add_source_str=False)

        # save changes: combat state
        if combat:
            await combat.final()
        await ctx.send(embed=embed)

    @staticmethod
    def _string_search_adv(rollstr):
        adv = d20.AdvType.NONE
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollstr) is not None:
            adv = d20.AdvType.ADV if re.search('(^|\s+)adv(\s+|$)', rollstr) is not None else d20.AdvType.DIS
            rollstr = re.sub('(adv|dis)(\s+|$)', '', rollstr)
        return rollstr, adv


def setup(bot):
    bot.add_cog(Dice(bot))
