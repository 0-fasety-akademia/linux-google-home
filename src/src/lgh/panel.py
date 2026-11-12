"""Compact tile panel that drops down under the tray icon."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

from . import APP_NAME, CREATED_BY, SUPPORTED_BY, VERSION  # noqa: E402
from .i18n import _  # noqa: E402
from .ui import state_text  # noqa: E402

CSS = b"""
.lgh-panel { background-color: @theme_bg_color; border: 1px solid alpha(@borders, 0.9); border-radius: 14px; }
.lgh-panel-title { font-weight: bold; font-size: 1.12em; }
.lgh-room { font-weight: 600; font-size: 0.86em; opacity: 0.7; margin-top: 8px; margin-bottom: 2px; margin-left: 2px; }
.lgh-tile {
  border-radius: 14px; padding: 7px 10px; border: none; box-shadow: none;
  background-image: none; background-color: alpha(@theme_fg_color, 0.07);
}
.lgh-tile:hover { background-color: alpha(@theme_fg_color, 0.12); }
.lgh-tile.on { background-color: alpha(#ffc400, 0.20); }
.lgh-tile.on:hover { background-color: alpha(#ffc400, 0.28); }
.lgh-tile.media-on { background-color: alpha(#34c38f, 0.20); }
.lgh-tile.media-on:hover { background-color: alpha(#34c38f, 0.28); }
.lgh-tile-name { font-weight: 600; font-size: 0.92em; }
.lgh-tile-sub { font-size: 0.8em; opacity: 0.7; }
.lgh-panel-foot { font-size: 0.8em; opacity: 0.6; }
"""

# small stroke icons (24x24); {c} = stroke colour
_ICONS = {
    "light": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.4 1.1 2.2h5c0-.8.4-1.6 1.1-2.2A6 6 0 0 0 12 3z"/>',
    "plug": '<rect x="5" y="3" width="14" height="18" rx="4"/><path d="M10 9v3M14 9v3M12 15v2"/>',
    "camera": '<rect x="3" y="7" width="12" height="10" rx="2"/><path d="M15 11l5-3v8l-5-3"/>',
    "speaker": '<rect x="6" y="3" width="12" height="18" rx="3"/><circle cx="12" cy="14" r="3"/><circle cx="12" cy="7.5" r="1"/>',
    "tv": '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "display": '<rect x="4" y="5" width="16" height="11" rx="2"/><path d="M9 20l3-4 3 4"/>',
    "group": '<rect x="3" y="6" width="8" height="13" rx="2"/><rect x="13" y="6" width="8" height="13" rx="2"/>',
    "thermo": '<path d="M10 14V5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0z"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "generic": '<circle cx="12" cy="12" r="7"/>',
    "login": '<path d="M10 17l5-5-5-5M15 12H3M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/>',
}
_CACHE: dict = {}


def tile_icon(kind: str, on: bool, dark: bool, size: int = 34) -> GdkPixbuf.Pixbuf:
    key = (kind, on, dark, size)
    if key not in _CACHE:
        if on:
            bg, fg, glow = "#ffc400", "#3a2c00", '<circle cx="17" cy="17" r="17" fill="#ffc400" opacity="0.35"/>'
        else:
            bg = "#3a3f47" if dark else "#e3e6eb"
            fg = "#c9ced6" if dark else "#5f6670"
            glow = ""
        if on == "media":
            bg, fg, glow = "#34c38f", "#06301f", '<circle cx="17" cy="17" r="17" fill="#34c38f" opacity="0.35"/>'
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="34" height="34" viewBox="0 0 34 34">{glow}'
               f'<circle cx="17" cy="17" r="{15 if glow else 16}" fill="{bg}"/>'
               f'<g transform="translate(6 6) scale(0.9167)" fill="none" stroke="{fg}" stroke-width="2" '
               f'stroke-linecap="round" stroke-linejoin="round">{_ICONS.get(kind, _ICONS["generic"])}</g></svg>')
        loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
        loader.set_size(size, size)
        loader.write(svg.encode())
        loader.close()
        _CACHE[key] = loader.get_pixbuf()
    return _CACHE[key]


def web_kind(t) -> str:
    icon = (t.icon or "").lower()
    typ = (t.type or "").upper()
    if "light" in icon or "bulb" in icon or typ == "LIGHT":
        return "light"
    if "videocam" in icon or "camera" in icon or typ == "CAMERA":
        return "camera"
    if "thermo" in icon or typ == "THERMOSTAT":
        return "thermo"
    if "lock" in icon or typ == "LOCK":
        return "lock"
    if typ in ("SWITCH", "OUTLET") or "switch" in icon or "outlet" in icon or "power" in icon:
        return "plug"
    if "speaker" in icon:
        return "speaker"
    if "tv" in icon:
        return "tv"
    return "generic"


class Tile(Gtk.Button):
    def __init__(self, on_click):
        super().__init__()
        self.get_style_context().add_class("lgh-tile")
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.set_size_request(184, 56)
        box = Gtk.Box(spacing=9)
        self.img = Gtk.Image()
        box.pack_start(self.img, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.name = Gtk.Label(xalign=0, use_underline=False)
        self.name.get_style_context().add_class("lgh-tile-name")
        self.name.set_ellipsize(Pango.EllipsizeMode.END)
        self.name.set_line_wrap(True)
        self.name.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.name.set_lines(2)
        self.name.set_max_width_chars(16)
        self.name.set_width_chars(16)
        self.sub = Gtk.Label(xalign=0)
        self.sub.get_style_context().add_class("lgh-tile-sub")
        self.sub.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub.set_max_width_chars(18)
        texts.pack_start(self.name, False, False, 0)
        texts.pack_start(self.sub, False, False, 0)
        box.pack_start(texts, True, True, 0)
        self.spin = Gtk.Spinner()
        box.pack_end(self.spin, False, False, 0)
        self.add(box)
        self.connect("clicked", lambda *_: on_click())
        self.show_all()

    def set(self, name, sub, kind, state, dark, pending=False, tooltip=None):
        """state: True (on), False (off), 'media' (playing), None (no state)"""
        self.name.set_text(name)
        self.sub.set_text(sub or "")
        self.sub.set_visible(bool(sub))
        self.img.set_from_pixbuf(tile_icon(kind, state if state in (True, "media") else False, dark))
        ctx = self.get_style_context()
        ctx.remove_class("on")
        ctx.remove_class("media-on")
        if state is True:
            ctx.add_class("on")
        elif state == "media":
            ctx.add_class("media-on")
        self.set_tooltip_text(tooltip or name)
        if pending:
            self.spin.show()
            self.spin.start()
        else:
            self.spin.stop()
            self.spin.hide()


class TilePanel(Gtk.Window):
    WIDTH = 460

    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=APP_NAME)
        self.app = app
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame.get_style_context().add_class("lgh-panel")
        head = Gtk.Box(spacing=6)
        t = Gtk.Label(label=APP_NAME)
        t.get_style_context().add_class("lgh-panel-title")
        head.set_center_widget(t)
        for icon, tip, cb in (("view-refresh-symbolic", _("refresh"), self._refresh),
                              ("window-new-symbolic", _("show"), self._open_window)):
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda *_a, c=cb: c())
            head.pack_end(b, False, False, 0)
        frame.pack_start(head, False, False, 0)

        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_max_content_height(560)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.scroll.add(self.body)
        frame.pack_start(self.scroll, True, True, 0)
        foot = Gtk.Label(label=f"{APP_NAME} {VERSION}\n{CREATED_BY}\n{SUPPORTED_BY}", xalign=0)
        foot.get_style_context().add_class("lgh-panel-foot")
        frame.pack_start(foot, False, False, 0)
        # explicit inner spacing (border-width is not honoured on the transparent popup)
        for w in (head, self.scroll, foot):
            w.set_margin_start(20)
            w.set_margin_end(20)
        head.set_margin_top(18)
        foot.set_margin_bottom(14)
        self.add(frame)
        frame.show_all()

        self.connect("focus-out-event", lambda *_: self._maybe_hide())
        self.connect("key-press-event", self._key)
        self._sig = None

    # -------------------------------------------------------------- showing
    def toggle(self):
        if self.get_visible():
            self.hide()
        else:
            self.popup()

    def popup(self):
        self._sig = None
        self.rebuild()
        self.set_size_request(self.WIDTH, -1)
        self.show()
        self._place()
        self.present_with_time(Gtk.get_current_event_time() or Gdk.CURRENT_TIME)
        GLib.timeout_add(80, self._place)  # after the real size is known

    def _place(self):
        disp = Gdk.Display.get_default()
        mon = disp.get_primary_monitor() or disp.get_monitor(0)
        wa = mon.get_workarea()
        w, _h = self.get_size()
        self.move(wa.x + wa.width - w - 8, wa.y + 6)
        return False

    def _maybe_hide(self):
        GLib.timeout_add(120, lambda: (self.hide() if not self.is_active() else None, False)[1])
        return False

    def _key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _refresh(self):
        self.app.backend.refresh()
        if self.app.webtiles:
            self.app.webtiles.reload()

    def _open_window(self):
        self.hide()
        self.app.show_window()

    # -------------------------------------------------------------- content
    def update(self):
        if self.get_visible():
            self.rebuild()

    def _signature(self):
        be, wt = self.app.backend, self.app.webtiles
        sig = [self.app.theme.dark]
        for d in be.devices.values():
            sig.append((d.id, d.name, d.online, d.is_playing, d.is_paused, d.is_standby,
                        d.activity_signature(), d.atv_state))
        if wt:
            sig.append(wt.state)
            sig += [(t.key, t.on, t.sub, t.pending) for t in wt.tiles]
        return tuple(sig)

    def rebuild(self):
        sig = self._signature()
        if sig == self._sig:
            return
        self._sig = sig
        for c in self.body.get_children():
            self.body.remove(c)
        dark = self.app.theme.dark
        be, wt = self.app.backend, self.app.webtiles

        local = sorted(be.devices.values(), key=lambda d: (not d.is_playing, d.kind != "tv", d.name.lower()))
        if local:
            grid = self._section(_("media"))
            for d in local:
                tile = Tile(lambda dev=d: self._media_click(dev))
                txt, _cls = state_text(d)
                what = d.activity_signature()
                state = "media" if (d.is_playing or d.is_paused) else (True if (d.kind == "tv" and d.atv_on) else False)
                if d.is_paused:
                    txt = _("paused") + (f" · {d.title}" if d.title else "")
                tile.set(d.name, what or txt, d.kind, state, dark,
                         tooltip=f"{d.name}\n{what or txt}")
                grid.add(tile)

        if wt is not None:
            if wt.state == "login":
                grid = self._section("Google Home (web)")
                tile = Tile(self._login)
                tile.set(_("web_login").rstrip("…"), "home.google.com", "login", False, dark)
                grid.add(tile)
            elif wt.state != "ok":
                grid = self._section("Google Home (web)")
                tile = Tile(lambda: None)
                tile.set(_("web_loading_devices"), "", "generic", False, dark, pending=True)
                grid.add(tile)
            else:
                room = object()
                grid = None
                for t in wt.tiles:
                    if t.room != room:
                        room = t.room
                        grid = self._section(room or _("other_devices"))
                    tile = Tile(lambda key=t.key, tog=t.toggle: self._web_click(key, tog))
                    sub = t.sub or ""
                    if not sub and web_kind(t) == "camera":
                        sub = _("camera")
                    if t.on is not None:
                        sub = _("on") if t.on else _("off")
                    tile.set(" ".join(t.name.replace("_", " ").split()), sub, web_kind(t), bool(t.on), dark, pending=bool(t.pending),
                             tooltip=t.name + ("\n" + _("click_toggle") if t.toggle else ""))
                    grid.add(tile)
        self.body.show_all()
        for child in self.body.get_children():
            if isinstance(child, Gtk.FlowBox):
                for fc in child.get_children():
                    tile = fc.get_child()
                    if not tile.spin.get_property("active"):
                        tile.spin.hide()
        if self.get_visible():
            GLib.idle_add(self._place)

    def _section(self, title):
        lbl = Gtk.Label(label=title, xalign=0, use_underline=False)
        lbl.get_style_context().add_class("lgh-room")
        self.body.pack_start(lbl, False, False, 0)
        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=2, max_children_per_line=2,
                           column_spacing=10, row_spacing=10)
        self.body.pack_start(grid, False, False, 0)
        return grid

    # -------------------------------------------------------------- clicks
    def _media_click(self, dev):
        if dev.player_state in ("PLAYING", "PAUSED", "BUFFERING"):
            self.app.backend.play_pause(dev)
        else:
            self._open_window()

    def _web_click(self, key, toggleable):
        if toggleable:
            self.app.webtiles.toggle(key)
        else:
            self.hide()
            self.app.open_web()

    def _login(self):
        self.hide()
        self.app.open_web()
