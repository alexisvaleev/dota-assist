# Dota Assist

Личный оверлей для Ranked All Pick: рекомендации пиков по фазам драфта
+ предметы в игре. Read-only: скриншоты экрана + официальный GSI.
Никакого чтения памяти, инъекций или модификации игры.

## Установка (Windows)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json   :: вписать stratz_token / account_id
python scripts\setup.py
```

`setup.py`: кладёт GSI-cfg в папку Dota, качает `data/*.json` в
`%APPDATA%\DotaAssist\data` и извлекает иконки из VPK туда же.
`config.json` не коммитится (в .gitignore), в exe не зашивается.

**Вручную:**

1. `-gamestateintegration` в параметры запуска Dota.
2. **Borderless Windowed** — в exclusive fullscreen оверлей не виден.
3. **Калибровка** `app/calibration.json`: на открытом экране драфта
   `python scripts\screenshot_for_calib.py` → по `draft_screen.png`
   замерить слоты `[x,y,w,h]` (team_left, team_right, bans),
   выставить `monitor` и `resolution`.
4. Иконки: если авто-экстракция не сработала — `Source2Viewer-CLI`
   (ValveResourceFormat), путь в `config.json -> vrf_cli`,
   затем `python scripts\extract_icons.py`.

## Запуск

```bat
python app\main.py
```

- До матча — заглушка. В драфте — фаза, враги, баны, топ пиков с
  разбивкой (контр/синергия/пул/мета). В игре — предметы.
- **Ctrl+Shift+D** — переключить click-through ⇄ интерактивный режим
  (кнопки Radiant/Dire и позиции 1–5, перетаскивание).

## Как считается

- Фаза 1 (до раскрытия) — чистая мета + личный пул.
- Фазы 2–3 — + матчапы против раскрытых врагов (сжатие по числу игр:
  4 победы из 4 ≠ +50), вес выше против вероятного лайн-оппонента
  (по positions.json), плюс синергия с союзниками.
- Кандидаты фильтруются по позиции (если выбрана и есть данные),
  забаненные и уже пикнутые исключаются.
- Предметы: тайминги OpenDota (секунды→окно [−5м, +10м]) + ситуативные
  правила `data/items.json`; купленное исключается, дорогое помечается.
- При плохом распознавании оверлей показывает предупреждение, а не
  делает вид, что всё точно.

## Данные

- Основной источник — **OpenDota** (без ключа). **STRATZ** — опционально:
  точнее матчапы и синергии с разбивкой по брекету (`stratz_token`).
- Кэш — `%APPDATA%\DotaAssist\data` (в dev — `data/` репо). Пишется
  атомарно; при сбое API остаётся старый кэш.
- `account_id` в конфиге → личная статистика героев (бонус «своего пула»).
- Иконки героев — ассеты Valve, живут только в `%APPDATA%` и не
  распространяются.

## Spike перед обкаткой (Windows)

1. `python scripts\gsi_dump.py` — пишет GSI-пакеты в `gsi_dumps/`;
   проверить, что приходит во время рейтингового драфта.
2. `python scripts\test_recognizer.py draft_screen.png -v` — точность
   CV на реальном скриншоте.
3. Заполнить `docs/findings.md`.

## Тесты

```bat
.venv\Scripts\python -m unittest discover -s tests -v
```

## Сборка .exe

```bat
pip install pyinstaller
python scripts\build.py        :: dist\DotaAssist.exe
python scripts\build_release.py :: + Inno Setup установщик
```

После установки запусти `python scripts\first_run.py` — скачает данные
и иконки в `%APPDATA%`.

## Ограничения

- Портрет не распознан (новая аркана) — слот «?» и пониженный confidence.
  Перезапусти `extract_icons.py` после патчей.
- CV ломается от смены разрешения/масштаба UI — перекалибруй.
- Имена героев в оверлее — английские (`localized_name` из OpenDota).
