# Dota Assist

Личный оверлей: контрпики в драфте + рекомендации предметов в игре.
Read-only: скриншоты экрана + официальный GSI. Никакого чтения памяти игры.

## Установка (Windows)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Подготовка (один раз)

```bat
copy config.example.json config.json   :: вписать stratz_token
python scripts\setup.py
```

`setup.py` делает сам: кладёт GSI-cfg в папку Dota (путь из `dota_path`
в конфиге), тянет `heroes/meta/matchups/builds.json` из OpenDota+STRATZ
и пробует извлечь иконки из VPK.

**Доработать вручную:**

1. `-gamestateintegration` в параметры запуска Dota.
2. Иконки: если авто-экстракция не сработала — скачать
   `Source2Viewer-CLI` (ValveResourceFormat), прописать `vrf_cli` в
   `config.json` и `python scripts\extract_icons.py`.
3. **Калибровка**: на открытом экране драфта (лобби/демо) запустить
   `python scripts\screenshot_for_calib.py` → по `draft_screen.png`
   замерить слоты и вписать в `app/calibration.json` (`[x,y,w,h]`).
4. **Иконки ролей**: 5 PNG (carry/mid/offlane/soft_support/hard_support)
   в `data/icons/roles/` — вырезать из того же скриншота.

`config.json` **не коммитить** — токен внутри, файл в .gitignore.

## Запуск

```bat
python app\main.py
```

## Проверка точности распознавания

```bat
python scripts\test_recognizer.py draft_screen.png --verbose
```
Показывает героя и скор по каждому слоту + топ-5 кандидатов.

## Сборка .exe (Windows)

```bat
pip install pyinstaller
python scripts\build.py
```
→ `dist/DotaAssist.exe`. **Не публикуй бинарь** — внутри твой STRATZ токен.

До входа в матч окно показывает заглушку; на драфте — пики и топ-3,
в игре — предметы. Окно click-through: клики проходят сквозь него.

## Как это работает

- **Драфт AP**: GSI даёт только твою сторону (`team_name`); пики врагов
  распознаются CV по координатам слотов из `calibration.json`.
- **CM/лобби**: драфт приходит целиком через GSI — CV не нужна.
- **В игре**: герой + составы команд из GSI → билд + ситуативные правила.

## Ограничения

- Если портрет не распознан (новая аркана) — слот показывается «?».
  Перезапусти `extract_icons.py` после патчей.
- Имена героев в оверлее — английские (`localized_name` из OpenDota).
- Неизвестные/пустые `calibration.json` координаты = CV не работает —
  сначала откалибруй.
