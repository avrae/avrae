"""
Created on Feb 27, 2017

@author: andrew
"""
import re

import discord

from cogs5e.funcs.dice import roll, SingleDiceGroup
from utils.functions import a_or_an, parse_resistances


def sheet_attack(attack, args, embed=None):
    """
    :param attack: (dict) The attack to roll
    :param args: (dict) Metadata arguments
    :param embed: (discord.Embed) if supplied, will use as base. If None, will create one.
    :returns: a dict with structure {"embed": discord.Embed(), "result": {metadata}}"""
    # print(args)
    if embed is None:
        embed = discord.Embed()

    total_damage = 0

    advnum_keys = [k for k in args if re.match(r'(adv|dis)\d+', k) and args.last(k, type_=bool)]
    advnum = {}
    for k in advnum_keys:  # parse adv# args
        m = re.match(r'(adv|dis)(\d+)', k)
        _adv = m.group(1)
        num = int(m.group(2))
        advnum[_adv] = num

    dnum_keys = [k for k in args if re.match(r'd\d+', k)]  # ['d1', 'd2'...]
    dnum = {}
    for k in dnum_keys:  # parse d# args
        for dmg in args.get(k):
            try:
                dnum[dmg] = int(k.split('d')[-1])
            except ValueError:
                embed.title = "Error"
                embed.colour = 0xff0000
                embed.description = "Malformed tag: {}".format(k)
                return {"embed": embed, "total_damage": 0}

    if args.get('phrase'):  # parse phrase
        embed.description = '*' + args.join('phrase', '\n') + '*'
    else:
        embed.description = '~~' + ' ' * 500 + '~~'

    if args.last('title') is not None:
        embed.title = args.last('title') \
            .replace('[charname]', args.last('name')) \
            .replace('[aname]', attack.get('name')) \
            .replace('[target]', args.last('t', ''))
    elif args.last('t') is not None:  # parse target
        embed.title = '{} attacks with {} at {}!'.format(args.last('name'), a_or_an(attack.get('name')), args.last('t'))
    else:
        embed.title = '{} attacks with {}!'.format(args.last('name'), a_or_an(attack.get('name')))

    adv = args.adv(True)
    crit = args.last('crit', None, bool) and 1
    hit = args.last('hit', None, bool) and 1
    miss = (args.last('miss', None, bool) and not hit) and 1
    ac = args.last('ac', type_=int)
    criton = args.last('criton', 20, int)
    rr = min(args.last('rr', 1, int), 25)
    reroll = args.last('reroll', 0, int)
    b = args.join('b', '+')

    for r in range(rr):  # start rolling attacks
        out = ''
        itercrit = 0
        if attack.get('attackBonus') is None and b:
            attack['attackBonus'] = '0'
        if attack.get('attackBonus') is not None and not (hit or miss):
            iteradv = adv
            for _adv, numHits in advnum.items():
                if numHits > 0:
                    iteradv = 1 if _adv == 'adv' else -1
                    advnum[_adv] -= 1

            formatted_d20 = '1d20'
            if iteradv == 1:
                formatted_d20 = '2d20kh1'
            elif iteradv == 2:
                formatted_d20 = '3d20kh1'
            elif iteradv == -1:
                formatted_d20 = '2d20kl1'

            if reroll:
                formatted_d20 = f"{formatted_d20}ro{reroll}"

            if b:
                toHit = roll(f"{formatted_d20}+{attack.get('attackBonus')}+{b}",
                             rollFor='To Hit', inline=True, show_blurbs=False)
            else:
                toHit = roll(f"{formatted_d20}+{attack.get('attackBonus')}", rollFor='To Hit', inline=True,
                             show_blurbs=False)

            try:
                parts = len(toHit.raw_dice.parts)
            except:
                parts = 0

            if parts > 0:
                out += toHit.result + '\n'
                try:
                    raw = next(p for p in toHit.raw_dice.parts if
                               isinstance(p, SingleDiceGroup) and p.max_value == 20).get_total()
                except StopIteration:
                    raw = 0
                if raw >= criton:
                    itercrit = 1
                else:
                    itercrit = toHit.crit
                if ac is not None:
                    if toHit.total < ac and itercrit == 0:
                        itercrit = 2  # miss!
                if crit and itercrit < 2:
                    itercrit = crit
            else:  # output wherever was there if error
                out += "**To Hit**: " + attack.get('attackBonus') + '\n'
        else:
            if hit:
                out += "**To Hit**: Automatic hit!\n"
            elif miss:
                out += "**To Hit**: Automatic miss!\n"
            if crit:
                itercrit = crit
            else:
                if miss:
                    itercrit = 2
                else:
                    itercrit = 0

        res = sheet_damage(attack.get('damage'), args, itercrit, dnum)
        out += res['damage']
        total_damage += res['total']

        if out is not '':
            if rr > 1:
                embed.add_field(name='Attack {}'.format(r + 1), value=out, inline=False)
            else:
                embed.add_field(name='Attack', value=out, inline=False)

    if rr > 1 and attack.get('damage') is not None:
        embed.add_field(name='Total Damage', value=str(total_damage))

    if attack.get('details'):
        embed.add_field(name='Effect', value=(attack.get('details', '')))

    if args.last('image') is not None:
        embed.set_thumbnail(url=args.last('image'))

    return {'embed': embed, 'total_damage': total_damage}


