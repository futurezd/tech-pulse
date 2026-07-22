#!/usr/bin/env python3
"""Multi-source candidate fetcher for the tech-pulse skill.

Deduplicated sources (each independent; failures skip gracefully):
  aihot  - aihot.virxact.com: Chinese AI industry aggregator (already covers
           Hacker News CN, 公众号, OpenAI, HuggingFace, xAI, Cursor, IT之家 ...).
  github - api.github.com search: fast-rising NEW repos (trending proxy).
  zhihu  - 知乎日报 official API (news-at.zhihu.com).
  juejin - 掘金 recommended feed (api.juejin.cn).
  solidot - solidot.org/index.rss: Chinese sci-tech news (RSS).

Prints a JSON array of candidates on stdout; logs to stderr.
Each candidate: {title, url, source, desc, metric, discuss, extra?}.
Config (env): SOURCES, AIHOT_LIMIT, GITHUB_LIMIT, ZHIHU_LIMIT, JUEJIN_LIMIT,
              SOLIDOT_LIMIT, GITHUB_DAYS.
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fetch")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_AIHOT_ITEM = re.compile(r"^/items/[a-z0-9]+$")


def _txt(el):
    return el.get_text(strip=True) if el else ""


def _aihot(limit):
    """Parse aihot home cards via clean DOM classes (.m-row-title/.m-row-summary/.m-row-src/.m-score/.m-row-time)."""
    r = requests.get("https://aihot.virxact.com", headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not _AIHOT_ITEM.match(href) or href in seen:
            continue
        title = _txt(a.select_one(".m-row-title")) or a.get_text(" ", strip=True)
        if not title:
            continue
        seen.add(href)
        item_id = href.split("/")[-1]
        sub = _txt(a.select_one(".m-row-src"))
        score_el = a.select_one(".m-score")
        score_s = _txt(score_el)
        score = int(score_s) if score_s.isdigit() else 0
        t = _txt(a.select_one(".m-row-time"))
        summ = _txt(a.select_one(".m-row-summary"))
        metric = f"{sub} · 热度{score}" + (f" · {t}" if t else "")
        out.append({
            "title": title,
            "url": "https://aihot.virxact.com" + href,
            "source": "aihot",
            "desc": summ,
            "metric": metric,
            "discuss": "",
            "extra": {"item_id": item_id, "subsource": sub, "score": score, "time": t},
        })
        if len(out) >= limit:
            break
    logger.info("aihot: %d", len(out))
    return out


def _github(limit, days):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    queries = [f"created:>{since} stars:>20", f"created:>{since} stars:>5"]
    seen, out = set(), []
    for q in queries:
        if len(out) >= limit:
            break
        for attempt in range(2):
            try:
                r = requests.get(
                    "https://api.github.com/search/repositories",
                    params={"q": q, "sort": "stars", "order": "desc", "per_page": min(50, max(limit, 30))},
                    headers=headers, timeout=20)
                if r.status_code == 403:
                    logger.warning("github rate-limited: %s", r.text[:80])
                    break
                if r.status_code != 200:
                    logger.warning("github search %d: %s", r.status_code, r.text[:80])
                    break
                for it in r.json().get("items", []):
                    name = it.get("full_name", "")
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    stars = it.get("stargazers_count", 0)
                    lang = it.get("language") or ""
                    created = (it.get("created_at") or "")[:10]
                    topics = it.get("topics") or []
                    metric = f"star {stars} · 建于{created}" + (f" · {lang}" if lang else "")
                    out.append({
                        "title": name,
                        "url": it.get("html_url", f"https://github.com/{name}"),
                        "source": "GitHub",
                        "desc": it.get("description") or "",
                        "metric": metric,
                        "discuss": "",
                        "extra": {"language": lang, "topics": topics[:8], "stars": stars, "created": created},
                    })
                    if len(out) >= limit:
                        break
                break
            except Exception as e:
                logger.warning("github attempt failed: %s", e)
                if attempt == 0:
                    time.sleep(2)
    logger.info("github: %d (since=%s)", len(out), since)
    return out[:limit]


def _zhihu(limit):
    r = requests.get("https://news-at.zhihu.com/api/4/news/latest", headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    out = []
    for s in r.json().get("stories", [])[:limit]:
        sid = s.get("id")
        url = s.get("url") or (f"https://daily.zhihu.com/story/{sid}" if sid else "")
        out.append({
            "title": (s.get("title") or "").strip(),
            "url": url,
            "source": "知乎日报",
            "desc": s.get("hint", ""),
            "metric": "知乎日报精选",
            "discuss": "",
            "extra": {"story_id": sid},
        })
    logger.info("zhihu: %d", len(out))
    return out


def _juejin(limit):
    r = requests.post(
        "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed",
        json={"cursor": "0", "limit": max(limit, 30), "sort_type": 200, "category_id": "0"},
        headers={"User-Agent": UA, "Content-Type": "application/json"}, timeout=15)
    r.raise_for_status()
    out = []
    for item in r.json().get("data", []):
        if item.get("item_type") != 2:
            continue
        info = item.get("item_info") or {}
        ai = info.get("article_info") or {}
        aid = ai.get("article_id")
        title = (ai.get("title") or "").strip()
        if not aid or not title:
            continue
        tags = [t.get("tag_name") for t in (info.get("tags") or []) if t.get("tag_name")][:5]
        digg = ai.get("digg_count") or 0
        view = ai.get("view_count") or 0
        out.append({
            "title": title,
            "url": f"https://juejin.cn/post/{aid}",
            "source": "掘金",
            "desc": (ai.get("brief_content") or "")[:120],
            "metric": f"赞{digg} · 阅读{view}" + (f" · {','.join(tags)}" if tags else ""),
            "discuss": "",
            "extra": {"article_id": aid, "tags": tags},
        })
        if len(out) >= limit:
            break
    logger.info("juejin: %d", len(out))
    return out


def _solidot(limit):
    """Solidot sci-tech news via RSS (solidot.org/index.rss). No score; metric = publish date."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    r = requests.get("https://www.solidot.org/index.rss", headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else []
    out = []
    for it in items[:limit]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title:
            continue
        pub_raw = (it.findtext("pubDate") or "").strip()
        if not pub_raw:
            pub_raw = (it.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
        date_s = ""
        mdate = re.search(r"\d{4}-\d{2}-\d{2}", pub_raw)
        if mdate:
            date_s = mdate.group(0)
        elif pub_raw:
            try:
                date_s = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d")
            except Exception:
                pass
        desc = re.sub(r"<[^>]+>", "", (it.findtext("description") or "")).strip()
        out.append({
            "title": title,
            "url": link,
            "source": "Solidot",
            "desc": desc[:200],
            "metric": date_s,
            "discuss": "",
            "extra": {"published": pub_raw},
        })
        if len(out) >= limit:
            break
    logger.info("solidot: %d", len(out))
    return out


_PRIORITY = {"aihot": 0, "GitHub": 1, "知乎日报": 2, "掘金": 3, "Solidot": 4}


def _score(x):
    nums = re.findall(r"\d+", x.get("metric", "") or "")
    return max((int(n) for n in nums), default=0)


def _norm_key(title):
    return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fff]", "", (title or "").lower()))


