from __future__ import annotations

import codecs

import pytest


@pytest.mark.parametrize(
    ["encoding"],
    [
        ("stomp1.0",),
        ("stomp1.1",),
        ("stomp1.2",),
    ],
)
def test_codec_lookup(encoding: str) -> None:
    """Verify that a custom codec is available after registration.

    :param encoding: the name of a STOMP encoding

    """
    assert isinstance(codecs.lookup(encoding), codecs.CodecInfo)


@pytest.mark.parametrize(
    ["encoding", "text", "expected"],
    [
        ("stomp1.0", "\nfoo\rbar: baz\\ b\0ff", b"\nfoo\rbar: baz\\ b\0ff"),
        ("stomp1.1", "\nfoo\rbar: baz\\ b\0ff", b"\\nfoo\rbar\\c baz\\\\ b\0ff"),
        ("stomp1.2", "\nfoo\rbar: baz\\ b\0ff", b"\\nfoo\\rbar\\c baz\\\\ b\0ff"),
    ],
)
def test_encoding(
    encoding: str,
    text: str,
    expected: bytes,
) -> None:
    """Verify that a given encoding can round-trip text to binary.

    :param text: the text to encode
    :param encoding: the name of a STOMP encoding
    :param expected: the binary representation of ``text`` expected for ``encoding``

    """
    encoded = text.encode(encoding)

    assert encoded == expected

    decoded = encoded.decode(encoding)

    assert decoded == text


@pytest.mark.parametrize(
    ["encoding"],
    [
        ("stomp1.1",),
        ("stomp1.2",),
    ],
)
def test_detect_incomplete_escape(encoding: str) -> None:
    """Verify that the codec detects an incomplete escape sequence.

    :param encoding: the name of a STOMP encoding

    """
    with pytest.raises(
        UnicodeError, match=r".*incomplete escape sequence at index 0.*"
    ):
        b"\\".decode(encoding)


@pytest.mark.parametrize(
    ["encoding"],
    [
        ("stomp1.1",),
        ("stomp1.2",),
    ],
)
def test_detect_invalid_escape(encoding: str) -> None:
    """Verify that the codec detects an invalid escape sequence.

    :param encoding: the name of a STOMP encoding

    """
    with pytest.raises(UnicodeError, match=r".*invalid escape sequence: b'\\\\x'.*"):
        b"\\x".decode(encoding)
