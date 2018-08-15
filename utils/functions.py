"""
Created on Oct 29, 2016

@author: andrew
"""
import asyncio
import errno
import logging
import os
import random
import re
import shlex
from io import BytesIO
from itertools import zip_longest

import aiohttp
import discord
from PIL import Image
from fuzzywuzzy import process, fuzz
from pygsheets import NoValidUrlKeyFound

from cogs5e.models.errors import SelectionCancelled, NoSelectionElements

log = logging.getLogger(__name__)


def discord_trim(str):
    result = []
    trimLen = 0
    lastLen = 0
    while trimLen <= len(str):
        trimLen += 1999
        result.append(str[lastLen:trimLen])
        lastLen += 1999
    return result


def list_get(index, default, l):
    try:
        a = l[index]
    except IndexError:
        a = default
    return a


def make_sure_path_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def get_positivity(string):
    if isinstance(string, bool):  # oi!
        return string
    lowered = string.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    elif lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    else:
        return None


def strict_search(list_to_search: list, key, value):
    """Fuzzy searches a list for a dict with a key "key" of value "value" """
    result = next((a for a in list_to_search if value.lower() == a.get(key, '').lower()), None)
    return result


def fuzzy_search(list_to_search: list, key, value):
    """Fuzzy searches a list for a dict with a key "key" of value "value" """
    try:
        result = next(a for a in list_to_search if value.lower() == a.get(key, '').lower())
    except StopIteration:
        try:
            result = next(a for a in list_to_search if value.lower() in a.get(key, '').lower())
        except StopIteration:
            return None
    return result


def fuzzywuzzy_search_all_3(list_to_search: list, key, value, cutoff=5, return_key=False):
    """Fuzzy searches a list for a dict with all keys "key" of value "value"
    result can be either an object or list of objects
    :returns: A two-tuple (result, strict) or None"""
    return search(list_to_search, value, lambda e: e[key], cutoff, return_key)


def fuzzywuzzy_search_all_3_list(list_to_search: list, value, cutoff=5):
    """Fuzzy searches a list for a value.
    result can be either an object or list of objects
    :returns: A two-tuple (result, strict) or None"""
    return search(list_to_search, value, lambda e: e)


