"""Parity-тест rule_v4.py (Python, через fast_env) и единственной JS-копии.

Физика игры не меняется: обе стороны используют тот же Runner.update() с
виртуальными часами dt = 1000/60 и тем же LCG seed. Игры идут последовательно.

Запуск:
    python parity_v4.py --cap 200000
    python parity_v4.py --cap 2000 --seeds 786003
"""

import argparse
import json
import sys
import time

from fast_env import DT, browser_ctx, make_page
from rule_v4 import RULE_V4_JS, RuleV4

SEEDS = [786003, 790015, 793000, 793001, 793002, 793003, 793004]

JS_LIB = r"""
function parityReset(seed, dt) {
  const r = window.Runner.instance_, d = r.tRex;
  if (!window.__parityRealNow) window.__parityRealNow = performance.now.bind(performance);
  performance.now = window.__parityRealNow;
  let x = seed >>> 0;
  Math.random = function () {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    return x / 4294967296;
  };
  r.scheduleNextUpdate = function () { this.updatePending = false; };
  if (r.raqId) cancelAnimationFrame(r.raqId);
  r.raqId = 0;
  r.updatePending = false;
  window.__parityJumpObs = null;
  r.playingIntro = false; d.playingIntro = false; r.activated = true;
  r.horizon.obstacleHistory.length = 0;
  r.horizon.clouds = [];
  // restart() сам вызывает update() и берёт this.time из getTimeStamp():
  // виртуальные часы должны быть уже включены ДО restart().
  performance.now = function () { return 0; };
  r.restart();
  r.horizon.obstacleHistory.length = 0;
  r.horizon.clouds = [];
  r.playingIntro = false; d.playingIntro = false; r.activated = true;
  const vnow = dt;
  performance.now = function () { return vnow; };
  r.time = 0;
  r.update();
}
function paritySnap() {
  const r = window.Runner.instance_, d = r.tRex;
  const list = r.horizon.obstacles || [];
  const o = list[0] || null, n = list[1] || null;
  const r2 = v => Math.round(v * 100) / 100;
  return {
    dead: !!r.crashed,
    type: o ? o.typeConfig.type : null,
    width: o ? o.width : 0,
    size: o ? o.size : 0,
    oy: o ? o.yPos : 0,
    oh: o ? o.typeConfig.height : 0,
    dist: o ? o.xPos - d.xPos : 1000,
    dist2: (o && n) ? n.xPos - d.xPos : 1000,
    gap: (o && n) ? n.xPos - o.xPos - o.width : -1,
    type2: n ? n.typeConfig.type : null,
    width2: n ? n.width : 0,
    removed: o ? !!o.remove : false,
    jumped_removed: !!(window.__parityJumpObs && window.__parityJumpObs.remove),
    oid: o ? (o.__oid || (o.__oid = (window.__parityOid = (window.__parityOid || 0) + 1))) : null,
    speed: r.currentSpeed,
    y: d.yPos,
    jumping: !!d.jumping,
    ducking: !!d.ducking,
    score: r.distanceRan
  };
}
function parityApply(a) {
  const r = window.Runner.instance_, d = r.tRex;
  // Ссылка на препятствие из прыжка — состояние для Python-зеркала.
  if (a === 1 && !d.jumping && !d.ducking)
    window.__parityJumpObs = (r.horizon.obstacles || [])[0] || null;
  if (a === 3) window.__parityJumpObs = null;
  if (a === 1 && !d.jumping && !d.ducking) {
    d.startJump(r.currentSpeed);
    d.endJump();
  } else if (a === 2 && !d.jumping && !d.ducking) {
    d.setDuck(true);
  } else if (a !== 2 && d.ducking) {
    d.setDuck(false);
  }
  if (a === 3 && d.jumping) d.setSpeedDrop();
}
function parityUpdate(dt) {
  const r = window.Runner.instance_, d = r.tRex;
  r.playingIntro = false; d.playingIntro = false; r.activated = true;
  const vnow = performance.now() + dt;
  performance.now = function () { return vnow; };
  r.update();
}
function parityDeath(s) {
  if (!s.dead) return null;
  return {type: s.type, width: s.width,
          oy: Math.round(s.oy * 100) / 100,
          speed: Math.round(s.speed * 100) / 100,
          dist: Math.round(s.dist * 100) / 100,
          jumping: s.jumping};
}
function parityRestore() { performance.now = window.__parityRealNow; }
"""

JS_INIT = ("([seed, dt]) => {\n" + JS_LIB + "\n"
           "  parityReset(seed, dt);\n"
           "  return paritySnap();\n"
           "}\n")

JS_STEP = ("([action, dt]) => {\n" + JS_LIB + "\n"
           "  parityApply(action);\n"
           "  parityUpdate(dt);\n"
           "  return paritySnap();\n"
           "}\n")

JS_RESTORE = "() => { if (window.__parityRealNow) performance.now = window.__parityRealNow; return true; }"

