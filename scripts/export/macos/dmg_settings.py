"""dmgbuild settings for the styled "drag to Applications" DMG.

Invoked by build_and_notarize.sh:

    dmgbuild -s dmg_settings.py \
        -D app=<SharlyChess.app> -D licenses=<Licenses dir> \
        -D background=<png> -D volicon=<icns> "<Volume>" <out.dmg>

dmgbuild writes the .DS_Store directly, so the layout works headless (CI) —
no Finder/AppleScript required.
"""

import os.path

# `defines` is injected by dmgbuild from the -D flags.
app_path = defines['app']  # noqa: F821
app_name = os.path.basename(app_path)
licenses_path = defines.get('licenses')  # noqa: F821
background_path = defines.get('background')  # noqa: F821
vol_icon = defines.get('volicon')  # noqa: F821

# Contents of the DMG window.
files = [app_path]
if licenses_path:
    files.append(licenses_path)

# Drag-install symlink.
symlinks = {'Applications': '/Applications'}

# Volume icon badge.
if vol_icon:
    badge_icon = vol_icon

# Window appearance.
background = background_path
default_view = 'icon-view'
show_icon_preview = False
window_rect = ((200, 200), (640, 400))
icon_size = 128
text_size = 12

# Icon positions (points, origin top-left of the window content).
icon_locations = {
    app_name: (160, 175),
    'Applications': (480, 175),
}
# Keep the window compact (just app -> arrow -> Applications); place the
# Licenses folder below the fold so it stays in the DMG but out of the way
# (reachable by scrolling).
if licenses_path:
    icon_locations[os.path.basename(licenses_path)] = (320, 560)