def sheet_damage(damage_str, args, itercrit=0, dnum=None):
    total_damage = 0
    out = ""
    if dnum is None:
        dnum = {}

    d = args.join('d', '+')
    crittype = args.last('crittype', 'default')
    c = args.join('c', '+')
    critdice = args.last('critdice', 0, int)
    showmiss = args.last('showmiss', False, bool)
    resist = args.get('resist')
    immune = args.get('immune')
    vuln = args.get('vuln')
    neutral = args.get('neutral')
    maxdmg = args.last('max', 0, int)
    
    if damage_str is None and d:
        damage_str = '0'
    if damage_str is not None:

        def parsecrit(damage_str, wep=False):
            if itercrit == 1:
                if crittype == '2x':
                    critDice = f"({damage_str})*2"
                    if c:
                        critDice += '+' + c
                else:
                    def critSub(matchobj):
                        extracritdice = critdice if critdice and wep else 0
                        return str(int(matchobj.group(1)) * 2 + extracritdice) + 'd' + matchobj.group(2)

                    critDice = re.sub(r'(\d+)d(\d+)', critSub, damage_str)
            else:
                critDice = damage_str
            return critDice

        # -d, -d# parsing
        if d:
            damage = parsecrit(damage_str, wep=True) + '+' + parsecrit(d)
        else:
            damage = parsecrit(damage_str, wep=True)

        for dice, numHits in dnum.items():
            if not itercrit == 2 and numHits > 0:
                damage += '+' + parsecrit(dice)
                dnum[dice] -= 1
    
        damage = parsemax(damage, maxdmg)
                
        # crit parsing
        rollFor = "Damage"
        if itercrit == 1:
            if c:
                damage += '+' + c
            rollFor = "Damage (CRIT!)"
        elif itercrit == 2:
            rollFor = "Damage (Miss!)"

        # resist parsing
        damage = parse_resistances(damage, resist, immune, vuln, neutral)

        # actual roll
        if itercrit == 2 and not showmiss:
            out = '**Miss!**\n'
        else:
            dmgroll = roll(damage, rollFor=rollFor, inline=True, show_blurbs=False)
            out = dmgroll.result + '\n'
            if not itercrit == 2:  # if we actually hit
                total_damage += dmgroll.total
    return {'damage': out, 'total': total_damage}

def parsemax(damage_str, maxdmg=0):
    if maxdmg == 0 :
        def maxSub(matchobj):
            return matchobj.group(1) + 'd' + matchobj.group(2) + 'mi' + matchobj.group(2)
        maxDice = re.sub(r'(\d+)d(\d+)', maxSub, damage_str)
    else:
        maxDice = damage_str
    return maxDice
