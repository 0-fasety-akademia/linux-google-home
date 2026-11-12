"""Main window: device cards, TV remote, embedded Google Home web app."""
from __future__ import annotations

import os
import threading
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

from . import APP_NAME, BUILD_DATE, CREATED_BY, SUPPORTED_BY, VERSION  # noqa: E402
from .backend import ATV_LAUNCH, Device  # noqa: E402
from .i18n import _  # noqa: E402

CSS = b"""
.lgh-card {
  background-color: @theme_base_color;
  border: 1px solid alpha(@borders, 0.7);
  border-radius: 16px;
  padding: 14px 16px;
}
.lgh-card.active { border-color: alpha(#34c38f, 0.85); }
.lgh-name { font-weight: bold; font-size: 1.08em; }
.lgh-pill {
  border-radius: 999px; padding: 1px 10px; font-size: 0.85em;
  background-color: alpha(@theme_fg_color, 0.08);
}
.lgh-pill.playing { background-color: alpha(#34c38f, 0.22); }
.lgh-pill.paused { background-color: alpha(#f5a524, 0.22); }
.lgh-pill.off { background-color: alpha(@theme_fg_color, 0.05); }
.lgh-dim { opacity: 0.68; }
.lgh-title { font-weight: 600; }
.lgh-cover { border-radius: 8px; }
.lgh-footer { padding: 4px 10px; font-size: 0.85em; }
.lgh-empty-title { font-size: 1.3em; font-weight: bold; }
.lgh-remote button { min-width: 44px; min-height: 36px; }
.lgh-ok { border-radius: 999px; min-width: 52px; min-height: 52px; font-weight: bold; }
.circular-btn { border-radius: 999px; }
"""

KIND_ICON = {
    "tv": "video-display-symbolic",
    "speaker": "audio-speakers-symbolic",
    "group": "audio-speakers-symbolic",
    "display": "computer-symbolic",
    "chromecast": "video-display-symbolic",
}

_cover_cache: dict[str, GdkPixbuf.Pixbuf] = {}


def load_cover(url: str, size: int, cb):
    if url in _cover_cache:
        cb(_cover_cache[url])
        return

    def work():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
            data = urllib.request.urlopen(req, timeout=8).read()
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pb = loader.get_pixbuf()
            w, h = pb.get_width(), pb.get_height()
            scale = size / max(w, h)
            pb = pb.scale_simple(max(1, int(w * scale)), max(1, int(h * scale)), GdkPixbuf.InterpType.BILINEAR)
            _cover_cache[url] = pb
            GLib.idle_add(cb, pb)
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()


def icon_button(icon: str, tooltip: str, cb, *args) -> Gtk.Button:
    b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
    b.set_tooltip_text(tooltip)
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.connect("clicked", lambda *_: cb(*args))
    return b


def state_text(dev: Device) -> tuple[str, str]:
    """(label, css class) for the status pill."""
    if not dev.online:
        if dev.atv_state == "unpaired" and not dev.has_cast:
            return _("not_paired"), "off"
        return _("offline"), "off"
    if dev.player_state in ("PLAYING",):
        return _("playing"), "playing"
    if dev.player_state == "BUFFERING":
        return _("buffering"), "playing"
    if dev.is_paused:
        return _("paused"), "paused"
    if dev.is_standby:
        return (_("off") if dev.kind == "tv" else _("standby")), "off"
    if dev.is_playing:
        return _("on"), "playing"
    if dev.kind == "tv" and dev.atv_on:
        return _("on"), ""
    return _("idle"), ""


