"""
Created on Oct 29, 2016

@author: andrew
"""
import asyncio
import logging
import random
import re
from io import BytesIO
from itertools import zip_longest

import aiohttp
import discord
import numpy
from PIL import Image
from fuzzywuzzy import fuzz, process
from pygsheets import NoValidUrlKeyFound

from cogs5e.models.errors import NoSelectionElements, SelectionCancelled

log = logging.getLogger(__name__)


def discord_trim(string):
    result = []
    trimLen = 0
    lastLen = 0
    while trimLen <= len(string):
        trimLen += 1999
        result.append(string[lastLen:trimLen])
        lastLen += 1999
    return result


def list_get(index, default, l):
    try:
        a = l[index]
    except IndexError:
        a = default
    return a


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


def search(list_to_search: list, value, key, cutoff=5, return_key=False, strict=False):
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param return_key: Whether to return the key of the object that matched or the object itself.
    :param strict: Kinda does nothing. I'm not sure why this is here.
    :returns: A two-tuple (result, strict) or None"""
    # full match, return result
    result = next((a for a in list_to_search if value.lower() == key(a).lower()), None)
    if result is None:
        partial_matches = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(partial_matches) > 1 or not partial_matches:
            names = [key(d) for d in list_to_search]
            fuzzy_map = {key(d): d for d in list_to_search}
            fuzzy_results = [r for r in process.extract(value, names, scorer=fuzz.ratio) if r[1] >= cutoff]
            fuzzy_sum = sum(r[1] for r in fuzzy_results)
            fuzzy_matches_and_confidences = [(fuzzy_map[r[0]], r[1] / fuzzy_sum) for r in fuzzy_results]

            # display the results in order of confidence
            weighted_results = []
            weighted_results.extend((match, confidence) for match, confidence in fuzzy_matches_and_confidences)
            weighted_results.extend((match, len(value) / len(key(match))) for match in partial_matches)
            sorted_weighted = sorted(weighted_results, key=lambda e: e[1], reverse=True)

            # build results list, unique
            results = []
            for r in sorted_weighted:
                if r[0] not in results:
                    results.append(r[0])
        else:
            results = partial_matches
        if return_key:
            return [key(r) for r in results], False
        else:
            return results, False
    if return_key:
        return key(result), True
    else:
        return result, True


async def search_and_select(ctx, list_to_search: list, value, key, cutoff=5, return_key=False, pm=False, message=None,
                            list_filter=None, selectkey=None, search_func=search, return_metadata=False):
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
    :param selectkey: If supplied, each option will display as selectkey(opt) in the select prompt.
    :param search_func: The function to use to search.
    :return:
    """
    if message:
        message = f"{message}\nOnly results from the 5e SRD are included."
    else:
        message = "Only results from the 5e SRD are included."
    if list_filter:
        list_to_search = list(filter(list_filter, list_to_search))

    if search_func is None:
        search_func = search

    if asyncio.iscoroutinefunction(search_func):
        result = await search_func(list_to_search, value, key, cutoff, return_key)
    else:
        result = search_func(list_to_search, value, key, cutoff, return_key)

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
    if not return_metadata:
        return result
    metadata = {
        "num_options": 1 if strict else len(results),
        "chosen_index": 0 if strict else results.index(result)
    }
    return result, metadata


def a_or_an(string, upper=False):
    if string.startswith('^') or string.endswith('^'):
        return string.strip('^')
    if re.match('[AEIOUaeiou].*', string):
        return 'an {0}'.format(string) if not upper else f'An {string}'
    return 'a {0}'.format(string) if not upper else f'A {string}'


def camel_to_title(string):
    return re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', string).title()


