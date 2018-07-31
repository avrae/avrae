"""
Created on Feb 27, 2017

@author: andrew
"""
import copy
import re

import discord

from cogs5e.funcs.dice import roll, SingleDiceGroup
from cogs5e.models.errors import NoSpellDC, NoSpellAB, InvalidSaveType
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

    advnum_keys = [k for k in args.keys() if re.match(r'(adv|dis)\d+', k)]
    advnum = {}
    for k in advnum_keys:  # parse adv# args
        m = re.match(r'(adv|dis)(\d+)', k)
        _adv = m.group(1)
        num = int(m.group(2))
        advnum[_adv] = num

    dnum_keys = [k for k in args.keys() if re.match(r'd\d+', k)]  # ['d1', 'd2'...] TODO should probably move this
    dnum = {}
    for k in dnum_keys:  # parse d# args
        for dmg in args[k].split('|'):
            try:
                dnum[dmg] = int(k.split('d')[-1])
            except ValueError:
                embed.title = "Error"
                embed.colour = 0xff0000
                embed.description = "Malformed tag: {}".format(k)
                return {"embed": embed, "total_damage": 0}

    if args.get('phrase') is not None:  # parse phrase
        embed.description = '*' + args.get('phrase') + '*'
    else:
        embed.description = '~~' + ' ' * 500 + '~~'

    if args.get('title') is not None:
        embed.title = args.get('title').replace('[charname]', args.get('name')).replace('[aname]',
                                                                                        attack.get('name')).replace(
            '[target]', args.get('t', ''))
    elif args.get('t') is not None:  # parse target
        embed.title = '{} attacks with {} at {}!'.format(args.get('name'), a_or_an(attack.get('name')), args.get('t'))
    else:
        embed.title = '{} attacks with {}!'.format(args.get('name'), a_or_an(attack.get('name')))

    for arg in ('rr', 'ac'):  # parse reroll/ac
        try:
            args[arg] = int(args.get(arg, None))
        except (ValueError, TypeError):
            args[arg] = None
    args['adv'] = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                            False) else -1 if args.get(
        'dis', False) else 0
    args['adv'] = 2 if args.get('ea', False) and not args.get('dis', False) else args['adv']
    args['crit'] = 1 if args.get('crit', False) else None
    args['hit'] = 1 if args.get('hit', False) else None
    for r in range(args.get('rr', 1) or 1):  # start rolling attacks
        out = ''
        itercrit = 0
        if attack.get('attackBonus') is None and args.get('b') is not None:
            attack['attackBonus'] = '0'
        if attack.get('attackBonus') is not None and not args.get('hit'):
            adv = args.get('adv')
            for _adv, numHits in advnum.items():
                if numHits > 0:
                    adv = 1 if _adv == 'adv' else -1
                    advnum[_adv] -= 1
            formatted_d20 = ('1d20' if adv == 0 else '2d20' + (
                'kh1' if adv == 1 else 'kl1') if not adv == 2 else '3d20kh1') \
                            + ('ro{}'.format(args.get('reroll', 0))
                               if int(args.get('reroll', 0)) else '')
            if args.get('b') is not None:
                toHit = roll(f'{formatted_d20}+' + attack.get('attackBonus') + '+' + args.get('b'),
                             rollFor='To Hit', inline=True, show_blurbs=False)
            else:
                toHit = roll(f'{formatted_d20}+' + attack.get('attackBonus'), rollFor='To Hit', inline=True,
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
                if raw >= (int(args.get('criton', 20)) or 20):
                    itercrit = 1
                else:
                    itercrit = toHit.crit
                if args.get('ac') is not None:
                    if toHit.total < args.get('ac') and itercrit == 0:
                        itercrit = 2  # miss!
                if args.get('crit') and itercrit < 2:
                    itercrit = args.get('crit', 0)
            else:  # output wherever was there if error
                out += "**To Hit**: " + attack.get('attackBonus') + '\n'
        else:
            if args.get('hit'):
                out += "**To Hit**: Automatic hit!\n"
            if args.get('crit'):
                itercrit = args.get('crit', 0)
            else:
                itercrit = 0

        res = sheet_damage(attack.get('damage'), args, itercrit, dnum)
        out += res['damage']
        total_damage += res['total']

        if out is not '':
            if (args.get('rr', 1) or 1) > 1:
                embed.add_field(name='Attack {}'.format(r + 1), value=out, inline=False)
            else:
                embed.add_field(name='Attack', value=out, inline=False)

    if (args.get('rr', 1) or 1) > 1 and attack.get('damage') is not None:
        embed.add_field(name='Total Damage', value=str(total_damage))

    if attack.get('details') is not None:
        embed.add_field(name='Effect', value=(attack.get('details', '')))

    if args.get('image') is not None:
        embed.set_thumbnail(url=args.get('image'))

    return {'embed': embed, 'total_damage': total_damage}


def sheet_damage(damage_str, args, itercrit=0, dnum=None):
    total_damage = 0
    out = ""
    if dnum is None:
        dnum = {}

    if damage_str is None and args.get('d') is not None:
        damage_str = '0'
    if damage_str is not None:

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
            else:
                critDice = damage_str
            return critDice

        # -d, -d# parsing
        if args.get('d') is not None:
            damage = parsecrit(damage_str, wep=True) + '+' + parsecrit(args.get('d'))
        else:
            damage = parsecrit(damage_str, wep=True)

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
        elif itercrit == 2:
            rollFor = "Damage (Miss!)"

        # resist parsing
        if 'resist' in args or 'immune' in args or 'vuln' in args:
            resistances = args.get('resist', '').split('|')
            immunities = args.get('immune', '').split('|')
            vulnerabilities = args.get('vuln', '').split('|')
            damage = parse_resistances(damage, resistances, immunities, vulnerabilities)

        # actual roll
        if itercrit == 2 and not args.get('showmiss', False):
            out = '**Miss!**\n'
        else:
            dmgroll = roll(damage, rollFor=rollFor, inline=True, show_blurbs=False)
            out = dmgroll.result + '\n'
            if not itercrit == 2:  # if we actually hit
                total_damage += dmgroll.total
    return {'damage': out, 'total': total_damage}


def sheet_cast(spell, args, embed=None):
    if embed is None:
        embed = discord.Embed()

    spell_level = int(spell.get('level', 0))
    spell_type = spell.get('type')  # save, attack, special

    cast_level = int(args.get('l', [spell_level])[-1])
    caster_name = args.get('name', ['Unnamed'])[-1]
    phrase = '\n'.join(args.get('phrase', []))
    dc = args.get('dc', [None])[-1]  # save DC (int)
    save_skill = args.get('save', [None])[-1] or spell.get('save', {}).get('save')  # str, dex, etc (optional)
    caster_level = int(args.get('casterlevel', [1])[-1])  # for cantrip scaling
    d = "+".join(args.get('d', []))
    crittype = args.get('crittype', ['default'])[-1]  # char.get_setting('crittype', 'default')
    spell_ab = sum(int(b) for b in args.get('ab', [0]))
    casting_mod = sum(int(b) for b in args.get('SPELL', [0]))

    total_damage = 0

    upcast_dmg = None
    if not cast_level == spell_level:
        upcast_dmg = spell.get('higher_levels', {}).get(str(cast_level))

    if phrase:  # parse phrase
        embed.description = '*' + phrase + '*'
    else:
        embed.description = '~~' + ' ' * 500 + '~~'

    embed.title = '{} casts {}!'.format(caster_name, spell['name'])

    if spell_type == 'save':  # save spell
        if not dc:
            raise NoSpellDC
        try:
            dc = int(dc)
        except:
            raise NoSpellDC

        try:
            save_skill = next(s for s in ('strengthSave',
                                          'dexteritySave',
                                          'constitutionSave',
                                          'intelligenceSave',
                                          'wisdomSave',
                                          'charismaSave') if save_skill.lower() in s.lower())
        except StopIteration:
            raise InvalidSaveType
        save = spell['save']

        if save['damage'] is None:  # save against effect
            embed.add_field(name="DC", value=str(dc) + "\n{} Save".format(save_skill[:3].upper()))
        else:  # damage spell
            dmg = save['damage'].replace("SPELL", str(casting_mod))

            if spell['level'] == '0' and spell.get('scales', True):
                def lsub(matchobj):
                    level = caster_level
                    if level < 5:
                        levelDice = "1"
                    elif level < 11:
                        levelDice = "2"
                    elif level < 17:
                        levelDice = "3"
                    else:
                        levelDice = "4"
                    return levelDice + 'd' + matchobj.group(2)

                dmg = re.sub(r'(\d+)d(\d+)', lsub, dmg)

            if upcast_dmg:
                dmg = dmg + '+' + upcast_dmg

            if d:
                dmg = dmg + '+' + d

            dmgroll = roll(dmg, rollFor="Damage", inline=True, show_blurbs=False)
            embed.add_field(name="Damage/DC",
                            value=dmgroll.result + "\n**DC:** {}\n{} Save".format(str(dc), save_skill[:3].upper()))
            total_damage = dmgroll.total
    elif spell['type'] == 'attack':  # attack spell
        outargs = copy.copy(args)
        outargs['crittype'] = crittype
        outargs['d'] = d or None
        for _arg, _value in outargs.items():
            if isinstance(_value, list):
                outargs[_arg] = _value[-1]
        attack = copy.copy(spell['atk'])
        attack['attackBonus'] = str(spell_ab)

        if not attack['attackBonus']:
            raise NoSpellAB

        if spell['level'] == '0' and spell.get('scales', True):
            def lsub(matchobj):
                level = caster_level
                if level < 5:
                    levelDice = "1"
                elif level < 11:
                    levelDice = "2"
                elif level < 17:
                    levelDice = "3"
                else:
                    levelDice = "4"
                return levelDice + 'd' + matchobj.group(2)

            attack['damage'] = re.sub(r'(\d+)d(\d+)', lsub, attack['damage'])

        if upcast_dmg:
            attack['damage'] = attack['damage'] + '+' + upcast_dmg

        attack['damage'] = attack['damage'].replace("SPELL", str(casting_mod))

        result = sheet_attack(attack, outargs)
        total_damage = result['total_damage']
        for f in result['embed'].fields:
            embed.add_field(name=f.name, value=f.value, inline=f.inline)
    else:  # special spell (MM/heal)
        outargs = copy.copy(args)  # just make an attack for it
        outargs['d'] = "+".join(args.get('d', [])) or None
        for _arg, _value in outargs.items():
            if isinstance(_value, list):
                outargs[_arg] = _value[-1]
        attack = {"name": spell['name'],
                  "damage": spell.get("damage", "0").replace('SPELL',
                                                             str(casting_mod)),
                  "attackBonus": None}
        if upcast_dmg:
            attack['damage'] = attack['damage'] + '+' + upcast_dmg
        result = sheet_attack(attack, outargs)
        total_damage = result['total_damage']
        for f in result['embed'].fields:
            embed.add_field(name=f.name, value=f.value, inline=f.inline)

    spell_ctx = spell_context(spell)
    if spell_ctx:
        embed.add_field(name='Effect', value=spell_ctx)

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
                for sentence in sentences[i:i + 3]:
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
                for sentence in sentences[i:i + 3]:
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
