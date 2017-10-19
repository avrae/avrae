"""
Created on Sep 23, 2016

@author: andrew
"""
import asyncio
import gc
import json
import logging
import re
import sys
import traceback
import uuid

from discord import Server
from discord.channel import PrivateChannel
from discord.enums import ChannelType
from discord.errors import NotFound
from discord.ext import commands

import credentials
from utils import checks
from utils.dataIO import DataIO

log = logging.getLogger(__name__)
memlog = logging.getLogger("memory")


class AdminUtils:
    """
    Administrative Utilities.
    """

    def __init__(self, bot):
        self.bot = bot
        self.muted = self.bot.db.not_json_get('muted', [])
        self.assume_dir_control_chan = None
        self.assume_dir_control_controller = None
        self.blacklisted_serv_ids = self.bot.db.not_json_get('blacklist', [])

        self.bot.loop.create_task(self.handle_pubsub())
        self.bot.db.pubsub.subscribe('server-info-requests', 'server-info-response',  # all-shard communication
                                     'admin-commands',  # 1-shard communication
                                     'asdc'  # assume direct control
                                     )
        self.requests = {}
        self.command_mem = {}
        self.mem_debug = self.bot.db.get("mem_debug", False)
        self.bot.loop.create_task(self.update_mem_state())
        self.bot.loop.create_task(self.collect_garbage())

        loglevels = self.bot.db.jget('loglevels', {})
        for logger, level in loglevels.items():
            try:
                logging.getLogger(logger).setLevel(level)
            except:
                log.warning(f"Failed to reset loglevel of {logger}")

    async def update_mem_state(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(10)
                self.mem_debug = self.bot.db.get("mem_debug", False)
        except asyncio.CancelledError:
            pass

    @commands.command(hidden=True)
    @checks.is_owner()
    async def blacklist(self, _id):
        self.blacklisted_serv_ids = self.bot.db.not_json_get('blacklist', [])
        self.blacklisted_serv_ids.append(_id)
        self.bot.db.not_json_set('blacklist', self.blacklisted_serv_ids)
        await self.bot.say(':ok_hand:')

    @commands.command(hidden=True)
    @checks.is_owner()
    async def restart(self):
        """Restarts Avrae. May fail sometimes due to bad programming on zhu.exe's end.
        Requires: Owner"""
        print("Shard {} going down for restart!".format(getattr(self.bot, 'shard_id', 0)))
        await self.bot.say("Byeeeeeee!")
        await self.bot.logout()
        sys.exit()

    @commands.command(hidden=True)
    @checks.is_owner()
    async def kill(self):
        await self.bot.say("I'm afraid I can't let you do that, Zhu.")

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
        out = self.discord_trim(out)
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
    async def clean_combat_keys(self):
        keys = self.bot.db._db.keys("*")
        keys = [k.decode() for k in keys]
        combat_keys = [k for k in keys if re.match(r'\d{18}\.avrae', k)]
        deleted = 0
        for k in combat_keys:
            self.bot.db.delete(k)
            print("deleted", k)
            deleted += 1
        await self.bot.say("Done! Deleted {} keys".format(deleted))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def migrate_cvars(self):
        cvars = self.bot.db.not_json_get('char_vars', {})
        num_users = 0
        num_cvars = 0
        for user_id, user_cvars in cvars.items():
            print("migrating cvars for {}...".format(user_id))
            user_chars = self.bot.db.not_json_get(user_id + '.characters', {})
            num_users += 1
            for character_id in user_cvars:
                print("  migrating character {}...".format(character_id))
                try:
                    stat_vars = {}
                    stat_vars.update(user_chars[character_id]['stats'])
                    stat_vars.update(user_chars[character_id]['levels'])
                    stat_vars['hp'] = user_chars[character_id]['hp']
                    stat_vars['armor'] = user_chars[character_id]['armor']
                    stat_vars.update(user_chars[character_id]['saves'])
                    user_chars[character_id]['stat_cvars'] = stat_vars
                except KeyError:
                    print("  error character not found")
                num_cvars += 1
            self.bot.db.not_json_set(user_id + '.characters', user_chars)
        await self.bot.say("Migrated {} cvars for {} users".format(num_cvars, num_users))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def backup_key(self, key):
        data = self.bot.db.get(key)
        if data:
            self.bot.db.set(f"{key}-backup", data)
            await self.bot.say('done')
        else:
            await self.bot.say('fail')

    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def code(self, ctx, *, code: str):
        """Arbitrarily runs code."""
        here = ctx.message.channel
        this = ctx.message

        def echo(out):
            self.msg(here, out)

        def rep(out):
            self.replace(this, out)

        def coro(coro):
            asyncio.ensure_future(coro)

        try:
            exec(code, globals(), locals())
        except:
            traceback.print_exc()
            out = self.discord_trim(traceback.format_exc())
            for o in out:
                await self.bot.send_message(ctx.message.channel, o)

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

    @commands.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def assume_direct_control(self, ctx, chan: str):
        """Assumes direct control of Avrae."""

        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])

            # remove `foo`
            return content.strip('` \n')

        self.assume_dir_control_chan = self.bot.get_channel(chan)
        self.assume_dir_control_controller = ctx.message.channel
        if self.assume_dir_control_chan is None:
            self.assume_dir_control_chan = await self.bot.get_user_info(chan)
        while True:
            response = await self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                       check=lambda m: m.content.startswith('`'))
            cleaned = cleanup_code(response.content)
            if cleaned in ('quit', 'exit', 'exit()'):
                await self.bot.say('Exiting.')
                self.assume_dir_control_chan = None
                return
            else:
                await self.bot.send_message(self.assume_dir_control_chan, cleaned)

    @commands.command(hidden=True, name="migrate_db", pass_context=True)
    @checks.is_owner()
    async def migrate_db(self, ctx):
        """Migrates entire db."""
        await self.bot.say("Are you absolutely, 100% sure you want to do this? **This will overwrite existing keys**.")
        msg = await self.bot.wait_for_message(author=ctx.message.author)
        if not msg.content == 'yes': return await self.bot.say("Aborting.")

        def _():
            old_db = DataIO(testing=True, test_database_url=credentials.old_database_url)
            for key in old_db._db.keys():
                try:
                    key = key.decode()
                    self.bot.db.set(key, old_db.get(key))
                    print(f"Migrated {key}")
                except Exception as e:
                    print(f"Error migrating {key}: {e}")

        await self.bot.loop.run_in_executor(None, _)
        await self.bot.say('done.')

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

    @commands.command(hidden=True, name="mem_debug")
    @checks.is_owner()
    async def _mem_debug(self):
        """Toggles global memory debug."""
        self.bot.db.set("mem_debug", not self.bot.db.get("mem_debug", False))
        await self.bot.say('done.')

    async def on_message(self, message):
        if message.author.id in self.muted:
            try:
                await self.bot.delete_message(message)
            except:
                pass
        if self.assume_dir_control_chan is not None:
            if isinstance(message.channel, PrivateChannel):
                if message.channel.user.id == self.assume_dir_control_chan.id:
                    await self.bot.send_message(self.assume_dir_control_controller,
                                                "**" + message.author.display_name + "**: " + message.content)
            elif message.channel.id == self.assume_dir_control_chan.id:
                await self.bot.send_message(self.assume_dir_control_controller,
                                            "**" + message.author.display_name + "**: " + message.content)

    async def on_server_join(self, server):
        if server.id in self.blacklisted_serv_ids: await self.bot.leave_server(server)
        bots = sum(1 for m in server.members if m.bot)
        members = len(server.members)
        ratio = bots / members
        if ratio >= 0.6 and members >= 20:
            log.info("Detected bot collection server ({}), ratio {}. Leaving.".format(server.id, ratio))
            try:
                await self.bot.send_message(server,
                                            "Please do not add me to bot collection servers. If you believe this is an error, please PM the bot author.")
            except:
                pass
            await asyncio.sleep(members / 200)
            await self.bot.leave_server(server)

    async def collect_garbage(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(3600)
                gc.collect()
        except asyncio.CancelledError:
            pass

    # async def on_command(self, command, ctx):
    #     if self.mem_debug:
    #         mem = psutil.Process().memory_full_info().uss
    #         if len(self.command_mem) > 30: self.command_mem = {} # let's not overflow
    #         self.command_mem[ctx.message.id] = mem # store mem usage before
    #         memlog.debug(f"Memory usage before processing command {command.qualified_name}: {mem}B")
    #
    # async def on_command_completion(self, command, ctx):
    #     if self.mem_debug:
    #         mem_before = self.command_mem[ctx.message.id]
    #         del self.command_mem[ctx.message.id]
    #         mem = psutil.Process().memory_full_info().uss
    #         mem_usage = mem - mem_before
    #         memlog.info(f"Total memory usage processing command {command.qualified_name}: {mem_usage}B")
    #
    # async def on_command_error(self, error, ctx):
    #     if self.mem_debug:
    #         mem_before = self.command_mem[ctx.message.id]
    #         del self.command_mem[ctx.message.id]
    #         mem = psutil.Process().memory_full_info().uss
    #         mem_usage = mem - mem_before
    #         memlog.info(f"Total memory usage processing command {ctx.command.qualified_name} (error): {mem_usage}B")

    def msg(self, dest, out):
        coro = self.bot.send_message(dest, out)
        asyncio.ensure_future(coro)

    def replace(self, msg, out):
        coro1 = self.bot.delete_message(msg)
        coro2 = self.bot.send_message(msg.channel, out)
        asyncio.ensure_future(coro1)
        asyncio.ensure_future(coro2)

    def discord_trim(self, str):
        result = []
        trimLen = 0
        lastLen = 0
        while trimLen <= len(str):
            trimLen += 1999
            result.append(str[lastLen:trimLen])
            lastLen += 1999
        return result

    async def send_logs(self):
        try:
            await self.bot.wait_until_ready()
            chan = self.bot.get_channel('298542945479557120')
            if chan is None: return
            while not self.bot.is_closed:
                await asyncio.sleep(3600)  # every hour
                await self.bot.send_file(chan, 'dicecloud.txt')
        except FileNotFoundError:
            pass
        except asyncio.CancelledError:
            pass

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
            await self.bot.create_invite(self.bot.get_server(server_id) or self.bot.get_channel(server_id).server)).url
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
                     'ping': self.__handle_ping_command}
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
                repsonse = CommandResponse(self.bot, reply_to, 'Failed to send message: ' + e)
            else:
                response = CommandResponse(self.bot, reply_to, "Sent message.")
            r = json.dumps(response.to_dict())
            self.bot.db.publish('admin-commands', r)

    async def __handle_ping_command(self, data):
        reply_to = data['uuid']
        response = CommandResponse(self.bot, reply_to, "Pong.")
        r = json.dumps(response.to_dict())
        self.bot.db.publish('admin-commands', r)


class PubSubMessage(object):
    def __init__(self, bot):
        self.shard_id = int(getattr(bot, 'shard_id', 0))
        self.uuid = str(uuid.uuid4())

    def to_dict(self):
        d = {}
        d['shard'] = self.shard_id
        d['uuid'] = self.uuid
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
