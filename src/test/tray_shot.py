import os, sys, types
sys.argv=[sys.argv[0]]
HERE=os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE,"demo.py")).read().split("sys.exit(App()")[0])
from lgh.webtiles import WebTile
from gi.repository import Gdk
import lgh.app as A
orig=A.App._start_webtiles
def fake(self):
    tiles=[dict(key="Salon/Kamera", name="KameraC210PIŁS", sub="", kind="generic", icon="videocam", on=None, room="Salon", toggle=False),
           dict(key="S/Hub", name="HubH100TAPO", sub="Wyłączono", kind="on-off", icon="switch", type="SWITCH", on=False, room="Sypialnia", toggle=True),
           dict(key="S/sc", name="Sypialnia _sciana_Tapo S210", sub="Wyłączono", kind="on-off", icon="switch", type="SWITCH", on=False, room="Sypialnia", toggle=True),
           dict(key="S/l", name="Lampka_sypialnia_Meross", sub="Włączono", kind="on-off", icon="lightbulb", type="LIGHT", on=True, room="Sypialnia", toggle=True),
           dict(key="S/su", name="Sypialnia _sufit_Tapo S210", sub="Wyłączono", kind="on-off", icon="switch", type="SWITCH", on=False, room="Sypialnia", toggle=True)]
    self.webtiles=types.SimpleNamespace(state="ok", tiles=[WebTile(t) for t in tiles], toggle=lambda k:0, reload=lambda:0)
    self.webtiles.tiles[3].on=True
    self.webtiles.tiles[2].pending=True
    GLib.timeout_add(2500, lambda: (self.toggle_panel(), False)[1]); return False
A.App._start_webtiles=fake
sys.exit(App().run([sys.argv[0]]))
