"""
Created on Dec 25, 2016

@author: zhu.exe#4211 (187421759484592128)
"""

import logging
import random
import re
from heapq import nlargest, nsmallest
from math import floor
from re import IGNORECASE

import numexpr

from cogs5e.models import errors

log = logging.getLogger(__name__)

VALID_OPERATORS = 'k|rr|ro|mi|ma|ra|e|p'
VALID_OPERATORS_ARRAY = VALID_OPERATORS.split('|')
VALID_OPERATORS_2 = re.compile('|'.join(["({})".format(i) for i in VALID_OPERATORS_ARRAY]))
DICE_PATTERN = re.compile(
    r'^\s*(?:(?:(\d*d\d+)(?:(?:' + VALID_OPERATORS + r')(?:[lh<>]?\d+))*|(\d+)|([-+*/().=])?)\s*(\[.*\])?)(.*?)\s*$',
    IGNORECASE)
MAX_REROLLS = 1000


def list_get(index, default, l):
    try:
        a = l[index]
    except IndexError:
        a = default
    return a


def old_roll(rollStr, adv: int = 0, rollFor='', inline=False, double=False, show_blurbs=True, **kwargs):
    raise RuntimeError("Make me new roll!")
    roller = Roll()
    result = roller.roll(rollStr, adv, rollFor, inline, double, show_blurbs, **kwargs)
    return result


def get_roll_comment(rollStr):
    """Returns: A two-tuple (dice without comment, comment)"""
    try:
        comment = ''
        no_comment = ''
        dice_set = re.split('([-+*/().=])', rollStr)
        dice_set = [d for d in dice_set if not d in (None, '')]
        log.debug("Found dice set: " + str(dice_set))
        for index, dice in enumerate(dice_set):
            match = DICE_PATTERN.match(dice)
            log.debug("Found dice group: " + str(match.groups()))
            no_comment += dice.replace(match.group(5), '')
            if match.group(5):
                comment = match.group(5) + ''.join(dice_set[index + 1:])
                break

        return no_comment, comment
    except:
        pass
    return rollStr, ''


