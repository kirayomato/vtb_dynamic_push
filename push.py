from win11toast import notify as _notify
import json
from logger import logger
import requests
from config import Config, general_headers
import re


class PushException(Exception):
    pass


prefix = "【消息推送】"
global_config = Config()


def requests_get(url, module_name="未指定", params=None, use_proxy=False):
    try:
        response = requests.get(url, headers=general_headers, params=params, timeout=10)
    except Exception as e:
        logger.error(f"网络错误 url: {url} ,error:{e}", prefix)
        return None
    return response


def requests_post(
    url,
    module_name="未指定",
    params=None,
    data=None,
    json=None,
    use_proxy=False,
):
    try:
        response = requests.post(
            url,
            headers=general_headers,
            params=params,
            data=data,
            json=json,
            timeout=10,
        )
    except Exception as e:
        logger.error(f"网络错误 url: {url} ,error:{e}", prefix)
        return None
    return response


def check_response_is_ok(response=None):
    if response is None:
        return False
    if response.status_code != requests.codes.OK:
        logger.error(
            "status: {}, url: {}".format(response.status_code, response.url), prefix
        )
        return False
    return True


class Push(object):
    pushplus_enable = None
    pushplus_token = None
    serverChan_enable = None
    serverChan_sckey = None
    wechat_enable = None
    wechat_corp_id = None
    wechat_agent_id = None
    wechat_corp_secret = None
    dingtalk_enable = None
    dingtalk_access_token = None

    def __init__(self):
        self.pushplus_enable = global_config.get("push_pushplus", "enable")
        self.pushplus_token = global_config.get("push_pushplus", "pushplus_token")

        self.gotify_enable = global_config.get("push_gotify", "enable")
        self.gotify_url = global_config.get("push_gotify", "gotify_url")
        self.gotify_token = global_config.get("push_gotify", "gotify_token")

        self.serverChan_enable = global_config.get("push_serverChan", "enable")
        self.serverChan_sckey = global_config.get("push_serverChan", "serverChan_SCKEY")

        self.wechat_enable = global_config.get("push_wechat", "enable")
        self.wechat_corp_id = global_config.get("push_wechat", "corp_id")
        self.wechat_agent_id = global_config.get("push_wechat", "agent_id")
        self.wechat_corp_secret = global_config.get("push_wechat", "corp_secret")

        self.dingtalk_enable = global_config.get("push_dingtalk", "enable")
        self.dingtalk_access_token = global_config.get("push_dingtalk", "access_token")

    def common_push(self, title, content, jump_url=None, pic_url=None, priority=6):
        """
        :param title: 推送标题
        :param content: 推送内容
        :param jump_url: 跳转url
        :param pic_url: 图片url
        """
        if content is None:
            content = ""
        if title is None:
            title = ""
        if self.pushplus_enable == "true":
            self._push_plus_push(title, content, jump_url, pic_url)

        if self.gotify_enable == "true":
            self._gotify_push(title, content, jump_url, pic_url, priority)

        if self.serverChan_enable == "true":
            self._server_chan_push(title, content, jump_url)

        if self.wechat_enable == "true":
            access_token = self._get_wechat_access_token()
            self._wechat_push(access_token, title, content, jump_url, pic_url)

        if self.dingtalk_enable == "true":
            self._dingtalk_push(title, content, jump_url, pic_url)

    def _gotify_push(self, title, content, url=None, pic_url=None, priority=6):
        """
        推送(pushplus)
        :title: 标题
        :content: 内容
        :url: 跳转地址
        :pic_url：图片地址
        """
        content += f"\n\n[链接]({url})"
        if pic_url:
            content += f"\n\n![Image]({pic_url})"

        if "更改" in title:
            priority = 2
        elif "转发" in title:
            priority = 4

        body = {
            "title": title,
            "message": content,
            "priority": priority,
            "extras": {
                "client::display": {"contentType": "text/markdown"},
                "client::notification": {"bigImageUrl": pic_url},
            },
        }
        push_url = f"http://{self.gotify_url}/message?token={self.gotify_token}"
        response = requests_post(push_url, json=body)
        if response:
            if response.status_code == 200:
                logger.debug("gotify推送成功", prefix)
            else:
                logger.error(
                    f"gotify推送失败, code:{response.status_code}, msg:{response.text}",
                    prefix,
                )
                raise PushException
        else:
            logger.error("gotify推送失败, 请求失败", prefix)
            raise PushException

    def _push_plus_push(self, title, content, url=None, pic_url=None):
        """
        推送(pushplus)
        :title: 标题
        :content: 内容
        :url: 跳转地址
        :pic_url：图片地址
        """
        content += f"<br/>[链接]({url})"
        if pic_url:
            content += f"<br/><br/><img src='{pic_url}'/>"
        body = {
            "token": f"{self.pushplus_token}",
            "title": f"{title}",
            "content": f"{content}",
            "template": "markdown",
        }
        push_url = "http://www.pushplus.plus/send/"
        response = requests_post(push_url, data=body)
        try:
            result = json.loads(str(response.content, "utf-8"))
        except json.JSONDecodeError as e:
            logger.error(
                f'解析content出错{e}\ncontent:{str(response.content, "utf-8")}', prefix
            )
            raise PushException
        if result["code"] == 200:
            logger.debug("pushplus推送成功", prefix)
        else:
            logger.error(
                f'pushplus推送失败, code:{result["code"]}, msg:{result["msg"]}', prefix
            )
            raise PushException

    def _server_chan_push(self, title, content, url=None, pic_url=None):
        """
        推送(serverChan)
        :title: 标题
        :content: 内容
        :url: 跳转地址
        """
        content += f"\n\n[链接]({url})"
        if pic_url:
            content += f"\n\n![Image]({pic_url})"
        body = {"title": f"{title}", "desp": f"{content}"}
        push_url = f"https://sctapi.ftqq.com/{self.serverChan_sckey}.send"
        response = requests.post(push_url, params=body)
        if check_response_is_ok(response):
            logger.debug("server_chan推送成功", prefix)
        else:
            logger.error("server_chan推送失败", prefix)
            raise PushException

    def _get_wechat_access_token(self):
        access_token = None
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}".format(
            corpid=self.wechat_corp_id, corpsecret=self.wechat_corp_secret
        )
        response = requests_get(url, "推送_wechat_获取access_tokon")
        if check_response_is_ok(response):
            result = json.loads(str(response.content, "utf-8"))
            access_token = result["access_token"]
        return access_token

    def _wechat_push(self, access_token, title, content, url=None, pic_url=None):
        """
        推送(wechat)
        :param access_token: 调用接口凭证
        :param title: 标题
        :param content: 内容
        :param url: 跳转url
        :param pic_url: 图片url
        """
        push_url = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        params = {"access_token": access_token}
        body = {
            "touser": "@all",
            "agentid": self.wechat_agent_id,
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 0,
            "duplicate_check_interval": 1800,
        }

        if pic_url is None:
            body["msgtype"] = "textcard"
            body["textcard"] = {
                "title": title,
                "description": content,
                "url": url,
                "btntxt": "打开详情",
            }
        else:
            body["msgtype"] = "news"
            body["news"] = {
                "articles": [
                    {
                        "title": title,
                        "description": content,
                        "url": url,
                        "picurl": pic_url,
                    }
                ]
            }

        response = requests_post(
            push_url, "推送_wechat", params=params, data=json.dumps(body)
        )
        logger.info(
            "【推送_wechat】{msg}".format(
                msg="成功" if check_response_is_ok(response) else "失败"
            )
        )

    def _dingtalk_push(self, title, content, url=None, pic_url=None):
        """
        推送(dingtalk)
        :param title: 标题
        :param content: 内容
        :param url: 跳转url
        :param pic_url: 图片url
        """
        push_url = "https://oapi.dingtalk.com/robot/send"
        params = {"access_token": self.dingtalk_access_token}
        body = {
            "msgtype": "link",
            "link": {"title": title, "text": content, "messageUrl": url},
        }

        if pic_url is not None:
            body["link"]["picUrl"] = pic_url

        response = requests_post(
            push_url,
            "推送_dingtalk",
            params=params,
            data=json.dumps(body),
        )
        logger.debug(response.json())
        logger.info(
            "【推送_dingtalk】{msg}".format(
                msg="成功" if check_response_is_ok(response) else "失败"
            )
        )


def notify(
    title,
    body,
    on_click=None,
    duration="long",
    scenario="Reminder",
    pic_url=None,
    **kwargs,
):
    if body:
        body = re.sub(r"[\x00-\x1F\x7F]", "", body)
    priority = 6
    push = Push()
    if kwargs.get("audio"):
        priority = 10
    push.common_push(title, body, on_click, pic_url, priority)
    if on_click is None:
        return _notify(
            title=title,
            body=body,
            duration=duration,
            scenario=scenario,
            app_id="vtb_dynamic",
            **kwargs,
        )
    else:
        return _notify(
            title=title,
            body=body,
            duration=duration,
            scenario=scenario,
            button={
                "activationType": "protocol",
                "arguments": on_click,
                "content": "打开页面",
            },
            on_click=on_click,
            app_id="vtb_dynamic",
            **kwargs,
        )
