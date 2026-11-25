"""Видимая игра Chrome Dino: реальный rAF, без наложений по умолчанию.

Примеры:
  python watch.py --agent rule_v3 --games 1 --seed0 92000 --cap 1000
  python watch.py --agent table:q_table_v4_best.npy --seed0 92000 --cap 1000
  python watch.py --agent rule_v3 --hud --screenshot after.png
  python watch.py --agent rule_v3 --raf-hz 120 --cap 1000
  python watch.py --agent rule_v3 --compare --seed0 92000
"""

import argparse
import csv
import json
import os
import time
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

from fast_env import DT, GAME_URL

CHROME_ARGS = ["--disable-gpu", "--disable-extensions", "--mute-audio"]

CSS_FIX = """
html, body {
  margin: 0 !important; padding: 0 !important;
  width: 100% !important; height: 100% !important;
  overflow: hidden !important;
}
.interstitial-wrapper {
  width: 100% !important; max-width: 600px !important;
  margin: 0 auto !important;
  transform: none !important; zoom: 1 !important;
}
.runner-container {
  width: 600px !important; max-width: none !important;
  margin: 0 auto !important; overflow: visible !important;
  transform: none !important; zoom: 1 !important;
}
.runner-container canvas, canvas {
  width: 600px !important; max-width: none !important;
  height: auto !important; display: block !important;
  margin: 0 auto !important;
  transform: none !important; zoom: 1 !important;
}
"""

def apply_css(page, args):
    if getattr(args, "no_css", False):
        return
    page.add_style_tag(content=CSS_FIX)


MUTE = """
() => {
  const r = window.Runner.instance_;
  r.playSound = function () {};
  const ctx = r.audioContext || null;
  if (ctx && ctx.suspend) ctx.suspend();
  return {ctx: !!ctx, state: ctx ? ctx.state : null};
}
"""

DIAGNOSE = """
() => {
  const c = document.querySelector('canvas');
  const cont = document.querySelector('.runner-container');
  const wrap = document.querySelector('.interstitial-wrapper');
  const rect = e => {
    if (!e) return null;
    const b = e.getBoundingClientRect();
    return {x: Math.round(b.x), y: Math.round(b.y),
            w: Math.round(b.width), h: Math.round(b.height)};
  };
  const chain = e => {
    const out = [];
    for (let p = e; p && p !== document.documentElement; p = p.parentElement) {
      const s = getComputedStyle(p);
      out.push({tag: p.tagName, cls: String(p.className || '').slice(0, 40),
                overflow: s.overflow, transform: s.transform, zoom: s.zoom,
                w: s.width, h: s.height});
    }
    return out;
  };
  return {
    innerWidth: innerWidth, innerHeight: innerHeight, dpr: devicePixelRatio,
    canvas: c ? {width: c.width, height: c.height, rect: rect(c)} : null,
    container: rect(cont), wrapper: rect(wrap),
    ancestors: c ? chain(c) : [],
    scroll: {x: scrollX, y: scrollY,
             docW: document.documentElement.scrollWidth,
             docH: document.documentElement.scrollHeight,
             bodyW: document.body.scrollWidth,
             bodyH: document.body.scrollHeight}
  };
}
"""


def load_table(path):
    import numpy as np
    d = np.load(path, allow_pickle=True).item()
    return {str(int(k)): [float(v) for v in vals] for k, vals in d.items()}


def load_dqn(path):
    import torch
    sd = torch.load(path, map_location="cpu")
    return {k: sd[k].numpy().tolist() for k in
            ("net.0.weight", "net.0.bias", "net.2.weight", "net.2.bias",
             "net.4.weight", "net.4.bias")}


