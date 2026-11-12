# Linux Google Home

A fast, lightweight Google Home companion for Ubuntu. Control your Google TV, Nest speakers and Chromecasts locally, see at a glance what is playing, and switch lights and plugs from a tile panel under the tray icon.

Part of a personal series of Ubuntu desktop apps (Linux iCloud Mail, Linux Apple Music Player, Linux iMessage, …).

Current version: **0.1.8** (2026-11-12)

Created by: JGu  
Supported by Claude

## Features

### Local devices (Wi-Fi, no cloud)

- **Automatic discovery** of every Cast device on the network: Google TV / Chromecast, Nest Audio, Nest Mini, Nest Hub and speaker groups.

- **Live status**: what is playing (app, title, artist or episode, cover art), whether the device is paused, idle or in standby, and its volume.

- **Playback controls**: play/pause, next, previous, stop, mute and volume.

- **Google TV remote** over the Android TV Remote v2 protocol (the same protocol the Google TV phone app uses):

  - power, input, settings, mute

  - D-pad and OK; arrow keys, Enter and Backspace work while the remote is open

  - back, home, play/pause, volume

  - quick launch for YouTube, Netflix, Disney+, Prime Video, Spotify and Max

  - typing text on the TV (optional, "TV keyboard" in the menu)

  - connects on demand and hangs up ~90 s after the last use, so the TV is left alone; "Keep TV remote connected" makes the connection permanent

  - one-time pairing with the 6-character code shown on the TV

### Google Home cloud devices (plugs, lights, cameras, …)

- A **Google Home (web)** tab embeds home.google.com. Sign in once; the session is kept.

- A hidden copy of the page reads every tile (room, name, on/off state) and pushes changes to the app as soon as they happen.

- Devices can be toggled from the tile panel. The app sends a real mouse click, because the page ignores clicks from scripts, and then confirms the new state from the page.

### Tray and tile panel

- Tray icon. Closing the window hides it to the tray; quit from the tray menu.

- **Device tiles** panel drops down under the tray. Open it from the tray menu or with a **middle click** on the tray icon.

  - Media tiles are green while something plays; clicking one pauses or resumes.

  - Cloud device tiles are yellow with a glowing icon when on and grey when off. Clicking one toggles the device, and a spinner shows until the device confirms.

- Refreshes live, plus a full refresh every 2 minutes.

### Desktop integration

- Light/dark theme follows the system. The app icon in the dock, app grid and tray switches with it.

- UI in Polish or English, following the system language.

- Optional notifications when a device starts playing something new.

- Optional start at login, hidden in the tray.

- Version, build date and credits (Created by: JGu, Supported by Claude) in the bottom-left corner of the window.

## Requirements

- Ubuntu 24.04 or newer (Python 3.11+)

- The laptop must be on the same network/subnet as the speakers and TV, because mDNS discovery is not routed across subnets.

- GNOME with the AppIndicator extension (enabled by default on Ubuntu) for the tray icon.

## Install

