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

**Версия:** `0.0.4`. **Python:** `3.10+`.

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
- **готовит контекст** — `/sync` загружает большие датасеты в облако AI Studio, не сжигая токены модели прямо сейчас;
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

#### Локальный файл vs облачный файл

- **Локальный** — на вашем диске, `local_path`. Источник правды.
- **Облачный** — в Files API, `files_api_uri`. Живёт 48 часов. Это
  **копия**, сделанная для отправки модели.

`replai` использует **SHA-256, а не имена**, чтобы понять, совпадают ли
версии. Переименование файла на диске — не проблема. Изменение содержимого —
ловится автоматически (`out-of-sync`). Если в хранилище нет копии
(`new-local`) или копия устарела (`out-of-sync`), `replai` предложит
перезалить.

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

#### Медиа автосохраняется всегда

Как только модель возвращает изображение/видео/аудио в ответе, оно
**немедленно** пишется в
`replai/sessions/<id>/media/<timestamp>_turnNNN_MMM.<ext>`. Это **не**
`/save` — `/save` по запросу пользователя. Это страховка от потери:
сгенерированные картинки невоспроизводимы.

Автосохранённое медиа сразу появляется в `/list` (с `src=gen`), доступно
для `/focus`, `/save`, `@`.

#### Три «выхода» из сессии

- **`/save`** — архив сессии (`saved/<path>`). Для истории, резервных
  копий, сравнения версий.
- **`/apply`** — выгрузка в реальный проект. Куда указали — туда и
  скопировалось. По умолчанию — в `--project`.
- **`/md`** — Markdown-отчёт из последнего ответа.

Три разных адресата — три разные команды.

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

---

### Язык интерфейса

`ru` (по умолчанию) и `en`. Переключается через `--lang` или
`REPLAI_LANG=en replai`.

---

### Меню сессий при запуске

При запуске **без** `--resume`, `--new`, `--sync` в TTY `replai` показывает
**меню всех сессий** с датой, количеством ходов/файлов, проектом и summary.

Пункт `0` или `Enter` — новая сессия. Ввод номера или полного `session_id` —
загрузка конкретной.

**`--project PATH`** фильтрует меню: показываются только сессии с этим
проектом.

**`--resume` без ID** — то же меню, но без пункта «новая» (Enter — отмена).

---

### Summary сессии на выходе

При выходе (`exit`, `quit`, `/exit`, `Ctrl+D`) `replai` **генерирует одно
короткое предложение** (до 100 символов) — суть работы в сессии — и
сохраняет в `manifest.json` (`summary`, `summary_at`).

**Зачем:** пользователь возвращается через день и хочет понять «что было в
той сессии» — без чтения лога.

**Отключить:** `--no-summary`.

**Не генерируется**, если: сессия пустая, Ctrl+C (прерывание — не выход).

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

#### Синхронизация (CLI)

| Опция | По умолчанию | Описание |
|---|---|---|
| `--sync` | off | Синхронизировать файлы проекта с хранилищем |
| `--dry-run` | off | Показать без действий |
| `--sync-check {auto,warn,off}` | `auto` | Политика при использовании файла |
| `--project-include-ignored` | off | Загружать файлы из `.gitignore` без вопросов |
| `--sync-clean-detached` | off | Разрешить удаление detached-файлов для очистки квоты |

**Особенности `--sync`:**
- В интерактивном терминале (TTY) `--sync` **не завершает работу**: он проводит синхронизацию и **запускает чат**.
- В режиме CI (без TTY) `--sync` делает работу и **завершается** (код 0).
- Запуск просто `replai --sync` без других флагов автоматически подхватывает последнюю сессию (эквивалент `--continue --sync`).

**Статусы файла** (`source != generated`):

| Локально | Хранилище | SHA-256 | Статус | `auto` |
|---|---|---|---|---|
| есть | есть | = | `ok` | ничего |
| есть | есть | ≠ | `out-of-sync` | спросить перезалить |
| есть | нет | — | `new-local` | спросить загрузить |
| нет | есть | — | `detached` | использовать URI |
| нет | нет | — | `lost` | ошибка |

