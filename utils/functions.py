"""
Created on Oct 29, 2016

@author: andrew
"""

import asyncio
import logging
import random
import re
from contextlib import suppress
from typing import Callable, TYPE_CHECKING, TypeVar

import disnake
from rapidfuzz import fuzz, process

from cogs5e.models.errors import NoSelectionElements, SelectionCancelled
from utils import constants, enums

if TYPE_CHECKING:
    from utils.context import AvraeContext

log = logging.getLogger(__name__)
sentinel = object()


def list_get(index, default, l):
    try:
        return l[index]
    except IndexError:
        return default


def get_positivity(string):
    if isinstance(string, bool):  # oi!
        return string
    lowered = string.lower()
    if lowered in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif lowered in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    else:
        return None


# ==== search / select menus ====
_HaystackT = TypeVar("_HaystackT")


def search(
    list_to_search: list[_HaystackT], value: str, key: Callable[[_HaystackT], str], cutoff=5, strict=False
) -> tuple[_HaystackT | list[_HaystackT], bool]:
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param strict: If True, will only search for exact matches.
    :returns: A two-tuple (result, strict)"""
    # there is nothing to search
    if len(list_to_search) == 0:
        return [], False

    # Remove limited use only items from search results
    try:
        list_to_search = list(filter(lambda a: not a.limited_use_only, list_to_search))
    except AttributeError:
        pass

    # full match, return result
    exact_matches = [a for a in list_to_search if value.lower() == key(a).lower()]
    if not (exact_matches or strict):
        partial_matches = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(partial_matches) > 1 or not partial_matches:
            names = [key(d).lower() for d in list_to_search]
            fuzzy_map = {key(d).lower(): d for d in list_to_search}
            fuzzy_results = [r for r in process.extract(value.lower(), names, scorer=fuzz.WRatio) if r[1] >= cutoff]
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

            # print out the results
            ratio_results = {}
            for result in results:
                ratio_results[key(result)] = fuzz.token_set_ratio(value.lower(), key(result).lower())

            # Sort
            sorted_results = sorted(results, key=lambda e: ratio_results[key(e)], reverse=True)
            results = sorted_results
            print(results)

        else:
            results = partial_matches
    else:
        results = exact_matches

    if len(results) > 1:
        return results, False
    elif not results:
        return [], False
    else:
        return results[0], True


def paginate(choices: list[_HaystackT], per_page: int) -> list[list[_HaystackT]]:
    out = []
    for start_idx in range(0, len(choices), per_page):
        out.append(choices[start_idx : start_idx + per_page])
    return out


async def get_selection(
    ctx,
    choices: list[_HaystackT],
    key: Callable[[_HaystackT], str],
    delete=True,
    pm=False,
    message=None,
    force_select=False,
    query=None,
):
    """Returns the selected choice, or raises an error.
    If delete is True, will delete the selection message and the response.
    If length of choices is 1, will return the only choice unless force_select is True.

    :raises NoSelectionElements: if len(choices) is 0.
    :raises SelectionCancelled: if selection is cancelled."""
    if len(choices) == 0:
        raise NoSelectionElements()
    elif len(choices) == 1 and not force_select:
        return choices[0]

    page = 0
    pages = paginate(choices, 10)
    m = None
    select_msg = None

    def chk(msg):
        content = msg.content.lower()
        valid = content in ("c", "n", "p")
        try:
            valid = valid or (1 <= int(content) <= len(choices))
        except ValueError:
            pass
        return msg.author == ctx.author and msg.channel == ctx.channel and valid

    for n in range(200):
        _choices = pages[page]
        names = [key(o) for o in _choices]
        embed = disnake.Embed()
        embed.title = "Multiple Matches Found"
        select_str = f"Your input was: `{query}`\n" if query else ""
        select_str += "Which one were you looking for? (Type the number or `c` to cancel)\n"
        if len(pages) > 1:
            select_str += "`n` to go to the next page, or `p` for previous\n"
            embed.set_footer(text=f"Page {page + 1}/{len(pages)}")
        for i, r in enumerate(names):
            select_str += f"**[{i + 1 + page * 10}]** - {r}\n"
        embed.description = select_str
        embed.colour = random.randint(0, 0xFFFFFF)
        if message:
            embed.add_field(name="Note", value=message, inline=False)
        if select_msg:
            await try_delete(select_msg)
        if not pm:
            select_msg = await ctx.channel.send(embed=embed)
        else:
            embed.add_field(
                name="Instructions",
                value=(
                    "Type your response in the channel you called the command. This message was PMed to "
                    "you to hide the monster name."
                ),
                inline=False,
            )
            select_msg = await ctx.author.send(embed=embed)

        try:
            m = await ctx.bot.wait_for("message", timeout=30, check=chk)
        except asyncio.TimeoutError:
            m = None

        if m is None:
            break
        if m.content.lower() == "n":
            if page + 1 < len(pages):
                page += 1
            else:
                await ctx.channel.send("You are already on the last page.")
        elif m.content.lower() == "p":
            if page - 1 >= 0:
                page -= 1
            else:
                await ctx.channel.send("You are already on the first page.")
        else:
            break

    if delete and not pm:
        with suppress(disnake.HTTPException):
            await select_msg.delete()
            if m is not None:
                await m.delete()
    if m is None or m.content.lower() == "c":
        raise SelectionCancelled()
    idx = int(m.content) - 1
    return choices[idx]


async def search_and_select(
    ctx: "AvraeContext",
    list_to_search: list[_HaystackT],
    query: str,
    key: Callable[[_HaystackT], str],
    cutoff=5,
    pm=False,
    message=None,
    list_filter=None,
    selectkey=None,
    return_metadata=False,
    strip_query_quotes=True,
    selector=get_selection,
) -> _HaystackT:
    """
    Searches a list for an object matching the key, and prompts user to select on multiple matches.
    Guaranteed to return a result - raises if there is no result.

    :param ctx: The context of the search.
    :param list_to_search: The list of objects to search.
    :param query: The value to search for.
    :param key: How to search - compares key(obj) to value
    :param cutoff: The cutoff percentage of fuzzy searches.
    :param pm: Whether to PM the user the select prompt.
    :param message: A message to add to the select prompt.
    :param list_filter: A filter to filter the list to search by.
    :param selectkey: If supplied, each option will display as selectkey(opt) in the select prompt.
    :param return_metadata: Whether to return a metadata object {num_options, chosen_index}.
    :param strip_query_quotes: Whether to strip quotes from the query.
    :param selector: The coroutine to use to select a result if multiple results are possible.
    """
    if list_filter:
        list_to_search = list(filter(list_filter, list_to_search))

    if strip_query_quotes:
        query = query.strip("\"'")

    result = search(list_to_search, query, key, cutoff)

    if result is None:
        raise NoSelectionElements("No matches found.")
    results, strict = result

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
            result = await selector(
                ctx, results, key=selectkey or key, pm=pm, message=message, force_select=True, query=query
            )
    if not return_metadata:
        return result
    metadata = {"num_options": 1 if strict else len(results), "chosen_index": 0 if strict else results.index(result)}
    return result, metadata


async def confirm(ctx, message, delete_msgs=False, response_check=get_positivity):
    """
    Confirms whether a user wants to take an action.

    :rtype: bool|None
    :param ctx: The current Context.
    :param message: The message for the user to confirm.
    :param delete_msgs: Whether to delete the messages.
    :param response_check: A function (str) -> bool that returns whether a given reply is a valid response.
    :type response_check: (str) -> bool
    :return: Whether the user confirmed or not. None if no reply was recieved
    """
    msg = await ctx.channel.send(message)
    try:
        reply = await ctx.bot.wait_for("message", timeout=30, check=auth_and_chan(ctx))
    except asyncio.TimeoutError:
        return None
    reply_bool = response_check(reply.content) if reply is not None else None
    if delete_msgs:
        try:
            await msg.delete()
            await reply.delete()
        except:
            pass
    return reply_bool


# ==== display helpers ====
def a_or_an(string, upper=False):
    if string.startswith("^") or string.endswith("^"):
        return string.strip("^")
    if re.match("[AEIOUaeiou].*", string):
        return "an {0}".format(string) if not upper else f"An {string}"
    return "a {0}".format(string) if not upper else f"A {string}"


def camel_to_title(string):
    return re.sub(r"((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))", r" \1", string).title()


def bubble_format(
    value: int, max_: int, fill_from_right=False, chars: constants.CounterBubbles = constants.COUNTER_BUBBLES["bubble"]
):
    """Returns a bubble string to represent a counter's value."""
    if max_ > 100:
        return f"{value}/{max_}"

    used = max_ - value
    filled = chars.filled * value
    empty = chars.empty * used
    if fill_from_right:
        return f"{empty}{filled}"
    return f"{filled}{empty}"