INSTALL = r"""
([agent, name, q, net, speedMult, cap, hudOn, rafHz, dt]) => {
  if (window.__watchInstalled) return true;
  window.__watchInstalled = true;
  const r = window.Runner.instance_;
  const nativeCancelRAF = window.cancelAnimationFrame.bind(window);
  // игра не должна сама ставить rAF: один управляемый цикл ниже
  window.requestAnimationFrame = function () { return 0; };
  window.cancelAnimationFrame = function (id) { nativeCancelRAF(id); };
  const realNow = performance.now.bind(performance);
  const w = window.__watch = {
    agent: agent, name: name, q: q || {}, net: net || null,
    speedMult: speedMult, cap: cap,
    rafHz: rafHz, dt: dt, virtual: 0,
    active: false, paused: false, frames: 0, deaths: 0,
    action: 0, dist1: 1000, speed: 0, death: null,
    t0: 0, elapsed: 0, ring: [], jumpObs: null, marks: [],
    fps: 0, fpsMeasured: false, timeout: false, lastProgress: 0
  };
  let el = null;
  if (hudOn) {
    el = document.createElement('div');
    el.id = '__dino_hud';
    el.style.cssText = 'position:fixed;right:12px;top:12px;z-index:9999;' +
      'background:rgba(0,0,0,.78);color:#5f5;font:12px monospace;' +
      'padding:8px 10px;white-space:pre;pointer-events:none;' +
      'border:1px solid #5f5;border-radius:4px;min-width:250px';
    document.body.appendChild(el);
  }
  function r2(v) { return Math.round(v * 100) / 100; }
  function snap() {
    const d = r.tRex, list = r.horizon.obstacles || [];
    const o = list[0] || null, n = list[1] || null;
    return {
      dead: !!r.crashed,
      d1: o ? o.xPos - d.xPos : 1000,
      w1: o ? o.width : 0, t1: o ? o.typeConfig.type : null,
      oy1: o ? o.yPos : 0, oh1: o ? o.typeConfig.height : 0,
      d2: n ? n.xPos - d.xPos : 1000, t2: n ? n.typeConfig.type : null,
      gap: (o && n) ? (n.xPos - o.xPos - o.width) : -1,
      removed1: o ? !!o.remove : false,
      speed: r.currentSpeed, y: r2(d.yPos), vy: r2(d.jumpVelocity),
      jumping: !!d.jumping, ducking: !!d.ducking, score: r.distanceRan
    };
  }
  function bucket(v, e) {
    for (let i = 0; i < e.length; i++) if (v <= e[i]) return i;
    return e.length;
  }
  function encode(s) {
    const sp = (s.speed && s.speed > 0.1) ? s.speed : 6.0;
    let k = 0;
    if (s.t1 === 'CACTUS_SMALL') k = 1;
    else if (s.t1 === 'CACTUS_LARGE') k = 2;
    else if (s.t1 === 'PTERODACTYL') k = s.oy1 < 60 ? 3 : (s.oy1 < 95 ? 4 : 5);
    const g = s.gap < 0 ? 0 : 1 + bucket(s.gap, [150,300,500]);
    const t = bucket(s.d1 / sp, [10,13,15,16,17,18,20,24,30]);
    return ((((t * 6 + k) * 3 + bucket(s.w1, [20,45])) * 2 +
             (s.jumping ? 1 : 0)) * 5) + g;
  }
  function greedy(s) {
    const row = w.q[encode(s)] || [0,0,0];
    let best = 0, bv = -Infinity;
    for (let i = 0; i < 3; i++) {
      if (s.jumping && i === 1) continue;
      if (row[i] > bv) { bv = row[i]; best = i; }
    }
    return best;
  }
  function rule(s) {
    const th = Math.max(25.0, 17.0 * s.speed);
    let a = 0;
    if (s.t1 === 'PTERODACTYL') {
      if (s.oy1 >= 60 && s.oy1 <= 90 && s.d1 <= 260) a = 2;
      else if (s.oy1 >= 95 && s.d1 <= th + 25) a = 1;
    } else if (s.d1 <= th && !s.jumping) a = 1;
    if (s.jumping && a === 1) a = 0;
    if (a === 1 && !s.jumping && !s.ducking) {
      w.jumpObs = (r.horizon.obstacles || [])[0] || null;
    }
    const nextLarge = (s.t1 === 'CACTUS_LARGE' && s.d1 <= 800) ||
                      (s.t2 === 'CACTUS_LARGE' && s.d2 <= 800);
    if (s.jumping && w.jumpObs && w.jumpObs.remove && nextLarge) {
      w.jumpObs = null;
      a = 3;
    }
    return a;
  }
  function rule4(s) {
    // rule_v3 + одна ветка DROP (rule_v4.py)
    if (s.jumping && s.t1 === 'PTERODACTYL' && s.oy1 >= 95
        && w.jumpObs && w.jumpObs.remove) {
      w.jumpObs = null;
      return 3;
    }
    return rule(s);
  }
  function dqn(s) {
    const n = w.net;
    let kind = [0,0,0,0,0,0];
    if (s.t1 === 'CACTUS_SMALL') kind[1] = 1;
    else if (s.t1 === 'CACTUS_LARGE') kind[2] = 1;
    else if (s.t1 === 'PTERODACTYL')
      kind[s.oy1 >= 95 ? 3 : (s.oy1 >= 60 ? 4 : 5)] = 1;
    const gap = s.gap > 0 ? s.gap : 400.0;
    const x = [
      Math.min(s.d1 / Math.max(s.speed, 0.5), 22) / 22,
      Math.min(s.d1, 400) / 400, Math.min(s.oh1, 60) / 60,
      Math.min(s.w1, 120) / 120, ...kind,
      Math.min(s.speed, 13) / 13, s.y / 100, s.vy / 12,
      s.jumping ? 1 : 0, s.ducking ? 1 : 0, Math.min(gap, 400) / 400
    ];
    function layer(X, W, B) {
      const out = new Array(B.length).fill(0);
      for (let i = 0; i < W.length; i++)
        for (let j = 0; j < W[i].length; j++) out[j] += X[i] * W[i][j];
      for (let j = 0; j < out.length; j++) {
        out[j] += B[j];
        if (out[j] < 0) out[j] = 0;
      }
      return out;
    }
    const out = layer(layer(layer(x, n['net.0.weight'], n['net.0.bias']),
                            n['net.2.weight'], n['net.2.bias']),
                      n['net.4.weight'], n['net.4.bias']);
    if (s.jumping) out[1] = -1e9;
    return out[0] >= out[1] && out[0] >= out[2] ? 0 : (out[1] >= out[2] ? 1 : 2);
  }
  function policy(s) {
    if (w.agent === 'rule_v3') return rule(s);
    if (w.agent === 'rule_v4') return rule4(s);
    if (w.agent === 'table') return greedy(s);
    return dqn(s);
  }
  function apply(s, a) {
    const d = r.tRex;
    if (a === 1 && !d.jumping && !d.ducking) {
      d.startJump(r.currentSpeed); d.endJump();
    } else if (a === 2 && !d.jumping && !d.ducking) {
      d.setDuck(true);
    } else if (a !== 2 && d.ducking) {
      d.setDuck(false);
    }
    if (a === 3 && d.jumping) d.setSpeedDrop();
  }
  function hud() {
    if (!el) return;
    const names = ['RUN','JUMP','DUCK','DROP','DEAD'];
    el.textContent = [
      w.name + ' | game ' + w.game,
      'frames ' + w.frames + ' | dist ' + Math.round(w.score),
      'speed ' + r2(w.speed) + ' | fps ' + r2(w.frames / Math.max(w.elapsed, .001)),
      'action ' + names[w.action < 0 ? 4 : w.action] + ' | dist1 ' + r2(w.dist1),
      'deaths ' + w.deaths
    ].join('\n') + (w.death ? '\nDEAD ' + w.death.type + ' speed ' +
                              w.death.speed + ' jumping ' + w.death.jumping : '');
  }
  window.__watchStart = function (seed, gameNo) {
    let x = seed >>> 0;
    Math.random = function () {
      x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
      return x / 4294967296;
    };
    w.game = gameNo;
    w.t0 = realNow(); w.elapsed = 0; w.score = 0;
    w.active = true; w.paused = false; w.frames = 0; w.death = null;
    w.fps = 0; w.fpsMeasured = false; w.timeout = false;
    w.lastProgress = realNow();
    w.action = 0; w.dist1 = 1000; w.ring = []; w.jumpObs = null;
    w.marks = [];
    w.virtual = 0;
    performance.now = function () { return 0; };
    if (r.raqId) cancelAnimationFrame(r.raqId);
    r.raqId = 0; r.updatePending = false;
    r.playingIntro = false; r.tRex.playingIntro = false; r.activated = true;
    r.horizon.obstacleHistory.length = 0; r.horizon.clouds = [];
    r.restart();
    r.horizon.obstacleHistory.length = 0; r.horizon.clouds = [];
    r.playingIntro = false; r.tRex.playingIntro = false; r.activated = true;
    r.time = 0;
    performance.now = function () { return w.virtual; };
    hud();
    return true;
  };
  window.__watchStop = function (timeout) {
    w.active = false;
    if (timeout) w.timeout = true;
    performance.now = realNow;
    return {frames: w.frames, score: w.score, death: w.death,
            deaths: w.deaths, elapsed: w.elapsed, timeout: w.timeout,
            fps: w.fps, ring: w.ring, marks: w.marks};
  };
  const orig = r.update.bind(r);
  r.update = function () {
    if (!w.active || w.paused) return;
    // фиксированный dt: скорость игры не зависит от частоты rAF
    w.virtual += w.dt * w.speedMult;
    performance.now = function () { return w.virtual; };
    const s = snap();
    const a = policy(s);
    apply(s, a);
    orig();
    const s2 = snap();
    w.frames++;
    w.action = a;
    w.dist1 = s2.d1;
    w.speed = s2.speed;
    w.score = s2.score;
    w.elapsed = (realNow() - w.t0) / 1000;
    if (!w.fpsMeasured && w.elapsed >= 10) {
      w.fpsMeasured = true;
      w.fps = w.frames / w.elapsed;
    }
    w.lastProgress = realNow();
    w.ring.push([w.frames, a, s2.y, r2(s2.d1), r2(s2.d2)]);
    if (w.ring.length > 60) w.ring.shift();
    if ([1, 2, 3, 5, 10, 50, 100, 200, 500, 600, 700, 800, 900, 1000].indexOf(w.frames) >= 0)
      w.marks.push([w.frames, r2(s2.score), r2(s2.speed), a, w.virtual]);
    if (s2.dead) {
      w.death = {type: s2.t1, width: s2.w1, oy: r2(s2.oy1), speed: r2(s2.speed),
                 dist: r2(s2.d1), jumping: s2.jumping};
      w.deaths++;
      w.action = -1;
      w.active = false;
      w.paused = true;
    } else if (w.frames >= w.cap) {
      w.active = false;
    }
    hud();
  };
  r.scheduleNextUpdate = function () { this.updatePending = false; };
  window.setTimeout(function tick () {
    if (w.active && !w.paused) r.update();
    window.setTimeout(tick, 1000 / w.rafHz);
  }, 1000 / w.rafHz);
  return true;
}
"""