JS_RUN = ("([seed, cap, dt]) => {\n" + RULE_V4_JS + "\n" + JS_LIB + "\n"
          "  parityReset(seed, dt);\n"
          "  const rt = {jumpObs: null};\n"
          "  let s = paritySnap();\n"
          "  let frames = 1, actions = '';\n"
          "  const marks = [];\n"
          "  while (!s.dead && frames < cap) {\n"
          "    const obs = (window.Runner.instance_.horizon.obstacles || [])[0] || null;\n"
          "    const a = ruleV4(s, rt, obs);\n"
          "    actions += String(a);\n"
          "    parityApply(a);\n"
          "    parityUpdate(dt);\n"
          "    frames++;\n"
          "    s = paritySnap();\n"
          "    if (frames % 1000 === 0) marks.push([frames, Math.round(s.score * 100) / 100]);\n"
          "  }\n"
          "  parityRestore();\n"
          "  return {frames: frames, score: s.score, actions: actions, marks: marks,\n"
          "          death: parityDeath(s), last: s};\n"
          "}\n")


def js_side(page, seed, cap):
    return page.evaluate(JS_RUN, [seed, cap, DT])


def py_side(page, seed, cap, want_all=False):
    """rule_v4.py через fast_env: один шаг за вызов, actions из Python."""
    s = page.evaluate(JS_INIT, [seed, DT])
    rule = RuleV4()
    actions = []
    marks = []
    frames = 1
    try:
        while not s["dead"] and frames < cap:
            a = rule.choose_action(s)
            actions.append(str(a))
            s = page.evaluate(JS_STEP, [a, DT])
            frames += 1
            if frames % 1000 == 0:
                marks.append([frames, round(s["score"], 2)])
    finally:
        page.evaluate(JS_RESTORE)
    result = {"frames": frames, "score": s["score"],
              "actions": "".join(actions), "marks": marks,
              "death": None if not s["dead"] else {
                  "type": s["type"], "width": s["width"],
                  "oy": round(s["oy"], 2), "speed": round(s["speed"], 2),
                  "dist": round(s["dist"], 2), "jumping": s["jumping"]},
              "last": s}
    if want_all:
        result["actions_list"] = actions
    return result


def first_diff(a, b):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else n


def report(seed, diff, j, p, frame):
    print("MISMATCH seed", seed, "diff_index", diff, "frame", frame, flush=True)
    print("  actions js ", j["actions"][max(0, frame - 6):frame + 6], flush=True)
    print("  actions py ", p["actions"][max(0, frame - 6):frame + 6], flush=True)
    print("  js  last", json.dumps(j["last"], ensure_ascii=False), flush=True)
    print("  py  last", json.dumps(p["last"], ensure_ascii=False), flush=True)
    print("  frames js/py", j["frames"], p["frames"], flush=True)
    print("  score  js/py", j["score"], p["score"], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=200000)
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    ap.add_argument("--first", action="store_true",
                    help="остановиться после первого расхождения")
    ap.add_argument("--js-only", action="store_true",
                    help="только JS-эталон: дойти до cap без смерти")
    ap.add_argument("--fast-check", action="store_true",
                    help="регрессия: 20 игр по 1 000 000 кадров, seed 790000+")
    args = ap.parse_args()
    t0 = time.perf_counter()
    with sync_playwright() as p:
        with browser_ctx(p) as bp:
            page = make_page(bp)
            ok = True
            if args.fast_check:
                deaths = 0
                for seed in range(790000, 790020):
                    j = js_side(page, seed, 1000000)
                    deaths += 1 if j["death"] else 0
                    print("FAST", seed, j["frames"], round(j["score"], 1),
                          "DEAD" if j["death"] else "CAP", "deaths", deaths,
                          "wall", round(time.perf_counter() - t0, 1), flush=True)
                print("FAST RESULT deaths", deaths, "/ 20", flush=True)
                page.close()
                return 0 if deaths == 0 else 1
            if args.js_only:
                for seed in args.seeds:
                    j = js_side(page, seed, args.cap)
                    good = j["frames"] >= args.cap and j["death"] is None
                    ok = ok and good
                    print("JS-ONLY", seed, j["frames"], round(j["score"], 1),
                          "CAP" if good else "DEAD", flush=True)
                page.close()
                return 0 if ok else 1
            for seed in args.seeds:
                j = js_side(page, seed, args.cap)
                py = py_side(page, seed, args.cap)
                d = first_diff(j["actions"], py["actions"])
                score_ok = round(j["score"], 2) == round(py["score"], 2)
                frames_ok = j["frames"] == py["frames"]
                marks_ok = j["marks"] == py["marks"]
                good = d is None and score_ok and frames_ok and marks_ok
                ok = ok and good
                print("PARITY", seed, "MATCH" if good else "MISMATCH",
                      "frames", j["frames"], py["frames"],
                      "score", round(j["score"], 2), round(py["score"], 2),
                      "actions", len(j["actions"]), len(py["actions"]),
                      "diff", d, "wall", round(time.perf_counter() - t0, 1),
                      flush=True)
                if not good:
                    report(seed, d, j, py,
                           (d if d is not None else min(j["frames"], py["frames"]) - 1))
                    if args.first:
                        break
            page.close()
    print("PARITY RESULT", "MATCH" if ok else "MISMATCH", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    sys.exit(main())
