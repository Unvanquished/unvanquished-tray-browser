# Unvanquished Tray - A minimalistic Unvanquished server browser
# Copyright (C) 2023  Maximilian Stahlberg
#
# This file is part of Unvanquished Tray. Unvanquished Tray is free software:
# you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# Unvanquished Tray is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import re
from functools import wraps
from itertools import islice
from socket import AF_INET, SOCK_DGRAM, socket
from time import perf_counter
from time import time as unix_time

from .common import QUERY_PREFIX, RECORD_SEP, SOCKET_TIMEOUT, logger
from .ping import Ping

GET_STATUS_BUFFER = 2**14
Q_GET_STATUS = QUERY_PREFIX + b"getstatus"
R_GET_STATUS = QUERY_PREFIX + b"statusResponse\n" + RECORD_SEP

MAX_SERVER_NAME_CHARS = 60
MAX_MAP_NAME_CHARS = 20


class Server:
    @staticmethod
    def strip_colors(string):
        stripped = ""
        chars = list(string)
        while chars:
            c = chars.pop(0)
            if c == "^" and chars:
                d = chars.pop(0)
                if d == "#":
                    chars = chars[6:]
            else:
                stripped += c
        return stripped

    @staticmethod
    def strip_emoticons(string):
        """Removes emoticon tags and normalizes whitespace."""
        return re.sub(r"\s*(\[.*?\]|\s)\s*", " ", string).strip()

    @staticmethod
    def _valid_or(default=None, *, fallback=None, cache=False):
        """Return a default if the last request did not produce a valid config.

        This decorates methods of :class:`Server`. The method will be executed
        if and only if the last server refresh, if any, was successful: the
        server must have provided a configuration that has passed initial
        sanity checks. If the method is either not executed or is executed and
        raises an exception, then the decorator returns the provided default
        value. In the latter case, the exception is further logged. If the
        method is successfully executed, then its return value is forwarded.

        Instead of a constant default, a fallback method can be provided that
        will be run instead of the (skipped or failed) decorated method and
        whose return value is then forwarded. This fallback should not depend
        on a valid configuration being provided by the server.

        If further caching is enabled, any return value forwarded in the
        presence of a server configuration will be cached within that
        configuration and returned immediately on a subsequent request.
        """
        assert default is None or fallback is None

        def wrapper(method):
            @wraps(method)
            def wrapped(server, *args, **kwargs):
                if server._config:
                    if cache and method in server._config:
                        return server._config[method]

                    try:
                        value = method(server, *args, **kwargs)
                    except Exception as error:
                        logger.warn(
                            f"Failed to obtain {method.__name__}"
                            f" for {server.address}: {error}"
                        )
                        value = fallback(server) if fallback else default

                    if cache:
                        server._config[method] = value

                    return value
                else:
                    return fallback(server) if fallback else default

            return wrapped

        return wrapper

    def __init__(self, host, port):
        self._host = host
        self._port = port

        self._config = None
        self._ping = Ping()

        self._last_refresh = 0
        self._last_refresh_error = None

    def __hash__(self):
        return hash(self._host) ^ hash(self._port)

    def __eq__(self, other):
        return self._host == other._host and self._port == other._port

    @staticmethod
    def _limit_to(string, length):
        return string if len(string) <= length else f"{string[:length-1]}…"

    def __str__(self):
        return (
            f"{self.num_playing}+{self.num_spectating}"
            f" on {self._limit_to(self.stripped_name, MAX_SERVER_NAME_CHARS)}"
            f" ({self._limit_to(self.map_name, MAX_MAP_NAME_CHARS)},"
            f" {self.ping * 1000:.0f} ms)"
        )

    def refresh(self):
        """Update the server status and ping.

        :raises RuntimeError:
            When the update has failed.
        """
        logger.debug(f"Refreshing {self.address}.")

        con = socket(AF_INET, SOCK_DGRAM)
        con.settimeout(SOCKET_TIMEOUT)
        con.connect((self._host, self._port))

        t = perf_counter()
        con.send(Q_GET_STATUS)
        response = con.recv(GET_STATUS_BUFFER)
        self._ping.register(perf_counter() - t)

        if not response:
            raise RuntimeError(
                f"Failed to query status of game server at {self.address}:"
                f" no response."
            )

        if not response.startswith(R_GET_STATUS):
            raise RuntimeError(
                f"Failed to query status of game server at {self.address}:"
                f" bad response header."
            )

        response = response[len(R_GET_STATUS) :]
        sections = response.splitlines()
        config = sections.pop(0).split(RECORD_SEP)

        if len(config) % 2 == 1:
            raise RuntimeError(
                f"Failed to query status of game server at {self.address}:"
                f" bad number of separators in config string section."
            )

        self._config = dict(
            (key.decode("ascii"), value.decode("utf8"))
            for it in (iter(config),)
            for _ in range(len(config) // 2)
            for key, value in (islice(it, 2),)
        )

        self._last_refresh = unix_time()

    def refresh_or_reset(self):
        """Try to :meth:`refresh` and reset state if it fails."""
        try:
            self.refresh()
        except Exception as error:
            error_str = str(error)

            # Log new errors with INFO, repeated errors with DEBUG level.
            logger.log(
                logging.INFO
                if error_str != self._last_refresh_error
                else logging.DEBUG,
                f"Failed to refresh game server {self.address}: {error_str}",
            )

            self._config = None
            self._ping.clear()

            self._last_refresh_error = error_str
        else:
            self._last_refresh_error = None

    @property
    def address(self):
        """Server's IP address and port as string."""
        return f"{self._host}:{self._port}"

    @property
    @_valid_or(False)
    def responsive(self):
        """Whether the last refresh attempt was successful.

        The content of the reported configuration is not checked.
        """
        return True

    @property
    def age(self):
        """Return time since last successful refresh in seconds."""
        return (
            unix_time() - self._last_refresh
            if self._last_refresh
            else float("inf")
        )

    @property
    def ping(self):
        """A moving average of recent response times."""
        return self._ping.mvavg

    @property
    @_valid_or(fallback=lambda server: server.address)
    def name(self):
        """Name of the server as given."""
        assert self._config
        return self._config["sv_hostname"]

    @property
    def stripped_name(self):
        """Name of the server without color codes."""
        return self.strip_emoticons(self.strip_colors(self.name))

    @property
    @_valid_or("unknown")
    def map_name(self):
        """Name of the server as given."""
        assert self._config
        return self._config["mapname"]

    @property
    @_valid_or((0,) * 5, cache=True)
    def player_stats(self):
        """Reports number of players (S/A/H) and bots (A/H) as five numbers."""
        assert self._config

        B = self._config["B"]
        P = self._config["P"]

        if len(B) != len(P):
            raise RuntimeError("Lengths of bot and player states do not match.")

        spectators, a_players, h_players, a_bots, h_bots = (0,) * 5

        for skill, team in zip(B, P):
            if skill == "-":  # real player
                if team == "-":  # empty slot
                    continue
                elif team == "0":
                    spectators += 1
                elif team == "1":
                    a_players += 1
                elif team == "2":
                    h_players += 1
                else:
                    raise RuntimeError("Bad team identifier for player.")
            else:  # bot
                if team == "1":
                    a_bots += 1
                elif team == "2":
                    h_bots += 1
                else:
                    raise RuntimeError("Bad team identifier for bot.")

        return spectators, a_players, h_players, a_bots, h_bots

    @property
    def num_players(self):
        """Number of players, both playing and spectating."""
        return sum(self.player_stats[:3])

    @property
    def num_playing(self):
        """Number of players on a team, excluding bots."""
        return sum(self.player_stats[1:3])

    @property
    def num_spectating(self):
        """Number of players not on a team."""
        return self.player_stats[0]
