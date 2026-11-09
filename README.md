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

**Версия:** `0.0.7`. **Python:** `3.10+`.

### Зачем это нужно

Обычный AI-чат в браузере теряет контекст, если что-то сломалось, и не умеет
работать с реальными файлами проекта. `replai`:

- **читает ваш проект с диска** — модель видит структуру и содержимое файлов;
- **принимает новые файлы из чата** (`/send`) — картинки, архивы, код;
- **автосохраняет всё, что вернула модель** — если это медиа, оно попадает
  в `media/` немедленно, чтобы вы не потеряли дорогой результат генерации;
- **синхронизирует в обе стороны** — `/sync` загружает большие датасеты в
  облако AI Studio, а `/apply` (Smart Pull) скачивает результаты работы
  нейросети обратно на диск;
- **упаковывает результаты** — `/save --zip` собирает все сгенерированные файлы и медиа в один архив;
- **переживает сбои** — сессия продолжается после Ctrl+C, kill, обрыва SSH;
- **помнит сессии** — на выходе генерируется summary, при запуске показывается
  меню всех сессий с описаниями.

### Принципы дизайна

1. **Честность имен (No Magic).** Из-за ограничений Google Files API имена в облаке могут транслитерироваться (например, `Промпт.txt` → `Promt.txt`). Чтобы вы не запутались, `/list` показывает **оба имени**: облачное (с префиксом) и локальное (оригинальное). Поиск (`@`, `/focus`) работает по любому из них.
2. **Два разных «хранилища».** Локальные файлы и облачные файлы (Gemini Files API) — это не одно и то же. Синхронизация идёт по SHA-256.
3. **`@name` — всегда облачная версия.** Устраняет неоднозначность.
4. **Ничего не теряется.** Медиа от модели автосохраняется. А при удалении файлов используется «Мягкое удаление» (Soft Delete) в корзину (`trash/`).

---

### Установка

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

### Ввод текста

| Действие | Клавиши |
|---|---|
| Отправить сообщение | `Enter` |
| Перенос строки (современные терминалы) | `Shift+Enter` |
| Перенос строки (универсальный) | `Alt+Enter` или `Esc`, затем `Enter` |
| Перенос строки (LF) | `Ctrl+J` |
| Вставка из буфера | `Ctrl+V` (сохраняет отступы и переносы) |
| История запросов | `↑` / `↓` |
| Выйти из сессии | `Ctrl+D` или `exit` / `quit` / `/exit` |

---

### Ключевые концепции

#### Двухслойная система имен
В версии 0.0.7 имена файлов в облаке и на диске могут отличаться. Это сделано для того, чтобы обойти ограничения Google API (который не принимает кириллицу в именах).
* В облаке: `replai_20261109_Promt.txt` (транслит).
* На диске: `Промпт.txt` (оригинал).
* В `/list`: выводятся обе строки, чтобы вы точно знали, какой файл на диске соответствует файлу в AI Studio.

Если в имени есть сложные символы (китайские иероглифы, эмодзи), к имени добавляется короткий хеш (`file_a1b2c3.txt`), чтобы исключить коллизии. Поиск (`@Промпт.txt` или `@Promt.txt`) сработает в обоих случаях.

#### Жизненный цикл файлов (48 часов)
Google Files API удаляет файлы через 48 часов. `replai` автоматически отслеживает `expires_at`. Если вы вернётесь через 3 дня и запустите `/apply`, скрипт корректно обработает «протухшие» файлы, не удаляя ваши локальные копии.

---

### CLI

#### Основные

| Опция | По умолчанию | Описание |
|---|---|---|
| `--project PATH` | — | Файл / **папка** / `.zip` |
| `--resume [ID]` | — | Продолжить (без ID — меню) |
| `--continue` | off | Последняя сессия без меню |

#### Синхронизация (Local -> Cloud)

| Опция | По умолчанию | Описание |
|---|---|---|
| `--sync` | off | Синхронизировать файлы проекта с хранилищем (Local -> Cloud) |

**Особенности `--sync`:**
- В интерактивном терминале (TTY) `--sync` **не завершает работу**: он проводит синхронизацию и **запускает чат**.
- В режиме CI (без TTY) `--sync` делает работу и **завершается** (код 0).

**Статусы файла:**

| Локально | Хранилище | Статус | `auto` |
|---|---|---|---|
| есть | есть | `ok` | ничего |
| есть | есть (разный SHA) | `out-of-sync` | спросить перезалить |
| есть | нет | `new-local` | спросить загрузить |
| нет | есть | `detached` | использовать URI |
| нет | нет | `lost` | ошибка |

#### Сканирование проекта

