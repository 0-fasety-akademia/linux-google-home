"""Follow the system light/dark preference: GTK theme variant, app icon in
the dock / app menu, and the tray icon."""
import os
import shutil
import subprocess

from gi.repository import Gio, GLib, Gtk

from . import SLUG

ICON_DIR = os.environ.get("LGH_ICON_DIR", "/usr/share/linux-google-home/icons")
USER_ICON = os.path.expanduser(f"~/.local/share/icons/hicolor/scalable/apps/{SLUG}.svg")


class ThemeWatcher:
    def __init__(self, on_changed):
        self.on_changed = on_changed
        self.dark = False
        self._iface = None
        src = Gio.SettingsSchemaSource.get_default()
        if src and src.lookup("org.gnome.desktop.interface", True):
            self._iface = Gio.Settings.new("org.gnome.desktop.interface")
            self._iface.connect("changed::color-scheme", self._changed)
            self._iface.connect("changed::gtk-theme", self._changed)
        # also listen to the freedesktop portal (works outside GNOME too)
        try:
            self._portal = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings", None)
            self._portal.connect("g-signal", self._portal_signal)
        except Exception:
            self._portal = None
        self._apply(initial=True)

    def _detect(self) -> bool:
        forced = os.environ.get("LGH_THEME")
        if forced in ("dark", "light"):
            return forced == "dark"
        if self._iface is not None:
            if self._iface.get_string("color-scheme") == "prefer-dark":
                return True
            if self._iface.get_string("gtk-theme").lower().endswith("dark"):
                return True
            if self._iface.get_string("color-scheme") == "prefer-light":
                return False
        if self._portal is not None:
            try:
                v = self._portal.call_sync(
                    "Read", GLib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
                    Gio.DBusCallFlags.NONE, 500, None)
                val = v.unpack()[0]
                while isinstance(val, GLib.Variant):
                    val = val.unpack()
                return val == 1
            except Exception:
                pass
        return False

    def _portal_signal(self, _proxy, _sender, signal, params):
        if signal == "SettingChanged":
            ns, key, _ = params.unpack()
            if ns == "org.freedesktop.appearance" and key == "color-scheme":
                GLib.idle_add(self._apply)

    def _changed(self, *_a):
        self._apply()

    def _apply(self, initial=False):
        dark = self._detect()
        if not initial and dark == self.dark:
            return False
        self.dark = dark
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", dark)
        install_user_icon(dark)
        self.on_changed(dark)
        return False

    @property
    def variant(self) -> str:
        return "dark" if self.dark else "light"


def icon_path(dark: bool) -> str:
    return os.path.join(ICON_DIR, ("dark" if dark else "light") + ".svg")


def install_user_icon(dark: bool):
    """Dock and app grid read the icon from the icon theme by name, so put
    the matching variant into the user's icon dir (overrides the system one)."""
    src = icon_path(dark)
    if not os.path.exists(src):
        return
    try:
        os.makedirs(os.path.dirname(USER_ICON), exist_ok=True)
        with open(src, "rb") as f:
            data = f.read()
        if os.path.exists(USER_ICON):
            with open(USER_ICON, "rb") as f:
                if f.read() == data:
                    return
        tmp = USER_ICON + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, USER_ICON)
        base = os.path.expanduser("~/.local/share/icons/hicolor")
        # touch the theme dir so GNOME Shell / dock reload the icon
        os.utime(base, None)
        if shutil.which("gtk-update-icon-cache") and os.path.exists(os.path.join(base, "index.theme")):
            subprocess.Popen(["gtk-update-icon-cache", "-q", "-t", base],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
