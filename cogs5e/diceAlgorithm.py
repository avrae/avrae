import asyncio
from heapq import nlargest, nsmallest
import json
from math import *
import os
import random
import re
import traceback

import discord
from discord.ext import commands
import numexpr

import checks
from cogs5e import tables
from functions import list_get, discord_trim

# Rolls Dice
def d_roller(obj, adv=0):
    res = []
    out = []
    opts = {'reroll':[]}
    crit = 0
    total = 0
    # Recognizes dice
    args = obj
    obj = re.findall('\d+', obj)
    obj = [int(x) for x in obj]
    numArgs = len(obj)
    if numArgs == 1:
        numDice = 1
        diceVal = obj[0]
    elif numArgs == 2:
        numDice = obj[0]
        diceVal = obj[-1]
    else: # split into xdy and operators
        numDice = obj[0]
        diceVal = obj[1]
        args = re.split('(\d+d\d+)', args)[-1]
        splargs = re.split('(kh)|(kl)|(r)', args)
        splargs = [a for a in splargs if a is not None]
        if 'kh' in splargs:
            opts['keep_highest'] = list_get(splargs.index('kh') + 1, 1, splargs)
        elif 'kl' in splargs: # don't keep lowest if we're keeping highest
            opts['keep_lowest'] = list_get(splargs.index('kl') + 1, 1, splargs)
        if 'r' in splargs: # reroll, can be chained
            for a in range(len(splargs)):
                if splargs[a] is 'r':
                    opts['reroll'].append(list_get(a + 1, 0, splargs))
            
    # dice repair/modification
    if numDice > 300 or diceVal < 1 or numDice == 0:
        raise Exception('Too many dice rolled.')
    
    for die in range(numDice):
        try:
            rand1 = random.randrange(1, diceVal + 1)
            rand2 = random.randrange(1, diceVal + 1)
            randres = (rand1 if adv == 0 else
                       rand1 if adv == 1 and rand1 > rand2 else
                       rand1 if adv == -1 and rand1 < rand2 else
                       rand2)
            res.append(randres)
        except:
            res.append(1)
            
    rawRes = list(map(str, res))
    
    if opts.get('reroll') is not []:
        reroll = [int(r) for r in opts.get('reroll')]
        for i in range(250): # let's only iterate 250 times for sanity
            breakCheck = True
            for r in reroll:
                if r in res:
                    breakCheck = False
            for r in range(len(res)):
                if res[r] in reroll:
                    try:
                        rand1 = random.randrange(1, diceVal + 1)
                        rand2 = random.randrange(1, diceVal + 1)
                        randres = (rand1 if adv == 0 else
                                   rand1 if adv == 1 and rand1 > rand2 else
                                   rand1 if adv == -1 and rand1 < rand2 else
                                   rand2)
                        res[r] = randres
                        rawRes.append(str(randres))
                    except:
                        res[r] = 1
                        rawRes.append('1')
            if breakCheck:
                break
    if opts.get('keep_highest') is not None:
        res = nlargest(int(opts.get('keep_highest')), res)
    elif opts.get('keep_lowest') is not None:
        res = nsmallest(int(opts.get('keep_lowest')), res)
        
    for r in res:
        total += r
        
    # check for crits/crails        
    if numDice == 1 and diceVal == 20 and int(rawRes[0]) == 20:
        crit = 1
    elif numDice == 1 and diceVal == 20 and int(rawRes[0]) == 1:
        crit = 2
    
    res = list(map(str, res))
    for r in range(0, len(rawRes)):
        if rawRes[r] in res:
            res.remove(rawRes[r])
        else:
            rawRes[r] = '~~' + rawRes[r] + '~~'
    
    # Returns string of answer
    
    for r in range(0, len(rawRes)):
        if rawRes[r] == '1' or rawRes[r] == str(diceVal):
            rawRes[r] = '_' + rawRes[r] + '_'
    
    # build the output list
    out = DiceResult(total, '[' + ', '.join(rawRes) + ']', crit)
    return out

