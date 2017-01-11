'''
Created on Sep 18, 2016

@author: andrew
'''
import asyncio
from os.path import isfile
import pickle
import random
import shlex
from string import capwords

import discord
from discord.ext import commands

from utils.functions import make_sure_path_exists, discord_trim
import signal


class Combat(object):
    def __init__(self, channel:discord.Channel, combatants=[], init:int=0, init_round:int=0, summary_message=None, options={}, name=""):
        self.channel = channel
        self.combatants = combatants
        self.sorted_combatants = None
        self.combatantGenerator = None
        self.current = init
        self.round = init_round
        self.summary_message = summary_message
        self.options = options
        self.name = name
        
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
        except:
            pass
        return combatant
    
    def get_combatant_group(self, name):
        group = None
        try:
            group = next(c for c in self.combatants if c.name.lower() == name.lower() and isinstance(c, CombatantGroup))
        except:
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
    
    def getNextCombatant(self):
        if self.sorted_combatants is None:
            self.sortCombatants()
        for c in self.sorted_combatants:
            yield c
    
    async def update_summary(self, bot):
        await bot.edit_message(self.summary_message, self.getSummary())
        
class CombatantGroup(object):
    def __init__(self, init:int=0, name:str='', author:discord.User=None, notes:str=''):
        self.init = init
        self.name = name
        self.author = author
        self.notes = notes
        self.mod = 0 #only needed for sorting in Combat, should always be 0
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
    def __init__(self, init:int=0, name:str='', author:discord.User=None, mod:int=0, notes:str='', effects=[], hp:int=None, max_hp:int=None, private:bool=False):
        self.init = init
        self.name = name
        self.author = author
        self.mod = mod
        self.notes = notes
        self.effects = effects
        self.hp = hp
        self.max_hp = max_hp
        self.private = private
        
    def __str__(self):
        return self.name
    
    def get_effect(self, name):
        effect = None
        try:
            effect = next(c for c in self.effects if c.name.lower() == name.lower())
        except:
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
        for e in self.effects:
            out.append('{} [{} rds]'.format(e.name, e.remaining if not e.remaining < 0 else '∞'))
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
    
    def get_status(self):
        csFormat = "{} {} {}{}"
        status = csFormat.format(self.name,
                                 self.get_hp(),
                                 '\n> ' + self.notes if self.notes is not '' else '',
                                 ('\n* ' + '\n* '.join([e.name + (" [{} rounds]".format(e.remaining) if e.remaining >= 0 else '') for e in self.effects])) if len(self.effects) is not 0 else '')
        return status
    
    def get_short_status(self):
        status = "{}: {} {}({})".format(self.init,
                                          self.name,
                                          self.get_hp() + ' ' if self.get_hp() is not '' else '',
                                          self.get_effects_and_notes())
        return status
    
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
    Initiative tracking commands.
    To use, first start combat in a channel by saying "!init begin".
    Then, each combatant should add themselves to the combat with "!init add <MOD> <NAME>".
    To hide a combatant's HP, add them with "!init add <MOD> <NAME> -h".
    Once every combatant is added, each combatant should set their max hp with "!init hp <NAME> max <MAXHP>".
    Then, you can proceed through combat with "!init next".
    Once combat ends, end combat with "!init end".
    For more help, the .help command shows applicable arguments for each command.
    '''

    def __init__(self, bot):
        self.bot = bot
        self.combats = []  # structure: array of dicts with structure {channel (Channel/Member), combatants (list of dict, [{init, name, author, mod, notes, effects}]), current (int), round (int)}
        
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
                            --name <NAME> (names the combat)"""
        if [c for c in self.combats if c.channel is ctx.message.channel]:
            await self.bot.say("You are already in combat. To end combat, use \"!init end\".")
            return
        options = {}
        name = ''
        args = shlex.split(args.lower())
        if '-1' in args:  # rolls a d100 instead of a d20 and multiplies modifier by 5
            options['d100_init'] = True
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
        try:
            await self.bot.pin_message(summaryMsg)
        except:
            pass
        await self.bot.say("Everyone roll for initiative! (\"!init add <MODIFIER> <NAME>\")")
            
    @init.command(pass_context=True)
    async def add(self, ctx, modifier : int, name : str, *, args:str=''):
        """Adds a combatant to the initiative order.
        Usage: !init add <MODIFIER> <NAME> <ARGS (opt)>
        Valid Arguments:    -h (hides HP)
                            -p (places at given number instead of rolling)
                            --controller <CONTROLLER> (pings a different person on turn)
                            --group <GROUP> (adds the combatant to a group)
                            --hp <HP> (starts with HP)"""
        private = False
        place = False
        controller = ctx.message.author
        group = None
        hp = None
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
            me = Combatant(name=name, init=init, author=controller, mod=modifier, effects=[], notes='', private=private, hp=hp, max_hp=hp)
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
        
    @init.command(pass_context=True, name="next", aliases=['n'])
    async def nextInit(self, ctx):
        """Moves to the next turn in initiative order.
        Usage: !init next"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat. Please start combat with \"!init begin\".")
            return
        
        if len(combat.combatants) == 0:
            await self.bot.say("There are no combatants.")
            return
        if combat.combatantGenerator is None:
            combat.combatantGenerator = combat.getNextCombatant()
        try:
            nextCombatant = next(combat.combatantGenerator)
            combat.current = nextCombatant.init
        except StopIteration:
            combat.combatantGenerator.close()
            combat.combatantGenerator = combat.getNextCombatant()
            combat.current = combat.sorted_combatants[0].init
            combat.round += 1
            nextCombatant = next(combat.combatantGenerator)
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
        
    @init.command(pass_context=True)
    async def opt(self, ctx, combatant : str, *, args : str):
        """Edits the options of a combatant.
        Usage: !init opt <NAME> <ARGS>
        Valid Arguments:    -h (hides HP)
                            --controller <CONTROLLER> (pings a different person on turn)"""
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
        
        if '-h' in args:
            private = not private
            combatant.private = private
        if '--controller' in args:
            try:
                controllerStr = args[args.index('--controller') + 1]
                controllerEscaped = controllerStr.replace('<', '').replace('>', '').replace('@', '').replace('!', '')
                a = ctx.message.server.get_member(controllerEscaped)
                b = ctx.message.server.get_member_named(controllerStr)
                combatant.author = a if a is not None else b if b is not None else controller
            except IndexError:
                await self.bot.say("You must pass in a controller with the --controller tag.")
                return
        
        await self.bot.say("Combatant options updated.", delete_after=10)
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
    async def hp(self, ctx, combatant : str, operator : str, hp : int):
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
        
        if 'mod' in operator.lower():
            combatant.hp += hp
        elif 'set' in operator.lower():
            combatant.hp = hp
        elif 'max' in operator.lower():
            if hp < 1:
                await self.bot.say("You can't have a negative max HP!")
            elif combatant.hp is None:
                combatant.hp = hp
                combatant.max_hp = hp
            else:
                combatant.max_hp = hp
        else:
            await self.bot.say("Incorrect operator. Use mod, set, or max.")
            return
        
        await self.bot.say("{}: {}".format(combatant.name, combatant.get_hp()), delete_after=10)
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
            for e in combatant.effects:
                combatant.effects.remove(e)
            await self.bot.say("All effects removed from {}.".format(combatant.name), delete_after=10)
        elif to_remove is None:
            await self.bot.say("Effect not found.")
            return
        else:
            combatant.effects.remove(to_remove)
            await self.bot.say('Effect {} removed from {}.'.format(to_remove.name, combatant.name), delete_after=10)
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
        
        for e in combatant.effects:
            combatant.effects.remove(e)
        
        combat.combatants.remove(combatant)
        await self.bot.say("{} removed from combat.".format(name), delete_after=10)
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
        
        for c in combat.combatants:
            del c
        
        await self.bot.edit_message(combat.summary_message, "```-----COMBAT ENDED-----```")
        try:
            await self.bot.unpin_message(combat.summary_message)
        except:
            pass
        
        try:
            self.combats.remove(combat)
        except:
            await self.bot.say("Failed to end combat.")
        else:
            await self.bot.say("Combat ended.")
            
    def __unload(self):
        make_sure_path_exists('./saves/init/')
        for combat in self.combats:
            combat.combatantGenerator = None
            path = '{}.avrae'.format(combat.channel.id)
            self.bot.db.set(path, pickle.dumps(combat, pickle.HIGHEST_PROTOCOL).decode('cp437'))
            print("PANIC BEFORE EXIT - Saved combat for {}!".format(combat.channel.id))
            
    @init.command(pass_context=True)
    async def save(self, ctx):
        """Saves combat to a file for long-term storage.
        Usage: !init save"""
        try:
            combat = next(c for c in self.combats if c.channel is ctx.message.channel)
        except StopIteration:
            await self.bot.say("You are not in combat.")
            return
        combat.combatantGenerator = None
        path = '{}.avrae'.format(ctx.message.channel.id)
        self.bot.db.set(path, pickle.dumps(combat, pickle.HIGHEST_PROTOCOL).decode('cp437'))
        await self.bot.say("Combat saved.")
        
    @init.command(pass_context=True)
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
