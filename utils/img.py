"""
Image processing utilities.
"""
import asyncio
from io import BytesIO

import aiohttp
import numpy
from PIL import Image

from cogs5e.models.errors import ExternalImportError


def preprocess_url(url):
    """
    Does any necessary changes to the URL before downloading the image.

    Current operations:
    www.dndbeyond.com/avatars -> media-waterdeep.cursecdn.com/avatars
    """
    return url.replace("www.dndbeyond.com/avatars", "media-waterdeep.cursecdn.com/avatars")


async def generate_token(img_url, color_override=None):
    img_url = preprocess_url(img_url)

    def process_img(img_bytes, color_override, image_format=None):
        # open the images
        b = BytesIO(img_bytes)
        img = Image.open(b)
        template = Image.open('res/template.png')
        transparency_template = Image.open('res/alphatemplate.tif')

        # crop/resize the token image
        width, height = img.size
        is_taller = height >= width
        if is_taller:
            box = (0, 0, width, width)
        else:
            box = (width / 2 - height / 2, 0, width / 2 + height / 2, height)
        img = img.crop(box)
        img = img.resize((260, 260), Image.ANTIALIAS)

        # find average color
        if color_override is None:
            num_pixels = img.size[0] * img.size[1]
            colors = img.getcolors(num_pixels)
            rgb = sum(c[0] * c[1][0] for c in colors), sum(c[0] * c[1][1] for c in colors), sum(
                c[0] * c[1][2] for c in colors)
            rgb = rgb[0] / num_pixels, rgb[1] / num_pixels, rgb[2] / num_pixels
        else:
            rgb = ((color_override >> 16) & 255, (color_override >> 8) & 255, color_override & 255)

        # color the circle
        bands = template.split()
        for i, v in enumerate(rgb):
            out = bands[i].point(lambda p: int(p * v / 255))
            bands[i].paste(out)

        # alpha blending
        try:
            alpha = img.getchannel("A")
            alpha_pixels = numpy.array(alpha)
            template_pixels = numpy.asarray(transparency_template)
            for r, row in enumerate(template_pixels):
                for c, col in enumerate(row):
                    alpha_pixels[r][c] = min(alpha_pixels[r][c], col)
            out = Image.fromarray(alpha_pixels, "L")
            img.putalpha(out)
        except ValueError:
            img.putalpha(transparency_template)

        colored_template = Image.merge(template.mode, bands)
        img.paste(colored_template, mask=colored_template)

        # save the image, close files
        out_bytes = BytesIO()
        img.save(out_bytes, "PNG")
        template.close()
        transparency_template.close()
        img.close()
        out_bytes.seek(0)
        return out_bytes

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as resp:
                if not 199 < resp.status < 300:
                    raise ExternalImportError(f"I was unable to download the image to tokenize. "
                                              f"({resp.status} {resp.reason})")
                # get the image type from the content type header
                content_type = resp.headers.get("Content-Type", '')
                if not content_type.startswith('image/'):
                    raise ExternalImportError(f"This does not look like an image file (content type {content_type}).")
                img_bytes = await resp.read()
        processed = await asyncio.get_event_loop().run_in_executor(None, process_img, img_bytes, color_override)
    except Exception:
        raise

    return processed