#### Сканирование проекта

| Опция | По умолчанию |
|---|---|
| `--project-max-file-bytes` | `6_000_000` (6 МБ) |
| `--project-max-total-bytes` | `500_000_000` (500 МБ) |
| `--project-max-files` | `200` |
| `--project-follow-symlinks` | off |
| `--project-include-ide-dirs` | off (`.idea/`, `.vscode/` исключены) |

> **Примечание:** Лимиты 6 МБ на файл и 500 МБ на проект по умолчанию настроены для комфортной работы с датасетами изображений. Если вы работаете только с текстом, их можно уменьшить для экономии памяти.

`.gitignore` учитывается. Жёстко исключены: `.git/`, `__pycache__/`, `.venv/`,
`node_modules/`, `dist/`, `*.pyc`, `*.so`, `*.log`, и т.п.

**`--project` = папка** — используется напрямую (не копируется в сессию).
**`--project` = `.zip`** — распаковывается в `<session_dir>/project_extracted/`.

---

### Команды REPL

| Команда | Назначение |
|---|---|
| `/list` | Список файлов сессии |
| `/focus <pattern> [текст]` | Сфокусироваться на файле с инструкцией |
| `@<path>` в тексте | Упоминание облачной версии файла |
| `/send <path...> [--text X]` | Добавить новый файл(ы) и отправить |
| `/sync [path]` | Синхронизировать проект с хранилищем (не отправляя модели) |
| `/save [path]` | Сохранить код/медиа ответа в архив `saved/` |
| `/md <file>` | Сохранить весь ответ как Markdown |
| `/apply <src> [dst]` | Выгрузить файлы из `saved/` в проект |
| `/forget <pattern>` | Убрать запись из сессии (detached-файлы удаляются и из облака) |
| `/session` | Информация о сессии |
| `/history` | История ходов (последние 15) |
| `/help` | Справка |
| `exit` / `quit` / `/exit` | Выход (генерирует summary) |

#### `/sync [path]` — подготовка датасета

Команда решает проблему: «Как загрузить 78 картинок в AI Studio, не отправляя их модели сразу (чтобы не сжечь контекст)?».

**Логика работы:**
1. Сканирует папку `--project` (или указанный `[path]`).
2. Если находит файлы, указанные в `.gitignore` (например, `dataset/`), **спрашивает разрешение** на их синхронизацию (потому что `.gitignore` — это для GitHub, а не для AI Studio).
3. Загружает всё в Files API и регистрирует в `manifest.json`.
4. **Ничего не отправляет модели.** Теперь вы можете точечно обращаться к файлам через `@` или `/focus`.

**Трехуровневое подтверждение загрузки:**
Если скрипт находит много новых или измененных файлов, он не заставляет вас нажимать `y` на каждый:
1. **Все:** «Найдено 78 файлов. Загрузить все? [Y/n]» (Enter — да).
2. **Папка:** Если вы ответили `n`, он сгруппирует файлы по папкам: «Загрузить все 70 файлов в папке 'dataset'?».
3. **Файл:** Только если вы отказались от всей папки, начнется перебор по одному.

**Удаление «мусора» (detached):**
Если вы удалили файл локально, но он остался в сессии, `/sync` предупредит об этом в конце и предложит удалить его из AI Studio, чтобы освободить квоту (по умолчанию — нет).

#### `/forget <pattern>` — убрать из сессии

Умное удаление:
- Если файл **есть на диске**: удаляет только запись из `manifest.json` (файл на диске и облачная копия остаются нетронутыми).
- Если файл **отсутствует на диске** (`detached`): удаляет запись из манифеста **и** вызывает `client.files.delete()` для очистки квоты в AI Studio.

#### `/apply <src> [dst]` — выгрузка в проект

**Направление:** `<session>/saved/` → `<dst>/`.