def verbose_stat(stat):
    """Returns the long stat name for a abbreviation (e.g. "str" -> "Strength", etc)"""
    return constants.STAT_ABBR_MAP[stat.lower()]


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


def chunk_text(text, max_chunk_size=1024, chunk_on=("\n\n", "\n", ". ", ", ", " "), chunker_i=0):
    """
    Recursively chunks *text* into a list of str, with each element no longer than *max_chunk_size*.
    Prefers splitting on the elements of *chunk_on*, in order.
    """

    if len(text) <= max_chunk_size:  # the chunk is small enough
        return [text]
    if chunker_i >= len(chunk_on):  # we have no more preferred chunk_on characters
        # optimization: instead of merging a thousand characters, just use list slicing
        return [text[:max_chunk_size], *chunk_text(text[max_chunk_size:], max_chunk_size, chunk_on, chunker_i + 1)]

    # split on the current character
    chunks = []
    split_char = chunk_on[chunker_i]
    for chunk in text.split(split_char):
        chunk = f"{chunk}{split_char}"
        if len(chunk) > max_chunk_size:  # this chunk needs to be split more, recurse
            chunks.extend(chunk_text(chunk, max_chunk_size, chunk_on, chunker_i + 1))
        elif chunks and len(chunk) + len(chunks[-1]) <= max_chunk_size:  # this chunk can be merged
            chunks[-1] += chunk
        else:
            chunks.append(chunk)

    # if the last chunk is just the split_char, yeet it
    if chunks[-1] == split_char:
        chunks.pop()

    # remove extra split_char from last chunk
    chunks[-1] = chunks[-1][: -len(split_char)]
    return chunks


