import json
from os.path import realpath, exists
import requests
from requests.exceptions import RequestException
from logger import logger
from push import notify
from pathlib import Path

proxies = {
    "http": "",
    "https": "",
}


def get_icon(headers, image_url, prefix, platform, uname, _type):
    image_url = image_url.split("?")[0]
    name = image_url.split("/")[-1]
    dir_path = Path("image") / platform / uname / _type
    dir_path.mkdir(parents=True, exist_ok=True)
    icon = str(dir_path / name)
    if exists(icon):
        return realpath(icon)
    try:
        r = requests.get(image_url, headers=headers, proxies=proxies, timeout=10)
    except RequestException as e:
        logger.warning(f"网络错误, error:{e}, url: {image_url}", prefix)
        return None
    if r.status_code != 200:
        return None
    with open(icon, "wb") as f:
        f.write(r.content)
    # img = Image.open(icon)
    # img = img.resize((64, 64))
    # img.save(f'icon/{uid}.ico')
    return realpath(icon)


def check_diff(
    ori,
    _dict,
    info_name,
    img,
    uid,
    uname,
    prefix,
    color,
    on_click,
    icon_path,
    pic=None,
    image=None,
):
    if ori != _dict[uid]:
        msg = f"【{uname}】更改了{info_name}"
        if img:
            content = ""
        else:
            content = f"【{_dict[uid]}】 -> 【{ori}】"
            msg += ": " + content

        logger.info(msg, prefix, color)

        notify(
            f"【{uname}】更改了{info_name}",
            content,
            icon=icon_path,
            on_click=on_click,
            pic_url=pic,
            image=image,
        )
        _dict[uid] = ori


def get_image(pic_url, headers, prefix, platform, uname, _type):
    image = None
    if pic_url:
        if isinstance(pic_url, list):
            for url in reversed(pic_url):
                opus_path = get_icon(headers, url, prefix, platform, uname, _type)
        else:
            opus_path = get_icon(headers, pic_url, prefix, platform, uname, _type)
        if opus_path is None:
            logger.warning(f"图片下载失败, url: {pic_url}", prefix)
        else:
            image = {"src": opus_path, "placement": "hero"}
    return image
