#!/usr/bin/python3
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)
# X11 (XWayland) lets the tile panel drop down right under the tray icon
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("LGH_ICON_DIR", os.path.join(HERE, "icons"))

from lgh.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
