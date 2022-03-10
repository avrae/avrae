import base64
import hashlib
import hmac
import random
import struct

import bson
import d20
import disnake.ext.commands
import disnake.utils
import draconic

from cogs5e.models.errors import AvraeException
from utils import config
from utils.dice import RerollableStringifier
from .context import AliasAuthor, AliasChannel, AliasGuild
from ..utils import ExecutionScope

MAX_ITER_LENGTH = 10000


# vroll(), roll()
class SimpleRollResult:
    def __init__(self, result):
        """
        :type result: d20.RollResult
        """
        self.dice = d20.MarkdownStringifier().stringify(result.expr.roll)
        self.total = result.total
        self.full = str(result)
        self.result = result
        self.raw = result.expr
        self._roll = result

    def __str__(self):
        """
        Equivalent to ``result.full``.
        """
        return self.full

    def consolidated(self):
        """
        Gets the most simplified version of the roll string. Consolidates totals and damage types together.

        Note that this modifies the result expression in place!

        >>> result = vroll("3d6[fire]+1d4[cold]")
        >>> str(result)
        '3d6 (3, 3, 2) [fire] + 1d4 (2) [cold] = `10`'
        >>> result.consolidated()
        '8 [fire] + 2 [cold]'

        :rtype: str
        """
        d20.utils.simplify_expr(self._roll.expr, ambig_inherit="left")
        return RerollableStringifier().stringify(self._roll.expr.roll)


def vroll(dice, multiply=1, add=0):
    """
    Rolls dice and returns a detailed roll result.

    :param str dice: The dice to roll.
    :param int multiply: How many times to multiply each set of dice by.
    :param int add: How many dice to add to each set of dice.
    :return: The result of the roll.
    :rtype: :class:`~aliasing.api.functions.SimpleRollResult`
    """
    return _vroll(str(dice), int(multiply), int(add))


def roll(dice):
    """
    Rolls dice and returns the total.

    :param str dice: The dice to roll.
    :return: The roll's total, or 0 if an error was encountered.
    :rtype: int
    """
    return _roll(str(dice))


def _roll(dice, roller=None):
    if roller is None:
        roller = d20.Roller()

    try:
        result = roller.roll(dice)
    except d20.RollError:
        return 0
    return result.total


def _vroll(dice, multiply=1, add=0, roller=None):
    if roller is None:
        roller = d20.Roller()

    dice_ast = roller.parse(dice)

    if multiply != 1 or add != 0:

        def mapper(node):
            if isinstance(node, d20.ast.Dice):
                node.num = (node.num * multiply) + add
            return node

        dice_ast = d20.utils.tree_map(mapper, dice_ast)

    try:
        rolled = roller.roll(dice_ast)
    except d20.RollError:
        return None
    return SimpleRollResult(rolled)


# range()
# noinspection PyProtectedMember
def safe_range(start, stop=None, step=None):
    if stop is None and step is None:
        if start > MAX_ITER_LENGTH:
            draconic._raise_in_context(
                draconic.IterableTooLong, "This range is too large."
            )
        return list(range(start))
    elif stop is not None and step is None:
        if stop - start > MAX_ITER_LENGTH:
            draconic._raise_in_context(
                draconic.IterableTooLong, "This range is too large."
            )
        return list(range(start, stop))
    elif stop is not None and step is not None:
        if (stop - start) / step > MAX_ITER_LENGTH:
            draconic._raise_in_context(
                draconic.IterableTooLong, "This range is too large."
            )
        return list(range(start, stop, step))
    else:
        raise draconic._raise_in_context(
            draconic.DraconicValueError, "Invalid arguments passed to range()"
        )


# err()
class AliasException(AvraeException):
    def __init__(self, msg, pm_user):
        super().__init__(msg)
        self.pm_user = pm_user


def err(reason, pm_user=False):
    """
    Stops evaluation of an alias and shows the user an error.

    :param str reason: The error to show.
    :param bool pm_user: Whether or not to PM the user the error traceback.
    :raises: AliasException
    """
    raise AliasException(str(reason), pm_user)