def launch(p, headless=False, viewport=None):
    kw = dict(channel="chrome", headless=headless, args=CHROME_ARGS)
    b = p.chromium.launch(**kw)
    if viewport is None:
        viewport = {"width": 1280, "height": 720}
    ctx = b.new_context(viewport=viewport, device_scale_factor=1)
    return b, ctx


def prepare_page(page, agent, name, q, net, args):
    page.goto(GAME_URL, wait_until="networkidle")
    apply_css(page, args)
    time.sleep(0.6)
    page.locator("canvas").click(force=True)
    page.keyboard.press("Space")
    time.sleep(0.3)
    mute = page.evaluate(MUTE)
    page.bring_to_front()
    page.evaluate("""() => {
      const r = window.Runner.instance_;
      if (r.raqId) cancelAnimationFrame(r.raqId);
      r.raqId = 0; r.updatePending = false;
    }""")
    page.evaluate(INSTALL, [agent, name, q, net, args.speed_mult, args.cap,
                            args.hud, args.raf_hz, DT])
    return mute


def wait_game(page, args, game_no, seed):
    t0 = time.perf_counter()
    last_print = t0
    last_progress = time.time()
    last_csv = time.time()
    prev_frames = -1
    while page.evaluate("() => !!window.__watch.active"):
        time.sleep(0.25)
        now = time.perf_counter()
        st = page.evaluate("""() => {const w=window.__watch;
          return [w.frames, Math.round(w.score), w.speed, w.deaths,
                  w.elapsed, w.cap];}""")
        if st[0] > prev_frames:
            prev_frames = st[0]
            last_progress = time.time()
        if now - last_print >= 300.0:
            last_print = now
            fps = st[0] / max(st[4], 0.001)
            eta = max(0.0, (st[5] - st[0]) / max(fps, 0.1))
            print(f"  game {game_no}/{args.games} {int(now-t0)}s {st[0]}f "
                  f"{st[1]}d fps {fps:.1f} ETA {int(eta)}s "
                  f"speed {round(st[2],2)} deaths {st[3]}", flush=True)
            if getattr(args, "csv", ""):
                try:
                    with open(args.csv, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow(
                            ["PROGRESS", game_no, seed, st[0], st[1],
                             f"fps {fps:.1f} eta {int(eta)}s", ""])
                    last_csv = time.time()
                except OSError:
                    pass
        if time.time() - last_progress > 60:
            print(f"  Прогресс не растёт 60 с: {prev_frames}f, TIMEOUT",
                  flush=True)
            page.evaluate("(t) => window.__watchStop(t)", True)
            break
        if getattr(args, "csv", "") and time.time() - last_csv > 330:
            print("CSV STALE >330s, abort", flush=True)
            os._exit(2)


def run_games(p, args, agent, table=None, dqn=None):
    name = args.agent
    csv_path = getattr(args, "csv", "")
    fh = open(csv_path, "w", newline="", encoding="utf-8") if csv_path else None
    cw = csv.writer(fh) if fh else None
    if cw:
        cw.writerow(["game", "seed", "frames", "distanceRan", "status", "death"])
        fh.flush()
    bkw, ctx = launch(p, headless=getattr(args, "headless", False),
                      viewport=args.viewport)
    try:
        page = ctx.new_page()
        mute = prepare_page(page, agent, name, table or {}, dqn, args)
        print("audio", json.dumps(mute), flush=True)
        deaths = 0
        valid = 0
        invalid = []
        timeouts = []
        for i in range(args.games):
            seed = args.seed0 + i
            page.evaluate("([s,i]) => window.__watchStart(s,i)", [seed, i + 1])
            if args.screenshot:
                time.sleep(2.0)
                page.screenshot(path=args.screenshot)
            wait_game(page, args, i + 1, seed)
            r = page.evaluate("() => window.__watchStop()")
            if r.get("timeout"):
                timeouts.append(seed)
                print(f"TIMEOUT seed {seed}: {r['frames']}f "
                      f"fps {round(r['fps'],1)} progress-watchdog",
                      flush=True)
                if cw:
                    cw.writerow([i + 1, seed, r["frames"],
                                 round(r["score"], 1), "TIMEOUT", ""])
                    fh.flush()
                time.sleep(2.0)
                continue
            if r["frames"] < 100 and not r["death"]:
                invalid.append(seed)
                print(f"INVALID seed {seed}: {r['frames']}f без смерти от препятствия",
                      flush=True)
                if cw:
                    cw.writerow([i + 1, seed, r["frames"],
                                 round(r["score"], 1), "INVALID", ""])
                    fh.flush()
                time.sleep(2.0)
                continue
            valid += 1
            if r["death"]:
                deaths += 1
            fps = r["frames"] / max(r["elapsed"], 0.001)
            print(f"game {i+1} seed {seed}: {r['frames']}f "
                  f"{round(r['score'],1)}d {round(fps,1)}fps "
                  f"{'DEAD ' + json.dumps(r['death'], ensure_ascii=False) if r['death'] else 'CAP'}"
                  "", flush=True)
            if cw:
                cw.writerow([i + 1, seed, r["frames"], round(r["score"], 1),
                             "DEAD" if r["death"] else "CAP",
                             json.dumps(r["death"], ensure_ascii=False)
                             if r["death"] else ""])
                fh.flush()
            if r["marks"]:
                print("marks", json.dumps(r["marks"]), flush=True)
            if args.trace and r["death"]:
                print("trace frame act y dist1 dist2", flush=True)
                for row in r["ring"]:
                    print(" ".join(str(x) for x in row), flush=True)
            time.sleep(2.0)
        if args.games:
            print("valid", valid, "deaths", deaths, "invalid", len(invalid),
                  "invalid_seeds", invalid, "timeouts", len(timeouts),
                  "timeout_seeds", timeouts, flush=True)
        page.close()
    finally:
        bkw.close()
        if fh:
            fh.close()


def watch_one(p, agent_spec, seed, seconds=60.0, cap=20000):
    """Одна видимая жадная игра для --watch-every в обучении."""
    a = SimpleNamespace(agent=agent_spec, games=1, seed0=seed,
                        speed_mult=1.0, cap=cap,
                        trace=False, hud=False, raf_hz=60, screenshot="",
                        no_css=False, viewport={"width": 1280, "height": 720})
    agent = agent_spec
    table, net = {}, None
    if agent.startswith("table:"):
        table = load_table(agent.split(":", 1)[1])
        agent = "table"
    elif agent.startswith("dqn:"):
        net = load_dqn(agent.split(":", 1)[1])
        agent = "dqn"
    run_games(p, a, agent, table, net)


def compare_mode(p, args, table):
    specs = [("rule_v3", "rule_v3", {}, None),
             ("rule_v4", "rule_v4", {}, None),
             ("table", "table:v4", table, None)]
    bkw, _ = launch(p, viewport=args.viewport)
    pages = []
    try:
        for i, (agent, name, q, net) in enumerate(specs):
            ctx = bkw.new_context(viewport=args.viewport,
                                  device_scale_factor=1)
            page = ctx.new_page()
            prepare_page(page, agent, name, q, net, args)
            try:
                page.evaluate("(x) => window.moveTo(x,0)", i * 1300)
            except Exception:
                pass
            pages.append((page, agent))
        for page, agent in pages:
            page.evaluate("(s) => window.__watchStart(s,1)", args.seed0)
        for page, agent in pages:
            wait_game(page, args, 1, args.seed0)
            r = page.evaluate("() => window.__watchStop()")
            print(agent, r["frames"], round(r["score"], 1),
                  json.dumps(r["death"], ensure_ascii=False) if r["death"] else "CAP",
                  flush=True)
    finally:
        bkw.close()


def raf_rate(p, seconds=10.0):
    bkw, ctx = launch(p)
    try:
        page = ctx.new_page()
        page.goto(GAME_URL, wait_until="networkidle")
        apply_css(page, None)
        r = page.evaluate("""(ms) => new Promise(resolve => {
          let n = 0; const t0 = performance.now();
          function f() { n++;
            if (performance.now() - t0 < ms) requestAnimationFrame(f);
            else resolve({frames: n, ms: performance.now() - t0});
          }
          requestAnimationFrame(f);
        })""", seconds * 1000)
        print("rAF native", r["frames"], "frames /", round(r["ms"]), "ms =",
              round(r["frames"] / (r["ms"] / 1000), 1), "fps", flush=True)
        page.close()
    finally:
        bkw.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True,
                    help="rule_v3 | rule_v4 | table:<file.npy> | dqn:<file.pt>")
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--seed0", type=int, default=92000)
    ap.add_argument("--speed-mult", type=float, default=1.0)
    ap.add_argument("--cap", type=int, default=20000)
    ap.add_argument("--raf-hz", type=int, default=60)
    ap.add_argument("--hud", action="store_true")
    ap.add_argument("--headless", action="store_true",
                    help="headless-браузер (звук выключен через --mute-audio)")
    ap.add_argument("--no-css", action="store_true",
                    help="не применять CSS-правку (для проверки до/после)")
    ap.add_argument("--csv", default="", help="CSV с результатами игр")
    ap.add_argument("--viewport", default="1280x720")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--raf-rate", action="store_true")
    ap.add_argument("--screenshot", default="", help="PNG через 2 с после старта")
    a = ap.parse_args()
    w, h = (int(x) for x in a.viewport.lower().split("x"))
    a.viewport = {"width": w, "height": h}

    if a.raf_rate:
        with sync_playwright() as p:
            raf_rate(p)
        return

    agent = a.agent
    table, net = {}, None
    if agent.startswith("table:"):
        table = load_table(agent.split(":", 1)[1])
        agent = "table"
    elif agent.startswith("dqn:"):
        net = load_dqn(agent.split(":", 1)[1])
        agent = "dqn"
    with sync_playwright() as p:
        if a.diagnose:
            bkw, ctx = launch(p, viewport=a.viewport)
            try:
                page = ctx.new_page()
                print("playwright viewport", page.viewport_size, flush=True)
                page.goto(GAME_URL, wait_until="networkidle")
                print("BEFORE", json.dumps(page.evaluate(DIAGNOSE),
                                           ensure_ascii=False), flush=True)
                apply_css(page, a)
                print("AFTER", json.dumps(page.evaluate(DIAGNOSE),
                                          ensure_ascii=False), flush=True)
                page.close()
            finally:
                bkw.close()
        elif a.compare:
            compare_mode(p, a, table)
        else:
            run_games(p, a, agent, table, net)


if __name__ == "__main__":
    main()
