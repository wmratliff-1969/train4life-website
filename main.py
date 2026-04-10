from flask import (Flask, render_template, redirect, url_for, session,
                   request, jsonify, flash, Response)
import os, json, hashlib, datetime, re, base64, uuid, threading, time, secrets
from collections import defaultdict
from functools import wraps
try:
    import requests as _http
    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

# Flask-SocketIO — optional, gracefully degrades to HTTP polling if missing
try:
    from flask_socketio import SocketIO as _SocketIO, emit as _sio_emit, \
        join_room as _sio_join, leave_room as _sio_leave
    _SIO_OK = True
except ImportError:
    _SIO_OK = False

# Load stripe conditionally so app works without it
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'train4life-secret-2026-change-in-prod')

# ── SocketIO + WebRTC live state ───────────────────────────────────────────────
if _SIO_OK:
    socketio = _SocketIO(app, cors_allowed_origins='*', async_mode='eventlet',
                         logger=False, engineio_logger=False)
else:
    socketio = None

_sio_lock             = threading.Lock()
_sio_broadcaster      = None   # socket-id of Jeff's broadcasting session
_sio_viewers          = {}     # sid -> {email, name}
_sio_broadcast_token  = None   # short-lived token issued at /admin/live page load
_online_users         = {}     # sid -> {email, name, last_seen} — socket-connected members
_http_online          = {}     # email -> {name, last_seen}  — HTTP-ping-based presence (app + web)
_pending_calls        = {}     # member_email -> {caller_name, from_sid, chat_id, expires_at}

import markupsafe
@app.template_filter('linkify')
def linkify_filter(text):
    """Turn URLs in text into clickable <a> tags."""
    escaped = str(markupsafe.escape(text))
    linked  = re.sub(
        r'(https?://[^\s<>"]+)',
        r'<a href="\1" target="_blank" rel="noopener" style="color:#4aecd4;text-decoration:underline;">\1</a>',
        escaped,
    )
    return markupsafe.Markup(linked)
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)

# Stripe config
STRIPE_PUBLIC_KEY  = os.environ.get('STRIPE_PUBLIC_KEY', '')
STRIPE_SECRET_KEY  = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
if STRIPE_AVAILABLE and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5001')

# ── Live stream status ────────────────────────────────────────────────────────
#
# TO GO LIVE:
# 1. Set LIVE_COUNTDOWN_TO to your showtime
#    (ISO format: 2026-04-04T18:00:00-06:00)
# 2. Set LIVE_STATUS = "countdown"
# 3. Bar shows live countdown to all visitors
# 4. When show starts: LIVE_STATUS = "live"
# 5. After show: LIVE_STATUS = "off"
#    clear LIVE_COUNTDOWN_TO
#
# LIVE_STATUS values: "off" | "countdown" | "live"
# Change in Railway Variables dashboard — no deploy needed
LIVE_STATUS = os.environ.get('LIVE_STATUS', 'off').strip().lower()
if LIVE_STATUS not in ('off', 'countdown', 'live'):
    LIVE_STATUS = 'off'
IS_LIVE = (LIVE_STATUS == 'live')  # backwards-compat for /live page

# Countdown target — ISO datetime string (e.g. "2026-04-04T18:00:00-06:00")
# Only used when LIVE_STATUS = "countdown"
LIVE_COUNTDOWN_TO = os.environ.get('LIVE_COUNTDOWN_TO', '').strip()

# Status bar message — auto-set by state, or override with LIVE_STATUS_MESSAGE
_default_messages = {
    'off':       '',
    'countdown': '🔴 GOING LIVE IN',
    'live':      '🔴 WE ARE LIVE RIGHT NOW!',
}
LIVE_STATUS_MESSAGE = os.environ.get('LIVE_STATUS_MESSAGE', '') or _default_messages[LIVE_STATUS]

# Stripe Price IDs (set these after creating products in Stripe dashboard)
STRIPE_PRICE_MONTHLY = os.environ.get('STRIPE_PRICE_MONTHLY', '')
STRIPE_PRICE_ANNUAL  = os.environ.get('STRIPE_PRICE_ANNUAL', '')

# ── Load content ──────────────────────────────────────────────────────────────
_base = os.path.dirname(__file__)
with open(os.path.join(_base, 'data', 'content.json')) as f:
    _content = json.load(f)

ALL_VHX_VIDEOS  = _content['videos']      # 415 videos
COLLECTIONS     = _content['collections'] # 84 collections
PRODUCTS        = _content['products']    # 30 products

# Build lookup maps
_vid_by_id   = {v['id']: v for v in ALL_VHX_VIDEOS}
_coll_by_id  = {c['id']: c for c in COLLECTIONS}
_prod_by_id  = {p['id']: p for p in PRODUCTS}

# Group videos by collection id
_vids_by_coll = defaultdict(list)
for v in ALL_VHX_VIDEOS:
    cid = v.get('canonical_collection_id', '')
    if cid:
        _vids_by_coll[cid].append(v)

# Build ordered collection rows (by video count, skip tiny/empty)
COLLECTION_ROWS = sorted(
    [(cid, _coll_by_id[cid], vids)
     for cid, vids in _vids_by_coll.items()
     if cid in _coll_by_id and len(vids) >= 2],
    key=lambda x: -len(x[2])
)

# YouTube-based Express + Revelation videos (embeddable)
EXPRESS_VIDEOS = [
    {"id":"express-1","title":"EXPRESS 1","youtube_id":"OzXRBaFP3C8","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/OzXRBaFP3C8/mqdefault.jpg","is_member_only":True},
    {"id":"express-2","title":"EXPRESS 2","youtube_id":"AfDG2NfXpuY","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/AfDG2NfXpuY/mqdefault.jpg","is_member_only":True},
    {"id":"express-3","title":"EXPRESS 3","youtube_id":"mYv2AlKP1rI","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/mYv2AlKP1rI/mqdefault.jpg","is_member_only":True},
    {"id":"express-4","title":"EXPRESS 4","youtube_id":"r8ZlAUe4p1k","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/r8ZlAUe4p1k/mqdefault.jpg","is_member_only":True},
    {"id":"express-5","title":"EXPRESS 5","youtube_id":"BscrzC2yyjE","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/BscrzC2yyjE/mqdefault.jpg","is_member_only":True},
    {"id":"express-6","title":"EXPRESS 6","youtube_id":"jpRuYGwrsU0","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/jpRuYGwrsU0/mqdefault.jpg","is_member_only":True},
    {"id":"express-7","title":"EXPRESS 7","youtube_id":"Wh-FGd_Y2GM","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/Wh-FGd_Y2GM/mqdefault.jpg","is_member_only":True},
    {"id":"express-8","title":"EXPRESS 8","youtube_id":"evVWecl3e3k","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/evVWecl3e3k/mqdefault.jpg","is_member_only":True},
    {"id":"express-9","title":"EXPRESS 9","youtube_id":"06QLZvQn6aI","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/06QLZvQn6aI/mqdefault.jpg","is_member_only":True},
    {"id":"express-10","title":"EXPRESS 10","youtube_id":"qLLw-TeZRZs","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/qLLw-TeZRZs/mqdefault.jpg","is_member_only":True},
    {"id":"express-11","title":"EXPRESS 11","youtube_id":"cqZ21h5Pkr4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/cqZ21h5Pkr4/mqdefault.jpg","is_member_only":True},
    {"id":"express-12","title":"EXPRESS 12","youtube_id":"bai-J_qVhnU","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/bai-J_qVhnU/mqdefault.jpg","is_member_only":True},
    {"id":"express-13","title":"EXPRESS 13","youtube_id":"fMwf0RJgFXs","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/fMwf0RJgFXs/mqdefault.jpg","is_member_only":True},
    {"id":"express-14","title":"EXPRESS 14","youtube_id":"WoOFkIk6g0E","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/WoOFkIk6g0E/mqdefault.jpg","is_member_only":True},
    {"id":"express-15","title":"EXPRESS 15","youtube_id":"sozSthazhNo","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/sozSthazhNo/mqdefault.jpg","is_member_only":True},
    {"id":"express-16","title":"EXPRESS 16","youtube_id":"4Ifkq6BXX0Y","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/4Ifkq6BXX0Y/mqdefault.jpg","is_member_only":True},
    {"id":"express-17","title":"EXPRESS 17","youtube_id":"AfDG2NfXpuY","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/AfDG2NfXpuY/mqdefault.jpg","is_member_only":True},
    {"id":"express-18","title":"EXPRESS 18","youtube_id":"pJUtp0yuBXs","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/pJUtp0yuBXs/mqdefault.jpg","is_member_only":True},
    {"id":"express-19","title":"EXPRESS 19","youtube_id":"1wcspRrbIbM","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/1wcspRrbIbM/mqdefault.jpg","is_member_only":True},
    {"id":"express-20","title":"EXPRESS 20","youtube_id":"g5EEUkYIu7k","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/g5EEUkYIu7k/mqdefault.jpg","is_member_only":True},
    {"id":"express-21","title":"EXPRESS 21","youtube_id":"9t2e_gu8p9s","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/9t2e_gu8p9s/mqdefault.jpg","is_member_only":True},
    {"id":"express-22","title":"EXPRESS 22","youtube_id":"QdwJTQucN7U","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/QdwJTQucN7U/mqdefault.jpg","is_member_only":True},
    {"id":"express-23","title":"EXPRESS 23","youtube_id":"TsGRrNzd1k4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/TsGRrNzd1k4/mqdefault.jpg","is_member_only":True},
    {"id":"express-24","title":"EXPRESS 24","youtube_id":"6ce1FUhRuGA","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/6ce1FUhRuGA/mqdefault.jpg","is_member_only":True},
    {"id":"express-25","title":"EXPRESS 25","youtube_id":"QrzZR8VGiV4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/QrzZR8VGiV4/mqdefault.jpg","is_member_only":True},
    {"id":"express-26","title":"EXPRESS 26","youtube_id":"nRfQxL4SxS4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/nRfQxL4SxS4/mqdefault.jpg","is_member_only":True},
]
REVELATION_VIDEOS = [
    {"id":"rev-1","title":"EP1 BEFORE YOU READ IT","youtube_id":"yDF-a1WUCis","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/yDF-a1WUCis/mqdefault.jpg","is_member_only":False},
    {"id":"rev-2","title":"EP2 THE GREAT REVEAL","youtube_id":"TslYNmqcRwk","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/TslYNmqcRwk/mqdefault.jpg","is_member_only":True},
    {"id":"rev-3","title":"EP3 THE PROMISE","youtube_id":"IkMUdxygZGo","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/IkMUdxygZGo/mqdefault.jpg","is_member_only":True},
    {"id":"rev-4","title":"EP4 MYSTERY OF THE SEVEN SPIRITS","youtube_id":"XPEDZA368T0","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/XPEDZA368T0/mqdefault.jpg","is_member_only":True},
    {"id":"rev-5","title":"EP5 A STUNNING VISION","youtube_id":"vTP7mS3SzpQ","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/vTP7mS3SzpQ/mqdefault.jpg","is_member_only":True},
    {"id":"rev-6","title":"EP6 FACE-TO-FACE WITH THE KING","youtube_id":"4Rl9U3vC6aI","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/4Rl9U3vC6aI/mqdefault.jpg","is_member_only":True},
    {"id":"rev-7","title":"EP7 MYSTERY OF THE SEVEN STARS","youtube_id":"Gn_g6bS35FA","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/Gn_g6bS35FA/mqdefault.jpg","is_member_only":True},
    {"id":"rev-8","title":"EP8 DIANA AND THE EPHESIANS","youtube_id":"Gbms60MuJtg","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/Gbms60MuJtg/mqdefault.jpg","is_member_only":True},
    {"id":"rev-9","title":"EP9 COULD THIS HAPPEN TO YOUR CHURCH","youtube_id":"HgKHTjs_h1E","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/HgKHTjs_h1E/mqdefault.jpg","is_member_only":True},
    {"id":"rev-10","title":"EP10 JUST A PINCH","youtube_id":"WoOFkIk6g0E","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/WoOFkIk6g0E/mqdefault.jpg","is_member_only":True},
    {"id":"rev-11","title":"EP11 THE CHURCH THAT WOULDN'T BREAK","youtube_id":"evVWecl3e3k","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/evVWecl3e3k/mqdefault.jpg","is_member_only":True},
]
_yt_by_id = {v['id']: v for v in EXPRESS_VIDEOS + REVELATION_VIDEOS}

# ── Title parsing ──────────────────────────────────────────────────────────────
_SERIES_PATTERNS = [
    (re.compile(r'\bexpress\b', re.I), 'Express'),
    (re.compile(r'\brevelation\b|\brev\b|\bRev EP\b', re.I), 'Revelation'),
    (re.compile(r'\bbible\s*bootcamp\b|\bbootcamp\b', re.I), 'Bible Bootcamp'),
]
_EP_RE  = re.compile(r'(?:ep\.?\s*|#|\bno\.?\s*)(\d+)|\b(\d+)\b', re.I)
_SEP_RE = re.compile(r'[—–\-:|]\s*(.+)$')

def parse_video_title(title):
    t = (title or '').strip()
    series = 'Other'
    for pat, name in _SERIES_PATTERNS:
        if pat.search(t):
            series = name
            break
    ep_m  = _EP_RE.search(t)
    episode = int(ep_m.group(1) or ep_m.group(2)) if ep_m else 0
    sub_m   = _SEP_RE.search(t)
    sub     = sub_m.group(1).strip() if sub_m else ''
    display = f"{series} {episode}" if episode else series
    return {'series': series, 'episode': episode, 'subTitle': sub,
            'displayTitle': display, 'fullTitle': t}

# ── VHX API helper ─────────────────────────────────────────────────────────────
VHX_API_KEY  = os.environ.get('VHX_API_KEY', 'W8R9VxBi3sWsDk8G5ymMTpRqgXwWyU4i')
VHX_BASE_URL = 'https://api.vhx.tv'

def _vhx_auth_header():
    creds = base64.b64encode(f'{VHX_API_KEY}:'.encode()).decode()
    return {'Authorization': f'Basic {creds}'}

def _fetch_vhx_videos(per_page=100, page=1):
    """Fetch a single page of videos from the VHX API (kept for compatibility)."""
    if not _HTTP_OK:
        return []
    try:
        r = _http.get(f'{VHX_BASE_URL}/videos',
                      params={'per_page': per_page, 'page': page, 'sort': 'newest'},
                      headers=_vhx_auth_header(), timeout=20)
        if not r.ok:
            return []
        data = r.json()
        return data.get('_embedded', {}).get('videos', [])
    except Exception:
        return []


