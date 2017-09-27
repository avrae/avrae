"""
Created on Dec 25, 2016

@author: andrew
"""
from heapq import nlargest, nsmallest
from math import floor
import random
from re import IGNORECASE
import re
import traceback

import numexpr

from cogs5e import tables
from utils.functions import list_get

VALID_OPERATORS = 'k|rr|ro|mi|ma'
VALID_OPERATORS_2 = '|'.join(["({})".format(i) for i in VALID_OPERATORS.split('|')])
VALID_OPERATORS_ARRAY = VALID_OPERATORS.split('|')

# Rolls Dice
def d_roller(obj, adv=0, double=False):
    if double:
        def critSub(matchobj):
            return str(int(matchobj.group(1)) * 2) + 'd' + matchobj.group(2)
        obj = re.sub(r'(\d+)d(\d+)', critSub, obj)
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
        if adv is not 0 and diceVal == 20:
            numDice = 2
            splargs = ['k', 'h1'] if adv is 1 else ['k', 'l1']
    elif numArgs == 2:
        numDice = obj[0]
        diceVal = obj[-1]
        if adv is not 0 and diceVal == 20:
            splargs = ['k', 'h' + str(numDice)] if adv is 1 else ['k', 'l' + str(numDice)]
            numDice = numDice * 2
    else: # split into xdy and operators
        numDice = obj[0]
        diceVal = obj[1]
        args = re.split('(\d+d\d+)', args)[-1]
        splargs = re.split(VALID_OPERATORS_2, args)
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
            
    if adv is not 0 and diceVal == 20:
        numDice = floor(numDice / 2) # for crit detection
            
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
        valid_operators = VALID_OPERATORS_ARRAY
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
            if splargs[a] == 'mi':
                min = list_get(a + 1, 0, splargs)
                for i, r in enumerate(res):
                    if r < int(min): 
                        try:
                            rawRes[rawRes.index(str(r))] = "{} -> _{}_".format(r, min)
                        except: pass
                        res[i] = int(min)
            if splargs[a] == 'ma':
                max = list_get(a + 1, 0, splargs)
                for i, r in enumerate(res):
                    if r > int(max): 
                        try:
                            rawRes[rawRes.index(str(r))] = "{} -> _{}_".format(r, max)
                        except: pass
                        res[i] = int(max)
        reroll(reroll_once, 1)
        reroll(rerollList)
        res = keep if keep is not None else res
        
        
    for r in res:
        total += r
        
    # check for crits/crails        
    if numDice == 1 and diceVal == 20 and total == 20:
        crit = 1
    elif numDice == 1 and diceVal == 20 and total == 1:
        crit = 2
    
    res = list(map(str, res))
    for r in range(len(rawRes)):
        toCompare = rawRes[len(rawRes) - (r + 1)]
        index = len(rawRes) - (r + 1)
        if '->' in toCompare: toCompare = toCompare.split('_')[-2]
        if toCompare in res:
            res.remove(toCompare)
        else:
            rawRes[index] = '~~' + rawRes[index] + '~~'
    
    # Returns string of answer
    
    for r in range(0, len(rawRes)):
        if rawRes[r] == '1' or rawRes[r] == str(diceVal):
            rawRes[r] = '_' + rawRes[r] + '_'
    
    # build the output list
    out = DiceResult(total, '(' + ', '.join(rawRes) + ')', crit)
    return out

# # Dice Roller
def roll(rollStr, adv:int=0, rollFor='', inline=False, double=False, show_blurbs=True):
    try:
        reply = []
        out_set = []
        crit = 0
        total = 0
        # Parses math/dice terms
        #dice_temp = rollStr.replace('^', '**')
        if '**' in rollStr:
            raise Exception("Exponents are currently disabled.")
        dice_temp = rollStr
        # Splits into sections of ['dice', 'operator', 'dice'...] like ['1d20', '+', '4d6', '+', '5']
        dice_set = re.split('([-+*/().<>= ])', dice_temp)
        out_set = re.split('([-+*/().<>= ])', dice_temp)
        eval_set = re.split('([-+*/().<>= ])', dice_temp)
