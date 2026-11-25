"""rule_v4 = rule_v3 + один DROP на высоком птеродактиле в прыжке.

Единственная правка: если динозавр в прыжке, ближайшее препятствие —
PTERODACTYL с oy >= 95 и препятствие, через которое начат прыжок, уже
пройдено (removed), выбирать DROP — штатное ускоренное приземление,
как для CACTUS_LARGE в rule_v2/rule_v3. Остальная логика rule_v3 не тронута.

Физика игры не меняется. rule_v3.py, rule_v1.py и таблицы не тронуты.
"""

from rule_v2 import DROP, LOOK_DIST
from rule_v3 import B, K, MIN_THRESHOLD, RuleV3

NAME = "rule_v4"

# Версия для встраивания в Runner.update(): те же поля, что в rule_v2.RULE_V2_JS.
# Единственная ветка сверх правил v3:
#   if (s.jumping && s.type === 'PTERODACTYL' && s.oy >= 95 &&
#       state.jumpObs && state.jumpObs.remove) {
#     state.jumpObs = null;
#     return DROP;
#   }


class RuleV4(RuleV3):
    """Python-зеркало RULE_V4_JS. Эталон поведения — JS, не этот файл.

    JS хранит ссылку на препятствие, через которое начат прыжок, и проверяет
    remove у него. fast_env отдаёт это состояние полем `jumped_removed`;
    физика не меняется. Логика ниже повторяет JS-правило целиком, включая
    ветку DROP из rule_v3 (nextLarge).
    """

    def choose_action(self, s):
        threshold = max(MIN_THRESHOLD, K * s["speed"] + B)
        if s["type"] == "PTERODACTYL":
            if 60 <= s["oy"] <= 90 and s["dist"] <= 260:
                action = 2
            elif s["oy"] >= 95 and s["dist"] <= threshold + 25:
                action = 1
            else:
                action = 0
        elif s["dist"] <= threshold and not s["jumping"]:
            action = 1
        else:
            action = 0
        if s["jumping"] and action == 1:
            action = 0

        has_jump_obs = self.jump_oid is not None
        if action == 1 and not s["jumping"] and not s["ducking"]:
            self.jump_oid = s.get("oid")
        removed = has_jump_obs and bool(s.get("jumped_removed"))

        next_large = ((s["type"] == "CACTUS_LARGE" and s["dist"] <= LOOK_DIST)
                      or (s.get("type2") == "CACTUS_LARGE"
                          and s.get("dist2", 1000) <= LOOK_DIST))
        if s["jumping"] and removed and next_large:
            self.jump_oid = None
            return DROP
        if (s["jumping"] and s["type"] == "PTERODACTYL"
                and s["oy"] >= 95 and removed):
            self.jump_oid = None
            return DROP
        return action


RULE = {"k": 17.0, "b": 0.0, "look_dist": 800.0,
        "frame_skip": 1, "name": NAME}

# Единственный источник in-page логики rule_v4: используется parity_v4.py и
# watch.py. Поля snapshot: type, oy, dist, type2, dist2, speed, jumping,
# ducking. state.jumpObs — ссылка на препятствие, через которое начат прыжок.
# Логика идентична Python-правилу выше; физика не затрагивается.
RULE_V4_JS = r"""
function ruleV4(s, state, obs) {
  const th = Math.max(25.0, 17.0 * s.speed + 0.0);
  let a = 0;
  if (s.type === 'PTERODACTYL') {
    if (s.oy >= 60 && s.oy <= 90 && s.dist <= 260) a = 2;
    else if (s.oy >= 95 && s.dist <= th + 25) a = 1;
  } else if (s.dist <= th && !s.jumping) {
    a = 1;
  }
  if (s.jumping && a === 1) a = 0;
  if (a === 1 && !s.jumping && !s.ducking) state.jumpObs = obs || null;
  const nextLarge = (s.type === 'CACTUS_LARGE' && s.dist <= 800.0) ||
                    (s.type2 === 'CACTUS_LARGE' && s.dist2 <= 800.0);
  if (s.jumping && state.jumpObs && state.jumpObs.remove && nextLarge) {
    state.jumpObs = null;
    return 3;
  }
  if (s.jumping && s.type === 'PTERODACTYL' && s.oy >= 95
      && state.jumpObs && state.jumpObs.remove) {
    state.jumpObs = null;
    return 3;
  }
  return a;
}
"""
