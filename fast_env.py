"""Детерминированный ускоренный режим для t-rex-runner.

Источник времени подменяется: rAF останавливается, Runner.instance_.update()
вызывается вручную с фиксированным dt = 1000/60. Физика и правила игры не меняются.
"""

import time

GAME_URL = "https://wayou.github.io/t-rex-runner/"
DT = 1000.0 / 60.0
CHROME_HINT = "Chrome не найден: установите системный Google Chrome (channel='chrome')."
PLAYWRIGHT_HINT = ("Playwright не найден: python -m pip install -r requirements.txt; "
                   "python -m playwright install chromium")
NETWORK_HINT = ("Нет доступа к сети: проверьте интернет и "
                "https://wayou.github.io/t-rex-runner/")

PREP = """
() => {
  const r = window.Runner.instance_;
  r.scheduleNextUpdate = function () { this.updatePending = false; };
  cancelAnimationFrame(r.raqId);
  r.raqId = 0;
  r.updatePending = false;
  return {raqId: r.raqId, playing: r.playing};
}
"""

RESET = """
() => {
  const r = window.Runner.instance_;
  r.playingIntro = false;
  r.tRex.playingIntro = false;
  r.activated = true;
  r.horizon.obstacleHistory.length = 0;
  r.horizon.clouds = [];
  r.restart();
  r.horizon.obstacleHistory.length = 0;
  r.horizon.clouds = [];
  r.scheduleNextUpdate = function () { this.updatePending = false; };
  cancelAnimationFrame(r.raqId);
  r.raqId = 0;
  r.updatePending = false;
  r.playingIntro = false;
  r.tRex.playingIntro = false;
  r.activated = true;
  return {playing: r.playing, crashed: r.crashed, score: r.distanceRan};
}
"""

SNAP = """
() => {
  const r = window.Runner.instance_;
  const d = r.tRex;
  const list = r.horizon.obstacles || [];
  const o = list[0] || null;
  const n = list[1] || null;
  const dead = !!r.crashed;
  const info = {
    dead: dead,
    status: dead ? "DEAD" : (r.playing ? "OK" : "NOT_PLAYING"),
    dist: o ? o.xPos - d.xPos : 1000,
    width: o ? o.width : 0,
    size: o ? o.size : 0,
    type: o ? o.typeConfig.type : null,
    oy: o ? o.yPos : 0,
    oh: o ? o.typeConfig.height : 0,
    gap: (o && n) ? (n.xPos - o.xPos - o.width) : -1,
    dist2: (o && n) ? (n.xPos - d.xPos) : 1000,
    type2: n ? n.typeConfig.type : null,
    width2: n ? n.width : 0,
    removed: o ? !!o.remove : false,
    jumped_removed: !!(window.__jumpObs && window.__jumpObs.remove),
    oid: o ? (o.__oid || (o.__oid = (window.__oidSeq = (window.__oidSeq || 0) + 1))) : null,
    speed: r.currentSpeed,
    y: d.yPos,
    vy: d.jumpVelocity,
    jumping: !!d.jumping,
    ducking: !!d.ducking,
    score: r.distanceRan,
    obstacles: list.length,
    mark: o ? !!o.testBird : false,
    frames: r.frames,
    time: r.time
  };
  if (dead) {
    info.death = {
      type: info.type, width: info.width, size: info.size,
      oy: round2(info.oy), oh: info.oh,
      speed: round2(info.speed), dist: round2(info.dist),
      jumping: info.jumping, ducking: info.ducking, y: round2(info.y)
    };
  }
  return info;
  function round2(v) { return Math.round(v * 100) / 100; }
}
"""