# noinspection PyTypeChecker
def parse_resistances(damage, resistances, immunities, vulnerabilities, neutral=None):
    if neutral is None:
        neutral = []
    # clean resists and whatnot
    resistances = [r for r in resistances if r]
    immunities = [r for r in immunities if r]
    vulnerabilities = [r for r in vulnerabilities if r]
    neutral = [r for r in neutral if r]

    damage = damage.strip("*/")

    # PEMDAS time!
    # split into groups
    groups = re.split(r"(\(.*\)|[+\-])", damage)
    groups = [g.strip() for g in groups if g.strip()]

    # P
    for i, group in enumerate(groups):
        paren = re.match(r"\((.*)\)", group)
        if paren:
            groups[i] = f"({parse_resistances(paren.group(1), resistances, immunities, vulnerabilities, neutral)})"

    # MD
    # we shouldn't really change the resists on these, so just group them
    for i, group in enumerate(groups.copy()):
        if group.startswith('*') or group.startswith('/'):
            groups[i - 1] += groups.pop(i)

    # AS
    # we kind of already did this, so...
    # on to the resist parsing!

    # split groups into (group, annotation)
    # ignore parens, since they're already done (in theory)
    for i, group in enumerate(groups):
        anno_match = re.search(r"\[(.*)\]", group)
        if anno_match and not '(' in group:
            groups[i] = (group.replace(anno_match.group(0), "").strip(), anno_match.group(1))
        else:
            groups[i] = (group, None)

    # for use in next part
    def on_anno(unk, annotation):
        if not annotation:
            return unk
        ann = annotation.lower()
        if any(n.lower() in ann for n in neutral):  # neutral overrides all
            return f"{unk}[{annotation}]"
        if any(v.lower() in ann for v in vulnerabilities):
            unk = f"({unk})*2"
        if not (annotation.startswith('^') or annotation.endswith('^')):  # ignore resist, immune
            if any(r.lower() in ann for r in resistances):
                unk = f"({unk})/2"
            if any(im.lower() in ann for im in immunities):
                unk = f"({unk})*0"
        return f"{unk}[{annotation}]"

    # iterate over group, anno pairs
    # if it's a parenthetical, clear unknown and skip
    # if it has no annotation and (unknown is not empty or it's not an op), add the group to a running unknown string
    # if it has an annotation, assume all unknowns are part of that annotation and apply correct multiplier
    # if we've reached the end, assume all unknowns were part of the last annotation and apply correct multiplier
    out = ""
    unknown = ""
    last_annotation = ""
    for group, anno in groups:
        if '(' in group:
            out += unknown
            out += group
            unknown = ""
        elif not anno and (unknown or not ('+' in group or '-' in group)):
            unknown += group
        elif anno:
            last_annotation = anno
            unknown += group
            out += on_anno(unknown, anno)
            unknown = ""
        else:  # generally, ops after parens, just pass it along
            out += group
    if unknown:
        out += on_anno(unknown, last_annotation)

    # test string: (3d6[vuln]+(1d4 +1d6[resist]))/2+1d6[vuln]+3d6[resist]/2
    return out


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
    selectMsg = None

    def chk(msg):
        valid = [str(v) for v in range(1, len(choices) + 1)] + ["c", "n", "p"]
        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.lower() in valid

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
        if selectMsg:
            try:
                await selectMsg.delete()
            except:
                pass
        if not pm:
            selectMsg = await ctx.channel.send(embed=embed)
        else:
            embed.add_field(name="Instructions",
                            value="Type your response in the channel you called the command. This message was PMed to "
                                  "you to hide the monster name.")
            selectMsg = await ctx.author.send(embed=embed)

        try:
            m = await ctx.bot.wait_for('message', timeout=30, check=chk)
        except asyncio.TimeoutError:
            m = None

        if m is None:
            break
        if m.content.lower() == 'n':
            if page + 1 < len(pages):
                page += 1
            else:
                await ctx.channel.send("You are already on the last page.")
        elif m.content.lower() == 'p':
            if page - 1 >= 0:
                page -= 1
            else:
                await ctx.channel.send("You are already on the first page.")
        else:
            break

    if delete and not pm:
        try:
            await selectMsg.delete()
            await m.delete()
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
    """Parses a list or string from... data.
    :returns str - The final text."""
    if not isinstance(text, list):
        return parse_data_formatting(str(text))

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
            elif not 'type' in entry:
                out.append((f"**{entry['name']}**: " if 'name' in entry else '') +
                           parse_data_entry(entry['entries']))
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
                if 'toRoll' in entry:
                    out.append(' + '.join(f"{d['number']}d{d['faces']}" for d in entry['toRoll']))
                else:
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
    msg = await ctx.channel.send(message)
    try:
        reply = await ctx.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
    except asyncio.TimeoutError:
        return None
    replyBool = get_positivity(reply.content) if reply is not None else None
    if delete_msgs:
        try:
            await msg.delete()
            await reply.delete()
        except:
            pass
    return replyBool


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

        # color the circle
        bands = template.split()
        for i, v in enumerate(rgb):
            out = bands[i].point(lambda p: int(p * v / 255))
            bands[i].paste(out)

        # alpha blending
        try:
            alpha = img.getchannel("A")
            alpha_pixels = numpy.array(alpha)
            template_pixels = numpy.asarray(transparency_template)
            for r, row in enumerate(template_pixels):
                for c, col in enumerate(row):
                    alpha_pixels[r][c] = min(alpha_pixels[r][c], col)
            out = Image.fromarray(alpha_pixels, "L")
            img.putalpha(out)
        except ValueError:
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

    if ctx.guild is not None:
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


def format_d20(adv, reroll=None):
    base_d20 = '1d20'
    if adv in (1, -1):
        base_d20 = '2d20'
    elif adv == 2:
        base_d20 = '3d20'
    if reroll:
        base_d20 = f"{base_d20}ro{reroll}"

    if adv in (1, 2):
        return f"{base_d20}kh1"
    elif adv == -1:
        return f"{base_d20}kl1"
    return base_d20


def auth_and_chan(ctx):
    """Message check: same author and channel"""

    def chk(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    return chk
