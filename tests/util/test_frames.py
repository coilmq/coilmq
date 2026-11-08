from __future__ import annotations

import io
from collections import OrderedDict

import pytest

from coilmq.util.frames import EmptyBuffer, parse_headers


@pytest.mark.parametrize(
    ["encoding", "frame", "expectation"],
    [
        # Command and preamble (i.e. the portion of the frame that comes before a
        # potential first body octet) are both terminated by LF.
        (
            "stomp1.0",
            b"DISCONNECT\n\n\x00",
            ("DISCONNECT", OrderedDict()),
        ),
        # Command, header, and preamble are terminated by LF.
        (
            "stomp1.0",
            b"BEGIN\ntransaction:tx1\n\n\x00",
            ("BEGIN", OrderedDict([("transaction", "tx1")])),
        ),
        # Header value contains leading and trailing whitepace.  This case is intended
        # to demonstrate https://github.com/coilmq/coilmq/issues/99.
        (
            "stomp1.0",
            b"SEND\ndestination:/queue/foo\n foo : bar \n\n\x00",
            ("SEND", OrderedDict([("destination", "/queue/foo"), (" foo ", " bar ")])),
        ),
        # Header name and value contain leading and trailing whitepace and escaped
        # characters.  This case is intended to demonstrate
        # https://github.com/coilmq/coilmq/issues/100.
        (
            "stomp1.1",
            b"SEND\ndestination:/queue/foo\n foo \r\\n: bar\\c\\cbaz\r\\n \n\n\x00",
            (
                "SEND",
                OrderedDict([
                    ("destination", "/queue/foo"),
                    (" foo \r\n", " bar::baz\r\n "),
                ]),
            ),
        ),
        # Command and preamble are both terminated by CR+LF.
        (
            "stomp1.2",
            b"DISCONNECT\r\n\r\n\0",
            ("DISCONNECT", OrderedDict()),
        ),
        # Command, header, and preamble are terminated by CR+LF.
        (
            "stomp1.2",
            b"CONNECT\r\naccept-version:1.0\r\n\r\n\0",
            ("CONNECT", OrderedDict([("accept-version", "1.0")])),
        ),
        # Command is terminated by CR+LF, preamble by LF. Kooky, but possible.
        (
            "stomp1.2",
            b"DISCONNECT\r\n\n\0",
            ("DISCONNECT", OrderedDict()),
        ),
        # Command and header are terminated by CR+LF, preamble by LF. Also kooky.
        (
            "stomp1.2",
            b"CONNECT\r\naccept-version:1.0\r\n\n\0",
            ("CONNECT", OrderedDict([("accept-version", "1.0")])),
        ),
        # Header name and value contain leading and trailing whitepace and escaped
        # characters.  Command, header, and preamble are terminated by CR+LF.  This case
        # is intended to demonstrate https://github.com/coilmq/coilmq/issues/100.
        (
            "stomp1.2",
            b"SEND\r\ndestination:/queue/foo\r\n foo \\r\\n: bar\\c\\cbaz\\r\\n \r\n\r\n\x00",
            (
                "SEND",
                OrderedDict([
                    ("destination", "/queue/foo"),
                    (" foo \r\n", " bar::baz\r\n "),
                ]),
            ),
        ),
    ],
)
def test_parse_headers(
    encoding: str,
    frame: bytes,
    expectation: tuple[str, OrderedDict[str, str]],
) -> None:
    """Verify that `parse_headers` returns the expected value.

    :param frame: the frame to parse
    :param expectation: the value that `parse_headers` is expected to return

    """
    assert parse_headers(io.BytesIO(frame), encoding) == expectation


@pytest.mark.parametrize(
    ["frame"],
    [
        (b"",),
        (b"\n\n\0",),
    ],
)
def test_parse_headers_empty_buffer(
    frame: bytes,
) -> None:
    """Verify that `parse_headers` raises the expected error.

    :param frame: the frame to parse

    """
    with pytest.raises(EmptyBuffer):
        parse_headers(io.BytesIO(frame))
