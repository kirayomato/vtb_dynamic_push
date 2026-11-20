"""动态内容的归一化与比较（纯逻辑，只依赖标准库）。

单独成模块的原因：utils 判定「这条动态的内容变没变」，storage 落库时判定
「要不要追加一个版本行」，两边必须用同一套归一化与比较口径，否则会出现
「内存说没变、表里却在刷版本」这类漂移。本模块无项目内依赖，可被两者共用。

对外只暴露：
    norm_pics(pic_url)   图片 URL 归一化
    ContentDiff           一次比对的结果
    content_diff(old, new)  比对两条动态内容
    same_content(old, new)  内容是否等价（storage 用）
"""

import re
from dataclasses import dataclass

#: 推送正文单侧裁剪长度。notify() 在 200 字处硬截断，「前/后」各留 80 字后
#: 仍能完整露出，长文只丢细节不丢结论。
_PUSH_CLIP = 80

#: 转发正文里由平台自己拼进去的「转发**昵称**的动态：」。
#: 昵称跟着账号走、与动态内容无关，改个名就会被判成作者改了正文，比较时抹掉。
_FORWARD_NAME_RE = re.compile(r"(转发\*\*).*?(\*\*的)")


def norm_pics(pic_url):
    """把 pic_url 归一化成可比较的元组：None/空 -> ()，str/list/tuple -> URL 元组。

    只去掉 ?query 与 #fragment：图床常给同一张图换签名参数或尺寸参数，比原串
    会反复误报"换了图"；路径变化（真换图）仍能被检出。入库时仍存原始值。
    """
    if not pic_url:
        return ()
    items = tuple(pic_url) if isinstance(pic_url, (list, tuple)) else (pic_url,)
    return tuple(
        str(i).split("?", 1)[0].split("#", 1)[0] for i in items if i is not None
    )


def _clip(text, limit=_PUSH_CLIP):
    """压缩空白并截断，供推送正文使用（长换行会吃掉推送的行宽）。"""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return s if len(s) <= limit else s[:limit] + "…"


def _cmp_text(text):
    """比较用的正文：抹掉转发人昵称，其余原样。

    只影响「算不算变了」，不影响展示与入库 —— 正文里该显示谁还是谁。
    """
    return _FORWARD_NAME_RE.sub(r"\1\2", text)


@dataclass(frozen=True)
class ContentDiff:
    """一次内容比对的结果。old/new_pics 是归一化后的 URL 元组。"""

    text_changed: bool
    pics_changed: bool
    old_text: str
    new_text: str
    old_pics: tuple
    new_pics: tuple

    @property
    def changed(self):
        return self.text_changed or self.pics_changed

    @property
    def fields(self):
        names = []
        if self.text_changed:
            names.append("文字")
        if self.pics_changed:
            names.append("图片")
        return "、".join(names) or "无"

    def summary(self):
        """给日志用的可读正文：文字带旧→新，图片报张数变化。

        全文输出，不裁剪 —— 日志要留全量痕迹，便于事后回看作者改了什么。
        """
        parts = []
        if self.text_changed:
            parts.append(
                f"【修改前】\n{self.old_text}\n【修改后】\n{self.new_text}"
            )
        if self.pics_changed:
            parts.append(
                f"图片：{len(self.old_pics)} 张 -> {len(self.new_pics)} 张（地址有变化）"
            )
        return "\n".join(parts)

    def push_summary(self):
        """给推送用的紧凑正文：两侧各裁到 _PUSH_CLIP 字，保证修改前后都露出来。

        notify() 会在 200 字处硬截断正文，而 summary() 是「修改前 + 修改后」
        全文，长文只截得到前半段、连「后」都看不到，故推送另用这一版。
        """
        parts = []
        if self.text_changed:
            parts.append(f"前：{_clip(self.old_text)}\n后：{_clip(self.new_text)}")
        if self.pics_changed:
            parts.append(f"图片：{len(self.old_pics)} -> {len(self.new_pics)} 张")
        return "\n".join(parts)


def content_diff(old, new):
    """比较两条动态内容，返回 ContentDiff。

    old/new 形如 (content, pic_url) 或 DYNAMIC_DICT 里的 (content, pic_url, ts)，
    只取前两项；None 文本按空串处理，避免 None 与 "" 反复互判。
    """
    old = old or ()
    new = new or ()
    old_text = old[0] if old and old[0] is not None else ""
    new_text = new[0] if new and new[0] is not None else ""
    old_pics = norm_pics(old[1] if len(old) > 1 else None)
    new_pics = norm_pics(new[1] if len(new) > 1 else None)
    return ContentDiff(
        text_changed=_cmp_text(str(old_text)) != _cmp_text(str(new_text)),
        pics_changed=old_pics != new_pics,
        old_text=str(old_text),
        new_text=str(new_text),
        old_pics=old_pics,
        new_pics=new_pics,
    )


def same_content(old, new):
    """两条内容是否等价（内容相同且图片归一化后相同）。

    storage 落库时用它决定「追加一个新版本」还是「什么都不写」，
    与 content_diff 同一口径。
    """
    return not content_diff(old, new).changed
