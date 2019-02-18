import logging
import random
import shlex
import traceback

from discord.ext import commands

from cogs5e.funcs import scripting
from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import select_monster_full, select_spell_full
from cogs5e.funcs.sheetFuncs import sheet_attack
from cogs5e.models import embeds
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter, add_fields_from_args
from cogs5e.models.errors import SelectionException
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup, Effect, MonsterCombatant, PlayerCombatant
from utils.argparser import argparse
from utils.functions import confirm, get_selection

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

    @commands.group(aliases=['i'])
    @commands.guild_only()
    async def init(self, ctx):
        """Commands to help track initiative."""
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Incorrect usage. Use {ctx.prefix}help init for help.")
        try:
            await ctx.message.delete()
        except:
            pass

    @init.command()
    async def begin(self, ctx, *args):
        """Begins combat in the channel the command is invoked.
        Usage: !init begin <ARGS (opt)>
        __Valid Arguments__
        dyn (dynamic init; rerolls all initiatives at the start of a round)
        turnnotif (notifies the next player)
        -name <NAME> (names the combat)"""
        await Combat.ensure_unique_chan(ctx)

        options = {}

        args = argparse(args)
        if args.last('dyn', False, bool):  # rerolls all inits at the start of each round
            options['dynamic'] = True
        if 'name' in args:
            options['name'] = args.last('name')
        if args.last('turnnotif', False, bool):
            options['turnnotif'] = True

        temp_summary_msg = await ctx.send("```Awaiting combatants...```")
        Combat.message_cache[temp_summary_msg.id] = temp_summary_msg  # add to cache

        combat = Combat.new(str(ctx.channel.id), temp_summary_msg.id, str(ctx.author.id), options, ctx)
        await combat.final()

        try:
            await temp_summary_msg.pin()
        except:
            pass
        await ctx.send(
            f"Everyone roll for initiative!\n"
            f"If you have a character set up with SheetManager: `{ctx.prefix}init join`\n"
            f"If it's a 5e monster: `{ctx.prefix}init madd [monster name]`\n"
            f"Otherwise: `{ctx.prefix}init add [modifier] [name]`")

    @init.command()
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
        controller = str(ctx.author.id)
        group = None
        hp = None
        ac = None
        resists = {}
        args = argparse(args)

        if args.last('h', type_=bool):
            private = True
        if args.last('p', type_=bool):
            place = True
        if args.last('controller'):
            controllerStr = args.last('controller')
            controllerEscaped = controllerStr.strip('<>@!')
            a = ctx.guild.get_member(int(controllerEscaped))
            b = ctx.guild.get_member_named(controllerStr)
            controller = str(a.id) if a is not None else str(b.id) if b is not None else controller
        if args.last('group'):
            group = args.last('group')
        if args.last('hp'):
            hp = args.last('hp', type_=int)
            if hp < 1:
                return await ctx.send("You must pass in a positive, nonzero HP with the -hp tag.")
        if args.last('ac'):
            ac = args.last('ac', type_=int)

        for k in ('resist', 'immune', 'vuln'):
            resists[k] = args.get(k)

        combat = await Combat.from_ctx(ctx)

        if combat.get_combatant(name) is not None:
            await ctx.send("Combatant already exists.")
            return

        if not place:
            init = random.randint(1, 20) + modifier
        else:
            init = modifier
            modifier = 0

        me = Combatant.new(name, controller, init, modifier, hp, hp, ac, private, resists, [], {}, ctx, combat)

        if group is None:
            combat.add_combatant(me)
            await ctx.send(
                "{}\n{} was added to combat with initiative {}.".format(f'<@{controller}>', name, init),
                delete_after=10)
        else:
            grp = combat.get_group(group, create=init)
            grp.add_combatant(me)
            await ctx.send(
                "{}\n{} was added to combat with initiative {} as part of group {}.".format(me.controller_mention(),
                                                                                            name, grp.init,
                                                                                            grp.name),
                delete_after=10)

        await combat.final()

    @init.command()
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
        self.bot.rdb.incr("monsters_looked_up_life")

        dexMod = monster.skills['dexterity']

        args = argparse(args)
        private = not args.last('h', type_=bool)

        group = args.last('group')
        adv = args.adv()
        b = args.join('b', '+')
        p = args.last('p', type_=int)
        rollhp = args.last('rollhp', False, bool)
        hp = args.last('hp', type_=int)
        ac = args.last('ac', type_=int)
        npr = args.last('npr', type_=bool)
        n = args.last('n', 1, int)
        name_template = args.last('name', monster.name[:2].upper() + '#')

        opts = {}
        if npr:
            opts['npr'] = True

        combat = await Combat.from_ctx(ctx)

        out = ''
        to_pm = ''
        recursion = 25 if n > 25 else 1 if n < 1 else n

        name_num = 1
        for i in range(recursion):
            name = name_template.replace('#', str(name_num))
            raw_name = name_template
            to_continue = False

            while combat.get_combatant(name) and name_num < 100:  # keep increasing to avoid duplicates
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
                controller = str(ctx.author.id)

                rolled_hp = None
                if rollhp:
                    rolled_hp = roll(monster.hitdice, inline=True)
                    to_pm += f"{name} began with {rolled_hp.skeleton} HP.\n"
                    rolled_hp = max(rolled_hp.total, 1)

                me = MonsterCombatant.from_monster(name, controller, init, dexMod, private, monster, ctx, combat, opts,
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
        await ctx.send(out, delete_after=15)
        if to_pm:
            await ctx.author.send(to_pm)

    @init.command(name='join', aliases=['cadd', 'dcadd'])
    async def join(self, ctx, *, args: str = ''):
        """Adds the current active character to combat. A character must be loaded through the SheetManager module first.
        Args: adv/dis
              -b [conditional bonus]
              -phrase [flavor text]
              -p [init value]
              -h (same as !init add)
              --group (same as !init add)"""
        char = await Character.from_ctx(ctx)
        character = char.character

        # if char.get_combat_id():
        #     return await ctx.send(f"This character is already in a combat. "
        #                               f"Please leave combat in <#{char.get_combat_id()}> first.\n"
        #                               f"If this seems like an error, please `!update` your character sheet.")
        # we just ignore this for now.
        # I'll figure out a better solution when I actually need it

        skills = character.get('skills')
        if skills is None:
            return await ctx.send('You must update your character sheet first.')
        skill = 'initiative'

        embed = EmbedWithCharacter(char, False)
        embed.colour = char.get_color()

        skill_effects = character.get('skill_effects', {})
        args += ' ' + skill_effects.get(skill, '')  # dicecloud v7 - autoadv

        args = shlex.split(args)
        args = argparse(args)
        adv = args.adv()
        b = args.join('b', '+') or None
        p = args.last('p', type_=int)
        phrase = args.join('phrase', '\n') or None

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
            init = p
            bonus = 0
            embed.title = "{} already rolled initiative!".format(char.get_name())
            embed.description = "Placed at initiative `{}`.".format(init)

        group = args.last('group')
        controller = str(ctx.author.id)
        private = args.last('h', type_=bool)
        bonus = roll(bonus).total

        combat = await Combat.from_ctx(ctx)

        me = await PlayerCombatant.from_character(char.get_name(), controller, init, bonus, char.get_ac(), private,
                                                  char.get_resists(), ctx, combat, char.id, str(ctx.author.id), char)

        if combat.get_combatant(char.get_name()) is not None:
            await ctx.send("Combatant already exists.")
            return

        if group is None:
            combat.add_combatant(me)
            embed.set_footer(text="Added to combat!")
        else:
            grp = combat.get_group(group, create=init)
            grp.add_combatant(me)
            embed.set_footer(text=f"Joined group {grp.name}!")

        await combat.final()
        await ctx.send(embed=embed)
        char.join_combat(str(ctx.channel.id))
        await char.commit(ctx)

    @init.command(name="next", aliases=['n'])
    async def nextInit(self, ctx):
        """Moves to the next turn in initiative order.
        It must be your turn or you must be the DM (the person who started combat) to use this command."""

        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        if combat.index is None:
            pass
        elif not str(ctx.author.id) in (combat.current_combatant.controller, combat.dm):
            await ctx.send("It is not your turn.")
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
        self.bot.rdb.incr('turns_init_tracked_life')
        if advanced_round:
            self.bot.rdb.incr('rounds_init_tracked_life')

        out = combat.get_turn_str()

        for co in toRemove:
            combat.remove_combatant(co)
            out += "{} automatically removed from combat.\n".format(co.name)

        await ctx.send(out)
        await combat.final()

    @init.command(name="prev", aliases=['previous', 'rewind'])
    async def prevInit(self, ctx):
        """Moves to the previous turn in initiative order."""

        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        combat.rewind_turn()

        await ctx.send(combat.get_turn_str())
        await combat.final()

    @init.command(name="move", aliases=['goto'])
    async def moveInit(self, ctx, target=None):
        """Moves to a certain initiative.
        `target` can be either a number, to go to that initiative, or a name.
        If not supplied, goes to the first combatant that the user controls."""
        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        if target is None:
            combatant = next((c for c in combat.get_combatants() if c.controller == str(ctx.author.id)), None)
            if combatant is None:
                return await ctx.send("You do not control any combatants.")
            combat.goto_turn(combatant, True)
        else:
            try:
                target = int(target)
                combat.goto_turn(target)
            except ValueError:
                combatant = await combat.select_combatant(target)
                combat.goto_turn(combatant, True)

        await ctx.send(combat.get_turn_str())
        await combat.final()

    @init.command(name="skipround", aliases=['round', 'skiprounds'])
    async def skipround(self, ctx, numrounds: int = 1):
        """Skips one or more rounds of initiative."""

        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            return await ctx.send("There are no combatants.")
        if combat.index is None:
            return await ctx.send(f"Please start combat with `{ctx.prefix}init next` first.")

        toRemove = []
        for co in combat.get_combatants():
            if isinstance(co, MonsterCombatant) and co.hp <= 0 and co is not combat.current_combatant:
                toRemove.append(co)

        combat.skip_rounds(numrounds)
        out = combat.get_turn_str()

        for co in toRemove:
            combat.remove_combatant(co)
            out += "{} automatically removed from combat.\n".format(co.name)

        await ctx.send(out)
        await combat.final()

    @init.command(name="reroll", aliases=['shuffle'])
    async def reroll(self, ctx):
        """Rerolls initiative for all combatants."""
        combat = await Combat.from_ctx(ctx)
        combat.reroll_dynamic()
        await ctx.send(f"Rerolled initiative! New order: {combat.get_summary()}")
        await combat.final()

    @init.command(name="list", aliases=['summary'])
    async def listInits(self, ctx):
        """Lists the combatants."""
        combat = await Combat.from_ctx(ctx)
        outStr = combat.get_summary()
        await ctx.send(outStr, delete_after=60)

    @init.command()
    async def note(self, ctx, name: str, *, note: str = ''):
        """Attaches a note to a combatant."""
        combat = await Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await ctx.send("Combatant not found.")

        combatant.notes = note
        if note == '':
            await ctx.send("Removed note.", delete_after=10)
        else:
            await ctx.send("Added note.", delete_after=10)
        await combat.final()

    @init.command(aliases=['opts'])
    async def opt(self, ctx, name: str, *args):
        """Edits the options of a combatant.
        __Valid Arguments__
        -h (hides HP)
        -p (changes init)
        -name <NAME> (changes combatant name)
        -controller <CONTROLLER> (pings a different person on turn)
        -ac <AC> (changes combatant AC)
        -resist <DMGTYPE>
        -immune <DMGTYPE>
        -vuln <DMGTYPE>
        -neutral <DMGTYPE>
        -group <GROUP> (changes group)
        -max <MAXHP> (sets max hp)
        -hp <HP> (sets current hp)"""
        combat = await Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name)
        if combatant is None:
            await ctx.send("Combatant not found.")
            return

        private = combatant.isPrivate
        controller = combatant.controller
        args = argparse(args)
        out = ''

        if args.last('h', type_=bool):
            private = not private
            combatant.isPrivate = private
            out += "\u2705 Combatant {}.\n".format('hidden' if private else 'unhidden')
        if 'controller' in args:
            try:
                controllerStr = args.last('controller')
                controllerEscaped = controllerStr.strip('<>@!')
                a = ctx.guild.get_member(int(controllerEscaped))
                b = ctx.guild.get_member_named(controllerStr)
                cont = str(a.id) if a is not None else str(b.id) if b is not None else controller
                combatant.controller = cont
                out += "\u2705 Combatant controller set to {}.\n".format(combatant.controller_mention())
            except IndexError:
                out += "\u274c You must pass in a controller with the --controller tag.\n"
        if 'ac' in args:
            try:
                ac = args.last('ac', type_=int)
                combatant.ac = ac
                out += "\u2705 Combatant AC set to {}.\n".format(ac)
            except:
                out += "\u274c You must pass in an AC with the --ac tag.\n"
        if 'p' in args:
            if combatant is combat.current_combatant:
                out += "\u274c You cannot change a combatant's initiative on their own turn.\n"
            else:
                try:
                    p = args.last('p', type_=int)
                    combatant.init = p
                    combat.sort_combatants()
                    out += "\u2705 Combatant initiative set to {}.\n".format(p)
                except:
                    out += "\u274c You must pass in a number with the -p tag.\n"
        if 'group' in args:
            if combatant is combat.current_combatant:
                out += "\u274c You cannot change a combatant's group on their own turn.\n"
            else:
                group = args.last('group')
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
            name = args.last('name')
            if combat.get_combatant(name, True) is not None:
                out += "\u274c There is already another combatant with that name.\n"
            elif name:
                combatant.name = name
                out += "\u2705 Combatant name set to {}.\n".format(name)
            else:
                out += "\u274c You must pass in a name with the -name tag.\n"
        for resisttype in ("resist", "immune", "vuln", "neutral"):
            if resisttype in args:
                for resist in args.get(resisttype):
                    resist = resist.lower()
                    combatant.set_resist(resist, resisttype)
                    out += f"\u2705 Now {resisttype} to {resist}.\n"
        if 'max' in args:
            maxhp = args.last('max', type_=int)
            if maxhp < 1:
                out += "\u274c Max HP must be at least 1.\n"
            else:
                combatant.hpMax = maxhp
                out += "\u2705 Combatant HP max set to {}.\n".format(maxhp)
        if 'hp' in args:
            hp = args.last('hp', type_=int)
            combatant.set_hp(hp)
            out += "\u2705 Combatant HP set to {}.\n".format(hp)

        if combatant.isPrivate:
            controller = ctx.guild.get_member(int(combatant.controller))
            if controller:
                await controller.send("{}'s options updated.\n".format(combatant.name) + out)
            await ctx.send("Combatant options updated.", delete_after=10)
        else:
            await ctx.send("{}'s options updated.\n".format(combatant.name) + out, delete_after=10)
        await combat.final()

    @init.command()
    async def status(self, ctx, name: str, *, args: str = ''):
        """Gets the status of a combatant or group.
        __Valid Arguments__
        private - PMs the controller of the combatant a more detailed status."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name, select_group=True)
        if combatant is None:
            await ctx.send("Combatant or group not found.")
            return

        private = 'private' in args.lower()
        if isinstance(combatant, Combatant):
            private = private and str(ctx.author.id) == combatant.controller
            status = combatant.get_status(private=private)
            if private and isinstance(combatant, MonsterCombatant):
                status = f"{status}\n* This creature is a {combatant.monster_name}."
        else:
            status = "\n".join([co.get_status(private=private and str(ctx.author.id) == co.controller) for co in
                                combatant.get_combatants()])
        if 'private' in args.lower():
            controller = ctx.guild.get_member(int(combatant.controller))
            if controller:
                await controller.send("```markdown\n" + status + "```")
        else:
            await ctx.send("```markdown\n" + status + "```", delete_after=30)

    @init.command()
    async def hp(self, ctx, name: str, operator: str, *, hp: str = ''):
        """Modifies the HP of a combatant.
        Usage: !init hp <NAME> <mod/set/max> <HP>
        If no operator is supplied, mod is assumed.
        If max is given with no number, resets combatant to max hp."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await ctx.send("Combatant not found.")
            return

        hp_roll = roll(hp, inline=True, show_blurbs=False)

        if 'mod' in operator.lower():
            if combatant.hp is None:
                combatant.set_hp(0)
            combatant.mod_hp(hp_roll.total)
        elif 'set' in operator.lower():
            combatant.set_hp(hp_roll.total)
        elif 'max' in operator.lower():
            if hp == '':
                combatant.set_hp(combatant.hpMax)
            elif hp_roll.total < 1:
                return await ctx.send("You can't have a negative max HP!")
            else:
                combatant.hpMax = hp_roll.total
        elif hp == '':
            hp_roll = roll(operator, inline=True, show_blurbs=False)
            if combatant.hp is None:
                combatant.set_hp(0)
            combatant.mod_hp(hp_roll.total)
        else:
            await ctx.send("Incorrect operator. Use mod, set, or max.")
            return

        out = "{}: {}".format(combatant.name, combatant.get_hp_str())
        if 'd' in hp: out += '\n' + hp_roll.skeleton

        await ctx.send(out, delete_after=10)
        if combatant.isPrivate:
            try:
                controller = ctx.guild.get_member(int(combatant.controller))
                await controller.send("{}'s HP: {}".format(combatant.name, combatant.get_hp_str(True)))
            except:
                pass
        await combat.final()

    @init.command()
    async def thp(self, ctx, name: str, *, thp: int):
        """Modifies the temporary HP of a combatant.
        Usage: !init thp <NAME> <HP>
        Sets the combatant's THP if hp is positive, modifies it otherwise (i.e. `!i thp Avrae 5` would set Avrae's THP to 5 but `!i thp Avrae -2` would remove 2 THP)."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await ctx.send("Combatant not found.")
            return

        if thp >= 0:
            combatant.temphp = thp
        else:
            if combatant.temphp:
                combatant.temphp += thp
            else:
                return await ctx.send("Combatant has no temp hp.")

        out = "{}: {}".format(combatant.name, combatant.get_hp_str())
        await ctx.send(out, delete_after=10)
        if combatant.isPrivate:
            try:
                controller = ctx.guild.get_member(int(combatant.controller))
                await controller.send("{}'s HP: {}".format(combatant.name, combatant.get_hp_str(True)))
            except:
                pass
        await combat.final()

    @init.command()
    async def effect(self, ctx, name: str, effect_name: str, *, args: str = ''):
        """Attaches a status effect to a combatant.
        [args] is a set of args that affects a combatant in combat.
        __**Valid Arguments**__
        -dur [duration]
        conc (makes effect require conc)
        end (makes effect tick on end of turn)
        __Attacks__
        -b [bonus] (see !a)
        -d [damage bonus] (see !a)
        -attack "[hit]|[damage]|[description]" (Adds an attack to the combatant)
        __Resists__
        -resist [resist] (gives the combatant resistance)
        -immune [immune] (gives the combatant immunity)
        -vuln [vulnability] (gives the combatant vulnerability)
        -neutral [neutral] (removes immune/resist/vuln)
        __General__
        -ac [ac] (modifies ac temporarily; adds if starts with +/- or sets otherwise)
        -sb [save bonus] (Adds a bonus to saving throws)"""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await ctx.send("Combatant not found.")
            return

        if effect_name.lower() in (e.name.lower() for e in combatant.get_effects()):
            return await ctx.send("Effect already exists.", delete_after=10)

        if isinstance(combatant, PlayerCombatant):
            args = argparse(args, combatant.character)
        else:
            args = argparse(args)
        duration = args.last('dur', -1, int)
        conc = args.last('conc', False, bool)
        end = args.last('end', False, bool)

        effectObj = Effect.new(combat, combatant, duration=duration, name=effect_name, effect_args=args,
                               concentration=conc, tick_on_end=end)
        result = combatant.add_effect(effectObj)
        out = "Added effect {} to {}.".format(effect_name, combatant.name)
        if result['conc_conflict']:
            conflicts = [e.name for e in result['conc_conflict']]
            out += f"\nRemoved {', '.join(conflicts)} due to concentration conflict!"
        await ctx.send(out, delete_after=10)
        await combat.final()

    @init.command(name='re')
    async def remove_effect(self, ctx, name: str, effect: str = ''):
        """Removes a status effect from a combatant. Removes all if effect is not passed."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await ctx.send("Combatant not found.")
            return

        if effect is '':
            combatant.remove_all_effects()
            await ctx.send("All effects removed from {}.".format(combatant.name), delete_after=10)
        else:
            to_remove = await combatant.select_effect(effect)
            children_removed = ""
            if to_remove.children:
                children_removed = f"Also removed {len(to_remove.children)} child effects."
            to_remove.remove()
            await ctx.send(f'Effect {to_remove.name} removed from {combatant.name}.\n{children_removed}',
                           delete_after=10)
        await combat.final()

    @init.group(aliases=['a'], invoke_without_command=True)
    async def attack(self, ctx, target_name, atk_name, *, args=''):
        """Rolls an attack against another combatant.
        Valid Arguments: see !a and !ma.
        `-custom` - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add damage and to hit."""
        return await self._attack(ctx, None, target_name, atk_name, args)

    @attack.command(name="list")
    async def attack_list(self, ctx):
        """Lists the active combatant's attacks."""
        combat = await Combat.from_ctx(ctx)
        combatant = combat.current_combatant
        if combatant is None:
            return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")

        if combatant.isPrivate and combatant.controller != str(ctx.author.id) and str(ctx.author.id) != combat.dm:
            return await ctx.send("You do not have permission to view this combatant's attacks.")

        attacks = combatant.attacks

        tempAttacks = []
        for a in attacks:
            damage = a['damage'] if a['damage'] is not None else 'no'
            if a['attackBonus'] is not None:
                try:
                    bonus = roll(a['attackBonus']).total
                except:
                    bonus = a['attackBonus']
                tempAttacks.append(f"**{a['name']}:** +{bonus} To Hit, {damage} damage.")
            else:
                tempAttacks.append(f"**{a['name']}:** {damage} damage.")
        if not tempAttacks:
            tempAttacks = ['No attacks.']
        a = '\n'.join(tempAttacks)
        if len(a) > 2000:
            a = ', '.join(atk['name'] for atk in attacks)
        if len(a) > 2000:
            a = "Too many attacks, values hidden!"

        if not combatant.isPrivate:
            destination = ctx.message.channel
        else:
            destination = ctx.message.author
        return await destination.send("{}'s attacks:\n{}".format(combatant.name, a))

    @init.command()
    async def aoo(self, ctx, combatant_name, target_name, atk_name, *, args=''):
        """Rolls an attack of opportunity against another combatant.
        Valid Arguments: see !a and !ma.
        `-custom` - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add damage and to hit."""
        return await self._attack(ctx, combatant_name, target_name, atk_name, args)

    async def _attack(self, ctx, combatant_name, target_name, atk_name, args):
        args = await scripting.parse_snippets(args, ctx)
        combat = await Combat.from_ctx(ctx)

        try:
            target = await combat.select_combatant(target_name, "Select the target.")
            if target is None:
                return await ctx.send("Target not found.")
        except SelectionException:
            return await ctx.send("Target not found.")

        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the attacker.")
                if combatant is None:
                    return await ctx.send("Combatant not found.")
            except SelectionException:
                return await ctx.send("Combatant not found.")

        attacks = combatant.attacks
        if '-custom' in args:
            attack = {'attackBonus': None, 'damage': None, 'name': atk_name}
        else:
            try:
                attack = await get_selection(ctx,
                                             [(a['name'], a) for a in attacks if atk_name.lower() in a['name'].lower()],
                                             message="Select your attack.")
            except SelectionException:
                return await ctx.send("Attack not found.")

        is_player = isinstance(combatant, PlayerCombatant)

        if is_player and combatant.character_owner == str(ctx.author.id):
            args = await combatant.character.parse_cvars(args, ctx)

        args = argparse(shlex.split(args))  # set up all the arguments
        args['name'] = combatant.name
        if target.ac is not None: args['ac'] = target.ac
        args['t'] = target.name
        args['resist'] = args.get('resist') or target.resists['resist']
        args['immune'] = args.get('immune') or target.resists['immune']
        args['vuln'] = args.get('vuln') or target.resists['vuln']
        args['neutral'] = args.get('neutral') or target.resists['neutral']
        if is_player:
            args['c'] = combatant.character.get_setting('critdmg') or args.get('c')
            args['reroll'] = combatant.character.get_setting('reroll') or 0
            args['crittype'] = combatant.character.get_setting('crittype') or 'default'
            args['critdice'] = (combatant.character.get_setting('critdice') or 0) + int(
                combatant.character.get_setting('hocrit', False))
            args['criton'] = combatant.character.get_setting('criton') or args.get('criton')

        result = sheet_attack(attack, args)
        embed = result['embed']

        if args.last('h', type_=bool):
            try:
                controller = ctx.guild.get_member(int(combatant.controller))
                await controller.send(embed=result['full_embed'])
            except:
                pass

        if is_player:
            embed.colour = combatant.character.get_color()
        else:
            embed.colour = random.randint(0, 0xffffff)
        if target.ac is not None and target.hp is not None:
            target.mod_hp(-result['total_damage'], overheal=False)

        if target.ac is not None:
            if target.hp is not None:
                embed.set_footer(text="{}: {}".format(target.name, target.get_hp_str()))
                if target.isPrivate:
                    try:
                        controller = ctx.guild.get_member(int(target.controller))
                        await controller.send(
                            f"{combatant.name} attacked with a {attack['name']}!"
                            f"\n{target.name}'s HP: {target.get_hp_str(True)}")
                    except:
                        pass
            else:
                embed.set_footer(text="Dealt {} damage to {}!".format(result['total_damage'], target.name))
            if target.is_concentrating() and result['total_damage'] > 0:
                embed.add_field(name="Concentration",
                                value=f"Check your concentration (DC {int(max(result['total_damage'] / 2, 10))})!")
        else:
            embed.set_footer(text="Target AC not set.")

        embeds.add_fields_from_args(embed, args.get('f', []))

        await ctx.send(embed=embed)
        await combat.final()

    @init.command()
    async def cast(self, ctx, spell_name, *, args=''):
        """Casts a spell against another combatant.
        __Valid Arguments__
        -t [target (chainable)]
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
        -phrase [phrase] - adds flavor text.
        -title [title] - changes the title of the cast. Replaces [sname] with spell name.
        -dur [duration] - changes duration of spell effects.
        int/wis/cha - different skill base for DC/AB"""
        return await self._cast(ctx, None, spell_name, args)

    @init.command()
    async def reactcast(self, ctx, combatant_name, spell_name, *, args=''):
        """Casts a spell against another combatant.
        __Valid Arguments__
        -t [target (chainable)]
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
        -phrase [phrase] - adds flavor text.
        -title [title] - changes the title of the cast. Replaces [sname] with spell name.
        int/wis/cha - different skill base for DC/AB"""
        return await self._cast(ctx, combatant_name, spell_name, args)

    async def _cast(self, ctx, combatant_name, spell_name, args):
        args = await scripting.parse_snippets(args, ctx)
        combat = await Combat.from_ctx(ctx)

        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the caster.")
                if combatant is None:
                    return await ctx.send("Combatant not found.")
            except SelectionException:
                return await ctx.send("Combatant not found.")

        if isinstance(combatant, CombatantGroup):
            return await ctx.send("Groups cannot cast spells.")

        is_character = isinstance(combatant, PlayerCombatant)

        if is_character and combatant.character_owner == str(ctx.author.id):
            args = await combatant.character.parse_cvars(args, ctx)
        args = shlex.split(args)
        args = argparse(args)

        if not args.last('i', type_=bool):
            spell = await select_spell_full(ctx, spell_name,
                                            list_filter=lambda s: s.name.lower() in combatant.spellcasting.lower_spells)
        else:
            spell = await select_spell_full(ctx, spell_name)

        targets = []
        for i, t in enumerate(args.get('t')):
            target = await combat.select_combatant(t, f"Select target #{i + 1}.", select_group=True)
            if isinstance(target, CombatantGroup):
                targets.extend(target.get_combatants())
            else:
                targets.append(target)

        result = await spell.cast(ctx, combatant, targets, args, combat=combat)

        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff) if not is_character else combatant.character.get_color()
        add_fields_from_args(embed, args.get('f'))
        await ctx.send(embed=embed)
        await combat.final()

    @init.command(name='remove')
    async def remove_combatant(self, ctx, *, name: str):
        """Removes a combatant or group from the combat.
        Usage: !init remove <NAME>"""
        combat = await Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name, select_group=True)
        if combatant is None:
            return await ctx.send("Combatant not found.")

        if combatant is combat.current_combatant:
            return await ctx.send("You cannot remove a combatant on their own turn.")

        if combatant.group is not None:
            group = combat.get_group(combatant.group)
            if len(group.get_combatants()) <= 1 and group is combat.current_combatant:
                return await ctx.send(
                    "You cannot remove a combatant if they are the only remaining combatant in this turn.")
        combat.remove_combatant(combatant)
        await ctx.send("{} removed from combat.".format(combatant.name), delete_after=10)
        await combat.final()

    @init.command()
    async def end(self, ctx, args=None):
        """Ends combat in the channel."""

        to_end = await confirm(ctx, 'Are you sure you want to end combat? (Reply with yes/no)', True)

        if to_end is None:
            return await ctx.send('Timed out waiting for a response or invalid response.', delete_after=10)
        elif not to_end:
            return await ctx.send('OK, cancelling.', delete_after=10)

        msg = await ctx.send("OK, ending...")
        if args != '-force':
            combat = await Combat.from_ctx(ctx)

            try:
                await ctx.author.send(f"End of combat report: {combat.round_num} rounds "
                                      f"{combat.get_summary(True)}")

                summary = await combat.get_summary_msg()
                await summary.edit(content=combat.get_summary() + " ```-----COMBAT ENDED-----```")
                await summary.unpin()
            except:
                pass

            await combat.end()
        else:
            await self.bot.mdb.combats.delete_one({"channel": str(ctx.channel.id)})

        await msg.edit(content="Combat ended.")


def setup(bot):
    bot.add_cog(InitTracker(bot))
