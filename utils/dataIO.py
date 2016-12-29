'''
Created on Dec 28, 2016

@author: andrew
'''

import os
import redis

class DataIO:
    '''
    A simple class to interface with the redis database.
    '''

    def __init__(self):
        self.db = redis.from_url(os.environ.get("REDIS_URL"))
        
    def get(self, key):
        return self.db.get(key).decode()
    
    def set(self, key, value):
        return self.db.set(key, value)
    
    def set_dict(self, key, dictionary):
        return self.db.hmset(key, dictionary)
    
    def get_dict(self, key, dict_key):
        return self.db.hget(key, dict_key).decode()
    
    def get_whole_dict(self, key):
        encoded_dict = self.db.hgetall(key)
        out = {}
        for k in encoded_dict.keys():
            out[k.decode()] = encoded_dict[k].decode()
        return out