"""Tests for authenticators."""

from io import StringIO
from pathlib import Path

try:
    from importlib.resources import as_file, files
except ImportError:  # pragma: no cover
    from importlib_resources import as_file, files

import pytest

from coilmq.auth.simple import SimpleAuthenticator

__authors__ = ['"Hans Lellelid" <hans@xmpl.org>']
__copyright__ = "Copyright 2009 Hans Lellelid"
__license__ = """Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""


class TestSimpleAuthenticator:
    def test_constructor(self) -> None:
        """Test the with passing auth store in constructor."""
        auth = SimpleAuthenticator({"user": "pass"})
        assert auth.authenticate("user", "pass") == True
        assert auth.authenticate("user1", "pass") == False
        assert auth.authenticate("user", "pass2") == False

    def test_from_ini_path_str(self) -> None:
        """Test loading store from a `str` path."""
        with as_file(files("tests.resources").joinpath("auth.ini")) as filename:
            auth = SimpleAuthenticator.from_ini(str(filename))
        assert auth.authenticate("juniper", "b3rr1es") == True
        assert auth.authenticate("oak", "ac$rrubrum") == True
        assert auth.authenticate("pinetree", "str0bus") == True
        assert auth.authenticate("foo", "bar") == False

    def test_from_ini_path_bytes(self) -> None:
        """Test loading store from a `bytes` path."""
        with as_file(files("tests.resources").joinpath("auth.ini")) as filename:
            auth = SimpleAuthenticator.from_ini(str(filename).encode())
        assert auth.authenticate("juniper", "b3rr1es") == True
        assert auth.authenticate("oak", "ac$rrubrum") == True
        assert auth.authenticate("pinetree", "str0bus") == True
        assert auth.authenticate("foo", "bar") == False

    def test_from_ini_path_object(self) -> None:
        """Test loading from a `Path`."""
        with as_file(files("tests.resources").joinpath("auth.ini")) as filename:
            auth = SimpleAuthenticator.from_ini(Path(filename))
        assert auth.authenticate("juniper", "b3rr1es") == True
        assert auth.authenticate("oak", "ac$rrubrum") == True
        assert auth.authenticate("pinetree", "str0bus") == True
        assert auth.authenticate("foo", "bar") == False

    def test_from_ini_file(self) -> None:
        """Test loading from a file-like object."""
        with as_file(
            files("tests.resources").joinpath("auth.ini")
        ) as filename, filename.open() as fp:
            auth = SimpleAuthenticator.from_ini(fp)

        assert auth.authenticate("juniper", "b3rr1es") == True
        assert auth.authenticate("oak", "ac$rrubrum") == True
        assert auth.authenticate("pinetree", "str0bus") == True
        assert auth.authenticate("foo", "bar") == False

    def test_from_ini_non_existent_file(self) -> None:
        """Test loading from path to a non-existent file."""
        with as_file(files("tests.resources").joinpath("auth-invalid.ini")) as filename:  # noqa: SIM117
            with pytest.raises(
                FileNotFoundError,
                match=r"\[Errno 2\] No such file or directory: '.*?auth-invalid\.ini'",
            ):
                SimpleAuthenticator.from_ini(filename)

    def test_from_ini_no_auth_section(self) -> None:
        """Test loading from a source without an ``[auth]`` section."""
        fp = StringIO("[something-else]\nusername=password")
        with pytest.raises(ValueError, match=r"No \[auth\] section in file: '.*?'"):
            SimpleAuthenticator.from_ini(fp)

    def test_from_ini_not_an_ini(self) -> None:
        """Test loading from a source without an ``[auth]`` section."""
        fp = StringIO("Lorem ipsum dolor sit amet")
        with pytest.raises(ValueError, match=r"Could not read file: '.*?'"):
            SimpleAuthenticator.from_ini(fp)
