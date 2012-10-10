"""
A simple redis-cache interface for storing python objects.
"""
from functools import wraps
import pickle
import json
import base64
import redis

connection = redis.StrictRedis()


class CacheMissException(Exception):
    pass


class SimpleCache(object):

    def __init__(self, limit=1000):
        self.limit = limit  # No of json encoded strings to cache
        
    def store(self, key, value):
        """ Stores a value after checking for space constraints and freeing up space if required """
        key = to_unicode(key)
        value = to_unicode(value)
    
        while connection.scard('SimpleCache:keys') >= self.limit:
            del_key = connection.spop('SimpleCache:keys')
            connection.delete("SimpleCache::%s" % del_key)

        pipe = connection.pipeline()
        pipe.set('SimpleCache::%s' % key, value)
        pipe.sadd("SimpleCache:keys", key)
        pipe.execute()

    def store_json(self, key, value):
        self.store(key, json.dumps(value))

    def store_pickle(self, key, value):
        self.store(key, base64.b64encode(pickle.dumps(value)))

    def get(self, key):
        key = to_unicode(key)
        if key in self:
            val = connection.get("SimpleCache::%s" % key)
            if val is None:  # redis deleted the key
                connection.srem('SimpleCache:keys', key)
                raise CacheMissException
            else:
                return val
        raise CacheMissException

    def get_json(self, key):
        return json.loads(self.get(key))

    def get_pickle(self, key):
        return pickle.loads(base64.b64decode(self.get(key)))

    def __contains__(self, key):
        return connection.sismember("SimpleCache:keys", key)

    def __len__(self):
        return connection.scard("SimpleCache:keys")

    def keys(self):
        keys = connection.keys("SimpleCache::*")
        return keys

    def flush(self):
        keys = self.keys()
        pipe = connection.pipeline()
        for key in keys:
            key_suffix = key[len("SimpleCache::"):]
            pipe.srem('SimpleCache:keys', key_suffix)
            pipe.delete(key)
        pipe.execute()


def cache_it(function):
    """
    Apply this decorator to cache any function returning a value. Arguments and function result
    must be pickleable.
    """
    cache = SimpleCache()
    
    @wraps(function)
    def func(*args):
        key = pickle.dumps(args)
        cache_key = '%s:%s' % (function.__name__, key)
        if cache_key in cache:
            try:
                return cache.get_pickle(cache_key)
            except CacheMissException:
                pass
    
        result = function(*args)
        cache.store_pickle(cache_key, result)
        return result
    return func


def cache_it_json(function):
    """
    A decorator similar to cache_it, but it serializes the return value to json, while storing
    in the database. Useful for types like list, tuple, dict, etc.
    """
    cache = SimpleCache()
    
    @wraps(function)
    def func(*args):
        key = json.dumps(args)
        cache_key = '%s:%s' % (function.__name__, key)
        if cache_key in cache:
            try:
                return cache.get_json(cache_key)
            except CacheMissException:
                pass
            
        result = function(*args)
        cache.store_json(cache_key, result)
        return result
    return func


def to_unicode(obj, encoding='utf-8'):
    if isinstance(obj, basestring):
        if not isinstance(obj, unicode):
            obj = unicode(obj, encoding)
    return obj
