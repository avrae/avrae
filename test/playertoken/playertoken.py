import asyncio
from io import BytesIO

import aiohttp
from PIL import Image

IMG_URL = "https://cdn.discordapp.com/attachments/263128686004404225/426254460373827604/nicholas-kole-juro.jpg"
TEMPLATE = Image.open('./template.png')
TRANSPARENCY_TEMPLATE = Image.open('./alphatemplate.tif')


def color(src, target):
    num_pixels = src.size[0] * src.size[1]
    colors = src.getcolors(num_pixels)
    rgb = sum(c[0] * c[1][0] for c in colors), sum(c[0] * c[1][1] for c in colors), sum(
        c[0] * c[1][2] for c in colors)
    rgb = rgb[0] / num_pixels, rgb[1] / num_pixels, rgb[2] / num_pixels
    bands = target.split()
    for i, v in enumerate(rgb):
        out = bands[i].point(lambda p: int(p * v / 255))
        bands[i].paste(out)
    return Image.merge(target.mode, bands)


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(IMG_URL) as resp:
            img_bytes = await resp.read()
    b = BytesIO(img_bytes)
    img = Image.open(b)
    width, height = img.size
    is_taller = height >= width
    if is_taller:
        box = (0, 0, width, width)
    else:
        box = (width / 2 - height / 2, 0, width / 2 + height / 2, height)
    img = img.crop(box)
    img = img.resize((260, 260))

    colored_template = color(img, TEMPLATE)
    img.paste(colored_template, mask=colored_template)
    img.putalpha(TRANSPARENCY_TEMPLATE)

    out_bytes = BytesIO()
    img.save(out_bytes)


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
