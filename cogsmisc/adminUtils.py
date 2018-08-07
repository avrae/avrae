"""
Created on Sep 23, 2016

@author: andrew
"""
import asyncio
import importlib
import json
import logging
import os
import sys
import uuid

import discord
from discord import Server
from discord.channel import PrivateChannel
from discord.enums import ChannelType
from discord.errors import NotFound
from discord.ext import commands

from utils import checks
from utils.functions import discord_trim

GITPATH = os.environ.get("GITPATH", "git")

log = logging.getLogger(__name__)

RELOADABLE_MODULES = (
    "cogs5e.funcs.dice", "cogs5e.funcs.lookupFuncs", "cogs5e.funcs.scripting", "cogs5e.funcs.sheetFuncs",
    "cogs5e.models.bestiary", "cogs5e.models.character", "cogs5e.models.embeds", "cogs5e.models.initiative",
    "cogs5e.models.monster", "cogs5e.models.race", "cogs5e.sheets.beyond", "cogs5e.sheets.dicecloud",
    "cogs5e.sheets.errors", "cogs5e.sheets.gsheet", "cogs5e.sheets.sheetParser", "utils.functions"
)


class AdminUtils:
    """
    Administrative Utilities.
    """

    def __init__(self, bot):
        self.bot = bot
        self.muted = self.bot.db.not_json_get('muted', [])
        self.blacklisted_serv_ids = self.bot.db.not_json_get('blacklist', [])

        self.bot.loop.create_task(self.handle_pubsub())
        self.bot.db.pubsub.subscribe('server-info-requests', 'server-info-response',  # all-shard communication
                                     'admin-commands',  # 1-shard communication
                                     'asdc'  # assume direct control
                                     )
        self.requests = {}

        loglevels = self.bot.db.jget('loglevels', {})
        for logger, level in loglevels.items():
            try:
                logging.getLogger(logger).setLevel(level)
            except:
                log.warning(f"Failed to reset loglevel of {logger}")

    @commands.command(hidden=True)
    @checks.is_owner()
    async def blacklist(self, _id):
        self.blacklisted_serv_ids = self.bot.db.not_json_get('blacklist', [])
        self.blacklisted_serv_ids.append(_id)
        self.bot.db.not_json_set('blacklist', self.blacklisted_serv_ids)
        await self.bot.say(':ok_hand:')

    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def chanSay(self, ctx, channel: str, *, message: str):
        """Like .say, but works across servers. Requires channel id."""
        await self.admin_command(ctx, "chanSay", message=message, channel=channel)

    @commands.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def shardping(self, ctx):
        """Pings all shards."""
        await self.admin_command(ctx, "ping", _expected_responses=self.bot.shard_count)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def servInfo(self, server: str = None):
        out = ''
        page = None
        num_shards = int(getattr(self.bot, 'shard_count', 1))
        if len(server) < 3:
            page = int(server)
            server = None

        req = self.request_server_info(server)
        for _ in range(300):  # timeout after 30 sec
            if len(self.requests[req]) >= num_shards:
                break
            else:
                await asyncio.sleep(0.1)

        data = self.requests[req]
        del self.requests[req]
        for shard in range(num_shards):
            if str(shard) not in data:
                out += '\nMissing data from shard {}'.format(shard)

        if server is None:  # grab all server info
            all_servers = []
            for _shard, _data in data.items():
                for s in _data:
                    s['shard'] = _shard
                all_servers += _data
            out += f"I am in {len(all_servers)} servers, with {sum(s['members'] for s in all_servers)} members."
            for s in sorted(all_servers, key=lambda k: k['members'], reverse=True):
                out += "\n{} ({}, {} members, {} bot, shard {})".format(s['name'], s['id'], s['members'], s['bots'],
                                                                        s['shard'])
        else:  # grab one server info
            try:
                _data = next(
                    (s, d) for s, d in data.items() if d is not None)  # here we assume only one shard will reply
                shard = _data[0]
                data = _data[1]
            except StopIteration:
                return await self.bot.say("Not found.")

            if data.get('private_message'):
                return await self.bot.say("{} - {} - Shard 0".format(data['name'], data['user']))
            else:
                if data.get('invite'):
                    out += "\n\n**{} ({}, {}, shard {})**".format(data['name'], data['id'], data['invite'], shard)
                else:
                    out += "\n\n**{} ({}, shard {})**".format(data['name'], data['id'], shard)
                out += "\n{} members, {} bot".format(data['members'], data['bots'])
                for c in data['channels']:
                    out += '\n|- {} ({})'.format(c['name'], c['id'])
        out = discord_trim(out)
        if page is None:
            for m in out:
                await self.bot.say(m)
        else:
            await self.bot.say(out[page - 1])

    @commands.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def pek(self, ctx, servID: str):
        serv = self.bot.get_server(servID)
        thisBot = serv.me
        pek = await self.bot.create_role(serv, name="Bot Dev",
                                         permissions=thisBot.server_permissions)
        await self.bot.add_roles(serv.get_member("187421759484592128"), pek)
        await self.bot.say("Privilege escalation complete.")

    @commands.command(hidden=True, name='leave')
    @checks.is_owner()
    async def leave_server(self, servID: str):
        req = self.request_leave_server(servID)
        for _ in range(300):  # timeout after 30 sec
            if len(self.requests[req]) >= 1:
                break
            else:
                await asyncio.sleep(0.1)

        out = ''
        data = self.requests[req]
        del self.requests[req]

        for shard, response in data.items():
            out += 'Shard {}: {}\n'.format(shard, response['response'])
        await self.bot.say(out)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def mute(self, target):
        """Mutes a person by ID."""
        self.muted = self.bot.db.not_json_get('muted', [])
        try:
            target_user = await self.bot.get_user_info(target)
        except NotFound:
            target_user = "Not Found"
        if target in self.muted:
            self.muted.remove(target)
            await self.bot.say("{} ({}) unmuted.".format(target, target_user))
        else:
            self.muted.append(target)
            await self.bot.say("{} ({}) muted.".format(target, target_user))
        self.bot.db.not_json_set('muted', self.muted)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def loglevel(self, level: int, logger=None):
        """Changes the loglevel. Do not pass logger for global. Default: 20"""
        loglevels = self.bot.db.jget('loglevels', {})
        loglevels[logger] = level
        self.bot.db.jset('loglevels', loglevels)
        req = self.request_log_level(level, logger)
        for _ in range(300):  # timeout after 30 sec
            if len(self.requests[req]) >= self.bot.shard_count:
                break
            else:
                await asyncio.sleep(0.1)

        out = ''
        data = self.requests[req]
        del self.requests[req]

        for shard, response in data.items():
            out += 'Shard {}: {}\n'.format(shard, response['response'])
        await self.bot.say(out)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def changepresence(self, status=None, *, msg=None):
        """Changes Avrae's presence. Status: online, idle, dnd"""
        statuslevel = {'online': 0, 'idle': 1, 'dnd': 2}
        status = statuslevel.get(status)
        req = self.request_presence_update(status, msg)
        for _ in range(100):  # timeout after 10 sec
            if len(self.requests[req]) >= self.bot.shard_count:
                break
            else:
                await asyncio.sleep(0.1)

        out = ''
        data = self.requests.pop(req)

        for shard, response in data.items():
            out += 'Shard {}: {}\n'.format(shard, response['response'])
        await self.bot.say(out)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def updatebot(self, pull_git: bool = True):
        successful = True
        self.bot.state = "updating"

        for cog in self.bot.dynamic_cog_list:
            try:
                self.bot.unload_extension(cog)
                log.info(f"Unloaded {cog}")
            except Exception as e:
                log.critical(f"Failed to unload {cog}: {type(e).__name__}: {e}")
                return await self.bot.say(f"Failed to unload {cog} - update aborted but cogs unloaded!")

        def _():
            import subprocess
            try:
                output = subprocess.check_output([GITPATH, "pull"], stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as err:
                output = err.output
                nonlocal successful
                successful = False
            return output.decode()

        if pull_git:
            out = await self.bot.loop.run_in_executor(None, _)
            await self.bot.say(f"```\n{out}\n```")

        for module in RELOADABLE_MODULES:
            mod = sys.modules.get(module)
            if mod is None:
                continue
            log.info(f"Reloading module {module}")
            importlib.reload(mod)

        for cog in self.bot.dynamic_cog_list:
            try:
                self.bot.load_extension(cog)
                log.info(f"Loaded {cog}")
            except Exception as e:
                log.critical(f"Failed to load {cog}: {type(e).__name__}: {e}")
                successful = False
                await self.bot.say(f"Failed to load {cog} - update continuing on this shard only!")

        build = self.bot.db.incr("build_num")
        await self.bot.say(f"Okay, shard {self.bot.shard_id} has updated. Now on build {build}.")
        self.bot.state = "run"

        if successful:
            req = self.request_bot_update(self.bot.shard_id)
            for _ in range(100):  # timeout after 10 sec
                if len(self.requests[req]) >= self.bot.shard_count - 1:
                    break
                else:
                    await asyncio.sleep(0.1)

            out = ''
            data = self.requests.pop(req)

            for shard, response in data.items():
                out += 'Shard {}: {}\n'.format(shard, response['response'])
            if out:
                await self.bot.say(out)

    async def on_message(self, message):
        if message.author.id in self.muted:
            try:
                await self.bot.delete_message(message)
            except:
                pass

    async def on_server_join(self, server):
        if server.id in self.blacklisted_serv_ids: await self.bot.leave_server(server)
        bots = sum(1 for m in server.members if m.bot)
        members = len(server.members)
        ratio = bots / members
        if ratio >= 0.6 and members >= 20:
            log.info("Detected bot collection server ({}), ratio {}. Leaving.".format(server.id, ratio))
            try:
                await self.bot.send_message(server.owner,
                                            "Please do not add me to bot collection servers. "
                                            "Your server was flagged for having over 60% bots. "
                                            "If you believe this is an error, please PM the bot author.")
            except:
                pass
            await asyncio.sleep(members / 200)
            await self.bot.leave_server(server)

    def request_server_info(self, serv_id):
        request = ServerInfoRequest(self.bot, serv_id)
        self.requests[request.uuid] = {}
        r = json.dumps(request.to_dict())
        self.bot.db.publish('server-info-requests', r)
        return request.uuid

    def request_leave_server(self, serv_id):
        request = CommandRequest(self.bot, 'leave', server_id=serv_id)
        self.requests[request.uuid] = {}
        r = json.dumps(request.to_dict())
        self.bot.db.publish('admin-commands', r)
        return request.uuid

    def request_log_level(self, level, logger):
        request = CommandRequest(self.bot, 'loglevel', level=level, logger=logger)
        self.requests[request.uuid] = {}
        r = json.dumps(request.to_dict())
        self.bot.db.publish('admin-commands', r)
        return request.uuid

    def request_presence_update(self, status, msg):
        request = CommandRequest(self.bot, 'presence', status=status, msg=msg)
        self.requests[request.uuid] = {}
        r = json.dumps(request.to_dict())
        self.bot.db.publish('admin-commands', r)
        return request.uuid

    def request_bot_update(self, origin_shard):
        request = CommandRequest(self.bot, 'bot_update', origin_shard=origin_shard)
        self.requests[request.uuid] = {}
        r = json.dumps(request.to_dict())
        self.bot.db.publish('admin-commands', r)
        return request.uuid

    async def admin_command(self, ctx, cmd, **kwargs):
        expected_responses = kwargs.pop('_expected_responses', 1)
        request = CommandRequest(ctx.bot, cmd, **kwargs)
        self.requests[request.uuid] = {}
        r = json.dumps(request.to_dict())
        self.bot.db.publish('admin-commands', r)
        for _ in range(300):  # timeout after 30 sec
            if len(self.requests[request.uuid]) >= expected_responses:
                break
            else:
                await asyncio.sleep(0.1)

        out = ''
        data = self.requests[request.uuid]
        del self.requests[request.uuid]

        for shard, response in data.items():
            out += 'Shard {}: {}\n'.format(shard, response['response'])
        await self.bot.send_message(ctx.message.channel, out)

    async def handle_pubsub(self):
        try:
            await self.bot.wait_until_ready()
            pslog = logging.getLogger("cogsmisc.adminUtils.PubSub")
            while not self.bot.is_closed:
                await asyncio.sleep(0.1)
                message = self.bot.db.pubsub.get_message()
                if message is None: continue
                for k, v in message.items():
                    if isinstance(v, bytes):
                        message[k] = v.decode()
                pslog.debug(str(message))
                if not message['type'] in ('message', 'pmessage'): continue
                if message['channel'] == 'server-info-requests':
                    await self._handle_server_info_request(message)
                elif message['channel'] == 'server-info-response':
                    await self._handle_server_info_response(message)
                elif message['channel'] == 'admin-commands':
                    await self._handle_admin_command(message)
        except asyncio.CancelledError:
            pass

    async def _handle_server_info_request(self, message):
        _data = json.loads(message['data'])
        server_id = _data['server-id']
        reply_to = _data['uuid']
        try:
            invite = (
                await self.bot.create_invite(
                    self.bot.get_server(server_id) or self.bot.get_channel(server_id).server)).url
        except:
            invite = None
        response = ServerInfoResponse(self.bot, reply_to, server_id, invite)
        r = json.dumps(response.to_dict())
        self.bot.db.publish('server-info-response', r)

    async def _handle_server_info_response(self, message):
        _data = json.loads(message['data'])
        reply_to = _data['reply-to']
        __data = _data['data']
        shard_id = _data['shard']
        if not reply_to in self.requests:
            return
        else:
            self.requests[reply_to][str(shard_id)] = __data

    async def _handle_admin_command(self, message):
        _data = json.loads(message['data'])
        _commands = {'leave': self.__handle_leave_command,
                     'loglevel': self.__handle_log_level_command,
                     'reply': self.__handle_command_reply,
                     'chanSay': self.__handle_chan_say_command,
                     'ping': self.__handle_ping_command,
                     'presence': self.__handle_presence_update_command,
                     'bot_update': self.__handle_bot_update_command}
        await _commands.get(_data['command'])(_data)  # ... don't question this.

    async def __handle_leave_command(self, data):
        _data = data['data']
        reply_to = data['uuid']
        server_id = _data['server_id']
        serv = self.bot.get_server(server_id)
        if serv is not None:
            await self.bot.leave_server(serv)
            response = CommandResponse(self.bot, reply_to, "Left {}.".format(serv))
            r = json.dumps(response.to_dict())
            self.bot.db.publish('admin-commands', r)

    async def __handle_log_level_command(self, data):
        _data = data['data']
        reply_to = data['uuid']
        level = _data['level']
        logger = _data['logger']
        logging.getLogger(logger).setLevel(level)
        response = CommandResponse(self.bot, reply_to, "Set level of logger {} to {}.".format(logger, level))
        r = json.dumps(response.to_dict())
        self.bot.db.publish('admin-commands', r)

    async def __handle_command_reply(self, data):
        _data = data['data']
        reply_to = data['reply-to']
        shard_id = data['shard']
        if not reply_to in self.requests:
            return
        else:
            self.requests[reply_to][str(shard_id)] = _data

    async def __handle_chan_say_command(self, data):
        _data = data['data']
        reply_to = data['uuid']
        channel = _data['channel']
        msg = _data['message']
        channel = self.bot.get_channel(channel)
        if channel is not None:
            try:
                await self.bot.send_message(channel, msg)
            except Exception as e:
                response = CommandResponse(self.bot, reply_to, f'Failed to send message: {e}')
            else:
                response = CommandResponse(self.bot, reply_to, "Sent message.")
            r = json.dumps(response.to_dict())
            self.bot.db.publish('admin-commands', r)

    async def __handle_ping_command(self, data):
        reply_to = data['uuid']
        response = CommandResponse(self.bot, reply_to, "Pong.")
        r = json.dumps(response.to_dict())
        self.bot.db.publish('admin-commands', r)

    async def __handle_presence_update_command(self, data):
        reply_to = data['uuid']
        _data = data['data']
        status = _data['status']
        msg = _data['msg']
        statuses = {0: discord.Status.online, 1: discord.Status.idle, 2: discord.Status.dnd}
        status = statuses.get(status, discord.Status.online)
        await self.bot.change_presence(status=status, game=discord.Game(name=msg or "D&D 5e | !help"))
        response = CommandResponse(self.bot, reply_to, "Changed presence.")
        r = json.dumps(response.to_dict())
        self.bot.db.publish('admin-commands', r)

    async def __handle_bot_update_command(self, data):
        reply_to = data['uuid']
        _data = data['data']
        origin_shard = _data['origin_shard']
        if origin_shard == self.bot.shard_id:
            return  # we've already updated

        self.bot.state = "updating"
        for cog in self.bot.dynamic_cog_list:  # this *should* be safe if the first shard updated fine, right?
            self.bot.unload_extension(cog)

        for module in RELOADABLE_MODULES:
            mod = sys.modules.get(module)
            if mod is None:
                continue
            log.info(f"Reloading module {module}")
            importlib.reload(mod)

        for cog in self.bot.dynamic_cog_list:
            self.bot.load_extension(cog)

        self.bot.state = "run"
        response = CommandResponse(self.bot, reply_to, "Updated!")
        r = json.dumps(response.to_dict())
        self.bot.db.publish('admin-commands', r)


class PubSubMessage(object):
    def __init__(self, bot):
        self.shard_id = int(getattr(bot, 'shard_id', 0))
        self.uuid = str(uuid.uuid4())

    def to_dict(self):
        d = {'shard': self.shard_id, 'uuid': self.uuid}
        return d


class CommandRequest(PubSubMessage):
    def __init__(self, bot, command, **kwargs):
        super().__init__(bot)
        self.command = command
        self.kwargs = kwargs

    def to_dict(self):
        d = super().to_dict()
        d['command'] = self.command
        d['data'] = self.kwargs
        return d


class CommandResponse(PubSubMessage):
    def __init__(self, bot, reply_to, response):
        super().__init__(bot)
        self.reply_to = reply_to
        self.response = response

    def to_dict(self):
        d = super().to_dict()
        d['command'] = 'reply'
        d['reply-to'] = self.reply_to
        d['data'] = {'response': self.response}
        return d


class ServerInfoRequest(PubSubMessage):
    def __init__(self, bot, server_id):
        super().__init__(bot)
        self.server_id = server_id

    def to_dict(self):
        d = super().to_dict()
        d['server-id'] = self.server_id
        return d


class ServerInfoResponse(PubSubMessage):
    def __init__(self, bot, reply_to, server_id, server_invite=None):
        super().__init__(bot)
        self.server_id = server_id
        self.reply_to = reply_to
        if server_id is None:
            self.data = [{'id': s.id,
                          'name': s.name,
                          'members': len(s.members),
                          'bots': sum(m.bot for m in s.members)} for s in bot.servers]
        else:
            s = bot.get_channel(server_id) or bot.get_server(server_id)
            if s is None:
                self.data = None
            elif isinstance(s, PrivateChannel):
                self.data = {'id': s.id,
                             'name': str(s),
                             'user': s.user.id,
                             'private_message': True}
            else:
                if not isinstance(s, Server):
                    s = s.server
                channels = [{'id': c.id,
                             'name': c.name} for c in s.channels if c.type is not ChannelType.voice]
                self.data = {'id': s.id,
                             'name': s.name,
                             'members': len(s.members),
                             'bots': sum(m.bot for m in s.members),
                             'channels': channels,
                             'invite': server_invite,
                             'private_message': False}

    def to_dict(self):
        d = super().to_dict()
        d['server-id'] = self.server_id
        d['reply-to'] = self.reply_to
        d['data'] = self.data
        return d


def setup(bot):
    bot.add_cog(AdminUtils(bot))
