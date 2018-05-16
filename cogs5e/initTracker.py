import copy
import logging
import random
import re
import shlex
import traceback

import discord
from discord.ext import commands

from cogs5e.funcs.dice import roll, SingleDiceGroup
from cogs5e.funcs.lookupFuncs import searchCharacterSpellName, searchSpellNameFull, \
    select_monster_full, getSpell, c
from cogs5e.funcs.sheetFuncs import sheet_attack, spell_context
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import NoSpellDC, InvalidSaveType, SelectionException
from cogs5e.models.initiative import Combat, Combatant, MonsterCombatant, Effect, PlayerCombatant, CombatantGroup
from utils.functions import parse_args_3, confirm, get_selection, parse_args_2, parse_resistances, parse_snippets, \
    strict_search

log = logging.getLogger(__name__)


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
        Valid Arguments: -dyn (dynamic init; rerolls all initiatives at the start of a round)
                         -name <NAME> (names the combat)
                         -turnnotif (notifies the next player)"""
        Combat.ensure_unique_chan(ctx)

        options = {}
        name = 'Current initiative'
        args = shlex.split(args.lower())
        if '-dyn' in args:  # rerolls all inits at the start of each round
            options['dynamic'] = True
        if '-name' in args:
            try:
                a = args[args.index('-name') + 1]
                options['name'] = a if a is not None else name
            except IndexError:
                await self.bot.say("You must pass in a name with the -name tag.")
                return
        if '-turnnotif' in args:
            options['turnnotif'] = True

        temp_summary_msg = await self.bot.say("```Awaiting combatants...```")
        Combat.message_cache[temp_summary_msg.id] = temp_summary_msg  # add to cache

        combat = Combat.new(ctx.message.channel.id, temp_summary_msg.id, ctx.message.author.id, options, ctx)
        await combat.final()

        try:
            await self.bot.pin_message(temp_summary_msg)
        except:
            pass
        await self.bot.say(
            "Everyone roll for initiative!\nIf you have a character set up with SheetManager: `!init join`\n"
            "If it's a 5e monster: `!init madd [monster name]`\nOtherwise: `!init add [modifier] [name]`")

    @init.command(pass_context=True)
    async def add(self, ctx, modifier: int, name: str, *args):
        """Adds a combatant to the initiative order.
        If a character is set up with the SheetManager module, you can use !init dcadd instead.
        If you are adding monsters to combat, you can use !init madd instead.
        Use !help init [dcadd|madd] for more help.
        Valid Arguments:    -h (hides HP)
                            -p (places at given number instead of rolling)
                            -controller <CONTROLLER> (pings a different person on turn)
                            -group <GROUP> (adds the combatant to a group)
                            -hp <HP> (starts with HP)
                            -ac <AC> (sets combatant AC)
                            -resist/immune/vuln <resistance>"""
        private = False
        place = False
        controller = ctx.message.author.id
        group = None
        hp = None
        ac = None
        resists = {}
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
                controller = a.id if a is not None else b.id if b is not None else controller
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

        for k in ('resist', 'immune', 'vuln'):
            resists[k] = args.get(k, [])

        combat = Combat.from_ctx(ctx)

        if combat.get_combatant(name) is not None:
            await self.bot.say("Combatant already exists.")
            return

        if not place:
            init = random.randint(1, 20) + modifier
        else:
            init = modifier
            modifier = 0

        me = Combatant.new(name, controller, init, modifier, hp, hp, ac, private, resists, [], [], ctx)

        if group is None:
            combat.add_combatant(me)
            await self.bot.say(
                "{}\n{} was added to combat with initiative {}.".format(f'<@{controller}>', name, init),
                delete_after=10)
        else:
            grp = combat.get_group(group, create=init)
            grp.add_combatant(me)
            await self.bot.say(
                "{}\n{} was added to combat with initiative {} as part of group {}.".format(me.controller_mention(),
                                                                                            name, grp.init,
                                                                                            grp.name),
                delete_after=10)

        await combat.final()

    @init.command(pass_context=True)
    async def madd(self, ctx, monster_name: str, *args):
        """Adds a monster to combat.
        Args: adv/dis
              -b [conditional bonus]
              -n [number of monsters]
              -p [init value]
              -name [name scheme, use "#" for auto-numbering, ex. "Orc#"]
              -h (same as !init add, default true)
              -group (same as !init add)
              -npr (removes physical resistances when added)
              -rollhp (rolls monster HP)
              -hp [starting hp]
              -ac [starting ac]"""

        monster = await select_monster_full(ctx, monster_name, pm=True)
        self.bot.db.incr("monsters_looked_up_life")

        dexMod = monster.skills['dexterity']

        args = parse_args_3(args)
        private = not bool(args.get('h', [False])[-1])

        group = args.get('group', [None])[-1]

        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0

        b = '+'.join(args.get('b', []))
        p = args.get('p', [None])[-1]
        rollhp = args.get('rollhp', [False])[-1]

        try:
            hp = args.get('hp', [None])[-1]
            ac = args.get('ac', [None])[-1]
        except (ValueError, TypeError):
            hp = None
            ac = None

        opts = {}
        if 'npr' in args:
            opts['npr'] = True

        combat = Combat.from_ctx(ctx)

        out = ''
        to_pm = ''
        try:
            recursion = int(args.get('n', [1])[-1])
        except ValueError:
            return await self.bot.say(args.get('n', [1])[-1] + " is not a number.")
        recursion = 25 if recursion > 25 else 1 if recursion < 1 else recursion

        name_num = 1
        for i in range(recursion):
            name = args.get('name', [monster.name[:2].upper() + '#'])[-1].replace('#', str(name_num))
            raw_name = args.get('name', [monster.name[:2].upper() + '#'])[-1]
            to_continue = False

            while combat.get_combatant(name) and name_num < 1000:  # keep increasing to avoid duplicates
                if '#' in raw_name:
                    name_num += 1
                    name = raw_name.replace('#', str(name_num))
                else:
                    out += "Combatant already exists.\n"
                    to_continue = True
                    break

            if to_continue:
                continue

            try:
                check_roll = None  # to make things happy
                if p is None:
                    if b:
                        check_roll = roll('1d20' + '{:+}'.format(dexMod) + '+' + b, adv=adv, inline=True)
                    else:
                        check_roll = roll('1d20' + '{:+}'.format(dexMod), adv=adv, inline=True)
                    init = check_roll.total
                else:
                    init = int(p)
                controller = ctx.message.author.id

                rolled_hp = None
                if rollhp:
                    rolled_hp = roll(monster.hitdice, inline=True)
                    to_pm += f"{name} began with {rolled_hp.skeleton} HP.\n"
                    rolled_hp = max(rolled_hp.total, 1)

                me = MonsterCombatant.from_monster(name, controller, init, dexMod, private, monster, ctx, opts,
                                                   hp=hp or rolled_hp, ac=ac)
                if group is None:
                    combat.add_combatant(me)
                    out += "{} was added to combat with initiative {}.\n".format(name,
                                                                                 check_roll.skeleton if p is None else p)
                else:
                    grp = combat.get_group(group, create=init)
                    grp.add_combatant(me)
                    out += "{} was added to combat with initiative {} as part of group {}.\n".format(
                        name, grp.init, grp.name)

            except Exception as e:
                log.error('\n'.join(traceback.format_exception(type(e), e, e.__traceback__)))
                out += "Error adding combatant: {}\n".format(e)

        await combat.final()
        await self.bot.say(out, delete_after=15)
        if to_pm:
            await self.bot.send_message(ctx.message.author, to_pm)

    @init.command(pass_context=True, name='join', aliases=['cadd', 'dcadd'])
    async def join(self, ctx, *, args: str = ''):
        """Adds the current active character to combat. A character must be loaded through the SheetManager module first.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -p [init value]
              -h (same as !init add)
              --group (same as !init add)"""
        char = Character.from_ctx(ctx)
        character = char.character

        if char.get_combat_id():
            return await self.bot.say(f"This character is already in a combat. "
                                      f"Please leave combat in <#{char.get_combat_id()}> first.\n"
                                      f"If this seems like an error, please `!update` your character sheet.")

        skills = character.get('skills')
        if skills is None:
            return await self.bot.say('You must update your character sheet first.')
        skill = 'initiative'

        embed = EmbedWithCharacter(char, False)
        embed.colour = char.get_color()

        skill_effects = character.get('skill_effects', {})
        args += ' ' + skill_effects.get(skill, '')  # dicecloud v7 - autoadv

        args = shlex.split(args)
        args = parse_args_3(args)
        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0
        b = '+'.join(args.get('b', [])) or None
        p = args.get('p', [None])[-1]
        phrase = '\n'.join(args.get('phrase', [])) or None

        if p is None:
            if b:
                bonus = '{:+}'.format(skills[skill]) + '+' + b
                check_roll = roll('1d20' + bonus, adv=adv, inline=True)
            else:
                bonus = '{:+}'.format(skills[skill])
                check_roll = roll('1d20' + bonus, adv=adv, inline=True)

            embed.title = '{} makes an Initiative check!'.format(char.get_name())
            embed.description = check_roll.skeleton + ('\n*' + phrase + '*' if phrase is not None else '')
            init = check_roll.total
        else:
            init = int(p)
            bonus = 0
            embed.title = "{} already rolled initiative!".format(char.get_name())
            embed.description = "Placed at initiative `{}`.".format(init)

        group = args.get('group', [None])[-1]
        controller = ctx.message.author.id
        private = bool(args.get('h', [False])[-1])
        bonus = roll(bonus).total

        me = PlayerCombatant.from_character(char.get_name(), controller, init, bonus, char.get_ac(), private,
                                            char.get_resists(), ctx, char.id, ctx.message.author.id)

        combat = Combat.from_ctx(ctx)

        if combat.get_combatant(char.get_name()) is not None:
            await self.bot.say("Combatant already exists.")
            return

        if group is None:
            combat.add_combatant(me)
            embed.set_footer(text="Added to combat!")
        else:
            grp = combat.get_group(group, create=init)
            grp.add_combatant(me)
            embed.set_footer(text=f"Joined group {grp.name}!")

        await combat.final()
        await self.bot.say(embed=embed)
        char.join_combat(ctx.message.channel.id).commit(ctx)

    @init.command(pass_context=True, name="next", aliases=['n'])
    async def nextInit(self, ctx):
        """Moves to the next turn in initiative order.
        It must be your turn or you must be the DM (the person who started combat) to use this command."""

        combat = Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await self.bot.say("There are no combatants.")
            return

        if combat.index is None:
            pass
        elif not ctx.message.author.id in (combat.current_combatant.controller, combat.dm):
            await self.bot.say("It is not your turn.")
            return

        toRemove = []
        if combat.current_combatant is not None:
            if isinstance(combat.current_combatant, CombatantGroup):
                thisTurn = [co for co in combat.current_combatant.get_combatants()]
            else:
                thisTurn = [combat.current_combatant]
            for co in thisTurn:
                if isinstance(co, MonsterCombatant) and co.hp <= 0:
                    toRemove.append(co)

        advanced_round = combat.advance_turn()
        self.bot.db.incr('turns_init_tracked_life')
        if advanced_round:
            self.bot.db.incr('rounds_init_tracked_life')

        nextCombatant = combat.current_combatant

        if isinstance(nextCombatant, CombatantGroup):
            thisTurn = nextCombatant.get_combatants()
            for co in thisTurn:
                co.on_turn()
            outStr = "**Initiative {} (round {})**: {} ({})\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   nextCombatant.name,
                                   ", ".join({co.controller_mention() for co in thisTurn}),
                                   '```markdown\n' + "\n".join([co.get_status() for co in thisTurn]) + '```')
        else:
            nextCombatant.on_turn()
            outStr = "**Initiative {} (round {})**: {}\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   "{} ({})".format(nextCombatant.name, nextCombatant.controller_mention()),
                                   '```markdown\n' + nextCombatant.get_status() + '```')

        for co in toRemove:
            combat.remove_combatant(co)
            co.on_remove()
            outStr += "{} automatically removed from combat.\n".format(co.name)

        if combat.options.get('turnnotif'):
            nextTurn = combat.next_combatant
            outStr += f"**Next up**: {nextTurn.name} ({nextTurn.controller_mention()})\n"
        await self.bot.say(outStr)
        await combat.final()

    @init.command(pass_context=True, name="prev", aliases=['previous', 'rewind'])
    async def prevInit(self, ctx):
        """Moves to the previous turn in initiative order."""

        combat = Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await self.bot.say("There are no combatants.")
            return

        combat.rewind_turn()

        nextCombatant = combat.current_combatant

        if isinstance(nextCombatant, CombatantGroup):
            thisTurn = nextCombatant.get_combatants()
            outStr = "**Initiative {} (round {})**: {} ({})\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   nextCombatant.name,
                                   ", ".join({co.controller_mention() for co in thisTurn}),
                                   '```markdown\n' + "\n".join([co.get_status() for co in thisTurn]) + '```')
        else:
            outStr = "**Initiative {} (round {})**: {}\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   "{} ({})".format(nextCombatant.name, nextCombatant.controller_mention()),
                                   '```markdown\n' + nextCombatant.get_status() + '```')

        if combat.options.get('turnnotif'):
            nextTurn = combat.next_combatant
            outStr += f"**Next up**: {nextTurn.name} ({nextTurn.controller_mention()})\n"
        await self.bot.say(outStr)
        await combat.final()

    @init.command(pass_context=True, name="move", aliases=['goto'])
    async def movesInit(self, ctx, init: int):
        """Moves to a certain initiative."""

        combat = Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await self.bot.say("There are no combatants.")
            return

        combat.goto_turn(init)

        nextCombatant = combat.current_combatant

        if isinstance(nextCombatant, CombatantGroup):
            thisTurn = nextCombatant.get_combatants()
            outStr = "**Initiative {} (round {})**: {} ({})\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   nextCombatant.name,
                                   ", ".join({co.controller_mention() for co in thisTurn}),
                                   '```markdown\n' + "\n".join([co.get_status() for co in thisTurn]) + '```')
        else:
            outStr = "**Initiative {} (round {})**: {}\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   "{} ({})".format(nextCombatant.name, nextCombatant.controller_mention()),
                                   '```markdown\n' + nextCombatant.get_status() + '```')

        if combat.options.get('turnnotif'):
            nextTurn = combat.next_combatant
            outStr += f"**Next up**: {nextTurn.name} ({nextTurn.controller_mention()})\n"
        await self.bot.say(outStr)
        await combat.final()

    @init.command(pass_context=True, name="list", aliases=['summary'])
    async def listInits(self, ctx):
        """Lists the combatants."""
        combat = Combat.from_ctx(ctx)
        outStr = combat.get_summary()
        await self.bot.say(outStr, delete_after=60)

    @init.command(pass_context=True)
    async def note(self, ctx, name: str, *, note: str = ''):
        """Attaches a note to a combatant."""
        combat = Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await self.bot.say("Combatant not found.")

        combatant.notes = note
        if note == '':
            await self.bot.say("Removed note.", delete_after=10)
        else:
            await self.bot.say("Added note.", delete_after=10)
        await combat.final()

    @init.command(pass_context=True, aliases=['opts'])
    async def opt(self, ctx, name: str, *args):
        """Edits the options of a combatant.
        Valid Arguments:    -h (hides HP)
                            -p (changes init)
                            -name <NAME> (changes combatant name)
                            -controller <CONTROLLER> (pings a different person on turn)
                            -ac <AC> (changes combatant AC)
                            -resist <RESISTANCE>
                            -immune <IMMUNITY>
                            -vuln <VULNERABILITY>
                            -group <GROUP> (changes group)"""
        combat = Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        private = combatant.isPrivate
        controller = combatant.controller
        args = parse_args_3(args)
        out = ''

        if args.get('h'):
            private = not private
            combatant.isPrivate = private
            out += "\u2705 Combatant {}.\n".format('hidden' if private else 'unhidden')
        if 'controller' in args:
            try:
                controllerStr = args.get('controller')[-1]
                controllerEscaped = controllerStr.strip('<>@!')
                a = ctx.message.server.get_member(controllerEscaped)
                b = ctx.message.server.get_member_named(controllerStr)
                cont = a.id if a is not None else b.id if b is not None else controller
                combatant.controller = cont
                out += "\u2705 Combatant controller set to {}.\n".format(combatant.controller_mention())
            except IndexError:
                out += "\u274c You must pass in a controller with the --controller tag.\n"
        if 'ac' in args:
            try:
                ac = int(args.get('ac')[-1])
                combatant.ac = ac
                out += "\u2705 Combatant AC set to {}.\n".format(ac)
            except:
                out += "\u274c You must pass in an AC with the --ac tag.\n"
        if 'p' in args:
            if combatant is combat.current_combatant:
                out += "\u274c You cannot change a combatant's initiative on their own turn.\n"
            else:
                try:
                    p = int(args.get('p')[-1])
                    combatant.init = p
                    combat.sort_combatants()
                    out += "\u2705 Combatant initiative set to {}.\n".format(p)
                except:
                    out += "\u274c You must pass in a number with the -p tag.\n"
        if 'group' in args:
            if combatant is combat.current_combatant:
                out += "\u274c You cannot change a combatant's group on their own turn.\n"
            else:
                group = args.get('group')[-1]
                if group.lower() == 'none':
                    combat.remove_combatant(combatant)
                    combat.add_combatant(combatant)
                    out += "\u2705 Combatant removed from all groups.\n"
                else:
                    group = combat.get_group(group, combatant.init)
                    combat.remove_combatant(combatant)
                    group.add_combatant(combatant)
                    out += "\u2705 Combatant group set to {}.\n".format(group.name)
        if 'name' in args:
            name = args.get('name')[-1]
            if combat.get_combatant(name) is not None:
                out += "\u274c There is already another combatant with that name.\n"
            elif name:
                combatant.name = name
                out += "\u2705 Combatant name set to {}.\n".format(name)
            else:
                out += "\u274c You must pass in a name with the -name tag.\n"
        if 'resist' in args:
            for resist in args.get('resist'):
                if resist in combatant.resists['resist']:
                    combatant.resists['resist'].remove(resist)
                    out += "\u2705 {} removed from combatant resistances.\n".format(resist)
                else:
                    combatant.resists['resist'].append(resist)
                    out += "\u2705 {} added to combatant resistances.\n".format(resist)
        if 'immune' in args:
            for immune in args.get('immune'):
                if immune in combatant.resists['immune']:
                    combatant.resists['immune'].remove(immune)
                    out += "\u2705 {} removed from combatant immunities.\n".format(immune)
                else:
                    combatant.resists['immune'].append(immune)
                    out += "\u2705 {} added to combatant immunities.\n".format(immune)
        if 'vuln' in args:
            for vuln in args.get('vuln'):
                if vuln in combatant.resists['vuln']:
                    combatant.resists['vuln'].remove(vuln)
                    out += "\u2705 {} removed from combatant vulnerabilities.\n".format(vuln)
                else:
                    combatant.resists['vuln'].append(vuln)
                    out += "\u2705 {} added to combatant vulnerabilities.\n".format(vuln)

        if combatant.isPrivate:
            await self.bot.send_message(ctx.message.server.get_member(combatant.controller),
                                        "{}'s options updated.\n".format(combatant.name) + out)
            await self.bot.say("Combatant options updated.", delete_after=10)
        else:
            await self.bot.say("{}'s options updated.\n".format(combatant.name) + out, delete_after=10)
        await combat.final()

    @init.command(pass_context=True)
    async def status(self, ctx, name: str, *, args: str = ''):
        """Gets the status of a combatant or group."""
        combat = Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name, select_group=True)
        if combatant is None:
            await self.bot.say("Combatant or group not found.")
            return

        private = 'private' in args.lower()
        if isinstance(combatant, Combatant):
            private = private and ctx.message.author.id == combatant.controller
            status = combatant.get_status(private=private)
        else:
            status = "\n".join([co.get_status(private=private and ctx.message.author.id == co.controller) for co in
                                combatant.get_combatants()])
        if 'private' in args.lower():
            await self.bot.send_message(ctx.message.server.get_member(combatant.controller),
                                        "```markdown\n" + status + "```")
        else:
            await self.bot.say("```markdown\n" + status + "```", delete_after=30)

    @init.command(pass_context=True)
    async def hp(self, ctx, name: str, operator: str, *, hp: str = ''):
        """Modifies the HP of a combatant.
        Usage: !init hp <NAME> <mod/set/max> <HP>
        If no operator is supplied, mod is assumed.
        If max is given with no number, resets combatant to max hp."""
        combat = Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        hp_roll = roll(hp, inline=True, show_blurbs=False)

        if 'mod' in operator.lower():
            if combatant.hp is None:
                combatant.hp = 0
            combatant.hp += hp_roll.total
        elif 'set' in operator.lower():
            combatant.set_hp(hp_roll.total)
        elif 'max' in operator.lower():
            if hp == '':
                combatant.set_hp(combatant.hpMax)
            elif hp_roll.total < 1:
                return await self.bot.say("You can't have a negative max HP!")
            else:
                combatant.hpMax = hp_roll.total
        elif hp == '':
            hp_roll = roll(operator, inline=True, show_blurbs=False)
            if combatant.hp is None:
                combatant.hp = 0
            combatant.hp += hp_roll.total
        else:
            await self.bot.say("Incorrect operator. Use mod, set, or max.")
            return

        out = "{}: {}".format(combatant.name, combatant.get_hp_str())
        if 'd' in hp: out += '\n' + hp_roll.skeleton

        await self.bot.say(out, delete_after=10)
        if combatant.isPrivate:
            try:
                await self.bot.send_message(ctx.message.server.get_member(combatant.controller),
                                            "{}'s HP: {}".format(combatant.name, combatant.get_hp_str(True)))
            except:
                pass
        await combat.final()

    @init.command(pass_context=True)
    async def thp(self, ctx, name: str, *, thp: int):
        """Modifies the temporary HP of a combatant.
        Usage: !init thp <NAME> <HP>
        Sets the combatant's THP if hp is positive, modifies it otherwise (i.e. `!i thp Avrae 5` would set Avrae's THP to 5 but `!i thp Avrae -2` would remove 2 THP)."""
        combat = Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        if thp >= 0:
            combatant.temphp = thp
        else:
            combatant.temphp += thp

        out = "{}: {}".format(combatant.name, combatant.get_hp_str())
        await self.bot.say(out, delete_after=10)
        if combatant.isPrivate:
            try:
                await self.bot.send_message(ctx.message.server.get_member(combatant.controller),
                                            "{}'s HP: {}".format(combatant.name, combatant.get_hp_str(True)))
            except:
                pass
        await combat.final()

    @init.command(pass_context=True)
    async def effect(self, ctx, name: str, duration: int, effect_name: str, *, effect: str = None):
        """Attaches a status effect to a combatant.
        [effect] is a set of args that will be appended to every `!i a` the combatant makes.
        Valid Arguments: -b [bonus] (see !a)
                         -d [damage bonus] (see !a)
                         -ac [ac] (modifies ac temporarily; adds if starts with +/- or sets otherwise)"""
        combat = Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        if effect_name.lower() in (e.name.lower() for e in combatant.get_effects()):
            return await self.bot.say("Effect already exists.", delete_after=10)

        effectObj = Effect.new(duration=duration, name=effect_name, effect=effect)
        combatant.add_effect(effectObj)
        await self.bot.say("Added effect {} to {}.".format(effect_name, combatant.name), delete_after=10)
        await combat.final()

    @init.command(pass_context=True, name='re')
    async def remove_effect(self, ctx, name: str, effect: str = ''):
        """Removes a status effect from a combatant. Removes all if effect is not passed."""
        combat = Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant not found.")
            return

        if effect is '':
            combatant.remove_all_effects()
            await self.bot.say("All effects removed from {}.".format(combatant.name), delete_after=10)
        else:
            to_remove = await combatant.select_effect(effect)
            combatant.remove_effect(to_remove)
            await self.bot.say('Effect {} removed from {}.'.format(to_remove.name, combatant.name), delete_after=10)
        await combat.final()

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
        combat = Combat.from_ctx(ctx)

        try:
            target = await combat.select_combatant(target_name, "Select the target.")
            if target is None:
                return await self.bot.say("Target not found.")
        except SelectionException:
            return await self.bot.say("Target not found.")

        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await self.bot.say("You must start combat with `!init next` first.")
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the attacker.")
                if combatant is None:
                    return await self.bot.say("Combatant not found.")
            except SelectionException:
                return await self.bot.say("Combatant not found.")

        attacks = combatant.attacks
        if '-custom' in args:
            attack = {'attackBonus': None, 'damage': None, 'name': atk_name}
        else:
            try:
                attack = await get_selection(ctx,
                                             [(a['name'], a) for a in attacks if atk_name.lower() in a['name'].lower()],
                                             message="Select your attack.")
            except SelectionException:
                return await self.bot.say("Attack not found.")

        args = parse_snippets(args, ctx)

        is_player = isinstance(combatant, PlayerCombatant)

        if is_player:
            args = await combatant.character.parse_cvars(args, ctx)

        args = parse_args_2(shlex.split(args))  # set up all the arguments
        args['name'] = combatant.name
        if target.ac is not None: args['ac'] = target.ac
        args['t'] = target.name
        args['resist'] = args.get('resist') or '|'.join(target.resists['resist'])
        args['immune'] = args.get('immune') or '|'.join(target.resists['immune'])
        args['vuln'] = args.get('vuln') or '|'.join(target.resists['vuln'])
        if is_player:
            args['c'] = combatant.character.get_setting('critdmg') or args.get('c')
            args['hocrit'] = combatant.character.get_setting('hocrit') or False
            args['reroll'] = combatant.character.get_setting('reroll') or 0
            args['crittype'] = combatant.character.get_setting('crittype') or 'default'

        result = sheet_attack(attack, args)
        embed = result['embed']
        if is_player:
            embed.colour = combatant.character.get_color()
        else:
            embed.colour = random.randint(0, 0xffffff)
        if target.ac is not None and target.hp is not None: target.hp -= result['total_damage']

        if target.ac is not None:
            if target.hp is not None:
                embed.set_footer(text="{}: {}".format(target.name, target.get_hp_str()))
                if target.isPrivate:
                    try:
                        await self.bot.send_message(ctx.message.server.get_member(target.controller),
                                                    "{}'s HP: {}".format(target.name, target.get_hp_str(True)))
                    except:
                        pass
            else:
                embed.set_footer(text="Dealt {} damage to {}!".format(result['total_damage'], target.name))
        else:
            embed.set_footer(text="Target AC not set.")

        _fields = args.get('f', [])
        if type(_fields) == list:
            for f in _fields:
                title = f.split('|')[0] if '|' in f else '\u200b'
                value = "|".join(f.split('|')[1:]) if '|' in f else f
                embed.add_field(name=title, value=value)

        await self.bot.say(embed=embed)
        await combat.final()

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
        combat = Combat.from_ctx(ctx)

        combatant = combat.current_combatant
        if combatant is None:
            return await self.bot.say("You must begin combat with !init next first.")

        is_character = isinstance(combatant, PlayerCombatant)
        if not is_character: return await self.bot.say(
            "This command requires a SheetManager integrated combatant.")  # TODO

        character = combatant.character

        args = parse_snippets(args, ctx)
        args = await character.parse_cvars(args, ctx)
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

        spell = strict_search(c.autospells, 'name', spell_name)
        if spell is None: return await self._old_cast(ctx, spell_name, *args)  # fall back to old cast

        can_cast = True
        spell_level = int(spell.get('level', 0))
        try:
            cast_level = int(args.get('l', [spell_level])[-1])
            assert spell_level <= cast_level <= 9
        except (AssertionError, ValueError):
            return await self.bot.say("Invalid spell level.")

        if is_character:
            # make sure we can cast it
            try:
                assert character.get_remaining_slots(cast_level) > 0
                assert spell['name'] in character.get_spell_list()
            except AssertionError:
                can_cast = False
            else:
                # use a spell slot
                if not args.get('i'):
                    character.use_slot(cast_level).commit(ctx)

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

        embed.title = '{} casts {} at...'.format(combatant.name, spell['name'])

        damage_save = None
        for i, t in enumerate(args.get('t', [])):
            target: Combatant = await combat.select_combatant(t, f"Select target #{i+1}.")
            if target is None:
                embed.add_field(name="{} not found!".format(t), value="Target not found.")
            elif not isinstance(target, (PlayerCombatant, MonsterCombatant)):
                embed.add_field(name="{} not supported!".format(t),
                                value="Target must be a monster or player added with `madd` or `cadd`.")
            else:
                spell_type = spell.get('type')
                if spell_type == 'save':  # save spell
                    out = ''
                    calculated_dc = character.evaluate_cvar('dc') or character.get_save_dc()
                    dc = args.get('dc', [None])[-1] or calculated_dc
                    if not dc:
                        raise NoSpellDC
                    try:
                        dc = int(dc)
                    except:
                        raise NoSpellDC

                    save_skill = args.get('save', [None])[-1] or spell.get('save', {}).get('save')
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
                                    level = character.get_level()
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

                        dmg = parse_resistances(dmg, args.get('resist', []) or target.resists['resist'],
                                                args.get('immune', []) or target.resists['immune'],
                                                args.get('vuln', []) or target.resists['vuln'])

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
                            embed_footer += "{}: {}\n".format(target.name, target.get_hp_str())
                            if target.isPrivate:
                                try:
                                    await self.bot.send_message(ctx.message.server.get_member(target.controller),
                                                                "{}'s HP: {}".format(target.name,
                                                                                     target.get_hp_str(True)))
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
                    outargs['resist'] = '|'.join(args.get('resist', [])) or '|'.join(target.resists['resist'])
                    outargs['immune'] = '|'.join(args.get('immune', [])) or '|'.join(target.resists['immune'])
                    outargs['vuln'] = '|'.join(args.get('vuln', [])) or '|'.join(target.resists['vuln'])
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
                            level = character.get_level()
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
                                                                    character.evaluate_cvar(
                                                                        "SPELL") or character.get_spell_ab() - character.get_prof_bonus()))

                    result = sheet_attack(attack, outargs)
                    out = ""
                    for f in result['embed'].fields:
                        out += "**__{0.name}__**\n{0.value}\n".format(f)

                    embed.add_field(name='...{}!'.format(target.name), value=out, inline=False)

                    if target.hp is not None:
                        target.hp -= result['total_damage']
                        embed_footer += "{}: {}\n".format(target.name, target.get_hp_str())
                        if target.isPrivate:
                            try:
                                await self.bot.send_message(ctx.message.server.get_member(target.controller),
                                                            "{}'s HP: {}".format(target.name, target.get_hp_str(True)))
                            except:
                                pass
                    else:
                        embed_footer += "Dealt {} damage to {}!".format(result['total_damage'], target.name)
                else:  # special spell (MM)
                    outargs = copy.copy(args)  # just make an attack for it
                    outargs['d'] = "+".join(args.get('d', [])) or None
                    for _arg, _value in outargs.items():
                        if isinstance(_value, list):
                            outargs[_arg] = _value[-1]
                    attack = {"name": spell['name'],
                              "damage": spell.get("damage", "0").replace('SPELL', str(
                                  character.evaluate_cvar(
                                      "SPELL") or character.get_spell_ab() - character.get_prof_bonus())),
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
                        embed_footer += "{}: {}\n".format(target.name, target.get_hp_str())
                        if target.isPrivate:
                            try:
                                await self.bot.send_message(ctx.message.server.get_member(target.controller),
                                                            "{}'s HP: {}".format(target.name, target.get_hp_str(True)))
                            except:
                                pass
                    else:
                        embed_footer += "Dealt {} damage to {}!".format(result['total_damage'], target.name)

        spell_ctx = spell_context(spell)
        if spell_ctx:
            embed.add_field(name='Effect', value=spell_ctx)

        if cast_level > 0:  # TODO: monster casters
            embed.add_field(name="Spell Slots", value=character.get_remaining_slots_str(cast_level))

        embed.colour = random.randint(0, 0xffffff) if not is_character else combatant.character.get_color()
        embed.set_footer(text=embed_footer)
        await self.bot.say(embed=embed)
        await combat.final()

    async def _old_cast(self, ctx, spell_name, *args):
        spell = getSpell(spell_name)
        self.bot.db.incr('spells_looked_up_life')
        if spell is None:
            return await self.bot.say("Spell not found.", delete_after=15)
        if spell.get('source') == "UAMystic":
            return await self.bot.say("Mystic talents are not supported.")

        char = Character.from_ctx(ctx)

        args = parse_snippets(' '.join(list(args)), ctx)
        args = await char.parse_cvars(args, ctx)
        args = shlex.split(args)
        args = parse_args_3(args)

        can_cast = True
        spell_level = int(spell.get('level', 0))
        try:
            cast_level = int(args.get('l', [spell_level])[-1])
            assert spell_level <= cast_level <= 9
        except (AssertionError, ValueError):
            return await self.bot.say("Invalid spell level.")

        # make sure we can cast it
        try:
            assert char.get_remaining_slots(cast_level) > 0
            assert spell_name in char.get_spell_list()
        except AssertionError:
            can_cast = False

        if args.get('i'):
            can_cast = True

        if not can_cast:
            embed = EmbedWithCharacter(char)
            embed.title = "Cannot cast spell!"
            embed.description = "Not enough spell slots remaining, or spell not in known spell list!\n" \
                                "Use `!game longrest` to restore all spell slots, or pass `-i` to ignore restrictions."
            if cast_level > 0:
                embed.add_field(name="Spell Slots", value=char.get_remaining_slots_str(cast_level))
            return await self.bot.say(embed=embed)

        if len(args) == 0:
            rolls = spell.get('roll', None)
            if isinstance(rolls, list):
                active_character = self.bot.db.not_json_get('active_characters', {}).get(
                    ctx.message.author.id)  # get user's active
                if active_character is not None:
                    rolls = '\n'.join(rolls).replace('SPELL', str(char.get_spell_ab() - char.get_prof_bonus())) \
                        .replace('PROF', str(char.get_prof_bonus()))
                    rolls = rolls.split('\n')
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + '\n'.join(
                    roll(r, inline=True).skeleton for r in rolls)
            elif rolls is not None:
                active_character = self.bot.db.not_json_get('active_characters', {}).get(
                    ctx.message.author.id)  # get user's active
                if active_character is not None:
                    rolls = rolls.replace('SPELL', str(char.get_spell_ab() - char.get_prof_bonus())) \
                        .replace('PROF', str(char.get_prof_bonus()))
                out = "**{} casts {}:** ".format(ctx.message.author.mention, spell['name']) + roll(rolls,
                                                                                                   inline=True).skeleton
            else:
                out = "**{} casts {}!** ".format(ctx.message.author.mention, spell['name'])
        else:
            rolls = args.get('r', [])
            roll_results = ""
            for r in rolls:
                res = roll(r, inline=True)
                if res.total is not None:
                    roll_results += res.result + '\n'
                else:
                    roll_results += "**Effect:** " + r
            out = "**{} casts {}:**\n".format(ctx.message.author.mention, spell['name']) + roll_results

        if not args.get('i'):
            char.use_slot(cast_level)
        if cast_level > 0:
            out += f"\n**Remaining Spell Slots**: {char.get_remaining_slots_str(cast_level)}"

        out = "Spell not supported by new cast, falling back to old cast.\n" + out
        char.commit(ctx)  # make sure we save changes
        await self.bot.say(out)
        spell_cmd = self.bot.get_command('spell')
        if spell_cmd is None: return await self.bot.say("Lookup cog not loaded.")
        await ctx.invoke(spell_cmd, name=spell['name'])

    @init.command(pass_context=True, name='remove')
    async def remove_combatant(self, ctx, *, name: str):
        """Removes a combatant or group from the combat.
        Usage: !init remove <NAME>"""
        combat = Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await self.bot.say("Combatant not found.")

        if combatant is combat.current_combatant:
            return await self.bot.say("You cannot remove a combatant on their own turn.")

        if combatant.group is not None:
            group = combat.get_group(combatant.group)
            if len(group.get_combatants()) <= 1 and group is combat.current_combatant:
                return await self.bot.say(
                    "You cannot remove a combatant if they are the only remaining combatant in this turn.")
        combat.remove_combatant(combatant)
        combatant.on_remove()
        await self.bot.say("{} removed from combat.".format(combatant.name), delete_after=10)
        await combat.final()

    @init.command(pass_context=True)
    async def end(self, ctx):
        """Ends combat in the channel."""

        combat = Combat.from_ctx(ctx)

        to_end = await confirm(ctx, 'Are you sure you want to end combat? (Reply with yes/no)', True)

        if to_end is None:
            return await self.bot.say('Timed out waiting for a response or invalid response.', delete_after=10)
        elif not to_end:
            return await self.bot.say('OK, cancelling.', delete_after=10)

        msg = await self.bot.say("OK, ending...")

        try:
            await self.bot.send_message(ctx.message.author, f"End of combat report: {combat.round_num} rounds "
                                                            f"{combat.get_summary(True)}")

            summary = await combat.get_summary_msg()
            await self.bot.edit_message(summary,
                                        combat.get_summary() + " ```-----COMBAT ENDED-----```")
            await self.bot.unpin_message(summary)
        except:
            pass

        combat.end()

        await self.bot.edit_message(msg, "Combat ended.")
