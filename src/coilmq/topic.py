"""Non-durable topic support functionality.

This code is inspired by the design of the Ruby stompserver project, by
Patrick Hurley and Lionel Bouton.  See http://stompserver.rubyforge.org/
"""

import logging
import uuid
from copy import deepcopy

import wrapt

from coilmq.subscription import SubscriptionManager
from coilmq.util import frames

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


class TopicManager:
    """Class that manages distribution of messages to topic subscribers.

    :var _subscriptions: A dict of registered topics, keyed by destination.
    :vartype _subscriptions: dict[str, set[coilmq.server.StompConnection]]
    """

    def __init__(self):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self._subscriptions = SubscriptionManager()

        # TODO: If we want durable topics, we'll need a store for topics.

    @wrapt.synchronized
    def close(self):
        """Closes all resources associated with this topic manager.

        (Currently this is simply here for API conformity w/ :class:`coilmq.queue.QueueManager`.)
        """
        self.log.info("Shutting down topic manager.")  # pragma: no cover

    @wrapt.synchronized
    def subscribe(self, connection, destination, id=None):
        """Subscribes a connection to the specified topic destination.

        :param connection: The client connection to subscribe.
        :type connection: coilmq.server.StompConnection
        :param destination: The topic destination (e.g. '/topic/foo')
        :type destination: str

        """
        self.log.debug("Subscribing %s to %s", connection, destination)
        self._subscriptions.subscribe(connection, destination, id=id)

    @wrapt.synchronized
    def unsubscribe(self, connection, destination, id=None):
        """Unsubscribes a connection from the specified topic destination.

        :param connection: The client connection to unsubscribe.
        :type connection: coilmq.server.StompConnection
        :param destination: The topic destination (e.g. '/topic/foo')
        :type destination: str

        """
        self.log.debug("Unsubscribing %s from %s", connection, destination)
        self._subscriptions.unsubscribe(connection, destination, id=id)

    @wrapt.synchronized
    def disconnect(self, connection):
        """Removes a subscriber connection.

        :param connection: The client connection to unsubscribe.
        :type connection: coilmq.server.StompConnection
        """
        self.log.debug("Disconnecting %s", connection)
        self._subscriptions.disconnect(connection)

    @wrapt.synchronized
    def send(self, message):
        """Sends a message to all subscribers of destination.

        :param message: The message frame.  (The frame will be modified to set command
            to MESSAGE and set a message id.)
        :type message: coilmq.util.frames.Frame
        """
        dest = message.headers.get("destination")
        if not dest:
            raise ValueError(f"Cannot send frame with no destination: {message}")

        message.cmd = frames.MESSAGE

        message.headers.setdefault("message-id", str(uuid.uuid4()))

        bad_subscribers = set()
        for subscriber in self._subscriptions.subscribers(dest):
            frame = deepcopy(message)
            frame.headers["subscription"] = subscriber.id
            try:
                subscriber.connection.send_frame(frame)
            except:  # noqa: E722
                self.log.exception(
                    "Error delivering message to subscriber %s; client will be disconnected.",
                    subscriber,
                )
                # We queue for deletion so we are not modifying the topics dict
                # while iterating over it.
                bad_subscribers.add(subscriber)

        for s in bad_subscribers:
            self.unsubscribe(s.connection, dest, id=s.id)
