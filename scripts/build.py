#!/usr/bin/env python3
"""Archive builder for the tech-pulse skill.

Formalizes the archive step: merge Codex's curation (selection.json) with fetched
candidates + details into docs/YYYY-MM-DD.md (concise) + docs/YYYY-MM-DD.json (sidecar)
and update docs/index.md.

selection.json (Codex-authored): [{"url","summary","related":[{"text","url"}]}]
candidates.json: fetch.py output (for title/source/metric/discuss)
details.json:    detail.py output (for body desc/firstp); multiple files allowed

Usage:
  python scripts/build.py --date 2026-07-21 --theme "..." \
      --candidates candidates.json --details details.json [detail_aos.json ...] \
      --selection selection.json [--docs docs]
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] in (bytes([0xff, 0xfe]), bytes([0xfe, 0xff])):
        text = raw.decode("utf-16")
    elif raw[:3] == bytes([0xef, 0xbb, 0xbf]):
        text = raw[3:].decode("utf-8")
    else:
        text = raw.decode("utf-8")
    return json.loads(text)


def _by_url(items):
    d = {}
    for x in items:
        d[x.get("url", "")] = x
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--theme", default="")
    ap.add_argument("--theme-file", default=None, help="Read today's theme from this UTF-8 file (overrides --theme; avoids shell quoting issues with quotes/spaces in the theme).")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--details", nargs="+", required=True)
    ap.add_argument("--selection", required=True)
    ap.add_argument("--docs", default=None)
    args = ap.parse_args()

    if args.theme_file:
        with open(args.theme_file, "rb") as f:
            raw = f.read()
        if raw[:2] in (bytes([0xff, 0xfe]), bytes([0xfe, 0xff])):
            args.theme = raw.decode("utf-16")
        elif raw[:3] == bytes([0xef, 0xbb, 0xbf]):
            args.theme = raw[3:].decode("utf-8")
        else:
            args.theme = raw.decode("utf-8")
        args.theme = args.theme.strip()

    sk = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs = args.docs or os.path.join(sk, "docs")
    os.makedirs(docs, exist_ok=True)

    cand = _by_url(_load(args.candidates))
    det = {}
    for f in args.details:
        det.update(_by_url(_load(f)))
    sel = _load(args.selection)

    side = []
    sources_seen = []
    for s in sel:
        u = s.get("url", "")
        c = cand.get(u, {})
        d = det.get(u, {})
        title = (d.get("title") or "").strip() or c.get("title") or u
        src = c.get("source", "") or d.get("source", "")
        if src and src not in sources_seen:
            sources_seen.append(src)
        metric = c.get("metric", "")
        if metric.strip().startswith("·"):
            metric = "aihot 精选"
        side.append({
            "title": title,
            "url": u,
            "discuss": c.get("discuss", ""),
            "metric": metric,
            "source": src,
            "summary": s.get("summary", ""),
            "related": s.get("related", []),
            "body": {"desc": d.get("desc", ""), "firstp": d.get("firstp", "")},
        })

    # ---- md (concise) ----
    lines = [f"# 今日值得关注的 10 件事 · {args.date}", "", ""]
    if args.theme:
        lines += [f"> 今日主题：{args.theme}", ""]
    for i, it in enumerate(side, 1):
        lines.append(f"## {i}. {it['title']}")
        lines.append(f"- 主链接：{it['url']}")
        if it.get("discuss"):
            lines.append(f"- 讨论：{it['discuss']}")
        lines.append(f"- 来源：{it['source']} · {it['metric']}")
        lines.append(f"- 摘要：{it['summary']}")
        lines.append("")
    footer = " / ".join(sources_seen) or "aihot / GitHub / 知乎日报 / 掘金"
    lines += ["---", f"*由 tech-pulse skill 生成 · {footer} · {args.date}*"]
    md = "\n".join(lines) + "\n"
    with open(os.path.join(docs, f"{args.date}.md"), "w", encoding="utf-8") as f:
        f.write(md)

    # ---- json sidecar ----
    with open(os.path.join(docs, f"{args.date}.json"), "w", encoding="utf-8") as f:
        json.dump(side, f, ensure_ascii=False, indent=2)

    # ---- index ----
    idx = os.path.join(docs, "index.md")
    entry = f"- [{args.date}]({args.date}.md)"
    head = "# 历史归档\n\n"
    cur = open(idx, encoding="utf-8").read() if os.path.exists(idx) else head
    if not cur.startswith("# "):
        cur = head + cur
    if entry not in cur:
        cur = cur.replace(head, head + entry + "\n", 1)
    with open(idx, "w", encoding="utf-8") as f:
        f.write(cur)

    print(f"built {args.date}: {len(side)} items | {args.date}.md {len(md)} chars | {args.date}.json | index.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
