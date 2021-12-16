import re
import time

import d20
import disnake

import utils.settings
from cogs5e.models import embeds
from utils.aldclient import discord_user_to_dict
from utils.dice import PersistentRollContext

INLINE_ROLLING_EMOJI = '\U0001f3b2'  # :game_die:
INLINE_ROLLING_RE = re.compile(r'\[\[(.+?]?)]]')


class InlineRoller:
    def __init__(self, bot):
        self.bot = bot

    async def handle_message_inline_rolls(self, message):
        # find roll expressions
        if not INLINE_ROLLING_RE.search(message.content):
            return

        # inline rolling feature flag
        if not await self.bot.ldclient.variation(
                "cog.dice.inline_rolling.enabled",
                user=discord_user_to_dict(message.author),
                default=False
        ):
            return

        if message.guild is not None:  # (always enabled in pms)
            guild_settings = await utils.settings.ServerSettings.for_guild(self.bot.mdb, message.guild.id)

            # if inline rolling is disabled on this server, skip
            if guild_settings.inline_enabled is utils.settings.guild.InlineRollingType.DISABLED:
                return

            # if inline rolling is set to react only, pop a reaction on it and return (we re-enter from on_reaction)
            if guild_settings.inline_enabled is utils.settings.guild.InlineRollingType.REACTION:
                try:
                    await message.add_reaction(INLINE_ROLLING_EMOJI)
                except disnake.HTTPException:
                    return  # if we can't react, just skip
                await self.inline_rolling_reaction_onboarding(message.author)
                return

        # if this is the user's first interaction with inline rolling, send an onboarding message
        await self.inline_rolling_message_onboarding(message.author)

        # otherwise do the rolls
        await self.do_inline_rolls(message)

    async def handle_reaction_inline_rolls(self, reaction, user):
        if user.id != reaction.message.author.id:
            return
        if reaction.emoji != INLINE_ROLLING_EMOJI:
            return
        message = reaction.message

        # find roll expressions
        if not INLINE_ROLLING_RE.search(message.content):
            return

        # if the reaction is in PMs (inline rolling always enabled), skip
        if message.guild is None:
            return

        # inline rolling feature flag
        if not await self.bot.ldclient.variation(
                "cog.dice.inline_rolling.enabled",
                user=discord_user_to_dict(message.author),
                default=False
        ):
            return

        # if inline rolling is not set to reactions, skip
        guild_settings = await utils.settings.ServerSettings.for_guild(self.bot.mdb, message.guild.id)
        if guild_settings.inline_enabled is not utils.settings.guild.InlineRollingType.REACTION:
            return

        # if this message has already been processed, skip
        if await self.bot.rdb.get(f"cog.dice.inline_rolling.messages.{message.id}.processed"):
            return

        # otherwise save that this message has been processed, remove reactions, and do the rolls
        await self.bot.rdb.setex(
            f"cog.dice.inline_rolling.messages.{message.id}.processed",
            str(time.time()),
            60 * 60 * 24
        )
        await self.do_inline_rolls(message)
        try:
            await reaction.clear()
        except disnake.HTTPException:
            pass

    @staticmethod
    async def do_inline_rolls(message):
        roll_exprs = _find_inline_exprs(message.content)

        out = []
        roller = d20.Roller(context=PersistentRollContext())
        for expr, context_before, context_after in roll_exprs:
            context_before = context_before.replace('\n', ' ')
            context_after = context_after.replace('\n', ' ')

            try:
                result = roller.roll(expr, allow_comments=True)
                if not result.comment:
                    out.append(f"{context_before}({result.result}){context_after}")
                else:
                    out.append(f"**{result.comment}**: {result.result}")
            except d20.RollSyntaxError:
                continue
            except d20.RollError as e:
                out.append(f"{context_before}({e!s}){context_after}")

        if not out:
            return

        await message.reply('\n'.join(out))

    async def inline_rolling_message_onboarding(self, user):
        if await self.bot.rdb.get(f"cog.dice.inline_rolling.users.{user.id}.onboarded.message"):
            return

        embed = embeds.EmbedWithColor()
        embed.title = "Inline Rolling"
        embed.description = f"Hi {user.mention}, it looks like this is your first time using inline rolling with me!"
        embed.add_field(
            name="What is Inline Rolling?",
            value="Whenever you send a message with some dice in between double brackets (e.g. `[[1d20]]`), I'll reply "
                  "to it with a roll for each one. You can send messages with multiple, too, like this: ```\n"
                  "I attack the goblin with my shortsword [[1d20 + 6]] for a total of [[1d6 + 3]] piercing damage.\n"
                  "```"
        )
        embed.set_footer(text="You won't see this message again.")

        try:
            await user.send(embed=embed)
        except disnake.HTTPException:
            return
        await self.bot.rdb.set(f"cog.dice.inline_rolling.users.{user.id}.onboarded.message", str(time.time()))

    async def inline_rolling_reaction_onboarding(self, user):
        if await self.bot.rdb.get(f"cog.dice.inline_rolling.users.{user.id}.onboarded.reaction"):
            return

        embed = embeds.EmbedWithColor()
        embed.title = "Inline Rolling - Reactions"
        embed.description = f"Hi {user.mention}, it looks like this is your first time using inline rolling with me!"
        embed.add_field(
            name="What is Inline Rolling?",
            value="Whenever you send a message with some dice in between double brackets (e.g. `[[1d20]]`), I'll react "
                  f"with the {INLINE_ROLLING_EMOJI} emoji. You can click it to have me roll all of the dice in your "
                  "message, and I'll reply with my own message!"
        )
        embed.set_footer(text="You won't see this message again.")

        try:
            await user.send(embed=embed)
        except disnake.HTTPException:
            return
        await self.bot.rdb.set(f"cog.dice.inline_rolling.users.{user.id}.onboarded.reaction", str(time.time()))


