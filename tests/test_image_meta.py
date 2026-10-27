import pytest
from PIL import Image, ImageSequence
from PIL.PngImagePlugin import PngInfo

from src.net.image_meta import strip_metadata


def test_strip_jpeg_removes_exif_and_keeps_pixels(tmp_path):
    src = tmp_path / "a.jpg"
    im = Image.new("RGB", (10, 20), (255, 0, 0))
    exif = Image.Exif()
    exif[271] = "TestPhone"                       # Make
    im.save(src, exif=exif)
    out = strip_metadata(src, tmp_path / "clean.jpg")
    with Image.open(out) as clean:
        assert dict(clean.getexif()) == {}
        assert clean.size == (10, 20)
        r, g, b = clean.convert("RGB").getpixel((0, 0))
        assert r >= 250 and g <= 5 and b <= 5


def test_strip_png_removes_text_metadata(tmp_path):
    src = tmp_path / "a.png"
    info = PngInfo()
    info.add_text("Comment", "secret")
    Image.new("RGBA", (4, 5), (0, 128, 0, 255)).save(src, pnginfo=info)
    out = strip_metadata(src, tmp_path / "clean.png")
    with Image.open(out) as clean:
        assert not clean.info.get("Comment")
        assert clean.size == (4, 5)


def test_strip_gif_keeps_animation(tmp_path):
    src = tmp_path / "a.gif"
    frames = [Image.new("RGB", (3, 3), color) for color in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=50, loop=0)
    out = strip_metadata(src, tmp_path / "clean.gif")
    with Image.open(out) as clean:
        assert clean.n_frames == 2
        assert len(list(ImageSequence.Iterator(clean))) == 2


def _durations(path):
    with Image.open(path) as im:
        out = []
        for frame in ImageSequence.Iterator(im):
            frame.load()
            out.append(frame.info.get("duration"))
        return out, im.n_frames


def test_strip_gif_keeps_per_frame_durations(tmp_path):
    src = tmp_path / "a.gif"
    frames = [Image.new("RGB", (3, 3), c) for c in ((255, 0, 0), (0, 0, 255), (0, 255, 0))]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=[50, 300, 120], loop=0)
    durations, n = _durations(strip_metadata(src, tmp_path / "clean.gif"))
    assert n == 3 and durations == [50, 300, 120]


@pytest.mark.parametrize("fmt,ext", [("WEBP", ".webp"), ("PNG", ".png")])
def test_strip_animated_webp_and_apng_keep_every_frame(tmp_path, fmt, ext):
    src = tmp_path / ("a" + ext)
    frames = [Image.new("RGBA", (4, 4), c) for c in ((255, 0, 0, 255), (0, 0, 255, 255))]
    frames[0].save(src, format=fmt, save_all=True, append_images=frames[1:], duration=[80, 240], loop=0)
    out = strip_metadata(src, tmp_path / ("clean" + ext))
    durations, n = _durations(out)
    assert n == 2 and durations == [80, 240]
    with Image.open(out) as clean:
        clean.seek(1)
        r, g, b, _a = clean.convert("RGBA").getpixel((0, 0))
        assert r <= 5 and g <= 5 and b >= 250                      # second frame, not a copy of the first


def test_huge_animation_is_refused_instead_of_decoded(tmp_path, monkeypatch):
    from src.errors import InputError
    from src.net import image_meta
    src = tmp_path / "a.gif"
    frames = [Image.new("RGB", (10, 10), c) for c in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=50, loop=0)
    monkeypatch.setattr(image_meta, "MAX_ANIMATION_PIXELS", 150)
    with pytest.raises(InputError):
        strip_metadata(src, tmp_path / "clean.gif")
