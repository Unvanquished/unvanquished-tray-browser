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
from functools import wraps
from multiprocessing.pool import ThreadPool
from socket import AF_INET, SOCK_DGRAM, socket
from time import time as unix_time

from .common import QUERY_PREFIX, RECORD_SEP, SOCKET_TIMEOUT, logger
from .server import Server

PROTOCOL = 86
SERVER_RECORD_LEN = 7  # IPv4, port, separator
Q_GET_SERVERS = QUERY_PREFIX + f"getservers {PROTOCOL}".encode("ascii")
R_GET_SERVERS = QUERY_PREFIX + b"getserversResponse" + RECORD_SEP

MAX_SERVERS_RECEIVED = 2**9
DEFAULT_MAIN_SERVERS = (
    ("master.unvanquished.net", 27950),
    ("master2.unvanquished.net", 27950),
)


class MainServer:
    def __init__(self, host, port):
        self._host = host
        self._port = port

        self._last_error_str = None

    def __str__(self):
        return f"{self._host}:{self._port}"

    def get_addresses(self):
        logger.debug(f"Requesting server list from {self}.")

        con = socket(AF_INET, SOCK_DGRAM)
        con.settimeout(SOCKET_TIMEOUT)
        con.connect((self._host, self._port))
        con.send(Q_GET_SERVERS)
        response = con.recv(
            len(R_GET_SERVERS) + SERVER_RECORD_LEN * MAX_SERVERS_RECEIVED
        )

        if not response:
            raise RuntimeError("No response.")

        if not response.startswith(R_GET_SERVERS):
            raise RuntimeError("Unexpected response header.")

        response = response[len(R_GET_SERVERS) :]
        num_servers = len(response) // SERVER_RECORD_LEN

        addresses = []
        for i in range(num_servers):
            ip0, ip1, ip2, ip3, port0, port1, sep = response[
                SERVER_RECORD_LEN * i : SERVER_RECORD_LEN * (i + 1)
            ]

            if sep != ord(RECORD_SEP):
                raise RuntimeError(
                    f"Faulty server list: missing separator byte."
                )

            host = f"{ip0:d}.{ip1:d}.{ip2:d}.{ip3:d}"
            port = (port0 << 8) + port1

            addresses.append((host, port))

        logger.debug(f"Main server {self} sent {len(addresses)} servers.")

        return addresses

    def try_get_addresses(self):
        """Attempt to get a list of game servers; default to an empty list."""
        try:
            return self.get_addresses()
        except Exception as error:
            error_str = str(error)

            # Log new errors with INFO, repeated errors with DEBUG level.
            logger.log(
                logging.INFO
                if error_str != self._last_error_str
                else logging.DEBUG,
                f"Failed to fetch servers from {self}: {error}",
            )

            self._last_error_str = error_str

            return []


class ServerList:
    @staticmethod
    def _check_refresh(method):
        @wraps(method)
        def wrapped(servers, *args, **kwargs):
            current_time = unix_time()

            if current_time - servers._last_update > servers._update_time:
                servers.update_servers()

            if current_time - servers._last_refresh > servers._refresh_time:
                servers.refresh_servers()

            return method(servers, *args, **kwargs)

        return wrapped

    def __init__(
        self,
        main_servers=DEFAULT_MAIN_SERVERS,
        *,
        update_time=60.0,
        refresh_time=1.0
    ):
        self._mains = [MainServer(host, port) for host, port in main_servers]
        self._update_time = update_time
        self._refresh_time = refresh_time

        self._servers = set()
        self._last_update = 0
        self._last_refresh = 0

        # Prevent logging duplicate errors for each main server.
        for main in self._mains:
            setattr(main, "_last_error_str", None)

    def update_servers(self):
        """Retrieve game server lists and refresh all known servers."""
        if not self._mains:
            raise RuntimeError("No main server configured.")

        with ThreadPool(len(self._mains)) as pool:
            addresses = sum(
                pool.map(MainServer.try_get_addresses, self._mains), []
            )

        if addresses:
            self._servers.update(Server(host, port) for host, port in addresses)
            self._last_update = unix_time()

        self.refresh_servers()

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
