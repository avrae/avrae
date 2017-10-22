"""
Created on Feb 27, 2017

@author: andrew
"""
import re

import discord

from cogs5e.funcs.dice import roll, SingleDiceGroup
from utils.functions import a_or_an, parse_resistances


def sheet_attack(attack, args, embed=None):
    """@:param embed (discord.Embed) if supplied, will use as base. If None, will create one.
    @:returns a dict with structure {"embed": discord.Embed(), "result": {metadata}}"""
    #print(args)
    if embed is None:
        embed = discord.Embed()
    total_damage = 0
    dnum_keys = [k for k in args.keys() if re.match(r'd\d+', k)] # ['d1', 'd2'...]
    dnum = {}
    for k in dnum_keys: # parse d# args
        for dmg in args[k].split('|'):
            try:
                dnum[dmg] = int(k.split('d')[-1])
            except ValueError:
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
        if attack.get('attackBonus') is None and args.get('b') is not None:
            attack['attackBonus'] = '0'
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

        if attack.get('damage') is None and args.get('d') is not None:
            attack['damage'] = '0'
        if attack.get('damage') is not None:

            def parsecrit(damage_str, wep=False):
                if itercrit == 1:
                    if args.get('crittype') == '2x':
                        critDice = f"({damage_str})*2"
                        if args.get('c') is not None:
                            critDice += '+' + args.get('c', '')
                    else:
                        def critSub(matchobj):
                            hocrit = 1 if args.get('hocrit') and wep else 0
                            return str(int(matchobj.group(1)) * 2 + hocrit) + 'd' + matchobj.group(2)
                        critDice = re.sub(r'(\d+)d(\d+)', critSub, damage_str)
                else: critDice = damage_str
                return critDice

            # -d, -d# parsing
            if args.get('d') is not None:
                damage = parsecrit(attack.get('damage'), wep=True) + '+' + parsecrit(args.get('d'))
            else:
                damage = parsecrit(attack.get('damage'), wep=True)

            for dice, numHits in dnum.items():
                if not itercrit == 2 and numHits > 0:
                    damage += '+' + parsecrit(dice)
                    dnum[dice] -= 1

            # crit parsing
            rollFor = "Damage"
            if itercrit == 1:
                if args.get('c') is not None:
                    damage += '+' + args.get('c', '')
                rollFor = "Damage (CRIT!)"

            # resist parsing
            if 'resist' in args or 'immune' in args or 'vuln' in args:
                resistances = args.get('resist', '').split('|')
                immunities = args.get('immune', '').split('|')
                vulnerabilities = args.get('vuln', '').split('|')
                damage = parse_resistances(damage, resistances, immunities, vulnerabilities)

            # actual roll
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

def spell_context(spell):
    """:returns str - Spell context."""
    context = ""

    if spell['type'] == 'save':  # context!
        if isinstance(spell['text'], list):
            text = '\n'.join(spell['text'])
        else:
            text = spell['text']
        sentences = text.split('.')

        for i, s in enumerate(sentences):
            if spell.get('save', {}).get('save').lower() + " saving throw" in s.lower():
                _sent = []
                for sentence in sentences[i:i+3]:
                    if not '\n\n' in sentence:
                        _sent.append(sentence)
                    else:
                        break
                _ctx = '. '.join(_sent)
                if not _ctx.strip() in context:
                    context += f'{_ctx.strip()}.\n'
    elif spell['type'] == 'attack':
        if isinstance(spell['text'], list):
            text = '\n'.join(spell['text'])
        else:
            text = spell['text']
        sentences = text.split('.')

        for i, s in enumerate(sentences):
            if " spell attack" in s.lower():
                _sent = []
                for sentence in sentences[i:i+3]:
                    if not '\n\n' in sentence:
                        _sent.append(sentence)
                    else:
                        break
                _ctx = '. '.join(_sent)
                if not _ctx.strip() in context:
                    context += f'{_ctx.strip()}.\n'
    else:
        if 'short' in spell:
            context = spell['short']

    return context