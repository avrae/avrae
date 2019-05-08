"""
Created on Feb 27, 2017

@author: andrew
"""
import copy
import re

import discord

from cogs5e.funcs.dice import SingleDiceGroup, roll
from utils.functions import a_or_an, parse_resistances, format_d20

HIT_DICT = {
    0: "HIT",
    1: "CRIT!",
    2: "MISS"
}


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

    if args.last('image') is not None:
        embed.set_thumbnail(url=args.last('image'))

    adv = args.adv(True)
    crit = args.last('crit', None, bool) and 1
    hit = args.last('hit', None, bool) and 1
    miss = (args.last('miss', None, bool) and not hit) and 1
    ac = args.last('ac', type_=int)
    criton = args.last('criton', 20, int)
    rr = min(args.last('rr', 1, int), 25)
    reroll = args.last('reroll', 0, int)
    b = args.join('b', '+')
    h = args.last('h', None, bool)

    if h:
        hidden_embed = copy.copy(embed)
    else:
        hidden_embed = discord.Embed()  # less memory? idek we don't use it anyway

    raw_attacks = []

    for r in range(rr):  # start rolling attacks
        out = ''
        hidden_out = ''
        itercrit = 0
        if attack.get('attackBonus') is None and b:
            attack['attackBonus'] = '0'
        if attack.get('attackBonus') is not None and not (hit or miss):
            iteradv = adv
            for _adv, numHits in advnum.items():
                if numHits > 0:
                    iteradv = 1 if _adv == 'adv' else -1
                    advnum[_adv] -= 1

            formatted_d20 = format_d20(iteradv, reroll)

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
                if ac:
                    hidden_out += f"**To Hit**: {formatted_d20}... = `{HIT_DICT[itercrit]}`\n"
                else:
                    hidden_out += f"**To Hit**: {formatted_d20}... = `{toHit.total}`\n"
            else:  # output wherever was there if error
                out += "**To Hit**: " + attack.get('attackBonus') + '\n'
                hidden_out += "**To Hit**: Unknown"
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
        if res['roll']:
            hidden_out += f"**Damage**: {res['roll'].consolidated()} = `{res['roll'].total}`"
        else:
            hidden_out += res['damage']
        total_damage += res['total']

        raw_attacks.append({'damage': res['total'], 'crit': itercrit})

        if out is not '':
            if rr > 1:
                embed.add_field(name='Attack {}'.format(r + 1), value=out, inline=False)
                hidden_embed.add_field(name='Attack {}'.format(r + 1), value=hidden_out, inline=False)
            else:
                embed.add_field(name='Attack', value=out, inline=False)
                hidden_embed.add_field(name='Attack', value=hidden_out, inline=False)

    if rr > 1 and attack.get('damage') is not None:
        embed.add_field(name='Total Damage', value=str(total_damage))
        hidden_embed.add_field(name='Total Damage', value=str(total_damage))

    if attack.get('details'):
        embed.add_field(name='Effect',
                        value=attack['details'] if len(attack['details']) < 1020 else f"{attack['details'][:1020]}...")

    out = {'embed': embed, 'total_damage': total_damage, 'full_embed': embed, 'raw_attacks': raw_attacks}
    if h:
        out['embed'] = hidden_embed
    return out


def sheet_damage(damage_str, args, itercrit=0, dnum=None):
    total_damage = 0
    out = ""
    if dnum is None:
        dnum = {}

    d = args.join('d', '+')
    c = args.join('c', '+')
    critdice = args.last('critdice', 0, int)
    showmiss = args.last('showmiss', False, bool)
    resist = args.get('resist')
    immune = args.get('immune')
    vuln = args.get('vuln')
    neutral = args.get('neutral')
    maxdmg = args.last('max', None, bool)
    mi = args.last('mi', None, int)

    if damage_str is None and d:
        damage_str = '0'
    dmgroll = None
    if damage_str is not None:

        def parsecrit(damage_str, wep=False):
            if itercrit == 1:
                def critSub(matchobj):
                    extracritdice = critdice if critdice and wep else 0
                    return f"{int(matchobj.group(1)) * 2 + extracritdice}d{matchobj.group(2)}"

                critDice = re.sub(r'(\d+)d(\d+)', critSub, damage_str)
            else:
                critDice = damage_str
            return critDice

        if mi:
            damage_str = re.sub(r'(\d+d\d+)', rf'\1mi{mi}', damage_str)

        # -d, -d# parsing
        if d:
            damage = parsecrit(damage_str, wep=True) + '+' + parsecrit(d)
        else:
            damage = parsecrit(damage_str, wep=True)

        for dice, numHits in dnum.items():
            if not itercrit == 2 and numHits > 0:
                damage += '+' + parsecrit(dice)
                dnum[dice] -= 1

        if maxdmg:
            def maxSub(matchobj):
                return f"{matchobj.group(1)}d{matchobj.group(2)}mi{matchobj.group(2)}"

            damage = re.sub(r'(\d+)d(\d+)', maxSub, damage)

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
    return {'damage': out, 'total': total_damage, 'roll': dmgroll}
