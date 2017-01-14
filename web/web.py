'''
Created on Jan 13, 2017

@author: andrew
'''

import asyncio
import os

from aiohttp import web

import aiohttp_jinja2  # @UnresolvedImport
import jinja2  # @UnresolvedImport


class Web:
    """A simple webserver."""
    
    
    def __init__(self, bot):
        self.bot = bot
        self.loop = self.bot.loop
        self.app = web.Application(loop=self.loop)
        aiohttp_jinja2.setup(self.app,
                             loader=jinja2.FileSystemLoader('./web/templates/'))
        self.app.router.add_static('/5etools/', './web/data/5etools/')
        self.run_app(self.app, host=os.environ.get('HOST'), port=os.environ.get('PORT'))
        
    def __unload(self):
        self.app.srv.close()
        self.loop.run_until_complete(self.app.srv.wait_closed())
        self.loop.run_until_complete(self.app.shutdown())
        self.loop.run_until_complete(self.app.handler.shutdown(60.0))
        self.loop.run_until_complete(self.app.cleanup())
        
    def setup_middlewares(self, app):
        error_middleware = self.error_pages({404: self.handle_404,
                                             500: self.handle_500})
        app.middlewares.append(error_middleware)
        
    def error_pages(self, overrides):
        async def middleware(app, handler):
            async def middleware_handler(request):
                try:
                    response = await handler(request)
                    override = overrides.get(response.status)
                    if override is None:
                        return response
                    else:
                        return await override(request, response)
                except web.HTTPException as ex:
                    override = overrides.get(ex.status)
                    if override is None:
                        raise
                    else:
                        return await override(request, ex)
            return middleware_handler
        return middleware
    
    async def handle_404(self, request, response):
        response = aiohttp_jinja2.render_template('404.html',
                                                  request,
                                                  {})
        return response
    
    
    async def handle_500(self, request, response):
        response = aiohttp_jinja2.render_template('500.html',
                                                  request,
                                                  {})
        return response

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