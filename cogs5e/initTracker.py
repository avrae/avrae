import random
import shlex

import cachetools
from discord.ext import commands

from cogs5e.models.errors import CombatChannelNotFound
from cogs5e.models.initiative import Combat, Combatant
from utils.functions import parse_args_3


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
        self.message_cache = cachetools.LRUCache(100)

    def get_combat_channel(self, combat):
        if combat.ctx:
            return combat.ctx.message.channel
        else:
            chan = self.bot.get_channel(combat.channel)
            if chan:
                return chan
            else:
                raise CombatChannelNotFound

    async def get_summary_msg(self, combat):
        if combat.summary in self.message_cache:
            return self.message_cache[combat.summary]
        else:
            msg = await self.bot.get_message(self.get_combat_channel(combat), combat.summary)
            self.message_cache[msg.id] = msg
            return msg

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
        self.message_cache[temp_summary_msg.id] = temp_summary_msg  # add to cache

        combat = Combat.new(ctx.message.channel.id, temp_summary_msg.id, ctx.message.author.id, options, ctx)
        await combat.final(await self.get_summary_msg(combat))

        try:
            await self.bot.pin_message(temp_summary_msg)
        except:
            pass
        await self.bot.say(
            "Everyone roll for initiative!\nIf you have a character set up with SheetManager: `!init cadd`\n"
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

            me = Combatant.new(name, controller, init, modifier, hp, hp, ac, private, resists, [], ctx)

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

        await combat.final(await self.get_summary_msg(combat))
