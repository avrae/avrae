'''
Created on Sep 18, 2016

@author: andrew
'''
import asyncio
import copy
from math import floor
from os.path import isfile
import pickle
import random
import re
import shlex
import signal
from string import capwords
import traceback

import discord
from discord.errors import NotFound
from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import searchMonster
from cogs5e.funcs.sheetFuncs import sheet_attack
from utils.functions import make_sure_path_exists, discord_trim, parse_args, \
    fuzzy_search, get_positivity, a_or_an, parse_args_2, text_to_numbers


class Combat(object):
    def __init__(self, channel:discord.Channel, combatants=[], init:int=0, init_round:int=0, summary_message=None, options={}, name=""):
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
        
    def get_combatant(self, name):
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
                combatant = next(c for c in allCombatants if name.lower() in c.name.lower() and isinstance(c, Combatant))
            except StopIteration:
                pass
            
        return combatant
    
    def get_combatant_group(self, name):
        group = None
        try:
            group = next(c for c in self.combatants if c.name.lower() == name.lower() and isinstance(c, CombatantGroup))
        except StopIteration:
            try:
                group = next(c for c in self.combatants if name.lower() in c.name.lower() and isinstance(c, CombatantGroup))
            except StopIteration:
                pass
        return group
    
    def checkGroups(self):
        for c in self.combatants:
            if isinstance(c, CombatantGroup):
                if len(c.combatants) is 0:
                    self.combatants.remove(c)
    
    def getSummary(self):
        combatants = sorted(self.combatants, key=lambda k: k.init, reverse=True)
        outStr = "```markdown\n{}: {} (round {})\n".format(self.name if self.name is not '' else "Current initiative", self.current, self.round)
        outStr += '=' * (len(outStr) - 13) 
        outStr += '\n'
        outStr += '\n'.join([c.get_short_status() for c in combatants])
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
    def __init__(self, init:int=0, name:str='', author:discord.User=None, notes:str=''):
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
    def __init__(self, init:int=0, name:str='', author:discord.User=None, mod:int=0, notes:str='', effects=[], hp:int=None, max_hp:int=None, private:bool=False, group:str=None, ac:int=None):
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
    
    def get_hp(self, private:bool=False):
        hpStr = ''
        if not self.private or private:
            hpStr = '<{}/{} HP>'.format(self.hp, self.max_hp) if self.max_hp is not None else '<{} HP>'.format(self.hp) if self.hp is not None else ''
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
    
    def get_hp_and_ac(self, private:bool=False):
        out = []
        out.append(self.get_hp(private))
        if self.ac is not None and not self.private:
            out.append("(AC {})".format(self.ac))
        return ' '.join(out)
    
    def get_status(self):
        csFormat = "{} {} {}{}"
        status = csFormat.format(self.name,
                                 self.get_hp_and_ac(),
                                 '\n> ' + self.notes if self.notes is not '' else '',
                                 ('\n* ' + '\n* '.join([e.name + (" [{} rounds]".format(e.remaining) if e.remaining >= 0 else '') for e in self.effects])) if len(self.effects) is not 0 else '')
        return status
    
    def get_short_status(self):
        status = "{}: {} {}({})".format(self.init,
                                          self.name,
                                          self.get_hp() + ' ' if self.get_hp() is not '' else '',
                                          self.get_effects_and_notes())
        return status
    
class DicecloudCombatant(Combatant):
    def __init__(self, init:int=0, author:discord.User=None, notes:str='', effects=[], private:bool=False, group:str=None, sheet=None):
        self.init = init
        self.name = sheet.get('stats', {}).get('name', 'Unknown')
        self.author = author
        self.mod = sheet.get('skills', {}).get('initiative', 0)
        self.notes = notes
        self.effects = effects
        self.hp = sheet.get('hp')
        self.max_hp = sheet.get('hp')
        self.ac = sheet.get('armor')
        self.private = private
        self.group = group
        self.resist = sheet.get('resist', [])
        self.immune = sheet.get('immune', [])
        self.vuln = sheet.get('vuln', [])
        self.sheet = sheet
        
    def __str__(self):
        return self.name
    
