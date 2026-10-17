"""小魔女聚合音乐网页原型。

启动：python XMNMusic_Web.py
浏览器访问：http://127.0.0.1:5050
"""

import os
import re
import json
import logging
import secrets
import threading
import time
from io import BytesIO
from flask import Flask, Response, jsonify, request, send_file, send_from_directory, stream_with_context
import requests
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC

from XMNMusic_Api import QQMusicAPI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_CANDIDATES = ("qq音乐.txt", "QQ音乐.txt")
COOKIE_FILE = next(
    (os.path.join(BASE_DIR, name) for name in COOKIE_CANDIDATES
     if os.path.isfile(os.path.join(BASE_DIR, name))),
    os.path.join(BASE_DIR, COOKIE_CANDIDATES[0]),
)
FAVORITES_FILE = os.path.join(BASE_DIR, "Favorites_Web.json")
NETEASE_COOKIE_FILE = os.path.join(BASE_DIR, "网易云.txt")
DEFAULT_COVER_FILE = os.path.join(BASE_DIR, "小魔女.jpg")
# Production frontend output. Override with XMN_MUSIC_FRONTEND_DIST when the
# built UI is stored outside the repository.
FRONTEND_DIST = os.path.abspath(os.environ.get(
    "XMN_MUSIC_FRONTEND_DIST",
    os.path.join(BASE_DIR, "frontend", "dist"),
))
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, "assets")
app = Flask(__name__)
# 终端日志（与桌面版一致）：操作过程全部记录到终端
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
app.logger.setLevel(logging.INFO)
music_api = QQMusicAPI(COOKIE_FILE if os.path.exists(COOKIE_FILE) else None)
# 当前环境可能配置了不可用的本地代理，音乐服务使用独立直连会话。
music_api.session.trust_env = False
web_session = requests.Session()
web_session.trust_env = False
netease_session = requests.Session()
netease_session.trust_env = False
netease_session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"})
stream_cache: dict[str, dict] = {}
stream_cache_lock = threading.Lock()
if os.path.isfile(NETEASE_COOKIE_FILE):
    try:
        with open(NETEASE_COOKIE_FILE, "r", encoding="utf-8-sig") as cookie_file:
            for part in cookie_file.read().strip().split(";"):
                if "=" in part:
                    key, value = part.split("=", 1)
                    if key.strip():
                        netease_session.cookies.set(key.strip(), value.strip(), domain=".music.163.com", path="/")
    except OSError:
        pass


def _netease_detail(song_ids: list) -> list[dict]:
    """批量取曲目详情，返回归一化后的列表（字段统一成老接口的命名）。

    【为什么换到 v3】实测 /api/song/detail 与 /api/search/get/web 属于同一批
    已下线端点：一旦被调用到阈值就永久返回 `{"code":405}`（body 只有 54 字节，
    songs 为空），且换 session、换 UA、清 cookie、等待数分钟都不会恢复 —— 是
    IP 级封禁。`/api/v3/song/detail` 与 `/api/search/get` 是当前存活的两条明文
    通道，压测 40 次 / 30 次零失败。

    归一化映射：ar→artists、al→album、dt(毫秒)→duration(毫秒)、
    al.picUrl→album.picUrl，让上层代码无需改动。
    """
    ids = [int(i) for i in song_ids]
    if not ids:
        return []
    out = []
    try:
        r = netease_session.get(
            "https://music.163.com/api/v3/song/detail",
            params={"c": json.dumps([{"id": i} for i in ids])}, timeout=10,
        )
        body = r.json()
    except (requests.RequestException, ValueError):
        return []
    for s in (body.get("songs") or []):
        al = s.get("al") or {}
        out.append({
            "id": s.get("id"),
            "name": s.get("name") or "",
            "fee": s.get("fee"),
            "duration": s.get("dt") or 0,
            "artists": s.get("ar") or [],
            "album": {"name": al.get("name", ""), "picUrl": al.get("picUrl", "")},
        })
    return out


def netease_search(keyword: str, page: int, limit: int) -> tuple[list[dict], int]:
    """网易云搜索。

    端点顺序有讲究：PC 端 /api/search/get 优先，/web 兜底。
    实测 /web 在连续调用后会返回 code=405（0 命中）且不会自行恢复，
    而 PC 端一直 code=200 —— 同曲免费版本回退依赖搜索，这里必须可靠。
    """
    result = {}
    for _url in ("https://music.163.com/api/search/get",
                 "https://music.163.com/api/search/get/web"):
        try:
            response = netease_session.get(
                _url,
                params={"s": keyword, "type": 1,
                        "offset": (page - 1) * limit, "limit": limit},
                timeout=10,
            )
            response.raise_for_status()
            result = response.json().get("result", {}) or {}
        except (requests.RequestException, ValueError) as exc:
            app.logger.warning(f"网易云搜索端点异常 {_url.split('/api/')[-1]}: {exc}")
            result = {}
        if result.get("songs"):
            break
    songs = []
    for item in result.get("songs", []):
        album = item.get("album", {}) or {}
        duration_ms = int(item.get("duration", 0) or 0)
        songs.append({
            "id": item.get("id"), "mid": str(item.get("id", "")),
            "name": item.get("name", ""),
            "singer": " / ".join(x.get("name", "") for x in (item.get("artists") or [])),
            "album": album.get("name", ""), "interval": duration_ms // 1000,
            "durationMs": duration_ms, "cover": album.get("picUrl", ""),
            "source": "netease", "platform": "netease",
        })
    return songs, int(result.get("songCount", 0) or 0)


