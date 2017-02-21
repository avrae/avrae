'''
Created on Feb 19, 2017

@author: andrew
'''
import asyncio
from urllib.parse import unquote

from aiohttp.web_exceptions import HTTPNotFound, HTTPForbidden
from aiohttp.web_urldispatcher import StaticRoute


class CustomStaticRoute(StaticRoute):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    @asyncio.coroutine
    def handle(self, request):
        filename = unquote(request.match_info['filename'])
        try:
            filepath = self._directory.joinpath(filename).resolve()
            filepath.relative_to(self._directory)
        except (ValueError, FileNotFoundError) as error:
            # relatively safe
            raise HTTPNotFound() from error
        except Exception as error:
            # perm error or other kind!
            request.app.logger.exception(error)
            raise HTTPNotFound() from error

        # on opening a dir, load it's contents if allowed
        if filepath.is_dir():
            if self._show_index:
                try:
                    ret = yield from self._file_sender.send(request, filepath / 'index.html')
                except PermissionError:
                    raise HTTPForbidden()
            else:
                raise HTTPForbidden()
        elif filepath.is_file():
            ret = yield from self._file_sender.send(request, filepath)
        else:
            raise HTTPNotFound

        return ret