| Опция | По умолчанию |
|---|---|
| `--project-max-file-bytes` | `2_000_000_000` (2 ГБ) |
| `--project-max-total-bytes` | `20_000_000_000` (20 ГБ) |
| `--project-max-files` | `1000` |

> **Примечание:** Лимиты синхронизированы с официальными ограничениями Google AI Studio.
> 
> **Защита контекста:** Если ваш проект содержит текстовые файлы размером более **1 МБ**, `replai` не будет вставлять их содержимое в системный промпт целиком. Кроме того, действует **глобальный лимит контекста в 500 000 символов**. Все файлы индексируются и доступны для точечного чтения через `@имя_файла` или `/focus`.

---

### Команды REPL

| Команда | Назначение |
|---|---|
| `/list` | Список файлов (облачные и локальные имена) |
| `/focus <pattern> [текст]` | Сфокусироваться на файле с инструкцией |
| `@<path>` в тексте | Упоминание облачной версии файла |
| `/send <path...> [--text X]` | Добавить новый файл(ы) и отправить |
| `/sync [path]` | Загрузить локальные файлы в облако (Local -> Cloud) |
| `/apply [pattern]` | **Smart Pull**: скачать файлы из облака на диск (Cloud -> Local) |
| `/save [path] [--zip]` | Сохранить блоки кода из ответа (или упаковать в ZIP) |
| `/md <file>` | Сохранить **весь текст** ответа как Markdown |
| `/forget <pattern>` | Убрать запись из сессии (detached-файлы удаляются и из облака) |
| `exit` / `/exit` | Выход |

#### `/sync [path]` — подготовка датасета (Local -> Cloud)

Сканирует папку `--project`. Если находит файлы, указанные в `.gitignore`
(например, `dataset/`), **спрашивает разрешение** на их синхронизацию. Загружает всё в Files API
и регистрирует в манифесте. **Ничего не отправляет модели.**

**Компактное подтверждение загрузки:**
1. **Сводка:** Показывает список папок и файлов. Спрашивает: «Загрузить все найденные файлы (N)? [Y/n/l]».
   * `Y` (Enter) — загрузить всё.
   * `n` — перейти к выбору по папкам/файлам.
   * `l` — вывести полный нумерованный список файлов.
2. **По папкам:** Если выбрано `n`, скрипт группирует файлы по папкам и спрашивает: «Папка 'dataset' (78 файлов). Загрузить все? [y/N/a]». 
   * `y` — загрузить всё в папке.
   * `N` (Enter) — пропустить папку.
   * `a` — перейти к поштучному подтверждению.
3. **По файлам:** Спрашивает по каждому: «Загрузить файл 'img_01.jpg'? [y/N]».

#### `/apply [pattern]` — Smart Pull (Cloud -> Local)

Скачивает файлы из облака AI Studio на локальный диск (через `client.files.download()`).

1. **`/apply` (без аргументов):** скачивает **все** файлы сессии в `--project`
   (или в папку `<session_dir>/downloads/`, если проект не задан).
2. **`/apply dataset/`:** скачивает только указанную папку.
3. **Восстановление имен:** Файлы на диск скачиваются под их **оригинальными локальными именами** (например, `Промпт.txt`, а не `Promt.txt`).
4. **Обработка состояний:**
   - `ok` — пропускает (версии совпадают).
   - `out-of-sync` — предлагает перезаписать локальный файл облачным.
   - `detached` — скачивает из облака (восстанавливает).
   - `new-local` — файл есть на диске, но нет в облаке. Предлагает `[Enter]` оставить или `[d]` **переместить в корзину** (`trash/`).
   - `lost` — предупреждает, что файл утерян безвозвратно.

#### `/save [path] [--zip]` vs `/md <file>`

- **`/save`** — извлекает и сохраняет **только блоки кода** (в тройных обратных кавычках) из последнего ответа модели. Идеально для сохранения скриптов.
- **`/save --zip`** — упаковывает все сгенерированные блоки кода **и** медиафайлы (включая отправленные через `/send`) в один ZIP-архив. Имеется защита от Zip Slip (выхода за пределы директории при распаковке).
- **`/md`** — сохраняет **весь текст** ответа модели целиком. Идеально для сохранения рассуждений или инструкций.

При совпадении имени файла при `/save`: `[o]` перезаписать / `[k]` новый с ID хода (`main_t003.py`) / `[s]` пропустить.

#### `/forget <pattern>`

Умное удаление:
- Если файл **есть на диске**: удаляет только запись из `manifest.json`.
- Если файл **отсутствует на диске** (`detached`): удаляет запись из манифеста
  **и** вызывает `client.files.delete()` для очистки квоты в AI Studio.

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
        ├── trash/                    ← мягкое удаление (Soft Delete)
        ├── downloads/                ← /apply, если не задан --project
        └── project_extracted/        ← только для --project *.zip
