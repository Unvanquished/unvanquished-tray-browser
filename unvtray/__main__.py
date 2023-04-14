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

import time
from sched import scheduler

from . import tray
from .servers import ServerList

TRAY_WAKEUP_TIME = 0.2
TRAY_REFRESH_TIME = 5
MAIN_UPDATE_TIME = 60


def setup(tray_icon):
    tray_icon.visible = True
    tray_icon.next_event = None  # Allow stopping the schedule.

    def update(schedule, servers):
        tray_icon.next_event = (
            schedule,
            schedule.enter(TRAY_REFRESH_TIME, 1, update, (schedule, servers)),
        )

        new_tray = tray.make_tray(servers)

        if new_tray.icon is not tray_icon.icon:  # Icons are cached.
            tray_icon.icon = new_tray.icon
            tray_icon._update_icon()

        tray_icon.menu = new_tray.menu
        tray_icon._update_menu()

    servers = ServerList(
        update_time=MAIN_UPDATE_TIME, refresh_time=TRAY_REFRESH_TIME / 2
    )

    schedule = scheduler(time.time, time.sleep)
    schedule.enter(0, 1, update, (schedule, servers))

    while schedule.run(False):
        time.sleep(TRAY_WAKEUP_TIME)  # Allow immediate quit.


def run():
    icon = tray.make_tray(None)
    icon.run(setup)


if __name__ == "__main__":
    run()