def search(list_to_search: list, value, key, cutoff=5, return_key=False):
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param return_key: Whether to return the key of the object that matched or the object itself.
    :returns: A two-tuple (result, strict) or None"""
    try:
        result = next(a for a in list_to_search if value.lower() == key(a).lower())
    except StopIteration:
        result = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(result) is 0:
            names = [key(d) for d in list_to_search]
            result = process.extract(value, names, scorer=fuzz.ratio)
            result = [r for r in result if r[1] >= cutoff]
            if len(result) is 0:
                return None
            else:
                if return_key:
                    return [r[0] for r in result], False
                else:
                    return [a for a in list_to_search if key(a) in [r[0] for r in result]], False
        else:
            if return_key:
                return [key(r) for r in result], False
            else:
                return result, False
    if return_key:
        return key(result), True
    else:
        return result, True


async def search_and_select(ctx, list_to_search: list, value, key, cutoff=5, return_key=False, pm=False,
                            message=None, list_filter=None, srd=False, selectkey=None):
    """
    Searches a list for an object matching the key, and prompts user to select on multiple matches.
    :param ctx: The context of the search.
    :param list_to_search: The list of objects to search.
    :param value: The value to search for.
    :param key: How to search - compares key(obj) to value
    :param cutoff: The cutoff percentage of fuzzy searches.
    :param return_key: Whether to return key(match) or match.
    :param pm: Whether to PM the user the select prompt.
    :param message: A message to add to the select prompt.
    :param list_filter: A filter to filter the list to search by.
    :param srd: Whether to only search items that have a property ['srd'] set to true, or a search function.
    :param selectkey: If supplied, each option will display as selectkey(opt) in the select prompt.
    :return:
    """
    if srd:
        if isinstance(srd, bool):
            srd = lambda e: e.get('srd')
        if list_filter:
            old = list_filter
            list_filter = lambda e: old(e) and srd(e)
        else:
            list_filter = srd
        message = "This server only shows results from the 5e SRD."
    if list_filter:
        list_to_search = list(filter(list_filter, list_to_search))
    result = search(list_to_search, value, key, cutoff, return_key)
    if result is None:
        raise NoSelectionElements("No matches found.")
    strict = result[1]
    results = result[0]

    if strict:
        result = results
    else:
        if len(results) == 1:
            result = results[0]
        else:
            if selectkey:
                result = await get_selection(ctx, [(selectkey(r), r) for r in results], pm=pm, message=message)
            elif return_key:
                result = await get_selection(ctx, [(r, r) for r in results], pm=pm, message=message)
            else:
                result = await get_selection(ctx, [(key(r), r) for r in results], pm=pm, message=message)
    return result


def parse_args_2(args):
    out = {}
    index = 0
    cFlag = False
    for a in args:
        if cFlag:
            cFlag = False
            continue
        if a == '-b' or a == '-d' or a == '-c':
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else:
                out[a.replace('-', '')] += ' + ' + list_get(index + 1, '0', args)
        elif re.match(r'-d\d+', a) or a.strip('-') in ('resist', 'immune', 'vuln'):
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else:
                out[a.replace('-', '')] += '|' + list_get(index + 1, '0', args)
        elif a in ('-phrase',):
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else:
                out[a.replace('-', '')] += '\n' + list_get(index + 1, '0', args)
        elif a == '-f':
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = [list_get(index + 1, '0', args)]
            else:
                out[a.replace('-', '')].append(list_get(index + 1, '0', args))
        elif a.startswith('-'):
            if list_get(index + 1, 'MISSING_ARGUMENT', args).startswith('-'):
                out[a.replace('-', '')] = 'True'
                index += 1
                continue
            else:
                out[a.replace('-', '')] = list_get(index + 1, 'MISSING_ARGUMENT', args)
        else:
            out[a] = 'True'
            index += 1
            continue
        index += 2
        cFlag = True
    return out



def a_or_an(string, upper=False):
    if re.match('[AEIOUaeiou].*', string):
        return 'an {0}'.format(string) if not upper else f'An {string}'
    return 'a {0}'.format(string) if not upper else f'A {string}'


def camel_to_title(string):
    return re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', string).title()


def parse_resistances(damage, resistances, immunities, vulnerabilities):
    COMMENT_REGEX = r'\[(?P<comment>.*?)\]'
    ROLL_STRING_REGEX = r'\[.*?]'

    comments = re.findall(COMMENT_REGEX, damage)
    roll_strings = re.split(ROLL_STRING_REGEX, damage)

    formatted_comments = []
    formatted_roll_strings = []

    for t, _ in enumerate(comments):
        if not roll_strings[t].replace(' ', '') == '':
            formatted_roll_strings.append(roll_strings[t])
            formatted_comments.append(comments[t])
        else:
            if len(formatted_comments) > 0:
                formatted_comments[-1] += ' ' + comments[t]
            else:
                pass  # eh, it'll error anyway

    if not roll_strings[-1].replace(' ', '') == '':
        formatted_roll_strings.append(roll_strings[-1])
        if formatted_comments:
            formatted_comments.append(formatted_comments[-1])  # carry over thingies
        else:
            formatted_comments.append('')

    for index, comment in enumerate(formatted_comments):
        roll_string = formatted_roll_strings[index].replace(' ', '')

        preop = ''
        if roll_string[0] in '-+*/().<>=':  # case: +6[blud]
            preop = roll_string[0]
            roll_string = roll_string[1:]
        if not comment.endswith('^'):
            for resistance in resistances:
                if resistance.lower() in comment.lower() and len(resistance) > 0:
                    roll_string = '({0}) / 2'.format(roll_string)
                    break
            for immunity in immunities:
                if immunity.lower() in comment.lower() and len(immunity) > 0:
                    roll_string = '({0}) * 0'.format(roll_string)
                    break
        for vulnerability in vulnerabilities:
            if vulnerability.lower() in comment.lower() and len(vulnerability) > 0:
                roll_string = '({0}) * 2'.format(roll_string)
                break
        formatted_roll_strings[index] = '{0}{1}{2}'.format(preop, roll_string,
                                                           "[{}]".format(comment) if comment is not '' else "")
    if formatted_roll_strings:
        damage = ''.join(formatted_roll_strings)

    return damage


def paginate(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return [i for i in zip_longest(*args, fillvalue=fillvalue) if i is not None]


async def get_selection(ctx, choices, delete=True, return_name=False, pm=False, message=None):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If delete is True, will delete the selection message and the response.
    If length of choices is 1, will return the only choice.
    :raises NoSelectionElements if len(choices) is 0.
    :raises SelectionCancelled if selection is cancelled."""
    if len(choices) < 2:
        if len(choices):
            return choices[0][1] if not return_name else choices[0]
        else:
            raise NoSelectionElements()
    page = 0
    pages = paginate(choices, 10)
    m = None

    def chk(msg):
        valid = [str(v) for v in range(1, len(choices) + 1)] + ["c", "n", "p"]
        return msg.content.lower() in valid

    for n in range(200):
        _choices = pages[page]
        names = [o[0] for o in _choices if o]
        embed = discord.Embed()
        embed.title = "Multiple Matches Found"
        selectStr = "Which one were you looking for? (Type the number or \"c\" to cancel)\n"
        if len(pages) > 1:
            selectStr += "`n` to go to the next page, or `p` for previous\n"
            embed.set_footer(text=f"Page {page+1}/{len(pages)}")
        for i, r in enumerate(names):
            selectStr += f"**[{i+1+page*10}]** - {r}\n"
        embed.description = selectStr
        embed.colour = random.randint(0, 0xffffff)
        if message:
            embed.add_field(name="Note", value=message)
        if not pm:
            if n == 0:
                selectMsg = await ctx.bot.send_message(ctx.message.channel, embed=embed)
            else:
                newSelectMsg = await ctx.bot.send_message(ctx.message.channel, embed=embed)
        else:
            embed.add_field(name="Instructions",
                            value="Type your response in the channel you called the command. This message was PMed to "
                                  "you to hide the monster name.")
            if n == 0:
                selectMsg = await ctx.bot.send_message(ctx.message.author, embed=embed)
            else:
                newSelectMsg = await ctx.bot.send_message(ctx.message.author, embed=embed)

        if n > 0:  # clean up old messages
            try:
                await ctx.bot.delete_message(selectMsg)
                await ctx.bot.delete_message(m)
            except:
                pass
            finally:
                selectMsg = newSelectMsg

        m = await ctx.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel,
                                           check=chk)
        if m is None:
            break
        if m.content.lower() == 'n':
            if page + 1 < len(pages):
                page += 1
            else:
                await ctx.bot.send_message(ctx.message.channel, "You are already on the last page.")
        elif m.content.lower() == 'p':
            if page - 1 >= 0:
                page -= 1
            else:
                await ctx.bot.send_message(ctx.message.channel, "You are already on the first page.")
        else:
            break

    if delete and not pm:
        try:
            await ctx.bot.delete_message(selectMsg)
            await ctx.bot.delete_message(m)
        except:
            pass
    if m is None or m.content.lower() == "c": raise SelectionCancelled()
    if return_name:
        return choices[int(m.content) - 1]
    return choices[int(m.content) - 1][1]


