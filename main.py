from flask import Flask, render_template, redirect, url_for, session, request, jsonify, flash
import os, json, hashlib, datetime
from collections import defaultdict
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'train4life-secret-2026-change-in-prod')

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
     "thumbnail":"https://img.youtube.com/vi/OzXRBaFP3C8/mqdefault.jpg"},
    {"id":"express-2","title":"EXPRESS 2","youtube_id":"AfDG2NfXpuY","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/AfDG2NfXpuY/mqdefault.jpg"},
    {"id":"express-3","title":"EXPRESS 3","youtube_id":"mYv2AlKP1rI","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/mYv2AlKP1rI/mqdefault.jpg"},
    {"id":"express-4","title":"EXPRESS 4","youtube_id":"r8ZlAUe4p1k","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/r8ZlAUe4p1k/mqdefault.jpg"},
    {"id":"express-5","title":"EXPRESS 5","youtube_id":"BscrzC2yyjE","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/BscrzC2yyjE/mqdefault.jpg"},
    {"id":"express-6","title":"EXPRESS 6","youtube_id":"jpRuYGwrsU0","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/jpRuYGwrsU0/mqdefault.jpg"},
    {"id":"express-7","title":"EXPRESS 7","youtube_id":"Wh-FGd_Y2GM","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/Wh-FGd_Y2GM/mqdefault.jpg"},
    {"id":"express-8","title":"EXPRESS 8","youtube_id":"evVWecl3e3k","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/evVWecl3e3k/mqdefault.jpg"},
    {"id":"express-9","title":"EXPRESS 9","youtube_id":"06QLZvQn6aI","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/06QLZvQn6aI/mqdefault.jpg"},
    {"id":"express-10","title":"EXPRESS 10","youtube_id":"qLLw-TeZRZs","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/qLLw-TeZRZs/mqdefault.jpg"},
    {"id":"express-11","title":"EXPRESS 11","youtube_id":"cqZ21h5Pkr4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/cqZ21h5Pkr4/mqdefault.jpg"},
    {"id":"express-12","title":"EXPRESS 12","youtube_id":"bai-J_qVhnU","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/bai-J_qVhnU/mqdefault.jpg"},
    {"id":"express-13","title":"EXPRESS 13","youtube_id":"fMwf0RJgFXs","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/fMwf0RJgFXs/mqdefault.jpg"},
    {"id":"express-14","title":"EXPRESS 14","youtube_id":"WoOFkIk6g0E","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/WoOFkIk6g0E/mqdefault.jpg"},
    {"id":"express-15","title":"EXPRESS 15","youtube_id":"sozSthazhNo","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/sozSthazhNo/mqdefault.jpg"},
    {"id":"express-16","title":"EXPRESS 16","youtube_id":"4Ifkq6BXX0Y","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/4Ifkq6BXX0Y/mqdefault.jpg"},
    {"id":"express-17","title":"EXPRESS 17","youtube_id":"AfDG2NfXpuY","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/AfDG2NfXpuY/mqdefault.jpg"},
    {"id":"express-18","title":"EXPRESS 18","youtube_id":"pJUtp0yuBXs","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/pJUtp0yuBXs/mqdefault.jpg"},
    {"id":"express-19","title":"EXPRESS 19","youtube_id":"1wcspRrbIbM","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/1wcspRrbIbM/mqdefault.jpg"},
    {"id":"express-20","title":"EXPRESS 20","youtube_id":"g5EEUkYIu7k","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/g5EEUkYIu7k/mqdefault.jpg"},
    {"id":"express-21","title":"EXPRESS 21","youtube_id":"9t2e_gu8p9s","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/9t2e_gu8p9s/mqdefault.jpg"},
    {"id":"express-22","title":"EXPRESS 22","youtube_id":"QdwJTQucN7U","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/QdwJTQucN7U/mqdefault.jpg"},
    {"id":"express-23","title":"EXPRESS 23","youtube_id":"TsGRrNzd1k4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/TsGRrNzd1k4/mqdefault.jpg"},
    {"id":"express-24","title":"EXPRESS 24","youtube_id":"6ce1FUhRuGA","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/6ce1FUhRuGA/mqdefault.jpg"},
    {"id":"express-25","title":"EXPRESS 25","youtube_id":"QrzZR8VGiV4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/QrzZR8VGiV4/mqdefault.jpg"},
    {"id":"express-26","title":"EXPRESS 26","youtube_id":"nRfQxL4SxS4","series":"EXPRESS 2026","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/nRfQxL4SxS4/mqdefault.jpg"},
]
REVELATION_VIDEOS = [
    {"id":"rev-1","title":"EP1 BEFORE YOU READ IT","youtube_id":"yDF-a1WUCis","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/yDF-a1WUCis/mqdefault.jpg"},
    {"id":"rev-2","title":"EP2 THE GREAT REVEAL","youtube_id":"TslYNmqcRwk","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/TslYNmqcRwk/mqdefault.jpg"},
    {"id":"rev-3","title":"EP3 THE PROMISE","youtube_id":"IkMUdxygZGo","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/IkMUdxygZGo/mqdefault.jpg"},
    {"id":"rev-4","title":"EP4 MYSTERY OF THE SEVEN SPIRITS","youtube_id":"XPEDZA368T0","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/XPEDZA368T0/mqdefault.jpg"},
    {"id":"rev-5","title":"EP5 A STUNNING VISION","youtube_id":"vTP7mS3SzpQ","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/vTP7mS3SzpQ/mqdefault.jpg"},
    {"id":"rev-6","title":"EP6 FACE-TO-FACE WITH THE KING","youtube_id":"4Rl9U3vC6aI","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/4Rl9U3vC6aI/mqdefault.jpg"},
    {"id":"rev-7","title":"EP7 MYSTERY OF THE SEVEN STARS","youtube_id":"Gn_g6bS35FA","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/Gn_g6bS35FA/mqdefault.jpg"},
    {"id":"rev-8","title":"EP8 DIANA AND THE EPHESIANS","youtube_id":"Gbms60MuJtg","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/Gbms60MuJtg/mqdefault.jpg"},
    {"id":"rev-9","title":"EP9 COULD THIS HAPPEN TO YOUR CHURCH","youtube_id":"HgKHTjs_h1E","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/HgKHTjs_h1E/mqdefault.jpg"},
    {"id":"rev-10","title":"EP10 JUST A PINCH","youtube_id":"WoOFkIk6g0E","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/WoOFkIk6g0E/mqdefault.jpg"},
    {"id":"rev-11","title":"EP11 THE CHURCH THAT WOULDN'T BREAK","youtube_id":"evVWecl3e3k","series":"REVELATION","duration":"10:00",
     "thumbnail":"https://img.youtube.com/vi/evVWecl3e3k/mqdefault.jpg"},
]
_yt_by_id = {v['id']: v for v in EXPRESS_VIDEOS + REVELATION_VIDEOS}

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

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/')
def index():
    sample_videos = EXPRESS_VIDEOS[:8] + REVELATION_VIDEOS[:4]
    top_programs = purchasable_products()[:8]
    return render_template('index.html',
        sample_videos=sample_videos,
        programs=top_programs,
        revelation_videos=REVELATION_VIDEOS[:4])


