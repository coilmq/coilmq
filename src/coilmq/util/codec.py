from __future__ import annotations

import codecs
import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from typing_extensions import Buffer

__all__ = [
    "register",
]


class StompCodec(codecs.Codec):
    """Convert text to/from utf-8 with escape sequences.

    :param escapes: character, escape sequence pairs

    """

    def __init__(self, escapes: list[tuple[str, str]]) -> None:
        """Initialize the object."""
        self.encode_map: dict[str, str] = {}
        self.decode_map: dict[bytes, bytes] = {}

        for source, escape in escapes:
            self.encode_map[source] = escape
            self.decode_map[escape.encode()] = source.encode()

        self.pattern = re.compile(
            f"[{''.join(re.escape(source) for source in self.encode_map)}]"
        )

    def encode(self, input: str, errors: str = "strict") -> tuple[bytes, int]:
        """Return the binary representation of a given text."""
        parts: list[str] = []
        start: int = 0

        for match in self.pattern.finditer(input):
            escape = self.encode_map[match[0]]
            parts.extend((input[start : match.start()], escape))
            start = match.end()

        parts.append(input[start:])

        return "".join(parts).encode(errors=errors), len(input)

    def decode(self, input: Buffer, errors: str = "strict") -> tuple[str, int]:
        """Return the text represented by utf-8 with escape sequences bytes."""
        if not isinstance(input, bytes):
            input = bytes(input)

        parts: list[bytes] = []
        start: int = 0

        while (index := input.find(b"\\", start)) != -1:
            escape = input[index : 2 + index]

            if len(escape) != 2:
                msg = f"incomplete escape sequence at index {index}"
                codecs.strict_errors(UnicodeError(msg))

            try:
                source = self.decode_map[escape]
            except KeyError as err:
                msg = f"invalid escape sequence: {err.args[0]}"
                codecs.strict_errors(UnicodeError(msg))

            parts.extend((input[start:index], source))
            start = 2 + index

        parts.append(input[start:])

        return b"".join(parts).decode(errors=errors), len(input)


STOMP_1P1 = StompCodec([
    ("\n", "\\n"),
    (":", "\\c"),
    ("\\", "\\\\"),
])
"""The STOMP 1.1 codec escapes newlines, colons, and the escape character itself."""

STOMP_1P2 = StompCodec([
    ("\r", "\\r"),
    ("\n", "\\n"),
    (":", "\\c"),
    ("\\", "\\\\"),
])
"""The STOMP 1.2 codec escapes carriage returns (and the 1.1 codec characters.)"""


def search_function(encoding_name: str) -> codecs.CodecInfo | None:
    """Return a STOMP codec.

    :param encoding_name: the name of an encoding

    :returns: the codec associated with the name, if its a STOMP codec, otherwise `None`

    """
    if encoding_name == "stomp1.0":
        return codecs.lookup("ascii")
    if encoding_name == "stomp1.1":
        return codecs.CodecInfo(STOMP_1P1.encode, STOMP_1P1.decode, name="stomp1.1")
    if encoding_name == "stomp1.2":
        return codecs.CodecInfo(STOMP_1P2.encode, STOMP_1P2.decode, name="stomp1.2")
    return None


@contextmanager
def register() -> Generator[None, None, None]:
    """Register and, if possible, unregister the STOMP codec search function."""
    try:
        codecs.register(search_function)
        yield
    finally:
        try:
            codecs.unregister(search_function)
        except AttributeError:
            # `codecs.unregister` was added in 3.10. As long as CoilMQ supports Python
            # versions older than 3.10, ignore a failed attempt to reference the method.
            pass
