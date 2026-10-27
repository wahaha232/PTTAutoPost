"""Strip image metadata (EXIF/GPS/text chunks) before uploading to a public host."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from ..errors import InputError

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
ANIMATED_FORMATS = {"GIF": "GIF", "WEBP": "WEBP", "PNG": "PNG"}     # APNG is reported as PNG
MAX_ANIMATION_PIXELS = 64 * 1024 * 1024    # frames x width x height (~256 MB as RGBA)


def _strip_animation(im: Image.Image, fmt: str, dst: Path) -> Path:
    """Re-encode every frame with its own duration and the loop count; no metadata is carried over."""
    n = int(getattr(im, "n_frames", 1) or 1)
    w, h = im.size
    if n * w * h > MAX_ANIMATION_PIXELS:
        raise InputError("動畫圖片的影格數與尺寸過大，為避免占用大量記憶體已拒絕處理。", f"{n} frames {w}x{h}")
    frames, durations = [], []
    for frame in ImageSequence.Iterator(im):
        frame.load()                                   # WebP fills info["duration"] only once the frame is loaded
        durations.append(int(frame.info.get("duration", 100) or 100))
        frames.append(frame.convert("RGBA"))
    kwargs = {"save_all": True, "append_images": frames[1:], "duration": durations,
              "loop": int(im.info.get("loop", 0) or 0)}
    if fmt == "GIF":
        kwargs["disposal"] = 2
    elif fmt == "WEBP":
        kwargs["lossless"] = True
        kwargs["exif"] = b""
    frames[0].save(dst, format=fmt, **kwargs)
    return dst


def strip_metadata(src: str | Path, dst: str | Path) -> Path:
    """Write a copy without EXIF/GPS/ICC/text metadata. Pixels are preserved (orientation applied)."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        fmt = (im.format or "").upper()
        if fmt in ANIMATED_FORMATS and getattr(im, "is_animated", False):
            return _strip_animation(im, ANIMATED_FORMATS[fmt], dst)
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
