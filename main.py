from flask import Flask, render_template, redirect, url_for, session, request, jsonify
import os, json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# --- Load content from data/content.json ---
_content_path = os.path.join(os.path.dirname(__file__), 'data', 'content.json')
with open(_content_path) as _f:
    _content = json.load(_f)

ALL_VHX_VIDEOS = _content['videos']       # 415 videos from VHX API
COLLECTIONS = _content['collections']     # 84 collections
PRODUCTS = _content['products']           # 30 products

# Keep YouTube-based Express and Revelation videos for the streaming section
EXPRESS_VIDEOS = [
    {"id":"express-1","title":"EXPRESS 1","youtube_id":"OzXRBaFP3C8","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-2","title":"EXPRESS 2","youtube_id":"AfDG2NfXpuY","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-3","title":"EXPRESS 3","youtube_id":"mYv2AlKP1rI","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-4","title":"EXPRESS 4","youtube_id":"r8ZlAUe4p1k","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-5","title":"EXPRESS 5","youtube_id":"BscrzC2yyjE","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-6","title":"EXPRESS 6","youtube_id":"jpRuYGwrsU0","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-7","title":"EXPRESS 7","youtube_id":"Wh-FGd_Y2GM","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-8","title":"EXPRESS 8","youtube_id":"evVWecl3e3k","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-9","title":"EXPRESS 9","youtube_id":"06QLZvQn6aI","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-10","title":"EXPRESS 10","youtube_id":"qLLw-TeZRZs","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-11","title":"EXPRESS 11","youtube_id":"cqZ21h5Pkr4","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-12","title":"EXPRESS 12","youtube_id":"bai-J_qVhnU","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-13","title":"EXPRESS 13","youtube_id":"fMwf0RJgFXs","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-14","title":"EXPRESS 14","youtube_id":"WoOFkIk6g0E","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-15","title":"EXPRESS 15","youtube_id":"sozSthazhNo","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-16","title":"EXPRESS 16","youtube_id":"4Ifkq6BXX0Y","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-17","title":"EXPRESS 17","youtube_id":"AfDG2NfXpuY","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-18","title":"EXPRESS 18","youtube_id":"pJUtp0yuBXs","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-19","title":"EXPRESS 19","youtube_id":"1wcspRrbIbM","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-20","title":"EXPRESS 20","youtube_id":"g5EEUkYIu7k","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-21","title":"EXPRESS 21","youtube_id":"9t2e_gu8p9s","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-22","title":"EXPRESS 22","youtube_id":"QdwJTQucN7U","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-23","title":"EXPRESS 23","youtube_id":"TsGRrNzd1k4","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-24","title":"EXPRESS 24","youtube_id":"6ce1FUhRuGA","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-25","title":"EXPRESS 25","youtube_id":"QrzZR8VGiV4","series":"EXPRESS 2026","duration":"10 min"},
    {"id":"express-26","title":"EXPRESS 26","youtube_id":"nRfQxL4SxS4","series":"EXPRESS 2026","duration":"10 min"},
]

