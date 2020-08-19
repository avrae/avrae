"""
Created on Oct 29, 2016

@author: andrew
"""
import asyncio
import logging
import random
import re
from itertools import zip_longest

import discord
from fuzzywuzzy import fuzz, process

from cogs5e.models.errors import NoSelectionElements, SelectionCancelled
from utils import constants

log = logging.getLogger(__name__)


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


def search(list_to_search: list, value, key, cutoff=5, return_key=False, strict=False):
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param return_key: Whether to return the key of the object that matched or the object itself.
    :param strict: If True, will only search for exact matches.
    :returns: A two-tuple (result, strict)"""
    # there is nothing to search
    if len(list_to_search) == 0:
        return [], False

    # full match, return result
    exact_matches = [a for a in list_to_search if value.lower() == key(a).lower()]
    if not (exact_matches or strict):
        partial_matches = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(partial_matches) > 1 or not partial_matches:
            names = [key(d).lower() for d in list_to_search]
            fuzzy_map = {key(d).lower(): d for d in list_to_search}
            fuzzy_results = [r for r in process.extract(value.lower(), names, scorer=fuzz.ratio) if r[1] >= cutoff]
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
    else:
        results = exact_matches

    if len(results) > 1:
        if return_key:
            return [key(r) for r in results], False
        else:
            return results, False
    elif not results:
        return [], False
    else:
        if return_key:
            return key(results[0]), True
        else:
            return results[0], True


async def search_and_select(ctx, list_to_search: list, query, key, cutoff=5, return_key=False, pm=False, message=None,
                            list_filter=None, selectkey=None, search_func=search, return_metadata=False):
    """
    Searches a list for an object matching the key, and prompts user to select on multiple matches.
    :param ctx: The context of the search.
    :param list_to_search: The list of objects to search.
    :param query: The value to search for.
    :param key: How to search - compares key(obj) to value
    :param cutoff: The cutoff percentage of fuzzy searches.
    :param return_key: Whether to return key(match) or match.
    :param pm: Whether to PM the user the select prompt.
    :param message: A message to add to the select prompt.
    :param list_filter: A filter to filter the list to search by.
    :param selectkey: If supplied, each option will display as selectkey(opt) in the select prompt.
    :param search_func: The function to use to search.
    :param return_metadata Whether to return a metadata object {num_options, chosen_index}.
    :return:
    """
    if list_filter:
        list_to_search = list(filter(list_filter, list_to_search))

    if search_func is None:
        search_func = search

    if asyncio.iscoroutinefunction(search_func):
        result = await search_func(list_to_search, query, key, cutoff, return_key)
    else:
        result = search_func(list_to_search, query, key, cutoff, return_key)

    if result is None:
        raise NoSelectionElements("No matches found.")
    strict = result[1]
    results = result[0]

    if strict:
        result = results
    else:
        if len(results) == 0:
            raise NoSelectionElements()

        first_result = results[0]
        confidence = fuzz.partial_ratio(key(first_result).lower(), query.lower())
        if len(results) == 1 and confidence > 75:
            result = first_result
        else:
            if selectkey:
                options = [(selectkey(r), r) for r in results]
            elif return_key:
                options = [(r, r) for r in results]
            else:
                options = [(key(r), r) for r in results]
            result = await get_selection(ctx, options, pm=pm, message=message, force_select=True)
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


def paginate(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return [i for i in zip_longest(*args, fillvalue=fillvalue) if i is not None]


async def get_selection(ctx, choices, delete=True, pm=False, message=None, force_select=False):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If delete is True, will delete the selection message and the response.
    If length of choices is 1, will return the only choice unless force_select is True.

    :raises NoSelectionElements: if len(choices) is 0.
    :raises SelectionCancelled: if selection is cancelled."""
    if len(choices) == 0:
        raise NoSelectionElements()
    elif len(choices) == 1 and not force_select:
        return choices[0][1]

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
            embed.set_footer(text=f"Page {page + 1}/{len(pages)}")
        for i, r in enumerate(names):
            selectStr += f"**[{i + 1 + page * 10}]** - {r}\n"
        embed.description = selectStr
        embed.colour = random.randint(0, 0xffffff)
        if message:
            embed.add_field(name="Note", value=message, inline=False)
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
                                  "you to hide the monster name.", inline=False)
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
    if m is None or m.content.lower() == "c":
        raise SelectionCancelled()
    return choices[int(m.content) - 1][1]


ABILITY_MAP = {'str': 'Strength', 'dex': 'Dexterity', 'con': 'Constitution',
               'int': 'Intelligence', 'wis': 'Wisdom', 'cha': 'Charisma'}


def verbose_stat(stat):
    return ABILITY_MAP[stat.lower()]


async def confirm(ctx, message, delete_msgs=False):
    """
    Confirms whether a user wants to take an action.
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


def auth_and_chan(ctx):
    """Message check: same author and channel"""

    def chk(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    return chk


async def try_delete(message):
    try:
        await message.delete()
    except discord.HTTPException:
        pass


def maybe_mod(val: str, base=0):
    """
    Takes an argument, which is a string that may start with + or -, and returns the value.
    If *val* starts with + or -, it returns *base + val*.
    Otherwise, it returns *val*.
    """
    base = base or 0

    try:
        if val.startswith(('+', '-')):
            base += int(val)
        else:
            base = int(val)
    except (ValueError, TypeError):
        return base
    return base


def bubble_format(value: int, max_: int, fill_from_right=False):
    """Returns a bubble string to represent a counter's value."""
    if max_ > 100:
        return f"{value}/{max_}"

    used = max_ - value
    filled = '\u25c9' * value
    empty = '\u3007' * used
    if fill_from_right:
        return f"{empty}{filled}"
    return f"{filled}{empty}"


def long_source_name(source):
    return constants.SOURCE_MAP.get(source, source)


def source_slug(source):
    return constants.SOURCE_SLUG_MAP.get(source)


def natural_join(things, between: str):
    if len(things) < 3:
        return f" {between} ".join(things)
    first_part = ", ".join(things[:-1])
    return f"{first_part}, {between} {things[-1]}"


def trim_str(text, max_len):
    """Trims a string to max_len."""
    if len(text) < max_len:
        return text
    return f"{text[:max_len - 4]}..."


async def user_from_id(ctx, the_id):
    """
    Gets a :class:`discord.User` given their user id in the context. Returns member if context has data.

    :type ctx: discord.ext.commands.Context
    :type the_id: int
    :rtype: discord.User
    """

    async def update_known_user(the_user):
        await ctx.bot.mdb.users.update_one(
            {"id": str(the_user.id)},
            {"$set": {'username': the_user.name, 'discriminator': the_user.discriminator,
                      'avatar': the_user.avatar, 'bot': the_user.bot}},
            upsert=True
        )

    if ctx.guild:  # try and get member
        member = ctx.guild.get_member(the_id)
        if member is not None:
            await update_known_user(member)
            return member

    # try and see if user is in bot cache
    user = ctx.bot.get_user(the_id)
    if user is not None:
        await update_known_user(user)
        return user

    # or maybe the user is in our known user db
    user_doc = await ctx.bot.mdb.users.find_one({"id": str(the_id)})
    if user_doc is not None:
        # noinspection PyProtectedMember
        # technically we're not supposed to create User objects like this
        # but it *should* be fine
        return discord.User(state=ctx.bot._connection, data=user_doc)

    # fetch the user from the Discord API
    try:
        fetched_user = await ctx.bot.fetch_user(the_id)
    except discord.NotFound:
        return None

    await update_known_user(fetched_user)
    return fetched_user