**`src`** — паттерн в сессии: имя, `<dir>/` (все файлы в папке), `#N`, glob.
**`dst`** — куда копировать. Если не указан — в `--project`.

#### `/save [path]` — архив последнего ответа

**Без аргумента:** все блоки кода + все медиа из последнего ответа. Показ плана, `[y/N]`.
**С аргументом:** сначала ищет в сессии, затем в блоках ответа.

**При совпадении имени:** `[o]` перезаписать / `[k]` новый с ID хода (`main_t003.py`) / `[s]` пропустить. Идентичное содержимое пропускается молча.

#### `/focus <pattern> [текст]` — прицельная отправка файла

Отправить один файл модели с инструкцией. `pattern` — `#N` (индекс из `/list`), точное имя, basename, glob.

**Зачем отдельно от `/send`:** `/focus` не добавляет новый файл — он **возвращает внимание** к уже известному. Полезно для итеративной отладки одного файла из большого датасета.

#### `@name` в тексте — упоминание облачной версии

Вставляет `[MENTION] <path> (версия из хранилища)` + содержимое из Files API. Если копия истекла, предложит перезалить.

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

---

### Требования

- **Python 3.10+**.
- **Google GenAI SDK** `google-genai>=1.0.0`.
- **pathspec** — опционально.
- **prompt-toolkit** — рекомендовано.

---

## 🇬🇧 Description and Documentation (English)

**Terminal REPL for Gemini — project-aware code chat with file round-trip.**

`replai` is a terminal shell for Gemini. It reads project sources, accepts
images/audio/video/archives/files directly from the chat, auto-saves any media
the model generates, lets you export results back to a real project, and
survives crashes via `resume` + `sync`.

**Version:** `0.0.4`. **Python:** `3.10+`.

### Why this exists

A regular AI chat in a browser loses context when something breaks and cannot
touch real project files. `replai`:

- **reads your project from disk** — the model sees structure and file contents;
- **accepts new files from the chat** (`/send`) — images, archives, code;
- **auto-saves everything the model returns** — media lands in `media/`
  immediately, so expensive generation is not lost;
- **lets you export** — `/save` for a session archive, `/apply` for the real
  project, `/md` for a Markdown report;
- **prepares context** — `/sync` uploads large datasets to AI Studio without burning the model's token limit right now;
- **survives failures** — session continues after Ctrl+C, kill, SSH disconnect;
- **remembers sessions** — a summary is generated on exit, and a session menu
  with descriptions appears on the next launch.

### Design principles

1. **State is visible and portable.** Everything lives in `./replai/`.
2. **Two different "storages".** Local files (`local_path`) and cloud files
   (Gemini Files API, `files_api_uri`) are **not the same**. `replai` syncs
   them by SHA-256, not by names.
3. **`@name` is always the cloud version.** Removes ambiguity about "which
   version the user means".
4. **Nothing is lost.** Model media is auto-saved to disk **before** you click
   anything. Loss is unacceptable.

---

### Installation

```bash
git clone https://github.com/vasiliypavlov/replai
cd replai
pip install -r requirements.txt
```

`requirements.txt`:

```
google-genai>=1.0.0
pathspec>=0.12.0
prompt-toolkit>=3.0.0
```

---

### Text input

| Action | Keys |
|---|---|
| Send message | `Enter` |
| Soft line break | `Shift+Enter` / `Alt+Enter` / `Ctrl+J` |
| Paste from clipboard | `Ctrl+V` |
| Request history | `↑` / `↓` |
| Exit session | `Ctrl+D` or `exit` / `quit` / `/exit` |

---

### CLI

#### Main

| Option | Default | Description |
|---|---|---|
| `--api-key PATH` | — | API key file |
| `--model NAME` | `gemini-3.8-flash` | Gemini model |
| `--project PATH` | — | File / **directory** / `.zip` |
| `--resume [ID]` | — | Resume (no ID — menu) |
| `--session [ID]` | — | Alias of `--resume` |
| `--continue` | off | Last session without menu |
| `--new` | off | New immediately, no menu |

