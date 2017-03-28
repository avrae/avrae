'''
Created on Mar 27, 2017

@author: andrew
'''
import copy
import os
import signal
import sys
import time

import credentials
from utils.dataIO import DataIO


class Overseer():
    def __init__(self):
        self.db = DataIO(TESTING, credentials.test_database_url)

TESTING = False
if "test" in sys.argv:
    TESTING = True
bot = Overseer()

def init():
    signal.signal(signal.SIGTERM, sigterm_handler)
    clean_shard_servers()

def loop():
    time.sleep(1)
    
def clean_shard_servers():
    shard_servers = bot.db.jget('shard_servers', {0: 0})
    num_shards = int(os.environ.get('SHARDS', 1))
    temp = copy.copy(shard_servers)
    for shard in shard_servers.keys():
        if int(shard) >= num_shards:
            del temp[shard]
            print("Overseer process deleted server data for shard {}".format(shard))
    bot.db.jset("shard_servers", temp)

def sigterm_handler(_signum, _frame):
    print("Overseer caught SIGTERM, sleeping for 15!")
    time.sleep(15)
    sys.exit(0)
    
if __name__ == '__main__':
    init()
    while True:
        loop()