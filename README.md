# replai

[Русский](#-описание-и-документация-russian) | [English](#-description-and-documentation-english)

---

## 🇷🇺 Описание и документация (Russian)

**Terminal REPL for Gemini — project-aware code chat with file round-trip.**

`replai` — интерактивная оболочка для работы с Gemini из терминала. Знает
исходники проекта, принимает изображения/аудио/видео/архивы/файлы прямо из
чата, автоматически сохраняет любое медиа из ответов модели, умеет выгружать
результат работы обратно в реальный проект, и переживает падения через
`resume` + `sync`.

**Версия:** `0.0.2`. **Python:** `3.10+`.

### Зачем это нужно

Обычный AI-чат в браузере теряет контекст, если что-то сломалось, и не умеет
работать с реальными файлами проекта. `replai`:

- **читает ваш проект с диска** — модель видит структуру и содержимое файлов;
- **принимает новые файлы из чата** (`/send`) — картинки, архивы, код;
- **автосохраняет всё, что вернула модель** — если это медиа (картинка,
  видео, аудио), оно попадает в `media/` немедленно, чтобы вы не потеряли
  дорогой результат генерации;
- **даёт выгрузить результат** — `/save` для архива сессии, `/apply` для
  реального проекта, `/md` для Markdown-отчёта;
- **переживает сбои** — сессия продолжается после Ctrl+C, kill, обрыва SSH;
- **помнит сессии** — на выходе генерируется summary, при запуске показывается
  меню всех сессий с описаниями.

### Принципы дизайна

Эти четыре принципа объясняют многие решения в `replai` — понимание
сэкономит вам часы отладки.

1. **Состояние видимо и портативно.** Всё лежит в `./replai/` рядом со
   скриптом, без скрытых папок в `~/.config`. Скопировали папку — перенесли
   сессии. Удалили папку — удалили всё.

2. **Два разных «хранилища».** Локальные файлы (на диске, `local_path`) и
   облачные файлы (Gemini Files API, `files_api_uri`) — **это не одно и то
   же**. Облако — плоское пространство `files/<id>`, где файлы живут
   48 часов, и `display_name` — единственный способ отличить «наш» файл от
   чужого. Локальный файл — источник правды. `replai` синхронизирует их по
   SHA-256, а не по именам.

3. **`@name` — всегда облачная версия.** Самое важное правило (подробно
   ниже). Устраняет неоднозначность «какую версию файла имеет в виду
   пользователь».

4. **Ничего не теряется.** Медиа от модели автосохраняется на диск **до**
   того, как вы нажмёте что-либо. Модель не флудит медиа, но каждая картинка
   дорога и невоспроизводима (seed не сохраняется) — потеря недопустима.

---

### Установка

```bash
git clone https://github.com/vasiliypavlov/replai
cd replai
pip install -r requirements.txt
```

`replai.py` — один файл, сборка не нужна. Запуск: `python replai.py --help`.

`requirements.txt`:

```
google-genai>=1.0.0
pathspec>=0.12.0
prompt-toolkit>=3.0.0
```

- **`pathspec`** опционален — без него `.gitignore` не учитывается, остальное
  работает.
- **`prompt-toolkit`** рекомендован — включает многострочный ввод с
  `Shift+Enter`, историю `↑`/`↓` и мягкие переносы. Без него `replai`
  переходит в fallback: многострочный ввод через `\` в конце строки или
  блок `"""…"""`.

---

### Быстрый старт

1. Положите API-ключ в `api-key.txt` рядом с `replai.py` (одна строка, только
   сам ключ). Либо `--api-key PATH`, либо `export GEMINI_API_KEY=...`.
2. Запустите: `python replai.py --project ./my_project`
3. Работайте — примеры команд в разделе **Команды REPL** ниже.

---

### Ввод текста

`replai` поддерживает **многострочный ввод** — удобно для длинных промптов,
вставки кода, пошаговых инструкций.

| Действие | Клавиши |
|---|---|
| Отправить сообщение | `Enter` |
| Перенос строки (современные терминалы) | `Shift+Enter` |
| Перенос строки (универсальный) | `Alt+Enter` или `Esc`, затем `Enter` |
| Перенос строки (LF) | `Ctrl+J` |
| Вставка из буфера | `Ctrl+V` (сохраняет отступы и переносы) |
| История запросов | `↑` / `↓` |
| Очистить буфер | `Ctrl+C` (при непустом вводе) |
| Выйти из сессии | `Ctrl+D` или `exit` / `quit` / `/exit` |

При переносе строки появляется визуальный маркер продолжения `... `.

**Почему `Shift+Enter`, а не «Enter → новая строка»:** обычный `Enter` —
самое частое действие (отправить), его нельзя менять. `Shift+Enter` —
привычный для чатов и IDE перенос, но требует поддержки терминала. Если
терминал не передаёт `Shift+Enter` как отдельное событие (старый `cmd.exe`,
простые SSH-клиенты), работает `Alt+Enter` или `Esc+Enter` — эти комбинации
понимает любой терминал.

**Fallback без `prompt-toolkit`:** многострочный ввод через `\` в конце
строки или блок `"""…"""`:

```
Вы: Напиши функцию, которая \
... принимает список чисел и \
... возвращает их сумму
```

---

### Ключевые концепции

#### Сессия = чистый timestamp

`session_id` — это `YYYYMMDD_HHMMSS` (например, `20261107_150453`). **Без
префикса.** Это имя директории в `replai/sessions/`.

**Префикс `replai_` есть только в `display_name`** — метке в Files API.
В имени папки, в аргументах команд, в баннере — чистый timestamp.

`Manifest.new` отказывается принимать `session_id` не по формату
`^\d{8}_\d{6}$`, а `make_display_name` терпит любое число префиксов на входе,
но всегда создаёт ровно один на выходе.

#### Локальный файл vs облачный файл

- **Локальный** — на вашем диске, `local_path`. Источник правды.
- **Облачный** — в Files API, `files_api_uri`. Живёт 48 часов. Это
  **копия**, сделанная для отправки модели.

`replai` использует **SHA-256, а не имена**, чтобы понять, совпадают ли
версии. Переименование файла на диске — не проблема. Изменение содержимого —
ловится автоматически (`out-of-sync`). Если в хранилище нет копии
(`new-local`) или копия устарела (`out-of-sync`), `replai` предложит
перезалить.

`display_name` в облаке = `replai_<session_id>_<путь>`. Служит для двух
целей: (1) отличить наши файлы от чужих в общем хранилище GCP-проекта,
(2) при поиске нормализоваться обратно до чистого пути `<путь>`.

#### `@name` — всегда облачная версия (важнейшее правило)

Это правило решает проблему неоднозначности: **какую именно версию файла
имеет в виду пользователь, когда пишет `@name`?** Ответ: ту, что лежит в
хранилище на момент отправки.

Разберём на примере:

- В хранилище `test_report.md` содержит «Мама ходит на работу» (старая).
- Локально (новый) `test_report.md` содержит «Мама мыла раму».

| Что вы пишете | Что видит модель |
|---|---|
| `/send "test_report.md" что в файле test_report.md` | **только** локальную («мыла раму») |
| `/send "test_report.md" что в @test_report.md` | **обе**: локальную + облачную («мыла раму» + «ходит на работу») |
| `что в @test_report.md` (без /send) | **только** облачную («ходит на работу») |

**Почему так:** `@` — явный маркер «версия из хранилища». Без `@` имя в
тексте — просто слово. `/send "path"` — явная команда «приложить свежую
локальную версию прямо сейчас».

Если облачная копия отсутствует или истекла (48 ч), `replai` предложит её
перезалить с диска — **одно нажатие Enter**. Пользователю не нужно думать о
48-часовом лимите.

Если облачного файла нет вообще и перезалить нечем (нет локальной копии):
предупреждение + `[Y/n]` — отправить сообщение всё равно (например,
`@Image1` в промпте для WAN — это не файл, а часть текста). `Enter` =
отправить как есть.

#### Медиа автосохраняется всегда

Как только модель возвращает изображение/видео/аудио в ответе, оно
**немедленно** пишется в
`replai/sessions/<id>/media/<timestamp>_turnNNN_MMM.<ext>`. Это **не**
`/save` — `/save` по запросу пользователя. Это страховка от потери:
сгенерированные картинки невоспроизводимы (seed потерян).

Каждое сохранение сопровождается строкой `[MEDIA]` в `log.txt` с тем же
timestamp и номером хода, что в имени файла — можно найти «к какому ответу
относится этот файл» простым `grep`.

Автосохранённое медиа сразу появляется в `/list` (с `src=gen`), доступно
для `/focus`, `/save`, `@`.

#### Три «выхода» из сессии

- **`/save`** — архив сессии (`saved/<path>`). Для истории, резервных
  копий, сравнения версий через `[o/k/s]` при совпадении имени.
- **`/apply`** — выгрузка в реальный проект. Куда указали — туда и
  скопировалось. По умолчанию — в `--project`.
- **`/md`** — Markdown-отчёт из последнего ответа.

Три разных адресата — три разные команды. `/save` не трогает проект, `/apply`
не трогает архив, `/md` не трогает ни то, ни другое.

---

### API-ключ

Приоритет источников:

| Порядок | Источник |
|---|---|
| 1 | `--api-key PATH` |
| 2 | `api-key.txt` рядом со скриптом |
| 3 | `GEMINI_API_KEY` (env) |
| 4 | `GOOGLE_API_KEY` (env, legacy) |

Ключ **никогда не принимается inline** (`--api-key sk-abc` → ошибка
«файл не найден»). При чтении файла проверяются права: если файл доступен
группе/остальным (`mode & 0o077`) — предупреждение `chmod 600`.

**Почему так:** ключ в `ps aux` и `~/.bash_history` — утечка навсегда.
Только файл с ограниченными правами или переменная окружения.

---

### Язык интерфейса

`ru` (по умолчанию) и `en`. Переключается через `--lang` или
`REPLAI_LANG=en replai`. Локализовано всё: справка, меню, баннер, команды,
промпты к модели, ошибки, summary.

---

### Меню сессий при запуске

При запуске **без** `--resume`, `--new`, `--sync` в TTY `replai` показывает
**меню всех сессий** с датой, количеством ходов/файлов, проектом и summary.

Пункт `0` или `Enter` — новая сессия. Ввод номера или полного `session_id` —
загрузка конкретной.

**`--project PATH`** фильтрует меню: показываются только сессии с этим
проектом (`os.path.normcase(abspath())`).

**`--resume` без ID** — то же меню, но без пункта «новая» (Enter — отмена).

Меню **не показывается** при: `--new` (сразу новая), `--sync` (batch),
`--resume <id>` (прямая загрузка), `--continue` (последняя), не-TTY (pipe,
CI).

---

### Summary сессии на выходе

При выходе (`exit`, `quit`, `/exit`, `Ctrl+D`) `replai` **генерирует одно
короткое предложение** (до 100 символов) — суть работы в сессии — и
сохраняет в `manifest.json` (`summary`, `summary_at`).

**Зачем:** пользователь возвращается через день и хочет понять «что было в
той сессии» — без чтения лога. Summary видно в меню, `/session`, баннере.

**Что НЕ происходит:** не пишется в `history` (это метаданные), не сохраняет
медиа, не перегенерируется, если манифест не менялся, не блокирует выход при
ошибке.

**Отключить:** `--no-summary`.

**Не генерируется**, если: сессия пустая, Ctrl+C (прерывание — не выход),
последний ход — user без model (после rollback).

---

### CLI

#### Основные

| Опция | По умолчанию | Описание |
|---|---|---|
| `--api-key PATH` | — | Файл с API-ключом |
| `--model NAME` | `gemini-3.8-flash` | Модель Gemini |
| `--temperature F` | `0.2` | Температура |
| `--project PATH` | — | Файл / **папка** / `.zip` |
| `--state-dir PATH` | `replai` | Корень состояния |
| `--resume [ID]` | — | Продолжить (без ID — меню) |
| `--session [ID]` | — | Алиас `--resume` |
| `--continue` | off | Последняя сессия без меню |
| `--new` | off | Сразу новая, без меню |
| `--no-summary` | off | Без summary на выходе |
| `--lang {ru,en}` | `ru` | Язык |
| `--help` / `--version` | — | Справка / версия |

#### Синхронизация

| Опция | По умолчанию | Описание |
|---|---|---|
| `--sync` | off | Разовый проход по манифесту + выход |
| `--dry-run` | off | Показать без действий |
| `--sync-check {auto,warn,off}` | `auto` | Политика при использовании файла |

**Статусы файла** (`source != generated`):

| Локально | Хранилище | SHA-256 | Статус | `auto` |
|---|---|---|---|---|
| есть | есть | = | `ok` | ничего |
| есть | есть | ≠ | `out-of-sync` | спросить перезалить |
| есть | нет | — | `new-local` | спросить загрузить |
| нет | есть | — | `detached` | использовать URI |
| нет | нет | — | `lost` | ошибка |

`detached` **никогда** не предлагает «обновить» — нечего, локальной версии
нет. Это сценарий размонтированной папки или удалённого файла: используется
копия из хранилища.

Медиа `source=generated` всегда `ok` и **пропускается** в `--sync` — оно уже
на диске.

#### Ретраи

| Опция | По умолчанию |
|---|---|
| `--send-retries N` | `4` |
| `--send-retry-delay F` | `2.0` сек |

Backoff `2 → 4 → 8 → 16` сек. Триггеры по подстроке: `503`, `UNAVAILABLE`,
`429`, `RESOURCE_EXHAUSTED`, `Deadline Exceeded`, `timeout`, `high demand`,
`overloaded`. Остальное — пробрасывается без ретраев.

#### Лимиты `/send`

`--limit-image-mb` (20), `--limit-video-mb` (500), `--limit-text-kb` (200),
`--limit-archive-mb` (200), `--limit-inline-total-mb` (18),
`--limit-request-total-mb` (500).

При превышении — `[y/N]`. Флаг `-y`/`--yes` пропускает подтверждения (для CI).

**Правило доставки бинарных файлов:**
- `size <= --limit-inline-total-mb` → байты в запросе (`Part.from_bytes`);
- иначе → `client.files.upload` + `Part.from_uri`.

Порог 18 МБ (а не 20) — запас под остальной текст запроса, чтобы не упереться
в жёсткий лимит Gemini (20 МБ на весь запрос).

#### Сканирование проекта

`--project-max-file-bytes` (200 КБ), `--project-max-total-bytes` (2 МБ),
`--project-max-files` (200), `--project-follow-symlinks` (off),
`--project-include-ide-dirs` (off).

`.gitignore` учитывается (если `pathspec` установлен). Жёстко исключены:
`.git/`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `*.pyc`, `*.so`,
`*.log`, и т.п. Симлинки по умолчанию **не** разыменовываются; с
`--project-follow-symlinks` — с защитой от циклов.

**`--project` = папка** — используется напрямую (не копируется в сессию).
**`--project` = `.zip`** — распаковывается в `<session_dir>/project_extracted/`.

---

### Команды REPL

| Команда | Назначение |
|---|---|
| `/list` | Список файлов сессии |
| `/focus <pattern> [текст]` | Сфокусироваться на файле с инструкцией |
| `@<path>` в тексте | Упоминание облачной версии файла |
| `/send <path...> [--text X]` | Добавить новый файл(ы) в сессию и отправить |
| `/save [path]` | Сохранить код/медиа ответа в архив `saved/` |
| `/md <file>` | Сохранить весь ответ как Markdown |
| `/apply <src> [dst]` | Выгрузить файлы из `saved/` в проект |
| `/forget <pattern>` | Убрать запись из сессии (файл на диске не трогается) |
| `/session` | Информация о сессии |
| `/history` | История ходов (последние 15, с turn ID) |
| `/help` | Справка |
| `exit` / `quit` / `/exit` | Выход (генерирует summary) |

Все команды начинаются с `/`. Для многострочного ввода — см. «Ввод текста».

#### `/list` — список файлов сессии

Таблица: `#` (индекс для `#N`), тип, src (`in`/`gen`), статус (sync-статус
для input, `ok` для generated), размер, нормализованное имя.