# # Dice Roller
def roll_create(rollStr, adv:int=0, rollFor='', inline=False):
    try:
        reply = []
        out_set = []
        crit = 0
        total = 0
        # Parses math/dice terms
        dice_temp = rollStr.replace('^', '**')
        # Splits into sections of ['dice', 'operator', 'dice'...] like ['1d20', '+', '4d6', '+', '5']
        dice_set = re.split('([-+*/^().])', dice_temp)
        out_set = re.split('([-+*/^().])', dice_temp)
        eval_set = re.split('([-+*/^().])', dice_temp)
        
        
        # Replaces dice sets with rolled results
        for i, t in enumerate(dice_set):
            if 'd' in t:
                result = d_roller(t, adv)
                out_set[i] = t + " " + result.result
                dice_set[i] = result.result
                eval_set[i] = str(result.plain)
                if not result.crit == 0:
                    crit = result.crit
                    
                    
        total = ''.join(eval_set)
        total = numexpr.evaluate(total)
        
        rolled = ' '.join(out_set).replace('**', '^').replace('_', '**')
        totalStr = str(floor(total))
        
        if not inline:
            # Builds end result while showing rolls
            reply.append(' '.join(out_set) + '\n_Total:_ ' + str(floor(total)))
            skeletonReply = reply
            # Replies to user with message
            reply = '\n\n'.join(reply).replace('**', '^').replace('_', '**')
            rollFor = rollFor if rollFor is not '' else 'Result'
            reply = ':game_die:\n**{}:** '.format(rollFor) + reply
            if adv == 1:
                reply += '\n**Rolled with Advantage**'
            elif adv == -1:
                reply += '\n**Rolled with Disadvantage**'
            if crit == 1:
                critStr = "\n_**Critical Hit!**_  " + tables.getCritMessage()
                reply += critStr
            elif crit == 2:
                critStr = "\n_**Critical Fail!**_  " + tables.getFailMessage()
                reply += critStr
        else:
            # Builds end result while showing rolls
            reply.append('' + ' '.join(out_set) + ' = `' + str(floor(total)) + '`')
                
            # Replies to user with message
            reply = '\n\n'.join(reply).replace('**', '^').replace('_', '**')
            skeletonReply = reply
            rollFor = rollFor if rollFor is not '' else 'Result'
            reply = ':game_die:\n**{}:** '.format(rollFor) + reply
            if adv == 1:
                reply += '\n**Rolled with Advantage**'
            elif adv == -1:
                reply += '\n**Rolled with Disadvantage**'
            if crit == 1:
                critStr = "\n_**Critical Hit!**_  " + tables.getCritMessage()
                reply += critStr
            elif crit == 2:
                critStr = "\n_**Critical Fail!**_  " + tables.getFailMessage()
                reply += critStr
        return DiceResult(result=floor(total), verbose_result=reply, crit=crit, rolled=rolled, skeleton=skeletonReply)
        
    except Exception as ex:
        traceback.print_exc()
        return DiceResult(verbose_result="Invalid input: {}".format(ex))

class DiceResult:
    """Class to hold the output of a dice roll."""
    def __init__(self, result:int=0, verbose_result:str='', crit:int=0, rolled:str='', skeleton:str=''):
        self.plain = result
        self.result = verbose_result
        self.crit = crit
        self.rolled = rolled
        self.skeleton = skeleton
        
    def __str__(self):
        return self.result

