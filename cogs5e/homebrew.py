import logging
import re

import discord
from discord.ext import commands

from cogs5e.models.embeds import HomebrewEmbedWithAuthor
from cogs5e.models.errors import NoActiveBrew, NoSelectionElements
from cogs5e.models.homebrew.bestiary import Bestiary, bestiary_from_critterdb, select_bestiary
from cogs5e.models.homebrew.pack import Pack, select_pack
from cogs5e.models.homebrew.tome import Tome, select_tome
from utils.functions import confirm

BREWER_ROLES = ("server brewer", "dragonspeaker")

log = logging.getLogger(__name__)


class Homebrew(commands.Cog):
    """Commands to manage homebrew in Avrae."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def can_manage_serverbrew(ctx):
        return ctx.author.guild_permissions.manage_guild or \
               any(r.name.lower() in BREWER_ROLES for r in ctx.author.roles) or \
               str(ctx.author.id) == ctx.bot.owner.id

    @commands.group(invoke_without_command=True)
    async def bestiary(self, ctx, *, name=None):
        """Commands to manage homebrew monsters.
        When called without an argument, lists the current bestiary and the monsters in it.
        When called with a name, switches to a different bestiary."""
        user_bestiaries = await self.bot.mdb.bestiaries.count_documents({"owner": str(ctx.author.id)})

        if not user_bestiaries:
            return await ctx.send(f"You have no bestiaries. Use `{ctx.prefix}bestiary import` to import one!")

        if name is None:
            bestiary = await Bestiary.from_ctx(ctx)
        else:
            try:
                bestiary = await select_bestiary(ctx, name)
            except NoActiveBrew:
                return await ctx.send(f"You have no bestiaries. Use `{ctx.prefix}bestiary import` to import one!")
            except NoSelectionElements:
                return await ctx.send("Bestiary not found.")
            await bestiary.set_active(ctx)
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        if bestiary.desc:
            embed.description = bestiary.desc
        monnames = '\n'.join(m.name for m in bestiary.monsters)
        if len(monnames) < 1020:
            embed.add_field(name="Creatures", value=monnames)
        else:
            embed.add_field(name="Creatures", value=f"{len(bestiary.monsters)} creatures.")
        await ctx.send(embed=embed)

    @bestiary.command(name='list')
    async def bestiary_list(self, ctx):
        """Lists your available bestiaries."""
        user_bestiaries = await self.bot.mdb.bestiaries.find({"owner": str(ctx.author.id)}, ['name']).to_list(None)
        await ctx.send(f"Your bestiaries: {', '.join(b['name'] for b in user_bestiaries)}")

    @bestiary.command(name='delete')
    async def bestiary_delete(self, ctx, *, name):
        """Deletes a bestiary from Avrae."""
        try:
            bestiary = await select_bestiary(ctx, name)
        except NoActiveBrew:
            return await ctx.send(f"You have no bestiaries. Use `{ctx.prefix}bestiary import` to import one!")
        except NoSelectionElements:
            return await ctx.send("Bestiary not found.")

        resp = await confirm(ctx, 'Are you sure you want to delete {}? (Reply with yes/no)'.format(bestiary.name))

        if resp:
            await self.bot.mdb.bestiaries.delete_one({"critterdb_id": bestiary.id})
            return await ctx.send('{} has been deleted.'.format(bestiary.name))
        else:
            return await ctx.send("OK, cancelling.")

    @bestiary.command(name='import')
    async def bestiary_import(self, ctx, url):
        """Imports a published bestiary from [CritterDB](https://critterdb.com/).
        If your attacks don't seem to be importing properly, you can add a hidden line to the description to set it:
        `<avrae hidden>NAME|TOHITBONUS|DAMAGE</avrae>"""
        # ex: https://critterdb.com//#/publishedbestiary/view/5acb0aa187653a455731b890
        # https://critterdb.com/#/publishedbestiary/view/57552905f9865548206b50b0
        if not 'critterdb.com' in url:
            return await ctx.send("This is not a CritterDB link.")
        if not 'publishedbestiary' in url:
            return await ctx.send("This is not a public bestiary. Publish it to import!")

        loading = await ctx.send("Importing bestiary (this may take a while for large bestiaries)...")
        bestiary_id = url.split('/view')[1].strip('/ \n')

        bestiary = await bestiary_from_critterdb(bestiary_id)

        await bestiary.commit(ctx)
        await bestiary.set_active(ctx)
        await loading.edit(content=f"Imported {bestiary.name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        monnames = '\n'.join(m.name for m in bestiary.monsters)
        if len(monnames) < 2040:
            embed.description = monnames
        else:
            embed.description = f"{len(bestiary.monsters)} creatures."
        await ctx.send(embed=embed)

    @bestiary.command(name='update')
    async def bestiary_update(self, ctx):
        """Updates the active bestiary from CritterDB."""
        active_bestiary = await self.bot.mdb.bestiaries.find_one({"owner": str(ctx.author.id), "active": True})

        if active_bestiary is None:
            return await ctx.send(
                f"You don't have a bestiary active. Add one with `{ctx.prefix}bestiary import` first!")
        loading = await ctx.send("Importing bestiary (this may take a while for large bestiaries)...")

        bestiary = await bestiary_from_critterdb(active_bestiary["critterdb_id"])

        await bestiary.commit(ctx)
        await loading.edit(content=f"Imported and updated {bestiary.name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await ctx.send(embed=embed)

    @bestiary.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    async def bestiary_server(self, ctx):
        """Toggles whether the active bestiary should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        if not self.can_manage_serverbrew(ctx):
            return await ctx.send("You do not have permission to manage server homebrew. Either __Manage Server__ "
                                  "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
                                  "is required.")
        bestiary = await Bestiary.from_ctx(ctx)
        is_server_active = await bestiary.toggle_server_active(ctx)
        if is_server_active:
            await ctx.send(f"Ok, {bestiary.name} is now active on {ctx.guild.name}!")
        else:
            await ctx.send(f"Ok, {bestiary.name} is no longer active on {ctx.guild.name}.")

    @bestiary_server.command(name='list')
    async def bestiary_server_list(self, ctx):
        """Shows what bestiaries are currently active on the server."""
        desc = ""
        async for doc in self.bot.mdb.bestiaries.find({"server_active": str(ctx.guild.id)}, ['name', 'owner']):
            desc += f"{doc['name']} (<@{doc['owner']}>)\n"
        await ctx.send(embed=discord.Embed(title="Active Server Bestiaries", description=desc))

    @commands.group(invoke_without_command=True)
    async def pack(self, ctx, *, name=None):
        """Commands to manage homebrew items.
        When called without an argument, lists the current pack and its description.
        When called with a name, switches to a different pack."""
        user_packs = await self.bot.mdb.packs.count_documents(Pack.view_query(str(ctx.author.id)))

        if not user_packs:
            return await ctx.send(
                "You have no packs. You can make one at <https://avrae.io/dashboard/homebrew/items>!")

        if name is None:
            pack = await Pack.from_ctx(ctx)
        else:
            try:
                pack = await select_pack(ctx, name)
            except NoActiveBrew:
                return await ctx.send(
                    "You have no packs. You can make one at <https://avrae.io/dashboard/homebrew/items>!")
            except NoSelectionElements:
                return await ctx.send("Pack not found.")
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
        await ctx.send(embed=embed)

    @pack.command(name='list')
    async def pack_list(self, ctx):
        """Lists your available packs."""
        available_pack_names = await self.bot.mdb.packs.find(
            Pack.view_query(str(ctx.author.id)),
            ['name']
        ).to_list(None)
        await ctx.send(f"Your available packs: {', '.join(p['name'] for p in available_pack_names)}")

    @pack.command(name='editor')
    async def pack_editor(self, ctx, user: discord.Member):
        """Allows another user to edit your active pack."""
        pack = await Pack.from_ctx(ctx)
        if not pack.owner['id'] == str(ctx.author.id):
            return await ctx.send("You do not have permission to add editors to this pack.")
        if pack.owner['id'] == str(user.id):
            return await ctx.send("You already own this pack.")

        if str(user.id) not in [e['id'] for e in pack.editors]:
            pack.editors.append({"username": str(user), "id": str(user.id)})
            await ctx.send(f"{user} added to {pack.name}'s editors.")
        else:
            pack.editors.remove(next(e for e in pack.editors if e['id'] == str(user.id)))
            await ctx.send(f"{user} removed from {pack.name}'s editors.")
        await pack.commit(ctx)

    @pack.command(name='subscribe', aliases=['sub'])
    async def pack_sub(self, ctx, url):
        """Subscribes to another user's pack."""
        pack_id_match = re.search(r"homebrew/items/([0-9a-f]{24})/?", url)
        if not pack_id_match:
            return await ctx.send("Invalid pack URL.")
        try:
            pack = await Pack.from_id(ctx, pack_id_match.group(1))
        except NoActiveBrew:
            return await ctx.send("Pack not found.")

        if not pack.public:
            return await ctx.send("This pack is not public.")

        user = ctx.author
        if str(user.id) not in [s['id'] for s in pack.subscribers]:
            pack.subscribers.append({"username": str(user), "id": str(user.id)})
            out = f"Subscribed to {pack.name} by {pack.owner['username']}. " \
                f"Use `{ctx.prefix}pack {pack.name}` to select it."
        else:
            pack.subscribers.remove(next(s for s in pack.subscribers if s['id'] == str(user.id)))
            out = f"Unsubscribed from {pack.name}."
        await pack.commit(ctx)
        await ctx.send(out)

    @pack.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    async def pack_server(self, ctx):
        """Toggles whether the active pack should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        if not self.can_manage_serverbrew(ctx):
            return await ctx.send("You do not have permission to manage server homebrew. Either __Manage Server__ "
                                  "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
                                  "is required.")
        pack = await Pack.from_ctx(ctx)
        is_server_active = await pack.toggle_server_active(ctx)
        if is_server_active:
            await ctx.send(f"Ok, {pack.name} is now active on {ctx.guild.name}!")
        else:
            await ctx.send(f"Ok, {pack.name} is no longer active on {ctx.guild.name}.")

    @pack_server.command(name='list')
    async def pack_server_list(self, ctx):
        """Shows what packs are currently active on the server."""
        desc = ""
        async for doc in self.bot.mdb.packs.find({"server_active": str(ctx.guild.id)}, ['name', 'owner']):
            desc += f"{doc['name']} (<@{doc['owner']['id']}>)\n"
        await ctx.send(embed=discord.Embed(title="Active Server Packs", description=desc))

    @commands.group(invoke_without_command=True)
    async def tome(self, ctx, *, name=None):
        """Commands to manage homebrew spells.
        When called without an argument, lists the current tome and its description.
        When called with a name, switches to a different tome."""
        user_tomes = await self.bot.mdb.tomes.count_documents(Tome.view_query(str(ctx.author.id)))

        if not user_tomes:
            return await ctx.send(
                "You have no tomes. You can make one at <https://avrae.io/dashboard/homebrew/spells>!")

        if name is None:
            tome = await Tome.from_ctx(ctx)
        else:
            try:
                tome = await select_tome(ctx, name)
            except NoActiveBrew:
                return await ctx.send(
                    "You have no tomes. You can make one at <https://avrae.io/dashboard/homebrew/spells>!")
            except NoSelectionElements:
                return await ctx.send("Tome not found.")
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
        await ctx.send(embed=embed)

    @tome.command(name='list')
    async def tome_list(self, ctx):
        """Lists your available tomes."""
        available_tome_names = await self.bot.mdb.tomes.find(
            Tome.view_query(str(ctx.author.id)),
            ['name']
        ).to_list(None)
        await ctx.send(f"Your available tomes: {', '.join(p['name'] for p in available_tome_names)}")

    @tome.command(name='editor')
    async def tome_editor(self, ctx, user: discord.Member):
        """Allows another user to edit your active tome."""
        tome = await Tome.from_ctx(ctx)
        if not tome.owner['id'] == str(ctx.author.id):
            return await ctx.send("You do not have permission to add editors to this tome.")
        if tome.owner['id'] == str(user.id):
            return await ctx.send("You already own this tome.")

        if str(user.id) not in [e['id'] for e in tome.editors]:
            tome.editors.append({"username": str(user), "id": str(user.id)})
            await ctx.send(f"{user} added to {tome.name}'s editors.")
        else:
            tome.editors.remove(next(e for e in tome.editors if e['id'] == str(user.id)))
            await ctx.send(f"{user} removed from {tome.name}'s editors.")
        await tome.commit(ctx)

    @tome.command(name='subscribe', aliases=['sub'])
    async def tome_sub(self, ctx, url):
        """Subscribes to another user's tome."""
        tome_id_match = re.search(r"homebrew/spells/([0-9a-f]{24})/?", url)
        if not tome_id_match:
            return await ctx.send("Invalid tome URL.")
        try:
            tome = await Tome.from_id(ctx, tome_id_match.group(1))
        except NoActiveBrew:
            return await ctx.send("Pack not found.")

        if not tome.public:
            return await ctx.send("This tome is not public.")

        user = ctx.author
        if str(user.id) not in [s['id'] for s in tome.subscribers]:
            tome.subscribers.append({"username": str(user), "id": str(user.id)})
            out = f"Subscribed to {tome.name} by {tome.owner['username']}. " \
                f"Use `{ctx.prefix}tome {tome.name}` to select it."
        else:
            tome.subscribers.remove(next(s for s in tome.subscribers if s['id'] == str(user.id)))
            out = f"Unsubscribed from {tome.name}."
        await tome.commit(ctx)
        await ctx.send(out)

    @tome.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    async def tome_server(self, ctx):
        """Toggles whether the active tome should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        if not self.can_manage_serverbrew(ctx):
            return await ctx.send("You do not have permission to manage server homebrew. Either __Manage Server__ "
                                  "Discord permissions or a role named \"Server Brewer\" or \"Dragonspeaker\" "
                                  "is required.")
        tome = await Tome.from_ctx(ctx)
        is_server_active = await tome.toggle_server_active(ctx)
        if is_server_active:
            await ctx.send(f"Ok, {tome.name} is now active on {ctx.guild.name}!")
        else:
            await ctx.send(f"Ok, {tome.name} is no longer active on {ctx.guild.name}.")

    @tome_server.command(name='list')
    async def tome_server_list(self, ctx):
        """Shows what tomes are currently active on the server."""
        desc = ""
        async for doc in self.bot.mdb.tomes.find({"server_active": str(ctx.guild.id)}, ['name', 'owner']):
            desc += f"{doc['name']} (<@{doc['owner']['id']}>)\n"
        await ctx.send(embed=discord.Embed(title="Active Server Tomes", description=desc))


def setup(bot):
    bot.add_cog(Homebrew(bot))
