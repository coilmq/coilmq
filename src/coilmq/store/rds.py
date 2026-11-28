import pickle
import sys

import wrapt

try:
    import redis
except ImportError:  # pragma: no cover
    sys.exit("please, install redis-py package to use redis-store")

from coilmq.config import CONFIG
from coilmq.store import QueueStore

__authors__ = (
    '"Hans Lellelid" <hans@xmpl.org>',
    '"Alexander Zhukov" <zhukovaa90@gmail.com>',
)
__copyright__ = "Copyright 2009 Hans Lellelid"
__license__ = """Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""


def make_redis_store(cfg=None):
    return RedisQueueStore(
        redis_conn=redis.Redis(**dict((cfg or CONFIG).items("redis")))
    )


class RedisQueueStore(QueueStore):
    """Simple Queue with Redis Backend."""

    def __init__(self, redis_conn=None):
        """The default connection parameters are: host='localhost', port=6379, db=0."""
        self.__db = redis_conn or redis.Redis()
        super().__init__()

    @wrapt.synchronized
    def enqueue(self, destination, frame):
        self.__db.rpush(destination, pickle.dumps(frame))

    @wrapt.synchronized
    def dequeue(self, destination):
        item = self.__db.lpop(destination)
        if item:
            return pickle.loads(item)

    @wrapt.synchronized
    def requeue(self, destination, frame):
        self.enqueue(destination, frame)

    @wrapt.synchronized
    def size(self, destination):
        return self.__db.llen(destination)

    @wrapt.synchronized
    def has_frames(self, destination):
        return self.size(destination) > 0

    @wrapt.synchronized
    def destinations(self):
        return self.__db.keys()