class Roll(object):
    def __init__(self, parts=None):
        if parts is None:
            parts = []
        self.parts = parts
        self._rerolls = 0

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
    def roll(self, rollStr, adv: int = 0, rollFor='', inline=False, double=False, show_blurbs=True, **kwargs):
        try:
            if '**' in rollStr:
                raise errors.InvalidArgument("Exponents are currently disabled.")
            self.parts = []
            # split roll string into XdYoptsSel [comment] or Op
            # set remainder to comment
            # parse each, returning a SingleDiceResult
            dice_set = re.split('([-+*/().=])', rollStr)
            dice_set = [d for d in dice_set if not d in (None, '')]
            log.debug("Found dice set: " + str(dice_set))
            for index, dice in enumerate(dice_set):
                match = DICE_PATTERN.match(dice)
                log.debug("Found dice group: " + str(match.groups()))
                # check if it's dice
                if match.group(1):
                    roll = self.roll_one(dice.replace(match.group(5), ''), adv)
                    self.parts.append(roll)
                # or a constant
                elif match.group(2):
                    self.parts.append(Constant(value=int(match.group(2)), annotation=match.group(4)))
                # or an operator
                elif not match.group(5):
                    self.parts.append(Operator(op=match.group(3), annotation=match.group(4)))

                if match.group(5):
                    self.parts.append(Comment(match.group(5) + ''.join(dice_set[index + 1:])))
                    break

            # calculate total
            crit = self.get_crit()
            try:
                total = self.get_total()
            except SyntaxError:
                raise errors.InvalidArgument("No dice found to roll.")
            rolled = ' '.join(str(res) for res in self.parts if not isinstance(res, Comment))
            if rollFor is '':
                rollFor = ''.join(str(c) for c in self.parts if isinstance(c, Comment))
            # return final solution
            if not inline:
                # Builds end result while showing rolls
                reply = ' '.join(
                    str(res) for res in self.parts if not isinstance(res, Comment)) + '\n**Total:** ' + str(
                    floor(total))
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
                reply = ' '.join(str(res) for res in self.parts if not isinstance(res, Comment)) + ' = `' + str(
                    floor(total)) + '`'
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
            return DiceResult(result=int(floor(total)), verbose_result=reply, crit=crit, rolled=rolled,
                              skeleton=skeletonReply, raw_dice=self)
        except Exception as ex:
            return DiceResult(verbose_result="Invalid input: {}".format(ex))

    def roll_one(self, dice, adv: int = 0):
        # splits dice and annotation
        split = re.match(r'^([^\[\]]*?)\s*(\[.*\])?\s*$', dice)
        dice = split.group(1).strip()
        annotation = split.group(2)

        # Recognizes dice
        obj = re.findall('\d+', dice)
        obj = [int(x) for x in obj]
        numArgs = len(obj)

        # prepare dice and operators
        ops = []
        if numArgs == 1:
            if not dice.startswith('d'):
                raise errors.InvalidArgument('Please pass in the value of the dice.')
            numDice = 1
            dice_size = obj[0]
            if adv is not 0 and dice_size == 20:
                numDice = 2
                ops = ['k', 'h1'] if adv is 1 else ['k', 'l1']
        elif numArgs == 2:
            numDice = obj[0]
            dice_size = obj[-1]
            if adv is not 0 and dice_size == 20:
                ops = ['k', 'h' + str(numDice)] if adv is 1 else ['k', 'l' + str(numDice)]
                numDice = numDice * 2
        else:  # split into xdy and operators
            numDice = obj[0]
            dice_size = obj[1]
            dice = re.split('(\d+d\d+)', dice)[-1]
            ops = VALID_OPERATORS_2.split(dice)
            ops = [a for a in ops if a is not None]

        # ensure limits
        if numDice > 300 or dice_size < 1:
            raise errors.InvalidArgument('Too many dice rolled.')

        # prepare output
        result = SingleDiceGroup(num_dice=numDice, max_value=dice_size, annotation=annotation or '', operators=ops)

        # roll dice
        for _ in range(numDice):
            try:
                tempdice = SingleDice(value=random.randint(1, dice_size), max_value=dice_size)
                result.rolled.append(tempdice)
            except:  # ?
                result.rolled.append(SingleDice())

        # define operators
        def _op_rr(buf):
            self._rerolls += result.reroll(buf, greedy=True)

        def _op_k(buf):
            result.keep(buf)

        def _op_ro(buf):
            self._rerolls += result.reroll(buf, once=True)

        def _op_ra(buf):
            result.reroll(buf, once=True, keep_rerolled=True, unique=True)

        def _op_e(buf):
            self._rerolls += result.reroll(buf, greedy=True, keep_rerolled=True)

        # run operators
        if ops is not None:
            buffer = list()
            operation = None
            last_operator = None

            for index, op in enumerate(ops):
                if self._rerolls > MAX_REROLLS:
                    raise OverflowError("Tried to reroll too many dice.")

                if operation is not None and op in VALID_OPERATORS_ARRAY and not op == last_operator:
                    operation(buffer)
                    buffer = list()
                    operation = None

                if op == 'rr':
                    buffer += parse_selectors([list_get(index + 1, 0, ops)], result, greedy=True)
                    operation = _op_rr
                elif op == 'k':
                    buffer += parse_selectors([list_get(index + 1, 0, ops)], result)
                    operation = _op_k
                elif op == 'p':
                    buffer += parse_selectors([list_get(index + 1, 0, ops)], result, inverse=True)
                    operation = _op_k
                elif op == 'ro':
                    buffer += parse_selectors([list_get(index + 1, 0, ops)], result)
                    operation = _op_ro
                elif op == 'mi':
                    _min = list_get(index + 1, 0, ops)
                    for r in result.rolled:
                        if r.value < int(_min):
                            r.update(int(_min))
                elif op == 'ma':
                    _max = list_get(index + 1, 0, ops)
                    for r in result.rolled:
                        if r.value > int(_max):
                            r.update(int(_max))
                elif op == 'ra':
                    buffer += parse_selectors([list_get(index + 1, 0, ops)], result)
                    operation = _op_ra
                elif op == 'e':
                    buffer += parse_selectors([list_get(index + 1, 0, ops)], result, greedy=True)
                    operation = _op_e

                if op in VALID_OPERATORS_ARRAY:
                    last_operator = op

            if self._rerolls > MAX_REROLLS:
                raise OverflowError("Tried to reroll too many dice.")
            if operation is not None:
                operation(buffer)

        return result


