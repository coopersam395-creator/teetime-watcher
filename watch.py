#!/usr/bin/env python3
"""Cancellation watcher: alerts (via ntfy) when a full tee time frees up.

Uses only Chronogolf's public tee-time search - no login, no personal data.
State (which slots were free last time) lives in state.json between runs.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text())
TZ = ZoneInfo(CFG["timezone"])
STATE = ROOT / "state.json"
API = "https://www.chronogolf.com/marketplace/clubs/{club}/teetimes"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def log(msg):
    print(f"{datetime.now(TZ):%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def mins(hhmm):
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def window(d):
    """One-off date windows (config "dates") override the weekly ones ("watch")."""
    return CFG.get("dates", {}).get(d.isoformat()) or CFG["watch"].get(d.strftime("%a"))


def watch_dates():
    today = datetime.now(TZ).date()
    for i in range(CFG["days_ahead"] + 1):
        d = today + timedelta(days=i)
        if window(d):
            yield d


def free_times(d):
    """Free start times in the watch window for this date, or None if not bookable yet."""
    w = window(d)
    affs = "".join(f"&affiliation_type_ids%5B%5D={CFG['affiliation_type_id']}"
                   for _ in range(w["players"]))
    url = (API.format(club=CFG["club_id"]) + f"?date={d.isoformat()}&course_id={CFG['course_id']}"
           f"{affs}&nb_holes={CFG['holes']}")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 422:          # outside booking range / not open yet
            return None
        raise
    lo, hi = mins(w["earliest"]), mins(w["latest"])
    if datetime.now(TZ).date() == d:   # today: ignore slots already past
        lo = max(lo, datetime.now(TZ).hour * 60 + datetime.now(TZ).minute + 30)
    return sorted(t["start_time"] for t in data
                  if not t.get("out_of_capacity") and not t.get("frozen")
                  and lo <= mins(t["start_time"]) <= hi)


def notify(d, times):
    topic = os.environ.get("NTFY_TOPIC")
    msg = f"{d:%a %d %b}: {', '.join(times)} just came free"
    log(f"ALERT: {msg}")
    if not topic:
        return
    link = f"https://www.chronogolf.com/club/{CFG['club_slug']}?date={d.isoformat()}"
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(), headers={
        "Title": "Tee time free!", "Tags": "golf", "Priority": "high", "Click": link})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"ntfy failed: {e}")


def check(state):
    for d in watch_dates():
        key = d.isoformat()
        try:
            now = free_times(d)
        except Exception as e:
            log(f"{key}: search failed: {e}")
            continue
        if now is None:
            continue
        before = state.get(key)
        if before is None:
            log(f"{key}: first look, {len(now)} free in window {now} (no alert)")
        else:
            new = [t for t in now if t not in before]
            if new:
                notify(d, new)
            elif now != before:
                log(f"{key}: now {now}")
        state[key] = now
    today = datetime.now(TZ).date().isoformat()
    for k in [k for k in state if k < today]:
        del state[k]


def quiet():
    h = datetime.now(TZ).hour
    q0, q1 = CFG["quiet_hours"]
    return h >= q0 or h < q1


def main():
    run_for = float(sys.argv[1]) if len(sys.argv) > 1 else 0   # minutes to keep looping
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    end = time.time() + run_for * 60
    while True:
        if quiet():
            log("Quiet hours - skipping.")
        else:
            check(state)
            STATE.write_text(json.dumps(state, indent=1))
        if time.time() + CFG["interval_seconds"] > end:
            break
        time.sleep(CFG["interval_seconds"])


if __name__ == "__main__":
    main()
