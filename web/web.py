'''
Created on Jan 13, 2017

@author: andrew
'''

import asyncio
import os

from aiohttp import web
import discord
from discord.ext import commands


class Web:
    """A simple webserver."""
    
    
    def __init__(self, bot):
        self.bot = bot
        self.loop = self.bot.loop
        self.app = web.Application(loop=self.loop)
        self.app.router.add_static('/5etools', './web/data/5etools')
        self.run_app(self.app, host=os.environ.get('HOST'), port=os.environ.get('PORT'))
        
    def __unload(self):
        self.app.srv.close()
        self.loop.run_until_complete(self.app.srv.wait_closed())
        self.loop.run_until_complete(self.app.shutdown())
        self.loop.run_until_complete(self.app.handler.shutdown(60.0))
        self.loop.run_until_complete(self.app.cleanup())

    def run_app(self, app, *, host='0.0.0.0', port=None,
            shutdown_timeout=60.0, ssl_context=None,
            print=print, backlog=128):
        """Run an app"""
        if port is None:
            if not ssl_context:
                port = 8080
            else:
                port = 8443
    
        loop = app.loop
    
        app.handler = app.make_handler()
        server = loop.create_server(app.handler, host, port, ssl=ssl_context,
                                    backlog=backlog)
        app.srv, app.startup_res = loop.run_until_complete(asyncio.gather(server,
                                                                  app.startup(),
                                                                  loop=loop))
    
        scheme = 'https' if ssl_context else 'http'
        print("======== Running on {scheme}://{host}:{port}/ ========".format(
                  scheme=scheme, host=host, port=port))