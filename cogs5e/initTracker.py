import collections
import functools
import logging
import traceback

import discord
from d20 import roll
from discord.ext import commands
from discord.ext.commands import NoPrivateMessage

from aliasing import helpers
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor, EmbedWithCharacter
from cogs5e.models.errors import InvalidArgument, NoSelectionElements, SelectionException
from cogs5e.models.initiative import Combat, Combatant, CombatantGroup, Effect, MonsterCombatant, PlayerCombatant
from cogs5e.models.sheet.attack import Attack
from cogs5e.models.sheet.base import Skill
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.utils import actionutils, checkutils, gameutils, targetutils
from cogs5e.utils.help_constants import *
from cogsmisc.stats import Stats
from gamedata.lookuputils import select_monster_full, select_spell_full
from utils import constants
from utils.argparser import argparse
from utils.functions import confirm, get_guild_member, search_and_select, try_delete

log = logging.getLogger(__name__)


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
        dyn - Dynamic initiative; Rerolls all initiatives at the start of a round.
        turnnotif - Notifies the controller of the next combatant in initiative.
        deathdelete - Disables deleting monsters below 0 hp.
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
        if args.last('deathdelete', False, bool):
            options['deathdelete'] = True

        temp_summary_msg = await ctx.send("```Awaiting combatants...```")

        combat = Combat.new(str(ctx.channel.id), temp_summary_msg.id, str(ctx.author.id), options, ctx)
        await combat.final()

        try:
            await temp_summary_msg.pin()
        except discord.HTTPException:
            pass
        await ctx.send(
            f"Everyone roll for initiative!\n"
            f"If you have a character set up with SheetManager: `{ctx.prefix}init join`\n"
            f"If it's a 5e monster: `{ctx.prefix}init madd <monster name>`\n"
            f"Otherwise: `{ctx.prefix}init add <modifier> <name>`"
        )

    @init.command()
    async def add(self, ctx, modifier: int, name: str, *args):
        """Adds a generic combatant to the initiative order.
        Generic combatants have a 10 in every stat and +0 to every modifier.
        If a character is set up with the SheetManager module, you can use !init join instead.
        If you are adding monsters to combat, you can use !init madd instead.

        __Valid Arguments__
        `-h` - Hides HP, AC, resistances, and attack list.
        `-p` - Places combatant at the given modifier, instead of rolling
        `-controller <controller>` - Pings a different person on turn.
        `-group <group>` - Adds the combatant to a group.
        `-hp <hp>` - Sets starting HP. Default: None.
        `-thp <thp>` - Sets starting THP. Default: 0.
        `-ac <ac>` - Sets the combatant' AC. Default: None.
        `-resist` <damage type> - Gives the combatant resistance to the given damage type.
        `-immune` <damage type> - Gives the combatant immunity to the given damage type.
        `-vuln` <damage type> - Gives the combatant vulnerability to the given damage type.
        `adv`/`dis` - Rolls the initiative check with advantage/disadvantage.
        `-note <note>` - Sets the combatant's note.
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
            controller = str(member.id) if member is not None and not member.bot else controller
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

        me = Combatant.new(
            name, controller, init, init_skill, hp, ac, private, Resistances.from_dict(resists), ctx,
            combat
        )

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
        `adv`/`dis` - Give advantage or disadvantage to the initiative roll.
        `-b <condition bonus>` - Adds a bonus to the combatant's initiative roll.
        `-n <number or dice>` - Adds more than one of that monster. Supports dice.
        `-p <value>` - Places combatant at the given value, instead of rolling.
        `-controller <controller>` - Pings a different person on turn.
        `-name <name>` - Sets the combatant's name. Use "#" for auto-numbering, e.g. "Orc#"
        `-h` - Hides HP, AC, Resists, etc. Default: True.
        `-group <group>` - Adds the combatant to a group.
        `-rollhp` - Rolls the monsters HP, instead of using the default value.
        `-hp <hp>` - Sets starting HP.
        `-thp <thp>` - Sets starting THP.
        `-ac <ac>` - Sets the combatant's starting AC.
        `-note <note>` - Sets the combatant's note.
        """

        monster = await select_monster_full(ctx, monster_name, pm=True)

        args = argparse(args)
        private = not args.last('h', type_=bool)
        controller = str(ctx.author.id)
        group = args.last('group')
        adv = args.adv(boolwise=True)
        b = args.join('b', '+')
        p = args.last('p', type_=int)
        rollhp = args.last('rollhp', False, bool)
        hp = args.last('hp', type_=int)
        thp = args.last('thp', type_=int)
        ac = args.last('ac', type_=int)
        n = args.last('n', 1)
        note = args.last('note')
        name_template = args.last('name', monster.name[:2].upper() + '#')
        init_skill = monster.skills.initiative

        combat = await Combat.from_ctx(ctx)

        out = ''
        to_pm = ''

        try:  # Attempt to get the add as a number
            n_result = int(n)
        except ValueError:  # if we're not a number, are we dice
            roll_result = roll(str(n))
            n_result = roll_result.total
            out += f"Rolling random number of combatants: {roll_result}\n"

        recursion = 25 if n_result > 25 else 1 if n_result < 1 else n_result

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

                # -controller (#1368)    
                if args.last('controller'):
                    controller_name = args.last('controller')
                    member = await commands.MemberConverter().convert(ctx, controller_name)
                    controller = str(member.id) if member is not None and not member.bot else controller

                # -hp
                rolled_hp = None
                if rollhp:
                    rolled_hp = roll(monster.hitdice)
                    to_pm += f"{name} began with {rolled_hp.result} HP.\n"
                    rolled_hp = max(rolled_hp.total, 1)

                me = MonsterCombatant.from_monster(
                    monster, ctx, combat, name, controller, init, private,
                    hp=hp or rolled_hp, ac=ac
                )

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
        `adv`/`dis` - Give advantage or disadvantage to the initiative roll.
        `-b <condition bonus>` - Adds a bonus to the combatants' Initiative roll.
        `-phrase <phrase>` - Adds flavor text.
        `-thumb <thumbnail URL>` - Adds flavor image.
        `-p <value>` - Places combatant at the given value, instead of rolling.
        `-h` - Hides HP, AC, Resists, etc.
        `-group <group>` - Adds the combatant to a group.
        `-note <note>` - Sets the combatant's note.
        [user snippet]
        """
        char: Character = await Character.from_ctx(ctx)
        args = await helpers.parse_snippets(args, ctx, character=char)
        args = argparse(args)

        embed = EmbedWithCharacter(char, False)

        p = args.last('p', type_=int)
        group = args.last('group')
        note = args.last('note')
        check_result = None

        if p is None:
            args.ignore('rr')
            args.ignore('dc')
            checkutils.update_csetting_args(char, args, char.skills.initiative)
            check_result = checkutils.run_check('initiative', char, args, embed)
            init = check_result.rolls[-1].total
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
        if (gamelog := self.bot.get_cog('GameLog')) and check_result is not None:
            await gamelog.send_check(ctx, me.character, check_result.skill_name, check_result.rolls)

    @init.command(name="next", aliases=['n'])
    async def init_next(self, ctx):
        """
        Moves to the next turn in initiative order.
        It must be your turn or you must be a DM to use this command.
        A DM is the user who started combat and anyone with the "DM", "GM", "Dungeon Master" or "Game Master" role.
        """

        combat = await Combat.from_ctx(ctx)
        servsettings = await ctx.get_server_settings()

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        # check: is the user allowed to move combat on
        author_id = str(ctx.author.id)
        allowed_to_pass = (
                (combat.index is None)  # no one's turn
                or author_id == combat.current_combatant.controller  # user's turn
                or author_id == combat.dm  # user is combat starter
                or servsettings.is_dm(ctx.author)  # user is DM
        )
        if not allowed_to_pass:
            await ctx.send("It is not your turn.")
            return

        # get the list of combatants to remove, but don't remove them yet (we need to advance the turn first
        # to prevent a re-sort happening if the last combatant on a turn is removed)
        to_remove = []
        if combat.current_combatant is not None and not combat.options.get('deathdelete', False):
            if isinstance(combat.current_combatant, CombatantGroup):
                this_turn = combat.current_combatant.get_combatants()
            else:
                this_turn = [combat.current_combatant]
            for co in this_turn:
                if isinstance(co, MonsterCombatant) and co.hp <= 0:
                    to_remove.append(co)

        # actually advance the turn
        advanced_round, out = combat.advance_turn()

        # now we can remove the combatants
        removed_messages = []
        for co in to_remove:
            combat.remove_combatant(co)
            removed_messages.append(f"{co.name} automatically removed from combat.")

        # misc stat stuff
        await Stats.increase_stat(ctx, "turns_init_tracked_life")
        if advanced_round:
            await Stats.increase_stat(ctx, "rounds_init_tracked_life")

        # build the output
        if combat.current_combatant is None:
            out.append('\nNo combatants remain.')
        else:
            out.append(combat.get_turn_str())
        out.extend(removed_messages)

        # send and commit
        await ctx.send("\n".join(out), allowed_mentions=combat.get_turn_str_mentions())
        await combat.final()

    @init.command(name="prev", aliases=['previous', 'rewind'])
    async def init_prev(self, ctx):
        """Moves to the previous turn in initiative order."""

        combat = await Combat.from_ctx(ctx)

        if len(combat.get_combatants()) == 0:
            await ctx.send("There are no combatants.")
            return

        combat.rewind_turn()

        await ctx.send(combat.get_turn_str(), allowed_mentions=combat.get_turn_str_mentions())
        await combat.final()

    @init.command(name="move", aliases=['goto'])
    async def init_move(self, ctx, target=None):
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

        to_remove = []
        for co in combat.get_combatants():
            if isinstance(co, MonsterCombatant) and co.hp <= 0 and co is not combat.current_combatant:
                to_remove.append(co)

        messages = combat.skip_rounds(numrounds)
        out = messages

        if (turn_str := combat.get_turn_str()) is not None:
            out.append(turn_str)
        else:
            out.append(combat.get_summary())

        for co in to_remove:
            combat.remove_combatant(co)
            out.append("{} automatically removed from combat.".format(co.name))

        await ctx.send("\n".join(out), allowed_mentions=combat.get_turn_str_mentions())
        await combat.final()

    @init.command(name="reroll", aliases=['shuffle'])
    async def reroll(self, ctx, *args):
        """
        Rerolls initiative for all combatants, and starts a new round of combat.
        __Valid Arguments__
        `-restart` - Resets the round counter (effectively restarting initiative).
        """
        combat = await Combat.from_ctx(ctx)
        a = argparse(args)

        new_order = combat.reroll_dynamic()
        await ctx.send(f"Rerolled initiative! New order:\n{new_order}")

        # -restart (#1053)
        if a.last('restart'):
            combat.round_num = 0

        # repost summary message
        old_summary = combat.get_summary_msg()
        new_summary = await ctx.send(combat.get_summary())
        combat.summary = new_summary.id
        try:
            await new_summary.pin()
            await old_summary.unpin()
        except discord.HTTPException:
            pass

        await combat.final()

    @init.command(name="meta", aliases=['metaset'])
    async def metasetting(self, ctx, *settings):
        """
        Changes the settings of the active combat.
        __Valid Settings__
        `dyn` - Dynamic initiative; Rerolls all initiatves at the start of a round.
        `turnnotif` - Notifies the controller of the next combatant in initiative.
        `deathdelete` - Toggles removing monsters below 0 HP.
        `-name <name>` - Sets a name for the combat instance
        """
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
        if args.last('deathdelete', default=False, type_=bool):
            options['deathdelete'] = not options.get('deathdelete', False)
            out += f"Monsters at 0 HP will be {'left' if options['deathdelete'] else 'removed'}.\n"

        combat.options = options
        await combat.commit()
        out = out if out else 'No Settings Changed'
        await ctx.send(out)

    @init.command(name="list", aliases=['summary'])
    async def init_list(self, ctx, *args):
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
        """
        Edits the options of a combatant.
        __Valid Arguments__
        `-h` - Hides HP, AC, Resists, etc.
        `-p <value>` - Changes the combatants' placement in the Initiative. Adds if starts with +/- or sets otherwise.
        `-name <name>` - Changes the combatants' name.
        `-controller <controller>` - Pings a different person on turn.
        `-ac <ac>` - Modifies combatants' AC. Adds if starts with +/- or sets otherwise.
        `-resist <damage type>` - Gives the combatant resistance to the given damage type.
        `-immune <damage type>` - Gives the combatant immunity to the given damage type.
        `-vuln <damage type>` - Gives the combatant vulnerability to the given damage type.
        `-neutral <damage type>` - Removes the combatants' immunity, resistance, or vulnerability to the given damage type.
        `-group <group>` - Adds the combatant to a group. To remove them from group, use -group None.
        `-max <maxhp>` - Modifies the combatants' Max HP. Adds if starts with +/- or sets otherwise.
        `-hp <hp>` - Modifies current HP. Adds if starts with +/- or sets otherwise.
        """  # noqa: E501
        combat = await Combat.from_ctx(ctx)

        comb = await combat.select_combatant(name, select_group=True)
        if comb is None:
            await ctx.send("Combatant not found.")
            return

        args = argparse(args)
        options = {}
        target_is_group = isinstance(comb, CombatantGroup)
        run_once = set()
        allowed_mentions = set()

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
            if member.bot:
                return "\u274c Bots cannot control combatants."
            allowed_mentions.add(member)
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
            group_name = args.last('group')
            new_group = combatant.set_group(group_name=group_name)
            if new_group is None:
                return f"\u2705 {combatant.name} removed from all groups."
            return f"\u2705 {combatant.name} added to group {new_group.name}."

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
                            destination = (await get_guild_member(ctx.guild, int(comb.controller))) or ctx.channel
                        else:
                            destination = ctx.channel
                        out[destination].append(response)

        if out:
            for destination, messages in out.items():
                await destination.send(
                    '\n'.join(messages),
                    allowed_mentions=discord.AllowedMentions(users=list(allowed_mentions))
                )
            await combat.final()
        else:
            await ctx.send("No valid options found.")

    @init.command()
    async def status(self, ctx, name: str = '', *, args: str = ''):
        """Gets the status of a combatant or group.
        If no name is specified, it will default to current combatant.
        __Valid Arguments__
        `private` - PMs the controller of the combatant a more detailed status."""

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
            status = "\n".join(
                [co.get_status(private=private and str(ctx.author.id) == co.controller) for co in
                 combatant.get_combatants()]
            )

        if private:
            await combatant.message_controller(ctx, f"```markdown\n{status}```")
        else:
            await ctx.send("```markdown\n" + status + "```")

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
                await combatant.message_controller(ctx, f"{combatant.name}'s HP: {combatant.hp_str(True)}")
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

        await gameutils.send_hp_result(ctx, combatant, delta)

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
        await gameutils.send_hp_result(ctx, combatant, delta)

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
        await gameutils.send_hp_result(ctx, combatant, f"{combatant.hp - before:+}")

    @init.command()
    async def thp(self, ctx, name: str, *, thp: str):
        """
        Modifies the temporary HP of a combatant.
        Usage: `!init thp <NAME> <HP>`
        Sets the combatants' THP if hp is positive, modifies it otherwise (i.e. `!i thp Avrae 5` would set Avrae's THP to 5 but `!i thp Avrae -2` would remove 2 THP).
        """  # noqa: E501
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

        await combat.final()
        await gameutils.send_hp_result(ctx, combatant, delta)

    @init.command()
    async def effect(self, ctx, target_name: str, effect_name: str, *args):
        """
        Attaches a status effect to a combatant.
        [args] is a set of args that affects a combatant in combat.
        See `!help init re` to remove effects.
        __**Valid Arguments**__
        `-dur <duration>` - Sets the duration of the effect, in rounds.
        `conc` - Makes the effect require concentration. Will end any other concentration effects.
        `end` - Makes the effect duration tick on the end of turn, rather than the beginning.
        `-t <target>` - Specifies more combatants to target, chainable (e.g., "-t or1 -t or2").
        `-parent <"[combatant]|[effect]">` - Sets a parent effect from a specified combatant.
        __Attacks__
        `adv`/`dis` - Give advantage or disadvantage to all attack rolls.
        `-b <bonus>` - Adds a bonus to hit.
        `-d <damage>` - Adds additional damage.
        `-attack <"[hit]|[damage]|[description]">` - Adds an attack to the combatant. The effect name will be the name of the attack. No [hit] will autohit (e.g., `-attack "|1d6[fire]|You just got burned!"`)
        __Resists__
        `-resist <damage type>` - Gives the combatant resistance to the given damage type.
        `-immune <damage type>` - Gives the combatant immunity to the given damage type.
        `-vuln <damage type>` - Gives the combatant vulnerability to the given damage type.
        `-neutral <damage type>` - Removes the combatant's immunity, resistance, or vulnerability to the given damage type.
        `magical` - Makes all damage from the combatant magical.
        `silvered` - Makes all damage from the combatant silvered.
        __General__
        `-ac <ac>` - modifies ac temporarily; adds if starts with +/- or sets otherwise.
        `-sb <save bonus>` - Adds a bonus to all saving throws.
        `-cb <check bonus>` - Adds a bonus to all ability checks.
        `-sadv/sdis <ability>` - Gives advantage/disadvantage on saving throws for the provided ability, or "all" for all saves.
        `-maxhp <hp>` - modifies maximum hp temporarily; adds if starts with +/- or sets otherwise.
        `-desc <description>` - Adds a description of the effect.
        """  # noqa: E501
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
        desc = args.last('desc')

        if parent is not None:
            parent = parent.split('|', 1)
            if not len(parent) == 2:
                raise InvalidArgument("`parent` arg must be formatted `COMBATANT|EFFECT_NAME`")
            p_combatant = await combat.select_combatant(
                parent[0],
                choice_message="Select the combatant with the parented effect."
            )
            parent = await p_combatant.select_effect(parent[1])

        embed = EmbedWithAuthor(ctx)
        for combatant in targets:
            if effect_name.lower() in (e.name.lower() for e in combatant.get_effects()):
                out = "Effect already exists."
            else:
                effect_obj = Effect.new(
                    combat, combatant, duration=duration, name=effect_name, effect_args=args,
                    concentration=conc, tick_on_end=end, desc=desc
                )
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

    @init.group(
        aliases=['a', 'action'], invoke_without_command=True, help=f"""
    Rolls an attack against another combatant.
    __**Valid Arguments**__
    {VALID_AUTOMATION_ARGS}
    -custom - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add to hit and damage.
    """
    )
    async def attack(self, ctx, atk_name=None, *, args=''):
        combat = await ctx.get_combat()
        combatant = combat.current_combatant
        if combatant is None:
            return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")

        if atk_name is None:
            return await self.attack_list(ctx, combatant)
        return await self._attack(ctx, combatant, atk_name, args)

    @attack.command(name="list")
    async def attack_list(self, ctx, *args):
        """Lists the active combatant's attacks."""
        combat = await ctx.get_combat()
        combatant = combat.current_combatant
        if combatant is None:
            return await ctx.send(f"You must start combat with `{ctx.prefix}init next` first.")
        return await self._attack_list(ctx, combatant, *args)

    @init.command(
        help=f"""
    Rolls an attack against another combatant.
    __**Valid Arguments**__
    {VALID_AUTOMATION_ARGS}
    -custom - Makes a custom attack with 0 to hit and base damage. Use `-b` and `-d` to add to hit and damage.
    """
    )
    async def aoo(self, ctx, combatant_name, atk_name=None, *, args=''):
        combat = await ctx.get_combat()
        try:
            combatant = await combat.select_combatant(combatant_name, "Select the attacker.")
        except SelectionException:
            return await ctx.send("Combatant not found.")

        if atk_name is None or atk_name == 'list':
            return await self._attack_list(ctx, combatant)
        return await self._attack(ctx, combatant, atk_name, args)

    @staticmethod
    async def _attack_list(ctx, combatant, *args):
        combat = await ctx.get_combat()

        if combatant.is_private and combatant.controller != str(ctx.author.id) and str(ctx.author.id) != combat.dm:
            return await ctx.send("You do not have permission to view this combatant's attacks.")

        if not combatant.is_private:
            destination = ctx
        else:
            destination = ctx.message.author

        if isinstance(combatant, PlayerCombatant):
            await actionutils.send_action_list(
                ctx, destination=destination, caster=combatant, attacks=combatant.attacks,
                actions=combatant.character.actions, args=args
            )
        else:
            await actionutils.send_action_list(
                ctx, destination=destination, caster=combatant, attacks=combatant.attacks, args=args
            )

    async def _attack(self, ctx, combatant, atk_name, unparsed_args):
        combat = await ctx.get_combat()

        # argument parsing
        is_player = isinstance(combatant, PlayerCombatant)
        if is_player and combatant.character_owner == str(ctx.author.id):
            args = await helpers.parse_snippets(unparsed_args, ctx, character=combatant.character)
        else:
            args = await helpers.parse_snippets(unparsed_args, ctx, statblock=combatant)
        args = argparse(args)

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

                    _, caster, attack = await search_and_select(
                        ctx, choices, atk_name, lambda choice: choice[0],
                        message="Select your attack."
                    )
            else:
                caster = combatant
                if 'custom' in args:  # single, custom
                    attack = Attack.new(name=atk_name, bonus_calc='0', damage_calc='0')
                elif is_player:  # single, noncustom, action?
                    attack = await actionutils.select_action(
                        ctx, atk_name, attacks=combatant.attacks, actions=combatant.character.actions,
                        message="Select your action."
                    )
                else:  # single, noncustom
                    attack = await actionutils.select_action(
                        ctx, atk_name, attacks=combatant.attacks, message="Select your attack."
                    )
        except SelectionException:
            return await ctx.send("Attack not found.")

        # target handling
        targets = await targetutils.definitely_combat(combat, args, allow_groups=True)

        # embed setup
        embed = discord.Embed(color=combatant.get_color())

        # run
        if isinstance(attack, Attack):
            result = await actionutils.run_attack(ctx, embed, args, caster, attack, targets, combat)
        else:
            result = await actionutils.run_action(ctx, embed, args, caster, attack, targets, combat)

        await ctx.send(embed=embed)
        if (gamelog := self.bot.get_cog('GameLog')) and is_player and result is not None:
            await gamelog.send_automation(ctx, combatant.character, attack.name, result)

    @init.command(
        aliases=['c'], help=f"""
    Rolls an ability check as the current combatant.
    {VALID_CHECK_ARGS}
    """
    )
    async def check(self, ctx, check, *, args=''):
        return await self._check(ctx, None, check, args)

    @init.command(
        aliases=['oc'], help=f"""
    Rolls an ability check as another combatant.
    {VALID_CHECK_ARGS}
    """
    )
    async def offturncheck(self, ctx, combatant_name, check, *, args=''):
        return await self._check(ctx, combatant_name, check, args)

    async def _check(self, ctx, combatant_name, check, args):
        combat = await Combat.from_ctx(ctx)
        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await ctx.send(
                    f"You must start combat with `{ctx.prefix}init next` to make a check as the current combatant."
                )
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the combatant to make the check.")
            except SelectionException:
                return await ctx.send("Combatant not found.")

        if isinstance(combatant, CombatantGroup):
            return await ctx.send("Groups cannot make checks.")

        skill_key = await search_and_select(ctx, constants.SKILL_NAMES, check, lambda s: s)
        embed = discord.Embed(color=combatant.get_color())

        args = await helpers.parse_snippets(args, ctx)
        args = argparse(args)

        result = checkutils.run_check(skill_key, combatant, args, embed)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if (gamelog := self.bot.get_cog('GameLog')) and isinstance(combatant, PlayerCombatant):
            await gamelog.send_check(ctx, combatant.character, result.skill_name, result.rolls)

    @init.command(
        aliases=['s'], help=f"""
    Rolls an ability save as the current combatant.
    {VALID_SAVE_ARGS}
    """
    )
    async def save(self, ctx, save, *, args=''):
        return await self._save(ctx, None, save, args)

    @init.command(
        aliases=['os'], help=f"""
    Rolls an ability save as another combatant.
    {VALID_CHECK_ARGS}
    """
    )
    async def offturnsave(self, ctx, combatant_name, save, *, args=''):
        return await self._save(ctx, combatant_name, save, args)

    async def _save(self, ctx, combatant_name, save, args):
        combat = await Combat.from_ctx(ctx)
        if combatant_name is None:
            combatant = combat.current_combatant
            if combatant is None:
                return await ctx.send(
                    f"You must start combat with `{ctx.prefix}init next` to make a save as the current combatant."
                )
        else:
            try:
                combatant = await combat.select_combatant(combatant_name, "Select the combatant to make the save.")
            except SelectionException:
                return await ctx.send("Combatant not found.")

        if isinstance(combatant, CombatantGroup):
            return await ctx.send("Groups cannot make saves.")

        embed = discord.Embed(color=combatant.get_color())
        args = await helpers.parse_snippets(args, ctx)
        args = argparse(args)

        result = checkutils.run_save(save, combatant, args, embed)

        # send
        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if (gamelog := self.bot.get_cog('GameLog')) and isinstance(combatant, PlayerCombatant):
            await gamelog.send_save(ctx, combatant.character, result.skill_name, result.rolls)

    @init.command(
        help=f"""
    Casts a spell against another combatant.
    __**Valid Arguments**__
    {VALID_SPELLCASTING_ARGS}
    
    {VALID_AUTOMATION_ARGS}
    """
    )
    async def cast(self, ctx, spell_name, *, args=''):
        return await self._cast(ctx, None, spell_name, args)

    @init.command(
        aliases=['rc'], help=f"""
    Casts a spell against another combatant.
    __**Valid Arguments**__
    {VALID_SPELLCASTING_ARGS}
    
    {VALID_AUTOMATION_ARGS}
    """
    )
    async def reactcast(self, ctx, combatant_name, spell_name, *, args=''):
        return await self._cast(ctx, combatant_name, spell_name, args)

    async def _cast(self, ctx, combatant_name, spell_name, args):
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
            args = await helpers.parse_snippets(args, ctx, character=combatant.character)
        else:
            args = await helpers.parse_snippets(args, ctx, statblock=combatant)
        args = argparse(args)

        if not args.last('i', type_=bool):
            try:
                spell = await select_spell_full(
                    ctx, spell_name,
                    list_filter=lambda s: s.name in combatant.spellbook
                )
            except NoSelectionElements:
                return await ctx.send(
                    f"No matching spells found in the combatant's spellbook. Cast again "
                    f"with the `-i` argument to ignore restrictions!"
                )
        else:
            spell = await select_spell_full(ctx, spell_name)

        targets = await targetutils.definitely_combat(combat, args, allow_groups=True)

        result = await spell.cast(ctx, combatant, targets, args, combat=combat)

        embed = result.embed
        embed.colour = combatant.get_color()
        await ctx.send(embed=embed)
        await combat.final()
        if (gamelog := self.bot.get_cog('GameLog')) and is_character and result.automation_result:
            await gamelog.send_automation(ctx, combatant.character, spell.name, result.automation_result)

    @init.command(name='remove')
    async def remove_combatant(self, ctx, *, name: str):
        """Removes a combatant or group from the combat.
        Usage: `!init remove <NAME>`"""
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
                    "You cannot remove a combatant if they are the only remaining combatant in this turn."
                )
        combat.remove_combatant(combatant)
        await ctx.send("{} removed from combat.".format(combatant.name))
        await combat.final()

    @init.command()
    async def end(self, ctx, args=None):
        """Ends combat in the channel.
        __Valid Arguments__
        `-force` - Forces an init to end, in case it's erroring."""

        to_end = await confirm(ctx, 'Are you sure you want to end combat? (Reply with yes/no)', True)

        if to_end is None:
            return await ctx.send('Timed out waiting for a response or invalid response.', delete_after=10)
        elif not to_end:
            return await ctx.send('OK, cancelling.', delete_after=10)

        msg = await ctx.send("OK, ending...")
        if args != '-force':
            combat = await Combat.from_ctx(ctx)

            try:
                await ctx.author.send(
                    f"End of combat report: {combat.round_num} rounds "
                    f"{combat.get_summary(True)}"
                )

                summary = combat.get_summary_msg()
                await summary.edit(content=combat.get_summary() + " ```-----COMBAT ENDED-----```")
                await summary.unpin()
            except discord.HTTPException:
                pass

            await combat.end()
        else:
            await self.bot.mdb.combats.delete_one({"channel": str(ctx.channel.id)})

        await msg.edit(content="Combat ended.")


def setup(bot):
    bot.add_cog(InitTracker(bot))
