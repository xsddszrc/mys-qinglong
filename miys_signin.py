#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""米游社每日签到 —— 青龙面板脚本。

支持米游社游戏社区签到（原神 / 崩坏：星穹铁道 / 绝区零 / 崩坏3 / 未定事件簿 /
崩坏学园2）、云游戏签到（云原神 / 云绝区零）以及米游币社区任务（社区签到、
看帖、点赞、分享），结果可推送到青龙通知或常见推送渠道。

思路与接口参考：
  - Marchen-orz/MiyoQian   （米游签：游戏签到 / 米游币任务 / 云游戏签到）
  - mxf133/mys-signin-helper（米游社签到助手：cookie 与签到流程）

常用环境变量（完整说明见 README.md）：
  MYS_COOKIE          必填，米游社 cookie；多账号用 & 或换行分隔
  MYS_STOKEN          可选，米游币任务用的 stoken
  MYS_SIGN_GAMES      可选，默认 genshin,starrail,zzz
  MYS_BBS_TASKS       可选，true / false / auto（默认 false）
  MYS_CLOUD_GENSHIN_TOKEN / MYS_CLOUD_ZZZ_TOKEN
  MYS_NOTIFY          可选，默认 true

仅使用 requests，青龙面板的 Python 环境默认已自带。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import re
import string
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover - 青龙面板一般已自带
    print(
        "缺少依赖 requests：请在青龙面板「依赖管理 → Python3」中安装 requests，"
        "或执行 pip3 install requests",
        flush=True,
    )
    raise

VERSION = "1.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 接口常量（参考 MiyoQian/miyouqian/constants.py）
# ---------------------------------------------------------------------------

BBS_VERSION = "2.106.2"
PASSPORT_APP_VERSION = "2.90.1"
PASSPORT_APP_ID = "bll8iq97cem8"

BBS_SALT = "idMMaGYmVgPzh3wxmWudUXKUPGidO7GM"
BBS_WEB_SALT = "G1ktdwFL4IyGkHuuWSmz0wUe9Db9scyK"
BBS_X6_SALT = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
PASSPORT_X4_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"

TAKUMI_API = "https://api-takumi.mihoyo.com"
BBS_API = "https://bbs-api.miyoushe.com"
PASSPORT_API = "https://passport-api.mihoyo.com"
ZZZ_ACT_API = "https://act-nap-api.mihoyo.com"

ACCOUNT_ROLES_URL = f"{TAKUMI_API}/binding/api/getUserGameRolesByCookie"
GAME_HOME_URL = f"{TAKUMI_API}/event/luna/home?lang=zh-cn"
GAME_INFO_URL = f"{TAKUMI_API}/event/luna/info?lang=zh-cn"
GAME_SIGN_URL = f"{TAKUMI_API}/event/luna/sign"
ZZZ_HOME_URL = f"{ZZZ_ACT_API}/event/luna/zzz/home?lang=zh-cn"
ZZZ_INFO_URL = f"{ZZZ_ACT_API}/event/luna/zzz/info?lang=zh-cn"
ZZZ_SIGN_URL = f"{ZZZ_ACT_API}/event/luna/zzz/sign"

BBS_TASKS_URL = f"{BBS_API}/apihub/wapi/getUserMissionsState"
BBS_SIGN_URL = f"{BBS_API}/apihub/app/api/signIn"
BBS_POST_LIST_URL = f"{BBS_API}/post/api/getForumPostList"
BBS_DETAIL_URL = f"{BBS_API}/post/api/getPostFull"
BBS_SHARE_URL = f"{BBS_API}/apihub/api/getShareConf"
BBS_LIKE_URL = f"{BBS_API}/post/api/post/upvote"
BBS_CREATE_VERIFICATION_URL = f"{BBS_API}/misc/api/createVerification?is_high=true"
BBS_VERIFY_VERIFICATION_URL = f"{BBS_API}/misc/api/verifyVerification"

COOKIE_TOKEN_REFRESH_URL = f"{TAKUMI_API}/auth/api/getCookieAccountInfoBySToken"
LTOKEN_BY_STOKEN_URL = f"{PASSPORT_API}/account/auth/api/getLTokenBySToken"

DEFAULT_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 12; Unspecified Device) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    f"Chrome/103.0.5060.129 Mobile Safari/537.36 miHoYoBBS/{BBS_VERSION}"
)
BBS_APP_UA = "okhttp/4.9.3"

DAMAGOU_URL = "http://api.damagou.top/apiv1/jiyanRecognize.html"
CAPTCHA_MAX_ATTEMPTS = 3

DEFAULT_GAMES = ("genshin", "starrail", "zzz")

GAMES: dict[str, dict[str, Any]] = {
    "genshin": {
        "name": "原神",
        "biz": "hk4e_cn",
        "act_id": "e202311201442471",
        "home_url": GAME_HOME_URL,
        "info_url": GAME_INFO_URL,
        "sign_url": GAME_SIGN_URL,
        "extra_headers": {"x-rpc-signgame": "hk4e"},
    },
    "starrail": {
        "name": "崩坏：星穹铁道",
        "biz": "hkrpg_cn",
        "act_id": "e202304121516551",
        "home_url": GAME_HOME_URL,
        "info_url": GAME_INFO_URL,
        "sign_url": GAME_SIGN_URL,
        "extra_headers": {},
    },
    "zzz": {
        "name": "绝区零",
        "biz": "nap_cn",
        "act_id": "e202406242138391",
        "home_url": ZZZ_HOME_URL,
        "info_url": ZZZ_INFO_URL,
        "sign_url": ZZZ_SIGN_URL,
        "extra_headers": {"x-rpc-signgame": "zzz"},
    },
    "honkai3rd": {
        "name": "崩坏3",
        "biz": "bh3_cn",
        "act_id": "e202306201626331",
        "home_url": GAME_HOME_URL,
        "info_url": GAME_INFO_URL,
        "sign_url": GAME_SIGN_URL,
        "extra_headers": {},
    },
    "tears": {
        "name": "未定事件簿",
        "biz": "nxx_cn",
        "act_id": "e202202251749321",
        "home_url": GAME_HOME_URL,
        "info_url": GAME_INFO_URL,
        "sign_url": GAME_SIGN_URL,
        "extra_headers": {},
    },
    "honkai2": {
        "name": "崩坏学园2",
        "biz": "bh2_cn",
        "act_id": "e202203291431091",
        "home_url": GAME_HOME_URL,
        "info_url": GAME_INFO_URL,
        "sign_url": GAME_SIGN_URL,
        "extra_headers": {},
    },
}

GAME_ALIASES = {
    "ys": "genshin",
    "yuanshen": "genshin",
    "genshin": "genshin",
    "原神": "genshin",
    "sr": "starrail",
    "hsr": "starrail",
    "starrail": "starrail",
    "星铁": "starrail",
    "崩铁": "starrail",
    "崩坏星穹铁道": "starrail",
    "zzz": "zzz",
    "绝区零": "zzz",
    "bh3": "honkai3rd",
    "honkai3rd": "honkai3rd",
    "崩坏3": "honkai3rd",
    "wd": "tears",
    "tears": "tears",
    "未定": "tears",
    "未定事件簿": "tears",
    "bh2": "honkai2",
    "honkai2": "honkai2",
    "崩坏2": "honkai2",
    "崩坏学园2": "honkai2",
}

BBS_FORUMS = {
    1: {"gids": "1", "forum_id": "1", "name": "崩坏3"},
    2: {"gids": "2", "forum_id": "26", "name": "原神"},
    3: {"gids": "3", "forum_id": "30", "name": "崩坏2"},
    4: {"gids": "4", "forum_id": "37", "name": "未定事件簿"},
    5: {"gids": "5", "forum_id": "34", "name": "大别野"},
    6: {"gids": "6", "forum_id": "52", "name": "崩坏：星穹铁道"},
    8: {"gids": "8", "forum_id": "57", "name": "绝区零"},
    9: {"gids": "9", "forum_id": "948", "name": "崩坏：因缘精灵"},
}

CLOUD_GAMES: dict[str, dict[str, str]] = {
    "genshin": {
        "name": "云原神",
        "coin_name": "米云币",
        "url": "https://api-cloudgame.mihoyo.com/hk4e_cg_cn/wallet/wallet/get",
        "host": "api-cloudgame.mihoyo.com",
        "referer": "https://app.mihoyo.com",
    },
    "zzz": {
        "name": "云绝区零",
        "coin_name": "邦邦点",
        "url": "https://cg-nap-api.mihoyo.com/nap_cn/cg/wallet/wallet/get",
        "host": "cg-nap-api.mihoyo.com",
        "referer": "",
    },
}

TRUTHY = {"1", "true", "yes", "y", "on", "enable", "enabled", "开", "是"}
FALSY = {"0", "false", "no", "n", "off", "disable", "disabled", "关", "否", ""}

DEBUG = False

# ---------------------------------------------------------------------------
# 日志与配置读取
# ---------------------------------------------------------------------------


