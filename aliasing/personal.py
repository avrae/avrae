"""
Personal aliases and snippets. Unrelated to the workshop.
"""
import abc

from aliasing.constants import ALIAS_SIZE_LIMIT, SNIPPET_SIZE_LIMIT
from cogs5e.models.errors import InvalidArgument


# ==== aliases ====
class _AliasBase(abc.ABC):
    def __init__(self, name, commands):
        self.name = name
        self.commands = commands

    @staticmethod
    def _checks(commands):
        if len(commands) > ALIAS_SIZE_LIMIT:
            raise InvalidArgument(f"Aliases must be shorter than {ALIAS_SIZE_LIMIT} characters.")


class Alias(_AliasBase):
    def __init__(self, name, commands, owner):
        super().__init__(name, commands)
        self.owner = owner

    @classmethod
    def new(cls, name, commands, owner):
        """
        Creates a new alias.

        :param name: The name of the alias.
        :type name: str
        :param commands: The commands that name is an alias of.
        :type commands: str
        :param owner: The owner of the alias. Must be str.
        :type owner: str
        """
        commands = str(commands)
        cls._checks(commands)
        return cls(name, commands, str(owner))

    async def commit(self, mdb):
        """
        Writes the alias to MongoDB, creating it if necessary.

        :param mdb: The database.
        :type mdb: motor.motor_asyncio.AsyncIOMotorDatabase
        """
        await mdb.aliases.update_one({"owner": self.owner, "name": self.name},
                                     {"$set": {"commands": self.commands}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        aliases = {}
        async for alias in ctx.bot.mdb.aliases.find({"owner": str(ctx.author.id)}):
            aliases[alias['name']] = alias['commands']
        return aliases


class Servalias(_AliasBase):
    def __init__(self, name, commands, server):
        super().__init__(name, commands)
        self.server = server

    @classmethod
    def new(cls, name, commands, server):
        """
        Creates a new server alias.

        :param name: The name of the alias.
        :type name: str
        :param commands: The commands that name is an alias of.
        :type commands: str
        :param server: The owner of the alias. Must be str.
        :type server: str
        """
        commands = str(commands)
        cls._checks(commands)
        return cls(name, commands, str(server))

    async def commit(self, mdb):
        """
        Writes the server alias to MongoDB, creating it if necessary.

        :param mdb: The database.
        :type mdb: motor.motor_asyncio.AsyncIOMotorDatabase
        """
        await mdb.servaliases.update_one({"server": self.server, "name": self.name},
                                         {"$set": {"commands": self.commands}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        servaliases = {}
        async for servalias in ctx.bot.mdb.servaliases.find({"server": str(ctx.guild.id)}):
            servaliases[servalias['name']] = servalias['commands']
        return servaliases


# ==== snippets ====
class _SnippetBase(abc.ABC):
    def __init__(self, name, snippet):
        self.name = name
        self.snippet = snippet

    @staticmethod
    def _checks(name, snippet):
        if len(snippet) > SNIPPET_SIZE_LIMIT:
            raise InvalidArgument(f"Snippets must be shorter than {SNIPPET_SIZE_LIMIT} characters.")
        if len(name) < 2:
            raise InvalidArgument("Snippet names must be at least 2 characters long.")
        if ' ' in name:
            raise InvalidArgument("Snippet names cannot contain spaces.")


class Snippet(_SnippetBase):
    def __init__(self, name, snippet, owner):
        super().__init__(name, snippet)
        self.owner = owner

    @classmethod
    def new(cls, name, snippet, owner):
        """
        Creates a new snippet.

        :param name: The name of the snippet.
        :type name: str
        :param snippet: The arguments the snippet is a shortcut of.
        :type snippet: str
        :param owner: The owner of the snippet. Must be str.
        :type owner: str
        """
        snippet = str(snippet)
        cls._checks(name, snippet)
        return cls(name, snippet, str(owner))

    async def commit(self, mdb):
        """
        Writes the snippet to MongoDB, creating it if necessary.

        :param mdb: The database.
        :type mdb: motor.motor_asyncio.AsyncIOMotorDatabase
        """
        await mdb.snippets.update_one({"owner": self.owner, "name": self.name},
                                      {"$set": {"snippet": self.snippet}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        snippets = {}
        async for snippet in ctx.bot.mdb.snippets.find({"owner": str(ctx.author.id)}):
            snippets[snippet['name']] = snippet['snippet']
        return snippets


class Servsnippet(_SnippetBase):
    def __init__(self, name, snippet, server):
        super().__init__(name, snippet)
        self.server = server

    @classmethod
    def new(cls, name, snippet, server):
        """
        Creates a new server snippet.

        :param name: The name of the snippet.
        :type name: str
        :param snippet: The arguments the snippet is a shortcut of.
        :type snippet: str
        :param server: The owner of the snippet. Must be str.
        :type server: str
        """
        snippet = str(snippet)
        cls._checks(name, snippet)
        return cls(name, snippet, str(server))

    async def commit(self, mdb):
        """
        Writes the snippet to MongoDB, creating it if necessary.

        :param mdb: The database.
        :type mdb: motor.motor_asyncio.AsyncIOMotorDatabase
        """
        await mdb.servsnippets.update_one({"server": self.server, "name": self.name},
                                          {"$set": {"snippet": self.snippet}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        servsnippets = {}
        if ctx.guild:
            async for servsnippet in ctx.bot.mdb.servsnippets.find({"server": str(ctx.guild.id)}):
                servsnippets[servsnippet['name']] = servsnippet['snippet']
        return servsnippets
