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
