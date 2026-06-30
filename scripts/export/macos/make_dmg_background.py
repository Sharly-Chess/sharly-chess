"""Generate the DMG window background: a right-pointing arrow on the icon row,
between the app icon (left) and the Applications symlink (right).

The image MUST match the dmgbuild window size in points (dmgbuild sizes the
window to the background image), so this is drawn 1:1 at the same rect as
``window_rect`` in dmg_settings.py.
"""

import sys

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 640, 400

# Vertical centre of the icon row (app + Applications); the arrow sits here.
ROW_Y = 175


def main(out_path: str) -> None:
    image = Image.new('RGBA', (WIDTH, HEIGHT), (245, 245, 247, 255))
    draw = ImageDraw.Draw(image)

    shaft_start = 245
    shaft_end = 358
    head = 24
    colour = (150, 150, 156, 255)

    draw.line([(shaft_start, ROW_Y), (shaft_end, ROW_Y)], fill=colour, width=10)
    draw.polygon(
        [
            (shaft_end, ROW_Y - head),
            (shaft_end + 34, ROW_Y),
            (shaft_end, ROW_Y + head),
        ],
        fill=colour,
    )

    image.save(out_path)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'dmg-background.png')