class Part:
    """Class to hold one part of the roll string."""
    pass


class SingleDiceGroup(Part):
    def __init__(self, num_dice: int = 0, max_value: int = 0, rolled=None, annotation: str = "", result: str = "",
                 operators=None):
        if operators is None:
            operators = []
        if rolled is None:
            rolled = []
        self.num_dice = num_dice
        self.max_value = max_value
        self.rolled = rolled  # list of SingleDice
        self.annotation = annotation
        self.result = result
        self.operators = operators

    def keep(self, rolls_to_keep):
        if rolls_to_keep is None: return
        for _roll in self.rolled:
            if not _roll.value in rolls_to_keep:
                _roll.kept = False
            elif _roll.kept:
                rolls_to_keep.remove(_roll.value)

    def reroll(self, rerollList, max_iterations=1000, greedy=False, keep_rerolled=False, unique=False, once=False):
        if not rerollList:
            return 0  # don't reroll nothing - minor optimization
        if unique:
            rerollList = list(set(rerollList))  # remove duplicates
        if len(rerollList) > 100:
            raise OverflowError("Too many dice to reroll (max 100)")
        last_index = 0
        count = 0
        should_continue = True
        while should_continue:  # let's only iterate 250 times for sanity
            should_continue = False
            if any(d.value in set(rerollList) for d in self.rolled[last_index:] if d.kept and not d.exploded):
                should_continue = True

            to_extend = []
            for r in self.rolled[last_index:]:  # no need to recheck everything
                count += 1
                if count > max_iterations:
                    should_continue = False
                    break

                if r.value in rerollList and r.kept and not r.exploded:
                    try:
                        tempdice = SingleDice(value=random.randint(1, self.max_value), max_value=self.max_value)
                        to_extend.append(tempdice)
                    except:
                        to_extend.append(SingleDice())

                    if not keep_rerolled:
                        r.drop()
                    else:
                        r.explode()

                    if not greedy:
                        rerollList.remove(r.value)

            last_index = len(self.rolled)
            self.rolled.extend(to_extend)

            if once:
                break

        return count

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

    def to_dict(self):
        return {'type': 'dice', 'dice': [d.to_dict() for d in self.rolled], 'annotation': self.annotation,
                'value': self.get_total(), 'is_crit': self.get_crit(), 'num_kept': self.get_num_kept(),
                'text': str(self), 'num_dice': self.num_dice, 'dice_size': self.max_value, 'operators': self.operators}


class SingleDice:
    def __init__(self, value: int = 0, max_value: int = 0, kept: bool = True, exploded: bool = False):
        self.value = value
        self.max_value = max_value
        self.kept = kept
        self.rolls = [value]  # list of ints (for X -> Y -> Z)
        self.exploded = exploded

    def drop(self):
        self.kept = False

    def explode(self):
        self.exploded = True

    def update(self, new_value):
        self.value = new_value
        self.rolls.append(new_value)

    def __str__(self):
        formatted_rolls = [str(r) for r in self.rolls]
        if int(formatted_rolls[-1]) == self.max_value or int(formatted_rolls[-1]) == 1:
            formatted_rolls[-1] = '**' + formatted_rolls[-1] + '**'
        if self.exploded:
            formatted_rolls[-1] = '__' + formatted_rolls[-1] + '__'
        if self.kept:
            return ' -> '.join(formatted_rolls)
        else:
            return '~~' + ' -> '.join(formatted_rolls) + '~~'

    def __repr__(self):
        return "<SingleDice object: value={0.value}, max_value={0.max_value}, kept={0.kept}, rolls={0.rolls}>".format(
            self)

    def to_dict(self):
        return {'type': 'single_dice', 'value': self.value, 'size': self.max_value, 'is_kept': self.kept,
                'rolls': self.rolls, 'exploded': self.exploded}


