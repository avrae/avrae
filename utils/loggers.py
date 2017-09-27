"""
Created on Jun 3, 2017

@author: andrew
"""
from datetime import datetime
import logging


class TextLogger:
    
    def __init__(self, file):
        self.file = file
        self.log = logging.getLogger("TextLogger")
        
    def text_log(self, ctx, message):
        timestamp = datetime.today().isoformat() + " "
        try:
            log = "channel {} ({}), server {} ({})\nmessage: {}\n----------\n".format(ctx.message.channel, ctx.message.channel.id, ctx.message.server, ctx.message.server.id, ctx.message.content)
        except AttributeError:
            log = "PM with {} ({})\nmessage: {}\n----------\n".format(ctx.message.author, ctx.message.author.id, ctx.message.content)
        # with open(self.file, mode='a', encoding='utf-8') as f:
        #     f.write(timestamp + message + log)
        self.log.info(message + log)
