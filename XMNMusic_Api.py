# 本文件由“方案 A”合并改造：以新版（基于 QQ 自家 musicu.fcg / vkey 接口、可读取 JSON
# 列表形式 cookie 的实现）为主体，并在末尾追加向后兼容垫片，保证
# XMNMusic.py / XMNMusic_UI.py 中的旧调用（QQMusicAPI、load_netease_cookies、
# search(source=...)、get_mobi_rank、parse_by_tunefree）依然可用。

import json
import os
import random
import re
import logging
from typing import Optional, Dict, List, Tuple

import requests

# 配置日志
logger = logging.getLogger(__name__)


# ============================================================
# API配置常量
# ============================================================
class APIConfig:
    """API请求配置"""
    DEFAULT_TIMEOUT = 10
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    QQ_MUSIC_BASE = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    QQ_MUSIC_REFERER = "https://y.qq.com/"
    QQ_TOPLIST_URL = "https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg"
    QQ_COVER_BASE = "https://y.gtimg.cn/music/photo_new/"


# ============================================================
# 网易云 cookie 占位（兼容垫片 #1）
# ============================================================
# 原版（合并前）会通过 load_netease_cookies() 加载网易云 cookie 并设置一个全局
# netease_session。这里我们不再维护网易云搜索逻辑（旧依赖第三方 AES/RSA 加密
# 中间层），但 XMNMusic.py 仍然 from XMNMusic_Api import load_netease_cookies，
# 因此保留一个可调用、不会抛异常的空实现，保证启动链路不被打断。
netease_session = requests.Session()
netease_session.trust_env = False  # 独立直连，不走系统代理
netease_session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://music.163.com/"
})
netease_csrf = ""


def load_netease_cookies(source: str):
    """加载网易云cookie文件。
    
    Args:
        source: cookie文件路径
    """
    global netease_csrf
    
    if not source or not os.path.isfile(source):
        return
    
    try:
        with open(source, "r", encoding="utf-8-sig") as f:
            cookie_content = f.read().strip()
            
        # 解析cookie字符串 (格式: key1=value1; key2=value2)
        for part in cookie_content.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key:
                    netease_session.cookies.set(
                        key, value, 
                        domain=".music.163.com", 
                        path="/"
                    )
                    
        logger.info(f"网易云cookie已加载: {source}")
    except Exception as e:
        logger.warning(f"加载网易云cookie失败: {e}")


