# 米游社每日签到 · 青龙脚本（miys-qinglong）

一个可以直接放进 **青龙面板** 运行的米游社签到脚本。支持米游社游戏社区签到、
云游戏签到和米游币社区任务，单文件、只依赖 `requests`，结果可走青龙通知或常见
推送渠道。

> 接口与流程参考了 [MiyoQian（米游签）](https://github.com/Marchen-orz/MiyoQian)
> 和 [mys-signin-helper（米游社签到助手）](https://github.com/mxf133/mys-signin-helper)
> 两个项目，按青龙脚本的使用习惯重写为单文件实现。

---

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `miys_signin.py` | 主脚本，放进青龙脚本目录即可运行 |
| `README.md` | 本说明 |
| `requirements.txt` | 依赖清单（只有 `requests`） |

---

## 功能

- **游戏社区签到**：原神、崩坏：星穹铁道、绝区零、崩坏3、未定事件簿、崩坏学园2
  （默认开启前三款），自动处理「今日已签到」「首次绑定」「-5003」等情况。
- **云游戏签到**：云原神、云绝区零，使用 `x-rpc-combo_token`，统计本次到账时长。
- **米游币社区任务**：社区签到、看帖、点赞（可自动取消）、分享，按任务进度自动
  决定执行次数。
- **多账号**：`&` / 换行分隔，或使用 JSON 做更细的按账号配置。
- **登录态刷新**：cookie 里缺少或过期 `cookie_token` / `ltoken` 时，可用 `stoken` 自动补齐。
- **可选验证码**：支持打码狗和自定义打码接口，用于游戏签到 / 社区签到 / 点赞。
- **结果推送**：优先使用青龙自带 `notify.py`，否则回退到 PushPlus、Server酱、
  Telegram、Bark、钉钉、飞书、企业微信、Gotify、自定义 Webhook。
- **适合定时任务**：请求间随机延时、失败重试、单账号异常不影响其他账号。

---

## 快速开始（青龙面板）

### 1. 放脚本

青龙面板 → **脚本管理** → 新建脚本 `miys_signin.py`，把本目录的
`miys_signin.py` 内容粘贴进去；或者直接把文件上传到容器的脚本目录：

```
/ql/data/scripts/miys_signin.py
```

> 部分旧版本青龙的脚本目录是 `/ql/scripts/`，以面板实际显示为准。

### 2. 装依赖

青龙面板 → **依赖管理** → **Python3** → 新建依赖，名称填 `requests`。

大多数青龙镜像已经自带 `requests`，如果脚本能直接跑就不用装。

### 3. 配环境变量

青龙面板 → **环境变量** → 新建：

| 名称 | 值 |
| --- | --- |
| `MYS_COOKIE` | 你的米游社 cookie（见下方[获取 cookie](#获取-cookie)） |

保存后先 **手动运行一次** 脚本，确认日志里能看到签到结果。

### 4. 建定时任务

青龙面板 → **定时任务** → 新建任务：

- 名称：`米游社签到`
- 命令：`task miys_signin.py`（等价：`python3 miys_signin.py`）
- 定时规则：`10 8 * * *`（每天 08:10，可按需修改）

保存后点「运行」测试一次，日志正常即可。

> 建议把分钟数错开（比如 `17 8 * * *`），避免和其他脚本挤在同一时刻。

### 5. 本地试跑（可选）

```bash
pip3 install requests

# 只检查配置，不发请求
MYS_COOKIE='ltuid=123456789; cookie_token=xxxx' python3 miys_signin.py --dry-run

# 正式运行
MYS_COOKIE='ltuid=123456789; cookie_token=xxxx' python3 miys_signin.py
```

---

## 获取 cookie

1. 浏览器登录 [米游社](https://www.miyoushe.com/)，按 `F12` 打开开发者工具。
2. 切到 **Network（网络）**，刷新页面，点任意一个发往 `miyoushe.com` /
   `mihoyo.com` 的请求。
3. 在 **Request Headers（请求标头）** 里找到 `Cookie:`，整段复制。

脚本需要的主要字段：

| 字段 | 用途 |
| --- | --- |
| `ltuid` / `ltuid_v2` / `account_id` | 账号 UID |
| `cookie_token` | 游戏社区签到（`event/luna`）的登录凭证 |
| `ltoken` / `ltoken_v2` | 米游社社区接口的登录凭证 |
| `mid` / `account_mid_v2` / `ltmid_v2` | v2 stoken 刷新时需要 |

把整段 cookie 直接填进 `MYS_COOKIE` 即可，脚本会自动解析。**不要**只复制
`cookie_token` 一个字段。

> 如果面板不方便输入换行，多账号请用 `&` 分隔；也可以使用 JSON 写法。

---

## 环境变量

### 账号与基础

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYS_COOKIE` | 无（必填） | 米游社 cookie，多账号用 `&` 或换行分隔；支持 `cookie#stoken` 写法 |
| `MYS_STOKEN` | 空 | 可选的 stoken。数量与账号一致时按顺序配对，只有一个时给第一个账号 |
| `MYS_ACCOUNTS` | 空 | JSON 数组写法，见[多账号与 JSON 配置](#多账号与-json-配置) |
| 兼容别名 | — | `MYS_COOKIE` 同时兼容 `MIYOUSHE_COOKIE`、`MYS_COOKIES`、`MIYOUSHE_COOKIES` |

### 游戏签到

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYS_GAME_CHECKIN` | `true` | 游戏社区签到总开关（兼容 `MYS_CHECKIN`） |
| `MYS_SIGN_GAMES` | `genshin,starrail,zzz` | 要签到的游戏，逗号分隔；填 `none` 关闭全部 |
| `MYS_GAME_BLACKLIST` | 空 | 按游戏屏蔽 UID，如 `genshin:100000001,100000002;starrail:100000003`，也支持 JSON |

游戏 key：

| key | 游戏 |
| --- | --- |
| `genshin` | 原神（别名 `ys`） |
| `starrail` | 崩坏：星穹铁道（别名 `sr` / `hsr`） |
| `zzz` | 绝区零 |
| `honkai3rd` | 崩坏3（别名 `bh3`） |
| `tears` | 未定事件簿（别名 `wd`） |
| `honkai2` | 崩坏学园2（别名 `bh2`） |

### 云游戏签到

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYS_CLOUD_GAMES` | `genshin,zzz` | 要签到的云游戏 |
| `MYS_CLOUD_GENSHIN_TOKEN` | 空 | 云原神的 `x-rpc-combo_token` |
| `MYS_CLOUD_ZZZ_TOKEN` | 空 | 云绝区零的 `x-rpc-combo_token` |

云游戏 token 获取方法（参考 MiyoQian 文档）：

1. 云原神：浏览器打开 <https://ys.mihoyo.com/cloud/> 并登录；云绝区零需要抓包。
2. `F12` → Network，过滤 `wallet/wallet/get`。
3. 打开成功的请求，复制请求头里的 `X-Rpc-Combo_token`。
4. 云原神和云绝区零的 token **不通用**，需要分别获取。

> 云游戏 token 按账号区分。多账号请用 `MYS_ACCOUNTS` 或 `cookie#stoken#云原神token#云绝区零token`
> 写法；`MYS_CLOUD_*_TOKEN` 适合单账号。

### 米游币任务

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYS_BBS_TASKS` | `false` | 米游币任务开关：`true` / `false` / `auto`（有 stoken 才执行） |
| `MYS_BBS_CHECKIN` | `true` | 社区签到 |
| `MYS_BBS_READ` | `true` | 看帖 |
| `MYS_BBS_LIKE` | `true` | 点赞 |
| `MYS_BBS_SHARE` | `true` | 分享 |
| `MYS_CANCEL_LIKE` | `true` | 点赞后取消点赞 |
| `MYS_BBS_FORUMS` | `5,2` | 社区签到版区 ID，逗号分隔；看帖/点赞/分享使用第一个版区 |
| `MYS_POST_LIMIT` | `5` | 每次最多取多少篇帖子（1-20） |

版区 ID：

| ID | 版区 |
| --- | --- |
| 1 | 崩坏3 |
| 2 | 原神 |
| 3 | 崩坏2 |
| 4 | 未定事件簿 |
| 5 | 大别野 |
| 6 | 崩坏：星穹铁道 |
| 8 | 绝区零 |
| 9 | 崩坏：因缘精灵 |

**米游币任务必须配置 stoken**（社区签到、点赞等走 App 接口）。stoken 的获取方式：

- 用 [MiyoQian](https://github.com/Marchen-orz/MiyoQian) 扫码登录后，在
  `data/credentials.yaml` 里复制对应账号的 `stoken` / `stuid` / `mid`；
- 或者用抓包工具从米游社 App 请求的 `Cookie` 里取 `stoken`。

stoken 有两种写法，任选：

```bash
# 1) 直接跟在 cookie 后面，用 # 分隔
MYS_COOKIE='ltuid=123456789; cookie_token=xxxx; ltoken=yyyy; mid=abcdef#v2_xxxxxxxx'

# 2) 完整写法（v2 stoken 需要 mid，推荐）
MYS_COOKIE='ltuid=123456789; cookie_token=xxxx#stuid=123456789; stoken=v2_xxxxxxxx; mid=abcdef'
```

如果 cookie 里已经有 `stoken` 字段，脚本会自动识别，不需要额外配置。

### 延时、重试与通知

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYS_DELAY` | `1-3` | 请求间随机延时（秒），支持 `1-3` 或 `0.5,2` |
| `MYS_RETRY` | `3` | HTTP 连接/5xx 重试次数（0-5） |
| `MYS_NOTIFY` | `true` | 是否推送结果 |
| `MYS_DRY_RUN` | `false` | 只打印配置，不发请求 |
| `MYS_DEBUG` | `false` | 输出调试日志 |

### 验证码（可选）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYS_CAPTCHA_USERKEY` | 空 | 打码狗 userkey，配置后优先用打码狗 |
| `MYS_CAPTCHA_URL` | 空 | 自定义打码接口地址 |
| `MYS_CAPTCHA_KEY` | 空 | 自定义接口的 `X-API-Key`（可选） |

不配置也能跑：触发验证码时对应任务会跳过或失败，日志里会写明原因。

自定义打码接口约定（参考 MiyoQian 的《自定义打码接口规范》）：

```
GET {MYS_CAPTCHA_URL}?gt=xxx&challenge=xxx
Header: X-API-Key: {MYS_CAPTCHA_KEY}

成功返回：
{"code": 0, "data": {"validate": "xxx", "challenge": "xxx"}}
```

---

## 多账号与 JSON 配置

最简单的多账号写法：

```bash
MYS_COOKIE='ltuid=111; cookie_token=aaa; ltoken=bbb & ltuid=222; cookie_token=ccc; ltoken=ddd'
```

如果每个账号的 stoken / 云游戏 token / 游戏列表不同，用 `MYS_ACCOUNTS`：

```json
[
  {
    "name": "主号",
    "cookie": "ltuid=111; cookie_token=aaa; ltoken=bbb; mid=mid111",
    "stoken": "v2_xxxxxxxx",
    "games": ["genshin", "starrail", "zzz"],
    "cloud": {
      "genshin": "云原神 combo_token",
      "zzz": "云绝区零 combo_token"
    }
  },
  {
    "name": "小号",
    "cookie": "ltuid=222; cookie_token=ccc; ltoken=ddd",
    "games": ["genshin"]
  }
]
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 否 | 显示名称 |
| `cookie` | 是（除非只配 stoken） | 米游社 cookie |
| `stoken` | 否 | 米游币任务用，也可写完整的 `stuid=..;stoken=..;mid=..` |
| `stuid` / `mid` | 否 | 一般能从 cookie/stoken 解析出来 |
| `games` | 否 | 该账号要签到的游戏；不填跟随 `MYS_SIGN_GAMES` |
| `cloud` | 否 | 云游戏 token，键为 `genshin` / `zzz` |
| `cloud_genshin` / `cloud_zzz` | 否 | `cloud` 的平铺写法，二者等价 |

> `MYS_ACCOUNTS` 的 JSON 建议写在一行（青龙环境变量里换行容易出错）；写错会在日志里
> 提示解析失败并回退到 `MYS_COOKIE`。

---

## 通知

脚本按以下顺序发送：

1. **青龙自带通知**：如果脚本目录有 `notify.py`（或旧版 `sendNotify.py`）并且
   有可用的 `send()`，直接使用青龙面板「通知设置」里的渠道。
2. **内置渠道**（没有青龙通知模块时）：读取以下环境变量，配置了哪个就用哪个。

| 渠道 | 环境变量 |
| --- | --- |
| PushPlus | `PUSH_PLUS_TOKEN`，可选 `PUSH_PLUS_USER`（topic） |
| Server酱 | `PUSH_KEY` / `SCKEY` / `SERVERCHAN_SENDKEY` / `SCT_SENDKEY` |
| Telegram | `TG_BOT_TOKEN` + `TG_USER_ID`（或 `TG_CHAT_ID`，多个用逗号分隔） |
| Bark | `BARK_PUSH`（key 或完整地址），可选 `BARK_ICON` |
| 钉钉机器人 | `DD_BOT_TOKEN`，可选 `DD_BOT_SECRET` |
| 飞书机器人 | `FSKEY` 或 `FEISHU_WEBHOOK` |
| 企业微信机器人 | `QYWX_KEY` |
| Gotify | `GOTIFY_URL` + `GOTIFY_TOKEN` |
| 自定义 Webhook | `MYS_WEBHOOK_URL`，可选 `MYS_WEBHOOK_TOKEN`（Bearer） |

自定义 Webhook 会收到：

```json
{"title": "米游社签到（成功 5 / 失败 0）", "content": "……", "source": "miys-qinglong"}
```

不想推送时设 `MYS_NOTIFY=false`。

---

## 命令行参数

脚本既能在青龙里直接运行，也支持命令行调试：

```bash
python3 miys_signin.py --dry-run                 # 只看配置
python3 miys_signin.py --games genshin,zzz       # 只签这两个游戏
python3 miys_signin.py --bbs                     # 强制开启米游币任务
python3 miys_signin.py --no-games --no-notify    # 只跑云游戏/米游币，不推送
python3 miys_signin.py --cookie 'ltuid=...'      # 临时指定 cookie，覆盖环境变量
python3 miys_signin.py --debug                   # 调试日志
```

| 参数 | 说明 |
| --- | --- |
| `--cookie` | 临时指定 cookie（多账号用 `&`） |
| `--games` | 指定游戏列表 |
| `--bbs` / `--no-bbs` | 强制开 / 关米游币任务 |
| `--no-games` | 关闭游戏签到 |
| `--no-cloud` | 关闭云游戏签到 |
| `--no-notify` | 不推送 |
| `--dry-run` | 只展示配置 |
| `--debug` | 调试输出 |
| `--version` | 版本号 |

---

## 输出与退出码

日志里每项任务都有标记：

```
[OK]   原神 旅行者(100000001) 签到成功，奖励 「原石」x20
[SKIP] 崩坏：星穹铁道 未找到绑定角色
[FAIL] 绝区零 xxx 签到失败: 登录状态失效，请重新登录(-100)
[INFO] 米游币本次新增 40
```

- 全部成功 / 跳过：退出码 `0`
- 有失败项或没有配置账号：退出码 `1`（青龙会把任务标记为失败）

---

## 常见问题

### `-100 登录状态失效，请重新登录`

- cookie 过期或缺少 `cookie_token`：重新从浏览器复制完整 cookie。
- 只配置了 `ltoken`：游戏签到接口认 `cookie_token`，请补上，或配置 stoken 让脚本
  自动刷新。
- cookie 和 stoken 不是同一个账号：检查 `ltuid` 是否一致。

### `-5003` / 提示「已签到」

今天已经签过了，属于正常情况，脚本会记为成功/跳过。

### 米游币任务提示 `cookie/stoken 可能已失效`

stoken 过期了，重新扫码或重新抓包获取。stoken 与 cookie 必须属于同一账号。

### `首次绑定，请先在米游社 App 手动签到一次`

该角色第一次绑定米游社，接口要求先在 App/游戏内手动签到一次，之后脚本才能签到。

### 触发验证码

米哈游风控触发。可以：

- 配置 `MYS_CAPTCHA_USERKEY`（打码狗）或 `MYS_CAPTCHA_URL`（自定义打码）；
- 或者不管它，等第二天再签；
- 频繁失败时把 `MYS_DELAY` 调大（例如 `3-8`），并确认没有多台设备同时运行。

### 云游戏提示 token 失效

`x-rpc-combo_token` 有有效期，过期后重新从浏览器/抓包获取。云原神和云绝区零的
token 不能混用。

### 青龙通知没有收到

- 先在青龙面板「通知设置」里点测试，确认面板本身能发；
- 青龙通知由脚本目录下的 `notify.py` 发送；如果该文件不存在，可以从青龙仓库复制一份，
  或直接使用下面的内置渠道（比如设 `PUSH_PLUS_TOKEN`）。

### 想换签到时间

改定时规则的 cron 表达式即可，例如 `25 7 * * *` 表示每天 07:25。脚本内部的
`MYS_DELAY` 只控制请求之间的随机间隔，不影响启动时间。

---

## 与参考项目的关系

- [MiyoQian](https://github.com/Marchen-orz/MiyoQian)：游戏签到、米游币任务、
  云游戏签到、验证码的接口与流程参考（提交 `1a2c351`）。
- [mys-signin-helper](https://github.com/mxf133/mys-signin-helper)：cookie 字段、
  `cookie_token` 会话校验、签到状态处理参考（提交 `d2852e2`）。

本脚本是面向青龙面板的独立重写，不包含两个项目的 GUI、扫码登录、商品兑换等
功能；也不依赖 `genshin.py`、`httpx`、`playwright` 等库。

---

## 免责声明

- 本项目仅供学习与交流使用，请遵守米哈游的用户协议与相关法律法规。
- 使用脚本可能带来账号风控等风险，请自行评估并承担后果。
- 请勿将本项目用于商业用途，也请不要大范围传播。
- cookie / stoken / 云游戏 token 属于敏感凭证，请勿提交到公开仓库或分享给他人。
