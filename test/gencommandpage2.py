import inspect
import itertools
import json

from discord.ext import commands
from discord.ext.commands import GroupMixin


def filter_command_list(_commands):
    """Returns a filtered list of commands based on the two attributes
    provided, :attr:`show_check_failure` and :attr:`show_hidden`. Also
    filters based on if :meth:`is_cog` is valid.

    Returns
    --------
    iterable
        An iterable with the filter being applied. The resulting value is
        a (key, value) tuple of the command name and the command itself.
    """

    def predicate(tuple):
        cmd = tuple[1]

        if cmd.hidden:
            return False
        return True

    iterator = _commands.items()
    return filter(predicate, iterator)


class HelpGen:

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='helpgen', pass_context=True)
    async def _default_help_command(self, ctx):
        result = self.parse(ctx.bot.commands)
        with open('temp.json', 'w') as f:
            json.dump(result, f)
        await self.bot.say("Saved to `temp.json`.")



    def parse(self, _commands):
        out = {"modules": []}

        def category(tup):
            cog = tup[1].cog_name
            # we insert the zero width space there to give it approximate
            # last place sorting position.
            return cog if cog is not None else '\u200bNo Category'

        data = sorted(filter_command_list(_commands), key=category)
        for category, commands in itertools.groupby(data, key=category):
            catdata = {
                "name": category,
                "desc": inspect.getdoc(self.bot.get_cog(category)),
                "commands": self.parse_commands(list(commands))
            }
            out['modules'].append(catdata)

        return out

    def parse_commands(self, _commands):
        out = []
        for name, command in _commands:
            if name in command.aliases:
                # skip aliases
                continue
            cmd = {
                "name": name,
                "short": command.short_doc or "TODO",
                "docs": command.help or "TODO",
                "args": self.parse_command_args(command),
                "signature": self.get_command_signature(command),
                "subcommands": [],
                "example": ""
            }
            if isinstance(command, GroupMixin):
                cmd['subcommands'] = self.parse_commands(filter_command_list(command.commands))
            out.append(cmd)
        return out

    def parse_command_args(self, cmd):
        out = []
        params = cmd.clean_params
        if len(params) > 0:
            for name, param in params.items():
                data = {
                    "name": name,
                    "required": False,
                    "default": None,
                    "multiple": False,
                    "desc": ""
                }
                if param.default is not param.empty:
                    # We don't want None or '' to trigger the [name=value] case and instead it should
                    # do [name] since [name=None] or [name=] are not exactly useful for the user.
                    should_print = param.default if isinstance(param.default, str) else param.default is not None
                    if should_print:
                        data['default'] = param.default
                elif param.kind == param.VAR_POSITIONAL:
                    data['multiple'] = True
                else:
                    data['required'] = True
                out.append(data)
        return out

    def get_command_signature(self, cmd):
        """Retrieves the signature portion of the help page."""
        prefix = "!"
        result = []
        parent = cmd.full_parent_name
        if len(cmd.aliases) > 0:
            aliases = '|'.join(cmd.aliases)
            fmt = '{0}[{1.name}|{2}]'
            if parent:
                fmt = '{0}{3} [{1.name}|{2}]'
            result.append(fmt.format(prefix, cmd, aliases, parent))
        else:
            name = prefix + cmd.name if not parent else prefix + parent + ' ' + cmd.name
            result.append(name)

        params = cmd.clean_params
        if len(params) > 0:
            for name, param in params.items():
                if param.default is not param.empty:
                    # We don't want None or '' to trigger the [name=value] case and instead it should
                    # do [name] since [name=None] or [name=] are not exactly useful for the user.
                    should_print = param.default if isinstance(param.default, str) else param.default is not None
                    if should_print:
                        result.append('[{}={}]'.format(name, param.default))
                    else:
                        result.append('[{}]'.format(name))
                elif param.kind == param.VAR_POSITIONAL:
                    result.append('[{}...]'.format(name))
                else:
                    result.append('<{}>'.format(name))

        return ' '.join(result)


def setup(bot):
    bot.add_cog(HelpGen(bot))
