from discord.ext import commands

from cogs5e.models.bestiary import Bestiary
from cogs5e.models.embeds import HomebrewEmbedWithAuthor
from utils.functions import get_selection


class Homebrew:
    """Commands to manage homebrew in Avrae."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True)
    async def bestiary(self, ctx, *, name=None):
        """Commands to manage homebrew monsters.
        When called without an argument, lists the current bestiary and the monsters in it.
        When called with a name, switches to a different bestiary."""
        user_bestiaries = self.bot.db.jget(ctx.message.author.id + '.bestaries', None)

        if user_bestiaries is None:
            return await self.bot.say("You have no bestiaries. Use `!bestiary import` to import one!")

        if name is None:
            bestiary = Bestiary.from_ctx(ctx)
            embed = HomebrewEmbedWithAuthor(ctx)
            embed.title = f"Active Bestiary: {bestiary.name}"
            embed.description = '\n'.join(m.name for m in bestiary.monsters)

        choices = []
        for url, bestiary in user_bestiaries.items():
            if bestiary['name'].lower() == name.lower():
                choices.append((bestiary, url))
            elif name.lower() in bestiary['name'].lower():
                choices.append((bestiary, url))

        if len(choices) > 1:
            choiceList = [(f"{c[0]['name']} (`{c[1]})`", c) for c in choices]

            result = await get_selection(ctx, choiceList, delete=True)
            if result is None:
                return await self.bot.say('Selection timed out or was cancelled.')

            bestiary = result[0]
            bestiary_url = result[1]
        elif len(choices) == 0:
            return await self.bot.say('Bestiary not found.')
        else:
            bestiary = choices[0][0]
            bestiary_url = choices[0][1]

        active_bestiaries = self.bot.db.jget('active_bestiaries', {})
        active_bestiaries[ctx.message.author.id] = bestiary_url
        self.bot.db.jset('active_characters', active_bestiaries)

        bestiary = Bestiary.from_raw(bestiary_url, bestiary)
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = f"Active Bestiary: {bestiary.name}"
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
