'''
Created on Jan 13, 2017

@author: andrew
'''

import asyncio
import os

from aiohttp import web
from aiohttp.web_reqrep import StreamResponse
import aiohttp_jinja2
import jinja2

from web.CustomStaticRoute import CustomStaticRoute


class Web:
    """A simple webserver."""
    
    
    def __init__(self, loop=None):
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self.app = web.Application(loop=self.loop)
        aiohttp_jinja2.setup(self.app,
                             loader=jinja2.FileSystemLoader('./web/templates'))
        self.setup_middlewares(self.app)
        self.app.router.add_static('/5etools/', './web/data/5etools')
        self.add_static('/', './web/data', show_index=True)
        
    def run(self):
        self.run_app(self.app, host=os.environ.get('HOST'), port=os.environ.get('PORT'))
    
    def add_static(self, prefix, path, *, name=None, expect_handler=None,
                   chunk_size=256 * 1024, response_factory=StreamResponse,
                   show_index=False):
        """Add static files view.

        prefix - url prefix
        path - folder with files

        """
        assert prefix.startswith('/')
        if not prefix.endswith('/'):
            prefix += '/'
        route = CustomStaticRoute(name, prefix, path,
                            expect_handler=expect_handler,
                            chunk_size=chunk_size,
                            response_factory=response_factory,
                            show_index=show_index)
        self.app.router.register_route(route)
        return route
        
    def __unload(self):
        self.app.srv.close()
        self.loop.run_until_complete(self.app.srv.wait_closed())
        self.loop.run_until_complete(self.app.shutdown())
        self.loop.run_until_complete(self.app.handler.shutdown(60.0))
        self.loop.run_until_complete(self.app.cleanup())
        
    def setup_middlewares(self, app):
        error_middleware = self.error_pages({403: self.handle_error,
                                             404: self.handle_error,
                                             500: self.handle_error})
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
    
    async def handle_error(self, request, response):
        response = aiohttp_jinja2.render_template('error.html',
                                                  request,
                                                  {'status': response.status,
                                                   'error': response.reason})
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
        print("w.0: ======== Running on {scheme}://{host}:{port}/ ========".format(
                  scheme=scheme, host=host, port=port))
        
        try:
            loop.run_forever()
        except KeyboardInterrupt:  # pragma: no cover
            pass
        finally:
            self.__unload()
        loop.close()
