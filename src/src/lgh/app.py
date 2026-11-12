"""Application entry point."""
from __future__ import annotations

import json
import logging
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, BUILD_DATE, CREATED_BY, SLUG, SUPPORTED_BY, VERSION  # noqa: E402
from .backend import Backend  # noqa: E402
from .i18n import _  # noqa: E402
from .theme import ThemeWatcher, icon_path  # noqa: E402

REFRESH_SECONDS = 120


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        GLib.set_application_name(APP_NAME)
        GLib.set_prgname(APP_ID)
        self.config_dir = os.path.join(GLib.get_user_config_dir(), SLUG)
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.config = self._load_config()
        self.window = None
        self.tray = None
        self.backend = None
        self.theme = None
        self.webtiles = None
        self._hidden_start = False

    # ---------------------------------------------------------------- config
    def _load_config(self):
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"notifications": True}

    def save_config(self):
        try:
            tmp = self.config_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.config, f, indent=1)
            os.replace(tmp, self.config_path)
        except OSError:
            pass

    def set_notifications(self, on: bool):
        if self.config.get("notifications", True) == on:
            return
        self.config["notifications"] = on
        self.save_config()
        if self.window:
            self.window.notif_chk.set_active(on)
        if self.tray:
            self.tray.rebuild()

    def set_remote_option(self, key, value):
        self.config[key] = value
        self.save_config()
        self.backend.apply_remote_settings(self.config.get("remote_mode", "on_demand"),
                                           bool(self.config.get("remote_ime", False)))
        for card in self.window.cards.values():
            card.update()

    # ------------------------------------------------------------- autostart
    @property
    def _autostart_file(self):
        return os.path.join(GLib.get_user_config_dir(), "autostart", APP_ID + ".desktop")

    def autostart_enabled(self) -> bool:
        return os.path.exists(self._autostart_file)

    def set_autostart(self, on: bool):
        f = self._autostart_file
        try:
            if on:
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f, "w") as fh:
                    fh.write("[Desktop Entry]\nType=Application\n"
                             f"Name={APP_NAME}\nExec={SLUG} --hidden\nIcon={SLUG}\n"
                             "X-GNOME-Autostart-enabled=true\nNoDisplay=false\n")
            elif os.path.exists(f):
                os.remove(f)
        except OSError:
            pass

    # ------------------------------------------------------------- lifecycle
    def do_command_line(self, cmd):
        args = cmd.get_arguments()[1:]
        self._hidden_start = "--hidden" in args
        self.activate()
        return 0

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()  # keep running in the tray when the window is closed
        self.theme = ThemeWatcher(self._theme_changed)
        self.backend = Backend(
            self.config_dir,
            on_change=lambda d: GLib.idle_add(self._dev_changed, d),
            on_removed=lambda d: GLib.idle_add(self._dev_removed, d),
            on_event=lambda kind, d, what: GLib.idle_add(self._dev_event, kind, d, what),
        )
        self.backend.remote_mode = self.config.get("remote_mode", "on_demand")
        self.backend.enable_ime = bool(self.config.get("remote_ime", False))
        from .ui import MainWindow
        from .tray import Tray
        self.window = MainWindow(self)
        self._apply_window_icon()
        self.webtiles = None
        from .panel import TilePanel
        self.panel = TilePanel(self)
        self.tray = Tray(self)
        self.backend.start()
        GLib.idle_add(self._start_webtiles)
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._periodic)

        for name, cb in (("show", lambda *_: self.show_window()), ("quit", lambda *_: self.quit_app())):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)

    def do_activate(self):
        if self._hidden_start:
            self._hidden_start = False
            return
        self.show_window()

    def show_window(self):
        self.window.show()
        self.window.present()

    def quit_app(self):
        try:
            self.backend.stop()
        except Exception:
            pass
        self.release()
        self.quit()

    # ------------------------------------------------------------------ hooks
    def _start_webtiles(self):
        if not self.config.get("web_tiles", True):
            return False
        try:
            from .webtiles import WebTiles, shared_context
            self.webtiles = WebTiles(shared_context(), self.panel_update)
        except Exception as e:  # WebKit missing etc.
            logging.getLogger("lgh").warning("web tiles disabled: %s", e)
        return False

    def toggle_panel(self):
        self.panel.toggle()

    def panel_update(self):
        if getattr(self, "panel", None) is not None:
            self.panel.update()

    def open_web(self):
        self.show_window()
        self.window.show_web()

    def _periodic(self):
        self.backend.refresh()
        return True

    def _dev_changed(self, dev):
        self.window.device_changed(dev)
        self.tray.schedule_rebuild()
        return False

    def _dev_removed(self, dev):
        self.window.device_removed(dev)
        self.tray.schedule_rebuild()
        return False

    def _dev_event(self, kind, dev, what):
        if kind == "started" and self.config.get("notifications", True):
            self.notify(dev.name, what, tag=f"dev-{dev.id}")
        return False

    def notify(self, title: str, body: str, tag: str | None = None):
        n = Gio.Notification.new(title)
        if body:
            n.set_body(body)
        n.set_icon(Gio.FileIcon.new(Gio.File.new_for_path(icon_path(self.theme.dark))))
        n.set_default_action("app.show")
        self.send_notification(tag, n)

    def _theme_changed(self, dark: bool):
        self._apply_window_icon()
        if self.tray:
            self.tray.set_dark(dark)
        self.panel_update()
        Gtk.IconTheme.get_default().rescan_if_needed()

    def _apply_window_icon(self):
        if self.window is None:
            return
        p = icon_path(self.theme.dark)
        if os.path.exists(p):
            try:
                self.window.set_icon_from_file(p)
            except GLib.Error:
                pass

    def show_about(self):
        dlg = Gtk.AboutDialog(transient_for=self.window, modal=True)
        dlg.set_program_name(APP_NAME)
        dlg.set_version(f"{VERSION} ({BUILD_DATE})")
        dlg.set_comments(_("about_text") + f"\n\n{CREATED_BY}\n{SUPPORTED_BY}")
        dlg.set_authors(["JGu", "Supported by Claude"])
        p = icon_path(self.theme.dark)
        if os.path.exists(p):
            from gi.repository import GdkPixbuf
            dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(p, 96, 96))
        dlg.set_license_type(Gtk.License.CUSTOM)
        dlg.set_license("Freeware License (No Modifications).\nFree to use and to share unmodified; modification is not permitted.\nSee /usr/share/doc/linux-google-home/copyright.")
        dlg.run()
        dlg.destroy()


def main():
    logging.basicConfig(level=os.environ.get("LGH_LOG", "WARNING"),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # always keep a small log of what the app sends to devices
    try:
        from logging.handlers import RotatingFileHandler
        log_dir = os.path.join(GLib.get_user_cache_dir(), SLUG)
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(os.path.join(log_dir, "app.log"), maxBytes=1_000_000, backupCount=2)
        fh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        fh.setLevel(logging.INFO)
        lg = logging.getLogger("lgh")
        lg.setLevel(logging.INFO)
        lg.addHandler(fh)
        for name in ("pychromecast", "androidtvremote2"):
            logging.getLogger(name).addHandler(fh)
            logging.getLogger(name).setLevel(logging.INFO)
    except OSError:
        pass
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {VERSION} ({BUILD_DATE})")
        return 0
    app = App()
    rc = app.run(sys.argv)
    sys.stdout.flush()
    os._exit(rc)  # don't wait for lingering network threads