def _vhx_get_customer(email):
    """Look up a VHX customer by email. Returns customer dict or None.

    VHX API quirk: GET /customers?email=X returns {"total":1} but no _embedded.
    Workaround: if total > 0, fetch all customers and match by email client-side.
    With ~78 customers this fits in one page.
    """
    if not _HTTP_OK or not email:
        return None
    email = email.strip().lower()
    try:
        # Step 1: confirm customer exists via email filter
        r = _http.get(f'{VHX_BASE_URL}/customers',
                      params={'email': email},
                      headers=_vhx_auth_header(), timeout=10)
        if not r.ok:
            return None
        data = r.json()
        # If _embedded came back (future API fix), use it directly
        customers = data.get('_embedded', {}).get('customers', [])
        if customers:
            return customers[0]
        # If total == 0, customer doesn't exist
        if not data.get('total', 0):
            return None
        # Step 2: email filter confirmed total > 0 but gave no data.
        # Fetch full customer list and match by email.
        page = 1
        while True:
            r2 = _http.get(f'{VHX_BASE_URL}/customers',
                           params={'per_page': 100, 'page': page},
                           headers=_vhx_auth_header(), timeout=15)
            if not r2.ok:
                break
            d2 = r2.json()
            for c in d2.get('_embedded', {}).get('customers', []):
                if (c.get('email') or '').strip().lower() == email:
                    return c
            total = d2.get('total', 0)
            fetched = page * 100
            if fetched >= total:
                break
            page += 1
    except Exception:
        pass
    return None


def _vhx_customer_is_subscribed(customer):
    """Return True if a VHX customer has an active subscription.

    Real VHX customer object uses:
      subscribed_to_site: true/false
      plan: "standard" (string, not object)
    """
    if not customer:
        return False
    # Primary field from real VHX API response
    if customer.get('subscribed_to_site'):
        return True
    # plan is a string like "standard" when subscribed
    plan = customer.get('plan')
    if plan and isinstance(plan, str) and plan not in ('', 'free', 'none'):
        return True
    # Fallback for nested object shape (in case it varies)
    if isinstance(plan, dict) and plan.get('active'):
        return True
    return False


def _vhx_get_auth_token(customer_href):
    """Get a signed JWT auth token for a VHX customer. Returns token string or None."""
    if not _HTTP_OK or not customer_href:
        return None
    try:
        r = _http.get(f'{customer_href}/authorize',
                      headers=_vhx_auth_header(), timeout=10)
        if r.ok:
            return r.json().get('token')
    except Exception:
        pass
    return None


def _vhx_create_customer(email, name=''):
    """Create a new VHX customer. Returns customer dict or None."""
    if not _HTTP_OK or not email:
        return None
    try:
        payload = {'email': email}
        if name:
            payload['name'] = name
        r = _http.post(f'{VHX_BASE_URL}/customers',
                       headers=_vhx_auth_header(),
                       json=payload, timeout=10)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def _vhx_provision_user(email, users, customer, password_hash=''):
    """Create or update a users.json entry from a known VHX customer object.
    Always sets password_hash so first-login sets the user's password."""
    cid      = str(customer.get('id', ''))
    chref    = (customer.get('_links') or {}).get('self', {}).get('href', '')
    is_sub   = _vhx_customer_is_subscribed(customer)
    if email not in users:
        users[email] = {
            'name':       customer.get('name', email.split('@')[0]),
            'email':      email,
            'password':   password_hash,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'plan':       'Monthly' if is_sub else None,
            'role':       'subscriber' if is_sub else 'free',
        }
    else:
        # Always update password so VHX member's first login sets their password
        if password_hash:
            users[email]['password'] = password_hash
        if is_sub and not users[email].get('plan'):
            users[email]['plan'] = 'Monthly'
    users[email]['vhx_customer_id']   = cid
    users[email]['vhx_customer_href'] = chref
    return users


def _fetch_all_vhx_videos():
    """Fetch ALL videos from the VHX API, looping through every page."""
    if not _HTTP_OK:
        return []
    all_videos = []
    page = 1
    try:
        while True:
            r = _http.get(f'{VHX_BASE_URL}/videos',
                          params={'per_page': 100, 'page': page, 'sort': 'newest'},
                          headers=_vhx_auth_header(), timeout=30)
            if not r.ok:
                break
            data = r.json()
            videos = data.get('_embedded', {}).get('videos', [])
            if not videos:
                break
            all_videos.extend(videos)
            total = data.get('total', 0)
            if len(all_videos) >= total:
                break
            page += 1
    except Exception:
        pass
    return all_videos

def _vhx_video_to_curator(v):
    """Shape a raw VHX API video object into our curator format."""
    vid_id   = str(v.get('id') or v.get('_id', ''))
    title    = v.get('title') or v.get('name') or 'Untitled'
    parsed   = parse_video_title(title)
    thumb    = ''
    thumb_obj = v.get('thumbnail') or {}
    for size in ('large', 'medium', 'small'):
        link = thumb_obj.get(size) or {}
        if isinstance(link, dict):
            thumb = link.get('location') or link.get('href', '')
        elif isinstance(link, str):
            thumb = link
        if thumb:
            break
    vhx_url = (v.get('_links') or {}).get('self', {}).get('href', '') or \
              v.get('href', '') or f'https://train4life.vhx.tv/videos/{vid_id}'
    dur  = v.get('duration', '')
    tags = v.get('tags') or []
    if tags and isinstance(tags[0], dict):
        tags = [t.get('name', '') for t in tags]
    return {
        'id':           vid_id,
        'title':        title,
        'thumbnail':    thumb,
        'vhx_url':      vhx_url,
        'duration':     dur,
        'tags':         tags,
        'series':       parsed['series'],
        'episode':      parsed['episode'],
        'subTitle':     parsed['subTitle'],
        'displayTitle': parsed['displayTitle'],
        'source':       'vhx',
    }

# ── Users (simple JSON file store) ────────────────────────────────────────────
_users_path = os.path.join(_base, 'data', 'users.json')

def _load_users():
    if not os.path.exists(_users_path):
        return {}
    with open(_users_path) as f:
        return json.load(f)

def _save_users(users):
    with open(_users_path, 'w') as f:
        json.dump(users, f, indent=2)

def _hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

JEFF_EMAIL = 'jeff@fastfitbootcamps.com'

def _ensure_jeff_account():
    """Create/update Jeff's member account at startup so it always exists."""
    users = _load_users()
    if JEFF_EMAIL not in users:
        users[JEFF_EMAIL] = {
            'name':       'Jeff',
            'email':      JEFF_EMAIL,
            'password':   '3a95fbcc0358bd08e7fc4e471238e757491825dd1e4cd97ece1ef5b74888e27c',  # Jeff2026
            'plan':       'express',
            'created_at': datetime.datetime.utcnow().isoformat(),
        }
        _save_users(users)
    else:
        # Ensure name is always "Jeff" for this account
        if users[JEFF_EMAIL].get('name') != 'Jeff':
            users[JEFF_EMAIL]['name'] = 'Jeff'
            _save_users(users)

def _current_user():
    """Return the current user's data dict, or None."""
    if not session.get('logged_in'):
        return None
    users = _load_users()
    return users.get(session.get('user_email'))

def _viewer_section(user=None):
    """Return the current viewer's program section: 'express', 'bible', or 'both'.

    Priority:
      1. Explicit ``section`` field on the user record (admin-settable)
      2. ``plan`` field — 'express' maps to express section
      3. Default 'both' — all other subscribers see every live stream
    """
    if user is None:
        user = _current_user()
    if not user:
        return 'both'
    sec = user.get('section', '').strip().lower()
    if sec in ('express', 'bible'):
        return sec
    plan = (user.get('plan') or '').strip().lower()
    if plan == 'express':
        return 'express'
    if plan in ('bible', 'bible_bootcamp'):
        return 'bible'
    return 'both'

def _is_subscribed(user=None):
    """Return True if user has an active subscription."""
    if user is None:
        user = _current_user()
    if not user:
        return False
    plan = user.get('plan')
    if not plan:
        return False
    # Check expiry if set
    expires = user.get('subscription_expires')
    if expires:
        try:
            exp_dt = datetime.datetime.fromisoformat(expires)
            if exp_dt < datetime.datetime.now(datetime.timezone.utc):
                return False
        except Exception:
            pass
    return True

# ── Auth decorator ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

# ── Helpers ────────────────────────────────────────────────────────────────────
def purchasable_products():
    return [p for p in PRODUCTS if p.get('video_count', 0) > 0 and p.get('price')]

def get_product_videos(product_id):
    product = _prod_by_id.get(product_id)
    if not product:
        return []
    vhx_id = product.get('vhx_id', '')
    if not vhx_id:
        return []
    return [v for v in ALL_VHX_VIDEOS if int(vhx_id) in (v.get('product_ids') or [])]

def _video_is_member_only(video):
    """Return True if this video requires a subscription to watch."""
    # YouTube-based videos use is_member_only field we set above
    if 'is_member_only' in video:
        return video['is_member_only']
    # VHX videos: use is_free field from content.json
    return not video.get('is_free', False)

# ── Forum helpers ──────────────────────────────────────────────────────────────
_forum_path = os.path.join(_base, 'data', 'forum_posts.json')
FORUM_CATEGORIES = ['General', 'Workouts', 'Bible Study', 'Nutrition']

def _load_posts():
    if not os.path.exists(_forum_path):
        return []
    with open(_forum_path) as f:
        return json.load(f)

def _save_posts(posts):
    with open(_forum_path, 'w') as f:
        json.dump(posts, f, indent=2)

# ── Messages helpers ───────────────────────────────────────────────────────────
_messages_path = os.path.join(_base, 'data', 'messages.json')
_reads_path    = os.path.join(_base, 'data', 'message_reads.json')
_easylist_path = os.path.join(_base, 'data', 'easylist_pending.json')
_msg_lock      = threading.Lock()
_easylist_lock = threading.Lock()
_rooms_lock    = threading.Lock()
_active_rooms  = {}   # chat_id -> {'url', 'room', 'expires_at'}

CHAT_IDS = ['announcements', 'express', 'bible']

def _load_messages():
    if not os.path.exists(_messages_path):
        return {c: [] for c in CHAT_IDS}
    with open(_messages_path) as f:
        return json.load(f)

def _save_messages(data):
    with open(_messages_path, 'w') as f:
        json.dump(data, f, indent=2)

def _load_reads():
    if not os.path.exists(_reads_path):
        return {}
    with open(_reads_path) as f:
        return json.load(f)

def _save_reads(data):
    with open(_reads_path, 'w') as f:
        json.dump(data, f, indent=2)

def _post_message(chat_id, sender_id, sender_name, content, is_admin=False):
    with _msg_lock:
        data = _load_messages()
        if chat_id not in data:
            data[chat_id] = []
        msg = {
            'id':          str(uuid.uuid4()),
            'sender_id':   sender_id,
            'sender_name': sender_name,
            'content':     content,
            'created_at':  datetime.datetime.utcnow().isoformat() + 'Z',
            'is_admin':    is_admin,
        }
        data[chat_id].append(msg)
        data[chat_id] = data[chat_id][-500:]   # keep last 500 per chat
        _save_messages(data)
        return msg

def _post_and_broadcast(chat_id, sender_id, sender_name, content, is_admin=False):
    """Post a message and push to SocketIO room for real-time delivery."""
    msg = _post_message(chat_id, sender_id, sender_name, content, is_admin)
    if socketio:
        try:
            socketio.emit('new_message', msg, to=f'chat:{chat_id}')
        except Exception:
            pass
    return msg

def _member_dm_id(email1, email2):
    """Consistent chat-id for a member↔member DM (order-independent)."""
    return 'mdm:' + ':'.join(sorted([email1.lower(), email2.lower()]))

def _get_member_conversations(email):
    """Return all member-to-member DM threads involving this email."""
    with _msg_lock:
        data = _load_messages()
    convos = []
    for key, msgs in data.items():
        if not key.startswith('mdm:'):
            continue
        parts = key[4:].split(':')
        if email.lower() not in [p.lower() for p in parts]:
            continue
        other = next((p for p in parts if p.lower() != email.lower()), None)
        last  = msgs[-1] if msgs else None
        convos.append({'chat_id': key, 'other_email': other, 'last_message': last})
    convos.sort(key=lambda c: c['last_message']['created_at'] if c['last_message'] else '', reverse=True)
    return convos

def _get_messages(chat_id, limit=50, since=None):
    with _msg_lock:
        data  = _load_messages()
        msgs  = data.get(chat_id, [])
        if since:
            msgs = [m for m in msgs if m['created_at'] > since]
        return msgs[-limit:]

def _mark_read(email, chat_id):
    with _msg_lock:
        reads = _load_reads()
        if email not in reads:
            reads[email] = {}
        reads[email][chat_id] = datetime.datetime.utcnow().isoformat() + 'Z'
        _save_reads(reads)

def _get_unread_count(email):
    with _msg_lock:
        data       = _load_messages()
        reads      = _load_reads()
        user_reads = reads.get(email, {})
        count      = 0
        for chat_id in CHAT_IDS:
            last_read = user_reads.get(chat_id, '')
            for m in data.get(chat_id, []):
                if m['sender_id'] == email:
                    continue
                if not last_read or m['created_at'] > last_read:
                    count += 1
        dm_key    = f'dm:{email}'
        last_read = user_reads.get(dm_key, '')
        for m in data.get(dm_key, []):
            if m['sender_id'] == email:
                continue
            if not last_read or m['created_at'] > last_read:
                count += 1
        # member-to-member DMs
        for key, msgs in data.items():
            if not key.startswith('mdm:'):
                continue
            parts = key[4:].split(':')
            if email.lower() not in [p.lower() for p in parts]:
                continue
            last_read = user_reads.get(key, '')
            for m in msgs:
                if m['sender_id'] == email:
                    continue
                if not last_read or m['created_at'] > last_read:
                    count += 1
        return count

def _ios_auth(email, token):
    """Return True if the token matches what is stored for this user."""
    if not email or not token:
        return False
    users = _load_users()
    user  = users.get(email.lower().strip(), {})
    return user.get('ios_token') == token

def _fire_onesignal(title, body):
    """Send a OneSignal push to all subscribers. Runs in a background thread."""
    import requests as _req
    def _send():
        try:
            r = _req.post(
                'https://onesignal.com/api/v1/notifications',
                headers={
                    'Authorization': 'Basic os_v2_app_qp4xpakk3nbdxnws2daht3syo7rialml4xnu26fn25hkmirrb7lhwtdkc7trtob66lt24iqidvhr644pgiochwchlgrlmkc7fp62fvq',
                    'Content-Type':  'application/json',
                },
                json={
                    'app_id':            '83f97781-4adb-423b-b6d2-d0c079ee5877',
                    'included_segments': ['All'],
                    'headings':          {'en': title},
                    'contents':          {'en': body},
                    'ios_sound':         'default',
                },
                timeout=5,
            )
            print(f'[PUSH] sent "{title}" → {r.status_code} {r.text[:120]}')
        except Exception as e:
            print(f'[PUSH] error: {e}')
    t = threading.Thread(target=_send, daemon=True)
    t.start()

def _send_onesignal_push_msg(heading, body_text, segment='All', filters=None):
    """Wrapper kept for backwards compat — delegates to _fire_onesignal."""
    _fire_onesignal(heading, body_text)


