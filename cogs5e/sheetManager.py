"""
Created on Jan 19, 2017

@author: andrew
"""
import asyncio
import logging
import time
import traceback

import discord
import yaml
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType

from aliasing import helpers
from cogs5e.models import embeds
from cogs5e.models.character import Character
from cogs5e.models.errors import ExternalImportError, NoCharacter
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.sheets.beyond import BeyondSheetParser, DDB_URL_RE
from cogs5e.sheets.dicecloud import DICECLOUD_URL_RE, DicecloudParser
from cogs5e.sheets.gsheet import GoogleSheet, extract_gsheet_id_from_url
from cogs5e.utils import actionutils, checkutils, targetutils
from cogs5e.utils.help_constants import *
from ddb.gamelog import CampaignLink
from ddb.gamelog.errors import NoCampaignLink
from utils import img
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.functions import confirm, get_positivity, list_get, search_and_select, try_delete
from utils.user_settings import CSetting

log = logging.getLogger(__name__)

CHARACTER_SETTINGS = {
    "color": CSetting("color", "hex", default="random", display_func=lambda val: f"#{val:06X}", min_=0,
                      max_=0xffffff),
    "criton": CSetting("criton", "number", description="crit range", default=20,
                       display_func=lambda val: f"{val}-20", min_=1, max_=20),
    "reroll": CSetting("reroll", "number", min_=1, max_=20),
    "srslots": CSetting("srslots", "boolean", description="short rest slots", default='disabled',
                        display_func=lambda val: 'enabled' if val else 'disabled'),
    "embedimage": CSetting("embedimage", "boolean", description="embed image", default='disabled',
                           display_func=lambda val: 'enabled' if val else 'disabled'),
    "critdice": CSetting("critdice", "number", description="extra crit dice", default=0),
    "talent": CSetting("talent", "boolean", description="reliable talent", default='disabled',
                       display_func=lambda val: 'enabled' if val else 'disabled'),
    "ignorecrit": CSetting("ignorecrit", "boolean", description="ignore crits", default='disabled',
                           display_func=lambda val: 'enabled' if val else 'disabled')
}


