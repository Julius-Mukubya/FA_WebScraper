"""Web UI for the scraper.   Run:  python app.py   then open http://localhost:8000"""
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper import extract, parse_field  # reuse the core logic

PORT = 8000
HEADERS = {"User-Agent": "Mozilla/5.0 (learning-scraper)"}
INDEX = Path(__file__).with_name("index.html")

# One-click modes: (item selector, [field specs])
PRESETS = {
    "links": (None, ["text=a[href]", "url=a[href]@href"]),
    "images": (None, ["image=img[src]@src", "alt=img[src]@alt"]),
    "headings": (None, ["heading=h1, h2, h3"]),
    "paragraphs": (None, ["text=p"]),
}


def extract_tables(soup):
    rows = []
    for t_index, table in enumerate(soup.select("table"), 1):
        for tr in table.select("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.select("th, td")]
            if cells:
                row = {"table": t_index}
                row.update({f"col{i}": v for i, v in enumerate(cells, 1)})
                rows.append(row)
    return rows


def scrape(req):
    url = req["url"].strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    mode = req.get("mode", "links")
    pages = max(1, min(int(req.get("pages") or 1), 50))
    next_sel = req.get("next") or None

    if mode == "custom":
        item = req.get("item") or None
        fields = [parse_field(f) for f in req.get("fields", []) if f.strip()]
        if not fields:
            raise ValueError("Add at least one field (e.g. title=h2 a)")
    elif mode in PRESETS:
        item, specs = PRESETS[mode]
        fields = [parse_field(s) for s in specs]
    else:
        item, fields = None, []

    rows, seen = [], set()
    for _ in range(pages):
        if not url or url in seen:
            break
        seen.add(url)
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=not req.get("insecure"))
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        rows.extend(extract_tables(soup) if mode == "tables" else extract(soup, item, fields, url))
        nxt = soup.select_one(next_sel) if next_sel else None
        url = urljoin(url, nxt["href"]) if nxt and nxt.get("href") else None
        if url:
            time.sleep(1)
    return rows


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_text(encoding="utf-8"), "text/html")
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path != "/api/scrape":
            return self._send(404, "{}")
        try:
            length = int(self.headers.get("Content-Length", 0))
            rows = scrape(json.loads(self.rfile.read(length)))
            self._send(200, json.dumps({"rows": rows}))
        except Exception as e:  # surface any problem to the UI
            self._send(400, json.dumps({"error": f"{type(e).__name__}: {e}"}))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Open http://localhost:{PORT}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
