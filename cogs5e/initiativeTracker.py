"""
Created on Sep 18, 2016

@author: andrew
"""
import asyncio
import copy
import datetime
import logging
import os
import pickle
import random
import re
import shlex
import traceback
from math import floor
from string import capwords

import discord
from discord.errors import NotFound, Forbidden
from discord.ext import commands

from cogs5e.funcs.dice import roll, SingleDiceGroup
from cogs5e.funcs.lookupFuncs import searchMonsterFull, searchAutoSpellFull, searchCharacterSpellName, \
    searchSpellNameFull
from cogs5e.funcs.sheetFuncs import sheet_attack, spell_context
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from utils.functions import parse_args, \
    fuzzy_search, get_positivity, parse_args_2, \
    parse_args_3, parse_resistances, \
    make_sure_path_exists

log = logging.getLogger(__name__)


class Combat(object):
    def __init__(self, channel: discord.Channel, combatants=[], init: int = 0, init_round: int = 0,
                 summary_message=None, options={}, name=""):
        self.channel = channel
        self.combatants = combatants
        self.sorted_combatants = None
        self.index = None
        self.current = init
        self.round = init_round
        self.summary_message = summary_message
        self.options = options
        self.name = name
        self.currentCombatant = None
        self.dm = None
        self.stats = {}
        self.lastmodified = datetime.datetime.now()

    def get_combatant(self, name, precise=False):
        combatant = None
        allCombatants = []
        for c in self.combatants:
            if isinstance(c, Combatant):
                allCombatants.append(c)
            else:
                for c2 in c.combatants:
                    allCombatants.append(c2)
        try:
            combatant = next(c for c in allCombatants if c.name.lower() == name.lower() and isinstance(c, Combatant))
        except StopIteration:
            try:
                if not precise:
                    combatant = next(
                        c for c in allCombatants if name.lower() in c.name.lower() and isinstance(c, Combatant))
            except StopIteration:
                pass

        return combatant

    def get_combatant_group(self, name):
        group = None
        try:
            group = next(c for c in self.combatants if c.name.lower() == name.lower() and isinstance(c, CombatantGroup))
        except StopIteration:
            try:
                group = next(
                    c for c in self.combatants if name.lower() in c.name.lower() and isinstance(c, CombatantGroup))
            except StopIteration:
                pass
        return group

    def checkGroups(self):
        for c in self.combatants:
            if isinstance(c, CombatantGroup):
                if len(c.combatants) == 0:
                    self.combatants.remove(c)

    def getSummary(self):
        combatants = sorted(self.combatants, key=lambda k: (k.init, k.mod), reverse=True)
        outStr = "```markdown\n{}: {} (round {})\n".format(self.name if self.name is not '' else "Current initiative",
                                                           self.current, self.round)
        outStr += '=' * (len(outStr) - 13)
        outStr += '\n'
        for c in combatants:
            outStr += ("# " if c is self.currentCombatant else "  ") + c.get_short_status() + "\n"
        outStr += "```"
        return outStr

    def sortCombatants(self):
        self.sorted_combatants = sorted(self.combatants, key=lambda k: (k.init, k.mod), reverse=True)
        if self.currentCombatant is not None:
            self.index = self.sorted_combatants.index(self.currentCombatant)

    def getNextCombatant(self):
        if self.index is None: self.index = -1
        if self.sorted_combatants is None:
            self.sortCombatants()
        self.index += 1
        return self.sorted_combatants[self.index]

    async def update_summary(self, bot):
        try:
            msg = await bot.edit_message(self.summary_message, self.getSummary())
        except:
            return
        self.summary_message = msg


class CombatantGroup(object):
    def __init__(self, init: int = 0, name: str = '', author: discord.User = None, notes: str = ''):
        self.init = init
        self.name = name
        self.author = author
        self.notes = notes
        self.mod = 0  # only needed for sorting in Combat, should always be 0
        self.combatants = []

    def __str__(self):
        return self.name

    def get_combatant(self, name):
        combatant = None
        try:
            combatant = next(c for c in self.combatants if c.name.lower() == name.lower())
        except:
            pass
        return combatant

    def get_short_status(self):
        status = "{}: {} ({} combatants)".format(self.init,
                                                 self.name,
                                                 len(self.combatants))
        return status


class Combatant(object):
    def __init__(self, init: int = 0, name: str = '', author: discord.User = None, mod: int = 0, notes: str = '',
                 effects=[], hp: int = None, max_hp: int = None, private: bool = False, group: str = None,
                 ac: int = None):
        self.init = init
        self.name = name
        self.author = author
        self.mod = mod
        self.notes = notes
        self.effects = effects
        self.hp = hp
        self.max_hp = max_hp
        self.ac = ac
        self.private = private
        self.group = group
        self.resist = []
        self.immune = []
        self.vuln = []

    def __str__(self):
        return self.name

    def get_effect(self, name):
        effect = None
        try:
            effect = next(c for c in self.effects if c.name.lower() == name.lower())
        except StopIteration:
            try:
                effect = next(c for c in self.effects if name.lower() in c.name.lower())
            except StopIteration:
                pass
        return effect

    def get_effects(self):
        out = []
        for e in self.effects:
            out.append('{} [{} rds]'.format(e.name, e.remaining if not e.remaining < 0 else '∞'))
        out = ', '.join(out)
        return out

    def get_long_effects(self):
        out = ''
        for e in self.effects:
            edesc = e.name
            if e.remaining >= 0:
                edesc += " [{} rounds]".format(e.remaining)
            if getattr(e, 'effect', None):
                edesc += " ({})".format(e.effect)
            out += '\n* ' + edesc
        return out  # ('\n* ' + '\n* '.join([e.name + (" [{} rounds]".format(e.remaining) if e.remaining >= 0 else '') for e in self.effects])) if len(self.effects) is not 0 else ''

    def get_effects_and_notes(self):
        out = []
        if self.ac is not None and not self.private:
            out.append('AC {}'.format(self.ac))
        for e in self.effects:
            out.append('{} [{} rds]'.format(e.name, e.remaining if not e.remaining < 0 else '∞'))
        if not self.notes == '':
            out.append(self.notes)
        out = ', '.join(out)
        return out

    def get_hp(self, private: bool = False):
        hpStr = ''
        if not self.private or private:
            hpStr = '<{}/{} HP>'.format(self.hp, self.max_hp) if self.max_hp is not None else '<{} HP>'.format(
                self.hp) if self.hp is not None else ''
        elif self.max_hp is not None and self.max_hp > 0:
            ratio = self.hp / self.max_hp
            if ratio >= 1:
                hpStr = "<Healthy>"
            elif 0.5 < ratio < 1:
                hpStr = "<Injured>"
            elif 0.15 < ratio <= 0.5:
                hpStr = "<Bloodied>"
            elif 0 < ratio <= 0.15:
                hpStr = "<Critical>"
            elif ratio <= 0:
                hpStr = "<Dead>"
        return hpStr

    def get_hp_and_ac(self, private: bool = False):
        out = [self.get_hp(private)]
        if self.ac is not None and (not self.private or private):
            out.append("(AC {})".format(self.ac))
        return ' '.join(out)

    def get_resist_string(self, private: bool = False):
        resistStr = ''
        self.resist = [r for r in self.resist if r]  # clean empty resists
        self.immune = [r for r in self.immune if r]  # clean empty resists
        self.vuln = [r for r in self.vuln if r]  # clean empty resists
        if not self.private or private:
            if len(self.resist) > 0:
                resistStr += "\n> Resistances: " + ', '.join(self.resist).title()
            if len(self.immune) > 0:
                resistStr += "\n> Immunities: " + ', '.join(self.immune).title()
            if len(self.vuln) > 0:
                resistStr += "\n> Vulnerabilities: " + ', '.join(self.vuln).title()
        return resistStr

    def get_status(self, private: bool = False):
        csFormat = "{} {} {}{}{}"
        status = csFormat.format(self.name,
                                 self.get_hp_and_ac(private),
                                 self.get_resist_string(private),
                                 '\n# ' + self.notes if self.notes is not '' else '',
                                 self.get_long_effects())
        return status

    def get_short_status(self):
        status = "{}: {} {}({})".format(self.init,
                                        self.name,
                                        self.get_hp() + ' ' if self.get_hp() is not '' else '',
                                        self.get_effects_and_notes())
        return status


