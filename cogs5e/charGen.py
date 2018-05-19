import logging
import random

from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import c, searchClass, searchBackground
from cogs5e.models.dicecloudClient import DicecloudClient, Parent
from cogs5e.models.embeds import EmbedWithAuthor
from utils.functions import parse_data_entry, ABILITY_MAP, get_selection, fuzzywuzzy_search_all_3, search_and_select

log = logging.getLogger(__name__)

SKILL_MAP = {'Acrobatics': 'acrobatics', 'Animal Handling': 'animalHandling', 'Arcana': 'arcana',
             'Athletics': 'athletics', 'Deception': 'deception', 'History': 'history', 'Initiaitve': 'initiative',
             'Insight': 'insight', 'Intimidation': 'intimidation', 'Investigation': 'investigation',
             'Medicine': 'medicine', 'Nature': 'nature', 'Perception': 'perception', 'Performance': 'performance',
             'Persuasion': 'persuasion', 'Religion': 'religion', 'Sleight of Hand': 'sleightOfHand',
             'Stealth': 'stealth', 'Survival': 'survival'}

CLASS_RESOURCE_NAMES = {"Ki Points": "ki", "Rage Damage": "rageDamage", "Rages": "rages",
                        "Sorcery Points": "sorceryPoints", "Superiority Dice": "superiorityDice",
                        "1st": "level1SpellSlots", "2nd": "level2SpellSlots", "3rd": "level3SpellSlots",
                        "4th": "level4SpellSlots", "5th": "level5SpellSlots", "6th": "level6SpellSlots",
                        "7th": "level7SpellSlots", "8th": "level8SpellSlots", "9th": "level9SpellSlots"}