`src=in` — из проекта или `/send`. `src=gen` — сгенерировано моделью.

#### `/focus <pattern> [текст]` — прицельная отправка файла

Отправить один файл модели с инструкцией. `pattern` — `#N` (индекс из
`/list`), точное имя, basename, glob, или `replai_<sid>_<path>`
(нормализуется).

Перед отправкой проверяется статус:

- `ok` → отправка;
- `out-of-sync` + `--sync-check auto` → спросит «обновить в хранилище?»;
- `warn` → только предупредит;
- `off` → молча отправит локальную;
- `detached` → использовать URI из хранилища;
- `lost` → ошибка.

**Зачем отдельно от `/send`:** `/focus` не добавляет новый файл — он
**возвращает внимание** к уже известному. Полезно для итеративной отладки
одного файла из большого датасета.

#### `@name` в тексте — упоминание облачной версии

Распознаётся в начале строки или после пробела/`(`/`[`/кавычки.
`user@example.com` не ломается. Trailing-пунктуация (`@main.py,`) отрезается.

**Что делает:** ищет файл в манифесте, проверяет `files_api_uri` и
`expires_at`, при необходимости предлагает перезалить. Вставляет
`[MENTION] <path> (версия из хранилища)` + содержимое из Files API.

**Отличие от `/send`:** `/send path` прикладывает **свежий локальный**
файл. `@name` в тексте — **облачную копию**. Это **разные файлы**, если
содержимое расходится. См. «Ключевые концепции».