class Dice:
    """Dice and math related commands."""
    def __init__(self, bot):
        self.bot = bot
        if os.path.isfile("./res/pbp_channels.json"):
            with open('./res/pbp_channels.json', mode='r', encoding='utf-8') as f:
                self.pbp_channels = json.load(f)
        else:
            self.pbp_channels = {}  # dict with struct: {server: {setting: bool}}
        
    async def on_message(self, message):
        if message.content.startswith('.d20'):
            rollStr = message.content.replace('.', '1').split(' ')[0]
            try:
                rollFor = ' '.join(message.content.split(' ')[1:])
            except:
                rollFor = ''
            adv = 0
            if re.search('(^|\s+)(adv|dis)(\s+|$)', rollFor) is not None:
                adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollFor) is not None else -1
                rollFor = re.sub('(adv|dis)(\s+|$)', '', rollFor)
            out = roll_create(rollStr, adv=adv, rollFor=rollFor, inline=True)
            out = out.result
            try:
                await self.bot.delete_message(message)
            except:
                pass
            await self.bot.send_message(message.channel, message.author.mention + '  ' + out)
                        
    @commands.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(manage_channels=True)
    async def pbp(self, ctx):
        """Toggles the play-by-post state of a channel.
        Usage: .pbp
        Requires: Bot Mod or Manage Channels"""
        try:
            if ctx.message.channel.id in self.pbp_channels[ctx.message.server.id]:
                self.pbp_channels[ctx.message.server.id].remove(ctx.message.channel.id)
                await self.bot.say("Channel PBP mode turned off.")
            else:
                self.pbp_channels[ctx.message.server.id].append(ctx.message.channel.id)
                await self.bot.say("Channel PBP mode turned on.")
        except:
            self.pbp_channels[ctx.message.server.id] = []
            self.pbp_channels[ctx.message.server.id].append(ctx.message.channel.id)
            await self.bot.say("Channel PBP mode turned on.")
            
        with open('./ext/pbp_channels.json', mode='w', encoding='utf-8') as f:
            json.dump(self.pbp_channels, f, sort_keys=True, indent=4)
        
    @commands.command(pass_context=True, name='r')
    async def rollCmd(self, ctx, rollStr, *, rollFor:str=''):
        """Rolls dice in xdy format.
        Usage: .r xdy Attack!
               .r xdy+z adv Attack with Advantage!
               .r xdy-z dis Hide with Heavy Armor!
               .r xdy+xdy*z
               .r XdYkhZ"""
        adv = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', rollFor) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', rollFor) is not None else -1
            rollFor = re.sub('(adv|dis)(\s+|$)', '', rollFor)
        res = roll_create(rollStr, adv=adv, rollFor=rollFor)
        out = res.result
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass
        outStr = ctx.message.author.mention + '  ' + out
        if len(outStr) > 1999:
            await self.bot.say(ctx.message.author.mention + '  :game_die:\n**Result:** ' + str(res.plain))
        else:
            await self.bot.say(outStr)
        
    @commands.command(pass_context=True, name='rrr')
    async def rrr(self, ctx, iterations:int, rollStr, dc:int, *, args=''):
        """Rolls dice in xdy format, given a set dc.
        Usage: .rrr <ITER> <xdy> <DC> [args]"""
        if iterations < 1 or iterations > 500:
            await self.bot.say("Too many or too few iterations.")
        adv = 0
        out = []
        successes = 0
        if re.search('(^|\s+)(adv|dis)(\s+|$)', args) is not None:
            adv = 1 if re.search('(^|\s+)adv(\s+|$)', args) is not None else -1
            args = re.sub('(adv|dis)(\s+|$)', '', args)
        for r in range(iterations):
            res = roll_create(rollStr, adv=adv, rollFor=args, inline=True)
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
    async def math(self, ctx):
        """Solves a math problem.
        Usage: .math <MATH>"""
        await self.e_math(ctx.message)
        
    @commands.command(pass_context=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_ooc(self, ctx):
        """Purges ooc chatter from a pbp channel.
        Usage: .purge_ooc"""
        def ooc_check(m):
            return m.content.startswith("((") and m.content.endswith("))")
        try:
            deleted = await self.bot.purge_from(ctx.message.channel, limit=100, check=ooc_check)
            await self.bot.delete_message(ctx.message)
        except:
            pass
        await self.bot.say("Purged {} OOC messages.".format(len(deleted)), delete_after=10)        
            
    async def e_math(self, message):
        try:
            texpr = message.content.replace('^', '**')
            texpr = texpr.split(' ')
            texpr = texpr[1:]
            texpr = ''.join(texpr)
            texpr = re.split('(\d+d\d+)', texpr)
            for x, y in enumerate(texpr):
                if re.search('\d+d\d+', y):
                    texpr[x] = self.d_roller(y)[0]
            texpr = ''.join(texpr)
            texpr = texpr.replace('_', '').replace('[', '(').replace(']', ')')
            tans = numexpr.evaluate(texpr)
            texpr = texpr.replace('**', '^')
            await self.bot.send_message(message.channel, 'Calculated: `{0}` = `{1}`'.format(texpr, tans))
        except:
            await self.bot.send_message(message.channel, 'Invalid Expression.')
            
    def roll(self, dice, author=None, rolling_for='', inline=False):  # unused old command
        resultTotal = 0 
        resultString = ''
        crit = 0
        args = dice.split(' ')[2:]
        dice = dice.split(' ')[1]
        try:  # check for +/-
            toAdd = int(dice.split('+')[1])
        except Exception:
            toAdd = 0
        try:
            toAdd = int(dice.split('-')[1]) * -1
        except:
            pass
        dice = dice.split('+')[0].split('-')[0]
    
        try:  # grab dice
            numDice = dice.split('d')[0]
            diceVal = dice.split('d')[1]
        except Exception:
            return "Format has to be in .r xdy+z. I don't have a high enough INT to read otherwise."
    
        if numDice == '':  # clean up dice in case of "d20"
            numDice = '1'
            dice = '1' + dice
    
        if int(numDice) > 500:  # make sure we aren't rolling too much
            return "I'm a dragon, not a robot! Roll less dice."
    
        rolls, limit = map(int, dice.split('d'))
    
        for r in range(rolls):
            number = random.randint(1, limit)
            if re.search('(^|\s+)(adv|dis)(\s+|$)', args):
                number2 = random.randint(1, limit)
                if re.search('(^|\s+)adv(\s+|$)', args):
                    number = number if number > number2 else number2
                else:
                    number = number if number < number2 else number2
            resultTotal = resultTotal + number
            
            if number == limit or number == 1:
                numStr = '**' + str(number) + '**'
            else:
                numStr = str(number)
        
            if resultString == '':
                resultString += numStr
            else:
                resultString += ', ' + numStr
    
        if numDice == '1' and diceVal == '20' and resultTotal == 20:
            crit = 1
        elif numDice == '1' and diceVal == '20' and resultTotal == 1:
            crit = 2
        
        rolling_for = rolling_for if rolling_for is not None else "Result"
        rolling_for = re.sub('(adv|dis)(\s+|$)', '', rolling_for)
        if not inline:
            if toAdd:
                resultTotal = resultTotal + toAdd
                resultString = resultString + ' ({:+})'.format(toAdd)
                
            if resultTotal < 1:
                resultString += "\nYou... actually rolled less than a 1. Good job."
            
            if rolling_for is '':
                rolling_for = None
                
            if toAdd == 0 and numDice == '1':
                resultString = author.mention + "  :game_die:\n**{}:** ".format(rolling_for if rolling_for is not None else 'Result') + resultString
            else:
                resultString = author.mention + "  :game_die:\n**{}:** ".format(rolling_for if rolling_for is not None else 'Result') + resultString + "\n**Total:** " + str(resultTotal)
                
            if 'adv' in args:
                resultString += "\n**Rolled with Advantage**"
            elif 'dis' in args:
                resultString += "\n**Rolled with Disadvantage**"
        
            if crit == 1:
                critStr = "\n_**Critical Hit!**_  " + tables.getCritMessage()
                resultString += critStr
            elif crit == 2:
                critStr = "\n_**Critical Fail!**_  " + tables.getFailMessage()
                resultString += critStr
        else:
            if toAdd:
                resultTotal = resultTotal + toAdd
                resultString = resultString + '{:+}'.format(toAdd)
            
            if rolling_for is '':
                rolling_for = None
                
            if toAdd == 0 and numDice == '1':
                resultString = author.mention + "  :game_die:\n**{}:** `".format(rolling_for if rolling_for is not None else 'Result') + resultString + "`"
            else:
                resultString = author.mention + "  :game_die:\n**{}:** `".format(rolling_for if rolling_for is not None else 'Result') + resultString + "` = `" + str(resultTotal) + '`'
                
            if re.search('(^|\s+)adv(\s+|$)', args):
                resultString += "\n**Rolled with Advantage**"
            elif re.search('(^|\s+)dis(\s+|$)', args):
                resultString += "\n**Rolled with Disadvantage**"
        
            if crit == 1:
                critStr = "\n_**Critical Hit!**_  " + tables.getCritMessage()
                resultString += critStr
            elif crit == 2:
                critStr = "\n_**Critical Fail!**_  " + tables.getFailMessage()
                resultString += critStr
            
        return resultString        
    