def netease_toplist(playlist_id: int = 3778678, num: int = 50) -> list[dict]:
    """网易云官方榜单（默认热歌榜 id=3778678），用于站点切换与 QQ 不可用时的回退。"""
    response = netease_session.get(
        "https://music.163.com/api/playlist/detail",
        params={"id": playlist_id}, timeout=15,
    )
    response.raise_for_status()
    result = response.json().get("result") or {}
    songs: list[dict] = []
    for track in (result.get("tracks") or [])[:num]:
        song_id = track.get("id")
        if not song_id:
            continue
        artists = track.get("artists") or []
        album = track.get("album") or {}
        duration = track.get("duration") or 0
        songs.append({
            "name": track.get("name") or "",
            "singer": " / ".join(str(a.get("name") or "") for a in artists),
            "album": album.get("name") or "",
            "album_mid": "",
            "mid": str(song_id),
            "interval": duration // 1000 if isinstance(duration, int) else 0,
            "cover": album.get("picUrl") or "",
            "source": "netease",
            "platform": "netease",
        })
    return songs


def resolve_netease(song_id: str, quality: str = "m4a") -> dict:
    bitrate = {
        "flac": 999000, "320": 320000, "128": 128000, "m4a": 128000,
    }.get(quality, 128000)
    response = netease_session.get(
        "https://music.163.com/api/song/enhance/player/url",
        params={"id": song_id, "ids": json.dumps([int(song_id)]), "br": bitrate},
        timeout=10,
    )
    response.raise_for_status()
    url_info = ((response.json().get("data") or [{}])[0]) or {}
    audio_url = url_info.get("url") or ""
    # 实际返回音质（服务端可能把 flac 降级为 320），用于降级标注与扩展名
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
    else:
        actual_quality = None
    # ---- VIP/SVIP 协议层回退 ----
    # 服务端对 fee=1 的曲目只发 30 秒试听（固定 481115 字节），
    # 且任何客户端身份伪造都绕不过权限判定（前六轮实测已穷尽）。
    # 但同一首歌在曲库里存在多个 song id，各自 fee 独立：
    #   fee=0 免费 / fee=8 低音质免费 —— 这些 id 无登录态即可拿完整版。
    # 于是走「同曲免费版本回退」：搜同名同歌手，挑 fee∈{0,8} 的 id 重取。
    vip_fallback_from = None
    if not audio_url:
        _fb = _resolve_netease_vip_fallback(song_id, quality)
        if _fb.get("url"):
            url_info = _fb["info"]
            audio_url = _fb["url"]
            _br = int(url_info.get("br") or 0)
            _typ = (url_info.get("type") or "").lower()
            vip_fallback_from = str(song_id)
            song_id = str(_fb["used_id"])
            if _typ == "m4a":
                actual_quality = "m4a"
            elif _br >= 900000:
                actual_quality = "flac"
            elif _br >= 300000:
                actual_quality = "320"
            elif _br > 0:
                actual_quality = "128"
            app.logger.info(
                f"网易云VIP回退成功: 原id={vip_fallback_from} "
                f"fee={_fb.get('fee')} → 免费版本 id={song_id} fee={_fb.get('used_fee')}")

    if not audio_url:
        app.logger.warning(f"网易云解析失败: mid={song_id} 所选={quality} br={_br} 无链接")
        return {
            "success": False, "url": "", "lyrics": "", "cover": "",
            "mid": str(song_id), "quality": quality,
            "format": url_info.get("type") or "",
            "actual_quality": actual_quality,
        }
    if actual_quality and actual_quality != quality:
        app.logger.info(f"网易云音质降级: mid={song_id} 所选={quality} 实际={actual_quality}")
    else:
        app.logger.info(f"网易云解析成功: mid={song_id} 音质={actual_quality or quality}")
    lyric_response = netease_session.get(
        "https://music.163.com/api/song/lyric",
        params={"id": song_id, "lv": -1, "kv": -1, "tv": -1}, timeout=10,
    )
    lyrics = ((lyric_response.json().get("lrc") or {}).get("lyric") or "") if lyric_response.ok else ""
    _det = _netease_detail([song_id])
    cover = ((_det[0].get("album") or {}).get("picUrl", "") if _det else "")
    return {
        "success": bool(audio_url), "url": audio_url, "lyrics": lyrics,
        "cover": cover, "mid": str(song_id), "quality": quality,
        "format": url_info.get("type") or "mp3",
        "actual_quality": actual_quality,
        "vip_fallback_from": vip_fallback_from,
    }


def _netease_song_fee(song_id: str) -> int | None:
    """取曲目 fee：0=免费 1=VIP 4=需购买 8=低音质免费。失败返回 None。"""
    songs = _netease_detail([song_id])
    return songs[0].get("fee") if songs else None


