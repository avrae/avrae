import asyncio
import logging
import random
from string import capwords

from MeteorClient import MeteorClient
from discord.ext import commands

import credentials
from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import c
from cogs5e.models.embeds import EmbedWithAuthor
from utils.functions import parse_data_entry, ABILITY_MAP

DICECLOUD_USERNAME = 'avrae'
DICECLOUD_PASSWORD = credentials.dicecloud_pass.encode()

log = logging.getLogger(__name__)


class CharGenerator:
    """Random character generator."""

    def __init__(self, bot):
        self.bot = bot
        self.makingChar = set()
        self.dicecloud_client = MeteorClient('ws://dicecloud.com/websocket', debug=self.bot.testing)
        self.dicecloud_client.initialized = False
        self.bot.loop.create_task(self.auth_dicecloud())

    async def auth_dicecloud(self):
        self.dicecloud_client.connect()
        log.info("Connecting to dicecloud")
        while not self.dicecloud_client.connected:
            await asyncio.sleep(0.1)
        self.dicecloud_client.login(DICECLOUD_USERNAME, DICECLOUD_PASSWORD)
        log.info("Logged in to dicecloud")

        await asyncio.sleep(1)  # wait until users collection has updated

        USER_ID = self.dicecloud_client.find_one('users', selector={'username': DICECLOUD_USERNAME}).get('_id')
        log.info("User ID: " + USER_ID)
        self.dicecloud_client.initialized = True
        self.dicecloud_client.user_id = USER_ID

    @commands.command(pass_context=True, name='randchar')
    async def randChar(self, ctx, level="0"):
        """Makes a random 5e character."""
        try:
            level = int(level)
        except:
            await self.bot.say("Invalid level.")
            return

        if level == 0:
            stats = '\n'.join(roll("4d6kh3", inline=True).skeleton for _ in range(6))
            await self.bot.say(f"{ctx.message.author.mention}\nGenerated random stats:\n{stats}")
            return

        if level > 20 or level < 1:
            await self.bot.say("Invalid level (must be 1-20).")
            return

        await self.genChar(ctx, level)

    @commands.command(pass_context=True, name="randname")
    async def randname(self, ctx):
        """Generates a random name, as per DMG rules."""
        await self.bot.say(f"Your random name: {self.nameGen()}")

    @commands.command(pass_context=True, name='makechar')
    async def char(self, ctx, level):
        """Gives you stats for a 5e character."""
        try:
            level = int(level)
        except:
            await self.bot.say("Invalid level.")
            return
        if level > 20 or level < 1:
            await self.bot.say("Invalid level (must be 1-20).")
            return
        if ctx.message.author not in self.makingChar:
            self.makingChar.add(ctx.message.author)
            self.bot.loop.create_task(self._time_making(ctx.message.author))
        else:
            await self.bot.say("You are already making a character!")
            return
        author = ctx.message.author
        channel = ctx.message.channel
        await self.bot.say(author.mention + " What race? (Include the subrace before the race; e.g. \"Wood Elf\")")

        def raceCheck(msg):
            return msg.content.lower() in ["hill dwarf", "mountain dwarf",
                                           "high elf", "wood elf", "drow",
                                           "lightfoot halfling", "stout halfling",
                                           "human", "dragonborn",
                                           "forest gnome", "rock gnome",
                                           "half-elf", "half-orc", "tiefling"]

        race = await self.bot.wait_for_message(timeout=90, author=author, channel=channel, check=raceCheck)
        if race:
            def classCheck(msg):
                return capwords(msg.content) in ["Totem Warrior Barbarian", "Berserker Barbarian",
                                                 "Lore Bard", "Valor Bard",
                                                 "Knowledge Cleric", "Life Cleric", "Light Cleric", "Nature Cleric",
                                                 "Tempest Cleric", "Trickery Cleric", "War Cleric",
                                                 "Land Druid", "Moon Druid",
                                                 "Champion Fighter", "Battle Master Fighter", "Eldritch Knight Fighter",
                                                 "Open Hand Monk", "Shadow Monk", "Four Elements Monk",
                                                 "Devotion Paladin", "Ancients Paladin", "Vengeance Paladin",
                                                 "Hunter Ranger", "Beast Master Ranger",
                                                 "Thief Rogue", "Assassin Rogue", "Arcane Trickster Rogue",
                                                 "Wild Magic Sorcerer", "Draconic Sorcerer",
                                                 "Archfey Warlock", "Fiend Warlock", "Great Old One Warlock",
                                                 "Abjuration Wizard", "Conjuration Wizard", "Divination Wizard",
                                                 "Enchantment Wizard", "Evocation Wizard", "Illusion Wizard",
                                                 "Necromancy Wizard", "Transmutation Wizard"]

            await self.bot.say(
                author.mention + " What class? (Include the archetype before the class; e.g. \"Life Cleric\")")
            classVar = await self.bot.wait_for_message(timeout=90, author=author, channel=channel, check=classCheck)
            if classVar:
                def backgroundCheck(msg):
                    return capwords(msg.content) in ["Acolyte", "Charlatan", "Criminal", "Entertainer", "Folk Hero",
                                                     "Guild Artisan", "Hermit", "Noble", "Outlander", "Sage", "Sailor",
                                                     "Soldier", "Urchin"]

                await self.bot.say(author.mention + " What background?")
                background = await self.bot.wait_for_message(timeout=90, author=author, channel=channel,
                                                             check=backgroundCheck)
                if background:
                    loading = await self.bot.say("Generating character, please wait...")
                    name = self.nameGen()
                    # Stat Gen
                    stats = self.genStats()
                    await self.bot.send_message(ctx.message.author, "**Stats for {0}:** `{1}`".format(name, stats))
                    # Race Gen
                    raceTraits = self.getRaceTraits(race.content, level)
                    raceTraitStr = ''
                    for t in raceTraits:
                        raceTraitStr += "\n\n**{trait}**: {desc}".format(**t)
                    raceTraitStr = "**Racial Traits ({0}):** {1}".format(capwords(race.content), raceTraitStr)
                    result = self.discord_trim(raceTraitStr)
                    for r in result:
                        await self.bot.send_message(ctx.message.author, r)
                    # Class Gen
                    classTraits = self.getClassTraits(classVar.content, level)
                    classTraitStr = ''
                    for t in classTraits:
                        classTraitStr += "\n\n**{0}**: {1}".format(t['trait'], t['desc'].replace('<br>', '\n'))
                    classTraitStr = "**Class Traits ({0}):** {1}".format(capwords(classVar.content), classTraitStr)
                    result = self.discord_trim(classTraitStr)
                    for r in result:
                        await self.bot.send_message(ctx.message.author, r)
                    # background Gen
                    backgroundTraits = self.getBackgroundTraits(background.content)
                    backgroundTraitStr = ''
                    for t in backgroundTraits:
                        backgroundTraitStr += "\n**{0}**: {1}".format(t['trait'], t['desc'].replace('<br>', '\n'))
                    backgroundTraitStr = "**Background Traits ({0}):** {1}".format(capwords(background.content),
                                                                                   backgroundTraitStr)
                    result = self.discord_trim(backgroundTraitStr)
                    for r in result:
                        await self.bot.send_message(ctx.message.author, r)

                    await self.bot.edit_message(loading,
                                                author.mention + " I have PM'd you stats for {0}, a level {1} {2} {3} with the {4} background.\nStat Block: `{5}`".format(
                                                    name, level, race.content, classVar.content, background.content,
                                                    stats))
                else:
                    await self.bot.say(
                        author.mention + " No background found. Make sure you are using a background from the 5e PHB.")
            else:
                await self.bot.say(
                    author.mention + " No class found. Make sure you are using a class from the 5e PHB, and include the archetype, even at low levels.")
        else:
            await self.bot.say(
                author.mention + " No race found. Make sure you are using a race from the 5e PHB, and use \"Drow\" instead of Dark Elf.")

        try:
            self.makingChar.remove(author)
        except (ValueError, KeyError):
            pass

    async def _time_making(self, author):
        try:
            await asyncio.sleep(180)
            try:
                self.makingChar.remove(author)
            except (ValueError, KeyError):
                pass
        except asyncio.CancelledError:
            pass

    async def genChar(self, ctx, final_level):
        loadingMessage = await self.bot.send_message(ctx.message.channel, "Generating character, please wait...")

        features = []
        race_attrs = {}
        class_attrs = {}
        gen_attrs = {}

        # Name Gen
        #    DMG name gen
        name = self.nameGen()
        # Stat Gen
        #    4d6d1
        #        reroll if too low/high
        stats = self.genStats()
        await self.bot.send_message(ctx.message.author, "**Stats for {0}:** `{1}`".format(name, stats))
        # Race Gen
        #    Racial Features
        race = random.choice([r for r in c.races if r['source'] in ('PHB', 'VGM')])

        _sizes = {'T': "Tiny", 'S': "Small",
                  'M': "Medium", 'L': "Large", 'H': "Huge"}
        embed = EmbedWithAuthor(ctx)
        embed.title = race['name']
        embed.description = f"Source: {race.get('source', 'unknown')}"
        embed.add_field(name="Speed",
                        value=race['speed'] + ' ft.' if isinstance(race['speed'], str) else \
                            ', '.join(f"{k} {v} ft." for k, v in race['speed'].items()))
        embed.add_field(name="Size", value=_sizes.get(race.get('size'), 'unknown'))

        ability = []
        for k, v in race['ability'].items():
            if not k == 'choose':
                ability.append(f"{k} {v}")
            else:
                ability.append(f"Choose {v[0]['count']} from {', '.join(v[0]['from'])} {v[0].get('amount', 1)}")

        embed.add_field(name="Ability Bonuses", value=', '.join(ability))
        if race.get('proficiency'):
            embed.add_field(name="Proficiencies", value=race.get('proficiency', 'none'))

        traits = []
        if 'trait' in race:
            one_rfeats = race.get('trait', [])
            for rfeat in one_rfeats:
                temp = {'name': rfeat['name'],
                        'text': parse_data_entry(rfeat['text'])}
                traits.append(temp)
        else:  # assume entries
            for entry in race['entries']:
                temp = {'name': entry['name'],
                        'text': parse_data_entry(entry['entries'])}
                traits.append(temp)

        for t in traits:
            f_text = t['text']
            f_text = [f_text[i:i + 1024] for i in range(0, len(f_text), 1024)]
            embed.add_field(name=t['name'], value=f_text[0])
            for piece in f_text[1:]:
                embed.add_field(name="con't", value=piece)

        await self.bot.send_message(ctx.message.author, embed=embed)

        # Class Gen
        #    Class Features
        _class = random.choice([cl for cl in c.classes if not 'UA' in cl.get('source')])
        subclass = random.choice([s for s in _class['subclasses'] if not 'UA' in s['source']])
        embed = EmbedWithAuthor(ctx)
        embed.title = f"{_class['name']} ({subclass['name']})"
        embed.add_field(name="Hit Die", value=f"1d{_class['hd']['faces']}")
        embed.add_field(name="Saving Throws", value=', '.join(ABILITY_MAP.get(p) for p in _class['proficiency']))

        levels = []
        starting_profs = f"You are proficient with the following items, " \
                         f"in addition to any proficiencies provided by your race or background.\n" \
                         f"Armor: {', '.join(_class['startingProficiencies'].get('armor', ['None']))}\n" \
                         f"Weapons: {', '.join(_class['startingProficiencies'].get('weapons', ['None']))}\n" \
                         f"Tools: {', '.join(_class['startingProficiencies'].get('tools', ['None']))}\n" \
                         f"Skills: Choose {_class['startingProficiencies']['skills']['choose']} from " \
                         f"{', '.join(_class['startingProficiencies']['skills']['from'])}"

        equip_choices = '\n'.join(f"• {i}" for i in _class['startingEquipment']['default'])
        gold_alt = f"Alternatively, you may start with {_class['startingEquipment']['goldAlternative']} gp " \
                   f"to buy your own equipment." if 'goldAlternative' in _class['startingEquipment'] else ''
        starting_items = f"You start with the following items, plus anything provided by your background.\n" \
                         f"{equip_choices}\n" \
                         f"{gold_alt}"

        for level in range(1, 21):
            level_str = []
            level_features = _class['classFeatures'][level - 1]
            for feature in level_features:
                level_str.append(feature.get('name'))
            levels.append(', '.join(level_str))

        embed.add_field(name="Starting Proficiencies", value=starting_profs)
        embed.add_field(name="Starting Equipment", value=starting_items)

        level_features_str = ""
        for i, l in enumerate(levels):
            level_features_str += f"`{i+1}` {l}\n"
        embed.description = level_features_str

        await self.bot.send_message(ctx.message.author, embed=embed)

        embed = EmbedWithAuthor(ctx)
        level_resources = {}
        for table in _class['classTableGroups']:
            relevant_row = table['rows'][final_level - 1]
            for i, col in enumerate(relevant_row):
                level_resources[table['colLabels'][i]] = parse_data_entry([col])

        for res_name, res_value in level_resources.items():
            embed.add_field(name=res_name, value=res_value)
        await self.bot.send_message(ctx.message.author, embed=embed)

        embed_queue = [EmbedWithAuthor(ctx)]
        num_subclass_features = 0
        num_fields = 0
        char_count = 0
        def inc_fields(text):
            nonlocal num_fields
            nonlocal char_count
            num_fields += 1
            char_count += len(text)
            if num_fields > 25:
                embed_queue.append(EmbedWithAuthor(ctx))
                num_fields = 0
                char_count = 0
            if char_count > 5800:
                embed_queue.append(EmbedWithAuthor(ctx))
                num_fields = 0
                char_count = 0
        for level in range(1, final_level + 1):
            level_features = _class['classFeatures'][level - 1]
            for f in level_features:
                if f.get('gainSubclassFeature'):
                    num_subclass_features += 1
                text = parse_data_entry(f['entries'])
                text = [text[i:i + 1024] for i in range(0, len(text), 1024)]
                inc_fields(text[0])
                embed_queue[-1].add_field(name=f['name'], value=text[0])
                for piece in text[1:]:
                    inc_fields(piece)
                    embed_queue[-1].add_field(name="con't", value=piece)
        for num in range(num_subclass_features):
            level_features = subclass['subclassFeatures'][num]
            for feature in level_features:
                for entry in feature.get('entries', []):
                    if not isinstance(entry, dict): continue
                    if not entry.get('type') == 'entries': continue
                    fe = {'name': entry['name'],
                          'text': parse_data_entry(entry['entries'])}
                    text = [fe['text'][i:i + 1024] for i in range(0, len(fe['text']), 1024)]
                    inc_fields(text[0])
                    embed_queue[-1].add_field(name=fe['name'], value=text[0])
                    for piece in text[1:]:
                        inc_fields(piece)
                        embed_queue[-1].add_field(name="con't", value=piece)

        for embed in embed_queue:
            await self.bot.send_message(ctx.message.author, embed=embed)

        # Background Gen
        #    Inventory/Trait Gen
        background = self.backgroundGen(ctx)
        backgroundTraits = background[1]
        background = background[0]
        backgroundTraitStr = ''
        for t in backgroundTraits:
            backgroundTraitStr += "\n**{0}**: {1}".format(t['trait'], t['desc'].replace('<br>', '\n'))
        backgroundTraitStr = "**Background Traits ({0}):** {1}".format(background, backgroundTraitStr)
        result = self.discord_trim(backgroundTraitStr)
        for r in result:
            await self.bot.send_message(ctx.message.author, r)

        out = "{6}\n{0}, {1} {2} {3}. {4} Background.\nStat Array: `{5}`\nI have PM'd you full character details.".format(
            name, race, classVar, level, background, stats, ctx.message.author.mention)

        await self.bot.edit_message(loadingMessage, out)

    def nameGen(self):
        name = ""
        beginnings = ["", "", "", "", "A", "Be", "De", "El", "Fa", "Jo", "Ki", "La", "Ma", "Na", "O", "Pa", "Re", "Si",
                      "Ta", "Va"]
        middles = ["bar", "ched", "dell", "far", "gran", "hal", "jen", "kel", "lim", "mor", "net", "penn", "quill",
                   "rond", "sark", "shen", "tur", "vash", "yor", "zen"]
        ends = ["", "a", "ac", "ai", "al", "am", "an", "ar", "ea", "el", "er", "ess", "ett", "ic", "id", "il", "is",
                "in", "or", "us"]
        name += random.choice(beginnings) + random.choice(middles) + random.choice(ends)
        name = name.capitalize()
        return name

    def genStats(self):
        stats = [roll('4d6kh3').total for i in range(6)]
        return stats
