import requests
from bs4 import BeautifulSoup
import html
from user_agent import generate_user_agent
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        url = query.get("url", [None])[0]

        if not url:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "message": "Missing 'url' parameter"
            }).encode())
            return

        try:
            headers = {
                "User-Agent": generate_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            encoded_url = requests.utils.quote(url.strip(), safe="")
            target_url = (
                "https://snapdownloader.com/tools/"
                f"instagram-reels-downloader/download?url={encoded_url}"
            )

            r = requests.get(target_url, headers=headers, timeout=20)
            if r.status_code != 200:
                raise Exception("Failed request")

            soup = BeautifulSoup(r.text, "html.parser")
            video_tag = soup.find("a", href=lambda x: x and ".mp4" in x.lower())

            if not video_tag:
                raise Exception("Reel not found or private")

            video = html.unescape(video_tag["href"]).strip()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "video": video,
                "dev": "@UseSir"
            }).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "message": str(e)
            }).encode())
