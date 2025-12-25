import requests
from bs4 import BeautifulSoup
import re
from user_agent import generate_user_agent
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import os

PIN_PROVIDER_URL = os.environ.get("PIN_PROVIDER_URL")
KEYS_FILE = "pinkeys.txt"

PINIMG_DOMAINS = ("pinimg.com", "v.pinimg.com", "i.pinimg.com")

def is_real_media(url):
    return (
        url
        and any(d in url for d in PINIMG_DOMAINS)
        and any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".mp4"])
    )

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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        api_key = query.get("key", [None])[0]
        url = query.get("url", [None])[0]

        if not api_key or not is_key_valid(api_key):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Invalid or expired API key"}).encode())
            return

        if not url:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Missing 'url' parameter"}).encode())
            return

        if not PIN_PROVIDER_URL:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Provider not configured"}).encode())
            return

        headers = {
            "user-agent": generate_user_agent(),
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://www.expertstool.com",
            "referer": PIN_PROVIDER_URL
        }

        try:
            r = requests.post(PIN_PROVIDER_URL, headers=headers, data={"url": url.strip()}, timeout=20)
            r.raise_for_status()
            html = r.text

            if any(x in html.lower() for x in ["api not work", "invalid", "captcha"]):
                raise Exception("Invalid Pinterest URL or service down")

            soup = BeautifulSoup(html, "html.parser")
            video_link = None
            photo_link = None

            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True).lower()
                if is_real_media(href) and href.lower().endswith(".mp4"):
                    if any(q in text for q in ["1080", "original", "hd"]):
                        video_link = href
                        break
                    if not video_link:
                        video_link = href

            if not video_link:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if is_real_media(href) and not href.lower().endswith(".mp4"):
                        photo_link = href
                        break

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            if video_link and is_real_media(video_link):
                self.wfile.write(json.dumps({"status": "success", "video": video_link, "dev": "@UseSir"}).encode())
            elif photo_link and is_real_media(photo_link):
                self.wfile.write(json.dumps({"status": "success", "photo": photo_link, "dev": "@UseSir"}).encode())
            else:
                self.wfile.write(json.dumps({"status": "error", "message": "No media found"}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
