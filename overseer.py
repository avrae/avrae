'''
Created on Mar 27, 2017

@author: andrew
'''
import copy
import os
import signal
import subprocess
import sys
import time

import credentials
from utils.dataIO import DataIO


class Overseer():
    def __init__(self):
        self.db = DataIO(TESTING, credentials.test_database_url)
        self.shards = {}
        self.web = None

TESTING = False
RUNNING = True
if "test" in sys.argv:
    TESTING = True

# SHARDS = int(os.environ.get('SHARDS', 1))
CLUSTER = int(sys.argv[-1])
CLUSTER_MAP = {0: (0, 2),
               1: (3, 6),
               2: (7, 10)}
CLUSTER_START = CLUSTER_MAP[CLUSTER][0]
CLUSTER_END = CLUSTER_MAP[CLUSTER][1]
ROLLING_TIMER = 0.25 # seconds between each shard start
bot = Overseer()

def init():
    signal.signal(signal.SIGTERM, sigterm_handler)
    if CLUSTER == 0:
        launch_web() # I mean okay
    # time.sleep(ROLLING_TIMER * CLUSTER_START) # rolling restart
    launch_shards()
    if CLUSTER == 0:
        clean_shard_servers()

def loop():
    time.sleep(30)
    if RUNNING:
        check_shards()
    
def launch_web():
    print("o.{}: Launching webserver".format(CLUSTER))
    if TESTING:
        bot.web = subprocess.Popen(["gunicorn", "-w", "2", "web.web:app"])
    else:
        bot.web = subprocess.Popen(["gunicorn", "-w", "1", "-b", "0.0.0.0:{}".format(os.environ.get("PORT")), "web.web:app"])
    
def launch_shards():
    for shard in range(CLUSTER_START, CLUSTER_END+1):
        if TESTING:
            print("o.{}: Launching shard test {}".format(CLUSTER, shard))
            bot.shards[shard] = subprocess.Popen(['python3', 'dbot.py', '-s', str(shard), 'test'])
        else:
            print("o.{}: Launching shard production {}".format(CLUSTER, shard))
            bot.shards[shard] = subprocess.Popen(['python3', 'dbot.py', '-s', str(shard)])
        time.sleep(ROLLING_TIMER)
    print("o.{}: Shards launched: {}".format(CLUSTER, {shard: process.pid for shard, process in bot.shards.items()}))
    
def check_shards():
    for shard, process in bot.shards.items():
        if process.poll() is not None:
            print('o.{}: Shard {} crashed with exit code {}, restarting...'.format(CLUSTER, shard, process.returncode))
            if TESTING:
                print("o.{}: Launching shard test {}".format(CLUSTER, shard))
                bot.shards[shard] = subprocess.Popen(['python3', 'dbot.py', '-s', str(shard), 'test'])
            else:
                print("o.{}: Launching shard production {}".format(CLUSTER, shard))
                bot.shards[shard] = subprocess.Popen(['python3', 'dbot.py', '-s', str(shard)])
            
    
def clean_shard_servers():
    shard_servers = bot.db.jget('shard_servers', {0: 0})
    num_shards = int(os.environ.get('SHARDS', 1))
    temp = copy.copy(shard_servers)
    for shard in shard_servers.keys():
        try:
            if int(shard) >= num_shards:
                del temp[shard]
                print("o.{}: Overseer process deleted server data for shard {}".format(CLUSTER, shard))
        except:
            print("o.{}: Error processing shard servers".format(CLUSTER))
    bot.db.jset("shard_servers", temp)

def sigterm_handler(_signum, _frame):
    global RUNNING
    RUNNING = False
    print("o.{}: Overseer caught SIGTERM, sleeping for 15!".format(CLUSTER))
    time.sleep(15)
    sys.exit(0)
    
if __name__ == '__main__':
    init()
    while True:
        loop()