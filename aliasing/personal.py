"""
Personal aliases and snippets. Unrelated to the workshop.
"""
import abc

from aliasing.constants import ALIAS_SIZE_LIMIT, SNIPPET_SIZE_LIMIT
from cogs5e.models.errors import InvalidArgument


class _CustomizationBase(abc.ABC):
    def __init__(self, name, code, owner):
        self.name = name
        self.code = code
        self.owner = owner

    @classmethod
    def new(cls, name, code, owner):
        """
        Creates a new customization.

        :param name: The name of the customization.
        :type name: str
        :param code: The commands that name is an alias of.
        :type code: str
        :param owner: The owner of the customization (user/guild). Must be str.
        :type owner: str
        """
        code = str(code)
        cls._checks(name, code)
        return cls(name, code, str(owner))

    async def commit(self, mdb):
        """
        Writes the customization to MongoDB, creating it if necessary.

        :param mdb: The database.
        :type mdb: motor.motor_asyncio.AsyncIOMotorDatabase
        """
        raise NotImplementedError

    async def delete(self, mdb):
        """
        Deletes this customization from the database.
        """
        raise NotImplementedError

    @staticmethod
    async def get_ctx_map(ctx):
        """
        Returns a dict mapping {name: command} for all customizations in scope.
        """
        raise NotImplementedError

    @classmethod
    async def get_named(cls, name, ctx):
        """
        Returns the customization named *name* in *ctx*, or None if not applicable.
        """
        raise NotImplementedError

    @classmethod
    async def get_code_for(cls, name, ctx):
        """
        Returns the code for the customization named *name* in *ctx*, or None if not applicable.
        """
        cust = await cls.get_named(name, ctx)
        if not cust:
            return None
        return cust.code

    @staticmethod
    def _checks(name, code):
        """
        Runs creation limit checks.

        :raises InvalidArgument: If any check fails.
        """
        raise NotImplementedError


class _AliasBase(_CustomizationBase, abc.ABC):
    @staticmethod
    def _checks(name, code):
        if len(code) > ALIAS_SIZE_LIMIT:
            raise InvalidArgument(f"Aliases must be shorter than {ALIAS_SIZE_LIMIT} characters.")
        if ' ' in name:
            raise InvalidArgument("Alias names cannot contain spaces.")


class _SnippetBase(_CustomizationBase, abc.ABC):
    @staticmethod
    def _checks(name, code):
        if len(code) > SNIPPET_SIZE_LIMIT:
            raise InvalidArgument(f"Snippets must be shorter than {SNIPPET_SIZE_LIMIT} characters.")
        if len(name) < 2:
            raise InvalidArgument("Snippet names must be at least 2 characters long.")
        if ' ' in name:
            raise InvalidArgument("Snippet names cannot contain spaces.")


class Alias(_AliasBase):
    async def commit(self, mdb):
        await mdb.aliases.update_one({"owner": self.owner, "name": self.name},
                                     {"$set": {"commands": self.code}}, upsert=True)

    async def delete(self, mdb):
        await mdb.aliases.delete_one({"owner": self.owner, "name": self.name})

    @staticmethod
    async def get_ctx_map(ctx):
        aliases = {}
        async for alias in ctx.bot.mdb.aliases.find({"owner": str(ctx.author.id)}):
            aliases[alias['name']] = alias['commands']
        return aliases

    @classmethod
    async def get_named(cls, name, ctx):
        doc = await ctx.bot.mdb.aliases.find_one({"owner": str(ctx.author.id), "name": name})
        if doc:
            return cls(doc['name'], doc['commands'], doc['owner'])
        return None


class Servalias(_AliasBase):
    async def commit(self, mdb):
        await mdb.servaliases.update_one({"server": self.owner, "name": self.name},
                                         {"$set": {"commands": self.code}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        servaliases = {}
        async for servalias in ctx.bot.mdb.servaliases.find({"server": str(ctx.guild.id)}):
            servaliases[servalias['name']] = servalias['commands']
        return servaliases

    @classmethod
    async def get_named(cls, name, ctx):
        doc = await ctx.bot.mdb.servaliases.find_one({"server": str(ctx.guild.id), "name": name})
        if doc:
            return cls(doc['name'], doc['commands'], doc['server'])
        return None


class Snippet(_SnippetBase):
    async def commit(self, mdb):
        await mdb.snippets.update_one({"owner": self.owner, "name": self.name},
                                      {"$set": {"snippet": self.code}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        snippets = {}
        async for snippet in ctx.bot.mdb.snippets.find({"owner": str(ctx.author.id)}):
            snippets[snippet['name']] = snippet['snippet']
        return snippets

    @classmethod
    async def get_named(cls, name, ctx):
        doc = await ctx.bot.mdb.snippets.find_one({"owner": str(ctx.author.id), "name": name})
        if doc:
            return cls(doc['name'], doc['snippet'], doc['owner'])
        return None


class Servsnippet(_SnippetBase):
    async def commit(self, mdb):
        await mdb.servsnippets.update_one({"server": self.owner, "name": self.name},
                                          {"$set": {"snippet": self.code}}, upsert=True)

    @staticmethod
    async def get_ctx_map(ctx):
        servsnippets = {}
        if ctx.guild:
            async for servsnippet in ctx.bot.mdb.servsnippets.find({"server": str(ctx.guild.id)}):
                servsnippets[servsnippet['name']] = servsnippet['snippet']
        return servsnippets

    @classmethod
    async def get_named(cls, name, ctx):
        doc = await ctx.bot.mdb.servsnippets.find_one({"server": str(ctx.guild.id), "name": name})
        if doc:
            return cls(doc['name'], doc['snippet'], doc['server'])
        return None
