#!/usr/bin/env python3
"""Source-aware detail fetcher for the tech-pulse skill.

Usage: python scripts/detail.py <url1> <url2> ...
Prints JSON: [{url, title, desc, firstp, links, source}]
- aihot (aihot.virxact.com/items/<id>): 精选理由 + AI摘要 + 原文链接 + 正文.
- GitHub (github.com/<o>/<r>): api.github.com repo metadata + README (firstp + related links).
- 知乎日报 (daily.zhihu.com/story/<id>): news-at.zhihu.com content API (body + links).
- 掘金 (juejin.cn/post/<id>): content_api detail; 失败则回退网页 meta description.
- Generic: requests.get + BeautifulSoup (meta description / first paragraph / notable links).
links = notable related pages (github, huggingface, arxiv, docs, x.com, ...) for deep-dive.
"""
import argparse
import base64
import json
import re
import sys
from html import unescape

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
LINK_RE = re.compile(r"https?://[^\s)\"`'<>]+", re.IGNORECASE)
NOTABLE_RE = re.compile(r"(github\.com|huggingface\.co|arxiv\.org|readthedocs\.io|docs\.|\.dev|\.io|npmjs\.com|pypi\.org|crates\.io|x\.com|twitter\.com|openai\.com|anthropic\.com)", re.IGNORECASE)


def _clean(text, n=600):
    text = unescape(re.sub(r"\s+", " ", text or "")).strip()
    return text[:n]


def _notable_links(text, cap=8):
    found, seen = [], set()
    for u in LINK_RE.findall(text or ""):
        u = u.rstrip(".,);]'")
        if u in seen or "api.github.com" in u:
            continue
        if NOTABLE_RE.search(u):
            seen.add(u)
            found.append(u)
        if len(found) >= cap:
            break
    return found


def _aihot_detail(url):
    info = {"source": "aihot"}
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            return info
        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string if soup.title else "") or ""
        info["title"] = title.split(" · ")[0].strip()
        orig = ""
        for a in soup.find_all("a", href=True):
            h, t = a["href"], a.get_text(strip=True)
            if t == "原文" and h.startswith("http") and "virxact" not in h:
                orig = h
                break
        full = soup.get_text(" ", strip=True)
        reason, summary = "", ""
        m = re.search(r"精选理由\s*(.*?)(?:AI 摘要|正文)", full, re.S)
        if m:
            reason = _clean(m.group(1), 400)
        m2 = re.search(r"AI 摘要\s*(.*?)(?:正文|原文|跳到正文)", full, re.S)
        if m2:
            summary = _clean(m2.group(1), 700)
        info["desc"] = reason or summary
        info["firstp"] = summary or reason
        links = []
        if orig:
            links.append(orig)
        links += _notable_links(full)
        info["links"] = links[:8]
    except Exception as e:
        info["_err"] = str(e)[:120]
    return info


def _github_detail(url):
    m = re.match(r"https?://github\.com/([^/]+)/([^/?#]+)", url)
    if not m:
        return {"source": "GitHub"}
    owner, repo = m.group(1), m.group(2)
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    info = {"source": "GitHub"}
    try:
        r = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=15)
        if r.status_code == 200:
            d = r.json()
            info["title"] = d.get("full_name") or f"{owner}/{repo}"
            info["desc"] = d.get("description") or ""
            info["stars"] = d.get("stargazers_count", 0)
            hp = d.get("homepage") or ""
            info["topics"] = d.get("topics") or []
            if hp:
                info["homepage"] = hp
    except Exception:
        pass
    firstp, links = "", []
    try:
        r = requests.get(f"https://api.github.com/repos/{owner}/{repo}/readme", headers=headers, timeout=15)
        if r.status_code == 200:
            content = r.json().get("content", "")
            raw = base64.b64decode(content).decode("utf-8", "ignore")
            no_code = re.sub(r"```.*?```", " ", raw, flags=re.S)
            plain = BeautifulSoup(no_code, "html.parser").get_text(" ")
            plain = re.sub(r"[#>*`|]", " ", plain)
            firstp = _clean(plain, 800)
            links = _notable_links(raw)
    except Exception:
        pass
    if info.get("homepage"):
        links = [info["homepage"]] + [l for l in links if l != info["homepage"]]
    info["firstp"] = firstp
    info["links"] = links
    return info


