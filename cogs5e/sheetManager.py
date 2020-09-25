"""
Created on Jan 19, 2017

@author: andrew
"""
import asyncio
import json
import logging
import traceback

import discord
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType

from aliasing import helpers
from cogs5e.funcs import attackutils, checkutils, targetutils
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithCharacter
from cogs5e.models.errors import ExternalImportError
from cogs5e.models.sheet.attack import Attack, AttackList
from cogs5e.sheets.beyond import BeyondSheetParser, DDB_URL_RE
from cogs5e.sheets.dicecloud import DicecloudParser
from cogs5e.sheets.gsheet import GoogleSheet, extract_gsheet_id_from_url
from utils import img
from utils.argparser import argparse
from utils.constants import SKILL_NAMES
from utils.functions import auth_and_chan, confirm, get_positivity, list_get, search_and_select, try_delete
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
                       display_func=lambda val: 'enabled' if val else 'disabled')
}


class SheetManager(commands.Cog):
    """
    Commands to load a character sheet into Avrae, and supporting commands to modify the character, as well as basic macros.
    """

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def new_arg_stuff(args, ctx, character):
        args = await helpers.parse_snippets(args, ctx)
        args = await helpers.parse_with_character(ctx, character, args)
        args = argparse(args)
        return args

    @commands.group(aliases=['a'], invoke_without_command=True)
    async def attack(self, ctx, atk_name=None, *, args: str = ''):
        """Rolls an attack for the current active character.
        __Valid Arguments__
        -t "<target>" - Sets targets for the attack. You can pass as many as needed. Will target combatants if channel is in initiative.
        -t "<target>|<args>" - Sets a target, and also allows for specific args to apply to them. (e.g, -t "OR1|hit" to force the attack against OR1 to hit)

        *adv/dis* - Advantage or Disadvantage
        *ea* - Elven Accuracy double advantage
        
        -ac <target ac> - overrides target AC
        *-b* <to hit bonus> - adds a bonus to hit
        -criton <num> - a number to crit on if rolled on or above
        *-d* <damage bonus> - adds a bonus to damage
        *-c* <damage bonus on crit> - adds a bonus to crit damage
        -rr <times> - number of times to roll the attack against each target
        *-mi <value>* - minimum value of each die on the damage roll
        
        *-resist* <damage resistance>
        *-immune* <damage immunity>
        *-vuln* <damage vulnerability>
        *-neutral* <damage type> - ignores this damage type in resistance calculations
        *-dtype <damage type>* - replaces all damage types with this damage type
        *-dtype <old>new>* - replaces all of one damage type with another (e.g. `-dtype fire>cold`)
        
        *hit* - automatically hits
        *miss* - automatically misses
        *crit* - automatically crits if hit
        *max* - deals max damage
        *magical* - makes the damage type magical

        -h - hides name and rolled values
        -phrase <text> - adds flavour text
        -title <title> - changes the result title *note: `[name]` and `[aname]` will be replaced automatically*
        -thumb <url> - adds flavour image
        -f "Field Title|Field Text" - see `!help embed`
        <user snippet> - see `!help snippet`

        An italicized argument means the argument supports ephemeral arguments - e.g. `-d1` applies damage to the first hit, `-b1` applies a bonus to one attack, and so on.
        """
        if atk_name is None:
            return await self.attack_list(ctx)

        char: Character = await Character.from_ctx(ctx)
        args = await self.new_arg_stuff(args, ctx, char)

        caster, targets, combat = await targetutils.maybe_combat(ctx, char, args)
        attack = await search_and_select(ctx, caster.attacks, atk_name, lambda a: a.name)

        embed = EmbedWithCharacter(char, name=False)
        await attackutils.run_attack(ctx, embed, args, caster, attack, targets, combat)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @attack.command(name="list")
    async def attack_list(self, ctx):
        """Lists the active character's attacks."""
        char: Character = await Character.from_ctx(ctx)
        atk_str = char.attacks.build_str(char)
        if len(atk_str) > 1000:
            atk_str = f"{atk_str[:1000]}\n[...]"
        return await ctx.send(f"{char.name}'s attacks:\n{atk_str}")

    @attack.command(name="add", aliases=['create'])
    async def attack_add(self, ctx, name, *args):
        """
        Adds an attack to the active character.
        __Arguments__
        -d [damage]: How much damage the attack should do.
        -b [to-hit]: The to-hit bonus of the attack.
        -desc [description]: A description of the attack.
        """
        character: Character = await Character.from_ctx(ctx)
        parsed = argparse(args)

        attack = Attack.new(name, bonus_calc=parsed.join('b', '+'),
                            damage_calc=parsed.join('d', '+'), details=parsed.join('desc', '\n'))

        conflict = next((a for a in character.overrides.attacks if a.name.lower() == attack.name.lower()), None)
        if conflict:
            if await confirm(ctx, "This will overwrite an attack with the same name. Continue?"):
                character.overrides.attacks.remove(conflict)
            else:
                return await ctx.send("Okay, aborting.")
        character.overrides.attacks.append(attack)
        await character.commit(ctx)

        out = f"Created attack {attack.name}!"
        if conflict:
            out += f" Removed a duplicate attack."
        await ctx.send(out)

    @attack.command(name="import")
    async def attack_import(self, ctx, *, data):
        """
        Imports an attack from JSON exported from the Avrae Dashboard.
        """
        character: Character = await Character.from_ctx(ctx)

        try:
            attack_json = json.loads(data)
        except json.decoder.JSONDecodeError:
            return await ctx.send("This is not a valid attack.")

        if not isinstance(attack_json, list):
            attack_json = [attack_json]

        try:
            attacks = AttackList.from_dict(attack_json)
        except:
            return await ctx.send("This is not a valid attack.")

        conflicts = [a for a in character.overrides.attacks if a.name.lower() in [new.name.lower() for new in attacks]]
        if conflicts:
            if await confirm(ctx, f"This will overwrite {len(conflicts)} attacks with the same name "
                                  f"({', '.join(c.name for c in conflicts)}). Continue?"):
                for conflict in conflicts:
                    character.overrides.attacks.remove(conflict)
            else:
                return await ctx.send("Okay, aborting.")

        character.overrides.attacks.extend(attacks)
        await character.commit(ctx)

        out = f"Imported {len(attacks)} attacks:\n{attacks.build_str(character)}"
        await ctx.send(out)

    @attack.command(name="delete", aliases=['remove'])
    async def attack_delete(self, ctx, name):
        """
        Deletes an attack override.
        """
        character: Character = await Character.from_ctx(ctx)
        attack = await search_and_select(ctx, character.overrides.attacks, name, lambda a: a.name)
        if not (await confirm(ctx, f"Are you sure you want to delete {attack.name}?")):
            return await ctx.send("Okay, aborting delete.")
        character.overrides.attacks.remove(attack)
        await character.commit(ctx)
        await ctx.send(f"Okay, deleted attack {attack.name}.")

    @commands.command(aliases=['s'])
    async def save(self, ctx, skill, *args):
        """Rolls a save for your current active character.
        __Valid Arguments__
        *adv/dis*
        *-b [conditional bonus]*
        -dc [dc] (does not apply to Death Saves)
        -rr [iterations] (does not apply to Death Saves)

        -phrase [flavor text]
        -title [title] *note: [name] and [sname] will be replaced automatically*
        -thumb [thumbnail URL]
        -f "Field Title|Field Text" - see `!help embed`

        An italicized argument means the argument supports ephemeral arguments - e.g. `-b1` applies a bonus to one save.
        """
        if skill == 'death':
            ds_cmd = self.bot.get_command('game deathsave')
            if ds_cmd is None:
                return await ctx.send("Error: GameTrack cog not loaded.")
            return await ctx.invoke(ds_cmd, *args)

        char: Character = await Character.from_ctx(ctx)

        embed = EmbedWithCharacter(char, name=False)

        args = await self.new_arg_stuff(args, ctx, char)
        checkutils.update_csetting_args(char, args)

        caster, _, _ = await targetutils.maybe_combat(ctx, char, args)

        checkutils.run_save(skill, caster, args, embed)

        # send
        await ctx.send(embed=embed)
        await try_delete(ctx.message)

    @commands.command(aliases=['c'])
    async def check(self, ctx, check, *args):
        """Rolls a check for your current active character.
        __Valid Arguments__
        *adv/dis*
        *-b [conditional bonus]*
        -dc [dc]
        -mc [minimum roll]
        -rr [iterations]
        str/dex/con/int/wis/cha (different skill base; e.g. Strength (Intimidation))

        -phrase [flavor text]
        -title [title] *note: [name] and [cname] will be replaced automatically*
        -thumb [thumbnail URL]
        -f "Field Title|Field Text" - see `!help embed`

        An italicized argument means the argument supports ephemeral arguments - e.g. `-b1` applies a bonus to one check.
        """
        char: Character = await Character.from_ctx(ctx)
        skill_key = await search_and_select(ctx, SKILL_NAMES, check, lambda s: s)

        embed = EmbedWithCharacter(char, False)
        skill = char.skills[skill_key]

        args = await self.new_arg_stuff(args, ctx, char)

        checkutils.update_csetting_args(char, args, skill)
        checkutils.run_check(skill_key, char, args, embed)

        await ctx.send(embed=embed)
        await try_delete(ctx.message)

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

        embed = EmbedWithCharacter(char, name=False)
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
        embed = EmbedWithCharacter(char, image=False)
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
        user_characters = await self.bot.mdb.characters.find({"owner": str(ctx.author.id)}).to_list(None)
        if not user_characters:
            return await ctx.send('You have no characters.')

        if name is None:
            active_character: Character = await Character.from_ctx(ctx)
            return await ctx.send(f'Currently active: {active_character.name}')

        selected_char = await search_and_select(ctx, user_characters, name, lambda e: e['name'],
                                                selectkey=lambda e: f"{e['name']} (`{e['upstream']}`)")

        char = Character.from_dict(selected_char)
        await char.set_active(ctx)

        await try_delete(ctx.message)

        await ctx.send(f"Active character changed to {char.name}.", delete_after=20)

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

        await ctx.send(f"Are you sure you want to delete {selected_char['name']}? (Reply with yes/no)")
        try:
            reply = await self.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
        except asyncio.TimeoutError:
            reply = None
        reply = get_positivity(reply.content) if reply is not None else None
        if reply is None:
            return await ctx.send('Timed out waiting for a response or invalid response.')
        elif reply:
            await Character.delete(ctx, str(ctx.author.id), selected_char['upstream'])
            return await ctx.send(f"{selected_char['name']} has been deleted.")
        else:
            return await ctx.send("OK, cancelling.")

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def update(self, ctx, *args):
        """Updates the current character sheet, preserving all settings.
        __Valid Arguments__
        `-v` - Shows character sheet after update is complete.
        `-nocc` - Do not automatically create or update custom counters for class resources and features."""
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

        await character.commit(ctx)
        await character.set_active(ctx)
        await loading.edit(content=f"Updated and saved data for {character.name}!")
        if args.last('v'):
            await ctx.send(embed=character.get_sheet_embed())

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
                                        check=lambda msg: msg.author == user
                                                          and msg.channel == ctx.channel
                                                          and get_positivity(msg.content) is not None)
        except asyncio.TimeoutError:
            m = None

        if m is None or not get_positivity(m.content): return await ctx.send("Transfer not confirmed, aborting.")

        character.owner = str(user.id)
        await character.commit(ctx)
        await ctx.send(f"Copied {character.name} to {user.display_name}'s storage.")

    @commands.command()
    async def csettings(self, ctx, *args):
        """Updates personalization settings for the currently active character.
        Valid Arguments:
        `color <hex color>` - Colors all embeds this color.
        `criton <number>` - Makes attacks crit on something other than a 20.
        `reroll <number>` - Defines a number that a check will automatically reroll on, for cases such as Halfling Luck.
        `srslots true/false` - Enables/disables whether spell slots reset on a Short Rest.
        `embedimage true/false` - Enables/disables whether a character's image is automatically embedded.
        `critdice <number>` - Adds additional dice for to critical attacks.
        `talent true/false` - Enables/disables whether to apply a rogue's Reliable Talent on checks you're proficient with."""
        char = await Character.from_ctx(ctx)

        out = ['Operations complete!']
        skip = False
        for i, arg in enumerate(args):
            if skip:
                continue
            if arg in CHARACTER_SETTINGS:
                skip = True
                out.append(CHARACTER_SETTINGS[arg].run(ctx, char, list_get(i + 1, None, args)))

        await char.commit(ctx)
        await ctx.send('\n'.join(out))

    async def _confirm_overwrite(self, ctx, _id):
        """Prompts the user if command would overwrite another character.
        Returns True to overwrite, False or None otherwise."""
        conflict = await self.bot.mdb.characters.find_one({"owner": str(ctx.author.id), "upstream": _id})
        if conflict:
            await ctx.channel.send(
                "Warning: This will overwrite a character with the same ID. Do you wish to continue (reply yes/no)?\n"
                f"If you only wanted to update your character, run `{ctx.prefix}update` instead.")
            try:
                reply = await self.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
            except asyncio.TimeoutError:
                reply = None
            replyBool = get_positivity(reply.content) if reply is not None else None
            return replyBool
        return True

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def dicecloud(self, ctx, url: str, *args):
        """
        Loads a character sheet from [Dicecloud](https://dicecloud.com/), resetting all settings.
        Share your character with `avrae` on Dicecloud (edit perms) for live updates.
        __Valid Arguments__
        `-nocc` - Do not automatically create custom counters for class resources and features.
        """
        if 'dicecloud.com' in url:
            url = url.split('/character/')[-1].split('/')[0]

        override = await self._confirm_overwrite(ctx, f"dicecloud-{url}")
        if not override: return await ctx.send("Character overwrite unconfirmed. Aborting.")

        loading = await ctx.send('Loading character data from Dicecloud...')
        parser = DicecloudParser(url)
        await self._load_sheet(ctx, parser, args, loading)

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def gsheet(self, ctx, url: str, *args):
        """Loads a character sheet from [GSheet v2.1](http://gsheet2.avrae.io) (auto) or [GSheet v1.4](http://gsheet.avrae.io) (manual), resetting all settings.
        The sheet must be shared with Avrae for this to work.
        Avrae's google account is `avrae-320@avrae-bot.iam.gserviceaccount.com`."""

        loading = await ctx.send('Loading character data from Google... (This usually takes ~30 sec)')
        try:
            url = extract_gsheet_id_from_url(url)
        except ExternalImportError:
            return await loading.edit(content="This is not a Google Sheets link.")

        override = await self._confirm_overwrite(ctx, f"google-{url}")
        if not override: return await ctx.send("Character overwrite unconfirmed. Aborting.")

        parser = GoogleSheet(url)
        await self._load_sheet(ctx, parser, args, loading)

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def beyond(self, ctx, url: str, *args):
        """
        Loads a character sheet from [D&D Beyond](https://www.dndbeyond.com/), resetting all settings.
        __Valid Arguments__
        `-nocc` - Do not automatically create custom counters for limited use features.
        """

        loading = await ctx.send('Loading character data from Beyond...')
        url = DDB_URL_RE.match(url)
        if url is None:
            return await loading.edit(content="This is not a D&D Beyond link.")
        url = url.group(1)

        override = await self._confirm_overwrite(ctx, f"beyond-{url}")
        if not override: return await ctx.send("Character overwrite unconfirmed. Aborting.")

        parser = BeyondSheetParser(url)
        await self._load_sheet(ctx, parser, args, loading)

    @staticmethod
    async def _load_sheet(ctx, parser, args, loading):
        try:
            character = await parser.load_character(ctx, argparse(args))
        except ExternalImportError as eep:
            return await loading.edit(content=f"Error loading character: {eep}")
        except Exception as eep:
            log.warning(f"Error importing character {parser.url}")
            log.warning(traceback.format_exc())
            return await loading.edit(content=f"Error loading character: {eep}")

        await loading.edit(content=f'Loaded and saved data for {character.name}!')

        await character.commit(ctx)
        await character.set_active(ctx)
        await ctx.send(embed=character.get_sheet_embed())


def setup(bot):
    bot.add_cog(SheetManager(bot))
