"""
Created on Dec 25, 2016

@author: andrew
"""

from copy import copy
from heapq import nlargest, nsmallest
import logging
from math import floor
import random
from re import IGNORECASE
import re
import traceback

import numexpr


log = logging.getLogger(__name__)

VALID_OPERATORS = 'k|rr|ro|mi|ma'
VALID_OPERATORS_2 = '|'.join(["({})".format(i) for i in VALID_OPERATORS.split('|')])
VALID_OPERATORS_ARRAY = VALID_OPERATORS.split('|')
DICE_PATTERN = r'^\s*(?:(?:(\d*d\d+)(?:(?:' + VALID_OPERATORS + r')(?:\d+|l\d+|h\d+))*|(\d+)|([-+*/().<>=])?)\s*(\[.*\])?)(.*?)\s*$'

def list_get(index, default, l):
    try:
        a = l[index]
    except IndexError:
        a = default
    return a

def roll(rollStr, adv:int=0, rollFor='', inline=False, double=False, show_blurbs=True, **kwargs):
    roller = Roll()
    result = roller.roll(rollStr, adv, rollFor, inline, double, show_blurbs, **kwargs)
    return result

def get_roll_comment(rollStr):
    """Returns: A two-tuple (dice without comment, comment)"""
    try:
        comment = ''
        no_comment = ''
        dice_set = re.split('([-+*/().<>=])', rollStr)
        dice_set = [d for d in dice_set if not d in (None, '')]
        log.debug("Found dice set: " + str(dice_set))
        for index, dice in enumerate(dice_set):
            match = re.match(DICE_PATTERN, dice, IGNORECASE)
            log.debug("Found dice group: " + str(match.groups()))
            no_comment += dice.replace(match.group(5), '')
            if match.group(5):
                comment = match.group(5) + ''.join(dice_set[index+1:])
                break
                
        return (no_comment, comment)
    except:
        pass
    return (rollStr, '')