REVELATION_VIDEOS = [
    {"id":"rev-1","title":"EP1 BEFORE YOU READ IT","youtube_id":"yDF-a1WUCis","series":"REVELATION","duration":"10 min"},
    {"id":"rev-2","title":"EP2 THE GREAT REVEAL","youtube_id":"TslYNmqcRwk","series":"REVELATION","duration":"10 min"},
    {"id":"rev-3","title":"EP3 THE PROMISE","youtube_id":"IkMUdxygZGo","series":"REVELATION","duration":"10 min"},
    {"id":"rev-4","title":"EP4 MYSTERY OF THE SEVEN SPIRITS","youtube_id":"XPEDZA368T0","series":"REVELATION","duration":"10 min"},
    {"id":"rev-5","title":"EP5 A STUNNING VISION","youtube_id":"vTP7mS3SzpQ","series":"REVELATION","duration":"10 min"},
    {"id":"rev-6","title":"EP6 FACE-TO-FACE WITH THE KING","youtube_id":"4Rl9U3vC6aI","series":"REVELATION","duration":"10 min"},
    {"id":"rev-7","title":"EP7 MYSTERY OF THE SEVEN STARS","youtube_id":"Gn_g6bS35FA","series":"REVELATION","duration":"10 min"},
    {"id":"rev-8","title":"EP8 DIANA AND THE EPHESIANS","youtube_id":"Gbms60MuJtg","series":"REVELATION","duration":"10 min"},
    {"id":"rev-9","title":"EP9 COULD THIS HAPPEN TO YOUR CHURCH","youtube_id":"HgKHTjs_h1E","series":"REVELATION","duration":"10 min"},
    {"id":"rev-10","title":"EP10 JUST A PINCH","youtube_id":"WoOFkIk6g0E","series":"REVELATION","duration":"10 min"},
    {"id":"rev-11","title":"EP11 THE CHURCH THAT WOULDN'T BREAK","youtube_id":"evVWecl3e3k","series":"REVELATION","duration":"10 min"},
]

STREAMABLE_VIDEOS = EXPRESS_VIDEOS + REVELATION_VIDEOS


def get_video_by_id(video_id):
    for v in STREAMABLE_VIDEOS:
        if v['id'] == video_id:
            return v
    return None

def get_product_by_id(product_id):
    for p in PRODUCTS:
        if p['id'] == product_id:
            return p
    return None

def get_product_videos(product_id):
    product = get_product_by_id(product_id)
    if not product:
        return []
    vhx_id = product.get('vhx_id', '')
    # Match by product_ids list in each video
    return [v for v in ALL_VHX_VIDEOS if vhx_id and int(vhx_id) in (v.get('product_ids') or [])]


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/')
def index():
    sample_videos = EXPRESS_VIDEOS[:8] + REVELATION_VIDEOS[:4]
    # Exclude system/subscription products (0 videos or no price)
    purchasable = [p for p in PRODUCTS if p.get('video_count', 0) > 0 and p.get('price')]
    top_programs = purchasable[:8]
    return render_template('index.html', sample_videos=sample_videos, programs=top_programs)


@app.route('/browse')
def browse():
    query = request.args.get('q', '').lower()
    if query:
        results = [v for v in STREAMABLE_VIDEOS
                   if query in v['title'].lower() or query in v.get('series', '').lower()]
        return render_template('browse.html',
            express_videos=[], revelation_videos=[], results=results, query=query)
    return render_template('browse.html',
        express_videos=EXPRESS_VIDEOS, revelation_videos=REVELATION_VIDEOS,
        results=None, query='')


@app.route('/watch/<video_id>')
def watch(video_id):
    video = get_video_by_id(video_id)
    if not video:
        return redirect(url_for('browse'))
    if video.get('series') == 'EXPRESS 2026':
        related = [v for v in EXPRESS_VIDEOS if v['id'] != video_id][:6]
    else:
        related = [v for v in REVELATION_VIDEOS if v['id'] != video_id][:6]
    return render_template('watch.html', video=video, related=related)


@app.route('/programs')
def programs():
    purchasable = [p for p in PRODUCTS if p.get('video_count', 0) > 0 and p.get('price')]
    return render_template('programs.html', programs=purchasable)


@app.route('/programs/<product_id>')
def program_detail(product_id):
    product = get_product_by_id(product_id)
    if not product:
        return redirect(url_for('programs'))
    videos = get_product_videos(product_id)
    return render_template('program_detail.html', program=product, videos=videos)


@app.route('/subscribe')
def subscribe():
    return render_template('subscribe.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['logged_in'] = True
        session['user_email'] = request.form.get('email', '')
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/account')
def account():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('account.html')


@app.route('/api/content')
def api_content():
    """JSON endpoint exposing all scraped VHX content."""
    return jsonify({
        'video_count': len(ALL_VHX_VIDEOS),
        'product_count': len(PRODUCTS),
        'collection_count': len(COLLECTIONS),
        'videos': ALL_VHX_VIDEOS,
        'products': PRODUCTS
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
