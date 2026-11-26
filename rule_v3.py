"""Финальное правило: rule_v2 + b=0 (ранний прыжок на низкой скорости).

Обоснование:
    jitter_deaths_v1.csv (200 игр, реальные интервалы rAF, seed 96000–96199):
        b=20 -> 26 смертей, все speed<10, CACTUS_LARGE width=75 size=3 в прыжке;
        b=10 -> 1 смерть; b=0 -> 0 смертей.
    ab2_b0.csv / ab2_b10.csv / ab2_b20.csv (seed 80000–80029, speed 13, лимит 10000):
        rule_v2 + drop: 30/30 до лимита при b=0, 10 и 20.
    rule_v3_final20k.csv (seed 91000–91029, лимит 20000):
        rule_v1(b=20): 27/30 до лимита; rule_v3(b=0): 30/30.

Физика игры не меняется. rule_v1.py не тронут.
"""

from rule_v2 import DROP, LOOK_DIST, RuleV2
from rule_v1 import K, MIN_THRESHOLD

NAME = "rule_v3"
B = 0.0

RULE_V3_JS = """
const th = Math.max(25.0, K * s.speed + 0.0);
"""


class RuleV3(RuleV2):
    def __init__(self):
        super().__init__()
        self.jump_oid = None

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

        if action == 1 and not s["jumping"] and not s["ducking"]:
            self.jump_oid = s.get("oid")
        next_large = ((s["type"] == "CACTUS_LARGE" and s["dist"] <= LOOK_DIST)
                      or (s.get("type2") == "CACTUS_LARGE"
                          and s.get("dist2", 1000) <= LOOK_DIST))
        if (s["jumping"] and self.jump_oid is not None
                and s.get("removed") and next_large):
            self.jump_oid = None
            return DROP
        return action


RULE = {"k": K, "b": B, "look_dist": LOOK_DIST,
        "frame_skip": 1, "name": NAME}
