"""Cloud-only devices (plugs, lights, cameras…) read from a hidden
home.google.com page. Shares cookies with the visible web tab, so signing in
there once is enough.

Tile DOM (checked 2026-11-05):
  div.space > h2 (room) … ghw-device-tile > ghw-tile-on-off > button.on-off-tile.<TYPE>.(in)active[title=Włącz|Wyłącz]
      p.title (name), p.subtitle (Włączono / Wyłączono / …)
  ghw-tile-media (speakers – handled locally via Cast, skipped here)
  ghw-tile-generic (cameras etc.)
"""
from __future__ import annotations

import json
import logging
import os
import re

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

LOG = logging.getLogger("lgh.web")

HOME_URL = os.environ.get("LGH_HOME_URL", "https://home.google.com/")

SCRAPE_JS = r"""
(() => {
  const onWords = /^(włączono|włączone|on|otwarte|open)$|^\d+\s?%/i;
  const out = [];
  document.querySelectorAll('ghw-device-tile').forEach((dt, i) => {
    const t = dt.firstElementChild && [...dt.querySelectorAll('*')].find(e => e.tagName.startsWith('GHW-TILE'));
    if (!t) return;
    const tag = t.tagName.toLowerCase().replace('ghw-tile-', '');
    if (tag === 'media') return;
    const nameEl = t.querySelector('.title');
    const name = nameEl ? nameEl.textContent.trim() : '';
    if (!name) return;
    const subEl = t.querySelector('.subtitle');
    const sub = subEl ? subEl.textContent.trim() : '';
    const b = t.querySelector('button');
    const cls = b ? (b.className || '').toString() : '';
    const title = b ? (b.getAttribute('title') || '') : '';
    const space = dt.closest('.space');
    const h = space && space.querySelector('h2');
    const icon = t.querySelector('mat-icon');
    let on = null;
    if (tag === 'on-off') {
      on = /(^|\s)active(\s|$)/.test(cls) || /^(wyłącz|turn off)$/i.test(title) || onWords.test(sub);
      if (/(^|\s)inactive(\s|$)/.test(cls) && /^(włącz|turn on)$/i.test(title)) on = false;
    }
    out.push({
      key: (h ? h.textContent.trim() : '') + '/' + name,
      name, sub, kind: tag, on,
      type: (cls.match(/\b(SWITCH|LIGHT|OUTLET|FAN|THERMOSTAT|CAMERA|LOCK|SENSOR|[A-Z_]{3,})\b/) || [])[1] || '',
      icon: icon ? icon.textContent.trim() : '',
      room: h ? h.textContent.trim() : '',
      toggle: tag === 'on-off' && !!b && b.getAttribute('aria-disabled') !== 'true',
    });
  });
  return JSON.stringify({url: location.href, tiles: out});
})()
"""

# MutationObserver -> push changes to Python immediately (debounced)
OBSERVER_JS = r"""
(() => {
  if (window.__lghObs) return;
  let timer = null;
  const push = () => {
    timer = null;
    try { window.webkit.messageHandlers.lgh.postMessage(%s); } catch (e) {}
  };
  window.__lghObs = new MutationObserver(() => { if (!timer) timer = setTimeout(push, 400); });
  window.__lghObs.observe(document.documentElement, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['class', 'title']});
  push();
})();
""" % SCRAPE_JS.strip().rstrip(";")

LOCATE_JS = r"""
(() => {
  const key = %s;
  for (const dt of document.querySelectorAll('ghw-device-tile')) {
    const t = dt.querySelector('ghw-tile-on-off');
    if (!t) continue;
    const name = (t.querySelector('.title') || {}).textContent;
    const space = dt.closest('.space');
    const h = space && space.querySelector('h2');
    if (((h ? h.textContent.trim() : '') + '/' + (name || '').trim()) === key) {
      const b = t.querySelector('button');
      if (!b) return 'null';
      b.scrollIntoView({block: 'center', inline: 'center'});
      const r = b.getBoundingClientRect();
      // click the icon area (left part) - avoids any inner links
      return JSON.stringify({x: r.left + Math.min(40, r.width / 4), y: r.top + r.height / 2});
    }
  }
  return 'null';
})()
"""


