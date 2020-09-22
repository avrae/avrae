import collections
import functools
import logging
import random
import traceback

import discord
from d20 import roll
from discord.ext import commands
from discord.ext.commands import NoPrivateMessage

from aliasing import helpers
from cogs5e.funcs import attackutils, checkutils, targetutils
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor, EmbedWithCharacter
from cogs5e.models.errors import InvalidArgument, NoSelectionElements, SelectionException
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup, Effect, MonsterCombatant, PlayerCombatant
from cogs5e.models.sheet.attack import Attack
from cogs5e.models.sheet.base import Skill
from cogs5e.models.sheet.resistance import Resistances
from cogsmisc.stats import Stats
from gamedata.lookuputils import select_monster_full, select_spell_full
from utils.argparser import argparse, argsplit
from utils.functions import confirm, search_and_select, try_delete

log = logging.getLogger(__name__)

DM_ROLES = {"dm", "gm", "dungeon master", "game master"}


class InitTracker(commands.Cog):
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

    @commands.group(aliases=['i'], invoke_without_command=True)
    async def init(self, ctx):
        """Commands to help track initiative."""
        await ctx.send(f"Incorrect usage. Use {ctx.prefix}help init for help.")

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise NoPrivateMessage()
        return True

    async def cog_before_invoke(self, ctx):
        await try_delete(ctx.message)

    @init.command()
    async def begin(self, ctx, *args):
        """Begins combat in the channel the command is invoked.
        Usage: !init begin <ARGS (opt)>
        __Valid Arguments__
        dyn - Dynamic initiative; Rerolls all initiatves at the start of a round.
        turnnotif - Notifies the controller of the next combatant in initiative.
        -name <name> - Sets a name for the combat instance."""
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
            f"If it's a 5e monster: `{ctx.prefix}init madd <monster name>`\n"
            f"Otherwise: `{ctx.prefix}init add <modifier> <name>`")

    @init.command()
    async def add(self, ctx, modifier: int, name: str, *args):
        """Adds a generic combatant to the initiative order.
        Generic combatants have a 10 in every stat and +0 to every modifier.
        If a character is set up with the SheetManager module, you can use !init join instead.
        If you are adding monsters to combat, you can use !init madd instead.

        __Valid Arguments__
        -h - Hides HP, AC, resistances, and attack list.
        -p - Places combatant at the given modifier, instead of rolling
        -controller <controller> - Pings a different person on turn.
        -group <group> - Adds the combatant to a group.
        -hp <hp> - Sets starting HP. Default: None.
        -thp <thp> - Sets starting THP. Default: 0.
        -ac <ac> - Sets the combatant' AC. Default: None.
        -resist <damage type> - Gives the combatant resistance to the given damage type.
        -immune <damage type> - Gives the combatant immunity to the given damage type.
        -vuln <damage type> - Gives the combatant vulnerability to the given damage type.
        adv/dis - Rolls the initiative check with advantage/disadvantage.
        -note <note> - Sets the combatant's note.
        """
        private = False
        place = None
        controller = str(ctx.author.id)
        group = None
        hp = None
        ac = None
        resists = {}
        args = argparse(args)
        adv = args.adv(boolwise=True)

        thp = args.last('thp', type_=int)

        if args.last('h', type_=bool):
            private = True

        if args.get('p'):
            try:
                place_arg = args.last('p')
                if place_arg is True:
                    place = modifier
                else:
                    place = int(place_arg)
            except (ValueError, TypeError):
                place = modifier

        if args.last('controller'):
            controller_name = args.last('controller')
            member = await commands.MemberConverter().convert(ctx, controller_name)
            controller = str(member.id) if member is not None else controller
        if args.last('group'):
            group = args.last('group')
        if args.last('hp'):
            hp = args.last('hp', type_=int)
            if hp < 1:
                return await ctx.send("You must pass in a positive, nonzero HP with the -hp tag.")
        if args.last('ac'):
            ac = args.last('ac', type_=int)

        note = args.last('note')

        for k in ('resist', 'immune', 'vuln'):
            resists[k] = args.get(k)

        combat = await Combat.from_ctx(ctx)

        if combat.get_combatant(name) is not None:
            await ctx.send("Combatant already exists.")
            return

        if place is None:
            init_skill = Skill(modifier, adv=adv)
            init_roll = roll(init_skill.d20())
            init = init_roll.total
            init_roll_skeleton = init_roll.result
        else:
            init_skill = Skill(0, adv=adv)
            init = place
            init_roll_skeleton = str(init)

        me = Combatant.new(name, controller, init, init_skill, hp, ac, private, Resistances.from_dict(resists), ctx,
                           combat)

        # -thp (#1142)
        if thp and thp > 0:
            me.temp_hp = thp

        # -note (#1211)
        if note:
            me.notes = note

        if group is None:
            combat.add_combatant(me)
            await ctx.send(f"{name} was added to combat with initiative {init_roll_skeleton}.")
        else:
            grp = combat.get_group(group, create=init)
            grp.add_combatant(me)
            await ctx.send(f"{name} was added to combat with initiative {grp.init} as part of group {grp.name}.")

        await combat.final()

    @init.command()
    async def madd(self, ctx, monster_name: str, *args):
        """Adds a monster to combat.
        __Valid Arguments__
        adv/dis - Give advantage or disadvantage to the initiative roll.
        -b <condition bonus> - Adds a bonus to the combatant's initiative roll.
        -n <number> - Adds more than one of that monster.
        -p <value> - Places combatant at the given value, instead of rolling.
        -name <name> - Sets the combatant's name. Use "#" for auto-numbering, e.g. "Orc#"
        -h - Hides HP, AC, Resists, etc. Default: True.
        -group <group> - Adds the combatant to a group.
        -rollhp - Rolls the monsters HP, instead of using the default value.
        -hp <hp> - Sets starting HP.
        -thp <thp> - Sets starting THP.
        -ac <ac> - Sets the combatant's starting AC.
        -note <note> - Sets the combatant's note.
        """

        monster = await select_monster_full(ctx, monster_name, pm=True)

        args = argparse(args)
        private = not args.last('h', type_=bool)

        group = args.last('group')
        adv = args.adv(boolwise=True)
        b = args.join('b', '+')
        p = args.last('p', type_=int)
        rollhp = args.last('rollhp', False, bool)
        hp = args.last('hp', type_=int)
        thp = args.last('thp', type_=int)
        ac = args.last('ac', type_=int)
        n = args.last('n', 1, int)
        note = args.last('note')
        name_template = args.last('name', monster.name[:2].upper() + '#')
        init_skill = monster.skills.initiative

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
                        check_roll = roll(f'{init_skill.d20(base_adv=adv)}+{b}')
                    else:
                        check_roll = roll(init_skill.d20(base_adv=adv))
                    init = check_roll.total
                else:
                    init = int(p)
                controller = str(ctx.author.id)

                # -hp
                rolled_hp = None
                if rollhp:
                    rolled_hp = roll(monster.hitdice)
                    to_pm += f"{name} began with {rolled_hp.result} HP.\n"
                    rolled_hp = max(rolled_hp.total, 1)

                me = MonsterCombatant.from_monster(monster, ctx, combat, name, controller, init, private,
                                                   hp=hp or rolled_hp, ac=ac)

                # -thp (#1142)
                if thp and thp > 0:
                    me.temp_hp = thp

                # -note (#1211)
                if note:
                    me.notes = note

                if group is None:
                    combat.add_combatant(me)
                    out += f"{name} was added to combat with initiative {check_roll.result if p is None else p}.\n"
                else:
                    grp = combat.get_group(group, create=init)
                    grp.add_combatant(me)
                    out += f"{name} was added to combat with initiative {grp.init} as part of group {grp.name}.\n"

            except Exception as e:
                log.warning('\n'.join(traceback.format_exception(type(e), e, e.__traceback__)))
                out += "Error adding combatant: {}\n".format(e)

        await combat.final()
        await ctx.send(out)
        if to_pm:
            await ctx.author.send(to_pm)

    @init.command(name='join', aliases=['cadd', 'dcadd'])
    async def join(self, ctx, *, args: str = ''):
        """
        Adds the current active character to combat. A character must be loaded through the SheetManager module first.
        __Valid Arguments__
        adv/dis - Give advantage or disadvantage to the initiative roll.
        -b <condition bonus> - Adds a bonus to the combatants' Initiative roll.
        -phrase <phrase> - Adds flavor text.
        -thumb <thumbnail URL> - Adds flavor image.
        -p <value> - Places combatant at the given value, instead of rolling.
        -h - Hides HP, AC, Resists, etc.
        -group <group> - Adds the combatant to a group.
        -note <note> - Sets the combatant's note.
        [user snippet]
        """
        char: Character = await Character.from_ctx(ctx)
        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_character(ctx, char, args)
        args = argparse(args)

        embed = EmbedWithCharacter(char, False)

        p = args.last('p', type_=int)
        group = args.last('group')
        note = args.last('note')

        if p is None:
            args.ignore('rr')
            args.ignore('dc')
            checkutils.update_csetting_args(char, args, char.skills.initiative)
            totals = checkutils.run_check('initiative', char, args, embed)
            init = totals[-1]
        else:
            init = p
            embed.title = "{} already rolled initiative!".format(char.name)
            embed.description = "Placed at initiative `{}`.".format(init)

        controller = str(ctx.author.id)
        private = args.last('h', type_=bool)

        combat = await Combat.from_ctx(ctx)

        if combat.get_combatant(char.name) is not None:
            await ctx.send("Combatant already exists.")
            return

        me = await PlayerCombatant.from_character(char, ctx, combat, controller, init, private)

        # -note (#1211)
        if note:
            me.notes = note

        if group is None:
            combat.add_combatant(me)
            embed.set_footer(text="Added to combat!")
        else:
            grp = combat.get_group(group, create=init)
            grp.add_combatant(me)
            embed.set_footer(text=f"Joined group {grp.name}!")

        await combat.final()
        await ctx.send(embed=embed)

    @init.command(name="next", aliases=['n'])
    async def nextInit(self, ctx):
        """Moves to the next turn in initiative order.
        It must be your turn or you must be the DM (the person who started combat) to use this command."""

        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        allowed_to_pass = (combat.index is None) \
                          or (str(ctx.author.id) in (combat.current_combatant.controller, combat.dm)) \
                          or DM_ROLES.intersection({r.name.lower() for r in ctx.author.roles})
        if not allowed_to_pass:
            await ctx.send("It is not your turn.")
            return

        toRemove = []
        if combat.current_combatant is not None:
            if isinstance(combat.current_combatant, CombatantGroup):
                thisTurn = combat.current_combatant.get_combatants()
            else:
                thisTurn = [combat.current_combatant]
            for co in thisTurn:
                if isinstance(co, MonsterCombatant) and co.hp <= 0:
                    toRemove.append(co)

        advanced_round, messages = combat.advance_turn()
        out = messages

        await Stats.increase_stat(ctx, "turns_init_tracked_life")
        if advanced_round:
            await Stats.increase_stat(ctx, "rounds_init_tracked_life")

        out.append(combat.get_turn_str())

        for co in toRemove:
            combat.remove_combatant(co)
            out.append("{} automatically removed from combat.\n".format(co.name))

        await ctx.send("\n".join(out), allowed_mentions=combat.get_turn_str_mentions())
        await combat.final()

    @init.command(name="prev", aliases=['previous', 'rewind'])
    async def prevInit(self, ctx):
        """Moves to the previous turn in initiative order."""

        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        combat.rewind_turn()

        await ctx.send(combat.get_turn_str(), allowed_mentions=combat.get_turn_str_mentions())
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

        await ctx.send(combat.get_turn_str(), allowed_mentions=combat.get_turn_str_mentions())
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

        messages = combat.skip_rounds(numrounds)
        out = messages

        out.append(combat.get_turn_str())

        for co in toRemove:
            combat.remove_combatant(co)
            out.append("{} automatically removed from combat.".format(co.name))

        await ctx.send("\n".join(out), allowed_mentions=combat.get_turn_str_mentions())
        await combat.final()

    @init.command(name="reroll", aliases=['shuffle'])
    async def reroll(self, ctx, *args):
        """
        Rerolls initiative for all combatants, and starts a new round of combat.
        __Valid Arguments__
        -restart - Resets the round counter (effectively restarting initiative).
        """
        combat = await Combat.from_ctx(ctx)
        a = argparse(args)

        new_order = combat.reroll_dynamic()
        await ctx.send(f"Rerolled initiative! New order:\n{new_order}")

        # -restart (#1053)
        if a.last('restart'):
            combat.round_num = 0

        # repost summary message
        old_summary = await combat.get_summary_msg()
        new_summary = await ctx.send(combat.get_summary())
        Combat.message_cache[new_summary.id] = new_summary  # add to cache
        combat.summary = new_summary.id
        try:
            await new_summary.pin()
            await old_summary.unpin()
        except:
            pass

        await combat.final()

    @init.command(name="meta", aliases=['metaset'])
    async def metasetting(self, ctx, *settings):
        """Changes the settings of the active combat.
        __Valid Settings__
        dyn - Dynamic initiative; Rerolls all initiatves at the start of a round.
        turnnotif - Notifies the controller of the next combatant in initiative.
        -name <name> - Sets a name for the combat instance"""
        args = argparse(settings)
        combat = await Combat.from_ctx(ctx)
        options = combat.options
        out = ""

        if args.last('dyn', False, bool):  # rerolls all inits at the start of each round
            options['dynamic'] = not options.get('dynamic')
            out += f"Dynamic initiative turned {'on' if options['dynamic'] else 'off'}.\n"
        if args.last('name'):
            options['name'] = args.last('name')
            out += f"Name set to {options['name']}.\n"
        if args.last('turnnotif', False, bool):
            options['turnnotif'] = not options.get('turnnotif')
            out += f"Turn notification turned {'on' if options['turnnotif'] else 'off'}.\n"

        combat.options = options
        await combat.commit()
        await ctx.send(out)

    @init.command(name="list", aliases=['summary'])
    async def listInits(self, ctx, *args):
        """Lists the combatants.
        __Valid Arguments__
        private - Sends the list in a private message."""
        combat = await Combat.from_ctx(ctx)
        private = 'private' in args
        destination = ctx if not private else ctx.author
        if private and str(ctx.author.id) == combat.dm:
            out = combat.get_summary(True)
        else:
            out = combat.get_summary()
        await destination.send(out)

    @init.command()
    async def note(self, ctx, name: str, *, note: str = ''):
        """Attaches a note to a combatant."""
        combat = await Combat.from_ctx(ctx)

        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await ctx.send("Combatant not found.")

        combatant.notes = note
        if note == '':
            await ctx.send("Removed note.")
        else:
            await ctx.send("Added note.")
        await combat.final()

    @init.command(aliases=['opts'])
    async def opt(self, ctx, name: str, *args):
        """Edits the options of a combatant.
        __Valid Arguments__
        -h - Hides HP, AC, Resists, etc.
        -p <value> - Changes the combatants' placement in the Initiative. Adds if starts with +/- or sets otherwise.
        -name <name> - Changes the combatants' name.
        -controller <controller> - Pings a different person on turn.
        -ac <ac> - Modifies combatants' AC. Adds if starts with +/- or sets otherwise.
        -resist <damage type> - Gives the combatant resistance to the given damage type.
        -immune <damage type> - Gives the combatant immunity to the given damage type.
        -vuln <damage type> - Gives the combatant vulnerability to the given damage type.
        -neutral <damage type> - Removes the combatants' immunity, resistance, or vulnerability to the given damage type.
        -group <group> - Adds the combatant to a group. To remove them from group, use -group None.
        -max <maxhp> - Modifies the combatants' Max HP. Adds if starts with +/- or sets otherwise.
        -hp <hp> - Modifies current HP. Adds if starts with +/- or sets otherwise."""
        combat = await Combat.from_ctx(ctx)

        comb = await combat.select_combatant(name, select_group=True)
        if comb is None:
            await ctx.send("Combatant not found.")
            return

        args = argparse(args)
        options = {}
        target_is_group = isinstance(comb, CombatantGroup)
        run_once = set()
        allowed_mentions = []

        def option(opt_name=None, pass_group=False, **kwargs):
            """
            Wrapper to register an option.
            :param str opt_name: The string to register the function under. Defaults to function name.
            :param bool pass_group: Whether to pass a group as the first argument to the function or a combatant.
            :param kwargs: kwargs that will always be passed to the function.
            """

            def wrapper(func):
                func_name = opt_name or func.__name__
                if pass_group and target_is_group:
                    old_func = func

                    async def func(_, *a, **k):
                        if func_name in run_once:
                            return
                        run_once.add(func_name)
                        return await old_func(comb, *a, **k)  # pop the combatant argument and sub in group
                func = options[func_name] = functools.partial(func, **kwargs)
                return func

            return wrapper

        def mod_or_set(opt_name, old_value):
            new_value = args.last(opt_name, type_=int)
            if args.last(opt_name).startswith(('-', '+')):
                new_value = (old_value or 0) + new_value
            return new_value, old_value

        @option()
        async def h(combatant):
            combatant.is_private = not combatant.is_private
            return f"\u2705 {combatant.name} {'hidden' if combatant.is_private else 'unhidden'}."

        @option()
        async def controller(combatant):
            controller_name = args.last('controller')
            member = await commands.MemberConverter().convert(ctx, controller_name)
            if member is None:
                return "\u274c New controller not found."
            allowed_mentions.append(member)
            combatant.controller = str(member.id)
            return f"\u2705 {combatant.name}'s controller set to {combatant.controller_mention()}."

        @option()
        async def ac(combatant):
            try:
                new_ac, old_ac = mod_or_set('ac', combatant.ac)
                combatant.ac = new_ac
                return f"\u2705 {combatant.name}'s AC set to {combatant.ac} (was {old_ac})."
            except InvalidArgument as e:
                return f"\u274c {str(e)}"

        @option(pass_group=True)
        async def p(combatant):
            if combatant is combat.current_combatant:
                return "\u274c You cannot change a combatant's initiative on their own turn."
            try:
                new_init, old_init = mod_or_set('p', combatant.init)
                combatant.init = new_init
                combat.sort_combatants()
                return f"\u2705 {combatant.name}'s initiative set to {combatant.init} (was {old_init})."
            except InvalidArgument as e:
                return f"\u274c {str(e)}"

        @option()
        async def group(combatant):
            current = combat.current_combatant
            was_current = combatant is current or \
                          (isinstance(current, CombatantGroup) and combatant in current and len(current) == 1)
            group_name = args.last('group')
            combat.remove_combatant(combatant, ignore_remove_hook=True)
            if group_name.lower() == 'none':
                combat.add_combatant(combatant)
                if was_current:
                    combat.goto_turn(combatant, True)
                return f"\u2705 {combatant.name} removed from all groups."
            else:
                c_group = combat.get_group(group_name, create=combatant.init)
                c_group.add_combatant(combatant)
                if was_current:
                    combat.goto_turn(combatant, True)
                return f"\u2705 {combatant.name} added to group {c_group.name}."

        @option(pass_group=True)
        async def name(combatant):
            old_name = combatant.name
            new_name = args.last('name')
            if combat.get_combatant(new_name, True) is not None:
                return f"\u274c There is already another combatant with the name {new_name}."
            elif new_name:
                combatant.name = new_name
                return f"\u2705 {old_name}'s name set to {new_name}."
            else:
                return "\u274c You must pass in a name with the -name tag."

        @option("max")
        async def max_hp(combatant):
            new_max, old_max = mod_or_set('max', combatant.max_hp)
            if new_max < 1:
                return "\u274c Max HP must be at least 1."
            else:
                combatant.max_hp = new_max
                return f"\u2705 {combatant.name}'s HP max set to {new_max} (was {old_max})."

        @option()
        async def hp(combatant):
            new_hp, old_hp = mod_or_set('hp', combatant.hp)
            combatant.set_hp(new_hp)
            return f"\u2705 {combatant.name}'s HP set to {new_hp} (was {old_hp})."

        @option("resist", resist_type="resist")
        @option("immune", resist_type="immune")
        @option("vuln", resist_type="vuln")
        @option("neutral", resist_type="neutral")
        async def resist(combatant, resist_type):
            result = []
            for damage_type in args.get(resist_type):
                damage_type = damage_type.lower()
                combatant.set_resist(damage_type, resist_type)
                result.append(damage_type)
            return f"\u2705 Updated {combatant.name}'s {resist_type}s: {', '.join(result)}"

        # run options
        if target_is_group:
            targets = comb.get_combatants().copy()
        else:
            targets = [comb]
        out = collections.defaultdict(lambda: [])

        for arg_name, opt_func in options.items():
            if arg_name in args:
                for target in targets:
                    response = await opt_func(target)
                    if response:
                        if target.is_private:
                            destination = ctx.guild.get_member(int(comb.controller)) or ctx.channel
                        else:
                            destination = ctx.channel
                        out[destination].append(response)

        if out:
            for destination, messages in out.items():
                await destination.send('\n'.join(messages),
                                       allowed_mentions=discord.AllowedMentions(users=allowed_mentions))
            await combat.final()
        else:
            await ctx.send("No valid options found.")

    @init.command()
    async def status(self, ctx, name: str = '', *, args: str = ''):
        """Gets the status of a combatant or group.
        If no name is specified, it will default to current combatant.
        __Valid Arguments__
        private - PMs the controller of the combatant a more detailed status."""

        combat = await Combat.from_ctx(ctx)

        if name == 'private' or name == '':
            combatant = combat.current_combatant
        else:
            combatant = await combat.select_combatant(name, select_group=True)

        if combatant is None:
            await ctx.send("Combatant or group not found.")
            return

        private = 'private' in args.lower() or name == 'private'
        if not isinstance(combatant, CombatantGroup):
            private = private and str(ctx.author.id) == combatant.controller
            status = combatant.get_status(private=private)
            if private and isinstance(combatant, MonsterCombatant):
                status = f"{status}\n* This creature is a {combatant.monster_name}."
        else:
            status = "\n".join([co.get_status(private=private and str(ctx.author.id) == co.controller) for co in
                                combatant.get_combatants()])

        if private:
            controller = ctx.guild.get_member(int(combatant.controller))
            if controller:
                await controller.send("```markdown\n" + status + "```")
        else:
            await ctx.send("```markdown\n" + status + "```")

    @staticmethod
    async def _send_hp_result(ctx, combatant, delta=None):
        deltaend = f" ({delta})" if delta else ""

        if combatant.is_private:
            await ctx.send(f"{combatant.name}: {combatant.hp_str()}")
            try:
                controller = ctx.guild.get_member(int(combatant.controller))
                await controller.send(f"{combatant.name}'s HP: {combatant.hp_str(True)}{deltaend}")
            except:
                pass
        else:
            await ctx.send(f"{combatant.name}: {combatant.hp_str()}{deltaend}")

    @init.group(invoke_without_command=True)
    async def hp(self, ctx, name: str, *, hp: str = None):
        """Modifies the HP of a combatant."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await ctx.send("Combatant not found.")

        if hp is None:
            await ctx.send(f"{combatant.name}: {combatant.hp_str()}")
            if combatant.is_private:
                try:
                    controller = ctx.guild.get_member(int(combatant.controller))
                    await controller.send(f"{combatant.name}'s HP: {combatant.hp_str(True)}")
                except:
                    pass
            return

        # i hp NAME mod X does not call i hp mod NAME X - handle this
        if hp.startswith('mod '):
            return await ctx.invoke(self.init_hp_mod, name=name, hp=hp[4:])
        elif hp.startswith('set '):
            return await ctx.invoke(self.init_hp_set, name=name, hp=hp[4:])
        elif hp.startswith('max ') or hp == 'max':
            return await ctx.invoke(self.init_hp_max, name=name, hp=hp[3:].strip())

        hp_roll = roll(hp)
        if combatant.hp is None:
            combatant.set_hp(0)
        combatant.modify_hp(hp_roll.total)
        await combat.final()
        if 'd' in hp:
            delta = hp_roll.result
        else:
            delta = f"{hp_roll.total:+}"

        await self._send_hp_result(ctx, combatant, delta)

    @hp.command(name='max')
    async def init_hp_max(self, ctx, name, *, hp: str = None):
        """Sets a combatant's max HP, or sets HP to max if no max is given."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await ctx.send("Combatant not found.")

        delta = None
        if not hp:
            before = combatant.hp or 0
            combatant.set_hp(combatant.max_hp)
            delta = f"{combatant.hp - before:+}"
        else:
            hp_roll = roll(hp)
            if hp_roll.total < 1:
                return await ctx.send("You can't have a negative max HP!")
            combatant.max_hp = hp_roll.total

        await combat.final()
        await self._send_hp_result(ctx, combatant, delta)

    @hp.command(name='mod', hidden=True)
    async def init_hp_mod(self, ctx, name, *, hp):
        """Modifies a combatant's current HP."""
        await ctx.invoke(self.hp, name=name, hp=hp)

    @hp.command(name='set')
    async def init_hp_set(self, ctx, name, *, hp):
        """Sets a combatant's HP to a certain value."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            return await ctx.send("Combatant not found.")

        before = combatant.hp or 0
        hp_roll = roll(hp)
        combatant.set_hp(hp_roll.total)
        await combat.final()
        await self._send_hp_result(ctx, combatant, f"{combatant.hp - before:+}")

    @init.command()
    async def thp(self, ctx, name: str, *, thp: str):
        """Modifies the temporary HP of a combatant.
        Usage: !init thp <NAME> <HP>
        Sets the combatants' THP if hp is positive, modifies it otherwise (i.e. `!i thp Avrae 5` would set Avrae's THP to 5 but `!i thp Avrae -2` would remove 2 THP)."""
        combat = await Combat.from_ctx(ctx)
        combatant = await combat.select_combatant(name)
        if combatant is None:
            await ctx.send("Combatant not found.")
            return

        thp_roll = roll(thp)
        value = thp_roll.total

        if value >= 0:
            combatant.temp_hp = value
        else:
            combatant.temp_hp += value

        delta = ""
        if 'd' in thp:
            delta = f"({thp_roll.result})"

        if combatant.is_private:
            await ctx.send(f"{combatant.name}: {combatant.hp_str()}")
            try:
                controller = ctx.guild.get_member(int(combatant.controller))
                await controller.send(f"{combatant.name}'s HP: {combatant.hp_str(True)} {delta}")
            except:
                pass
        else:
            await ctx.send(f"{combatant.name}: {combatant.hp_str()} {delta}")
        await combat.final()

    @init.command()
    async def effect(self, ctx, target_name: str, effect_name: str, *args):
        """Attaches a status effect to a combatant.
        [args] is a set of args that affects a combatant in combat.
        See `!help init re` to remove effects.
        __**Valid Arguments**__
        -dur <duration> - Sets the duration of the effect, in rounds.
        conc - Makes the effect require concentration. Will end any other concentration effects.
        end - Makes the effect duration tick on the end of turn, rather than the beginning.
        -t <target> - Specifies more combatant's to target, chainable (e.g., "-t or1 -t or2").
        -parent <"[combatant]|[effect]"> - Sets a parent effect from a specified combatant.
        __Attacks__
        -b <bonus> - Adds a bonus to hit.
        -d <damage> - Adds additional damage.
        -attack <"[hit]|[damage]|[description]"> - Adds an attack to the combatant. The effect name will be the name of the attack. No [hit] will autohit (e.g., -attack "|1d6[fire]|")
        __Resists__
        -resist <damage type> - Gives the combatant resistance to the given damage type.
        -immune <damage type> - Gives the combatant immunity to the given damage type.
        -vuln <damage type> - Gives the combatant vulnerability to the given damage type.`-custom` - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add damage and to hit.
        -neutral <damage type> - Removes the combatant's immunity, resistance, or vulnerability to the given damage type.
        __General__
        -ac <ac> - modifies ac temporarily; adds if starts with +/- or sets otherwise.
        -sb <save bonus> - Adds a bonus to all saving throws."""
        combat = await Combat.from_ctx(ctx)
        args = argparse(args)

        targets = []

        for i, t in enumerate([target_name] + args.get('t')):
            target = await combat.select_combatant(t, f"Select target #{i + 1}.", select_group=True)
            if isinstance(target, CombatantGroup):
                targets.extend(target.get_combatants())
            else:
                targets.append(target)

        duration = args.last('dur', -1, int)
        conc = args.last('conc', False, bool)
        end = args.last('end', False, bool)
        parent = args.last('parent')

        if parent is not None:
            parent = parent.split('|', 1)
            if not len(parent) == 2:
                raise InvalidArgument("`parent` arg must be formatted `COMBATANT|EFFECT_NAME`")
            p_combatant = await combat.select_combatant(parent[0],
                                                        choice_message="Select the combatant with the parented effect.")
            parent = await p_combatant.select_effect(parent[1])

        embed = EmbedWithAuthor(ctx)
        for combatant in targets:
            if effect_name.lower() in (e.name.lower() for e in combatant.get_effects()):
                out = "Effect already exists."
            else:
                effect_obj = Effect.new(combat, combatant, duration=duration, name=effect_name, effect_args=args,
                                        concentration=conc, tick_on_end=end)
                result = combatant.add_effect(effect_obj)
                if parent:
                    effect_obj.set_parent(parent)
                out = f"Added effect {effect_name} to {combatant.name}."
                if result['conc_conflict']:
                    conflicts = [e.name for e in result['conc_conflict']]
                    out += f"\nRemoved {', '.join(conflicts)} due to concentration conflict!"
            embed.add_field(name=combatant.name, value=out)
        await ctx.send(embed=embed)
        await combat.final()

    @init.command(name='re')
    async def remove_effect(self, ctx, name: str, effect: str = None):
        """Removes a status effect from a combatant or group. Removes all if effect is not passed."""
        combat = await Combat.from_ctx(ctx)

        targets = []

        target = await combat.select_combatant(name, select_group=True)
        if isinstance(target, CombatantGroup):
            targets.extend(target.get_combatants())
        else:
            targets.append(target)

        out = ""

        for combatant in targets:
            if effect is None:
                combatant.remove_all_effects()
                out += f"All effects removed from {combatant.name}.\n"
            else:
                to_remove = await combatant.select_effect(effect)
                children_removed = ""
                if to_remove.children:
                    children_removed = f"Also removed {len(to_remove.children)} child effects.\n"
                to_remove.remove()
                out += f'Effect {to_remove.name} removed from {combatant.name}.\n{children_removed}'
        await ctx.send(out)
        await combat.final()

    @init.group(aliases=['a'], invoke_without_command=True)
    async def attack(self, ctx, atk_name, *, args=''):
        """Rolls an attack against another combatant.
        __Valid Arguments__
        -t "<target>" - Sets targets for the attack. You can pass as many as needed.
        -t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        *adv/dis* - Give advantage or disadvantage to the attack roll(s).
        *ea* - Elven Accuracy, double advantage on the attack roll.

        *-b <bonus>* - Adds a bonus to hit.

        -criton <value> - The number the attack crits on if rolled on or above.
        *-d <damage>* - Adds additional damage.
        *-c <damage>* - Adds additional damage for when the attack crits, not doubled.
        -rr <value> - How many attacks to make at the target.
        *-mi <value>* - Minimum value of each die on the damage roll.

        *-resist <damage type>* - Gives the target resistance to the given damage type.
        *-immune <damage type>* - Gives the target immunity to the given damage type.
        *-vuln <damage type>* - Gives the target vulnerability to the given damage type.
        *-neutral <damage type>* - Removes the targets immunity, resistance, or vulnerability to the given damage type.

        *hit* - The attack automatically hits.
        *miss* - The attack automatically misses.
        *crit* - The attack automatically crits.
        *max* - Maximizes damage rolls.

        -h - Hides rolled values.
        -phrase <phrase> - Adds flavor text.
        -title <title> - Changes the title of the attack. Replaces [name] with attackers name and [aname] with the attacks name.
        -f "Field Title|Field Text" - Creates a field with the given title and text.
        -thumb <url> - Adds a thumbnail to the attack.
        [user snippet] - Allows the user to use snippets on the attack.

        -custom - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add to hit and damage.

        An italicized argument means the argument supports ephemeral arguments - e.g. `-d1` applies damage to the first hit, `-b1` applies a bonus to one attack, and so on."""
        return await self._attack(ctx, None, atk_name, args)

    @attack.command(name="list")
    async def attack_list(self, ctx):
        """Lists the active combatant's attacks."""
        combat = await Combat.from_ctx(ctx)
        combatant = combat.current_combatant
        if combatant is None:
            return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")

        if combatant.is_private and combatant.controller != str(ctx.author.id) and str(ctx.author.id) != combat.dm:
            return await ctx.send("You do not have permission to view this combatant's attacks.")

        atk_str = combatant.attacks.build_str(combatant)
        if len(atk_str) > 1000:
            atk_str = f"{atk_str[:1000]}\n[...]"

        if not combatant.is_private:
            destination = ctx.message.channel
        else:
            destination = ctx.message.author
        return await destination.send("{}'s attacks:\n{}".format(combatant.name, atk_str))

    @init.command()
    async def aoo(self, ctx, combatant_name, atk_name, *, args=''):
        """Rolls an attack of opportunity against another combatant.
        __Valid Arguments__
        -t "<target>" - Sets targets for the attack. You can pass as many as needed.
        -t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        *adv/dis* - Give advantage or disadvantage to the attack roll(s).
        *ea* - Elven Accuracy, double advantage on the attack roll.

        *-b <bonus>* - Adds a bonus to hit.

        -criton <value> - The number the attack crits on if rolled on or above.
        *-d <damage>* - Adds additional damage.
        *-c <damage>* - Adds additional damage for when the attack crits, not doubled.
        -rr <value> - How many attacks to make at the target.
        *-mi <value>* - Minimum value on the attack roll.

        *-resist <damage type>* - Gives the target resistance to the given damage type.
        *-immune <damage type>* - Gives the target immunity to the given damage type.
        *-vuln <damage type>* - Gives the target vulnerability to the given damage type.
        *-neutral <damage type>* - Removes the targets immunity, resistance, or vulnerability to the given damage type.

        *hit* - The attack automatically hits.
        *miss* - The attack automatically misses.
        *crit* - The attack automatically crits.
        *max* - Maximizes damage rolls.

        -h - Hides rolled values.
        -phrase <phrase> - Adds flavor text.
        -title <title> - Changes the title of the attack. Replaces [name] with attackers name and [aname] with the attacks name.
        -f "Field Title|Field Text" - Creates a field with the given title and text.
        -thumb <url> - Adds a thumbnail to the attack.
        [user snippet] - Allows the user to use snippets on the attack.

        -custom - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add to hit and damage.

        An italicized argument means the argument supports ephemeral arguments - e.g. `-d1` applies damage to the first hit, `-b1` applies a bonus to one attack, and so on."""
        return await self._attack(ctx, combatant_name, atk_name, args)

    @staticmethod
    async def _attack(ctx, combatant_name, atk_name, unparsed_args):
        args = await helpers.parse_snippets(unparsed_args, ctx)
        raw_args = argsplit(unparsed_args)
        combat = await Combat.from_ctx(ctx)

        # attacker handling
        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the attacker.")
            except SelectionException:
                return await ctx.send("Combatant not found.")

        # argument parsing
        is_player = isinstance(combatant, PlayerCombatant)
        if is_player and combatant.character_owner == str(ctx.author.id):
            args = await helpers.parse_with_character(ctx, combatant.character, args)
        else:
            args = await helpers.parse_with_statblock(ctx, combatant, args)
        args = argparse(args)

        # handle old targeting method
        target_name = None
        if 't' not in args and len(raw_args) > 0:
            target_name = atk_name
            atk_name = raw_args[0]

        # attack selection/caster handling
        try:
            if isinstance(combatant, CombatantGroup):
                if 'custom' in args:  # group, custom
                    caster = combatant.get_combatants()[0]
                    attack = Attack.new(name=atk_name, bonus_calc='0', damage_calc='0')
                else:  # group, noncustom
                    choices = []  # list of (name, caster, attack)
                    for com in combatant.get_combatants():
                        for atk in com.attacks:
                            choices.append((f"{atk.name} ({com.name})", com, atk))

                    _, caster, attack = await search_and_select(ctx, choices, atk_name, lambda choice: choice[0],
                                                                message="Select your attack.")
            else:
                caster = combatant
                if 'custom' in args:  # single, custom
                    attack = Attack.new(name=atk_name, bonus_calc='0', damage_calc='0')
                else:  # single, noncustom
                    attack = await search_and_select(ctx, combatant.attacks, atk_name, lambda a: a.name,
                                                     message="Select your attack.")
        except SelectionException:
            return await ctx.send("Attack not found.")

        # target handling
        if 't' not in args and target_name is not None:
            # old single-target
            targets = []
            try:
                target = await combat.select_combatant(target_name, "Select the target.", select_group=True)
                if isinstance(target, CombatantGroup):
                    targets.extend(target.get_combatants())
                else:
                    targets.append(target)
            except SelectionException:
                return await ctx.send("Target not found.")
            await ctx.author.send(f"You are using the old targeting syntax, which is deprecated. "
                                  f"In the future, you should use "
                                  f"`{ctx.prefix}init attack {atk_name} -t {target_name}`!")
        else:
            # multi-targeting
            targets = await targetutils.definitely_combat(combat, args, allow_groups=True)

        # embed setup
        embed = discord.Embed()
        if is_player:
            embed.colour = combatant.character.get_color()
        else:
            embed.colour = random.randint(0, 0xffffff)

        # run
        await attackutils.run_attack(ctx, embed, args, caster, attack, targets, combat)

        await ctx.send(embed=embed)

    @init.command()
    async def cast(self, ctx, spell_name, *, args=''):
        """Casts a spell against another combatant.
        __Valid Arguments__
        -t "<target>" - Sets targets for the spell. You can pass as many as needed.
        -t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        -i - Ignores Spellbook restrictions, for demonstrations or rituals.
        -l <level> - Specifies the level to cast the spell at.
        noconc - Ignores concentration requirements.
        -h - Hides rolled values.
        **__Save Spells__**
        -dc <Save DC> - Overrides the spell save DC.
        -save <Save type> - Overrides the spell save type.
        -d <damage> - Adds additional damage.
        pass - Target automatically succeeds save.
        fail - Target automatically fails save.
        adv/dis - Target makes save at advantage/disadvantage.
        **__Attack Spells__**
        See `!a`.
        **__All Spells__**
        -phrase <phrase> - adds flavor text.
        -title <title> - changes the title of the cast. Replaces [sname] with spell name.
        -thumb <url> - adds an image to the cast.
        -dur <duration> - changes the duration of any effect applied by the spell.
        -mod <spellcasting mod> - sets the value of the spellcasting ability modifier.
        int/wis/cha - different skill base for DC/AB (will not account for extra bonuses)"""
        return await self._cast(ctx, None, spell_name, args)

    @init.command(aliases=['rc'])
    async def reactcast(self, ctx, combatant_name, spell_name, *, args=''):
        """Casts a spell against another combatant, as a reaction.
        __Valid Arguments__
        -t "[target]" - Sets targets for the spell. You can pass as many as needed.
        -t "[target]|[args]" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        -i - Ignores Spellbook restrictions, for demonstrations or rituals.
        -l <level> - Specifies the level to cast the spell at.
        noconc - Ignores concentration requirements.
        -h - Hides rolled values.
        **__Save Spells__**
        -dc <Save DC> - Overrides the spell save DC.
        -save <Save type> - Overrides the spell save type.
        -d <damage> - Adds additional damage.
        pass - Target automatically succeeds save.
        fail - Target automatically fails save.
        adv/dis - Target makes save at advantage/disadvantage.
        **__Attack Spells__**
        See `!a`.
        **__All Spells__**
        -phrase <phrase> - adds flavor text.
        -title <title> - changes the title of the cast. Replaces [sname] with spell name.
        -thumb <url> - adds an image to the cast.
        -dur <duration> - changes the duration of any effect applied by the spell.
        -mod <spellcasting mod> - sets the value of the spellcasting ability modifier.
        int/wis/cha - different skill base for DC/AB (will not account for extra bonuses)"""
        return await self._cast(ctx, combatant_name, spell_name, args)

    @staticmethod
    async def _cast(ctx, combatant_name, spell_name, args):
        args = await helpers.parse_snippets(args, ctx)
        combat = await Combat.from_ctx(ctx)

        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the caster.")
            except SelectionException:
                return await ctx.send("Combatant not found.")

        if isinstance(combatant, CombatantGroup):
            return await ctx.send("Groups cannot cast spells.")

        is_character = isinstance(combatant, PlayerCombatant)

        if is_character and combatant.character_owner == str(ctx.author.id):
            args = await helpers.parse_with_character(ctx, combatant.character, args)
        else:
            args = await helpers.parse_with_statblock(ctx, combatant, args)
        args = argparse(args)

        if not args.last('i', type_=bool):
            try:
                spell = await select_spell_full(ctx, spell_name,
                                                list_filter=lambda s: s.name in combatant.spellbook)
            except NoSelectionElements:
                return await ctx.send(f"No matching spells found in the combatant's spellbook. Cast again "
                                      f"with the `-i` argument to ignore restrictions!")
        else:
            spell = await select_spell_full(ctx, spell_name)

        targets = await targetutils.definitely_combat(combat, args, allow_groups=True)

        result = await spell.cast(ctx, combatant, targets, args, combat=combat)

        embed = result['embed']
        embed.colour = random.randint(0, 0xffffff) if not is_character else combatant.character.get_color()
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
        await ctx.send("{} removed from combat.".format(combatant.name))
        await combat.final()

    @init.command()
    async def end(self, ctx, args=None):
        """Ends combat in the channel.
        __Valid Arguments__
        -force - Forces an init to end, in case it's erroring."""

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
