import logging
import collections
import functools
import disnake

from disnake.ext import commands
from disnake.ext.commands import NoPrivateMessage
from contextlib import suppress
from discord.ext import commands
from aliasing import helpers

from cogs5e.models.character import Character
from cogs5e.models.errors import InvalidArgument, NoSelectionElements, SelectionException
from cogs5e.models.embeds import EmbedWithAuthor, EmbedWithCharacter, EmbedWithColor
from cogs5e.utils import actionutils, targetutils
from cogs5e.utils.help_constants import *
from gamedata.lookuputils import select_spell_full
from utils.argparser import argparse
from utils.functions import confirm, get_guild_member, try_delete, get_selection

from cogs5e.exploration.explore import Explore
from cogs5e.exploration.explorer import Explorer, PlayerExplorer
from cogs5e.exploration.effect import Effect

from .group import ExplorerGroup
from ..initiative import CombatNotFound
from ..models.sheet.resistance import Resistances

log = logging.getLogger(__name__)


class ExplorationTracker(commands.Cog):
    """
    Exploration tracking commands. Use !help explore for more details.
    To use, first start exploration in a channel by saying "!explore begin".
    Then, each explorer should add themselves to the combat with "!explore add <NAME>".
    Then, you can advance exploration with "!explore adv".
    Once exploration ends, end exploration with "!explore end".
    For more help, the !help command shows applicable arguments for each command.
    """

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise NoPrivateMessage()
        return True

    async def cog_before_invoke(self, ctx):
        await try_delete(ctx.message)

    # ==== commands ====
    @commands.group(aliases=["e"], invoke_without_command=True)
    async def explore(self, ctx):
        """Commands to help exploration."""
        await ctx.send(f"Incorrect usage. Use {ctx.prefix}help explore for help.")

    @explore.command()
    async def begin(self, ctx, *args):
        """Begins exploration in the channel the command is invoked.
        Usage: !explore begin <ARGS (opt)>
        __Valid Argument__
        -name <name> - Sets a name for the exploration instance."""
        await Explore.ensure_unique_chan(ctx)

        options = {}
        args = argparse(args)
        if "name" in args:
            options["name"] = args.last("name")

        temp_summary_msg = await ctx.send("```Awaiting explorers...```")

        exploration = Explore.new(str(ctx.channel.id), temp_summary_msg.id, str(ctx.author.id), options, ctx)

        with suppress(disnake.HTTPException):
            await temp_summary_msg.pin()
        out = (
            f"If you have a character set up with SheetManager: `{ctx.prefix}explore join`\n"
            f"Otherwise: `{ctx.prefix}explore add <name>`"
        )

        await exploration.final()
        await ctx.send(out)

    @explore.command()
    async def add(self, ctx, name: str, *args):
        """Adds a generic explorer to the exploration.
        If a character is set up with the SheetManager module, you can use !explore join instead.

        __Valid Arguments__
        `-u` - Unhides HP, AC, resistances
        `-controller <controller>` - Pings a different person on turn.
        `-group <group>` - Adds the explorer to a group.
        `-note <note>` - Sets the explorer's note.
        """

        private = True
        controller = str(ctx.author.id)
        group = None
        hp = None
        ac = None
        resists = {}
        args = argparse(args)

        if args.last("u", type_=bool):
            private = False

        if args.last("controller"):
            controller_name = args.last("controller")
            member = await commands.MemberConverter().convert(ctx, controller_name)
            controller = str(member.id) if member is not None and not member.bot else controller
        if args.last("group"):
            group = args.last("group")
        if args.last("hp"):
            hp = args.last("hp", type_=int)
            if hp < 1:
                return await ctx.send("You must pass in a positive, nonzero HP with the -hp tag.")
        if args.last("ac"):
            ac = args.last("ac", type_=int)

        note = args.last("note")

        exploration = await ctx.get_exploration()

        if exploration.get_explorer(name, True) is not None:
            await ctx.send("Explorer already exists.")
            return

        me = Explorer.new(
            name, controller, hp, ac, private, Resistances.from_dict(resists), ctx, exploration
        )

        # -note (#1211)
        if note:
            me.notes = note

        if group is None:
            exploration.add_explorer(me)
            await ctx.send(f"{name} was added to exploration.")
        else:
            grp = exploration.get_group(group)
            grp.add_explorer(me)
            await ctx.send(f"{name} was added to exploration as part of group {grp.name}.")

        await exploration.final()

    @explore.command()
    async def enctimer(self, ctx, time: int, *args):
        """Changes the interval between rolling random encounters
        Usage: !explore enctimer <number> [-h]
        __Valid Arguments__
        -h ensures the interval entered is expressed in hours (600s of rounds), default is minutes"""
        hour = "-h" in args
        if hour:
            time = time * 10 * 60
        else:
            time = time * 10
        exploration = await ctx.get_exploration()
        exploration.set_enc_timer(time)
        await exploration.final()

    @explore.command()
    async def getchance(self, ctx):
        exp = await ctx.get_exploration
        ctx.send(exp.chance)

    @explore.command(name="chance")
    async def setchance(self, ctx, percent: int):
        """Sets the percentile chance of actually rolling on the encounter table. If not set, the chance is 100%
        Usage: !explore chance 1..100
        the chance must be a whole number"""
        exploration = await ctx.get_exploration()
        exploration.set_chance(percent)
        await exploration.final()

    @explore.command(name="join", aliases=["cadd", "dcadd"])
    async def join(self, ctx, *, args: str = ""):
        """
        Adds the current active character to exploration. A character must be loaded through the SheetManager module first.
        __Valid Arguments__
        `-phrase <phrase>` - Adds flavor text.
        `-thumb <thumbnail URL>` - Adds flavor image.
        `-group <group>` - Adds the explorer to a group.
        `-note <note>` - Sets the explorer's note.
        [user snippet]
        """
        char: Character = await ctx.get_character()
        args = await helpers.parse_snippets(args, ctx, character=char)
        args = argparse(args)

        embed = EmbedWithCharacter(char, False)

        group = args.last("group")
        note = args.last("note")
        check_result = None

        args.ignore("rr")
        args.ignore("dc")

        controller = str(ctx.author.id)

        exploration = await ctx.get_exploration()

        if exploration.get_explorer(char.name, True) is not None:
            await ctx.send("Explorer already exists.")
            return

        me = await PlayerExplorer.from_character(char, ctx, exploration, controller)

        # -note (#1211)
        if note:
            me.notes = note

        if group is None:
            exploration.add_explorer(me)
            embed.set_footer(text="Added to exploration!")
        else:
            grp = exploration.get_group(group)
            grp.add_explorer(me)
            embed.set_footer(text=f"Joined group {grp.name}!")

        await exploration.final()
        await ctx.send(embed=embed)

    @explore.command(name="advance", aliases=["adv", "a"])
    async def advance(self, ctx, numrounds: int = 1, time: str = "R"):
        """
        Advances exploration one or more rounds.
        Usage: !explore advance <number> <R/M/H>
        R ensures exploration will be advanced by rounds
        M ensures exploration will be advanced by minutes (tens of rounds)
        H ensures exploration will be advanced by hours (600s of rounds)
        By default it advances rounds.
        If no number is entered, exploration will advance 1 round
        """
        exploration = await ctx.get_exploration()
        try:
            combat = await ctx.get_combat()
        except CombatNotFound:
            combat = None

        if exploration.dm != str(ctx.author.id):
            await ctx.send("Only the game master can advance the clock!")
        else:
            if combat is not None:
                await ctx.send("Can't advance exploration during combat! Finish the combat first.")
            else:
                if time.upper() in ['R', 'RD', 'RDS', 'ROUNDS']:
                    numrounds = numrounds
                elif time.upper() in ['M', 'MI', 'MIN', 'MINS', 'MINUTES']:
                    numrounds *= 10
                elif time.upper() in ['H', 'HR', 'HOURS']:
                    numrounds = numrounds * 10 * 60

                messages = await exploration.skip_rounds(ctx, numrounds)
                if len(messages[1]) > 0:
                    embed = EmbedWithColor()
                    embed.description = "\n".join(messages[1])
                    await ctx.author.send(embed=embed)
                out = [exploration.get_summary()]
                await ctx.send("\n".join(out))
                if messages[0] is not None:
                    embed = EmbedWithColor()
                    embed.description = messages[0]
                    await ctx.send(embed=embed)

                await exploration.final()

    @explore.command()
    async def rest(self, ctx, length: str):
        exploration = await ctx.get_exploration()
        try:
            combat = await ctx.get_combat()
        except CombatNotFound:
            combat = None
        if exploration.dm != str(ctx.author.id):
            await ctx.send("Only the game master can declare rests!")
        else:
            if combat is not None:
                await ctx.send("Can't rest during combat! Finish the combat first.")
            else:
                if length == "short":
                    exploration.skip_rounds(600)
                elif length == "long":
                    exploration.skip_rounds(4800)
                else:
                    await ctx.send("Invalid rest length. It has to be either short or long")

    @explore.command(name="list", aliases=["summary"])
    async def list(self, ctx, *args):
        """Lists the explorers.
        __Valid Arguments__
        -p - Sends the list in a private message."""
        exploration = await ctx.get_exploration()
        private = "-p" in args
        destination = ctx if not private else ctx.author
        if private and str(ctx.author.id) == exploration.dm:
            out = exploration.get_summary(True)
        else:
            out = exploration.get_summary()
        await destination.send(out)

    @explore.command()
    async def note(self, ctx, name: str, *, note: str = ""):
        """Attaches a note to an explorer."""
        exploration = await ctx.get_exploration()

        explorer = await exploration.select_explorer(name)
        if explorer is None:
            return await ctx.send("Explorer not found.")

        explorer.notes = note
        if note == "":
            await ctx.send("Removed note.")
        else:
            await ctx.send("Added note.")
        await exploration.final()

    @explore.command(aliases=["opts"])
    async def opt(self, ctx, name: str, *args):
        """
        Edits the options of an explorer.
        __Valid Arguments__
        `-h` - Hides HP, AC, Resists, etc.
        `-name <name>` - Changes the explorer's name.
        `-controller <controller>` - Pings a different person on turn.
        """  # noqa: E501
        exploration = await ctx.get_exploration()

        expl = await exploration.select_explorer(name, select_group=True)
        if expl is None:
            await ctx.send("Explorer not found.")
            return

        args = argparse(args)
        options = {}
        target_is_group = isinstance(expl, ExplorerGroup)
        run_once = set()
        allowed_mentions = set()

        def option(opt_name=None, pass_group=False, **kwargs):
            """
            Wrapper to register an option.
            :param: str opt_name: The string to register the function under. Defaults to function name.
            :param: bool pass_group: Whether to pass a group as the first argument to the function or an explorer.
            :param: kwargs: kwargs that will always be passed to the function.
            """

            def wrapper(func):
                target_is_group = False
                func_name = opt_name or func.__name__
                if pass_group and target_is_group:
                    old_func = func

                    async def func(_, *a, **k):
                        if func_name in run_once:
                            return
                        run_once.add(func_name)
                        return await old_func(expl, *a, **k)  # pop the explorer argument and sub in group

                func = options[func_name] = functools.partial(func, **kwargs)
                return func

            return wrapper

        def mod_or_set(opt_name, old_value):
            new_value = args.last(opt_name, type_=int)
            if args.last(opt_name).startswith(("-", "+")):
                new_value = (old_value or 0) + new_value
            return new_value, old_value

        @option()
        async def controller(explorer):
            controller_name = args.last("controller")
            member = await commands.MemberConverter().convert(ctx, controller_name)
            if member is None:
                return "\u274c New controller not found."
            if member.bot:
                return "\u274c Bots cannot control explorers."
            allowed_mentions.add(member)
            explorer.controller = str(member.id)
            return f"\u2705 {explorer.name}'s controller set to {explorer.controller_mention()}."

        @option()
        async def group(explorer):
            group_name = args.last("group")
            new_group = explorer.set_group(group_name=group_name)
            if new_group is None:
                return f"\u2705 {explorer.name} removed from all groups."
            return f"\u2705 {explorer.name} added to group {new_group.name}."

        @option(pass_group=True)
        async def name(explorer):
            old_name = explorer.name
            new_name = args.last("name")
            if exploration.get_explorer(new_name, True) is not None:
                return f"\u274c There is already another explorer with the name {new_name}."
            elif new_name:
                explorer.name = new_name
                return f"\u2705 {old_name}'s name set to {new_name}."
            else:
                return "\u274c You must pass in a name with the -name tag."

        # run options
        targets = [expl]
        out = collections.defaultdict(lambda: [])

        for arg_name, opt_func in options.items():
            if arg_name in args:
                for target in targets:
                    response = await opt_func(target)
                    if response:
                        if target.is_private:
                            destination = (await get_guild_member(ctx.guild, int(expl.controller))) or ctx.channel
                        else:
                            destination = ctx.channel
                        out[destination].append(response)

        if out:
            for destination, messages in out.items():
                await destination.send(
                    "\n".join(messages), allowed_mentions=disnake.AllowedMentions(users=list(allowed_mentions))
                )
            await exploration.final()
        else:
            await ctx.send("No valid options found.")

    @explore.command()
    async def status(self, ctx, name: str = "", *, args: str = ""):
        """Gets the status of an explorer or group.
        Name must be specified in order to work
        __Valid Arguments__
        `private` - PMs the controller of the explorer a more detailed status."""

        exploration = await ctx.get_exploration()

        if name == "private" or name == "":
            await ctx.send("Name not provided.")
            return
        else:
            explorer = await exploration.select_explorer(name, select_group=True)

        if explorer is None:
            await ctx.send("Explorer or group not found.")
            return

        private = "private" in args.lower() or name == "private"
        if not isinstance(explorer, ExplorerGroup):
            private = private and str(ctx.author.id) == explorer.controller
            status = explorer.get_status(private=private)
        else:
            status = "\n".join(
                [
                    ex.get_status(private=private and str(ctx.author.id) == ex.controller)
                    for ex in explorer.get_explorers()
                ]
            )

        if private:
            await explorer.message_controller(ctx, f"```markdown\n{status}```")
        else:
            await ctx.send("```markdown\n" + status + "```")

    @explore.command()
    async def light(self, ctx, effect_name: str, target_name: str):
        """
        Attaches torch or lantern as an effect to a target explorer
        Usage: !explore light <torch/lantern> <explorer's name>
        See `!help explore re` to remove effects.
        """  # noqa: E501
        exploration = await ctx.get_exploration()

        targets = []
        desc = ""
        duration = -1

        for i, t in enumerate([target_name]):
            target = await exploration.select_explorer(t, f"Select target #{i + 1}.", select_group=True)
            if isinstance(target, ExplorerGroup):
                targets.extend(target.get_explorers())
            else:
                targets.append(target)

        if effect_name in ["torch", "Torch"]:
            desc = "20 ft radius bright light + 20 ft radius dim light"
            duration = 600

        if effect_name in ["Lantern", "lantern"]:
            desc = "30 ft radius bright light + 30 ft radius dim light"
            duration = 600

        embed = EmbedWithAuthor(ctx)

        for explorer in targets:
            if effect_name.lower() in (e.name.lower() for e in explorer.get_effects()):
                out = "Effect already exists."
            else:
                effect_obj = Effect.new(
                    exploration,
                    explorer,
                    duration=duration,
                    name=effect_name,
                    effect_args=[],
                    concentration=False,
                    tick_on_end=False,
                    desc=desc,
                )
                result = explorer.add_effect(effect_obj)
                if effect_name in ["torch", "Torch", "Lantern", "lantern"]:
                    out = f"{explorer.name} lit a {effect_name}."
                else:
                    out = f"Added effect {effect_name} to {explorer.name}."
            embed.add_field(name=explorer.name, value=out)
        await ctx.send(embed=embed)
        await exploration.final()

    @explore.command()
    async def effect(self, ctx, target_name: str, effect_name: str, *args):
        """
        Attaches a status effect to an explorer.
        [args] is a set of args that affects an explorer during an exploration.
        See `!help explore re` to remove effects.
        __**Valid Arguments**__
        `-dur <duration>` - Sets the duration of the effect, in rounds.
        `conc` - Makes the effect require concentration. Will end any other concentration effects.
        `end` - Makes the effect duration tick on the end of turn, rather than the beginning.
        `-t <target>` - Specifies more explorers to target, chainable (e.g., "-t or1 -t or2").
        `-parent <"[explorer]|[effect]">` - Sets a parent effect from a specified explorer.
        `-desc <description>` - Adds a description of the effect.
        """  # noqa: E501
        exploration = await ctx.get_exploration()
        args = argparse(args)

        targets = []

        for i, t in enumerate([target_name] + args.get("t")):
            target = await exploration.select_explorer(t, f"Select target #{i + 1}.", select_group=True)
            if isinstance(target, ExplorerGroup):
                targets.extend(target.get_explorers())
            else:
                targets.append(target)

        duration = args.last("dur", -1, int)
        conc = args.last("conc", False, bool)
        end = args.last("end", False, bool)
        parent = args.last("parent")
        desc = args.last("desc")

        if desc is None and duration == -1 and effect_name in ["Light", "light", "torch", "Torch"]:
            desc = "20 ft radius bright light + 20 ft radius dim light"
            duration = 600

        if desc is None and duration == -1 and effect_name in ["Lantern", "lantern"]:
            desc = "30 ft radius bright light + 30 ft radius dim light"
            duration = 600

        if parent is not None:
            parent = parent.split("|", 1)
            if not len(parent) == 2:
                raise InvalidArgument("`parent` arg must be formatted `EXPLORER|EFFECT_NAME`")
            p_explorer = await exploration.select_explorer(
                parent[0], choice_message="Select the explorer with the parented effect."
            )
            parent = await p_explorer.select_effect(parent[1])

        embed = EmbedWithAuthor(ctx)

        for explorer in targets:
            if effect_name.lower() in (e.name.lower() for e in explorer.get_effects()):
                out = "Effect already exists."
            else:
                effect_obj = Effect.new(
                    exploration,
                    explorer,
                    duration=duration,
                    name=effect_name,
                    effect_args=args,
                    concentration=conc,
                    tick_on_end=end,
                    desc=desc,
                )
                result = explorer.add_effect(effect_obj)
                if parent:
                    effect_obj.set_parent(parent)
                if effect_name in ["torch", "Torch", "Lantern", "lantern"]:
                    out = f"{explorer.name} lit a {effect_name}."
                else:
                    out = f"Added effect {effect_name} to {explorer.name}."
                if result["conc_conflict"]:
                    conflicts = [e.name for e in result["conc_conflict"]]
                    out += f"\nRemoved {', '.join(conflicts)} due to concentration conflict!"
            embed.add_field(name=explorer.name, value=out)
        await ctx.send(embed=embed)
        await exploration.final()

    @explore.command(name="re")
    async def remove_effect(self, ctx, name: str, effect: str = None):
        """Removes a status effect from an explorer or group. Removes all if effect is not passed."""
        exploration = await ctx.get_exploration()

        targets = []

        target = await exploration.select_explorer(name, select_group=True)
        if isinstance(target, ExplorerGroup):
            targets.extend(target.get_explorers())
        else:
            targets.append(target)

        out = ""

        for explorer in targets:
            if effect is None:
                explorer.remove_all_effects()
                out += f"All effects removed from {explorer.name}.\n"
            else:
                to_remove = await explorer.select_effect(effect)
                children_removed = ""
                if to_remove.children:
                    children_removed = f"Also removed {len(to_remove.children)} child effects.\n"
                to_remove.remove()
                out += f"Effect {to_remove.name} removed from {explorer.name}.\n{children_removed}"
        await ctx.send(out)
        await exploration.final()

    @explore.command(
        aliases=["c"],
        help=f"""
        Casts a spell.
        __**Valid Arguments**__
        {VALID_SPELLCASTING_ARGS}
        
        {VALID_AUTOMATION_ARGS}
        """,
    )
    async def cast(self, ctx, explorer_name, spell_name, *args):
        exploration = await ctx.get_exploration()

        if explorer_name is None:
            return await ctx.send("Explorer must be specified")
        else:
            try:
                explorer = await exploration.select_explorer(explorer_name, "Select the caster.")
            except SelectionException:
                return await ctx.send("Explorer not found.")

        if isinstance(explorer, ExplorerGroup):
            explorer = await get_selection(
                ctx, explorer.get_explorers(), key=lambda com: com.name, message="Select the caster."
            )

        is_character = isinstance(explorer, PlayerExplorer)
        if is_character and explorer.character_owner == str(ctx.author.id):
            args = await helpers.parse_snippets(args, ctx, character=explorer.character)
        else:
            args = await helpers.parse_snippets(args, ctx, statblock=explorer)
        args = argparse(args)

        if not args.last("i", type_=bool):
            try:
                spell = await select_spell_full(ctx, spell_name, list_filter=lambda s: s.name in explorer.spellbook)
            except NoSelectionElements:
                return await ctx.send(
                    f"No matching spells found in {explorer.name}'s spellbook. Cast again "
                    "with the `-i` argument to ignore restrictions!"
                )
        else:
            spell = await select_spell_full(ctx, spell_name)

        targets = await targetutils.definitely_combat(exploration, args, allow_groups=True)
        result = await actionutils.cast_spell(spell, ctx, explorer, targets, args, combat=None)

        embed = result.embed
        embed.colour = explorer.get_color()
        await ctx.send(embed=embed)
        if (gamelog := self.bot.get_cog("GameLog")) and is_character and result.automation_result:
            await gamelog.send_automation(ctx, explorer.character, spell.name, result.automation_result)

    @explore.command(name="remove")
    async def remove_explorer(self, ctx, *, name: str):
        """Removes an explorer or group from the exploration.
        Usage: `!explore remove <NAME>`"""
        exploration = await ctx.get_exploration()

        explorer = await exploration.select_explorer(name, select_group=True)
        if explorer is None:
            return await ctx.send("Explorer not found.")

        exploration.remove_explorer(explorer)
        await ctx.send("{} removed from exploration.".format(explorer.name))
        await exploration.final()

    @explore.command()
    async def end(self, ctx, args=None):
        """Ends exploration in the channel."""

        to_end = await confirm(ctx, "Are you sure you want to end exploration? (Reply with yes/no)", True)

        if to_end is None:
            return await ctx.send("Timed out waiting for a response or invalid response.", delete_after=10)
        elif not to_end:
            return await ctx.send("OK, cancelling.", delete_after=10)

        msg = await ctx.send("OK, ending...")
        exploration = await ctx.get_exploration()

        with suppress(disnake.HTTPException):
            await ctx.author.send(f"End of exploration report: {exploration.round_num} rounds " f"{exploration.get_summary(True)}")
            summary = exploration.get_summary_msg()
            await summary.edit(content=exploration.get_summary() + " ```-----EXPLORATION ENDED-----```")
            await summary.unpin()

        await exploration.end()
        await msg.edit(content="Exploration ended.")
