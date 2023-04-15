#!/usr/bin/env python3

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

import argparse
from pathlib import Path

import unvtray
from unvtray.tray import make_icon

APP_NAME = unvtray.__name__  # pyright: ignore

APP_ICON_DIR = Path("package") / "icons"
APP_ICON_SIZES = tuple(2**i for i in range(5, 10))
APP_ICON_PLAYER_NUM = 8

TEST_ICON_DIR = Path("icon_test")
TEST_ICON_MAX_PLAYERS = 20


def write_icon(players, path, size=None):
    print(f"Writing {path}.")

    if size is None:
        icon = make_icon(players)
    else:
        icon = make_icon(players, size)

    icon.save(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--application",
        action="store_true",
        help=f"update application items in {APP_ICON_DIR}",
    )
    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help=f"write test tray icons to {TEST_ICON_DIR}",
    )
    args = parser.parse_args()

    if not any(flag for _, flag in args._get_kwargs()):
        parser.print_help()

    if args.application:
        if not APP_ICON_DIR.is_dir():
            raise RuntimeError(f"Directory {APP_ICON_DIR} not found.")

        for size in APP_ICON_SIZES:
            subdir = APP_ICON_DIR / f"{size}x{size}"
            subdir.mkdir(exist_ok=True)

            write_icon(APP_ICON_PLAYER_NUM, subdir / f"{APP_NAME}.png", size)

    if args.test:
        TEST_ICON_DIR.mkdir(exist_ok=True)

        write_icon(None, TEST_ICON_DIR / "icon_initial.png")
        write_icon(-1, TEST_ICON_DIR / "icon_disconnect.png")

        for num in range(TEST_ICON_MAX_PLAYERS + 1):
            write_icon(num, TEST_ICON_DIR / f"icon_{num:02d}.png")
