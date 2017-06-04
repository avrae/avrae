'''
Created on Jun 3, 2017

@author: andrew
'''

class TextLogger:
    
    def __init__(self, file):
        self.file = file
        
    def text_log(self, ctx, message):
        try:
            log = "channel {} ({}), server {} ({})\nmessage: {}\n----------\n".format(ctx.message.channel, ctx.message.channel.id, ctx.message.server, ctx.message.server.id, ctx.message.content)
        except AttributeError:
            log = "PM with {} ({})\nmessage: {}\n----------\n".format(ctx.message.author, ctx.message.author.id, ctx.message.content)
        with open(self.file, mode='a', encoding='utf-8') as f:
            f.write(message + log)
            print(message + log)
