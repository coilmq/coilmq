"""A simple authenticator implementation."""

from configparser import ConfigParser

from coilmq.auth import Authenticator
from coilmq.config import config
from coilmq.exception import ConfigError

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


def make_simple():
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

    """
    authfile = config.get("coilmq", "auth.simple.file")
    if not authfile:
        raise ConfigError("Missing configuration parameter: auth.simple.file")
    sa = SimpleAuthenticator()
    sa.from_configfile(authfile)
    return sa


class SimpleAuthenticator(Authenticator):
    """A simple configfile-based authenticator.

    :var store: Authentication key-value store (of logins to passwords).
    :vartype store: dict[str, str]
    """

    def __init__(self, store=None):
        """Initialize the authenticator to use (optionally) specified :paramref:`store`.

        :param store: Authentication store whose keys are user names and values are
            passwords.
        :type store: dict[str, str]
        """
        if store is None:
            store = {}
        self.store = store

    def from_configfile(self, configfile):
        """Initialize the authentication store from a "config"-style file.

        Auth "config" file is parsed with :py:class:`configparser.ConfigParser` and must contain
        an ``[auth]`` section whose keys are user names and values are passwords.

        Example auth file::

            [auth]
            someuser = somepass
            anotheruser = anotherpass

        :param configfile: Path to config file or file-like object.
        :type configfile: typing.Any
        :raises ValueError: If file could not be read or does not contain an ``[auth]``
            section.
        """
        cfg = ConfigParser()
        if hasattr(configfile, "read"):
            cfg.read_file(configfile)
        else:
            filesread = cfg.read(configfile)
            if not filesread:
                raise ValueError(f"Could not parse auth file: {configfile}")

        if not cfg.has_section("auth"):
            raise ValueError("Config file contains no [auth] section.")

        self.store = dict(cfg.items("auth"))

    def authenticate(self, login: str, passcode: str) -> bool:
        return login in self.store and self.store[login] == passcode
