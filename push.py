from win11toast import notify as _notify
import json
from logger import logger
import random
from colorama import Fore
import requests
prefix = '【消息推送】'
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1664.3 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_2) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1309.0 Safari/537.17",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1664.3 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1944.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.1 Safari/537.36",
    "Mozilla/5.0 (Windows NT 4.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.3319.102 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2309.372 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2117.157 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1866.237 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2224.3 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.16 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.60 Safari/537.17",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.62 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.101 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1623.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.90 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1468.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1464.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1467.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.14 (KHTML, like Gecko) Chrome/24.0.1292.0 Safari/537.14",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1500.55 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.2 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.17 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1667.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2226.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.4; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2214.93 Safari/537.36",
]


def get_random_useragent():
    return random.choice(USER_AGENTS)


def requests_get(url, module_name='未指定', headers=None, params=None, use_proxy=False):
    if headers is None:
        headers = {}
    headers = dict({
        'User-Agent': get_random_useragent()
    }, **headers)
    try:
        response = requests.get(url, headers=headers,
                                params=params, timeout=10)
    except Exception as e:
        logger.error(f"网络错误 url:{url},error:{e}", prefix)
        return None
    return response


def requests_post(url, module_name='未指定', headers=None, params=None, data=None, json=None, use_proxy=False):
    if headers is None:
        headers = {}
    headers = dict({
        'User-Agent': get_random_useragent()
    }, **headers)
    try:
        response = requests.post(url, headers=headers, params=params,
                                 data=data, json=json, timeout=10)
    except Exception as e:
        logger.error(f"网络错误 url:{url},error:{e}", prefix)
        return None
    return response


