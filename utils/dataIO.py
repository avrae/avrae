'''
Created on Dec 28, 2016

@author: andrew
'''

import json
import os

import redis



class DataIO:
    '''
    A simple class to interface with the redis database.
    '''

    def __init__(self, testing=False, test_database_url=''):
        if not testing:
            self._db = redis.from_url(os.environ.get("REDIS_URL"))
        else:
            self._db = redis.from_url(test_database_url)
        
    def get(self, key, default=None):
        encoded_data = self._db.get(key)
        return encoded_data.decode() if encoded_data is not None else default
    
    def set(self, key, value):
        return self._db.set(key, value)
    
    def incr(self, key):
        return self._db.incr(key)
    
    def exists(self, key):
        return self._db.exists(key)
    
    def delete(self, key):
        return self._db.delete(key)
    
    def setex(self, key, value, expiration):
        return self._db.setex(key, value, expiration)
    
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
    
    def jset(self, key, data, **kwargs):
        return self.not_json_set(key, data, **kwargs)
    
    def jsetex(self, key, data, exp, **kwargs):
        data = json.dumps(data, **kwargs)
        return self.setex(key, data, exp)
    
    def jget(self, key, default=None):
        return self.not_json_get(key, default)
    
    def not_json_set(self, key, data, **kwargs):
        data = json.dumps(data, **kwargs)
        return self.set(key, data)
        
    def not_json_get(self, key, default=None):
        data = self.get(key)
        return json.loads(data) if data is not None else default
        
        