class CharGenerator:
    """Random character generator."""

    def __init__(self, bot):
        self.bot = bot

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

    @commands.command(name="randname")
    async def randname(self):
        """Generates a random name, as per DMG rules."""
        await self.bot.say(f"Your random name: {self.nameGen()}")

    @commands.command(pass_context=True, name='charref', aliases=['makechar'])
    async def char(self, ctx, level):
        """Gives you reference stats for a 5e character."""
        try:
            level = int(level)
        except:
            await self.bot.say("Invalid level.")
            return
        if level > 20 or level < 1:
            await self.bot.say("Invalid level (must be 1-20).")
            return

        author = ctx.message.author
        channel = ctx.message.channel

        await self.bot.say(author.mention + " What race?")
        race_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if race_response is None: return await self.bot.say("Race not found.")
        race = await search_and_select(ctx, c.fancyraces, race_response.content, lambda e: e.name)

        await self.bot.say(author.mention + " What class?")
        class_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if class_response is None: return await self.bot.say("Class not found.")
        result = searchClass(class_response.content)
        if result is None: return await self.bot.say("Class not found.")
        _class = await resolve(result, ctx)

        if 'subclasses' in _class:
            await self.bot.say(author.mention + " What subclass?")
            subclass_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
            if subclass_response is None: return await self.bot.say("Subclass not found.")
            result = fuzzywuzzy_search_all_3(_class['subclasses'], 'name', subclass_response.content)
            subclass = await resolve(result, ctx)
        else:
            subclass = None

        await self.bot.say(author.mention + " What background?")
        bg_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if bg_response is None: return await self.bot.say("Background not found.")
        result = searchBackground(bg_response.content)
        background = await resolve(result, ctx)

        await self.genChar(ctx, level, race, _class, subclass, background)

    async def genChar(self, ctx, final_level, race=None, _class=None, subclass=None, background=None):
        loadingMessage = await self.bot.send_message(ctx.message.channel, "Generating character, please wait...")
        color = random.randint(0, 0xffffff)

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
        race = race or random.choice([r for r in c.fancyraces if r.source in ('PHB', 'VGM', 'MTF')])

        embed = EmbedWithAuthor(ctx)
        embed.title = race.name
        embed.description = f"Source: {race.source}"
        embed.add_field(name="Speed", value=race.get_speed_str())
        embed.add_field(name="Size", value=race.size)
        embed.add_field(name="Ability Bonuses", value=race.get_asi_str())
        for t in race.get_traits():
            f_text = t['text']
            f_text = [f_text[i:i + 1024] for i in range(0, len(f_text), 1024)]
            embed.add_field(name=t['name'], value=f_text[0])
            for piece in f_text[1:]:
                embed.add_field(name="** **", value=piece)

        embed.colour = color
        await self.bot.send_message(ctx.message.author, embed=embed)

        # Class Gen
        #    Class Features
        _class = _class or random.choice([cl for cl in c.classes if not 'UA' in cl.get('source')])
        subclass = subclass or random.choice([s for s in _class['subclasses'] if not 'UA' in s['source']])
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

        for level in range(1, final_level + 1):
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

        embed.colour = color
        await self.bot.send_message(ctx.message.author, embed=embed)

        embed = EmbedWithAuthor(ctx)
        level_resources = {}
        for table in _class['classTableGroups']:
            relevant_row = table['rows'][final_level - 1]
            for i, col in enumerate(relevant_row):
                level_resources[table['colLabels'][i]] = parse_data_entry([col])

        for res_name, res_value in level_resources.items():
            embed.add_field(name=res_name, value=res_value)

        embed.colour = color
        await self.bot.send_message(ctx.message.author, embed=embed)

        embed_queue = [EmbedWithAuthor(ctx)]
        num_subclass_features = 0
        num_fields = 0

        def inc_fields(text):
            nonlocal num_fields
            num_fields += 1
            if num_fields > 25:
                embed_queue.append(EmbedWithAuthor(ctx))
                num_fields = 0
            if len(str(embed_queue[-1].to_dict())) + len(text) > 5800:
                embed_queue.append(EmbedWithAuthor(ctx))
                num_fields = 0

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
                    embed_queue[-1].add_field(name="\u200b", value=piece)
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
                        embed_queue[-1].add_field(name="\u200b", value=piece)

        for embed in embed_queue:
            embed.colour = color
            await self.bot.send_message(ctx.message.author, embed=embed)

        # Background Gen
        #    Inventory/Trait Gen
        background = background or random.choice(c.backgrounds)
        embed = EmbedWithAuthor(ctx)
        embed.title = background['name']
        embed.description = f"*Source: {background.get('source', 'Unknown')}*"

        ignored_fields = ['suggested characteristics', 'specialty',
                          'harrowing event']
        for trait in background['trait']:
            if trait['name'].lower() in ignored_fields: continue
            text = '\n'.join(t for t in trait['text'] if t)
            text = [text[i:i + 1024] for i in range(0, len(text), 1024)]
            embed.add_field(name=trait['name'], value=text[0])
            for piece in text[1:]:
                embed.add_field(name="\u200b", value=piece)
        embed.colour = color
        await self.bot.send_message(ctx.message.author, embed=embed)

        out = "{6}\n{0}, {1} {7} {2} {3}. {4} Background.\nStat Array: `{5}`\nI have PM'd you full character details.".format(
            name, race.name, _class['name'], final_level, background['name'], stats, ctx.message.author.mention,
            subclass['name'])

        await self.bot.edit_message(loadingMessage, out)

    @commands.command(pass_context=True)
    async def autochar(self, ctx, level):
        """Automagically creates a dicecloud sheet for you, with basic character information complete."""
        try:
            level = int(level)
        except:
            await self.bot.say("Invalid level.")
            return
        if level > 20 or level < 1:
            await self.bot.say("Invalid level (must be 1-20).")
            return

        author = ctx.message.author
        channel = ctx.message.channel

        await self.bot.say(author.mention + " What race?")
        race_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if race_response is None: return await self.bot.say("Race not found.")
        race = await search_and_select(ctx, c.fancyraces, race_response.content, lambda e: e.name)

        await self.bot.say(author.mention + " What class?")
        class_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if class_response is None: return await self.bot.say("Class not found.")
        result = searchClass(class_response.content)
        if result is None: return await self.bot.say("Class not found.")
        _class = await resolve(result, ctx)

        if 'subclasses' in _class:
            await self.bot.say(author.mention + " What subclass?")
            subclass_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
            if subclass_response is None: return await self.bot.say("Subclass not found.")
            result = fuzzywuzzy_search_all_3(_class['subclasses'], 'name', subclass_response.content)
            subclass = await resolve(result, ctx)
        else:
            subclass = None

        await self.bot.say(author.mention + " What background?")
        bg_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if bg_response is None: return await self.bot.say("Background not found.")
        result = searchBackground(bg_response.content)
        background = await resolve(result, ctx)

        await self.bot.say(author.mention + " What is your dicecloud username?")
        user_response = await self.bot.wait_for_message(timeout=60, author=author, channel=channel)
        if user_response is None: return await self.bot.say("Timed out waiting for a response.")
        username = user_response.content

        await self.createCharSheet(ctx, level, username, race, _class, subclass, background)

    async def createCharSheet(self, ctx, final_level, dicecloud_username, race=None, _class=None, subclass=None,
                              background=None):
        dc = DicecloudClient.getInstance()
        caveats = []  # a to do list for the user

        # Name Gen + Setup
        #    DMG name gen
        name = self.nameGen()
        race = race or random.choice([r for r in c.fancyraces if r['source'] in ('PHB', 'VGM', 'MTF')])
        _class = _class or random.choice([cl for cl in c.classes if not 'UA' in cl.get('source')])
        subclass = subclass or random.choice([s for s in _class['subclasses'] if not 'UA' in s['source']])
        background = background or random.choice(c.backgrounds)

        char_id = dc.create_character(name=name, race=race.name, backstory=background['name'])
        try:
            await dc.share_character(char_id, dicecloud_username)
        except:
            dc.delete_character(char_id)  # clean up
            return await self.bot.say("Invalid dicecloud username.")

        loadingMessage = await self.bot.send_message(ctx.message.channel, "Generating character, please wait...")

        # Stat Gen
        # Allow user to enter base values
        caveats.append("**Base Ability Scores**: Enter your base ability scores (without modifiers) in the feature "
                       "titled Base Ability Scores.")

        # Race Gen
        #    Racial Features
        speed = race.speed if isinstance(race.speed, int) else race.speed.get('walk', '30')
        dc.insert_effect(char_id, Parent.race(char_id), 'base', value=int(speed), stat='speed')

        for k, v in race.ability.items():
            if not k == 'choose':
                dc.insert_effect(char_id, Parent.race(char_id), 'add', value=int(v), stat=ABILITY_MAP[k].lower())
            else:
                dc.insert_effect(char_id, Parent.race(char_id), 'add', value=int(v[0].get('amount', 1)))
                caveats.append(
                    f"**Racial Ability Bonus ({int(v[0].get('amount', 1)):+})**: In your race (Journal tab), select the"
                    f" score you want a bonus to (choose {v[0]['count']} from {', '.join(v[0]['from'])}).")

        for t in race.get_traits():
            dc.insert_feature(char_id, t['name'], t['text'])
        caveats.append("**Racial Features**: Check that the number of uses for each feature is correct, and apply "
                       "any effects they grant.")

        # Class Gen
        #    Class Features
        class_id = dc.insert_class(char_id, final_level, _class['name'])
        dc.insert_effect(char_id, Parent.class_(class_id), 'add', stat=f"d{_class['hd']['faces']}HitDice",
                         calculation=f"{_class['name']}Level")
        hpPerLevel = (int(_class['hd']['faces']) / 2) + 1
        firstLevelHp = int(_class['hd']['faces']) - hpPerLevel
        dc.insert_effect(char_id, Parent.class_(class_id), 'add', stat='hitPoints',
                         calculation=f"{hpPerLevel}*{_class['name']}Level+{firstLevelHp}")
        caveats.append("**HP**: HP is currently calculated using class average; change the value in the Journal tab "
                       "under your class if you wish to change it.")

        for saveProf in _class['proficiency']:
            profKey = ABILITY_MAP.get(saveProf).lower() + 'Save'
            dc.insert_proficiency(char_id, Parent.class_(class_id), profKey, type_='save')
        for prof in _class['startingProficiencies'].get('armor', []):
            dc.insert_proficiency(char_id, Parent.class_(class_id), prof, type_='armor')
        for prof in _class['startingProficiencies'].get('weapons', []):
            dc.insert_proficiency(char_id, Parent.class_(class_id), prof, type_='weapon')
        for prof in _class['startingProficiencies'].get('tools', []):
            dc.insert_proficiency(char_id, Parent.class_(class_id), prof, type_='tool')
        for _ in range(int(_class['startingProficiencies']['skills']['choose'])):
            dc.insert_proficiency(char_id, Parent.class_(class_id), type_='skill')  # add placeholders
        caveats.append(f"**Skill Proficiencies**: You get to choose your skill proficiencies. Under your class "
                       f"in the Journal tab, you may select {_class['startingProficiencies']['skills']['choose']} "
                       f"skills from {', '.join(_class['startingProficiencies']['skills']['from'])}.")

        equip_choices = '\n'.join(f"• {i}" for i in _class['startingEquipment']['default'])
        gold_alt = f"Alternatively, you may start with {_class['startingEquipment']['goldAlternative']} gp " \
                   f"to buy your own equipment." if 'goldAlternative' in _class['startingEquipment'] else ''
        starting_items = f"You start with the following items, plus anything provided by your background.\n" \
                         f"{equip_choices}\n" \
                         f"{gold_alt}"
        caveats.append(f"**Starting Class Equipment**: {starting_items}")

        level_resources = {}
        for table in _class['classTableGroups']:
            relevant_row = table['rows'][final_level - 1]
            for i, col in enumerate(relevant_row):
                level_resources[table['colLabels'][i]] = parse_data_entry([col])

        for res_name, res_value in level_resources.items():
            stat_name = CLASS_RESOURCE_NAMES.get(res_name)
            if stat_name:
                dc.insert_effect(char_id, Parent.class_(class_id), 'base', value=int(res_value), stat=stat_name)

        num_subclass_features = 0
        for level in range(1, final_level + 1):
            level_features = _class['classFeatures'][level - 1]
            for f in level_features:
                if f.get('gainSubclassFeature'):
                    num_subclass_features += 1
                text = parse_data_entry(f['entries'], True)
                dc.insert_feature(char_id, f['name'], text)
        for num in range(num_subclass_features):
            level_features = subclass['subclassFeatures'][num]
            for feature in level_features:
                for entry in feature.get('entries', []):
                    if not isinstance(entry, dict): continue
                    if not entry.get('type') == 'entries': continue
                    fe = {'name': entry['name'],
                          'text': parse_data_entry(entry['entries'], True)}
                    dc.insert_feature(char_id, fe['name'], fe['text'])
        caveats.append("**Class Features**: Check that the number of uses for each feature is correct, and apply "
                       "any effects they grant.")
        caveats.append("**Spellcasting**: If your class can cast spells, be sure to set your number of known spells, "
                       "max prepared, DC, attack bonus, and what spells you know in the Spells tab. You can add a "
                       "spell to your spellbook by connecting the character to Avrae and running `!sb add <SPELL>`.")

        # Background Gen
        #    Inventory/Trait Gen
        for trait in background['trait']:
            text = '\n'.join(t for t in trait['text'] if t)
            if 'proficiency' in trait['name'].lower():
                for skill in text.split(', '):
                    if skill in SKILL_MAP:
                        dc.insert_proficiency(char_id, Parent.background(char_id), SKILL_MAP.get(skill))
                    else:
                        dc.insert_proficiency(char_id, Parent.background(char_id), skill, type_='tool')
            elif 'language' in trait['name'].lower():
                for lang in text.split(', '):
                    dc.insert_proficiency(char_id, Parent.background(char_id), lang, type_='language')
                caveats.append("**Languages**: Some backgrounds' languages may ask you to choose one or more. Fill "
                               "this out in the Persona tab.")
            elif trait['name'].lower().startswith('feature'):
                tname = trait['name'][9:]
                dc.insert_feature(char_id, tname, text)
            elif trait['name'].lower().startswith('equipment'):
                caveats.append(f"**Background Equipment**: Your background grants you {text}")

        out = f"Generated {name}! I have PMed you the link."
        await self.bot.send_message(ctx.message.author, f"https://dicecloud.com/character/{char_id}/{name}")
        await self.bot.send_message(ctx.message.author,
                                    "**__Caveats__**\nNot everything is automagical! Here are some things you still "
                                    "have to do manually:\n" + '\n\n'.join(caveats))
        await self.bot.send_message(ctx.message.author,
                                    f"When you're ready, load your character into Avrae with the command "
                                    f"`!dicecloud https://dicecloud.com/character/{char_id}/{name} -cc`")
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


async def resolve(result, ctx):
    if result is None:
        return None
    strict = result[1]
    results = result[0]

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            result = await get_selection(ctx, [(r['name'], r) for r in results])
    return result
