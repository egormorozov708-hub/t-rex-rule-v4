"""Ночной sequential-прогон JS-эталона rule_v4 (fast, старт 6).

Два режима:
  python night_run.py            — супервизор: игры по очереди, сторож, отчёты
  python night_run.py --game N   — одна игра (до смерти или cap 10 000 000)

Физику, RULE_V4_JS, JS-логику, rule_v3.py и rule_v4.py не трогает:
использует parity_v4.js_side() как есть.
"""

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
CSV = RESULTS / "night_v4.csv"
DEATHS = RESULTS / "night_deaths.jsonl"
STATE = RESULTS / "night_state.json"
LOG = RESULTS / "night_log.txt"
SUMMARY = ROOT / "summary.md"
CAP = 10_000_000
SEED0 = 800000
STALE = 300.0
MAX_CONSECUTIVE_RESTARTS = 3


def now():
    return datetime.now()


def log(msg):
    line = now().strftime("%H:%M:%S") + " " + msg
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def deadline_at(hhmm="06:00"):
    h, m = (int(x) for x in hhmm.split(":"))
    d = datetime.combine(date.today(), datetime.min.time()).replace(hour=h, minute=m)
    if now() >= d:
        d += timedelta(days=1)
    return d


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"next_seed": SEED0, "games": 0, "deaths": 0, "total_frames": 0,
            "death_frames": [], "reasons": {}, "restarts": 0,
            "consecutive_restarts": 0}


def save_state(st):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE)


def game_mode(seed):
    sys.path.insert(0, str(ROOT))
    from playwright.sync_api import sync_playwright

    from fast_env import browser_ctx, make_page
    from parity_v4 import js_side

    with sync_playwright() as p:
        with browser_ctx(p) as bp:
            page = make_page(bp)
            try:
                j = js_side(page, seed, CAP)
            finally:
                page.close()

    last = j["last"]
    outcome = "DEATH" if j["death"] else "CAP"
    rec = {"seed": seed, "frames": j["frames"], "score": j["score"],
           "outcome": outcome}
    if j["death"]:
        d = j["death"]
        rec["death"] = {
            "seed": seed, "frame": j["frames"], "type": d["type"],
            "width": d["width"], "oy": d["oy"], "speed": d["speed"],
            "dist": d["dist"], "jumping": d["jumping"],
            "obstacle2": {"type": last.get("type2"), "width": last.get("width2"),
                          "dist": last.get("dist2"), "gap": last.get("gap")},
            "actions60": j["actions"][-60:],
        }
    out = RESULTS / ("night_game_%d.json" % seed)
    out.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    print("GAME %d %d %s" % (seed, j["frames"], outcome), flush=True)


def summary(st, final=False, restarts_note=""):
    dfs = st["death_frames"]
    lines = ["# Ночной прогон rule_v4 (JS-эталон)", ""]
    lines.append("- Обновлено: %s" % now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("- Игр: %d" % st["games"])
    lines.append("- Смертей: %d" % st["deaths"])
    lines.append("- Сумма кадров: %d" % st["total_frames"])
    if dfs:
        lines.append("- Кадров до смерти: min %d, median %.1f" %
                     (min(dfs), statistics.median(dfs)))
    lines.append("- Причины: " + (", ".join("%s %d" % (k, v)
                 for k, v in sorted(st["reasons"].items())) or "нет"))
    if final:
        lines.append("")
        lines.append("## Итог")
        lines.append("- Кадров на одну смерть: %s" %
                     ("%.1f" % (st["total_frames"] / st["deaths"])
                      if st["deaths"] else "нет смертей"))
        if dfs:
            lines.append("- Кадры до смерти: mean %.1f, median %.1f, min %d, max %d" %
                         (statistics.mean(dfs), statistics.median(dfs),
                          min(dfs), max(dfs)))
        total = sum(st["reasons"].values()) or 1
        lines.append("- Причины с долями: " + (", ".join(
            "%s %d (%.1f%%)" % (k, v, 100.0 * v / total)
            for k, v in sorted(st["reasons"].items())) or "нет"))
        lines.append("- Перезапусков сторожа: %d" % st["restarts"])
        if restarts_note:
            lines.append("- " + restarts_note)
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=int, default=None, help="пуск одной игры")
    ap.add_argument("--deadline", default="06:00")
    a = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    if a.game is not None:
        game_mode(a.game)
        return 0

    end = deadline_at(a.deadline)
    st = load_state()
    with CSV.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["seed", "frames", "distanceRan", "outcome"])
    log("START seeds from %d, deadline %s, cap %d" %
        (st["next_seed"], end.strftime("%H:%M"), CAP))
    t0 = time.time()
    last_status = 0.0
    last_summary = 0.0
    note = ""

    while now() < end:
        seed = st["next_seed"]
        st["next_seed"] = seed + 1
        save_state(st)
        child = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "night_run.py"), "--game", str(seed)],
            cwd=str(ROOT), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        wd = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "csv_watchdog.py"),
             "--csv", str(CSV), "--pid", str(child.pid),
             "--seconds", str(int(STALE)), "--interval", "10"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        killed = False
        while child.poll() is None:
            if wd.poll() is not None and wd.returncode == 2:
                killed = True
                break
            tm = time.time()
            if tm - last_status >= 60:
                last_status = tm
                elapsed = max(1.0, tm - t0)
                log("STATUS %s games %d deaths %d frames %d fps %.1f ETA %s" %
                    (now().strftime("%H:%M"), st["games"], st["deaths"],
                     st["total_frames"], st["total_frames"] / elapsed,
                     str(end - now()).split(".")[0]))
            if tm - last_summary >= 600:
                last_summary = tm
                summary(st)
            time.sleep(2)

        if wd.poll() is None:
            wd.terminate()
            try:
                wd.wait(timeout=5)
            except subprocess.TimeoutExpired:
                wd.kill()
        if killed:
            child.kill()
            child.wait()
            st["restarts"] += 1
            st["consecutive_restarts"] += 1
            note = " watchdog: CSV stale %ds, seed %d убит, continue %d" % (
                int(STALE), seed, seed + 1)
            log("WATCHDOG RESTART %d for seed %d" % (st["restarts"], seed))
            save_state(st)
            summary(st)
            if st["consecutive_restarts"] >= MAX_CONSECUTIVE_RESTARTS:
                note += "; 3 подряд — остановка"
                log("STOP: 3 consecutive watchdog restarts")
                break
            continue

        child.wait()
        rec_path = RESULTS / ("night_game_%d.json" % seed)
        if not rec_path.exists():
            note = " missing result for seed %d" % seed
            log("ERROR no result seed %d" % seed)
            save_state(st)
            continue
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        with CSV.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([rec["seed"], rec["frames"],
                                    round(rec["score"], 1), rec["outcome"]])
        if rec.get("death"):
            with DEATHS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec["death"], ensure_ascii=False) + "\n")
            st["deaths"] += 1
            st["death_frames"].append(rec["frames"])
            st["reasons"][rec["death"]["type"]] = \
                st["reasons"].get(rec["death"]["type"], 0) + 1
        st["games"] += 1
        st["total_frames"] += rec["frames"]
        st["consecutive_restarts"] = 0
        save_state(st)
        log("DONE seed %d %d %s | games %d deaths %d" %
            (seed, rec["frames"], rec["outcome"], st["games"], st["deaths"]))

    summary(st, final=True, restarts_note=note)
    log("FINISH games %d deaths %d frames %d restarts %d" %
        (st["games"], st["deaths"], st["total_frames"], st["restarts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