class Constant(Part):
    def __init__(self, value: int = 0, annotation: str = ""):
        self.value = value
        self.annotation = annotation if annotation is not None else ''

    def __str__(self):
        return "{0.value} {0.annotation}".format(self)

    def get_eval(self):
        return str(self.value)

    def to_dict(self):
        return {'type': 'constant', 'value': self.value, 'annotation': self.annotation}


class Operator(Part):
    def __init__(self, op: str = "+", annotation: str = ""):
        self.op = op if op is not None else ''
        self.annotation = annotation if annotation is not None else ''

    def __str__(self):
        return "{0.op} {0.annotation}".format(self)

    def get_eval(self):
        return self.op

    def to_dict(self):
        return {'type': 'operator', 'value': self.op, 'annotation': self.annotation}


class Comment(Part):
    def __init__(self, comment: str = ""):
        self.comment = comment

    def __str__(self):
        return self.comment.strip()

    def to_dict(self):
        return {'type': 'comment', 'value': self.comment}


def parse_selectors(opts, res, greedy=False, inverse=False):
    """Returns a list of ints."""
    for o in range(len(opts)):
        if opts[o][0] is 'h':
            opts[o] = nlargest(int(opts[o].split('h')[1]), (d.value for d in res.rolled if d.kept))
        elif opts[o][0] is 'l':
            opts[o] = nsmallest(int(opts[o].split('l')[1]), (d.value for d in res.rolled if d.kept))
        elif opts[o][0] is '>':
            if greedy:
                opts[o] = list(range(int(opts[o].split('>')[1]) + 1, res.max_value + 1))
            else:
                opts[o] = [d.value for d in res.rolled if d.value > int(opts[o].split('>')[1])]
        elif opts[o][0] is '<':
            if greedy:
                opts[o] = list(range(1, int(opts[o].split('<')[1])))
            else:
                opts[o] = [d.value for d in res.rolled if d.value < int(opts[o].split('<')[1])]
    out = []
    for o in opts:
        if isinstance(o, list):
            out.extend(int(l) for l in o)
        elif not greedy:
            out.extend(int(o) for a in res.rolled if a.value is int(o) and a.kept)
        else:
            out.append(int(o))

    if not inverse:
        return out

    inverse_out = []
    for rolled in res.rolled:
        if rolled.kept and rolled.value in out:
            out.remove(rolled.value)
        elif rolled.kept:
            inverse_out.append(rolled.value)
    return inverse_out


class DiceResult:
    """Class to hold the output of a dice roll."""

    def __init__(self, result: int = 0, verbose_result: str = '', crit: int = 0, rolled: str = '', skeleton: str = '',
                 raw_dice: Roll = None):
        self.plain = result
        self.total = result
        self.result = verbose_result
        self.crit = crit
        self.rolled = rolled
        self.skeleton = skeleton if skeleton is not '' else verbose_result
        self.raw_dice = raw_dice  # Roll

    def __str__(self):
        return self.result

    def __repr__(self):
        return '<DiceResult object: total={}>'.format(self.total)

    def consolidated(self):
        """Gets the most simplified version of the roll string."""
        if self.raw_dice is None:
            return "0"
        parts = []  # list of (part, annotation)
        last_part = ""
        for p in self.raw_dice.parts:
            if isinstance(p, SingleDiceGroup):
                last_part += str(p.get_total())
            else:
                last_part += str(p)
            if not isinstance(p, Comment) and p.annotation:
                parts.append((last_part, p.annotation))
                last_part = ""
        if last_part:
            parts.append((last_part, ""))

        to_roll = ""
        last_annotation = ""
        out = ""
        for numbers, annotation in parts:
            if annotation and annotation != last_annotation and to_roll:
                out += f"{old_roll(to_roll).total:+} {last_annotation}"
                to_roll = ""
            if annotation:
                last_annotation = annotation
            to_roll += numbers
        if to_roll:
            out += f"{old_roll(to_roll).total:+} {last_annotation}"
        out = out.strip('+ ')
        return out


if __name__ == '__main__':
    while True:
        print(old_roll(input().strip()))
