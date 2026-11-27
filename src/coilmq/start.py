"""Entrypoint for starting the application."""

from __future__ import annotations

import enum
import logging
import logging.config
import os
import threading
import warnings
from configparser import ConfigParser
from contextlib import nullcontext
from typing import TYPE_CHECKING

import click
import daemon as pydaemon
import pid
from click_option_group import optgroup

import coilmq.util.codec
from coilmq.config import CONFIG, init_config, resolve_name
from coilmq.queue import QueueManager
from coilmq.server.socket_server import ThreadedStompServer
from coilmq.topic import TopicManager

if TYPE_CHECKING:
    from coilmq.auth import Authenticator

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

LOGGER = logging.getLogger(__name__)


def server_from_config() -> ThreadedStompServer:
    """Initialize a server from the global configuration.

    :returns: The configured server.

    """
    queue_store_factory = resolve_name(CONFIG.get("coilmq", "qstore.factory"))

    subscriber_scheduler_factory = resolve_name(
        CONFIG.get("coilmq", "scheduler.subscriber_priority_factory")
    )

    queue_scheduler_factory = resolve_name(
        CONFIG.get("coilmq", "scheduler.queue_priority_factory")
    )

    if CONFIG.has_option("coilmq", "auth.factory"):
        authenticator_factory = resolve_name(CONFIG.get("coilmq", "auth.factory"))
        authenticator: Authenticator = authenticator_factory()
    else:
        authenticator = None

    addr = CONFIG.get("coilmq", "listen_addr")
    port = CONFIG.getint("coilmq", "listen_port")

    server = ThreadedStompServer(
        (addr, port),
        queue_manager=QueueManager(
            store=queue_store_factory(),
            subscriber_scheduler=subscriber_scheduler_factory(),
            queue_scheduler=queue_scheduler_factory(),
        ),
        topic_manager=TopicManager(),
        authenticator=authenticator,
    )

    LOGGER.info("Created server: %r", server)

    return server


def serve(
    config: str | None,
    log: bool | None,
    log_filename: str | None,
    log_format: str | None,
    log_level: int | None,
):
    """Start the STOMP server.

    This function uses the provided arguments to configure logging then starts the STOMP
    server.

    If ``config`` is a path to a readable INI-style file with a ``[loggers]`` section,
    it is passed to `logging.config.fileConfig` and other ``log*`` arguments are
    ignored.  If ``log`` is `True` or any of the ``log_*`` arguments are non-`None`,
    configure logging with `logging.basicConfig`; default values are substituted for
    ``log_*`` arguments whose values are `None`.

    :param config: A CoilMQ configuration file path; used to configure logging if
        non-`None`.

    :param log: If `True`, configure logging with `logging.basicConfig`.

    :param log_filename: The path to a file where log messages will be written.  If
        `logging.basicConfig` is called and this argument is `None`, log messages are
        not written to a file.

    :param log_format: A %-style log message format string.  See the `LogRecord
        attributes`_ documentation for a listing of the fields a format string can
        reference.  If `logging.basicConfig` is called and this argument is `None`, the
        format string used is ``"%(levelname)-8s %(message)s"``.

    :param log_level: A numeric log level.  If `logging.basicConfig` is called and this
        argument is `None`, the log level is `logging.INFO`.

    .. _LogRecord attributes:
        https://docs.python.org/3/library/logging.html#logrecord-attributes

    """
    log_arg = any(x is not None for x in [log_filename, log_format, log_level])

    # Option 1: configure logging with user-provided configuration file
    cfg = ConfigParser()

    if (
        config is not None
        and os.path.exists(config)
        and cfg.read([config])
        and cfg.has_section("loggers")
    ):
        if log or log_arg:
            logging.warning(  # ruff: ignore[root-logger-call]
                "configuring logging with file %s (ignoring logging CLI argument)",
                config,
            )
        logging.config.fileConfig(config, disable_existing_loggers=False)

    # Option 2: configure logging with user-provided --log* arguments
    if log or log_arg:
        logging.basicConfig(
            filename=log_filename,
            level=logging.INFO if log_level is None else log_level,
            format="%(levelname)-8s %(message)s" if log_format is None else log_format,
        )

    server = server_from_config()

    interval = CONFIG.getfloat("coilmq", "debug.stats_poll_interval")
    stats_thread = RepeatThread(interval, stats_loop, (server,))
    stats_thread.name = "DiagnosticThread"
    stats_thread.daemon = True

    try:
        if interval > 0:
            stats_thread.start()

        LOGGER.info("STOMP server listening on %s:%s", *server.server_address)

        try:
            server.serve_forever()
        finally:
            stats_thread.cancel()

    finally:
        server.shutdown()
        server.server_close()