#### `/send <path...> [--text X]` — добавить файл в сессию

Синтаксис:

```
/send "file.png" Привет
/send "a.png" "b.png" --text Сравни
/send "my file with spaces.png" test
```

Правила парсинга: если есть `--text` — всё до него пути, всё после — текст.
Иначе: токен в кавычках → путь; без кавычек существующий файл → путь; иначе
→ начало текста.

По типу: text инлайнится в промпт; archive распаковывается в память;
image/video/audio/binary — inline или Files API по размеру.

**Если в тексте есть `@name`** (например, `/send "test_report.md" что в
@test_report.md`) — обе версии уйдут модели с явными метками: `[FILE]`
(локальная, свежая) + `[MENTION]` (облачная, старая). Модель видит их как
**разные файлы** и не путает.

Если `@name` не найден в сессии/хранилище — предупреждение + `[Y/n]`. Enter
= отправить без упоминания (для промптов типа `@Image1` где `@` — часть
текста).

#### `/save [path]` — архив последнего ответа

**Без аргумента:** все блоки кода + все медиа из последнего ответа. Показ
плана, `[y/N]`.

**С аргументом:** сначала ищет в сессии (по имени, индексу, glob), затем в
блоках ответа. Найдено → `shutil.copy2` в `saved/<path>`.

