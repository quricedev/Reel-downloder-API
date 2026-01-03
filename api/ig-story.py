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
                if ":" not in line:
                    continue
                key, expiry = line.split(":", 1)
                if key == api_key:
                    return datetime.utcnow() <= datetime.strptime(expiry, "%d/%m/%Y")
    except:
        pass
    return False


def encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode()


def decode_url(token: str) -> str:
    return base64.urlsafe_b64decode(token.encode()).decode()


def normalize_media_url(url: str) -> str:
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return f"{MEDIA_BASE}{url}"
    return url


def detect_quality(url: str) -> str:
    u = url.lower()
    if "1080" in u or "hd" in u or "fhd" in u:
        return "1080p"
    return "720p"


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)

        if query.get("link"):
            return self.handle_proxy(query)

        return self.handle_stories(query)



    def handle_stories(self, query):
        api_key = query.get("key", [None])[0]
        username = query.get("username", [None])[0]

        if not api_key or not is_key_valid(api_key):
            return self.send_json(401, "Invalid or expired API key")

        if not username:
            return self.send_json(400, "username is required")

        if not PROVIDER_URL or not MEDIA_BASE:
            return self.send_json(500, "Api not configured")

        try:
            r = requests.get(
                f"{PROVIDER_URL}?url={username}&method=allstories",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20
            )
            r.raise_for_status()

            html = r.json().get("html", "")


            timestamps = re.findall(
                r'<small>.*?<i class="far fa-clock".*?>.*?</i>\s*(.*?)</small>',
                html,
                re.DOTALL
            )

            stories = []
            seen = set()


            video_matches = re.findall(
                r'<source src="([^"]+\.mp4[^"]*)"',
                html
            )

            for i, raw_url in enumerate(video_matches):
                media_url = normalize_media_url(raw_url)
                if media_url in seen:
                    continue

                seen.add(media_url)

                stories.append({
                    "type": "video",
                    "quality": detect_quality(media_url),
                    "timestamp": timestamps[i] if i < len(timestamps) else None,
                    "url": media_url
                })

            image_matches = re.findall(
                r'<img[^>]+src="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                html,
                re.I
            )

            for j, raw_url in enumerate(image_matches):
                media_url = normalize_media_url(raw_url)
                if media_url in seen:
                    continue

                seen.add(media_url)

                stories.append({
                    "type": "image",
                    "quality": "original",
                    "timestamp": timestamps[len(stories)] if len(stories) < len(timestamps) else None,
                    "url": media_url
                })

            if not stories:
                return self.send_json(404, "No stories found")

            host = self.headers.get("host")
            output = []

            for idx, item in enumerate(stories, start=1):
                token = encode_url(item["url"])
                output.append({
                    "index": idx,
                    "type": item["type"],
                    "quality": item["quality"],
                    "posted": item["timestamp"],
                    "download_url": f"https://{host}/api/ig-story?link={token}"
                })

            self.send_json(200, {
                "status": "success",
                "username": username,
                "total_stories": len(output),
                "stories": output,
                "provider": "UseSir",
                "owner": "@UseSir / @OverShade"
            })

        except Exception as e:
            self.send_json(500, "failed to fetch stories")


    def handle_proxy(self, query):
        token = query.get("link", [None])[0]

        try:
            target = decode_url(token)

            if not target.startswith("http"):
                raise Exception("Invalid media URL")

            r = requests.get(target, stream=True, timeout=20)
            r.raise_for_status()

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


    def send_json(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(
            {"status": "error" if code != 200 else "success", "message": message},
            indent=2
        ).encode())
