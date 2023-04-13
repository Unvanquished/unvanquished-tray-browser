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

HIGH_PLAYER_COUNT = 6


@lru_cache()
def _make_icon(
    text="",
    *,
    text_color="lightgray",
    bg_color="#555",
    border_color="#222",
    text_size=2 / 3,
    text_hori_margin=1 / 64,
    text_vert_margin=-2 / 64,
    border_width=1 / 64,
    icon_file=str(ASSET_DIR / "unvanquished.png"),
    font_file=str(ASSET_DIR / "FreeMonoBold.otf"),
):
    icon = Image.open(icon_file)
    assert icon.size[0] == icon.size[1], "Icon image must be square."

    if text:
        s = icon.size[0]
        h = text_hori_margin * s
        v = text_vert_margin * s
        b = border_width * s
        th = int(text_size * s)  # text height
        font = ImageFont.truetype(font_file, size=th)
        tw = font.getlength(text) + 2 * h  # text width

        canvas = ImageDraw.Draw(icon)
        canvas.rectangle(
            (s - tw - 2 * b, s - th - 2 * v - 2 * b, s - 1, s - 1),
            fill=border_color,
        )
        canvas.rectangle(
            (s - tw - b, s - th - 2 * v - b, s - b - 1, s - b - 1),
            fill=bg_color,
        )
        canvas.text(
            (s - tw - b - 1 + h, s - th - b - v - 1),
            text,
            align="right",
            font=font,
            fill=text_color,
        )

    return icon


def make_icon(players=None):
    icon_data = dict(text_color="#f9fcee")

    if players is None:  # No data yet.
        pass
    elif players < 0:  # Disconnected.
        icon_data["text"] = "?"
        icon_data["bg_color"] = "darkred"
    else:
        icon_data["text"] = f"{players:d}"
        icon_data["bg_color"] = "#233f47"  # dark teal

        if players >= HIGH_PLAYER_COUNT:
            icon_data["bg_color"] = "darkgreen"
            icon_data["text_color"] = "#c7ffc7"

    return _make_icon(**icon_data)


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


def make_tray(servers=None):
    if servers is None:
        icon = make_icon(None)
    elif not servers.online():
        icon = make_icon(-1)
    else:
        icon = make_icon(servers.max_playing)

    tray = Icon(name="Unvanquished Tray", icon=icon, menu=make_menu(servers))

    return tray


if __name__ == "__main__":
    import sys

    print("Updating the example icon.")

    example_icon = make_icon(8)
    example_icon.save("example.png")

    if "--test" in sys.argv:
        print("Saving icons for inspection.")

        icon_initial = make_icon()
        icon_initial.save("icon_initial.png")

        icon_disconnect = make_icon(-1)
        icon_disconnect.save("icon_disconnect.png")

        icon_few = make_icon(0)
        icon_few.save("icon_few.png")

        icon_many = make_icon(HIGH_PLAYER_COUNT)
        icon_many.save("icon_many.png")

        icon_two_digits = make_icon(10)
        icon_two_digits.save("icon_two_digits.png")