def _dedup(items):
    """Cross-source dedup by normalized title (and URL); keep higher source priority / score."""
    out, seen_url = [], set()
    for x in items:
        u = x.get("url", "")
        if u and u in seen_url:
            continue
        seen_url.add(u)
        k = _norm_key(x.get("title", ""))
        if not k:
            out.append(x)
            continue
        dup = next((o for o in out if _norm_key(o.get("title", "")) == k), None)
        if dup is None:
            out.append(x)
        else:
            xp = _PRIORITY.get(x.get("source", ""), 9)
            op = _PRIORITY.get(dup.get("source", ""), 9)
            if xp < op or (xp == op and _score(x) > _score(dup)):
                out[out.index(dup)] = x
    return out

SOURCES = {
    "aihot": lambda: _aihot(int(os.getenv("AIHOT_LIMIT", "12"))),
    "github": lambda: _github(int(os.getenv("GITHUB_LIMIT", "8")), int(os.getenv("GITHUB_DAYS", "14"))),
    "zhihu": lambda: _zhihu(int(os.getenv("ZHIHU_LIMIT", "6"))),
    "juejin": lambda: _juejin(int(os.getenv("JUEJIN_LIMIT", "6"))),
    "solidot": lambda: _solidot(int(os.getenv("SOLIDOT_LIMIT", "6"))),
}


def _heat(metric, source):
    m = metric or ""
    if "热度" in m:
        n = re.search(r"热度(\d+)", m)
        return "热" + n.group(1) if n else "热?"
    if source == "GitHub":
        n = re.search(r"star\s*(\d+)", m)
        return "★" + n.group(1) if n else "GitHub"
    if "赞" in m:
        n = re.search(r"赞(\d+)", m)
        return "赞" + n.group(1) if n else m[:8]
    if source == "Solidot":
        n = re.search(r"(\d{4}-\d{2}-\d{2})", m)
        return n.group(1) if n else source
    return (m[:10] or "-")


def _compact(i, x):
    src = x.get("source", "")
    title = (x.get("title") or "").replace("\n", " ").strip()
    desc = (x.get("desc") or "").replace("\n", " ").strip()
    return f"[{i}] {src} {_heat(x.get('metric', ''), src)} | {title} | {desc[:60]}"


def main():
    ap = argparse.ArgumentParser(description="Multi-source candidate fetcher for tech-pulse.")
    ap.add_argument("--out", help="Write JSON to this file (UTF-8) instead of stdout. Avoids shell redirection re-encoding to UTF-16 on Windows PowerShell.")
    ap.add_argument("--compact", action="store_true", help="Print a compact one-line-per-item index (idx/source/heat/title/short-desc) to stdout for low-token curation; pair with --out (urls stay in the file).")
    args = ap.parse_args()
    requested = [s for s in os.getenv("SOURCES", "aihot,github,zhihu,juejin,solidot").split(",") if s.strip()]
    items = []
    for s in requested:
        fn = SOURCES.get(s)
        if not fn:
            logger.warning("unknown source: %s", s)
            continue
        try:
            items.extend(fn())
        except Exception as e:
            logger.warning("%s skipped: %s", s, e)
    before = len(items)
    items = _dedup(items)
    if before != len(items):
        logger.info("dedup: %d -> %d", before, len(items))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
        logger.info("wrote %d candidates -> %s", len(items), args.out)
    if args.compact:
        for i, x in enumerate(items):
            print(_compact(i, x))
    elif not args.out:
        sys.stdout.write(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