def _find_inline_exprs(content, context_before=5, context_after=2, max_context_len=128):
    """Returns an iterator of tuples (expr, context_before, context_after)."""

    # create list alternating (before, expr; text, expr; ...; text, expr; after)
    segments = INLINE_ROLLING_RE.split(content)

    # want (before, expr, after; ...; before, expr, after)
    # so split up each pair of (text, expr) by trimming the text into (last_after, before, expr)
    # with priority on before
    trimmed_segments = []
    for text, expr in zip(a := iter(segments), a):  # fun way to take pairs from a list!
        text_len = len(text)

        # before is always text[before_idx:len(text)]
        before_idx = 0
        before_bits = text.rsplit(maxsplit=context_before)
        if len(before_bits) > context_before:
            before_idx += len(before_bits[0])
        before_idx = max(before_idx, text_len - max_context_len)
        before = text[before_idx:text_len]

        # last_after is always text[0:last_after_end_idx]
        last_after_end_idx = text_len
        after_bits = text.split(maxsplit=context_after)
        if len(after_bits) > context_after:
            last_after_end_idx -= len(after_bits[-1])
        last_after_end_idx = min(last_after_end_idx, before_idx, max_context_len)
        last_after = text[0:last_after_end_idx]

        trimmed_segments.extend((last_after, before, expr))

    if not trimmed_segments:
        return

    # now we have (junk, before, expr; after, before, expr; ...; after, before, expr)
    # discard the first junk
    discarded_before = trimmed_segments.pop(0)
    # and clean up the last after
    discarded_after = False
    last_after = segments[-1]
    last_after_end_idx = len(last_after)
    after_bits = last_after.split(maxsplit=context_after)
    if len(after_bits) > context_after:
        last_after_end_idx -= len(after_bits[-1])
        discarded_after = True
    if last_after_end_idx > max_context_len:
        last_after_end_idx = max_context_len
        discarded_after = True
    trimmed_segments.append(last_after[0:last_after_end_idx])
    # we also use whether or not the chopped-off bits at the very start and end exist for ellipses

    # now we have (before, expr, after; ...)
    # do ellipses and yield triples (expr, context_before, context_after)
    num_triples = len(trimmed_segments) // 3
    for idx, (before, expr, after) in enumerate(zip(a := iter(trimmed_segments), a, a)):
        context_before = before.lstrip()
        context_after = after.rstrip()

        if idx or discarded_before:  # not the first or something was discarded before first
            context_before = f"...{context_before}"

        if idx + 1 < num_triples or discarded_after:  # not the last or something was discarded after last
            context_after = f"{context_after}..."

        yield expr.strip(), context_before, context_after
