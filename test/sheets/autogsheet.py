import random

import pygsheets

from cogs5e.funcs.lookupFuncs import c
from cogs5e.funcs.lookupFuncs import *

PARENT_FOLDER_ID = '0B7G4hVfa4Trwak1vUWF2U19KaDA'
TEMPLATE_SPREADSHEET_ID = '1etrBJ0qCDXACovYHUM4XvjE0erndThwRLcUQzX6ts8w'
TEMPLATE_WORKSHEET_ID = '1750226729'
FEATURES_CELLS = [f"Z{i}" for i in range(45, 57)] + [f"AH{i}" for i in range(45, 57)]

def get_selection(choices):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If length of choices is 1, will return the only choice."""
    if len(choices) < 2:
        if len(choices):
            return choices[0]
        else:
            return ''
    choices = choices[:10]  # sanity
    names = [o[0] for o in choices]
    results = [o[1] for o in choices]
    selectStr = " Which one were you looking for? (Type the number)\n"
    for i, r in enumerate(names):
        selectStr += f"[{i+1}] - {r}\n"
    try:
        index = int(input(selectStr)) - 1
    except ValueError:
        return ''
    return results[index]


def do_selection(result):
    if result is None:
        return ''
    strict = result[1]
    results = result[0]

    if strict:
        return results
    else:
        if len(results) == 1:
            return results[0]
        else:
            return get_selection([(r['name'], r) for r in results])


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
        name, race['name'], _class['name'], final_level, background['name'], stats, ctx.message.author.mention,
        subclass['name'])

    await self.bot.edit_message(loadingMessage, out)


def main():
    gc = pygsheets.authorize(service_file='./avrae-0b82f09d7ab3.json')

    template = gc.open_by_key(TEMPLATE_SPREADSHEET_ID)  # open template
    new_sheet = gc.create("TESTNew CharacterTEST", parent_id=PARENT_FOLDER_ID)  # create new character sheet

    template.sheet1.copy_to(new_sheet.id)  # copy character sheet over
    new_sheet.del_worksheet(new_sheet.sheet1)  # delete default worksheet
    new_sheet.worksheet().title = "v1.3"  # pretty it a little

    feature_cell_index = 0

    feature_cell_index = do_race(new_sheet.worksheet(), feature_cell_index)
    feature_cell_index = do_class_and_level(new_sheet.worksheet(), feature_cell_index)
    email = input("Please enter your Google account email: ")
    new_sheet.share(email, role='writer')  # give control to user


if __name__ == '__main__':
    main()
