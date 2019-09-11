import random
import re

import discord
from discord.ext import commands

from cogs5e.funcs import checkutils, scripting, targetutils
from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import select_monster_full
from cogs5e.models import embeds
from cogs5e.models.automation import Automation
from cogs5e.models.monster import Monster
from cogs5e.models.sheet import Attack
from cogsmisc.stats import Stats
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.functions import a_or_an, search_and_select, try_delete


class Dice(commands.Cog):
    """Dice and math related commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='2', hidden=True)
    async def quick_roll(self, ctx, *, mod: str = '0'):
        """Quickly rolls a d20."""
        rollStr = '1d20+' + mod
        await ctx.invoke(self.rollCmd, rollStr=rollStr)

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
        __Supported Selectors_
        lX (lowest X)
        hX (highest X)
        >X/<X (greater than or less than X)"""

        if rollStr == '0/0':  # easter eggs
            return await ctx.send("What do you expect me to do, destroy the universe?")

        adv = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv)
        out = res.result
        await try_delete(ctx.message)
        outStr = ctx.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await ctx.send(
                ctx.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(
                    res.plain))
        else:
            await ctx.send(outStr)
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.command(name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations: int, rollStr, *, args=''):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <xdy> [args]"""
        if iterations < 1 or iterations > 100:
            return await ctx.send("Too many or too few iterations.")
        adv = 0
        out = []
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for _ in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            out.append(res)
        outStr = "Rolling {} iterations...\n".format(iterations)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} total.'.format(sum(o.total for o in out))
        else:
            outStr = "Rolling {} iterations...\n[Output truncated due to length]\n".format(iterations) + \
                     '{} total.'.format(sum(o.total for o in out))
        await try_delete(ctx.message)
        await ctx.send(ctx.author.mention + '\n' + outStr)
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.command(name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations: int, rollStr, dc: int = 0, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 100:
            return await ctx.send("Too many or too few iterations.")
        adv = 0
        out = []
        successes = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for r in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            if res.plain >= dc:
                successes += 1
            out.append(res)
        outStr = "Rolling {} iterations, DC {}...\n".format(iterations, dc)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} successes.'.format(str(successes))
        else:
            outStr = "Rolling {} iterations, DC {}...\n[Output truncated due to length]\n".format(iterations,
                                                                                                  dc) + '{} successes.'.format(
                str(successes))
        await try_delete(ctx.message)
        await ctx.send(ctx.author.mention + '\n' + outStr)
        await Stats.increase_stat(ctx, "dice_rolled_life")

    @commands.group(aliases=['ma', 'monster_attack'], invoke_without_command=True)
    async def monster_atk(self, ctx, monster_name, atk_name=None, *, args=''):
        """Rolls a monster's attack.
        __Valid Arguments__
        -t "<target>" - Sets targets for the attack. You can pass as many as needed. Will target combatants if channel is in initiative.
        -t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        adv/dis
        -ac [target ac]
        -b [to hit bonus]
        -d [damage bonus]
        -d# [applies damage to the first # hits]
        -rr [times to reroll]
        -t [target]
        -phrase [flavor text]
        crit (automatically crit)
        -h (hides monster name and image)"""
        if atk_name is None or atk_name == 'list':
            return await ctx.invoke(self.monster_atk_list, monster_name)

        await try_delete(ctx.message)

        monster = await select_monster_full(ctx, monster_name)
        attacks = monster.attacks
        monster_name = monster.get_title_name()

        attack = await search_and_select(ctx, attacks, atk_name, lambda a: a['name'])
        args = await scripting.parse_snippets(args, ctx)
        args = argparse(args)
        if not args.last('h', type_=bool):
            name = monster_name
            image = args.get('image') or monster.get_image_url()
        else:
            name = "An unknown creature"
            image = None

        attack = Attack.from_old(attack)

        embed = discord.Embed()
        if args.last('title') is not None:
            embed.title = args.last('title') \
                .replace('[name]', name) \
                .replace('[aname]', attack.name)
        else:
            embed.title = '{} attacks with {}!'.format(name, a_or_an(attack.name))

        if image:
            embed.set_thumbnail(url=image)

        caster, targets, combat = await targetutils.maybe_combat(ctx, monster, args)
        await Automation.from_attack(attack).run(ctx, embed, caster, targets, args, combat=combat, title=embed.title)
        if combat:
            await combat.final()

        _fields = args.get('f')
        embeds.add_fields_from_args(embed, _fields)
        embed.colour = random.randint(0, 0xffffff)

        if monster.source == 'homebrew':
            embeds.add_homebrew_footer(embed)

        await ctx.send(embed=embed)

    @monster_atk.command(name="list")
    async def monster_atk_list(self, ctx, monster_name):
        await try_delete(ctx.message)

        monster = await select_monster_full(ctx, monster_name)
        monster_name = monster.get_title_name()
        attacks = monster.attacks
        attacks_string = '\n'.join("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                              a['attackBonus'],
                                                                              a['damage'] or 'no') for a in attacks)
        return await ctx.send("{}'s attacks:\n{}".format(monster_name, attacks_string))

    @commands.command(aliases=['mc'])
    async def monster_check(self, ctx, monster_name, check, *args):
        """Rolls a check for a monster.
        __Valid Arguments__
        *adv/dis*
        *-b [conditional bonus]*
        -phrase [flavor text]
        -title [title] *note: [name] and [cname] will be replaced automatically*
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

        args = await scripting.parse_snippets(args, ctx)
        args = argparse(args)

        checkutils.run_check(skill_key, monster, args, embed)

        if args.last('image') is not None:
            embed.set_thumbnail(url=args.last('image'))
        elif not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        if monster.source == 'homebrew':
            embeds.add_homebrew_footer(embed)

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
        -dc [dc]
        -rr [iterations]
        -h (hides name and image of monster)"""

        monster: Monster = await select_monster_full(ctx, monster_name)

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = await scripting.parse_snippets(args, ctx)
        args = argparse(args)

        checkutils.run_save(save_stat, monster, args, embed)

        if args.last('image') is not None:
            embed.set_thumbnail(url=args.last('image'))
        elif not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        if monster.source == 'homebrew':
            embeds.add_homebrew_footer(embed)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)


def setup(bot):
    bot.add_cog(Dice(bot))
