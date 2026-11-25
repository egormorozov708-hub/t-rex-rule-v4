"""Принятое правило B (шаг 2): rule_v1 + speed-drop перед вторым кактусом.

Обоснование (управляемый сценарий, gap_experiment.csv, 2820 прогонов):
    прыжок при dist1 = 20..45  -> 0% выживания (столкновение с малым кактусом);
    dist1 = 50..160            -> 0..95% (приземление слишком близко ко второму);
    dist1 >= 165               -> 100% (20/20 для size 1/2/3).
Один прыжок через оба кактуса не проходит ни при одном dist1 (gap_single.csv).
Speed-drop сразу после того, как первый кактус позади, даёт 100% при dist1>=50
(gap_drop.csv).

A/B на seed 80000-80029, старт speed 13, лимит 10000:
    rule_v1: 29/30 до лимита, 1 смерть, median 10000;
    rule_v2: 30/30 до лимита, 0 смертей, median 10000.

Физика игры не меняется: используется штатный Trex.setSpeedDrop(), доступный
игроку при зажатой кнопке «вниз» в прыжке. rule_v1.py не тронут.
"""

from rule_v1 import (B, BIRD_DUCK_DIST, BIRD_DUCK_Y, BIRD_JUMP_EXTRA,
                     BIRD_JUMP_MIN_Y, FRAME_SKIP, K, MIN_THRESHOLD)

NAME = "rule_v2"
LOOK_DIST = 800.0          # px до второго CACTUS_LARGE
DROP = 3                   # Rack action: штатный Trex.setSpeedDrop()

# Авторитетная реализация для встраивания в Runner.update() (без round-trip).
# В rule_v2_drop_eval.py используется именно она.
RULE_V2_JS = """
// state: {jumpObs: null} — объект первого препятствия в текущем прыжке.
function ruleV2(s, d, state) {
  const th = Math.max(25.0, K * s.speed + B);
  let a = 0;
  if (s.type === 'PTERODACTYL') {
    if (s.oy >= 60 && s.oy <= 90 && s.dist <= 260) a = 2;
    else if (s.oy >= 95 && s.dist <= th + 25) a = 1;
  } else if (s.dist <= th && !s.jumping) {
    a = 1;
  }
  if (s.jumping && a === 1) a = 0;
  if (a === 1 && !d.jumping && !d.ducking) {
    state.jumpObs = (Runner.instance_.horizon.obstacles || [])[0] || null;
    d.startJump(Runner.instance_.currentSpeed);
    d.endJump();
  } else if (a === 2 && !d.jumping && !d.ducking) {
    d.setDuck(true);
  } else if (a !== 2 && d.ducking) {
    d.setDuck(false);
  }
  const nextLarge = (s.type === 'CACTUS_LARGE' && s.dist <= LOOK_DIST) ||
                    (s.type2 === 'CACTUS_LARGE' && s.dist2 <= LOOK_DIST);
  if (d.jumping && state.jumpObs && state.jumpObs.remove && nextLarge) {
    d.setSpeedDrop();
    state.jumpObs = null;
  }
  return a;
}
"""


class RuleV2:
    """Python-обёртка; snapshot должен содержать oid/removed/dist2/type2.

    oid — стабильный идентификатор первого препятствия, removed — его флаг
    удаления из Horizon.updateObstacles(). Эквивалентный in-page вариант выше
    не требует этих полей: он хранит ссылку на объект препятствия.
    """

    def __init__(self):
        self.jump_oid = None

    def choose_action(self, s):
        threshold = max(MIN_THRESHOLD, K * s["speed"] + B)
        if s["type"] == "PTERODACTYL":
            if BIRD_DUCK_Y[0] <= s["oy"] <= BIRD_DUCK_Y[1] and s["dist"] <= BIRD_DUCK_DIST:
                action = 2
            elif s["oy"] >= BIRD_JUMP_MIN_Y and s["dist"] <= threshold + BIRD_JUMP_EXTRA:
                action = 1
            else:
                action = 0
        elif s["dist"] <= threshold and not s["jumping"]:
            action = 1
        else:
            action = 0
        if s["jumping"] and action == 1:
            action = 0

        if action == 1 and not s["jumping"] and not s["ducking"]:
            self.jump_oid = s.get("oid")
        elif action == 2 and not s["jumping"] and not s["ducking"]:
            pass
        elif action != 2 and s["ducking"]:
            pass

        next_large = ((s["type"] == "CACTUS_LARGE" and s["dist"] <= LOOK_DIST)
                      or (s.get("type2") == "CACTUS_LARGE"
                          and s.get("dist2", 1000) <= LOOK_DIST))
        if (s["jumping"] and self.jump_oid is not None
                and s.get("removed") and next_large):
            self.jump_oid = None
            return DROP
        return action


RULE = {"k": K, "b": B, "look_dist": LOOK_DIST,
        "frame_skip": FRAME_SKIP, "name": NAME}