_CONTEXT = None


def shared_context():
    """One WebKit context (cookies, cache) for the visible tab and the hidden page."""
    global _CONTEXT
    if _CONTEXT is None:
        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2
        base = os.path.join(GLib.get_user_data_dir(), "linux-google-home", "web")
        cache = os.path.join(GLib.get_user_cache_dir(), "linux-google-home", "web")
        os.makedirs(base, exist_ok=True)
        dm = WebKit2.WebsiteDataManager(base_data_directory=base, base_cache_directory=cache)
        ctx = WebKit2.WebContext.new_with_website_data_manager(dm)
        cm = dm.get_cookie_manager()
        cm.set_persistent_storage(os.path.join(base, "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE)
        cm.set_accept_policy(WebKit2.CookieAcceptPolicy.NO_THIRD_PARTY)
        _CONTEXT = ctx
    return _CONTEXT


class WebTile:
    __slots__ = ("key", "name", "sub", "kind", "on", "type", "icon", "room", "toggle", "pending")

    def __init__(self, d: dict):
        for k in self.__slots__:
            setattr(self, k, d.get(k))
        self.pending = False


class WebTiles:
    """state: 'loading' | 'ok' | 'login' | 'error'"""

    def __init__(self, context, on_update):
        from gi.repository import WebKit2
        self.WebKit2 = WebKit2
        self.on_update = on_update
        self.tiles: list[WebTile] = []
        self.state = "loading"
        self._devices_url = None
        ucm = WebKit2.UserContentManager()
        ucm.register_script_message_handler("lgh")
        ucm.connect("script-message-received::lgh", self._on_message)
        self.view = WebKit2.WebView(web_context=context, user_content_manager=ucm)
        s = self.view.get_settings()
        s.set_media_playback_requires_user_gesture(True)
        s.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        self.view.connect("load-changed", self._on_load)
        self.view.connect("web-process-terminated", lambda *_: GLib.timeout_add_seconds(5, self.reload))
        # an offscreen toplevel keeps the page alive and rendering without a window
        self.win = Gtk.OffscreenWindow()
        self.win.set_default_size(1200, 900)
        self.win.add(self.view)
        self.win.show_all()
        self.view.load_uri(HOME_URL)
        GLib.timeout_add_seconds(45, self._poll)
        GLib.timeout_add_seconds(30 * 60, self._periodic_reload)

    # ----------------------------------------------------------------- loading
    def _on_load(self, view, event):
        if event != self.WebKit2.LoadEvent.FINISHED:
            return
        uri = view.get_uri() or ""
        if "accounts.google.com" in uri or "/welcome" in uri:
            self._set_state("login")
            return
        m = re.match(r"(https://home\.google\.com/home/[^/]+)/", uri)
        if m and not uri.rstrip("/").endswith("/devices"):
            self._devices_url = m.group(1) + "/devices"
            view.load_uri(self._devices_url)
            return
        if m:
            self._devices_url = uri
        self._inject()
        # Angular renders after load; poll a few times until tiles appear
        for t in (2, 5, 10):
            GLib.timeout_add_seconds(t, self._poll_once)

    def _inject(self):
        self._eval(OBSERVER_JS, None)

    def _eval(self, js, cb):
        def done(view, res):
            try:
                val = view.evaluate_javascript_finish(res)
                if cb:
                    cb(val.to_string() if val is not None else None)
            except GLib.Error as e:
                LOG.debug("js error: %s", e)
                if cb:
                    cb(None)
        self.view.evaluate_javascript(js, -1, None, None, None, done)

    def _on_message(self, _ucm, value):
        try:
            text = value.to_string() if hasattr(value, "to_string") else value.get_js_value().to_string()
        except Exception:
            return
        self._parse(text)

    def _poll_once(self):
        self._eval(SCRAPE_JS, self._parse)
        return False

    def _poll(self):
        if self.state != "login":
            self._eval(OBSERVER_JS, None)  # re-arm observer after SPA navigations
            self._poll_once()
        return True

    def _periodic_reload(self):
        self.reload()
        return True

    def reload(self):
        self.view.load_uri(self._devices_url or HOME_URL)
        return False

    def _parse(self, text):
        if not text:
            return
        try:
            data = json.loads(text)
        except ValueError:
            return
        url = data.get("url", "")
        if "/welcome" in url or "accounts.google.com" in url:
            self._set_state("login")
            return
        tiles = [WebTile(d) for d in data.get("tiles", [])]
        if not tiles and self.tiles and self.state == "ok":
            return  # transient re-render; keep last known
        old = [(t.key, t.on, t.sub, t.pending) for t in self.tiles]
        prev = {t.key: t for t in self.tiles}
        for t in tiles:
            p = prev.get(t.key)
            if p is not None and p.pending and t.on == p.on and t.key == getattr(self, "_pending_key", None) \
                    and t.on == getattr(self, "_pending_from", None):
                t.pending = True  # still waiting for the device
        self.tiles = tiles
        if old != [(t.key, t.on, t.sub, t.pending) for t in tiles] or self.state != "ok":
            self.state = "ok"
            self.on_update()

    def _set_state(self, st):
        if st != self.state:
            self.state = st
            self.on_update()

    # ----------------------------------------------------------------- actions
    def toggle(self, key: str):
        """Click the tile in the hidden page with a real (trusted) mouse click -
        Google's page ignores synthetic JS clicks."""
        tile = next((t for t in self.tiles if t.key == key), None)
        if tile is None or not tile.toggle:
            return
        tile.pending = True
        self._pending_key, self._pending_from = key, tile.on
        self.on_update()

        def located(res):
            try:
                pos = json.loads(res) if res else None
            except ValueError:
                pos = None
            if not pos:
                self._finish_pending()
                self.reload()
                return
            # give the page a moment to finish scrolling, then click
            GLib.timeout_add(150, self._real_click, pos["x"], pos["y"])

        self._eval(LOCATE_JS % json.dumps(key), located)
        # confirm from the page; if nothing changed the dot falls back to the real state
        GLib.timeout_add(8000, self._finish_pending)

    def _real_click(self, x, y):
        from gi.repository import Gdk
        win = self.view.get_window()
        if win is None:
            return False
        seat = Gdk.Display.get_default().get_default_seat()
        dev = seat.get_pointer() if seat else None
        t = Gtk.get_current_event_time() or GLib.get_monotonic_time() // 1000

        def ev(kind, **kw):
            e = Gdk.Event.new(kind)
            e.window = win
            e.send_event = False
            e.time = t
            e.x, e.y = float(x), float(y)
            e.x_root, e.y_root = float(x), float(y)
            for k, v in kw.items():
                setattr(e, k, v)
            if dev is not None:
                e.set_device(dev)
            return e

        self.view.event(ev(Gdk.EventType.MOTION_NOTIFY, state=0))
        self.view.event(ev(Gdk.EventType.BUTTON_PRESS, button=1, state=0))
        self.view.event(ev(Gdk.EventType.BUTTON_RELEASE, button=1, state=Gdk.ModifierType.BUTTON1_MASK))
        for ms in (600, 1500, 3000, 5000):
            GLib.timeout_add(ms, self._poll_once)
        return False

    def _finish_pending(self):
        changed = False
        for t in self.tiles:
            if t.pending:
                t.pending = False
                changed = True
        if changed:
            self.on_update()
        return False

    def after_login(self):
        """Visible tab finished signing in -> reload hidden page."""
        if self.state == "login":
            self.reload()
