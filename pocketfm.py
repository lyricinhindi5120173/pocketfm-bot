import re
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

_APP  = "https://api.pocketfm.com"
_WEB  = "https://pocketfm.com"

# Confirmed CloudFront .m3u8 pattern (Mahagatha ep 51, xBrowser):
# https://ddqs490ahjgsl.cloudfront.net/<hash>/Default/QVBR/<hash>.m3u8
_CF_RE   = re.compile(r"https://[a-z0-9]+\.cloudfront\.net/[a-f0-9]{10,}/[^\s\"'<>]+")
_M3U8_RE = re.compile(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*")
_STRIP   = "\"' ,\\;"

_UA = (
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/112.0.0.0 Mobile Safari/537.36"
)

# OTP endpoints to try in order
_SEND_OTP_URLS = [
    _APP + "/v2/send_otp",
    _APP + "/v2/user/send_otp",
    _APP + "/v2/login/send_otp",
    _WEB + "/api/auth/send-otp",
]
_VERIFY_OTP_URLS = [
    _APP + "/v2/verify_otp",
    _APP + "/v2/user/verify_otp",
    _APP + "/v2/login/verify_otp",
    _WEB + "/api/auth/verify-otp",
]

# Episode endpoints to try in order
_EP_ENDPOINTS = [
    (_APP + "/v2/episode_info", "episode_slug"),
    (_APP + "/v2/episode_info", "slug"),
    (_APP + "/v2/get_episode",  "episode_slug"),
    (_APP + "/v2/episode",      "slug"),
]

# Show episode-list endpoints
_SHOW_ENDPOINTS = [
    _APP + "/v2/show_episodes",
    _APP + "/v2/get_show_episodes",
    _APP + "/v2/episode_list",
]


# ── Session ───────────────────────────────────────────────────────

def _session():
    s = requests.Session()
    r = Retry(
        total=3, backoff_factor=1.0,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET", "POST"}, raise_on_status=False,
    )
    a = HTTPAdapter(max_retries=r)
    s.mount("https://", a)
    s.mount("http://",  a)
    return s


# ── Headers ───────────────────────────────────────────────────────

def _app_headers(token=""):
    return {
        "User-Agent":      _UA,
        "Accept":          "application/json, text/plain, */*",
        "Content-Type":    "application/json",
        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin":          _WEB,
        "Referer":         _WEB + "/",
        "Connection":      "keep-alive",
        "access-token":    token,
        "app-version":     "9.0.0",
        "platform":        "android",
        "locale":          "IN",
        "language":        "hindi",
    }


def _web_headers(token=""):
    parts = ["locale=IN", "language=hindi"]
    if token:
        parts.insert(0, "auth-token=" + token)
    return {
        "User-Agent":                _UA,
        "Accept":                    "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language":           "en-IN,en;q=0.9,hi;q=0.8",
        "Accept-Encoding":           "gzip, deflate, br",
        "Cache-Control":             "no-cache",
        "Referer":                   _WEB + "/",
        "Upgrade-Insecure-Requests": "1",
        "Connection":                "keep-alive",
        "Cookie":                    "; ".join(parts),
    }


# ── OTP Login ─────────────────────────────────────────────────────

def send_otp(phone):
    """
    Send OTP to phone number.
    Returns (success: bool, message: str).
    """
    payload = {
        "phone":        phone,
        "country_code": "91",
        "phone_number": phone,
    }
    s = _session()
    for url in _SEND_OTP_URLS:
        try:
            r = s.post(url, json=payload, headers=_app_headers(), timeout=15)
            if r.status_code in (200, 201):
                data = r.json()
                if not data.get("error") and not data.get("is_error"):
                    return True, "OTP sent successfully"
            elif r.status_code == 422:
                return False, "Invalid phone number format."
        except requests.RequestException:
            continue
    return False, "Could not reach Pocket FM OTP service. Try again later."


def verify_otp(phone, otp):
    """
    Verify OTP and return the access token.
    Returns (success: bool, token: str, message: str).
    """
    payload = {
        "phone":        phone,
        "otp":          otp,
        "country_code": "91",
        "phone_number": phone,
    }
    s = _session()
    for url in _VERIFY_OTP_URLS:
        try:
            r = s.post(url, json=payload, headers=_app_headers(), timeout=15)
            if r.status_code not in (200, 201):
                continue
            data = r.json()
            # Try all known token key paths across API versions
            token = (
                (data.get("user_info") or {}).get("access_token") or
                (data.get("user_info") or {}).get("token")        or
                (data.get("user")      or {}).get("access_token") or
                (data.get("user")      or {}).get("token")        or
                (data.get("data")      or {}).get("access_token") or
                (data.get("data")      or {}).get("token")        or
                data.get("access_token") or
                data.get("token") or
                ""
            )
            if token:
                return True, token, "Login successful!"
            err = data.get("message") or data.get("error_message") or "Wrong OTP."
            return False, "", str(err)
        except requests.RequestException:
            continue
    return False, "", "OTP verification failed. Please try again."


# ── Stream extraction ─────────────────────────────────────────────

def _find_stream(text):
    """Find CloudFront .m3u8 URL in any text blob."""
    clean = text.replace("\\/", "/")
    try:
        alt = clean.encode("utf-8").decode("unicode_escape")
    except Exception:
        alt = clean
    for src in (clean, alt):
        hits = _CF_RE.findall(src)
        if hits:
            return hits[0].rstrip(_STRIP)
        hits = _M3U8_RE.findall(src)
        if hits:
            return hits[0].rstrip(_STRIP)
    return None


def _find_stream_in_dict(data):
    if not isinstance(data, dict):
        return None
    hit = _find_stream(json.dumps(data))
    if hit:
        return hit
    for w in ("episode_info", "episode", "data", "result", "content"):
        obj = data.get(w)
        if not isinstance(obj, dict):
            continue
        for k in ("stream_url", "audio_url", "content_url", "url",
                   "streamUrl", "audioUrl", "hls_url"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
    for k in ("stream_url", "audio_url", "content_url", "url",
               "streamUrl", "audioUrl", "hls_url"):
        v = data.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def _find_title(data, fallback):
    for w in ("episode_info", "episode", "data", "result"):
        obj = data.get(w)
        if not isinstance(obj, dict):
            continue
        for k in ("title", "name", "episode_title"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    for k in ("title", "name", "episode_title"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def _walk_for_episodes(obj, depth=0):
    if depth > 12:
        return []
    ep_keys = {"slug", "episode_slug", "id", "episode_id", "hash"}
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and ep_keys & obj[0].keys():
            return obj
        for item in obj:
            r = _walk_for_episodes(item, depth + 1)
            if r:
                return r
    elif isinstance(obj, dict):
        for key in ("episodes", "episode_list", "episodeList",
                    "tracks", "items", "data", "list"):
            val = obj.get(key)
            if isinstance(val, list) and val:
                r = _walk_for_episodes(val, depth + 1)
                if r:
                    return r
            elif isinstance(val, dict):
                for sub in ("data", "items", "list", "episodes"):
                    inner = val.get(sub)
                    if isinstance(inner, list) and inner:
                        r = _walk_for_episodes(inner, depth + 1)
                        if r:
                            return r
        for val in obj.values():
            r = _walk_for_episodes(val, depth + 1)
            if r:
                return r
    return []


def _slug_terminal(slug):
    parts = [p for p in str(slug).split("/") if p]
    return parts[-1] if parts else str(slug)


def _soup_title(soup, fallback):
    for tag, attr in [("meta", {"property": "og:title"}),
                      ("meta", {"name": "twitter:title"})]:
        n = soup.find(tag, attr)
        if n and n.get("content", "").strip():
            return n["content"].strip()
    h = soup.find("h1")
    if h:
        return h.get_text(strip=True)
    t = soup.find("title")
    if t:
        return t.get_text(strip=True)
    return fallback


# ── Episode fetchers ──────────────────────────────────────────────

def _fetch_from_page(s, episode_slug, token):
    """
    Load episode page with auth cookies.
    CloudFront .m3u8 is embedded in HTML source for purchased episodes.
    Returns (title, stream_url, status).
    """
    hdrs = _web_headers(token)
    for url in [_WEB + "/episode/" + episode_slug,
                _WEB + "/show/episode/" + episode_slug]:
        try:
            r = s.get(url, headers=hdrs, timeout=20)
        except requests.RequestException:
            continue
        if r.status_code not in (200, 304):
            continue
        soup   = BeautifulSoup(r.text, "html.parser")
        title  = _soup_title(soup, "Episode_" + episode_slug)
        stream = _find_stream(r.text)
        if stream:
            return title, stream, "OK"
        ns = soup.find("script", id="__NEXT_DATA__")
        if ns:
            try:
                payload = json.loads(ns.string or "{}")
                stream  = _find_stream(json.dumps(payload))
                if not stream:
                    stream = _find_stream_in_dict(payload)
                if stream:
                    return title, stream, "OK"
            except Exception:
                pass
        for script in soup.find_all("script"):
            stream = _find_stream(script.string or "")
            if stream:
                return title, stream, "OK"
    return None, None, "Stream not found in page source"


def _fetch_from_api(s, episode_slug, token):
    """
    Call mobile REST API for a single episode.
    Returns (title, stream_url, status).
    """
    if not token:
        return None, None, "No token — please login first with /login"
    hdrs = _app_headers(token)
    last = "All API endpoints failed"
    for base_url, param_key in _EP_ENDPOINTS:
        try:
            r = s.get(base_url, headers=hdrs, timeout=15,
                      params={param_key: episode_slug, "content": "1"})
            if r.status_code == 401:
                return None, None, "Token expired (401). Use /login to get a new one."
            if r.status_code == 403:
                return None, None, "Episode not purchased on this account (403)."
            if r.status_code != 200:
                last = "HTTP " + str(r.status_code)
                continue
            data   = r.json()
            stream = _find_stream_in_dict(data)
            title  = _find_title(data, "Episode_" + episode_slug)
            if stream:
                return title, stream, "OK"
            if data.get("is_locked") or data.get("locked"):
                return None, None, "Episode is coin-locked."
            last = "200 OK but no stream URL in response"
        except requests.RequestException as e:
            last = str(e)
    return None, None, last


# ── Public functions called by the bot ───────────────────────────

def get_episode(episode_slug, token):
    """
    Get .m3u8 stream URL for one episode.
    Returns (title, stream_url, status).
    """
    s = _session()
    # Try page scrape first (confirmed working for purchased episodes)
    title, stream, status = _fetch_from_page(s, episode_slug, token)
    if stream:
        return title, stream, "OK"
    # Fall back to API
    return _fetch_from_api(s, episode_slug, token)


def get_show_episodes(show_slug, token):
    """
    Get all episode slugs for a show.
    Returns (list_of_slugs, status).
    """
    s    = _session()
    hdrs = _app_headers(token)
    all_eps = []

    for endpoint in _SHOW_ENDPOINTS:
        offset, limit, found = 0, 100, False
        while True:
            try:
                r = s.get(endpoint, headers=hdrs, timeout=15,
                          params={"show_slug": show_slug, "offset": offset,
                                  "limit": limit, "content": "1"})
            except requests.RequestException:
                break
            if r.status_code != 200:
                break
            try:
                data = r.json()
            except Exception:
                break
            eps = _walk_for_episodes(data)
            if not eps:
                break
            all_eps.extend(eps)
            found = True
            if len(eps) < limit:
                break
            offset += limit
            time.sleep(0.2)
        if found:
            break

    if not all_eps:
        # Fallback: scrape show page
        try:
            r = s.get(_WEB + "/show/" + show_slug,
                      headers=_web_headers(token), timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                ns   = soup.find("script", id="__NEXT_DATA__")
                if ns:
                    payload = json.loads(ns.string or "{}")
                    all_eps = _walk_for_episodes(payload)
        except Exception:
            pass

    slugs = []
    for ep in all_eps:
        s_val = (
            ep.get("slug") or ep.get("episode_slug") or
            ep.get("hash") or str(ep.get("id", ""))
        )
        if s_val:
            slugs.append(_slug_terminal(s_val))

    # Also pull episode slugs directly from /episode/ links on page
    if not slugs:
        try:
            r = s.get(_WEB + "/show/" + show_slug,
                      headers=_web_headers(token), timeout=15)
            if r.status_code == 200:
                for ep_id in re.findall(r"/episode/([A-Za-z0-9_-]{6,})", r.text):
                    slugs.append(ep_id)
        except Exception:
            pass

    slugs = list(dict.fromkeys(slugs))  # deduplicate, keep order
    if slugs:
        return slugs, "OK"
    return [], "No episodes found for this show slug."