class MonsterCombatant(Combatant):
    def __init__(self, name:str='', init:int=0, author:discord.User=None, notes:str='', effects=[], private:bool=True, group:str=None, modifier:int=0, monster=None):
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
        self.monster = monster
        
    def get_status(self):
        csFormat = "{} {} {}{}{}"
        status = csFormat.format(self.name,
                                 self.get_hp_and_ac(),
                                 '\n> ' + self.notes if self.notes is not '' else '',
                                 ('\n* ' + '\n* '.join([e.name + (" [{} rounds]".format(e.remaining) if e.remaining >= 0 else '') for e in self.effects])) if len(self.effects) is not 0 else '',
                                 "\n- This combatant will be automatically removed if they remain below 0 HP." if self.hp <= 0 else "")
        return status
        
    def __str__(self):
        return self.name
    
class Effect(object):
    def __init__(self, duration:int=-1, name:str='', desc:str='', remaining:int=-1):
        self.name = name
        self.duration = duration
        self.remaining = remaining
        self.desc = desc
        
    def __str__(self):
        return self.name

class InitTracker:
    '''
    Initiative tracking commands. Use !help init for more details.
    To use, first start combat in a channel by saying "!init begin".
    Then, each combatant should add themselves to the combat with "!init add <MOD> <NAME>".
    To hide a combatant's HP, add them with "!init add <MOD> <NAME> -h".
    Once every combatant is added, each combatant should set their max hp with "!init hp <NAME> max <MAXHP>".
    Then, you can proceed through combat with "!init next".
    Once combat ends, end combat with "!init end".
    For more help, the !help command shows applicable arguments for each command.
    '''

    def __init__(self, bot):
        self.bot = bot
        self.combats = []  # structure: array of dicts with structure {channel (Channel/Member), combatants (list of dict, [{init, name, author, mod, notes, effects}]), current (int), round (int)}
        self.bot.loop.create_task(self.panic_load())
        
    def parse_cvars(self, args, _id, character, char_id):
        tempargs = []
        user_cvars = copy.copy(self.bot.db.not_json_get('char_vars', {}).get(_id, {}).get(char_id, {}))
        stat_vars = {}
        stats = copy.copy(character['stats'])
        for stat in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'):
            stats[stat+'Score'] = stats[stat]
            del stats[stat]
        stat_vars.update(stats)
        stat_vars.update(character['levels'])
        stat_vars['hp'] = character['hp']
        stat_vars['armor'] = character['armor']
        stat_vars.update(character['saves'])
        for arg in args:
            for var in re.finditer(r'{([^{}]+)}', arg):
                raw = var.group(0)
                out = var.group(1)
                for cvar, value in user_cvars.items():
                    out = out.replace(cvar, str(value))
                for cvar, value in stat_vars.items():
                    out = out.replace(cvar, str(value))
                arg = arg.replace(raw, '{}'.format(roll(out).total))
            for var in re.finditer(r'<([^<>]+)>', arg):
                raw = var.group(0)
                out = var.group(1)
                for cvar, value in user_cvars.items():
                    out = out.replace(cvar, str(value))
                for cvar, value in stat_vars.items():
                    out = out.replace(cvar, str(value))
                arg = arg.replace(raw, out)
            tempargs.append(arg)
        return tempargs
        
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
    async def begin(self, ctx, *, args:str=''):
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
        if '-dyn' in args:  # rolls a d100 instead of a d20 and multiplies modifier by 5
            options['dynamic'] = True
        if '--name' in args:
            try:
                a = args[args.index('--name') + 1]
                name = a if a is not None else name
            except IndexError:
                await self.bot.say("You must pass in a name with the --name tag.")
                return
        combat = Combat(channel=ctx.message.channel, combatants=[], init=0, init_round=1, options=options, name=capwords(name))
        self.combats.append(combat)
        summaryMsg = await self.bot.say(combat.getSummary())
        combat.summary_message = summaryMsg
        combat.dm = ctx.message.author
        try:
            await self.bot.pin_message(summaryMsg)
        except:
            pass
        await self.bot.say("Everyone roll for initiative!\nIf you have a character set up with SheetManager: `!init dcadd`\nIf it's a 5e monster: `!init madd [monster name]`\nOtherwise: `!init add [modifier] [name]`")
            
    @init.command(pass_context=True)
    async def add(self, ctx, modifier : int, name : str, *, args:str=''):
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
        args = shlex.split(args.lower())
        
        if '-h' in args:
            private = True
        if '-p' in args:
            place = True
        if '--controller' in args:
            try:
                controllerStr = args[args.index('--controller') + 1]
                controllerEscaped = controllerStr.replace('<', '').replace('>', '').replace('@', '').replace('!', '')
                a = ctx.message.server.get_member(controllerEscaped)
                b = ctx.message.server.get_member_named(controllerStr)
                controller = a if a is not None else b if b is not None else controller
            except IndexError:
                await self.bot.say("You must pass in a controller with the --controller tag.")
                return
        if '--group' in args:
            try:
                group = capwords(args[args.index('--group') + 1])
            except IndexError:
                await self.bot.say("You must pass in a group with the --group tag.")
                return
        if '--hp' in args:
            try:
                hp = int(args[args.index('--hp') + 1])
                if hp < 1:
                    hp = None
                    raise Exception
            except:
                await self.bot.say("You must pass in a positive, nonzero HP with the --hp tag.")
                return
        if '--ac' in args:
            try:
                ac = int(args[args.index('--ac') + 1])
            except:
                await self.bot.say("You must pass in an AC with the --ac tag.")
                return
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return
        
        if combat.get_combatant(name) is not None:
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
            me = Combatant(name=name, init=init, author=controller, mod=modifier, effects=[], notes='', private=private, hp=hp, max_hp=hp, group=group, ac=ac)
            if group is None:
                combat.combatants.append(me)
                await self.bot.say("{}\n{} was added to combat with initiative {}.".format(controller.mention, name, init), delete_after=10)
            elif combat.get_combatant_group(group) is None:
                newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
                newGroup.combatants.append(me)
                combat.combatants.append(newGroup)
                await self.bot.say("{}\n{} was added to combat as part of group {}, with initiative {}.".format(controller.mention, name, group, init), delete_after=10)
            else:
                group = combat.get_combatant_group(group)
                group.combatants.append(me)
                await self.bot.say("{}\n{} was added to combat as part of group {}.".format(controller.mention, name, group.name), delete_after=10)
        except Exception as e:
            await self.bot.say("Error adding combatant: {}".format(e))
            return
        
        await combat.update_summary(self.bot)
        combat.sortCombatants()
        
    @init.command(pass_context=True, name='cadd', aliases=['dcadd'])
    async def dcadd(self, ctx, *, args:str=''):
        """Adds the current active character to combat. A character must be loaded through the SheetManager module first.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -p [init value]
              -h (same as !init add)
              --group (same as !init add)"""
        user_characters = self.bot.db.not_json_get(ctx.message.author.id + '.characters', {})
        active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
        if active_character is None:
            return await self.bot.say('You have no characters loaded.')
        character = user_characters[active_character]
        skills = character.get('skills')
        if skills is None:
            return await self.bot.say('You must update your character sheet first.')
        skill = 'initiative'
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return
        
        if combat.get_combatant(character.get('stats', {}).get('name')) is not None:
            await self.bot.say("Combatant already exists.")
            return
        
        embed = discord.Embed()
        embed.colour = random.randint(0, 0xffffff) if character.get('settings', {}).get('color') is None else character.get('settings', {}).get('color')
        
        args = shlex.split(args)
        args = parse_args(args)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = args.get('b', None)
        p = args.get('p', None)
        phrase = args.get('phrase', None)
        
        if p is None:
            if b is not None:
                check_roll = roll('1d20' + '{:+}'.format(skills[skill]) + '+' + b, adv=adv, inline=True)
            else:
                check_roll = roll('1d20' + '{:+}'.format(skills[skill]), adv=adv, inline=True)
            
            embed.title = '{} makes an {} check!'.format(character.get('stats', {}).get('name'),
                                                        re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', skill).title())
            embed.description = check_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
            init = check_roll.total
        else:
            init = int(p)
            embed.title = "{} already rolled initiative!".format(character.get('stats', {}).get('name'))
            embed.description = "Placed at initiative `{}`.".format(init)
        
        group = args.get('group')
        controller = ctx.message.author
        
        me = DicecloudCombatant(init=init, author=ctx.message.author, effects=[], notes='', private=args.get('h', False), group=args.get('group', None), sheet=character)
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
    async def madd(self, ctx, monster_name:str, *, args:str=''):
        """Adds a monster to combat.
        Args: adv/dis
              -b [conditional bonus]
              -n [number of monsters]
              -p [init value]
              --name [name scheme, use "#" for auto-numbering, ex. "Orc#"]
              -h (same as !init add, default true)
              --group (same as !init add)"""
        
        monster = searchMonster(monster_name, return_monster=True, visible=True)
        self.bot.botStats["monsters_looked_up_session"] += 1
        self.bot.db.incr("monsters_looked_up_life")
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        dexMod = floor((int(monster['dex']) - 10) / 2)

        args = shlex.split(args)
        args = parse_args(args)
        private = args.get('h', True)
        group = args.get('group')
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv', False) else -1 if args.get('dis', False) else 0
        b = args.get('b', None)
        p = args.get('p', None)
        
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return
        
        out = ''
        recursion = int(args.get('n', 1))
        recursion = 25 if recursion > 25 else 1 if recursion < 1 else recursion
        
        for i in range(recursion):
            name = args.get('name', monster['name'][:2].upper() + '#').replace('#', str(i + 1))
            if combat.get_combatant(name) is not None:
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
                me = MonsterCombatant(name=name, init=init, author=controller, effects=[], notes='', private=private, group=group, monster=monster, modifier=dexMod)
                if group is None:
                    combat.combatants.append(me)
                    out += "{} was added to combat with initiative {}.\n".format(name, check_roll.skeleton if p is None else p)
                elif combat.get_combatant_group(group) is None:
                    newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
                    newGroup.combatants.append(me)
                    combat.combatants.append(newGroup)
                    out += "{} was added to combat as part of group {}, with initiative {}.\n".format(name, group, check_roll.skeleton if p is None else p)
                else:
                    temp_group = combat.get_combatant_group(group)
                    temp_group.combatants.append(me)
                    out += "{} was added to combat as part of group {}.\n".format(name, temp_group.name)
            except Exception as e:
                traceback.print_exc()
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
        except IndexError:
            combat.current = combat.sorted_combatants[0].init
            combat.round += 1
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
                                   nextCombatant.author.mention,
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
        
    @init.command(pass_context=True, name="list")
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
    async def note(self, ctx, combatant : str, *, note : str=''):
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
        await self.bot.say("Added note.", delete_after=10)
        await combat.update_summary(self.bot)
        
    @init.command(pass_context=True, aliases=['opts'])
    async def opt(self, ctx, combatant : str, *, args : str):
        """Edits the options of a combatant.
        Usage: !init opt <NAME> <ARGS>
        Valid Arguments:    -h (hides HP)
                            -p (changes init)
                            --controller <CONTROLLER> (pings a different person on turn)
                            --ac <AC> (changes combatant AC)
                            --resist <RESISTANCE>
                            --immune <IMMUNITY>
                            --vuln <VULNERABILITY>"""
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
        args = parse_args(args)
        out = ''
        
        if args.get('h'):
            private = not private
            combatant.private = private
            out += "\u2705 Combatant {}.\n".format('hidden' if private else 'unhidden')
        if 'controller' in args:
            try:
                controllerStr = args.get('controller')
                controllerEscaped = controllerStr.replace('<', '').replace('>', '').replace('@', '').replace('!', '')
                a = ctx.message.server.get_member(controllerEscaped)
                b = ctx.message.server.get_member_named(controllerStr)
                combatant.author = a if a is not None else b if b is not None else controller
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
        if 'resist' in args:
            resist = args.get('resist')
            if resist in combatant.resist:
                combatant.resist.remove(resist)
                out += "\u2705 {} removed from combatant resistances.\n".format(resist)
            else:
                combatant.resist.append(resist)
                out += "\u2705 {} added to combatant resistances.\n".format(resist)
        if 'immune' in args:
            immune = args.get('immune')
            if immune in combatant.immune:
                combatant.immune.remove(immune)
                out += "\u2705 {} removed from combatant immunities.\n".format(immune)
            else:
                combatant.immune.append(immune)
                out += "\u2705 {} added to combatant immunities.\n".format(immune)
        if 'vuln' in args:
            vuln = args.get('vuln')
            if vuln in combatant.vuln:
                combatant.vuln.remove(vuln)
                out += "\u2705 {} removed from combatant vulnerabilities.\n".format(vuln)
            else:
                combatant.vuln.append(vuln)
                out += "\u2705 {} added to combatant vulnerabilities.\n".format(vuln)
        
        await self.bot.say("Combatant options updated.\n" + out, delete_after=10)
        await combat.update_summary(self.bot)
        
    @init.command(pass_context=True)
    async def status(self, ctx, combatant : str, *, args:str=''):
        """Gets the status of a combatant.
        Usage: !init status <NAME> <ARGS (opt)>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        
        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return
        
        if 'private' in args.lower():
            await self.bot.send_message(combatant.author, "```markdown\n" + combatant.get_status(private=True) + "```")
        else:
            await self.bot.say("```markdown\n" + combatant.get_status() + "```", delete_after=30)
        
    @init.command(pass_context=True)
    async def hp(self, ctx, combatant : str, operator : str, *, hp : str = ''):
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
                await self.bot.send_message(combatant.author, "{}'s HP: {}/{}".format(combatant.name, combatant.hp, combatant.max_hp))
            except:
                pass
        await combat.update_summary(self.bot)
        
    @init.command(pass_context=True)
    async def effect(self, ctx, combatant : str, duration : int, effect : str, *, desc : str=''):
        """Attaches a status effect to a combatant.
        Usage: !init effect <NAME> <DURATION (rounds)> <EFFECT> <DESC (opt)>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        
        combatant = combat.get_combatant(combatant)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return
        
        if effect.lower() in (e.name.lower() for e in combatant.effects):
            return await self.bot.say("Effect already exists.", delete_after=10)
        
        effectObj = Effect(duration=duration, name=effect, desc=desc, remaining=duration)
        combatant.effects.append(effectObj)
        await self.bot.say("Added effect {} to {}.".format(effect, combatant.name), delete_after=10)
        await combat.update_summary(self.bot)
        
    @init.command(pass_context=True, name='re')
    async def remove_effect(self, ctx, combatant:str, effect:str=''):
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
        Valid Arguments: see !a and !ma."""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        target = combat.get_combatant(target_name)
        if target is None:
            await self.bot.say("Target not found.")
            return
        combatant = combat.currentCombatant
        if combatant is None:
            return await self.bot.say("You must begin combat with !init next first.")
        
        if isinstance(combatant, DicecloudCombatant):
            attacks = combatant.sheet.get('attacks') # get attacks
            try: #fuzzy search for atk_name
                attack = next(a for a in attacks if atk_name.lower() == a.get('name').lower())
            except StopIteration:
                try:
                    attack = next(a for a in attacks if atk_name.lower() in a.get('name').lower())
                except StopIteration:
                    return await self.bot.say('No attack with that name found.')
                    
            args = shlex.split(args)
            tempargs = []
            for arg in args: # parse snippets
                for snippet, arguments in self.bot.db.not_json_get('damage_snippets', {}).get(ctx.message.author.id, {}).items():
                    if arg == snippet: 
                        tempargs += shlex.split(arguments)
                        break
                tempargs.append(arg)
            active_character = self.bot.db.not_json_get('active_characters', {}).get(ctx.message.author.id)
            tempargs = self.parse_cvars(tempargs, ctx.message.author.id, combatant.sheet, active_character)
            args = parse_args_2(tempargs)
            if attack.get('details') is not None:
                attack['details'] = self.parse_cvars([attack['details']], ctx.message.author.id, combatant.sheet, active_character)[0]
            args['name'] = combatant.sheet.get('stats', {}).get('name', "NONAME")
            if target.ac is not None: args['ac'] = target.ac
            args['t'] = target.name
            args['resist'] = args.get('resist') or '|'.join(target.resist)
            args['immune'] = args.get('immune') or '|'.join(target.immune)
            args['vuln'] = args.get('vuln') or '|'.join(target.vuln)
            result = sheet_attack(attack, args)
            result['embed'].colour = random.randint(0, 0xffffff) if combatant.sheet.get('settings', {}).get('color') is None else combatant.sheet.get('settings', {}).get('color')
            if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']
        elif isinstance(combatant, MonsterCombatant):
            attacks = combatant.monster.get('attacks') # get attacks
            attack = fuzzy_search(attacks, 'name', atk_name)
            if attack is None:
                return await self.bot.say("No attack with that name found.", delete_after=15)
            attack['details'] = attack.get('desc')
                    
            args = shlex.split(args)
            args = parse_args_2(args)
            args['name'] = a_or_an(combatant.monster.get('name')).title()
            if target.ac is not None: args['ac'] = target.ac
            args['t'] = target.name
            args['resist'] = args.get('resist') or '|'.join(target.resist)
            args['immune'] = args.get('immune') or '|'.join(target.immune)
            args['vuln'] = args.get('vuln') or '|'.join(target.vuln)
            result = sheet_attack(attack, args)
            result['embed'].colour = random.randint(0, 0xffffff)
            if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']
        elif isinstance(combatant, CombatantGroup):
            attacks = []
            for c in combatant.combatants:
                if isinstance(c, DicecloudCombatant):
                    attacks += c.sheet.get('attacks', [])
                elif isinstance(c, MonsterCombatant):
                    attacks += c.monster.get('attacks', [])
            attack = fuzzy_search(attacks, 'name', atk_name)
            if attack is None:
                return await self.bot.say("No attack with that name found.", delete_after=15)
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
            return await self.bot.say('Integrated attacks are only supported for combatants added via `madd` or `dcadd`.', delete_after=15)
        embed = result['embed']
        if target.ac is not None:
            if target.hp is not None:
                embed.set_footer(text="{}: {}".format(target.name, target.get_hp()))
                if target.private:
                    try:
                        await self.bot.send_message(target.author, "{}'s HP: {}/{}".format(target.name, target.hp, target.max_hp))
                    except:
                        pass
            else:
                embed.set_footer(text="Dealt {} damage to {}!".format(result['total_damage'], target.name))
        else: embed.set_footer(text="Target AC not set.")
        await self.bot.say(embed=embed)
        await combat.update_summary(self.bot)
        
    @init.command(pass_context=True, hidden=True)
    async def sim(self, ctx):
        """Simulates the current turn of combat.
        MonsterCombatants will target any non-monster combatant, and DicecloudCombatants will target any monster combatants."""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        current = combat.currentCombatant
        if isinstance(current, CombatantGroup):
            thisTurn = [c for c in current.combatants]
        else:
            thisTurn = [current]
        for current in thisTurn:
            await asyncio.sleep(1) #select target
            isMonster = isinstance(current, MonsterCombatant)
            numAtks = 1
            if isMonster: # TODO: better multiattack parsing
                if 'multiattack' in [a.get('name', '').lower() for a in current.monster.get('action', [{}])]:
                    ma_text = next(''.join(a.get('text')) for a in current.monster.get('action', [{}]) if a['name'].lower() == 'multiattack')
                    ma_text = text_to_numbers(ma_text)
                    numAtks = int(re.search(r'\d+', ma_text).group())
            for a in range(numAtks):
                await asyncio.sleep(1) #select attack
                if isMonster:
                    targets = [c for c in combat.combatants if not isinstance(c, MonsterCombatant)]
                else:
                    targets = [c for c in combat.combatants if isinstance(c, MonsterCombatant)]
                if len(targets) == 0:
                    await self.bot.say("```diff\n+ {} sees no targets!\n```".format(current.name))
                    break
                target = random.choice(targets)
                await self.bot.say("```diff\n+ {} swings at {}!```".format(current.name, target.name))
                
                if isinstance(current, DicecloudCombatant):
                    attacks = current.sheet.get('attacks') # get attacks
                    attacks = [a for a in attacks if a.get('attackBonus') is not None]
                    if len(attacks) < 1:
                        await self.bot.say("```diff\n- {} has no attacks!```".format(current.name))
                        break
                    attack = random.choice(attacks)
                    args = {}
                    args['name'] = current.sheet.get('stats', {}).get('name', "NONAME")
                    if target.ac is not None: args['ac'] = target.ac
                    args['t'] = target.name
                    result = sheet_attack(attack, args)
                    result['embed'].colour = random.randint(0, 0xffffff) if current.sheet.get('settings', {}).get('color') is None else current.sheet.get('settings', {}).get('color')
                    target.hp -= result['total_damage']
                elif isinstance(current, MonsterCombatant):
                    attacks = current.monster.get('attacks') # get attacks
                    attacks = [a for a in attacks if a.get('attackBonus') is not None]
                    if len(attacks) < 1:
                        await self.bot.say("```diff\n- {} has no attacks!```".format(current.name))
                        break
                    attack = random.choice(attacks)
                    args = {}
                    args['name'] = a_or_an(current.monster.get('name')).title()
                    if target.ac is not None: args['ac'] = target.ac
                    args['t'] = target.name
                    result = sheet_attack(attack, args)
                    result['embed'].colour = random.randint(0, 0xffffff)
                    if target.ac is not None: target.hp -= result['total_damage']
                else:
                    return await self.bot.say('Integrated attacks are only supported for combatants added via `madd` or `dcadd`.', delete_after=15)
                embed = result['embed']
                if target.ac is not None: 
                    embed.set_footer(text="{}: {}".format(target.name, target.get_hp()))
                else: embed.set_footer(text="Target AC not set.")
                killed = "\n- Killed {}!".format(target.name) if target.hp <= 0 else ""
                if target.hp <= 0:
                    if target.group is None:
                        combat.combatants.remove(target)
                    else:
                        group = combat.get_combatant_group(target.group)
                        group.combatants.remove(target)
                    combat.sortCombatants()
                    combat.checkGroups()
                await self.bot.say("```diff\n- Dealt {} damage!{}```".format(result['total_damage'], killed), embed=embed)
                await combat.update_summary(self.bot)
        
    @init.command(pass_context=True, name='remove')
    async def remove_combatant(self, ctx, *, name : str):
        """Removes a combatant from the combat.
        Usage: !init remove <NAME>"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        
        combatant = combat.get_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return
        if combatant == combat.currentCombatant:
            return await self.bot.say("You cannot remove a combatant on their own turn.")
        
        for e in combatant.effects:
            combatant.effects.remove(e)
        
        if combatant.group is None:
            combat.combatants.remove(combatant)
        else:
            group = combat.get_combatant_group(combatant.group)
            if len(group.combatants) <= 1:
                return await self.bot.say("You cannot remove a combatant if they are the only remaining combatant in this turn.")
            group.combatants.remove(combatant)
        await self.bot.say("{} removed from combat.".format(combatant.name), delete_after=10)
        await combat.update_summary(self.bot)
        combat.sortCombatants()
        combat.checkGroups()
        
    @init.command(pass_context=True)
    async def end(self, ctx):
        """Ends combat in the channel.
        Usage: !init end"""
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
                    await self.bot.send_message(c.author, "{}'s final HP: {}".format(c.name, c.get_hp(True)))
                except:
                    pass
        
        try:
            await self.bot.edit_message(combat.summary_message, combat.summary_message.content + "\n```-----COMBAT ENDED-----```")
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
        temp_key = []
        for combat in self.combats:
            combat.combatantGenerator = None
            path = '{}.avrae'.format(combat.channel.id)
            self.bot.db.set(path, pickle.dumps(combat, pickle.HIGHEST_PROTOCOL).decode('cp437'))
            print("PANIC BEFORE EXIT - Saved combat for {}!".format(combat.channel.id))
            temp_key.append(combat.channel.id)
        self.bot.db.jsetex('temp_combatpanic.{}'.format(getattr(self.bot, 'shard_id', 0)), temp_key, 120) # timeout in 2 minutes
        
    async def panic_load(self):
        await self.bot.wait_until_ready()
        combats = self.bot.db.jget('temp_combatpanic.{}'.format(getattr(self.bot, 'shard_id', 0)), [])
        for c in combats:
            if self.bot.get_channel(c) is None:
                print('Shard check for {} failed, aborting.'.format(c))
                continue
            path = '{}.avrae'.format(c)
            combat = self.bot.db.get(path, None)
            if combat is None:
                print('Combat not found reloading {}, aborting'.format(c))
                continue
            combat = pickle.loads(combat.encode('cp437'))
            combat.channel = self.bot.get_channel(combat.channel.id)
            if combat.channel is None:
                print('Combat channel not found reloading {}, aborting'.format(c))
                continue
            self.combats.append(combat)
            try:
                if combat.summary_message is not None:
                    combat.summary_message = await self.bot.get_message(combat.channel, combat.summary_message.id)
            except NotFound:
                print('Summary Message not found reloading {}'.format(c))
            except:
                pass
            print("Autoreloaded {}".format(c))
            await self.bot.send_message(combat.channel, "Combat automatically reloaded after bot restart!")
        self.bot.db.delete('temp_combatpanic.{}'.format(getattr(self.bot, 'shard_id', 0)))
            
    @init.command(pass_context=True, hidden=True)
    async def save(self, ctx):
        """Saves combat to a file for long-term storage.
        Usage: !init save"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        path = '{}.avrae'.format(ctx.message.channel.id)
        self.bot.db.set(path, pickle.dumps(combat, pickle.HIGHEST_PROTOCOL).decode('cp437'))
        await self.bot.say("Combat saved.")
        
    @init.command(pass_context=True, hidden=True)
    async def load(self, ctx):
        """Loads combat from a file.
        Usage: !init load"""
        if [c for c in self.combats if c.channel is ctx.message.channel]:
            await self.bot.say("You are already in combat. To end combat, use \"!init end\".")
            return
        path = '{}.avrae'.format(ctx.message.channel.id)
        combat = self.bot.db.get(path, None)
        if combat is None:
            return await self.bot.say("No combat saved.")
        combat = pickle.loads(combat.encode('cp437'))
        combat.channel = ctx.message.channel
        self.combats.append(combat)
        summaryMsg = await self.bot.say(combat.getSummary())
        combat.summary_message = summaryMsg
        try:
            await self.bot.pin_message(summaryMsg)
        except:
            pass
        await self.bot.say("Combat loaded.")
