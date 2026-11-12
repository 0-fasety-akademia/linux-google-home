"""Tray icon (Ayatana AppIndicator) with a live 'now playing' list."""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AI  # noqa: E402
except (ValueError, ImportError):  # pragma: no cover
    AI = None

from . import APP_NAME, SLUG  # noqa: E402
from .i18n import _  # noqa: E402
from .theme import icon_path  # noqa: E402


_DOT_SVG = {
    True: ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
           '<circle cx="8" cy="8" r="7" fill="#ffd54a" opacity="0.35"/>'
           '<circle cx="8" cy="8" r="4.5" fill="#ffc400"/></svg>'),
    False: ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
            '<circle cx="8" cy="8" r="4" fill="none" stroke="#8a8f98" stroke-width="1.6"/></svg>'),
    None: ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
           '<circle cx="8" cy="8" r="2.5" fill="#8a8f98"/></svg>'),
}
_DOT_CACHE: dict = {}


def dot_pixbuf(state):
    if state not in _DOT_CACHE:
        loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
        loader.write(_DOT_SVG[state].encode())
        loader.close()
        _DOT_CACHE[state] = loader.get_pixbuf()
    return _DOT_CACHE[state]


def dot_item(label: str, state) -> Gtk.MenuItem:
    item = Gtk.ImageMenuItem(label=label)
    item.set_image(Gtk.Image.new_from_pixbuf(dot_pixbuf(state)))
    item.set_always_show_image(True)
    return item


class Tray:
    def __init__(self, app):
        self.app = app
        self._pending = False
        self.ind = None
        if AI is None:
            return
        self.ind = AI.Indicator.new(SLUG, "", AI.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_title(APP_NAME)
        self.ind.set_status(AI.IndicatorStatus.ACTIVE)
        self.set_dark(app.theme.dark)
        self.rebuild()

    def set_dark(self, dark: bool):
        if not self.ind:
            return
        p = icon_path(dark)
        self.ind.set_icon_theme_path(os.path.dirname(p))
        self.ind.set_icon_full(os.path.splitext(os.path.basename(p))[0], APP_NAME)

    def schedule_rebuild(self, force=False):
        # menu is static now; live content lives in the tile panel
        self.app.panel_update()

    def rebuild(self):
        if not self.ind:
            return
        menu = Gtk.Menu()
        panel = Gtk.MenuItem(label=_("panel"), use_underline=False)
        panel.connect("activate", lambda *_: self.app.toggle_panel())
        menu.append(panel)
        show = Gtk.MenuItem(label=_("show"), use_underline=False)
        show.connect("activate", lambda *_: self.app.show_window())
        menu.append(show)
        menu.append(Gtk.SeparatorMenuItem())
        notif = Gtk.CheckMenuItem(label=_("notifications"))
        notif.set_active(self.app.config.get("notifications", True))
        notif.connect("toggled", lambda c: self.app.set_notifications(c.get_active()))
        menu.append(notif)
        menu.append(Gtk.SeparatorMenuItem())
        q = Gtk.MenuItem(label=_("quit"))
        q.connect("activate", lambda *_: self.app.quit_app())
        menu.append(q)
        menu.show_all()
        self.ind.set_menu(menu)
        # middle click on the tray icon opens the tiles directly
        self.ind.set_secondary_activate_target(panel)
