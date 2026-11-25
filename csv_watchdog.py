"""Внешний сторож: убивает прогон, если CSV не растёт 5 минут.

Отдельный процесс, не имеет отношения к игровой логике и физике.
Запуск:
    python csv_watchdog.py --csv results/run.csv --pid 12345

Наблюдает за размером и mtime файла. Если оба не меняются дольше
--seconds (по умолчанию 300 с), завершает процесс --pid и всех его детей.
"""

import argparse
import os
import subprocess
import sys
import time


def kill(pid):
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"WATCHDOG taskkill failed for pid {pid}: "
                  f"{(r.stderr or r.stdout).strip() or 'unknown error'}",
                  file=sys.stderr, flush=True)
    else:
        os.kill(pid, 15)


def alive(pid):
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"WATCHDOG tasklist failed: "
                  f"{(r.stderr or r.stdout).strip() or 'unknown error'}",
                  file=sys.stderr, flush=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--seconds", type=float, default=300.0)
    ap.add_argument("--interval", type=float, default=10.0)
    a = ap.parse_args()

    last_size, last_mtime = -1, -1.0
    last_change = time.time()
    print("WATCHDOG start", a.csv, "pid", a.pid,
          "stale", int(a.seconds), "s", flush=True)
    while True:
        try:
            st = os.stat(a.csv)
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size, mtime = -1, -1.0
        if (size, mtime) != (last_size, last_mtime):
            last_size, last_mtime = size, mtime
            last_change = time.time()
        if not alive(a.pid):
            print("WATCHDOG target gone, exit", flush=True)
            return 0
        stale = time.time() - last_change
        if stale >= a.seconds:
            print("WATCHDOG CSV STALE", round(stale), "s: kill", a.pid,
                  flush=True)
            kill(a.pid)
            return 2
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