def gen_error_message():
    subject = random.choice(['a kobold', 'the green dragon', 'the Frost Mage', 'Avrae', 'the wizard',
                             'an iron golem'])
    verb = random.choice(['must be', 'should be', 'has been', 'will be'])
    thing_to_do = random.choice(['stopped', 'killed', 'talked to', 'found', 'destroyed', 'fought'])
    return f"{subject} {verb} {thing_to_do}"


ABILITY_MAP = {'str': 'Strength', 'dex': 'Dexterity', 'con': 'Constitution',
               'int': 'Intelligence', 'wis': 'Wisdom', 'cha': 'Charisma'}


def verbose_stat(stat):
    return ABILITY_MAP[stat]


def parse_data_entry(text, md_breaks=False):
    """Parses a list or string from astranauta data.
    :returns str - The final text."""
    if not isinstance(text, list): return str(text)

    out = []
    join_str = '\n' if not md_breaks else '  \n'

    for entry in text:
        if not isinstance(entry, dict):
            out.append(str(entry))
        elif isinstance(entry, dict):
            if not 'type' in entry and 'title' in entry:
                out.append(f"**{entry['title']}**: {parse_data_entry(entry['text'])}")
            elif not 'type' in entry and 'istable' in entry:  # only for races
                temp = f"**{entry['caption']}**\n" if 'caption' in entry else ''
                temp += ' - '.join(f"**{cl}**" for cl in entry['thead']) + '\n'
                for row in entry['tbody']:
                    temp += ' - '.join(f"{col}" for col in row) + '\n'
                out.append(temp.strip())
            elif entry['type'] == 'entries':
                out.append((f"**{entry['name']}**: " if 'name' in entry else '') + parse_data_entry(
                    entry['entries']))  # oh gods here we goooooooo
            elif entry['type'] == 'item':
                out.append((f"**{entry['name']}**: " if 'name' in entry else '') + parse_data_entry(
                    entry['entry']))  # oh gods here we goooooooo
            elif entry['type'] == 'options':
                pass  # parsed separately in classfeat
            elif entry['type'] == 'list':
                out.append('\n'.join(f"- {parse_data_entry([t])}" for t in entry['items']))
            elif entry['type'] == 'table':
                temp = f"**{entry['caption']}**\n" if 'caption' in entry else ''
                temp += ' - '.join(f"**{cl}**" for cl in entry['colLabels']) + '\n'
                for row in entry['rows']:
                    temp += ' - '.join(f"{col}" for col in row) + '\n'
                out.append(temp.strip())
            elif entry['type'] == 'invocation':
                pass  # this is only found in options
            elif entry['type'] == 'abilityAttackMod':
                out.append(f"`{entry['name']} Attack Bonus = "
                           f"{' or '.join(ABILITY_MAP.get(a) for a in entry['attributes'])}"
                           f" modifier + Proficiency Bonus`")
            elif entry['type'] == 'abilityDc':
                out.append(f"`{entry['name']} Save DC = 8 + "
                           f"{' or '.join(ABILITY_MAP.get(a) for a in entry['attributes'])}"
                           f" modifier + Proficiency Bonus`")
            elif entry['type'] == 'bonus':
                out.append("{:+}".format(entry['value']))
            elif entry['type'] == 'dice':
                out.append(f"{entry['number']}d{entry['faces']}")
            elif entry['type'] == 'bonusSpeed':
                out.append(f"{entry['value']} feet")
            else:
                log.warning(f"Missing astranauta entry type parse: {entry}")
        else:
            log.warning(f"Unknown astranauta entry: {entry}")

    return parse_data_formatting(join_str.join(out))


