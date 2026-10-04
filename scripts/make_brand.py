"""Generate the brand images in custom_components/watch_time_tracker/brand/.

Run: python scripts/make_brand.py  (needs Pillow, which Home Assistant installs)
"""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = Path(__file__).parent.parent / "custom_components/watch_time_tracker/brand"
BLUE = (3, 169, 244, 255)
WHITE = (255, 255, 255, 255)


def icon(size: int) -> Image.Image:
    """A TV with a clock on its screen."""
    s = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=48 * s, fill=BLUE)
    # TV body and stand
    d.rounded_rectangle(
        (36 * s, 56 * s, 220 * s, 180 * s),
        radius=14 * s,
        outline=WHITE,
        width=round(12 * s),
    )
    d.line((100 * s, 210 * s, 156 * s, 210 * s), fill=WHITE, width=round(12 * s))
    d.line((128 * s, 180 * s, 128 * s, 210 * s), fill=WHITE, width=round(12 * s))
    # Clock
    d.ellipse((92 * s, 82 * s, 164 * s, 154 * s), outline=WHITE, width=round(9 * s))
    d.line((128 * s, 118 * s, 128 * s, 96 * s), fill=WHITE, width=round(8 * s))
    d.line((128 * s, 118 * s, 146 * s, 118 * s), fill=WHITE, width=round(8 * s))
    return img


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        icon(size).save(BRAND / name)
    # Logo: same mark (HA falls back to the icon shape for square logos).
    icon(256).save(BRAND / "logo.png")
    icon(512).save(BRAND / "logo@2x.png")


if __name__ == "__main__":
    main()
