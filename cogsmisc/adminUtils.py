'''
Created on Sep 23, 2016

@author: andrew
'''
import asyncio
import copy
import json
import os
import re
import sys
import traceback
import uuid

import discord
from discord.channel import PrivateChannel
from discord.enums import ChannelType
from discord.errors import NotFound
from discord.ext import commands

from utils import checks


class AdminUtils:
    '''
    Administrative Utilities.
    '''


    def __init__(self, bot):
        self.bot = bot
        self.muted = self.bot.db.not_json_get('muted', [])
        self.assume_dir_control_chan = None
        self.assume_dir_control_controller = None
        self.blacklisted_serv_ids = self.bot.db.not_json_get('blacklist', [])
        
        self.bot.loop.create_task(self.handle_pubsub())
        self.bot.db.pubsub.subscribe('server-info-requests', 'server-info-response')
        self.server_info = {}
        
    
    @commands.command(hidden=True)
    @checks.is_owner()
    async def blacklist(self, _id):
        self.blacklisted_serv_ids = self.bot.db.not_json_get('blacklist', [])
        self.blacklisted_serv_ids.append(_id)
        self.bot.db.not_json_set('blacklist', self.blacklisted_serv_ids)
        await self.bot.say(':ok_hand:')
    
    @commands.command(hidden=True, aliases=['kill'])
    @checks.is_owner()
    async def restart(self):
        """Restarts Avrae. May fail sometimes due to bad programming on zhu.exe's end.
        Requires: Owner"""
        print("Shard {} going down for restart!".format(getattr(self.bot, 'shard_id', 0)))
        await self.bot.say("Byeeeeeee!")
        await self.bot.logout()
        sys.exit()
            
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def chanSay(self, ctx, channel : str, * , message : str):
        """Like .say, but works across servers. Requires channel id."""
        channel = self.bot.get_channel(channel)
        try:
            await self.bot.send_message(channel, message)
        except Exception as e:
            await self.bot.say('Failed to send message: ' + e)
            
        
    @commands.command(hidden=True)
    @checks.is_owner()
    async def announce(self, *, msg : str):
        for s in [se for se in self.bot.servers]:
            try:
                await self.bot.send_message(s, msg)
            except:
                pass
        
    @commands.command(hidden=True)
    @checks.is_owner()
    async def servInfo(self, server:str=None):
        out = ''
        page = None
        num_shards = int(getattr(self.bot, 'shard_count', 1))
        if len(server) < 3:
            page = int(server)
            server = None
            
        req = self.request_server_info(server)
        for _ in range(300): # timeout after 30 sec
            if len(self.server_info[req]) >= num_shards: break
            else: await asyncio.sleep(0.1)
        
        data = self.server_info[req]
        del self.server_info[req]
        for shard in range(num_shards):
            if shard not in data:
                out += '\nMissing data from shard {}'.format(shard)
        
        if server is None: # grab all server info
            all_servers = []
            for _shard, _data in data.items():
                _data['shard'] = _shard
                all_servers += _data
            for s in sorted(all_servers, key=lambda k: k['members'], reverse=True):
                out += "\n{} ({}, {} members, {} bot, shard {})".format(s['name'], s['id'], s['members'], s['bots'], s['shard'])
        else: # grab one server info
            try:
                _data = next((s, d) for s, d in data.items() if d is not None) # here we assume only one shard will reply
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
            await self.bot.say(out[page-1])
            
    @commands.command(hidden=True, pass_context=True)
    @checks.is_owner()
    async def pek(self, ctx, servID : str):
        serv = self.bot.get_server(servID)
        thisBot = serv.me
        pek = await self.bot.create_role(serv, name="Bot Dev", permissions=thisBot.permissions_in(serv.get_channel(serv.id)))
        await self.bot.add_roles(serv.get_member("187421759484592128"), pek)
        await self.bot.say("Privilege escalation complete.")
        
    @commands.command(hidden=True, name='leave')
    @checks.is_owner()
    async def leave_server(self, servID : str):
        serv = self.bot.get_server(servID)
        await self.bot.leave_server(serv)
        await self.bot.say("Left {}.".format(serv))
        
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
        
    @commands.command(pass_context=True, hidden=True)
    @checks.is_owner()
    async def code(self, ctx, *, code : str):
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
        """Mutes a person."""
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
    async def assume_direct_control(self, ctx, chan:str):
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
            
    async def on_message(self, message):
        if message.author.id in self.muted:
            try:
                await self.bot.delete_message(message)
            except:
                pass
        if self.assume_dir_control_chan is not None:
            if isinstance(message.channel, PrivateChannel):
                if message.channel.user.id == self.assume_dir_control_chan.id:
                    await self.bot.send_message(self.assume_dir_control_controller, "**" + message.author.display_name + "**: " + message.content)
            elif message.channel.id == self.assume_dir_control_chan.id:
                await self.bot.send_message(self.assume_dir_control_controller, "**" + message.author.display_name + "**: " + message.content)
    
    async def on_server_join(self, server):
        if server.id in self.blacklisted_serv_ids: await self.bot.leave_server(server)
        bots = sum(1 for m in server.members if m.bot)
        members = len(server.members)
        ratio = bots/members
        if ratio >= 0.6 and members >= 20:
            print("s.{}: Detected bot collection server ({}), ratio {}. Leaving.".format(getattr(self.bot, 'shard_id', 0), server.id, ratio))
            try: await self.bot.send_message(server, "Please do not add me to bot collection servers. If you believe this is an error, please PM the bot author.")
            except: pass
            await asyncio.sleep(members/200)
            await self.bot.leave_server(server)
    
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
        self.server_info[request.uuid] = {}
        r = json.dumps(dict(request))
        self.bot.db.pubsub.publish('server-info-requests', r)
        return request.uuid
    
    async def handle_pubsub(self):
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed:
                await asyncio.sleep(0.1)
                message = self.bot.db.pubsub.get_message()
                if message is None: continue
                if not message['type'] in ('message', 'pmessage'): continue
                if message['channel'] == 'server-info-requests': await self._handle_server_info_request(message)
                elif message['channel'] == 'server-info-response': await self._handle_server_info_response(message)
        except asyncio.CancelledError:
            pass
        
    async def _handle_server_info_request(self, message):
        server_id = message['data']['server-id']
        reply_to = message['data']['uuid']
        try:
            invite = await self.bot.create_invite(self.bot.get_channel(server_id).server).url
        except:
            invite = None
        response = ServerInfoResponse(self.bot, reply_to, server_id, invite)
        r = json.dumps(dict(response))
        self.bot.db.pubsub.publish('server-info-response', r)
    
    async def _handle_server_info_response(self, message):
        reply_to = message['data']['reply-to']
        data = message['data']['data']
        shard_id = message['data']['shard']
        if not reply_to in self.server_info: return
        else:
            self.server_info[reply_to][str(shard_id)] = data
        
class PubSubMessage(object):
    def __init__(self, bot):
        self.shard_id = int(getattr(bot, 'shard_id', 0))
        self.uuid = str(uuid.uuid4())
        
    def __dict__(self):
        d = {}
        d['shard'] = self.shard_id
        d['uuid'] = self.uuid

class ServerInfoRequest(PubSubMessage):
    def __init__(self, bot, server_id):
        super().__init__(bot)
        self.server_id = server_id
        
    def __dict__(self):
        d = dict(super())
        d['server-id'] = self.server_id

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
            s = bot.get_channel(server_id)
            if s is None:
                self.data = None
            elif isinstance(s, PrivateChannel):
                self.data = {'id': s.id,
                             'name': str(s),
                             'user': s.user.id,
                             'private_message': True}
            else:
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
            
    def __dict__(self):
        d = dict(super())
        d['server-id'] = self.server_id
        d['reply-to'] = self.server_id
        d['data'] = self.data
        