import logging

import discord
from discord.ext import commands

from cogs5e.models.embeds import HomebrewEmbedWithAuthor
from cogs5e.models.errors import NoActiveBrew, NoSelectionElements
from cogs5e.models.homebrew.bestiary import Bestiary, bestiary_from_critterdb, select_bestiary
from cogs5e.models.homebrew.pack import Pack, select_pack
from utils.functions import confirm

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
        user_bestiaries = await self.bot.mdb.bestiaries.count_documents({"owner": ctx.message.author.id})

        if not user_bestiaries:
            return await self.bot.say("You have no bestiaries. Use `!bestiary import` to import one!")

        if name is None:
            bestiary = await Bestiary.from_ctx(ctx)
        else:
            try:
                bestiary = await select_bestiary(ctx, name)
            except NoActiveBrew:
                return await self.bot.say("You have no bestiaries. Use `!bestiary import` to import one!")
            except NoSelectionElements:
                return await self.bot.say("Bestiary not found.")
            await bestiary.set_active(ctx)
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await self.bot.say(embed=embed)

    @bestiary.command(pass_context=True, name='list')
    async def bestiary_list(self, ctx):
        """Lists your available bestiaries."""
        user_bestiaries = await self.bot.mdb.bestiaries.find({"owner": ctx.message.author.id}, ['name']).to_list(None)
        await self.bot.say(f"Your bestiaries: {', '.join(b['name'] for b in user_bestiaries)}")

    @bestiary.command(pass_context=True, name='delete')
    async def bestiary_delete(self, ctx, *, name):
        """Deletes a bestiary from Avrae."""
        try:
            bestiary = await select_bestiary(ctx, name)
        except NoActiveBrew:
            return await self.bot.say("You have no bestiaries. Use `!bestiary import` to import one!")
        except NoSelectionElements:
            return await self.bot.say("Bestiary not found.")

        resp = await confirm(ctx, 'Are you sure you want to delete {}? (Reply with yes/no)'.format(bestiary.name))

        if resp:
            await self.bot.mdb.bestiaries.delete_one({"critterdb_id": bestiary.id})
            return await self.bot.say('{} has been deleted.'.format(bestiary.name))
        else:
            return await self.bot.say("OK, cancelling.")

    @bestiary.command(pass_context=True, name='import')
    async def bestiary_import(self, ctx, url):
        """Imports a published bestiary from [CritterDB](https://critterdb.com/)."""
        # ex: https://critterdb.com//#/publishedbestiary/view/5acb0aa187653a455731b890
        # https://critterdb.com/#/publishedbestiary/view/57552905f9865548206b50b0
        if not 'critterdb.com' in url:
            return await self.bot.say("This is not a CritterDB link.")
        if not 'publishedbestiary' in url:
            return await self.bot.say("This is not a public bestiary. Publish it to import!")

        loading = await self.bot.say("Importing bestiary (this may take a while for large bestiaries)...")
        bestiary_id = url.split('/view')[1].strip('/ \n')

        bestiary = await bestiary_from_critterdb(bestiary_id)

        await bestiary.commit(ctx)
        await bestiary.set_active(ctx)
        await self.bot.edit_message(loading, f"Imported {bestiary.name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await self.bot.say(embed=embed)

    @bestiary.command(pass_context=True, name='update')
    async def bestiary_update(self, ctx):
        """Updates the active bestiary from CritterDB."""
        active_bestiary = await self.bot.mdb.bestiaries.find_one({"owner": ctx.message.author.id, "active": True})

        if active_bestiary is None:
            return await self.bot.say("You don't have a bestiary active. Add one with `!bestiary import` first!")
        loading = await self.bot.say("Importing bestiary (this may take a while for large bestiaries)...")

        bestiary = await bestiary_from_critterdb(active_bestiary["critterdb_id"])

        await bestiary.commit(ctx)
        await self.bot.edit_message(loading, f"Imported and updated {bestiary.name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await self.bot.say(embed=embed)

    @commands.group(pass_context=True, invoke_without_command=True)
    async def pack(self, ctx, *, name=None):
        """Commands to manage homebrew items.
        When called without an argument, lists the current pack and its description.
        When called with a name, switches to a different pack."""
        user_packs = await self.bot.mdb.packs.count_documents(
            {"$or": [{"owner.id": ctx.message.author.id}, {"editors.id": ctx.message.author.id}]})

        if not user_packs:
            return await self.bot.say(
                "You have no packs. You can make one at <https://avrae.io/dashboard/homebrew/items>!")

        if name is None:
            pack = await Pack.from_ctx(ctx)
        else:
            try:
                pack = await select_pack(ctx, name)
            except NoActiveBrew:
                return await self.bot.say(
                    "You have no packs. You can make one at <https://avrae.io/dashboard/homebrew/items>!")
            except NoSelectionElements:
                return await self.bot.say("Pack not found.")
            await pack.set_active(ctx)
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = pack.name
        embed.description = pack.desc
        embed.set_thumbnail(url=pack.image)
        itemnames = "\n".join(i['name'] for i in pack.items)
        if len(itemnames) < 1200:
            embed.add_field(name="Items", value=itemnames)
        else:
            embed.add_field(name="Items", value=f"{len(pack.items)} items.")
        await self.bot.say(embed=embed)

    @pack.command(pass_context=True, name='list')
    async def pack_list(self, ctx):
        """Lists your available packs."""
        available_pack_names = await self.bot.mdb.packs.find(
            {"$or": [{"owner.id": ctx.message.author.id}, {"editors.id": ctx.message.author.id}]},
            ['name']
        ).to_list(None)
        await self.bot.say(f"Your available packs: {', '.join(p['name'] for p in available_pack_names)}")

    @pack.command(pass_context=True, name='editor')
    async def pack_editor(self, ctx, user: discord.Member):
        """Allows another user to edit your active pack."""
        pack = await Pack.from_ctx(ctx)
        if not pack.owner['id'] == ctx.message.author.id:
            return await self.bot.say("You do not have permission to add editors to this pack.")
        if pack.owner['id'] == user.id:
            return await self.bot.say("You already own this pack.")

        if user.id not in [e['id'] for e in pack.editors]:
            pack.editors.append({"username": str(user), "id": user.id})
            await self.bot.say(f"{user} added to {pack.name}'s editors.")
        else:
            pack.editors.remove(next(e for e in pack.editors if e['id'] == user.id))
            await self.bot.say(f"{user} removed from {pack.name}'s editors.")
        await pack.commit(ctx)


def setup(bot):
    bot.add_cog(Homebrew(bot))
