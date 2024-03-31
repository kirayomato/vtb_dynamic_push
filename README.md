# vtb_dynamic_push
## 简介

定时检测指定B站的动态更新，直播开播和微博更新。如果发生变化进行推送

本项目基于[nfe-w](https://github.com/nfe-w)的[bili_dynamic_push](https://github.com/nfe-w/bili_dynamic_push)和[weibo_dynamic_push](https://github.com/nfe-w/weibo_dynamic_push/)进行开发，推荐使用本项目前先阅读原项目有关介绍

本项目在原项目的基础上增加了多项功能

1. 支持填写cookies，获取仅粉丝可见内容，且在cookies失效时进行提示

    检测微博cookies是否有效的原理为尝试获取一个微博全为粉丝可见的账号的微博，如果能成功获取到微博则说明cookies有效，需要先关注对应账号

    B站cookies目前没有作用，即使填写了也无法获取充电专属内容

2. Windows弹窗推送，更加方便桌面用户使用，效果如图

    ![推送示例](example.png)

    点击消息或下方按钮即可打开对应动态/直播间链接

    推送通知使用`win11toast`库实现，在Windows10上不保证能正常使用


3. 微博和动态检测功能增加头像、签名变化的检测。直播检测功能增加直播间标题、封面变化的检测。

## 运行环境

- [Python 3](https://www.python.org/)

## 使用教程

#### 0. 下载
在[Releases](https://github.com/kirayomato/vtb_dynamic_push/releases)下载最新版本代码压缩包并解压到一个文件夹中

#### 1. 填写config.ini配置信息

`weibo`下的参数
- `enable_dynamic_push`是否启用微博推送

- `uid_list`为需要扫描的up主uid列表，使用英文逗号分隔，必填
- `intervals_second`为扫描间隔秒数，不建议过于频繁，必填
- `enable_cookies_check`是否启用cookies检测功能，默认关闭
- `cookies_check_uid`检测cookies使用的账号，默认为[Hitomi浅川瞳poi
](https://weibo.com/u/1794972577)。要求公开微博小于5条，公开+仅粉丝可见微博大于5条。

`bili`下的参数
- `enable_dynamic_push`是否启用微博推送

- `enable_living_push`是否启用开播推送

- `dynamic_uid_list`为需要扫描动态的up主uid列表，使用英文逗号分隔，必填

- `live_uid_list`为需要扫描直播的up主uid列表，使用英文逗号分隔，必填。注意是uid而不是直播间号
- `special_list`特别关注列表，在其中的up主开播时推送将会增加响铃，需要同时填写在`live_uid_list`中
- `intervals_second`为扫描间隔秒数，不建议过于频繁，必填

以下推送渠道继承自原项目未进行修改，应该能够正常使用，但是因为我用不上所以没有测试

`push_serverChan`下的参数

- `enable`是否启用serverChan推送
- `serverChan_SCKEY`如果启用该推送，则必填，参考 http://sc.ftqq.com/3.version

`push_serverChan_turbo`下的参数

- `enable`是否启用serverChan_Turbo推送
- `serverChan_SendKey`如果启用该推送，则必填，参考 https://sct.ftqq.com

`push_wechat`下的参数

- `enable`是否启用微信推送
- `corp_id`企业id，如果启用该推送，则必填
- `agent_id`应用id，如果启用该推送，则必填
- `corp_secret`应用Secret，如果启用该推送，则必填

`push_dingtalk`下的参数

- `enable`是否启用钉钉bot推送
- `access_token`机器人access_token，如果启用该推送，则必填

#### 2.填写cookies

在`BiliCookies.json`文件中填写b站cookies，在`WeiboCookies.json`文件中填写微博cookies

微博cookies需要在 https://m.weibo.cn/ 中登陆进行获取

cookies要求为json格式，结构如下
```
{
    "name": xxx,
    "value": xxx
}
```
推荐使用[EditThisCookie](https://chromewebstore.google.com/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg)插件，导出后全部复制进去即可
#### 3.安装第三方库

`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/`

#### 4.启动脚本

`python main.py`

## 声明

- 本仓库发布的`vtb_dynamic_push`项目中涉及的任何脚本，仅用于测试和学习研究，禁止用于商业用途
- `kirayomato` 对任何脚本问题概不负责，包括但不限于由任何脚本错误导致的任何损失或损害
- 以任何方式查看此项目的人或直接或间接使用`vtb_dynamic_push`项目的任何脚本的使用者都应仔细阅读此声明
- `kirayomato` 保留随时更改或补充此免责声明的权利。一旦使用并复制了任何相关脚本或`vtb_dynamic_push`项目，则视为已接受此免责声明
- 本项目遵循`MIT LICENSE`协议，如果本声明与`MIT LICENSE`协议有冲突之处，以本声明为准
