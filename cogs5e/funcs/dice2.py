'''
Created on Dec 25, 2016

@author: andrew
'''

from heapq import nlargest, nsmallest
import random
from re import IGNORECASE
import re
import traceback

from utils.functions import list_get


VALID_OPERATORS = 'k|rr|ro|mi|ma'
VALID_OPERATORS_2 = '|'.join(["({})".format(i) for i in VALID_OPERATORS.split('|')])
VALID_OPERATORS_ARRAY = VALID_OPERATORS.split('|')
DICE_PATTERN = r'^\s*(?:(?:(?:(\d+d\d+)(?:(?:' + VALID_OPERATORS + r')(?:\d+|l\d+|h\d+))*|(\d+))\s*?(\[.*\])?)|(?:[-+*/().<>=])?)\s*$'

# # Dice Roller
def roll(rollStr, adv:int=0, rollFor='', inline=False, double=False, show_blurbs=True):
    try:
        if '**' in rollStr:
            raise Exception("Exponents are currently disabled.")
        results = []
        # split roll string into XdYoptsSel [comment] or Op
        dice_set = re.split('([-+*/().<>=])', rollStr)
        for index, dice in enumerate(dice_set):
            match = re.match(DICE_PATTERN, dice, IGNORECASE)
            if match:
                # check if it's dice
                if match.group(1):
                    roll = roll_one(dice, adv)
                    results.append(roll)
                # or a constant
                elif match.group(2):
                    results.append(Constant(value=int(match.group(2)), annotation=match.group(3)))
                # or an operator
                else:
                    results.append(Operator(op=match.group(0)))
            else:
                results.append(Comment(''.join(dice_set[index:])))
        # set remainder to comment
        # parse each, returning a SingleDiceResult
        # return final solution
    except Exception as ex:
        print('Error in roll():')
        traceback.print_exc()
        return DiceResult(verbose_result="Invalid input: {}".format(ex))
    
def roll_one(dice, adv:int=0):
    result = SingleDiceGroup()
    # splits dice and comments
    split = re.match(r'^([^\[\]]*?)\s*(\[.*\])?\s*$', dice)
    dice = split.group(1)
    annotation = split.group(2)
    result.annotation = annotation
    # Recognizes dice
    obj = re.findall('\d+', dice)
    obj = [int(x) for x in obj]
    numArgs = len(obj)
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
    
    for die in range(numDice):
        try:
            tempdice = SingleDice()
            tempdice.value = random.randint(1, diceVal)
            tempdice.max_value = diceVal
            result.rolled.append(tempdice)
        except:
            result.rolled.append(SingleDice())
            
    if ops is not None:
        def reroll(rerollList, iterations=250):
            for i in range(iterations): # let's only iterate 250 times for sanity
                breakCheck = True
                for r in rerollList:
                    if r in (d.value for d in result.rolled):
                        breakCheck = False
                for i, r in enumerate(result.rolled):
                    if r in rerollList:
                        try:
                            tempdice = SingleDice()
                            tempdice.value = random.randint(1, diceVal)
                            tempdice.max_value = diceVal
                            result.rolled.append(tempdice)
                            r.drop()
                        except:
                            result.rolled.append(SingleDice())
                            r.drop()
                if breakCheck:
                    break
            rerollList = []
            
        rerollList = []
        reroll_once = []
        keep = None
        valid_operators = VALID_OPERATORS_ARRAY
        for index, op in enumerate(ops):
            if op == 'rr':
                rerollList += parse_selectors([list_get(index + 1, 0, ops)], result)
            elif op in valid_operators:
                reroll(rerollList)
                rerollList = []
            if op == 'k':
                keep = [] if keep is None else keep
                keep += parse_selectors([list_get(a + 1, 0, ops)], result)
            elif op in valid_operators:
                result.keep(keep)
                keep = None
            if op == 'ro':
                reroll_once += parse_selectors([list_get(a + 1, 0, ops)], result)
            elif op in valid_operators:
                reroll(reroll_once, 1)
                reroll_once = []
            if op == 'mi':
                _min = list_get(a + 1, 0, ops)
                for r in result.rolled:
                    if r.value < int(_min): 
                        r.update(_min)
            if op == 'ma':
                _max = list_get(a + 1, 0, ops)
                for r in result.rolled:
                    if r.value > int(_max): 
                        r.update(_max)
        reroll(reroll_once, 1)
        reroll(rerollList)
        result.keep(keep)

class Part:
    """Class to hold one part of the roll string."""
    pass

class SingleDiceGroup(Part):
    def __init__(self, total:int=0, num_dice:int=0, max_value:int=0, rolled:list=[], annotation:str="", result:str="", operators:list=[]):
        self.total = total
        self.num_dice = num_dice
        self.max_value = max_value
        self.rolled = rolled # list of SingleDice
        self.annotation = annotation
        self.result = result
        self.operators = operators
        
    def keep(self, rolls_to_keep:list): # TODO
        for roll in self.rolled:
            if not roll.value in rolls_to_keep:
                roll.kept = False
                
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
        
class Constant(Part):
    def __init__(self, value:int=0, annotation:str=""):
        self.value = value
        self.annotation = annotation

class Operator(Part):
    def __init__(self, op:str="+"):
        self.op = op

class Comment(Part):
    def __init__(self, comment:str=""):
        self.comment = comment

def parse_selectors(opts, res):
    """Returns a list of ints."""
    for o in range(len(opts)):
        if opts[o][0] is 'h':
            opts[o] = nlargest(int(opts[o].split('h')[1]), (d.value for d in res))
        if opts[o][0] is 'l':
            opts[o] = nsmallest(int(opts[o].split('l')[1]), (d.value for d in res))
    out = []
    for o in opts:
        if isinstance(o, list):
            out += [int(l) for l in o]
        else:
            out += [int(o) for a in res if a is int(o)]
    return out

class DiceResult:
    """Class to hold the output of a dice roll."""
    def __init__(self, result:int=0, verbose_result:str='', crit:int=0, rolled:str='', skeleton:str='', raw_dice:list=[]):
        self.plain = result
        self.total = result
        self.result = verbose_result
        self.crit = crit
        self.rolled = rolled
        self.skeleton = skeleton if skeleton is not '' else verbose_result
        self.raw_dice = raw_dice # list of Part
        
    def __str__(self):
        return self.result
    
    def __repr__(self):
        return '<DiceResult object: total={}>'.format(self.total)
