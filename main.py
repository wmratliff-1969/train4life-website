from flask import (Flask, render_template, redirect, url_for, session,
                   request, jsonify, flash, Response)
import os, json, hashlib, datetime, re
from collections import defaultdict
from functools import wraps

# Load stripe conditionally so app works without it
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'train4life-secret-2026-change-in-prod')

# Stripe config
STRIPE_PUBLIC_KEY  = os.environ.get('STRIPE_PUBLIC_KEY', '')
STRIPE_SECRET_KEY  = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
if STRIPE_AVAILABLE and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5001')

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

def _current_user():
    """Return the current user's data dict, or None."""
    if not session.get('logged_in'):
        return None
    users = _load_users()
    return users.get(session.get('user_email'))

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
        revelation_videos=REVELATION_VIDEOS[:4],
        stripe_public_key=STRIPE_PUBLIC_KEY)


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
                               player='youtube', subscribed=subscribed)

    # VHX video
    video = _vid_by_id.get(video_id)
    if not video:
        return redirect(url_for('browse'))

    member_only = _video_is_member_only(video)
    if member_only and not subscribed:
        return render_template('upgrade_wall.html', video=video,
                               stripe_public_key=STRIPE_PUBLIC_KEY)

    cid = video.get('canonical_collection_id', '')
    related = [v for v in _vids_by_coll.get(cid, []) if v['id'] != video_id][:8]
    if not related:
        related = ALL_VHX_VIDEOS[:8]

    return render_template('watch.html', video=video, related=related,
                           player='vhx', subscribed=subscribed)


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
    # If coming back from Stripe with session_id, verify and mark user
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

    if event['type'] in ('checkout.session.completed', 'invoice.payment_succeeded'):
        obj = event['data']['object']
        email = obj.get('customer_email') or (obj.get('metadata') or {}).get('user_email', '')
        plan = (obj.get('metadata') or {}).get('plan', 'monthly')
        if email:
            users = _load_users()
            if email in users:
                users[email]['plan'] = 'Annual' if plan == 'annual' else 'Monthly'
                users[email]['stripe_customer_id'] = obj.get('customer', '')
                _save_users(users)

    elif event['type'] in ('customer.subscription.deleted', 'customer.subscription.paused'):
        obj = event['data']['object']
        customer_id = obj.get('customer', '')
        if customer_id:
            users = _load_users()
            for email, u in users.items():
                if u.get('stripe_customer_id') == customer_id:
                    u['plan'] = None
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
