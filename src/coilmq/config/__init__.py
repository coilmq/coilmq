"""Configuration support functionality.

The global `CONFIG` object, a :py:class:`configparser.ConfigParser`, is initialized from
the default configuration file, ``defaults.cfg``, embedded in the `coilmq.config`
module.

"""

import importlib
import os.path
from configparser import ConfigParser
from typing import Final

try:
    from importlib.resources import as_file, files
except ImportError:  # pragma: no cover
    from importlib_resources import as_file, files


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

#: The global configuration object containing the default configuration.
CONFIG: Final[ConfigParser] = ConfigParser()
with as_file(
    files("coilmq.config").joinpath("defaults.cfg")
) as filename, filename.open() as src:
    CONFIG.read_file(src)


def init_config(config_file=None):
    r"""Override and/or add to the global configuration.

    The values in ``config_file`` will override and/or add to those in `CONFIG` that
    were loaded from the embedded default configuration file.

        >>> from coilmq.config import CONFIG, init_config
        >>> CONFIG.getint("coilmq", "listen_port")
        61613
        >>> from tempfile import NamedTemporaryFile
        >>> with NamedTemporaryFile("w") as tmp:
        ...     print("[coilmq]\nlisten_port = 12345", file=tmp, flush=True)
        ...     init_config(tmp.name)
        >>> CONFIG.getint("coilmq", "listen_port")
        12345

    :param config_file: The path to a configuration file.
    :type config_file: str

    :raises ValueError: if the specified file could not be read.

    """
    if config_file and os.path.exists(config_file):
        read = CONFIG.read([config_file])
        if not read:
            raise ValueError(f"Could not read configuration from file: {config_file}")


def resolve_name(name):
    """Resolve a dotted name to some object (usually class, module, or function).

    Supported naming formats include:

    1. ``path.to.module:method``
    2. ``path.to.module.ClassName``

    >>> resolve_name('coilmq.store.memory.MemoryQueue')
    <class 'coilmq.store.memory.MemoryQueue'>
    >>> t = resolve_name('coilmq.store.dbm:make_dbm')
    >>> import inspect
    >>> inspect.isfunction(t)
    True
    >>> t.__name__
    'make_dbm'

    :param name: The dotted name (e.g. ``path.to.MyClass``)
    :type name: str

    :returns: The resolved object (class, callable, etc.) or :py:obj:`None` if not
        found.
    """
    sep_index = max(name.rfind(sep) for sep in (":", "."))

    module_name = name[:sep_index]
    member_name = name[1 + sep_index :]

    module = importlib.import_module(module_name)

    return getattr(module, member_name)
