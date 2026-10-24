"""Strip image metadata (EXIF/GPS/text chunks) before uploading to a public host."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}


def strip_metadata(src: str | Path, dst: str | Path) -> Path:
    """Write a copy without EXIF/GPS/ICC/text metadata. Pixels are preserved (orientation applied)."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        fmt = (im.format or "").upper()
        if fmt == "GIF" and getattr(im, "is_animated", False):
            frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(im)]
            frames[0].save(dst, format="GIF", save_all=True, append_images=frames[1:],
                           loop=int(im.info.get("loop", 0)), duration=im.info.get("duration", 100),
                           disposal=2)
            return dst
        oriented = ImageOps.exif_transpose(im)
        mode = "RGBA" if oriented.mode in ("P", "PA") else oriented.mode
        clean = oriented.convert(mode) if mode != oriented.mode else oriented.copy()
        clean.info.clear()
        kwargs = {}
        if fmt in ("JPEG", "PNG", "WEBP"):
            kwargs["exif"] = b""
        if fmt == "JPEG":
            kwargs["quality"] = 95
        clean.save(dst, format=fmt, **kwargs)
    return dst
