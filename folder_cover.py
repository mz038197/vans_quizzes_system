"""Folder cover pictures: turn an uploaded picture into one small 16:9 WebP."""

import io

from PIL import Image, ImageOps

SIZE = (640, 360)
ACCEPTED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
MAX_PIXELS = 25_000_000  # more than a phone photo; keeps decoding near 100 MB of memory


class CoverError(ValueError):
    """The upload is not a picture we can use. The message is for the Teacher."""


def make_cover(raw):
    """Crop the middle of the picture to 16:9, shrink it to 640×360 and return WebP bytes."""
    if not raw:
        raise CoverError('請選一張圖片')
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in ACCEPTED_FORMATS:
                raise CoverError('只接受 JPG、PNG、WebP 或 GIF 圖片')
            width, height = picture.size
            if width * height > MAX_PIXELS:
                raise CoverError('圖片太大，請換一張比較小的圖片')
            if picture.format == 'JPEG':  # decode at about 2× the cover size: much less memory for big photos
                picture.draft('RGB', (SIZE[0] * 2, SIZE[1] * 2))
            picture = ImageOps.exif_transpose(picture)
            picture = picture.convert('RGBA' if _has_transparency(picture) else 'RGB')
            cover = ImageOps.fit(picture, SIZE, Image.Resampling.LANCZOS)
    except CoverError:
        raise
    except Exception as error:  # Pillow raises many kinds on broken files (bad EXIF gives KeyError, TypeError…)
        raise CoverError('這個檔案不是可以讀的圖片') from error
    out = io.BytesIO()
    cover.save(out, 'WEBP', quality=80, method=4)
    return out.getvalue()


def _has_transparency(picture):
    return picture.mode in ('RGBA', 'LA', 'PA') or (picture.mode == 'P' and 'transparency' in picture.info)