# typeof()
def typeof(inst):
    """
    Returns the name of the type of an object.

    :param inst: The object to find the type of.
    :return: The type of the object.
    :rtype: str
    """
    return type(inst).__name__


# rand(), randint(x)
def rand():
    return random.random()


def randint(start, stop=None, step=1):
    return random.randrange(start, stop, step)


def randchoice(seq):
    return random.choice(seq)


# signatures
SIG_SECRET = config.DRACONIC_SIGNATURE_SECRET
SIG_STRUCT = struct.Struct(
    "!QQQ12sB"
)  # u64, u64, u64, byte[12], u8 - https://docs.python.org/3/library/struct.html
SIG_HASH_ALG = (
    hashlib.sha1
)  # SHA1 is technically compromised but the hash collision attack vector is not feasible here


def create_signature(
    ctx: disnake.ext.commands.Context,
    execution_scope: ExecutionScope,
    user_data: int,
    workshop_collection_id: bson.ObjectId = None,
):
    if not 0 <= user_data <= 31:
        raise ValueError("User data must be an unsigned 5-bit integer ([0..31]).")

    # if workshop collection is not available, stick 12 null bytes there :(
    workshop_collection_bytes = (
        bytes(12) if workshop_collection_id is None else workshop_collection_id.binary
    )
    # tail byte: [user data](5)[scope](3)
    tail_byte = ((user_data << 3) | execution_scope.value) & 0xFF

    # encode
    packed = SIG_STRUCT.pack(
        ctx.message.id,
        ctx.channel.id,
        ctx.author.id,
        workshop_collection_bytes,
        tail_byte,
    )
    b64_data = base64.b64encode(packed)

    # sign
    signature = hmac.new(SIG_SECRET, packed + SIG_SECRET, SIG_HASH_ALG)
    b64_signature = base64.b64encode(signature.digest())

    return f"{b64_data.decode()}.{b64_signature.decode()}"


def verify_signature(ctx: disnake.ext.commands.Context, data: str):
    # decode
    try:
        encoded_data, encoded_signature = data.split(".", 1)
        decoded_data = base64.b64decode(encoded_data, validate=True)
        decoded_signature = base64.b64decode(encoded_signature, validate=True)
        message_id, channel_id, author_id, object_id, tail_byte = SIG_STRUCT.unpack(
            decoded_data
        )
    except (ValueError, struct.error) as e:
        raise ValueError("Failed to unpack signature: invalid format") from e

    # verify
    verification = hmac.new(SIG_SECRET, decoded_data + SIG_SECRET, SIG_HASH_ALG)
    is_valid = hmac.compare_digest(decoded_signature, verification.digest())
    if not is_valid:
        raise ValueError("Failed to verify signature: invalid signature")

    # resolve
    timestamp = ((message_id >> 22) + disnake.utils.DISCORD_EPOCH) / 1000
    execution_scope = ExecutionScope(tail_byte & 0x07)
    user_data = (tail_byte & 0xF8) >> 3
    collection_id = (
        object_id.hex() if any(object_id) else None
    )  # bytes is an iterable of int, check if it's all 0

    channel = ctx.bot.get_channel(channel_id)
    author = ctx.bot.get_user(author_id)
    guild = None
    if channel is not None and isinstance(channel, disnake.abc.GuildChannel):
        guild = channel.guild

    return {
        "message_id": message_id,
        "channel_id": channel_id,
        "author_id": author_id,
        "timestamp": timestamp,
        "scope": execution_scope.name,
        "user_data": user_data,
        "workshop_collection_id": collection_id,
        "guild_id": guild and guild.id,  # may be None
        "guild": guild and AliasGuild(guild),  # may be None
        "channel": channel and AliasChannel(channel),  # may be None
        "author": author and AliasAuthor(author),  # may be None
    }