def smart_trim(text, max_len=1024, dots="[...]"):
    """Uses chunk_text to return a trimmed str."""
    chunks = chunk_text(text, max_len - len(dots))
    out = chunks[0].strip()
    if len(chunks) > 1:
        return f"{chunks[0]}{dots}"
    return out


def ordinal(number: int) -> str:
    """
    Converts an integer into its ordinal counterpart (eg. 1 -> 1st, 2 -> 2nd, 3 -> 3rd, etc...)

    :param int number: Integer to convert
    :return: Ordinal form of the given number
    """
    ORDINAL_SUFFIXES = ("st", "nd", "rd", "th")

    number = int(number)
    if number // 10 == 1:
        return f"{number}th"
    else:
        # index rolls over when number increases by 10, with the number shifted 1 to the left to match the 1st with a 1
        index = min(3, (abs(number) - 1) % 10)
        return f"{number}{ORDINAL_SUFFIXES[index]}"


# ==== misc helpers ====
def auth_and_chan(ctx):
    """Message check: same author and channel"""

    def chk(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    return chk


async def try_delete(message):
    try:
        await message.delete()
    except disnake.HTTPException:
        pass


def maybe_mod(val: str, base=0):
    """
    Takes an argument, which is a string that may start with + or -, and returns the value.
    If *val* starts with + or -, it returns *base + val*.
    Otherwise, it returns *val*.
    """
    # This is done to handle GenericCombatants who might not have an hp/ac/etc
    base = base or 0

    try:
        if val.startswith(("+", "-")):
            base += int(val)
        else:
            base = int(val)
    except (ValueError, TypeError):
        return base
    return base


# ==== user stuff ====
async def user_from_id(ctx, the_id):
    """
    Gets a :class:`disnake.User` given their user id in the context. Returns member if context has data.

    :type ctx: disnake.ext.commands.Context
    :type the_id: int
    :rtype: disnake.User
    """

    async def update_known_user(the_user):
        avatar_hash = the_user.avatar.key if the_user.avatar is not None else None
        await ctx.bot.mdb.users.update_one(
            {"id": str(the_user.id)},
            {
                "$set": {
                    "username": the_user.name,
                    "discriminator": the_user.discriminator,
                    "avatar": avatar_hash,
                    "bot": the_user.bot,
                }
            },
            upsert=True,
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
        return disnake.User(state=ctx.bot._connection, data=user_doc)

    # fetch the user from the Discord API
    try:
        fetched_user = await ctx.bot.fetch_user(the_id)
    except disnake.NotFound:
        return None

    await update_known_user(fetched_user)
    return fetched_user


async def get_guild_member(guild, member_id):
    """Gets and caches a specific guild member."""
    if guild is None:
        return None
    if (member := guild.get_member(member_id)) is not None:
        return member
    result = await guild.query_members(user_ids=[member_id], limit=1, cache=True)
    if result:
        return result[0]
    return None


def reconcile_adv(adv=False, dis=False, eadv=False) -> enums.AdvantageType:
    """
    Reconciles sets of advantage passed in

    :param adv: Combined advantage
    :param dis: Combined disadvantage
    :param eadv:  Combined elven accuracy
    :return: The combined advantage result
    """
    result = 0
    if adv or eadv:
        result += 1
    if dis:
        result += -1
    if eadv and not dis:
        return enums.AdvantageType.ELVEN
    return enums.AdvantageType(result)


def maybe_http_url(url: str):
    """Returns a url if one found, otherwise None."""
    # Mainly used for embed.set_thumbnail(url=url)
    return url if "http" in url else None


def exactly_one(iterable):
    """If the iterable yields exactly one element, return it; otherwise return None"""
    # I got nerdsniped and compared this to checking len(list(iterable)) == 1 instead, and this is only 70ns faster
    # but it's much more memory efficient if the iterator is large so, cool, I guess
    retval = next(iterable, None)
    if next(iterable, sentinel) is sentinel:
        return retval
    return None


split_regex = re.compile(r"\W+")


def get_initials(name: str) -> str:
    """
    Returns the initials for a given string if its multiple words, otherwise returns the first two letters in uppercase.
    """
    # Mainly used for monster combatants in initiative
    split_name = split_regex.split(name)

    # Single word, return first two letters, uppercase
    if len(split_name) == 1:
        return name[:2].upper()

    # Multiple words, find initials
    return "".join(word[0] for word in split_name if word)