STEP = """
([action, n, dt, seed]) => {
  const r = window.Runner.instance_;
  const d = r.tRex;
  if (seed !== null && seed !== undefined) {
    let x = seed >>> 0;
    Math.random = function () {
      x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
      return x / 4294967296;
    };
  }
  if (action === 1 && !d.jumping && !d.ducking)
    window.__jumpObs = (r.horizon.obstacles || [])[0] || null;
  if (action === 3) window.__jumpObs = null;
  if (!r.crashed) {
    if (action === 1 && !d.jumping && !d.ducking) {
      d.startJump(r.currentSpeed);
      d.endJump();
    } else if (action === 2 && !d.jumping && !d.ducking) {
      d.setDuck(true);
    } else if (action !== 2 && d.ducking) {
      d.setDuck(false);
    }
    if (action === 3 && d.jumping) {
      d.setSpeedDrop();
    }
  }
  for (let i = 0; i < n; i++) {
    if (r.crashed) break;
    r.playingIntro = false;
    d.playingIntro = false;
    r.activated = true;
    r.time = performance.now() - dt;
    r.update();
  }
  const list = r.horizon.obstacles || [];
  const o = list[0] || null;
  const nx = list[1] || null;
  const dead = !!r.crashed;
  const info = {
    dead: dead,
    status: dead ? "DEAD" : (r.playing ? "OK" : "NOT_PLAYING"),
    dist: o ? o.xPos - d.xPos : 1000,
    width: o ? o.width : 0,
    size: o ? o.size : 0,
    type: o ? o.typeConfig.type : null,
    oy: o ? o.yPos : 0,
    oh: o ? o.typeConfig.height : 0,
    gap: (o && nx) ? (nx.xPos - o.xPos - o.width) : -1,
    dist2: (o && nx) ? (nx.xPos - d.xPos) : 1000,
    type2: nx ? nx.typeConfig.type : null,
    width2: nx ? nx.width : 0,
    removed: o ? !!o.remove : false,
    jumped_removed: !!(window.__jumpObs && window.__jumpObs.remove),
    oid: o ? (o.__oid || (o.__oid = (window.__oidSeq = (window.__oidSeq || 0) + 1))) : null,
    speed: r.currentSpeed,
    y: d.yPos,
    vy: d.jumpVelocity,
    jumping: !!d.jumping,
    ducking: !!d.ducking,
    score: r.distanceRan,
    obstacles: list.length,
    mark: o ? !!o.testBird : false,
    frames: r.frames,
    time: r.time
  };
  if (dead) {
    info.death = {
      type: info.type, width: info.width, size: info.size,
      oy: round2(info.oy), oh: info.oh,
      speed: round2(info.speed), dist: round2(info.dist),
      jumping: info.jumping, ducking: info.ducking, y: round2(info.y)
    };
  }
  return info;
  function round2(v) { return Math.round(v * 100) / 100; }
}
"""


RULE_RUN = """
([seed, k, b, maxSteps, frameSkip, dt]) => {
  const r = window.Runner.instance_;
  let x = seed >>> 0;
  Math.random = function () {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    return x / 4294967296;
  };
  const realNow = performance.now.bind(performance);
  let vnow = 0;
  performance.now = function () { return vnow; };
  r.scheduleNextUpdate = function () { this.updatePending = false; };
  cancelAnimationFrame(r.raqId);
  r.raqId = 0;
  r.updatePending = false;
  r.playingIntro = false;
  r.tRex.playingIntro = false;
  r.activated = true;
  r.horizon.obstacleHistory.length = 0;
  r.horizon.clouds = [];
  r.restart();
  r.horizon.obstacleHistory.length = 0;
  r.horizon.clouds = [];
  r.playingIntro = false;
  r.tRex.playingIntro = false;
  r.activated = true;
  const d = r.tRex;
  function r2(v) { return Math.round(v * 100) / 100; }
  function snap() {
    const list = r.horizon.obstacles || [];
    const o = list[0] || null;
    const n = list[1] || null;
    const s = {
      dead: !!r.crashed,
      dist: o ? o.xPos - d.xPos : 1000,
      width: o ? o.width : 0,
      size: o ? o.size : 0,
      type: o ? o.typeConfig.type : null,
      oy: o ? o.yPos : 0,
      oh: o ? o.typeConfig.height : 0,
      gap: (o && n) ? (n.xPos - o.xPos - o.width) : -1,
      dist2: (o && n) ? (n.xPos - d.xPos) : 1000,
      type2: n ? n.typeConfig.type : null,
      width2: n ? n.width : 0,
      removed: o ? !!o.remove : false,
      jumped_removed: !!(window.__jumpObs && window.__jumpObs.remove),
      oid: o ? (o.__oid || (o.__oid = (window.__oidSeq = (window.__oidSeq || 0) + 1))) : null,
      speed: r.currentSpeed,
      y: d.yPos, vy: d.jumpVelocity,
      jumping: !!d.jumping, ducking: !!d.ducking,
      score: r.distanceRan, obstacles: list.length,
      frames: r.frames
    };
    if (s.dead) {
      s.death = {
        type: s.type, width: s.width, size: s.size,
        oy: r2(s.oy), oh: s.oh, speed: r2(s.speed), dist: r2(s.dist),
        jumping: s.jumping, ducking: s.ducking, y: r2(s.y),
        gap: r2(s.gap), obstacles: s.obstacles,
        next: n ? {type: n.typeConfig.type, width: n.width,
                   size: n.size, oy: r2(n.yPos),
                   dist: r2(n.xPos - d.xPos)} : null
      };
    }
    return s;
  }
  function rule(s) {
    const th = Math.max(25.0, k * s.speed + b);
    if (s.type === 'PTERODACTYL') {
      if (s.oy >= 60 && s.oy <= 90 && s.dist <= 260) return 2;
      if (s.oy >= 95 && s.dist <= th + 25) return 1;
      return 0;
    }
    if (s.dist <= th && !s.jumping) return 1;
    return 0;
  }
  vnow += dt;
  r.update();
  let s = snap();
  let frames = 1;
  while (!s.dead && frames < maxSteps) {
    let a = rule(s);
    if (s.jumping && a === 1) a = 0;
    if (a === 1 && !d.jumping && !d.ducking)
      window.__jumpObs = (r.horizon.obstacles || [])[0] || null;
    if (a === 1 && !d.jumping && !d.ducking) {
      d.startJump(r.currentSpeed);
      d.endJump();
    } else if (a === 2 && !d.jumping && !d.ducking) {
      d.setDuck(true);
    } else if (a !== 2 && d.ducking) {
      d.setDuck(false);
    }
    for (let i = 0; i < frameSkip && !r.crashed; i++) {
      r.playingIntro = false;
      d.playingIntro = false;
      r.activated = true;
      vnow += dt;
      r.update();
    }
    frames += frameSkip;
    s = snap();
  }
  performance.now = realNow;
  return {
    frames: frames, score: s.score, death: s.death || null,
    capped: (!s.dead && frames >= maxSteps),
    speed: r2(r.currentSpeed)
  };
}
"""