class DicecloudCombatant(Combatant):
    def __init__(self, init: int = 0, author: discord.User = None, notes: str = '', effects=[], private: bool = False,
                 group: str = None, sheet=None, character=None):
        self.init = init
        self.name = sheet.get('stats', {}).get('name', 'Unknown')
        self.author = author
        self.mod = sheet.get('skills', {}).get('initiative', 0)
        self.notes = notes
        self.effects = effects
        self.hp = character.get_current_hp()
        self.max_hp = sheet.get('hp')
        self.ac = sheet.get('armor')
        self.private = private
        self.group = group
        self.resist = sheet.get('resist', [])
        self.immune = sheet.get('immune', [])
        self.vuln = sheet.get('vuln', [])
        self.saves = sheet.get('saves', {})
        self.sheet = sheet
        self.id = character.id
        self.auth_id = author.id

    def __str__(self):
        return self.name


class MonsterCombatant(Combatant):
    def __init__(self, name: str = '', init: int = 0, author: discord.User = None, notes: str = '', effects=[],
                 private: bool = True, group: str = None, modifier: int = 0, monster=None, opts={}):
        self.init = init
        self.name = name
        self.author = author
        self.mod = modifier
        self.notes = notes
        self.effects = effects
        self.hp = int(monster['hp'].split(' (')[0])
        self.max_hp = int(monster['hp'].split(' (')[0])
        self.ac = int(monster['ac'].split(' (')[0])
        self.private = private
        self.group = group
        self.resist = monster.get('resist', '').replace(' ', '').split(',')
        self.immune = monster.get('immune', '').replace(' ', '').split(',')
        self.vuln = monster.get('vulnerable', '').replace(' ', '').split(',')

        self.saves = {'strengthSave': floor((int(monster['str']) - 10) / 2),
                      'dexteritySave': floor((int(monster['dex']) - 10) / 2),
                      'constitutionSave': floor((int(monster['con']) - 10) / 2),
                      'intelligenceSave': floor((int(monster['int']) - 10) / 2),
                      'wisdomSave': floor((int(monster['wis']) - 10) / 2),
                      'charismaSave': floor((int(monster['cha']) - 10) / 2)}
        save_overrides = monster.get('save', '').split(', ')
        for s in save_overrides:
            try:
                _type = next(sa for sa in ('strengthSave',
                                           'dexteritySave',
                                           'constitutionSave',
                                           'intelligenceSave',
                                           'wisdomSave',
                                           'charismaSave') if s.split(' ')[0].lower() in sa.lower())
                mod = int(s.split(' ')[1])
                self.saves[_type] = mod
            except:
                pass

        self.monster = monster

        # fix npr and blug/pierc/slash
        if opts.get('npr'):
            for t in (self.resist, self.immune, self.vuln):
                for e in t:
                    for d in ('bludgeoning', 'piercing', 'slashing'):
                        if d in e: t.remove(e)
        for t in (self.resist, self.immune, self.vuln):
            for e in t:
                for d in ('bludgeoning', 'piercing', 'slashing'):
                    if d in e and not d.lower() == e.lower():
                        try:
                            t.remove(e)
                        except ValueError:
                            pass
                        t.append(d)

    def get_status(self, private: bool = False):
        csFormat = "{} {} {}{}{}{}"
        status = csFormat.format(self.name,
                                 self.get_hp_and_ac(private),
                                 self.get_resist_string(private),
                                 '\n# ' + self.notes if self.notes is not '' else '',
                                 self.get_long_effects(),
                                 "\n- This combatant will be automatically removed if they remain below 0 HP." if self.hp <= 0 else "")
        return status

    def __str__(self):
        return self.name


class Effect(object):
    def __init__(self, duration: int = -1, name: str = '', effect: str = '', remaining: int = -1):
        self.name = name
        self.duration = duration
        self.remaining = remaining
        self.effect = effect

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<initiativeTracker.Effect object name={} duration={} remaining={} effect={}>".format(self.name,
                                                                                                     self.duration,
                                                                                                     self.remaining,
                                                                                                     self.effect)


