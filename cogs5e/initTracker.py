import shlex

import cachetools
from discord.ext import commands

from cogs5e.models.initiative import Combat


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
                raise CombatChannelNotFound  # TODO

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
        Valid Arguments:    -1 (modifies initiative rolls)
                            -dyn (dynamic init; rerolls all initiatives at the start of a round)
                            --name <NAME> (names the combat)"""
        Combat.ensure_unique_chan(ctx)

        options = {}
        name = 'Current initiative'
        args = shlex.split(args.lower())
        if '-1' in args:  # rolls a d100 instead of a d20 and multiplies modifier by 5
            options['d100_init'] = True
        if '-dyn' in args:  # rerolls all inits at the start of each round
            options['dynamic'] = True
        if '--name' in args:
            try:
                a = args[args.index('--name') + 1]
                options['name'] = a if a is not None else name
            except IndexError:
                await self.bot.say("You must pass in a name with the --name tag.")
                return

        temp_summary_msg = await self.bot.say("```Awaiting combatants...```")
        self.message_cache[temp_summary_msg.id] = temp_summary_msg  # add to cache

        Combat(ctx.message.channel.id, temp_summary_msg.id, ctx.message.author.id, options, ctx).commit()

        try:
            await self.bot.pin_message(temp_summary_msg)
        except:
            pass
        await self.bot.say(
            "Everyone roll for initiative!\nIf you have a character set up with SheetManager: `!init cadd`\n"
            "If it's a 5e monster: `!init madd [monster name]`\nOtherwise: `!init add [modifier] [name]`")