def _send_apns_push(device_token, title, body, extra_data=None, notif_type='message'):
    """Send a push notification directly via APNs HTTP/2 using .p8 JWT auth.
    Requires APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, APNS_KEY env vars.
    Set APNS_SANDBOX=true for Xcode development builds (uses sandbox endpoint).
    """
    key_id    = os.environ.get('APNS_KEY_ID', '').strip()
    team_id   = os.environ.get('APNS_TEAM_ID', '').strip()
    bundle_id = os.environ.get('APNS_BUNDLE_ID', '').strip()
    # APNS_KEY is the full .p8 PEM content; Render may store \n literally
    key_pem   = os.environ.get('APNS_KEY', '').replace('\\n', '\n').strip()
    sandbox   = os.environ.get('APNS_SANDBOX', '').lower() in ('1', 'true', 'yes')
    if not all([key_id, team_id, bundle_id, key_pem, device_token]):
        print(f'[APNs] missing config or token, skipping')
        return
    try:
        import jwt as pyjwt
        import httpx
    except ImportError as e:
        print(f'[APNs] missing dependency: {e}')
        return
    now   = int(time.time())
    token = pyjwt.encode(
        {'iss': team_id, 'iat': now},
        key_pem,
        algorithm='ES256',
        headers={'kid': key_id},
    )
    aps = {
        'alert': {'title': title, 'body': body},
        'sound': 'default',
        # Wake the app in the background so it can update state
        'content-available': 1,
    }
    payload = {'aps': aps}
    if extra_data:
        payload.update(extra_data)
    host = 'api.sandbox.push.apple.com' if sandbox else 'api.push.apple.com'
    headers = {
        'authorization':   f'bearer {token}',
        'apns-push-type':  'alert',
        'apns-topic':      bundle_id,
        'apns-priority':   '10',
        # Store notification for up to 24 h if device is unreachable
        'apns-expiration': str(now + 86400),
    }
    url = f'https://{host}/3/device/{device_token}'
    try:
        with httpx.Client(http2=True, timeout=10) as client:
            resp = client.post(url, json=payload, headers=headers)
        print(f'[APNs] {"sandbox" if sandbox else "prod"} → {device_token[:20]}... status={resp.status_code}')
        if resp.status_code != 200:
            print(f'[APNs] error body: {resp.text}')
    except Exception as e:
        print(f'[APNs] send error: {e}')


def _push_to_member(email, title, body, notif_type, extra=None):
    """Send a targeted push to a specific member.
    Uses APNs directly if apns_device_token is stored; falls back to OneSignal.
    extra: optional dict merged into the data payload (e.g. {'url': '/video-jeff'}).
    Runs in a background thread so it never blocks a request."""
    users      = _load_users()
    user       = users.get(email, {})
    apns_token = user.get('apns_device_token', '').strip()
    player_id  = user.get('onesignal_player_id', '').strip()

    if not apns_token and not player_id:
        print(f'[PUSH] no push token for {email}, skipping')
        return

    data_dict  = {'type': notif_type}
    if extra:
        data_dict.update(extra)
    extra_data = {'data': data_dict}

    def _send():
        # ── APNs (primary) ────────────────────────────────────────────
        if apns_token:
            _send_apns_push(apns_token, title, body, extra_data)
            return   # APNs succeeded (or failed silently); don't double-notify
        # ── OneSignal (fallback if no APNs token yet) ─────────────────
        api_key = os.environ.get('ONESIGNAL_API_KEY',
            'os_v2_app_qp4xpakk3nbdxnws2daht3syo7rialml4xnu26fn25hkmirrb7lhwtdkc7trtob66lt24iqidvhr644pgiochwchlgrlmkc7fp62fvq')
        app_id  = os.environ.get('ONESIGNAL_APP_ID', '83f97781-4adb-423b-b6d2-d0c079ee5877')
        onesignal_payload = {
            'app_id':             app_id,
            'include_player_ids': [player_id],
            'headings':           {'en': title},
            'contents':           {'en': body},
            'ios_sound':          'default',
            'data':               {'type': notif_type},
        }
        try:
            import requests as _rp
            resp = _rp.post(
                'https://onesignal.com/api/v1/notifications',
                headers={'Authorization': f'Basic {api_key}', 'Content-Type': 'application/json'},
                json=onesignal_payload, timeout=5,
            )
            print(f'[PUSH/OneSignal] {notif_type} → {email}: {resp.status_code} {resp.text[:120]}')
        except Exception as e:
            print(f'[PUSH/OneSignal] error sending to {email}: {e}')

    threading.Thread(target=_send, daemon=True).start()


