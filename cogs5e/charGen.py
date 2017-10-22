import asyncio
import json
import random
from string import capwords

from discord.ext import commands

from cogs5e.funcs.dice import roll


class CharGenerator:
    """Random character generator."""
    
    def __init__(self, bot):
        self.bot = bot
        self.makingChar = set()
        with open('./res/raceTraits.json', 'r') as t:
            self.raceTraits = json.load(t)
        with open('./res/classTraits.json', 'r') as t:
            self.classTraits = json.load(t)
        with open('./res/backgroundTraits.json', 'r') as t:
            self.bgTraits = json.load(t)
    
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
                   "Knowledge Cleric", "Life Cleric", "Light Cleric", "Nature Cleric", "Tempest Cleric", "Trickery Cleric", "War Cleric",
                   "Land Druid", "Moon Druid",
                   "Champion Fighter", "Battle Master Fighter", "Eldritch Knight Fighter",
                   "Open Hand Monk", "Shadow Monk", "Four Elements Monk",
                   "Devotion Paladin", "Ancients Paladin", "Vengeance Paladin",
                   "Hunter Ranger", "Beast Master Ranger",
                   "Thief Rogue", "Assassin Rogue", "Arcane Trickster Rogue",
                   "Wild Magic Sorcerer", "Draconic Sorcerer",
                   "Archfey Warlock", "Fiend Warlock", "Great Old One Warlock",
                   "Abjuration Wizard", "Conjuration Wizard", "Divination Wizard", "Enchantment Wizard", "Evocation Wizard", "Illusion Wizard", "Necromancy Wizard", "Transmutation Wizard"]

            await self.bot.say(author.mention + " What class? (Include the archetype before the class; e.g. \"Life Cleric\")")
            classVar = await self.bot.wait_for_message(timeout=90, author=author, channel=channel, check=classCheck)
            if classVar:
                def backgroundCheck(msg):
                    return capwords(msg.content) in ["Acolyte", "Charlatan", "Criminal", "Entertainer", "Folk Hero", "Guild Artisan", "Hermit", "Noble", "Outlander", "Sage", "Sailor", "Soldier", "Urchin"]
                await self.bot.say(author.mention + " What background?")
                background = await self.bot.wait_for_message(timeout=90, author=author, channel=channel, check=backgroundCheck)
                if background:    
                    loading = await self.bot.say("Generating character, please wait...")
                    name = self.nameGen()
                    #Stat Gen
                    stats = self.genStats()
                    await self.bot.send_message(ctx.message.author, "**Stats for {0}:** `{1}`".format(name, stats))
                    #Race Gen
                    raceTraits = self.getRaceTraits(race.content, level)
                    raceTraitStr = ''
                    for t in raceTraits:
                        raceTraitStr += "\n\n**{trait}**: {desc}".format(**t)
                    raceTraitStr = "**Racial Traits ({0}):** {1}".format(capwords(race.content), raceTraitStr)
                    result = self.discord_trim(raceTraitStr) 
                    for r in result:
                        await self.bot.send_message(ctx.message.author, r)
                    #Class Gen
                    classTraits = self.getClassTraits(classVar.content, level)
                    classTraitStr = ''
                    for t in classTraits:
                        classTraitStr += "\n\n**{0}**: {1}".format(t['trait'], t['desc'].replace('<br>', '\n'))
                    classTraitStr = "**Class Traits ({0}):** {1}".format(capwords(classVar.content), classTraitStr)
                    result = self.discord_trim(classTraitStr) 
                    for r in result:
                        await self.bot.send_message(ctx.message.author, r)
                    #background Gen
                    backgroundTraits = self.getBackgroundTraits(background.content)
                    backgroundTraitStr = ''
                    for t in backgroundTraits:
                        backgroundTraitStr += "\n**{0}**: {1}".format(t['trait'], t['desc'].replace('<br>', '\n'))
                    backgroundTraitStr = "**Background Traits ({0}):** {1}".format(capwords(background.content), backgroundTraitStr)
                    result = self.discord_trim(backgroundTraitStr) 
                    for r in result:
                        await self.bot.send_message(ctx.message.author, r)
                        
                    await self.bot.edit_message(loading, author.mention + " I have PM'd you stats for {0}, a level {1} {2} {3} with the {4} background.\nStat Block: `{5}`".format(name, level, race.content, classVar.content, background.content, stats))
                else:
                    await self.bot.say(author.mention + " No background found. Make sure you are using a background from the 5e PHB.")
            else:
                await self.bot.say(author.mention + " No class found. Make sure you are using a class from the 5e PHB, and include the archetype, even at low levels.")
        else:
            await self.bot.say(author.mention + " No race found. Make sure you are using a race from the 5e PHB, and use \"Drow\" instead of Dark Elf.")

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
    
    async def genChar(self, ctx, level):
        loadingMessage = await self.bot.send_message(ctx.message.channel, "Generating character, please wait...")
        
        #Name Gen
        #    DMG name gen
        name = self.nameGen()
        #Stat Gen
        #    4d6d1
        #        reroll if too low/high
        stats = self.genStats()
        await self.bot.send_message(ctx.message.author, "**Stats for {0}:** `{1}`".format(name, stats))
        #Race Gen
        #    Racial Features
        race = self.raceGen(ctx, level)
        raceTraits = race[1]
        race = race[0]
        raceTraitStr = ''
        for t in raceTraits:
            raceTraitStr += "\n\n**{trait}**: {desc}".format(**t)
        raceTraitStr = "**Racial Traits ({0}):** {1}".format(race, raceTraitStr)
        result = self.discord_trim(raceTraitStr) 
        for r in result:
            await self.bot.send_message(ctx.message.author, r)
        #Class Gen
        #    Class Features
        classVar = self.classGen(ctx, level)
        classTraits = classVar[1]
        classVar = classVar[0]
        classTraitStr = ''
        for t in classTraits:
            classTraitStr += "\n\n**{0}**: {1}".format(t['trait'], t['desc'].replace('<br>', '\n'))
        classTraitStr = "**Class Traits ({0}):** {1}".format(classVar, classTraitStr)
        result = self.discord_trim(classTraitStr) 
        for r in result:
            await self.bot.send_message(ctx.message.author, r)
        #Background Gen
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
        
        out = "{6}\n{0}, {1} {2} {3}. {4} Background.\nStat Array: `{5}`\nI have PM'd you full character details.".format(name, race, classVar, level, background, stats, ctx.message.author.mention)
        
        await self.bot.edit_message(loadingMessage, out)
    
    def nameGen(self):
        name = ""
        beginnings = ["", "", "", "", "A", "Be", "De", "El", "Fa", "Jo", "Ki", "La", "Ma", "Na", "O", "Pa", "Re", "Si", "Ta", "Va"]
        middles = ["bar", "ched", "dell", "far", "gran", "hal", "jen", "kel", "lim", "mor", "net", "penn", "quill", "rond", "sark", "shen", "tur", "vash", "yor", "zen"]
        ends = ["", "a", "ac", "ai", "al", "am", "an", "ar", "ea", "el", "er", "ess", "ett", "ic", "id", "il", "is", "in", "or", "us"]
        name += random.choice(beginnings) + random.choice(middles) + random.choice(ends)
        name = name.capitalize()
        return name
    
    def raceGen(self, ctx, level):
        races = ["Hill Dwarf", "Mountain Dwarf",
                 "High Elf", "Wood Elf", "Drow",
                 "Lightfoot Halfling", "Stout Halfling",
                 "Human", "Human", "Dragonborn",
                 "Forest Gnome", "Rock Gnome",
                 "Half-Elf", "Half-Orc", "Tiefling"]
        race = random.choice(races)
        raceTraitsArray = self.getRaceTraits(race, level)
        return [race, raceTraitsArray]
    
    def classGen(self, ctx, level):
        classes = [["Totem Warrior Barbarian", "Berserker Barbarian"],
                   ["Lore Bard", "Valor Bard"],
                   ["Knowledge Cleric", "Life Cleric", "Light Cleric", "Nature Cleric", "Tempest Cleric", "Trickery Cleric", "War Cleric"],
                   ["Land Druid", "Moon Druid"],
                   ["Champion Fighter", "Battle Master Fighter", "Eldritch Knight Fighter"],
                   ["Open Hand Monk", "Shadow Monk", "Four Elements Monk"],
                   ["Devotion Paladin", "Ancients Paladin", "Vengeance Paladin"],
                   ["Hunter Ranger", "Beast Master Ranger"],
                   ["Thief Rogue", "Assassin Rogue", "Arcane Trickster Rogue"],
                   ["Wild Magic Sorcerer", "Draconic Sorcerer"],
                   ["Archfey Warlock", "Fiend Warlock", "Great Old One Warlock"],
                   ["Abjuration Wizard", "Conjuration Wizard", "Divination Wizard", "Enchantment Wizard", "Evocation Wizard", "Illusion Wizard", "Necromancy Wizard", "Transmutation Wizard"]]
        
        classVar = random.randint(0, 11)
        classVar = random.choice(classes[classVar])
        
        classTraitsArray = self.getClassTraits(classVar, level)
        return [classVar, classTraitsArray]
    
    def backgroundGen(self, ctx):
        backgrounds = ["Acolyte", "Charlatan", "Criminal", "Entertainer", "Folk Hero", "Guild Artisan", "Hermit", "Noble", "Outlander", "Sage", "Sailor", "Soldier", "Urchin"]
        background = random.choice(backgrounds)
        backgroundTraitsArray = self.getBackgroundTraits(background)
        return [background, backgroundTraitsArray]
    
    def statGen(self):
        a = random.randint(1,6)
        b = random.randint(1,6)
        c = random.randint(1,6)
        d = random.randint(1,6)
        lowest = min(a, b, c, d)
        return a + b + c + d - lowest
    
    def genStats(self):
        stats = [roll('4d6kh3').total for i in range(6)]
        return stats
    
    def getRaceTraits(self, race, level):
        traits = [t for t in self.raceTraits if t["race"].upper()==race.upper() and t["level"]<=level]
