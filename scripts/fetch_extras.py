"""
Fetch all VHX extras and save to static/extras.json.
Run from project root: python3 scripts/fetch_extras.py
"""
import requests
import json
import os

VHX_API_KEY = 'W8R9VxBi3sWsDk8G5ymMTpRqgXwWyU4i'
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'static', 'extras.json')

all_extras = []
page = 1
while True:
    response = requests.get(
        'https://api.vhx.tv/extras',
        auth=(VHX_API_KEY, ''),
        params={'per_page': 100, 'page': page}
    )
    data = response.json()
    extras = data.get('_embedded', {}).get('extras', [])
    if not extras:
        break
    all_extras.extend(extras)
    total = data.get('total', 0)
    print(f"Page {page}: {len(extras)} extras, total so far: {len(all_extras)}/{total}")
    if len(all_extras) >= total:
        break
    page += 1

with open(OUTPUT, 'w') as f:
    json.dump(all_extras, f, indent=2)

print(f"Done. Total extras saved: {len(all_extras)}")
