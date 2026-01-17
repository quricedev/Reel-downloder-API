import os
import json
import time
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")
OPENROUTER_URL = os.environ.get("OPENROUTER_URL")
MODEL_NAME = os.environ.get("OPENROUTER_MODEL")

KEYS_FILE = os.path.join(os.path.dirname(__file__), "..", "WormGptkeys.txt")
IP_USAGE_FILE = os.path.join(os.path.dirname(__file__), "..", "ip_usage.json")

MAX_REQUESTS = 20
WINDOW_SECONDS = 60  


def load_ip_usage():
    try:
        with open(IP_USAGE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_ip_usage(data):
    with open(IP_USAGE_FILE, "w") as f:
        json.dump(data, f)


def validate_key(api_key, ip):
    try:
        with open(KEYS_FILE, "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) < 2:
                    continue

                key = parts[0]
                expiry = parts[1]
                limited = len(parts) == 3 and parts[2] == "limit"

                if key != api_key:
                    continue

                if datetime.utcnow() > datetime.strptime(expiry, "%d/%m/%Y"):
                    return False, "API key is invalid or expired"

                if limited:
                    usage = load_ip_usage()
                    now = int(time.time())

                    usage.setdefault(key, {})
                    usage[key].setdefault(ip, [])

                    usage[key][ip] = [
                        t for t in usage[key][ip]
                        if now - t < WINDOW_SECONDS
                    ]

                    if len(usage[key][ip]) >= MAX_REQUESTS:
                        return False, "IP request limit reached"

                    usage[key][ip].append(now)
                    save_ip_usage(usage)

                return True, None
    except:
        pass

    return False, "API key is invalid or expired"


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)

        api_key = query.get("key", [None])[0]
        text = query.get("text", [None])[0]

        ip = (
            self.headers.get("x-forwarded-for")
            or self.client_address[0]
        )

        if not api_key:
            return self.error(400, "API key is required")

        valid, msg = validate_key(api_key, ip)
        if not valid:
            return self.error(401, msg)

        if not text:
            return self.error(400, "Missing 'text' parameter")

        try:
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "user", "content": text}
                ]
            }

            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://usesir.vercel.app",
                "X-Title": "UseSir Ask API"
            }

            r = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=30
            )

            r.raise_for_status()
            data = r.json()

            answer = data["choices"][0]["message"]["content"]

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "query": text,
                "response": answer,
                "owner": "@UseSir / @OverShade"
            }, indent=2).encode())

        except:
            self.error(500, "Failed to generate response")

    def error(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "error",
            "error": {
                "message": message
            },
            "owner": "@UseSir / @OverShade"
        }, indent=2).encode())
