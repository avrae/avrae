"""
Created on Oct 29, 2016

@author: andrew
"""
import errno
import logging
import os
import random
import re

import discord
from fuzzywuzzy import process, fuzz
from pygsheets import NoValidUrlKeyFound

from cogs5e.models.errors import SelectionCancelled, NoSelectionElements

log = logging.getLogger(__name__)


def print_table(table):
    tableStr = ''
    col_width = [max(len(x) for x in col) for col in zip(*table)]
    for line in table:
        tableStr += "| " + " | ".join("{:{}}".format(x, col_width[i])
                                      for i, x in enumerate(line)) + " |"
        tableStr += '\n'
    return tableStr


def discord_trim(str):
    result = []
    trimLen = 0
    lastLen = 0
    while trimLen <= len(str):
        trimLen += 1999
        result.append(str[lastLen:trimLen])
        lastLen += 1999
    return result


def embed_trim(str):
    result = []
    trimLen = 0
    lastLen = 0
    while trimLen <= len(str):
        trimLen += 1023
        result.append(str[lastLen:trimLen])
        lastLen += 1023
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


def fuzzywuzzy_search(list_to_search: list, key, value, cutoff=5):
    """Fuzzy searches a list for a dict with a key "key" of value "value" """
    names = [d[key] for d in list_to_search]
    result = process.extractOne(value, names, score_cutoff=cutoff)
    if result is None:
        return None
    else:
        return next(a for a in list_to_search if result[0] == a.get(key, ''))


def fuzzywuzzy_search_all_old(list_to_search: list, key, value):
    """Fuzzy searches a list for a dict with all keys "key" of value "value" """
    names = [d[key] for d in list_to_search]
    result = process.extract(value, names, scorer=fuzz.ratio)
    if len(result) is 0:
        return None
    else:
        return result


def fuzzywuzzy_search_all(list_to_search: list, key, value):
    """Fuzzy searches a list for a dict with all keys "key" of value "value" """
    try:
        result = next(a for a in list_to_search if value.lower() == a.get(key, '').lower())
    except StopIteration:
        try:
            result = next(a for a in list_to_search if value.lower() in a.get(key, '').lower())
        except StopIteration:
            names = [d[key] for d in list_to_search]
            result = process.extract(value, names, scorer=fuzz.ratio)
            if len(result) is 0:
                return None
            else:
                return result
    return [(result[key], 99)]


def fuzzywuzzy_search_all_2(list_to_search: list, key, value, cutoff=60):
    """Fuzzy searches a list for a dict with all keys "key" of value "value" """
    try:
        result = next(a for a in list_to_search if value.lower() == a.get(key, '').lower())
    except StopIteration:
        try:
            result = next(a for a in list_to_search if value.lower() in a.get(key, '').lower())
        except StopIteration:
            names = [d[key] for d in list_to_search]
            result = process.extract(value, names, scorer=fuzz.ratio)
            result = [r for r in result if r[1] >= cutoff]
            if len(result) is 0:
                return None
            else:
                return next(a for a in list_to_search if result[0][0] == a.get(key, ''))
    return result


def fuzzywuzzy_search_all_3(list_to_search: list, key, value, cutoff=5, return_key=False):
    """Fuzzy searches a list for a dict with all keys "key" of value "value"
    result can be either an object or list of objects
    :returns: A two-tuple (result, strict) or None"""
    try:
        result = next(a for a in list_to_search if value.lower() == a.get(key, '').lower())
    except StopIteration:
        result = [a for a in list_to_search if value.lower() in a.get(key, '').lower()]
        if len(result) is 0:
            names = [d[key] for d in list_to_search]
            result = process.extract(value, names, scorer=fuzz.ratio)
            result = [r for r in result if r[1] >= cutoff]
            if len(result) is 0:
                return None
            else:
                if return_key:
                    return [r[0] for r in result], False
                else:
                    return [a for a in list_to_search if a.get(key, '') in [r[0] for r in result]], False
        else:
            if return_key:
                return [r[key] for r in result], False
            else:
                return result, False
    if return_key:
        return result[key], True
    else:
        return result, True


def fuzzywuzzy_search_all_3_list(list_to_search: list, value, cutoff=5):
    """Fuzzy searches a list for a value.
    result can be either an object or list of objects
    :returns: A two-tuple (result, strict) or None"""
    try:
        result = next(a for a in list_to_search if value.lower() == a.lower())
    except StopIteration:
        result = [a for a in list_to_search if value.lower() in a.lower()]
        if len(result) is 0:
            names = list_to_search
            result = process.extract(value, names, scorer=fuzz.ratio)
            result = [r for r in result if r[1] >= cutoff]
            if len(result) is 0:
                return None
            else:
                return [r[0] for r in result], False
        else:
            return result, False
    return result, True


