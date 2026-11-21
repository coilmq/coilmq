"""Queue storage module that uses thread-safe, in-memory data structures."""

from collections import defaultdict, deque

import wrapt

from coilmq.store import QueueStore

__authors__ = ['"Hans Lellelid" <hans@xmpl.org>']
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


class MemoryQueue(QueueStore):
    """A QueueStore implementation that stores messages in memory."""

    def __init__(self):
        QueueStore.__init__(self)
        self._messages = defaultdict(deque)

    @wrapt.synchronized
    def enqueue(self, destination, frame):
        self._messages[destination].appendleft(frame)

    @wrapt.synchronized
    def dequeue(self, destination):
        try:
            return self._messages[destination].pop()
        except IndexError:
            return None

    @wrapt.synchronized
    def size(self, destination):
        """Size of the queue for specified destination.

        :param destination: The queue destination (e.g. /queue/foo)
        :type destination: str
        """
        return len(self._messages[destination])

    @wrapt.synchronized
    def has_frames(self, destination):
        """Whether this queue has frames for the specified destination."""
        return bool(self._messages[destination])

    @wrapt.synchronized
    def destinations(self):
        """Provides a list of destinations (queue "addresses") available.

        :returns: A list of the destinations available.
        :rtype: set
        """
        return set(self._messages.keys())
