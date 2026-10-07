# Dota Assist

[![ci](https://github.com/alexisvaleev/dota-assist/actions/workflows/ci.yml/badge.svg)](https://github.com/alexisvaleev/dota-assist/actions/workflows/ci.yml)
[![release](https://github.com/alexisvaleev/dota-assist/actions/workflows/release.yml/badge.svg)](https://github.com/alexisvaleev/dota-assist/actions/workflows/release.yml)

Личный оверлей для **Dota 2 Ranked All Pick**: подсказывает пики по фазам
драфта и предметы в игре. Read-only: скриншоты экрана (CV) + официальный
Game State Integration. Никакого чтения памяти, инъекций или модификации
игры.

## Что делает

- **Драфт**: фаза раунда, раскрытые враги и баны, топ-5 кандидатов с
  разбивкой «почему» (мета / контрпик / синергия / твой пул).
- **Игра**: предметы по таймингам OpenDota + ситуативные правила;
  купленное исключается, недоступное помечается.
- **Оверлей**: полупрозрачный, всегда поверх, click-through по умолчанию.
  `Ctrl+Shift+D` — интерактивный режим (сторона, позиция 1–5, drag).

## Установка (plug&play)

1. Скачай **`DotaAssist-Setup.exe`** из
   [Releases](https://github.com/alexisvaleev/dota-assist/releases) →
   установи → запусти.
2. Первый старт сам качает данные и иконки в `%APPDATA%\DotaAssist`
   (~5–10 мин, один раз).
3. В Dota: параметры запуска `-gamestateintegration`, режим окна
   **Borderless Windowed** (в exclusive fullscreen оверлей не виден).
4. Один раз откалибруй слоты драфта (см. ниже).

### Калибровка

Слоты портретов — это прямоугольники `[x,y,w,h]` в
`app\calibration.json` рядом с exe (переопределяет встроенную) или в
`%APPDATA%\DotaAssist\app\calibration.json`:

```bat
:: на открытом экране драфта (лобби/демо):
python scripts\screenshot_for_calib.py   :: -> draft_screen.png
:: в Paint замерь 5 слотов каждой команды + ряд банов,
:: впиши в calibration.json, выстави monitor и resolution
python scripts\test_recognizer.py draft_screen.png -v  :: проверка точности
```

Координаты масштабируются автоматически при другом разрешении.

## Как считаются рекомендации

- **Фаза 1** (до раскрытия врагов) — мета патча + твой личный пул.
- **Фазы 2–3** — матчапы против раскрытых врагов со сжатием по числу игр
  (4 победы из 4 ≠ +50), вес выше против вероятного лайн-оппонента,
  плюс синергия с союзниками.
- Фильтры: позиция (кнопки 1–5), баны, уже пикнутые.
- При низкой уверенности CV показывается предупреждение — тул не делает
  вид, что всё точно.

## Данные

- **OpenDota** — основной источник (без ключа). **STRATZ** — опционально
  (точнее матчапы/синергии по брекету; `stratz_token` в `config.json`).
- Кэш — `%APPDATA%\DotaAssist\data`, пишется атомарно: при сбое API
  остаётся предыдущий рабочий набор.
- `account_id` → личная статистика героев (бонус «своего пула»).
- Иконки героев — ассеты Valve; качаются со Steam CDN локально, в
  релиз/репозиторий не входят.

## Для разработки

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
python scripts\setup.py        :: GSI-cfg + данные + иконки
python app\main.py
```

Тесты: `.venv\Scripts\python -m unittest discover -s tests -v`

Релиз: `git tag v0.x.y && git push --tags` — CI соберёт exe + установщик.

| Папка | Содержимое |
|---|---|
| `app/engine/` | чистое ядро: DraftState, скоринг, предметы (без Qt/CV) |
| `app/` | `gsi_server` (Flask), `draft_watcher` (mss), `recognizer` (OpenCV), `overlay` (PyQt6), `bootstrap` (автозагрузка данных) |
| `scripts/` | dev-обёртки: fetch_data, fetch_icons_cdn, extract_icons, gsi_dump, setup, build |
| `docs/findings.md` | чеклист spike-проверок на Windows |

## Spike перед обкаткой

1. `python scripts\gsi_dump.py` — что реально приходит в GSI на драфте.
2. `test_recognizer.py` на скриншоте — точность CV.
3. Заполнить `docs/findings.md`.

## Ограничения

- Портрет не распознан (новая аркана/персона) → слот «?» и предупреждение.
- CV ломается от смены разрешения/масштаба UI — перекалибруй.
- Имена героев — английские (`localized_name` из OpenDota).
- Тул избегает известных инвазивных техник, но гарантий от Valve нет.

## Лицензия

MIT. Не для коммерческого использования — личный инструмент.
