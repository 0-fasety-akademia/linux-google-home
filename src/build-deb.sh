#!/bin/bash
set -e
cd "$(dirname "$0")"
VER=$(python3 -c "import sys; sys.path.insert(0,'src'); import lgh; print(lgh.VERSION)")
PKG=linux-google-home
R=build/${PKG}_${VER}_all
rm -rf build && mkdir -p $R/DEBIAN $R/usr/lib/$PKG $R/usr/bin $R/usr/share/$PKG/icons \
  $R/usr/share/applications $R/usr/share/icons/hicolor/scalable/apps $R/usr/share/doc/$PKG
cp -r src/main.py src/lgh src/vendor $R/usr/lib/$PKG/
find $R -name __pycache__ -prune -exec rm -rf {} +
cp src/icons/light.svg src/icons/dark.svg $R/usr/share/$PKG/icons/
cp src/icons/light.svg $R/usr/share/icons/hicolor/scalable/apps/$PKG.svg
for s in 48 128 256; do mkdir -p $R/usr/share/icons/hicolor/${s}x${s}/apps; rsvg-convert -w $s src/icons/light.svg -o $R/usr/share/icons/hicolor/${s}x${s}/apps/$PKG.png; done
cat > $R/usr/bin/$PKG <<'S'
#!/bin/sh
export LGH_ICON_DIR=/usr/share/linux-google-home/icons
exec /usr/bin/python3 /usr/lib/linux-google-home/main.py "$@"
S
chmod 755 $R/usr/bin/$PKG
cat > $R/usr/share/applications/io.github.jaro.LinuxGoogleHome.desktop <<'S'
[Desktop Entry]
Type=Application
Name=Linux Google Home
Comment=Google Home on Ubuntu: TV, speakers and Chromecasts
Comment[pl]=Google Home na Ubuntu: TV, głośniki i Chromecasty
Exec=linux-google-home
Icon=linux-google-home
Terminal=false
Categories=Utility;AudioVideo;
Keywords=google;home;nest;chromecast;tv;cast;
StartupNotify=true
StartupWMClass=io.github.jaro.LinuxGoogleHome
X-GNOME-UsesNotifications=true
S
cp README.md $R/usr/share/doc/$PKG/README.md
cp LICENSE $R/usr/share/doc/$PKG/copyright
SIZE=$(du -sk $R/usr | cut -f1)
cat > $R/DEBIAN/control <<S
Package: $PKG
Version: $VER
Section: utils
Priority: optional
Architecture: all
Installed-Size: $SIZE
Maintainer: Jaro <jaroslawguza83@gmail.com>
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, gir1.2-ayatanaappindicator3-0.1, python3-zeroconf (>= 0.128), python3-cryptography, python3-aiofiles, python3-requests, python3-ifaddr
Recommends: gnome-shell-extension-appindicator
Description: Google Home for Ubuntu (TV, speakers, Chromecasts) with tray
 Local control of Google TV (remote over Android TV Remote v2) and Cast
 devices (what's playing, volume, playback), a tray showing what is
 running, plus the Google Home web app for lights, plugs and thermostats.
S
cat > $R/DEBIAN/postinst <<'S'
#!/bin/sh
set -e
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
S
chmod 755 $R/DEBIAN/postinst
dpkg-deb --root-owner-group --build $R >/dev/null
echo build/${PKG}_${VER}_all.deb
