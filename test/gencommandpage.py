"""
Created on Jan 17, 2017

@author: andrew
"""

from discord.ext import commands
from discord.ext.commands.core import Group


def get_command_signature(command):
    """Retrieves the signature portion of the help page."""
    result = []
    prefix = '!'
    cmd = command
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
                result.append('&lt;{}&gt;'.format(name))

    return ' '.join(result)


def get_command_args_rows(command):
    out = ""
    params = command.clean_params
    if len(params) > 0:
        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str) else param.default is not None
                if should_print:
                    out += f"""        <tr>
          <td><kbd>{name}</kbd> (default {param.default}) - Detail each command argument here.</td>
            </tr>\n"""
                else:
                    out += f"""        <tr>
          <td><kbd>{name}</kbd> (optional) - Detail each command argument here.</td>
            </tr>\n"""
            elif param.kind == param.VAR_POSITIONAL:
                out += f"""        <tr>
          <td><kbd>{name}</kbd> (optional) - Detail each command argument here.</td>
            </tr>\n"""
            else:
                out += f"""        <tr>
          <td><kbd>{name}</kbd> - Detail each command argument here.</td>
            </tr>\n"""
    return out

def parse(commands_):
    out = []
    for command_name, command in commands_.items():
        if command.hidden: continue
        if command_name in command.aliases: continue
        if not isinstance(command, Group):
            args = get_command_args_rows(command)
            id_name = command.qualified_name.lower().replace(' ', '-')
            out.append((command_name, f"""
    <div class="panel panel-default">
      <div class="panel-heading" role="tab" id="{id_name}">
        <h4 class="panel-title">
          <a role="button" data-toggle="collapse" aria-expanded="false" aria-controls="{id_name}-c" href="#{id_name}-c">
            <b>{command.name}</b> - {command.short_doc.replace('<', '&lt;').replace('>', '&gt;') if command.short_doc else "TODO"} - {get_command_signature(command)}
          </a>
        </h4>
      </div>
      <div id="{id_name}-c" aria-labelledby="{id_name}" class="panel-collapse collapse" role="tabpanel">
        <div class="panel-body">
          <p>
            {command.help.replace('<', '&lt;').replace('>', '&gt;') if command.help else "TODO"}
          </p>
          <table class="table table-striped table-bordered">
            <thead>
            <tr>
                <th>Arguments</th>
            </tr>
            </thead>
            <tbody>
    {args}
            </tbody>
          </table>
          <p>
            <b>Example</b>: <code>{get_command_signature(command)}</code> <!-- TODO -->
          </p>
        </div>
      </div>
    </div>\n"""))
        else:  # I hate this formatting.
            subcommands = ''.join(i[1] for i in sorted(parse(command.commands), key=lambda l: l[0]))
            id_name = command.qualified_name.lower().replace(' ', '-')
            args = get_command_args_rows(command)
            out.append((command_name, f"""
<div class="panel panel-default">
  <div class="panel-heading" role="tab" id="{id_name}">
    <h4 class="panel-title">
      <a role="button" data-toggle="collapse" aria-expanded="false" aria-controls="{id_name}-c" href="#{id_name}-c">
        <b>{command.name}</b> - {command.short_doc.replace('<', '&lt;').replace('>', '&gt;') if command.short_doc else "TODO"} - {get_command_signature(command)}<br>
        <small>Has subcommands.</small>
      </a>
    </h4>
  </div>
  <div id="{id_name}-c" aria-labelledby="{id_name}" class="panel-collapse collapse" role="tabpanel">
    <div class="panel-body">
      <p>
        {command.help.replace('<', '&lt;').replace('>', '&gt;') if command.help else "TODO"}
      </p>
      <table class="table table-striped table-bordered">
        <thead>
        <tr>
            <th>Arguments</th>
        </tr>
        </thead>
        <tbody>
{args}
        </tbody>
      </table>
      <p>
        <b>Subcommands</b>
      </p>
      {subcommands}
      <p>
        <b>Example</b>: <code>{get_command_signature(command)}</code> <!-- TODO -->
      </p>
    </div>
  </div>
</div>\n"""))
    return out

class HelpGen:

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='helpgen', pass_context=True)
    async def _default_help_command(self, ctx):
        result = parse(ctx.bot.commands)
        r = ''.join(i[1] for i in sorted(result, key=lambda l: l[0]))
        with open('temp.html', 'w') as f:
            f.write(r)