**При совпадении имени:** `[o]` перезаписать / `[k]` новый с ID хода
(`main_t003.py`, старый цел) / `[s]` пропустить. Идентичное содержимое
пропускается молча (`⏭ Без изменений`).

**Куда:** `replai/sessions/<id>/saved/`. **Не** в проект, **не** в хранилище.

**Зачем:** архив в сессии. Для истории, для сравнения версий. Если нужно в
**проект** — используйте `/apply`.

#### `/apply <src> [dst]` — выгрузка в проект

**Направление:** `<session>/saved/` → `<dst>/`. Это **выход из сессии в
реальность**.

**`src`** — паттерн в сессии: имя, `<dir>/` (все файлы в папке), `#N`, glob.

**`dst`** — куда копировать. Если не указан — в `--project`:
- если `--project` = папка → в неё;
- если `--project` = `.zip` → в `<session>/project_extracted/`.

**Поведение:** показывает план (`new` / `CONFLICT`), спрашивает `[y/N]`.
При конфликте — `[y/N]` per file (обходится `--force`/`--yes`).

**`--dry-run`** — только план, без копирования.

**Зачем отдельно от `/save`:** `/save` = «хочу архив», `/apply` = «хочу в
рабочий проект». Разные адресаты — разные команды.

#### `/forget <pattern>` — убрать из сессии

Удаляет запись из `manifest.files()`. **Не** удаляет с диска
(`local_path`), **не** удаляет из Files API. Только убирает из контекста:
после `/forget` файл не находится в `/list`, `@`, `/focus`, `/save`.

Для `source=generated` — отдельное подтверждение (файл в `media/` остаётся).

**Зачем:** очистить сессию от лишних записей, не трогая реальные файлы.
Полезно в долгих сессиях и при исчерпании квоты 20 ГБ в Files API (убрать
запись → перезалить с локальной).

`--dry-run` — только показать.

#### `/md <file>` — Markdown-экспорт

Сохраняет `LAST_RESPONSE["text"]` в файл.

- Без явного пути (`/md report.md`) → `saved/report.md`.
- С явным путём (`/md ./out.md`, `/md ~/docs/x.md`, `/md C:\x.md`) → путь
  как есть, `~` раскрывается, вложенные папки создаются.

В выводе **абсолютный** путь и размер — пользователь видит, куда реально
ушёл файл.

#### `/session` — информация о сессии

ID, summary, дата, модель, проект, счётчики файлов/ходов/медиа, пути
манифеста/лога/saved/media, готовая строка `replai --resume <id>` для
копипаста.

#### `/history` — последние 15 ходов

С `[turn:N]` — номер хода, совпадает с `turnNNN` в именах медиафайлов и
`file_tNNN` при `/save` с `[k]`. Позволяет сопоставить артефакт с ходом.

#### `/help` — шпаргалка

#### `exit` / `quit` / `/exit` — выход

Три эквивалентных способа. Генерирует summary. Ctrl+D — тоже с summary.
Ctrl+C — прерывает операцию, не выходит.

---

### Структура состояния

```text
replai/
└── sessions/
    └── 20261107_142305/              ← session_id = YYYYMMDD_HHMMSS
        ├── manifest.json             ← атомарная запись, инкрементально
        ├── log.txt                   ← append, с [turn:NNN]
        ├── saved/                    ← /save и /md
        ├── media/                    ← автосохранение медиа
        └── project_extracted/        ← только для --project *.zip
```

Всё видимое, всё портативное.

---

### Устойчивость к сбоям

- **Ретраи 503/429** — экспоненциальный backoff.
- **Атомарная запись манифеста** через `.tmp` → `os.replace`.
- **Инкрементальная запись** после каждого действия.
- **Rollback хода при Ctrl+C** — orphan user-запись удаляется из `history`,
  чтобы summary и resume работали с консистентной историей.
- **Автоочистка устаревших `files_api_uri`** при изменении локального SHA
  (`add_file`) — старый URI не будет «фантомно» использован.
- **Предупреждение при text-fallback на URI** — если локальный файл
  недоступен, `replai` явно скажет, что использует версию из хранилища.

---

### Примеры

#### Отладка по одному файлу из большого датасета

```
/list
/focus "Five of Wands.jpg" Скрипт выдаёт красный фон вместо белого
```

#### Сравнение двух файлов в одном вопросе

```
Почему в @prepress/lift.py функция lift() для @Five\ of\ Wands.jpg
даёт красный фон, а для @Six\ of\ Wands.jpg — белый?
```

#### Генерация и сохранение изображения

```
Сгенерируй открытку с драконом в стиле industrial, 512x512
# [1 медиафайл автосохранён в media/]

/save
# Сохранит картинку в saved/
```