class FastGame:
    def __init__(self, page):
        self.page = page
        self.frames = 0

    def prepare(self):
        return self.page.evaluate(PREP)

    def reset(self, seed=None, speed=None):
        self.page.evaluate(RESET)
        if speed is not None:
            self.page.evaluate("(v) => Runner.instance_.setSpeed(v)", speed)
        self.frames = 0
        if seed is not None:
            return self.seed_step(seed)
        return self.step(0, 1)

    def seed_step(self, seed):
        s = self.page.evaluate(STEP, [0, 1, DT, int(seed) & 0xFFFFFFFF])
        self.frames += 1
        return s

    def observe(self):
        return self.page.evaluate(SNAP)

    def step(self, action=0, frames=1):
        s = self.page.evaluate(STEP, [action, frames, DT, None])
        self.frames += frames
        return s

    def run_rule(self, seed, k, b, max_steps=50000, frame_skip=1):
        """Целая игра с правилом A внутри страницы; см. RULE_RUN."""
        s = self.page.evaluate(RULE_RUN,
                               [int(seed) & 0xFFFFFFFF, k, b,
                                int(max_steps), int(frame_skip), DT])
        self.frames = s["frames"]
        return s


def make_page(browser):
    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError as exc:
        raise RuntimeError(PLAYWRIGHT_HINT) from exc
    page = browser.new_page(viewport={"width": 800, "height": 600})
    try:
        page.goto(GAME_URL, wait_until="networkidle")
    except PlaywrightError as exc:
        page.close()
        raise RuntimeError(NETWORK_HINT) from exc
    page.evaluate("""() => {
  const r = window.Runner.instance_;
  if (r) {
    r.playSound = function () {};
    if (r.audioContext && r.audioContext.suspend) r.audioContext.suspend();
  }
  return true;
}""")
    time.sleep(1.0)
    page.locator("canvas").click(force=True)
    page.keyboard.press("Space")
    time.sleep(0.3)
    return page


def browser_ctx(p):
    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError as exc:
        raise RuntimeError(PLAYWRIGHT_HINT) from exc
    try:
        return p.chromium.launch(
            channel="chrome", headless=True,
            args=["--disable-gpu", "--disable-extensions", "--mute-audio"])
    except (PlaywrightError, OSError) as exc:
        raise RuntimeError(CHROME_HINT) from exc
