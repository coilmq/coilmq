from __future__ import annotations

import io
from collections import OrderedDict

import pytest

from coilmq.util.frames import EmptyBuffer, parse_headers


@pytest.mark.parametrize(
    ["frame", "expectation"],
    [
        # Command and preamble (i.e. the portion of the frame that comes before a
        # potential first body octet) are both terminated by LF.
        (
            b"DISCONNECT\n\n\x00",
            ("DISCONNECT", OrderedDict()),
        ),
        # Command, header, and preamble are terminated by LF.
        (
            b"BEGIN\ntransaction:tx1\n\n\x00",
            ("BEGIN", OrderedDict([("transaction", "tx1")])),
        ),
        # Header value contains leading and trailing whitepace. The case is intended to
        # demonstrate https://github.com/coilmq/coilmq/issues/99.
        (
            b"SEND\ndestination:/queue/foo\n foo : bar \n\n\x00",
            ("SEND", OrderedDict([("destination", "/queue/foo"), (" foo ", " bar ")])),
        ),
    ],
)
def test_parse_headers(
    frame: bytes,
    expectation: tuple[str, OrderedDict[str, str]],
) -> None:
    """Verify that `parse_headers` returns the expected value.

    :param frame: the frame to parse
    :param expectation: the value that `parse_headers` is expected to return

    """
    assert parse_headers(io.BytesIO(frame)) == expectation


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
