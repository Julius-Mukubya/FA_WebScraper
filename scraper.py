"""A general-purpose scraper. You supply the URL and the CSS selectors; it works on any static site.

Usage:
  python scraper.py URL --field NAME=SELECTOR [--field ...] [options]

Field syntax:
  title=h3 a            -> text of the matched element
  link=h3 a@href        -> the 'href' attribute of the matched element
  (the part after the last '@' is the attribute name)

Options:
  --item SELECTOR   Repeating container (e.g. "article.product"). One row per match,
                    and fields are looked up inside each container.
                    Without it, each field is extracted page-wide and rows are zipped.
  --next SELECTOR   Link to the next page (e.g. "li.next a"). Enables crawling.
  --pages N         Max pages to fetch (default 1)
  --delay SECONDS   Pause between requests (default 1)
  --out FILE        Output file, .csv or .json (default output.csv)
  --insecure        Skip SSL certificate checks (only if you get certificate errors)

Example:
  python scraper.py https://books.toscrape.com/ --item "article.product_pod" ^
      --field "title=h3 a@title" --field "price=p.price_color" ^
      --next "li.next a" --pages 3 --out books.csv
"""
import argparse
import csv
import json
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:  # use the Windows/OS certificate store if available (helps behind corporate proxies)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


def parse_field(spec):
    """'name=selector@attr' -> (name, selector, attr or None)"""
    name, _, rest = spec.partition("=")
    if not name or not rest:
        raise SystemExit(f"Bad --field '{spec}'. Use NAME=SELECTOR or NAME=SELECTOR@ATTR")
    if "@" in rest:
        selector, _, attr = rest.rpartition("@")
    else:
        selector, attr = rest, ""
    return name.strip(), selector.strip(), attr.strip() or None


def value_of(element, attr):
    if element is None:
        return None
    return element.get(attr) if attr else element.get_text(" ", strip=True)


def extract(soup, item_selector, fields, base_url):
    rows = []
    if item_selector:
        for item in soup.select(item_selector):
            row = {name: value_of(item.select_one(sel), attr) for name, sel, attr in fields}
            rows.append(row)
    else:
        columns = {name: [value_of(e, attr) for e in soup.select(sel)] for name, sel, attr in fields}
        for values in zip(*columns.values()):
            rows.append(dict(zip(columns.keys(), values)))
    # make relative URLs absolute
    for row in rows:
        for (name, _, attr) in fields:
            if attr in ("href", "src") and row[name]:
                row[name] = urljoin(base_url, row[name])
    return rows


def save(rows, path):
    if not rows:
        print("No rows extracted - check your selectors.")
        return
    if path.endswith(".json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {path}")


def main():
    p = argparse.ArgumentParser(description="General-purpose CSS-selector web scraper")
    p.add_argument("url")
    p.add_argument("--field", action="append", required=True, help="NAME=SELECTOR[@ATTR]")
    p.add_argument("--item")
    p.add_argument("--next")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--delay", type=float, default=1)
    p.add_argument("--out", default="output.csv")
    p.add_argument("--insecure", action="store_true")
    args = p.parse_args()

    fields = [parse_field(f) for f in args.field]
    headers = {"User-Agent": "Mozilla/5.0 (learning-scraper)"}
    url, rows, seen = args.url, [], set()

    for _ in range(args.pages):
        if not url or url in seen:
            break
        seen.add(url)
        print(f"Fetching {url}")
        resp = requests.get(url, headers=headers, timeout=15, verify=not args.insecure)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")  # bytes: let the parser detect encoding

        page_rows = extract(soup, args.item, fields, url)
        print(f"  found {len(page_rows)} rows")
        rows.extend(page_rows)

        nxt = soup.select_one(args.next) if args.next else None
        url = urljoin(url, nxt["href"]) if nxt and nxt.get("href") else None
        if url:
            time.sleep(args.delay)

    save(rows, args.out)


if __name__ == "__main__":
    main()
