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

**Версия:** `0.0.5`. **Python:** `3.10+`.

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
- **переживает сбои** — сессия продолжается после Ctrl+C, kill, обрыва SSH;
- **помнит сессии** — на выходе генерируется summary, при запуске показывается
  меню всех сессий с описаниями.

### Принципы дизайна

1. **Никаких двойных стандартов (No Magic).** Имена файлов в `/list` — это
   точные имена из Google AI Studio (с префиксом сессии). Если вы копируете
   имя, вы копируете именно то, что видит облако. Это исключает риск
   «попросить модель поправить не тот файл».
2. **Два разных «хранилища».** Локальные файлы и облачные файлы (Gemini Files
   API) — это не одно и то же. Синхронизация идёт по SHA-256.
3. **`@name` — всегда облачная версия.** Устраняет неоднозначность.
4. **Ничего не теряется.** Медиа от модели автосохраняется. А при удалении
   файлов используется «Мягкое удаление» (Soft Delete) в корзину.

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

#### Точные имена файлов
В версии 0.0.5 команда `/list` выводит **точные имена** (`display_name`),
под которыми файлы зарегистрированы в Google AI Studio. Это сделано, чтобы вы
могли скопировать имя и вставить его в запрос `@...`. 

**Короткие имена в `@`:** Вы можете писать `@main.py`. Но если в сессии
окажется несколько файлов с таким именем (например, `replai_111_main.py` и
`replai_222_main.py`), `replai` **не будет угадывать**. Он выдаст ошибку:
`⚠ Неоднозначное имя @main.py. Найдено 2 файла. Укажите полное имя из /list.`
Это защищает от порчи не того файла.

#### Жизненный цикл файлов (48 часов)
Google Files API удаляет файлы через 48 часов. `replai` автоматически
отслеживает `expires_at`. Если вы вернётесь через 3 дня и запустите `/apply`,
скрипт корректно обработает «протухшие» файлы, не удаляя ваши локальные копии.

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
| `--project-max-file-bytes` | `6_000_000` (6 МБ) |
| `--project-max-total-bytes` | `500_000_000` (500 МБ) |
| `--project-max-files` | `200` |

> **Примечание:** Лимиты 6 МБ на файл и 500 МБ на проект настроены для комфортной работы с датасетами изображений (например, 78 картинок Таро).

---

### Команды REPL

| Команда | Назначение |
|---|---|
| `/list` | Список файлов (точные имена из AI Studio) |
| `/focus <pattern> [текст]` | Сфокусироваться на файле с инструкцией |
| `@<path>` в тексте | Упоминание облачной версии файла |
| `/send <path...> [--text X]` | Добавить новый файл(ы) и отправить |
| `/sync [path]` | Загрузить локальные файлы в облако (Local -> Cloud) |
| `/apply [pattern]` | **Smart Pull**: скачать файлы из облака на диск (Cloud -> Local) |
| `/save [path]` | Сохранить код/медиа ответа в архив `saved/` |
| `/md <file>` | Сохранить весь ответ как Markdown |
| `/forget <pattern>` | Убрать запись из сессии (detached-файлы удаляются и из облака) |
| `exit` / `/exit` | Выход |

#### `/sync [path]` — подготовка датасета (Local -> Cloud)

Сканирует папку `--project`. Если находит файлы, указанные в `.gitignore`
(например, `dataset/`), **спрашивает разрешение** на их синхронизацию (потому
что `.gitignore` — это для GitHub, а не для AI Studio). Загружает всё в Files API
и регистрирует в манифесте. **Ничего не отправляет модели.**

**Трехуровневое подтверждение загрузки:** (Все -> Папка -> Файл). Если скрипт
находит 78 новых файлов, он спросит «Загрузить все?». Если вы ответите `n`, он
сгруппирует по папкам: «Загрузить все 78 файлов в папке 'dataset'?». И только
если откажетесь от папки, начнется перебор по одному.

#### `/apply [pattern]` — Smart Pull (Cloud -> Local)

Переопределенная в v0.0.5 команда. Скачивает файлы из облака AI Studio на
локальный диск (через `client.files.download()`).

1. **`/apply` (без аргументов):** скачивает **все** файлы сессии в `--project`
   (или в папку `<session_dir>/downloads/`, если проект не задан).
2. **`/apply dataset/`:** скачивает только указанную папку.
3. **Обработка состояний:**
   - `ok` — пропускает (версии совпадают).
   - `out-of-sync` — предлагает перезаписать локальный файл облачным.
   - `detached` — скачивает из облака (восстанавливает).
   - `new-local` — файл есть на диске, но нет в облаке (например, протух).
     Предлагает `[Enter]` оставить или `[d]` **переместить в корзину** (`trash/`).
   - `lost` — предупреждает, что файл утерян безвозвратно.

#### `/forget <pattern>`

Умное удаление:
- Если файл **есть на диске**: удаляет только запись из `manifest.json`.
- Если файл **отсутствует на диске** (`detached`): удаляет запись из манифеста
  **и** вызывает `client.files.delete()` для очистки квоты в AI Studio.

#### `/save [path]` — архив последнего ответа

**Без аргумента:** все блоки кода + все медиа из последнего ответа.
**При совпадении имени:** `[o]` перезаписать / `[k]` новый с ID хода
(`main_t003.py`) / `[s]` пропустить.

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

**Version:** `0.0.5`. **Python:** `3.10+`.

### Design principles

1. **No Magic.** `/list` shows exact names from Google AI Studio. If an `@name`
   is ambiguous (multiple files with same basename), the script errors out instead
   of guessing.
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
| `--project-max-file-bytes` | `6_000_000` (6 MB) |
| `--project-max-total-bytes` | `500_000_000` (500 MB) |

---

### REPL commands

| Command | Purpose |
|---|---|
| `/list` | List session files (exact names from AI Studio) |
| `/focus <pattern> [text]` | Focus on a file with instruction |
| `@<path>` in text | Mention the storage version of the file |
| `/send <path...> [--text X]` | Add new file(s) to session and send |
| `/sync [path]` | Upload local files to cloud (Local -> Cloud) |
| `/apply [pattern]` | **Smart Pull**: download files from cloud to disk (Cloud -> Local) |
| `/save [path]` | Save code/media from last response to `saved/` archive |
| `/md <file>` | Save the entire response as Markdown |
| `/forget <pattern>` | Remove entry (detached files also deleted from cloud) |

#### `/apply [pattern]` — Smart Pull (Cloud -> Local)

Downloads files from AI Studio to disk (via `client.files.download()`).

1. `/apply` — downloads all session files to `--project` (or `<session_dir>/downloads/`).
2. `/apply dataset/` — downloads only the specified folder.
3. **State handling:**
   - `ok` — skip.
   - `out-of-sync` — ask to overwrite local file.
   - `detached` — download from cloud (restore).
   - `new-local` — file exists on disk, but not in cloud. Asks to keep `[Enter]` or move to `trash/` `[d]`.
   - `lost` — warn the user.

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