class Roll(object):
    def __init__(self, parts:list=[]):
        self.parts = parts
        
    def get_crit(self):
        """Returns: 0 for no crit, 1 for 20, 2 for 1."""
        try:
            crit = next(p.get_crit() for p in self.parts if isinstance(p, SingleDiceGroup))
        except StopIteration:
            crit = 0
        return crit
            
    def get_total(self):
        """Returns: int"""
        return numexpr.evaluate(''.join(p.get_eval() for p in self.parts if not isinstance(p, Comment)))
    
    # # Dice Roller
    def roll(self, rollStr, adv:int=0, rollFor='', inline=False, double=False, show_blurbs=True, **kwargs):
        try:
            if '**' in rollStr:
                raise Exception("Exponents are currently disabled.")
            results = self
            results.parts = []
            # split roll string into XdYoptsSel [comment] or Op
            # set remainder to comment
            # parse each, returning a SingleDiceResult
            dice_set = re.split('([-+*/().<>=])', rollStr)
            dice_set = [d for d in dice_set if not d in (None, '')]
            log.debug("Found dice set: " + str(dice_set))
            for index, dice in enumerate(dice_set):
                match = re.match(DICE_PATTERN, dice, IGNORECASE)
                log.debug("Found dice group: " + str(match.groups()))
                # check if it's dice
                if match.group(1):
                    roll = self.roll_one(dice.replace(match.group(5), ''), adv)
                    results.parts.append(roll)
                # or a constant
                elif match.group(2):
                    results.parts.append(Constant(value=int(match.group(2)), annotation=match.group(4)))
                # or an operator
                else:
                    results.parts.append(Operator(op=match.group(3), annotation=match.group(4)))
                    
                if match.group(5):
                    results.parts.append(Comment(match.group(5) + ''.join(dice_set[index+1:])))
                    break
            
            # calculate total
            crit = results.get_crit()
            total = results.get_total()
            rolled = ' '.join(str(res) for res in results.parts if not isinstance(res, Comment))
            if rollFor is '':
                rollFor = ''.join(str(c) for c in results.parts if isinstance(c, Comment))
            # return final solution
            skeletonReply = ''
            if not inline:
                # Builds end result while showing rolls
                reply = ' '.join(str(res) for res in results.parts if not isinstance(res, Comment)) + '\n**Total:** ' + str(floor(total))
                skeletonReply = reply
                rollFor = rollFor if rollFor is not '' else 'Result'
                reply = '**{}:** '.format(rollFor) + reply
                if show_blurbs:
                    if adv == 1:
                        reply += '\n**Rolled with Advantage**'
                    elif adv == -1:
                        reply += '\n**Rolled with Disadvantage**'
                    if crit == 1:
                        critStr = "\n_**Critical Hit!**_  "
                        reply += critStr
                    elif crit == 2:
                        critStr = "\n_**Critical Fail!**_  "
                        reply += critStr
            else:
                # Builds end result while showing rolls
                reply = ' '.join(str(res) for res in results.parts if not isinstance(res, Comment)) + ' = `' + str(floor(total)) + '`'
                skeletonReply = reply
                rollFor = rollFor if rollFor is not '' else 'Result'
                reply = '**{}:** '.format(rollFor) + reply
                if show_blurbs:
                    if adv == 1:
                        reply += '\n**Rolled with Advantage**'
                    elif adv == -1:
                        reply += '\n**Rolled with Disadvantage**'
                    if crit == 1:
                        critStr = "\n_**Critical Hit!**_  "
                        reply += critStr
                    elif crit == 2:
                        critStr = "\n_**Critical Fail!**_  "
                        reply += critStr
            reply = re.sub(' +', ' ', reply)
            skeletonReply = re.sub(' +', ' ', str(skeletonReply))
            return DiceResult(result=floor(total), verbose_result=reply, crit=crit, rolled=rolled, skeleton=skeletonReply, raw_dice=results)
        except Exception as ex:
            if not isinstance(ex, (SyntaxError, KeyError)):
                log.error('Error in roll() caused by roll {}:'.format(rollStr))
                traceback.print_exc()
            return DiceResult(verbose_result="Invalid input: {}".format(ex))
        
    def roll_one(self, dice, adv:int=0):
        result = SingleDiceGroup()
        result.rolled = []
        # splits dice and comments
        split = re.match(r'^([^\[\]]*?)\s*(\[.*\])?\s*$', dice)
        dice = split.group(1).strip()
        annotation = split.group(2)
        result.annotation = annotation if annotation is not None else ''
        # Recognizes dice
        obj = re.findall('\d+', dice)
        obj = [int(x) for x in obj]
        numArgs = len(obj)
        
        ops = []
        if numArgs == 1:
            if not dice.startswith('d'):
                raise Exception('Please pass in the value of the dice.')
            numDice = 1
            diceVal = obj[0]
            if adv is not 0 and diceVal == 20:
                numDice = 2
                ops = ['k', 'h1'] if adv is 1 else ['k', 'l1']
        elif numArgs == 2:
            numDice = obj[0]
            diceVal = obj[-1]
            if adv is not 0 and diceVal == 20:
                ops = ['k', 'h' + str(numDice)] if adv is 1 else ['k', 'l' + str(numDice)]
                numDice = numDice * 2
        else: # split into xdy and operators
            numDice = obj[0]
            diceVal = obj[1]
            dice = re.split('(\d+d\d+)', dice)[-1]
            ops = re.split(VALID_OPERATORS_2, dice)
            ops = [a for a in ops if a is not None]
    
        # dice repair/modification
        if numDice > 300 or diceVal < 1 or numDice == 0:
            raise Exception('Too many dice rolled.')
        
        result.max_value = diceVal
        result.num_dice = numDice
        result.operators = ops
        
        for _ in range(numDice):
            try:
                tempdice = SingleDice()
                tempdice.value = random.randint(1, diceVal)
                tempdice.rolls = [tempdice.value]
                tempdice.max_value = diceVal
                tempdice.kept = True
                result.rolled.append(tempdice)
            except:
                result.rolled.append(SingleDice())
                
        if ops is not None:
            
                
            rerollList = []
            reroll_once = []
            keep = None
            valid_operators = VALID_OPERATORS_ARRAY
            for index, op in enumerate(ops):
                if op == 'rr':
                    rerollList += parse_selectors([list_get(index + 1, 0, ops)], result, greedy=True)
                elif op in valid_operators:
                    result.reroll(rerollList)
                    rerollList = []
                if op == 'k':
                    keep = [] if keep is None else keep
                    keep += parse_selectors([list_get(index + 1, 0, ops)], result)
                elif op in valid_operators:
                    result.keep(keep)
                    keep = None
                if op == 'ro':
                    reroll_once += parse_selectors([list_get(index + 1, 0, ops)], result)
                elif op in valid_operators:
                    result.reroll(reroll_once, 1)
                    reroll_once = []
                if op == 'mi':
                    _min = list_get(index + 1, 0, ops)
                    for r in result.rolled:
                        if r.value < int(_min): 
                            r.update(int(_min))
                if op == 'ma':
                    _max = list_get(index + 1, 0, ops)
                    for r in result.rolled:
                        if r.value > int(_max): 
                            r.update(int(_max))
            result.reroll(reroll_once, 1)
            result.reroll(rerollList)
            result.keep(keep)
            
        return result

class Part:
    """Class to hold one part of the roll string."""
    pass

