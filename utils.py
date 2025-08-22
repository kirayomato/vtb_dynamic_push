import json
from os.path import realpath, exists
import requests
from requests.exceptions import RequestException
from logger import logger
from push import notify

proxies = {
    "http": "",
    "https": "",
}


def get_icon(headers, face, prefix, path=""):
    face = face.split("?")[0]
    name = face.split("/")[-1]
    icon = f"icon/{path}{name}"
    if exists(icon):
        return realpath(icon)
    try:
        r = requests.get(face, headers=headers, proxies=proxies, timeout=10)
    except RequestException as e:
        logger.warning(f"网络错误, error:{e}, url: {face}", prefix)
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


def get_image(pic_url, headers, prefix):
    image = None
    if pic_url:
        if isinstance(pic_url, list):
            for i in reversed(pic_url):
                opus_path = get_icon(headers, i, prefix, "opus/")
        else:
            opus_path = get_icon(headers, pic_url, prefix, "opus/")
        if opus_path is None:
            logger.warning(f"图片下载失败, url: {pic_url}", prefix)
        else:
            image = {"src": opus_path, "placement": "hero"}
    return image
