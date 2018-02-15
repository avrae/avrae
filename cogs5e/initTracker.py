import logging
import random
import shlex
import traceback
from math import floor

from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import searchMonsterFull
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.initiative import Combat, Combatant, MonsterCombatant, Effect, PlayerCombatant
from utils.functions import parse_args_3, confirm, get_selection, parse_args_2

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
                         -name <NAME> (names the combat)"""
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

        try:
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
                raise NotImplementedError  # TODO: groups
        except Exception as e:
            await self.bot.say("Error adding combatant: {}".format(e))
            return

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
              -npr (removes physical resistances when added)"""

        monster = await searchMonsterFull(monster_name, ctx, pm=True)
        self.bot.db.incr("monsters_looked_up_life")
        if monster['monster'] is None:
            return await self.bot.say(monster['string'][0], delete_after=15)
        monster = monster['monster']
        dexMod = floor((int(monster['dex']) - 10) / 2)

        args = parse_args_3(args)
        private = not bool(args.get('h', [False])[-1])

        group = args.get('group', [None])[-1]

        adv = 0 if args.get('adv', False) and args.get('dis', False) else 1 if args.get('adv',
                                                                                        False) else -1 if args.get(
            'dis', False) else 0

        b = '+'.join(args.get('b', []))
        p = args.get('p', [None])[-1]

        opts = {}
        if 'npr' in args:
            opts['npr'] = True

        combat = Combat.from_ctx(ctx)

        out = ''
        try:
            recursion = int(args.get('n', [1])[-1])
        except ValueError:
            return await self.bot.say(args.get('n', 1) + " is not a number.")
        recursion = 25 if recursion > 25 else 1 if recursion < 1 else recursion

        name_num = 1
        for i in range(recursion):
            name = args.get('name', [monster['name'][:2].upper() + '#'])[-1].replace('#', str(name_num))

            while combat.get_combatant(name):  # keep increasing to avoid duplicates
                name_num += 1
                name = args.get('name', [monster['name'][:2].upper() + '#'])[-1].replace('#', str(name_num))

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

                me = MonsterCombatant.from_monster(name, controller, init, dexMod, private, monster, ctx, opts)
                if group is None:
                    combat.add_combatant(me)
                    out += "{} was added to combat with initiative {}.\n".format(name,
                                                                                 check_roll.skeleton if p is None else p)
                # elif combat.get_combatant_group(group) is None:  # TODO
                #     newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
                #     newGroup.combatants.append(me)
                #     combat.combatants.append(newGroup)
                #     out += "{} was added to combat as part of group {}, with initiative {}.\n".format(name, group,
                #                                                                                       check_roll.skeleton if p is None else p)
                # else:
                #     temp_group = combat.get_combatant_group(group)
                #     temp_group.combatants.append(me)
                #     out += "{} was added to combat as part of group {}.\n".format(name, temp_group.name)
            except Exception as e:
                log.error('\n'.join(traceback.format_exception(type(e), e, e.__traceback__)))
                out += "Error adding combatant: {}\n".format(e)

        await self.bot.say(out, delete_after=15)
        await combat.final()

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
                                      f"Please leave combat in <#{char.get_combat_id()}> first.")

        skills = character.get('skills')
        if skills is None:
            return await self.bot.say('You must update your character sheet first.')
        skill = 'initiative'
        combat = Combat.from_ctx(ctx)

        if combat.get_combatant(char.get_name()) is not None:
            await self.bot.say("Combatant already exists.")
            return

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

        me = PlayerCombatant.from_character(char.get_name(), controller, init, bonus, char.get_ac(), private, ctx,
                                            char.id, ctx.message.author.id)

        if group is None:
            combat.add_combatant(me)
            embed.set_footer(text="Added to combat!")
        # elif combat.get_combatant_group(group) is None:  # TODO: group
        #     newGroup = CombatantGroup(name=group, init=init, author=controller, notes='')
        #     newGroup.combatants.append(me)
        #     combat.combatants.append(newGroup)
        #     embed.set_footer(text="Added to combat in group {}!".format('group'))
        # else:
        #     group = combat.get_combatant_group(group)
        #     group.combatants.append(me)
        #     embed.set_footer(text="Added to combat in group {}!".format('group'))

        char.join_combat(ctx.message.channel.id).commit(ctx)

        await self.bot.say(embed=embed)
        await combat.final()

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

        toRemove = []  # TODO: automatic dead monster combatant removal
        # if combat.currentCombatant is not None:
        #     if isinstance(combat.currentCombatant, CombatantGroup):
        #         thisTurn = [c for c in combat.currentCombatant.combatants]
        #     else:
        #         thisTurn = [combat.currentCombatant]
        #     for c in thisTurn:
        #         if isinstance(c, MonsterCombatant) and c.hp <= 0:
        #             toRemove.append(c)

        advanced_round = combat.advance_turn()
        self.bot.db.incr('turns_init_tracked_life')
        if advanced_round:
            self.bot.db.incr('rounds_init_tracked_life')

        nextCombatant = combat.current_combatant

        # try:
        #     nextCombatant = combat.getNextCombatant()
        #     combat.current = nextCombatant.init
        #     combat.currentCombatant = nextCombatant
        #     self.bot.db.incr('turns_init_tracked_life')
        # except IndexError:
        #     combat.current = combat.sorted_combatants[0].init
        #     combat.round += 1
        #     self.bot.db.incr('rounds_init_tracked_life')
        #     combat.index = None
        #     if combat.options.get('dynamic', False):
        #         for combatant in combat.combatants:
        #             combatant.init = roll('1d20+' + str(combatant.mod)).total
        #         combat.sorted_combatants = sorted(combat.combatants, key=lambda k: (k.init, k.mod), reverse=True)
        #     nextCombatant = combat.getNextCombatant()
        #     combat.currentCombatant = nextCombatant

        if False:  # TODO - groups
            pass
            # thisTurn = nextCombatant.combatants
            # for c in thisTurn:
            #     c.on_turn()
            # outStr = "**Initiative {} (round {})**: {} ({})\n{}"
            # outStr = outStr.format(combat.current,
            #                        combat.round,
            #                        nextCombatant.name,
            #                        ", ".join({c.controller_mention() for c in thisTurn}),
            #                        '```markdown\n' + "\n".join([c.get_status() for c in thisTurn]) + '```')
        else:
            nextCombatant.on_turn()
            outStr = "**Initiative {} (round {})**: {}\n{}"
            outStr = outStr.format(combat.turn_num,
                                   combat.round_num,
                                   "{} ({})".format(nextCombatant.name, nextCombatant.controller_mention()),
                                   '```markdown\n' + nextCombatant.get_status() + '```')

        # TODO: actual autoremove
        # for c in toRemove:
        #     if c.group is None:
        #         combat.combatants.remove(c)
        #     else:
        #         group = combat.get_combatant_group(c.group)
        #         group.combatants.remove(c)
        #     outStr += "{} automatically removed from combat.\n".format(c.name)
        # if len(toRemove) > 0:
        #     combat.sortCombatants()
        #     combat.checkGroups()

        await self.bot.say(outStr)
        await combat.final()

    @init.command(pass_context=True, name="list", aliases=['summary'])
    async def listInits(self, ctx):
        """Lists the combatants."""
        combat = Combat.from_ctx(ctx)
        outStr = combat.getSummary()
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
                cont = a if a is not None else b if b is not None else controller
                combatant.controller = cont.id
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
            if combatant == combat.currentCombatant:
                out += "\u274c You cannot change a combatant's initiative on their own turn.\n"
            else:
                try:
                    p = int(args.get('p')[-1])
                    combatant.init = p
                    combat.sort_combatants()
                    out += "\u2705 Combatant initiative set to {}.\n".format(p)
                except:
                    out += "\u274c You must pass in a number with the -p tag.\n"
        # if 'group' in args:  # TODO
        #     if combatant == combat.currentCombatant:
        #         out += "\u274c You cannot change a combatant's group on their own turn.\n"
        #     else:
        #         group = args.get('group')
        #         if group.lower() == 'none':
        #             if combatant.group:
        #                 currentGroup = combat.get_combatant_group(combatant.group)
        #                 currentGroup.combatants.remove(combatant)
        #             combatant.group = None
        #             combat.combatants.append(combatant)
        #             combat.checkGroups()
        #             combat.sortCombatants()
        #             out += "\u2705 Combatant removed from all groups.\n"
        #         elif combat.get_combatant_group(group) is not None:
        #             if combatant.group:
        #                 currentGroup = combat.get_combatant_group(combatant.group)
        #                 currentGroup.combatants.remove(combatant)
        #             else:
        #                 combat.combatants.remove(combatant)
        #             group = combat.get_combatant_group(group)
        #             combatant.group = group.name
        #             group.combatants.append(combatant)
        #             combat.checkGroups()
        #             combat.sortCombatants()
        #             out += "\u2705 Combatant group set to {}.\n".format(group)
        #         else:
        #             out += "\u274c New group not found.\n"
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
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await self.bot.say("Combatant or group not found.")
            return

        private = 'private' in args.lower() if ctx.message.author.id == combatant.controller else False
        if isinstance(combatant, Combatant):
            status = combatant.get_status(private=private)
        else:
            status = "\n".join([c.get_status(private=private) for c in combatant.combatants])
        if 'private' in args.lower():
            await self.bot.send_message(ctx.message.server.get_member(combatant.controller),
                                        "```markdown\n" + status + "```")
        else:
            await self.bot.say("```markdown\n" + status + "```", delete_after=30)

    @init.command(pass_context=True)
    async def hp(self, ctx, name: str, operator: str, *, hp: str = ''):
        """Modifies the HP of a combatant.
        Usage: !init hp <NAME> <mod/set/max> <HP>"""
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
            combatant.hp = hp_roll.total
        elif 'max' in operator.lower():
            if hp == '':
                combat.hp = combatant.hpMax
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
                                            "{}'s HP: {}/{}".format(combatant.name, combatant.hp, combatant.hpMax))
            except:
                pass
        await combat.final()

    @init.command(pass_context=True)
    async def effect(self, ctx, name: str, duration: int, effect_name: str, *, effect: str = None):
        """Attaches a status effect to a combatant.
        [effect] is a set of args that will be appended to every `!i a` the combatant makes."""
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
        target = await combat.select_combatant(target_name, "Select the target.")
        if target is None:
            await self.bot.say("Target not found.")
            return

        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await self.bot.say("You must start combat with `!init next` first.")
        else:
            combatant = await combat.select_combatant(combatant_name, "Select the attacker.")
            if combatant is None:
                return await self.bot.say("Combatant not found.")

        # if not isinstance(combatant, CombatantGroup): # TODO: effects
        #     for eff in combatant.effects:
        #         if hasattr(eff, "effect"):
        #             args += " " + eff.effect if eff.effect is not None else ""

        attacks = combatant.attacks
        if '-custom' in args:
            attack = {'attackBonus': None, 'damage': None, 'name': atk_name}
        else:
            attack = await get_selection(ctx,
                                         [(a['name'], a) for a in attacks if atk_name.lower() in a['name'].lower()],
                                         message="Select your attack.")

        tempargs = shlex.split(args)  # parse snippets
        user_snippets = self.bot.db.not_json_get('damage_snippets', {}).get(ctx.message.author.id, {})
        for index, arg in enumerate(tempargs):  # parse snippets
            snippet_value = user_snippets.get(arg)
            if snippet_value:
                tempargs[index] = snippet_value
            elif ' ' in arg:
                tempargs[index] = shlex.quote(arg)
        args = " ".join(tempargs)

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
                                                    "{}'s HP: {}/{}".format(target.name, target.hp, target.max_hp))
                    except:
                        pass
            else:
                embed.set_footer(text="Dealt {} damage to {}!".format(result['total_damage'], target.name))
        else:
            embed.set_footer(text="Target AC not set.")

        _fields = args.get('f', [])
        if type(_fields) == list:
            for f in _fields:
                title = f.split('|')[0] if '|' in f else '--'
                value = "|".join(f.split('|')[1:]) if '|' in f else f
                embed.add_field(name=title, value=value)

        await self.bot.say(embed=embed)
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
            summary = await combat.get_summary_msg()
            await self.bot.edit_message(summary,
                                        combat.get_summary() + " ```-----COMBAT ENDED-----```")
            await self.bot.unpin_message(summary)
        except:
            pass

        combat.end()

        await self.bot.edit_message(msg, "Combat ended.")
