"""
Image processing utilities.
"""
import asyncio
from io import BytesIO

import aiohttp
from PIL import Image, ImageChops

from cogs5e.models.errors import ExternalImportError

TOKEN_SIZE = (256, 256)


def preprocess_url(url):
    """
    Does any necessary changes to the URL before downloading the image.

    Current operations:
    www.dndbeyond.com/avatars -> media-waterdeep.cursecdn.com/avatars
    """
    return url.replace("www.dndbeyond.com/avatars", "media-waterdeep.cursecdn.com/avatars")


async def generate_token(img_url, is_subscriber=False):
    img_url = preprocess_url(img_url)

    def process_img(the_img_bytes, template_fp='res/template-f.png'):
        # open the images
        b = BytesIO(the_img_bytes)
        img = Image.open(b).convert('RGBA')
        template_img = Image.open(template_fp)
        mask_img = Image.open('res/alphatemplate.tif')

        # crop/resize the token image
        width, height = img.size
        is_taller = height >= width
        if is_taller:
            box = (0, 0, width, width)
        else:
            box = (width / 2 - height / 2, 0, width / 2 + height / 2, height)
        img = img.crop(box)
        img = img.resize(TOKEN_SIZE, Image.ANTIALIAS)

        # paste mask
        mask_img = ImageChops.darker(mask_img, img.getchannel('A'))
        img.putalpha(mask_img)

        # paste template
        img.paste(template_img, mask=template_img)

        # save the image, close files
        out_bytes = BytesIO()
        img.save(out_bytes, "PNG")
        template_img.close()
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
        if is_subscriber:
            template = 'res/template-s.png'
        else:
            template = 'res/template-f.png'
        processed = await asyncio.get_event_loop().run_in_executor(None, process_img, img_bytes, template)
    except Exception:
        raise

    return processed
