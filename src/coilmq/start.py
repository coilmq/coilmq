"""Entrypoint for starting the application."""

from __future__ import annotations

import logging
import os
import threading
import warnings
from contextlib import nullcontext
from typing import TYPE_CHECKING

is_nt = os.name == "nt"

if not is_nt:
    import daemon as pydaemon
    import pid
else:
    pydaemon = pid = None

import click
from click_option_group import optgroup

import coilmq.util.codec
from coilmq.config import CONFIG, init_config, init_logging, resolve_name
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


def server_from_config(config=None, server_class=None, additional_kwargs=None):
    """Gets a configured :class:`coilmq.server.socket_server.StompServer` from specified config.

    If :paramref:`config` is :py:obj:`None`, global L{coilmq.config.config} var will be used instead.

    :param config: A loaded configuration.
    :type config: configparser.ConfigParser

    :param server_class:
        Which class to use for the server.

    :param additional_kwargs:
        Any additional args that should be passed to class.

    :returns: The configured StompServer.
    :rtype: coilmq.server.socket_server.StompServer
    """
    if not config:
        config = CONFIG

    queue_store_factory = resolve_name(config.get("coilmq", "qstore.factory"))
    subscriber_scheduler_factory = resolve_name(
        config.get("coilmq", "scheduler.subscriber_priority_factory")
    )
    queue_scheduler_factory = resolve_name(
        config.get("coilmq", "scheduler.queue_priority_factory")
    )

    if config.has_option("coilmq", "auth.factory"):
        authenticator_factory = resolve_name(config.get("coilmq", "auth.factory"))
        authenticator: Authenticator = authenticator_factory()
    else:
        authenticator = None

    server = ThreadedStompServer(
        (config.get("coilmq", "listen_addr"), config.getint("coilmq", "listen_port")),
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
    configfile,
    listen_addr,
    listen_port,
    logfile,
    debug,
    daemon,
    uid,
    gid,
    pidfile,
    umask,
    rundir,
):
    """Takes a context object, which implements the __enter__/__exit__ "with" interface
    and starts a server within that context.

    This method is a refactored single-place for handling the server-run code whether
    running in daemon or non-daemon mode.  It is invoked with a dummy (passthrough)
    context object for the non-daemon use case.

    :param options: The compiled collection of options that need to be parsed.
    :type options: configparser.ConfigParser
    :param context: The context object that implements __enter__/__exit__ "with"
        methods.
    :type context: object

    :raises Exception: Any underlying exception will be logged but then re-raised.

    .. seealso:: :func:`server_from_config`
    """
    log_level = logging.DEBUG if debug else logging.INFO

    # There's a possibility here that init_logging() will throw an exception.  If it does,
    # AND we're in a daemon context, then we're not going to be able to do anything with it.
    # We've got no stderr/stdout here; and so (to my knowledge) no reliable (& cross-platform),
    # way to display errors.
    init_logging(logfile=logfile, loglevel=log_level, configfile=configfile)

    server = server_from_config()

    interval = CONFIG.getfloat("coilmq", "debug.stats_poll_interval")
    stats_thread = RepeatThread(interval, stats_loop, (server,))
    stats_thread.name = "DiagnosticThread"
    stats_thread.daemon = True

    try:
        if log_level <= logging.DEBUG and interval > 0:
            stats_thread.start()

        LOGGER.info("STOMP server listening on %s:%s", *server.server_address)

        try:
            server.serve_forever()
        finally:
            stats_thread.cancel()

    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Stomp server stopped by user interrupt.")
    except Exception:
        LOGGER.exception("Stomp server stopped due to error")
    finally:
        server.shutdown()
        server.server_close()


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
    default=int(CONFIG.get("coilmq", "listen_port")),
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
    help="Log to specified file (unless logging configured in config file).",
    metavar="FILE",
)
@optgroup.option(
    "--debug",
    default=False,
    is_flag=True,
    help="Sets logging to debug (unless logging configured in config file).",
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
    debug: bool,
    daemon: bool,
    uid: int | None,
    gid: int | None,
    pidfile: str | None,
    umask: int | None,
    rundir: str,
):
    """Run a CoilMQ server."""
    # Initialize the configuration before entering the context block.  Wait until inside
    # the context block to initialize logging.
    init_config(config)

    if host is not None:
        CONFIG.set("coilmq", "listen_addr", host)

    if port is not None:
        CONFIG.set("coilmq", "listen_port", str(port))

        if daemon and is_nt:
            warnings.warn(
                "Daemon context is not available for NT platform", stacklevel=2
            )

    # in an on-daemon mode, we use a dummy context object
    # so we can use the same run-server code as the daemon version.
    context = (
        pydaemon.DaemonContext(
            uid=uid,
            gid=gid,
            pidfile=None if pidfile is None else pid.PidFile(pidname=pidfile),
            umask=0 if umask is None else umask,
            working_directory=rundir,
        )
        if daemon and pydaemon
        else nullcontext()
    )

    with context, coilmq.util.codec.register():
        serve(
            config,
            host,
            port,
            logfile,
            debug,
            daemon,
            uid,
            gid,
            pidfile,
            umask,
            rundir,
        )


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
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        LOGGER.exception("Server terminated due to error")
