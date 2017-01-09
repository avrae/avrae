'''
Created on Dec 25, 2016

@author: andrew
'''
from heapq import nlargest, nsmallest
from math import floor
import random
import re
import traceback

import numexpr

from cogs5e import tables
from utils.functions import list_get


# Rolls Dice
def d_roller(obj, adv=0):
    res = []
    splargs = None
    crit = 0
    total = 0
    # Recognizes dice
    args = obj
    obj = re.findall('\d+', obj)
    obj = [int(x) for x in obj]
    numArgs = len(obj)
    if numArgs == 1:
        if not args.startswith('d'):
            raise Exception('Please pass in the value of the dice.')
        numDice = 1
        diceVal = obj[0]
        if adv is not 0:
            numDice = 2
            splargs = ['k', 'h1'] if adv is 1 else ['k', 'l1']
    elif numArgs == 2:
        numDice = obj[0]
        diceVal = obj[-1]
        if adv is not 0:
            splargs = ['k', 'h' + str(numDice)] if adv is 1 else ['k', 'l' + str(numDice)]
            numDice = numDice * 2
    else: # split into xdy and operators
        numDice = obj[0]
        diceVal = obj[1]
        args = re.split('(\d+d\d+)', args)[-1]
        splargs = re.split('(k)|(rr)|(ro)', args)
        splargs = [a for a in splargs if a is not None]
            
    # dice repair/modification
    if numDice > 300 or diceVal < 1 or numDice == 0:
        raise Exception('Too many dice rolled.')
    
    for die in range(numDice):
        try:
            randres = random.randrange(1, diceVal + 1)
            res.append(randres)
        except:
            res.append(1)
            
    rawRes = list(map(str, res))
    
    if splargs is not None:
        def reroll(rerollList, iterations=250):
            for i in range(iterations): # let's only iterate 250 times for sanity
                breakCheck = True
                for r in rerollList:
                    if r in res:
                        breakCheck = False
                for r in range(len(res)):
                    if res[r] in rerollList:
                        try:
                            randres = random.randint(1, diceVal)
                            res[r] = randres
                            rawRes.append(str(randres))
                        except:
                            res[r] = 1
                            rawRes.append('1')
                if breakCheck:
                    break
            rerollList = []
            
        rerollList = []
        reroll_once = []
        keep = None
        valid_operators = ['rr', 'k', 'ro']
        for a in range(len(splargs)):
            if splargs[a] == 'rr':
                rerollList += parse_selectors([list_get(a + 1, 0, splargs)], res)
            elif splargs[a] in valid_operators:
                reroll(rerollList)
                rerollList = []
            if splargs[a] == 'k':
                keep = [] if keep is None else keep
                keep += parse_selectors([list_get(a + 1, 0, splargs)], res)
            elif splargs[a] in valid_operators:
                res = keep if keep is not None else res
                keep = None
            if splargs[a] == 'ro':
                reroll_once += parse_selectors([list_get(a + 1, 0, splargs)], res)
            elif splargs[a] in valid_operators:
                reroll(reroll_once, 1)
                reroll_once = []
        reroll(reroll_once, 1)
        reroll(rerollList)
        res = keep if keep is not None else res
        
        
    for r in res:
        total += r
        
    # check for crits/crails        
    if numDice == 1 and diceVal == 20 and int(rawRes[0]) == 20:
        crit = 1
    elif numDice == 1 and diceVal == 20 and int(rawRes[0]) == 1:
        crit = 2
    
    res = list(map(str, res))
    for r in range(len(rawRes)):
        if rawRes[len(rawRes) - (r + 1)] in res:
            res.remove(rawRes[len(rawRes) - (r + 1)])
        else:
            rawRes[len(rawRes) - (r + 1)] = '~~' + rawRes[len(rawRes) - (r + 1)] + '~~'
    
    # Returns string of answer
    
    for r in range(0, len(rawRes)):
        if rawRes[r] == '1' or rawRes[r] == str(diceVal):
            rawRes[r] = '_' + rawRes[r] + '_'
    
    # build the output list
    out = DiceResult(total, '(' + ', '.join(rawRes) + ')', crit)
    return out

# # Dice Roller
def roll(rollStr, adv:int=0, rollFor='', inline=False):
    try:
        reply = []
        out_set = []
        crit = 0
        total = 0
        # Parses math/dice terms
        dice_temp = rollStr.replace('^', '**')
        # Splits into sections of ['dice', 'operator', 'dice'...] like ['1d20', '+', '4d6', '+', '5']
        dice_set = re.split('([-+*/^().<>=])', dice_temp)
        out_set = re.split('([-+*/^().<>=])', dice_temp)
        eval_set = re.split('([-+*/^().<>=])', dice_temp)
        
        
        # Replaces dice sets with rolled results
        for i, t in enumerate(dice_set):
            try:
                annotation = re.findall(r'\[.*\]', t)[0]
                t = t.replace(annotation, '')
            except:
                annotation = ''
            if 'd' in t:
                result = d_roller(t, adv)
                out_set[i] = t + " " + result.result + " " + annotation
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
    
def parse_selectors(opts, res):
    for o in range(len(opts)):
        if opts[o][0] is 'h':
            opts[o] = nlargest(int(opts[o].split('h')[1]), res)
        if opts[o][0] is 'l':
            opts[o] = nsmallest(int(opts[o].split('l')[1]), res)
    out = []
    for o in opts:
        if isinstance(o, list):
            out += [int(l) for l in o]
        else:
            out += [int(o) for a in res if a is int(o)]
    return out

class DiceResult:
    """Class to hold the output of a dice roll."""
    def __init__(self, result:int=0, verbose_result:str='', crit:int=0, rolled:str='', skeleton:str=''):
        self.plain = result
        self.total = result
        self.result = verbose_result
        self.crit = crit
        self.rolled = rolled
        self.skeleton = skeleton
        
    def __str__(self):
        return self.result