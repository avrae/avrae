import asyncio
import logging
import random

from discord.ext import commands

from cogs5e.funcs.dice import roll
from cogs5e.funcs.lookupFuncs import c, searchRace, searchClass, searchBackground
from cogs5e.models.embeds import EmbedWithAuthor
from utils.functions import parse_data_entry, ABILITY_MAP, get_selection, fuzzywuzzy_search_all_3

log = logging.getLogger(__name__)


class CharGenerator:
    """Random character generator."""

    def __init__(self, bot):
        self.bot = bot
        self.makingChar = set()

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

        await self.bot.say(author.mention + " What race?")
        race_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if race_response is None: return await self.bot.say("Race not found.")
        result = searchRace(race_response.content)
        race = await resolve(result, ctx)

        await self.bot.say(author.mention + " What class?")
        class_response = await self.bot.wait_for_message(timeout=90, author=author, channel=channel)
        if class_response is None: return await self.bot.say("Class not found.")
        result = searchClass(class_response.content)
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

        try:
            self.makingChar.remove(author)
        except (ValueError, KeyError):
            pass

        await self.genChar(ctx, level, race, _class, subclass, background)

    async def _time_making(self, author):
        try:
            await asyncio.sleep(180)
            try:
                self.makingChar.remove(author)
            except (ValueError, KeyError):
                pass
        except asyncio.CancelledError:
            pass

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
        race = race or random.choice([r for r in c.races if r['source'] in ('PHB', 'VGM')])

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
                embed.add_field(name="\u200b", value=piece)

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
            name, race['name'], _class['name'], final_level, background['name'], stats, ctx.message.author.mention,
            subclass['name'])

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