class SingleDiceGroup(Part):
    def __init__(self, num_dice:int=0, max_value:int=0, rolled:list=[], annotation:str="", result:str="", operators:list=[]):
        self.num_dice = num_dice
        self.max_value = max_value
        self.rolled = rolled # list of SingleDice
        self.annotation = annotation
        self.result = result
        self.operators = operators
        
    def keep(self, rolls_to_keep):
        if rolls_to_keep is None: return
        for roll in self.rolled:
            if not roll.value in rolls_to_keep:
                roll.kept = False
            else:
                rolls_to_keep.remove(roll.value)
                
    def reroll(self, rerollList, iterations=250, greedy=False):
        for i in range(iterations): # let's only iterate 250 times for sanity
            temp = copy(rerollList)
            breakCheck = True
            for r in rerollList:
                if r in (d.value for d in self.rolled if d.kept):
                    breakCheck = False
            for r in self.rolled:
                if r.value in temp and r.kept:
                    try:
                        tempdice = SingleDice()
                        tempdice.value = random.randint(1, self.max_value)
                        tempdice.rolls = [tempdice.value]
                        tempdice.max_value = self.max_value
                        tempdice.kept = True
                        self.rolled.append(tempdice)
                        r.drop()
                    except:
                        self.rolled.append(SingleDice())
                        r.drop()
                    if not greedy:
                        temp.remove(r.value)
            if breakCheck:
                break
        rerollList = []
                
    def get_total(self):
        """Returns:
        int - The total value of the dice."""
        return sum(r.value for r in self.rolled if r.kept)
    
    def get_eval(self):
        return str(self.get_total())
    
    def get_num_kept(self):
        return sum(1 for r in self.rolled if r.kept)
    
    def get_crit(self):
        """Returns:
        int - 0 for no crit, 1 for crit, 2 for crit fail."""
        if self.get_num_kept() == 1 and self.max_value == 20:
            if self.get_total() == 20:
                return 1
            elif self.get_total() == 1:
                return 2
        return 0
    
    def __str__(self):
        return "{0.num_dice}d{0.max_value}{1} ({2}) {0.annotation}".format(
                self, ''.join(self.operators), ', '.join(str(r) for r in self.rolled))
                
class SingleDice:
    def __init__(self, value:int=0, max_value:int=0, kept:bool=True):
        self.value = value
        self.max_value = max_value
        self.kept = kept
        self.rolls = [value] # list of ints (for X -> Y -> Z)
        
    def drop(self):
        self.kept = False
        
    def update(self, new_value):
        self.value = new_value
        self.rolls.append(new_value)
        
    def __str__(self):
        formatted_rolls = [str(r) for r in self.rolls]
        if int(formatted_rolls[-1]) == self.max_value or int(formatted_rolls[-1]) == 1:
            formatted_rolls[-1] = '**' + formatted_rolls[-1] + '**'
        if self.kept:
            return ' -> '.join(formatted_rolls)
        else:
            return '~~' + ' -> '.join(formatted_rolls) + '~~'
        
    def __repr__(self):
        return "<SingleDice object: value={0.value}, max_value={0.max_value}, kept={0.kept}, rolls={0.rolls}>".format(self)
        
class Constant(Part):
    def __init__(self, value:int=0, annotation:str=""):
        self.value = value
        self.annotation = annotation if annotation is not None else ''
        
    def __str__(self):
        return "{0.value} {0.annotation}".format(self)
    
    def get_eval(self):
        return str(self.value)

class Operator(Part):
    def __init__(self, op:str="+", annotation:str=""):
        self.op = op if op is not None else ''
        self.annotation = annotation if annotation is not None else ''
        
    def __str__(self):
        return "{0.op} {0.annotation}".format(self)
    
    def get_eval(self):
        return self.op

class Comment(Part):
    def __init__(self, comment:str=""):
        self.comment = comment
        
    def __str__(self):
        return self.comment.strip()

def parse_selectors(opts, res, greedy=False):
    """Returns a list of ints."""
    for o in range(len(opts)):
        if opts[o][0] is 'h':
            opts[o] = nlargest(int(opts[o].split('h')[1]), (d.value for d in res.rolled))
        if opts[o][0] is 'l':
            opts[o] = nsmallest(int(opts[o].split('l')[1]), (d.value for d in res.rolled))
    out = []
    for o in opts:
        if isinstance(o, list):
            out += [int(l) for l in o]
        elif not greedy:
            out += [int(o) for a in res.rolled if a.value is int(o)]
        else:
            out += [int(o)]
    return out

class DiceResult:
    """Class to hold the output of a dice roll."""
    def __init__(self, result:int=0, verbose_result:str='', crit:int=0, rolled:str='', skeleton:str='', raw_dice:Roll=None):
        self.plain = result
        self.total = result
        self.result = verbose_result
        self.crit = crit
        self.rolled = rolled
        self.skeleton = skeleton if skeleton is not '' else verbose_result
        self.raw_dice = raw_dice # Roll
        
    def __str__(self):
        return self.result
    
    def __repr__(self):
        return '<DiceResult object: total={}>'.format(self.total)