class DeviceCard(Gtk.Box):
    def __init__(self, win: "MainWindow", dev: Device):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.win, self.be, self.dev = win, win.backend, dev
        self.get_style_context().add_class("lgh-card")
        self.set_size_request(340, -1)
        self._cover_url = None
        self._vol_lock = False

        # header -------------------------------------------------------
        head = Gtk.Box(spacing=10)
        self.kind_img = Gtk.Image.new_from_icon_name(KIND_ICON.get(dev.kind, "video-display-symbolic"), Gtk.IconSize.LARGE_TOOLBAR)
        head.pack_start(self.kind_img, False, False, 0)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.name_lbl = Gtk.Label(xalign=0)
        self.name_lbl.get_style_context().add_class("lgh-name")
        self.name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.model_lbl = Gtk.Label(xalign=0)
        self.model_lbl.get_style_context().add_class("lgh-dim")
        self.model_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        names.pack_start(self.name_lbl, False, False, 0)
        names.pack_start(self.model_lbl, False, False, 0)
        head.pack_start(names, True, True, 0)
        self.pill = Gtk.Label()
        self.pill.get_style_context().add_class("lgh-pill")
        self.pill.set_valign(Gtk.Align.CENTER)
        head.pack_end(self.pill, False, False, 0)
        self.pack_start(head, False, False, 0)

        # now playing --------------------------------------------------
        np = Gtk.Box(spacing=10)
        self.cover = Gtk.Image()
        self.cover.get_style_context().add_class("lgh-cover")
        np.pack_start(self.cover, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.title_lbl = Gtk.Label(xalign=0)
        self.title_lbl.get_style_context().add_class("lgh-title")
        self.title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub_lbl = Gtk.Label(xalign=0)
        self.sub_lbl.get_style_context().add_class("lgh-dim")
        self.sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        texts.pack_start(self.title_lbl, False, False, 0)
        texts.pack_start(self.sub_lbl, False, False, 0)
        np.pack_start(texts, True, True, 0)
        self.np_box = np
        self.pack_start(np, False, False, 0)

        # media controls -----------------------------------------------
        ctl = Gtk.Box(spacing=2)
        self.prev_b = icon_button("media-skip-backward-symbolic", _("prev"), self.be.prev, dev)
        self.play_b = icon_button("media-playback-start-symbolic", _("play_pause"), self.be.play_pause, dev)
        self.next_b = icon_button("media-skip-forward-symbolic", _("next"), self.be.next, dev)
        self.stop_b = icon_button("media-playback-stop-symbolic", _("stop"), self.be.stop, dev)
        for b in (self.prev_b, self.play_b, self.next_b, self.stop_b):
            ctl.pack_start(b, False, False, 0)
        self.mute_b = icon_button("audio-volume-high-symbolic", _("mute"), self.be.toggle_mute, dev)
        ctl.pack_start(self.mute_b, False, False, 0)
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol.set_draw_value(False)
        self.vol.set_hexpand(True)
        self.vol.set_tooltip_text(_("volume"))
        self.vol.connect("value-changed", self._vol_changed)
        ctl.pack_start(self.vol, True, True, 0)
        self.vdown_b = icon_button("list-remove-symbolic", _("volume") + " −", self.be.volume_step, dev, False)
        self.vup_b = icon_button("list-add-symbolic", _("volume") + " +", self.be.volume_step, dev, True)
        ctl.pack_start(self.vdown_b, False, False, 0)
        ctl.pack_start(self.vup_b, False, False, 0)
        self.ctl_row = ctl
        self.pack_start(ctl, False, False, 0)

        # TV row ---------------------------------------------------------
        tv = Gtk.Box(spacing=6)
        self.power_b = Gtk.Button.new_from_icon_name("system-shutdown-symbolic", Gtk.IconSize.BUTTON)
        self.power_b.set_tooltip_text(_("power"))
        self.power_b.connect("clicked", lambda *_: self.be.power(dev))
        tv.pack_start(self.power_b, False, False, 0)
        self.remote_b = Gtk.MenuButton(label=_("remote"))
        self.remote_b.set_image(Gtk.Image.new_from_icon_name("input-gaming-symbolic", Gtk.IconSize.BUTTON))
        self.remote_b.set_always_show_image(True)
        self.remote_b.set_popover(RemotePopover(self.be, dev))
        tv.pack_start(self.remote_b, True, True, 0)
        self.pair_b = Gtk.Button(label=_("pair_remote"))
        self.pair_b.get_style_context().add_class("suggested-action")
        self.pair_b.connect("clicked", lambda *_: self.win.pair(dev))
        tv.pack_start(self.pair_b, True, True, 0)
        self.remote_status = Gtk.Label(xalign=0)
        self.remote_status.get_style_context().add_class("lgh-dim")
        tv.pack_start(self.remote_status, True, True, 0)
        self.tv_row = tv
        self.pack_start(tv, False, False, 0)

        self.show_all()
        self.update()

    def _vol_changed(self, scale):
        if not self._vol_lock:
            self.be.set_volume(self.dev, scale.get_value() / 100.0)

    def update(self):
        d = self.dev
        self.kind_img.set_from_icon_name(KIND_ICON.get(d.kind, "video-display-symbolic"), Gtk.IconSize.LARGE_TOOLBAR)
        self.name_lbl.set_text(d.name)
        kind_label = {"tv": _("tv"), "speaker": _("speaker"), "group": _("group"),
                      "display": _("display"), "chromecast": _("chromecast")}[d.kind]
        self.model_lbl.set_text(" · ".join(x for x in (kind_label, d.model) if x and x != kind_label))
        txt, cls = state_text(d)
        ctx = self.pill.get_style_context()
        for c in ("playing", "paused", "off"):
            ctx.remove_class(c)
        if cls:
            ctx.add_class(cls)
        self.pill.set_text(txt)
        card_ctx = self.get_style_context()
        (card_ctx.add_class if d.is_playing else card_ctx.remove_class)("active")

        # now playing
        title = d.title
        app = d.app_name
        if title:
            self.title_lbl.set_text(title)
            self.sub_lbl.set_text(" · ".join(x for x in (d.subtitle, app) if x))
        elif app:
            self.title_lbl.set_text(app)
            self.sub_lbl.set_text("")
        else:
            self.title_lbl.set_text("")
            self.sub_lbl.set_text("")
        self.np_box.set_visible(bool(title or app))
        self.sub_lbl.set_visible(bool(self.sub_lbl.get_text()))
        url = d.image_url
        if url != self._cover_url:
            self._cover_url = url
            if url:
                load_cover(url, 56, lambda pb: self._cover_url == url and self.cover.set_from_pixbuf(pb))
            else:
                self.cover.clear()
        self.cover.set_visible(bool(url))

        # controls
        has_media = d.player_state not in (None, "IDLE", "UNKNOWN")
        remote_ok = d.atv_state in ("connected", "idle")
        self.play_b.get_image().set_from_icon_name(
            "media-playback-pause-symbolic" if d.player_state == "PLAYING" else "media-playback-start-symbolic",
            Gtk.IconSize.BUTTON)
        for b in (self.prev_b, self.play_b, self.next_b):
            b.set_sensitive(has_media or remote_ok)
        self.stop_b.set_sensitive(bool(d.cast_status and d.cast_status.app_id) or remote_ok)
        self.mute_b.get_image().set_from_icon_name(
            "audio-volume-muted-symbolic" if d.muted else "audio-volume-high-symbolic", Gtk.IconSize.BUTTON)
        vol = d.volume
        use_slider = d.has_cast and not remote_ok
        self.vol.set_visible(use_slider)
        self.vdown_b.set_visible(not use_slider)
        self.vup_b.set_visible(not use_slider)
        if vol is not None and use_slider:
            self._vol_lock = True
            self.vol.set_value(round(vol * 100))
            self._vol_lock = False
        online = d.online
        self.ctl_row.set_visible(d.has_cast or remote_ok)
        for w in (self.mute_b, self.vol, self.vdown_b, self.vup_b):
            w.set_sensitive(online)

        # tv / remote
        self.tv_row.set_visible(d.has_remote)
        self.power_b.set_visible(remote_ok)
        self.remote_b.set_visible(remote_ok)
        self.pair_b.set_visible(d.atv_state == "unpaired")
        if d.atv_state == "pairing":
            self.remote_status.set_text(_("remote_connecting"))
        elif d.atv_state == "error":
            self.remote_status.set_text(_("offline"))
        else:
            self.remote_status.set_text("")
        self.remote_status.set_visible(bool(self.remote_status.get_text()))
        self.remote_b.get_popover().set_ime(self.be.enable_ime)


class RemotePopover(Gtk.Popover):
    def __init__(self, be, dev: Device):
        super().__init__()
        self.be, self.dev = be, dev
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)
        box.get_style_context().add_class("lgh-remote")

        def k(icon_or_label, key, tip, label=False):
            b = Gtk.Button(label=icon_or_label) if label else Gtk.Button.new_from_icon_name(icon_or_label, Gtk.IconSize.BUTTON)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda *_: be.key(dev, key))
            return b

        top = Gtk.Box(spacing=6, homogeneous=True)
        top.pack_start(k("system-shutdown-symbolic", "KEYCODE_POWER", _("power")), True, True, 0)
        top.pack_start(k("video-display-symbolic", "KEYCODE_TV_INPUT", _("input")), True, True, 0)
        top.pack_start(k("emblem-system-symbolic", "KEYCODE_SETTINGS", _("settings")), True, True, 0)
        top.pack_start(k("audio-volume-muted-symbolic", "KEYCODE_VOLUME_MUTE", _("mute")), True, True, 0)
        box.pack_start(top, False, False, 0)

        pad = Gtk.Grid(column_spacing=6, row_spacing=6, halign=Gtk.Align.CENTER)
        pad.attach(k("go-up-symbolic", "KEYCODE_DPAD_UP", "↑"), 1, 0, 1, 1)
        pad.attach(k("go-previous-symbolic", "KEYCODE_DPAD_LEFT", "←"), 0, 1, 1, 1)
        ok = k("OK", "KEYCODE_DPAD_CENTER", "OK", label=True)
        ok.get_style_context().add_class("lgh-ok")
        pad.attach(ok, 1, 1, 1, 1)
        pad.attach(k("go-next-symbolic", "KEYCODE_DPAD_RIGHT", "→"), 2, 1, 1, 1)
        pad.attach(k("go-down-symbolic", "KEYCODE_DPAD_DOWN", "↓"), 1, 2, 1, 1)
        box.pack_start(pad, False, False, 0)

        nav = Gtk.Box(spacing=6, homogeneous=True)
        nav.pack_start(k("edit-undo-symbolic", "KEYCODE_BACK", _("back")), True, True, 0)
        nav.pack_start(k("go-home-symbolic", "KEYCODE_HOME", _("home")), True, True, 0)
        nav.pack_start(k("media-playback-start-symbolic", "KEYCODE_MEDIA_PLAY_PAUSE", _("play_pause")), True, True, 0)
        nav.pack_start(k("audio-volume-low-symbolic", "KEYCODE_VOLUME_DOWN", _("volume") + " −"), True, True, 0)
        nav.pack_start(k("audio-volume-high-symbolic", "KEYCODE_VOLUME_UP", _("volume") + " +"), True, True, 0)
        box.pack_start(nav, False, False, 0)

        lbl = Gtk.Label(label=_("apps"), xalign=0)
        lbl.get_style_context().add_class("lgh-dim")
        box.pack_start(lbl, False, False, 0)
        apps = Gtk.FlowBox(max_children_per_line=3, selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=6, row_spacing=6, homogeneous=True)
        for name, link in ATV_LAUNCH:
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda _b, l=link: be.launch(dev, l))
            apps.add(b)
        box.pack_start(apps, False, False, 0)

        txt = Gtk.Box(spacing=6)
        self.entry = Gtk.Entry(placeholder_text=_("type_text"))
        self.entry.connect("activate", self._send)
        txt.pack_start(self.entry, True, True, 0)
        sb = Gtk.Button(label=_("send"))
        sb.connect("clicked", self._send)
        txt.pack_start(sb, False, False, 0)
        box.pack_start(txt, False, False, 0)

        self.txt_row = txt
        self.add(box)
        box.show_all()
        self.connect("show", lambda *_: be.remote_wake(dev))
        # arrow keys / enter on the keyboard drive the TV while popover is open
        self.connect("key-press-event", self._key)

    def set_ime(self, on: bool):
        self.txt_row.set_visible(on)

    def _send(self, *_a):
        t = self.entry.get_text()
        if t:
            self.be.send_text(self.dev, t)
            self.entry.set_text("")

    def _key(self, _w, ev):
        if self.entry.has_focus():
            return False
        m = {
            Gdk.KEY_Up: "KEYCODE_DPAD_UP", Gdk.KEY_Down: "KEYCODE_DPAD_DOWN",
            Gdk.KEY_Left: "KEYCODE_DPAD_LEFT", Gdk.KEY_Right: "KEYCODE_DPAD_RIGHT",
            Gdk.KEY_Return: "KEYCODE_DPAD_CENTER", Gdk.KEY_KP_Enter: "KEYCODE_DPAD_CENTER",
            Gdk.KEY_BackSpace: "KEYCODE_BACK",
        }
        code = m.get(ev.keyval)
        if code:
            self.be.key(self.dev, code)
            return True
        return False


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.app = app
        self.backend = app.backend
        self.set_default_size(*app.config.get("size", (1040, 700)))
        self.cards: dict[str, DeviceCard] = {}
        self.web = None

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # header bar
        hb = Gtk.HeaderBar(show_close_button=True)
        self.set_titlebar(hb)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        sw = Gtk.StackSwitcher(stack=self.stack)
        hb.set_custom_title(sw)
        ref = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        ref.set_tooltip_text(_("refresh"))
        ref.connect("clicked", self._refresh)
        hb.pack_start(ref)
        menu_b = Gtk.MenuButton()
        menu_b.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_b.set_popover(self._build_menu())
        hb.pack_end(menu_b)
        hb.show_all()

        # devices page
        dev_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.dev_stack = Gtk.Stack()
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                        valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        sp = Gtk.Spinner(active=True)
        sp.set_size_request(32, 32)
        empty.pack_start(sp, False, False, 0)
        t = Gtk.Label(label=_("searching"))
        t.get_style_context().add_class("lgh-empty-title")
        empty.pack_start(t, False, False, 0)
        h = Gtk.Label(label=_("searching_hint"))
        h.get_style_context().add_class("lgh-dim")
        empty.pack_start(h, False, False, 0)
        self.dev_stack.add_named(empty, "empty")
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                                column_spacing=14, row_spacing=14, margin=18,
                                valign=Gtk.Align.START, min_children_per_line=1, max_children_per_line=4)
        self.flow.set_sort_func(self._sort)
        scroll.add(self.flow)
        self.dev_stack.add_named(scroll, "list")
        dev_page.pack_start(self.dev_stack, True, True, 0)
        self.stack.add_titled(dev_page, "devices", _("devices"))

        # web page (lazy)
        self.web_holder = Gtk.Box()
        self.stack.add_titled(self.web_holder, "web", _("web"))
        self.stack.connect("notify::visible-child-name", self._page_changed)

        # footer with version
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.pack_start(self.stack, True, True, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        foot = Gtk.Box(spacing=8)
        foot.get_style_context().add_class("lgh-footer")
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for text in (f"{APP_NAME} {VERSION} · {BUILD_DATE}", CREATED_BY, SUPPORTED_BY):
            lbl = Gtk.Label(label=text, xalign=0)
            lbl.get_style_context().add_class("lgh-dim")
            info.pack_start(lbl, False, False, 0)
        foot.pack_start(info, False, False, 0)
        self.count_lbl = Gtk.Label(xalign=1, valign=Gtk.Align.END)
        self.count_lbl.get_style_context().add_class("lgh-dim")
        foot.pack_end(self.count_lbl, False, False, 0)
        outer.pack_start(foot, False, False, 0)
        self.add(outer)

        self.connect("delete-event", self._on_close)
        outer.show_all()
        self._update_counts()

    # ----------------------------------------------------------------- menu
    def _build_menu(self):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=10, spacing=6)
        self.notif_chk = Gtk.CheckButton(label=_("notifications"))
        self.notif_chk.set_active(self.app.config.get("notifications", True))
        self.notif_chk.connect("toggled", lambda c: self.app.set_notifications(c.get_active()))
        box.pack_start(self.notif_chk, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 4)
        always = Gtk.CheckButton(label=_("remote_always"))
        always.set_tooltip_text(_("remote_always_tip"))
        always.set_active(self.app.config.get("remote_mode", "on_demand") == "always")
        always.connect("toggled", lambda c: self.app.set_remote_option("remote_mode", "always" if c.get_active() else "on_demand"))
        box.pack_start(always, False, False, 0)
        ime = Gtk.CheckButton(label=_("remote_ime"))
        ime.set_tooltip_text(_("remote_ime_tip"))
        ime.set_active(self.app.config.get("remote_ime", False))
        ime.connect("toggled", lambda c: self.app.set_remote_option("remote_ime", c.get_active()))
        box.pack_start(ime, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 4)
        auto = Gtk.CheckButton(label=_("autostart"))
        auto.set_active(self.app.autostart_enabled())
        auto.connect("toggled", lambda c: self.app.set_autostart(c.get_active()))
        box.pack_start(auto, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 4)
        about = Gtk.ModelButton(text=_("about"))
        about.connect("clicked", lambda *_: self.app.show_about())
        box.pack_start(about, False, False, 0)
        quit_b = Gtk.ModelButton(text=_("quit"))
        quit_b.connect("clicked", lambda *_: self.app.quit_app())
        box.pack_start(quit_b, False, False, 0)
        box.show_all()
        pop.add(box)
        return pop

    # --------------------------------------------------------------- events
    def _on_close(self, *_a):
        w, h = self.get_size()
        self.app.config["size"] = [w, h]
        self.app.save_config()
        self.hide()
        return True

    def _refresh(self, *_a):
        self.backend.refresh()
        if self.web is not None and self.stack.get_visible_child_name() == "web":
            self.web.reload()

    def _sort(self, a, b):
        da, db = a.get_child().dev, b.get_child().dev
        ka = (not da.is_playing, not da.online, da.kind != "tv", da.name.lower())
        kb = (not db.is_playing, not db.online, db.kind != "tv", db.name.lower())
        return (ka > kb) - (ka < kb)

    def device_changed(self, dev: Device):
        card = self.cards.get(dev.id)
        if card is None:
            card = DeviceCard(self, dev)
            self.cards[dev.id] = card
            self.flow.add(card)
            card.get_parent().show_all()
            card.update()
        else:
            card.update()
        self.flow.invalidate_sort()
        self._update_counts()

    def device_removed(self, dev: Device):
        card = self.cards.pop(dev.id, None)
        if card:
            self.flow.remove(card.get_parent())
        self._update_counts()

    def _update_counts(self):
        n = len(self.cards)
        self.dev_stack.set_visible_child_name("list" if n else "empty")
        playing = sum(1 for c in self.cards.values() if c.dev.is_playing)
        self.count_lbl.set_text(_("n_devices", n=n) + (" · " + _("n_playing", n=playing) if playing else ""))

    # ------------------------------------------------------------------ web
    def _page_changed(self, *_a):
        if self.stack.get_visible_child_name() == "web" and self.web is None:
            self._create_web()

    def _create_web(self):
        try:
            gi.require_version("WebKit2", "4.1")
            from gi.repository import WebKit2
        except (ValueError, ImportError):
            self.web_holder.pack_start(Gtk.Label(label=_("error", err="WebKit2GTK 4.1")), True, True, 0)
            self.web_holder.show_all()
            return
        from .webtiles import shared_context
        ctx = shared_context()
        web = WebKit2.WebView.new_with_context(ctx)
        s = web.get_settings()
        s.set_enable_developer_extras(False)
        s.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ON_DEMAND)
        s.set_enable_smooth_scrolling(True)
        # pop-ups (sign-in, links) open in the same view
        web.connect("create", lambda v, _a: v)
        web.connect("decide-policy", self._web_policy)
        web.connect("load-changed", self._web_loaded)
        web.load_uri("https://home.google.com/")
        self.web = web
        self.web_holder.pack_start(web, True, True, 0)
        self.web_holder.show_all()

    def _web_loaded(self, view, event):
        from gi.repository import WebKit2
        if event == WebKit2.LoadEvent.FINISHED and "/home/" in (view.get_uri() or ""):
            if self.app.webtiles:
                self.app.webtiles.after_login()

    def show_web(self):
        self.stack.set_visible_child_name("web")

    def _web_policy(self, _view, decision, dtype):
        from gi.repository import WebKit2
        if dtype == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            host = GLib.Uri.parse(uri, GLib.UriFlags.NONE).get_host() or ""
            if host.endswith("google.com"):
                self.web.load_uri(uri)
            else:
                Gtk.show_uri_on_window(self, uri, Gdk.CURRENT_TIME)
            decision.ignore()
            return True
        return False

    # -------------------------------------------------------------- pairing
    def pair(self, dev: Device):
        dlg = Gtk.Dialog(title=_("pair_title", name=dev.name), transient_for=self, modal=True)
        dlg.add_button(_("cancel"), Gtk.ResponseType.CANCEL)
        ok = dlg.add_button(_("pair_ok"), Gtk.ResponseType.OK)
        ok.get_style_context().add_class("suggested-action")
        ok.set_sensitive(False)
        box = dlg.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(12); box.set_margin_bottom(12); box.set_margin_start(16); box.set_margin_end(16)
        info = Gtk.Label(label=_("remote_connecting"), xalign=0, wrap=True)
        box.pack_start(info, False, False, 0)
        entry = Gtk.Entry(placeholder_text=_("pair_code"), max_length=6, activates_default=True)
        entry.set_sensitive(False)
        entry.get_style_context().add_class("monospace")
        box.pack_start(entry, False, False, 0)
        dlg.set_default_response(Gtk.ResponseType.OK)
        entry.connect("changed", lambda e: ok.set_sensitive(len(e.get_text().strip()) == 6))
        dlg.show_all()

        def started(err):
            def ui():
                if err:
                    info.set_text(_("pair_failed", err=err))
                else:
                    info.set_text(_("pair_body"))
                    entry.set_sensitive(True)
                    entry.grab_focus()
            GLib.idle_add(ui)

        self.backend.start_pairing(dev, started)

        def on_resp(d, resp):
            if resp == Gtk.ResponseType.OK:
                code = entry.get_text()
                info.set_text(_("remote_connecting"))
                ok.set_sensitive(False)

                def finished(err):
                    def ui():
                        if err:
                            info.set_text(_("pair_failed", err=err or "?"))
                            entry.set_text("")
                            # restart so the TV shows a fresh code
                            self.backend.start_pairing(dev, started)
                        else:
                            self.app.notify(_("pair_done", name=dev.name), "")
                            d.destroy()
                    GLib.idle_add(ui)

                self.backend.finish_pairing(dev, code, finished)
            else:
                if dev.atv_state == "pairing":
                    dev.atv_state = "unpaired"
                    self.device_changed(dev)
                d.destroy()

        dlg.connect("response", on_resp)
