#!/usr/bin/env python3
"""Fetch METI press-release headlines from official web pages (not the stale Atom feed)."""
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import json
import re

BASE = "https://www.meti.go.jp"
INDEX = BASE + "/press/index.html"
JST = timezone(timedelta(hours=9))
OUTPUT = Path("site")

class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.text = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.text = []
    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            title = " ".join(" ".join(self.text).split())
            if title:
                self.links.append((self.href, title))
            self.href = None

def get_links(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; METI-news-widget/1.0)", "Accept": "text/html"})
    with urlopen(req, timeout=25) as response:
        content = response.read(2_000_000)
        encoding = response.headers.get_content_charset() or "utf-8"
    parser = AnchorParser()
    parser.feed(content.decode(encoding, errors="replace"))
    return [(urljoin(url, href), title) for href, title in parser.links]

def collect():
    year = datetime.now(JST).year
    # The index and annual archives are official METI pages.
    pages = [INDEX, f"{BASE}/press/{year}/index.html",
             f"{BASE}/press/{year-1}/index.html"]
    discovered = {}
    for page in pages:
        try:
            links = get_links(page)
            print("Fetched:", page, "links:", len(links))
        except Exception as exc:
            print("Unable to fetch", page, str(exc))
            continue
        for href, title in links:
            if not href.startswith(BASE + "/press/"):
                continue
            path = urlparse(href).path
            # Release URLs commonly contain YYYYMMDD as a path segment.
            m = re.search(r"/press/(20\\d{2})/\\d{2}/(20\\d{6})[^/]*/[^/]+\\.html$", path)
            if m and len(title) >= 8:
                day = m.group(2)
                try:
                    datetime.strptime(day, "%Y%m%d")
                except ValueError:
                    continue
                discovered[href] = {"date": day, "title": title, "url": href}
            # Follow archive/list pages, not arbitrary release pages.
            elif (path.endswith("/index.html") and
                  re.search(rf"/press/{year}(?:/|$)", path) and
                  href not in pages and len(pages) < 18):
                pages.append(href)
    items = sorted(discovered.values(), key=lambda x: (x["date"], x["url"]), reverse=True)
    if not items:
        raise RuntimeError("No press-release links found. Check official page structure and workflow logs.")
    latest = datetime.strptime(items[0]["date"], "%Y%m%d").replace(tzinfo=JST)
    if datetime.now(JST) - latest > timedelta(days=35):
        raise RuntimeError("Latest found release is older than 35 days; refusing to publish stale headlines.")
    return items[:12]

def html(items):
    updated = datetime.now(JST).strftime("%Y/%m/%d %H:%M JST")
    rows = "\\n".join(
        '<a class="entry" href="{url}" target="_blank" rel="noopener noreferrer">'
        '<time>{date}</time><span>{title}</span><b>↗</b></a>'.format(
            url=escape(item["url"], quote=True),
            date=f'{item["date"][:4]}.{item["date"][4:6]}.{item["date"][6:]}',
            title=escape(item["title"]))
        for item in items
    )
    return f"""<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10800">
<title>METI News Releases</title>
<style>
:root{{color-scheme:light dark;font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;padding:0 4px;background:transparent;color:light-dark(#24262b,#e6e6e6);font-size:13px}}
header{{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:14px 0;border-bottom:1px solid light-dark(#e7e7e7,#404040)}}
strong{{font-size:12px;letter-spacing:.09em}}small{{font-size:10px;color:light-dark(#767676,#aaa)}}
.entry{{display:grid;grid-template-columns:82px minmax(0,1fr) 14px;gap:9px;padding:12px 0;border-bottom:1px solid light-dark(#ececec,#383838);text-decoration:none;color:inherit;line-height:1.55}}
.entry:hover{{opacity:.7}}time{{font-size:11px;color:light-dark(#747474,#aaa);white-space:nowrap;padding-top:2px}}b{{font-weight:400;color:#888}}
footer{{padding:12px 0;color:light-dark(#777,#aaa);font-size:10px}}footer a{{color:inherit}}
</style></head><body>
<header><strong>METI / NEWS RELEASES</strong><small>取得 {updated}</small></header>
<main>{rows}</main>
<footer>Source: <a href="{INDEX}" target="_blank" rel="noopener noreferrer">経済産業省 ニュースリリース</a></footer>
</body></html>"""

def main():
    items = collect()
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "index.html").write_text(html(items), encoding="utf-8")
    (OUTPUT / "releases.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(items)} headlines; latest {items[0]['date']}")

if __name__ == "__main__":
    main()
