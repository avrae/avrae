import asyncio
import json
import os
import random
import re
import shlex

import discord
from discord.ext import commands
import numexpr

from cogs5e.dice import roll
from cogs5e.lookupFuncs import searchSpell, searchMonster
from utils import checks
from utils.functions import fuzzy_search, parse_args


class Dice:
    """Dice and math related commands."""
    def __init__(self, bot):
        self.bot = bot
        
    async def on_message(self, message):
        if message.content.startswith('!d20'):
            self.bot.botStats["dice_rolled_session"] += 1
            self.bot.botStats["dice_rolled_life"] += 1
            rollStr = message.content.replace('!', '1').split(' ')[0]
            try:
                rollFor = ' '.join(message.content.split(' ')[1:])
            except:
                rollFor = ''
            adv = 0
            if re.search('(^|\s+)(adv|dis)(\s+|$)', rollFor) is not None:
                adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollFor) is not None else -1
                rollFor = re.sub('(adv|dis)(\s+|$)', '', rollFor)
            out = roll(rollStr, adv=adv, rollFor=rollFor, inline=True)
            out = out.result
            try:
                await self.bot.delete_message(message)
            except:
                pass
            await self.bot.send_message(message.channel, message.author.mention + '  :game_die:\n' + out)
            
    @commands.command(name='2', hidden=True, pass_context=True)
    async def quick_roll(self, ctx, *, mod:str='0'):
        """Quickly rolls a d20."""
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.botStats["dice_rolled_life"] += 1
        rollStr = '1d20+' + mod
        adv = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollStr) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollStr) is not None else -1
            rollStr = re.sub('(adv|dis)(\s+|$)', '', rollStr)
        out = roll(rollStr, adv=adv, inline=True)
        out = out.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '  :game_die:\n' + out)
                        
        
    @commands.command(pass_context=True, name='roll', aliases=['r'])
    async def rollCmd(self, ctx, *, rollStr:str):
        """Rolls dice in xdy format.
        Usage: !r xdy Attack!
               !r xdy+z adv Attack with Advantage!
               !r xdy-z dis Hide with Heavy Armor!
               !r xdy+xdy*z
               !r XdYkhZ
        Supported Operators: k (keep)
                             ro (reroll once)
                             rr (reroll infinitely)
                             >/< (test if result is greater than/less than)
        Supported Selectors: lX (lowest X)
                             hX (highest X)"""
        
        adv = 0
        self.bot.botStats["dice_rolled_session"] += 1
        self.bot.botStats["dice_rolled_life"] += 1
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
            await self.bot.say(ctx.message.author.mention + '  :game_die:\n**Result:** ' + str(res.plain))
        else:
            await self.bot.say(outStr)
    
    @commands.command(pass_context=True, name='multiroll', aliases=['rr'])
    async def rr(self, ctx, iterations:int, rollStr, *, args=''):
        """Rolls dice in xdy format a given number of times.
        Usage: !rrr <iterations> <xdy> [args]"""
        if iterations < 1 or iterations > 500:
            return await self.bot.say("Too many or too few iterations.")
        self.bot.botStats["dice_rolled_session"] += iterations
        self.bot.botStats["dice_rolled_life"] += iterations
        adv = 0
        out = []
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for r in range(iterations):
            res = roll(rollStr, adv=adv, rollFor=args, inline=True)
            out.append(res)
        outStr = "Rolling {} iterations...\n".format(iterations)
        outStr += '\n'.join([o.skeleton for o in out])
        if len(outStr) < 1500:
            outStr += '\n{} total.'.format(sum(o.total for o in out))
        else:
            outStr = "Rolling {} iterations...\n".format(iterations) + '{} total.'.format(sum(o.total for o in out))
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)
        
    @commands.command(pass_context=True, name='iterroll', aliases=['rrr'])
    async def rrr(self, ctx, iterations:int, rollStr, dc:int, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: !rrr <iterations> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 500:
            return await self.bot.say("Too many or too few iterations.")
        self.bot.botStats["dice_rolled_session"] += iterations
        self.bot.botStats["dice_rolled_life"] += iterations
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
            outStr = "Rolling {} iterations, DC {}...\n".format(iterations, dc) + '{} successes.'.format(str(successes))
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say(ctx.message.author.mention + '\n' + outStr)
        
    @commands.command(pass_context=True)
    async def cast(self, ctx, *, args : str):
        """Casts a spell (i.e. rolls all the dice and displays a summary [auto-deleted after 15 sec]).
        Valid Arguments: -r <Some Dice> - Instead of rolling the default dice, rolls this instead."""
        
        try:
            guild_id = ctx.message.server.id 
            pm = self.bot.db.not_json_get("lookup_settings", {}).get(guild_id, {}).get("pm_result", False)    
        except:
            pm = False
        
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        args = args.split('-r')
        args = [re.sub('^\s+|\s+$', '', a) for a in args]
        spellName = args[0]
        
        spell = searchSpell(spellName, return_spell=True)
        self.bot.botStats["spells_looked_up_session"] += 1
        self.bot.botStats["spells_looked_up_life"] += 1
        if spell['spell'] is None:
            return await self.bot.say(spell['string'][0], delete_after=15)
        result = spell['string']
        spell = spell['spell']
        
        if len(args) == 1:
            rolls = spell.get('roll', '')
            if isinstance(rolls, list):
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + '\n'.join(roll(r, inline=True).skeleton for r in rolls)
            else:
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + roll(rolls, inline=True).skeleton

        else:
            rolls = args[1:]
            roll_results = ""
            for r in rolls:
                res = roll(r, inline=True)
                if res.total is not None:
                    roll_results += res.result + '\n'
                else:
                    roll_results += "**Effect:** " + r
            out = "**{} casts {}:**\n".format(ctx.message.author.mention, spell['name']) + roll_results
            
        await self.bot.say(out)
        for r in result:
            if pm:
                await self.bot.send_message(ctx.message.author, r)
            else:
                await self.bot.say(r, delete_after=15)
                
    @commands.command(pass_context=True, aliases=['ma'])
    async def monster_atk(self, ctx, monster_name, atk_name, *, args=''):
        """Rolls a monster's attack.
        Valid Arguments: adv/dis
                         -ac [target ac]
                         -b [to hit bonus]
                         -d [damage bonus]
                         -rr [times to reroll]
                         -t [target]
                         -phrase [flavor text]
                         crit (automatically crit)"""
        
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        
        monster = searchMonster(monster_name, return_monster=True, visible=True)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.botStats["monsters_looked_up_life"] += 1
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        attacks = monster.get('attacks')
        attack = fuzzy_search(attacks, 'name', atk_name)
        if attack is None:
            return await self.bot.say("No attack with that name found.", delete_after=15)
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff)
        
        args = shlex.split(args)
        total_damage = 0
        args = parse_args(args)
            
        if args.get('phrase') is not None:
            embed.description = '*' + args.get('phrase') + '*'
        else:
            embed.description = '~~' + ' '*500 + '~~'
            
        if args.get('target') is not None:
            embed.title = 'A {} attacks with a {} at {}!'.format(monster.get('name'), attack.get('name'), args.get('target'))
        else:
            embed.title = 'A {} attacks with a {}!'.format(monster.get('name'), attack.get('name'))
        
        for arg in ('rr', 'ac'):
            try:
                args[arg] = int(args.get(arg, 1))
            except (ValueError, TypeError):
                args[arg] = None
        args['adv'] = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        args['crit'] = 1 if args.get('crit', False) else None
        for r in range(args.get('rr', 1) or 1):
            if attack.get('attackBonus') is not None:
                if args.get('b') is not None:
                    toHit = roll('1d20+' + attack.get('attackBonus') + '+' + args.get('b'), adv=args.get('adv'), rollFor='To Hit', inline=True, show_blurbs=False)
                else:
                    toHit = roll('1d20+' + attack.get('attackBonus'), adv=args.get('adv'), rollFor='To Hit', inline=True, show_blurbs=False)
    
                out = ''
                out += toHit.result + '\n'
                itercrit = toHit.crit if not args.get('crit') else args.get('crit', 0)
                if args.get('ac') is not None:
                    if toHit.total < args.get('ac') and itercrit == 0:
                        itercrit = 2 # miss!
                
                if attack.get('damage') is not None:
                    if args.get('d') is not None:
                        damage = attack.get('damage') + '+' + args.get('d')
                    else:
                        damage = attack.get('damage')
                    
                    if itercrit == 1:
                        dmgroll = roll(damage, rollFor='Damage (CRIT!)', inline=True, double=True, show_blurbs=False)
                        out += dmgroll.result + '\n'
                        total_damage += dmgroll.total
                    elif itercrit == 2:
                        out += '**Miss!**\n'
                    else:
                        dmgroll = roll(damage, rollFor='Damage', inline=True, show_blurbs=False)
                        out += dmgroll.result + '\n'
                        total_damage += dmgroll.total
            else:
                out = ''
                if attack.get('damage') is not None:
                    if args.get('d') is not None:
                        damage = attack.get('damage') + '+' + args.get('d')
                    else:
                        damage = attack.get('damage')
                    
                    dmgroll = roll(damage, rollFor='Damage', inline=True, show_blurbs=False)
                    out += dmgroll.result + '\n'
                    total_damage += dmgroll.total
            
            if out is not '':
                if args.get('rr', 1) > 1:
                    embed.add_field(name='Attack {}'.format(r+1), value=out, inline=False)
                else:
                    embed.add_field(name='Attack', value=out, inline=False)
            
        if args.get('rr', 1) > 1 and attack.get('damage') is not None:
            embed.add_field(name='Total Damage', value=str(total_damage))
        
        if attack.get('desc') is not None:
            embed.add_field(name='Details', value=(attack.get('desc', '')))
        
        await self.bot.say(embed=embed)
            
