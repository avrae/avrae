import logging
import re

import discord
from bson import ObjectId
from discord.ext import commands

from cogs5e.models.embeds import HomebrewEmbedWithAuthor
from cogs5e.models.errors import NoActiveBrew, NoSelectionElements
from cogs5e.models.homebrew.bestiary import Bestiary, bestiary_from_critterdb, select_bestiary
from cogs5e.models.homebrew.pack import Pack, select_pack
from cogs5e.models.homebrew.tome import Tome, select_tome
from utils.functions import confirm

BREWER_ROLES = ("server brewer", "dragonspeaker")

log = logging.getLogger(__name__)


class Homebrew:
    """Commands to manage homebrew in Avrae."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def can_manage_serverbrew(ctx):
        return ctx.message.author.server_permissions.manage_server or \
               any(r.name.lower() in BREWER_ROLES for r in ctx.message.author.roles) or \
               ctx.message.author.id == ctx.bot.owner.id

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

    @bestiary.group(pass_context=True, name='server', no_pm=True, invoke_without_command=True)
    async def bestiary_server(self, ctx):
        """Toggles whether the active bestiary should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        if not self.can_manage_serverbrew(ctx):
            return await self.bot.say("You do not have permission to manage server homebrew. Either __Manage Server__ "
                                      "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
                                      "is required.")
        bestiary = await Bestiary.from_ctx(ctx)
        is_server_active = await bestiary.toggle_server_active(ctx)
        if is_server_active:
            await self.bot.say(f"Ok, {bestiary.name} is now active on {ctx.message.server.name}!")
        else:
            await self.bot.say(f"Ok, {bestiary.name} is no longer active on {ctx.message.server.name}.")

    @bestiary_server.command(pass_context=True, name='list')
    async def bestiary_server_list(self, ctx):
        """Shows what bestiaries are currently active on the server."""
        desc = ""
        async for doc in self.bot.mdb.bestiaries.find({"server_active": ctx.message.server.id}, ['name', 'owner']):
            desc += f"{doc['name']} (<@{doc['owner']}>)\n"
        await self.bot.say(embed=discord.Embed(title="Active Server Bestiaries", description=desc))

    @commands.group(pass_context=True, invoke_without_command=True)
    async def pack(self, ctx, *, name=None):
        """Commands to manage homebrew items.
        When called without an argument, lists the current pack and its description.
        When called with a name, switches to a different pack."""
        user_packs = await self.bot.mdb.packs.count_documents(Pack.view_query(ctx.message.author.id))

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
        if pack.image:
            embed.set_thumbnail(url=pack.image)
        itemnames = "\n".join(i['name'] for i in pack.items)
        if len(itemnames) < 1020:
            embed.add_field(name="Items", value=itemnames)
        else:
            embed.add_field(name="Items", value=f"{len(pack.items)} items.")
        await self.bot.say(embed=embed)

    @pack.command(pass_context=True, name='list')
    async def pack_list(self, ctx):
        """Lists your available packs."""
        available_pack_names = await self.bot.mdb.packs.find(
            Pack.view_query(ctx.message.author.id),
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

    @pack.command(pass_context=True, name='subscribe', aliases=['sub'])
    async def pack_sub(self, ctx, url):
        """Subscribes to another user's pack."""
        pack_id_match = re.search(r"homebrew/items/([0-9a-f]{24})/?", url)
        if not pack_id_match:
            return await self.bot.say("Invalid pack URL.")
        try:
            pack = await Pack.from_id(ctx, pack_id_match.group(1))
        except NoActiveBrew:
            return await self.bot.say("Pack not found.")

        if not pack.public:
            return await self.bot.say("This pack is not public.")

        user = ctx.message.author
        if user.id not in [s['id'] for s in pack.subscribers]:
            pack.subscribers.append({"username": str(user), "id": user.id})
            out = f"Subscribed to {pack.name} by {pack.owner['username']}. Use `!pack {pack.name}` to select it."
        else:
            pack.subscribers.remove(next(s for s in pack.subscribers if s['id'] == user.id))
            out = f"Unsubscribed from {pack.name}."
        await pack.commit(ctx)
        await self.bot.say(out)

    @pack.group(pass_context=True, name='server', no_pm=True, invoke_without_command=True)
    async def pack_server(self, ctx):
        """Toggles whether the active pack should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        if not self.can_manage_serverbrew(ctx):
            return await self.bot.say("You do not have permission to manage server homebrew. Either __Manage Server__ "
                                      "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
                                      "is required.")
        pack = await Pack.from_ctx(ctx)
        is_server_active = await pack.toggle_server_active(ctx)
        if is_server_active:
            await self.bot.say(f"Ok, {pack.name} is now active on {ctx.message.server.name}!")
        else:
            await self.bot.say(f"Ok, {pack.name} is no longer active on {ctx.message.server.name}.")

    @pack_server.command(pass_context=True, name='list')
    async def pack_server_list(self, ctx):
        """Shows what packs are currently active on the server."""
        desc = ""
        async for doc in self.bot.mdb.packs.find({"server_active": ctx.message.server.id}, ['name', 'owner']):
            desc += f"{doc['name']} (<@{doc['owner']['id']}>)\n"
        await self.bot.say(embed=discord.Embed(title="Active Server Packs", description=desc))

    @commands.group(pass_context=True, invoke_without_command=True)
    async def tome(self, ctx, *, name=None):
        """Commands to manage homebrew spells.
        When called without an argument, lists the current tome and its description.
        When called with a name, switches to a different tome."""
        user_tomes = await self.bot.mdb.tomes.count_documents(Tome.view_query(ctx.message.author.id))

        if not user_tomes:
            return await self.bot.say(
                "You have no tomes. You can make one at <https://avrae.io/dashboard/homebrew/spells>!")

        if name is None:
            tome = await Tome.from_ctx(ctx)
        else:
            try:
                tome = await select_tome(ctx, name)
            except NoActiveBrew:
                return await self.bot.say(
                    "You have no tomes. You can make one at <https://avrae.io/dashboard/homebrew/spells>!")
            except NoSelectionElements:
                return await self.bot.say("Tome not found.")
            await tome.set_active(ctx)
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = tome.name
        embed.description = tome.desc
        if tome.image:
            embed.set_thumbnail(url=tome.image)
        spellnames = "\n".join(i.name for i in tome.spells)
        if len(spellnames) < 1020:
            embed.add_field(name="Spells", value=spellnames)
        else:
            embed.add_field(name="Spells", value=f"{len(tome.spells)} spells.")
        await self.bot.say(embed=embed)

    @tome.command(pass_context=True, name='list')
    async def tome_list(self, ctx):
        """Lists your available tomes."""
        available_tome_names = await self.bot.mdb.tomes.find(
            Tome.view_query(ctx.message.author.id),
            ['name']
        ).to_list(None)
        await self.bot.say(f"Your available tomes: {', '.join(p['name'] for p in available_tome_names)}")

    @tome.command(pass_context=True, name='editor')
    async def tome_editor(self, ctx, user: discord.Member):
        """Allows another user to edit your active tome."""
        tome = await Tome.from_ctx(ctx)
        if not tome.owner['id'] == ctx.message.author.id:
            return await self.bot.say("You do not have permission to add editors to this tome.")
        if tome.owner['id'] == user.id:
            return await self.bot.say("You already own this tome.")

        if user.id not in [e['id'] for e in tome.editors]:
            tome.editors.append({"username": str(user), "id": user.id})
            await self.bot.say(f"{user} added to {tome.name}'s editors.")
        else:
            tome.editors.remove(next(e for e in tome.editors if e['id'] == user.id))
            await self.bot.say(f"{user} removed from {tome.name}'s editors.")
        await tome.commit(ctx)

    @tome.command(pass_context=True, name='subscribe', aliases=['sub'])
    async def tome_sub(self, ctx, url):
        """Subscribes to another user's tome."""
        tome_id_match = re.search(r"homebrew/spells/([0-9a-f]{24})/?", url)
        if not tome_id_match:
            return await self.bot.say("Invalid tome URL.")
        try:
            tome = await Tome.from_id(ctx, tome_id_match.group(1))
        except NoActiveBrew:
            return await self.bot.say("Pack not found.")

        if not tome.public:
            return await self.bot.say("This tome is not public.")

        user = ctx.message.author
        if user.id not in [s['id'] for s in tome.subscribers]:
            tome.subscribers.append({"username": str(user), "id": user.id})
            out = f"Subscribed to {tome.name} by {tome.owner['username']}. Use `!tome {tome.name}` to select it."
        else:
            tome.subscribers.remove(next(s for s in tome.subscribers if s['id'] == user.id))
            out = f"Unsubscribed from {tome.name}."
        await tome.commit(ctx)
        await self.bot.say(out)

    @tome.group(pass_context=True, name='server', no_pm=True, invoke_without_command=True)
    async def tome_server(self, ctx):
        """Toggles whether the active tome should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        if not self.can_manage_serverbrew(ctx):
            return await self.bot.say("You do not have permission to manage server homebrew. Either __Manage Server__ "
                                      "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
                                      "is required.")
        tome = await Tome.from_ctx(ctx)
        is_server_active = await tome.toggle_server_active(ctx)
        if is_server_active:
            await self.bot.say(f"Ok, {tome.name} is now active on {ctx.message.server.name}!")
        else:
            await self.bot.say(f"Ok, {tome.name} is no longer active on {ctx.message.server.name}.")

    @tome_server.command(pass_context=True, name='list')
    async def tome_server_list(self, ctx):
        """Shows what tomes are currently active on the server."""
        desc = ""
        async for doc in self.bot.mdb.tomes.find({"server_active": ctx.message.server.id}, ['name', 'owner']):
            desc += f"{doc['name']} (<@{doc['owner']['id']}>)\n"
        await self.bot.say(embed=discord.Embed(title="Active Server Tomes", description=desc))


def setup(bot):
    bot.add_cog(Homebrew(bot))
