'''
Created on Feb 27, 2017

@author: andrew
'''
import re

import discord
import numexpr

from cogs5e.funcs.dice import roll, SingleDiceGroup
from utils.functions import a_or_an


def sheet_attack(attack, args):
    """Returns: a dict with structure {"embed": discord.Embed(), "result": {metadata}}"""
    embed = discord.Embed()
    total_damage = 0
    dnum_keys = [k for k in args.keys() if re.match(r'd\d+', k)] # ['d1', 'd2'...]
    dnum = {}
    for k in dnum_keys: # parse d# args
        for dmg in args[k].split('|'):
            try:
                dnum[dmg] = int(k.split('d')[-1])
            except ValueError:
                embed = discord.Embed()
                embed.title = "Error"
                embed.colour = 0xff0000
                embed.description = "Malformed tag: {}".format(k)
                return {"embed": embed, "total_damage": 0}
        
    if args.get('phrase') is not None: # parse phrase
        embed.description = '*' + args.get('phrase') + '*'
    else:
        embed.description = '~~' + ' '*500 + '~~'
        
    
    if args.get('title') is not None:
        embed.title = args.get('title').replace('[charname]', args.get('name')).replace('[aname]', attack.get('name')).replace('[target]', args.get('t', ''))
    elif args.get('t') is not None: # parse target
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
            
            try:
                parts = len(toHit.raw_dice.parts)
            except:
                parts = 0
            
            if parts > 0:
                out += toHit.result + '\n'
                try:
                    raw = next(p for p in toHit.raw_dice.parts if isinstance(p, SingleDiceGroup) and p.max_value == 20).get_total()
                except StopIteration:
                    raw = 0
                if args.get('crit'):
                    itercrit = args.get('crit', 0)
                elif raw >= (args.get('criton', 20) or 20):
                    itercrit = 1
                else:
                    itercrit = toHit.crit
                if args.get('ac') is not None:
                    if toHit.total < args.get('ac') and itercrit == 0:
                        itercrit = 2 # miss!
            else: # output wherever was there if error
                out += "**To Hit**: " + attack.get('attackBonus') + '\n'
            
        if attack.get('damage') is not None:
            if args.get('d') is not None:
                damage = attack.get('damage') + '+' + args.get('d')
            else:
                damage = attack.get('damage')
                
            for dice, numHits in dnum.items():
                if not itercrit == 2 and numHits > 0:
                    damage += '+' + dice
                    dnum[dice] -= 1
            
            rollFor = "Damage"
            if itercrit == 1:
                def critSub(matchobj):
                    return str(int(matchobj.group(1)) * 2) + 'd' + matchobj.group(2)
                critDice = re.sub(r'(\d+)d(\d+)', critSub, damage)
                if args.get('c') is not None:
                    critDice += '+' + args.get('c', '')
                damage = critDice
                rollFor = "Damage (CRIT!)"
            
            if 'resist' in args or 'immune' in args or 'vuln' in args:
                COMMENT_REGEX = r'\[(?P<comment>.*?)\]'
                ROLL_STRING_REGEX = r'\[.*?]'
                
                comments = re.findall(COMMENT_REGEX, damage)
                roll_strings = re.split(ROLL_STRING_REGEX, damage)
                
                index = 0
                resistances = args.get('resist', '').split('|')
                immunities = args.get('immune', '').split('|')
                vulnerabilities = args.get('vuln', '').split('|')
                
                formatted_comments = []
                formatted_roll_strings = []
                
                t = 0
                for comment in comments:
                    if not roll_strings[t].replace(' ', '') == '':
                        formatted_roll_strings.append(roll_strings[t])
                        formatted_comments.append(comments[t])
                    else:
                        formatted_comments[-1] += ' ' + comments[t]
                    t += 1
                        
                
                for comment in formatted_comments:
                    roll_string = formatted_roll_strings[index].replace(' ', '')
                            
                    preop = ''
                    if roll_string[0] in '-+*/().<>=': # case: +6[blud]
                        preop = roll_string[0]
                        roll_string = roll_string[1:]
                    for resistance in resistances:
                        if resistance.lower() in comment.lower() and len(resistance) > 0:
                            roll_string = '({0}) / 2'.format(roll_string)
                            break
                    for immunity in immunities:
                        if immunity.lower() in comment.lower() and len(immunity) > 0:
                            roll_string = '({0}) * 0'.format(roll_string)
                            break
                    for vulnerability in vulnerabilities:
                        if vulnerability.lower() in comment.lower() and len(vulnerability) > 0:
                            roll_string = '({0}) * 2'.format(roll_string)
                            break
                    formatted_roll_strings[index] = '{0}{1}[{2}]'.format(preop, roll_string, comment)
                    index = index + 1
                if formatted_roll_strings:
                    damage = ''.join(formatted_roll_strings)
            
            if itercrit == 2:
                out += '**Miss!**\n'
            else:
                dmgroll = roll(damage, rollFor=rollFor, inline=True, show_blurbs=False)
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
    
    if args.get('image') is not None:
        embed.set_thumbnail(url=args.get('image'))
        
    return {'embed': embed, 'total_damage': total_damage}