FORMATTING = {'bold': '**', 'italic': '*', 'b': '**', 'i': '*'}
PARSING = {
    'creature': lambda e: e.split('|')[-1],
    'item': lambda e: e.split('|')[0],
    'filter': lambda e: e.split('|')[0],
    'condition': lambda e: e,
    'spell': lambda e: e.split('|')[0]
}


def parse_data_formatting(text):
    """Parses a {@format } string."""
    exp = re.compile(r'{@(\w+) (.+?)}')

    def sub(match):
        if match.group(1) in PARSING:
            f = PARSING.get(match.group(1), lambda e: e)
            return f(match.group(2))
        else:
            f = FORMATTING.get(match.group(1), '')
            if not match.group(1) in FORMATTING:
                log.warning(f"Unknown tag: {match.group(1)}")
            return f"{f}{match.group(2)}{f}"

    while exp.search(text):
        text = exp.sub(sub, text)
    return text


def dicecloud_parse(spell):
    """
    :param spell: The spell to parse.
    :return: (dict) A dictionary with all the keys necessary for dicecloud exporting.
    """
    mat = re.search(r'\(([^()]+)\)', spell['components'])
    schools = {
        "A": "Abjuration",
        "EV": "Evocation",
        "EN": "Enchantment",
        "I": "Illusion",
        "D": "Divination",
        "N": "Necromancy",
        "T": "Transmutation",
        "C": "Conjuration"
    }
    spellDesc = []
    if isinstance(spell['text'], list):
        for a in spell["text"]:
            if a is '': continue
            spellDesc.append(a.replace("At Higher Levels: ", "**At Higher Levels:** ").replace(
                "This spell can be found in the Elemental Evil Player's Companion", ""))
    else:
        spellDesc.append(spell['text'].replace("At Higher Levels: ", "**At Higher Levels:** ").replace(
            "This spell can be found in the Elemental Evil Player's Companion", ""))

    text = '\n\n'.join(spellDesc)
    return {
        'name': spell['name'],
        'description': text,
        'castingTime': spell['time'],
        'range': spell['range'],
        'duration': spell['duration'],
        'components.verbal': 'V' in spell['components'],
        'components.somatic': 'S' in spell['components'],
        'components.concentration': 'Concentration' in spell['duration'],
        'components.material': mat.group(1) if mat else None,
        'ritual': 'ritual' in spell,
        'level': int(spell['level']),
        'school': schools.get(spell.get('school', 'A'))
    }


URL_KEY_V1_RE = re.compile(r'key=([^&#]+)')
URL_KEY_V2_RE = re.compile(r'/spreadsheets/d/([a-zA-Z0-9-_]+)')