#### Синхронизация после правок

```bash
replai --project ./proj --sync --yes
```

#### Восстановление после падения

```bash
replai --resume                       # меню всех сессий
replai --resume 20261107_142305       # конкретная
replai --session 20261107_142305      # алиас
replai --continue                     # последняя
```

#### CI-режим (без интерактива)

```bash
replai --yes --project ./proj --sync
```

`--yes` автоматически:
- выбирает «новую сессию» в меню (или `Y` на авто-вопросах sync);
- подтверждает перезалив при `--sync`;
- подтверждает `[y/N]` при превышении лимитов в `/send`.

---

### Требования

- **Python 3.10+** (аннотации `X | None`, `tuple[list[str], str]`).
- **Google GenAI SDK** `google-genai>=1.0.0`.
- **pathspec** — опционально, для парсинга `.gitignore`.
- **prompt-toolkit** — рекомендовано, для многострочного ввода и истории.
- ОС: Linux, macOS, Windows.

---

### Roadmap

`v0.0.2` — текущая. Что осознанно **не** вошло:

- **Скачивание из Files API в `/save`.** Если модель вернула ссылку
  (`file_data`) вместо `inline_data` — упоминается как текст.
- **Батчинг загрузки** больших файлов в одном `/send`.
- **Стриминг ответа** (`stream=True`).
- **Кросс-сессионный поиск в `@`** — сейчас только текущая сессия.
- **Очистка `media/`** — файлы копятся, лимита нет.
- **`/apply` в `project_extracted/`** — сейчас копирует в `--project`, а не
  внутрь распакованного zip.
- **Persistent input history** (`FileHistory` in `saved/.history`) — сейчас
  `InMemoryHistory`, `↑`/`↓` работает только внутри одной сессии.
- **Cross-terminal Shift+Enter reliability** — зависит от протокола
  терминала (Kitty / `modifyOtherKeys=2` / `CSI-u`); fallback `Alt+Enter` /
  `Ctrl+J` универсален.

---

## 🇬🇧 Description and Documentation (English)

**Terminal REPL for Gemini — project-aware code chat with file round-trip.**

`replai` is a terminal shell for Gemini. It reads project sources, accepts
images/audio/video/archives/files directly from the chat, auto-saves any media
the model generates, lets you export results back to a real project, and
survives crashes via `resume` + `sync`.

**Version:** `0.0.2`. **Python:** `3.10+`.

### Why this exists

A regular AI chat in a browser loses context when something breaks and cannot
touch real project files. `replai`:

- **reads your project from disk** — the model sees structure and file contents;
- **accepts new files from the chat** (`/send`) — images, archives, code;
- **auto-saves everything the model returns** — media (image/video/audio) lands
  in `media/` immediately, so expensive generation is not lost;
- **lets you export** — `/save` for a session archive, `/apply` for the real
  project, `/md` for a Markdown report;
- **survives failures** — session continues after Ctrl+C, kill, SSH disconnect;
- **remembers sessions** — a summary is generated on exit, and a session menu
  with descriptions appears on the next launch.

### Design principles

Four principles explain many decisions in `replai` — understanding them saves
hours of debugging.

1. **State is visible and portable.** Everything lives in `./replai/` next to
   the script. No hidden folders in `~/.config`. Copy the folder — move
   sessions. Delete the folder — delete everything.

2. **Two different "storages".** Local files (on disk, `local_path`) and cloud
   files (Gemini Files API, `files_api_uri`) are **not the same**. Cloud is a
   flat space `files/<id>` where files live 48 hours, and `display_name` is
   the only way to tell "our" file from a foreign one. Local file is the
   source of truth. `replai` syncs them by SHA-256, not by names.

3. **`@name` is always the cloud version.** The most important rule (see
   below). It removes ambiguity about "which version the user means".

4. **Nothing is lost.** Model media is auto-saved to disk **before** you click
   anything. The model does not spam media, but each image is expensive and
   non-reproducible (seed is not preserved) — loss is unacceptable.

---

### Installation

```bash
git clone https://github.com/vasiliypavlov/replai
cd replai
pip install -r requirements.txt
```

`replai.py` is a single file, no build step. Run: `python replai.py --help`.

`requirements.txt`:

```
google-genai>=1.0.0
pathspec>=0.12.0
prompt-toolkit>=3.0.0
```

- **`pathspec`** is optional — without it `.gitignore` is not honored,
  everything else works.
