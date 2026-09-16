from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def create_icon(destination: Path) -> None:
    image = Image.new("RGBA", (512, 512), (7, 4, 17, 255))
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((70, 70, 442, 442), fill=(83, 47, 255, 155))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(55)))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (64, 64, 448, 448),
        radius=104,
        fill=(20, 12, 48, 245),
        outline=(128, 91, 255, 255),
        width=14,
    )
    draw.ellipse((137, 137, 375, 375), outline=(52, 221, 255, 255), width=26)
    draw.arc((178, 178, 334, 334), 25, 330, fill=(196, 173, 255, 255), width=25)
    draw.ellipse((238, 238, 274, 274), fill=(255, 255, 255, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        destination,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o ícone do aplicativo Oráculo.")
    parser.add_argument("destination", type=Path)
    create_icon(parser.parse_args().destination)


if __name__ == "__main__":
    main()
