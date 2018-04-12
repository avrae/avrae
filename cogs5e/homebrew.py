import logging

import aiohttp
from discord.ext import commands

from cogs5e.models.bestiary import Bestiary
from cogs5e.models.embeds import HomebrewEmbedWithAuthor
from cogs5e.models.monster import Monster
from utils.functions import get_selection, confirm

log = logging.getLogger(__name__)


class Homebrew:
    """Commands to manage homebrew in Avrae."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True, invoke_without_command=True)
    async def bestiary(self, ctx, *, name=None):
        """Commands to manage homebrew monsters.
        When called without an argument, lists the current bestiary and the monsters in it.
        When called with a name, switches to a different bestiary."""
        user_bestiaries = self.bot.db.jget(ctx.message.author.id + '.bestiaries', None)

        if user_bestiaries is None:
            return await self.bot.say("You have no bestiaries. Use `!bestiary import` to import one!")

        if name is None:
            bestiary = Bestiary.from_ctx(ctx)
        else:
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
            self.bot.db.jset('active_bestiaries', active_bestiaries)

            bestiary = Bestiary.from_raw(bestiary_url, bestiary)
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await self.bot.say(embed=embed)

    @bestiary.command(pass_context=True, name='list')
    async def bestiary_list(self, ctx):
        """Lists your available bestiaries."""
        user_bestiaries = ctx.bot.db.jget(ctx.message.author.id + '.bestiaries', {})
        await self.bot.say(f"Your bestiaries: {', '.join(b['name'] for b in user_bestiaries.values())}")

    @bestiary.command(pass_context=True, name='delete')
    async def bestiary_delete(self, ctx):
        """Deletes the active bestiary from Avrae."""
        bestiary = Bestiary.from_ctx(ctx)

        resp = await confirm(ctx, 'Are you sure you want to delete {}? (Reply with yes/no)'.format(bestiary.name))

        if resp:
            user_bestiaries = ctx.bot.db.jget(ctx.message.author.id + '.bestiaries', {})
            active_bestiaries = ctx.bot.db.jget('active_bestiaries', {})
            active_bestiaries[ctx.message.author.id] = None
            del user_bestiaries[bestiary.id]
            self.bot.db.jset(ctx.message.author.id + '.bestiaries', user_bestiaries)
            self.bot.db.not_json_set('active_bestiaries', active_bestiaries)
            return await self.bot.say('{} has been deleted.'.format(bestiary.name))
        else:
            return await self.bot.say("OK, cancelling.")

    @bestiary.command(pass_context=True, name='import')
    async def bestiary_import(self, ctx, url):
        """Imports a published bestiary from [CritterDB](http://www.critterdb.com/)."""
        # ex: http://www.critterdb.com/#/publishedbestiary/view/5acb0aa187653a455731b890
        # http://www.critterdb.com/#/publishedbestiary/view/57552905f9865548206b50b0
        if not 'critterdb.com' in url:
            return await self.bot.say("This is not a CritterDB link.")
        bestiary_id = url.split('/view')[1].strip('/ \n')
        log.info(f"Getting bestiary ID {bestiary_id}...")
        index = 1
        creatures = []
        loading = await self.bot.say("Importing bestiary (this may take a while for large bestiaries)...")
        async with aiohttp.ClientSession() as session:
            for _ in range(100):  # 100 pages max
                log.info(f"Getting page {index} of {bestiary_id}...")
                async with session.get(
                        f"http://www.critterdb.com/api/publishedbestiaries/{bestiary_id}/creatures/{index}") as resp:
                    raw = await resp.json()
                    if not raw:
                        break
                    creatures.extend(raw)
                    index += 1
            async with session.get(f"http://www.critterdb.com/api/publishedbestiaries/{bestiary_id}") as resp:
                raw = await resp.json()
                name = raw['name']

        parsed_creatures = [Monster.from_critterdb(c) for c in creatures]
        bestiary = Bestiary(bestiary_id, name, parsed_creatures).set_active(ctx).commit(ctx)
        await self.bot.edit_message(loading, f"Imported {name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await self.bot.say(embed=embed)

    @bestiary.command(pass_context=True, name='update')
    async def bestiary_update(self, ctx):
        """Updates the active bestiary from CritterDB."""
        bestiary_id = self.bot.db.jget('active_bestiaries', {}).get(ctx.message.author.id)
        if bestiary_id is None:
            return await self.bot.say("You don't have a bestiary active. Add one with `!bestiary import` first!")

        log.info(f"Getting bestiary ID {bestiary_id}...")
        index = 1
        creatures = []
        loading = await self.bot.say("Importing bestiary (this may take a while for large bestiaries)...")
        async with aiohttp.ClientSession() as session:
            for _ in range(100):  # 100 pages max
                log.info(f"Getting page {index} of {bestiary_id}...")
                async with session.get(
                        f"http://www.critterdb.com/api/publishedbestiaries/{bestiary_id}/creatures/{index}") as resp:
                    raw = await resp.json()
                    if not raw:
                        break
                    creatures.extend(raw)
                    index += 1
            async with session.get(f"http://www.critterdb.com/api/publishedbestiaries/{bestiary_id}") as resp:
                raw = await resp.json()
                name = raw['name']

        parsed_creatures = [Monster.from_critterdb(c) for c in creatures]
        bestiary = Bestiary(bestiary_id, name, parsed_creatures).set_active(ctx).commit(ctx)
        await self.bot.edit_message(loading, f"Imported and updated {name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await self.bot.say(embed=embed)
