"""Замороженное эталонное правило A (шаг 1 нового плана).

Не обучается и не меняется в ходеExperiments. Параметры подобраны на
детерминированном быстром режиме:
    k = 17, b = 20, frame_skip = 1, cap = 50000
    медиана 50000 кадров, 27/30 обрезаны, худшая игра 29602.

Логика:
    PTERODACTYL yPos 100 -> прыжок, 75 -> присед, 50 -> бежать;
    остальные препятствия: прыжок при dist <= k*speed + b.
    currentSpeed — число px/кадр.
"""

K = 17.0
B = 20.0
FRAME_SKIP = 1
MIN_THRESHOLD = 25.0

# Птица: range yPos (включительно) -> действие.
BIRD_JUMP_MIN_Y = 95
BIRD_DUCK_Y = (60, 90)
BIRD_DUCK_DIST = 260
BIRD_JUMP_EXTRA = 25


def choose_action(s):
    """0=бежать, 1=прыжок, 2=присед. s — snapshot из fast_env.SNAP."""
    threshold = max(MIN_THRESHOLD, K * s["speed"] + B)
    if s["type"] == "PTERODACTYL":
        if BIRD_DUCK_Y[0] <= s["oy"] <= BIRD_DUCK_Y[1] and s["dist"] <= BIRD_DUCK_DIST:
            return 2
        if s["oy"] >= BIRD_JUMP_MIN_Y and s["dist"] <= threshold + BIRD_JUMP_EXTRA:
            return 1
        return 0
    if s["dist"] <= threshold and not s["jumping"]:
        return 1
    return 0


RULE = {
    "k": K,
    "b": B,
    "frame_skip": FRAME_SKIP,
    "name": "rule_v1",
}