class SheetManager(commands.Cog):
    """
    Commands to load a character sheet into Avrae, and supporting commands to modify the character, as well as basic macros.
    """  # noqa: E501

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def new_arg_stuff(args, ctx, character):
        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_character(ctx, character, args)
        args = argparse(args)
        return args

    @commands.group(aliases=['a', 'attack'], invoke_without_command=True, help=f"""
    Performs an action (attack or ability) for the current active character.
    __**Valid Arguments**__
    {VALID_AUTOMATION_ARGS}
    """)
    async def action(self, ctx, atk_name=None, *, args: str = ''):
        if atk_name is None:
            return await self.action_list(ctx)

        char: Character = await Character.from_ctx(ctx)
        args = await self.new_arg_stuff(args, ctx, char)
        hide = args.last('h', type_=bool)
        embed = embeds.EmbedWithCharacter(char, name=False, image=not hide)

        caster, targets, combat = await targetutils.maybe_combat(ctx, char, args)
        # we select from caster attacks b/c a combat effect could add some
        attack_or_action = await actionutils.select_action(ctx, atk_name, attacks=caster.attacks, actions=char.actions)

        if isinstance(attack_or_action, Attack):
            result = await actionutils.run_attack(ctx, embed, args, caster, attack_or_action, targets, combat)
        else:
            result = await actionutils.run_action(ctx, embed, args, caster, attack_or_action, targets, combat)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if (gamelog := self.bot.get_cog('GameLog')) and result is not None:
            await gamelog.send_automation(ctx, char, attack_or_action.name, result)

    @action.command(name="list")
    async def action_list(self, ctx, *args):
        """
        Lists the active character's actions.
        __Valid Arguments__
        -v - Verbose: Displays each action's character sheet description rather than the effect summary.
        attack - Only displays the available attacks.
        action - Only displays the available actions.
        bonus - Only displays the available bonus actions.
        reaction - Only displays the available reactions.
        other - Only displays the available actions that have another activation time.
        """
        char: Character = await Character.from_ctx(ctx)
        caster = await targetutils.maybe_combat_caster(ctx, char)
        embed = embeds.EmbedWithCharacter(char, name=False)
        embed.title = f"{char.name}'s Actions"

        await actionutils.send_action_list(
            ctx, caster=caster, attacks=caster.attacks, actions=char.actions, embed=embed, args=args)

    # ---- attack management commands ----
    @action.command(name="add", aliases=['create'])
    async def attack_add(self, ctx, name, *args):
        """
        Adds an attack to the active character.
        __Valid Arguments__
        -d <damage> - How much damage the attack should do.
        -b <to-hit> - The to-hit bonus of the attack.
        -desc <description> - A description of the attack.
        -verb <verb> - The verb to use for this attack. (e.g. "Padellis <verb> a dagger!")
        proper - This attack's name is a proper noun.
        -criton <#> - This attack crits on a number other than a natural 20.
        -phrase <text> - Some flavor text to add to each attack with this attack.
        -thumb <image url> - The attack's image.
        -c <extra crit damage> - How much extra damage (beyond doubling dice) this attack does on a crit.
        """
        character: Character = await Character.from_ctx(ctx)
        parsed = argparse(args)

        attack = Attack.new(name, bonus_calc=parsed.join('b', '+'),
                            damage_calc=parsed.join('d', '+'), details=parsed.join('desc', '\n'),
                            verb=parsed.last('verb'), proper=parsed.last('proper', False, bool),
                            criton=parsed.last('criton', type_=int), phrase=parsed.join('phrase', '\n'),
                            thumb=parsed.last('thumb'), extra_crit_damage=parsed.last('c'))

        conflict = next((a for a in character.overrides.attacks if a.name.lower() == attack.name.lower()), None)
        if conflict:
            if await confirm(ctx, "This will overwrite an attack with the same name. Continue? (Reply with yes/no)"):
                character.overrides.attacks.remove(conflict)
            else:
                return await ctx.send("Okay, aborting.")
        character.overrides.attacks.append(attack)
        await character.commit(ctx)

        out = f"Created attack {attack.name}!"
        if conflict:
            out += f" Removed a duplicate attack."
        await ctx.send(out)

    @action.command(name="import")
    async def attack_import(self, ctx, *, data: str):
        """
        Imports an attack from JSON or YAML exported from the Avrae Dashboard.
        """
        # strip any code blocks
        if data.startswith(('```\n', '```json\n', '```yaml\n', '```yml\n', '```py\n')) and data.endswith('```'):
            data = '\n'.join(data.split('\n')[1:]).rstrip('`\n')

        character: Character = await Character.from_ctx(ctx)

        try:
            attack_json = yaml.safe_load(data)
        except yaml.YAMLError:
            return await ctx.send("This is not a valid attack.")

        if not isinstance(attack_json, list):
            attack_json = [attack_json]

        try:
            attacks = AttackList.from_dict(attack_json)
        except Exception:
            return await ctx.send("This is not a valid attack.")

        conflicts = [a for a in character.overrides.attacks if a.name.lower() in [new.name.lower() for new in attacks]]
        if conflicts:
            if await confirm(ctx, f"This will overwrite {len(conflicts)} attacks with the same name "
                                  f"({', '.join(c.name for c in conflicts)}). Continue? (Reply with yes/no)"):
                for conflict in conflicts:
                    character.overrides.attacks.remove(conflict)
            else:
                return await ctx.send("Okay, aborting.")

        character.overrides.attacks.extend(attacks)
        await character.commit(ctx)

        out = f"Imported {len(attacks)} attacks:\n{attacks.build_str(character)}"
        await ctx.send(out)

    @action.command(name="delete", aliases=['remove'])
    async def attack_delete(self, ctx, name):
        """
        Deletes an attack override.
        """
        character: Character = await Character.from_ctx(ctx)
        attack = await search_and_select(ctx, character.overrides.attacks, name, lambda a: a.name)
        if not (await confirm(ctx, f"Are you sure you want to delete {attack.name}? (Reply with yes/no)")):
            return await ctx.send("Okay, aborting delete.")
        character.overrides.attacks.remove(attack)
        await character.commit(ctx)
        await ctx.send(f"Okay, deleted attack {attack.name}.")

    @commands.command(aliases=['s'], help=f"""
    Rolls a save for your current active character.
    {VALID_SAVE_ARGS}
    """)
    async def save(self, ctx, skill, *args):
        if skill == 'death':
            ds_cmd = self.bot.get_command('game deathsave')
            if ds_cmd is None:
                return await ctx.send("Error: GameTrack cog not loaded.")
            return await ctx.invoke(ds_cmd, *args)

        char: Character = await Character.from_ctx(ctx)

        args = await self.new_arg_stuff(args, ctx, char)

        hide = args.last('h', type_=bool)

        embed = embeds.EmbedWithCharacter(char, name=False, image=not hide)

        checkutils.update_csetting_args(char, args)
        caster = await targetutils.maybe_combat_caster(ctx, char)

        result = checkutils.run_save(skill, caster, args, embed)

        # send
        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if gamelog := self.bot.get_cog('GameLog'):
            await gamelog.send_save(ctx, char, result.skill_name, result.rolls)

    @commands.command(aliases=['c'], help=f"""
    Rolls a check for your current active character.
    {VALID_CHECK_ARGS}
    """)
    async def check(self, ctx, check, *args):
        char: Character = await Character.from_ctx(ctx)
        skill_key = await search_and_select(ctx, SKILL_NAMES, check, lambda s: s)
        args = await self.new_arg_stuff(args, ctx, char)

        hide = args.last('h', type_=bool)

        embed = embeds.EmbedWithCharacter(char, name=False, image=not hide)
        skill = char.skills[skill_key]

        checkutils.update_csetting_args(char, args, skill)
        caster = await targetutils.maybe_combat_caster(ctx, char)

        result = checkutils.run_check(skill_key, caster, args, embed)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)
        if gamelog := self.bot.get_cog('GameLog'):
            await gamelog.send_check(ctx, char, result.skill_name, result.rolls)

    @commands.group(invoke_without_command=True)
    async def desc(self, ctx):
        """Prints or edits a description of your currently active character."""
        char: Character = await Character.from_ctx(ctx)

        desc = char.description
        if not desc:
            desc = 'No description available.'

        if len(desc) > 2048:
            desc = desc[:2044] + '...'
        elif len(desc) < 2:
            desc = 'No description available.'

        embed = embeds.EmbedWithCharacter(char, name=False)
        embed.title = char.name
        embed.description = desc

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @desc.command(name='update', aliases=['edit'])
    async def edit_desc(self, ctx, *, desc):
        """Updates the character description."""
        char: Character = await Character.from_ctx(ctx)
        char.overrides.desc = desc
        await char.commit(ctx)
        await ctx.send("Description updated!")

    @desc.command(name='remove', aliases=['delete'])
    async def remove_desc(self, ctx):
        """Removes the character description, returning to the default."""
        char: Character = await Character.from_ctx(ctx)
        char.overrides.desc = None
        await char.commit(ctx)
        await ctx.send(f"Description override removed!")

    @commands.group(invoke_without_command=True)
    async def portrait(self, ctx):
        """Shows or edits the image of your currently active character."""
        char: Character = await Character.from_ctx(ctx)

        if not char.image:
            return await ctx.send("No image available.")

        embed = discord.Embed()
        embed.title = char.name
        embed.colour = char.get_color()
        embed.set_image(url=char.image)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @portrait.command(name='update', aliases=['edit'])
    async def edit_portrait(self, ctx, *, url):
        """Updates the character portrait."""
        char: Character = await Character.from_ctx(ctx)
        char.overrides.image = url
        await char.commit(ctx)
        await ctx.send("Portrait updated!")

    @portrait.command(name='remove', aliases=['delete'])
    async def remove_portrait(self, ctx):
        """Removes the character portrait, returning to the default."""
        char: Character = await Character.from_ctx(ctx)
        char.overrides.image = None
        await char.commit(ctx)
        await ctx.send(f"Portrait override removed!")

    @commands.command(hidden=True)  # hidden, as just called by token command
    async def playertoken(self, ctx, *args):
        """
        Generates and sends a token for use on VTTs.
        __Valid Arguments__
        -border <gold|plain|none> - Chooses the token border.
        """

        char: Character = await Character.from_ctx(ctx)
        if not char.image:
            return await ctx.send("This character has no image.")

        token_args = argparse(args)
        ddb_user = await self.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        is_subscriber = ddb_user and ddb_user.is_subscriber

        try:
            processed = await img.generate_token(char.image, is_subscriber, token_args)
        except Exception as e:
            return await ctx.send(f"Error generating token: {e}")

        file = discord.File(processed, filename="image.png")
        embed = embeds.EmbedWithCharacter(char, image=False)
        embed.set_image(url="attachment://image.png")
        await ctx.send(file=file, embed=embed)
        processed.close()

    @commands.command()
    async def sheet(self, ctx):
        """Prints the embed sheet of your currently active character."""
        char: Character = await Character.from_ctx(ctx)

        await ctx.send(embed=char.get_sheet_embed())
        await try_delete(ctx.message)

    @commands.group(aliases=['char'], invoke_without_command=True)
    async def character(self, ctx, *, name: str = None):
        """Switches the active character."""
        if name is None:
            embed = await self._active_character_embed(ctx)
            await ctx.send(embed=embed)
            return

        user_characters = await self.bot.mdb.characters.find({"owner": str(ctx.author.id)}).to_list(None)
        if not user_characters:
            return await ctx.send('You have no characters.')

        selected_char = await search_and_select(ctx, user_characters, name, lambda e: e['name'],
                                                selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)")

        char = Character.from_dict(selected_char)
        result = await char.set_active(ctx)
        await try_delete(ctx.message)
        if result.did_unset_server_active:
            await ctx.send(f"Active character changed to {char.name}. Your server active character has been unset.")
        else:
            await ctx.send(f"Active character changed to {char.name}.")

    @character.command(name='server')
    @commands.guild_only()
    async def character_server(self, ctx):
        """
        Sets the current global active character as a server character.
        If the character is already the server character, unsets the server character.
        
        All commands in the server that use your active character will instead use the server character, even if the active character is changed elsewhere.
        """  # noqa: E501
        char: Character = await Character.from_ctx(ctx, ignore_guild=True)

        if char.is_active_server(ctx):
            await char.unset_server_active(ctx)
            msg = f"Active server character unset from {char.name}."
            try:
                global_character = await Character.from_ctx(ctx)
            except NoCharacter:
                await ctx.send(f"{msg} You have no global active character.")
            else:
                await ctx.send(f"{msg} {global_character.name} is now active.")
        else:
            result = await char.set_server_active(ctx)
            if result.did_unset_server_active:
                await ctx.send(f"Active server character changed to {char.name}.")
            else:
                await ctx.send(f"Active server character set to {char.name}.")

        await try_delete(ctx.message)

    @character.command(name='list')
    async def character_list(self, ctx):
        """Lists your characters."""
        user_characters = await self.bot.mdb.characters.find(
            {"owner": str(ctx.author.id)}, ['name']
        ).to_list(None)
        if not user_characters:
            return await ctx.send('You have no characters.')
        await ctx.send('Your characters:\n{}'.format(', '.join(sorted(c['name'] for c in user_characters))))

    @character.command(name='delete')
    async def character_delete(self, ctx, *, name):
        """Deletes a character."""
        user_characters = await self.bot.mdb.characters.find(
            {"owner": str(ctx.author.id)}, ['name', 'upstream']
        ).to_list(None)
        if not user_characters:
            return await ctx.send('You have no characters.')

        selected_char = await search_and_select(ctx, user_characters, name, lambda e: e['name'],
                                                selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)")

        if await confirm(ctx, f"Are you sure you want to delete {selected_char['name']}? (Reply with yes/no)"):
            await Character.delete(ctx, str(ctx.author.id), selected_char['upstream'])
            return await ctx.send(f"{selected_char['name']} has been deleted.")
        else:
            return await ctx.send("Ok, cancelling.")

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def update(self, ctx, *args):
        """
        Updates the current character sheet, preserving all settings.
        __Valid Arguments__
        `-v` - Shows character sheet after update is complete.
        `-nocc` - Do not automatically create or update custom counters for class resources and features.
        `-noprep` - Import all known spells as prepared.
        """
        old_character: Character = await Character.from_ctx(ctx)
        url = old_character.upstream
        args = argparse(args)

        prefixes = 'dicecloud-', 'google-', 'beyond-'
        _id = url[:]
        for p in prefixes:
            if url.startswith(p):
                _id = url[len(p):]
                break
        sheet_type = old_character.sheet_type
        if sheet_type == 'dicecloud':
            parser = DicecloudParser(_id)
            loading = await ctx.send('Updating character data from Dicecloud...')
        elif sheet_type == 'google':
            parser = GoogleSheet(_id)
            loading = await ctx.send('Updating character data from Google...')
        elif sheet_type == 'beyond':
            parser = BeyondSheetParser(_id)
            loading = await ctx.send('Updating character data from Beyond...')
        else:
            return await ctx.send(f"Error: Unknown sheet type {sheet_type}.")

        try:
            character = await parser.load_character(ctx, args)
        except ExternalImportError as eep:
            return await loading.edit(content=f"Error loading character: {eep}")
        except Exception as eep:
            log.warning(f"Error importing character {old_character.upstream}")
            log.warning(traceback.format_exc())
            return await loading.edit(content=f"Error loading character: {eep}")

        character.update(old_character)
        
        # keeps an old check if the old character was active on the current server
        was_server_active = old_character.is_active_server(ctx)
        
        await character.commit(ctx)
        
        # overwrites the old_character's server active state
        # since character._active_guilds is old_character._active_guilds here
        if old_character.is_active_global():
            await character.set_active(ctx)
        if was_server_active:
            await character.set_server_active(ctx)
        
        await loading.edit(content=f"Updated and saved data for {character.name}!")
        if args.last('v'):
            await ctx.send(embed=character.get_sheet_embed())
        if sheet_type == 'beyond':
            await send_ddb_ctas(ctx, character)

    @commands.command()
    async def transferchar(self, ctx, user: discord.Member):
        """Gives a copy of the active character to another user."""
        character: Character = await Character.from_ctx(ctx)
        overwrite = ''

        conflict = await self.bot.mdb.characters.find_one({"owner": str(user.id), "upstream": character.upstream})
        if conflict:
            overwrite = "**WARNING**: This will overwrite an existing character."

        await ctx.send(f"{user.mention}, accept a copy of {character.name}? (Type yes/no)\n{overwrite}",
                       allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        try:
            m = await self.bot.wait_for('message', timeout=300,
                                        check=lambda msg: (msg.author == user
                                                           and msg.channel == ctx.channel
                                                           and get_positivity(msg.content) is not None))
        except asyncio.TimeoutError:
            m = None

        if m is None or not get_positivity(m.content):
            return await ctx.send("Transfer not confirmed, aborting.")

        character.owner = str(user.id)
        await character.commit(ctx)
        await ctx.send(f"Copied {character.name} to {user.display_name}'s storage.")

    @commands.command()
    async def csettings(self, ctx, *args):
        """Updates personalization settings for the currently active character.

        __**Valid Arguments**__
        Use `<setting> reset` to reset a setting to the default.

        `color <hex color>` - Colors all character-based built-in embeds this color. Accessible as the cvar `color`
        `criton <number>` - Makes attacks crit on something other than a 20.
        `reroll <number>` - Defines a number that a check will automatically reroll on, for cases such as Halfling Luck.
        `srslots true/false` - Enables/disables whether spell slots reset on a Short Rest.
        `embedimage true/false` - Enables/disables whether a character's image is automatically embedded.
        `critdice <number>` - Adds additional damage dice on a critical hit. 
        `talent true/false` - Enables/disables whether to apply a rogue's Reliable Talent on checks you're proficient with.
        `ignorecrit true/false` - Prevents critical hits from applying, for example with adamantine armor."""  # noqa: E501
        char = await Character.from_ctx(ctx)

        out = []
        skip = False
        for i, arg in enumerate(args):
            if skip:
                continue
            if arg in CHARACTER_SETTINGS:
                skip = True
                out.append(CHARACTER_SETTINGS[arg].run(ctx, char, list_get(i + 1, None, args)))

        if not out:
            return await ctx.send(f"No valid settings found. See `{ctx.prefix}help {ctx.invoked_with}` for a list "
                                  f"of valid settings.")

        await char.commit(ctx)
        await ctx.send('\n'.join(out))

    async def _confirm_overwrite(self, ctx, _id):
        """Prompts the user if command would overwrite another character.
        Returns True to overwrite, False or None otherwise."""
        conflict = await self.bot.mdb.characters.find_one({"owner": str(ctx.author.id), "upstream": _id})
        if conflict:
            return await confirm(
                ctx,
                f"Warning: This will overwrite a character with the same ID. Do you wish to continue "
                f"(Reply with yes/no)?\n"
                f"If you only wanted to update your character, run `{ctx.prefix}update` instead.")
        return True

    @commands.command(name='import')
    @commands.max_concurrency(1, BucketType.user)
    async def import_sheet(self, ctx, url: str, *args):
        """
        Loads a character sheet from one of the accepted sites:
            [D&D Beyond](https://www.dndbeyond.com/)
            [Dicecloud](https://dicecloud.com/)
            [GSheet v2.1](https://gsheet2.avrae.io) (auto)
            [GSheet v1.4](https://gsheet.avrae.io) (manual)
        
        __Valid Arguments__
        `-nocc` - Do not automatically create custom counters for class resources and features.
        `-noprep` - Import all known spells as prepared.

        __Sheet-specific Notes__
        D&D Beyond:
            Private sheets can be imported if you have linked your DDB and Discord accounts.  Otherwise, the sheet needs to be publicly shared.
            
        Dicecloud:
            Share your character with `avrae` on Dicecloud (edit permissions) for live updates.
        
        Gsheet:
            The sheet must be shared with directly with Avrae or be publicly viewable to anyone with the link.
            Avrae's google account is `avrae-320@avrae-bot.iam.gserviceaccount.com`.


        """  # noqa: E501
        url = await self._check_url(ctx, url)  # check for < >
        # Sheets in order: DDB, Dicecloud, Gsheet
        if beyond_match := DDB_URL_RE.match(url):
            loading = await ctx.send('Loading character data from Beyond...')
            prefix = 'beyond'
            url = beyond_match.group(1)
            parser = BeyondSheetParser(url)
        elif dicecloud_match := DICECLOUD_URL_RE.match(url):
            loading = await ctx.send('Loading character data from Dicecloud...')
            url = dicecloud_match.group(1)
            prefix = 'dicecloud'
            parser = DicecloudParser(url)
        else:
            try:
                url = extract_gsheet_id_from_url(url)
            except ExternalImportError:
                return await ctx.send("Sheet type did not match accepted formats.")
            loading = await ctx.send('Loading character data from Google...')
            prefix = 'google'
            parser = GoogleSheet(url)

        override = await self._confirm_overwrite(ctx, f"{prefix}-{url}")
        if not override:
            return await ctx.send("Character overwrite unconfirmed. Aborting.")

        # Load the parsed sheet
        character = await self._load_sheet(ctx, parser, args, loading)
        if character and beyond_match:
            await send_ddb_ctas(ctx, character)

    @commands.command(hidden=True, aliases=['gsheet', 'dicecloud'])
    @commands.max_concurrency(1, BucketType.user)
    async def beyond(self, ctx, url: str, *args):
        """
        This is an old command and has been replaced. Use `!import` instead!
        """
        await self.import_sheet(ctx, url, *args)

    @staticmethod
    async def _load_sheet(ctx, parser, args, loading):
        try:
            character = await parser.load_character(ctx, argparse(args))
        except ExternalImportError as eep:
            await loading.edit(content=f"Error loading character: {eep}")
            return
        except Exception as eep:
            log.warning(f"Error importing character {parser.url}")
            log.warning(traceback.format_exc())
            await loading.edit(content=f"Error loading character: {eep}")
            return

        await loading.edit(content=f'Loaded and saved data for {character.name}!')

        await character.commit(ctx)
        await character.set_active(ctx)
        await ctx.send(embed=character.get_sheet_embed())
        return character

    @staticmethod
    async def _check_url(ctx, url):
        if url.startswith('<') and url.endswith('>'):
            url = url.strip('<>')
            await ctx.send(
                "Hey! Looks like you surrounded that URL with '<' and '>'. I removed them, but remember not to "
                "include those for other arguments!"
                f"\nUse `{ctx.prefix}help` for more details.")
        return url

    @staticmethod
    async def _active_character_embed(ctx):
        """Creates an embed to be displayed when the active character is checked"""
        active_character: Character = await ctx.get_character()
        embed = embeds.EmbedWithCharacter(active_character)

        desc = (f"Your current active character is {active_character.name}. "
                f"All of your checks, saves and actions will use this character's stats.")
        if (link := active_character.get_sheet_url()) is not None:
            desc = f"{desc}\n[Go to Character Sheet]({link})"
        embed.description = desc
        embed.set_footer(text=f"To change active characters, use {ctx.prefix}character <name>.")

        # for a global character, we can return here
        if not active_character.is_active_server(ctx):
            return embed

        # get the global active character or None
        try:
            global_character: Character = await ctx.get_character(ignore_guild=True)
        except NoCharacter:
            embed.set_footer(text=f"{active_character.name} is only active on {ctx.guild.name}. You have no global "
                                  f"active character. To set one, use {ctx.prefix}character <name>.")
            return embed

        # global active character is server active
        if global_character.upstream == active_character.upstream:
            embed.set_footer(text=f"{active_character.name} is active on {ctx.guild.name} and globally. "
                                  f"To change active characters, use {ctx.prefix}character <name>.")
            return embed

        # global and server active differ
        embed.set_footer(text=f"{active_character.name} is active on {ctx.guild.name}, overriding your global active "
                              f"character. To change active characters, use {ctx.prefix}character <name>.")
        return embed


async def send_ddb_ctas(ctx, character):
    """Sends relevant CTAs after a DDB character is imported. Only show a CTA 1/24h to not spam people."""
    ddb_user = await ctx.bot.ddb.get_ddb_user(ctx, ctx.author.id)
    if ddb_user is not None:
        ld_dict = ddb_user.to_ld_dict()
    else:
        ld_dict = {"key": str(ctx.author.id), "anonymous": True}
    gamelog_flag = await ctx.bot.ldclient.variation('cog.gamelog.cta.enabled', ld_dict, False)

    # has the user seen this cta within the last 7d?
    if await ctx.bot.rdb.get(f"cog.sheetmanager.cta.seen.{ctx.author.id}"):
        return

    embed = embeds.EmbedWithCharacter(character)
    embed.title = "Heads up!"
    embed.description = "There's a couple of things you can do to make your experience even better!"
    embed.set_footer(text="You won't see this message again this week.")

    # link ddb user
    if ddb_user is None:
        embed.add_field(
            name="Connect Your D&D Beyond Account",
            value="Visit your [Account Settings](https://www.dndbeyond.com/account) page in D&D Beyond to link your "
                  "D&D Beyond and Discord accounts. This lets you use all your D&D Beyond content in Avrae for free!",
            inline=False
        )
    # game log
    if character.ddb_campaign_id and gamelog_flag:
        try:
            await CampaignLink.from_id(ctx.bot.mdb, character.ddb_campaign_id)
        except NoCampaignLink:
            embed.add_field(
                name="Link Your D&D Beyond Campaign",
                value=f"Sync rolls between a Discord channel and your D&D Beyond character sheet by linking your "
                      f"campaign! Use `{ctx.prefix}campaign https://www.dndbeyond.com/campaigns/"
                      f"{character.ddb_campaign_id}` in the Discord channel you want to link it to.",
                inline=False
            )

    if not embed.fields:
        return
    await ctx.send(embed=embed)
    await ctx.bot.rdb.setex(f"cog.sheetmanager.cta.seen.{ctx.author.id}", str(time.time()), 60 * 60 * 24 * 7)


def setup(bot):
    bot.add_cog(SheetManager(bot))
