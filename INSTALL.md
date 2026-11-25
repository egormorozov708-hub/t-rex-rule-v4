# Установка

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Требуется системный Google Chrome: оба режима (`fast_env.py`, `watch.py`)
запускают его через `channel="chrome"`, fallback на bundled Chromium нет.

Проверка установки (одна игра, 3000 кадров, ожидаемый результат `22495.5`):

```bash
python parity_v4.py --js-only --cap 3000 --seeds 792000
```

Игра загружается с `https://wayou.github.io/t-rex-runner/`, нужен доступ в интернет.
Локальные исходники игры в репозиторий не включены.
