from __future__ import annotations

import abc
import datetime
import importlib.metadata
import re
import socket
import uuid
from typing import TYPE_CHECKING, cast

from coilmq.exception import AuthError, ProtocolError
from coilmq.util import frames
from coilmq.util.concurrency import CoilThreadingTimer
from coilmq.util.frames import ConnectedFrame, ReceiptFrame

if TYPE_CHECKING:
    from coilmq.engine import StompEngine
    from coilmq.util.frames import Frame


class AbstractSTOMP(abc.ABC):
    """Abstract base class for STOMP frame adaptors.

    Subclasses of `AbstractSTOMP` adapt a single STOMP version's semantics to CoilMQ's
    internal machinery.

    :param engine: The engine associated with the adaptor.

    """

    def __init__(self, engine: StompEngine, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.engine = engine

    @property
    @abc.abstractmethod
    def encoding(self) -> str:
        """Return the name of the header encoding.

        Each version of STOMP specifies slightly different, incompatible methods for
        encoding a frame's headers.  Subclasses of `AbstractSTOMP` return the name of
        the encoding used by the version of STOMP supported by the class.

        """

    @abc.abstractmethod
    def process_frame(self, frame: Frame) -> ReceiptFrame | None:
        """Dispatches a frame to the appropriate internal method.

        :param frame: The incoming frame.

        """

    def close(self) -> None:  # ruff: ignore[empty-method-without-abstract-decorator]
        """Close the adaptor by releasing any held resources."""


class STOMP10(AbstractSTOMP):
    """Adapt STOMP 1.0 to CoilMQ's internal machinery."""

    @property
    def encoding(self) -> str:
        return "stomp1.0"

    def process_frame(self, frame: Frame) -> ReceiptFrame | None:
        """Dispatches a frame to the appropriate internal method.

        :param frame: The incoming frame.

        :raises ProtocolError: if a frame violates the protocol.

        """
        if frame.cmd == frames.CONNECT:
            self.connect(frame)
            # Do not send a ``RECEIPT`` frame for ``CONNECT`` even if the command
            # happens to include a ``receipt`` header.
            return None

        if frame.cmd == frames.SEND:
            transaction = frame.headers.get("transaction")

            if transaction is None:
                self.send(frame)
            elif transaction in self.engine.transactions:
                self.engine.transactions[transaction].append(frame)
            else:
                raise ProtocolError(f"Invalid transaction: {transaction}")

        elif frame.cmd == frames.SUBSCRIBE:
            self.subscribe(frame)
        elif frame.cmd == frames.UNSUBSCRIBE:
            self.unsubscribe(frame)
        elif frame.cmd == frames.BEGIN:
            self.begin(frame)
        elif frame.cmd == frames.COMMIT:
            self.commit(frame)
        elif frame.cmd == frames.ABORT:
            self.abort(frame)
        elif frame.cmd == frames.ACK:
            transaction = frame.headers.get("transaction")

            if transaction is None:
                self.ack(frame)
            elif transaction in self.engine.transactions:
                self.engine.transactions[transaction].append(frame)
            else:
                raise ProtocolError(f"Invalid transaction: {transaction}")

        elif frame.cmd == frames.DISCONNECT:
            self.disconnect(frame)
        else:
            raise ProtocolError(f"Invalid command: {frame.cmd}")

        # The protocol is not especially clear here (not sure why I'm surprised) about
        # the expected behavior WRT receipts and errors.  We will assume that the
        # ``RECEIPT`` frame should not be sent if there is an error.  We'll also assume
        # that a transaction should not preclude sending the receipt frame.
        return self._frame_to_receipt_frame(frame)

    def _frame_to_receipt_frame(self, frame: Frame) -> ReceiptFrame | None:
        """Return a ``RECEIPT`` frame if the client asked for one.

        :param frame: A command frame from a client.

        :returns: If ``frame`` has a ``receipt`` header, this method will return a
            ``RECEIPT`` frame with the same header, otherwise `None`.

        """
        receipt = frame.headers.get("receipt")
        return ReceiptFrame(receipt=str(receipt)) if receipt is not None else None

    def connect(self, frame: Frame, response: ConnectedFrame | None = None) -> None:
        """Establish a new connection.

        For servers with authentication enabled, check the frame's ``login`` and
        ``passcode`` headers.

        :param frame: A ``CONNECT`` frame.
        :param response: A ``CONNECTED`` frame, if this method is called from
            the handler for a greater version of the protocol specification or
            `None`, if this method is the first to see the ``CONNECT`` frame.

        :raises AuthError: if the frame's ``login` and/or ``passcode`` are rejected.

        """
        self.engine.log.debug("CONNECT")

        if self.engine.authenticator and (
            (login := frame.headers.get("login")) is None
            or (passcode := frame.headers.get("passcode")) is None
            or not self.engine.authenticator.authenticate(str(login), str(passcode))
        ):
            raise AuthError(f"Authentication failed")

        self.engine.connected = True

        response = response or ConnectedFrame(str(uuid.uuid4()))

        # TODO: Do we want to do anything special to track sessions?
        # (Actually, I don't think the spec actually does anything with this at all.)
        self.engine.connection.send_frame(response)

    def send(self, frame):
        """Deliver a message to a queue or topic.

        :param frame: A ``SEND`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        dest = frame.headers.get("destination")
        if not dest:
            raise ProtocolError("Missing destination for SEND command.")

        if dest.startswith("/queue/"):
            self.engine.queue_manager.send(frame)
        else:
            self.engine.topic_manager.send(frame)

    def subscribe(self, frame):
        """Add this connection to a destination.

        :param frame: A ``SUBSCRIBE`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        ack = frame.headers.get("ack")
        reliable = ack and ack.lower() == "client"

        self.engine.connection.reliable_subscriber = reliable

        dest = frame.headers.get("destination")
        if not dest:
            raise ProtocolError("Missing destination for SUBSCRIBE command.")

        subscription_id = frame.headers.get("id")
        if dest.startswith("/queue/"):
            self.engine.queue_manager.subscribe(
                self.engine.connection, dest, id=subscription_id
            )
        else:
            self.engine.topic_manager.subscribe(
                self.engine.connection, dest, id=subscription_id
            )

    def unsubscribe(self, frame):
        """Remove this connection from a destination.

        :param frame: An ``UNSUBSCRIBE`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        dest = frame.headers.get("destination")
        if not dest:
            raise ProtocolError("Missing destination for UNSUBSCRIBE command.")

        subscription_id = frame.headers.get("id")
        if dest.startswith("/queue/"):
            self.engine.queue_manager.unsubscribe(
                self.engine.connection, dest, id=subscription_id
            )
        else:
            self.engine.topic_manager.unsubscribe(
                self.engine.connection, dest, id=subscription_id
            )

    def begin(self, frame):
        """Start a new transaction.

        :param frame: A ``BEGIN`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        if not frame.transaction:
            raise ProtocolError("Missing transaction for BEGIN command.")

        self.engine.transactions[frame.transaction] = []

    def commit(self, frame):
        """Execute the specified pending transaction.

        :param frame: A ``COMMIT`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        if not frame.transaction:
            raise ProtocolError("Missing transaction for COMMIT command.")

        if not frame.transaction in self.engine.transactions:
            raise ProtocolError(f"Invalid transaction: {frame.transaction}")

        for tframe in self.engine.transactions[frame.transaction]:
            del tframe.headers["transaction"]
            self.process_frame(tframe)

        self.engine.queue_manager.clear_transaction_frames(
            self.engine.connection, frame.transaction
        )
        del self.engine.transactions[frame.transaction]

    def abort(self, frame):
        """Roll back the specified pending transaction.

        :param frame: An ``ABORT`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        if not frame.transaction:
            raise ProtocolError("Missing transaction for ABORT command.")

        if not frame.transaction in self.engine.transactions:
            raise ProtocolError(f"Invalid transaction: {frame.transaction}")

        self.engine.queue_manager.resend_transaction_frames(
            self.engine.connection, frame.transaction
        )
        del self.engine.transactions[frame.transaction]

    def ack(self, frame):
        """Retire a message that the client has acknowledged receiving.

        :param frame: An ``ACK`` frame.

        :raises ProtocolError: if required headers are missing.

        """
        if "message-id" not in frame.headers:
            raise ProtocolError("No message-id specified for ACK command.")
        self.engine.queue_manager.ack(
            self.engine.connection, frame, id=frame.headers.get("id")
        )

    def disconnect(self, frame):
        """Unbind the connection.

        :param frame: A ``DISCONNECT`` frame.

        .. Note:: Clients are supposed to send this command.  In practice, CoilMQ can
                  handle a client silently closing the connection.

        """
        self.engine.log.debug("Disconnect")
        self.engine.unbind()


class STOMP11(STOMP10):
    """Adapt STOMP 1.1 to CoilMQ's internal machinery."""

    def __init__(
        self,
        engine: StompEngine,
        send_heartbeat_interval: int = 100,
        receive_heartbeat_interval: int = 100,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(engine, *args, **kwargs)
        self.timer = CoilThreadingTimer()
        self.send_heartbeat_interval = datetime.timedelta(
            milliseconds=send_heartbeat_interval
        )
        self.receive_heartbeat_interval = datetime.timedelta(
            milliseconds=receive_heartbeat_interval
        )

    @property
    def encoding(self) -> str:
        return "stomp1.1"

    def process_frame(self, frame: Frame) -> ReceiptFrame | None:
        if frame.cmd == frames.STOMP:
            self.stomp(frame)
            # Do not send a ``RECEIPT`` frame for ``STOMP`` even if the command happens
            # to include a ``receipt`` header.
            return None

        if frame.cmd == frames.NACK:
            transaction = frame.headers.get("transaction")

            if transaction is None:
                self.nack(frame)
            elif transaction in self.engine.transactions:
                self.engine.transactions[transaction].append(frame)
            else:
                raise ProtocolError(f"Invalid transaction: {transaction}")

        else:
            return super().process_frame(frame)

        return self._frame_to_receipt_frame(frame)

    def close(self):
        self.timer.stop()

    def enable_heartbeat(self, cx: int, cy: int) -> tuple[int, int]:
        if self.send_heartbeat_interval and cy:
            self.send_heartbeat_interval = max(
                self.send_heartbeat_interval, datetime.timedelta(milliseconds=cy)
            )
            self.timer.schedule(
                self.send_heartbeat_interval.total_seconds(), self.send_heartbeat
            )
        if self.receive_heartbeat_interval and cx:
            self.receive_heartbeat_interval = max(
                self.send_heartbeat_interval, datetime.timedelta(milliseconds=cx)
            )
            self.timer.schedule(
                self.receive_heartbeat_interval.total_seconds(),
                self.check_receive_heartbeat,
            )
        self.timer.start()
        sx = int(self.send_heartbeat_interval / datetime.timedelta(milliseconds=1))
        sy = int(self.receive_heartbeat_interval / datetime.timedelta(milliseconds=1))
        return sx, sy

    def send_heartbeat(self):
        if not self.engine.connected:
            return
        self.engine.connection.send_heartbeat()

    def check_receive_heartbeat(self):
        ago = datetime.datetime.now() - self.engine.connection.last_data
        if ago > (self.receive_heartbeat_interval * 2):
            self.engine.log.debug(
                "No heartbeat was received for %s seconds", ago.total_seconds()
            )
            self.engine.unbind()

    def connect(self, frame: Frame, response: ConnectedFrame | None = None) -> None:
        """Establish a new connection.

        For servers with authentication enabled, check the frame's ``login`` and
        ``passcode`` headers.

        :param frame: A ``CONNECT`` frame.
        :param response: A ``CONNECTED`` frame, if this method is called from
            the handler for a greater version of the protocol specification or
            `None`, if this method is the first to see the ``CONNECT`` frame.

        :raises AuthError: if the frame's ``login` and/or ``passcode`` are rejected.
        :raises ProtocolError: if the frame's ``heart-beat`` header is malformed.

        """
        response = response or ConnectedFrame(str(uuid.uuid4()))
        response.headers.setdefault("version", "1.1")
        response.headers["server"] = f"coilmq/{importlib.metadata.version('coilmq')}"

        heart_beat = frame.headers.get("heart-beat")
        if heart_beat:
            match = re.match(r"(?P<cx>\d+),(?P<cy>\d+)$", heart_beat)
            if not match:
                msg = "Malformed 'heart-beat'"
                raise ProtocolError(msg)
            groups = match.groupdict()
            cx = int(cast("str", groups["cx"]))
            cy = int(cast("str", groups["cy"]))
            sx, sy = self.enable_heartbeat(cx, cy)
            response.headers["heart-beat"] = f"{sx},{sy}"

        super().connect(frame, response)

    def stomp(self, frame: Frame) -> None:
        """Establish a new connection.

        This method handles the ``STOMP`` command added in STOMP 1.1.  ``STOMP`` is an
        alias for the ``CONNECT`` command.

        :param frame: A ``STOMP`` frame.

        """
        self.connect(frame)

    def subscribe(self, frame):
        if "id" not in frame.headers:
            raise ProtocolError("No 'id' specified for SUBSCRIBE command.")
        super().subscribe(frame)

    def unsubscribe(self, frame):
        if "id" not in frame.headers:
            raise ProtocolError("No 'id' specified for UNSUBSCRIBE command.")
        super().unsubscribe(frame)

    def ack(self, frame):
        if "subscription" not in frame.headers:
            raise ProtocolError("No 'subscription' specified for ACK command.")
        if "message-id" not in frame.headers:
            raise ProtocolError("No message-id specified for ACK command.")
        self.engine.queue_manager.ack(
            self.engine.connection, frame, id=frame.headers["subscription"]
        )

    def nack(self, frame):
        """Roll back a message that a client did not consume.

        A ``NACK`` command indicates that a reliable subscriber received a frame but did
        not consume it.  That frame is eligible for delivery to another subscriber.

        :param frame: A ``NACK`` frame.

        .. Note:: This method is a placeholder.  CoilMQ does not implement the ``NACK``
                  command at this time.

        """
        if not frame.headers.get("message-id"):
            raise ProtocolError("No message-id specified for NACK command.")
        if not frame.headers.get("subscription"):
            raise ProtocolError("No subscription specified for NACK command.")

        raise NotImplementedError("Nack implementation incomplete")
        # ToDo: self.engine.queue_manager.nack()


class STOMP12(STOMP11):
    """Adapt STOMP 1.2 to CoilMQ's internal machinery."""

    @property
    def encoding(self) -> str:
        return "stomp1.2"

    def connect(self, frame: Frame, response: ConnectedFrame | None = None) -> None:
        """Establish a new connection.

        For servers with authentication enabled, check the frame's ``login`` and
        ``passcode`` headers.

        :param frame: A ``CONNECT`` frame.
        :param response: A ``CONNECTED`` frame, if this method is called from
            the handler for a greater version of the protocol specification or
            `None`, if this method is the first to see the ``CONNECT`` frame.

        :raises AuthError: if the frame's ``login` and/or ``passcode`` are rejected.
        :raises ProtocolError: if the frame's ``heart-beat`` header is malformed or
            required headers are missing.

        """
        host = frame.headers.get("host")
        if not host:
            raise ProtocolError('"host" header is required')
        if host != socket.getfqdn():
            raise ProtocolError("Virtual hosting is not supported or host is unknown")
        response = response or ConnectedFrame(str(uuid.uuid4()))
        response.headers.setdefault("version", "1.2")
        super().connect(frame, response)

    def ack(self, frame):
        if "id" not in frame.headers:
            raise ProtocolError("No 'id' specified for ACK command.")
        if "message-id" not in frame.headers:
            raise ProtocolError("No message-id specified for ACK command.")
        self.engine.queue_manager.ack(
            self.engine.connection, frame, id=frame.headers["id"]
        )