@app.route('/browse')
@login_required
def browse():
    query = request.args.get('q', '').strip().lower()
    if query:
        results = [v for v in ALL_VHX_VIDEOS
                   if query in v['title'].lower()
                   or query in (v.get('collection_title') or '').lower()
                   or query in (v.get('description') or '').lower()]
        # also search YouTube videos
        yt_results = [v for v in (EXPRESS_VIDEOS + REVELATION_VIDEOS)
                      if query in v['title'].lower() or query in v['series'].lower()]
        return render_template('browse.html',
            collection_rows=[], results=results + yt_results,
            query=query, express_videos=[], revelation_videos=[],
            programs=[], watch_history=[])

    # recent history for Continue Watching
    history_ids = session.get('watch_history', [])
    history = [_vid_by_id.get(vid) or _yt_by_id.get(vid) for vid in history_ids[:6]]
    history = [v for v in history if v]

    return render_template('browse.html',
        collection_rows=COLLECTION_ROWS[:15],
        express_videos=EXPRESS_VIDEOS,
        revelation_videos=REVELATION_VIDEOS,
        programs=purchasable_products(),
        results=None, query='',
        watch_history=history)


@app.route('/watch/<video_id>')
@login_required
def watch(video_id):
    # Track history
    history = session.get('watch_history', [])
    if video_id in history:
        history.remove(video_id)
    history.insert(0, video_id)
    session['watch_history'] = history[:20]

    # YouTube-based video?
    video = _yt_by_id.get(video_id)
    if video:
        if video.get('series') == 'EXPRESS 2026':
            related = [v for v in EXPRESS_VIDEOS if v['id'] != video_id][:8]
        else:
            related = [v for v in REVELATION_VIDEOS if v['id'] != video_id][:8]
        return render_template('watch.html', video=video, related=related, player='youtube')

    # VHX video
    video = _vid_by_id.get(video_id)
    if not video:
        return redirect(url_for('browse'))

    cid = video.get('canonical_collection_id', '')
    related = [v for v in _vids_by_coll.get(cid, []) if v['id'] != video_id][:8]
    if not related:
        related = ALL_VHX_VIDEOS[:8]

    return render_template('watch.html', video=video, related=related, player='vhx')


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
    return render_template('subscribe.html')


@app.route('/subscribe/success')
def subscribe_success():
    return render_template('subscribe_success.html')


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
                    'created_at': datetime.datetime.utcnow().isoformat(),
                    'plan': None,
                }
                _save_users(users)
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
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        users = _load_users()
        user  = users.get(email)
        if user and user['password'] == _hash_pw(pw):
            session['logged_in']  = True
            session['user_email'] = email
            session['user_name']  = user.get('name', email.split('@')[0])
            next_url = request.args.get('next') or request.form.get('next') or url_for('browse')
            return redirect(next_url)
        else:
            error = 'Invalid email or password.'
    return render_template('login.html', error=error,
                           next=request.args.get('next', ''))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/account')
@login_required
def account():
    users = _load_users()
    user  = users.get(session['user_email'], {})
    return render_template('account.html', user=user)


@app.route('/api/content')
def api_content():
    return jsonify({
        'video_count':      len(ALL_VHX_VIDEOS),
        'product_count':    len(PRODUCTS),
        'collection_count': len(COLLECTIONS),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
