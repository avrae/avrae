import logging
import re

import discord
from discord.ext import commands

from cogs5e.models.embeds import HomebrewEmbedWithAuthor
from cogs5e.models.errors import NoActiveBrew, NoSelectionElements, NotAllowed
from cogs5e.models.homebrew import Pack, Tome
from cogs5e.models.homebrew.bestiary import Bestiary, select_bestiary
from utils import checks
from utils.functions import confirm, search_and_select, user_from_id

log = logging.getLogger(__name__)


class Homebrew(commands.Cog):
    """Commands to manage homebrew in Avrae."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    async def bestiary(self, ctx, *, name=None):
        """Commands to manage homebrew monsters.
        When called without an argument, lists the current bestiary and the monsters in it.
        When called with a name, switches to a different bestiary."""
        user_bestiaries = await Bestiary.num_user(ctx)

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
        await bestiary.load_monsters(ctx)
        monnames = '\n'.join(m.name for m in bestiary.monsters)
        if len(monnames) < 1020:
            embed.add_field(name="Creatures", value=monnames)
        else:
            embed.add_field(name="Creatures", value=f"{len(bestiary.monsters)} creatures.")
        await ctx.send(embed=embed)

    @bestiary.command(name='list')
    async def bestiary_list(self, ctx):
        """Lists your available bestiaries."""
        out = [b.name async for b in Bestiary.user_bestiaries(ctx)]
        await ctx.send(f"Your bestiaries: {', '.join(out)}")

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
            await bestiary.unsubscribe(ctx)
            return await ctx.send('{} has been deleted.'.format(bestiary.name))
        else:
            return await ctx.send("OK, cancelling.")

    @bestiary.command(name='import')
    async def bestiary_import(self, ctx, url):
        """
        Imports a bestiary from [CritterDB](https://critterdb.com/).

        To share a bestiary with Avrae, enable Link Sharing in the sharing menu of your bestiary!

        If your attacks don't seem to be importing properly, you can add a hidden line to the description to set it:
        `<avrae hidden>NAME|TOHITBONUS|DAMAGE</avrae>`
        """

        # ex: https://critterdb.com//#/publishedbestiary/view/5acb0aa187653a455731b890
        # https://critterdb.com/#/publishedbestiary/view/57552905f9865548206b50b0
        # https://critterdb.com:443/#/bestiary/view/5acfe382de482a4d0ed57b46
        if not (match := re.match(
                r'https?://(?:www\.)?critterdb.com(?::443|:80)?.*#/(published)?bestiary/view/([0-9a-f]+)',
                url)):
            return await ctx.send("This is not a CritterDB link.")

        loading = await ctx.send("Importing bestiary (this may take a while for large bestiaries)...")
        bestiary_id = match.group(2)
        is_published = bool(match.group(1))

        bestiary = await Bestiary.from_critterdb(ctx, bestiary_id, published=is_published)

        await bestiary.set_active(ctx)
        await bestiary.load_monsters(ctx)
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
        try:
            active_bestiary = await Bestiary.from_ctx(ctx)
        except NoActiveBrew:
            return await ctx.send(
                f"You don't have a bestiary active. Add one with `{ctx.prefix}bestiary import` first!")
        loading = await ctx.send("Updating bestiary (this may take a while for large bestiaries)...")

        old_server_subs = await active_bestiary.server_subscriptions(ctx)
        await active_bestiary.unsubscribe(ctx)
        bestiary = await Bestiary.from_critterdb(ctx, active_bestiary.upstream, active_bestiary.published)

        await bestiary.add_server_subscriptions(ctx, old_server_subs)
        await bestiary.set_active(ctx)
        await bestiary.load_monsters(ctx)
        await loading.edit(content=f"Imported and updated {bestiary.name}!")
        embed = HomebrewEmbedWithAuthor(ctx)
        embed.title = bestiary.name
        embed.description = '\n'.join(m.name for m in bestiary.monsters)
        await ctx.send(embed=embed)

    @bestiary.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    @checks.can_edit_serverbrew()
    async def bestiary_server(self, ctx):
        """Toggles whether the active bestiary should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        bestiary = await Bestiary.from_ctx(ctx)
        is_server_active = await bestiary.toggle_server_active(ctx)
        if is_server_active:
            await ctx.send(f"Ok, {bestiary.name} is now active on {ctx.guild.name}!")
        else:
            await ctx.send(f"Ok, {bestiary.name} is no longer active on {ctx.guild.name}.")

    @bestiary_server.command(name='list')
    @commands.guild_only()
    async def bestiary_server_list(self, ctx):
        """Shows what bestiaries are currently active on the server."""
        desc = []
        async for best in Bestiary.server_bestiaries(ctx):
            sharer = await best.get_server_sharer(ctx)
            desc.append(f"{best.name} (<@{sharer}>)")
        await ctx.send(embed=discord.Embed(title="Active Server Bestiaries", description="\n".join(desc)))

    @bestiary_server.command(name='remove', aliases=['delete'])
    @commands.guild_only()
    @checks.can_edit_serverbrew()
    async def bestiary_server_remove(self, ctx, bestiary_name):
        """Removes a server bestiary."""
        bestiaries = []
        async for best in Bestiary.server_bestiaries(ctx):
            bestiaries.append(best)

        bestiary = await search_and_select(ctx, bestiaries, bestiary_name, lambda b: b.name)
        await bestiary.toggle_server_active(ctx)
        await ctx.send(f"Ok, {bestiary.name} is no longer active on {ctx.guild.name}.")

    @commands.group(invoke_without_command=True)
    async def pack(self, ctx, *, name=None):
        """Commands to manage homebrew items.
        When called without an argument, lists the current pack and its description.
        When called with a name, switches to a different pack."""
        num_visible = await Pack.num_visible(ctx)

        if not num_visible:
            return await ctx.send(
                "You have no packs. You can make one at <https://avrae.io/dashboard/homebrew/items>!")

        if name is None:
            pack = await Pack.from_ctx(ctx)
        else:
            try:
                pack = await Pack.select(ctx, name)
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
        itemnames = "\n".join(i.name for i in pack.items)
        if not pack.items:
            embed.add_field(name="Items", value=f"This pack has no items.")
        elif len(itemnames) < 1020:
            embed.add_field(name="Items", value=itemnames)
        else:
            embed.add_field(name="Items", value=f"{len(pack.items)} items.")
        await ctx.send(embed=embed)

    @pack.command(name='list')
    async def pack_list(self, ctx):
        """Lists your available packs."""
        available_pack_names = Pack.user_visible(ctx, meta_only=True)
        await ctx.send(f"Your available packs: {', '.join([p['name'] async for p in available_pack_names])}")

    @pack.command(name='editor')
    async def pack_editor(self, ctx, user: discord.Member):
        """Allows another user to edit your active pack."""
        pack = await Pack.from_ctx(ctx)
        if not pack.is_owned_by(ctx.author):
            return await ctx.send("You do not have permission to add editors to this pack.")
        elif pack.is_owned_by(user):
            return await ctx.send("You already own this pack.")

        can_edit = await pack.toggle_editor(ctx, user)

        if can_edit:
            await ctx.send(f"{user} added to {pack.name}'s editors.")
        else:
            await ctx.send(f"{user} removed from {pack.name}'s editors.")

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

        await pack.subscribe(ctx)
        pack_owner = await user_from_id(ctx, pack.owner)
        await ctx.send(f"Subscribed to {pack.name} by {pack_owner}. "
                       f"Use `{ctx.prefix}pack {pack.name}` to select it.")

    @pack.command(name='unsubscribe', aliases=['unsub'])
    async def pack_unsub(self, ctx, name):
        """Unsubscribes from another user's pack."""
        pack = await Pack.select(ctx, name)
        try:
            await pack.unsubscribe(ctx)
        except NotAllowed:
            return await ctx.send("You aren't subscribed to this pack! Maybe you own it, or are an editor?")
        await ctx.send(f"Unsubscribed from {pack.name}.")

    @pack.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    @checks.can_edit_serverbrew()
    async def pack_server(self, ctx):
        """Toggles whether the active pack should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        pack = await Pack.from_ctx(ctx)
        is_server_active = await pack.toggle_server_active(ctx)
        if is_server_active:
            await ctx.send(f"Ok, {pack.name} is now active on {ctx.guild.name}!")
        else:
            await ctx.send(f"Ok, {pack.name} is no longer active on {ctx.guild.name}.")

    @pack_server.command(name='list')
    @commands.guild_only()
    async def pack_server_list(self, ctx):
        """Shows what packs are currently active on the server."""
        desc = ""
        async for pack in Pack.server_active(ctx, meta_only=True):
            desc += f"{pack['name']} (<@{pack['owner']}>)\n"
        await ctx.send(embed=discord.Embed(title="Active Server Packs", description=desc))

    @pack_server.command(name='remove', aliases=['delete'])
    @commands.guild_only()
    @checks.can_edit_serverbrew()
    async def pack_server_remove(self, ctx, pack_name):
        """Removes a server pack."""
        pack_metas = [p async for p in Pack.server_active(ctx, meta_only=True)]

        pack_meta = await search_and_select(ctx, pack_metas, pack_name, lambda b: b['name'])
        pack = await Pack.from_id(ctx, pack_meta['_id'])

        await pack.toggle_server_active(ctx)
        await ctx.send(f"Ok, {pack.name} is no longer active on {ctx.guild.name}.")

    @commands.group(invoke_without_command=True)
    async def tome(self, ctx, *, name=None):
        """Commands to manage homebrew spells.
        When called without an argument, lists the current tome and its description.
        When called with a name, switches to a different tome."""
        num_visible = await Tome.num_visible(ctx)

        if not num_visible:
            return await ctx.send(
                "You have no tomes. You can make one at <https://avrae.io/dashboard/homebrew/spells>!")

        if name is None:
            tome = await Tome.from_ctx(ctx)
        else:
            try:
                tome = await Tome.select(ctx, name)
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
        if not tome.spells:
            embed.add_field(name="Spells", value=f"This tome has no spells.")
        elif len(spellnames) < 1020:
            embed.add_field(name="Spells", value=spellnames)
        else:
            embed.add_field(name="Spells", value=f"{len(tome.spells)} spells.")
        await ctx.send(embed=embed)

    @tome.command(name='list')
    async def tome_list(self, ctx):
        """Lists your available tomes."""
        available_tome_names = Tome.user_visible(ctx, meta_only=True)
        await ctx.send(f"Your available tomes: {', '.join([p['name'] async for p in available_tome_names])}")

    @tome.command(name='editor')
    async def tome_editor(self, ctx, user: discord.Member):
        """Allows another user to edit your active tome."""
        tome = await Tome.from_ctx(ctx)
        if not tome.is_owned_by(ctx.author):
            return await ctx.send("You do not have permission to add editors to this tome.")
        elif tome.is_owned_by(user):
            return await ctx.send("You already own this tome.")

        can_edit = await tome.toggle_editor(ctx, user)

        if can_edit:
            await ctx.send(f"{user} added to {tome.name}'s editors.")
        else:
            await ctx.send(f"{user} removed from {tome.name}'s editors.")

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

        await tome.subscribe(ctx)
        tome_owner = await user_from_id(ctx, tome.owner)
        await ctx.send(f"Subscribed to {tome.name} by {tome_owner}. "
                       f"Use `{ctx.prefix}tome {tome.name}` to select it.")

    @tome.command(name='unsubscribe', aliases=['unsub'])
    async def tome_unsub(self, ctx, name):
        """Unsubscribes from another user's tome."""
        tome = await Tome.select(ctx, name)
        try:
            await tome.unsubscribe(ctx)
        except NotAllowed:
            return await ctx.send("You aren't subscribed to this tome! Maybe you own it, or are an editor?")
        await ctx.send(f"Unsubscribed from {tome.name}.")

    @tome.group(name='server', invoke_without_command=True)
    @commands.guild_only()
    @checks.can_edit_serverbrew()
    async def tome_server(self, ctx):
        """Toggles whether the active tome should be viewable by anyone on the server.
        Requires __Manage Server__ permissions or a role named "Server Brewer" to run."""
        tome = await Tome.from_ctx(ctx)
        is_server_active = await tome.toggle_server_active(ctx)
        if is_server_active:
            await ctx.send(f"Ok, {tome.name} is now active on {ctx.guild.name}!")
        else:
            await ctx.send(f"Ok, {tome.name} is no longer active on {ctx.guild.name}.")

    @tome_server.command(name='list')
    @commands.guild_only()
    async def tome_server_list(self, ctx):
        """Shows what tomes are currently active on the server."""
        desc = ""
        async for tome in Tome.server_active(ctx, meta_only=True):
            desc += f"{tome['name']} (<@{tome['owner']}>)\n"
        await ctx.send(embed=discord.Embed(title="Active Server Tomes", description=desc))

    @tome_server.command(name='remove', aliases=['delete'])
    @commands.guild_only()
    @checks.can_edit_serverbrew()
    async def tome_server_remove(self, ctx, tome_name):
        """Removes a server tome."""
        tome_metas = [t async for t in Tome.server_active(ctx, meta_only=True)]

        tome_meta = await search_and_select(ctx, tome_metas, tome_name, lambda b: b['name'])
        tome = await Tome.from_id(ctx, tome_meta['_id'])

        await tome.toggle_server_active(ctx)
        await ctx.send(f"Ok, {tome.name} is no longer active on {ctx.guild.name}.")


def setup(bot):
    bot.add_cog(Homebrew(bot))
