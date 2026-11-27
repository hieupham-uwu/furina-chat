from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=4)
def _avatar_font(size):
    for filename in ("segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(filename, size)
        except OSError:
            continue
    return ImageFont.load_default()


def initial_avatar(name, size, color, status_color=None):
    resolution = size * 3
    image = Image.new("RGBA", (resolution, resolution))
    draw = ImageDraw.Draw(image)
    circle = resolution - 12 if status_color else resolution
    draw.ellipse((0, 0, circle - 1, circle - 1), fill=color)

    font = _avatar_font(round(resolution * 0.46))
    letter = (name.strip()[:1] or "?").upper()
    left, top, right, bottom = draw.textbbox((0, 0), letter, font=font)
    draw.text(((circle - left - right) / 2, (circle - top - bottom) / 2), letter, font=font, fill="white")

    if status_color:
        draw.ellipse((resolution - 39, resolution - 39, resolution - 1, resolution - 1), fill="white")
        draw.ellipse((resolution - 33, resolution - 33, resolution - 7, resolution - 7), fill=status_color)
    return ctk.CTkImage(light_image=image, size=(size, size))
