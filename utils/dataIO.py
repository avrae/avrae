'''
Created on Dec 28, 2016

@author: andrew
'''

import os
import redis
import json

class DataIO:
    '''
    A simple class to interface with the redis database.
    '''

    def __init__(self):
        self._db = redis.from_url(os.environ.get("REDIS_URL"))
        
    def get(self, key, default=None):
        encoded_data = self._db.get(key)
        return encoded_data.decode() if encoded_data is not None else default
    
    def set(self, key, value):
        return self._db.set(key, value)
    
    def set_dict(self, key, dictionary):
        if len(dictionary) == 0:
            return self._db.delete(key)
        return self._db.hmset(key, dictionary)
    
    def get_dict(self, key, dict_key):
        return self._db.hget(key, dict_key).decode()
    
    def get_whole_dict(self, key, default={}):
        encoded_dict = self._db.hgetall(key)
        if encoded_dict is None: return default
        out = {}
        for k in encoded_dict.keys():
            out[k.decode()] = encoded_dict[k].decode()
        return out
    
    def not_json_set(self, key, data):
        data = json.dumps(data)
        return self.set(key, data)
        
    def not_json_get(self, key, default=None):
        data = self.get(key)
        return json.loads(data) if data is not None else default
        
        