- **`prompt-toolkit`** is recommended — enables multiline input with
  `Shift+Enter`, history `↑`/`↓`, and soft line breaks. Without it, `replai`
  falls back to `\`-continuation or `"""…"""` blocks.

---

### Quick start

1. Put the API key in `api-key.txt` next to `replai.py` (single line, key only).
   Or `--api-key PATH`, or `export GEMINI_API_KEY=...`.
2. Run: `python replai.py --project ./my_project`
3. Work — see **REPL commands** below.

---

### Text input

`replai` supports **multiline input** — useful for long prompts, code
snippets, and step-by-step instructions.

| Action | Keys |
|---|---|
| Send message | `Enter` |
| Soft line break (modern terminals) | `Shift+Enter` |
| Soft line break (universal fallback) | `Alt+Enter` or `Esc` then `Enter` |
| Soft line break (LF) | `Ctrl+J` |
| Paste from clipboard | `Ctrl+V` (preserves indentation and line breaks) |
| Request history | `↑` / `↓` |
| Clear buffer | `Ctrl+C` (while typing) |
| Exit session | `Ctrl+D` or `exit` / `quit` / `/exit` |

On line break, a continuation marker `... ` appears.

**Why `Shift+Enter` and not "just Enter → newline":** plain `Enter` is the
most frequent action (send message) and cannot be remapped. `Shift+Enter` is
the familiar soft break in chats and IDEs, but it requires terminal support.
If the terminal does not emit `Shift+Enter` as a distinct event (old
`cmd.exe`, simple SSH clients), `Alt+Enter` or `Esc+Enter` work — these are
understood by any terminal.

**Fallback without `prompt-toolkit`:** multiline input via trailing `\` or
`"""…"""` blocks:

```
You: Write a function that \
... takes a list of numbers and \
... returns their sum
```

---

### Key concepts

#### Session = pure timestamp

`session_id` is `YYYYMMDD_HHMMSS` (e.g. `20261107_150453`). **No prefix.**
This is the directory name inside `replai/sessions/`.

**The `replai_` prefix exists only in `display_name`** — a label in Files API.
In folder name, command arguments, banner — clean timestamp.

`Manifest.new` rejects `session_id` not matching `^\d{8}_\d{6}$`, and
`make_display_name` tolerates any number of prefixes on input but always
produces exactly one on output.

#### Local file vs cloud file

- **Local** — on your disk, `local_path`. Source of truth.
- **Cloud** — in Files API, `files_api_uri`. Lives 48 hours. A **copy** made
  for sending to the model.

`replai` uses **SHA-256, not names**, to determine if versions match. Renaming
a local file is a non-issue. Content change is detected automatically
(`out-of-sync`). If storage has no copy (`new-local`) or the copy is stale
(`out-of-sync`), `replai` offers to re-upload.

`display_name` in cloud = `replai_<session_id>_<path>`. Serves two purposes:
(1) distinguish our files from foreign ones in a shared GCP project,
(2) on search, normalize back to the clean `<path>`.

#### `@name` is always the cloud version (most important rule)

This rule solves the ambiguity: **which version of the file does the user mean
when writing `@name`?** Answer: the one in storage at the moment of sending.

Example:

- In storage, `test_report.md` contains "Mom goes to work" (old).
- Locally, `test_report.md` contains "Mom washed the frame" (new).

| What you type | What the model sees |
|---|---|
| `/send "test_report.md" what is in file test_report.md` | **only** local ("washed the frame") |
| `/send "test_report.md" what is in @test_report.md` | **both**: local + cloud ("washed the frame" + "goes to work") |
| `what is in @test_report.md` (no /send) | **only** cloud ("goes to work") |

**Why:** `@` is an explicit marker of "storage version". Without `@`, the name
in text is just a word. `/send "path"` is an explicit command "attach the fresh
local version right now".

If the cloud copy is missing or expired (48h), `replai` offers to re-upload it
from disk — **one Enter**, fully transparent. The user does not need to think
about the 48-hour limit.

**What if the cloud file does not exist at all and there is nothing to
re-upload from** (no local copy either): warning + `[Y/n]` — send anyway (e.g.
`@Image1` in a WAN prompt is text, not a file). `Enter` = send as is.

#### Media is always auto-saved

The moment the model returns an image/video/audio in its response, it is
**immediately** written to
`replai/sessions/<id>/media/<timestamp>_turnNNN_MMM.<ext>`. This is **not**
`/save` — `/save` is on user request. This is a safety net: generated images
are non-reproducible (seed is lost).

Every save is accompanied by a `[MEDIA]` line in `log.txt` with the same
timestamp and turn number as in the filename — you can find "which response
this file belongs to" with a simple `grep`.

Auto-saved media immediately appears in `/list` (with `src=gen`), available
for `/focus`, `/save`, `@`.

#### Three "exits" from the session

- **`/save`** — session archive (`saved/<path>`). For history, backups,
  comparing versions via `[o/k/s]` on name collision.
- **`/apply`** — export to a real project. Where you said — there it copied.
  Default — `--project`.
- **`/md`** — Markdown report from the last response.

Three different targets — three different commands. `/save` does not touch the
project, `/apply` does not touch the archive, `/md` touches neither.

---

### API key

Precedence:

| Order | Source |
|---|---|
| 1 | `--api-key PATH` |
| 2 | `api-key.txt` next to the script |
| 3 | `GEMINI_API_KEY` (env) |
| 4 | `GOOGLE_API_KEY` (env, legacy) |

The key is **never accepted inline** (`--api-key sk-abc` → error "file not
found"). File permissions are checked: if accessible by group/others
(`mode & 0o077`) — warning `chmod 600`.

**Why:** a key in `ps aux` and `~/.bash_history` is leaked forever. Only a
file with restricted permissions or an env variable is safe.

---

### UI language

`ru` (default) and `en`. Switch via `--lang` or `REPLAI_LANG=en replai`.
Localized: help, menu, banner, commands, prompts, errors, summary.

---

### Session menu on startup

When launched **without** `--resume`, `--new`, `--sync` in a TTY, `replai`
shows a **menu of all sessions** with date, turn/file counts, project, and
summary.

`0` or `Enter` — new session. Number or full `session_id` — load specific.

**`--project PATH`** filters the menu: only sessions for that project
(`os.path.normcase(abspath())`).

**`--resume` without ID** — same menu, but no "new session" option (Enter —
cancel).

Menu is **not shown** when: `--new` (new immediately), `--sync` (batch),
`--resume <id>` (direct load), `--continue` (last), not a TTY (pipe, CI).

---

### Session summary on exit

On exit (`exit`, `quit`, `/exit`, `Ctrl+D`), `replai` **generates one short
sentence** (up to 100 chars) — the essence of the session work — and stores
in `manifest.json` (`summary`, `summary_at`).

**Why:** the user returns a day later and wants to know "what was that
session" — without reading the log. Summary is visible in the menu, `/session`,
banner.

**What does NOT happen:** not written to `history` (metadata), does not save
media, not regenerated if the manifest hasn't changed, does not block exit on
error.

**Disable:** `--no-summary`.

**Not generated** if: session empty, Ctrl+C (interruption — not exit), last
turn is a user turn without a model turn (after rollback).

---

### CLI

#### Main

| Option | Default | Description |
|---|---|---|
| `--api-key PATH` | — | API key file |
| `--model NAME` | `gemini-3.8-flash` | Gemini model |
| `--temperature F` | `0.2` | Temperature |
| `--project PATH` | — | File / **directory** / `.zip` |
| `--state-dir PATH` | `replai` | State root |
| `--resume [ID]` | — | Resume (no ID — menu) |
| `--session [ID]` | — | Alias of `--resume` |
| `--continue` | off | Last session without menu |
| `--new` | off | New immediately, no menu |
| `--no-summary` | off | No summary on exit |
| `--lang {ru,en}` | `ru` | UI language |
| `--help` / `--version` | — | Help / version |

#### Sync

| Option | Default | Description |
|---|---|---|
| `--sync` | off | One-shot manifest pass + exit |
| `--dry-run` | off | Show actions without executing |
| `--sync-check {auto,warn,off}` | `auto` | File-use policy |

**File states** (`source != generated`):

| Local | Storage | SHA-256 | Status | `auto` |
|---|---|---|---|---|
| yes | yes | = | `ok` | nothing |
| yes | yes | ≠ | `out-of-sync` | ask re-upload |
| yes | no | — | `new-local` | ask upload |
| no | yes | — | `detached` | use URI |
| no | no | — | `lost` | error |

`detached` **never** offers "update" — nothing to update, no local version.
This is the unmounted-folder or deleted-file scenario: the storage copy is used.

Media with `source=generated` is always `ok` and **skipped** in `--sync` — it
is already on disk.

#### Retries

| Option | Default |
|---|---|
| `--send-retries N` | `4` |
| `--send-retry-delay F` | `2.0` sec |

Backoff `2 → 4 → 8 → 16` sec. Triggers by substring: `503`, `UNAVAILABLE`,
`429`, `RESOURCE_EXHAUSTED`, `Deadline Exceeded`, `timeout`, `high demand`,
`overloaded`. Anything else is raised immediately.

#### `/send` limits

`--limit-image-mb` (20), `--limit-video-mb` (500), `--limit-text-kb` (200),
`--limit-archive-mb` (200), `--limit-inline-total-mb` (18),
`--limit-request-total-mb` (500).

On exceed — `[y/N]`. Flag `-y`/`--yes` skips confirmations (for CI).

**Delivery rule for binary files:**
- `size <= --limit-inline-total-mb` → bytes in request (`Part.from_bytes`);
- otherwise → `client.files.upload` + `Part.from_uri`.

Threshold 18 MB (not 20) — a margin for the rest of the request text, so as
not to hit Gemini's hard limit (20 MB per request).

#### Project scanning

`--project-max-file-bytes` (200 KB), `--project-max-total-bytes` (2 MB),
`--project-max-files` (200), `--project-follow-symlinks` (off),
`--project-include-ide-dirs` (off).

`.gitignore` is honored (if `pathspec` is installed). Hard-excluded: `.git/`,
`__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `*.pyc`, `*.so`, `*.log`,
etc. Symlinks are **not** dereferenced by default; with
`--project-follow-symlinks` — with cycle protection.

