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
import os
import re
from functools import wraps
from itertools import islice
from multiprocessing.pool import ThreadPool
from socket import AF_INET, SOCK_DGRAM, socket
from time import perf_counter
from time import time as unix_time

LOGLEVEL = os.getenv("LOGLEVEL", "INFO").upper()
logging.basicConfig(level=LOGLEVEL)
logger = logging.getLogger("Unvanquished Tray")

PROTOCOL = 86
PREFIX = b"\xff\xff\xff\xff"
RECORD_SEP = b"\\"
SERVER_RECORD_LEN = 7  # IPv4, port, separator
GET_STATUS_BUFFER = 2**14
Q_GET_SERVERS = PREFIX + f"getservers {PROTOCOL}".encode("ascii")
R_GET_SERVERS = PREFIX + b"getserversResponse" + RECORD_SEP
Q_GET_STATUS = PREFIX + b"getstatus"
R_GET_STATUS = PREFIX + b"statusResponse\n" + RECORD_SEP

SOCKET_TIMEOUT = 1


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


def strip_emoticons(string):
    """Removes emoticon tags and normalizes whitespace."""
    return re.sub("\s*(\[.*?\]|\s)\s*", " ", string).strip()


class Server:
    @staticmethod
    def _valid_or(default=None):
        def wrapper(method):
            @wraps(method)
            def wrapped(server, *args, **kwargs):
                if server._config:
                    return method(server, *args, **kwargs)
                else:
                    return default

            return wrapped

        return wrapper

    def __init__(self, host, port):
        self._host = host
        self._port = port

        self._config = None
        self._ping = None

        self._last_refresh = 0
        self._last_refresh_error = None

    def __hash__(self):
        return hash(self._host) ^ hash(self._port)

    def __eq__(self, other):
        return self._host == other._host and self._port == other._port

    def __str__(self):
        return (
            f"{self.num_playing}+{self.num_spectating}"
            f" on {self.stripped_name}"
            f" ({self.map_name}, {self.ping * 1000:.0f} ms)"
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
        self._ping = perf_counter() - t

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
            self._ping = None

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
    @_valid_or(float("inf"))
    def ping(self):
        assert self._ping
        return self._ping

    @property
    @_valid_or("unknown")
    def name(self):
        """Name of the server as given."""
        assert self._config
        return self._config["sv_hostname"]

    @property
    def stripped_name(self):
        """Name of the server without color codes."""
        return strip_emoticons(strip_colors(self.name))

    @property
    @_valid_or("unknown")
    def map_name(self):
        """Name of the server as given."""
        assert self._config
        return self._config["mapname"]

    @property
    @_valid_or((0,) * 5)
    def player_stats(self):
        assert self._config

        try:
            B = self._config["B"]
            P = self._config["P"]
        except KeyError as error:
            raise RuntimeError("No bot/player status fields found.") from error

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


class ServerList:
    @staticmethod
    def _check_refresh(method):
        @wraps(method)
        def wrapped(servers, *args, **kwargs):
            current_time = unix_time()

            if current_time - servers._last_update > servers._update_time:
                servers.try_update_servers()

            if current_time - servers._last_refresh > servers._refresh_time:
                servers.refresh_servers()

            return method(servers, *args, **kwargs)

        return wrapped

    def __init__(
        self,
        main_address="master.unvanquished.net",
        main_port=27950,
        *,
        max_servers=2**9,
        update_time=60.0,
        refresh_time=1.0,
    ):
        self._host = main_address
        self._port = main_port
        self._max_servers = max_servers
        self._update_time = update_time
        self._refresh_time = refresh_time

        self._servers = set()
        self._last_update = 0
        self._last_update_error = None
        self._last_refresh = 0

    @property
    def _main_str(self):
        return f"{self._host}:{self._port}"

    def query_addresses(self):
        logger.debug(f"Requesting server list from {self._main_str}.")

        con = socket(AF_INET, SOCK_DGRAM)
        con.settimeout(SOCKET_TIMEOUT)
        con.connect((self._host, self._port))
        con.send(Q_GET_SERVERS)
        response = con.recv(len(R_GET_SERVERS) + 7 * self._max_servers)

        if not response:
            raise RuntimeError(
                f"Failed to query main server at {self._main_str} for servers:"
                f" no response."
            )

        if not response.startswith(R_GET_SERVERS):
            raise RuntimeError(
                f"Failed to query main server at {self._main_str}:"
                f" bad response header."
            )

        response = response[len(R_GET_SERVERS) :]

        if len(response) % SERVER_RECORD_LEN:
            raise RuntimeError(
                f"Main server at {self._main_str} sent faulty server list:"
                f" payload has unexpected size of {len(response)}"
                f" (not a multiple of {SERVER_RECORD_LEN})."
            )

        num_servers = len(response) // SERVER_RECORD_LEN

        for i in range(num_servers):
            ip0, ip1, ip2, ip3, port0, port1, sep = response[
                SERVER_RECORD_LEN * i : SERVER_RECORD_LEN * (i + 1)
            ]

            if sep != ord(RECORD_SEP):
                raise RuntimeError(
                    f"Main server at {self._main_str} sent faulty server list:"
                    f" unexpected separator byte {chr(sep)}."
                )

            server_addr = f"{ip0:d}.{ip1:d}.{ip2:d}.{ip3:d}"
            server_port = (port0 << 8) + port1

            yield server_addr, server_port

    def update_servers(self):
        """Retrieve a server list and refresh all servers.

        :raises RuntimeError:
            If the server list could not be retrieved.
        """
        self._servers.update(
            Server(host, port) for host, port in self.query_addresses()
        )
        self._last_update = unix_time()

        self.refresh_servers()

    def try_update_servers(self):
        """Try to retrieve a server list and refresh all servers on success."""
        try:
            self.update_servers()
        except Exception as error:
            error_str = str(error)

            # Log new errors with INFO, repeated errors with DEBUG level.
            logger.log(
                logging.INFO
                if error_str != self._last_update_error
                else logging.DEBUG,
                f"Failed to fetch servers from {self._main_str}: {error}",
            )

            self._last_update_error = error_str
        else:
            self._last_update_error = None

    def refresh_servers(self):
        """Refresh all currently known servers (failure resets status)."""
        if self._servers:
            with ThreadPool(len(self._servers)) as pool:
                pool.map(Server.refresh_or_reset, self._servers)

            self._last_refresh = unix_time()

    def _ranking(self, server):
        return (-server.num_playing, -server.num_spectating, server.ping)

    @_check_refresh
    def online(self):
        """Whether any servers responded recently."""
        if not self._servers:
            return False

        if not any(
            server.age < 1.5 * self._refresh_time for server in self._servers
        ):
            return False

        return True

    @property
    @_check_refresh
    def sorted_entries(self):
        return sorted(self._servers, key=self._ranking)

    @_check_refresh
    def filter(
        self,
        *,
        only_responsive=True,
        max_servers=None,
        max_ping=None,
        min_players=0,
        min_playing=0,
    ):
        selected = []
        for server in self._servers:
            if only_responsive and not server.responsive:
                continue

            if max_ping is not None and server.ping > max_ping:
                continue

            if server.num_players < min_players:
                continue

            if server.num_playing < min_playing:
                continue

            selected.append(server)

            if max_servers is not None and len(selected) >= max_servers:
                break

        servers = sorted(selected, key=self._ranking)

        return servers if max_servers is None else servers[:max_servers]

    @property
    @_check_refresh
    def max_playing(self):
        """Largest number of active players on any server."""
        return max(server.num_playing for server in self._servers)

    @_check_refresh
    def __str__(self):
        return "\n".join(
            f"{server.address:>21}"
            f" | {server.ping * 1000:3.0f} ms"
            f" | {a}:{h}+{spec} players"
            f" | {ab}:{hb} bots"
            f" | {server.map_name[:15]:>15}"
            f" | {server.stripped_name}"
            for server in self.sorted_entries
            for spec, a, h, ab, hb in (server.player_stats,)
        )


if __name__ == "__main__":
    servers = ServerList()
    print(servers)
