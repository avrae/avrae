"""
{
  "modules": [
    {
      "name": "string",
      "desc": "string",
      "commands": [
        {
          "name": "string",
          "short": "string",
          "docs": "string",
          "args": [
            {
              "name": "string",
              "required": true,
              "default": null,
              "multiple": false,
              "desc": ""
            }
          ],
          "signature": "!autochar <level>",
          "subcommands": [],
          "example": ""
        }
      ]
    }
  ]
}
"""

import argparse
import itertools
import json
import os
import sys

from disnake.ext.commands import Group

# path hack to import from parent folder
sys.path.insert(1, os.path.join(sys.path[0], ".."))

parser = argparse.ArgumentParser()
parser.add_argument("-o", help="The file to output to.")


def get_command_signature(command):
    parent = command.full_parent_name
    if len(command.aliases) > 0:
        aliases = "|".join(command.aliases)
        fmt = "[%s|%s]" % (command.name, aliases)
        if parent:
            fmt = parent + " " + fmt
        alias = fmt
    else:
        alias = command.name if not parent else parent + " " + command.name

    return "!%s %s" % (alias, command.signature)


def parse_command_args(command):
    args = []

    params = command.clean_params
    if not params:
        return args

    for name, param in params.items():
        arg_meta = {"name": name, "required": True, "default": None, "multiple": False, "desc": ""}

        if param.default is not param.empty:
            arg_meta["required"] = False
            # We don't want None or '' to trigger the [name=value] case and instead it should
            # do [name] since [name=None] or [name=] are not exactly useful for the user.
            should_print = param.default if isinstance(param.default, str) else param.default is not None
            if should_print:
                arg_meta["default"] = param.default
        elif param.kind == param.VAR_POSITIONAL:
            arg_meta["required"] = False
            arg_meta["multiple"] = True
        elif command._is_typing_optional(param.annotation):
            arg_meta["required"] = False
        args.append(arg_meta)

    return args


def parse_command(command):
    """
    :type command disnake.ext.commands.Command
    """
    subcommands = []
    if isinstance(command, Group):
        commands = sorted(command.commands, key=lambda c: c.name)
        for subcommand in commands:
            subcommands.append(parse_command(subcommand))

    arguments = parse_command_args(command)
    command_meta = {
        "name": command.name,
        "short": command.short_doc,
        "docs": command.help,
        "args": arguments,
        "signature": get_command_signature(command),
        "subcommands": subcommands,
        "example": "",
    }
    return command_meta


def parse_module(module, commands):
    commands = sorted(commands, key=lambda c: c.name)
    parsed_commands = []

    for command in commands:
        parsed_commands.append(parse_command(command))

    if commands[0].cog is not None:
        module_meta = {"name": module, "desc": commands[0].cog.description, "commands": parsed_commands}
    else:
        module_meta = {"name": "Uncategorized", "desc": "Commands not in a module.", "commands": parsed_commands}
    return module_meta


def main(out="commands.json"):
    from dbot import bot

    modules = []

    # helpers
    no_category = "\u200bUncategorized"

    def get_category(command):
        cog = command.cog
        return cog.qualified_name if cog is not None else no_category

    # build an iterator of (category, commands)
    iterator = filter(lambda c: not c.hidden, bot.commands)
    filtered = sorted(iterator, key=get_category)
    to_iterate = itertools.groupby(filtered, key=get_category)

    # add modules to output
    for module, commands in to_iterate:
        modules.append(parse_module(module, commands))

    with open(out, "w") as f:
        json.dump({"modules": modules}, f)


if __name__ == "__main__":
    args, unknown = parser.parse_known_args()
    main(args.o or "commands.json")