# Ensure Jeff's member account exists on every startup
_ensure_jeff_account()

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    status, countdown_to, message, timer_for, stream_url = _get_live_vars()
    settings = _load_live_settings()
    return dict(
        is_live=(status == 'live'),
        live_status=status,
        live_status_message=message,
        live_countdown_to=countdown_to,
        live_timer_for=timer_for,
        live_stream_url=stream_url,
        viewer_section=_viewer_section(),
        banner_enabled=settings.get('banner_enabled', True),
        ticker_enabled=settings.get('ticker_enabled', False),
        ticker_text=settings.get('ticker_text', ''),
    )


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/api/live-status')
def api_live_status():
    status, countdown_to, message, timer_for, stream_url = _get_live_vars()
    # If a WebRTC broadcaster is active in memory, always report live
    # regardless of what the settings file says (guards against race
    # conditions or session check failures in broadcaster_ready handler)
    webrtc_active = (_sio_broadcaster is not None)
    if webrtc_active:
        status = 'live'
    settings = _load_live_settings()
    response = jsonify({
        'status': status,
        'countdown_to': countdown_to,
        'message': message,
        'timer_for': timer_for,
        'stream_url': stream_url,
        'webrtc_active': webrtc_active,
        'banner_enabled': settings.get('banner_enabled', True),
        'ticker_enabled': settings.get('ticker_enabled', False),
        'ticker_text': settings.get('ticker_text', ''),
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.route('/api/admin/set-timer-for', methods=['POST'])
def api_set_timer_for():
    """Session-authenticated endpoint: update only timer_for in live settings.
    Called by the admin_live page when a Show Timer For radio button is clicked."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    tf = data.get('timer_for', 'both')
    if tf not in ('both', 'express', 'bible'):
        tf = 'both'
    # Merge into current settings so no other field is overwritten
    settings = _load_live_settings()
    settings['timer_for'] = tf
    _save_live_settings(settings)
    return jsonify({'ok': True, 'timer_for': tf})


@app.route('/live')
def live():
    status, countdown_to, message, timer_for, stream_url = _get_live_vars()
    settings    = _load_live_settings()
    stream_mode = settings.get('stream_mode', '')
    return render_template('live.html',
                           is_live=(status == 'live'),
                           live_status=status,
                           live_countdown_to=countdown_to,
                           live_timer_for=timer_for,
                           live_stream_url=stream_url,
                           stream_mode=stream_mode,
                           viewer_section=_viewer_section(),
                           sio_enabled=_SIO_OK)


@app.route('/')
def index():
    sample_videos = EXPRESS_VIDEOS[:8] + REVELATION_VIDEOS[:4]
    top_programs = purchasable_products()[:8]
    return render_template('index.html',
        sample_videos=sample_videos,
        programs=top_programs,
        revelation_videos=REVELATION_VIDEOS[:4],
        stripe_public_key=STRIPE_PUBLIC_KEY)


# ── Forgot / Reset Password ────────────────────────────────────────────────────

_reset_tokens = {}   # token -> {'email': ..., 'expires': datetime}

def _make_reset_token(email):
    import secrets
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = {
        'email':   email,
        'expires': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return token

def _consume_reset_token(token):
    """Return email if token is valid and not expired, else None. Removes token."""
    entry = _reset_tokens.pop(token, None)
    if not entry:
        return None
    if datetime.datetime.utcnow() > entry['expires']:
        return None
    return entry['email']


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot_password.html', sent=False, error=None)

    email = request.form.get('email', '').strip().lower()
    if not email:
        return render_template('forgot_password.html', sent=False,
                               error='Please enter your email address.')

    token = _make_reset_token(email)

    # Try to send email via SMTP if configured
    smtp_host = os.environ.get('SMTP_HOST', '')
    sent_email = False
    if smtp_host:
        try:
            import smtplib
            from email.mime.text import MIMEText
            reset_url = f"{BASE_URL}/reset-password?token={token}"
            msg = MIMEText(
                f"Hi,\n\nClick the link below to reset your TRAIN4LIFE password "
                f"(valid for 1 hour):\n\n{reset_url}\n\nIf you didn't request this, ignore this email.",
                'plain'
            )
            msg['Subject'] = 'TRAIN4LIFE — Reset Your Password'
            msg['From']    = os.environ.get('SMTP_FROM', 'noreply@train4life.life')
            msg['To']      = email
            with smtplib.SMTP(smtp_host, int(os.environ.get('SMTP_PORT', 587))) as s:
                s.starttls()
                s.login(os.environ.get('SMTP_USER', ''), os.environ.get('SMTP_PASS', ''))
                s.sendmail(msg['From'], [email], msg.as_string())
            sent_email = True
        except Exception:
            pass

    # Show token on screen when SMTP is not configured (dev/test mode)
    dev_token = None if sent_email else token
    return render_template('forgot_password.html', sent=True,
                           email=email, dev_token=dev_token)


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token', '') or request.form.get('token', '')

    if request.method == 'GET':
        if not token or token not in _reset_tokens:
            return render_template('reset_password.html', valid=False, token=token)
        return render_template('reset_password.html', valid=True, token=token)

    # POST — save new password
    new_pw  = request.form.get('password', '').strip()
    new_pw2 = request.form.get('password2', '').strip()

    if not new_pw or len(new_pw) < 6:
        return render_template('reset_password.html', valid=True, token=token,
                               error='Password must be at least 6 characters.')
    if new_pw != new_pw2:
        return render_template('reset_password.html', valid=True, token=token,
                               error='Passwords do not match.')

    email = _consume_reset_token(token)
    if not email:
        return render_template('reset_password.html', valid=False, token=token)

    users = _load_users()
    if email not in users:
        users[email] = {'email': email, 'plan': '', 'name': ''}
    users[email]['password'] = _hash_pw(new_pw)
    _save_users(users)

    return render_template('reset_password.html', done=True)


@app.route('/browse')
@login_required
def browse():
    query = request.args.get('q', '').strip().lower()
    if query:
        results = [v for v in ALL_VHX_VIDEOS
                   if query in v['title'].lower()
                   or query in (v.get('collection_title') or '').lower()
                   or query in (v.get('description') or '').lower()]
        yt_results = [v for v in (EXPRESS_VIDEOS + REVELATION_VIDEOS)
                      if query in v['title'].lower() or query in v['series'].lower()]
        return render_template('browse.html',
            collection_rows=[], results=results + yt_results,
            query=query, express_videos=[], revelation_videos=[],
            programs=[], watch_history=[], is_subscribed=_is_subscribed())

    history_ids = session.get('watch_history', [])
    history = [_vid_by_id.get(vid) or _yt_by_id.get(vid) for vid in history_ids[:6]]
    history = [v for v in history if v]

    return render_template('browse.html',
        collection_rows=COLLECTION_ROWS[:15],
        express_videos=EXPRESS_VIDEOS,
        revelation_videos=REVELATION_VIDEOS,
        programs=purchasable_products(),
        results=None, query='',
        watch_history=history,
        is_subscribed=_is_subscribed())


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return render_template('search.html', results=[], query='')
    ql = query.lower()
    results = [v for v in ALL_VHX_VIDEOS
               if ql in v['title'].lower()
               or ql in (v.get('collection_title') or '').lower()
               or ql in (v.get('description') or '').lower()]
    yt_results = [v for v in (EXPRESS_VIDEOS + REVELATION_VIDEOS)
                  if ql in v['title'].lower() or ql in v.get('series','').lower()]
    all_results = yt_results + results
    return render_template('search.html', results=all_results, query=query)


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip().lower()
    if len(query) < 2:
        return jsonify([])
    results = []
    for v in (EXPRESS_VIDEOS + REVELATION_VIDEOS + ALL_VHX_VIDEOS):
        title = v.get('title', '')
        series = v.get('series') or v.get('collection_title') or ''
        if query in title.lower() or query in series.lower():
            results.append({
                'id': v['id'],
                'title': title,
                'series': series,
                'thumbnail': v.get('thumbnail') or (
                    'https://img.youtube.com/vi/' + v['youtube_id'] + '/mqdefault.jpg'
                    if v.get('youtube_id') else ''),
            })
        if len(results) >= 8:
            break
    return jsonify(results)


def _get_vhx_token_for_session():
    """Return a VHX auth token for the currently logged-in user, using cached href."""
    email = session.get('user_email', '')
    if not email:
        return None
    # Use cached href from session to avoid extra API call on every page
    chref = session.get('vhx_customer_href')
    if not chref:
        users = _load_users()
        user  = users.get(email, {})
        chref = user.get('vhx_customer_href', '')
        if not chref:
            customer = _vhx_get_customer(email)
            if customer:
                chref = (customer.get('_links') or {}).get('self', {}).get('href', '')
                if chref:
                    users[email]['vhx_customer_href'] = chref
                    users[email]['vhx_customer_id'] = str(customer.get('id', ''))
                    _save_users(users)
        if chref:
            session['vhx_customer_href'] = chref
    return _vhx_get_auth_token(chref) if chref else None


@app.route('/watch/<video_id>')
@login_required
def watch(video_id):
    subscribed = _is_subscribed()

    # Track history
    history = session.get('watch_history', [])
    if video_id in history:
        history.remove(video_id)
    history.insert(0, video_id)
    session['watch_history'] = history[:20]

    # YouTube-based video?
    video = _yt_by_id.get(video_id)
    if video:
        member_only = video.get('is_member_only', True)
        if member_only and not subscribed:
            return render_template('upgrade_wall.html', video=video,
                                   stripe_public_key=STRIPE_PUBLIC_KEY)
        if video.get('series') == 'EXPRESS 2026':
            related = [v for v in EXPRESS_VIDEOS if v['id'] != video_id][:8]
        else:
            related = [v for v in REVELATION_VIDEOS if v['id'] != video_id][:8]
        return render_template('watch.html', video=video, related=related,
                               player='youtube', subscribed=subscribed,
                               vhx_auth_token=None)

    # VHX video
    video = _vid_by_id.get(video_id)
    if not video:
        return redirect(url_for('browse'))

    member_only = _video_is_member_only(video)
    if member_only and not subscribed:
        return render_template('upgrade_wall.html', video=video,
                               stripe_public_key=STRIPE_PUBLIC_KEY)

    # Get VHX auth token so the embed plays without VHX paywall
    vhx_auth_token = _get_vhx_token_for_session() if subscribed else None

    cid = video.get('canonical_collection_id', '')
    related = [v for v in _vids_by_coll.get(cid, []) if v['id'] != video_id][:8]
    if not related:
        related = ALL_VHX_VIDEOS[:8]

    return render_template('watch.html', video=video, related=related,
                           player='vhx', subscribed=subscribed,
                           vhx_auth_token=vhx_auth_token)


@app.route('/programs')
def programs():
    return render_template('programs.html', programs=purchasable_products())


@app.route('/programs/<product_id>')
def program_detail(product_id):
    product = _prod_by_id.get(product_id)
    if not product:
        return redirect(url_for('programs'))
    videos = get_product_videos(product_id)
    return render_template('program_detail.html', program=product, videos=videos)


@app.route('/subscribe')
def subscribe():
    return render_template('subscribe.html', stripe_public_key=STRIPE_PUBLIC_KEY)


@app.route('/subscribe/success')
def subscribe_success():
    session_id = request.args.get('session_id')
    if session_id and STRIPE_AVAILABLE and STRIPE_SECRET_KEY:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            if checkout_session.payment_status == 'paid' and session.get('logged_in'):
                users = _load_users()
                email = session['user_email']
                if email in users:
                    plan_name = 'Annual' if 'annual' in (checkout_session.metadata or {}).get('plan', '') else 'Monthly'
                    users[email]['plan'] = plan_name
                    users[email]['stripe_customer_id'] = checkout_session.customer
                    users[email]['stripe_subscription_id'] = checkout_session.subscription
                    # Create VHX customer if they don't have one yet, so video embeds work
                    if not users[email].get('vhx_customer_id'):
                        vhx_c = _vhx_get_customer(email) or _vhx_create_customer(email, users[email].get('name', ''))
                        if vhx_c:
                            users[email]['vhx_customer_id']   = str(vhx_c.get('id', ''))
                            users[email]['vhx_customer_href'] = (vhx_c.get('_links') or {}).get('self', {}).get('href', '')
                    _save_users(users)
        except Exception:
            pass
    return render_template('subscribe_success.html')


@app.route('/subscribe/cancel')
def subscribe_cancel():
    return redirect(url_for('subscribe'))


# ── Stripe Checkout ────────────────────────────────────────────────────────────

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    if not STRIPE_AVAILABLE or not STRIPE_SECRET_KEY:
        return jsonify({'error': 'Stripe not configured'}), 503

    plan = request.json.get('plan', 'monthly') if request.is_json else request.form.get('plan', 'monthly')
    price_id = STRIPE_PRICE_ANNUAL if plan == 'annual' else STRIPE_PRICE_MONTHLY

    if not price_id:
        # Fallback: create price inline if no price ID configured
        try:
            amount = 5500 if plan == 'annual' else 699
            interval = 'year' if plan == 'annual' else 'month'
            price = stripe.Price.create(
                unit_amount=amount,
                currency='usd',
                recurring={'interval': interval},
                product_data={'name': f'TRAIN4LIFE All Access {"Annual" if plan == "annual" else "Monthly"}'},
            )
            price_id = price.id
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=BASE_URL + '/subscribe/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=BASE_URL + '/subscribe/cancel',
            customer_email=session.get('user_email'),
            metadata={'plan': plan, 'user_email': session.get('user_email', '')},
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except Exception:
            return jsonify({'error': 'Invalid signature'}), 400
    else:
        try:
            event = json.loads(payload)
        except Exception:
            return jsonify({'error': 'Bad payload'}), 400

    obj = event['data']['object']

    if event['type'] in ('checkout.session.completed', 'invoice.payment_succeeded'):
        email = obj.get('customer_email') or (obj.get('metadata') or {}).get('user_email', '')
        plan  = (obj.get('metadata') or {}).get('plan', 'monthly')
        stripe_customer_id = obj.get('customer', '')
        if email:
            users = _load_users()
            if email in users:
                users[email]['plan'] = 'Annual' if plan == 'annual' else 'Monthly'
                if stripe_customer_id:
                    users[email]['stripe_customer_id'] = stripe_customer_id
                _save_users(users)

    elif event['type'] in ('customer.subscription.created', 'customer.subscription.updated'):
        customer_id = obj.get('customer', '')
        status      = obj.get('status', '')  # active, trialing, past_due, canceled, etc.
        if customer_id and status in ('active', 'trialing'):
            users = _load_users()
            for email, u in users.items():
                if u.get('stripe_customer_id') == customer_id:
                    u['plan'] = u.get('plan') or 'Monthly'
                    break
            _save_users(users)

    elif event['type'] in ('customer.subscription.deleted', 'customer.subscription.paused'):
        customer_id = obj.get('customer', '')
        if customer_id:
            users = _load_users()
            for email, u in users.items():
                if u.get('stripe_customer_id') == customer_id:
                    u['plan'] = None
                    break
            _save_users(users)

    elif event['type'] == 'invoice.payment_failed':
        customer_id = obj.get('customer', '')
        if customer_id:
            users = _load_users()
            for email, u in users.items():
                if u.get('stripe_customer_id') == customer_id:
                    u['payment_failed'] = True
                    u['payment_failed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    break
            _save_users(users)

    return jsonify({'status': 'ok'})


# ── Forum ──────────────────────────────────────────────────────────────────────

@app.route('/forum')
def forum():
    category = request.args.get('cat', '')
    posts = _load_posts()
    if category and category in FORUM_CATEGORIES:
        posts = [p for p in posts if p.get('category') == category]
    # Sort newest first
    posts = sorted(posts, key=lambda p: p.get('created_at', ''), reverse=True)
    return render_template('forum.html', posts=posts, categories=FORUM_CATEGORIES,
                           active_category=category)


@app.route('/forum/new', methods=['GET', 'POST'])
@login_required
def forum_new():
    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        body     = request.form.get('body', '').strip()
        category = request.form.get('category', 'General')
        if not title or not body:
            return render_template('forum_new.html', categories=FORUM_CATEGORIES,
                                   error='Title and message are required.')
        if category not in FORUM_CATEGORIES:
            category = 'General'
        posts = _load_posts()
        new_id = str(len(posts) + 1)
        posts.append({
            'id': new_id,
            'title': title,
            'body': body,
            'category': category,
            'author_name': session.get('user_name', 'Member'),
            'author_email': session.get('user_email', ''),
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'replies': [],
        })
        _save_posts(posts)
        return redirect(url_for('forum_post', post_id=new_id))
    return render_template('forum_new.html', categories=FORUM_CATEGORIES, error=None)


@app.route('/forum/<post_id>', methods=['GET', 'POST'])
def forum_post(post_id):
    posts = _load_posts()
    post = next((p for p in posts if p['id'] == post_id), None)
    if not post:
        return redirect(url_for('forum'))
    if request.method == 'POST' and session.get('logged_in'):
        body = request.form.get('body', '').strip()
        if body:
            post['replies'].append({
                'body': body,
                'author_name': session.get('user_name', 'Member'),
                'author_email': session.get('user_email', ''),
                'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
            _save_posts(posts)
        return redirect(url_for('forum_post', post_id=post_id))
    return render_template('forum_post.html', post=post)


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        name  = request.form.get('name', '').strip()
        if not email or not pw or not name:
            error = 'All fields are required.'
        elif len(pw) < 6:
            error = 'Password must be at least 6 characters.'
        else:
            users = _load_users()
            if email in users:
                error = 'An account with that email already exists.'
            else:
                users[email] = {
                    'name': name,
                    'email': email,
                    'password': _hash_pw(pw),
                    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'plan': None,
                    'role': 'free',
                }
                _save_users(users)
                session.permanent      = True
                session['logged_in']   = True
                session['user_email']  = email
                session['user_name']   = name
                return redirect(url_for('browse'))
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(request.args.get('next') or url_for('browse'))
    error = None
    if request.method == 'POST':
        email   = request.form.get('email', '').strip().lower()
        pw      = request.form.get('password', '')
        next_url = request.args.get('next') or request.form.get('next') or url_for('browse')
        users   = _load_users()
        user    = users.get(email)
        pw_hash = _hash_pw(pw)

        # ── 1. Local auth ──────────────────────────────────────────────────────
        if user and user.get('password') == pw_hash:
            session.permanent     = True
            session['logged_in']  = True
            session['user_email'] = email
            session['user_name']  = user.get('name', email.split('@')[0])
            return redirect(next_url)

        # ── 2. VHX fallback — email-only lookup, no VHX password check ─────────
        # VHX members have never set a password on this site.
        # If their email exists in VHX, accept any password they type and
        # save it as their new password for future logins.
        vhx_customer = _vhx_get_customer(email)
        if vhx_customer:
            users = _vhx_provision_user(email, users, vhx_customer, password_hash=pw_hash)
            _save_users(users)
            session.permanent     = True
            session['logged_in']  = True
            session['user_email'] = email
            session['user_name']  = users[email].get('name', email.split('@')[0])
            return redirect(next_url)

        error = 'No account found with that email. If you subscribed through VHX, enter your VHX email address.'
    return render_template('login.html', error=error,
                           next=request.args.get('next', ''))


@app.route('/api/login', methods=['POST', 'OPTIONS'])
def api_login():
    # CORS preflight
    if request.method == 'OPTIONS':
        resp = Response()
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return resp

    data     = request.get_json(silent=True) or {}
    email    = data.get('email', '').strip().lower()
    pw       = data.get('password', '')

    def _json(payload, status=200):
        r = jsonify(payload)
        r.headers['Access-Control-Allow-Origin'] = '*'
        return r, status

    if not email or not pw:
        return _json({'success': False, 'error': 'Email and password are required'}, 400)

    users   = _load_users()
    user    = users.get(email)
    pw_hash = _hash_pw(pw)

    def _mint_token(email, users):
        """Generate and persist a long-lived iOS token, return it."""
        token = str(uuid.uuid4())
        users[email]['ios_token'] = token
        _save_users(users)
        return token

    def _set_session_and_respond(email, user, users):
        """Set Flask session cookie (for WKWebView) AND return JSON token."""
        token = user.get('ios_token') or _mint_token(email, users)
        name  = user.get('name', email.split('@')[0])
        # Set Flask session so subsequent WKWebView requests (ping-online, etc.) work
        session.permanent    = True
        session['logged_in'] = True
        session['user_email'] = email
        session['user_name']  = name
        return _json({
            'success': True,
            'email':   email,
            'plan':    user.get('plan') or 'free',
            'name':    name,
            'token':   token,
        })

    # ── 1. Local auth ──────────────────────────────────────────────────────
    if user and user.get('password') == pw_hash:
        return _set_session_and_respond(email, user, users)

    # ── 2. VHX fallback — email-only lookup, saves password for future ─────
    vhx_customer = _vhx_get_customer(email)
    if vhx_customer:
        users = _vhx_provision_user(email, users, vhx_customer, password_hash=pw_hash)
        _save_users(users)
        user  = users.get(email, {})
        return _set_session_and_respond(email, user, users)

    return _json({'success': False, 'error': 'Invalid email or password'}, 401)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ── Forgot / Reset Password ────────────────────────────────────────────────────

_reset_tokens = {}   # token -> {'email': ..., 'expires': datetime}

def _make_reset_token(email):
    import secrets
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = {
        'email':   email,
        'expires': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return token

def _consume_reset_token(token):
    """Return email if token is valid and not expired, else None. Removes token."""
    entry = _reset_tokens.pop(token, None)
    if not entry:
        return None
    if datetime.datetime.utcnow() > entry['expires']:
        return None
    return entry['email']


@app.route('/account')
@login_required
def account():
    users = _load_users()
    user  = users.get(session['user_email'], {})
    subscribed = _is_subscribed(user)
    return render_template('account.html', user=user, subscribed=subscribed)


# ── SEO routes ─────────────────────────────────────────────────────────────────

@app.route('/sitemap.xml')
def sitemap():
    base = BASE_URL.rstrip('/')
    urls = [
        base + '/',
        base + '/browse',
        base + '/programs',
        base + '/subscribe',
        base + '/forum',
    ]
    for v in EXPRESS_VIDEOS + REVELATION_VIDEOS:
        urls.append(base + f'/watch/{v["id"]}')
    for p in purchasable_products():
        urls.append(base + f'/programs/{p["id"]}')
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml_parts.append(f'  <url><loc>{u}</loc></url>')
    xml_parts.append('</urlset>')
    return Response('\n'.join(xml_parts), mimetype='application/xml')


@app.route('/robots.txt')
def robots():
    return Response(
        'User-agent: *\nAllow: /\nDisallow: /account\nDisallow: /api/\n'
        f'Sitemap: {BASE_URL}/sitemap.xml\n',
        mimetype='text/plain'
    )


@app.route('/api/content')
def api_content():
    return jsonify({
        'video_count':      len(ALL_VHX_VIDEOS),
        'product_count':    len(PRODUCTS),
        'collection_count': len(COLLECTIONS),
    })


# ── LIVE SETTINGS (Upstash Redis primary, in-memory cache, file fallback) ─────
# Render's filesystem is ephemeral — resets on every deploy. Settings are stored
# in Upstash Redis (free hosted Redis with a REST API, no extra packages needed).
# In-memory dict acts as a per-request cache so we don't hit Redis on every call.
# Falls back to the committed data/live-settings.json if Upstash is not configured.
_live_settings_path = os.path.join(_base, 'data', 'live-settings.json')
_live_settings_mem = None   # None = not yet initialised (cache)

_UPSTASH_URL   = os.environ.get('UPSTASH_REDIS_REST_URL', '').rstrip('/')
_UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')
_UPSTASH_KEY   = 'live_settings'

def _upstash_get():
    """Fetch live_settings JSON from Upstash. Returns dict or None on error/missing."""
    if not _UPSTASH_URL or not _UPSTASH_TOKEN:
        return None
    try:
        r = _http.get(
            f'{_UPSTASH_URL}/get/{_UPSTASH_KEY}',
            headers={'Authorization': f'Bearer {_UPSTASH_TOKEN}'},
            timeout=3,
        )
        result = r.json().get('result')
        if result:
            return json.loads(result)
    except Exception as e:
        print(f'[UPSTASH] get error: {e}', flush=True)
    return None

def _upstash_set(data):
    """Persist live_settings JSON to Upstash. Fire-and-forget; failures are non-fatal."""
    if not _UPSTASH_URL or not _UPSTASH_TOKEN:
        return
    try:
        encoded = json.dumps(data, separators=(',', ':'))
        r = _http.post(
            f'{_UPSTASH_URL}/set/{_UPSTASH_KEY}',
            headers={
                'Authorization': f'Bearer {_UPSTASH_TOKEN}',
                'Content-Type': 'text/plain',
            },
            data=encoded,
            timeout=3,
        )
        print(f'[UPSTASH] set → {r.status_code}', flush=True)
    except Exception as e:
        print(f'[UPSTASH] set error: {e}', flush=True)

def _load_live_settings():
    """Return current live settings. In-memory cache → Upstash → file seed."""
    global _live_settings_mem
    if _live_settings_mem is not None:
        return dict(_live_settings_mem)
    # First call this process: try Upstash first (survives restarts)
    from_redis = _upstash_get()
    if from_redis is not None:
        print(f'[UPSTASH] loaded settings from Redis: {from_redis}', flush=True)
        _live_settings_mem = from_redis
        return dict(_live_settings_mem)
    # Fall back to committed seed file
    if os.path.exists(_live_settings_path):
        try:
            with open(_live_settings_path) as f:
                _live_settings_mem = json.load(f)
                print(f'[SETTINGS] loaded from seed file', flush=True)
                return dict(_live_settings_mem)
        except Exception:
            pass
    _live_settings_mem = {}
    return {}

def _save_live_settings(data):
    global _live_settings_mem
    _live_settings_mem = dict(data)   # update cache immediately
    _upstash_set(data)                # persist to Redis (survives restarts)
    # Also write file as last-resort backup
    os.makedirs(os.path.dirname(_live_settings_path), exist_ok=True)
    try:
        with open(_live_settings_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ── OneSignal push notifications ───────────────────────────────────────────────

def _send_onesignal_push(status):
    """Fire-and-forget push to all OneSignal subscribers.
    Only sends for 'live' and 'countdown' — silently skips 'off' or missing keys."""
    app_id  = os.environ.get('ONESIGNAL_APP_ID', '').strip()
    api_key = os.environ.get('ONESIGNAL_API_KEY', '').strip()
    if not app_id or not api_key:
        return   # OneSignal not configured yet

    if status == 'live':
        title = '🔴 TRAIN4LIFE IS LIVE NOW!'
        body  = 'Jeff is live! Tap to watch.'
    elif status == 'countdown':
        title = '⏰ TRAIN4LIFE Going Live Soon!'
        body  = 'Live session starting — get ready to train!'
    else:
        return   # nothing to send for 'off'

    payload = {
        'app_id':              app_id,
        'included_segments':   ['All'],
        'headings':            {'en': title},
        'contents':            {'en': body},
        'ios_sound':           'default',
        'ios_badgeType':       'Increase',
        'ios_badgeCount':      1,
        'url':                 'train4life://',   # deep-link opens the app
    }
    try:
        _http.post(
            'https://onesignal.com/api/v1/notifications',
            json=payload,
            headers={
                'Authorization': f'Basic {api_key}',
                'Content-Type':  'application/json',
            },
            timeout=8,
        )
    except Exception:
        pass   # never block the admin action if push fails

def _get_live_vars():
    """Return current live status vars — saved settings override env vars."""
    settings = _load_live_settings()
    # Use 'in' membership so saved empty-string doesn't silently fall through
    status = settings['status'] if 'status' in settings else os.environ.get('LIVE_STATUS', 'off')
    if status not in ('off', 'countdown', 'live'):
        status = 'off'
    countdown_to = settings['countdown_to'] if 'countdown_to' in settings else os.environ.get('LIVE_COUNTDOWN_TO', '')
    # message: use saved value if key exists (even if blank), else env var, else default
    _defaults = {
        'off':       '',
        'countdown': '🔴 GOING LIVE SOON — Click to get notified!',
        'live':      '🔴 WE ARE LIVE RIGHT NOW!',
    }
    if 'message' in settings:
        message = settings['message']           # honour whatever Jeff saved, including blank
    else:
        message = os.environ.get('LIVE_STATUS_MESSAGE', '') or _defaults[status]
    timer_for = settings.get('timer_for', 'both')
    if timer_for not in ('both', 'express', 'bible'):
        timer_for = 'both'
    stream_url = settings.get('stream_url', '')
    return status, countdown_to, message, timer_for, stream_url

# ── APP CONTENT CURATOR ────────────────────────────────────────────────────────

_app_content_path = os.path.join(_base, 'data', 'app-content.json')
ADMIN_PASSWORD    = os.environ.get('ADMIN_PASSWORD', 'train4lifeadmin')
ADMIN_API_KEY     = os.environ.get('WEBSITE_ADMIN_KEY', 'train4life-admin-sync-2026')

_EMPTY_APP_CONTENT = {
    'last_updated': '',
    'express':      [],
    'bible_bootcamp': [],
}

def _load_app_content():
    if not os.path.exists(_app_content_path):
        return dict(_EMPTY_APP_CONTENT)
    with open(_app_content_path) as f:
        return json.load(f)

def _save_app_content(data):
    data['last_updated'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(_app_content_path, 'w') as f:
        json.dump(data, f, indent=2)

def _all_curator_videos():
    """Return combined list of all videos for curation.
    Tries VHX API first; falls back to content.json."""
    videos = []

    # Fetch all videos from VHX API across all pages
    vhx_live = _fetch_all_vhx_videos()
    if vhx_live:
        seen = set()
        for v in vhx_live:
            entry = _vhx_video_to_curator(v)
            if entry['id'] not in seen:
                seen.add(entry['id'])
                videos.append(entry)
    else:
        # Fallback: content.json (YouTube + VHX)
        for v in EXPRESS_VIDEOS + REVELATION_VIDEOS:
            thumb  = v.get('thumbnail') or f"https://img.youtube.com/vi/{v['youtube_id']}/mqdefault.jpg"
            parsed = parse_video_title(v['title'])
            videos.append({
                'id': v['id'], 'title': v['title'], 'thumbnail': thumb,
                'youtube_id': v.get('youtube_id', ''), 'vhx_url': v.get('vhx_watch_url', ''),
                'series': parsed['series'], 'episode': parsed['episode'],
                'subTitle': parsed['subTitle'], 'displayTitle': parsed['displayTitle'],
                'duration': v.get('duration', ''), 'source': 'youtube',
            })
        for v in ALL_VHX_VIDEOS:
            parsed = parse_video_title(v['title'])
            videos.append({
                'id': v['id'], 'title': v['title'], 'thumbnail': v.get('thumbnail', ''),
                'youtube_id': '', 'vhx_url': v.get('vhx_watch_url', ''),
                'series': parsed['series'], 'episode': parsed['episode'],
                'subTitle': parsed['subTitle'], 'displayTitle': parsed['displayTitle'],
                'duration': v.get('duration', ''), 'source': 'vhx',
            })
    return videos


def _admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login', next=request.path))
        return f(*args, **kwargs)
    return decorated


# ── Messages Routes ────────────────────────────────────────────────────────────

def _msg_auth():
    """Return (email, is_admin) or (None, False) if not authenticated."""
    # Admin session — is_admin may be set without logged_in
    if session.get('is_admin'):
        email = session.get('user_email', 'admin')
        return email, True
    # Member web session
    if session.get('logged_in'):
        email = session.get('user_email', '')
        return email, False
    # iOS Bearer token
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        parts = auth[7:].split(':', 1)
        if len(parts) == 2:
            email, token = parts[0], parts[1]
            if _ios_auth(email, token):
                return email, False
    return None, False


@app.route('/messages')
@login_required
def messages_page():
    email       = session.get('user_email', '')
    unread      = _get_unread_count(email) if email else 0
    member_convos = _get_member_conversations(email) if email else []
    # Enrich with other user's display name
    users = _load_users()
    for c in member_convos:
        other = users.get(c['other_email'], {})
        c['other_name'] = other.get('name') or (c['other_email'].split('@')[0].capitalize())
    return render_template('messages_list.html', unread=unread, member_convos=member_convos)


@app.route('/video-jeff')
@login_required
def video_jeff():
    """Dedicated face-to-face video call page — no text, just WebRTC with Jeff."""
    email   = session.get('user_email', '')
    chat_id = f'dm:{email}'
    return render_template('video_jeff.html',
        my_email=email,
        chat_id=chat_id,
        sio_enabled=_SIO_OK,
    )


@app.route('/messages/dm/<path:member_email>')
@login_required
def messages_dm_by_email(member_email):
    """Canonical DM URL: /messages/dm/<email>  — redirects to /messages/dm.
    The session already identifies the logged-in member; the email in the URL
    is informational so direct links work from the iOS app."""
    return redirect(url_for('messages_chat', chat_id='dm'))


@app.route('/messages/<chat_id>', methods=['GET', 'POST'])
@login_required
def messages_chat(chat_id):
    email    = session.get('user_email', '')
    users    = _load_users()
    user     = users.get(email, {})
    name     = user.get('name') or email.split('@')[0].capitalize()

    valid = ['announcements', 'express', 'bible', 'dm']
    if chat_id not in valid:
        return redirect(url_for('messages_page'))

    actual_id  = f'dm:{email}' if chat_id == 'dm' else chat_id
    is_readonly = (chat_id == 'announcements')

    error = None
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            error = 'Message cannot be empty.'
        elif len(content) > 2000:
            error = 'Message too long (max 2000 characters).'
        elif is_readonly:
            error = 'Only Jeff can post to Announcements.'
        else:
            _post_and_broadcast(actual_id, email, name, content, False)
            return redirect(url_for('messages_chat', chat_id=chat_id))

    msgs = _get_messages(actual_id)
    _mark_read(email, actual_id)

    titles = {
        'announcements': ('📢 Announcements',    'Posts from Jeff — read only'),
        'express':       ('⚡ Express Community', 'Chat with fellow Express members'),
        'bible':         ('📖 Bible Bootcamp',    'Bible Bootcamp community chat'),
        'dm':            ('💬 Jeff (Direct)',      'Private message with Jeff'),
    }
    title, subtitle = titles[chat_id]
    return render_template('messages_chat.html',
        chat_id=actual_id, title=title, subtitle=subtitle,
        messages=msgs, is_readonly=is_readonly,
        my_email=email, error=error,
        is_dm=(chat_id == 'dm'),
        sio_enabled=_SIO_OK,
    )


@app.route('/messages/member/<path:target_email>', methods=['GET', 'POST'])
@login_required
def messages_member(target_email):
    email = session.get('user_email', '')
    users = _load_users()
    user  = users.get(email, {})
    name  = user.get('name') or email.split('@')[0].capitalize()

    # Validate target exists
    target_user = users.get(target_email)
    if not target_user or target_email == email:
        return redirect(url_for('messages_page'))

    target_name = target_user.get('name') or target_email.split('@')[0].capitalize()
    chat_id     = _member_dm_id(email, target_email)

    error = None
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            error = 'Message cannot be empty.'
        elif len(content) > 2000:
            error = 'Message too long (max 2000 characters).'
        else:
            _post_and_broadcast(chat_id, email, name, content, False)
            return redirect(url_for('messages_member', target_email=target_email))

    msgs = _get_messages(chat_id)
    _mark_read(email, chat_id)
    return render_template('messages_chat.html',
        chat_id=chat_id,
        title=f'💬 {target_name}',
        subtitle=f'Private conversation with {target_name}',
        messages=msgs, is_readonly=False,
        my_email=email, error=error,
        is_dm=True,
        sio_enabled=_SIO_OK,
    )


@app.route('/api/members')
@login_required
def api_members():
    users = _load_users()
    my_email = session.get('user_email', '')
    members = []
    for em, u in users.items():
        if em == my_email:
            continue
        members.append({
            'email': em,
            'name': u.get('name') or em.split('@')[0].capitalize(),
        })
    members.sort(key=lambda m: m['name'].lower())
    return jsonify({'members': members})


@app.route('/api/live/save-replay', methods=['POST'])
@_admin_required
def api_live_save_replay():
    f = request.files.get('replay')
    if not f:
        return jsonify({'error': 'no file'}), 400
    replay_dir = os.path.join(_base, 'data', 'replays')
    os.makedirs(replay_dir, exist_ok=True)
    stamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    path  = os.path.join(replay_dir, f'replay_{stamp}.webm')
    f.save(path)
    # Log reference in live settings
    settings = _load_live_settings()
    replays  = settings.get('replays', [])
    replays.insert(0, {'file': f'replay_{stamp}.webm', 'created_at': stamp})
    settings['replays'] = replays[:20]
    _save_live_settings(settings)
    return jsonify({'ok': True, 'file': f'replay_{stamp}.webm'})


@app.route('/api/messages')
def api_get_messages():
    email, is_admin = _msg_auth()

    chat      = request.args.get('chat', 'announcements')
    member_id = request.args.get('member_id', email or '')
    since     = request.args.get('since', '')

    if chat == 'dm':
        # Short form: ?chat=dm&member_id=email@example.com
        if not email:
            return jsonify({'error': 'unauthorized'}), 401
        chat_id = f'dm:{member_id}'
        if not is_admin and member_id != email:
            return jsonify({'error': 'forbidden'}), 403
    elif chat.startswith('dm:'):
        # Full form: ?chat=dm:email@example.com  (sent by the member's own page)
        if not email:
            return jsonify({'error': 'unauthorized'}), 401
        dm_email = chat[3:]
        if not is_admin and dm_email != email:
            return jsonify({'error': 'forbidden'}), 403
        chat_id = chat
    elif chat in CHAT_IDS:
        # Group chats are readable without auth (public community channels)
        chat_id = chat
    else:
        return jsonify({'error': 'invalid chat'}), 400

    msgs = _get_messages(chat_id, since=since or None)
    if email:
        _mark_read(email, chat_id)
    return jsonify({'messages': msgs, 'chat_id': chat_id})


@app.route('/api/video/start', methods=['POST'])
def api_video_start():
    """Return (or create) a Daily.co room for a DM, so both parties join the same room."""
    app_key = request.headers.get('X-App-Key', '')
    email, is_admin = _msg_auth()
    if not email and app_key != 'Smallville2006':
        return jsonify({'error': 'unauthorized'}), 401

    daily_key = os.environ.get('DAILY_API_KEY', '').strip()
    if not daily_key:
        return jsonify({'error': 'Video calls not configured'}), 503

    body         = request.get_json(silent=True) or {}
    raw_chat     = body.get('chat_id') or body.get('chat', '')
    member_email = body.get('member_email', '') or ''

    # Resolve canonical DM key
    # Admin sends:  {chat_id: "dm:wmratliff@gmail.com"}
    # iOS app sends: {chat: "dm", member_email: "wmratliff@gmail.com"}
    if raw_chat.startswith('dm:'):
        chat_id = raw_chat
    elif raw_chat == 'dm':
        resolved_email = email or member_email
        chat_id = f'dm:{resolved_email}' if resolved_email else 'dm'
    else:
        chat_id = raw_chat

    print(f'=== VIDEO START: raw_chat={raw_chat!r} email={email!r} member_email={member_email!r} chat_id={chat_id!r} ===')
    print(f'=== ACTIVE ROOMS: {list(_active_rooms.keys())} ===')

    # ── Return existing active room if one exists ─────────────────────────────
    with _rooms_lock:
        existing = _active_rooms.get(chat_id)
    print(f'=== FOUND ROOM: {existing} ===')
    if existing and existing['expires_at'] > time.time():
        print(f'=== VIDEO JOIN EXISTING ROOM: chat={chat_id} url={existing["url"]} ===')
        return jsonify({'url': existing['url'], 'room': existing['room']})

    # ── Create new Daily.co room ──────────────────────────────────────────────
    room_name = 'train4life-' + uuid.uuid4().hex[:10]
    exp       = int(time.time()) + 3600

    try:
        import requests as _r
        resp = _r.post(
            'https://api.daily.co/v1/rooms',
            headers={'Authorization': f'Bearer {daily_key}', 'Content-Type': 'application/json'},
            json={
                'name':       room_name,
                'privacy':    'public',
                'properties': {'exp': exp, 'max_participants': 10},
            },
            timeout=8,
        )
        room = resp.json()
        if 'url' not in room:
            return jsonify({'error': room.get('error', 'Failed to create room')}), 500
        room_url = room['url']
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # ── Save as active room for this DM ──────────────────────────────────────
    with _rooms_lock:
        _active_rooms[chat_id] = {
            'url':        room_url,
            'room':       room_name,
            'expires_at': time.time() + 3600,
        }

    # ── Push notification (only sent when room is first created) ─────────────
    if is_admin and chat_id.startswith('dm:'):
        # Jeff is calling a specific member — target them directly
        target_email = chat_id[3:]
        _push_to_member(target_email,
                        '📹 Jeff is calling you!',
                        'Tap to join the video call',
                        'video_call')

    return jsonify({'url': room_url, 'room': room_name})


@app.route('/api/video/clear', methods=['GET', 'POST'])
def api_video_clear():
    """Clear all active video rooms so fresh ones get created on next tap."""
    if not session.get('is_admin'):
        return jsonify({'error': 'unauthorized'}), 401
    with _rooms_lock:
        count = len(_active_rooms)
        _active_rooms.clear()
    print(f'=== VIDEO ROOMS CLEARED: {count} room(s) removed ===')
    return jsonify({'status': 'cleared', 'count': count})


# ── EasyList PC-bridge endpoints ─────────────────────────────────────────────

def _load_easylist():
    if not os.path.exists(_easylist_path):
        return []
    try:
        with open(_easylist_path) as f:
            return json.load(f)
    except Exception:
        return []

def _save_easylist(listings):
    os.makedirs(os.path.dirname(_easylist_path), exist_ok=True)
    with open(_easylist_path, 'w') as f:
        json.dump(listings, f)

@app.route('/api/easylist/pending', methods=['GET', 'POST'])
def api_easylist_pending():
    """GET: PC retrieves pending listings. POST: iOS uploads pending listings."""
    if request.headers.get('X-App-Key', '') != 'Smallville2006':
        return jsonify({'error': 'unauthorized'}), 401

    if request.method == 'POST':
        data     = request.get_json(silent=True) or {}
        incoming = data.get('listings', [])
        if not incoming:
            return jsonify({'error': 'no listings provided'}), 400
        with _easylist_lock:
            existing  = _load_easylist()
            exist_ids = {l['id'] for l in existing}
            added = 0
            for l in incoming:
                if l.get('id') and l['id'] not in exist_ids:
                    l['server_status'] = 'pending'
                    existing.append(l)
                    added += 1
            _save_easylist(existing)
        print(f'=== EASYLIST: received {len(incoming)}, added {added} new ===')
        return jsonify({'ok': True, 'received': len(incoming), 'added': added})

    else:  # GET — PC script fetches pending
        with _easylist_lock:
            all_listings = _load_easylist()
        pending = [l for l in all_listings if l.get('server_status') == 'pending']
        return jsonify({'listings': pending})


@app.route('/api/easylist/mark-posted', methods=['POST'])
def api_easylist_mark_posted():
    """PC calls this after successfully posting a listing to Facebook."""
    if request.headers.get('X-App-Key', '') != 'Smallville2006':
        return jsonify({'error': 'unauthorized'}), 401
    data       = request.get_json(silent=True) or {}
    listing_id = data.get('id', '')
    if not listing_id:
        return jsonify({'error': 'id required'}), 400
    with _easylist_lock:
        listings = _load_easylist()
        found = False
        for l in listings:
            if l.get('id') == listing_id:
                l['server_status'] = 'posted'
                found = True
                break
        if found:
            _save_easylist(listings)
    return jsonify({'ok': found, 'id': listing_id})


@app.route('/api/messages', methods=['POST'])
def api_post_message():
    email, is_admin = _msg_auth()
    if not email:
        return jsonify({'error': 'unauthorized'}), 401

    data      = request.get_json(silent=True) or {}
    chat      = data.get('chat', '')
    content   = (data.get('content') or '').strip()
    member_id = data.get('member_id', email)

    if not content:
        return jsonify({'error': 'empty message'}), 400
    if len(content) > 2000:
        return jsonify({'error': 'message too long'}), 400

    users       = _load_users()
    user        = users.get(email, {})
    sender_name = user.get('name') or email.split('@')[0].capitalize()

    if chat == 'dm':
        chat_id = f'dm:{member_id}'
    elif chat in CHAT_IDS:
        if chat == 'announcements' and not is_admin:
            return jsonify({'error': 'only admin can post to announcements'}), 403
        chat_id = chat
    else:
        return jsonify({'error': 'invalid chat'}), 400

    msg = _post_and_broadcast(chat_id, email, sender_name, content, is_admin)

    # Push notification — targeted to DM recipient or broadcast for group chats
    if is_admin:
        if chat == 'dm':
            _push_to_member(member_id,
                            '💬 New message from Jeff',
                            content[:100],
                            'dm')
        else:
            # Group chat — broadcast to all members
            _fire_onesignal('💬 New message from Jeff', content[:100])

    return jsonify({'message': msg})


@app.route('/api/messages/unread')
def api_messages_unread():
    email, _ = _msg_auth()
    if not email:
        return jsonify({'count': 0})
    count = _get_unread_count(email)
    return jsonify({'count': count})


@app.route('/api/messages/mark-read', methods=['POST'])
def api_messages_mark_read():
    email, _ = _msg_auth()
    if not email:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    chat = data.get('chat', '')
    member_id = data.get('member_id', email)
    chat_id = f'dm:{member_id}' if chat == 'dm' else chat
    _mark_read(email, chat_id)
    return jsonify({'ok': True})


@app.route('/admin/messages')
def admin_messages_page():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    with _msg_lock:
        data  = _load_messages()
        reads = _load_reads()
    users       = _load_users()
    admin_reads = reads.get('__admin__', {})
    dm_convos   = []
    for key, msgs in data.items():
        if not key.startswith('dm:') or not msgs:
            continue
        member_email = key[3:]
        last_msg     = msgs[-1]
        last_read    = admin_reads.get(key, '')
        unread       = sum(1 for m in msgs
                           if not m['is_admin'] and (not last_read or m['created_at'] > last_read))
        dm_convos.append({
            'email':        member_email,
            'name':         users.get(member_email, {}).get('name') or member_email.split('@')[0],
            'last_message': last_msg['content'][:60],
            'last_time':    last_msg['created_at'],
            'unread':       unread,
        })
    dm_convos.sort(key=lambda x: x['last_time'], reverse=True)
    return render_template('admin_messages_list.html', dm_convos=dm_convos)


@app.route('/admin/messages/dm/<path:member_email>', methods=['GET', 'POST'])
def admin_messages_dm(member_email):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    dm_key = f'dm:{member_email}'
    if request.method == 'POST':
        print(f"=== DM SEND ROUTE HIT === member={member_email}")
        content = request.form.get('content', '').strip()
        if content and len(content) <= 2000:
            _post_and_broadcast(dm_key, JEFF_EMAIL, 'Jeff', content, True)
            _push_to_member(member_email,
                            '💬 New message from Jeff',
                            content[:100],
                            'dm')
        return redirect(url_for('admin_messages_dm', member_email=member_email))
    msgs = _get_messages(dm_key)
    _mark_read('__admin__', dm_key)
    users = _load_users()
    member_name = users.get(member_email, {}).get('name') or member_email.split('@')[0]
    return render_template('admin_chat.html',
        title=f'💬 {member_name}', subtitle=member_email,
        messages=msgs, back_url=url_for('admin_messages_page'),
        post_url=url_for('admin_messages_dm', member_email=member_email),
        chat_id=dm_key,
        sio_enabled=_SIO_OK,
    )


@app.route('/admin/messages/<chat_id>', methods=['GET', 'POST'])
def admin_messages_chat(chat_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    valid = ['announcements', 'express', 'bible']
    if chat_id not in valid:
        return redirect(url_for('admin_messages_page'))
    if request.method == 'POST':
        print(f"=== ADMIN CHAT SEND HIT === chat_id={chat_id}")
        content = request.form.get('content', '').strip()
        if content and len(content) <= 2000:
            _post_and_broadcast(chat_id, JEFF_EMAIL, 'Jeff', content, True)
            _fire_onesignal('💬 New message from Jeff', content[:100])
        return redirect(url_for('admin_messages_chat', chat_id=chat_id))
    msgs = _get_messages(chat_id)
    _mark_read('__admin__', chat_id)
    titles = {
        'announcements': ('📢 Announcements',    'Post to all members'),
        'express':       ('⚡ Express Community', 'Express group chat'),
        'bible':         ('📖 Bible Bootcamp',    'Bible Bootcamp group chat'),
    }
    title, subtitle = titles[chat_id]
    return render_template('admin_chat.html',
        title=title, subtitle=subtitle,
        messages=msgs, back_url=url_for('admin_messages_page'),
        post_url=url_for('admin_messages_chat', chat_id=chat_id),
        chat_id=chat_id,
        sio_enabled=_SIO_OK,
    )


@app.route('/admin/api/send', methods=['POST'])
def admin_api_send():
    """Dedicated admin send endpoint — bypasses _msg_auth, checks is_admin directly."""
    print("=== MESSAGE SEND ROUTE HIT ===")
    print(f"=== ONESIGNAL KEY: {os.environ.get('ONESIGNAL_API_KEY', 'NOT SET')[:20]} ===")
    if not session.get('is_admin'):
        return jsonify({'error': 'unauthorized'}), 401
    data    = request.get_json(silent=True) or {}
    chat    = data.get('chat', '').strip()
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'empty message'}), 400
    if len(content) > 2000:
        return jsonify({'error': 'message too long'}), 400
    # Resolve chat_id
    if chat in CHAT_IDS:
        chat_id = chat
    elif chat.startswith('dm:'):
        chat_id = chat
    else:
        return jsonify({'error': f'invalid chat: {chat!r}'}), 400
    jeff_email = session.get('user_email', JEFF_EMAIL)
    msg = _post_and_broadcast(chat_id, jeff_email, 'Jeff', content, True)

    # Push notification — targeted for DM, broadcast for group chats
    if chat_id.startswith('dm:'):
        target_email = chat_id[3:]
        _push_to_member(target_email, '💬 New message from Jeff', content[:100], 'dm')
    else:
        _fire_onesignal('💬 New message from Jeff', content[:100])

    return jsonify({'message': msg})


@app.route('/api/admin/conversations')
def api_admin_conversations():
    if not session.get('is_admin'):
        return jsonify({'error': 'forbidden'}), 403
    with _msg_lock:
        data  = _load_messages()
        reads = _load_reads()
    users = _load_users()
    admin_reads = reads.get('__admin__', {})
    convos = []
    for key, msgs in data.items():
        if not key.startswith('dm:') or not msgs:
            continue
        member_email = key[3:]
        last_msg     = msgs[-1]
        last_read    = admin_reads.get(key, '')
        unread       = sum(1 for m in msgs if not m['is_admin'] and (not last_read or m['created_at'] > last_read))
        convos.append({'email': member_email, 'name': users.get(member_email, {}).get('name') or member_email, 'last_message': last_msg['content'][:60], 'last_time': last_msg['created_at'], 'unread': unread})
    convos.sort(key=lambda x: x['last_time'], reverse=True)
    return jsonify({'conversations': convos})


@app.route('/admin')
def admin_index():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/dashboard')
@_admin_required
def admin_dashboard():
    status, countdown_to, message, timer_for, stream_url = _get_live_vars()
    users = _load_users()
    subscriber_count = sum(1 for u in users.values() if u.get('plan') and u.get('plan') != 'free')
    app_content = _load_app_content()
    app_video_count = len(app_content.get('express', [])) + len(app_content.get('bible_bootcamp', []))
    return render_template('admin_dashboard.html',
                           live_status=status,
                           live_countdown_to=countdown_to,
                           live_message=message,
                           subscriber_count=subscriber_count,
                           app_video_count=app_video_count,
                           total_video_count=len(ALL_VHX_VIDEOS),
                           revenue=None)


@app.route('/admin/members')
@_admin_required
def admin_members():
    users = _load_users()
    # Exclude admin/Jeff accounts
    admin_emails = {'jeff@train4life.life', 'wmratliff@gmail.com', JEFF_EMAIL}
    members = []
    for email, u in users.items():
        if email.lower() in admin_emails:
            continue
        raw_date = u.get('created_at', '')
        try:
            from datetime import datetime as _dt
            joined = _dt.fromisoformat(raw_date.replace('Z', '+00:00')).strftime('%b %d, %Y')
        except Exception:
            joined = raw_date[:10] if raw_date else '—'
        plan = (u.get('plan') or 'free').strip() or 'free'
        members.append({
            'email':  email,
            'name':   u.get('name') or email.split('@')[0].capitalize(),
            'joined': joined,
            'plan':   plan,
        })
    members.sort(key=lambda m: m['joined'], reverse=True)
    return render_template('admin_members.html', members=members)


@app.route('/admin/live', methods=['GET', 'POST'])
@_admin_required
def admin_live():
    global _sio_broadcast_token
    # Rotate token on every page load; the JS embeds it and sends it back
    # with broadcaster_ready so the SocketIO handler can auth without
    # relying on session cookies (which don't reliably travel over WS).
    _sio_broadcast_token = secrets.token_hex(24)
    status, countdown_to, message, timer_for, stream_url = _get_live_vars()
    saved = False
    if request.method == 'POST':
        print(f'[DEBUG] admin_live POST received — form keys: {list(request.form.keys())}', flush=True)
        new_status = request.form.get('status', 'off')
        if new_status not in ('off', 'countdown', 'live'):
            new_status = 'off'
        new_countdown  = request.form.get('countdown_to', '').strip()
        new_message    = request.form.get('message', '').strip()
        new_timer_for  = request.form.get('timer_for', 'both')
        if new_timer_for not in ('both', 'express', 'bible'):
            new_timer_for = 'both'
        new_stream_url    = request.form.get('stream_url', '').strip()
        new_banner_enabled = '1' in request.form.getlist('banner_enabled')
        new_ticker_enabled = '1' in request.form.getlist('ticker_enabled')
        new_ticker_text    = request.form.get('ticker_text', '').strip()
        print(f'[DEBUG] admin_live saving: status={new_status!r} countdown={new_countdown!r} message={new_message!r} timer_for={new_timer_for!r}', flush=True)
        _save_live_settings({
            'status':         new_status,
            'countdown_to':   new_countdown,
            'message':        new_message,
            'timer_for':      new_timer_for,
            'stream_url':     new_stream_url,
            'banner_enabled': new_banner_enabled,
            'ticker_enabled': new_ticker_enabled,
            'ticker_text':    new_ticker_text,
        })
        print(f'[DEBUG] admin_live save done — mem now: {_live_settings_mem}', flush=True)
        _send_onesignal_push(new_status)
        status, countdown_to, message, timer_for, stream_url = new_status, new_countdown, new_message, new_timer_for, new_stream_url
        saved = True
    settings = _load_live_settings()
    return render_template('admin_live.html',
                           live_status=status,
                           live_countdown_to=countdown_to,
                           live_message=message,
                           live_timer_for=timer_for,
                           live_stream_url=stream_url,
                           live_banner_enabled=settings.get('banner_enabled', True),
                           live_ticker_enabled=settings.get('ticker_enabled', False),
                           live_ticker_text=settings.get('ticker_text', ''),
                           saved=saved,
                           broadcast_token=_sio_broadcast_token)


@app.route('/api/admin/broadcast-token', methods=['POST', 'OPTIONS'])
def api_broadcast_token():
    """Video builder endpoint — issues a fresh WebRTC broadcast token.
    Authorization: Bearer <ADMIN_PASSWORD>
    Returns: { token: '...' }
    """
    if request.method == 'OPTIONS':
        resp = jsonify({})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        return resp
    global _sio_broadcast_token
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer ') or auth[7:] != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    import secrets
    _sio_broadcast_token = secrets.token_hex(24)
    resp = jsonify({'token': _sio_broadcast_token})
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/api/admin/set-live', methods=['POST'])
def api_admin_set_live():
    """iOS admin endpoint — POST JSON with Authorization: Bearer <password>."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer ') or auth[7:] != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    new_status = data.get('status', 'off')
    if new_status not in ('off', 'countdown', 'live'):
        return jsonify({'error': 'Invalid status'}), 400
    _save_live_settings({
        'status':       new_status,
        'countdown_to': data.get('countdown_to', ''),
        'message':      data.get('message', ''),
        'timer_for':    data.get('timer_for', 'both'),
        'stream_url':   data.get('stream_url', ''),
    })
    _send_onesignal_push(new_status)
    status, countdown_to, message, timer_for, stream_url = _get_live_vars()
    resp = jsonify({'ok': True, 'status': status, 'countdown_to': countdown_to, 'message': message})
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session.permanent     = True
            session['is_admin']   = True
            session['user_email'] = JEFF_EMAIL   # so _msg_auth() returns Jeff's real email
            next_url = request.args.get('next', url_for('admin_app_content'))
            return redirect(next_url)
        error = 'Wrong password.'
    return render_template('admin_login.html', error=error)


@app.route('/admin/guide')
@_admin_required
def admin_guide():
    return render_template('admin_guide.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/admin/app-content', methods=['GET', 'POST'])
@_admin_required
def admin_app_content():
    app_content = _load_app_content()

    if request.method == 'POST':
        data = request.get_json(silent=True)
        if data:
            # Enrich each video with parsed title fields
            for section in ('express', 'bible_bootcamp'):
                enriched = []
                for v in data.get(section, []):
                    p = parse_video_title(v.get('title') or v.get('fullTitle', ''))
                    v.setdefault('series',       p['series'])
                    v.setdefault('episode',      p['episode'])
                    v.setdefault('subTitle',     p['subTitle'])
                    v.setdefault('displayTitle', p['displayTitle'])
                    v.setdefault('fullTitle',    p['fullTitle'])
                    v.setdefault('sort_override', True)
                    enriched.append(v)
                app_content[section] = enriched
            _save_app_content(app_content)
            return jsonify({'success': True, 'message': 'Saved & published to app.'})
        return jsonify({'error': 'Invalid JSON'}), 400

    all_videos   = _all_curator_videos()
    selected_ids = set(
        [v['id'] for v in app_content.get('express', [])]
        + [v['id'] for v in app_content.get('bible_bootcamp', [])]
    )
    return render_template('admin_app_content.html',
                           all_videos=all_videos,
                           app_content=app_content,
                           selected_ids=selected_ids)


@app.route('/api/app-content', methods=['GET'])
def api_app_content():
    app_content = _load_app_content()
    resp = jsonify(app_content)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'public, max-age=60'
    return resp


@app.route('/api/app-content/add', methods=['POST'])
def api_app_content_add():
    if request.headers.get('X-Admin-Key') != ADMIN_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    data     = request.get_json(silent=True) or {}
    section  = data.get('section', '').strip()
    video_id = str(data.get('video_id', '')).strip()
    title    = data.get('title', '').strip()
    thumb    = data.get('thumbnail', '').strip()
    vhx_url  = data.get('vhx_url', '').strip()

    if section not in ('express', 'bible_bootcamp'):
        return jsonify({'error': "section must be 'express' or 'bible_bootcamp'"}), 400
    if not video_id or not title:
        return jsonify({'error': 'video_id and title required'}), 400

    parsed = parse_video_title(title)
    app_content = _load_app_content()
    existing_ids = {v['id'] for v in app_content.get(section, [])}
    if video_id not in existing_ids:
        order = len(app_content.get(section, [])) + 1
        app_content.setdefault(section, []).append({
            'id':           video_id,
            'title':        title,
            'thumbnail':    thumb,
            'vhx_url':      vhx_url,
            'order':        order,
            'sort_override': False,
            'series':       parsed['series'],
            'episode':      parsed['episode'],
            'subTitle':     parsed['subTitle'],
            'fullTitle':    parsed['fullTitle'],
            'displayTitle': parsed['displayTitle'],
        })
        _save_app_content(app_content)

    return jsonify({'success': True, 'section': section, 'video_id': video_id})


# ── PDF LIBRARY ─────────────────────────────────────────────────────────────────

_pdfs_path   = os.path.join(_base, 'static', 'pdfs.json')
_pdfs_dir    = os.path.join(_base, 'static', 'pdfs')
_thumbs_dir  = os.path.join(_base, 'static', 'pdf-thumbs')
_videos_path = os.path.join(_base, 'static', 'videos.json')


def _load_pdfs():
    if not os.path.exists(_pdfs_path):
        return []
    with open(_pdfs_path) as f:
        return json.load(f)


def _save_pdfs(data):
    with open(_pdfs_path, 'w') as f:
        json.dump(data, f, indent=2)


def _load_videos():
    if not os.path.exists(_videos_path):
        return []
    with open(_videos_path) as f:
        return json.load(f)


def _save_videos(data):
    with open(_videos_path, 'w') as f:
        json.dump(data, f, indent=2)


def _safe_filename(name):
    name = re.sub(r'[^\w\s\-.]', '', name).strip()
    return re.sub(r'\s+', '_', name)


VHX_API_KEY    = 'W8R9VxBi3sWsDk8G5ymMTpRqgXwWyU4i'
_extras_path   = os.path.join(_base, 'static', 'extras.json')


def _load_extras():
    if not os.path.exists(_extras_path):
        return []
    with open(_extras_path) as f:
        return json.load(f)


def _fmt_size(n):
    if not n:
        return ''
    if n < 1024:
        return f'{n} B'
    if n < 1024 * 1024:
        return f'{n // 1024} KB'
    return f'{n / (1024*1024):.1f} MB'


def _categorize_extras(extras):
    express, bible, other = [], [], []
    for e in extras:
        t = e.get('title', '').upper()
        item = {
            'id':            e['id'],
            'title':         re.sub(r'\.(pdf|png|jpg|jpeg)$', '', e.get('title', ''), flags=re.I).strip(),
            'file_type':     e.get('file_type', ''),
            'file_size':     e.get('file_size', 0),
            'file_size_label': _fmt_size(e.get('file_size', 0)),
            'thumbnail':     (e.get('thumbnail') or {}).get('medium'),
        }
        if 'REVELATION' in t:
            bible.append(item)
        elif any(k in t for k in ('EXPRESS', 'CALENDAR', 'CHEAT')):
            express.append(item)
        else:
            other.append(item)
    return express, bible, other


@app.route('/resources')
def resources():
    extras = _load_extras()
    express_extras, bible_extras, other_extras = _categorize_extras(extras)
    pdf_entries = _load_pdfs()
    total = len(express_extras) + len(bible_extras) + len(other_extras) + len(pdf_entries)
    return render_template('resources.html',
                           express_extras=express_extras,
                           bible_extras=bible_extras,
                           other_extras=other_extras,
                           pdf_entries=pdf_entries,
                           total_count=total)


@app.route('/resources/download/<int:extra_id>')
def resources_download(extra_id):
    """Fetch a fresh signed URL from VHX and redirect to it."""
    if not _HTTP_OK:
        return 'Download unavailable', 503
    try:
        resp = _http.get(
            f'https://api.vhx.tv/extras/{extra_id}',
            auth=(VHX_API_KEY, ''),
            timeout=10,
        )
        url = resp.json().get('url')
        if url:
            return redirect(url)
    except Exception:
        pass
    return 'Download link unavailable', 503


@app.route('/api/pdfs', methods=['GET'])
def api_pdfs():
    pdfs = _load_pdfs()
    resp = jsonify(pdfs)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'public, max-age=60'
    return resp


@app.route('/api/extras', methods=['GET'])
def api_extras():
    extras = _load_extras()
    express, bible, other = _categorize_extras(extras)
    resp = jsonify({
        'total': len(extras),
        'express': express,
        'bible': bible,
        'other': other,
    })
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'public, max-age=300'
    return resp


@app.route('/api/add-pdf', methods=['POST', 'OPTIONS'])
def api_add_pdf():
    if request.method == 'OPTIONS':
        r = Response()
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Admin-Password'
        return r
    _pub_pass = 'Smallville2006'
    if (request.headers.get('X-Admin-Key') != ADMIN_API_KEY
            and request.headers.get('X-Admin-Password') != ADMIN_PASSWORD
            and request.headers.get('X-Admin-Password') != _pub_pass):
        return jsonify({'error': 'Unauthorized'}), 401

    title       = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    category    = request.form.get('category', 'other').strip()
    pdf_file    = request.files.get('pdf_file')
    thumb_file  = request.files.get('thumbnail_file')

    if not title or not pdf_file:
        return jsonify({'error': 'title and pdf_file are required'}), 400

    os.makedirs(_pdfs_dir, exist_ok=True)
    os.makedirs(_thumbs_dir, exist_ok=True)

    import uuid as _uuid
    uid = _uuid.uuid4().hex[:8]
    pdf_name  = uid + '_' + _safe_filename(pdf_file.filename or 'file.pdf')
    pdf_path  = os.path.join(_pdfs_dir, pdf_name)
    pdf_file.save(pdf_path)
    _base_url = 'https://www.train4life.life'
    pdf_url = _base_url + '/static/pdfs/' + pdf_name

    thumb_url = None
    if thumb_file and thumb_file.filename:
        thumb_name = uid + '_' + _safe_filename(thumb_file.filename)
        thumb_file.save(os.path.join(_thumbs_dir, thumb_name))
        thumb_url = _base_url + '/static/pdf-thumbs/' + thumb_name

    from datetime import date as _date
    pdfs = _load_pdfs()
    pdfs.append({
        'id':          'pdf_' + uid,
        'title':       title,
        'description': description,
        'category':    category,
        'url':         pdf_url,
        'thumbnail':   thumb_url,
        'created_at':  str(_date.today()),
    })
    _save_pdfs(pdfs)

    r = jsonify({'success': True, 'id': 'pdf_' + uid, 'url': pdf_url})
    r.headers['Access-Control-Allow-Origin'] = '*'
    return r


# ── Video library ────────────────────────────────────────────────────────────

@app.route('/api/videos', methods=['GET'])
def api_videos():
    videos = _load_videos()
    r = jsonify(videos)
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Cache-Control'] = 'public, max-age=60'
    return r


@app.route('/api/add-video', methods=['POST', 'OPTIONS'])
def api_add_video():
    if request.method == 'OPTIONS':
        resp = Response()
        resp.headers['Access-Control-Allow-Origin']  = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Admin-Password'
        return resp

    _pub_pass = 'Smallville2006'
    if (request.headers.get('X-Admin-Key')      != ADMIN_API_KEY
            and request.headers.get('X-Admin-Password') != ADMIN_PASSWORD
            and request.headers.get('X-Admin-Password') != _pub_pass):
        return jsonify({'error': 'Unauthorized'}), 401

    data          = request.get_json(silent=True) or {}
    title         = data.get('title', '').strip()
    description   = data.get('description', '').strip()
    category      = data.get('category', 'other').strip()
    thumbnail_url = (data.get('thumbnail_url') or '').strip() or None
    vhx_url       = (data.get('vhx_url') or '').strip() or None

    if not title:
        return jsonify({'error': 'title is required'}), 400

    from datetime import date as _date
    import uuid as _uuid

    videos = _load_videos()
    vid_id = 'vid_' + _uuid.uuid4().hex[:8]
    videos.append({
        'id':            vid_id,
        'title':         title,
        'description':   description,
        'category':      category,
        'thumbnail_url': thumbnail_url,
        'vhx_url':       vhx_url,
        'created_at':    str(_date.today()),
    })
    _save_videos(videos)

    r = jsonify({'success': True, 'id': vid_id})
    r.headers['Access-Control-Allow-Origin'] = '*'
    return r


@app.route('/admin/pdfs', methods=['GET', 'POST'])
@_admin_required
def admin_pdfs():
    message = None
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category    = request.form.get('category', 'other').strip()
        pdf_file    = request.files.get('pdf_file')
        thumb_file  = request.files.get('thumbnail_file')

        if not title or not pdf_file:
            message = 'Error: title and PDF file are required.'
        else:
            os.makedirs(_pdfs_dir, exist_ok=True)
            os.makedirs(_thumbs_dir, exist_ok=True)

            import uuid as _uuid
            uid = _uuid.uuid4().hex[:8]
            pdf_name = uid + '_' + _safe_filename(pdf_file.filename or 'file.pdf')
            pdf_file.save(os.path.join(_pdfs_dir, pdf_name))
            pdf_url = '/static/pdfs/' + pdf_name

            thumb_url = None
            if thumb_file and thumb_file.filename:
                thumb_name = uid + '_' + _safe_filename(thumb_file.filename)
                thumb_file.save(os.path.join(_thumbs_dir, thumb_name))
                thumb_url = '/static/pdf-thumbs/' + thumb_name

            pdfs = _load_pdfs()
            pdfs.append({
                'id':          uid,
                'title':       title,
                'description': description,
                'category':    category,
                'url':         pdf_url,
                'thumbnail':   thumb_url,
            })
            _save_pdfs(pdfs)
            message = f'"{title}" uploaded successfully.'

    pdfs = _load_pdfs()
    return render_template('admin_pdfs.html', pdfs=pdfs, message=message)


@app.route('/admin/pdfs/delete', methods=['POST'])
@_admin_required
def admin_pdfs_delete():
    pdf_id = request.form.get('pdf_id', '').strip()
    pdfs   = _load_pdfs()
    entry  = next((p for p in pdfs if p['id'] == pdf_id), None)
    if entry:
        # Remove files
        for field in ('url', 'thumbnail'):
            rel = entry.get(field)
            if rel:
                fpath = os.path.join(_base, rel.lstrip('/'))
                if os.path.exists(fpath):
                    os.remove(fpath)
        pdfs = [p for p in pdfs if p['id'] != pdf_id]
        _save_pdfs(pdfs)
    return redirect(url_for('admin_pdfs'))


# ═══════════════════════════════════════════════════════════════════════════════
# SOCKETIO EVENTS — WebRTC signaling + real-time messaging
# ═══════════════════════════════════════════════════════════════════════════════

if _SIO_OK and socketio:

    @socketio.on('connect')
    def _sio_connect():
        pass  # auth is checked per-event via session

    @socketio.on('disconnect')
    def _sio_disconnect():
        global _sio_broadcaster, _sio_viewers, _online_users
        sid = request.sid
        with _sio_lock:
            is_broadcaster = (sid == _sio_broadcaster)
            if is_broadcaster:
                _sio_broadcaster = None
            _sio_viewers.pop(sid, None)
            _online_users.pop(sid, None)
            count = len(_sio_viewers)
        if is_broadcaster:
            try:
                settings = _load_live_settings()
                if settings.get('stream_mode') == 'webrtc':
                    settings['status']     = 'off'
                    settings['stream_mode'] = ''
                    _save_live_settings(settings)
            except Exception:
                pass
            socketio.emit('stream_ended', {}, to='livestream')
        socketio.emit('viewer_count', {'count': count}, to='livestream')

    # ── WebRTC live streaming ────────────────────────────────────────────────

    @socketio.on('broadcaster_ready')
    def _sio_broadcaster_ready(data=None):
        global _sio_broadcaster
        # Prefer token-based auth (session cookies are unreliable over
        # WebSocket-only transport on some hosts).  Fall back to session
        # flag so older clients still work.
        data = data or {}
        token_ok = (
            _sio_broadcast_token is not None
            and data.get('token') == _sio_broadcast_token
        )
        if not token_ok and not session.get('is_admin'):
            print(f"[broadcaster_ready] BLOCKED — token_ok={token_ok} "
                  f"is_admin={session.get('is_admin')} sid={request.sid}")
            return
        with _sio_lock:
            _sio_broadcaster = request.sid
        _sio_join('livestream')
        settings = _load_live_settings()
        settings['status']      = 'live'
        settings['stream_mode'] = 'webrtc'
        _save_live_settings(settings)
        socketio.emit('stream_started', {}, to='livestream', include_self=False)
        with _sio_lock:
            count = len(_sio_viewers)
        _sio_emit('viewer_count', {'count': count})

    @socketio.on('stop_broadcast')
    def _sio_stop_broadcast(data=None):
        global _sio_broadcaster
        data = data or {}
        token_ok = (
            _sio_broadcast_token is not None
            and data.get('token') == _sio_broadcast_token
        )
        if not token_ok and not session.get('is_admin'):
            return
        with _sio_lock:
            _sio_broadcaster = None
        settings = _load_live_settings()
        settings['status']      = 'off'
        settings['stream_mode'] = ''
        _save_live_settings(settings)
        socketio.emit('stream_ended', {}, to='livestream')

    @socketio.on('join_live')
    def _sio_join_live():
        global _sio_viewers
        sid   = request.sid
        email = session.get('user_email', '')
        name  = session.get('user_name', 'Member') or 'Member'
        _sio_join('livestream')
        with _sio_lock:
            _sio_viewers[sid]  = {'email': email, 'name': name}
            broadcaster        = _sio_broadcaster
            count              = len(_sio_viewers)
        socketio.emit('viewer_count', {'count': count}, to='livestream')
        if broadcaster:
            socketio.emit('new_viewer', {'sid': sid, 'name': name}, to=broadcaster)
        _sio_emit('stream_state', {'is_live': broadcaster is not None})

    @socketio.on('leave_live')
    def _sio_leave_live():
        global _sio_viewers
        sid = request.sid
        _sio_leave('livestream')
        with _sio_lock:
            _sio_viewers.pop(sid, None)
            count = len(_sio_viewers)
        socketio.emit('viewer_count', {'count': count}, to='livestream')

    @socketio.on('webrtc_offer')
    def _sio_webrtc_offer(data):
        to = data.get('to')
        if to:
            socketio.emit('webrtc_offer',
                          {'offer': data.get('offer'), 'from': request.sid}, to=to)

    @socketio.on('webrtc_answer')
    def _sio_webrtc_answer(data):
        to = data.get('to')
        if to:
            socketio.emit('webrtc_answer',
                          {'answer': data.get('answer'), 'from': request.sid}, to=to)

    @socketio.on('webrtc_ice')
    def _sio_webrtc_ice(data):
        to = data.get('to')
        if to:
            socketio.emit('webrtc_ice',
                          {'candidate': data.get('candidate'), 'from': request.sid}, to=to)

    @socketio.on('live_chat')
    def _sio_live_chat(data):
        email = session.get('user_email', '')
        if not email:
            return
        name     = session.get('user_name', 'Member') or 'Member'
        content  = (data.get('content') or '').strip()[:500]
        is_admin = bool(session.get('is_admin'))
        if not content:
            return
        msg = {
            'name':     name,
            'content':  content,
            'is_admin': is_admin,
            'ts':       datetime.datetime.utcnow().strftime('%H:%M'),
        }
        socketio.emit('live_chat', msg, to='livestream')

    # ── Real-time messaging ──────────────────────────────────────────────────

    @socketio.on('join_chat')
    def _sio_join_chat(data):
        chat_id = (data.get('chat_id') or '').strip()
        if chat_id:
            _sio_join(f'chat:{chat_id}')

    @socketio.on('leave_chat')
    def _sio_leave_chat(data):
        chat_id = (data.get('chat_id') or '').strip()
        if chat_id:
            _sio_leave(f'chat:{chat_id}')

    # ── Peer-to-peer video call signaling ────────────────────────────────────
    # Each DM chat gets a call room: call:<chat_id>
    # Server only relays — no media touches the server.

    @socketio.on('join_call_room')
    def _sio_join_call_room(data):
        chat_id = (data.get('chat_id') or '').strip()
        if chat_id:
            _sio_join(f'call:{chat_id}')

    @socketio.on('call_invite')
    def _sio_call_invite(data):
        """Caller announces a call to the room (all other participants)."""
        chat_id     = (data.get('chat_id') or '').strip()
        caller_name = (session.get('user_name') or session.get('user_email') or 'Someone').split()[0]
        if chat_id:
            # ── APNs push FIRST — fires before socket so it arrives even if
            #    the member's WKWebView socket is not connected ──────────────
            if chat_id.startswith('dm:') and session.get('is_admin'):
                member_email = chat_id[3:].lower()
                _push_to_member(
                    member_email,
                    '📹 Incoming Video Call',
                    'Jeff is calling you \u2014 tap to answer',
                    'video_call',
                    extra={'url': '/video-jeff'},
                )

            payload = {'from': request.sid, 'caller_name': caller_name, 'chat_id': chat_id}
            socketio.emit('call_invite', payload, to=f'call:{chat_id}', include_self=False)
            # When a member calls, also ping the admin's global toast (any admin page)
            if not session.get('is_admin'):
                socketio.emit('call_invite', payload, to='call:admin')
            # HTTP fallback: store/update pending call so member can poll /api/incoming-call
            # Works even when WKWebView SocketIO connection isn't established.
            # If admin_members already POSTed a pending call, update from_sid with real SID.
            if chat_id.startswith('dm:'):
                member_email = chat_id[3:].lower()
                existing = _pending_calls.get(member_email)
                _pending_calls[member_email] = {
                    'caller_name': caller_name,
                    'from_sid':    request.sid,
                    'chat_id':     chat_id,
                    'expires_at':  time.time() + 30,
                }

    @socketio.on('call_accept')
    def _sio_call_accept(data):
        """Callee accepts — sends their sid to the caller."""
        to = data.get('to')
        if to:
            socketio.emit('call_accept', {'from': request.sid}, to=to)
        # Clear any pending call stored for HTTP polling
        email = (session.get('user_email') or '').lower()
        _pending_calls.pop(email, None)

    @socketio.on('call_decline')
    def _sio_call_decline(data):
        """Callee declines."""
        to = data.get('to')
        if to:
            socketio.emit('call_decline', {}, to=to)
        # Clear any pending call stored for HTTP polling
        email = (session.get('user_email') or '').lower()
        _pending_calls.pop(email, None)

    @socketio.on('call_offer')
    def _sio_call_offer(data):
        """Caller sends WebRTC offer to callee."""
        to = data.get('to')
        if to:
            socketio.emit('call_offer', {'offer': data.get('offer'), 'from': request.sid}, to=to)

    @socketio.on('call_answer')
    def _sio_call_answer(data):
        """Callee sends WebRTC answer to caller."""
        to = data.get('to')
        if to:
            socketio.emit('call_answer', {'answer': data.get('answer'), 'from': request.sid}, to=to)

    @socketio.on('call_ice')
    def _sio_call_ice(data):
        """Relay ICE candidate between peers."""
        to = data.get('to')
        if to:
            socketio.emit('call_ice', {'candidate': data.get('candidate'), 'from': request.sid}, to=to)

    @socketio.on('call_end')
    def _sio_call_end(data):
        """Either party ends the call — notify the whole room."""
        chat_id = (data.get('chat_id') or '').strip()
        if chat_id:
            socketio.emit('call_end', {}, to=f'call:{chat_id}')

    # ── Online presence ──────────────────────────────────────────────────────

    @socketio.on('user_online')
    def _sio_user_online():
        """Member emits this on page load to register as online."""
        email = session.get('user_email', '')
        name  = session.get('user_name', '') or (email.split('@')[0] if email else '')
        if not email or session.get('is_admin'):
            return
        sid = request.sid
        with _sio_lock:
            _online_users[sid] = {'email': email, 'name': name, 'last_seen': time.time()}
        # Auto-join DM call room so Jeff can reach the member from any page
        _sio_join(f'call:dm:{email}')

    @socketio.on('user_heartbeat')
    def _sio_user_heartbeat():
        """Client sends every 30s to stay marked online."""
        sid = request.sid
        with _sio_lock:
            if sid in _online_users:
                _online_users[sid]['last_seen'] = time.time()


@app.route('/api/ping-online', methods=['GET', 'POST'])
def api_ping_online():
    """Any logged-in member hits this on page load to mark themselves online.
    Works from web browsers AND iOS WKWebViews without requiring socket.io.
    Accepts GET or POST so WKWebView fetch() calls always succeed."""
    email = session.get('user_email', '')
    name  = session.get('user_name', '') or (email.split('@')[0] if email else '')
    if not email or session.get('is_admin'):
        return jsonify({'ok': False, 'reason': 'no session'}), 403
    with _sio_lock:
        _http_online[email] = {'name': name, 'last_seen': time.time()}
    return jsonify({'ok': True, 'email': email})


@app.route('/api/incoming-call', methods=['GET', 'POST'])
def api_incoming_call():
    """HTTP fallback for incoming call notification.
    GET  — member polls; returns pending call for the logged-in user (or null).
    POST (admin) — Jeff stores a pending call: {email, caller_name}.
    POST (member) — member accepted/declined; clears their own pending call.
    Ensures the popup appears even when WKWebView SocketIO fails.
    """
    if not session.get('logged_in'):
        return jsonify({'call': None})
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if session.get('is_admin'):
            # Jeff is storing a pending call for a member
            target_email  = (data.get('email') or '').strip().lower()
            caller_name   = (data.get('caller_name') or 'Jeff').strip()
            if target_email:
                _pending_calls[target_email] = {
                    'caller_name': caller_name,
                    'from_sid':    None,   # SocketIO SID not available here; set later by socket
                    'chat_id':     f'dm:{target_email}',
                    'expires_at':  time.time() + 30,
                }
                # Fire APNs push immediately — do not rely solely on SocketIO call_invite
                # (SocketIO often fails to connect inside WKWebView on iOS)
                _push_to_member(
                    target_email,
                    '📹 Incoming Video Call',
                    f'{caller_name} is calling you \u2014 tap to answer',
                    'video_call',
                    extra={'url': '/video-jeff'},
                )
            return jsonify({'ok': True})
        else:
            # Member clearing their own pending call (accepted or declined)
            email = (session.get('user_email') or '').lower()
            _pending_calls.pop(email, None)
            return jsonify({'ok': True})
    # GET — member polls for a pending call
    email = (session.get('user_email') or '').lower()
    call  = _pending_calls.get(email)
    if not call:
        return jsonify({'call': None})
    if call['expires_at'] < time.time():
        _pending_calls.pop(email, None)
        return jsonify({'call': None})
    return jsonify({'call': {
        'caller_name': call['caller_name'],
        'from_sid':    call['from_sid'],
        'chat_id':     call['chat_id'],
    }})


@app.route('/api/whoami')
def api_whoami():
    """Debug endpoint — returns current session state so you can verify
    the iOS app / WKWebView is actually logged in."""
    return jsonify({
        'logged_in':  bool(session.get('logged_in')),
        'user_email': session.get('user_email', None),
        'user_name':  session.get('user_name', None),
        'is_admin':   bool(session.get('is_admin')),
    })


@app.route('/api/register-device', methods=['POST'])
def api_register_device():
    """iOS app calls this after login to store push tokens.
    Accepts apns_token (raw APNs hex token, primary) and player_id (OneSignal, fallback).
    At least one push token is required."""
    data       = request.get_json(silent=True) or {}
    email      = (data.get('email')      or '').strip().lower()
    token      = (data.get('token')      or '').strip()
    apns_token = (data.get('apns_token') or '').strip()
    player_id  = (data.get('player_id') or '').strip()
    if not email or not token:
        return jsonify({'ok': False, 'error': 'missing fields'}), 400
    if not apns_token and not player_id:
        return jsonify({'ok': False, 'error': 'missing push token'}), 400
    users = _load_users()
    user  = users.get(email)
    if not user or user.get('ios_token') != token:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    if apns_token:
        users[email]['apns_device_token'] = apns_token
        print(f'[DEVICE] ✅ APNs token saved for {email}: {apns_token}')
    if player_id:
        users[email]['onesignal_player_id'] = player_id
        print(f'[DEVICE] ✅ OneSignal player_id saved for {email}: {player_id}')
    _save_users(users)
    # Verify what was actually written
    saved = _load_users().get(email, {})
    print(f'[DEVICE] 📋 Verified users.json for {email}: apns_device_token={saved.get("apns_device_token","(none)")[:20]}...')
    return jsonify({'ok': True, 'apns_token_saved': bool(apns_token), 'player_id_saved': bool(player_id)})


@app.route('/api/test-push', methods=['GET', 'POST'])
def api_test_push():
    """Send a test APNs push to the currently logged-in user (GET or POST).
    Useful for verifying APNs config + device token registration."""
    email, _ = _msg_auth()
    if not email:
        return jsonify({'ok': False, 'error': 'not logged in'}), 401
    users      = _load_users()
    user       = users.get(email, {})
    apns_token = user.get('apns_device_token', '').strip()
    player_id  = user.get('onesignal_player_id', '').strip()
    if not apns_token and not player_id:
        return jsonify({'ok': False, 'error': f'no push token registered for {email}',
                        'hint': 'open the app and wait for DeviceRegistration to run'}), 400
    print(f'[TEST-PUSH] sending test push to {email} apns={apns_token[:20] if apns_token else "none"} onesignal={player_id[:20] if player_id else "none"}')
    _push_to_member(email, '🔔 Test Push', f'APNs working for {email}!', 'message')
    return jsonify({
        'ok': True,
        'email': email,
        'apns_token': apns_token[:20] + '...' if apns_token else None,
        'player_id':  player_id[:20] + '...' if player_id else None,
    })


@app.route('/api/online-users')
def api_online_users():
    """Return list of currently online members (admin only).
    Merges socket-based presence (_online_users) with HTTP-ping presence (_http_online)
    so iOS app users and web users both appear."""
    if not session.get('is_admin'):
        return jsonify({'error': 'unauthorized'}), 403
    now = time.time()
    socket_cutoff = now - 300  # socket heartbeat every 30s → 5 min TTL
    http_cutoff   = now - 300  # HTTP ping every 60s → 5 min TTL
    with _sio_lock:
        socket_users = [u for u in _online_users.values() if u['last_seen'] > socket_cutoff]
        http_users   = [{'email': e, 'name': v['name']}
                        for e, v in _http_online.items() if v['last_seen'] > http_cutoff]
    # Never show the admin's own email(s) in the Online Now panel
    own_email = (session.get('user_email') or '').lower()
    seen, unique = set(), []
    for u in socket_users:
        if u['email'] not in seen and u['email'].lower() != own_email:
            seen.add(u['email'])
            unique.append({'email': u['email'], 'name': u['name']})
    for u in http_users:
        if u['email'] not in seen and u['email'].lower() != own_email:
            seen.add(u['email'])
            unique.append(u)
    return jsonify({'online': unique})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    if socketio:
        socketio.run(app, host='0.0.0.0', port=port, debug=True)
    else:
        app.run(host='0.0.0.0', port=port, debug=True)
