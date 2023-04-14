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

from time import time as unix_time


class Ping:
    def __init__(self, average_over_seconds=60):
        self._duration = average_over_seconds
        self._register = []
        self._min = float("inf")

    def _clear_old(self):
        if not self._register:
            return

        num_outdated = 0
        threshold = unix_time() - self._duration
        for t, _ in self._register:
            if t < threshold:
                num_outdated += 1
            else:
                break

        if not num_outdated:
            return
        elif num_outdated >= len(self._register):
            self._register = self._register[-1:]  # Always keep latest.
        else:
            self._register = self._register[num_outdated:]

    def __str__(self):
        if self._register:
            return f"{self.mvavg * 1000:.0f} ms"
        else:
            return "not reached"

    def register(self, response_time_seconds):
        """Register a current server response time.

        A value of :obj:`None` denotes a failure to respond; this will clear
        records.
        """
        if response_time_seconds is None:
            self._register.clear()
        else:
            t = unix_time()
            self._register.append((t, response_time_seconds))
            self._min = min(self._min, response_time_seconds)

    def clear(self):
        """Clear records."""
        self.register(None)

    @property
    def min(self):
        """Report smallest response time measured in s, or ``float("inf")``."""
        return self._min

    @property
    def mvavg(self):
        """Report average response time over the configured time span in s.

        If the server did not respond to the last request, returns infinity.
        """
        self._clear_old()

        if self._register:
            return sum(r[1] for r in self._register) / len(self._register)
        else:
            return float("inf")
