import os
import json
import html
import base64
import requests
from bs4 import BeautifulSoup
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime
from user_agent import generate_user_agent

PROVIDER_URL = os.environ.get("TWITTER_PROVIDER")
KEYS_FILE = os.path.join(os.path.dirname(__file__), "..", "twitterkey.txt")

def is_key_valid(api_key):
    try:
        with open(KEYS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if ":" not in line:
                    continue
                key, expiry = line.split(":", 1)
                if key == api_key:
                    return datetime.utcnow() <= datetime.strptime(expiry, "%d/%m/%Y")
    except:
        pass
    return False

def encode_url(url):
    return base64.urlsafe_b64encode(url.encode()).decode()

def decode_url(token):
    return base64.urlsafe_b64decode(token.encode()).decode()

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)

        if query.get("link"):
            self.proxy_video(query)
        else:
            self.fetch_video(query)

    def fetch_video(self, query):
        api_key = query.get("key", [None])[0]
        url = query.get("url", [None])[0]

        if not api_key or not is_key_valid(api_key):
            return self.json(401, "Invalid or expired API key")

        if not url:
            return self.json(400, "Missing 'url' parameter")

        if not PROVIDER_URL:
            return self.json(500, "Api not configured")

        try:
            headers = {
                "User-Agent": generate_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://snapdownloader.com/tools/twitter-video-downloader",
                "Origin": "https://snapdownloader.com"
            }

            encoded = quote(url.strip(), safe="")
            target = f"{PROVIDER_URL}?url={encoded}"

            r = requests.get(
                target,
                headers=headers,
                timeout=20,
                allow_redirects=True
            )

            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            videos = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".mp4" in href.lower():
                    videos.append(html.unescape(href))

            if not videos:
                return self.json(404, "Video not found or tweet is private")

            best = videos[-1]
            token = encode_url(best)

            host = self.headers.get("host")
            proxy_url = f"https://{host}/api/twitter-download?link={token}"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "download_url": proxy_url,
                "quality": "highest",
                "provider": "UseSir",
                "owner": "@UseSir / @OverShade"
            }, indent=2).encode())

        except:
            self.json(500, "failed to fetch twitter video")

    def proxy_video(self, query):
        token = query.get("link", [None])[0]

        try:
            target = decode_url(token)
            r = requests.get(target, stream=True, timeout=20)

            self.send_response(200)
            self.send_header(
                "Content-Type",
                r.headers.get("Content-Type", "video/mp4")
            )
            self.send_header("Content-Disposition", "inline")
            self.end_headers()

            for chunk in r.iter_content(8192):
                if chunk:
                    self.wfile.write(chunk)

        except:
            self.send_response(500)
            self.end_headers()

    def json(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "error",
            "message": message
        }).encode())
