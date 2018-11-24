import random
import re
import shlex

import discord
from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import select_monster_full
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.models import embeds
from cogs5e.models.monster import Monster, SKILL_MAP
from utils.argparser import argparse
from utils.functions import fuzzy_search, a_or_an, verbose_stat, camel_to_title


class Dice:
    """Dice and math related commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='2', hidden=True, pass_context=True)
    async def quick_roll(self, ctx, *, mod: str = '0'):
        """Quickly rolls a d20."""
        self.bot.rdb.incr('dice_rolled_life')
        rollStr = '1d20+' + mod
        await ctx.invoke(self.bot.get_command("roll"), rollStr=rollStr)

    @commands.command(pass_context=True, name='roll', aliases=['r'])
    async def rollCmd(self, ctx, *, rollStr: str = '1d20'):
        """Rolls dice in xdy format.
        Usage: !r xdy Attack!
               !r xdy+z adv Attack with Advantage!
               !r xdy-z dis Hide with Heavy Armor!
               !r xdy+xdy*z
               !r XdYkhZ
               !r 4d6mi2[fire] Elemental Adept, Fire
               !r 2d6e6 Explode on 6
               !r 10d6ra6 Spell Bombardment
               !r 4d6ro<3 Great Weapon Master
        Supported Operators: k (keep)
                             ro (reroll once)
                             rr (reroll infinitely)
                             mi/ma (min/max result)
                             e (explode dice of value)
                             ra (reroll and add)
        Supported Selectors: lX (lowest X)
                             hX (highest X)
                             >X/<X (greater than or less than X)"""

        if rollStr == '0/0':  # easter eggs
            return await self.bot.say("What do you expect me to do, destroy the universe?")

        adv = 0
        self.bot.rdb.incr('dice_rolled_life')
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        res = roll(rollStr, adv=adv)
        out = res.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        outStr = ctx.message.author.mention + '  :game_die:\n' + out
        if len(outStr) > 1999:
            await self.bot.say(
                ctx.message.author.mention + '  :game_die:\n[Output truncated due to length]\n**Result:** ' + str(
                    res.plain))
        else:
            await self.bot.say(outStr)

    @commands.command(pass_context=True, name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations: int, rollStr, *, args=''):
        """Rolls dice in xdy format a given number of times.
        Usage: !rrr <iterations> <xdy> [args]"""
        if iterations < 1 or iterations > 100:
            return await self.bot.say("Too many or too few iterations.")
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
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)

    @commands.command(pass_context=True, name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations: int, rollStr, dc: int = 0, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 100:
            return await self.bot.say("Too many or too few iterations.")
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
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)

    @commands.command(pass_context=True, aliases=['ma', 'monster_attack'])
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
        -h (hide monster name/image)"""

        try:
            await self.bot.delete_message(ctx.message)
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
            return await self.bot.say("{}'s attacks:\n{}".format(monster_name, attacks_string))
        attack = fuzzy_search(attacks, 'name', atk_name)
        if attack is None:
            return await self.bot.say("No attack with that name found.", delete_after=15)

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
            embed.set_footer(text="Homebrew content.", icon_url="https://avrae.io/static/homebrew.png")

        await self.bot.say(embed=embed)

    @commands.command(pass_context=True, aliases=['mc'])
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
        skills = monster.skills

        try:
            skill = next(a for a in skills.keys() if check.lower() == a.lower())
        except StopIteration:
            try:
                skill = next(a for a in skills.keys() if check.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid check.')

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = argparse(args)
        adv = args.adv()
        b = args.join('b', '+')
        phrase = args.join('phrase', '\n')
        formatted_d20 = '1d20' if adv == 0 else '2d20' + ('kh1' if adv == 1 else 'kl1')
        iterations = min(args.last('rr', 1, int), 25)
        dc = args.last('dc', type_=int)
        num_successes = 0

        mod = skills[skill]
        skill_name = skill
        if any(args.last(s, type_=bool) for s in ("str", "dex", "con", "int", "wis", "cha")):
            base = next(s for s in ("str", "dex", "con", "int", "wis", "cha") if args.last(s, type_=bool))
            mod = mod - monster.get_mod(SKILL_MAP[skill]) + monster.get_mod(base)
            skill_name = f"{verbose_stat(base)} ({skill})"

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
                result = roll(roll_str, adv=adv, inline=True)
                if dc and result.total >= dc:
                    num_successes += 1
                embed.add_field(name=f"Check {i+1}", value=result.skeleton)
            if dc:
                embed.set_footer(text=f"{num_successes} Successes | {iterations - num_successes} Failues")
        else:
            result = roll(roll_str, adv=adv, inline=True)
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
            embed.set_footer(text="Homebrew content.", icon_url="https://avrae.io/static/homebrew.png")

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @commands.command(pass_context=True, aliases=['ms'])
    async def monster_save(self, ctx, monster_name, save, *args):
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

        saves = monster.saves

        try:
            save = next(a for a in saves.keys() if save.lower() == a.lower())
        except StopIteration:
            try:
                save = next(a for a in saves.keys() if save.lower() in a.lower())
            except StopIteration:
                return await self.bot.say('That\'s not a valid save.')

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)

        args = argparse(args)
        adv = args.adv()
        b = args.join('b', '+')
        phrase = args.join('phrase', '\n')
        iterations = min(args.last('rr', 1, int), 25)
        dc = args.last('dc', type_=int)
        num_successes = 0

        if b is not None:
            roll_str = '1d20{:+}'.format(saves[save]) + '+' + b
        else:
            roll_str = '1d20{:+}'.format(saves[save])

        if not args.last('h', type_=bool):
            default_title = f'{monster_name} makes {a_or_an(camel_to_title(save))}!'
        else:
            default_title = f"An unknown creature makes {a_or_an(camel_to_title(save))}!"

        embed.title = args.last('title', '') \
                          .replace('[mname]', monster_name) \
                          .replace('[sname]', camel_to_title(save)) \
                      or default_title

        if iterations > 1:
            embed.description = (f"**DC {dc}**\n" if dc else '') + ('*' + phrase + '*' if phrase is not None else '')
            for i in range(iterations):
                result = roll(roll_str, adv=adv, inline=True)
                if dc and result.total >= dc:
                    num_successes += 1
                embed.add_field(name=f"Check {i+1}", value=result.skeleton)
            if dc:
                embed.set_footer(text=f"{num_successes} Successes | {iterations - num_successes} Failues")
        else:
            result = roll(roll_str, adv=adv, inline=True)
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
            embed.set_footer(text="Homebrew content.", icon_url="https://avrae.io/static/homebrew.png")

        await self.bot.say(embed=embed)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass


def setup(bot):
    bot.add_cog(Dice(bot))
