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

import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pystray import Icon, Menu, MenuItem

ASSET_DIR = Path(__file__).parent / "assets"


@lru_cache()
def make_icon(
    text="",
    color="gray",
    text_color="white",
    size=64,
    text_scale=2 / 3,
    icon_file=str(ASSET_DIR / "unvanquished.png"),
    font_file=str(ASSET_DIR / "FreeMonoBold.otf"),
):
    s = size
    th = int(text_scale * size)  # text height
    icon = Image.open(icon_file)
    font = ImageFont.truetype(font_file, size=th)
    tw = font.getlength(text)  # text width
    canvas = ImageDraw.Draw(icon)
    canvas.rectangle((s - tw, s - th, s, s), fill=color)
    canvas.text(
        (s - tw, s - th),
        text,
        align="right",
        font=font,
        fill=text_color,
    )
    return icon


def make_connect_action(server):
    def connect():
        subprocess.call(["xdg-open", f"unv://{server.address}"])

    return connect


def launch_action():
    subprocess.call(["unvanquished"])


def quit_action(icon):
    if icon.next_event:
        schedule, next_event = icon.next_event
        schedule.cancel(next_event)
        icon.next_event = None

    icon.stop()


def make_menu(servers=None):
    items = []

    if servers:
        items.extend(
            MenuItem(str(server), make_connect_action(server), default=not i)
            for i, server in enumerate(servers.filter())
        )
        items.append(Menu.SEPARATOR)

    items.append(MenuItem("Launch Unvanquished", launch_action))
    items.append(MenuItem("Quit", quit_action))

    menu = Menu(*items)
    return menu


def make_tray(servers=None, *, player_threshold=6):
    icon_data = dict(text_color="#e1e5d9")

    if servers is None:
        pass
    elif not servers.online():
        icon_data["text"] = "?"
        icon_data["color"] = "darkred"
    else:
        icon_data["text"] = f"{servers.max_playing:d}"
        icon_data["color"] = "#233f47"  # dark teal

        if servers.max_playing >= player_threshold:
            icon_data["text_color"] = "lightgreen"

    tray = Icon(
        name="Unvanquished Tray",
        icon=make_icon(**icon_data),
        menu=make_menu(servers),
    )

    return tray
