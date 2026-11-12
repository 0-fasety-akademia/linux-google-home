"""Local control of Google Home devices.

* Google Cast (pychromecast)  -> speakers, displays, Chromecasts, TVs with
  Chromecast built-in: status, what is playing, volume, play/pause/stop.
* Android TV Remote v2 (androidtvremote2) -> Google TV / Android TV:
  power, remote keys, launching apps, typing text.

Everything here runs off the GTK main loop. Callbacks (on_change, on_removed,
on_event) are invoked from worker threads; the UI marshals them itself.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import zeroconf
import pychromecast
from pychromecast.discovery import CastBrowser, SimpleCastListener
from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth

from . import APP_NAME

LOG = logging.getLogger("lgh.backend")

ATV_SERVICE = "_androidtvremote2._tcp.local."
MEDIA_NS = "urn:x-cast:com.google.cast.media"

# Android package -> friendly name (used for Google TV "current app")
ATV_APP_NAMES = {
    "com.google.android.youtube.tv": "YouTube",
    "com.google.android.youtube.tvkids": "YouTube Kids",
    "com.google.android.youtube.tvmusic": "YouTube Music",
    "com.netflix.ninja": "Netflix",
    "com.disney.disneyplus": "Disney+",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.spotify.tv.android": "Spotify",
    "com.wbd.stream": "Max",
    "com.hbo.hbonow": "Max",
    "com.apple.atve.androidtv.appletv": "Apple TV",
    "pl.tvn.player.tv": "Player",
    "pl.redefine.ipla": "Polsat Box Go",
    "com.canalplus.canalplus": "Canal+",
    "com.skyshowtime.skyshowtime.google": "SkyShowtime",
    "com.google.android.apps.tv.launcherx": None,  # home screen
    "com.google.android.tvlauncher": None,
    "com.google.android.leanbacklauncher": None,
    "com.google.android.backdrop": None,  # ambient mode
    "com.android.tv.settings": "Ustawienia / Settings",
    "com.google.android.tvrecommendations": None,
}

# Quick-launch buttons for the TV remote (deep links work without app ids)
ATV_LAUNCH = [
    ("YouTube", "https://www.youtube.com"),
    ("Netflix", "https://www.netflix.com/title"),
    ("Disney+", "https://www.disneyplus.com"),
    ("Prime Video", "https://app.primevideo.com"),
    ("Spotify", "spotify://"),
    ("Max", "https://play.max.com"),
]

LAUNCHER_PACKAGES = {k for k, v in ATV_APP_NAMES.items() if v is None}


def atv_app_name(package: str | None) -> str | None:
    if not package or package in LAUNCHER_PACKAGES:
        return None
    if package in ATV_APP_NAMES:
        return ATV_APP_NAMES[package]
    # com.vendor.appname -> Appname
    tail = package.rsplit(".", 1)[-1]
    return tail[:1].upper() + tail[1:]


class Device:
    """Merged view of one physical device (Cast and/or Android TV remote)."""

    def __init__(self, dev_id: str, name: str, host: str):
        self.id = dev_id
        self.name = name
        self.host = host
        self.model = ""
        self.manufacturer = ""
        self.cast_type = None  # 'cast' | 'audio' | 'group'
        self.cast: pychromecast.Chromecast | None = None
        self.cast_status = None
        self.media_status = None
        self.cast_connected = False
        # Android TV remote
        self.atv: AndroidTVRemote | None = None
        self.atv_state = "none"  # none|unpaired|connecting|connected|idle|pairing|error
        self._atv_last_use = 0.0
        self._atv_closing = False
        self._atv_watch = None
        self.atv_on: bool | None = None
        self.atv_app: str | None = None
        self.atv_volume: dict | None = None
        self.atv_host: str | None = None
        self.atv_port = 6466
        self.atv_pair_port = 6467
        # notification bookkeeping
        self._last_sig: str | None = None
        self._sig_primed = False
        self.last_seen = time.time()

    # ------------------------------------------------------------------ kinds
    @property
    def kind(self) -> str:
        model = (self.model or "").lower()
        if self.cast_type == "group":
            return "group"
        if self.atv_host or "tv" in model.split() or "google tv" in model:
            return "tv"
        if self.cast_type == "audio":
            return "speaker"
        if "hub" in model or "display" in model:
            return "display"
        if "chromecast" in model:
            return "chromecast"
        if self.manufacturer and "google" not in self.manufacturer.lower():
            return "tv"  # TV with Chromecast built-in
        return "chromecast"

    @property
    def has_cast(self) -> bool:
        return self.cast is not None

    @property
    def cast_media_ok(self) -> bool:
        """True only if the app running on the device speaks the Cast media
        protocol. Sending media commands otherwise makes pychromecast LAUNCH the
        Default Media Receiver - which closes e.g. Netflix on Google TV and shows
        the blue Cast screen."""
        cs = self.cast_status
        return bool(cs and cs.app_id and MEDIA_NS in (cs.namespaces or []))

    @property
    def has_remote(self) -> bool:
        return self.atv_host is not None

    # ------------------------------------------------------------------ state
    @property
    def app_name(self) -> str | None:
        cs = self.cast_status
        if cs and cs.display_name and cs.app_id and cs.display_name not in ("Backdrop",):
            return cs.display_name
        return atv_app_name(self.atv_app)

    @property
    def player_state(self) -> str | None:
        ms = self.media_status
        if not ms or not self.cast_status or not self.cast_status.app_id:
            return None
        return ms.player_state  # PLAYING | PAUSED | BUFFERING | IDLE | UNKNOWN

    @property
    def is_playing(self) -> bool:
        if self.player_state in ("PLAYING", "BUFFERING"):
            return True
        # Google TV with a real app in foreground (no cast session) counts as active
        if self.atv_on and atv_app_name(self.atv_app):
            return True
        return False

    @property
    def is_paused(self) -> bool:
        return self.player_state == "PAUSED"

    @property
    def is_standby(self) -> bool:
        if self.atv_on is False:
            return True
        cs = self.cast_status
        return bool(cs and cs.is_stand_by and not cs.app_id)

    @property
    def online(self) -> bool:
        return self.cast_connected or self.atv_state in ("connected", "idle")

    @property
    def title(self) -> str | None:
        ms = self.media_status
        if ms and self.player_state not in (None, "IDLE", "UNKNOWN"):
            return ms.title
        return None

    @property
    def subtitle(self) -> str | None:
        ms = self.media_status
        if ms and self.title:
            return ms.artist or ms.series_title or ms.album_name
        return None

    @property
    def image_url(self) -> str | None:
        ms = self.media_status
        if ms and self.title and ms.images:
            return ms.images[0].url
        return None

    @property
    def volume(self) -> float | None:
        if self.atv_state == "connected" and self.atv_volume and self.atv_volume.get("max"):
            return self.atv_volume["level"] / self.atv_volume["max"]
        if self.cast_status:
            return self.cast_status.volume_level
        return None

    @property
    def muted(self) -> bool:
        if self.cast_status:
            return bool(self.cast_status.volume_muted)
        if self.atv_volume:
            return bool(self.atv_volume.get("muted"))
        return False

    def activity_signature(self) -> str | None:
        """What is 'running' right now, as a short human string (or None)."""
        if not self.is_playing:
            return None
        parts = [p for p in (self.app_name, self.title) if p]
        return " — ".join(parts) if parts else None


class Backend:
    def __init__(
        self,
        config_dir: str,
        on_change: Callable[[Device], None],
        on_removed: Callable[[Device], None],
        on_event: Callable[[str, Device, str], None],
    ):
        self.config_dir = config_dir
        os.makedirs(config_dir, exist_ok=True)
        self.certfile = os.path.join(config_dir, "remote_cert.pem")
        self.keyfile = os.path.join(config_dir, "remote_key.pem")
        self.on_change = on_change
        self.on_removed = on_removed
        self.on_event = on_event
        self.devices: dict[str, Device] = {}
        self._cast_ids: dict[str, str] = {}  # cast uuid -> device id
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="lgh-cmd")
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="lgh-async")
        self.zconf: zeroconf.Zeroconf | None = None
        self.browser: CastBrowser | None = None
        self._atv_browser = None
        self._stopped = False
        # Remote: "on_demand" connects only while you use the remote (the TV is left
        # alone otherwise); "always" keeps a permanent connection (live app/volume).
        self.remote_mode = "on_demand"
        self.enable_ime = False  # TV keyboard / text input; off by default

    # ---------------------------------------------------------------- startup
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self):
        self._loop_thread.start()
        self.zconf = zeroconf.Zeroconf()
        self.browser = CastBrowser(
            SimpleCastListener(self._cast_added, self._cast_removed, self._cast_updated),
            self.zconf,
        )
        self.browser.start_discovery()
        self._atv_browser = zeroconf.ServiceBrowser(self.zconf, ATV_SERVICE, listener=_AtvListener(self))

    def stop(self):
        self._stopped = True
        try:
            if self.browser:
                self.browser.stop_discovery()
        except Exception:
            pass
        for d in list(self.devices.values()):
            try:
                if d.cast:
                    d.cast.disconnect(timeout=1)
            except Exception:
                pass
            try:
                if d.atv:
                    d.atv.disconnect()
            except Exception:
                pass
        try:
            if self.zconf:
                self.zconf.close()
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _emit(self, dev: Device):
        dev.last_seen = time.time()
        self._check_activity(dev)
        try:
            self.on_change(dev)
        except Exception:
            LOG.exception("on_change failed")

    def _check_activity(self, dev: Device):
        sig = dev.activity_signature()
        if not dev._sig_primed:
            # first status after discovery: remember, do not notify
            if dev.online:
                dev._sig_primed = True
                dev._last_sig = sig
            return
        if sig and sig != dev._last_sig:
            try:
                self.on_event("started", dev, sig)
            except Exception:
                LOG.exception("on_event failed")
        dev._last_sig = sig

    def _find_by_host(self, host: str) -> Device | None:
        for d in self.devices.values():
            if d.cast_type != "group" and (d.host == host or d.atv_host == host):
                return d
        return None

    # ------------------------------------------------------------------- cast
    def _cast_added(self, uuid, _service):
        info = self.browser.devices.get(uuid)
        if not info:
            return
        with self._lock:
            if str(uuid) in self._cast_ids:
                return
            dev = None
            if info.cast_type != "group":
                # attach to an Android TV remote already found on the same host
                for other in self.devices.values():
                    if other.atv_host == info.host and other.cast is None:
                        dev = other
                        break
            if dev is None:
                dev = Device(str(uuid), info.friendly_name or info.host, info.host)
                self.devices[dev.id] = dev
            dev.name = info.friendly_name or dev.name
            dev.model = info.model_name or ""
            dev.manufacturer = info.manufacturer or ""
            dev.cast_type = info.cast_type
            self._cast_ids[str(uuid)] = dev.id
        try:
            cast = pychromecast.get_chromecast_from_cast_info(info, self.zconf, tries=None, retry_wait=5, timeout=10)
        except Exception as e:  # pragma: no cover - network specific
            LOG.warning("cannot create cast %s: %s", dev.name, e)
            self._emit(dev)
            return
        dev.cast = cast
        cast.register_status_listener(_CastStatusL(self, dev))
        cast.media_controller.register_status_listener(_MediaStatusL(self, dev))
        cast.register_connection_listener(_ConnL(self, dev))
        cast.start()
        self._emit(dev)

    def _cast_updated(self, uuid, _service):
        info = self.browser.devices.get(uuid)
        dev = self.devices.get(self._cast_ids.get(str(uuid), ""))
        if info and dev:
            dev.name = info.friendly_name or dev.name
            dev.host = info.host
            self._emit(dev)

    def _cast_removed(self, uuid, _service, _info):
        with self._lock:
            dev = self.devices.get(self._cast_ids.get(str(uuid), ""))
        if dev:
            dev.cast_connected = False
            self._emit(dev)

    # -------------------------------------------------------------- androidtv
    def _atv_found(self, name: str, host: str, port: int):
        with self._lock:
            dev = self._find_by_host(host)
            if dev is None:
                dev = Device("atv:" + host, name, host)
                self.devices[dev.id] = dev
            if dev.atv_host and dev.atv is not None:
                return
            dev.atv_host = host
            dev.atv_port = port or 6466
        self._emit(dev)
        asyncio.run_coroutine_threadsafe(self._atv_connect(dev, probe=not self._persistent), self._loop)

    def _new_remote(self, dev: Device) -> AndroidTVRemote:
        return AndroidTVRemote(
            client_name=APP_NAME,
            certfile=self.certfile,
            keyfile=self.keyfile,
            host=dev.atv_host,
            api_port=dev.atv_port,
            pair_port=dev.atv_pair_port,
            loop=self._loop,
            enable_ime=self.enable_ime,
        )

    def _wire_atv_callbacks(self, dev: Device):
        r = dev.atv

        def is_on(v):
            dev.atv_on = v
            self._emit(dev)

        def app(v):
            dev.atv_app = v
            self._emit(dev)

        def vol(v):
            dev.atv_volume = dict(v)
            self._emit(dev)

        def avail(v):
            if dev._atv_closing:
                return
            dev.atv_state = "connected" if v else "connecting"
            self._emit(dev)

        r.add_is_on_updated_callback(is_on)
        r.add_current_app_updated_callback(app)
        r.add_volume_info_updated_callback(vol)
        r.add_is_available_updated_callback(avail)

    @property
    def _persistent(self) -> bool:
        return self.remote_mode == "always"

    async def _atv_connect(self, dev: Device, probe: bool = False):
        """Connect the remote. probe=True: on-demand mode, just check pairing and
        hang up again right away."""
        if dev.atv is None:
            dev.atv = self._new_remote(dev)
            await dev.atv.async_generate_cert_if_missing()
            self._wire_atv_callbacks(dev)
        if dev.atv_state == "connected":
            return
        dev._atv_closing = False
        LOG.info("%s: remote connecting (probe=%s, mode=%s, ime=%s)", dev.name, probe, self.remote_mode, self.enable_ime)
        dev.atv_state = "connecting"
        self._emit(dev)
        try:
            await dev.atv.async_connect()
        except InvalidAuth:
            dev.atv_state = "unpaired"
            self._emit(dev)
            return
        except (CannotConnect, ConnectionClosed, OSError) as e:
            LOG.info("android tv %s not reachable: %s", dev.name, e)
            dev.atv_state = "error"
            self._emit(dev)
            if self._persistent:
                await asyncio.sleep(30)
                if not self._stopped and dev.atv_state == "error" and self._persistent:
                    await self._atv_connect(dev)
            return
        dev.atv_state = "connected"
        dev.atv_on = dev.atv.is_on
        dev.atv_app = dev.atv.current_app
        dev.atv_volume = dict(dev.atv.volume_info) if dev.atv.volume_info else None
        if self._persistent:
            dev.atv.keep_reconnecting(lambda: self._atv_invalid_auth(dev))
        else:
            dev._atv_last_use = self._loop.time() - (85 if probe else 0)
            if dev._atv_watch is None or dev._atv_watch.done():
                dev._atv_watch = self._loop.create_task(self._atv_idle_watch(dev))
        self._emit(dev)

    async def _atv_idle_watch(self, dev: Device):
        """On-demand mode: hang up ~90 s after the last remote use."""
        while not self._stopped and dev.atv_state == "connected" and not self._persistent:
            await asyncio.sleep(5)
            if self._loop.time() - dev._atv_last_use > 90:
                self._atv_hangup(dev)
                return

    def _atv_hangup(self, dev: Device):
        if dev.atv is None:
            return
        dev._atv_closing = True
        LOG.info("%s: remote hang up", dev.name)
        try:
            dev.atv.disconnect()
        except Exception:
            pass
        if dev.atv_state == "connected":
            dev.atv_state = "idle"
            dev.atv_app = None
        self._emit(dev)

    def apply_remote_settings(self, mode: str, ime: bool):
        """Called from the UI when the user changes remote options."""
        ime_changed = ime != self.enable_ime
        self.remote_mode, self.enable_ime = mode, ime

        def go():
            for dev in list(self.devices.values()):
                if not dev.atv_host or dev.atv_state in ("unpaired", "pairing", "none"):
                    continue
                self._atv_hangup(dev)
                if ime_changed:
                    dev.atv = None  # re-created with the new IME setting
                if self._persistent:
                    self._loop.create_task(self._atv_connect(dev))
        self._loop.call_soon_threadsafe(go)

    def _atv_invalid_auth(self, dev: Device):
        dev.atv_state = "unpaired"
        self._emit(dev)

    def start_pairing(self, dev: Device, done: Callable[[Exception | None], None]):
        async def go():
            try:
                if dev.atv is None:
                    dev.atv = self._new_remote(dev)
                    self._wire_atv_callbacks(dev)
                await dev.atv.async_generate_cert_if_missing()
                await dev.atv.async_start_pairing()
                dev.atv_state = "pairing"
                done(None)
            except Exception as e:
                done(e)
        asyncio.run_coroutine_threadsafe(go(), self._loop)

    def finish_pairing(self, dev: Device, code: str, done: Callable[[Exception | None], None]):
        async def go():
            try:
                await dev.atv.async_finish_pairing(code.strip().upper())
            except Exception as e:
                dev.atv_state = "unpaired"
                self._emit(dev)
                done(e)
                return
            done(None)
            dev.atv_state = "idle"
            await self._atv_connect(dev, probe=not self._persistent)
        asyncio.run_coroutine_threadsafe(go(), self._loop)

    # ---------------------------------------------------------------- actions
    def _bg(self, fn, *a):
        LOG.info("cast command: %s %s", getattr(fn, "__qualname__", fn), a)

        def run():
            try:
                fn(*a)
            except Exception as e:
                LOG.warning("command failed: %s", e)
        self._pool.submit(run)

    def _atv_call(self, dev: Device, fn):
        """Run a remote command, connecting first if needed (on-demand mode)."""
        if not dev.atv_host or dev.atv_state not in ("connected", "idle", "connecting", "error"):
            return False

        async def run():
            if dev.atv_state != "connected":
                await self._atv_connect(dev)
            if dev.atv_state == "connected":
                dev._atv_last_use = self._loop.time()
                LOG.info("%s: remote command", dev.name)
                _safe(fn)
        asyncio.run_coroutine_threadsafe(run(), self._loop)
        return True

    def remote_wake(self, dev: Device):
        """Remote popover opened: connect now so the first key press is instant."""
        self._atv_call(dev, lambda: None)

    def key(self, dev: Device, keycode: str):
        self._atv_call(dev, lambda: dev.atv.send_key_command(keycode))

    def launch(self, dev: Device, link: str):
        self._atv_call(dev, lambda: dev.atv.send_launch_app_command(link))

    def send_text(self, dev: Device, text: str):
        self._atv_call(dev, lambda: dev.atv.send_text(text))

    def power(self, dev: Device):
        if not self._atv_call(dev, lambda: dev.atv.send_key_command("KEYCODE_POWER")):
            if dev.cast:
                self._bg(dev.cast.quit_app)

    def play_pause(self, dev: Device):
        if dev.cast and dev.player_state and dev.cast_media_ok:
            mc = dev.cast.media_controller
            self._bg(mc.pause if dev.player_state == "PLAYING" else mc.play)
        else:
            self.key(dev, "KEYCODE_MEDIA_PLAY_PAUSE")

    def stop(self, dev: Device):
        if dev.cast and dev.cast_status and dev.cast_status.app_id:
            self._bg(dev.cast.quit_app)
        else:
            self.key(dev, "KEYCODE_MEDIA_STOP")

    def next(self, dev: Device):
        if dev.cast and dev.player_state and dev.cast_media_ok:
            self._bg(dev.cast.media_controller.queue_next)
        else:
            self.key(dev, "KEYCODE_MEDIA_NEXT")

    def prev(self, dev: Device):
        if dev.cast and dev.player_state and dev.cast_media_ok:
            self._bg(dev.cast.media_controller.queue_prev)
        else:
            self.key(dev, "KEYCODE_MEDIA_PREVIOUS")

    def set_volume(self, dev: Device, level: float):
        if dev.cast:
            self._bg(dev.cast.set_volume, max(0.0, min(1.0, level)))

    def volume_step(self, dev: Device, up: bool):
        if dev.atv_state in ("connected", "idle"):
            self.key(dev, "KEYCODE_VOLUME_UP" if up else "KEYCODE_VOLUME_DOWN")
        elif dev.cast:
            self._bg(dev.cast.volume_up if up else dev.cast.volume_down, 0.05)

    def toggle_mute(self, dev: Device):
        if dev.cast:
            self._bg(dev.cast.set_volume_muted, not dev.muted)
        else:
            self.key(dev, "KEYCODE_VOLUME_MUTE")

    def refresh(self):
        """Ask every device for a fresh status (periodic + manual)."""
        for dev in list(self.devices.values()):
            # passive: never send anything that could launch an app on the device
            if dev.cast and dev.cast_connected and dev.cast_media_ok:
                LOG.info("%s: refresh media status (%s)", dev.name, dev.cast_status.display_name)
                self._bg(dev.cast.media_controller.update_status)
            elif dev.atv_state == "error" and dev.atv is not None and self._persistent:
                asyncio.run_coroutine_threadsafe(self._atv_connect(dev), self._loop)
            self._emit(dev)

    def playing_devices(self) -> list[Device]:
        return [d for d in self.devices.values() if d.is_playing or d.is_paused]


def _safe(fn):
    try:
        fn()
    except Exception as e:
        LOG.warning("remote command failed: %s", e)


class _CastStatusL:
    def __init__(self, be: Backend, dev: Device):
        self.be, self.dev = be, dev

    def new_cast_status(self, status):
        old = self.dev.cast_status
        if not old or old.app_id != status.app_id:
            LOG.info("%s: running app -> %s (%s)", self.dev.name, status.display_name, status.app_id)
        self.dev.cast_status = status
        self.dev.cast_connected = True
        if not status.app_id:
            self.dev.media_status = None
        self.be._emit(self.dev)


class _MediaStatusL:
    def __init__(self, be: Backend, dev: Device):
        self.be, self.dev = be, dev

    def new_media_status(self, status):
        self.dev.media_status = status
        self.be._emit(self.dev)

    def load_media_failed(self, *_a):
        pass


class _ConnL:
    def __init__(self, be: Backend, dev: Device):
        self.be, self.dev = be, dev

    def new_connection_status(self, status):
        self.dev.cast_connected = status.status == "CONNECTED"
        self.be._emit(self.dev)


class _AtvListener(zeroconf.ServiceListener):
    def __init__(self, be: Backend):
        self.be = be

    def _resolve(self, zc, type_, name):
        info = zc.get_service_info(type_, name, timeout=3000)
        if not info:
            return
        addrs = info.parsed_addresses(zeroconf.IPVersion.V4Only)
        if not addrs:
            return
        nice = name[: -len(type_) - 1] if name.endswith(type_) else name
        self.be._atv_found(nice, addrs[0], info.port or 6466)

    def add_service(self, zc, type_, name):
        threading.Thread(target=self._resolve, args=(zc, type_, name), daemon=True).start()

    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)

    def remove_service(self, zc, type_, name):
        pass
