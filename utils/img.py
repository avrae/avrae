"""
Image processing utilities.
"""

import asyncio
import hashlib
import os
from io import BytesIO

import aiohttp
from PIL import Image, ImageChops

from cogs5e.models.errors import ExternalImportError
from utils import config

TOKEN_SIZE = (256, 256)


def preprocess_url(url):
    """
    Does any necessary changes to the URL before downloading the image.
    Current operations:
    www.dndbeyond.com/avatars -> ${DDB_MEDIA_BUCKET_DOMAIN}/avatars
    """
    return url.replace("www.dndbeyond.com/avatars", f"{config.DDB_MEDIA_S3_BUCKET_DOMAIN}/avatars")


async def generate_token(img_url, is_subscriber=False, token_args=None):
    img_url = preprocess_url(img_url)
    template = "res/template-s.png" if is_subscriber else "res/template-f.png"
    if token_args:
        border = token_args.last("border")
        if border == "plain":
            template = "res/template-f.png"
        elif border == "none":
            template = None

    def process_img(the_img_bytes, template_fp="res/template-f.png"):
        # open the image
        b = BytesIO(the_img_bytes)
        img = Image.open(b).convert("RGBA")

        # crop/resize the token image
        width, height = img.size
        if height >= width:
            box = (0, 0, width, width)
        else:
            box = (width / 2 - height / 2, 0, width / 2 + height / 2, height)
        img = img.resize(TOKEN_SIZE, Image.Resampling.LANCZOS, box)

        # paste mask
        mask_img = Image.open("res/alphatemplate.tif")
        mask_img = ImageChops.darker(mask_img, img.getchannel("A"))
        img.putalpha(mask_img)
        mask_img.close()

        # paste template
        if template_fp:
            template_img = Image.open(template_fp)
            img.paste(template_img, mask=template_img)
            template_img.close()

        # save the image, close files
        out_bytes = BytesIO()
        img.save(out_bytes, "PNG")
        img.close()
        out_bytes.seek(0)
        return out_bytes

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as resp:
                if not 199 < resp.status < 300:
                    raise ExternalImportError(
                        f"I was unable to download the image to tokenize. ({resp.status} {resp.reason})"
                    )
                # get the image type from the content type header
                content_type = resp.headers.get("Content-Type", "")
                if not content_type.startswith("image/"):
                    raise ExternalImportError(f"This does not look like an image file (content type {content_type}).")
                img_bytes = await resp.read()
        processed = await asyncio.get_event_loop().run_in_executor(None, process_img, img_bytes, template)
    except Exception:
        raise

    return processed


async def fetch_monster_image(img_url: str):
    """
    Fetches a monster token image from the given URL, caching it until the bot restarts.

    :returns: A file-like object (file or bytesio) containing the monster token, or a path to the existing cached image.
    :rtype: BytesIO or str
    """
    # ensure cache dir exists
    os.makedirs(".cache/monster-tokens", exist_ok=True)

    sha = hashlib.sha1(img_url.encode()).hexdigest()
    cache_path = f".cache/monster-tokens/{sha}.png"
    if os.path.exists(cache_path):
        return cache_path

    async with aiohttp.ClientSession() as session:
        async with session.get(img_url) as resp:
            if not 199 < resp.status < 300:
                raise ExternalImportError(f"I was unable to retrieve the monster token. ({resp.status} {resp.reason})")
            img_bytes = await resp.read()

    # cache
    with open(cache_path, "wb") as f:
        f.write(img_bytes)

    return BytesIO(img_bytes)
