# vtb_dynamic_push
## 简介

定时检测指定B站的动态更新，直播开播和微博更新。如果发生变化进行推送


## 运行环境

- [Python 3](https://www.python.org/)

## 使用教程

#### 1. 填写config.ini配置信息

`weibo`下的参数
- `enable_dynamic_push`是否启用微博推送

- `uid_list`为需要扫描的up主uid列表，使用英文逗号分隔，必填
- `intervals_second`为扫描间隔秒数，不建议过于频繁，必填

`bili`下的参数
- `enable_dynamic_push`是否启用微博推送

- `enable_living_push`是否启用开播推送

- `dynamic_uid_list`为需要扫描动态的up主uid列表，使用英文逗号分隔，必填

- `live_uid_list`为需要扫描直播的up主uid列表，使用英文逗号分隔，必填
- `intervals_second`为扫描间隔秒数，不建议过于频繁，必填



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

#### 2.安装第三方库

`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/`

#### 3.启动脚本

`python3 main.py`
