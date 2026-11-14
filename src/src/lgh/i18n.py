"""Tiny PL/EN translation layer following the system language."""
import locale
import os

_STRINGS = {
    "devices": ("Urządzenia", "Devices"),
    "theme": ("Motyw", "Theme"),
    "theme_system": ("Systemowy (jasny / ciemny)", "System (light / dark)"),
    "theme_aurora": ("Aurora (jasny / ciemny)", "Aurora (light / dark)"),
    "web": ("Google Home (web)", "Google Home (web)"),
    "searching": ("Szukam urządzeń w sieci…", "Searching for devices on your network…"),
    "searching_hint": (
        "Laptop musi być w tej samej sieci Wi-Fi co głośniki i TV.",
        "The laptop must be on the same Wi-Fi network as your speakers and TV.",
    ),
    "n_devices": ("Urządzenia: {n}", "Devices: {n}"),
    "n_playing": ("odtwarza: {n}", "playing: {n}"),
    "idle": ("Bezczynny", "Idle"),
    "standby": ("Czuwanie", "Standby"),
    "off": ("Wyłączony", "Off"),
    "on": ("Włączony", "On"),
    "offline": ("Niedostępny", "Unavailable"),
    "playing": ("Odtwarza", "Playing"),
    "paused": ("Wstrzymano", "Paused"),
    "buffering": ("Buforowanie", "Buffering"),
    "remote": ("Pilot", "Remote"),
    "not_paired": ("Niesparowany", "Not paired"),
    "pair_remote": ("Połącz pilota", "Pair remote"),
    "power": ("Zasilanie", "Power"),
    "mute": ("Wycisz", "Mute"),
    "stop": ("Zatrzymaj", "Stop"),
    "play_pause": ("Odtwórz / pauza", "Play / pause"),
    "next": ("Następny", "Next"),
    "prev": ("Poprzedni", "Previous"),
    "volume": ("Głośność", "Volume"),
    "home": ("Ekran główny", "Home"),
    "back": ("Wstecz", "Back"),
    "input": ("Źródło", "Input"),
    "settings": ("Ustawienia", "Settings"),
    "apps": ("Aplikacje", "Apps"),
    "type_text": ("Wpisz tekst na TV…", "Type text on TV…"),
    "send": ("Wyślij", "Send"),
    "pair_title": ("Parowanie z {name}", "Pairing with {name}"),
    "pair_body": (
        "Na ekranie telewizora pojawił się kod. Wpisz go poniżej.",
        "A code is now shown on your TV screen. Enter it below.",
    ),
    "pair_code": ("Kod z TV", "Code from TV"),
    "pair_ok": ("Połącz", "Pair"),
    "cancel": ("Anuluj", "Cancel"),
    "pair_failed": ("Parowanie nie powiodło się: {err}", "Pairing failed: {err}"),
    "pair_done": ("Pilot połączony z {name}", "Remote paired with {name}"),
    "remote_connecting": ("Łączenie z pilotem…", "Connecting remote…"),
    "show": ("Pokaż okno", "Show window"),
    "quit": ("Zakończ", "Quit"),
    "now_playing": ("Teraz odtwarzane", "Now playing"),
    "nothing_playing": ("Nic nie jest odtwarzane", "Nothing is playing"),
    "notifications": ("Powiadomienia o odtwarzaniu", "Playback notifications"),
    "autostart": ("Uruchamiaj przy logowaniu (w trayu)", "Start at login (in tray)"),
    "web_login": ("Zaloguj się do Google Home (web)…", "Sign in to Google Home (web)…"),
    "web_loading_devices": ("Ładowanie urządzeń Google Home…", "Loading Google Home devices…"),
    "other_devices": ("Inne", "Other"),
    "click_toggle": ("Kliknij, aby włączyć / wyłączyć", "Click to turn on / off"),
    "camera": ("Kamera", "Camera"),
    "media": ("Multimedia", "Media"),
    "panel": ("Kafelki urządzeń", "Device tiles"),
    "remote_always": ("Pilot TV połączony na stałe", "Keep TV remote connected"),
    "remote_always_tip": (
        "Domyślnie aplikacja łączy się z TV tylko na czas używania pilota i rozłącza po ~1,5 min. "
        "Stałe połączenie daje podgląd aplikacji na TV na żywo, ale na niektórych TV przeszkadza (np. Netflix z fizycznego pilota).",
        "By default the app connects to the TV only while you use the remote and hangs up after ~1.5 min. "
        "A permanent connection shows the TV's current app live, but interferes on some TVs (e.g. Netflix from the physical remote).",
    ),
    "remote_ime": ("Klawiatura TV (wpisywanie tekstu)", "TV keyboard (text input)"),
    "remote_ime_tip": (
        "Rejestruje aplikację jako klawiaturę na TV, żeby wpisywać tekst z laptopa. Może przeszkadzać niektórym aplikacjom na TV.",
        "Registers the app as a keyboard on the TV so you can type from the laptop. May interfere with some TV apps.",
    ),
    "refresh": ("Odśwież", "Refresh"),
    "about": ("O aplikacji", "About"),
    "about_text": (
        "Sterowanie Google Home z Ubuntu: TV, głośniki i Chromecasty lokalnie, reszta przez wersję web.",
        "Control Google Home from Ubuntu: TV, speakers and Chromecasts locally, everything else via the web app.",
    ),
    "started_on": ("{dev}: {what}", "{dev}: {what}"),
    "group": ("Grupa głośników", "Speaker group"),
    "tv": ("Telewizor", "TV"),
    "speaker": ("Głośnik", "Speaker"),
    "display": ("Wyświetlacz", "Display"),
    "chromecast": ("Chromecast", "Chromecast"),
    "web_loading": ("Ładowanie Google Home…", "Loading Google Home…"),
    "error": ("Błąd: {err}", "Error: {err}"),
}

def _detect_pl() -> bool:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return val.lower().startswith("pl")
    try:
        loc = locale.getlocale()[0] or ""
        return loc.lower().startswith("pl")
    except Exception:
        return False


IS_PL = _detect_pl()


def _(key: str, **kw) -> str:
    pl, en = _STRINGS.get(key, (key, key))
    s = pl if IS_PL else en
    return s.format(**kw) if kw else s
