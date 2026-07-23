#!/usr/bin/env python3
"""All-in-one curation script for tech-pulse: pick + detail + build in one shot.

Replaces the multi-step flow (pick URLs -> write selection.json -> run detail.py
-> run build.py) with a single command, minimizing model token usage.

Picks file format (simple text, model writes this):
  Line 1:  theme: one-sentence theme
  Rest:    index|summary    (one per selected item, 10 lines)

  Optionally: index|summary|url1,url2  to add manual related links

Usage:
  python scripts/curate.py --date 2026-07-23 --picks picks.txt \
      --candidates candidates.json [--docs docs]

Internally:
  1. Reads candidates.json to resolve indices -> URLs
  2. Fetches details for those URLs (reuses detail.py functions)
  3. Auto-extracts related links from detail pages
  4. Writes selection.json + details.json + theme.txt
  5. Runs build.py to produce docs/YYYY-MM-DD.md + .json + index.md
  6. Prints a one-line success message
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load_picks(path):
    """Parse picks file: first 'theme:' line = theme, rest = 'index|summary[|urls]'."""
    theme = ""
    entries = []  # list of (index, summary, related_urls)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            low = line.strip().lower()
            if low.startswith("theme:") or low.startswith("theme\uff1a"):
                theme = line.split(":", 1)[-1].strip()
                continue
            parts = line.split("|")
            idx_str = parts[0].strip()
            summary = parts[1].strip() if len(parts) > 1 else ""
            related_urls = []
            if len(parts) > 2 and parts[2].strip():
                related_urls = [u.strip() for u in parts[2].split(",") if u.strip()]
            try:
                idx = int(idx_str)
                entries.append((idx, summary, related_urls))
            except ValueError:
                continue
    return theme, entries


def main():
    ap = argparse.ArgumentParser(description="All-in-one curation for tech-pulse.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--picks", required=True, help="Picks file (text: theme + index|summary lines)")
    ap.add_argument("--candidates", required=True, help="candidates.json from fetch.py")
    ap.add_argument("--docs", default=None)
    ap.add_argument("--skip-detail", action="store_true", help="Skip detail fetching (sidecar will lack body/links)")
    args = ap.parse_args()

    sk = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1) Load candidates
    with open(args.candidates, encoding="utf-8") as f:
        cand_list = json.load(f)

    # 2) Parse picks
    theme, picks = _load_picks(args.picks)
    if not picks:
        print("ERROR: no picks found", file=sys.stderr)
        return 1

    # 3) Resolve indices -> URLs
    urls = []
    for idx, summary, related_urls in picks:
        if idx < 0 or idx >= len(cand_list):
            print(f"WARNING: index {idx} out of range, skipped", file=sys.stderr)
            continue
        url = cand_list[idx].get("url", "")
        if url:
            urls.append((url, summary, related_urls))

    if not urls:
        print("ERROR: no valid picks", file=sys.stderr)
        return 1

    # 4) Fetch details (reuse detail.py)
    det_map = {}
    if not args.skip_detail:
        import logging
        logging.disable(logging.WARNING)
        import detail
        for url, _, _ in urls:
            info = detail.detail(url)
            det_map[url] = info

    det_path = os.path.join(sk, "details.json")
    with open(det_path, "w", encoding="utf-8") as f:
        json.dump(list(det_map.values()), f, ensure_ascii=False, indent=2)

    # 5) Build selection.json (auto-extract related from detail links)
    selection = []
    for url, summary, manual_related in urls:
        related = []
        if manual_related:
            for u in manual_related:
                related.append({"text": "", "url": u})
        else:
            # auto-extract from detail links
            det = det_map.get(url, {})
            for link_url in det.get("links", [])[:5]:
                related.append({"text": "", "url": link_url})
        selection.append({"url": url, "summary": summary, "related": related})

    sel_path = os.path.join(sk, "selection.json")
    with open(sel_path, "w", encoding="utf-8") as f:
        json.dump(selection, f, ensure_ascii=False, indent=2)

    # 6) Write theme.txt
    theme_path = os.path.join(sk, "theme.txt")
    with open(theme_path, "w", encoding="utf-8") as f:
        f.write(theme + "\n")

    # 7) Build
    docs = args.docs or os.path.join(sk, "docs")
    build_args = [
        "--date", args.date,
        "--theme-file", theme_path,
        "--candidates", args.candidates,
        "--details", det_path,
        "--selection", sel_path,
        "--docs", docs,
    ]
    import build
    old_argv = sys.argv
    sys.argv = ["build.py"] + build_args
    try:
        rc = build.main()
    finally:
        sys.argv = old_argv

    if rc != 0:
        print(f"ERROR: build.py returned {rc}", file=sys.stderr)
        return rc

    print(f"done: {len(selection)} items -> {args.date}.md + {args.date}.json + index.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