**`--project` = directory** — used directly (not copied into session).
**`--project` = `.zip`** — extracted to `<session_dir>/project_extracted/`.

---

### REPL commands

| Command | Purpose |
|---|---|
| `/list` | Session file list |
| `/focus <pattern> [text]` | Focus on a file with instruction |
| `@<path>` in text | Mention the storage version of the file |
| `/send <path...> [--text X]` | Add new file(s) to session and send |
| `/save [path]` | Save code/media from last response to `saved/` archive |
| `/md <file>` | Save the entire response as Markdown |
| `/apply <src> [dst]` | Export files from `saved/` into actual project |
| `/forget <pattern>` | Remove entry from session (file on disk kept) |
| `/session` | Session info |
| `/history` | Turn history (last 15, with turn ID) |
| `/help` | Cheatsheet |
| `exit` / `quit` / `/exit` | Exit (generates summary) |

All commands start with `/`. For multiline input — see "Text input".

#### `/list` — session file list

Table: `#` (index for `#N`), type, src (`in`/`gen`), status (sync status for
input, `ok` for generated), size, normalized name.

`src=in` — from project or `/send`. `src=gen` — model-generated.

#### `/focus <pattern> [text]` — targeted file send

Send one file with an instruction. `pattern` — `#N` (index from `/list`),
exact name, basename, glob, or `replai_<sid>_<path>` (normalized).

Before sending, status is checked:

- `ok` → send;
- `out-of-sync` + `--sync-check auto` → ask "update in storage?";
- `warn` → warn only;
- `off` → silently send local;
- `detached` → use URI from storage;
- `lost` → error.

**Why separate from `/send`:** `/focus` does not add a new file — it **returns
attention** to an already known file. Useful for iterative debugging of one
file from a large dataset.

#### `@name` in text — cloud version mention

Recognized at start of line or after space/`(`/`[`/quote. `user@example.com`
is not broken. Trailing punctuation (`@main.py,`) is stripped.

**What it does:** looks up the file in the manifest, checks `files_api_uri`
and `expires_at`, offers to re-upload if needed. Inserts
`[MENTION] <path> (storage version)` + content from Files API.

**Difference from `/send`:** `/send path` attaches the **fresh local** file.
`@name` in text — the **cloud copy**. These are **different files** if content
differs. See "Key concepts".

#### `/send <path...> [--text X]` — add file to session

Syntax:

```
/send "file.png" Hello
/send "a.png" "b.png" --text Compare
/send "my file with spaces.png" test
```

Parsing: if `--text` present — everything before is paths, everything after is
text. Otherwise: quoted token → path; unquoted existing file → path; otherwise
→ start of text.

By type: text inline; archive extracted in memory; image/video/audio/binary —
inline or Files API by size.

**If text contains `@name`** (e.g. `/send "test_report.md" what is in
@test_report.md`) — both versions go to the model with explicit labels:
`[FILE]` (local, fresh) + `[MENTION]` (cloud, old). The model sees them as
**different files** and doesn't confuse them.

If `@name` not found in session/storage — warning + `[Y/n]`. Enter = send
without mention (for prompts like `@Image1` where `@` is text).

#### `/save [path]` — archive the last response