#### Sync (CLI)

| Option | Default | Description |
|---|---|---|
| `--sync` | off | Sync project files with storage |
| `--dry-run` | off | Show actions without executing |
| `--sync-check {auto,warn,off}` | `auto` | File-use policy |
| `--project-include-ignored` | off | Sync `.gitignore` excluded files without prompting |
| `--sync-clean-detached` | off | Allow deletion of detached files to free quota |

**Behavior of `--sync`:**
- In a TTY (interactive terminal), `--sync` **does not exit**: it syncs and **starts the chat**.
- In CI mode (no TTY), it syncs and **exits** (code 0).
- Running `replai --sync` without other flags automatically picks the last session (equivalent to `--continue --sync`).

**File states** (`source != generated`):

| Local | Storage | SHA-256 | Status | `auto` |
|---|---|---|---|---|
| yes | yes | = | `ok` | nothing |
| yes | yes | ≠ | `out-of-sync` | ask re-upload |
| yes | no | — | `new-local` | ask upload |
| no | yes | — | `detached` | use URI |
| no | no | — | `lost` | error |

#### Project scanning

| Option | Default |
|---|---|
| `--project-max-file-bytes` | `6_000_000` (6 MB) |
| `--project-max-total-bytes` | `500_000_000` (500 MB) |
| `--project-max-files` | `200` |
| `--project-follow-symlinks` | off |
| `--project-include-ide-dirs` | off |

> **Note:** Default limits (6 MB per file, 500 MB per project) are tuned for comfortable work with image datasets. If you work with text only, you can lower them.

---

### REPL commands

| Command | Purpose |
|---|---|
| `/list` | Session file list |
| `/focus <pattern> [text]` | Focus on a file with instruction |
| `@<path>` in text | Mention the storage version of the file |
| `/send <path...> [--text X]` | Add new file(s) to session and send |
| `/sync [path]` | Synchronize project with storage (without sending to model) |
| `/save [path]` | Save code/media from last response to `saved/` archive |
| `/md <file>` | Save the entire response as Markdown |
| `/apply <src> [dst]` | Export files from `saved/` into actual project |
| `/forget <pattern>` | Remove entry (detached files also deleted from cloud) |
| `/session` | Session info |
| `/history` | Turn history (last 15) |
| `/help` | Cheatsheet |
| `exit` / `quit` / `/exit` | Exit (generates summary) |

#### `/sync [path]` — dataset preparation

Solves the problem: "How to upload 78 images to AI Studio without sending them to the model right now (to avoid burning context)?".

**How it works:**
1. Scans the `--project` folder (or `[path]`).
2. If it finds files excluded in `.gitignore` (e.g., `dataset/`), it **asks for permission** to sync them (`.gitignore` is for GitHub, not for AI Studio).
3. Uploads to Files API and registers in `manifest.json`.
4. **Does not send anything to the model.** You can now target files via `@` or `/focus`.

**Three-tier upload confirmation:**
If there are many new/changed files, it won't make you press `y` for each:
1. **All:** "Found 78 files. Upload all? [Y/n]".
2. **Folder:** If you answer `n`, it groups by folders: "Upload all 70 files in 'dataset'?".
3. **File:** Only if you declined the folder, it iterates one by one.

**Cleanup (detached files):**
If you deleted a file locally but it's still in the session, `/sync` will warn you and offer to delete it from AI Studio to free quota.

#### `/forget <pattern>`

Smart deletion:
- If file **exists on disk**: removes only the record from `manifest.json`.
- If file is **missing on disk** (`detached`): removes the record **and** calls `client.files.delete()` to free AI Studio quota.

#### `@name` in text

Inserts `[MENTION] <path> (storage version)` + content from Files API. If the copy is expired, it offers to re-upload.

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

---

### Requirements

- **Python 3.10+**.
- **Google GenAI SDK** `google-genai>=1.0.0`.
- **pathspec** — optional.
- **prompt-toolkit** — recommended.
```