#         print(traits)
        return traits
    
    def getClassTraits(self, classVar, level):
        traits = [t for t in self.classTraits if t["class"].upper()==classVar.upper() and t["level"]<=level]
        return traits
    
    def getBackgroundTraits(self, background):
        rawTraits = next(t for t in self.bgTraits if t["background"].upper()==background.upper())
        persTrait1 = ""
        persTrait2 = ""
        while persTrait1 == persTrait2:
            persTrait1 = random.choice(rawTraits["traits"])
            persTrait2 = random.choice(rawTraits["traits"])
        ideal = random.choice(rawTraits["ideals"])
        bond = random.choice(rawTraits["bonds"])
        flaw = random.choice(rawTraits["flaws"])
        traits = [
                      {"trait": "Proficiencies",
                       "desc": rawTraits["proficiencies"]},
                      {"trait": "Languages",
                       "desc": rawTraits["languages"]},
                      {"trait": "Equipment",
                       "desc": rawTraits["equipment"]},
                      {"trait": "Feature",
                       "desc": rawTraits["feature"]},
                      {"trait": "Personality Trait 1",
                       "desc": persTrait1},
                      {"trait": "Personality Trait 2",
                       "desc": persTrait2},
                      {"trait": "Ideal",
                       "desc": ideal},
                      {"trait": "Bond",
                       "desc": bond},
                      {"trait": "Flaw",
                       "desc": flaw}
                  ]
        return traits
    
    def discord_trim(self, str):
        result = []
        trimLen = 0
        lastLen = 0
        while trimLen <= len(str):
            trimLen += 1999
            result.append(str[lastLen:trimLen])
            lastLen += 1999
        
        return result
    