#         print("Dice Set is: " + str(dice_set))
        
        # Replaces dice sets with rolled results
        stack = []
        nextAnno = ''
        rollForTemp = ''
        for i, t in enumerate(dice_set):
        #             print("Processing a t: " + t)
        #             print("Stack: " + str(stack))
        #             print("NextAnno: " + nextAnno)
            breakCheck = False
            if t is '':
                continue
            
            if not 'annotation' in stack:
                try: # t looks like: " 1d20[annotation] words"
                    nextAnno = re.findall(r'\[.*\]', t)[0] # finds any annotation encosed by brackets
                    t = t.replace(nextAnno, '') # and removes it from the string
                except:
                    nextAnno = '' # no annotation
                if '[' in t:
                    stack.append('annotation')
                    nextAnno += t 
                    out_set[i] = ''
                    eval_set[i] = ''
                    continue
            if ']' in t:
                if 'annotation' in stack:
                    t = nextAnno + t
                    nextAnno = re.findall(r'\[.*\]', t)[0] # finds any annotation encosed by brackets
                    t = t.replace(nextAnno, '') # and removes it from the string
                    stack.remove('annotation')
            if 'annotation' in stack:
                nextAnno += t 
                out_set[i] = ''
                eval_set[i] = ''
                continue
            
            if re.search('^\s*((\d*(d|' + VALID_OPERATORS + '|padellis)?(h\d|l\d|\d)+)+|([-+*/^().<>= ]))?(\[.*\])?\s*$', t, flags=IGNORECASE):
                if 'd' in t:
                    try:
                        result = d_roller(t, adv, double=double)
                        out_set[i] = t + " " + result.result + " " + nextAnno if nextAnno is not '' else t + " " + result.result
                        eval_set[i] = str(result.plain)
                        if not result.crit == 0:
                            crit = result.crit
                    except Exception as e:
                        out_set[i] = t + " (ERROR: {}) ".format(str(e)) + nextAnno if nextAnno is not '' else t + " (ERROR: {})".format(str(e))
                        eval_set[i] = "0"
                else:
                    out_set[i] = t + " " + nextAnno if nextAnno is not '' else t
                    eval_set[i] = t
                nextAnno = ''
            else:
                rollForTemp = ''.join(dice_set[i:]) # that means the rest of the string isn't part of the roll
                rollForTemp = re.sub('(^\s+|\s+$)', '', rollForTemp) # get rid of starting/trailing whitespace
                breakCheck = True
                
            if breakCheck:
                out_set = out_set[:i]
                eval_set = eval_set[:i]
                break
 
#         print("Out Set is: " + str(out_set))
#         print("Eval Set is: " + str(eval_set))
        total = ''.join(eval_set)
        try:
            total = numexpr.evaluate(total)
        except SyntaxError:
            total = 0
            return DiceResult(verbose_result="Invalid input: Nothing rolled or missing argument after operator.")
        
        rolled = ''.join(out_set).replace('**', '^').replace('_', '**')
        totalStr = str(floor(total))
        
        if rollFor is '':
            rollFor = rollForTemp if rollForTemp is not '' else rollFor
        
        skeletonReply = ''
        if not inline:
            # Builds end result while showing rolls
            reply.append(' '.join(out_set) + '\n_Total:_ ' + str(floor(total)))
            # Replies to user with message
            reply = '\n\n'.join(reply).replace('**', '^').replace('_', '**')
            skeletonReply = reply
            rollFor = rollFor if rollFor is not '' else 'Result'
            reply = '**{}:** '.format(rollFor) + reply
            if show_blurbs:
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
            reply = '**{}:** '.format(rollFor) + reply
            if show_blurbs:
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
        reply = re.sub(' +', ' ', reply)
        skeletonReply = re.sub(' +', ' ', str(skeletonReply))
        return DiceResult(result=floor(total), verbose_result=reply, crit=crit, rolled=rolled, skeleton=skeletonReply)
        
    except Exception as ex:
        print('Error in roll():')
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
        self.skeleton = skeleton if skeleton is not '' else verbose_result
        
    def __str__(self):
        return self.result
    
    def __repr__(self):
        return '<DiceResult object: total={}>'.format(self.total)
