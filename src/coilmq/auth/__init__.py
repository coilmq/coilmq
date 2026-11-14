"""Authentication for STOMP over TCP.

The STOMP protocol specifies that a client may set ``login`` and ``passcode``
headers in the ``CONNECT`` (or ``STOMP``) frame to authenticate with the server.
CoilMQ provides an `Authenticator` abstract base class that defines the
interface for classes that handle authentication using the STOMP protocol alone.

Authentication providers are instantiated and configured in the application
scope and shared across all request handlers.  Therefore, authenticator
implementations must be thread-safe.

"""

import abc

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


class Authenticator(abc.ABC):
    """Abstract base class for authenticators."""

    @abc.abstractmethod
    def authenticate(self, login: str, passcode: str) -> bool:
        """Authenticate a ``CONNECT`` frame's ``login`` and ``passcode`` headers.

        :param login: The user identifier to authenticate.
        :param passcode: The password to authenticate.

        :returns: `True` if ``login`` is a known user identifier and
            ``passcode`` matches the password associated with ``login``,
            otherwise `False`.

        """