def extract_gsheet_id_from_url(url):
    m2 = URL_KEY_V2_RE.search(url)
    if m2:
        return m2.group(1)

    m1 = URL_KEY_V1_RE.search(url)
    if m1:
        return m1.group(1)

    raise NoValidUrlKeyFound


async def confirm(ctx, message, delete_msgs=False):
    """
    Confirms whether a user wants to take an actions.
    :rtype: bool|None
    :param ctx: The current Context.
    :param message: The message for the user to confirm.
    :param delete_msgs: Whether to delete the messages.
    :return: Whether the user confirmed or not. None if no reply was recieved
    """
    msg = await ctx.bot.send_message(ctx.message.channel, message)
    reply = await ctx.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel)
    replyBool = get_positivity(reply.content) if reply is not None else None
    if delete_msgs:
        try:
            await ctx.bot.delete_message(msg)
            await ctx.bot.delete_message(reply)
        except:
            pass
    return replyBool


def parse_snippets(args: str, ctx) -> str:
    """
    Parses user and server snippets.
    :param args: The string to parse. Will be split automatically
    :param ctx: The Context.
    :return: The string, with snippets replaced.
    """
    tempargs = shlex.split(args)
    snippets = ctx.bot.db.jget('server_snippets', {}).get(ctx.message.server.id,
                                                          {}) if ctx.message.server is not None else {}
    snippets.update(ctx.bot.db.not_json_get('damage_snippets', {}).get(ctx.message.author.id, {}))
    for index, arg in enumerate(tempargs):  # parse snippets
        snippet_value = snippets.get(arg)
        if snippet_value:
            tempargs[index] = snippet_value
        elif ' ' in arg:
            tempargs[index] = shlex.quote(arg)
    return " ".join(tempargs)


async def generate_token(img_url, color_override=None):
    def process_img(img_bytes, color_override):
        b = BytesIO(img_bytes)
        img = Image.open(b)
        template = Image.open('res/template.png')
        transparency_template = Image.open('res/alphatemplate.tif')
        width, height = img.size
        is_taller = height >= width
        if is_taller:
            box = (0, 0, width, width)
        else:
            box = (width / 2 - height / 2, 0, width / 2 + height / 2, height)
        img = img.crop(box)
        img = img.resize((260, 260), Image.ANTIALIAS)

        if color_override is None:
            num_pixels = img.size[0] * img.size[1]
            colors = img.getcolors(num_pixels)
            rgb = sum(c[0] * c[1][0] for c in colors), sum(c[0] * c[1][1] for c in colors), sum(
                c[0] * c[1][2] for c in colors)
            rgb = rgb[0] / num_pixels, rgb[1] / num_pixels, rgb[2] / num_pixels
        else:
            rgb = ((color_override >> 16) & 255, (color_override >> 8) & 255, color_override & 255)

        bands = template.split()
        for i, v in enumerate(rgb):
            out = bands[i].point(lambda p: int(p * v / 255))
            bands[i].paste(out)

        img.putalpha(transparency_template)
        colored_template = Image.merge(template.mode, bands)
        img.paste(colored_template, mask=colored_template)

        out_bytes = BytesIO()
        img.save(out_bytes, "PNG")
        out_bytes.seek(0)
        return out_bytes

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as resp:
                img_bytes = await resp.read()
        processed = await asyncio.get_event_loop().run_in_executor(None, process_img, img_bytes, color_override)
    except Exception:
        raise

    return processed


def clean_content(content, ctx):
    transformations = {
        re.escape('<@{0.id}>'.format(member)): '@' + member.display_name
        for member in ctx.message.mentions
    }

    # add the <@!user_id> cases as well..
    second_mention_transforms = {
        re.escape('<@!{0.id}>'.format(member)): '@' + member.display_name
        for member in ctx.message.mentions
    }

    transformations.update(second_mention_transforms)

    if ctx.message.server is not None:
        role_transforms = {
            re.escape('<@&{0.id}>'.format(role)): '@' + role.name
            for role in ctx.message.role_mentions
        }
        transformations.update(role_transforms)

    def repl(obj):
        return transformations.get(re.escape(obj.group(0)), '')

    pattern = re.compile('|'.join(transformations.keys()))
    result = pattern.sub(repl, content)

    transformations = {
        '@everyone': '@\u200beveryone',
        '@here': '@\u200bhere'
    }

    def repl2(obj):
        return transformations.get(obj.group(0), '')

    pattern = re.compile('|'.join(transformations.keys()))
    return pattern.sub(repl2, result)