def log(message: str = "") -> None:
    print(message, flush=True)


def debug(message: str) -> None:
    if DEBUG:
        log(f"[debug] {message}")


def env_raw(*names: str) -> str | None:
    """按顺序取第一个存在的环境变量（保留空字符串语义）。"""
    for name in names:
        if name in os.environ:
            return os.environ[name]
    return None


def env_str(*names: str, default: str = "") -> str:
    raw = env_raw(*names)
    return raw.strip() if raw is not None and raw.strip() else default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUTHY:
        return True
    if value in FALSY:
        return False
    return default


def env_int(name: str, default: int, low: int | None = None, high: int | None = None) -> int:
    raw = env_str(name)
    if not raw:
        return default
    try:
        value = int(float(raw))
    except ValueError:
        log(f"[警告] 环境变量 {name}={raw} 不是整数，使用默认值 {default}")
        return default
    if low is not None:
        value = max(value, low)
    if high is not None:
        value = min(value, high)
    return value


def dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def split_entries(raw: str) -> list[str]:
    """多账号分隔：& 或换行（也支持混合使用）。"""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in re.split(r"[&\n]+", text) if part.strip()]


def split_list(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;|\s]+", raw or "") if part.strip()]


def parse_games(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
    else:
        items = split_list(str(value))
    games: list[str] = []
    for item in items:
        key = item.strip().lower()
        key = GAME_ALIASES.get(key, key)
        if key in GAMES:
            if key not in games:
                games.append(key)
        elif key not in ("", "none", "off", "无"):
            log(f"[警告] 未知游戏配置: {item}（可选: {', '.join(GAMES)}）")
    return games


def parse_cloud_games(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else split_list(str(value))
    games: list[str] = []
    for item in items:
        key = str(item).strip().lower()
        if key in CLOUD_GAMES:
            if key not in games:
                games.append(key)
        elif key not in ("", "none", "off", "无"):
            log(f"[警告] 未知云游戏配置: {item}（可选: {', '.join(CLOUD_GAMES)}）")
    return games


def parse_delay(raw: str | None) -> tuple[float, float]:
    text = (raw or "").strip()
    if not text:
        return (1.0, 3.0)
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[-~,，]\s*(\d+(?:\.\d+)?)\s*", text)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
    else:
        try:
            low = high = float(text)
        except ValueError:
            log(f"[警告] 无法解析延时配置 MYS_DELAY={text}，使用默认 1-3 秒")
            return (1.0, 3.0)
    low = max(low, 0.0)
    high = max(high, low)
    return (low, high)


def parse_blacklist(raw: str | None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    text = (raw or "").strip()
    if not text:
        return result
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            log(f"[警告] MYS_GAME_BLACKLIST JSON 解析失败: {exc}")
            return result
        if isinstance(payload, dict):
            for key, value in payload.items():
                game_key = GAME_ALIASES.get(str(key).strip().lower(), str(key).strip().lower())
                if game_key not in GAMES:
                    continue
                if isinstance(value, (list, tuple, set)):
                    uids = {str(item).strip() for item in value if str(item).strip()}
                else:
                    uids = {item for item in re.split(r"[,|/\s]+", str(value)) if item}
                if uids:
                    result[game_key] = uids
        return result
    for chunk in re.split(r"[;\n]+", text):
        if ":" not in chunk:
            continue
        key, values = chunk.split(":", 1)
        game_key = GAME_ALIASES.get(key.strip().lower(), key.strip().lower())
        if game_key not in GAMES:
            continue
        uids = {item.strip() for item in re.split(r"[,|/\s]+", values) if item.strip()}
        if uids:
            result[game_key] = uids
    return result


# ---------------------------------------------------------------------------
# 签名（参考 MiyoQian/miyouqian/core/crypto.py）
# ---------------------------------------------------------------------------


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def random_text(length: int) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def ds(web: bool = False) -> str:
    """米游社 App / Web 的 DS（v1）。"""
    salt = BBS_WEB_SALT if web else BBS_SALT
    timestamp = str(int(time.time()))
    nonce = random_text(6)
    sign = md5(f"salt={salt}&t={timestamp}&r={nonce}")
    return f"{timestamp},{nonce},{sign}"


def ds_x6(body: str = "", query: str = "") -> str:
    """带 body/query 的 DS（x6 盐，社区签到等接口使用）。"""
    timestamp = str(int(time.time()))
    nonce = str(random.randint(100001, 200000))
    sign = md5(f"salt={BBS_X6_SALT}&t={timestamp}&r={nonce}&b={body}&q={query}")
    return f"{timestamp},{nonce},{sign}"


def ds_x4(body: str = "", query: str = "") -> str:
    """护照接口使用的 DS（x4 盐）。"""
    timestamp = str(int(time.time()))
    nonce = str(random.randint(100000, 200000))
    sign = md5(f"salt={PASSPORT_X4_SALT}&t={timestamp}&r={nonce}&b={body}&q={query}")
    return f"{timestamp},{nonce},{sign}"


# ---------------------------------------------------------------------------
# Cookie 工具（参考 MiyoQian/miyouqian/core/cookies.py）
# ---------------------------------------------------------------------------


def normalize_cookie(raw: str) -> str:
    text = str(raw or "").strip()
    if text.lower().startswith("cookie:"):
        text = text[7:]
    text = text.replace("\r", ";").replace("\n", ";")
    parts: list[str] = []
    for item in text.split(";"):
        item = item.strip()
        if item and "=" in item:
            parts.append(item)
    return "; ".join(parts)


def cookie_value(cookie: str, names: tuple[str, ...]) -> str:
    for name in names:
        match = re.search(rf"(?:^|;\s*){re.escape(name)}=([^;]+)", cookie or "")
        if match:
            return match.group(1).strip()
    return ""


def guess_uid(cookie: str) -> str:
    return cookie_value(
        cookie,
        ("account_id", "account_id_v2", "ltuid", "ltuid_v2", "login_uid", "stuid"),
    )


def guess_mid(cookie: str) -> str:
    return cookie_value(cookie, ("mid", "account_mid_v2", "ltmid_v2"))


def set_cookie_value(cookie: str, key: str, value: str) -> str:
    text = cookie or ""
    pattern = re.compile(rf"(^|;\s*){re.escape(key)}=([^;]*)")
    if pattern.search(text):
        return pattern.sub(lambda match: f"{match.group(1)}{key}={value}", text, count=1)
    base = text.rstrip("; ").strip()
    return f"{base}; {key}={value}" if base else f"{key}={value}"


def stoken_cookie(account: "Account") -> str:
    """米游币接口需要的 stoken cookie。"""
    uid = account.stuid or guess_uid(account.cookie)
    mid = account.mid or guess_mid(account.cookie)
    items: list[str] = []
    if uid:
        items.append(f"stuid={uid}")
    if account.stoken:
        items.append(f"stoken={account.stoken}")
    if mid:
        items.append(f"mid={mid}")
    return ";".join(items)


def account_device_id(account: "Account") -> str:
    seed = account.stuid or account.mid or md5(account.cookie)
    return str(uuid.uuid3(uuid.NAMESPACE_URL, f"miys-qinglong:{seed}")).upper()


# ---------------------------------------------------------------------------
# 账号
# ---------------------------------------------------------------------------


@dataclass
class Account:
    cookie: str = ""
    stoken: str = ""
    stuid: str = ""
    mid: str = ""
    games: list[str] = field(default_factory=list)
    cloud: dict[str, str] = field(default_factory=dict)
    name: str = ""
    refresh_failed: bool = False

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        self.cookie = normalize_cookie(self.cookie)
        raw_stoken = str(self.stoken or "").strip()
        if STOKEN_COOKIE_RE.search(raw_stoken.lower()):
            self.stuid = str(
                self.stuid
                or cookie_value(raw_stoken, ("stuid", "ltuid", "account_id", "login_uid"))
            )
            self.mid = str(
                self.mid
                or cookie_value(raw_stoken, ("mid", "account_mid_v2", "ltmid_v2"))
            )
            self.stoken = cookie_value(raw_stoken, ("stoken", "stoken_v2"))
        else:
            self.stoken = raw_stoken
        if not self.stoken:
            self.stoken = cookie_value(self.cookie, ("stoken", "stoken_v2"))
        if not self.stuid:
            self.stuid = guess_uid(self.cookie)
        if not self.mid:
            self.mid = guess_mid(self.cookie)
        self.games = dedupe([game for game in self.games if game in GAMES])
        self.cloud = {
            key: str(value).strip()
            for key, value in (self.cloud or {}).items()
            if key in CLOUD_GAMES and str(value).strip()
        }

    @property
    def label(self) -> str:
        ident = self.stuid or self.mid or "未知账号"
        return f"{self.name}({ident})" if self.name else ident

    @property
    def has_login(self) -> bool:
        return bool(self.cookie or self.stoken)


STOKEN_COOKIE_RE = re.compile(r"(?:^|;)\s*(?:stoken|stoken_v2)=")


def looks_like_stoken(text: str) -> bool:
    value = (text or "").strip()
    low = value.lower()
    if "cookie_token" in low or "ltoken" in low:
        return False
    if STOKEN_COOKIE_RE.search(low):
        return True
    return bool(re.fullmatch(r"v2_[0-9A-Za-z_\-=]+", value))


def parse_account(entry: str, name: str = "") -> Account:
    """解析单个账号。

    entry 形如：
        cookie
        cookie#stoken
        cookie#stoken#云原神token#云绝区零token
    也接受只填 stoken（stuid=..;stoken=..;mid=..）的写法。
    """
    text = (entry or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    parts = [part.strip().strip("'\"") for part in text.split("#")]
    cookie = parts[0] if parts else ""
    stoken = parts[1] if len(parts) > 1 else ""
    cloud: dict[str, str] = {}
    if len(parts) > 2 and parts[2]:
        cloud["genshin"] = parts[2]
    if len(parts) > 3 and parts[3]:
        cloud["zzz"] = parts[3]
    if len(parts) > 4:
        log("[警告] 账号配置中 # 分隔的字段过多，已忽略多余部分")
    if looks_like_stoken(cookie) and not stoken:
        stoken, cookie = cookie, ""
    return Account(cookie=cookie, stoken=stoken, cloud=cloud, name=name)


def parse_accounts() -> list[Account]:
    accounts: list[Account] = []

    raw_json = env_raw("MYS_ACCOUNTS", "MYS_ACCOUNTS_JSON")
    if raw_json and raw_json.strip():
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            log(f"[错误] MYS_ACCOUNTS JSON 解析失败: {exc}")
            payload = None
        if isinstance(payload, dict):
            payload = [payload]
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    accounts.append(parse_account(item))
                elif isinstance(item, dict):
                    cloud_raw = item.get("cloud")
                    cloud: dict[str, str] = {}
                    if isinstance(cloud_raw, dict):
                        cloud.update(
                            {
                                str(key): str(value)
                                for key, value in cloud_raw.items()
                                if str(value).strip()
                            }
                        )
                    if item.get("cloud_genshin"):
                        cloud["genshin"] = str(item["cloud_genshin"])
                    if item.get("cloud_zzz"):
                        cloud["zzz"] = str(item["cloud_zzz"])
                    games = item.get("games")
                    accounts.append(
                        Account(
                            cookie=str(item.get("cookie") or ""),
                            stoken=str(item.get("stoken") or ""),
                            stuid=str(item.get("stuid") or item.get("uid") or ""),
                            mid=str(item.get("mid") or ""),
                            games=parse_games(games) if games else [],
                            cloud=cloud,
                            name=str(item.get("name") or ""),
                        )
                    )
                else:
                    log(f"[警告] MYS_ACCOUNTS 中的元素格式不支持: {type(item).__name__}")

    if not accounts:
        raw = env_str("MYS_COOKIE", "MIYOUSHE_COOKIE", "MYS_COOKIES", "MIYOUSHE_COOKIES")
        for entry in split_entries(raw):
            accounts.append(parse_account(entry))

    return enrich_accounts(accounts)


def enrich_accounts(accounts: list[Account]) -> list[Account]:
    """补充全局 stoken / 云游戏 token，过滤空账号并生成显示名。"""
    # 兼容单独的 MYS_STOKEN：数量一致时按顺序配对，只有一个时给第一个账号
    global_stoken = env_str("MYS_STOKEN")
    if global_stoken and accounts:
        stokens = split_entries(global_stoken)
        if len(stokens) == len(accounts):
            for account, stoken in zip(accounts, stokens):
                if not account.stoken and stoken:
                    account.stoken = stoken
                    account.normalize()
        elif len(stokens) == 1 and accounts:
            if not accounts[0].stoken:
                accounts[0].stoken = stokens[0]
                accounts[0].normalize()
        else:
            log("[警告] MYS_STOKEN 数量与账号数量不一致，已忽略")

    # 全局云游戏 token（单账号场景最方便）
    global_cloud = {
        "genshin": env_str("MYS_CLOUD_GENSHIN_TOKEN", "MYS_CLOUD_GENSHIN"),
        "zzz": env_str("MYS_CLOUD_ZZZ_TOKEN", "MYS_CLOUD_ZZZ"),
    }
    for account in accounts:
        for key, token in global_cloud.items():
            if token and not account.cloud.get(key):
                account.cloud[key] = token

    accounts = [account for account in accounts if account.has_login]
    for index, account in enumerate(accounts, start=1):
        if not account.name and len(accounts) > 1:
            account.name = f"账号{index}"
    return accounts


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------


class HttpClient:
    def __init__(self, retries: int = 3, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry_kwargs: dict[str, Any] = {
            "total": max(retries, 0),
            "connect": max(retries, 0),
            "read": max(retries, 0),
            "backoff_factor": 0.8,
            "status_forcelist": (429, 500, 502, 503, 504),
            "raise_on_status": False,
        }
        try:
            retry = Retry(allowed_methods=frozenset(("GET", "POST")), **retry_kwargs)
        except TypeError:  # 兼容 urllib3 < 1.26
            retry = Retry(**retry_kwargs)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            debug(f"{method} {url} 异常: {exc}")
            return {"retcode": -1, "message": f"网络请求失败: {exc}", "data": None}
        try:
            payload = response.json()
        except ValueError:
            return {
                "retcode": -1,
                "message": f"接口返回非 JSON（HTTP {response.status_code}）",
                "data": None,
            }
        if not isinstance(payload, dict):
            return {"retcode": -1, "message": "接口返回格式异常", "data": None}
        debug(f"{method} {url} -> retcode={payload.get('retcode')} message={payload.get('message')}")
        return payload

    def close(self) -> None:
        self.session.close()


def reason_text(data: dict[str, Any]) -> str:
    message = str(data.get("message") or data.get("msg") or "未知错误")
    retcode = data.get("retcode")
    return f"{message}({retcode})" if retcode not in (None, 0) else message


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 验证码（可选，参考 MiyoQian/miyouqian/core/captcha.py）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptchaSolution:
    validate: str
    challenge: str


class CaptchaSolver:
    def __init__(self, url: str = "", api_key: str = "", damagou: str = "") -> None:
        self.url = url.strip()
        self.api_key = api_key.strip()
        self.damagou = damagou.strip()

    @classmethod
    def from_env(cls) -> "CaptchaSolver":
        return cls(
            url=env_str("MYS_CAPTCHA_URL"),
            api_key=env_str("MYS_CAPTCHA_KEY"),
            damagou=env_str("MYS_CAPTCHA_USERKEY"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.url or self.damagou)

    @property
    def label(self) -> str:
        if self.damagou:
            return "打码狗"
        if self.url:
            return "自定义打码接口"
        return "验证码渠道"

    def solve(
        self, gt: str, challenge: str, success: Any = None
    ) -> CaptchaSolution | None:
        if self.damagou:
            return self._solve_damagou(gt, challenge, success)
        if self.url:
            return self._solve_custom(gt, challenge)
        return None

    def _solve_damagou(
        self, gt: str, challenge: str, success: Any
    ) -> CaptchaSolution | None:
        params: dict[str, Any] = {
            "userkey": self.damagou,
            "gt": gt,
            "challenge": challenge,
            "isJson": "2",
        }
        try:
            if success is not None and int(success) == 0:
                params["success"] = 0
        except (TypeError, ValueError):
            pass
        try:
            response = requests.get(DAMAGOU_URL, params=params, timeout=60)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            log(f"打码狗请求失败: {exc}")
            return None
        if str(data.get("status")) != "0":
            log(f"打码狗识别失败: {data.get('msg') or data.get('message') or '未知错误'}")
            return None
        raw = str(data.get("data") or "")
        if "|" not in raw:
            log("打码狗返回格式异常")
            return None
        chal, validate = raw.split("|", 1)
        chal, validate = chal.strip(), validate.strip()
        if not chal or not validate:
            return None
        return CaptchaSolution(validate=validate, challenge=chal)

    def _solve_custom(self, gt: str, challenge: str) -> CaptchaSolution | None:
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        last_error = "未知错误"
        for attempt in range(1, CAPTCHA_MAX_ATTEMPTS + 1):
            try:
                response = requests.get(
                    self.url,
                    params={"gt": gt, "challenge": challenge},
                    headers=headers,
                    timeout=60,
                )
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
                time.sleep(1)
                continue
            code = data.get("code")
            if str(code) == "0":
                payload = data.get("data") or {}
                validate = str(payload.get("validate") or "").strip()
                chal = str(payload.get("challenge") or challenge).strip()
                if validate:
                    return CaptchaSolution(validate=validate, challenge=chal or challenge)
                last_error = "接口返回成功但缺少 data.validate"
                break
            last_error = f"[{code}] {data.get('message') or '未知错误'}"
            if attempt < CAPTCHA_MAX_ATTEMPTS:
                time.sleep(1)
        log(f"自定义打码接口识别失败: {last_error}")
        return None


SOLVER = CaptchaSolver()


# ---------------------------------------------------------------------------
# 登录态刷新
# ---------------------------------------------------------------------------


def ensure_cookie_token(client: HttpClient, account: Account, force: bool = False) -> bool:
    """用 stoken 换 cookie_token，补齐账号 cookie。"""
    if not account.stoken:
        return False
    if force and account.refresh_failed:
        return False
    if not force and cookie_value(account.cookie, ("cookie_token", "cookie_token_v2")):
        return True
    if not account.stuid:
        log("[警告] 未能解析出 stuid/account_id，无法用 stoken 刷新 cookie_token")
        return False
    headers = {
        "cookie": stoken_cookie(account),
        "user-agent": DEFAULT_MOBILE_UA,
    }
    data = client.request("GET", COOKIE_TOKEN_REFRESH_URL, headers=headers)
    if data.get("retcode") != 0:
        log(f"[警告] 刷新 cookie_token 失败: {reason_text(data)}")
        account.refresh_failed = True
        return False
    token = str((data.get("data") or {}).get("cookie_token") or "")
    if not token:
        log("[警告] 刷新 cookie_token 失败: 接口未返回 cookie_token")
        account.refresh_failed = True
        return False
    account.cookie = set_cookie_value(account.cookie, "cookie_token", token)
    # 只用 stoken 配置时，补上 UID / mid，游戏签到接口需要
    for key in ("ltuid", "account_id", "ltuid_v2", "account_id_v2", "login_uid"):
        if not cookie_value(account.cookie, (key,)):
            account.cookie = set_cookie_value(account.cookie, key, account.stuid)
    if account.mid:
        for key in ("ltmid_v2", "account_mid_v2", "mid"):
            if not cookie_value(account.cookie, (key,)):
                account.cookie = set_cookie_value(account.cookie, key, account.mid)
    if not cookie_value(account.cookie, ("ltoken", "ltoken_v2")):
        refresh_ltoken(client, account)
    account.refresh_failed = False
    log("已使用 stoken 刷新 cookie_token")
    return True


def refresh_ltoken(client: HttpClient, account: Account) -> bool:
    """用 stoken 换 ltoken（米游社 wapi 接口需要）。"""
    if not account.stoken or not account.mid:
        return False
    headers = {
        "user-agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) miHoYoBBS/{BBS_VERSION}",
        "x-rpc-app_version": BBS_VERSION,
        "x-rpc-client_type": "5",
        "x-requested-with": "com.mihoyo.hyperion",
        "referer": "https://webstatic.mihoyo.com",
        "x-rpc-device_id": account_device_id(account),
        "cookie": f"mid={account.mid};stoken={account.stoken}",
        "DS": ds_x4(query=f"stoken={account.stoken}"),
    }
    data = client.request(
        "GET",
        LTOKEN_BY_STOKEN_URL,
        params={"stoken": account.stoken},
        headers=headers,
    )
    if data.get("retcode") != 0:
        debug(f"刷新 ltoken 失败: {reason_text(data)}")
        return False
    token = str((data.get("data") or {}).get("ltoken") or "")
    if not token:
        debug("刷新 ltoken 失败: 接口未返回 ltoken")
        return False
    account.cookie = set_cookie_value(account.cookie, "ltoken", token)
    return True


# ---------------------------------------------------------------------------
# 请求头
# ---------------------------------------------------------------------------


def game_headers(account: Account, game: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "DS": ds(web=True),
        "x-rpc-channel": "miyousheluodi",
        "Origin": "https://act.mihoyo.com",
        "x-rpc-app_version": BBS_VERSION,
        "User-Agent": DEFAULT_MOBILE_UA,
        "x-rpc-client_type": "5",
        "Referer": "https://act.mihoyo.com/",
        "Accept-Language": "zh-CN,en-US;q=0.8",
        "X-Requested-With": "com.mihoyo.hyperion",
        "Cookie": account.cookie,
        "x-rpc-device_id": account_device_id(account),
    }
    headers.update(game.get("extra_headers") or {})
    return headers


def bbs_web_headers(account: Account) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://webstatic.mihoyo.com",
        "User-Agent": DEFAULT_MOBILE_UA,
        "Referer": "https://webstatic.mihoyo.com",
        "Accept-Language": "zh-CN,en-US;q=0.8",
        "X-Requested-With": "com.mihoyo.hyperion",
        "Cookie": account.cookie,
    }


def bbs_app_headers(account: Account, challenge: str = "") -> dict[str, str]:
    headers = {
        "DS": ds(web=False),
        "cookie": stoken_cookie(account) if account.stoken else account.cookie,
        "x-rpc-client_type": "2",
        "x-rpc-app_version": BBS_VERSION,
        "x-rpc-sys_version": "12",
        "x-rpc-channel": "miyousheluodi",
        "x-rpc-device_id": account_device_id(account),
        "x-rpc-device_name": "Xiaomi MI 6",
        "x-rpc-device_model": "Mi 6",
        "x-rpc-h265_supported": "1",
        "Referer": "https://app.mihoyo.com",
        "Content-Type": "application/json; charset=UTF-8",
        "Host": "bbs-api.miyoushe.com",
        "x-rpc-verify_key": PASSPORT_APP_ID,
        "x-rpc-csm_source": "home",
        "User-Agent": BBS_APP_UA,
    }
    if challenge:
        headers["x-rpc-challenge"] = challenge
    return headers


# ---------------------------------------------------------------------------
# 游戏社区签到
# ---------------------------------------------------------------------------


def describe_award(awards: list[dict[str, Any]], index: int) -> str:
    if not awards:
        return "未知"
    index = min(max(index, 0), len(awards) - 1)
    award = awards[index] or {}
    return f"「{award.get('name', '未知')}」x{award.get('cnt', '?')}"


def game_roles(
    client: HttpClient, account: Account, game: dict[str, Any]
) -> list[dict[str, Any]] | None:
    def call() -> dict[str, Any]:
        return client.request(
            "GET",
            ACCOUNT_ROLES_URL,
            params={"game_biz": game["biz"]},
            headers=game_headers(account, game),
        )

    data = call()
    if data.get("retcode") == -100 and ensure_cookie_token(client, account, force=True):
        data = call()
    if data.get("retcode") != 0:
        log(f"获取{game['name']}绑定角色失败: {reason_text(data)}")
        return None
    roles = (data.get("data") or {}).get("list")
    return roles if isinstance(roles, list) else []


def game_awards(
    client: HttpClient, account: Account, game: dict[str, Any]
) -> list[dict[str, Any]]:
    data = client.request(
        "GET",
        game["home_url"],
        params={"act_id": game["act_id"]},
        headers=game_headers(account, game),
    )
    if data.get("retcode") != 0:
        debug(f"获取{game['name']}奖励列表失败: {reason_text(data)}")
        return []
    awards = (data.get("data") or {}).get("awards")
    return awards if isinstance(awards, list) else []


def game_sign_info(
    client: HttpClient, account: Account, game: dict[str, Any], role: dict[str, Any]
) -> dict[str, Any] | None:
    params = {
        "act_id": game["act_id"],
        "region": role.get("region"),
        "uid": role.get("game_uid"),
    }

    def call() -> dict[str, Any]:
        return client.request(
            "GET", game["info_url"], params=params, headers=game_headers(account, game)
        )

    data = call()
    if data.get("retcode") == -100 and ensure_cookie_token(client, account, force=True):
        data = call()
    if data.get("retcode") != 0:
        log(f"查询签到状态失败: {reason_text(data)}")
        return None
    payload = data.get("data")
    return payload if isinstance(payload, dict) else {}


def game_sign(
    client: HttpClient,
    account: Account,
    game: dict[str, Any],
    role: dict[str, Any],
    solution: CaptchaSolution | None = None,
) -> dict[str, Any]:
    headers = game_headers(account, game)
    if solution:
        headers.update(
            {
                "x-rpc-challenge": solution.challenge,
                "x-rpc-validate": solution.validate,
                "x-rpc-seccode": f"{solution.validate}|jordan",
            }
        )
    payload = {
        "act_id": game["act_id"],
        "region": role.get("region"),
        "uid": role.get("game_uid"),
    }
    return client.request("POST", game["sign_url"], json=payload, headers=headers)


def game_solve_captcha(
    client: HttpClient,
    account: Account,
    game: dict[str, Any],
    role: dict[str, Any],
    data: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """游戏签到触发验证码时尝试自动处理，返回最后一次签到响应。"""
    for attempt in range(1, CAPTCHA_MAX_ATTEMPTS + 1):
        payload = data.get("data") or {}
        gt = str(payload.get("gt") or "")
        challenge = str(payload.get("challenge") or "")
        need_captcha = data.get("retcode") == 1034 or payload.get("success") == 1
        if not need_captcha:
            return data
        if not SOLVER.enabled:
            log("触发验证码，但未配置识别渠道（MYS_CAPTCHA_URL / MYS_CAPTCHA_USERKEY），跳过")
            return data
        if not gt or not challenge:
            log("触发验证码，但接口未返回 gt/challenge")
            return data
        log(f"{label} 触发验证码，正在调用{SOLVER.label}识别({attempt}/{CAPTCHA_MAX_ATTEMPTS})")
        solution = SOLVER.solve(gt, challenge, success=payload.get("success"))
        if not solution:
            return data
        data = game_sign(client, account, game, role, solution)
        if data.get("retcode") == -100:
            return data
    return data


def checkin_game(
    client: HttpClient,
    account: Account,
    game_key: str,
    opts: "Options",
    report: "AccountReport",
) -> None:
    game = GAMES[game_key]
    name = game["name"]
    log(f"== {name} ==")
    log(f"正在获取{name}绑定角色")
    roles = game_roles(client, account, game)
    if roles is None:
        report.fail(f"{name} 获取绑定角色失败")
        return
    if not roles:
        report.skip(f"{name} 未找到绑定角色")
        return

    awards = game_awards(client, account, game)
    blacklist = opts.blacklist.get(game_key, set())
    for role in roles:
        uid = str(role.get("game_uid") or "")
        nickname = str(role.get("nickname") or uid)
        label = f"{name} {nickname}({uid})"
        if uid and uid in blacklist:
            report.skip(f"{label} 在黑名单中")
            continue

        log(f"正在查询 {label} 签到状态")
        info = game_sign_info(client, account, game, role)
        if info is None:
            report.fail(f"{label} 查询签到状态失败")
            continue
        if info.get("first_bind"):
            report.skip(f"{label} 首次绑定，请先在米游社 App 手动签到一次")
            continue

        signed = bool(info.get("is_sign"))
        day_index = max(safe_int(info.get("total_sign_day")) - 1, 0)
        if signed:
            report.ok(f"{label} 今日已签到，奖励 {describe_award(awards, day_index)}")
            continue

        log(f"正在为 {label} 签到")
        data = game_sign(client, account, game, role)
        if data.get("retcode") == -100 and ensure_cookie_token(client, account, force=True):
            data = game_sign(client, account, game, role)
        data = game_solve_captcha(client, account, game, role, data, label)

        retcode = data.get("retcode")
        payload = data.get("data") or {}
        if retcode == -5003:
            report.ok(f"{label} 今日已签到，奖励 {describe_award(awards, day_index)}")
        elif retcode == 0 and payload.get("success") != 1:
            report.ok(f"{label} 签到成功，奖励 {describe_award(awards, day_index + 1)}")
        elif retcode == 1034 or payload.get("success") == 1:
            report.fail(f"{label} 触发验证码，未能完成签到")
        else:
            report.fail(f"{label} 签到失败: {reason_text(data)}")


# ---------------------------------------------------------------------------
# 云游戏签到
# ---------------------------------------------------------------------------


def cloud_headers(game: dict[str, str], token: str) -> dict[str, str]:
    headers = {
        "Host": game["host"],
        "Accept": "*/*",
        "x-rpc-combo_token": token,
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/99.0.4844.84 Safari/537.36"
        ),
    }
    if game.get("referer"):
        headers["Referer"] = game["referer"]
    return headers


def cloud_wallet(client: HttpClient, game: dict[str, str], token: str) -> dict[str, Any]:
    return client.request("GET", game["url"], headers=cloud_headers(game, token))


def cloud_free_time(wallet: dict[str, Any]) -> int:
    return safe_int((wallet.get("free_time") or {}).get("free_time"))


def cloud_send_free_time(wallet: dict[str, Any]) -> int:
    return safe_int((wallet.get("free_time") or {}).get("send_freetime"))


def format_minutes(minutes: int) -> str:
    minutes = max(minutes, 0)
    hours, minute = divmod(minutes, 60)
    if hours and minute:
        return f"{hours}小时{minute}分钟"
    if hours:
        return f"{hours}小时"
    return f"{minute}分钟"


def describe_wallet(game: dict[str, Any], wallet: dict[str, Any]) -> str:
    free_time = cloud_free_time(wallet)
    play_card = str((wallet.get("play_card") or {}).get("short_msg") or "未知")
    coin_num = safe_int((wallet.get("coin") or {}).get("coin_num"))
    return (
        f"{game['name']} 当前免费时长 {format_minutes(free_time)}，"
        f"畅玩卡状态 {play_card}，拥有{game['coin_name']} {coin_num} 枚"
    )


def checkin_cloud_game(
    client: HttpClient,
    account: Account,
    game_key: str,
    opts: "Options",
    report: "AccountReport",
) -> None:
    game = CLOUD_GAMES[game_key]
    name = game["name"]
    token = account.cloud.get(game_key, "")
    log(f"正在进行{name}签到")
    data = cloud_wallet(client, game, token)
    retcode = data.get("retcode")
    if retcode == -100:
        report.fail(f"{name} token 失效或账号状态受限")
        return
    if retcode != 0:
        report.fail(f"{name} 签到失败: {reason_text(data)}")
        return

    wallet = data.get("data") or {}
    free_time = cloud_free_time(wallet)
    gained = cloud_send_free_time(wallet)
    if gained <= 0 and free_time < 600:
        time.sleep(random.randint(3, 6))
        try:
            latest = cloud_wallet(client, game, token)
        except Exception:
            latest = {}
        if latest.get("retcode") == 0:
            latest_wallet = latest.get("data") or {}
            gained = max(cloud_free_time(latest_wallet) - free_time, 0)
            wallet = latest_wallet
    elif gained > 0:
        # 签到响应里的 free_time 是发放前快照，展示时补上本次到账时长
        free_time_info = dict(wallet.get("free_time") or {})
        free_time_info["free_time"] = str(free_time + gained)
        wallet = {**wallet, "free_time": free_time_info}

    if gained > 0:
        report.ok(f"{name} 签到成功，获得 {gained} 分钟免费时长")
    else:
        report.ok(f"{name} 今日已签到或免费时长已达上限")
    log(describe_wallet(game, wallet))


def checkin_cloud_games(
    client: HttpClient, account: Account, opts: "Options", report: "AccountReport"
) -> None:
    configured = [
        key for key in opts.cloud_games if key in CLOUD_GAMES and account.cloud.get(key)
    ]
    if not configured:
        log("未配置云游戏 token，跳过云游戏签到")
        return
    log("== 云游戏签到 ==")
    for game_key in configured:
        checkin_cloud_game(client, account, game_key, opts, report)
        sleep_delay(opts)


# ---------------------------------------------------------------------------
# 米游币社区任务
# ---------------------------------------------------------------------------


def bbs_mission_state(client: HttpClient, account: Account) -> dict[str, Any]:
    def call() -> dict[str, Any]:
        return client.request(
            "GET",
            BBS_TASKS_URL,
            params={"point_sn": "myb"},
            headers=bbs_web_headers(account),
        )

    data = call()
    if data.get("retcode") == -100 and ensure_cookie_token(client, account, force=True):
        data = call()
    if data.get("retcode") != 0:
        log(f"获取米游币任务状态失败: {reason_text(data)}")
        return {}
    payload = data.get("data")
    return payload if isinstance(payload, dict) else {}


def bbs_task_flags(state: dict[str, Any]) -> dict[str, Any]:
    flags: dict[str, Any] = {
        "sign": False,
        "read": False,
        "read_num": 3,
        "like": False,
        "like_num": 5,
        "share": False,
    }
    mapping = {
        58: ("sign", None),
        59: ("read", "read_num"),
        60: ("like", "like_num"),
        61: ("share", None),
    }
    for mission in state.get("states") or []:
        mission_id = safe_int(mission.get("mission_id"))
        if mission_id not in mapping:
            continue
        flag, num_key = mapping[mission_id]
        if mission.get("is_get_award"):
            flags[flag] = True
        elif num_key:
            flags[num_key] = max(
                safe_int(flags[num_key]) - safe_int(mission.get("happened_times")), 0
            )
    return flags


def bbs_sign_request(
    client: HttpClient, account: Account, body: str, challenge: str = ""
) -> dict[str, Any]:
    headers = bbs_app_headers(account, challenge=challenge)
    headers["DS"] = ds_x6(body=body)
    return client.request("POST", BBS_SIGN_URL, data=body, headers=headers)


def bbs_like_request(
    client: HttpClient,
    account: Account,
    payload: dict[str, Any],
    challenge: str = "",
) -> dict[str, Any]:
    return client.request(
        "POST",
        BBS_LIKE_URL,
        json=payload,
        headers=bbs_app_headers(account, challenge=challenge),
    )


def bbs_captcha_challenge(
    client: HttpClient, account: Account, scene: str, attempt: int
) -> str:
    log(f"{scene}触发验证码，正在调用{SOLVER.label}识别({attempt}/{CAPTCHA_MAX_ATTEMPTS})")
    data = client.request(
        "GET", BBS_CREATE_VERIFICATION_URL, headers=bbs_app_headers(account)
    )
    if data.get("retcode") != 0:
        log(f"{scene}验证码初始化失败: {reason_text(data)}")
        return ""
    payload = data.get("data") or {}
    gt = str(payload.get("gt") or "")
    challenge = str(payload.get("challenge") or "")
    if not gt or not challenge:
        log(f"{scene}验证码初始化结果缺少 gt/challenge")
        return ""
    solution = SOLVER.solve(gt, challenge, success=payload.get("success"))
    if not solution:
        return ""
    verify = client.request(
        "POST",
        BBS_VERIFY_VERIFICATION_URL,
        json={
            "geetest_challenge": solution.challenge,
            "geetest_validate": solution.validate,
            "geetest_seccode": f"{solution.validate}|jordan",
        },
        headers=bbs_app_headers(account),
    )
    if verify.get("retcode") != 0:
        log(f"{scene}验证码校验失败: {reason_text(verify)}")
        return ""
    passed = str((verify.get("data") or {}).get("challenge") or "")
    if not passed:
        log(f"{scene}验证码校验结果缺少 challenge")
        return ""
    return passed


def bbs_retry_with_captcha(
    client: HttpClient,
    account: Account,
    scene: str,
    request: Any,
) -> dict[str, Any]:
    if not SOLVER.enabled:
        log(f"{scene}触发验证码，未配置验证码识别渠道，已跳过")
        return {"retcode": 1034, "message": "触发验证码"}
    for attempt in range(1, CAPTCHA_MAX_ATTEMPTS + 1):
        challenge = bbs_captcha_challenge(client, account, scene, attempt)
        if not challenge:
            continue
        data = request(challenge)
        if data.get("retcode") == 0:
            return data
        log(f"{scene}验证码提交失败: {reason_text(data)}")
    return {"retcode": 1034, "message": "验证码处理失败"}


def bbs_posts(
    client: HttpClient, account: Account, opts: "Options"
) -> list[tuple[str, str, str]]:
    forums = [BBS_FORUMS[fid] for fid in opts.forums if fid in BBS_FORUMS]
    if not forums:
        return []
    forum = forums[0]
    data = client.request(
        "GET",
        BBS_POST_LIST_URL,
        params={
            "forum_id": forum["forum_id"],
            "is_good": "false",
            "is_hot": "false",
            "page_size": 20,
            "sort_type": 1,
        },
        headers=bbs_app_headers(account),
    )
    if data.get("retcode") != 0:
        log(f"获取帖子列表失败: {reason_text(data)}")
        return []
    raw_posts = (data.get("data") or {}).get("list") or []
    posts: list[tuple[str, str, str]] = []
    for item in raw_posts:
        post = item.get("post") or {}
        post_id = str(post.get("post_id") or "")
        title = str(post.get("subject") or post_id)
        if post_id:
            posts.append((post_id, title, forum["gids"]))
    random.shuffle(posts)
    return posts[: opts.post_limit]


def bbs_community_sign(
    client: HttpClient, account: Account, opts: "Options", report: "AccountReport"
) -> None:
    for forum_id in opts.forums:
        forum = BBS_FORUMS.get(forum_id)
        if not forum:
            continue
        name = forum["name"]
        log(f"正在进行{name}社区签到")
        body = json.dumps({"gids": forum["gids"]}, separators=(",", ":"))
        data = bbs_sign_request(client, account, body)
        if data.get("retcode") == 1034:
            data = bbs_retry_with_captcha(
                client,
                account,
                "社区签到",
                lambda challenge: bbs_sign_request(client, account, body, challenge),
            )
        if data.get("retcode") == 0:
            message = str(data.get("message") or "")
            if "已签到" in message or "已签" in message:
                report.skip(f"{name} 社区签到已完成")
            else:
                report.ok(f"{name} 社区签到成功")
        else:
            report.fail(f"{name} 社区签到失败: {reason_text(data)}")
        sleep_delay(opts)


def bbs_read_posts(
    client: HttpClient,
    account: Account,
    posts: list[tuple[str, str, str]],
    opts: "Options",
    report: "AccountReport",
) -> None:
    for post_id, title, _gids in posts:
        log(f"正在浏览: {title}")
        data = client.request(
            "GET",
            BBS_DETAIL_URL,
            params={"post_id": post_id},
            headers=bbs_app_headers(account),
        )
        if data.get("retcode") == 0 or data.get("message") == "OK":
            report.ok(f"看帖 {title}")
        else:
            report.fail(f"看帖 {title} 失败: {reason_text(data)}")
        sleep_delay(opts)


def bbs_like_posts(
    client: HttpClient,
    account: Account,
    posts: list[tuple[str, str, str]],
    opts: "Options",
    report: "AccountReport",
) -> None:
    for post_id, title, gids in posts:
        log(f"正在点赞: {title}")
        payload = {"post_id": post_id, "is_cancel": False, "gids": gids}
        data = bbs_like_request(client, account, payload)
        if data.get("retcode") == 1034:
            data = bbs_retry_with_captcha(
                client,
                account,
                "点赞",
                lambda challenge: bbs_like_request(client, account, payload, challenge),
            )
        if data.get("retcode") == 0 or data.get("message") == "OK":
            report.ok(f"点赞 {title}")
            if opts.cancel_like:
                sleep_delay(opts)
                log(f"正在取消点赞: {title}")
                cancel_payload = {**payload, "is_cancel": True}
                bbs_like_request(client, account, cancel_payload)
        else:
            report.fail(f"点赞 {title} 失败: {reason_text(data)}")
        sleep_delay(opts)


def bbs_share_posts(
    client: HttpClient,
    account: Account,
    posts: list[tuple[str, str, str]],
    opts: "Options",
    report: "AccountReport",
) -> None:
    for post_id, title, _gids in posts:
        log(f"正在分享: {title}")
        data = client.request(
            "GET",
            BBS_SHARE_URL,
            params={"entity_id": post_id, "entity_type": 1},
            headers=bbs_web_headers(account),
        )
        if data.get("retcode") == 0 or data.get("message") == "OK":
            report.ok(f"分享 {title}")
        else:
            report.fail(f"分享 {title} 失败: {reason_text(data)}")
        sleep_delay(opts)


def run_bbs_tasks(
    client: HttpClient, account: Account, opts: "Options", report: "AccountReport"
) -> None:
    if not account.stoken:
        log("未配置 stoken，跳过米游币社区任务")
        log("如需执行，请使用 MYS_COOKIE 的 cookie#stoken 写法，或设置 MYS_STOKEN")
        report.skip("米游币任务：未配置 stoken")
        return

    log("== 米游币社区任务 ==")
    if not cookie_value(account.cookie, ("cookie_token", "cookie_token_v2")):
        ensure_cookie_token(client, account)
    elif not cookie_value(account.cookie, ("ltoken", "ltoken_v2")):
        # 米游社 wapi 接口走网页登录态，缺 ltoken 时用 stoken 补一下
        refresh_ltoken(client, account)

    state = bbs_mission_state(client, account)
    if not state:
        report.fail("米游币任务状态获取失败（cookie/stoken 可能已失效）")
        return

    received = safe_int(state.get("already_received_points"))
    can_get = safe_int(state.get("can_get_points"))
    total_points = safe_int(state.get("total_points"))
    possible_today = received + can_get
    log(f"米游币今日进度：已获得 {received}，还可获得 {can_get}，预计总共可获得 {possible_today}")

    if can_get == 0:
        report.skip(f"米游币任务今日已完成（今日已得 {received}，总计 {total_points}）")
        return

    flags = bbs_task_flags(state)
    if opts.bbs_checkin:
        if flags["sign"]:
            report.skip("社区签到已完成")
        else:
            bbs_community_sign(client, account, opts, report)
    else:
        log("社区签到已在配置中关闭")

    enabled = {
        "read": opts.bbs_read,
        "like": opts.bbs_like,
        "share": opts.bbs_share,
    }
    interaction = [
        ("read", "read_num", "看帖", bbs_read_posts),
        ("like", "like_num", "点赞", bbs_like_posts),
        ("share", None, "分享", bbs_share_posts),
    ]
    needs_posts = any(enabled[flag] and not flags[flag] for flag, _, _, _ in interaction)

    if needs_posts:
        log("正在获取帖子列表")
        posts = bbs_posts(client, account, opts)
        if not posts:
            report.fail("获取帖子列表失败，无法执行看帖/点赞/分享")
        else:
            for flag, num_key, label, action in interaction:
                if not enabled[flag]:
                    continue
                if flags[flag]:
                    report.skip(f"{label}任务已完成")
                    continue
                limit = int(flags[num_key]) if num_key else 1
                if limit <= 0:
                    report.skip(f"{label}任务无需执行")
                    continue
                action(client, account, posts[:limit], opts, report)
    else:
        for flag, _num_key, label, _action in interaction:
            if enabled[flag] and flags[flag]:
                report.skip(f"{label}任务已完成")

    latest = bbs_mission_state(client, account) or state
    final_received = safe_int(latest.get("already_received_points")) or received
    final_total = safe_int(latest.get("total_points")) or total_points
    gained = max(final_received - received, 0)
    final_possible = max(possible_today, final_received)
    log(
        f"米游币任务结束：今日已得 {final_received}，"
        f"还能获得 {max(final_possible - final_received, 0)}，当前总计 {final_total}"
    )
    report.info(f"米游币本次新增 {gained}")


# ---------------------------------------------------------------------------
# 结果收集与通知
# ---------------------------------------------------------------------------


@dataclass
class AccountReport:
    label: str
    lines: list[str] = field(default_factory=list)
    success: int = 0
    failed: int = 0
    skipped: int = 0

    def _add(self, marker: str, message: str) -> None:
        line = f"{marker} {message}"
        self.lines.append(line)
        log(line)

    def ok(self, message: str) -> None:
        self.success += 1
        self._add("[OK]", message)

    def fail(self, message: str) -> None:
        self.failed += 1
        self._add("[FAIL]", message)

    def skip(self, message: str) -> None:
        self.skipped += 1
        self._add("[SKIP]", message)

    def info(self, message: str) -> None:
        self._add("[INFO]", message)


def _push_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> bool:
    try:
        response = requests.post(url, json=payload, headers=headers or {}, timeout=20)
        if response.status_code >= 400:
            log(f"[警告] 推送接口返回 HTTP {response.status_code}: {url.split('?')[0]}")
            return False
        return True
    except requests.RequestException as exc:
        log(f"[警告] 推送请求失败: {exc}")
        return False


def _push_form(url: str, payload: dict[str, Any]) -> bool:
    try:
        response = requests.post(url, data=payload, timeout=20)
        if response.status_code >= 400:
            log(f"[警告] 推送接口返回 HTTP {response.status_code}")
            return False
        return True
    except requests.RequestException as exc:
        log(f"[警告] 推送请求失败: {exc}")
        return False


def _notify_pushplus(title: str, content: str) -> bool:
    token = env_str("PUSH_PLUS_TOKEN")
    if not token:
        return False
    payload: dict[str, Any] = {
        "token": token,
        "title": title,
        "content": content,
        "template": "txt",
    }
    topic = env_str("PUSH_PLUS_USER")
    if topic and topic != "default":
        payload["topic"] = topic
    return _push_json("https://www.pushplus.plus/send", payload)


def _notify_serverchan(title: str, content: str) -> bool:
    key = env_str("PUSH_KEY", "SCKEY", "SERVERCHAN_SENDKEY", "SCT_SENDKEY")
    if not key:
        return False
    return _push_form(
        f"https://sctapi.ftqq.com/{key}.send", {"title": title, "desp": content}
    )


def _notify_telegram(title: str, content: str) -> bool:
    token = env_str("TG_BOT_TOKEN")
    chat_ids = env_str("TG_USER_ID", "TG_CHAT_ID")
    if not token or not chat_ids:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = False
    for chat_id in re.split(r"[,|&\s]+", chat_ids):
        if not chat_id:
            continue
        ok = _push_form(url, {"chat_id": chat_id, "text": f"{title}\n\n{content}"}) or ok
    return ok


def _notify_bark(title: str, content: str) -> bool:
    raw = env_str("BARK_PUSH")
    if not raw:
        return False
    if "://" in raw:
        base, _, device_key = raw.rstrip("/").rpartition("/")
        url = f"{base}/push"
    else:
        url = "https://api.day.app/push"
        device_key = raw
    if not device_key:
        return False
    payload: dict[str, Any] = {
        "device_key": device_key,
        "title": title,
        "body": content,
        "group": "米游社",
    }
    icon = env_str("BARK_ICON")
    if icon:
        payload["icon"] = icon
    return _push_json(url, payload)


def _notify_dingtalk(title: str, content: str) -> bool:
    token = env_str("DD_BOT_TOKEN")
    if not token:
        return False
    url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
    secret = env_str("DD_BOT_SECRET")
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
        ).digest()
        sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
        url += f"&timestamp={timestamp}&sign={sign}"
    return _push_json(
        url, {"msgtype": "text", "text": {"content": f"{title}\n{content}"}}
    )


def _notify_feishu(title: str, content: str) -> bool:
    webhook = env_str("FEISHU_WEBHOOK")
    key = env_str("FSKEY")
    if not webhook and not key:
        return False
    url = webhook or f"https://open.feishu.cn/open-apis/bot/v2/hook/{key}"
    return _push_json(
        url, {"msg_type": "text", "content": {"text": f"{title}\n{content}"}}
    )


def _notify_wecom(title: str, content: str) -> bool:
    key = env_str("QYWX_KEY")
    if not key:
        return False
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    return _push_json(url, {"msgtype": "text", "text": {"content": f"{title}\n{content}"}})


def _notify_gotify(title: str, content: str) -> bool:
    base = env_str("GOTIFY_URL")
    token = env_str("GOTIFY_TOKEN")
    if not base or not token:
        return False
    url = f"{base.rstrip('/')}/message?token={token}"
    return _push_json(url, {"title": title, "message": content, "priority": 5})


def _notify_webhook(title: str, content: str) -> bool:
    url = env_str("MYS_WEBHOOK_URL")
    if not url:
        return False
    headers: dict[str, str] = {}
    token = env_str("MYS_WEBHOOK_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _push_json(
        url,
        {"title": title, "content": content, "source": "miys-qinglong"},
        headers=headers,
    )


def _send_qinglong_notify(title: str, content: str) -> bool:
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    for module_name in ("notify", "sendNotify"):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        sender = getattr(module, "send", None) or getattr(module, "sendNotify", None)
        if not callable(sender):
            continue
        try:
            sender(title, content)
            log("已通过青龙通知推送结果")
            return True
        except Exception as exc:
            log(f"[警告] 青龙通知发送失败: {exc}")
            return False
    return False


def send_notification(title: str, content: str) -> bool:
    if _send_qinglong_notify(title, content):
        return True
    channels = (
        ("PushPlus", _notify_pushplus),
        ("Server酱", _notify_serverchan),
        ("Telegram", _notify_telegram),
        ("Bark", _notify_bark),
        ("钉钉", _notify_dingtalk),
        ("飞书", _notify_feishu),
        ("企业微信", _notify_wecom),
        ("Gotify", _notify_gotify),
        ("自定义 Webhook", _notify_webhook),
    )
    sent: list[str] = []
    for name, func in channels:
        try:
            if func(title, content):
                sent.append(name)
        except Exception as exc:
            log(f"[警告] {name} 推送异常: {exc}")
    if sent:
        log(f"已通过 {'、'.join(sent)} 推送结果")
        return True
    log("未找到可用的推送渠道，本次结果仅输出到日志")
    return False


# ---------------------------------------------------------------------------
# 运行配置与主流程
# ---------------------------------------------------------------------------


@dataclass
class Options:
    game_checkin: bool = True
    games: list[str] = field(default_factory=lambda: list(DEFAULT_GAMES))
    cloud_games: list[str] = field(default_factory=lambda: list(CLOUD_GAMES))
    bbs_mode: str = "off"
    bbs_checkin: bool = True
    bbs_read: bool = True
    bbs_like: bool = True
    bbs_share: bool = True
    cancel_like: bool = True
    forums: list[int] = field(default_factory=lambda: [5, 2])
    post_limit: int = 5
    delay: tuple[float, float] = (1.0, 3.0)
    retries: int = 3
    notify: bool = True
    dry_run: bool = False
    blacklist: dict[str, set[str]] = field(default_factory=dict)


def build_options(args: argparse.Namespace) -> Options:
    opts = Options()

    raw_games = env_raw("MYS_SIGN_GAMES", "MYS_GAMES", "MYS_GAME_LIST")
    if args.games is not None:
        opts.games = parse_games(args.games)
    elif raw_games is not None:
        opts.games = parse_games(raw_games)

    opts.game_checkin = env_bool("MYS_GAME_CHECKIN", env_bool("MYS_CHECKIN", True))
    if args.no_games:
        opts.game_checkin = False

    raw_cloud = env_raw("MYS_CLOUD_GAMES")
    if raw_cloud is not None:
        opts.cloud_games = parse_cloud_games(raw_cloud)
    if args.no_cloud:
        opts.cloud_games = []

    raw_bbs = env_raw("MYS_BBS_TASKS", "MYS_BBS")
    mode = "off"
    if raw_bbs is not None:
        value = raw_bbs.strip().lower()
        if value == "auto":
            mode = "auto"
        elif value in TRUTHY:
            mode = "on"
        elif value in FALSY:
            mode = "off"
        else:
            log(f"[警告] MYS_BBS_TASKS={raw_bbs} 无法识别，按关闭处理")
    if args.bbs:
        mode = "on"
    if args.no_bbs:
        mode = "off"
    opts.bbs_mode = mode

    opts.bbs_checkin = env_bool("MYS_BBS_CHECKIN", True)
    opts.bbs_read = env_bool("MYS_BBS_READ", True)
    opts.bbs_like = env_bool("MYS_BBS_LIKE", True)
    opts.bbs_share = env_bool("MYS_BBS_SHARE", True)
    opts.cancel_like = env_bool("MYS_CANCEL_LIKE", True)
    opts.post_limit = env_int("MYS_POST_LIMIT", 5, low=1, high=20)

    raw_forums = env_str("MYS_BBS_FORUMS")
    if raw_forums:
        forums: list[int] = []
        for item in split_list(raw_forums):
            try:
                forum_id = int(item)
            except ValueError:
                log(f"[警告] 无效的社区版区 ID: {item}")
                continue
            if forum_id in BBS_FORUMS and forum_id not in forums:
                forums.append(forum_id)
            else:
                log(f"[警告] 不支持的社区版区 ID: {forum_id}")
        if forums:
            opts.forums = forums

    opts.delay = parse_delay(env_str("MYS_DELAY"))
    opts.retries = env_int("MYS_RETRY", 3, low=0, high=5)
    opts.blacklist = parse_blacklist(env_str("MYS_GAME_BLACKLIST"))
    opts.notify = env_bool("MYS_NOTIFY", True) and not args.no_notify
    opts.dry_run = args.dry_run or env_bool("MYS_DRY_RUN", False)
    return opts


def sleep_delay(opts: Options) -> None:
    low, high = opts.delay
    if high <= 0:
        return
    time.sleep(random.uniform(low, high))


def print_dry_run(accounts: list[Account], opts: Options, bbs_enabled: bool) -> None:
    log("")
    log("--dry-run：仅展示配置，不发起任何请求 --")
    log(f"游戏签到：{'开启' if opts.game_checkin else '关闭'}（{', '.join(opts.games) or '无'}）")
    log(f"云游戏签到：{', '.join(opts.cloud_games) or '无'}")
    log(
        f"米游币任务：{opts.bbs_mode}"
        f"（实际{'执行' if bbs_enabled else '不执行'}；"
        f"签到 {int(opts.bbs_checkin)} / 看帖 {int(opts.bbs_read)} / "
        f"点赞 {int(opts.bbs_like)} / 分享 {int(opts.bbs_share)}）"
    )
    log(f"社区版区：{', '.join(str(i) for i in opts.forums)}")
    log(f"请求延时：{opts.delay[0]:g}-{opts.delay[1]:g} 秒")
    log(f"验证码渠道：{SOLVER.label if SOLVER.enabled else '未配置'}")
    log(f"结果推送：{'开启' if opts.notify else '关闭'}")
    log("")
    for index, account in enumerate(accounts, start=1):
        log(f"账号 {index}：{account.label}")
        log(
            f"  cookie：{'已配置' if account.cookie else '未配置'}；"
            f"stoken：{'已配置' if account.stoken else '未配置'}"
        )
        log(f"  游戏：{', '.join(account.games) if account.games else '跟随全局'}")
        clouds = ', '.join(key for key, token in account.cloud.items() if token) or '无'
        log(f"  云游戏 token：{clouds}")


def run_account(
    client: HttpClient,
    account: Account,
    opts: Options,
    bbs_enabled: bool,
    report: AccountReport,
) -> None:
    if not account.stuid:
        log("[警告] 未能从 cookie/stoken 解析出账号 UID（ltuid/account_id），部分接口可能失败")

    games = [game for game in opts.games if not account.games or game in account.games]
    did_something = False

    if opts.game_checkin and games:
        did_something = True
        if not cookie_value(account.cookie, ("cookie_token", "cookie_token_v2")):
            if not ensure_cookie_token(client, account):
                log(
                    "[警告] cookie 中缺少 cookie_token，游戏签到可能返回 -100；"
                    "请重新抓取 cookie，或配置 stoken 让脚本自动刷新"
                )
        for game_key in games:
            checkin_game(client, account, game_key, opts, report)
            sleep_delay(opts)
    elif not opts.game_checkin:
        log("游戏签到已在配置中关闭")
    else:
        log("本次没有需要签到的游戏（检查 MYS_SIGN_GAMES 或账号的 games 配置）")

    if opts.cloud_games and any(account.cloud.get(key) for key in opts.cloud_games):
        did_something = True
        checkin_cloud_games(client, account, opts, report)
    elif opts.cloud_games:
        log("未配置云游戏 token，跳过云游戏签到")

    if bbs_enabled:
        did_something = True
        run_bbs_tasks(client, account, opts, report)

    if not did_something:
        report.info("没有启用任何任务（游戏签到 / 云游戏 / 米游币），已跳过")


def build_notify_content(
    reports: list[AccountReport], ok: int, failed: int, skipped: int
) -> str:
    lines = [time.strftime("%Y-%m-%d %H:%M:%S"), ""]
    for report in reports:
        lines.append(report.label)
        lines.extend(report.lines or ["（无执行结果）"])
        lines.append("")
    lines.append(f"汇总：成功 {ok}，失败 {failed}，跳过 {skipped}")
    lines.append(f"miys-qinglong v{VERSION}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="米游社每日签到（青龙面板脚本）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "环境变量：MYS_COOKIE、MYS_STOKEN、MYS_SIGN_GAMES、MYS_BBS_TASKS、\n"
            "MYS_CLOUD_GENSHIN_TOKEN、MYS_CLOUD_ZZZ_TOKEN、MYS_NOTIFY 等，\n"
            "完整说明见 README.md。"
        ),
    )
    parser.add_argument("--cookie", help="临时指定 cookie（多账号用 & 分隔），覆盖环境变量")
    parser.add_argument("--games", help="指定要签到的游戏，如 genshin,starrail,zzz")
    parser.add_argument("--bbs", action="store_true", help="强制开启米游币社区任务")
    parser.add_argument("--no-bbs", action="store_true", help="强制关闭米游币社区任务")
    parser.add_argument("--no-games", action="store_true", help="关闭游戏社区签到")
    parser.add_argument("--no-cloud", action="store_true", help="关闭云游戏签到")
    parser.add_argument("--no-notify", action="store_true", help="不推送结果")
    parser.add_argument("--dry-run", action="store_true", help="只展示配置，不发请求")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    parser.add_argument("--version", action="version", version=f"miys-qinglong {VERSION}")
    return parser


def main(argv: list[str] | None = None) -> int:
    global DEBUG, SOLVER
    args = build_parser().parse_args(argv)
    DEBUG = args.debug or env_bool("MYS_DEBUG", False)
    SOLVER = CaptchaSolver.from_env()
    opts = build_options(args)

    log("========================================")
    log(f"米游社签到 miys-qinglong v{VERSION}")
    log("========================================")

    accounts = parse_accounts()
    if args.cookie:
        accounts = enrich_accounts(
            [parse_account(entry) for entry in split_entries(args.cookie)]
        )
    if not accounts:
        log("[错误] 未找到账号配置：请设置环境变量 MYS_COOKIE（多账号用 & 或换行分隔）")
        return 1
    log(f"共读取到 {len(accounts)} 个账号")

    bbs_enabled = opts.bbs_mode == "on" or (
        opts.bbs_mode == "auto" and any(account.stoken for account in accounts)
    )
    if opts.bbs_mode == "auto" and not bbs_enabled:
        log("米游币任务未启用：MYS_BBS_TASKS=auto 但所有账号都没有配置 stoken")

    if opts.dry_run:
        print_dry_run(accounts, opts, bbs_enabled)
        return 0

    client = HttpClient(retries=opts.retries)
    reports: list[AccountReport] = []
    try:
        for index, account in enumerate(accounts, start=1):
            report = AccountReport(label=f"账号 {index}/{len(accounts)}：{account.label}")
            log("")
            log(f"===== {report.label} =====")
            try:
                run_account(client, account, opts, bbs_enabled, report)
            except Exception as exc:  # 单个账号异常不影响其他账号
                log(f"[FAIL] 账号执行异常: {exc}")
                if DEBUG:
                    traceback.print_exc()
                report.fail(f"账号执行异常: {exc}")
            reports.append(report)
    finally:
        client.close()

    total_ok = sum(report.success for report in reports)
    total_failed = sum(report.failed for report in reports)
    total_skipped = sum(report.skipped for report in reports)

    log("")
    log("========== 汇总 ==========")
    for report in reports:
        log(
            f"{report.label}：成功 {report.success}，失败 {report.failed}，"
            f"跳过 {report.skipped}"
        )
    log(f"合计：成功 {total_ok}，失败 {total_failed}，跳过 {total_skipped}")

    if opts.notify:
        title = f"米游社签到（成功 {total_ok} / 失败 {total_failed}）"
        content = build_notify_content(reports, total_ok, total_failed, total_skipped)
        send_notification(title, content)

    if total_failed:
        log("存在失败项，请检查上方日志")
        return 1
    log("全部任务执行完成")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("已手动中断")
        sys.exit(130)