**Without argument:** all code blocks + all media from the last response. Plan
shown, `[y/N]`.

**With argument:** first looks in the session (by name, index, glob), then in
response blocks. Found → `shutil.copy2` to `saved/<path>`.

**On name collision:** `[o]` overwrite / `[k]` new with turn ID
(`main_t003.py`, old intact) / `[s]` skip. Identical content skipped silently
(`⏭ Unchanged`).

**Target:** `replai/sessions/<id>/saved/`. **Not** the project, **not** storage.

**Why:** archive in the session. For history, for version comparison. If you
need it in the **project** — use `/apply`.

#### `/apply <src> [dst]` — export to project

**Direction:** `<session>/saved/` → `<dst>/`. This is the **exit from session
to reality**.

**`src`** — pattern in session: name, `<dir>/` (all files in folder), `#N`,
glob.

**`dst`** — where to copy. If not specified — to `--project`:
- `--project` = directory → into it;
- `--project` = `.zip` → into `<session>/project_extracted/`.

**Behavior:** shows plan (`new` / `CONFLICT`), asks `[y/N]`. On conflict —
`[y/N]` per file (bypassed by `--force`/`--yes`).

**`--dry-run`** — plan only.

**Why separate from `/save`:** `/save` = "I want an archive", `/apply` = "I
want it in my working project". Different targets — different commands.

#### `/forget <pattern>` — remove from session

Removes the record from `manifest.files()`. **Does not** delete from disk
(`local_path`), **does not** delete from Files API. Just removes from context:
after `/forget`, the file is not found in `/list`, `@`, `/focus`, `/save`.

For `source=generated` — separate confirmation (file in `media/` remains).

**Why:** clean the session from extra records without touching real files.
Useful in long sessions and when the Files API 20 GB quota is exhausted
(remove record → re-upload from local).

`--dry-run` — show only.

#### `/md <file>` — Markdown export

Saves `LAST_RESPONSE["text"]` to a file.

- Without explicit path (`/md report.md`) → `saved/report.md`.
- With explicit path (`/md ./out.md`, `/md ~/docs/x.md`, `/md C:\x.md`) →
  path as is, `~` expanded, nested folders created.

Output shows **absolute** path and size — the user sees where the file
actually went.

#### `/session` — session info

ID, summary, date, model, project, file/turn/media counts,
manifest/log/saved/media paths, ready-to-copy `replai --resume <id>`.

#### `/history` — last 15 turns

With `[turn:N]` — the turn number, matching `turnNNN` in media filenames and
`file_tNNN` on `/save` with `[k]`. Allows correlating an artifact with a turn.

#### `/help` — cheatsheet

#### `exit` / `quit` / `/exit` — exit

Three equivalent ways. Generates summary. Ctrl+D — same with summary. Ctrl+C —
interrupts the operation, does not exit.

---

### State structure

```text
replai/
└── sessions/
    └── 20261107_142305/              ← session_id = YYYYMMDD_HHMMSS
        ├── manifest.json             ← atomic writes, incremental
        ├── log.txt                   ← append, with [turn:NNN]
        ├── saved/                    ← /save and /md
        ├── media/                    ← media auto-save
        └── project_extracted/        ← only for --project *.zip
```

All visible, all portable.

---

### Resilience

- **Retries on 503/429** — exponential backoff.
- **Atomic manifest write** via `.tmp` → `os.replace`.
- **Incremental write** after every action.
- **Turn rollback on Ctrl+C** — orphan user record removed from `history`, so
  summary and resume work on a consistent history.
- **Auto-cleanup of stale `files_api_uri`** when local SHA changes
  (`add_file`) — old URI won't be "phantomly" used.
- **Warning on text fallback to URI** — if local file is unavailable,
  `replai` explicitly says it is using the storage version.

---

### Examples

#### Debugging one file from a large dataset

```
/list
/focus "Five of Wands.jpg" Script produces red background instead of white
```

#### Comparing two files in one question

```
Why does @prepress/lift.py's lift() function give red background for
@Five\ of\ Wands.jpg, but white for @Six\ of\ Wands.jpg?
```

#### Generating and saving an image

```
Generate a dragon postcard in industrial style, 512x512
# [1 media file auto-saved to media/]

/save
# Saves the image to saved/
```

#### Sync after edits

```bash
replai --project ./proj --sync --yes
```

#### Recovery after a crash

```bash
replai --resume                       # session menu
replai --resume 20261107_142305       # specific
replai --session 20261107_142305      # alias
replai --continue                     # latest
```

#### CI mode (no interactivity)

```bash
replai --yes --project ./proj --sync
```

`--yes` automatically:
- selects "new session" in menu (or `Y` on sync prompts);
- confirms re-upload in `--sync`;
- confirms `[y/N]` prompts on `/send` limits.

---

### Requirements

- **Python 3.10+** (annotations `X | None`, `tuple[list[str], str]`).
- **Google GenAI SDK** `google-genai>=1.0.0`.
- **pathspec** — optional, for `.gitignore` parsing.
- **prompt-toolkit** — recommended, for multiline input and history.
- OS: Linux, macOS, Windows.

---

### Roadmap

`v0.0.2` — current. Deliberately **not** included:

- **Download from Files API in `/save`.** If model returned a link
  (`file_data`) instead of `inline_data` — mentioned as text.
- **Upload batching** for large files in one `/send`.
- **Response streaming** (`stream=True`).
- **Cross-session `@` search** — currently current session only.
- **`media/` cleanup** — files accumulate, no limit.
- **`/apply` into `project_extracted/`** — currently copies to `--project`,
  not into the extracted zip.
- **Persistent input history** (`FileHistory` in `saved/.history`) — currently
  `InMemoryHistory`, `↑`/`↓` works within one session only.
- **Cross-terminal Shift+Enter reliability** — depends on terminal protocol
  (Kitty / `modifyOtherKeys=2` / `CSI-u`); `Alt+Enter` / `Ctrl+J` fallback is
  universal.
```