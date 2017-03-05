'''
Created on Feb 27, 2017

@author: andrew
'''
import re

import discord
import numexpr

from cogs5e.funcs.dice import roll
from utils.functions import a_or_an


def sheet_attack(attack, args):
    """Returns: a dict with structure {"embed": discord.Embed(), "result": {metadata}}"""
    embed = discord.Embed()
    total_damage = 0
    dnum_keys = [k for k in args.keys() if re.match(r'd\d+', k)] # ['d1', 'd2'...]
    dnum = {}
    for k in dnum_keys: # parse d# args
        for dmg in args[k].split('|'):
            dnum[dmg] = int(k.split('d')[-1])
        
    if args.get('phrase') is not None: # parse phrase
        embed.description = '*' + args.get('phrase') + '*'
    else:
        embed.description = '~~' + ' '*500 + '~~'
        
        
    if args.get('t') is not None: # parse target
        embed.title = '{} attacks with {} at {}!'.format(args.get('name'), a_or_an(attack.get('name')), args.get('t'))
    else:
        embed.title = '{} attacks with {}!'.format(args.get('name'), a_or_an(attack.get('name')))
    
    for arg in ('rr', 'ac'): # parse reroll/ac
        try:
            args[arg] = int(args.get(arg, None))
        except (ValueError, TypeError):
            args[arg] = None
    args['adv'] = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
    args['crit'] = 1 if args.get('crit', False) else None
    for r in range(args.get('rr', 1) or 1): # start rolling attacks
        out = ''
        itercrit = 0
        if attack.get('attackBonus') is not None:
            if args.get('b') is not None:
                toHit = roll('1d20+' + attack.get('attackBonus') + '+' + args.get('b'), adv=args.get('adv'), rollFor='To Hit', inline=True, show_blurbs=False)
            else:
                toHit = roll('1d20+' + attack.get('attackBonus'), adv=args.get('adv'), rollFor='To Hit', inline=True, show_blurbs=False)

            out += toHit.result + '\n'
            raw = toHit.total - roll(attack.get('attackBonus') + '+' + (args.get('b') or '0')).total
            if args.get('crit'):
                itercrit = args.get('crit', 0)
            elif raw >= (args.get('criton', 20) or 20):
                itercrit = 1
            else:
                itercrit = toHit.crit
            if args.get('ac') is not None:
                if toHit.total < args.get('ac') and itercrit == 0:
                    itercrit = 2 # miss!
            
        if attack.get('damage') is not None:
            if args.get('d') is not None:
                damage = attack.get('damage') + '+' + args.get('d')
            else:
                damage = attack.get('damage')
                
            for dice, numHits in dnum.items():
                if not itercrit == 2 and numHits > 0:
                    damage += '+' + dice
                    dnum[dice] -= 1
            
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
        
        if out is not '':
            if (args.get('rr', 1) or 1) > 1:
                embed.add_field(name='Attack {}'.format(r+1), value=out, inline=False)
            else:
                embed.add_field(name='Attack', value=out, inline=False)
        
    if (args.get('rr', 1) or 1) > 1 and attack.get('damage') is not None:
        embed.add_field(name='Total Damage', value=str(total_damage))
    
    if attack.get('details') is not None:
        embed.add_field(name='Effect', value=(attack.get('details', '')))
        
    return {'embed': embed, 'total_damage': total_damage}