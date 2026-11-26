"""A simple authenticator implementation."""

from __future__ import annotations

import os
from configparser import ConfigParser, NoSectionError, ParsingError
from typing import TYPE_CHECKING, Final, TextIO

from coilmq.auth import Authenticator
from coilmq.config import CONFIG
from coilmq.exception import ConfigError

if TYPE_CHECKING:
    from typing_extensions import Self


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

__all__ = [
    "SimpleAuthenticator",
    "make_simple",
]


def make_simple() -> Authenticator:
    """Return an authenticator with login/passcode pairs loaded from a file.

    When a CoilMQ server's configuration file assigns this function to the
    ``auth.factory`` setting, this function creates the server's authenticator.
    The same configuration file must also assign a path to the
    ``auth.simple.file`` setting.  The path should refer to an INI file
    containing login/passcode pairs.  This function reads the the login/passcode
    pairs from the INI file's ``[auth]`` section.

    The following INI file snippet would tell CoilMQ to call this function to
    get an authenticator with login/passcode pairs loaded from
    ``/path/to/auth.ini``::

        [coilmq]
        auth.factory = coilmq.auth.simple:make_simple
        auth.simple.file = /path/to/auth.ini

    :returns: An authenticator populated from the file referenced by CoilMQ's
        global configuration.

    :raises ConfigError: if the CoilMQ configuration file does not define
        ``coilmq.auth.simple.file``.
    :raises FileNotFoundError: if the path given by ``auth.simple.file`` could
        not be opened.
    :raises ValueError: if the ``auth.simple.file`` is not a valid INI file or
        does not contain an ``[auth]`` section.

    """
    authfile = CONFIG.get("coilmq", "auth.simple.file")
    if not authfile:
        raise ConfigError("Missing configuration parameter: auth.simple.file")
    return SimpleAuthenticator.from_ini(authfile)


class SimpleAuthenticator(Authenticator):
    r"""A `dict`\ -backed authenticator.

    :param store: each item is a login/passcode pair

    """

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store: Final[dict[str, str]] = store or {}

    @classmethod
    def from_ini(cls, ini: TextIO | str | bytes | os.PathLike[str]) -> Self:
        """Initialize an authenticator from an INI file.

        Load credentials from an INI file with an ``[auth]`` section.  Each
        option in the ``[auth]`` section is a login/passcode pair.  A file with
        the following content, loaded with this method, would yield an
        authenticator with two login/passcode pairs::

            [auth]
            someuser = somepass
            anotheruser = anotherpass

        :param ini: Path to an INI file or file-like object opened in text mode.

        :raises FileNotFoundError: if the path could not be opened.
        :raises ValueError: if the file is not a valid INI file or does not
            contain an ``[auth]`` section.

        """
        cfg = ConfigParser()

        try:
            if isinstance(ini, (str, bytes, os.PathLike)):
                with open(ini) as src:
                    cfg.read_file(src)
            else:
                cfg.read_file(ini)
        except ParsingError as err:
            msg = f"Could not read file: '{ini}'"
            raise ValueError(msg) from err

        try:
            return cls(dict(cfg.items("auth")))
        except NoSectionError as err:
            msg = f"No [auth] section in file: '{ini}'"
            raise ValueError(msg) from err

    def authenticate(self, login: str, passcode: str) -> bool:
        return login in self.store and self.store[login] == passcode