class InitTracker:
    """
    Initiative tracking commands. Use !help init for more details.
    To use, first start combat in a channel by saying "!init begin".
    Then, each combatant should add themselves to the combat with "!init add <MOD> <NAME>".
    To hide a combatant's HP, add them with "!init add <MOD> <NAME> -h".
    Once every combatant is added, each combatant should set their max hp with "!init hp <NAME> max <MAXHP>".
    Then, you can proceed through combat with "!init next".
    Once combat ends, end combat with "!init end".
    For more help, the !help command shows applicable arguments for each command.
    """

    def __init__(self, bot):
        self.bot = bot
        self.combats = []  # structure: array of dicts with structure {channel (Channel/Member), combatants (list of dict, [{init, name, author, mod, notes, effects}]), current (int), round (int)}
        self.bot.loop.create_task(self.panic_load())

    @commands.group(pass_context=True, aliases=['i'], no_pm=True)
    async def init(self, ctx):
        """Commands to help track initiative."""
        if ctx.invoked_subcommand is None:
            await self.bot.say("Incorrect usage. Use !help init for help.")
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @init.command(pass_context=True)
    async def begin(self, ctx, *, args: str = ''):
        """Begins combat in the channel the command is invoked.
        Usage: !init begin <ARGS (opt)>
        Valid Arguments:    -1 (modifies initiative rolls)
                            -dyn (dynamic init; rerolls all initiatives at the start of a round)
                            --name <NAME> (names the combat)"""
        if [c for c in self.combats if c.channel is ctx.message.channel]:
            await self.bot.say("You are already in combat. To end combat, use \"!init end\".")
            return
        options = {}
        name = ''
        args = shlex.split(args.lower())
        if '-1' in args:  # rolls a d100 instead of a d20 and multiplies modifier by 5
            options['d100_init'] = True
        if '-dyn' in args:  # rerolls all inits at the start of each round
            options['dynamic'] = True
        if '--name' in args:
            try:
                a = args[args.index('--name') + 1]
                name = a if a is not None else name
            except IndexError:
                await self.bot.say("You must pass in a name with the --name tag.")
                return
        combat = Combat(channel=ctx.message.channel, combatants=[], init=0, init_round=1, options=options,
                        name=capwords(name))
        self.combats.append(combat)
        summaryMsg = await self.bot.say(combat.getSummary())
        combat.summary_message = summaryMsg
        combat.dm = ctx.message.author
        try:
            await self.bot.pin_message(summaryMsg)
        except:
            pass
        await self.bot.say(
            "Everyone roll for initiative!\nIf you have a character set up with SheetManager: `!init cadd`\nIf it's a 5e monster: `!init madd [monster name]`\nOtherwise: `!init add [modifier] [name]`")

    @init.command(pass_context=True)
    async def add(self, ctx, modifier: int, name: str, *, args: str = ''):
        """Adds a combatant to the initiative order.
        If a character is set up with the SheetManager module, you can use !init dcadd instead.
        If you are adding monsters to combat, you can use !init madd instead.
        Use !help init [dcadd|madd] for more help.
        Valid Arguments:    -h (hides HP)
                            -p (places at given number instead of rolling)
                            --controller <CONTROLLER> (pings a different person on turn)
                            --group <GROUP> (adds the combatant to a group)
                            --hp <HP> (starts with HP)
                            --ac <AC> (sets combatant AC)"""
        private = False
        place = False
        controller = ctx.message.author
        group = None
        hp = None
        ac = None
        args = shlex.split(args)
        args = parse_args_3(args)

        if 'h' in args:
            private = True
        if 'p' in args:
            place = True
        if 'controller' in args:
            try:
                controllerStr = args['controller'][0]
                controllerEscaped = controllerStr.replace('<', '').replace('>', '').replace('@', '').replace('!', '')
                a = ctx.message.server.get_member(controllerEscaped)
                b = ctx.message.server.get_member_named(controllerStr)
                controller = a if a is not None else b if b is not None else controller
            except IndexError:
                await self.bot.say("You must pass in a controller with the --controller tag.")
                return
        if 'group' in args:
            try:
                group = args['group'][0]
            except IndexError:
                await self.bot.say("You must pass in a group with the --group tag.")
                return
        if 'hp' in args:
            try:
                hp = int(args['hp'][0])
                if hp < 1:
                    hp = None
                    raise Exception
            except:
                await self.bot.say("You must pass in a positive, nonzero HP with the --hp tag.")
                return
        if 'ac' in args:
            try:
                ac = int(args['ac'][0])
            except:
                await self.bot.say("You must pass in an AC with the --ac tag.")
                return
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return

        if combat.get_combatant(name, True) is not None:
            await self.bot.say("Combatant already exists.")
            return

        try:
            if not place:
                if combat.options.get('d100_init') is True:
                    init = random.randint(1, 100) + (modifier * 5)
                else:
                    init = random.randint(1, 20) + modifier
            else:
                init = modifier
                modifier = 0
            me = Combatant(name=name, init=init, author=controller, mod=modifier, effects=[], notes='', private=private,
                           hp=hp, max_hp=hp, group=group, ac=ac)
            if group is None:
                combat.combatants.append(me)
                await self.bot.say(
                    "{}\n{} was added to combat with initiative {}.".format(controller.mention, name, init),
                    delete_after=10)
            elif combat.get_combatant_group(group) is None:
                newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
                newGroup.combatants.append(me)
                combat.combatants.append(newGroup)
                await self.bot.say(
                    "{}\n{} was added to combat as part of group {}, with initiative {}.".format(controller.mention,
                                                                                                 name, group, init),
                    delete_after=10)
            else:
                group = combat.get_combatant_group(group)
                group.combatants.append(me)
                await self.bot.say(
                    "{}\n{} was added to combat as part of group {}.".format(controller.mention, name, group.name),
                    delete_after=10)
        except Exception as e:
            await self.bot.say("Error adding combatant: {}".format(e))
            return

        await combat.update_summary(self.bot)
        combat.sortCombatants()

    @init.command(pass_context=True, name='cadd', aliases=['dcadd'])
    async def dcadd(self, ctx, *, args: str = ''):
        """Adds the current active character to combat. A character must be loaded through the SheetManager module first.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -p [init value]
              -h (same as !init add)
              --group (same as !init add)"""
        char = Character.from_ctx(ctx)
        character = char.character
        skills = character.get('skills')
        if skills is None:
            return await self.bot.say('You must update your character sheet first.')
        skill = 'initiative'
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return

        if combat.get_combatant(character.get('stats', {}).get('name'), True) is not None:
            await self.bot.say("Combatant already exists.")
            return

        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get(
            'color') is None else character.get('settings', {}).get('color')

        skill_effects = character.get('skill_effects', {})
        args += ' ' + skill_effects.get(skill, '')  # dicecloud v7 - autoadv

        args = shlex.split(args)
        args = parse_args(args)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0
        b = args.get('b', None)
        p = args.get('p', None)
        phrase = args.get('phrase', None)

        if p is None:
            if b is not None:
                check_roll = roll('1d20' + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
            else:
                check_roll = roll('1d20' + '{:+}'.format(skills[skill]), adv=adv, inline=True)

            embed.title = '{} makes an {} check!'.format(character.get('stats', {}).get('name'),
                                                         re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1',
                                                                skill).title())
            embed.description = check_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
            init = check_roll.total
        else:
            init = int(p)
            embed.title = "{} already rolled initiative!".format(character.get('stats', {}).get('name'))
            embed.description = "Placed at initiative `{}`.".format(init)

        group = args.get('group')
        controller = ctx.message.author

        me = DicecloudCombatant(init=init, author=ctx.message.author, effects=[], notes='',
                                private=args.get('h', False), group=args.get('group', None), sheet=character,
                                character=char)
        if group is None:
            combat.combatants.append(me)
            embed.set_footer(text="Added to combat!")
        elif combat.get_combatant_group(group) is None:
            newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
            newGroup.combatants.append(me)
            combat.combatants.append(newGroup)
            embed.set_footer(text="Added to combat in group {}!".format('group'))
        else:
            group = combat.get_combatant_group(group)
            group.combatants.append(me)
            embed.set_footer(text="Added to combat in group {}!".format('group'))
        await self.bot.say(embed=embed)
        await combat.update_summary(self.bot)
        combat.sortCombatants()

    @init.command(pass_context=True)
    async def update(self, ctx, combatant):
        """Updates a combatant's sheet if they were `cadd`ed."""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no characters loaded.')
        character = user_characters[active_character]
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return
        combatant = combat.get_combatant(combatant)
        if combatant is None:
            return await self.bot.say('Combatant not found.', delete_after=10)
        elif not isinstance(combatant, DicecloudCombatant):
            return await self.bot.say('Combatant is not a SheetManager integrated combatant.', delete_after=10)
        else:
            combatant.sheet = character
            await self.bot.say('Combatant sheet updated!', delete_after=15)

    @init.command(pass_context=True)
    async def madd(self, ctx, monster_name: str, *, args: str = ''):
        """Adds a monster to combat.
        Args: adv/dis
              -b [conditional bonus]
              -n [number of monsters]
              -p [init value]
              --name [name scheme, use "#" for auto-numbering, ex. "Orc#"]
              -h (same as !init add, default true)
              --group (same as !init add)
              -npr (removes physical resistances when added)"""

        monster = await searchMonsterFull(monster_name, ctx, pm=True)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr("monsters_looked_up_life")
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        dexMod = floor((int(monster['dex']) - 10) / 2)

        args = shlex.split(args)
        args = parse_args(args)
        private = not 'h' in args
        group = args.get('group')
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0
        b = args.get('b', None)
        p = args.get('p', None)

        opts = {}
        if 'npr' in args:
            opts['npr'] = True

        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return

        out = ''
        try:
            recursion = int(args.get('n', 1))
        except ValueError:
            return await self.bot.say(args.get('n', 1) + " is not a number.")
        recursion = 25 if recursion > 25 else 1 if recursion < 1 else recursion

        for i in range(recursion):
            name = args.get('name', monster['name'][:2].upper() + '#').replace('#', str(i + 1))
            if combat.get_combatant(name, True) is not None:
                out += "{} already exists.\n".format(name)
                continue

            try:
                if p is None:
                    if b is not None:
                        check_roll = roll('1d20' + '{:+}'.format(dexMod) + '+' + b, adv=adv, inline=True)
                    else:
                        check_roll = roll('1d20' + '{:+}'.format(dexMod), adv=adv, inline=True)
                    init = check_roll.total
                else:
                    init = int(p)
                controller = ctx.message.author
                me = MonsterCombatant(name=name, init=init, author=controller, effects=[], notes='', private=private,
                                      group=group, monster=monster, modifier=dexMod, opts=opts)
                if group is None:
                    combat.combatants.append(me)
                    out += "{} was added to combat with initiative {}.\n".format(name,
                                                                                 check_roll.skeleton if p is None else p)
                elif combat.get_combatant_group(group) is None:
                    newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
                    newGroup.combatants.append(me)
                    combat.combatants.append(newGroup)
                    out += "{} was added to combat as part of group {}, with initiative {}.\n".format(name, group,
                                                                                                      check_roll.skeleton if p is None else p)
                else:
                    temp_group = combat.get_combatant_group(group)
                    temp_group.combatants.append(me)
                    out += "{} was added to combat as part of group {}.\n".format(name, temp_group.name)
            except Exception as e:
                log.error('\n'.join(traceback.format_exception(type(e), e, e.__traceback__)))
                out += "Error adding combatant: {}\n".format(e)

        await self.bot.say(out, delete_after=15)
        await combat.update_summary(self.bot)
        combat.sortCombatants()

    @init.command(pass_context=True, name="next", aliases=['n'])
    async def nextInit(self, ctx):
        """Moves to the next turn in initiative order.
        It must be your turn or you must be the DM (the person who started combat) to use this command.
        Usage: !init next"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return

        if len(combat.combatants) == 0:
            await self.bot.say("There are no combatants.")
            return

        combat.lastmodified = datetime.datetime.now()

        if combat.currentCombatant is None:
            pass
        elif not ctx.message.author.id in (combat.currentCombatant.author.id, combat.dm.id):
            await self.bot.say("It is not your turn.")
            return

        toRemove = []
        if combat.currentCombatant is not None:
            if isinstance(combat.currentCombatant, CombatantGroup):
                thisTurn = [c for c in combat.currentCombatant.combatants]
            else:
                thisTurn = [combat.currentCombatant]
            for c in thisTurn:
                if isinstance(c, MonsterCombatant) and c.hp <= 0:
                    toRemove.append(c)

        try:
            nextCombatant = combat.getNextCombatant()
            combat.current = nextCombatant.init
            combat.currentCombatant = nextCombatant
            self.bot.db.incr('turns_init_tracked_life')
        except IndexError:
            combat.current = combat.sorted_combatants[0].init
            combat.round += 1
            self.bot.db.incr('rounds_init_tracked_life')
            combat.index = None
            if combat.options.get('dynamic', False):
                for combatant in combat.combatants:
                    combatant.init = roll('1d20+' + str(combatant.mod)).total
                combat.sorted_combatants = sorted(combat.combatants, key=lambda k: (k.init, k.mod), reverse=True)
            nextCombatant = combat.getNextCombatant()
            combat.currentCombatant = nextCombatant
        if isinstance(nextCombatant, CombatantGroup):
            thisTurn = [c for c in nextCombatant.combatants]
            for c in thisTurn:
                for e in c.effects:
                    if e.remaining == 0:
                        c.effects.remove(e)
                    else:
                        e.remaining -= 1
            outStr = "**Initiative {} (round {})**: {} ({})\n{}"
            outStr = outStr.format(combat.current,
                                   combat.round,
                                   nextCombatant.name,
                                   ", ".join({c.author.mention for c in thisTurn}),
                                   '```markdown\n' + "\n".join([c.get_status() for c in thisTurn]) + '```')
        else:
            thisTurn = [nextCombatant]
            for c in thisTurn:
                for e in c.effects:
                    if e.remaining == 0:
                        c.effects.remove(e)
                    else:
                        e.remaining -= 1
            outStr = "**Initiative {} (round {})**: {}\n{}"
            outStr = outStr.format(combat.current,
                                   combat.round,
                                   " and ".join(["{} ({})".format(c.name, c.author.mention) for c in thisTurn]),
                                   '```markdown\n' + "\n".join([c.get_status() for c in thisTurn]) + '```')
        for c in toRemove:
            if c.group is None:
                combat.combatants.remove(c)
            else:
                group = combat.get_combatant_group(c.group)
                group.combatants.remove(c)
            outStr += "{} automatically removed from combat.\n".format(c.name)
        if len(toRemove) > 0:
            combat.sortCombatants()
            combat.checkGroups()
        await self.bot.say(outStr)
        await combat.update_summary(self.bot)

    @init.command(pass_context=True, name="list", aliases=['summary'])
    async def listInits(self, ctx):
        """Lists the combatants.
        Usage: !init list"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        outStr = combat.getSummary()

        await self.bot.say(outStr, delete_after=60)

    @init.command(pass_context=True)
    async def note(self, ctx, combatant: str, *, note: str = ''):
        """Attaches a note to a combatant.
        Usage: !init note <NAME> <NOTE>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        combatant.notes = note
        if note == '':
            await self.bot.say("Removed note.", delete_after=10)
        else:
            await self.bot.say("Added note.", delete_after=10)
        await combat.update_summary(self.bot)

    @init.command(pass_context=True, aliases=['opts'])
    async def opt(self, ctx, combatant: str, *, args: str):
        """Edits the options of a combatant.
        Usage: !init opt <NAME> <ARGS>
        Valid Arguments:    -h (hides HP)
                            -p (changes init)
                            --name <NAME> (changes combatant name)
                            --controller <CONTROLLER> (pings a different person on turn)
                            --ac <AC> (changes combatant AC)
                            --resist <RESISTANCE>
                            --immune <IMMUNITY>
                            --vuln <VULNERABILITY>
                            --group <GROUP> (changes group)"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        private = combatant.private
        controller = combatant.author
        args = shlex.split(args)
        args = parse_args_2(args)
        out = ''

        if args.get('h'):
            private = not private
            combatant.private = private
            out += "\u2705 Combatant {}.\n".format('hidden' if private else 'unhidden')
        if 'controller' in args:
            try:
                controllerStr = args.get('controller')
                controllerEscaped = controllerStr.strip('<>@!')
                a = ctx.message.server.get_member(controllerEscaped)
                b = ctx.message.server.get_member_named(controllerStr)
                cont = a if a is not None else b if b is not None else controller
                combatant.author = cont
                out += "\u2705 Combatant controller set to {}.\n".format(combatant.author.mention)
            except IndexError:
                out += "\u274c You must pass in a controller with the --controller tag.\n"
        if 'ac' in args:
            try:
                ac = int(args.get('ac'))
                combatant.ac = ac
                out += "\u2705 Combatant AC set to {}.\n".format(ac)
            except:
                out += "\u274c You must pass in an AC with the --ac tag.\n"
        if 'p' in args:
            if combatant == combat.currentCombatant:
                out += "\u274c You cannot change a combatant's initiative on their own turn.\n"
            else:
                try:
                    p = int(args.get('p'))
                    combatant.init = p
                    combat.sortCombatants()
                    out += "\u2705 Combatant initiative set to {}.\n".format(p)
                except:
                    out += "\u274c You must pass in a number with the -p tag.\n"
        if 'group' in args:

            if combatant == combat.currentCombatant:
                out += "\u274c You cannot change a combatant's group on their own turn.\n"
            else:
                group = args.get('group')
                if group.lower() == 'none':
                    if combatant.group:
                        currentGroup = combat.get_combatant_group(combatant.group)
                        currentGroup.combatants.remove(combatant)
                    combatant.group = None
                    combat.combatants.append(combatant)
                    combat.checkGroups()
                    combat.sortCombatants()
                    out += "\u2705 Combatant removed from all groups.\n"
                elif combat.get_combatant_group(group) is not None:
                    if combatant.group:
                        currentGroup = combat.get_combatant_group(combatant.group)
                        currentGroup.combatants.remove(combatant)
                    else:
                        combat.combatants.remove(combatant)
                    group = combat.get_combatant_group(group)
                    combatant.group = group.name
                    group.combatants.append(combatant)
                    combat.checkGroups()
                    combat.sortCombatants()
                    out += "\u2705 Combatant group set to {}.\n".format(group)
                else:
                    out += "\u274c New group not found.\n"
        if 'name' in args:
            name = args.get('name')
            if combat.get_combatant(name, True) is not None:
                out += "\u274c There is already another combatant with that name.\n"
            elif name:
                combatant.name = name
                out += "\u2705 Combatant name set to {}.\n".format(name)
            else:
                out += "\u274c You must pass in a name with the -name tag.\n"
        if 'resist' in args:
            resist = args.get('resist')
            for resist in resist.split('|'):
                if resist in combatant.resist:
                    combatant.resist.remove(resist)
                    out += "\u2705 {} removed from combatant resistances.\n".format(resist)
                else:
                    combatant.resist.append(resist)
                    out += "\u2705 {} added to combatant resistances.\n".format(resist)
        if 'immune' in args:
            immune = args.get('immune')
            for immune in immune.split('|'):
                if immune in combatant.immune:
                    combatant.immune.remove(immune)
                    out += "\u2705 {} removed from combatant immunities.\n".format(immune)
                else:
                    combatant.immune.append(immune)
                    out += "\u2705 {} added to combatant immunities.\n".format(immune)
        if 'vuln' in args:
            vuln = args.get('vuln')
            for vuln in vuln.split('|'):
                if vuln in combatant.vuln:
                    combatant.vuln.remove(vuln)
                    out += "\u2705 {} removed from combatant vulnerabilities.\n".format(vuln)
                else:
                    combatant.vuln.append(vuln)
                    out += "\u2705 {} added to combatant vulnerabilities.\n".format(vuln)

        if combatant.private:
            await self.bot.send_message(combatant.author, "{}'s options updated.\n".format(combatant.name) + out)
            await self.bot.say("Combatant options updated.", delete_after=10)
        else:
            await self.bot.say("{}'s options updated.\n".format(combatant.name) + out, delete_after=10)
        await combat.update_summary(self.bot)

    @init.command(pass_context=True)
    async def status(self, ctx, combatant: str, *, args: str = ''):
        """Gets the status of a combatant or group.
        Usage: !init status <NAME> <ARGS (opt)>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(combatant) or combat.get_combatant_group(combatant)
        if combatant is None:
            await self.bot.say("Combatant or group not found.")
            return

        private = 'private' in args.lower() if ctx.message.author.id == combatant.author.id else False
        if isinstance(combatant, Combatant):
            status = combatant.get_status(private=private)
        else:
            status = "\n".join([c.get_status(private=private) for c in combatant.combatants])
        if 'private' in args.lower():
            await self.bot.send_message(combatant.author, "```markdown\n" + status + "```")
        else:
            await self.bot.say("```markdown\n" + status + "```", delete_after=30)

    @init.command(pass_context=True)
    async def hp(self, ctx, combatant: str, operator: str, *, hp: str = ''):
        """Modifies the HP of a combatant.
        Usage: !init hp <NAME> <mod/set/max> <HP>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        hp_roll = roll(hp, inline=True, show_blurbs=False)

        if 'mod' in operator.lower():
            if combatant.hp is None:
                combatant.hp = 0
            combatant.hp += hp_roll.total
        elif 'set' in operator.lower():
            combatant.hp = hp_roll.total
        elif 'max' in operator.lower():
            if hp_roll.total < 1:
                await self.bot.say("You can't have a negative max HP!")
            elif combatant.hp is None:
                combatant.hp = hp_roll.total
                combatant.max_hp = hp_roll.total
            else:
                combatant.max_hp = hp_roll.total
        elif hp == '':
            hp_roll = roll(operator, inline=True, show_blurbs=False)
            if combatant.hp is None:
                combatant.hp = 0
            combatant.hp += hp_roll.total
        else:
            await self.bot.say("Incorrect operator. Use mod, set, or max.")
            return

        out = "{}: {}".format(combatant.name, combatant.get_hp())
        if 'd' in hp: out += '\n' + hp_roll.skeleton

        await self.bot.say(out, delete_after=10)
        if combatant.private:
            try:
                await self.bot.send_message(combatant.author,
                                            "{}'s HP: {}/{}".format(combatant.name, combatant.hp, combatant.max_hp))
            except:
                pass
        await combat.update_summary(self.bot)

    @init.command(pass_context=True)
    async def effect(self, ctx, combatant: str, duration: int, name: str, *, effect: str = None):
        """Attaches a status effect to a combatant.
        Usage: !init effect <COMBATANT> <DURATION (rounds)> <NAME> [effect]
        [effect] is a set of args that will be appended to every `!i a` the combatant makes."""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        if name.lower() in (e.name.lower() for e in combatant.effects):
            return await self.bot.say("Effect already exists.", delete_after=10)

        effectObj = Effect(duration=duration, name=name, remaining=duration, effect=effect)
        combatant.effects.append(effectObj)
        await self.bot.say("Added effect {} to {}.".format(name, combatant.name), delete_after=10)
        await combat.update_summary(self.bot)

    @init.command(pass_context=True, name='re')
    async def remove_effect(self, ctx, combatant: str, effect: str = ''):
        """Removes a status effect from a combatant. Removes all if effect is not passed.
        Usage: !init re <NAME> <EFFECT (opt)>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        to_remove = combatant.get_effect(effect)
        if effect is '':
            combatant.effects = []
            await self.bot.say("All effects removed from {}.".format(combatant.name), delete_after=10)
        elif to_remove is None:
            await self.bot.say("Effect not found.")
            return
        else:
            combatant.effects.remove(to_remove)
            await self.bot.say('Effect {} removed from {}.'.format(to_remove.name, combatant.name), delete_after=10)
        await combat.update_summary(self.bot)

    @init.command(pass_context=True, aliases=['a'])
    async def attack(self, ctx, target_name, atk_name, *, args=''):
        """Rolls an attack against another combatant.
        Valid Arguments: see !a and !ma.
        `-custom` - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add damage and to hit."""
        return await self._attack(ctx, None, target_name, atk_name, args)

    @init.command(pass_context=True)
    async def aoo(self, ctx, combatant_name, target_name, atk_name, *, args=''):
        """Rolls an attack of opportunity against another combatant.
        Valid Arguments: see !a and !ma.
        `-custom` - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add damage and to hit."""
        return await self._attack(ctx, combatant_name, target_name, atk_name, args)

    async def _attack(self, ctx, combatant_name, target_name, atk_name, args):
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        target = combat.get_combatant(target_name)
        if target is None:
            await self.bot.say("Target not found.")
            return
        if combatant_name is None:
            combatant = combat.currentCombatant
            if combatant is None:
                return await self.bot.say("You must start combat with `!init next` first.")
        else:
            combatant = combat.get_combatant(combatant_name)
            if combatant is None:
                return await self.bot.say("Combatant not found.")

        if not isinstance(combatant, CombatantGroup):
            for eff in combatant.effects:
                if hasattr(eff, "effect"):
                    args += " " + eff.effect if eff.effect is not None else ""

        if isinstance(combatant, DicecloudCombatant):
            if not '-custom' in args:
                attacks = combatant.sheet.get('attacks')  # get attacks
                try:  # fuzzy search for atk_name
                    attack = next(a for a in attacks if atk_name.lower() == a.get('name').lower())
                except StopIteration:
                    try:
                        attack = next(a for a in attacks if atk_name.lower() in a.get('name').lower())
                    except StopIteration:
                        return await self.bot.say('No attack with that name found.')
            else:
                attack = {'attackBonus': None, 'damage': None, 'name': atk_name}

            tempargs = shlex.split(args)
            user_snippets = self.bot.db.not_json_get('damage_snippets', {}).get(ctx.message.author.id, {})
            for index, arg in enumerate(tempargs):  # parse snippets
                snippet_value = user_snippets.get(arg)
                if snippet_value:
                    tempargs[index] = snippet_value
                elif ' ' in arg:
                    tempargs[index] = shlex.quote(arg)

            args = " ".join(tempargs)
            tempchar = Character(combatant.sheet, combatant.id)
            args = tempchar.parse_cvars(args, ctx)
            args = shlex.split(args)
            args = parse_args_2(args)
            if attack.get('details') is not None:
                attack['details'] = tempchar.parse_cvars(attack['details'], ctx)
            args['name'] = combatant.name  # combatant.sheet.get('stats', {}).get('name', "NONAME")
            if target.ac is not None: args['ac'] = target.ac
            args['t'] = target.name
            args['resist'] = args.get('resist') or '|'.join(target.resist)
            args['immune'] = args.get('immune') or '|'.join(target.immune)
            args['vuln'] = args.get('vuln') or '|'.join(target.vuln)
            args['criton'] = combatant.sheet.get('settings', {}).get('criton', 20) or 20
            args['c'] = combatant.sheet.get('settings', {}).get('critdmg') or args.get('c')
            args['hocrit'] = combatant.sheet.get('settings', {}).get('hocrit') or False
            args['crittype'] = combatant.sheet.get('settings', {}).get('crittype') or 'default'
            result = sheet_attack(attack, args)
            result['embed'].colour = random.randint(0, 0xffffff) if combatant.sheet.get('settings', {}).get(
                'color') is None else combatant.sheet.get('settings', {}).get('color')
            if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']
        elif isinstance(combatant, MonsterCombatant):
            if not '-custom' in args:
                attacks = combatant.monster.get('attacks')  # get attacks
                attack = fuzzy_search(attacks, 'name', atk_name)
                if attack is None:
                    return await self.bot.say("No attack with that name found.", delete_after=15)
                attack['details'] = attack.get('desc')
            else:
                attack = {'attackBonus': None, 'damage': None, 'name': atk_name}

            args = shlex.split(args)
            args = parse_args_2(args)
            args['name'] = combatant.name  # a_or_an(combatant.monster.get('name')).title()
            if target.ac is not None: args['ac'] = target.ac
            args['t'] = target.name
            args['resist'] = args.get('resist') or '|'.join(target.resist)
            args['immune'] = args.get('immune') or '|'.join(target.immune)
            args['vuln'] = args.get('vuln') or '|'.join(target.vuln)
            result = sheet_attack(attack, args)
            result['embed'].colour = random.randint(0, 0xffffff)
            if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']
        elif isinstance(combatant, CombatantGroup):
            if not '-custom' in args:
                attacks = []
                for c in combatant.combatants:
                    if isinstance(c, DicecloudCombatant):
                        attacks += c.sheet.get('attacks', [])
                    elif isinstance(c, MonsterCombatant):
                        attacks += c.monster.get('attacks', [])
                attack = fuzzy_search(attacks, 'name', atk_name)
                if attack is None:
                    return await self.bot.say("No attack with that name found.", delete_after=15)
            else:
                attack = {'attackBonus': None, 'damage': None, 'name': atk_name}
            attack['details'] = attack.get('desc') if attack.get('details') is None else attack['details']
            args = shlex.split(args)
            args = parse_args_2(args)
            args['name'] = "One of the {}".format(combatant.name)
            if target.ac is not None: args['ac'] = target.ac
            args['t'] = target.name
            result = sheet_attack(attack, args)
            result['embed'].colour = random.randint(0, 0xffffff)
            if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']
        else:
            if not '-custom' in args:
                return await self.bot.say("Integrated attacks must be custom for nonintegrated combatants.")
            else:
                attack = {'attackBonus': None, 'damage': None, 'name': atk_name}
            args = shlex.split(args)
            args = parse_args_2(args)
            args['name'] = combatant.name
            if target.ac is not None: args['ac'] = target.ac
            args['t'] = target.name
            args['resist'] = args.get('resist') or '|'.join(target.resist)
            args['immune'] = args.get('immune') or '|'.join(target.immune)
            args['vuln'] = args.get('vuln') or '|'.join(target.vuln)
            result = sheet_attack(attack, args)
            result['embed'].colour = random.randint(0, 0xffffff)
            if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']
        embed = result['embed']
        if target.ac is not None:
            if target.hp is not None:
                embed.set_footer(text="{}: {}".format(target.name, target.get_hp()))
                if target.private:
                    try:
                        await self.bot.send_message(target.author,
                                                    "{}'s HP: {}/{}".format(target.name, target.hp, target.max_hp))
                    except:
                        pass
            else:
                embed.set_footer(text="Dealt {} damage to {}!".format(result['total_damage'], target.name))
        else:
            embed.set_footer(text="Target AC not set.")
        await self.bot.say(embed=embed)
        await combat.update_summary(self.bot)

    @init.command(pass_context=True)
    async def cast(self, ctx, spell_name, *, args):
        """Casts a spell against another combatant.
        __Valid Arguments__
        -t [target (chainable)] - Required
        -i - Ignores Spellbook restrictions, for demonstrations or rituals.
        -l [level] - Specifies the level to cast the spell at.
        **__Save Spells__**
        -dc [Save DC] - Default: Pulls a cvar called `dc`.
        -save [Save type] - Default: The spell's default save.
        -d [damage] - adds additional damage.
        adv/dis - forces all saves to be at adv/dis.
        **__Attack Spells__**
        See `!a`.
        **__All Spells__**
        -phrase [phrase] - adds flavor text."""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.currentCombatant
        if combatant is None:
            return await self.bot.say("You must begin combat with !init next first.")

        is_character = isinstance(combatant, DicecloudCombatant)
        if not is_character: return await self.bot.say("This command requires a SheetManager integrated combatant.")

        character = Character.from_bot_and_ids(self.bot, combatant.auth_id, combatant.id)

        tempargs = shlex.split(args)
        user_snippets = self.bot.db.not_json_get('damage_snippets', {}).get(ctx.message.author.id, {})
        for index, arg in enumerate(tempargs):  # parse snippets
            snippet_value = user_snippets.get(arg)
            if snippet_value:
                tempargs[index] = snippet_value
            elif ' ' in arg:
                tempargs[index] = shlex.quote(arg)

        args = " ".join(tempargs)
        args = character.parse_cvars(args, ctx)
        args = shlex.split(args)
        args = parse_args_3(args)

        if not args.get('t'):
            return await self.bot.say("You must pass in targets with `-t target`.", delete_after=15)

        embed = discord.Embed()
        embed_footer = ''
        if args.get('phrase') is not None:  # parse phrase
            embed.description = '*' + '\n'.join(args.get('phrase')) + '*'
        else:
            embed.description = '~~' + ' ' * 500 + '~~'

        if not args.get('i'):
            spell_name = await searchCharacterSpellName(spell_name, ctx, character)
        else:
            spell_name = await searchSpellNameFull(spell_name, ctx)

        if spell_name is None: return await self.bot.say(embed=discord.Embed(title="Unsupported spell!",
                                                                             description="The spell was not found or is not supported."))

        spell = await searchAutoSpellFull(spell_name, ctx)

        can_cast = True
        spell_level = int(spell.get('level', 0))
        try:
            cast_level = int(args.get('l', [spell_level])[-1])
            assert spell_level <= cast_level <= 9
        except (AssertionError, ValueError):
            return await self.bot.say("Invalid spell level.")

        # make sure we can cast it
        try:
            assert character.get_remaining_slots(cast_level) > 0
            assert spell['name'] in character.get_spell_list()
        except AssertionError:
            can_cast = False
        else:
            # use a spell slot
            if not args.get('i'):
                character.use_slot(cast_level)

        if args.get('i'):
            can_cast = True

        if not can_cast:
            embed = EmbedWithCharacter(character)
            embed.title = "Cannot cast spell!"
            embed.description = "Not enough spell slots remaining, or spell not in known spell list!\n" \
                                "Use `!game longrest` to restore all spell slots, or pass `-i` to ignore restrictions."
            if cast_level > 0:
                embed.add_field(name="Spell Slots", value=character.get_remaining_slots_str(cast_level))
            return await self.bot.say(embed=embed)

        upcast_dmg = None
        if not cast_level == spell_level:
            upcast_dmg = spell.get('higher_levels', {}).get(str(cast_level))

        if args.get('title') is not None:
            embed.title = args.get('title')[-1].replace('[charname]', args.get('name')).replace('[sname]',
                                                                                                spell['name']).replace(
                '[target]', args.get('t', ''))
        else:
            embed.title = '{} casts {} at...'.format(combatant.name, spell['name'])

        damage_save = None
        for i, t in enumerate(args.get('t', [])):
            target = combat.get_combatant(t)
            if target is None:
                embed.add_field(name="{} not found!".format(t), value="Target not found.")
            elif not isinstance(target, (DicecloudCombatant, MonsterCombatant)):
                embed.add_field(name="{} not supported!".format(t),
                                value="Target must be a monster or player added with `madd` or `cadd`.")
            else:
                spell_type = spell.get('type')
                if spell_type == 'save':  # save spell
                    out = ''
                    calculated_dc = character.evaluate_cvar('dc') or character.get_save_dc()
                    dc = args.get('dc', [None])[-1] or calculated_dc
                    if not dc:
                        return await self.bot.say(embed=discord.Embed(title="Error: Save DC not found.",
                                                                      description="Your spell save DC is not found. Most likely cause is that you do not have spells."))
                    try:
                        dc = int(dc)
                    except:
                        return await self.bot.say(embed=discord.Embed(title="Error: Save DC malformed.",
                                                                      description="Your spell save DC is malformed."))

                    save_skill = args.get('save', [None])[-1] or spell.get('save', {}).get('save')
                    try:
                        save_skill = next(s for s in ('strengthSave',
                                                      'dexteritySave',
                                                      'constitutionSave',
                                                      'intelligenceSave',
                                                      'wisdomSave',
                                                      'charismaSave') if save_skill.lower() in s.lower())
                    except StopIteration:
                        return await self.bot.say(embed=discord.Embed(title="Invalid save!",
                                                                      description="{} is not a valid save.".format(
                                                                          save_skill)))
                    save = spell['save']

                    save_roll_mod = target.saves.get(save_skill, 0)
                    adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                                    False) else -1 if args.get(
                        'dis', False) else 0

                    save_roll = roll('1d20{:+}'.format(save_roll_mod), adv=adv,
                                     rollFor='{} Save'.format(save_skill[:3].upper()), inline=True, show_blurbs=False)
                    is_success = save_roll.total >= dc
                    out += save_roll.result + ("; Success!" if is_success else "; Failure!") + '\n'

                    if save['damage'] is None:
                        if i == 0:
                            embed.add_field(name="DC", value=str(dc))
                        embed.add_field(name='...{}!'.format(target.name), value=out, inline=False)
                    else:  # save against damage spell
                        if damage_save is None:
                            dmg = save['damage']

                            if is_character and spell['level'] == '0' and spell.get('scales', True):
                                def lsub(matchobj):
                                    level = combatant.sheet.get('levels', {}).get('level', 0)
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

                            if args.get('d') is not None:
                                dmg = dmg + '+' + "+".join(args.get('d', []))

                            dmgroll = roll(dmg, rollFor="Damage", inline=True, show_blurbs=False)
                            embed.add_field(name="Damage/DC", value=dmgroll.result + "\n**DC**: {}".format(str(dc)))
                            d = ""
                            for p in dmgroll.raw_dice.parts:
                                if isinstance(p, SingleDiceGroup):
                                    d += "{} {}".format(p.get_total(), p.annotation)
                                else:
                                    d += str(p)
                            damage_save = d
                        dmg = damage_save

                        dmg = parse_resistances(dmg, args.get('resist', []) or target.resist,
                                                args.get('immune', []) or target.immune,
                                                args.get('vuln', []) or target.vuln)

                        if is_success:
                            if save['success'] == 'half':
                                dmg = "({})/2".format(dmg)
                            else:
                                dmg = "0"

                        dmgroll = roll(dmg, rollFor="Damage", inline=True, show_blurbs=False)
                        out += dmgroll.result + '\n'

                        embed.add_field(name='...{}!'.format(target.name), value=out, inline=False)

                        if target.hp is not None:
                            target.hp -= dmgroll.total
                            embed_footer += "{}: {}\n".format(target.name, target.get_hp())
                            if target.private:
                                try:
                                    await self.bot.send_message(target.author,
                                                                "{}'s HP: {}/{}".format(target.name, target.hp,
                                                                                        target.max_hp))
                                except:
                                    pass
                        else:
                            embed_footer += "Dealt {} damage to {}!".format(dmgroll.total, target.name)
                elif spell['type'] == 'attack':  # attack spell
                    if not is_character: return await self.bot.say(embed=discord.Embed(title="Unsupported spell!",
                                                                                       description="Attack spells are only supported for combatants added with `cadd`."))

                    outargs = copy.copy(args)
                    outargs['t'] = target.name
                    if target.ac is not None: outargs['ac'] = target.ac
                    outargs['resist'] = '|'.join(args.get('resist', [])) or '|'.join(target.resist)
                    outargs['immune'] = '|'.join(args.get('immune', [])) or '|'.join(target.immune)
                    outargs['vuln'] = '|'.join(args.get('vuln', [])) or '|'.join(target.vuln)
                    outargs['d'] = "+".join(args.get('d', [])) or None
                    outargs['crittype'] = character.get_setting('crittype', 'default')
                    for _arg, _value in outargs.items():
                        if isinstance(_value, list):
                            outargs[_arg] = _value[-1]
                    attack = copy.copy(spell['atk'])
                    attack['attackBonus'] = str(
                        character.evaluate_cvar(attack['attackBonus']) or character.get_spell_ab())

                    if not attack['attackBonus']:
                        return await self.bot.say(embed=discord.Embed(title="Error: Casting ability not found.",
                                                                      description="Your casting ability is not found. Most likely cause is that you do not have spells."))

                    if is_character and spell['level'] == '0' and spell.get('scales', True):
                        def lsub(matchobj):
                            level = combatant.sheet.get('levels', {}).get('level', 0)
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

                    attack['damage'] = attack['damage'].replace("SPELL",
                                                                str(
                                                                    character.get_spell_ab() - character.get_prof_bonus()))

                    result = sheet_attack(attack, outargs)
                    out = ""
                    for f in result['embed'].fields:
                        out += "**__{0.name}__**\n{0.value}\n".format(f)

                    embed.add_field(name='...{}!'.format(target.name), value=out, inline=False)

                    if target.hp is not None:
                        target.hp -= result['total_damage']
                        embed_footer += "{}: {}\n".format(target.name, target.get_hp())
                        if target.private:
                            try:
                                await self.bot.send_message(target.author,
                                                            "{}'s HP: {}/{}".format(target.name, target.hp,
                                                                                    target.max_hp))
                            except:
                                pass
                    else:
                        embed_footer += "Dealt {} damage to {}!".format(dmgroll.total, target.name)
                else:  # special spell (MM)
                    outargs = copy.copy(args)  # just make an attack for it
                    outargs['d'] = "+".join(args.get('d', [])) or None
                    for _arg, _value in outargs.items():
                        if isinstance(_value, list):
                            outargs[_arg] = _value[-1]
                    attack = {"name": spell['name'],
                              "damage": spell.get("damage", "0").replace('SPELL', str(
                                  character.get_spell_ab() - character.get_prof_bonus())),
                              "attackBonus": None}
                    if upcast_dmg:
                        attack['damage'] = attack['damage'] + '+' + upcast_dmg
                    result = sheet_attack(attack, outargs)
                    out = ""
                    for f in result['embed'].fields:
                        out += "**__{0.name}__**\n{0.value}\n".format(f)

                    embed.add_field(name='...{}!'.format(target.name), value=out, inline=False)

                    if target.hp is not None:
                        target.hp -= result['total_damage']
                        embed_footer += "{}: {}\n".format(target.name, target.get_hp())
                        if target.private:
                            try:
                                await self.bot.send_message(target.author,
                                                            "{}'s HP: {}/{}".format(target.name, target.hp,
                                                                                    target.max_hp))
                            except:
                                pass
                    else:
                        embed_footer += "Dealt {} damage to {}!".format(dmgroll.total, target.name)

        spell_ctx = spell_context(spell)
        if spell_ctx:
            embed.add_field(name='Effect', value=spell_ctx)

        if cast_level > 0:
            embed.add_field(name="Spell Slots", value=character.get_remaining_slots_str(cast_level))

        embed.colour = getattr(combatant, 'sheet', {}).get('settings', {}).get('color') or random.randint(0, 0xffffff)
        embed.set_footer(text=embed_footer)
        character.manual_commit(self.bot, combatant.auth_id)
        await self.bot.say(embed=embed)

    @init.command(pass_context=True)
    async def sim(self, ctx, *, args: str = ""):
        """Simulates the current turn of combat.
        MonsterCombatants will target any non-monster combatant, and DicecloudCombatants will target any monster combatants.
        Valid Arguments: -t [target]"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        current = combat.currentCombatant
        if current is None:
            return self.bot.say("I can't simulate nobody's turn.")
        elif isinstance(current, CombatantGroup):
            thisTurn = [c for c in current.combatants]
        else:
            thisTurn = [current]

        args = parse_args(shlex.split(args))
        supplied_target = None
        if 't' in args:
            supplied_target = combat.get_combatant(args.get('t'))
            if supplied_target is None:
                await self.bot.say("Target not found.")
                return

        for current in thisTurn:
            await asyncio.sleep(1)  # select target
            isMonster = isinstance(current, MonsterCombatant)
            if isMonster:
                if 'multiattack' in [a.get('name', '').lower() for a in current.monster.get('action', [{}])]:
                    mon_attacks = current.monster.get('attacks')
                    possible_attacks = next(a.get('multiattack', []) for a in current.monster.get('action', [{}]) if
                                            a['name'].lower() == 'multiattack')
                    chosen_attack = random.choice(possible_attacks)
                    attacks = []
                    for atk in chosen_attack:  # [{"Melee": 2}],
                        for _ in range(int(list(atk.values())[0])):
                            try:
                                attacks.append(next(a for a in mon_attacks if list(atk.keys())[0] in a.get('name')))
                            except StopIteration:
                                try:
                                    attacks.append(next(a for a in mon_attacks if list(atk.keys())[0] in a.get('desc')))
                                except:
                                    raise
                    random.shuffle(attacks)
                else:
                    mon_attacks = current.monster.get('attacks')  # get attacks
                    mon_attacks = [a for a in mon_attacks if a.get('attackBonus') is not None]
                    if len(mon_attacks) < 1:
                        await self.bot.say("```diff\n- {} has no attacks!```".format(current.name))
                        break
                    attacks = [random.choice(mon_attacks)]
            elif isinstance(current, DicecloudCombatant):
                char_attacks = current.sheet.get('attacks')  # get attacks
                char_attacks = [a for a in char_attacks if a.get('attackBonus') is not None]
                if len(char_attacks) < 1:
                    await self.bot.say("```diff\n- {} has no attacks!```".format(current.name))
                    break
                attack = random.choice(char_attacks)
                attacks = [attack]
            else:
                await self.bot.say("Simulation is only supported for combatants added with `madd` or `cadd`.")
                continue
            for a in attacks:
                if supplied_target is None:
                    if isMonster:
                        targets = [c for c in combat.combatants if
                                   not (isinstance(c, MonsterCombatant) or isinstance(c, CombatantGroup))]
                    else:
                        targets = [c for c in combat.combatants if isinstance(c, MonsterCombatant)]
                    if len(targets) == 0:
                        await self.bot.say("```diff\n+ {} sees no targets!\n```".format(current.name))
                        break
                target = supplied_target or random.choice(targets)

                await self.bot.say("```diff\n+ {} swings at {}!```".format(current.name, target.name))
                args = {}
                args['name'] = current.name
                if target.ac is not None: args['ac'] = target.ac
                args['t'] = target.name
                result = sheet_attack(a, args)
                if target.ac is not None:
                    if target.hp is not None: target.hp -= result['total_damage']

                if isinstance(current, DicecloudCombatant):
                    result['embed'].colour = random.randint(0, 0xffffff) if current.sheet.get('settings', {}).get(
                        'color') is None else current.sheet.get('settings', {}).get('color')
                elif isinstance(current, MonsterCombatant):
                    result['embed'].colour = random.randint(0, 0xffffff)
                else:
                    return await self.bot.say(
                        'Integrated attacks are only supported for combatants added via `madd` or `dcadd`.',
                        delete_after=15)
                embed = result['embed']
                if target.ac is not None:
                    if target.hp is not None:
                        embed.set_footer(text="{}: {}".format(target.name, target.get_hp()))
                    else:
                        embed.set_footer(text="Target HP not set.")
                else:
                    embed.set_footer(text="Target AC not set.")
                killed = ""
                if target.hp is not None:
                    killed = "\n- Killed {}!".format(target.name) if target.hp <= 0 else ""
                # if target.hp <= 0:
                #                         if target.group is None:
                #                             combat.combatants.remove(target)
                #                         else:
                #                             group = combat.get_combatant_group(target.group)
                #                             group.combatants.remove(target)
                #                         combat.sortCombatants()
                #                         combat.checkGroups()
                await self.bot.say("```diff\n- Dealt {} damage!{}```".format(result['total_damage'], killed),
                                   embed=embed)
                await combat.update_summary(self.bot)
                await asyncio.sleep(2)  # select attack

    @init.command(pass_context=True, name='remove')
    async def remove_combatant(self, ctx, *, name: str):
        """Removes a combatant or group from the combat.
        Usage: !init remove <NAME>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        combatant = combat.get_combatant(name) or combat.get_combatant_group(name)
        if combatant is None:
            await self.bot.say("Combatant or group not found.")
            return
        if combatant == combat.currentCombatant:
            return await self.bot.say("You cannot remove a combatant on their own turn.")

        if isinstance(combatant, CombatantGroup):
            for e in combatant.combatants:
                combatant.combatants.remove(e)
            combat.combatants.remove(combatant)
        else:
            for e in combatant.effects:
                combatant.effects.remove(e)

            if combatant.group is None:
                combat.combatants.remove(combatant)
            else:
                group = combat.get_combatant_group(combatant.group)
                if len(group.combatants) <= 1 and group == combat.currentCombatant:
                    return await self.bot.say(
                        "You cannot remove a combatant if they are the only remaining combatant in this turn.")
                group.combatants.remove(combatant)
        await self.bot.say("{} removed from combat.".format(combatant.name), delete_after=10)
        await combat.update_summary(self.bot)
        combat.checkGroups()
        combat.sortCombatants()

    @init.command(pass_context=True)
    async def end(self, ctx):
        """Ends combat in the channel.
        Usage: !init end
        Syncronises final HP."""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return

        msg = await self.bot.say('Are you sure you want to end combat? (Reply with yes/no)')
        reply = await self.bot.wait_for_message(timeout=30, author=ctx.message.author)
        replyBool = get_positivity(reply.content) if reply is not None else None
        try:
            await self.bot.delete_message(msg)
            await self.bot.delete_message(reply)
        except:
            pass
        if replyBool is None:
            return await self.bot.say('Timed out waiting for a response or invalid response.', delete_after=10)
        elif not replyBool:
            return await self.bot.say('OK, cancelling.', delete_after=10)

        msg = await self.bot.say("OK, ending...")

        for c in combat.combatants:
            if isinstance(c, DicecloudCombatant):
                try:
                    character = Character.from_bot_and_ids(self.bot, c.author.id, c.id)
                    character.set_hp(c.hp).manual_commit(self.bot, c.author.id)
                except:
                    pass
                try:
                    await self.bot.send_message(c.author, "{}'s final HP: {}".format(c.name, c.get_hp(True)))
                except:
                    pass

        try:
            await self.bot.edit_message(combat.summary_message,
                                        combat.summary_message.content + "\n```-----COMBAT ENDED-----```")
            await self.bot.unpin_message(combat.summary_message)
        except:
            pass

        try:
            self.combats.remove(combat)
        except:
            await self.bot.edit_message(msg, "Failed to end combat.")
        else:
            await self.bot.edit_message(msg, "Combat ended.")

    def __unload(self):
        self.panic_save()

    def panic_save(self):
        make_sure_path_exists('temp/')
        with open(f'temp/combats-{self.bot.shard_id}.avrae', mode='w') as f:
            f.write('\n'.join(c.channel.id for c in self.combats))
            # self.bot.db.jsetex('temp_combatpanic.{}'.format(getattr(self.bot, 'shard_id', 0)), temp_key, 120) # timeout in 2 minutes
        for combat in self.combats:
            combat.combatantGenerator = None
            path = 'temp/{}.avrae'.format(combat.channel.id)
            with open(path, mode='wb') as f:
                pickle.dump(combat, f, pickle.HIGHEST_PROTOCOL)
            # self.bot.db.setex(path, pickle.dumps(combat, pickle.HIGHEST_PROTOCOL).decode('cp437'), 604800) # ttl 1 wk
            log.info("Saved combat for {}!".format(combat.channel.id))

    async def panic_load(self):
        make_sure_path_exists('temp/')
        await self.bot.wait_until_ready()
        try:
            with open(f'temp/combats-{self.bot.shard_id}.avrae', mode='r') as f:
                combats = f.readlines()
        except:
            combats = []
        # combats = self.bot.db.jget('temp_combatpanic.{}'.format(getattr(self.bot, 'shard_id', 0)), [])
        temp_msgs = []
        for c in combats:
            c = c.strip()
            if self.bot.get_channel(c) is None:
                log.warning('Shard check for {} failed, aborting.'.format(c))
                continue
            path = 'temp/{}.avrae'.format(c)
            try:
                with open(path, mode='rb') as f:
                    combat = pickle.load(f)
                os.remove(path)
            except:
                log.warning('Combat not found reloading {}, aborting'.format(c))
                continue
            # combat = self.bot.db.get(path, None)
            # if combat is None:
            #     log.warning('Combat not found reloading {}, aborting'.format(c))
            #     continue
            # combat = pickle.loads(combat.encode('cp437'))
            if combat.lastmodified + datetime.timedelta(weeks=1) < datetime.datetime.now():
                log.warning('Combat not modified for over 1w reloading {}, aborting'.format(c))
                continue
            combat.channel = self.bot.get_channel(combat.channel.id)
            if combat.channel is None:
                log.warning('Combat channel not found reloading {}, aborting'.format(c))
                continue
            self.combats.append(combat)
            try:
                if combat.summary_message is not None:
                    combat.summary_message = await self.bot.get_message(combat.channel, combat.summary_message.id)
            except NotFound:
                log.warning('Summary Message not found reloading {}'.format(c))
            except:
                pass
            log.info("Autoreloaded {}".format(c))
            try:
                temp_msgs.append(
                    await self.bot.send_message(combat.channel, "Combat automatically reloaded after bot restart!"))
            except Forbidden:
                log.warning('No permission to post in {}'.format(c))
        # self.bot.db.delete('temp_combatpanic.{}'.format(getattr(self.bot, 'shard_id', 0)))
        await asyncio.sleep(30)
        for msg in temp_msgs:
            try:
                await self.bot.delete_message(msg)
            except:
                pass

    @init.command(pass_context=True, hidden=True)
    async def save(self, ctx):
        """Saves combat to a file for long-term storage.
        Usage: !init save"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        # path = '{}.avrae'.format(ctx.message.channel.id)
        # self.bot.db.setex(path, pickle.dumps(combat, pickle.HIGHEST_PROTOCOL).decode('cp437'), 604800) # ttl 1 wk
        combat.combatantGenerator = None
        path = 'temp/{}.avrae'.format(combat.channel.id)
        with open(path, mode='wb') as f:
            pickle.dump(combat, f, pickle.HIGHEST_PROTOCOL)
        log.info("Saved combat for {}!".format(combat.channel.id))
        await self.bot.say("Combat saved.")

    @init.command(pass_context=True, hidden=True)
    async def load(self, ctx):
        """Loads combat from a file.
        Usage: !init load"""
        if [c for c in self.combats if c.channel is ctx.message.channel]:
            await self.bot.say("You are already in combat. To end combat, use \"!init end\".")
            return
        path = 'temp/{}.avrae'.format(ctx.message.channel.id)
        try:
            with open(path, mode='rb') as f:
                combat = pickle.load(f)
            os.remove(path)
        except:
            combat = None
        # path = '{}.avrae'.format(ctx.message.channel.id)
        # combat = self.bot.db.get(path, None)
        if combat is None:
            return await self.bot.say("No combat saved.")
        # combat = pickle.loads(combat.encode('cp437'))
        combat.channel = ctx.message.channel
        self.combats.append(combat)
        summaryMsg = await self.bot.say(combat.getSummary())
        combat.summary_message = summaryMsg
        try:
            await self.bot.pin_message(summaryMsg)
        except:
            pass
        await self.bot.say("Combat loaded.")
