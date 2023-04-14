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

from subprocess import Popen

from .common import logger

UNVANQUISHED = "unvanquished"
UNV_URI_HANDLERS = ("xdg-open", "open")


def launch(server=None):
    if server is None:
        Popen([UNVANQUISHED])
        logger.debug(f"Started {UNVANQUISHED}.")
    else:
        uri = f"unv://{server.address}"

        for uri_handler in UNV_URI_HANDLERS:
            try:
                Popen([uri_handler, uri])
            except FileNotFoundError as error:
                logger.debug(
                    f"{uri_handler} does not seem to be installed;"
                    f" moving to next option."
                )
            else:
                logger.debug(f"Passed {uri} to {uri_handler}.")
                break
        else:
            Popen([UNVANQUISHED, "+connect", uri])
            logger.debug(f"Passed {uri} directly to {UNVANQUISHED}.")