class LogLevel(enum.IntEnum):
    CRITICAL = logging.CRITICAL
    FATAL = logging.FATAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG


@click.command()
@click.option(
    "-c",
    "--config",
    help="read configuration from CONFIG; extends the default configuration",
    metavar="CONFIG",
)
@optgroup.group(
    "Server configuration",
    help="These options override settings loaded from configuration files.",
)
@optgroup.option(
    "-b",
    "--host",
    default=CONFIG.get("coilmq", "listen_addr"),
    show_default=True,
    help="listen on the specified address; overrides coilmq.listen_addr in CONFIG",
    metavar="ADDR",
)
@optgroup.option(
    "-p",
    "--port",
    default=CONFIG.getint("coilmq", "listen_port"),
    show_default=True,
    help="listen on the specified port; overrides coilmq.listen_port in CONFIG",
    type=int,
    metavar="PORT",
)
@optgroup.group(
    "Logging configuration",
    help="These options are ignored if CONFIG has a [loggers] section.",
)
@optgroup.option(
    "-l",
    "--logfile",
    help="Log to specified file (unless logging configured in config file). (DEPRECATED)",
    metavar="FILE",
)
@optgroup.option(
    "--debug",
    default=None,
    flag_value=True,
    is_flag=True,
    help="Sets logging to debug (unless logging configured in config file). (DEPRECATED)",
)
@optgroup.option(
    "--log",
    default=None,
    flag_value=True,
    is_flag=True,
    help="enable logging",
)
@optgroup.option(
    "--log-filename",
    help="configure logging to write to the specified file; implies --log",
    metavar="FILE",
)
@optgroup.option(
    "--log-format",
    help="configure logging to use the specified format; implies --log",
)
@optgroup.option(
    "--log-level",
    type=click.Choice(LogLevel, case_sensitive=False),
    help="configure logging to display logs at (and above) the specified level; implies --log",
)
@optgroup.group(
    name="Daemon configuration",
    help="These options are ignored on non-POSIX operating systems.",
)
@optgroup.option(
    "-d",
    "--daemon",
    default=False,
    show_default=True,
    is_flag=True,
    help="run server as a daemon",
)
@optgroup.option(
    "-u",
    "--uid",
    help="daemon process UID",
    type=int,
    metavar="UID",
)
@optgroup.option(
    "-g",
    "--gid",
    help="daemon process GID",
    type=int,
    metavar="GID",
)
@optgroup.option(
    "--pidfile",
    help="file path for the PID file that the daemon will create",
    metavar="FILE",
)
@optgroup.option(
    "--umask",
    help="umask, in octal, to apply to the daemon process",
    type=lambda x: int(x, 8),
    metavar="MASK",
)
@optgroup.option(
    "--rundir",
    default="/",
    show_default=True,
    help="daemon process working directory",
    metavar="DIR",
)
def main(
    config: str | None,
    host: str | None,
    port: int | None,
    logfile: str | None,
    debug: bool | None,
    log: bool | None,
    log_filename: str | None,
    log_format: str | None,
    log_level: int | None,
    daemon: bool,
    uid: int | None,
    gid: int | None,
    pidfile: str | None,
    umask: int | None,
    rundir: str,
):
    """Run a CoilMQ server."""
    init_config(config)

    if host is not None:
        CONFIG.set("coilmq", "listen_addr", host)

    if port is not None:
        CONFIG.set("coilmq", "listen_port", str(port))

    if logfile is not None:
        warnings.warn("The option 'logfile' is deprecated.", DeprecationWarning)

    if debug is not None:
        warnings.warn("The option 'debug' is deprecated.", DeprecationWarning)

    if log is None and (debug is not None or logfile is not None):
        log = True

    if log_filename is None and logfile is not None:
        log_filename = logfile

    if log_level is None and debug is not None:
        log_level = logging.DEBUG

    if daemon and os.name != "posix":
        warnings.warn("daemon mode is only supported on POSIX")
        daemon = False

    if daemon:
        context = pydaemon.DaemonContext(
            uid=uid,
            gid=gid,
            pidfile=None if pidfile is None else pid.PidFile(pidname=pidfile),
            umask=0 if umask is None else umask,
            working_directory=rundir,
        )
    else:
        context = nullcontext()

    with context, coilmq.util.codec.register():
        serve(config, log, log_filename, log_format, log_level)


class RepeatThread(threading.Timer):
    def run(self) -> None:
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


def stats_loop(server: ThreadedStompServer) -> None:
    LOGGER.debug("Stats heartbeat -------------------------------")
    for destination in server.queue_manager.store.destinations():
        LOGGER.debug(
            "Queue %s: size=%s, subscribers=%s",
            destination,
            server.queue_manager.store.size(destination),
            server.queue_manager.subscriber_count(destination),
        )


if __name__ == "__main__":
    main()