def check_response_is_ok(response=None):
    if response is None:
        return False
    if response.status_code != requests.codes.OK:
        logger.error('status: {}, url: {}'.format(
            response.status_code, response.url), prefix)
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
        from config import global_config
        self.pushplus_enable = global_config.get_raw(
            'push_pushplus', 'enable')
        self.pushplus_token = global_config.get_raw(
            'push_pushplus', 'pushplus_token')

        self.gotify_enable = global_config.get_raw(
            'push_gotify', 'enable')
        self.gotify_url = global_config.get_raw(
            'push_gotify', 'gotify_url')
        self.gotify_token = global_config.get_raw(
            'push_gotify', 'gotify_token')

        self.serverChan_enable = global_config.get_raw(
            'push_serverChan', 'enable')
        self.serverChan_sckey = global_config.get_raw(
            'push_serverChan', 'serverChan_SCKEY')

        self.wechat_enable = global_config.get_raw('push_wechat', 'enable')
        self.wechat_corp_id = global_config.get_raw('push_wechat', 'corp_id')
        self.wechat_agent_id = global_config.get_raw('push_wechat', 'agent_id')
        self.wechat_corp_secret = global_config.get_raw(
            'push_wechat', 'corp_secret')

        self.dingtalk_enable = global_config.get_raw('push_dingtalk', 'enable')
        self.dingtalk_access_token = global_config.get_raw(
            'push_dingtalk', 'access_token')

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
        if self.pushplus_enable == 'true':
            self._push_plus_push(title, content, jump_url, pic_url)

        if self.gotify_enable == 'true':
            self._gotify_push(title, content, jump_url, pic_url, priority)

        if self.serverChan_enable == 'true':
            self._server_chan_push(title, content, jump_url)

        if self.wechat_enable == 'true':
            access_token = self._get_wechat_access_token()
            self._wechat_push(access_token, title, content, jump_url, pic_url)

        if self.dingtalk_enable == 'true':
            self._dingtalk_push(title, content, jump_url, pic_url)

    def _gotify_push(self, title, content, url=None, pic_url=None, priority=6):
        """
        推送(pushplus)
        :title: 标题
        :content: 内容
        :url: 跳转地址
        :pic_url：图片地址
        """
        content += f'\n\n[链接]({url})'
        if pic_url:
            content += f"\n\n![Image]({pic_url})"

        if '更改' in title:
            priority = 2
        elif '转发' in title:
            priority = 4

        body = {
            "title": title,
            "message": content,
            "priority": priority,
            "extras": {
                "client::display": {
                    "contentType": "text/markdown"
                },
                "client::notification": {
                    "bigImageUrl": pic_url
                }
            }
        }
        push_url = f'http://{self.gotify_url}/message?token={self.gotify_token}'
        response = requests_post(push_url, json=body)
        if response:
            if response.status_code == 200:
                logger.debug('gotify推送成功', prefix)
            else:
                logger.error(
                    f'gotify推送失败, code:{response.status_code}, msg:{response.text}', prefix)
        else:
            logger.error('gotify推送失败, 请求失败', prefix)

    def _push_plus_push(self, title, content, url=None, pic_url=None):
        """
        推送(pushplus)
        :title: 标题
        :content: 内容
        :url: 跳转地址
        :pic_url：图片地址
        """
        content += f'<br/>[链接]({url})'
        if pic_url:
            content += f"<br/><br/><img src='{pic_url}'/>"
        body = {
            "token": f"{self.pushplus_token}",
            "title": f"{title}",
            "content": f"{content}",
            "template": 'markdown'
        }
        push_url = 'http://www.pushplus.plus/send/'
        response = requests_post(push_url, data=body)
        try:
            result = json.loads(str(response.content, 'utf-8'))
        except json.JSONDecodeError as e:
            logger.error(
                f'解析content出错{e}\ncontent:{str(response.content, "utf-8")}', prefix)
            return
        if result['code'] == 200:
            logger.debug('pushplus推送成功', prefix)
        else:
            logger.error(
                f'pushplus推送失败, code:{result["code"]}, msg:{result["msg"]}', prefix)

    def _server_chan_push(self, title, content, url=None, pic_url=None):
        """
        推送(serverChan)
        :title: 标题
        :content: 内容
        :url: 跳转地址
        """
        content += f'\n\n[链接]({url})'
        if pic_url:
            content += f"\n\n![Image]({pic_url})"
        body = {
            "title": f"{title}",
            "desp": f"{content}"
        }
        push_url = f'https://sctapi.ftqq.com/{self.serverChan_sckey}.send'
        response = requests.post(push_url, params=body)
        if check_response_is_ok(response):
            logger.debug('server_chan推送成功', prefix)
        else:
            logger.error('server_chan推送失败', prefix)

    def _get_wechat_access_token(self):
        access_token = None
        url = 'https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}'.format(
            corpid=self.wechat_corp_id, corpsecret=self.wechat_corp_secret)
        response = requests_get(url, '推送_wechat_获取access_tokon')
        if check_response_is_ok(response):
            result = json.loads(str(response.content, 'utf-8'))
            access_token = result['access_token']
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
        push_url = 'https://qyapi.weixin.qq.com/cgi-bin/message/send'
        params = {
            "access_token": access_token
        }
        body = {
            "touser": "@all",
            "agentid": self.wechat_agent_id,
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 0,
            "duplicate_check_interval": 1800
        }

        if pic_url is None:
            body["msgtype"] = "textcard"
            body["textcard"] = {
                "title": title,
                "description": content,
                "url": url,
                "btntxt": "打开详情"
            }
        else:
            body["msgtype"] = "news"
            body["news"] = {
                "articles": [
                    {
                        "title": title,
                        "description": content,
                        "url": url,
                        "picurl": pic_url
                    }
                ]
            }

        response = requests_post(
            push_url, '推送_wechat', params=params, data=json.dumps(body))
        logger.info('【推送_wechat】{msg}'.format(
            msg='成功' if check_response_is_ok(response) else '失败'))

    def _dingtalk_push(self, title, content, url=None, pic_url=None):
        """
        推送(dingtalk)
        :param title: 标题
        :param content: 内容
        :param url: 跳转url
        :param pic_url: 图片url
        """
        push_url = 'https://oapi.dingtalk.com/robot/send'
        headers = {
            "Content-Type": "application/json"
        }
        params = {
            "access_token": self.dingtalk_access_token
        }
        body = {
            "msgtype": "link",
            "link": {
                "title": title,
                "text": content,
                "messageUrl": url
            }
        }

        if pic_url is not None:
            body["link"]["picUrl"] = pic_url

        response = requests_post(
            push_url, '推送_dingtalk', headers=headers, params=params, data=json.dumps(body))
        logger.debug(response.json())
        logger.info('【推送_dingtalk】{msg}'.format(
            msg='成功' if check_response_is_ok(response) else '失败'))


def notify(title, body, on_click=None, duration='long', scenario='Reminder', pic_url=None, **kwargs):
    priority = 6
    push = Push()
    if kwargs.get('audio'):
        priority = 10
    push.common_push(title, body, on_click, pic_url, priority)
    if on_click is None:
        return _notify(title=title, body=body, duration=duration, scenario=scenario,
                       app_id='vtb_dynamic', **kwargs)
    else:
        return _notify(title=title, body=body, duration=duration, scenario=scenario,
                       button={'activationType': 'protocol',
                               'arguments': on_click, 'content': '打开页面'},
                       on_click=on_click, app_id='vtb_dynamic', **kwargs)
