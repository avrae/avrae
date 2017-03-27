'''
Created on Mar 27, 2017

@author: andrew
'''
from web.web import Web
import asyncio

running = True
loop = asyncio.get_event_loop()

if __name__ == '__main__':
    web = Web(loop)
    web.run()