def _netease_fetch_url(song_id: str, quality: str) -> dict:
    """按指定 song id 取播放信息（返回 url_info 字典，失败返回 {}）。"""
    bitrate = {
        "flac": 999000, "320": 320000, "128": 128000, "m4a": 128000,
    }.get(quality, 128000)
    try:
        r = netease_session.get(
            "https://music.163.com/api/song/enhance/player/url",
            params={"id": song_id, "ids": json.dumps([int(song_id)]), "br": bitrate},
            timeout=10,
        )
        r.raise_for_status()
        return ((r.json().get("data") or [{}])[0]) or {}
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return {}


def _resolve_netease_vip_fallback(song_id: str, quality: str = "m4a") -> dict:
    """VIP 曲目的协议层回退：找同曲免费版本 id 并取直链。

    原理见 resolve_netease 内注释。返回 {"url","info","used_id","fee","used_fee"}，
    失败返回 {}。整个过程只读曲库，不涉及任何账号凭证。
    """
    # 先确认原曲是付费档。免费曲目无链接通常是别的原因（下架/地区），
    # 回退也救不了，直接跳过省一次搜索。
    # 注意：fee 取不到（接口偶发限流返回空）时**不能**放弃 —— 回退全程只读曲库、
    # 无副作用，宁可多试一次也不要漏掉 VIP 曲目。
    fee = _netease_song_fee(song_id)
    if fee is not None and fee not in (1, 4):
        app.logger.info(f"网易云VIP回退跳过: id={song_id} fee={fee} 非付费档")
        return {}
    # 拿元数据拼搜索词
    _det = _netease_detail([song_id])
    if not _det:
        return {}
    s = _det[0]
    name = (s.get("name") or "").strip()
    artists = "/".join(a.get("name", "") for a in (s.get("artists") or []))
    dur = int((s.get("duration") or 0) // 1000)
    if not name:
        return {}
    keyword = f"{name} {artists.split('/')[0]}".strip()
    try:
        hits, _ = netease_search(keyword, page=1, limit=50)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {}
    cands = []
    for h in hits:
        if str(h.get("mid")) == str(song_id):
            continue
        if (h.get("name") or "").strip() != name:
            continue
        cands.append(h)
    # 免费档优先，其次时长最接近原曲（避开 live/remix/片段）
    def _rank(c):
        f = c.get("_fee")
        return (f not in (0, 8), abs(int(c.get("interval") or 0) - dur), int(c.get("mid") or 0))
    # 补 fee：搜索接口不返回 fee，批量查一次
    ids = [int(c["mid"]) for c in cands[:12] if str(c.get("mid", "")).isdigit()]
    if not ids:
        return {}
    fee_map = {}
    for s in _netease_detail(ids):
        try:
            fee_map[int(s.get("id"))] = s.get("fee")
        except (TypeError, ValueError):
            continue
    for c in cands[:12]:
        c["_fee"] = fee_map.get(int(c["mid"]) if str(c.get("mid", "")).isdigit() else -1)
    free = [c for c in cands[:12] if c.get("_fee") in (0, 8)]
    if not free:
        app.logger.info(f"网易云VIP回退无免费版本: id={song_id} 歌={name} 候选={len(cands)}")
        return {}
    free.sort(key=_rank)
    for c in free:
        info = _netease_fetch_url(str(c["mid"]), quality)
        url = info.get("url") or ""
        if not url:
            continue
        # 试听片段固定 481115 字节，用 size 字段直接排除
        size = int(info.get("size") or 0)
        if size == 481115:
            continue
        # 反推时长 >= 真实时长 * 0.9 才算完整版
        br = int(info.get("br") or 0)
        real = int(c.get("interval") or 0)
        if br and real and size and (size * 8 / br) < real * 0.9:
            continue
        return {"url": url, "info": info, "used_id": c["mid"],
                "fee": fee, "used_fee": c.get("_fee")}
    app.logger.info(f"网易云VIP回退候选均不可播: id={song_id} 免费候选={len(free)}")
    return {}


def resolve_qq(song_id: str, quality: str = "m4a") -> dict:
    """解析QQ音乐播放地址（与桌面版一致：音质不足时自动降级 F000→M800→M500→m4a兜底）。"""
    lyrics = music_api.get_lyric(song_id) or ""
    # 复用桌面版同款入口 get_song_url：内部按所选音质逐级降级，全部失败才兜底 m4a
    audio_url = music_api.get_song_url(song_id, quality)

    if not audio_url:
        app.logger.warning(f"QQ解析失败: mid={song_id} 所选={quality} 全链无链接")
        return {
            "success": False, "url": "", "lyrics": "", "cover": "",
            "mid": str(song_id), "quality": quality, "format": "",
            "actual_quality": None,
        }

    # 用 URL 前缀(F000/M800/M500/C400)推断实际拿到的音质
    actual_quality = None
    if quality == "m4a":
        actual_quality = "m4a"
    else:
        _m = re.search(r'/(F\d{3}|M\d{3}|C\d{3})', audio_url)
        if _m:
            _tag = _m.group(1)
            if _tag.startswith("F"):
                actual_quality = "flac"
            elif _tag.startswith("C"):
                actual_quality = "m4a"
            elif _tag == "M800":
                actual_quality = "320"
            elif _tag == "M500":
                actual_quality = "128"
        if actual_quality is None:
            actual_quality = quality  # 无前缀时以所选档位为准

    if actual_quality and actual_quality != quality:
        app.logger.info(f"QQ音质降级: mid={song_id} 所选={quality} 实际={actual_quality}")
    else:
        app.logger.info(f"QQ解析成功: mid={song_id} 音质={actual_quality or quality}")

    detail = music_api.get_song_detail(song_id) or {}
    album_mid = detail.get("album_mid") or ""
    cover = music_api.get_album_cover(album_mid, size=1500) if album_mid else ""
    return {
        "success": bool(audio_url), "url": audio_url or "", "lyrics": lyrics,
        "cover": cover, "mid": str(song_id), "quality": quality,
        "format": "m4a" if quality == "m4a" else "flac" if quality == "flac" else "mp3",
        "actual_quality": actual_quality,
    }


def resolve_song(source: str, song_id: str, quality: str) -> dict:
    """按平台执行唯一解析流程，不在失败后切换接口。"""
    if source == "netease":
        return resolve_netease(song_id, quality=quality)
    if source == "qq":
        return resolve_qq(song_id, quality=quality)
    raise ValueError("不支持的音乐来源")


def create_stream_url(audio_url: str, source: str) -> str:
    now = time.time()
    token = secrets.token_urlsafe(24)
    with stream_cache_lock:
        expired = [key for key, value in stream_cache.items() if value["expires"] <= now]
        for key in expired:
            stream_cache.pop(key, None)
        stream_cache[token] = {"url": audio_url, "source": source, "expires": now + 1800}
    return f"/api/stream/{token}"


def cover_url_with_size(url: str, size: int) -> str:
    if not url:
        return ""
    if "music.126.net" in url:
        url = re.sub(r"[?&]param=\d+y\d+", "", url)
        return f"{url}{'&' if '?' in url else '?'}param={size}y{size}"
    if "y.gtimg.cn" in url:
        return re.sub(r"T002R\d+x\d+", f"T002R{size}x{size}", url)
    return url


def fetch_cover(cover_url: str, preferred_size: int = 1500) -> bytes:
    """按指定尺寸优先获取封面，失败后降级重试。
    
    Args:
        cover_url: 封面URL
        preferred_size: 优先尝试的尺寸（1500/1200/800/500/300）
    
    Returns:
        封面图片二进制数据
    """
    if not cover_url:
        return b""
    
    referer = "https://music.163.com/" if "music.126.net" in cover_url else "https://y.qq.com/"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": referer}
    
    # QQ音乐CDN实际支持的尺寸（排除1000）
    all_sizes = (1500, 1200, 800, 500, 300)
    
    # 构建降级链：优先尺寸 -> 其他尺寸
    if preferred_size in all_sizes:
        sizes_to_try = [preferred_size] + [s for s in all_sizes if s != preferred_size]
    else:
        sizes_to_try = all_sizes
    
    last_error = "封面响应内容无效"
    for size in sizes_to_try:
        try:
            response = web_session.get(
                cover_url_with_size(cover_url, size), headers=headers, timeout=10
            )
            response.raise_for_status()
            if len(response.content) > 1024:
                return response.content
        except requests.RequestException as exc:
            last_error = str(exc)
    
    raise ValueError(last_error)


def write_tags(file_data: bytes, suffix: str, song: dict, cover_data: bytes, lyrics: str) -> bytes:
    """在内存中写入媒体标签，避免服务器残留下载临时文件。"""
    title, artist, album = song.get("name", ""), song.get("singer", ""), song.get("album", "")
    buffer = BytesIO(file_data)
    if suffix == ".mp3":
        audio = MP3(buffer, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(TALB(encoding=3, text=album))
        if cover_data:
            audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data))
        if lyrics:
            audio.tags.delall("USLT")
            audio.tags.add(USLT(encoding=3, lang="chi", desc="", text=lyrics))
        audio.save(buffer)
    elif suffix == ".m4a":
        audio = MP4(buffer)
        audio["\xa9nam"], audio["\xa9ART"], audio["\xa9alb"] = title, artist, album
        if lyrics:
            audio["\xa9lyr"] = lyrics
        if cover_data:
            audio["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
        buffer.seek(0)
        audio.save(buffer)
    elif suffix == ".flac":
        audio = FLAC(buffer)
        audio["TITLE"], audio["ARTIST"], audio["ALBUM"] = title, artist, album
        if lyrics:
            audio["LYRICS"] = lyrics
        if cover_data:
            from mutagen.flac import Picture
            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = cover_data
            audio.add_picture(picture)
        buffer.seek(0)
        audio.save(buffer)
    buffer.seek(0)
    return buffer.read()


def normalize_song(song: dict | None, source: str | None = None) -> dict:
    """Return the stable Song DTO shared by QQ, NetEase and the frontend."""
    item = dict(song or {})
    raw_source = item.get("source") or item.get("platform") or source or "qq"
    raw_source = str(raw_source).strip().lower()
    if raw_source in {"20", "qqmusic", "qq_music"}:
        raw_source = "qq"
    if raw_source not in {"qq", "netease"}:
        raw_source = str(source or "qq").strip().lower()
        if raw_source not in {"qq", "netease"}:
            raw_source = "qq"
    mid = item.get("mid") or item.get("id") or ""
    singer = item.get("singer", "")
    if isinstance(singer, (list, tuple)):
        singer = " / ".join(str(value) for value in singer)
    album = item.get("album", "")
    if isinstance(album, dict):
        album = album.get("name", "")
    try:
        interval = int(float(item.get("interval") or 0))
    except (TypeError, ValueError):
        interval = 0
    duration_ms = item.get("durationMs")
    try:
        duration_ms = int(float(duration_ms)) if duration_ms is not None else interval * 1000
    except (TypeError, ValueError):
        duration_ms = interval * 1000
    item.update({
        "mid": str(mid),
        "name": str(item.get("name") or item.get("title") or ""),
        "singer": str(singer or ""),
        "album": str(album or ""),
        "album_mid": str(item.get("album_mid") or ""),
        "interval": interval,
        "durationMs": duration_ms,
        "cover": str(item.get("cover") or ""),
        "source": raw_source,
        "platform": raw_source,
        "region": str(item.get("region") or item.get("area") or ""),
    })
    return item


def normalize_songs(songs: list[dict] | None, source: str | None = None) -> list[dict]:
    return [normalize_song(song, source=source) for song in (songs or []) if isinstance(song, dict)]


def normalize_song_detail(data: dict | None, source: str, mid: str, *, name: str = "", singer: str = "", album: str = "") -> dict:
    detail = dict(data or {})
    normalized_source = source if source in {"qq", "netease"} else "qq"
    detail.update({
        "mid": str(detail.get("mid") or mid),
        "name": str(detail.get("name") or name or ""),
        "singer": str(detail.get("singer") or singer or ""),
        "album": str(detail.get("album") or album or ""),
        "source": normalized_source,
        "platform": normalized_source,
        "url": str(detail.get("url") or ""),
        "lyrics": str(detail.get("lyrics") or ""),
        "quality": str(detail.get("quality") or "m4a"),
        "format": str(detail.get("format") or ""),
        "actual_quality": detail.get("actual_quality"),
    })
    return detail


def load_favorites() -> list[dict]:
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return normalize_songs(data) if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_favorites(items: list[dict]) -> None:
    with open(FAVORITES_FILE, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


@app.get("/assets/default-cover")
def default_cover():
    """Compatibility URL used by old clients and the new frontend."""
    # Vite copies public/assets/default-cover.webp into dist/assets. Keep the
    # legacy JPG as a fallback for an unbuilt/partially upgraded deployment.
    candidates = (
        os.path.join(FRONTEND_ASSETS, "default-cover.webp"),
        os.path.join(FRONTEND_ASSETS, "default-cover.png"),
        os.path.join(FRONTEND_ASSETS, "default-cover.jpg"),
        os.path.join(FRONTEND_ASSETS, "maido-cover-default.jpg"),
        os.path.join(BASE_DIR, "frontend", "public", "assets", "default-cover.jpg"),
        DEFAULT_COVER_FILE,
    )
    cover_file = next((path for path in candidates if os.path.isfile(path)), "")
    if not cover_file:
        return jsonify({"error": "默认封面文件不存在"}), 404
    mimetype = "image/webp" if cover_file.endswith(".webp") else "image/png" if cover_file.endswith(".png") else "image/jpeg"
    return send_file(cover_file, mimetype=mimetype, conditional=True)


@app.get("/assets/<path:filename>")
def frontend_asset(filename: str):
    """Serve Vite's hashed production assets from frontend/dist/assets."""
    if not os.path.isdir(FRONTEND_ASSETS):
        return jsonify({"error": "前端静态资源未构建"}), 404
    return send_from_directory(FRONTEND_ASSETS, filename, conditional=True)


@app.get("/favicon.svg")
def frontend_favicon():
    favicon = os.path.join(FRONTEND_DIST, "favicon.svg")
    if not os.path.isfile(favicon):
        return jsonify({"error": "前端图标未构建"}), 404
    return send_file(favicon, mimetype="image/svg+xml", conditional=True)


@app.get("/")
def index():
    index_file = os.path.join(FRONTEND_DIST, "index.html")
    if not os.path.isfile(index_file):
        return jsonify({
            "error": "前端尚未构建",
            "hint": "请运行 npm --prefix frontend run build，或设置 XMN_MUSIC_FRONTEND_DIST",
        }), 503
    return send_file(index_file, mimetype="text/html")


@app.get("/api/search")
def search():
    keyword = request.args.get("q", "").strip()
    try:
        page = max(1, min(50, int(request.args.get("page", 1))))
    except (TypeError, ValueError):
        page = 1
    if not keyword:
        return jsonify({"songs": [], "page": 1, "total_pages": 1})
    try:
        source = request.args.get("source", "qq").lower()
        if source not in ("qq", "netease"):
            source = "qq"
        used_fallback = False
        if source == "netease":
            songs, total = netease_search(keyword, page=page, limit=15)
        else:
            songs, total = music_api.search(keyword, page=page, limit=15, source="qq")
            # QQ 搜索无结果（cookie过期/无版权）时，自动切换到网易云搜索
            if not songs:
                app.logger.warning(f"QQ搜索无结果，自动切换到网易云搜索: {keyword}")
                songs, total = netease_search(keyword, page=page, limit=15)
                used_fallback = bool(songs)
    except Exception as exc:
        app.logger.exception("搜索失败")
        return jsonify({"error": f"搜索接口异常：{exc}"}), 502
    if not songs:
        app.logger.info(f"搜索: 关键词={keyword} 平台={source} -> 无结果")
        return jsonify({"error": "未搜索到歌曲，当前接口未返回有效数据"}), 404
    if total:
        total_pages = max(1, min(50, (total + 14) // 15))
    else:
        total_pages = page if len(songs) < 15 else min(50, page + 1)
    actual_source = "netease" if used_fallback else source
    songs = normalize_songs(songs, source=actual_source)
    app.logger.info(f"搜索: 关键词={keyword} 平台={actual_source} 第{page}页 -> {len(songs)}首 (总结果约{total})")
    return jsonify({"songs": songs, "page": page, "total_pages": total_pages,
                    "fallback": "netease" if used_fallback else ""})


@app.get("/api/recommend")
def recommend():
    site = request.args.get("site", "").lower()
    songs: list[dict] = []
    used_fallback = False
    if site == "netease":
        # 站点切换：网易云首页热歌榜
        try:
            songs = netease_toplist(num=50)
        except Exception:
            app.logger.exception("网易云热歌榜加载失败")
            songs = []
        if not songs:
            app.logger.warning("网易云热歌榜无数据，自动切换回QQ热歌榜")
            used_fallback = True
            try:
                songs = music_api.get_mobi_rank(period="day") or []
            except Exception:
                app.logger.exception("QQ热歌榜加载失败")
                songs = []
    else:
        try:
            songs = music_api.get_mobi_rank(period="day") or []
        except Exception:
            app.logger.exception("QQ热歌榜加载失败")
            songs = []
        # QQ 榜单不可用（cookie过期/接口异常）时，自动切换到网易云热歌榜
        if not songs:
            app.logger.warning("QQ热歌榜无数据，自动切换到网易云热歌榜")
            used_fallback = True
            try:
                songs = netease_toplist(num=50)
            except Exception:
                app.logger.exception("网易云热歌榜回退也失败")
                songs = []
    if not songs:
        return jsonify({"error": "热歌榜加载失败：QQ与网易云均无数据"}), 502
    raw_source = str(songs[0].get("source") or songs[0].get("platform") or "").lower()
    fallback = "netease" if raw_source == "netease" else "qq"
    songs = normalize_songs(songs, source=fallback)
    if used_fallback and site == "netease" and fallback == "qq":
        fallback = "qq_fallback"
    return jsonify({"songs": songs[:50], "fallback": fallback, "site": site or "qq"})


# 网易云官方榜单 ID 映射（用于站点切换时的榜单菜单；QQ top_id -> 网易云 playlist id）
# 26热歌榜->热歌榜, 27新歌榜->飙升榜(3778677新歌榜已停更), 4流行指数榜->原创榜
# 欧美/韩国/日本等网易云无对应官方榜，前端会在网易云模式下禁用这些按钮
NETEASE_TOPLIST_IDS = {26: 3778678, 27: 19723756, 4: 2884035}


@app.get("/api/toplist/<int:top_id>")
def toplist(top_id):
    site = request.args.get("site", "").lower()
    if site == "netease":
        # 站点切换：网易云榜单（26 映射热歌榜，27 映射新歌榜，其余为网易云自身榜单ID）
        playlist_id = NETEASE_TOPLIST_IDS.get(top_id, 3778678)
        songs: list[dict] = []
        try:
            songs = netease_toplist(playlist_id=playlist_id, num=50)
        except Exception:
            app.logger.exception(f"网易云榜单(playlist_id={playlist_id})加载失败")
            songs = []
        if not songs:
            app.logger.warning("网易云榜单无数据，自动切换回QQ榜单")
            try:
                songs = music_api.get_toplist(top_id=top_id, num=50)
            except Exception:
                songs = []
            fallback = "qq_fallback" if songs else ""
        else:
            fallback = "netease"
        if not songs:
            return jsonify({"error": "榜单暂无数据"}), 502
        songs = normalize_songs(songs, source=("netease" if fallback == "netease" else "qq"))
        return jsonify({"songs": songs, "top_id": top_id, "fallback": fallback, "site": "netease"})
    allowed = {26, 27, 4, 5, 6, 16, 17, 18, 19, 20, 23, 24, 25, 28, 29, 30, 31, 32, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100}
    if top_id not in allowed:
        return jsonify({"error": "不支持的榜单"}), 400
    songs = music_api.get_toplist(top_id=top_id, num=50)
    fallback = "qq"
    # QQ 榜单不可用时，自动切换到网易云热歌榜
    if not songs:
        app.logger.warning(f"QQ榜单(top_id={top_id})无数据，自动切换到网易云热歌榜")
        try:
            songs = netease_toplist(num=50)
            fallback = "netease"
        except Exception:
            app.logger.exception("网易云榜单回退也失败")
            songs = []
    if not songs:
        return jsonify({"error": "榜单暂无数据"}), 502
    榜单地区 = {5: "华语", 6: "华语", 16: "欧美", 17: "韩语", 18: "日语"}.get(top_id)
    for 歌曲 in songs:
        if fallback == "qq":
            歌曲["source"] = "qq"
            歌曲["platform"] = "qq"
        if 榜单地区:
            歌曲["region"] = 榜单地区
    songs = normalize_songs(songs, source=fallback)
    return jsonify({"songs": songs, "top_id": top_id, "fallback": fallback})


@app.get("/api/status")
def status():
    return jsonify({
        "cookie_file": os.path.basename(COOKIE_FILE) if os.path.isfile(COOKIE_FILE) else "",
        "cookie_found": os.path.isfile(COOKIE_FILE),
        "cookie_count": len(music_api.session.cookies),
        "uin": music_api.uin,
        "netease_cookie_found": os.path.isfile(NETEASE_COOKIE_FILE),
        "netease_cookie_count": len(netease_session.cookies),
    })


@app.get("/api/song/<mid>")
def song_detail(mid):
    source = request.args.get("source", "qq").lower()
    name = request.args.get("name", "").strip()
    singer = request.args.get("singer", "").strip()
    album = request.args.get("album", "").strip()
    data: dict = {}
    try:
        data = resolve_song(source, mid, quality="m4a")
    except (ValueError, requests.RequestException, KeyError, TypeError) as exc:
        app.logger.warning("播放解析失败: %s", exc)
    # QQ 不可用（cookie过期/无版权）时，自动切换到网易云同名歌曲播放
    if source == "qq" and not data.get("url"):
        if name:
            app.logger.warning(f"QQ播放不可用，自动切换网易云: 歌={name} 歌手={singer or '-'}")
            candidates: list[dict] = []
            try:
                candidates, _ = netease_search(f"{name} {singer}".strip(), page=1, limit=5)
            except Exception:
                app.logger.exception("网易云搜索回退失败")
            if candidates:
                try:
                    data = resolve_song("netease", candidates[0]["mid"], quality="m4a")
                except Exception:
                    app.logger.exception("网易云播放解析失败")
                    data = {}
                if data.get("url"):
                    source = "netease"
                    app.logger.info(f"已切换到网易云播放: {candidates[0]['name']} mid={candidates[0]['mid']}")
    if not data.get("url"):
        app.logger.warning(f"播放解析无链接: mid={mid} 平台={source}")
        return jsonify({"error": "未获取到播放链接（QQ与网易云均失败）"}), 502
    data = normalize_song_detail(data, source, mid, name=name, singer=singer, album=album)
    data["url"] = create_stream_url(data["url"], source)
    return jsonify(data)


@app.get("/api/resolve/<mid>")
def resolve(mid):
    quality = request.args.get("quality", "m4a").lower()
    if quality not in ("flac", "320", "128", "m4a"):
        return jsonify({"error": "不支持的音质参数"}), 400
    source = request.args.get("source", "qq").lower()
    try:
        data = resolve_song(source, mid, quality=quality)
    except (ValueError, requests.RequestException, KeyError, TypeError) as exc:
        app.logger.warning("链接解析失败: %s", exc)
        return jsonify({"error": f"链接解析失败：{exc}"}), 502
    if not data.get("url"):
        return jsonify({"error": "未获取到播放链接"}), 502
    data = normalize_song_detail(data, source, mid)
    return jsonify(data)


@app.get("/api/stream/<token>")
def stream_audio(token):
    with stream_cache_lock:
        item = stream_cache.get(token)
    if not item or item["expires"] <= time.time():
        return jsonify({"error": "播放链接已过期，请重新选择歌曲"}), 410

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com/" if item["source"] == "netease" else "https://y.qq.com/",
    }
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]
    try:
        upstream = web_session.get(item["url"], headers=headers, stream=True, timeout=(10, 30))
        upstream.raise_for_status()
    except requests.RequestException as exc:
        app.logger.warning("播放流请求失败: %s", exc)
        return jsonify({"error": "音频流请求失败"}), 502

    response_headers = {
        key: value for key, value in upstream.headers.items()
        if key.lower() in ("content-type", "content-length", "content-range", "accept-ranges")
    }

    @stream_with_context
    def generate():
        try:
            for chunk in upstream.iter_content(64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(generate(), status=upstream.status_code, headers=response_headers)


@app.get("/api/favorites")
def favorites():
    return jsonify(load_favorites())


@app.post("/api/favorites")
def update_favorites():
    song = request.get_json(silent=True) or {}
    if not song.get("mid"):
        return jsonify({"error": "歌曲缺少 ID"}), 400
    source = str(song.get("source") or song.get("platform") or "qq").lower()
    song = normalize_song(song, source=source)
    source = song["source"]
    items = load_favorites()
    key = song["mid"]
    items = [item for item in items if not (
        str(item.get("mid", "")) == key
        and (item.get("source") or item.get("platform") or "qq") == source
    )]
    if request.args.get("active", "1") == "1":
        items.append(song)
    save_favorites(items)
    return jsonify({"items": items})


@app.get("/api/cover")
def cover_download():
    try:
        data = fetch_cover(request.args.get("url", ""))
    except (requests.RequestException, ValueError) as exc:
        app.logger.warning("封面下载失败: %s", exc)
        return jsonify({"error": f"封面下载失败：{exc}"}), 502
    if not data:
        return jsonify({"error": "封面下载失败"}), 502
    return app.response_class(data, mimetype="image/jpeg", headers={"Content-Disposition": "attachment; filename=cover.jpg"})


@app.get("/api/download/<mid>")
def download(mid):
    song_name = request.args.get("name", "music")
    singer = request.args.get("singer", "").strip()
    album = request.args.get("album", "").strip()
    quality = request.args.get("quality", "320").lower()
    cover_size = int(request.args.get("coverSize", "1200"))  # 默认1200=高清（与桌面版一致）

    if quality not in ("flac", "320", "128", "m4a"):
        return jsonify({"error": "不支持的音质参数"}), 400

    # 验证封面尺寸
    if cover_size not in (1500, 1200, 800, 500, 300):
        cover_size = 1200  # 无效尺寸时使用默认值

    source = request.args.get("source", "qq").lower()
    app.logger.info(f"下载请求: 歌={song_name} 歌手={singer or '-'} 音质={quality} 平台={source}")
    data: dict = {}
    try:
        data = resolve_song(source, mid, quality=quality)
    except (ValueError, requests.RequestException, KeyError, TypeError) as exc:
        app.logger.warning("下载解析失败: %s", exc)
    # QQ 不可用（cookie过期/无版权）时，自动切换到网易云同名歌曲下载
    if source == "qq" and not data.get("url"):
        if song_name:
            app.logger.warning(f"QQ下载不可用，自动切换网易云: 歌={song_name} 歌手={singer or '-'} 音质={quality}")
            candidates: list[dict] = []
            try:
                candidates, _ = netease_search(f"{song_name} {singer}".strip(), page=1, limit=5)
            except Exception:
                app.logger.exception("网易云搜索回退失败")
            if candidates:
                try:
                    data = resolve_song("netease", candidates[0]["mid"], quality=quality)
                except Exception:
                    app.logger.exception("网易云下载解析失败")
                    data = {}
                if data.get("url"):
                    source = "netease"
                    app.logger.info(f"已切换到网易云下载: {candidates[0]['name']} mid={candidates[0]['mid']}")
    url = data.get("url")
    if not url:
        return jsonify({"error": "未获取到下载链接（QQ与网易云均失败）"}), 502
    try:
        response = web_session.get(url, stream=True, timeout=(10, 30))
        response.raise_for_status()
    except requests.RequestException as exc:
        app.logger.warning("音频下载失败: %s", exc)
        return jsonify({"error": "音频服务器请求失败"}), 502
    file_format = str(data.get("format", "")).lower()
    # 扩展名以实际音质为准（与桌面版一致），URL/format 仅兜底：
    # flac->.flac、320/128(MP3)->.mp3、m4a(AAC)->.m4a，不把 M4A 改名成 MP3
    actual_q = data.get("actual_quality")
    _ext_map = {"flac": ".flac", "320": ".mp3", "128": ".mp3", "m4a": ".m4a"}
    suffix = _ext_map.get(actual_q) or (
        ".flac" if ".flac" in url.lower() or file_format == "flac"
        else ".m4a" if ".m4a" in url.lower() or file_format in ("m4a", "aac")
        else ".mp3"
    )
    display_name = f"{singer}-{song_name}" if singer else song_name
    safe_name = re.sub(r'[<>:"/\\|?*]', "", display_name).strip() or "music"
    # 降级标注：实际音质低于所选时，文件名加【128KBPS】（与桌面版一致，未降级不标）
    if actual_q:
        _rank = {"m4a": 1, "128": 2, "320": 3, "flac": 4}
        _label = {"flac": "FLAC", "320": "320KBPS", "128": "128KBPS", "m4a": "128KBPS"}
        if quality in _rank and actual_q in _label and _rank[actual_q] < _rank[quality]:
            safe_name = f"{safe_name}【{_label[actual_q]}】"
            app.logger.info(f"降级下载标注: 所选={quality} 实际={actual_q} -> {safe_name}{suffix}")
    file_data = response.content
    response.close()
    # 封面获取/标签写入是增强功能：失败只记日志，照常返回音频（与桌面版行为一致）
    try:
        cover_data = b""
        if data.get("cover"):
            try:
                cover_data = fetch_cover(data.get("cover", ""), preferred_size=cover_size)
            except Exception as exc:
                app.logger.warning("封面获取失败(跳过封面): %s", exc)
        song = {
            "name": song_name,
            "singer": singer,
            "album": request.args.get("album", ""),
        }
        file_data = write_tags(file_data, suffix, song, cover_data, data.get("lyrics", ""))
    except Exception as exc:
        app.logger.warning("写入音乐标签失败(跳过标签，照常下载): %s", exc)
    app.logger.info(
        f"下载完成: 文件={safe_name}{suffix} 大小={len(file_data) / 1024 / 1024:.1f}MB "
        f"歌词={'有' if data.get('lyrics') else '无'} 封面={'有' if cover_data else '无'}"
    )
    mime_types = {".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4"}
    return send_file(
        BytesIO(file_data),
        as_attachment=True,
        download_name=safe_name + suffix,
        mimetype=mime_types[suffix],
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("XMN_MUSIC_PORT", "5050")), debug=False)