def _zhihu_detail(url):
    m = re.search(r"story/(\d+)", url)
    sid = m.group(1) if m else url.rstrip("/").split("/")[-1]
    info = {"source": "知乎日报"}
    try:
        r = requests.get(f"https://news-at.zhihu.com/api/4/news/{sid}", headers={"User-Agent": UA}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            info["title"] = d.get("title", "")
            info["desc"] = d.get("image_source", "") or d.get("title", "")
            body = d.get("body") or ""
            soup = BeautifulSoup(body, "html.parser")
            firstp = ""
            for p in soup.find_all("p"):
                t = p.get_text(strip=True)
                if len(t) > 20:
                    firstp = _clean(t, 600)
                    break
            info["firstp"] = firstp or _clean(soup.get_text(" "), 600)
            info["links"] = _notable_links(body)
    except Exception:
        pass
    return info


def _juejin_detail(url):
    m = re.search(r"/post/(\d+)", url)
    aid = m.group(1) if m else url.rstrip("/").split("/")[-1]
    info = {"source": "掘金"}
    try:
        r = requests.post("https://api.juejin.cn/content_api/v1/article/detail",
                          json={"article_id": aid},
                          headers={"User-Agent": UA, "Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            j = r.json()
            if j.get("err_no") == 0:
                d = (j.get("data") or {}).get("article_info") or {}
                info["title"] = d.get("title", "")
                info["desc"] = (d.get("brief_content") or "")[:200]
                content = d.get("mark_content") or d.get("content") or ""
                plain = BeautifulSoup(re.sub(r"[#>*`|]", " ", content), "html.parser").get_text(" ")
                info["firstp"] = _clean(plain, 600)
                info["links"] = _notable_links(content)
    except Exception:
        pass
    if not info.get("desc") and not info.get("firstp"):
        try:
            r = requests.get(f"https://juejin.cn/post/{aid}", headers={"User-Agent": UA}, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"):
                info["desc"] = _clean(md["content"], 200)
                info["firstp"] = _clean(md["content"], 400)
        except Exception:
            pass
    return info


def _generic_detail(url):
    info = {"source": "Web"}
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            return info
        soup = BeautifulSoup(r.text, "html.parser")
        info["title"] = (soup.title.get_text(strip=True) if soup.title else "") or url
        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            info["desc"] = _clean(desc["content"], 300)
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content") and not info.get("desc"):
            info["desc"] = _clean(og["content"], 300)
        firstp = ""
        for p in soup.find_all(["p", "article"]):
            t = p.get_text(" ", strip=True)
            if len(t) > 40:
                firstp = _clean(t, 600)
                break
        info["firstp"] = firstp
        info["links"] = _notable_links(r.text)
    except Exception as e:
        info["_err"] = str(e)[:120]
    return info


def detail(url):
    u = url.lower()
    if "aihot.virxact.com" in u:
        info = _aihot_detail(url)
    elif "github.com" in u:
        info = _github_detail(url)
    elif "daily.zhihu.com" in u or "zhihu.com" in u:
        info = _zhihu_detail(url)
    elif "juejin.cn" in u:
        info = _juejin_detail(url)
    else:
        info = _generic_detail(url)
    info["url"] = url
    info.setdefault("title", "")
    info.setdefault("desc", "")
    info.setdefault("firstp", "")
    info.setdefault("links", [])
    return info


def main():
    ap = argparse.ArgumentParser(description="Source-aware detail fetcher for tech-pulse.")
    ap.add_argument("urls", nargs="*", help="One or more URLs to fetch details for.")
    ap.add_argument("--out", help="Write JSON to this file (UTF-8) instead of stdout. Avoids shell redirection re-encoding to UTF-16 on Windows PowerShell.")
    args = ap.parse_args()
    urls = [u for u in args.urls if u.startswith("http")]
    out = [detail(u) for u in urls]
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
