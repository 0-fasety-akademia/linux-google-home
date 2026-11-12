"""Run the app with fake devices (no network) for screenshots/tests."""
import os, sys, types, time
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.join(SRC, "vendor")); sys.path.insert(0, SRC)
os.environ.setdefault("LGH_ICON_DIR", os.path.join(SRC, "icons"))
from gi.repository import GLib
import lgh.backend as B
from lgh.app import App

def NS(**k): return types.SimpleNamespace(**k)

class FakeCast:
    def __init__(s): s.media_controller = NS(pause=lambda:0, play=lambda:0, queue_next=lambda:0, queue_prev=lambda:0, update_status=lambda:0)
    def quit_app(s): pass
    def set_volume(s, v): pass
    def set_volume_muted(s, m): pass

def fake_start(self):
    def mk(i, name, model, ctype, manu="Google Inc."):
        d = B.Device(i, name, "192.168.1.%d" % len(self.devices)); d.model=model; d.cast_type=ctype; d.manufacturer=manu
        d.cast = FakeCast(); d.cast_connected=True; self.devices[i]=d; return d
    tv = mk("tv", "Salon TV", "Google TV Streamer", "cast"); tv.atv_host="192.168.1.50"; tv.atv_state="connected"; tv.atv_on=True
    tv.atv_app="com.netflix.ninja"; tv.atv_volume={"level":18,"max":100,"muted":False}
    tv.cast_status=NS(app_id="CA5E8412", display_name="Netflix", is_stand_by=False, volume_level=0.18, volume_muted=False)
    tv.media_status=NS(player_state="PLAYING", title="Stranger Things", artist=None, series_title="S5:E3", album_name=None, images=[])
    k = mk("kitchen", "Kuchnia", "Google Nest Audio", "audio")
    k.cast_status=NS(app_id="CC32E753", display_name="Spotify", is_stand_by=False, volume_level=0.42, volume_muted=False)
    k.media_status=NS(player_state="PAUSED", title="Bohemian Rhapsody", artist="Queen", series_title=None, album_name="A Night at the Opera", images=[])
    h = mk("hub", "Sypialnia", "Google Nest Hub", "cast")
    h.cast_status=NS(app_id=None, display_name=None, is_stand_by=True, volume_level=0.3, volume_muted=False)
    m = mk("mini", "Łazienka", "Google Nest Mini", "audio")
    m.cast_status=NS(app_id=None, display_name=None, is_stand_by=False, volume_level=0.25, volume_muted=True)
    g = mk("grp", "Cały dom", "Google Cast Group", "group")
    g.cast_status=NS(app_id=None, display_name=None, is_stand_by=False, volume_level=0.5, volume_muted=False)
    tv2 = B.Device("atv:x", "Telewizor Sony", "192.168.1.60"); tv2.atv_host="192.168.1.60"; tv2.atv_state="unpaired"; self.devices[tv2.id]=tv2
    for d in self.devices.values():
        d._sig_primed = True
        self.on_change(d)
    def later():
        # simulate a new thing starting -> notification
        m.cast_status=NS(app_id="X", display_name="YouTube Music", is_stand_by=False, volume_level=0.25, volume_muted=False)
        m.media_status=NS(player_state="PLAYING", title="Lose Yourself", artist="Eminem", series_title=None, album_name=None, images=[])
        self._emit(m); return False
    GLib.timeout_add(1500, later)

B.Backend.start = fake_start
B.Backend.stop = lambda self: None
sys.exit(App().run([sys.argv[0]] + sys.argv[1:]))
