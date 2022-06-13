"""
Created on Jan 19, 2017

@author: andrew
"""
import logging
import traceback

from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType

from cogs5e.exploration import NoEncounter
from cogs5e.exploration.encounter import Encounter
from cogs5e.models import embeds
from cogs5e.models.embeds import EmbedWithColor
from cogs5e.models.errors import ExternalImportError
from cogs5e.exploration.gsheet import GoogleSheet, extract_gsheet_id_from_url

from utils.argparser import argparse
from utils.functions import confirm, search_and_select, try_delete

log = logging.getLogger(__name__)


class GSheetManager(commands.Cog):
    """
    Commands to load an encounter sheet into Exploration bot, and supporting commands to modify the sheet, as well as basic macros.
    """  # noqa: E501

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def esheet(self, ctx, *args):
        """Prints the embed sheet of your currently active encounter sheet.
        __Valid Arguments__
        -pub - Sends the list to the channel instead of private message."""
        enc: Encounter = await ctx.get_encounter()
        private = "-pub" in args
        destination = ctx if private else ctx.author

        await destination.send(embed=enc.get_sheet_embed())
        await try_delete(ctx.message)

    @commands.command()
    async def rollenc(self, ctx, num: int = 1, *args):
        """Rolls on the currently active encounter sheet as many times as indicated. If no number is submitted, will roll once
        Usage: !rollenc <number> [-p]
        __Valid Arguments__
        -p - Sends the list to the channel instead of private message."""
        enc: Encounter = await ctx.get_encounter()
        embed = EmbedWithColor()
        private = "-p" in args
        destination = ctx if private else ctx.author
        res = enc.roll_encounters(num, 100)
        if num == 1:
            encounters = ["**Random encounter:**\n"]
        else:
            encounters = ["**Random encounters:**\n"]
        for r in res:
            if r[1] is not None:
                encounters.append(f"{r[2]}) {r[1]} {r[0]}")
            else:
                encounters.append(f"{r[2]}) {r[0]}")
        embed.description = "\n".join(encounters)
        await destination.send(embed=embed)
        await try_delete(ctx.message)

    @commands.group(aliases=["enc"], invoke_without_command=True)
    async def encounter(self, ctx, *, name: str = None):
        """Switches the active encounter sheet."""
        if name is None:
            embed = await self._active_encounter_embed(ctx)
            await ctx.send(embed=embed)
            return

        user_encounters = await self.bot.mdb.encounters.find({"owner": str(ctx.author.id)}).to_list(None)
        if not user_encounters:
            return await ctx.send("You have no encounter sheets.")

        selected_enc = await search_and_select(
            ctx, user_encounters, name, lambda e: e["name"], selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)"
        )

        sheet = Encounter.from_dict(selected_enc)
        result = await sheet.set_active(ctx)
        await try_delete(ctx.message)
        if result.did_unset_server_active:
            await ctx.send(
                f"Active sheet changed to {sheet.name}. Your server active encounter sheet has been unset.",
                delete_after=30,
            )
        else:
            await ctx.send(f"Active sheet changed to {sheet.name}.", delete_after=15)

    @encounter.command(name="eserver")
    @commands.guild_only()
    async def encounter_server(self, ctx):
        """
        Sets the current global active encounter sheet as a server sheet.
        If the sheet is already the server sheet, unsets the server sheet.

        All commands in the server that use your active sheet will instead use the server sheet, even if the active sheet is changed elsewhere.
        """  # noqa: E501
        enc: Encounter = await Encounter.from_ctx(ctx, ignore_guild=True)

        if enc.is_active_server(ctx):
            await enc.unset_server_active(ctx)
            msg = f"{enc.name} is no longer active on this server."
            try:
                global_encounter = await ctx.get_encounter()
            except NoEncounter:
                await ctx.send(f"{msg} You have no global active sheet.")
            else:
                await ctx.send(f"{msg} {global_encounter.name} is now active.")
        else:
            result = await enc.set_server_active(ctx)
            if result.did_unset_server_active:
                await ctx.send(f"Active server sheet changed to {enc.name}.")
            else:
                await ctx.send(f"Active server sheet set to {enc.name}.")

        await try_delete(ctx.message)

    @encounter.command(name="list")
    async def encounter_list(self, ctx):
        """Lists your random encounter sheets."""
        user_encounters = await self.bot.mdb.encounters.find({"owner": str(ctx.author.id)}, ["name"]).to_list(None)
        if not user_encounters:
            return await ctx.send("You have no sheets.")
        await ctx.send("Your sheets:\n{}".format(", ".join(sorted(c["name"] for c in user_encounters))))

    @encounter.command(name="delete")
    async def encounter_delete(self, ctx, *, name):
        """Deletes a sheet."""
        user_encounters = await self.bot.mdb.encounters.find(
            {"owner": str(ctx.author.id)}, ["name", "upstream"]
        ).to_list(None)
        if not user_encounters:
            return await ctx.send("You have no sheets.")

        selected_enc = await search_and_select(
            ctx, user_encounters, name, lambda e: e["name"], selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)"
        )

        if await confirm(ctx, f"Are you sure you want to delete {selected_enc['name']}? (Reply with yes/no)"):
            await Encounter.delete(ctx, str(ctx.author.id), selected_enc["upstream"])
            return await ctx.send(f"{selected_enc['name']} has been deleted.")
        else:
            return await ctx.send("Ok, cancelling.")

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def updateenc(self, ctx, *args):
        """
        Updates the current encounter sheet, preserving all settings.
        __Valid Arguments__
        `-v` - Shows encounter sheet after update is complete.
        """
        old_encounter: Encounter = await ctx.get_encounter()
        url = old_encounter.upstream
        args = argparse(args)

        prefix = "google-"
        _id = url[:]
        _id = url[len(prefix) :]

        parser = GoogleSheet(_id)
        loading = await ctx.send("Updating encounter data from Google...")

        try:
            encounter = await parser.load_encounter(ctx)
        except ExternalImportError as eep:
            return await loading.edit(content=f"Error loading sheet: {eep}")
        except Exception as eep:
            log.warning(f"Error importing sheet {old_encounter.upstream}")
            log.warning(traceback.format_exc())
            return await loading.edit(content=f"Error loading sheet: {eep}")

        # keeps an old check if the old sheet was active on the current server
        was_server_active = old_encounter.is_active_server(ctx)

        await encounter.commit(ctx)

        # overwrites the old_encounter's server active state
        # since encounter._active_guilds is old_encounter._active_guilds here
        if old_encounter.is_active_global():
            await encounter.set_active(ctx)
        if was_server_active:
            await encounter.set_server_active(ctx)

        await loading.edit(content=f"Updated and saved data for {encounter.name}!")
        if args.last("v"):
            await ctx.send(embed=encounter.get_sheet_embed())

    async def _confirm_overwrite(self, ctx, _id):
        """Prompts the user if command would overwrite another sheet.
        Returns True to overwrite, False or None otherwise."""
        conflict = await self.bot.mdb.encounters.find_one({"owner": str(ctx.author.id), "upstream": _id})
        if conflict:
            return await confirm(
                ctx,
                f"Warning: This will overwrite an encounter sheet with the same ID. Do you wish to continue "
                f"(Reply with yes/no)?\n"
                f"If you only wanted to update your sheet, run `{ctx.prefix}update` instead.",
            )
        return True

    @commands.command(name="importenc")
    @commands.max_concurrency(1, BucketType.user)
    async def import_esheet(self, ctx, url: str):
        """
        Loads an encounter sheet from google sheets
        The sheet must be shared with directly with Avrae or be publicly viewable to anyone with the link.
        Exploration bot's google account is `explorationbotproject@gmail.com`.
        Encounter table sheet template can be found at: https://docs.google.com/spreadsheets/d/1uS1bVIcje7effn8SUeOyZqCJfDpEsbUTGzpomS63Dao
        """  # noqa: E501
        url = await self._check_url(ctx, url)  # check for < >

        try:
            url = extract_gsheet_id_from_url(url)
        except ExternalImportError:
            return await ctx.send("Sheet type did not match accepted format.")
        loading = await ctx.send("Loading sheet data from Google...")
        prefix = "google"
        parser = GoogleSheet(url)

        override = await self._confirm_overwrite(ctx, f"{prefix}-{url}")
        if not override:
            return await ctx.send("Encounter sheet overwrite unconfirmed. Aborting.")

        # Load the parsed sheet
        await self._load_sheet(ctx, parser, loading)

    @staticmethod
    async def _load_sheet(ctx, parser, loading):
        try:
            encounter = await parser.load_encounter(ctx)
        except ExternalImportError as eep:
            await loading.edit(content=f"Error loading sheet: {eep}")
            return
        except Exception as eep:
            log.warning(f"Error importing sheet {parser.url}")
            log.warning(traceback.format_exc())
            await loading.edit(content=f"Error loading sheet: {eep}")
            return

        await loading.edit(content=f"Loaded and saved data for {encounter.name}!")

        await encounter.commit(ctx)
        await encounter.set_active(ctx)
        await ctx.send(embed=encounter.get_sheet_embed())
        return encounter

    @staticmethod
    async def _check_url(ctx, url):
        if url.startswith("<") and url.endswith(">"):
            url = url.strip("<>")
            await ctx.send(
                "Hey! Looks like you surrounded that URL with '<' and '>'. I removed them, but remember not to "
                "include those for other arguments!"
                f"\nUse `{ctx.prefix}help` for more details."
            )
        return url

    @staticmethod
    async def _active_encounter_embed(ctx):
        """Creates an embed to be displayed when the active encountersheet is checked"""
        active_encounter: Encounter = await ctx.get_encounter()
        embed = embeds.EmbedWithColor()

        desc = (
            f"Your current active encounter sheet is {active_encounter.name}. "
        )
        if (link := active_encounter.get_sheet_url()) is not None:
            desc = f"{desc}\n[Go to Encounter Sheet]({link})"
        embed.description = desc
        embed.set_footer(text=f"To change active encounter sheets, use {ctx.prefix}encounter <name>.")

        # for a global encounter, we can return here
        if not active_encounter.is_active_server(ctx):
            return embed

        # get the global active encounter or None
        try:
            global_encounter: Encounter = await ctx.get_encounter(ignore_guild=True)
        except NoEncounter:
            embed.set_footer(
                text=f"{active_encounter.name} is only active on {ctx.guild.name}. You have no global "
                f"active encounter sheet. To set one, use {ctx.prefix}encounter <name>."
            )
            return embed

        # global active encounter is server active
        if global_encounter.upstream == active_encounter.upstream:
            embed.set_footer(
                text=f"{active_encounter.name} is active on {ctx.guild.name} and globally. "
                f"To change active encounter sheet, use {ctx.prefix}encounter <name>."
            )
            return embed

        # global and server active differ
        embed.set_footer(
            text=f"{active_encounter.name} is active on {ctx.guild.name}, overriding your global active "
            f"encounter. To change active encounter sheet, use {ctx.prefix}encounter <name>."
        )
        return embed


def setup(bot):
    bot.add_cog(GSheetManager(bot))
