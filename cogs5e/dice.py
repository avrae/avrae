import random
import re

import discord
from discord.ext import commands

from cogs5e.funcs import scripting
from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import select_monster_full
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.models import embeds
from cogs5e.models.monster import Monster, SKILL_MAP
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.functions import a_or_an, camel_to_title, search_and_select, verbose_stat


class Dice(commands.Cog):
    """Dice and math related commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='2', hidden=True)
    async def quick_roll(self, ctx, *, mod: str = '0'):
        """Quickly rolls a d20."""
        self.bot.rdb.incr('dice_rolled_life')
        rollStr = '1d20+' + mod
        await ctx.invoke(self.bot.get_command("roll"), rollStr=rollStr)

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
        self.bot.rdb.incr('dice_rolled_life')
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv)
        out = res.result
        try:
            await ctx.message.delete()
        except:
            pass
        outStr = ctx.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await ctx.send(
                ctx.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(
                    res.plain))
        else:
            await ctx.send(outStr)

    @commands.command(name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations: int, rollStr, *, args=''):
        """Rolls dice in xdy format a given number of times.
        Usage: !rr <iterations> <xdy> [args]"""
        if iterations < 1 or iterations > 100:
            return await ctx.send("Too many or too few iterations.")
        self.bot.rdb.incr('dice_rolled_life')
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
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send(ctx.author.mention + '\n' + outStr)

    @commands.command(name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations: int, rollStr, dc: int = 0, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 100:
            return await ctx.send("Too many or too few iterations.")
        self.bot.rdb.incr('dice_rolled_life')
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
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send(ctx.author.mention + '\n' + outStr)

    @commands.command(aliases=['ma', 'monster_attack'])
    async def monster_atk(self, ctx, monster_name, atk_name='list', *, args=''):
        """Rolls a monster's attack.
        Attack name can be "list" for a list of all of the monster's attacks.
        __Valid Arguments__
        adv/dis
        -ac [target ac]
        -b [to hit bonus]
        -d [damage bonus]
        -d# [applies damage to the first # hits]
        -rr [times to reroll]
        -t [target]
        -phrase [flavor text]
        crit (automatically crit)
        -h (hides monster name, image, and attack details)"""

        try:
            await ctx.message.delete()
        except:
            pass

        monster = await select_monster_full(ctx, monster_name)
        self.bot.rdb.incr('monsters_looked_up_life')
        attacks = monster.attacks
        monster_name = monster.get_title_name()
        if atk_name == 'list':
            attacks_string = '\n'.join("**{0}:** +{1} To Hit, {2} damage.".format(a['name'],
                                                                                  a['attackBonus'],
                                                                                  a['damage'] or 'no') for a in attacks)
            return await ctx.send("{}'s attacks:\n{}".format(monster_name, attacks_string))
        attack = await search_and_select(ctx, attacks, atk_name, lambda a: a['name'])
        args = await scripting.parse_snippets(args, ctx)
        args = argparse(args)
        if not args.last('h', type_=bool):
            args['name'] = monster_name
            args['image'] = args.get('image') or monster.get_image_url()
        else:
            args['name'] = "An unknown creature"
        attack['details'] = attack.get('desc') or attack.get('details')

        result = sheet_attack(attack, args)
        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff)
        embeds.add_fields_from_args(embed, args.get('f'))

        if monster.source == 'homebrew':
            embed.set_footer(text="Homebrew content.", icon_url="https://avrae.io/assets/img/homebrew.png")

        if args.last('h', type_=bool):
            try:
                await ctx.author.send(embed=result['full_embed'])
            except:
                pass

        await ctx.send(embed=embed)

    @commands.command(aliases=['mc'])
    async def monster_check(self, ctx, monster_name, check, *args):
        """Rolls a check for a monster.
        __Valid Arguments__
        adv/dis
        -b [conditional bonus]
        -phrase [flavor text]
        -title [title] *note: [mname] and [cname] will be replaced automatically*
        -dc [dc]
        -rr [iterations]
        str/dex/con/int/wis/cha (different skill base; e.g. Strength (Intimidation))
        -h (hides name and image of monster)"""

        monster: Monster = await select_monster_full(ctx, monster_name)
        self.bot.rdb.incr('monsters_looked_up_life')

        monster_name = monster.get_title_name()
        skill_key = await search_and_select(ctx, SKILL_NAMES, check, lambda s: s)
        skill_name = camel_to_title(skill_key)

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = await scripting.parse_snippets(args, ctx)
        args = argparse(args)

        adv = args.adv(boolwise=True)
        b = args.join('b', '+')
        phrase = args.join('phrase', '\n')
        iterations = min(args.last('rr', 1, int), 25)
        dc = args.last('dc', type_=int)
        num_successes = 0

        skill = monster.skills[skill_key]
        mod = skill.value
        formatted_d20 = skill.d20(base_adv=adv, base_only=True)

        if any(args.last(s, type_=bool) for s in ("str", "dex", "con", "int", "wis", "cha")):
            base = next(s for s in ("str", "dex", "con", "int", "wis", "cha") if args.last(s, type_=bool))
            mod = mod - monster.get_mod(SKILL_MAP[skill_key]) + monster.get_mod(base)
            skill_name = f"{verbose_stat(base)} ({skill_name})"

        skill_name = skill_name.title()
        if not args.last('h', type_=bool):
            default_title = '{} makes {} check!'.format(monster_name, a_or_an(skill_name))
        else:
            default_title = f"An unknown creature makes {a_or_an(skill_name)} check!"

        if b is not None:
            roll_str = formatted_d20 + '{:+}'.format(mod) + '+' + b
        else:
            roll_str = formatted_d20 + '{:+}'.format(mod)

        embed.title = args.last('title', '') \
                          .replace('[mname]', monster_name) \
                          .replace('[cname]', skill_name) \
                      or default_title

        if iterations > 1:
            embed.description = (f"**DC {dc}**\n" if dc else '') + ('*' + phrase + '*' if phrase is not None else '')
            for i in range(iterations):
                result = roll(roll_str, inline=True)
                if dc and result.total >= dc:
                    num_successes += 1
                embed.add_field(name=f"Check {i + 1}", value=result.skeleton)
            if dc:
                embed.set_footer(text=f"{num_successes} Successes | {iterations - num_successes} Failues")
        else:
            result = roll(roll_str, inline=True)
            if dc:
                embed.set_footer(text="Success!" if result.total >= dc else "Failure!")
            embed.description = (f"**DC {dc}**\n" if dc else '') + result.skeleton + (
                '\n*' + phrase + '*' if phrase is not None else '')

        embeds.add_fields_from_args(embed, args.get('f'))

        if args.last('image') is not None:
            embed.set_thumbnail(url=args.last('image'))
        elif not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        if monster.source == 'homebrew':
            embed.set_footer(text="Homebrew content.", icon_url="https://avrae.io/assets/img/homebrew.png")

        await ctx.send(embed=embed)
        try:
            await ctx.message.delete()
        except:
            pass

    @commands.command(aliases=['ms'])
    async def monster_save(self, ctx, monster_name, save_stat, *args):
        """Rolls a save for a monster.
        __Valid Arguments__
        adv/dis
        -b [conditional bonus]
        -phrase [flavor text]
        -title [title] *note: [mname] and [cname] will be replaced automatically*
        -dc [dc]
        -rr [iterations]
        -h (hides name and image of monster)"""

        monster: Monster = await select_monster_full(ctx, monster_name)
        self.bot.rdb.incr('monsters_looked_up_life')
        monster_name = monster.get_title_name()

        try:
            save = monster.saves.get(save_stat)
            save_name = f"{verbose_stat(save_stat[:3]).title()} Save"
        except ValueError:
            return await ctx.send('That\'s not a valid save.')

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = await scripting.parse_snippets(args, ctx)
        args = argparse(args)
        adv = args.adv(boolwise=True)
        b = args.join('b', '+')
        phrase = args.join('phrase', '\n')
        iterations = min(args.last('rr', 1, int), 25)
        dc = args.last('dc', type_=int)
        num_successes = 0

        formatted_d20 = save.d20(base_adv=adv)

        if b:
            roll_str = f"{formatted_d20}+{b}"
        else:
            roll_str = formatted_d20

        if not args.last('h', type_=bool):
            default_title = f'{monster_name} makes {a_or_an(save_name)}!'
        else:
            default_title = f"An unknown creature makes {a_or_an(save_name)}!"

        embed.title = args.last('title', '') \
                          .replace('[mname]', monster_name) \
                          .replace('[sname]', save_name) \
                      or default_title

        if iterations > 1:
            embed.description = (f"**DC {dc}**\n" if dc else '') + ('*' + phrase + '*' if phrase is not None else '')
            for i in range(iterations):
                result = roll(roll_str, inline=True)
                if dc and result.total >= dc:
                    num_successes += 1
                embed.add_field(name=f"Check {i + 1}", value=result.skeleton)
            if dc:
                embed.set_footer(text=f"{num_successes} Successes | {iterations - num_successes} Failues")
        else:
            result = roll(roll_str, inline=True)
            if dc:
                embed.set_footer(text="Success!" if result.total >= dc else "Failure!")
            embed.description = (f"**DC {dc}**\n" if dc else '') + result.skeleton + (
                '\n*' + phrase + '*' if phrase is not None else '')

        embeds.add_fields_from_args(embed, args.get('f'))

        if args.last('image') is not None:
            embed.set_thumbnail(url=args.last('image'))
        elif not args.last('h', type_=bool):
            embed.set_thumbnail(url=monster.get_image_url())

        if monster.source == 'homebrew':
            embed.set_footer(text="Homebrew content.", icon_url="https://avrae.io/assets/img/homebrew.png")

        await ctx.send(embed=embed)
        try:
            await ctx.message.delete()
        except:
            pass


def setup(bot):
    bot.add_cog(Dice(bot))