def parse_args(args):
    out = {}
    index = 0
    for a in args:
        if a == '-b' or a == '-d':
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = list_get(index + 1, None, args)
            else:
                out[a.replace('-', '')] += ' + ' + list_get(index + 1, None, args)
        elif a.startswith('-'):
            nextArg = list_get(index + 1, None, args)
            if nextArg is None or nextArg.startswith('-'): nextArg = True
            out[a.replace('-', '')] = nextArg
        else:
            out[a] = "True"
        index += 1
    return out


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
        elif a in ('-phrase'):
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else:
                out[a.replace('-', '')] += '\n' + list_get(index + 1, '0', args)
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


def parse_args_3(args):
    out = {}
    index = 0
    for a in args:
        if a.startswith('-'):
            if out.get(a.replace('-', '')) is None:
                out[a.replace('-', '')] = [list_get(index + 1, '0', args)]
            else:
                out[a.replace('-', '')].append(list_get(index + 1, 'MISSING_ARGUMENT', args))
        else:
            if out.get(a) is None:
                out[a] = ["True"]
            else:
                out[a].append("True")
        index += 1
    return out


def a_or_an(string):
    if re.match('[AEIOUaeiou].*', string):
        return 'an {0}'.format(string)
    return 'a {0}'.format(string)


def camel_to_title(string):
    return re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', string).title()


def text_to_numbers(string):
    numbers = {'one': '1',
               'two': '2',
               'three': '3',
               'four': '4',
               'five': '5',
               'six': '6',
               'seven': '7',
               'eight': '8',
               'nine': '9',
               'ten': '10',
               'once': '1',
               'twice': '2',
               'thrice': '3'}
    for t, i in numbers.items():
        string = string.replace(t, i)
    return string


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


async def get_selection(ctx, choices, delete=True, return_name=False, pm=False):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If delete is True, will delete the selection message and the response.
    If length of choices is 1, will return the only choice.
    @:raises NoSelectionElements if len(choices) is 0.
    @:raises SelectionCancelled if selection is cancelled."""
    if len(choices) < 2:
        if len(choices):
            return choices[0][1] if not return_name else choices[0]
        else:
            raise NoSelectionElements()
    choices = choices[:10]  # sanity
    names = [o[0] for o in choices]
    results = [o[1] for o in choices]
    embed = discord.Embed()
    embed.title = "Multiple Matches Found"
    selectStr = " Which one were you looking for? (Type the number, or \"c\" to cancel)\n"
    for i, r in enumerate(names):
        selectStr += f"**[{i+1}]** - {r}\n"
    embed.description = selectStr
    embed.colour = random.randint(0, 0xffffff)
    if not pm:
        selectMsg = await ctx.bot.send_message(ctx.message.channel, embed=embed)
    else:
        embed.add_field(name="Instructions",
                        value="Type your response in the channel you called the command. This message was PMed to you to hide the monster name.")
        selectMsg = await ctx.bot.send_message(ctx.message.author, embed=embed)

    def chk(msg):
        valid = [str(v) for v in range(1, len(choices) + 1)] + ["c"]
        return msg.content.lower() in valid

    m = await ctx.bot.wait_for_message(timeout=30, author=ctx.message.author, channel=ctx.message.channel,
                                       check=chk)
    if delete and not pm:
        try:
            await ctx.bot.delete_message(selectMsg)
            await ctx.bot.delete_message(m)
        except:
            pass
    if m is None or m.content.lower() == "c": raise SelectionCancelled()
    if return_name:
        return choices[int(m.content) - 1]
    return results[int(m.content) - 1]


def gen_error_message():
    subject = random.choice(['a kobold', 'the green dragon', 'the Frost Mage', 'Avrae', 'the wizard',
                             'an iron golem'])
    verb = random.choice(['must be', 'should be', 'has been', 'will be'])
    thing_to_do = random.choice(['stopped', 'killed', 'talked to', 'found', 'destroyed', 'fought'])
    return f"{subject} {verb} {thing_to_do}"


ABILITY_MAP = {'str': 'Strength', 'dex': 'Dexterity', 'con': 'Constitution',
               'int': 'Intelligence', 'wis': 'Wisdom', 'cha': 'Charisma'}


def parse_data_entry(text):
    """Parses a list or string from astranauta data.
    :returns str - The final text."""
    if not isinstance(text, list): return str(text)

    out = []

    for entry in text:
        if not isinstance(entry, dict):
            out.append(str(entry))
        elif isinstance(entry, dict):
            if not 'type' in entry and not 'title' in entry:
                log.warning(f"Unknown astranauta entry type: {entry}")

            if not 'type' in entry and 'title' in entry:
                out.append(f"**{entry['title']}**: {parse_data_entry(entry['text'])}")
            elif entry['type'] == 'entries':
                out.append((f"**{entry['name']}**: " if 'name' in entry else '') + parse_data_entry(
                    entry['entries']))  # oh gods here we goooooooo
            elif entry['type'] == 'options':
                pass  # parsed separately in classfeat
            elif entry['type'] == 'list':
                out.append('\n'.join(f"- {t}" for t in entry['items']))
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

    return '\n'.join(out)


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