#     def roll(self, dice, author=None, rolling_for='', inline=False):  # unused old command
#         resultTotal = 0 
#         resultString = ''
#         crit = 0
#         args = dice.split(' ')[2:]
#         dice = dice.split(' ')[1]
#         try:  # check for +/-
#             toAdd = int(dice.split('+')[1])
#         except Exception:
#             toAdd = 0
#         try:
#             toAdd = int(dice.split('-')[1]) * -1
#         except:
#             pass
#         dice = dice.split('+')[0].split('-')[0]
#     
#         try:  # grab dice
#             numDice = dice.split('d')[0]
#             diceVal = dice.split('d')[1]
#         except Exception:
#             return "Format has to be in .r xdy+z. I don't have a high enough INT to read otherwise."
#     
#         if numDice == '':  # clean up dice in case of "d20"
#             numDice = '1'
#             dice = '1' + dice
#     
#         if int(numDice) > 500:  # make sure we aren't rolling too much
#             return "I'm a dragon, not a robot! Roll less dice."
#     
#         rolls, limit = map(int, dice.split('d'))
#     
#         for r in range(rolls):
#             number = random.randint(1, limit)
#             if re.search('(^|\s+)(adv|dis)(\s+|$)', args):
#                 number2 = random.randint(1, limit)
#                 if re.search('(^|\s+)adv(\s+|$)', args):
#                     number = number if number > number2 else number2
#                 else:
#                     number = number if number < number2 else number2
#             resultTotal = resultTotal + number
#             
#             if number == limit or number == 1:
#                 numStr = '**' + str(number) + '**'
#             else:
#                 numStr = str(number)
#         
#             if resultString == '':
#                 resultString += numStr
#             else:
#                 resultString += ', ' + numStr
#     
#         if numDice == '1' and diceVal == '20' and resultTotal == 20:
#             crit = 1
#         elif numDice == '1' and diceVal == '20' and resultTotal == 1:
#             crit = 2
#         
#         rolling_for = rolling_for if rolling_for is not None else "Result"
#         rolling_for = re.sub('(adv|dis)(\s+|$)', '', rolling_for)
#         if not inline:
#             if toAdd:
#                 resultTotal = resultTotal + toAdd
#                 resultString = resultString + ' ({:+})'.format(toAdd)
#                 
#             if resultTotal < 1:
#                 resultString += "\nYou... actually rolled less than a 1. Good job."
#             
#             if rolling_for is '':
#                 rolling_for = None
#                 
#             if toAdd == 0 and numDice == '1':
#                 resultString = author.mention + "  :game_die:\n**{}:** ".format(rolling_for if rolling_for is not None else 'Result') + resultString
#             else:
#                 resultString = author.mention + "  :game_die:\n**{}:** ".format(rolling_for if rolling_for is not None else 'Result') + resultString + "\n**Total:** " + str(resultTotal)
#                 
#             if 'adv' in args:
#                 resultString += "\n**Rolled with Advantage**"
#             elif 'dis' in args:
#                 resultString += "\n**Rolled with Disadvantage**"
#         
#             if crit == 1:
#                 critStr = "\n_**Critical Hit!**_  " + tables.getCritMessage()
#                 resultString += critStr
#             elif crit == 2:
#                 critStr = "\n_**Critical Fail!**_  " + tables.getFailMessage()
#                 resultString += critStr
#         else:
#             if toAdd:
#                 resultTotal = resultTotal + toAdd
#                 resultString = resultString + '{:+}'.format(toAdd)
#             
#             if rolling_for is '':
#                 rolling_for = None
#                 
#             if toAdd == 0 and numDice == '1':
#                 resultString = author.mention + "  :game_die:\n**{}:** `".format(rolling_for if rolling_for is not None else 'Result') + resultString + "`"
#             else:
#                 resultString = author.mention + "  :game_die:\n**{}:** `".format(rolling_for if rolling_for is not None else 'Result') + resultString + "` = `" + str(resultTotal) + '`'
#                 
#             if re.search('(^|\s+)adv(\s+|$)', args):
#                 resultString += "\n**Rolled with Advantage**"
#             elif re.search('(^|\s+)dis(\s+|$)', args):
#                 resultString += "\n**Rolled with Disadvantage**"
#         
#             if crit == 1:
#                 critStr = "\n_**Critical Hit!**_  " + tables.getCritMessage()
#                 resultString += critStr
#             elif crit == 2:
#                 critStr = "\n_**Critical Fail!**_  " + tables.getFailMessage()
#                 resultString += critStr
#             
#         return resultString        
    