# ============================================================
# QQMusicAPI：以新版为核心
# ============================================================
class QQMusicAPI:
    """QQ 音乐 API 封装（基于 QQ 自家 musicu.fcg / vkey / 歌词 / 榜单接口）。

    兼容垫片：
        - __init__ 接受旧的 cookie 字符串（key=value; ...）格式，自动转成内部统一格式。
        - search() 新增 source / page / limit 等关键字参数，向下兼容 XMNMusic_UI.py 的旧调用。
        - 新增 get_mobi_rank() 与 parse_by_tunefree() 两个旧接口，内部走新版自研实现。
    """

    def __init__(self, cookie_path: str = None):
        logger.info(f"初始化QQMusicAPI cookie_path={cookie_path}")
        logger.info(f"初始化QQMusicAPI cookie_path={cookie_path}")
        self.session = requests.Session()
        self.guid = str(random.randint(1000000000, 9999999999))
        self.uin = "0"
        self._setup_headers()
        if cookie_path:
            try:
                self._load_cookies(cookie_path)
            except Exception:
                pass

    # ---------- 通用请求头 ----------
    def _setup_headers(self) -> None:
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://y.qq.com/",
            "Origin": "https://y.qq.com",
            "Accept": "application/json",
        })

    # ---------- Cookie 加载（兼容垫片 #2：同时支持 JSON 列表与字符串） ----------
    def _load_cookies(self, source: str):
        """加载 cookie。

        支持以下来源：
            1) http(s) URL，返回内容是 JSON 列表 [{name, value, domain, path}, ...]
            2) 本地文件，内容同上
            3) http(s) URL 或本地文件，内容是字符串 "k=v; k2=v2"（旧版 qq音乐.txt）
        """
        try:
            if source.startswith("http://") or source.startswith("https://"):
                resp = requests.get(source, timeout=15)
                resp.raise_for_status()
                raw = resp.text
            else:
                with open(source, "r", encoding="utf-8") as f:
                    raw = f.read()
        except Exception:
            return

        raw = (raw or "").strip()
        if not raw:
            return

        # 先尝试按新版 JSON 列表解析
        cookies_list = None
        try:
            cookies_list = json.loads(raw)
            if not isinstance(cookies_list, list):
                cookies_list = None
        except Exception:
            cookies_list = None

        if cookies_list is not None:
            for c in cookies_list:
                try:
                    if c.get("name") == "uin":
                        self.uin = c.get("value", "0")
                    domain = c.get("domain", ".qq.com")
                    path = c.get("path", "/")
                    self.session.cookies.set(
                        c["name"], c["value"],
                        domain=domain, path=path,
                    )
                except Exception:
                    continue
            return

        # 兜底：旧版字符串 cookie "k=v; k2=v2"
        # 直接写入请求头，避免与 self.session.cookies 命名空间冲突
        self.session.headers["Cookie"] = raw
        # uin 提取：只匹配作为完整 key 的 uin（前后是 ; 或字符串边界），
        # 避免误读 _qimei_q32=u0...78665... 之类长字符串里的子串
        m = re.search(r"(?:^|;\s*)uin=([^;]+?)(?:;|$)", raw)
        if m:
            self.uin = m.group(1).strip()
        # 同时设置到 session cookies jar，使 requests 自动按域发送
        for pair in raw.split(";"):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                try:
                    self.session.cookies.set(k, v, domain=".qq.com", path="/")
                except Exception:
                    pass

    # ---------- 搜索 ----------
    def search(self, keyword: str, page: int = 1, limit: int = 30,
               source: str = "qq") -> tuple[list[dict], int]:
        """统一搜索入口。

        为保持向后兼容，保留 source / page / limit 关键字参数。当前仅实现
        source == "qq"；source == "netease" 走占位逻辑（旧版网易云搜索已停用）。
        返回 (songs, total_count)；每条 song 字段：
            name, singer, album, album_mid, mid, interval, cover, platform
        """
        if source == "netease":
            # 网易云音乐搜索实现
            try:
                response = netease_session.get(
                    "https://music.163.com/api/search/get/web",
                    params={"s": keyword, "type": 1, "offset": (page - 1) * limit, "limit": limit},
                    timeout=APIConfig.DEFAULT_TIMEOUT
                )
                response.raise_for_status()
                result = response.json().get("result", {}) or {}
                songs = []
                for item in result.get("songs", []):
                    album = item.get("album", {}) or {}
                    duration_ms = int(item.get("duration", 0) or 0)
                    songs.append({
                        "name": item.get("name", ""),
                        "singer": " / ".join(x.get("name", "") for x in (item.get("artists") or [])),
                        "album": album.get("name", ""),
                        "album_mid": "",
                        "mid": str(item.get("id", "")),
                        "interval": duration_ms // 1000,
                        "cover": album.get("picUrl", ""),
                        "platform": "netease",
                    })
                total_count = int(result.get("songCount", 0) or 0)
                return songs, total_count
            except Exception as e:
                logger.warning(f"网易云搜索失败: {e}")
                return [], 0

        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        payload = {
            "req_0": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicDesktop",
                "param": {
                    "query": keyword,
                    "page_num": page,
                    "page_size": limit,
                },
            },
            "comm": {
                "uin": self.uin,
                "format": "json",
                "ct": 24,
                "cv": 0,
            },
        }
        songs = []
        total_count = 0
        try:
            resp = self.session.post(url, json=payload, timeout=APIConfig.DEFAULT_TIMEOUT)
            data = resp.json()
            song_data = data["req_0"]["data"]["body"]["song"]
            total_count = song_data.get("totalNum", 0) or 0
            for item in song_data.get("list", []):
                album = item.get("album", {}) or {}
                album_mid = album.get("mid", "")
                songs.append({
                    "id": item.get("id"),
                    "mid": item.get("mid", ""),
                    "name": item.get("title", "") or item.get("name", ""),
                    "singer": " / ".join(
                        s.get("name", "") for s in (item.get("singer") or [])
                    ),
                    "album": album.get("name", ""),
                    "album_mid": album_mid,
                    "interval": item.get("interval", 0),
                    "cover": self.get_album_cover(album_mid) if album_mid else "",
                    "platform": "qq",
                })
        except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"搜索请求失败: {e}")
            pass
        return songs, total_count

    # ---------- 旧版热歌榜（兼容垫片 #3：内部走新版 get_toplist） ----------
    def get_mobi_rank(self, period: str = "day") -> list[dict]:
        """兼容旧 UI 的热歌榜入口。

    原（合并前）该方法走 8.217.219.169:5214 中转站；新版完全自研，直接基于
    QQ 自家 toplist 接口（topid=26 即“热歌榜”），并把字段映射为旧版 UI 期望的
    name / singer / album / mid / interval / durationMs / cover / source / use_tunefree。
    period 参数保留签名以兼容旧调用，但当前仅支持日榜。
        """
        try:
            raw = self.get_toplist(top_id=26, num=50)
        except Exception:
            return []
        songs = []
        for item in raw:
            mid = item.get("mid") or item.get("id") or ""
            if not mid:
                continue
            interval = item.get("interval", 0) or 0
            songs.append({
                "name": item.get("name", ""),
                "singer": item.get("singer", ""),
                "album": item.get("album", ""),
                "mid": str(mid),
                "interval": interval,
                "durationMs": interval * 1000,
                "cover": item.get("cover") or self.get_album_cover(item.get("album_mid", "")),
                "source": "qq",
                "platform": "qq",
                "use_tunefree": True,
            })
        return songs

    # ---------- 旧版 tunefree 解析（兼容垫片 #4） ----------
    def parse_by_tunefree(self, platform: str, song_id: str,
                          quality: str = "320k") -> dict | None:
        """兼容旧 UI 的解析入口。

    根据 platform 参数分发：
        - "netease"：走网易云官方 API（player/url + song/lyric + song/detail）
        - 其他（默认 "qq"）：走 QQ 自研 get_song_url / get_lyric / get_song_detail

    返回结构保持旧版：包含 success / url / mid / cover / lyrics 字段的 dict。
        """
        platform = (platform or "qq").lower()

        # ===== 网易云解析路径 =====
        if platform == "netease":
            mid_str = str(song_id)
            bitrate = {
                "flac": 999000, "320": 320000, "128": 128000,
                "320k": 320000, "128k": 128000, "m4a": 128000,
            }.get((quality or "128").lower(), 128000)

            # 1) 拿播放链接
            audio_url = ""
            actual_quality = None  # 实际返回音质（flac/320/128/m4a），用于降级标注
            try:
                resp = netease_session.get(
                    "https://music.163.com/api/song/enhance/player/url",
                    params={"id": mid_str, "ids": f"[{mid_str}]", "br": bitrate},
                    timeout=APIConfig.DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
                url_info = ((resp.json().get("data") or [{}])[0]) or {}
                audio_url = url_info.get("url") or ""
                # 从返回的 br/type 推断实际音质（请求 flac 可能被降级为 320）
                _br = int(url_info.get("br") or 0)
                _typ = (url_info.get("type") or "").lower()
                if _typ == "m4a":
                    actual_quality = "m4a"
                elif _br >= 900000:
                    actual_quality = "flac"
                elif _br >= 300000:
                    actual_quality = "320"
                elif _br > 0:
                    actual_quality = "128"
            except Exception as e:
                logger.warning(f"网易云播放链接解析失败: {e}")
                audio_url = ""

            if not audio_url:
                return {
                    "success": False,
                    "url": "", "lyrics": "", "cover": "",
                    "mid": mid_str, "quality": quality,
                    "actual_quality": None,
                }

            # 2) 拿歌词
            lyrics = ""
            try:
                ly = netease_session.get(
                    "https://music.163.com/api/song/lyric",
                    params={"id": mid_str, "lv": -1, "kv": -1, "tv": -1},
                    timeout=APIConfig.DEFAULT_TIMEOUT,
                )
                if ly.ok:
                    lyrics = ((ly.json().get("lrc") or {}).get("lyric") or "")
            except Exception:
                pass

            # 3) 拿封面
            cover = ""
            try:
                det = netease_session.get(
                    "https://music.163.com/api/song/detail",
                    params={"ids": f"[{mid_str}]"},
                    timeout=APIConfig.DEFAULT_TIMEOUT,
                )
                if det.ok:
                    detail = ((det.json().get("songs") or [{}])[0]) or {}
                    cover = (detail.get("album") or {}).get("picUrl", "") or ""
            except Exception:
                pass

            return {
                "success": True,
                "url": audio_url,
                "lyrics": lyrics,
                "cover": cover,
                "mid": mid_str,
                "quality": quality,
                "actual_quality": actual_quality,
            }

        # ===== QQ 解析路径（默认） =====
        try:
            url = self.get_song_url(str(song_id), quality=quality)
        except Exception:
            url = None

        # 从 URL 前缀推断实际音质：F000=FLAC / M800=320K / M500=128K / C400=M4A（RS 等未知不标）
        actual_quality = None
        if url:
            _qm = re.search(r'/(F\d{3}|M\d{3}|C\d{3})', url)
            if _qm:
                _tag = _qm.group(1)
                if _tag.startswith("F"):
                    actual_quality = "flac"
                elif _tag.startswith("C"):
                    actual_quality = "m4a"
                elif _tag == "M800":
                    actual_quality = "320"
                elif _tag == "M500":
                    actual_quality = "128"

        if not url:
            return {
                "success": False,
                "url": "",
                "lyrics": "",
                "cover": "",
                "mid": str(song_id),
                "quality": quality,
                "actual_quality": None,
            }

        # 尝试拉歌词（QQ 官方接口）
        lyrics = ""
        try:
            lyrics = self.get_lyric(str(song_id)) or ""
        except Exception:
            lyrics = ""

        # 尝试取歌曲详情以补 cover
        cover = ""
        try:
            detail = self.get_song_detail(str(song_id))
            if detail:
                album_mid = detail.get("album_mid") or ""
                if album_mid:
                    cover = self.get_album_cover(album_mid)
        except Exception:
            cover = ""

        return {
            "success": True,
            "url": url,
            "lyrics": lyrics,
            "cover": cover,
            "mid": str(song_id),
            "quality": quality,
            "actual_quality": actual_quality,
        }

    # ---------- 新版自研：QQ 官方榜单 ----------
    def get_toplist(self, top_id: int = 26, num: int = 50) -> list[dict]:
        """通过 QQ 自家 toplist 接口拉榜单，返回字段：
        id, mid, name, singer, album, album_mid, interval, cover
        """
        url = "https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg"
        params = {"topid": top_id, "page": 1, "tpl": 3, "format": "json"}
        songs: list[dict] = []
        try:
            resp = self.session.get(url, params=params, timeout=APIConfig.DEFAULT_TIMEOUT)
            data = resp.json()
            for entry in (data.get("songlist") or []):
                info = entry.get("data", {}) or {}
                mid = info.get("mid", "") or info.get("songmid", "")
                if not mid:
                    continue
                album_mid = info.get("albummid", "")
                interval = info.get("interval", 0) or 0
                songs.append({
                    "id": info.get("id"),
                    "mid": mid,
                    "name": info.get("title", "") or info.get("songname", "") or info.get("name", ""),
                    "singer": " / ".join(
                        s.get("name", "") for s in (info.get("singer") or [])
                    ),
                    "album": info.get("albumname", ""),
                    "album_mid": album_mid,
                    "interval": interval,
                    "cover": self.get_album_cover(album_mid) if album_mid else "",
                })
        except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"搜索请求失败: {e}")
            pass
        return songs[:num]

    # ---------- 新版自研：QQ vkey 拿播放链接（MP3 优先，m4a 兜底） ----------
    def get_song_url(self, song_mid: str, quality: str = "auto") -> str | None:
        """通过 QQ 自家 vkey 接口拿播放链接。

        Args:
            song_mid: 歌曲 mid
            quality: 音质偏好，取值：
                - "auto"：自动按 F000 → M800 → M500 → m4a 降级（默认）
                - "flac" / "lossless"：优先 FLAC，降级到 320k → 128k → m4a
                - "320" / "320k"：只拿 320k MP3，不行降到 128k → m4a
                - "128" / "128k"：只拿 128k MP3，不行降到 m4a
                - "m4a"：只拿 m4a 兜底

        重要：RS02 不是 320k 也不是臻品，实测是 60 秒试听片段（约 0.9MB），
        绝对不能放在降级链首位！会拿到残缺文件。
        """
        # 不同 quality 对应的降级链（注意：RS02/RS03 是试听片段，全部禁用）
        chain_map = {
            "auto":     ("F000", "M800", "M500"),
            "flac":     ("F000", "M800", "M500"),
            "lossless": ("F000", "M800", "M500"),
            "320":      ("M800", "M500"),
            "320k":     ("M800", "M500"),
            "128":      ("M500",),
            "128k":     ("M500",),
            "m4a":      ("M500",),   # m4a 单独走下面兜底
        }
        chain = chain_map.get(quality.lower(), chain_map["auto"])

        # 一次 probe 拿真实 media_mid，所有档位共用
        media_mid = self._qq_probe_media_mid(song_mid)

        if quality.lower() == "m4a":
            # 用户明确要 m4a，直接走兜底（QQ 默认 m4a）
            return self._qq_vkey_default(song_mid)

        # 按音质优先级降级尝试
        for prefer in chain:
            url = self._qq_vkey_url(song_mid, media_mid, prefer=prefer)
            if url:
                return url
        # 兜底：老 vkey 接口，不带 filename（QQ 默认返回 m4a）
        return self._qq_vkey_default(song_mid)

    @staticmethod
    def _extract_media_mid(filename: str) -> str | None:
        """从 QQ 返回的 filename（如 'C400003okWvo1qZu9c.m4a'）里抽出真实 mid。"""
        m = re.match(r"(?:C\d{3}|M\d{3}|F\d{3}|RS\d{2})([0-9A-Za-z]+)\.", filename or "")
        return m.group(1) if m else None

    def _qq_probe_media_mid(self, song_mid: str) -> str:
        """不带 filename 调一次 vkey，提取真实 audio media_mid。失败则回退 song_mid。"""
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        payload = {
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "guid": self.guid,
                    "songmid": [song_mid],
                    "songtype": [0],
                    "uin": self.uin,
                    "loginflag": 1,
                    "platform": "20",
                },
            },
            "comm": {"uin": self.uin, "format": "json", "ct": 24, "cv": 0},
        }
        try:
            resp = self.session.post(url, json=payload, timeout=APIConfig.DEFAULT_TIMEOUT)
            data = resp.json().get("req_0", {}).get("data") or {}
            midurlinfo = data.get("midurlinfo") or []
            if midurlinfo:
                fn = midurlinfo[0].get("filename", "") or midurlinfo[0].get("purl", "")
                extracted = self._extract_media_mid(fn)
                if extracted:
                    return extracted
        except Exception:
            pass
        return song_mid

    def _qq_vkey_url(self, song_mid: str, media_mid: str, prefer: str = "M800") -> str | None:
        """用 vkey.GetVkeyServer 拿指定档位的播放链接。

        Args:
            song_mid: 歌曲 mid
            media_mid: probe 出来的真实音频 mid（可与 song_mid 不同）
            prefer: "RS02"=臻品(mp3), "F000"=FLAC, "M800"=320k mp3,
                    "M500"=128k mp3, "C400"=m4a
        """
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        ext_map = {"RS": "mp3", "F": "flac", "M": "mp3", "C": "m4a"}
        ext = ext_map.get(prefer[:1], "mp3")
        payload = {
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "guid": self.guid,
                    "songmid": [song_mid],
                    "songtype": [0],
                    "uin": self.uin,
                    "loginflag": 1,
                    "platform": "20",
                    "filename": [f"{prefer}{media_mid}.{ext}"],
                },
            },
            "comm": {"uin": self.uin, "format": "json", "ct": 24, "cv": 0},
        }
        try:
            resp = self.session.post(url, json=payload, timeout=APIConfig.DEFAULT_TIMEOUT)
            result = resp.json()
            data = result.get("req_0", {}).get("data") or {}
            midurlinfo = data.get("midurlinfo") or []
            if not midurlinfo:
                return None
            purl = midurlinfo[0].get("purl", "")
            sip_list = data.get("sip") or []
            if purl and sip_list:
                return sip_list[0] + purl
        except Exception:
            pass
        return None

    def _qq_vkey_default(self, song_mid: str) -> str | None:
        """老 vkey 接口兜底，不指定 filename，QQ 默认返回 m4a。"""
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        payload = {
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "guid": self.guid,
                    "songmid": [song_mid],
                    "songtype": [0],
                    "uin": self.uin,
                    "loginflag": 1,
                    "platform": "20",
                },
            },
            "comm": {
                "uin": self.uin,
                "format": "json",
                "ct": 24,
                "cv": 0,
            },
        }
        try:
            resp = self.session.post(url, json=payload, timeout=APIConfig.DEFAULT_TIMEOUT)
            result = resp.json()
            info = result["req_0"]["data"]["midurlinfo"][0]
            purl = info.get("purl", "")
            sip = result["req_0"]["data"]["sip"][0]
            if purl:
                return sip + purl
        except Exception:
            pass
        return None

    # ---------- 新版自研：封面工具 ----------
    def get_album_cover(self, album_mid: str, size: int = 300) -> str:
        if not album_mid:
            return ""
        return (
            f"https://y.gtimg.cn/music/photo_new/T002R{size}x{size}M000"
            f"{album_mid}.jpg"
        )

    # ---------- 新版自研：歌词 ----------
    def get_lyric(self, song_mid: str) -> str:
        """通过 QQ 自家 musicu.fcg 拉歌词（带 base64 解码）。

        说明：旧版 c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg 对非 web 端 cookie
        经常返回空，需要用 musicu.fcg 走 music.musichallSong.PlayLyricInfo 模块。
        歌词字段是 base64 编码，必须解码才是 LRC 明文。
        """
        import base64
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        payload = {
            "req_0": {
                "module": "music.musichallSong.PlayLyricInfo",
                "method": "GetPlayLyricInfo",
                "param": {"songMID": song_mid, "kgmid": "", "musicid": ""},
            },
            "comm": {"uin": self.uin, "format": "json", "ct": 24, "cv": 0},
        }
        try:
            resp = self.session.post(url, json=payload, timeout=APIConfig.DEFAULT_TIMEOUT)
            data = resp.json().get("req_0", {}).get("data") or {}
            lyric = data.get("lyric", "") or ""
            if not lyric:
                return ""
            # lyric 是 base64 编码，先 padding 再解码
            try:
                pad = (-len(lyric)) % 4
                lyric = base64.b64decode(lyric + "=" * pad).decode("utf-8", errors="ignore")
            except Exception:
                # 解码失败说明是明文，原样返回
                pass
            # 还原真实换行（QQ 用 \\n 转义）
            return lyric.replace("\\n", "\n").replace("\\r", "").strip()
        except Exception:
            return ""

    # ---------- 新版自研：歌曲详情 ----------
    def get_song_detail(self, song_mid: str) -> dict | None:
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        payload = {
            "req_0": {
                "module": "music.trackInfo.UniformRuleServer",
                "method": "GetTrackInfo",
                "param": {"ids": [song_mid], "types": [0]},
            },
            "comm": {
                "uin": self.uin,
                "format": "json",
                "ct": 24,
                "cv": 0,
            },
        }
        try:
            resp = self.session.post(url, json=payload, timeout=APIConfig.DEFAULT_TIMEOUT)
            data = resp.json()
            info = data["req_0"]["data"]["tracks"][0]
            album = info.get("album", {}) or {}
            return {
                "name": info.get("title", "") or info.get("name", ""),
                "singer": " / ".join(
                    s.get("name", "") for s in (info.get("singer") or [])
                ),
                "album": album.get("name", ""),
                "album_mid": album.get("mid", ""),
                "interval": info.get("interval", 0),
            }
        except Exception:
            return None