Download the newest `linux-google-home_<version>_all.deb` from the [Releases page](https://github.com/jgu-linux-apps/linux-google-home/releases/latest) and install it:

```
sudo apt install ./linux-google-home_<version>_all.deb
```

Run it from the app grid ("Linux Google Home") or with `linux-google-home`. Use `linux-google-home --hidden` to start in the tray, or `linux-google-home --version` to print the version.

## Build from source

The source code is in the `src/` folder of this repository; the `.deb` packages are not kept in git but attached to [GitHub Releases](https://github.com/jgu-linux-apps/linux-google-home/releases). Pushing a tag `vX.Y.Z` that matches `VERSION` in `src/src/lgh/__init__.py` makes GitHub Actions (`.github/workflows/release.yml`) build the package and publish the release.

Run inside `src/`:

```
./build-deb.sh        # -> build/linux-google-home_<version>_all.deb
```

Run without installing:

```
python3 src/main.py
python3 test/demo.py   # UI with fake devices, no network needed
```

## Project layout

Paths relative to `src/`:

```
src/main.py            entry point (sets vendor path, GDK_BACKEND=x11)
src/lgh/__init__.py    app id, name, VERSION, BUILD_DATE
src/lgh/app.py         Gtk.Application: lifecycle, config, notifications, autostart
src/lgh/backend.py     Cast (pychromecast) + Android TV Remote (androidtvremote2)
src/lgh/ui.py          main window, device cards, TV remote popover, web tab, pairing
src/lgh/panel.py       tile panel under the tray
src/lgh/tray.py        Ayatana AppIndicator tray icon and menu
src/lgh/webtiles.py    hidden home.google.com page: tile scraping and toggling
src/lgh/theme.py       light/dark detection, theme-aware icons
src/lgh/i18n.py        PL/EN strings
src/icons/             light.svg / dark.svg app icons
src/vendor/            bundled pure-Python libs (pychromecast, casttube, androidtvremote2, protobuf)
test/                  demo with fake devices, web tile test against a replica page
build-deb.sh           .deb packaging
```

## Data and privacy

- Config, TV pairing certificate: `~/.config/linux-google-home/`

- Web session (cookies) for home.google.com: `~/.local/share/linux-google-home/web/`

- Log of device activity and commands sent: `~/.cache/linux-google-home/app.log`

- Speakers and the TV are controlled only on the local network. The only internet traffic is the embedded home.google.com page and cover art loaded from the URLs the speakers report.

## Known limitations

- Speakers, the TV and Chromecasts are discovered on the local network only.

- The TV remote needs a Google TV / Android TV. A TV that only has Chromecast built in gets status, playback and volume, but no remote.

- Cloud devices depend on the layout of home.google.com (checked 2026-11-05). If Google changes the page, the tile reader may need an update.

- A left click on the tray icon always opens the menu (Ubuntu AppIndicator behaviour); use a middle click to open the tiles directly.

- The app runs on X11/XWayland so the panel can be placed under the tray.

## Version history

### 0.1.8 — 2026-11-12

- License: the app is now published under the Freeware License (No Modifications), see `LICENSE`; free to use and share unmodified, modification is not permitted. No other changes in the app.

### 0.1.7 — 2026-11-12

- No changes in the app. The repository now keeps the source code in `src/`, and the `.deb` is published on the GitHub Releases page (built by GitHub Actions for every version tag). README: installation from Releases, cleaned-up code blocks.

### 0.1.6 — 2026-11-07

- **Fix (root cause of Netflix closing on the TV):** the 2-minute status refresh asked the TV for media status over Cast. When the running app (e.g. Netflix on Google TV) doesn't speak the Cast media protocol, pychromecast responds by *launching the Default Media Receiver*. That closed Netflix and showed the blue Cast screen. The app now only queries or controls media over Cast when the running app supports it; otherwise it stays passive or uses the TV remote.

- New log file `~/.cache/linux-google-home/app.log` (rotating, max ~3 MB). It records which app is running on each device and every command the app sends (Cast and remote), so issues like this can be traced.

### 0.1.5 — 2026-11-07

- **Fix:** with the app running, Netflix would not start from the TV's own remote. The Android TV remote connection was permanent and registered the app as a keyboard (IME) on the TV, which can interfere with TV apps.

  - The remote now connects **on demand**: only when you open the remote or send a command, and it hangs up about 90 s after the last use. At startup it only checks pairing and disconnects.

  - The TV keyboard (IME) is **off by default**. Turn it on in the menu ("TV keyboard (text input)") if you want to type on the TV from the laptop. The text field in the remote is shown only then.

  - New menu option **"Keep TV remote connected"** restores the old permanent connection, which shows the current TV app live.

### 0.1.4 — 2026-11-06

- Credits "Created by: JGu" and "Supported by Claude" in the window footer (below the version), in the tile panel and in the About dialog.

### 0.1.3 — 2026-11-05

- Tile panel layout: more space at the top and on the sides, wider gaps between tiles and rooms.

- Panel header now shows the app name ("Linux Google Home"), centered and bold.

### 0.1.2 — 2026-11-05

- New **device tile panel** under the tray: compact, readable tiles grouped into Media and Google Home rooms, replacing the text list in the tray menu.

- Open the panel from the tray menu ("Device tiles") or with a middle click on the tray icon.

- **Fix:** toggling Google Home devices from the tray did nothing. The page ignores script clicks, so the app now sends a real mouse click to the hidden page and confirms the state, showing a spinner while it waits. The tile returns to the real state if the device did not change.

- **Fix:** underscores in device names were shown doubled or eaten in the tray menu (GTK mnemonics). Names are now shown with spaces.

- Icons per device type: light, plug/switch, camera, speaker, TV, display, group.

- The app runs on X11/XWayland (`GDK_BACKEND=x11`) so the panel can be positioned.

### 0.1.1 — 2026-11-05

- Google Home cloud devices (Tapo plugs, Meross lamp, camera, …) in the tray menu, grouped by room with an on/off indicator dot.

- A hidden home.google.com page shares its sign-in with the Google Home (web) tab and reports changes live.

### 0.1.0 — 2026-11-05

- First release.

- Local discovery and control of Cast devices: status, what is playing, cover art, playback controls and volume.

- Google TV remote over Android TV Remote v2 with pairing, D-pad, app launch and text input.

- Google Home (web) tab with a persistent session.

- Tray with a now-playing list and quick actions; close-to-tray.

- Playback notifications, start at login, PL/EN, light/dark theme with matching icons, and the version shown in the window.

- .deb package.

