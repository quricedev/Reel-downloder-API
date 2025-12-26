import os
import json
import requests
import re
import base64
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

PROVIDER_URL = os.environ.get("IG_STORY_PROVIDER")
MEDIA_BASE = os.environ.get("IG_STORY_MEDIA_BASE")

KEYS_FILE = os.path.join(os.path.dirname(__file__), "..", "igstorykey.txt")

def is_key_valid(api_key):
    try:
        with open(KEYS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                key, expiry = line.split(":", 1)
                if key == api_key:
                    return datetime.utcnow() <= datetime.strptime(expiry, "%d/%m/%Y")
    except:
        pass
    return False

def encode_proxy_url(url):
    return base64.urlsafe_b64encode(url.encode()).decode()

def decode_proxy_url(token):
    return base64.urlsafe_b64decode(token.encode()).decode()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if query.get("link", [None])[0]:
            self.handle_proxy(query)
        else:
            self.handle_stories(query)

    def handle_stories(self, query):
        api_key = query.get("key", [None])[0]
        username = query.get("username", [None])[0]

        if not api_key or not is_key_valid(api_key):
            self.send_json(401, {
                "status": "error",
                "message": "Invalid or expired API key"
            })
            return

        if not username:
            self.send_json(400, {
                "status": "error",
                "message": "username is required"
            })
            return

        if not PROVIDER_URL or not MEDIA_BASE:
            self.send_json(500, {
                "status": "error",
                "message": "Api not configured"
            })
            return

        headers = {
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
            "accept": "*/*"
        }

        try:
            r = requests.get(
                f"{PROVIDER_URL}?url={username}&method=allstories",
                headers=headers,
                timeout=20
            )
            r.raise_for_status()
            data = r.json()

            html = data.get("html", "")

            paths = re.findall(
                r'/media\.php\?media=[^"\']+\.mp4[^"\']*',
                html
            )

            paths = list(dict.fromkeys(paths))

            host = self.headers.get("host")
            base_url = f"https://{host}"

            stories = []
            for i, path in enumerate(paths, start=1):
                full_media_url = f"{MEDIA_BASE}{path}"
                token = encode_proxy_url(full_media_url)

                stories.append({
                    "index": i,
                    "type": "video",
                    "download_url": f"{base_url}/api/ig-story?link={token}"
                })

            response = {
                "status": "success",
                "username": username,
                "total_stories": len(stories),
                "stories": stories,
                "provider": "UseSir",
                "owner": "@UseSir / @OverShade"
            }

            self.send_json(200, response)

        except:
            self.send_json(500, {
                "status": "error",
                "message": "failed to fetch stories"
            })

    def handle_proxy(self, query):
        token = query.get("link", [None])[0]

        if not token:
            self.send_response(400)
            self.end_headers()
            return

        try:
            target = decode_proxy_url(token)
            r = requests.get(target, stream=True, timeout=20)

            self.send_response(200)
            self.send_header(
                "Content-Type",
                r.headers.get("Content-Type", "application/octet-stream")
            )
            self.send_header("Content-Disposition", "inline")
            self.end_headers()

            for chunk in r.iter_content(8192):
                if chunk:
                    self.wfile.write(chunk)

        except:
            self.send_response(500)
            self.end_headers()

    def send_json(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload, indent=2).encode())