```

---

## 🇬🇧 Description and Documentation (English)

**Terminal REPL for Gemini — project-aware code chat with file round-trip.**

`replai` is a terminal shell for Gemini. It reads project sources, accepts
images/audio/video/archives/files directly from the chat, auto-saves any media
the model generates, lets you export results back to a real project, and
survives crashes via `resume` + `sync`.

**Version:** `0.0.7`. **Python:** `3.10+`.

### Design principles

1. **Name Honesty (No Magic).** Due to Google Files API limits, cloud names may be transliterated. `/list` shows both the cloud name (with prefix) and the local name. Search (`@`, `/focus`) works with either.
2. **Two different "storages".** Sync is based on SHA-256.
3. **`@name` is always the cloud version.**
4. **Nothing is lost.** Media is auto-saved. Deletions go to `trash/` (Soft Delete).

---

### CLI

#### Sync (Local -> Cloud)

| Option | Default | Description |
|---|---|---|
| `--sync` | off | Sync project files with storage |

**Behavior of `--sync`:**
- In a TTY (interactive terminal), `--sync` **does not exit**: it syncs and **starts the chat**.
- In CI mode (no TTY), it syncs and **exits** (code 0).

#### Project scanning

| Option | Default |
|---|---|
| `--project-max-file-bytes` | `2_000_000_000` (2 GB) |
| `--project-max-total-bytes` | `20_000_000_000` (20 GB) |
| `--project-max-files` | `1000` |

> **Note:** Defaults are aligned with Google AI Studio limits.
> 
> **Context protection:** Text files larger than **1 MB** and a global limit of **500,000 characters** prevent token limit exhaustion. They are still indexed and available on-demand via `@filename` or `/focus`.

---

### REPL commands

| Command | Purpose |
|---|---|
| `/list` | List session files (cloud and local names) |
| `/focus <pattern> [text]` | Focus on a file with instruction |
| `@<path>` in text | Mention the storage version of the file |
| `/send <path...> [--text X]` | Add new file(s) to session and send |
| `/sync [path]` | Upload local files to cloud (Local -> Cloud) |
| `/apply [pattern]` | **Smart Pull**: download files from cloud to disk (Cloud -> Local) |
| `/save [path] [--zip]` | Save code blocks (or pack into ZIP) |
| `/md <file>` | Save **entire response TEXT** as Markdown |
| `/forget <pattern>` | Remove entry (detached files also deleted from cloud) |

#### `/sync [path]` — dataset preparation (Local -> Cloud)

Scans the `--project` folder. If it finds files excluded in `.gitignore`, it **asks for permission** to sync them. Uploads to Files API and registers in `manifest.json`. **Does not send anything to the model.**

**Compact summary confirmation:**
1. **Summary:** Shows a folder tree. Asks: "Upload all N files? [Y/n/l]".
   * `Y` (Enter) — upload all.
   * `n` — choose by folders/files.
   * `l` — print the full numbered list.
2. **By directory:** If `n`, it groups by folders: "Folder 'dataset' (78 files). Upload all files? [y/N/a]".
3. **By file:** Asks for each: "Upload file 'img_01.jpg'? [y/N]".

#### `/apply [pattern]` — Smart Pull (Cloud -> Local)

Downloads files from AI Studio to disk (via `client.files.download()`).

1. `/apply` — downloads all session files to `--project` (or `<session_dir>/downloads/`).
2. `/apply dataset/` — downloads only the specified folder.
3. **Name Restoration:** Files are saved using their **original local names** (e.g., `Промпт.txt` instead of `Promt.txt`).
4. **State handling:**
   - `ok` — skip.
   - `out-of-sync` — ask to overwrite local file.
   - `detached` — download from cloud (restore).
   - `new-local` — file exists on disk, but not in cloud. Asks to keep `[Enter]` or move to `trash/` `[d]`.
   - `lost` — warn the user.

#### `/save [path] [--zip]` vs `/md <file>`

- **`/save`** — extracts and saves **only code blocks** (inside triple backticks) from the last response.
- **`/save --zip`** — packs all generated code and media (including files sent via `/send`) into a single ZIP archive. Includes Zip Slip protection.
- **`/md`** — saves the **entire text** of the response.

#### `/forget <pattern>`

- File on disk: removes only the record from `manifest.json`.
- Missing file (`detached`): removes the record **and** calls `client.files.delete()`.

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
        ├── trash/                    ← soft delete storage
        ├── downloads/                ← /apply target if no --project
        └── project_extracted/        ← only for --project *.zip
```