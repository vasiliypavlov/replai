# replai v0.0.5
# Terminal REPL for Gemini — project-aware code chat with file round-trip.
# State dir: ./replai/ (visible, portable). No hidden dirs.
# License: MIT

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import mimetypes
import os
import re
import shlex
import shutil
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
    from prompt_toolkit.history import InMemoryHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

if HAS_PROMPT_TOOLKIT:
    for _seq in (
        "\x1b[13;2u",     # Kitty keyboard protocol
        "\x1b[27;2;13~",   # xterm modifyOtherKeys=2
        "\x1b[27;2;13u",   # CSI-u variant
        "\x1b[13;2~",      # Linux / Cygwin variant
    ):
        ANSI_SEQUENCES[_seq] = (Keys.Escape, Keys.ControlM)

try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False

from google import genai
from google.genai import types

__version__ = "0.0.5"

# ─── Localization (i18n) ──────────────────────────────────────────────────
CURRENT_LANG = os.environ.get("REPLAI_LANG", "ru").lower().strip()
if CURRENT_LANG not in ("en", "eng", "english"):
    CURRENT_LANG = "ru"
else:
    CURRENT_LANG = "en"

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "cli_desc": "Терминальный REPL для Gemini — контекстный чат с файлами проекта.",
        "cli_epilog": (
            "Запуск без флагов в TTY показывает меню сессий.\n"
            "--new — принудительно новая сессия (без меню).\n"
            "При выходе (exit/quit/Ctrl+D) генерируется summary сессии\n"
            "(если не указан --no-summary).\n"
        ),
        "api_key_help": "Путь к файлу с API-ключом",
        "model_help": "Модель Gemini (default: %(default)s)",
        "temp_help": "Температура (default: %(default)s)",
        "project_help": "Файл, папка или .zip с исходниками проекта",
        "resume_help": "Продолжить конкретную сессию (без ID — интерактивный выбор)",
        "continue_help": "Продолжить последнюю сессию без меню",
        "new_help": "Не показывать меню сессий, создать новую",
        "sync_help": "Синхронизировать файлы сессии с хранилищем (в TTY запускает чат)",
        "dry_run_help": "Показать операции без реальных действий",
        "sync_check_help": "Политика проверки синхронизации",
        "yes_help": "Автоподтверждение [y/N] и перезапись без вопросов",
        "force_help": "Перезаписывать файлы при /save и /apply без вопросов",
        "no_summary_help": "Не генерировать summary при выходе",
        "state_dir_help": "Директория состояния (default: %(default)s)",
        "lang_help": "Язык интерфейса: ru (по умолчанию) или en",
        "retries_help": "Максимум попыток отправки при 503/429 (default: %(default)s)",
        "retry_delay_help": "Начальная задержка backoff в секундах (default: %(default)s)",
        "project_include_ignored_help": "Синхронизировать файлы из .gitignore без подтверждения",
        "sync_clean_detached_help": "Разрешить удаление detached файлов из Files API для очистки квоты",
        "server_overloaded": "⚠ Сервер перегружен ({err}). Повтор через {delay:.1f} сек (попытка {attempt}/{max_retries})...",
        "key_perms_warn": "⚠ Файл ключа доступен группе/остальным: {path}. Рекомендуется: chmod 600 {path}",
        "key_read_err": "⚠ Не удалось прочитать {path}: {err}",
        "key_not_found": "Ошибка: API-ключ не найден.",
        "key_hint_path": "  → Укажите путь: --api-key PATH",
        "key_hint_file": "  → Или положите файл: {path}",
        "key_hint_env": "  → Или установите переменную окружения GEMINI_API_KEY",
        "key_file_missing": "Ошибка: файл ключа не найден: {path}",
        "key_file_empty": "⚠ Ошибка: файл с API-ключом найден, но он пуст: {path}",
        "key_file_empty_hint": "  → Вам нужно вставить ваш ключ Google API внутрь этого файла.",
        "key_instructions": (
            "🔑 Как получить API-ключ Google:\n"
            "  1. Перейдите в Google AI Studio: https://aistudio.google.com/app/apikey\n"
            "  2. Нажмите «Create API key» и скопируйте ключ.\n"
            "  3. Вставьте его в файл: {path}\n"
            "  4. Сохраните файл и запустите replai снова."
        ),
        "client_init_err": "Ошибка инициализации Gemini Client: {err}",
        "session_not_found": "Сессия не найдена: {id}",
        "session_load_err": "Сессия не загружена: {id}",
        "session_corrupt": "⚠ Манифест повреждён ({path}): {err}",
        "session_invalid_id": "Некорректный session_id: {value!r}. Ожидается YYYYMMDD_HHMMSS.",
        "session_id_mismatch": "⚠ Manifest session_id ({stored}) не совпадает с именем папки ({folder})",
        "file_skipped_size": "⚠ Пропущен (>{limit}): {path} ({size})",
        "proj_limit_bytes": "⚠ Достигнут лимит проекта ({limit}); остаток пропущен.",
        "proj_limit_files": "⚠ Достигнут лимит файлов ({limit}).",
        "extracting_zip": "Распаковка архива проекта в {dir}...",
        "scanning_proj": "Сканирование: {path}",
        "indexed_files": "  Индексировано файлов: {count}",
        "sync_banner": "Запуск синхронизации с хранилищем Gemini...",
        "sync_summary": "\nИтог синхронизации:",
        "sync_reuploaded": "✓ Перезалит: {name}",
        "sync_uploaded": "✓ Загружен: {name}",
        "sync_lvl1_prompt": "Загрузить все найденные файлы ({count})? [Y/n] (Y — да для всех, n — перейти к пошаговому выбору): ",
        "sync_lvl2_dir_prompt": "Папка '{dir}' ({count} файлов). Загрузить все файлы каталога? [y/N/a] (y — да для всех, N — пропустить папку, a — спрашивать по каждому): ",
        "sync_lvl3_file_prompt": "Загрузить файл '{name}'? [y/N]: ",
        "sync_ask_reupload": "⚠ {name} изменился. Перезалить? [y/N]: ",
        "sync_ask_upload": "Загрузить новый файл {name}? [y/N]: ",
        "sync_detached": "⚠ {name}: локальный файл не найден; используется копия из хранилища",
        "sync_lost": "✗ {name}: файл недоступен ни локально, ни в хранилище",
        "sync_out_of_sync": "⚠ Предупреждение: {name} изменён локально (out-of-sync).",
        "sync_ask_update": "⚠ {name} изменился на диске. Обновить в хранилище? [y/N]: ",
        "sync_gitignore_ask": "⚠ Найдены файлы, исключенные в .gitignore ({path}: {count} файлов). Синхронизировать их с AI Studio? [y/N/a]: ",
        "sync_detached_ask": "⚠ Обнаружено {count} отсоединённых (detached) файлов. Они есть в AI Studio, но отсутствуют локально. Удалить их из сессии и AI Studio (освободить квоту)? [y/N]: ",
        "sync_detached_deleted": "✓ Удалён из хранилища и сессии: {name}",
        "sync_detached_del_err": "⚠ Ошибка удаления файла из хранилища ({uri}): {err}",
        "project_conflict_ask": "⚠ В сессии был проект {old}. Вы указали {new}. Заменить контекст проекта? [Y/n]: ",
        "file_not_found": "Ошибка: файл не найден: {path}",
        "file_unsupported": "⚠ Пропущен неподдерживаемый тип файла: {path}",
        "file_read_err": "⚠ Ошибка чтения файла {path}: {err}",
        "archive_read_err": "⚠ Ошибка чтения архива {path}: {err}",
        "prompt_archive_start": "--- АРХИВ: {name} ---",
        "prompt_archive_end": "--- КОНЕЦ АРХИВА: {name} ---",
        "prompt_attached_header": "Прикреплённые материалы:\n",
        "prompt_instruction": "Инструкция: {text}",
        "prompt_default_analyze": "Проанализируй переданные материалы.",
        "warn_size_limit": "⚠ {path}: {size} > {limit} {unit}. Продолжить? [y/N]: ",
        "warn_total_size": "⚠ Суммарный объём запроса {size}. Продолжить? [y/N]: ",
        "mention_not_found": "⚠ @{target}: файл не найден в сессии",
        "mention_command_hint": "⚠ @{target}: это имя команды, а не файла. Используйте /{name}.",
        "mention_reupload": "⚠ @{target}: копия в хранилище {reason}. Загрузить актуальную версию с диска? [Y/n]: ",
        "mention_local_missing": "⚠ @{target}: локальный файл отсутствует на диске для загрузки.",
        "mention_reupload_failed": "⚠ @{target}: не удалось загрузить в хранилище.",
        "unresolved_mentions": "⚠ Не найдено в хранилище: {names}. Отправить запрос без этих файлов? [Y/n]: ",
        "menu_header": "Доступные сессии:",
        "menu_header_resume": "Выберите сессию для продолжения:",
        "menu_new_opt": "   0) Создать новую сессию\n",
        "menu_more": "  ... и ещё {count} старых сессий (используйте --resume <id>)\n",
        "menu_hint_new": "Номер или session_id (Enter — новая сессия): ",
        "menu_hint_cancel": "Номер или session_id (Enter — отмена): ",
        "menu_invalid": "Некорректный номер сессии. Повторите ввод.",
        "menu_empty": "Сохранённые сессии отсутствуют.",
        "continue_no_session": "Нет сохранённых сессий для --continue.",
        "session_summary_gen": "\nГенерирую краткое описание сессии...",
        "summary_success": "✓ Summary: {text}",
        "summary_fail": "⚠ Summary не сгенерировано",
        "summary_err": "⚠ Ошибка при генерации summary: {err}",
        "summary_aborted": "\n[Генерация summary прервана]",
        "summary_prompt": (
            "Проанализируй этот диалог и сгенерируй ОДНО короткое предложение "
            "(не более 100 символов) на русском языке, которое отражает суть "
            "работы в этой сессии (с {start} по {end}). "
            "Ответь только текстом предложения — без кавычек, без префиксов, "
            "без вводных слов вроде 'Суть сессии:', без markdown."
        ),
        "system_instruction": (
            "Ты — экспертный ассистент по программированию.\n"
            "Отвечай профессионально, структурированно и строго по делу.\n"
            "Всегда оформляй блоки с кодом в тройные обратные кавычки с явным указанием языка."
        ),
        "proj_structure_header": "Структура проекта",
        "proj_contents_header": "Содержимое файлов проекта",
        "banner_active": " replai v{ver} — сессия активна",
        "banner_commands": " Команды: /list /focus /send /save /md /apply /forget /sync /session /history /help | exit",
        "banner_mentions": " Упоминания файлов: @path прямо в тексте (версия из хранилища)",
        "banner_shortcuts": " Перенос строки: Shift+Enter / Alt+Enter. Отправка: Enter.",
        "user_prompt": "\nВы: ",
        "session_ended": "\nСессия завершена.",
        "operation_interrupted": "\n[Операция прервана]",
        "exec_error": "\n⚠ Ошибка выполнения: {err}",
        "unknown_cmd": "Неизвестная команда: {cmd}. Введите /help для справки.",
        "session_empty": "Сессия пуста.",
        "files_in_session": "\nФайлы в сессии ({count}):",
        "history_empty": "История сессии пуста.",
        "history_header": "\nИстория ходов ({count}):",
        "role_user": "Пользователь",
        "role_gemini": "Gemini",
        "save_exists_title": "\n⚠ Файл уже существует: {path}",
        "save_opt_overwrite": "  [o] перезаписать",
        "save_opt_keep": "  [k] сохранить как новый с ID хода (turn={turn:03d})",
        "save_opt_skip": "  [s] пропустить",
        "save_opt_choice": "Выбор [o/k/s]: ",
        "save_opt_invalid": "Введите o (overwrite), k (keep both) или s (skip).",
        "save_unchanged": "⏭ Без изменений: {path}",
        "save_success": "✓ Сохранён блок кода: {path}",
        "save_copied": "✓ Скопировано: {path}",
        "save_api_download_unsupported": "⚠ Скачивание из Gemini Files API для {name} пока не поддерживается.\n   URI: {uri}",
        "save_fail_content": "Не удалось получить содержимое файла: {name}",
        "save_not_found": "Не найдено ни в коде ответа модели, ни в сессии: {arg}",
        "save_no_blocks_or_media": "В последнем ответе модели нет блоков кода. (Для сохранения всего текста сообщения используйте: /md <файл.md>)",
        "save_found_count": "\nНайдено {count} блоков кода / медиа (turn={turn:03d}):",
        "save_ask_all": "Записать все найденные блоки кода на диск? [y/N]: ",
        "focus_usage": "Использование: /focus <pattern> [текст инструкции]",
        "focus_not_found": "Файл не найден в сессии: {pattern}",
        "focus_prep_failed": "Не удалось подготовить содержимое для {name}",
        "send_usage": 'Использование: /send <path...> [--text "сообщение"]',
        "send_no_files": "Не указаны файлы для отправки.",
        "md_usage": "Использование: /md <filename.md>",
        "md_no_response": "Ответ модели отсутствует.",
        "md_success": "✓ Текст ответа сохранён: {path} ({size})",
        "apply_usage": "Использование: /apply <src> [dst]  — src: имя/glob/папка; dst по умолчанию = --project",
        "apply_no_project": "Ошибка: dst не указан и нет --project. Укажите /apply <src> <dst>.",
        "apply_not_found": "Не найдено подходящих файлов в сессии: {pattern}",
        "apply_plan": "\nПрименить {count} файлов: {src} → {dst}",
        "apply_ask": "Применить изменения к проекту? [y/N]: ",
        "apply_conflict": "⚠ {target} существует. Перезаписать? [y/N]: ",
        "apply_local_missing": "⚠ {name}: исходный файл недоступен",
        "apply_success": "✓ {target}",
        "apply_err": "⚠ {target}: {err}",
        "apply_done": "Применено: {done}/{total}",
        "forget_usage": "Использование: /forget <pattern> [--dry-run]",
        "forget_not_found": "Не найдено файлов в сессии по паттерну: {pattern}",
        "forget_generated_warn": "⚠ {name} — сгенерированное медиа. Удалить запись (файл в media/ останется)? [y/N]: ",
        "forget_all_confirm": "Удалить все {count} записей из сессии? [y/N]: ",
        "forget_done": "✓ Забыто: {name}",
        "forget_dry_run": "  [dry-run] {name}",
        "media_saved_notify": "\n[{count} медиафайл(ов) автосохранено в media/]",
        "media_save_err": "⚠ Не удалось сохранить {name}: {err}",
        "files_api_failed": "⚠ Обработка файла в Google Files API провалена: {path}",
        "parse_err_paths": "Ошибка парсинга путей: {err}",
        "parse_err_syntax": "Ошибка синтаксиса аргументов: {err}",
        "age_just_now": "только что",
        "age_mins": "{n} мин назад",
        "age_hours": "{n} ч назад",
        "age_days": "{n} дн назад",
        "help_text": """
Команды replai:
  /list                      — список файлов сессии
  /focus <pattern> [текст]   — передать файл модели (#1, имя, glob) с инструкцией
  @<path> в тексте           — упоминание файла из хранилища (Files API)
  /send <path...> [--text X] — загрузить новый файл(ы) и отправить в контекст
  /save [path]               — сохранить только блоки КОДА из ответа модели в saved/
  /md <file>                 — сохранить весь ТЕКСТ ответа модели в Markdown
  /apply <src> [dst]         — выгрузить сохранённые файлы из saved/ в проект
  /forget <pattern>          — удалить запись (detached-файлы удаляются и из облака)
  /sync [path]               — синхронизировать проект или новую папку с хранилищем
  /session                   — статус и параметры сессии
  /history                   — журнал ходов текущей сессии
  /help                      — справка
  exit | quit | /exit        — завершение (генерирует summary)

Ввод текста:
  Shift+Enter / Alt+Enter    — мягкий перенос строки без отправки
  Enter                      — отправить сообщение модели
  Стрелки ↑ / ↓              — навигация по истории команд
""".strip(),
    },
    "en": {
        "cli_desc": "Terminal REPL for Gemini — project-aware code chat with file round-trip.",
        "cli_epilog": (
            "Starting without flags in a TTY displays the session menu.\n"
            "--new — force a new session (bypass menu).\n"
            "On exit (exit/quit/Ctrl+D), a session summary is generated\n"
            "(unless --no-summary is specified).\n"
        ),
        "api_key_help": "Path to API key file",
        "model_help": "Gemini model (default: %(default)s)",
        "temp_help": "Temperature (default: %(default)s)",
        "project_help": "Source file, directory, or .zip archive of the project",
        "resume_help": "Resume a specific session (interactive selection if no ID)",
        "continue_help": "Resume the last session without menu",
        "new_help": "Do not show session menu, create a new session",
        "sync_help": "Synchronize session files with storage (starts chat in TTY)",
        "dry_run_help": "Show actions without executing",
        "sync_check_help": "Sync verification policy",
        "yes_help": "Auto-confirm [y/N] prompts and overwrite without asking",
        "force_help": "Overwrite files on /save and /apply without prompting",
        "no_summary_help": "Do not generate summary on session exit",
        "state_dir_help": "State storage directory (default: %(default)s)",
        "lang_help": "UI language: ru (default) or en",
        "retries_help": "Max send attempts on 503/429 (default: %(default)s)",
        "retry_delay_help": "Initial backoff delay in seconds (default: %(default)s)",
        "project_include_ignored_help": "Sync .gitignore excluded files without prompting",
        "sync_clean_detached_help": "Allow deletion of detached files from Files API to free quota",
        "server_overloaded": "⚠ Server overloaded ({err}). Retrying in {delay:.1f}s (attempt {attempt}/{max_retries})...",
        "key_perms_warn": "⚠ Key file accessible by group/others: {path}. Recommended: chmod 600 {path}",
        "key_read_err": "⚠ Failed to read {path}: {err}",
        "key_not_found": "Error: API key not found.",
        "key_hint_path": "  → Specify path: --api-key PATH",
        "key_hint_file": "  → Or place file: {path}",
        "key_hint_env": "  → Or set GEMINI_API_KEY environment variable",
        "key_file_missing": "Error: API key file not found: {path}",
        "key_file_empty": "⚠ Error: API key file found, but it is empty: {path}",
        "key_file_empty_hint": "  → You need to paste your Google API key into this file.",
        "key_instructions": (
            "🔑 How to get a Google API key:\n"
            "  1. Go to Google AI Studio: https://aistudio.google.com/app/apikey\n"
            "  2. Click 'Create API key' and copy the key.\n"
            "  3. Paste it into the file: {path}\n"
            "  4. Save the file and run replai again."
        ),
        "client_init_err": "Failed to initialize Gemini Client: {err}",
        "session_not_found": "Session not found: {id}",
        "session_load_err": "Failed to load session: {id}",
        "session_corrupt": "⚠ Manifest corrupted ({path}): {err}",
        "session_invalid_id": "Invalid session_id: {value!r}. Expected YYYYMMDD_HHMMSS.",
        "session_id_mismatch": "⚠ Manifest session_id ({stored}) does not match folder ({folder})",
        "file_skipped_size": "⚠ Skipped (>{limit}): {path} ({size})",
        "proj_limit_bytes": "⚠ Project size limit reached ({limit}); remaining files skipped.",
        "proj_limit_files": "⚠ Project file count limit reached ({limit}).",
        "extracting_zip": "Extracting project archive to {dir}...",
        "scanning_proj": "Scanning: {path}",
        "indexed_files": "  Indexed files: {count}",
        "sync_banner": "Starting synchronization with Gemini storage...",
        "sync_summary": "\nSync Summary:",
        "sync_reuploaded": "✓ Re-uploaded: {name}",
        "sync_uploaded": "✓ Uploaded: {name}",
        "sync_lvl1_prompt": "Upload all {count} files to cloud? [Y/n] (Y — all, n — choose directories/files): ",
        "sync_lvl2_dir_prompt": "Folder '{dir}' ({count} files). Upload all files in this directory? [y/N/a] (y — yes for all, N — skip folder, a — ask each): ",
        "sync_lvl3_file_prompt": "Upload file '{name}'? [y/N]: ",
        "sync_ask_reupload": "⚠ {name} has changed. Re-upload? [y/N]: ",
        "sync_ask_upload": "Upload new file {name}? [y/N]: ",
        "sync_detached": "⚠ {name}: local file missing; using storage copy",
        "sync_lost": "✗ {name}: unavailable both locally and in storage",
        "sync_out_of_sync": "⚠ Warning: {name} was modified locally (out-of-sync).",
        "sync_ask_update": "⚠ {name} was modified on disk. Update in storage? [y/N]: ",
        "sync_gitignore_ask": "⚠ Found files excluded in .gitignore ({path}: {count} files). Sync them with AI Studio? [y/N/a]: ",
        "sync_detached_ask": "⚠ Detected {count} detached files (in cloud, missing locally). Delete them from session and AI Studio (free quota)? [y/N]: ",
        "sync_detached_deleted": "✓ Deleted from storage and session: {name}",
        "sync_detached_del_err": "⚠ Error deleting file from storage ({uri}): {err}",
        "project_conflict_ask": "⚠ Session was linked to {old}. You provided {new}. Replace project context? [Y/n]: ",
        "file_not_found": "Error: file not found: {path}",
        "file_unsupported": "⚠ Skipped unsupported file type: {path}",
        "file_read_err": "⚠ Error reading {path}: {err}",
        "archive_read_err": "⚠ Error reading archive {path}: {err}",
        "prompt_archive_start": "--- ARCHIVE: {name} ---",
        "prompt_archive_end": "--- END OF ARCHIVE: {name} ---",
        "prompt_attached_header": "Attached materials:\n",
        "prompt_instruction": "Instruction: {text}",
        "prompt_default_analyze": "Analyze the attached materials.",
        "warn_size_limit": "⚠ {path}: {size} > {limit} {unit}. Continue? [y/N]: ",
        "warn_total_size": "⚠ Total request volume {size}. Continue? [y/N]: ",
        "mention_not_found": "⚠ @{target}: file not found in session",
        "mention_command_hint": "⚠ @{target}: this is a command name, not a file. Use /{name}.",
        "mention_reupload": "⚠ @{target}: storage copy {reason}. Re-upload local version? [Y/n]: ",
        "mention_local_missing": "⚠ @{target}: local file unavailable for re-upload.",
        "mention_reupload_failed": "⚠ @{target}: failed to re-upload to storage.",
        "unresolved_mentions": "⚠ Not found in storage: {names}. Send without these mentions? [Y/n]: ",
        "menu_header": "Available sessions:",
        "menu_header_resume": "Select a session to resume:",
        "menu_new_opt": "   0) Create a new session\n",
        "menu_more": "  ... and {count} more older sessions (use --resume <id>)\n",
        "menu_hint_new": "Enter number or session_id (Enter — new session): ",
        "menu_hint_cancel": "Enter number or session_id (Enter — cancel): ",
        "menu_invalid": "Invalid session number. Please try again.",
        "menu_empty": "No saved sessions found.",
        "continue_no_session": "No sessions to continue.",
        "session_summary_gen": "\nGenerating brief session summary...",
        "summary_success": "✓ Summary: {text}",
        "summary_fail": "⚠ Summary was not generated",
        "summary_err": "⚠ Error generating summary: {err}",
        "summary_aborted": "\n[Summary generation aborted]",
        "summary_prompt": (
            "Analyze this dialogue and generate ONE concise sentence "
            "(under 100 characters) in English summarizing the work done "
            "in this session (from {start} to {end}). "
            "Reply strictly with the summary sentence — no quotes, no prefixes, "
            "no introductory words like 'Session summary:', no markdown."
        ),
        "system_instruction": (
            "You are an expert software engineering assistant.\n"
            "Respond professionally, structured, and strictly to the point.\n"
            "Always wrap code blocks in triple backticks with explicit language identifiers."
        ),
        "proj_structure_header": "Project Structure",
        "proj_contents_header": "Project File Contents",
        "banner_active": " replai v{ver} — session active",
        "banner_commands": " Commands: /list /focus /send /save /md /apply /forget /sync /session /history /help | exit",
        "banner_mentions": " File mentions: @path directly in text (storage copy)",
        "banner_shortcuts": " Newline: Shift+Enter / Alt+Enter. Submit: Enter.",
        "user_prompt": "\nYou: ",
        "session_ended": "\nSession finished.",
        "operation_interrupted": "\n[Operation interrupted]",
        "exec_error": "\n⚠ Execution error: {err}",
        "unknown_cmd": "Unknown command: {cmd}. Type /help for assistance.",
        "session_empty": "Session is empty.",
        "files_in_session": "\nFiles in session ({count}):",
        "history_empty": "Session history is empty.",
        "history_header": "\nTurn history ({count}):",
        "role_user": "User",
        "role_gemini": "Gemini",
        "save_exists_title": "\n⚠ File already exists: {path}",
        "save_opt_overwrite": "  [o] overwrite",
        "save_opt_keep": "  [k] save as new with turn ID (turn={turn:03d})",
        "save_opt_skip": "  [s] skip",
        "save_opt_choice": "Choice [o/k/s]: ",
        "save_opt_invalid": "Please enter o (overwrite), k (keep both), or s (skip).",
        "save_unchanged": "⏭ Unchanged: {path}",
        "save_success": "✓ Code block saved: {path}",
        "save_copied": "✓ Copied: {path}",
        "save_api_download_unsupported": "⚠ Downloading from Gemini Files API for {name} not supported yet.\n   URI: {uri}",
        "save_fail_content": "Failed to retrieve content for file: {name}",
        "save_not_found": "Found neither in model code response nor in session: {arg}",
        "save_no_blocks_or_media": "No code blocks found in model response. (To save entire message text, use: /md <file.md>)",
        "save_found_count": "\nFound {count} code blocks / media (turn={turn:03d}):",
        "save_ask_all": "Save all extracted code blocks to disk? [y/N]: ",
        "focus_usage": "Usage: /focus <pattern> [instruction text]",
        "focus_not_found": "File not found in session: {pattern}",
        "focus_prep_failed": "Failed to prepare content for {name}",
        "send_usage": 'Usage: /send <path...> [--text "message"]',
        "send_no_files": "No files specified for sending.",
        "md_usage": "Usage: /md <filename.md>",
        "md_no_response": "Model response is missing.",
        "md_success": "✓ Response text saved: {path} ({size})",
        "apply_usage": "Usage: /apply <src> [dst]  — src: name/glob/dir; dst defaults to --project",
        "apply_no_project": "Error: dst not specified and no --project. Use /apply <src> <dst>.",
        "apply_not_found": "No matching session files found: {pattern}",
        "apply_plan": "\nApply {count} files: {src} → {dst}",
        "apply_ask": "Apply changes to project? [y/N]: ",
        "apply_conflict": "⚠ {target} exists. Overwrite? [y/N]: ",
        "apply_local_missing": "⚠ {name}: source file unavailable",
        "apply_success": "✓ {target}",
        "apply_err": "⚠ {target}: {err}",
        "apply_done": "Applied: {done}/{total}",
        "forget_usage": "Usage: /forget <pattern> [--dry-run]",
        "forget_not_found": "No files matched pattern: {pattern}",
        "forget_generated_warn": "⚠ {name} is generated media. Remove entry (media/ file kept)? [y/N]: ",
        "forget_all_confirm": "Remove all {count} entries from session? [y/N]: ",
        "forget_done": "✓ Forgotten: {name}",
        "forget_dry_run": "  [dry-run] {name}",
        "media_saved_notify": "\n[{count} media file(s) auto-saved to media/]",
        "media_save_err": "⚠ Failed to save {name}: {err}",
        "files_api_failed": "⚠ File processing failed in Google Files API: {path}",
        "parse_err_paths": "Path parsing error: {err}",
        "parse_err_syntax": "Argument syntax error: {err}",
        "age_just_now": "just now",
        "age_mins": "{n}m ago",
        "age_hours": "{n}h ago",
        "age_days": "{n}d ago",
        "help_text": """
replai commands:
  /list                      — list session files
  /focus <pattern> [text]    — focus model on file (#1, name, glob) with instruction
  @<path> in text            — mention file from storage (Files API)
  /send <path...> [--text X] — upload new file(s) and send to context
  /save [path]               — save only CODE blocks from response into saved/
  /md <file>                 — export full response TEXT to Markdown
  /apply <src> [dst]         — export files from saved/ into actual project
  /forget <pattern>          — remove entry (detached files also deleted from cloud)
  /sync [path]               — synchronize project or new folder with storage
  /session                   — session status and parameters
  /history                   — turn history of current session
  /help                      — cheatsheet
  exit | quit | /exit        — exit (generates summary)

Input shortcuts:
  Shift+Enter / Alt+Enter    — soft newline without submitting
  Enter                      — send prompt to model
  Arrow keys ↑ / ↓           — command history navigation
""".strip(),
    },
}


def tr(key: str, **kwargs) -> str:
    text = STRINGS.get(CURRENT_LANG, STRINGS["ru"]).get(key, STRINGS["ru"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


# ─── Constants ────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_STATE_DIR = "replai"
SESSIONS_SUBDIR = "sessions"
MANIFEST_FILE = "manifest.json"
LOG_FILE = "log.txt"
SAVED_SUBDIR = "saved"
MEDIA_SUBDIR = "media"
SESSION_MENU_LIMIT = 20

_SESSION_ID_RE = re.compile(r"^\d{8}_\d{6}$")
_MENTION_RE = re.compile(r'(?:^|(?<=[\s(\["]))@(?:"([^"]+)"|((?:[^\s"()\[\]\\]|\\.)+))')

TEXT_EXTENSIONS = {
    ".py", ".pyi", ".pyx", ".md", ".rst", ".txt",
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".xml", ".html", ".htm", ".css", ".scss", ".sass",
    ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx",
    ".sh", ".bash", ".zsh", ".fish", ".ps1",
    ".sql", ".dockerfile", ".makefile", ".cmake", ".bat",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".rs", ".go",
    ".java", ".kt", ".kts", ".swift", ".php", ".rb",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus"}
ARCHIVE_EXTENSIONS = {".zip"}

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".venv", "venv", "env", "virtualenv",
    "node_modules", "dist", "build",
    ".idea", ".vscode",
}
EXCLUDED_FILE_PATTERNS = {
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.dylib", "*.o", "*.a",
    "*.log", "*.tmp", "*.bak", "*.swp", "*.swo", "*.egg-info",
}

DEFAULT_LIMITS = {
    "image_mb": 20, "video_mb": 500, "text_kb": 200,
    "archive_mb": 200, "inline_total_mb": 18, "request_total_mb": 500,
}

_REPL_COMMANDS = {
    "list", "focus", "send", "save", "md", "session", "history",
    "help", "exit", "quit", "apply", "forget", "sync",
}

_MIME_TO_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/webp": ".webp", "image/gif": ".gif", "image/bmp": ".bmp",
    "image/tiff": ".tiff", "image/svg+xml": ".svg",
    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
    "video/x-msvideo": ".avi", "video/x-matroska": ".mkv",
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a",
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/ogg": ".ogg",
    "audio/flac": ".flac", "audio/aac": ".aac",
}


# ─── Small utilities ──────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def human_size(n: int | float) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024.0:
            return f"{x:.1f} {unit}"
        x /= 1024.0
    return f"{x:.1f} PB"


def _parse_iso_to_naive_local(iso_str: str) -> datetime | None:
    if not iso_str:
        return None
    try:
        clean = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is not None:
            return dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _time_of(iso_str: str) -> str:
    dt = _parse_iso_to_naive_local(iso_str)
    return dt.strftime("%H:%M") if dt else "?"


def _human_age(created_iso: str) -> str:
    created = _parse_iso_to_naive_local(created_iso)
    if not created:
        return "?"
    delta = datetime.now() - created
    if delta.days > 0:
        return tr("age_days", n=delta.days)
    hours = delta.seconds // 3600
    if hours > 0:
        return tr("age_hours", n=hours)
    mins = delta.seconds // 60
    if mins > 0:
        return tr("age_mins", n=mins)
    return tr("age_just_now")


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_display_name(name: str) -> str:
    s = (name or "").replace("\\", "/")
    s = re.sub(r"^(?:replai_)+", "replai_", s)
    m = re.match(r"^replai_\d{8}_\d{6}_(.+)$", s)
    if m:
        return m.group(1)
    m2 = re.match(r"^\d{8}_\d{6}_(?!(?:turn\d{3}_\d{3}))(.+)$", s)
    if m2:
        return m2.group(1)
    return s


def make_display_name(session_id: str, rel_path: str) -> str:
    sid = session_id[len("replai_"):] if session_id.startswith("replai_") else session_id
    rel_path = rel_path.replace(os.sep, "/").lstrip("/")
    return f"replai_{sid}_{rel_path}"


def ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def atomic_write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    ensure_dir(os.path.dirname(path) or ".")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    try:
        ans = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not ans:
        return default
    return ans in ("y", "yes", "д", "да")


def is_explicit_path(p: str) -> bool:
    return bool(
        os.path.isabs(p)
        or p.startswith(("./", "../", "~", ".\\", "..\\"))
        or re.match(r"^[a-zA-Z]:[\\/]", p)
    )


def parse_send_args(body: str) -> tuple[list[str], str]:
    body = body.strip()
    if not body:
        return [], ""

    if "--text" in body.split():
        idx = body.find("--text")
        pre = body[:idx].strip()
        post = body[idx + len("--text"):].strip()
        try:
            raw_paths = shlex.split(pre)
        except ValueError as e:
            raise ValueError(tr("parse_err_paths", err=e)) from e
        paths = [t for t in raw_paths if t]
        return paths, post

    try:
        tokens = shlex.split(body)
    except ValueError as e:
        raise ValueError(tr("parse_err_syntax", err=e)) from e

    paths: list[str] = []
    text_parts: list[str] = []
    collecting_paths = True
    for tok in tokens:
        if collecting_paths:
            if os.path.exists(tok):
                paths.append(tok)
            elif not paths:
                paths.append(tok)
                collecting_paths = False
            else:
                collecting_paths = False
                text_parts.append(tok)
        else:
            text_parts.append(tok)
    return paths, " ".join(text_parts)


def send_message_with_retry(chat, payload, max_retries: int = 4, initial_delay: float = 2.0):
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return chat.send_message(payload)
        except Exception as e:
            err = str(e)
            transient = any(c in err for c in (
                "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
                "Deadline Exceeded", "deadline exceeded",
                "timeout", "Timeout", "high demand", "overloaded",
            ))
            if transient and attempt < max_retries:
                print(tr("server_overloaded", err=err.splitlines()[0],
                         delay=delay, attempt=attempt, max_retries=max_retries))
                time.sleep(delay)
                delay *= 2
            else:
                raise


def lang_to_ext(lang: str) -> str:
    return {
        "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts", "bash": ".sh", "sh": ".sh",
        "json": ".json", "yaml": ".yml", "yml": ".yml", "toml": ".toml",
        "html": ".html", "css": ".css", "sql": ".sql", "markdown": ".md",
        "md": ".md", "c": ".c", "cpp": ".cpp", "rust": ".rs", "rs": ".rs",
        "go": ".go", "java": ".java",
    }.get((lang or "").lower(), ".txt")


def mime_to_ext(mime: str) -> str:
    mime = (mime or "").lower().split(";")[0].strip()
    if mime in _MIME_TO_EXT:
        return _MIME_TO_EXT[mime]
    if "/" in mime:
        subtype = mime.split("/", 1)[1].split("+")[0]
        return "." + re.sub(r"[^a-z0-9]+", "_", subtype.lower())
    return ".bin"


def classify_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in ARCHIVE_EXTENSIONS:
        return "archive"
    if ext in TEXT_EXTENSIONS:
        return "text"
    mime, _ = mimetypes.guess_type(path)
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("text/"):
            return "text"
        if mime in ("application/json", "application/xml", "application/javascript"):
            return "text"
    return "skip"


def file_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _is_image_model(model_name: str) -> bool:
    return "image" in (model_name or "").lower()


# ─── API key ──────────────────────────────────────────────────────────────
def _read_key_file(path: str) -> str | None:
    try:
        st = os.stat(path)
        if sys.platform != "win32" and (st.st_mode & 0o077):
            print(tr("key_perms_warn", path=path), file=sys.stderr)
    except OSError:
        pass
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
        return key or None
    except OSError as e:
        print(tr("key_read_err", path=path, err=e), file=sys.stderr)
        return None


def load_api_key(cli_path: str | None) -> str | None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(script_dir, "api-key.txt")

    if cli_path:
        if not os.path.isfile(cli_path):
            print(tr("key_file_missing", path=cli_path), file=sys.stderr)
            print(tr("key_instructions", path=cli_path), file=sys.stderr)
            return None
        key = _read_key_file(cli_path)
        if not key:
            print(tr("key_file_empty", path=cli_path), file=sys.stderr)
            print(tr("key_file_empty_hint"), file=sys.stderr)
            print(tr("key_instructions", path=cli_path), file=sys.stderr)
            return None
        return key

    if os.path.isfile(default_path):
        key = _read_key_file(default_path)
        if not key:
            print(tr("key_file_empty", path=default_path), file=sys.stderr)
            print(tr("key_file_empty_hint"), file=sys.stderr)
            print(tr("key_instructions", path=default_path), file=sys.stderr)
            return None
        return key

    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(var)
        if val:
            return val.strip()

    print(tr("key_not_found"), file=sys.stderr)
    print(tr("key_hint_path"), file=sys.stderr)
    print(tr("key_hint_file", path=default_path), file=sys.stderr)
    print(tr("key_hint_env"), file=sys.stderr)
    print(tr("key_instructions", path=default_path), file=sys.stderr)
    return None


# ─── State dirs ───────────────────────────────────────────────────────────
STATE_DIR = DEFAULT_STATE_DIR


def state_root() -> str:
    return ensure_dir(os.path.join(os.getcwd(), STATE_DIR))


def sessions_root() -> str:
    return ensure_dir(os.path.join(state_root(), SESSIONS_SUBDIR))


def session_dir(session_id: str) -> str:
    return os.path.join(sessions_root(), session_id)


def make_session_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ─── Project scanner ──────────────────────────────────────────────────────
def _is_excluded_filename(fn: str) -> bool:
    return any(fnmatch.fnmatch(fn, pat) for pat in EXCLUDED_FILE_PATTERNS)


def _load_gitignore(root: str):
    if not HAS_PATHSPEC:
        return None
    gi = os.path.join(root, ".gitignore")
    if not os.path.isfile(gi):
        return None
    try:
        with open(gi, "r", encoding="utf-8", errors="replace") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    except Exception:
        return None


def extract_project_zip(zip_path: str, target_dir: str) -> str:
    ensure_dir(target_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    return target_dir


def scan_project(
    root: str,
    max_file_bytes: int,
    max_total_bytes: int,
    max_files: int,
    follow_symlinks: bool = False,
    include_ide: bool = False,
    include_ignored: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Сканирует проект. Возвращает (included_files, gitignored_files)."""
    root = os.path.abspath(root)
    if os.path.isfile(root):
        kind = classify_file(root)
        if kind == "skip":
            return [], []
        return [{
            "rel_path": os.path.basename(root),
            "abs_path": root,
            "size": os.path.getsize(root),
            "kind": kind,
        }], []

    if not os.path.isdir(root):
        return [], []

    excluded = set(EXCLUDED_DIRS)
    if include_ide:
        excluded.discard(".idea")
        excluded.discard(".vscode")

    gitignore = _load_gitignore(root)
    results: list[dict] = []
    ignored_results: list[dict] = []
    total = 0
    visited_real: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        if follow_symlinks:
            real = os.path.realpath(dirpath)
            if real in visited_real:
                dirnames[:] = []
                continue
            visited_real.add(real)

        dirnames[:] = [
            d for d in dirnames
            if d not in excluded and not d.endswith(".egg-info")
        ]

        for fn in sorted(filenames):
            abs_p = os.path.join(dirpath, fn)
            if os.path.islink(abs_p) and not follow_symlinks:
                continue
            rel_p = os.path.relpath(abs_p, root).replace(os.sep, "/")
            if _is_excluded_filename(fn):
                continue
            try:
                sz = os.path.getsize(abs_p)
            except OSError:
                continue
            kind = classify_file(abs_p)
            if kind == "skip":
                continue
            if sz > max_file_bytes:
                print(tr("file_skipped_size", limit=human_size(max_file_bytes),
                         path=rel_p, size=human_size(sz)), file=sys.stderr)
                continue

            entry = {"rel_path": rel_p, "abs_path": abs_p, "size": sz, "kind": kind}

            is_git_ignored = bool(gitignore and gitignore.match_file(rel_p))
            if is_git_ignored and not include_ignored:
                ignored_results.append(entry)
                continue

            if total + sz > max_total_bytes:
                print(tr("proj_limit_bytes", limit=human_size(max_total_bytes)), file=sys.stderr)
                return results, ignored_results

            if len(results) >= max_files:
                print(tr("proj_limit_files", limit=max_files), file=sys.stderr)
                return results, ignored_results

            results.append(entry)
            total += sz

    return results, ignored_results


# ─── Manifest ─────────────────────────────────────────────────────────────
class Manifest:
    def __init__(self, sdir: str, data: dict):
        self.sdir = sdir
        self.path = os.path.join(sdir, MANIFEST_FILE)
        self.data = data

    @classmethod
    def new(cls, sdir, session_id, model, project_path):
        if not _SESSION_ID_RE.match(session_id):
            raise ValueError(tr("session_invalid_id", value=session_id))
        ensure_dir(sdir)
        return cls(sdir, {
            "session_id": session_id,
            "version": __version__,
            "created": now_iso(),
            "last_updated": now_iso(),
            "model": model,
            "project_path": os.path.abspath(project_path) if project_path else None,
            "summary": None,
            "summary_at": None,
            "files": [],
            "history": [],
        })

    @classmethod
    def load(cls, sdir):
        p = os.path.join(sdir, MANIFEST_FILE)
        if not os.path.isfile(p):
            p2 = p + ".tmp"
            if os.path.isfile(p2):
                p = p2
            else:
                return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(tr("session_corrupt", path=p, err=e), file=sys.stderr)
            return None
        folder = os.path.basename(sdir.rstrip("/\\"))
        stored = data.get("session_id")
        if stored and stored != folder:
            print(tr("session_id_mismatch", stored=stored, folder=folder), file=sys.stderr)
        return cls(sdir, data)

    def save(self):
        self.data["last_updated"] = now_iso()
        atomic_write_json(self.path, self.data)

    def files(self) -> list[dict]:
        return self.data.get("files", [])

    def add_file(self, entry: dict) -> None:
        existing = self.find_by_display_name(entry["display_name"])
        if existing:
            old_sha = existing.get("local_sha256")
            new_sha = entry.get("local_sha256")
            if old_sha and new_sha and old_sha != new_sha:
                existing.pop("files_api_uri", None)
                existing.pop("files_api_sha256", None)
                existing.pop("expires_at", None)
                existing.pop("uploaded_at", None)
            existing.update(entry)
        else:
            self.data.setdefault("files", []).append(entry)

    def find_by_display_name(self, display_name: str) -> dict | None:
        for f in self.files():
            if f.get("display_name") == display_name:
                return f
        return None

    def find_file(self, query: str) -> dict | None:
        matches = self.find_all_files(query)
        return matches[0] if matches else None

    def find_all_files(self, query: str) -> list[dict]:
        files = self.files()
        if not files or not query:
            return []

        # Поддержка поиска по индексу #1, #2 и т.д.
        raw_idx = query.lstrip("#")
        if raw_idx.isdigit():
            idx = int(raw_idx) - 1
            if 0 <= idx < len(files):
                return [files[idx]]

        query_clean = query.strip("\"'").replace("\\", "/")
        query_norm = normalize_display_name(query_clean)

        matched = []
        for f in files:
            disp_name = f.get("display_name", "")
            fn = normalize_display_name(disp_name)
            name_base = f.get("name", "")
            
            # 1. Точное совпадение (введено полное имя из /list, короткое имя или базовое)
            if query_clean == disp_name or query_norm == fn or query_clean == fn or query_clean == name_base:
                matched.append(f)
                
            # 2. Поиск по маске (glob) - проверяем и полное имя, и нормализованное
            elif fnmatch.fnmatch(disp_name, query_clean) or fnmatch.fnmatch(fn, query_clean) or fnmatch.fnmatch(name_base, query_clean):
                matched.append(f)
                
            # 3. Поиск по папке (введено имя папки, возможно с префиксом из /list)
            elif fn.startswith(query_norm.rstrip("/") + "/"):
                matched.append(f)

        return matched


# ─── Session log ──────────────────────────────────────────────────────────
class SessionLog:
    def __init__(self, path: str):
        self.path = path
        ensure_dir(os.path.dirname(path) or ".")
        self._f = open(path, "a", encoding="utf-8")

    def write(self, tag: str, text: str, ts: datetime | None = None, turn: int | None = None) -> None:
        ts = ts or datetime.now()
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        turn_str = f"[turn:{turn:03d}] " if turn is not None else ""
        self._f.write(f"[{ts_str}] {turn_str}[{tag}] {text}\n")
        self._f.flush()

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass


def _next_turn(manifest: Manifest) -> int:
    max_turn = 0
    for t in manifest.data.get("history", []):
        tt = t.get("turn", 0)
        if isinstance(tt, int) and tt > max_turn:
            max_turn = tt
    return max_turn + 1


def record_turn(manifest: Manifest, log: SessionLog, role: str, text: str,
                ts: datetime | None = None, turn: int | None = None) -> int:
    ts = ts or datetime.now()
    history = manifest.data.setdefault("history", [])
    if turn is None:
        if role == "user" or not history:
            turn = _next_turn(manifest)
        else:
            turn = history[-1].get("turn", 1)
    log.write(role.upper(), text, ts=ts, turn=turn)
    history.append({
        "role": role, "text": text,
        "timestamp": ts.isoformat(timespec="seconds"),
        "turn": turn,
    })
    manifest.save()
    return turn


# ─── Sync state ───────────────────────────────────────────────────────────
def resolve_file_state(entry: dict) -> str:
    if entry.get("source") == "generated":
        return "ok"
    local = entry.get("local_path")
    has_local = bool(local) and os.path.isfile(local)
    has_api = bool(entry.get("files_api_uri"))
    if has_local and has_api:
        try:
            sha_now = sha256_of_file(local)
        except OSError:
            return "detached"
        return "ok" if sha_now == entry.get("local_sha256") else "out-of-sync"
    if has_local:
        return "new-local"
    if has_api:
        return "detached"
    return "lost"


def _upload(client, abs_path, display_name):
    try:
        uploaded = client.files.upload(file=abs_path, config={"display_name": display_name})
        state_prop = getattr(uploaded, "state", None)
        state_name = getattr(state_prop, "name", str(state_prop or ""))
        while state_name == "PROCESSING":
            time.sleep(1.5)
            uploaded = client.files.get(name=uploaded.name)
            state_prop = getattr(uploaded, "state", None)
            state_name = getattr(state_prop, "name", str(state_prop or ""))
        if state_name == "FAILED":
            print(tr("files_api_failed", path=abs_path), file=sys.stderr)
            return None, None, None
        uri = getattr(uploaded, "uri", None)
        sha = getattr(uploaded, "sha256_hash", None)
        exp = getattr(uploaded, "expiration_time", None)
        exp_str = exp.isoformat() if hasattr(exp, "isoformat") else (str(exp) if exp else None)
        return uri, sha, exp_str
    except Exception as e:
        print(tr("file_read_err", path=abs_path, err=e), file=sys.stderr)
        return None, None, None


def _delete_cloud_file(client, file_uri_or_name: str) -> bool:
    """Удаляет файл из Google Files API."""
    if not file_uri_or_name:
        return False
    m = re.search(r"files/[a-zA-Z0-9_\-]+", file_uri_or_name)
    resource_name = m.group(0) if m else file_uri_or_name
    try:
        client.files.delete(name=resource_name)
        return True
    except Exception as e:
        print(tr("sync_detached_del_err", uri=file_uri_or_name, err=e), file=sys.stderr)
        return False


def sync_session(
    client,
    manifest: Manifest,
    args: argparse.Namespace,
    dry_run: bool = False,
    extra_path: str | None = None,
) -> dict[str, int]:
    """
    Ядро синхронизации с трёхуровневым подтверждением (ТЗ v0.0.3/v0.0.4).
    """
    print(tr("sync_banner"))
    session_id = manifest.data.get("session_id", make_session_id())
    sdir = session_dir(session_id)

    # 1. Сканирование путей для добавления
    scan_targets = []
    if extra_path:
        scan_targets.append(os.path.abspath(extra_path))
    elif manifest.data.get("project_path"):
        scan_targets.append(manifest.data["project_path"])

    for target in scan_targets:
        if not os.path.exists(target):
            continue
        p_root = target
        if os.path.isfile(target) and zipfile.is_zipfile(target):
            extracted = os.path.join(sdir, "project_extracted")
            p_root = extract_project_zip(target, extracted)
        elif os.path.isfile(target):
            p_root = os.path.abspath(target)

        include_ignored_flag = getattr(args, "project_include_ignored", False)
        scanned_files, ignored_files = scan_project(
            p_root,
            max_file_bytes=args.project_max_file_bytes,
            max_total_bytes=args.project_max_total_bytes,
            max_files=args.project_max_files,
            follow_symlinks=args.project_follow_symlinks,
            include_ide=args.project_include_ide_dirs,
            include_ignored=include_ignored_flag,
        )

        # Обработка .gitignore
        if ignored_files and not include_ignored_flag:
            if sys.stdin.isatty() and not getattr(args, "yes", False):
                ans = input(tr("sync_gitignore_ask", path=os.path.basename(p_root), count=len(ignored_files))).strip().lower()
                if ans in ("y", "yes", "a", "all", "д", "да"):
                    scanned_files.extend(ignored_files)

        for f in scanned_files:
            rel = f["rel_path"]
            entry = {
                "name": os.path.basename(f["abs_path"]),
                "display_name": make_display_name(session_id, rel),
                "local_path": f["abs_path"],
                "abs_path": f["abs_path"],
                "local_sha256": sha256_of_file(f["abs_path"]),
                "kind": f["kind"],
                "size": f["size"],
                "mime": file_mime(f["abs_path"]),
            }
            manifest.add_file(entry)

    # 2. Выявление статусов и сбор файлов для загрузки
    summary = {"ok": 0, "out-of-sync": 0, "new-local": 0, "detached": 0, "lost": 0}
    detached_entries: list[dict] = []
    pending_uploads: list[dict] = []

    for entry in manifest.files():
        if entry.get("source") == "generated":
            continue
        state = resolve_file_state(entry)
        summary[state] = summary.get(state, 0) + 1
        name = normalize_display_name(entry.get("display_name", "?"))

        if state == "detached":
            detached_entries.append(entry)
        elif state == "lost":
            print(tr("sync_lost", name=name))
        elif state in ("new-local", "out-of-sync"):
            pending_uploads.append(entry)

    # 3. Трёхуровневый режим подтверждения загрузки
    if pending_uploads and not dry_run:
        def do_upload(entry):
            state_before = resolve_file_state(entry)
            name = normalize_display_name(entry.get("display_name", "?"))
            uri, sha, exp = _upload(client, entry["local_path"], entry["display_name"])
            if uri:
                entry["files_api_uri"] = uri
                entry["files_api_sha256"] = sha
                if exp: entry["expires_at"] = exp
                entry["local_sha256"] = sha256_of_file(entry["local_path"])
                entry["uploaded_at"] = now_iso()
                if state_before == "out-of-sync":
                    print(tr("sync_reuploaded", name=name))
                else:
                    print(tr("sync_uploaded", name=name))

        # Уровень 1: Загрузить абсолютно все файлы?
        upload_all = False
        if getattr(args, "yes", False):
            upload_all = True
        elif sys.stdin.isatty():
            upload_all = ask_yes_no(tr("sync_lvl1_prompt", count=len(pending_uploads)), default=True)

        if upload_all:
            for entry in pending_uploads:
                do_upload(entry)
        else:
            # Уровень 2 и 3: Группировка по папкам и поштучное подтверждение
            grouped = defaultdict(list)
            for entry in pending_uploads:
                rel = normalize_display_name(entry.get("display_name", entry.get("name", "")))
                d = os.path.dirname(rel)
                grouped[d].append(entry)

            for d, files in grouped.items():
                d_name = d if d else ("(root)" if CURRENT_LANG == "en" else "(корень)")
                dir_choice = "a"  # default: спрашивать по каждому

                if sys.stdin.isatty() and not getattr(args, "yes", False):
                    ans = input(tr("sync_lvl2_dir_prompt", count=len(files), dir=d_name)).strip().lower()
                    if ans in ("y", "yes", "д", "да"):
                        dir_choice = "y"
                    elif ans in ("n", "no", "н", "нет", ""):
                        dir_choice = "n"
                    elif ans in ("a", "ask", "all", "п", "поштучно"):
                        dir_choice = "a"

                if dir_choice == "n":
                    continue
                elif dir_choice == "y":
                    for entry in files:
                        do_upload(entry)
                else:
                    # Уровень 3: Поштучный запрос по каждому файлу
                    for entry in files:
                        f_name = normalize_display_name(entry.get("display_name", entry.get("name", "")))
                        if getattr(args, "yes", False) or ask_yes_no(tr("sync_lvl3_file_prompt", name=f_name), default=False):
                            do_upload(entry)

    elif dry_run and pending_uploads:
        for entry in pending_uploads:
            print(f"[dry-run] {resolve_file_state(entry)}: {entry.get('local_path')}")

    # 4. Обработка detached файлов
    if detached_entries and not dry_run:
        clean_detached_allowed = False
        if not sys.stdin.isatty():
            clean_detached_allowed = getattr(args, "sync_clean_detached", False)
        else:
            if getattr(args, "yes", False) and getattr(args, "sync_clean_detached", False):
                clean_detached_allowed = True
            else:
                clean_detached_allowed = ask_yes_no(tr("sync_detached_ask", count=len(detached_entries)), default=False)

        if clean_detached_allowed:
            for entry in list(detached_entries):
                d_name = normalize_display_name(entry.get("display_name", "?"))
                uri = entry.get("files_api_uri")
                if uri:
                    _delete_cloud_file(client, uri)
                try:
                    manifest.files().remove(entry)
                    print(tr("sync_detached_deleted", name=d_name))
                except ValueError:
                    pass
        else:
            for entry in detached_entries:
                print(tr("sync_detached", name=normalize_display_name(entry.get("display_name", "?"))))

    if not dry_run:
        manifest.save()

    print(tr("sync_summary"))
    for k in ("ok", "out-of-sync", "new-local", "detached", "lost"):
        print(f"  {k:<12}: {summary.get(k, 0)}")

    return summary


# ─── Content builders ────────────────────────────────────────────────────
def build_tree(project_files):
    tree = {}
    for f in project_files:
        parts = f["rel_path"].split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = f
    lines = []
    def walk(node, prefix=""):
        entries = sorted(node.keys(),
                         key=lambda k: (not isinstance(node[k], dict), k.lower()))
        for i, name in enumerate(entries):
            last = (i == len(entries) - 1)
            conn = "└── " if last else "├── "
            child = node[name]
            if isinstance(child, dict):
                lines.append(prefix + conn + name + "/")
                walk(child, prefix + ("    " if last else "│   "))
            else:
                lines.append(prefix + conn + name)
    walk(tree)
    return "\n".join(lines)


def build_system_instruction(project_files, project_root):
    parts = [tr("system_instruction")]
    if project_files:
        root_name = os.path.basename(project_root.rstrip(os.sep)) if project_root else "project"
        parts.append(f"\n## {tr('proj_structure_header')}\n\n```\n{root_name}/\n{build_tree(project_files)}\n```")
        parts.append(f"\n## {tr('proj_contents_header')}\n")
        for f in project_files:
            if f.get("kind") == "text":
                # Защита от контекстного переполнения (файлы больше 1 МБ не инлайнятся)
                if f.get("size", 0) > 1_000_000:
                    parts.append(f"\n### `{f['rel_path']}`\n\n[Файл пропущен в системном промпте из-за размера ({human_size(f.get('size', 0))}). Доступен по запросу через /focus или @.]")
                    continue
                
                p = f.get("abs_path") or f.get("local_path")
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    parts.append(f"\n### `{f['rel_path']}`\n\n```\n{content}\n```")
                except OSError as e:
                    parts.append(f"\n### `{f['rel_path']}`\n\n[{e}]")
    return "\n".join(parts)


def extract_code_blocks(text):
    """
    Строго извлекает только валидные блоки кода из тройных обратных кавычек.
    Исключает чистую прозу, списки и markdown-разметку.
    """
    blocks = []
    pattern = re.compile(r"```([\w+-]*)[^\n]*\r?\n(.*?)\r?\n```", re.DOTALL)
    fname_re = re.compile(
        r"^\s*(?:#|//|<!--|/\*|--)\s*(?:[Ff]ile:\s*)?([a-zA-Z0-9_.\-/\\]+\.[a-zA-Z0-9_]+)"
    )
    non_code_langs = {"markdown", "md", "text", "txt"}

    for i, m in enumerate(pattern.finditer(text)):
        lang = (m.group(1) or "").strip().lower()
        code = m.group(2).strip("\r\n")

        # Если блок пуст — пропускаем
        if not code.strip():
            continue

        filename = None
        for line in code.split("\n")[:4]:
            cm = fname_re.match(line)
            if cm:
                filename = cm.group(1).replace("\\", "/")
                break
        if not filename:
            prose = text[max(0, m.start() - 300):m.start()]
            pm = re.search(r"[`'\"]?([a-zA-Z0-9_.\-/\\]+\.[a-zA-Z0-9_]+)[`'\"]?\s*:?\s*$", prose.strip())
            if pm:
                filename = pm.group(1).replace("\\", "/")

        # Фильтрация: отсекаем обычный разговорный markdown/текст, если нет признаков кода
        if lang in non_code_langs and not filename:
            # Проверяем, есть ли явные признаки программного кода
            has_code_markers = any(kw in code for kw in ("def ", "import ", "class ", "function ", "const ", "var ", "{", "}", "SELECT ", "CREATE "))
            if not has_code_markers:
                continue

        if not filename:
            filename = f"block_{i+1}{lang_to_ext(lang)}"

        blocks.append({"lang": lang, "code": code, "filename": filename, "order": i})
    return blocks


def extract_response_content(response):
    text_parts, media = [], []
    for cand in (getattr(response, "candidates", None) or []):
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in (getattr(content, "parts", None) or []):
            txt = getattr(part, "text", None)
            if txt:
                text_parts.append(txt); continue
            inline = getattr(part, "inline_data", None)
            if inline is not None:
                raw = getattr(inline, "data", None)
                if raw:
                    if isinstance(raw, str):
                        try:
                            raw = base64.b64decode(raw)
                        except Exception:
                            raw = raw.encode("utf-8")
                    mime = getattr(inline, "mime_type", None) or "application/octet-stream"
                    media.append({"mime": mime, "bytes": raw})
                continue
            file_data = getattr(part, "file_data", None)
            if file_data is not None:
                uri = getattr(file_data, "file_uri", "") or ""
                mime = getattr(file_data, "mime_type", "") or ""
                if uri:
                    text_parts.append(f"[media reference: {mime} {uri}]")
    if not text_parts:
        try:
            t = getattr(response, "text", None)
            if t:
                text_parts.append(t)
        except Exception:
            pass
    return "\n".join(text_parts).strip(), media


def save_response_media(manifest, sdir, media_list, turn_number, ts):
    if not media_list:
        return []
    media_dir = ensure_dir(os.path.join(sdir, MEDIA_SUBDIR))
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    entries = []
    for i, m in enumerate(media_list, 1):
        ext = mime_to_ext(m["mime"])
        filename = f"{ts_str}_turn{turn_number:03d}_{i:03d}{ext}"
        target = os.path.join(media_dir, filename)
        counter = 1
        while os.path.exists(target):
            counter += 1
            filename = f"{ts_str}_turn{turn_number:03d}_{i:03d}_{counter}{ext}"
            target = os.path.join(media_dir, filename)
        tmp = target + ".tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(m["bytes"])
            os.replace(tmp, target)
        except OSError as e:
            try:
                if os.path.exists(tmp): os.remove(tmp)
            except Exception: pass
            print(tr("media_save_err", name=filename, err=e), file=sys.stderr)
            continue
        mime = m["mime"]
        kind = ("image" if mime.startswith("image/") else
                "video" if mime.startswith("video/") else
                "audio" if mime.startswith("audio/") else "binary")
        entry = {
            "name": filename, "display_name": filename,
            "local_path": target, "abs_path": target,
            "local_sha256": sha256_of_file(target),
            "kind": kind, "size": os.path.getsize(target),
            "mime": mime, "source": "generated", "turn": turn_number,
        }
        manifest.add_file(entry)
        entries.append(entry)
    if entries:
        manifest.save()
    return entries


def build_parts_for_entry(entry, warn_missing_local: bool = False):
    mime = entry.get("mime") or file_mime(entry.get("name", ""))
    local = entry.get("local_path")
    kind = entry.get("kind", "text")

    if kind == "text" and local and os.path.isfile(local):
        try:
            with open(local, "r", encoding="utf-8", errors="replace") as fh:
                return [types.Part.from_text(text=fh.read())]
        except OSError:
            pass

    uri = entry.get("files_api_uri")
    if kind == "text" and warn_missing_local and uri:
        if not (local and os.path.isfile(local)):
            print(f"⚠ {normalize_display_name(entry.get('display_name',''))}: "
                  f"локальный файл недоступен, используется версия из хранилища",
                  file=sys.stderr)

    if uri:
        return [types.Part.from_uri(file_uri=uri, mime_type=mime)]

    if local and os.path.isfile(local):
        try:
            with open(local, "rb") as fh:
                return [types.Part.from_bytes(data=fh.read(), mime_type=mime)]
        except OSError:
            return []
    return []


# ─── CLI ─────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="replai", description=tr("cli_desc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=tr("cli_epilog"),
    )
    p.add_argument("--version", action="version", version=f"replai {__version__}")
    p.add_argument("--api-key", metavar="PATH", help=tr("api_key_help"))
    p.add_argument("--model", default=DEFAULT_MODEL, help=tr("model_help"))
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help=tr("temp_help"))
    p.add_argument("--project", metavar="PATH", help=tr("project_help"))
    p.add_argument("--resume", "--session", metavar="SESSION_ID", nargs="?",
                   const="__interactive__", help=tr("resume_help"))
    p.add_argument("--continue", dest="continue_last", action="store_true",
                   help=tr("continue_help"))
    p.add_argument("--new", action="store_true", help=tr("new_help"))
    p.add_argument("--sync", action="store_true", help=tr("sync_help"))
    p.add_argument("--dry-run", action="store_true", help=tr("dry_run_help"))
    p.add_argument("--sync-check", choices=["auto", "warn", "off"], default="auto",
                   help=tr("sync_check_help"))
    p.add_argument("--project-include-ignored", action="store_true",
                   help=tr("project_include_ignored_help"))
    p.add_argument("--sync-clean-detached", action="store_true",
                   help=tr("sync_clean_detached_help"))
    p.add_argument("--yes", "-y", action="store_true", help=tr("yes_help"))
    p.add_argument("--force", action="store_true", help=tr("force_help"))
    p.add_argument("--no-summary", action="store_true", help=tr("no_summary_help"))
    p.add_argument("--state-dir", metavar="PATH", default=DEFAULT_STATE_DIR,
                   help=tr("state_dir_help"))
    p.add_argument("--lang", choices=["ru", "en"], default=None, help=tr("lang_help"))

    p.add_argument("--limit-image-mb", type=int, default=DEFAULT_LIMITS["image_mb"])
    p.add_argument("--limit-video-mb", type=int, default=DEFAULT_LIMITS["video_mb"])
    p.add_argument("--limit-text-kb", type=int, default=DEFAULT_LIMITS["text_kb"])
    p.add_argument("--limit-archive-mb", type=int, default=DEFAULT_LIMITS["archive_mb"])
    p.add_argument("--limit-inline-total-mb", type=int, default=DEFAULT_LIMITS["inline_total_mb"])
    p.add_argument("--limit-request-total-mb", type=int, default=DEFAULT_LIMITS["request_total_mb"])

    p.add_argument("--send-retries", type=int, default=4, help=tr("retries_help"))
    p.add_argument("--send-retry-delay", type=float, default=2.0, help=tr("retry_delay_help"))

    # Новые лимиты по спецификации Google Files API
    p.add_argument("--project-max-file-bytes", type=int, default=2_000_000_000)      # 2 ГБ
    p.add_argument("--project-max-total-bytes", type=int, default=20_000_000_000)   # 20 ГБ
    p.add_argument("--project-max-files", type=int, default=1000)                    # 1000 файлов
    p.add_argument("--project-follow-symlinks", action="store_true")
    p.add_argument("--project-include-ide-dirs", action="store_true")
    return p.parse_args(argv)


# ─── REPL state / helpers ────────────────────────────────────────────────
LAST_RESPONSE: dict = {"text": "", "media": [], "turn": 0}


def cmd_list(manifest: Manifest):
    files = manifest.files()
    if not files:
        print(tr("session_empty")); return
    print(tr("files_in_session", count=len(files)))
    type_col = "type" if CURRENT_LANG == "en" else "тип"
    status_col = "status" if CURRENT_LANG == "en" else "статус"
    size_col = "size" if CURRENT_LANG == "en" else "размер"
    name_col = "name" if CURRENT_LANG == "en" else "имя"
    print(f"{'#':>4}  {type_col:<7}  {'src':<5}  {status_col:<12}  {size_col:>9}  {name_col}")
    print("-" * 82)
    for i, f in enumerate(files, 1):
        name = f.get("display_name", "?")  # Показываем точное имя из AI Studio
        kind = f.get("kind", "?")
        src = "gen" if f.get("source") == "generated" else "in"
        status = "ok" if src == "gen" else resolve_file_state(f)
        size = human_size(f.get("size", 0))
        print(f"{i:>4}  {kind:<7}  {src:<5}  {status:<12}  {size:>9}  {name}")
    print()


def cmd_session_info(session_id, manifest: Manifest, args, project_root=None):
    n_files = len(manifest.files())
    n_turns = len(manifest.data.get("history", []))
    gen = [f for f in manifest.files() if f.get("source") == "generated"]
    gen_total = sum(f.get("size", 0) for f in gen)
    summary = manifest.data.get("summary") or "—"
    media_label = "media" if CURRENT_LANG == "en" else "медиа"
    proj_display = manifest.data.get('project_path') or '—'
    if proj_display != '—' and project_root and os.path.isdir(project_root) and \
       project_root != proj_display and "project_extracted" in project_root:
        proj_display += " (extracted)"
    print(f"""
Session ID:  {session_id}
Summary:     {summary}
Started:     {manifest.data.get('created', '?')}
Model:       {manifest.data.get('model', args.model)}
Project:     {proj_display}
Files:       {n_files}
Generated:   {len(gen)} {media_label} ({human_size(gen_total)})
Turns:       {n_turns}
Manifest:    {manifest.path}
Log:         {os.path.join(session_dir(session_id), LOG_FILE)}
Saved:       {os.path.join(session_dir(session_id), SAVED_SUBDIR)}
Media:       {os.path.join(session_dir(session_id), MEDIA_SUBDIR)}
Resume:      replai --resume {session_id}
""".strip())


def cmd_history(manifest: Manifest):
    history = manifest.data.get("history", [])
    if not history:
        print(tr("history_empty")); return
    print(tr("history_header", count=len(history)))
    for i, turn in enumerate(history[-15:], 1):
        role = tr("role_user") if turn.get("role") == "user" else tr("role_gemini")
        txt = turn.get("text", "").strip().replace("\n", " ")
        snippet = (txt[:80] + "...") if len(txt) > 80 else txt
        t_no = turn.get("turn", "?")
        print(f"  {i:>2}. [{turn.get('timestamp', '?')}] [turn:{t_no}] {role}: {snippet}")
    print()


def print_help():
    print(tr("help_text"))


def _resolve_save_target(target, turn, args):
    if not os.path.exists(target):
        return target
    if args.force or args.yes:
        return target
    stem, ext = os.path.splitext(target)
    print(tr("save_exists_title", path=target))
    print(tr("save_opt_overwrite"))
    print(tr("save_opt_keep", turn=turn))
    print(tr("save_opt_skip"))
    while True:
        try:
            ans = input(tr("save_opt_choice")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(); return None
        if ans in ("o", "overwrite", "п", "перезаписать"):
            return target
        if ans in ("k", "keep", "new", "н", "новый", ""):
            new_target = f"{stem}_t{turn:03d}{ext}"
            counter = 1
            while os.path.exists(new_target):
                counter += 1
                new_target = f"{stem}_t{turn:03d}_{counter}{ext}"
            return new_target
        if ans in ("s", "skip", "пропустить", "нет"):
            return None
        print(tr("save_opt_invalid"))


def _save_block(block, save_root, turn, args):
    """Сохраняет извлеченный блок кода в файл."""
    target = os.path.join(save_root, block["filename"])
    ensure_dir(os.path.dirname(target) or ".")
    if os.path.isfile(target):
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                if f.read().replace("\r\n", "\n") == block["code"].replace("\r\n", "\n"):
                    print(tr("save_unchanged", path=target))
                    return
        except OSError:
            pass
    final = _resolve_save_target(target, turn, args)
    if not final:
        return
    with open(final, "w", encoding="utf-8") as f:
        f.write(block["code"])
    print(tr("save_success", path=final))


def _save_session_entry(entry, save_root, turn, args):
    name = normalize_display_name(entry.get("display_name", "?"))
    target = os.path.join(save_root, name)
    ensure_dir(os.path.dirname(target) or ".")
    local = entry.get("local_path")
    if local and os.path.isfile(local):
        if os.path.isfile(target):
            try:
                if sha256_of_file(target) == sha256_of_file(local):
                    print(tr("save_unchanged", path=target)); return
            except OSError:
                pass
        final = _resolve_save_target(target, turn, args)
        if not final:
            return
        try:
            shutil.copy2(local, final)
            print(tr("save_copied", path=final))
            return
        except OSError as e:
            print(tr("file_read_err", path=local, err=e), file=sys.stderr)
    if entry.get("files_api_uri"):
        print(tr("save_api_download_unsupported",
                 name=name, uri=entry["files_api_uri"]))
        return
    print(tr("save_fail_content", name=name))


def cmd_save(manifest, save_root, arg, args):
    """
    Сохраняет строго блоки КОДА из последнего ответа модели (ТЗ п. 3).
    Приоритет: блоки кода из LAST_RESPONSE -> затем файлы сессии.
    """
    ensure_dir(save_root)
    turn = LAST_RESPONSE.get("turn", 0)

    # 1. Если аргумент передан: ищем блок кода в последнем ответе модели В ПЕРВУЮ ОЧЕРЕДЬ!
    if arg:
        if LAST_RESPONSE["text"]:
            for b in extract_code_blocks(LAST_RESPONSE["text"]):
                if b["filename"] == arg or os.path.basename(b["filename"]) == os.path.basename(arg):
                    _save_block(b, save_root, turn, args)
                    return
        # Только если такого блока кода нет — проверяем файл сессии
        entry = manifest.find_file(arg)
        if entry:
            entry_turn = entry.get("turn", turn) if isinstance(entry.get("turn"), int) else turn
            _save_session_entry(entry, save_root, entry_turn or turn, args)
            return

        print(tr("save_not_found", arg=arg))
        return

    # 2. Если вызван без аргументов: извлекаем блоки кода и медиа
    blocks = extract_code_blocks(LAST_RESPONSE["text"]) if LAST_RESPONSE["text"] else []
    media_entries = LAST_RESPONSE.get("media", [])

    if not blocks and not media_entries:
        print(tr("save_no_blocks_or_media"))
        return

    total = len(blocks) + len(media_entries)
    print(tr("save_found_count", count=total, turn=turn))
    i = 0
    for b in blocks:
        i += 1
        target = os.path.join(save_root, b["filename"])
        size = human_size(len(b["code"].encode("utf-8")))
        first_line = b["code"].split("\n")[0][:40]
        print(f"  {i}) [code]  {b['filename']} ({b['lang'] or 'code'}, {size}) -> {first_line}...")
    for m in media_entries:
        i += 1
        target = os.path.join(save_root, m["name"])
        print(f"  {i}) [media] {m['name']} ({m['mime']}, {human_size(m['size'])})")

    if not args.yes and not ask_yes_no(tr("save_ask_all"), default=False):
        return

    for b in blocks:
        _save_block(b, save_root, turn, args)
    for m in media_entries:
        m_turn = m.get("turn", turn) if isinstance(m.get("turn"), int) else turn
        _save_session_entry(m, save_root, m_turn or turn, args)


def cmd_focus(client, manifest, pattern, text_message, args):
    entry = manifest.find_file(pattern)
    if not entry:
        print(tr("focus_not_found", pattern=pattern)); return None
    state = resolve_file_state(entry)
    name = entry.get("display_name", "?")  # Полное имя для контекста
    if entry.get("source") != "generated":
        if state == "out-of-sync":
            if args.sync_check == "auto":
                if args.yes or ask_yes_no(tr("sync_ask_update", name=name), default=False):
                    uri, sha, exp = _upload(client, entry["local_path"], entry["display_name"])
                    if uri:
                        entry["files_api_uri"] = uri
                        entry["files_api_sha256"] = sha
                        if exp: entry["expires_at"] = exp
                        entry["local_sha256"] = sha256_of_file(entry["local_path"])
                        entry["uploaded_at"] = now_iso()
                        manifest.save()
            elif args.sync_check == "warn":
                print(tr("sync_out_of_sync", name=name))
        elif state == "detached":
            print(tr("sync_detached", name=name))
        elif state == "lost":
            print(tr("sync_lost", name=name)); return None
    parts = build_parts_for_entry(entry, warn_missing_local=True)
    if not parts:
        print(tr("focus_prep_failed", name=name)); return None
    header = f"[FOCUS] {name}"
    if entry.get("local_sha256"):
        header += f" (sha256:{entry['local_sha256'][:10]})"
    result = [types.Part.from_text(text=header)] + parts
    if text_message:
        result.append(types.Part.from_text(text=tr("prompt_instruction", text=text_message)))
    return result


def _ensure_storage_uri(client, manifest, entry, args) -> str | None:
    uri = entry.get("files_api_uri")
    expired = False
    if uri and entry.get("expires_at"):
        exp = _parse_iso_to_naive_local(entry["expires_at"])
        if exp and exp < datetime.now():
            expired = True
    if uri and not expired:
        return uri

    local = entry.get("local_path")
    name = normalize_display_name(entry.get("display_name", "?"))
    if not (local and os.path.isfile(local)):
        print(tr("mention_local_missing", target=name), file=sys.stderr)
        return None
    reason = ("expired" if expired else "missing") if CURRENT_LANG == "en" else ("истёк (48ч)" if expired else "отсутствует")
    if not args.yes and not ask_yes_no(tr("mention_reupload", target=name, reason=reason), default=True):
        return None
    new_uri, sha, exp = _upload(client, local, entry["display_name"])
    if not new_uri:
        print(tr("mention_reupload_failed", target=name), file=sys.stderr)
        return None
    entry["files_api_uri"] = new_uri
    entry["files_api_sha256"] = sha
    if exp: entry["expires_at"] = exp
    entry["local_sha256"] = sha256_of_file(local)
    entry["uploaded_at"] = now_iso()
    manifest.save()
    return new_uri


def resolve_mentions(client, manifest, text, args):
    parts = []
    seen = set()
    unresolved = []
    for m in _MENTION_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        target = raw.replace("\\ ", " ").strip()
        target_clean = target.rstrip(",.;:!?")
        entry = manifest.find_file(target_clean) or manifest.find_file(target)
        if entry is None:
            cmd_name = target_clean.lower().lstrip("@")
            if cmd_name in _REPL_COMMANDS:
                print(tr("mention_command_hint", target=target_clean, name=cmd_name), file=sys.stderr)
            else:
                print(tr("mention_not_found", target=target_clean), file=sys.stderr)
            unresolved.append(target_clean)
            continue

        uri = _ensure_storage_uri(client, manifest, entry, args)
        if not uri:
            unresolved.append(target_clean)
            continue

        disp_key = entry.get("display_name") or entry.get("name")
        if disp_key in seen:
            continue
        seen.add(disp_key)

        name = normalize_display_name(entry["display_name"])
        mime = entry.get("mime") or file_mime(name)
        label = "storage version" if CURRENT_LANG == "en" else "версия из хранилища"
        parts.append(types.Part.from_text(text=f"[MENTION] {name} ({label})"))
        parts.append(types.Part.from_uri(file_uri=uri, mime_type=mime))
    return text, parts, unresolved


def cmd_send(client, manifest, session_id, args, paths, text_message):
    valid_paths = []
    pre_total = 0
    for path in paths:
        if not os.path.isfile(path):
            print(tr("file_not_found", path=path), file=sys.stderr); return None, None
        valid_paths.append(path)
        pre_total += os.path.getsize(path)
    if pre_total > args.limit_request_total_mb * 1024 * 1024:
        if not (args.yes or ask_yes_no(tr("warn_total_size", size=human_size(pre_total)), default=False)):
            return None, None

    request_parts, embedded_text = [], []
    for path in valid_paths:
        sz = os.path.getsize(path)
        kind = classify_file(path)
        if kind == "skip":
            print(tr("file_unsupported", path=path), file=sys.stderr); continue
        mime = file_mime(path)
        limit_mb = None
        if kind == "image": limit_mb = args.limit_image_mb
        elif kind == "video": limit_mb = args.limit_video_mb
        elif kind == "archive": limit_mb = args.limit_archive_mb
        if limit_mb and sz > limit_mb * 1024 * 1024:
            if not (args.yes or ask_yes_no(tr("warn_size_limit", path=path,
                    size=human_size(sz), limit=limit_mb, unit="MB"), default=False)):
                continue
        if kind == "text" and sz > args.limit_text_kb * 1024:
            if not (args.yes or ask_yes_no(tr("warn_size_limit", path=path,
                    size=human_size(sz), limit=args.limit_text_kb, unit="KB"), default=False)):
                continue

        base_name = os.path.basename(path)
        display_name = make_display_name(session_id, base_name)
        entry = {
            "name": base_name, "display_name": display_name,
            "local_path": os.path.abspath(path), "abs_path": os.path.abspath(path),
            "local_sha256": sha256_of_file(path),
            "kind": kind, "size": sz, "mime": mime,
        }

        if kind == "archive":
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    embedded_text.append(tr("prompt_archive_start", name=base_name))
                    for info in zf.infolist():
                        if info.is_dir(): continue
                        z_ext = os.path.splitext(info.filename)[1].lower()
                        if z_ext in TEXT_EXTENSIONS:
                            try:
                                with zf.open(info.filename) as zh:
                                    data = zh.read().decode("utf-8", errors="replace")
                                embedded_text.append(f"\n## {info.filename}\n```\n{data}\n```")
                            except Exception: pass
                    embedded_text.append(tr("prompt_archive_end", name=base_name))
            except Exception as e:
                print(tr("archive_read_err", path=path, err=e), file=sys.stderr); continue
            manifest.add_file(entry); continue

        if kind == "text":
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                embedded_text.append(f"\n## {base_name}\n```\n{content}\n```")
            except OSError as e:
                print(tr("file_read_err", path=path, err=e), file=sys.stderr); continue
            manifest.add_file(entry); continue

        use_api = sz > args.limit_inline_total_mb * 1024 * 1024
        if use_api:
            uri, sha, exp = _upload(client, path, display_name)
            if not uri: continue
            entry["files_api_uri"] = uri
            entry["files_api_sha256"] = sha
            if exp: entry["expires_at"] = exp
            entry["uploaded_at"] = now_iso()
            manifest.add_file(entry)
            request_parts.append(types.Part.from_text(text=f"[FILE] {base_name} (new, this turn)"))
            request_parts.extend(build_parts_for_entry(entry))
        else:
            manifest.add_file(entry)
            with open(path, "rb") as f:
                data = f.read()
            request_parts.append(types.Part.from_text(text=f"[FILE] {base_name} (new, this turn)"))
            request_parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    manifest.save()

    _, mention_parts, unresolved = resolve_mentions(client, manifest, text_message, args)
    if mention_parts:
        request_parts.extend(mention_parts)

    final_text = []
    if embedded_text:
        final_text.append(tr("prompt_attached_header") + "\n".join(embedded_text))
    if text_message:
        final_text.append(tr("prompt_instruction", text=text_message))
    if not final_text:
        final_text.append(tr("prompt_default_analyze"))
    request_parts.append(types.Part.from_text(text="\n\n".join(final_text)))
    return request_parts, unresolved


# ─── F2: /apply ──────────────────────────────────────────────────────────
def _default_apply_dst(manifest, session_id, project_root):
    proj = manifest.data.get("project_path")
    if project_root and os.path.isdir(project_root):
        return project_root
    if proj:
        if os.path.isfile(proj) and zipfile.is_zipfile(proj):
            return os.path.join(session_dir(session_id), "project_extracted")
        if os.path.isdir(proj):
            return proj
    return None


def cmd_apply(manifest, session_id, src_pattern, dst_path, project_root, args):
    if not dst_path:
        dst_path = _default_apply_dst(manifest, session_id, project_root)
        if not dst_path:
            print(tr("apply_no_project")); return

    s_root = session_dir(session_id)
    save_dir = os.path.join(s_root, SAVED_SUBDIR)
    src_clean = (src_pattern or "").strip("\"'").rstrip("/")

    candidates: dict[str, str] = {}

    if os.path.isdir(save_dir):
        for root_d, _, files_in_d in os.walk(save_dir):
            for fn in files_in_d:
                abs_f = os.path.join(root_d, fn)
                rel_f = os.path.relpath(abs_f, save_dir).replace(os.sep, "/")
                candidates[rel_f] = abs_f

    for f in manifest.files():
        if f.get("source") == "generated":
            continue
        name = normalize_display_name(f.get("display_name", ""))
        loc = f.get("local_path")
        if name not in candidates and loc and os.path.isfile(loc):
            candidates[name] = loc

    matched = []
    for rel_name, src_abs in sorted(candidates.items()):
        if not src_clean:
            matched.append((rel_name, src_abs))
        elif rel_name == src_clean or rel_name.startswith(src_clean + "/") or \
             fnmatch.fnmatch(rel_name, src_clean) or os.path.basename(rel_name) == src_clean:
            matched.append((rel_name, src_abs))

    if not matched:
        print(tr("apply_not_found", pattern=src_pattern or "(all)")); return

    plan = []
    print(tr("apply_plan", count=len(matched), src=src_pattern or "(all)", dst=dst_path))

    single_file_target = (len(matched) == 1 and not (os.path.isdir(dst_path) or dst_path.endswith(("/", "\\"))))

    for rel_name, src_abs in matched:
        if single_file_target:
            target = dst_path
        else:
            target = os.path.join(dst_path, rel_name)
        status = "CONFLICT" if os.path.exists(target) else "new"
        print(f"  {rel_name}  →  {target}  [{status}]")
        plan.append((src_abs, target, rel_name))

    if args.dry_run:
        return
    if not args.yes and not ask_yes_no(tr("apply_ask"), default=False):
        return

    copied = 0
    for src_abs, target, rel_name in plan:
        if not os.path.isfile(src_abs):
            print(tr("apply_local_missing", name=rel_name), file=sys.stderr)
            continue
        ensure_dir(os.path.dirname(target) or ".")
        if os.path.exists(target) and not args.force and not args.yes:
            if not ask_yes_no(tr("apply_conflict", target=target), default=False):
                continue
        try:
            shutil.copy2(src_abs, target)
            print(tr("apply_success", target=target))
            copied += 1
        except OSError as e:
            print(tr("apply_err", target=target, err=e), file=sys.stderr)
    print(tr("apply_done", done=copied, total=len(plan)))


# ─── F6: /forget (Удаление из манифеста и облака при detached) ─────────────
def _forget_entry(client, manifest, entry, args, dry_run=False):
    name = normalize_display_name(entry.get("display_name", "?"))
    is_generated = entry.get("source") == "generated"
    is_detached = resolve_file_state(entry) == "detached"

    if is_generated and not args.force:
        if not args.yes and not ask_yes_no(tr("forget_generated_warn", name=name), default=False):
            return False

    if dry_run:
        print(tr("forget_dry_run", name=name))
        return True

    # Для detached файлов вызываем client.files.delete()
    if is_detached and entry.get("files_api_uri"):
        _delete_cloud_file(client, entry["files_api_uri"])

    try:
        manifest.files().remove(entry)
        print(tr("forget_done", name=name))
        return True
    except ValueError:
        return False


def cmd_forget(client, manifest, arg, args, dry_run=False):
    if not arg:
        print(tr("forget_usage")); return
    matched = manifest.find_all_files(arg)
    if not matched:
        print(tr("forget_not_found", pattern=arg)); return

    if not args.yes and len(matched) > 1 and not dry_run:
        if not ask_yes_no(tr("forget_all_confirm", count=len(matched)), default=False):
            return

    changed = False
    for f in list(matched):
        if _forget_entry(client, manifest, f, args, dry_run=dry_run):
            changed = True
    if changed and not dry_run:
        manifest.save()


# ─── Session summary ─────────────────────────────────────────────────────
def _last_preview(data, max_len=70):
    for turn in reversed(data.get("history", [])):
        txt = (turn.get("text") or "").strip()
        if txt:
            txt = " ".join(txt.split())
            return txt[:max_len] + ("..." if len(txt) > max_len else "")
    return ""


def generate_session_summary(chat, manifest, args):
    history = manifest.data.get("history", [])
    if not history or history[-1].get("role") != "model":
        return None
    first_t = _time_of(history[0].get("timestamp", ""))
    last_t = _time_of(history[-1].get("timestamp", ""))
    prompt = tr("summary_prompt", start=first_t, end=last_t)
    try:
        response = send_message_with_retry(
            chat, prompt, max_retries=min(args.send_retries, 2),
            initial_delay=args.send_retry_delay,
        )
        text, _ = extract_response_content(response)
        summary = text.strip().strip('"\'`«»').strip()
        if summary:
            return summary[:200]
    except Exception as e:
        print(tr("summary_err", err=e), file=sys.stderr)
    return None


def _finalize_session(chat, manifest, args):
    if args.no_summary:
        return
    history = manifest.data.get("history", [])
    if not history:
        return
    existing = manifest.data.get("summary")
    if existing and manifest.data.get("summary_at") == manifest.data.get("last_updated"):
        return
    print(tr("session_summary_gen"))
    try:
        summary = generate_session_summary(chat, manifest, args)
    except KeyboardInterrupt:
        print(tr("summary_aborted")); return
    except Exception as e:
        print(tr("summary_err", err=e), file=sys.stderr); return
    if summary:
        manifest.data["summary"] = summary
        manifest.data["summary_at"] = now_iso()
        manifest.save()
        print(tr("summary_success", text=summary))
    else:
        print(tr("summary_fail"))


# ─── Session menu ────────────────────────────────────────────────────────
def _collect_session_rows(match_project=None):
    root = sessions_root()
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        mpath = os.path.join(root, name, MANIFEST_FILE)
        if not os.path.isfile(mpath):
            continue
        try:
            with open(mpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if match_project:
            proj = data.get("project_path")
            if not proj or os.path.normcase(os.path.abspath(proj)) != match_project:
                continue
        rows.append({
            "session_id": name,
            "created": data.get("created", ""),
            "n_files": len(data.get("files", [])),
            "n_turns": len(data.get("history", [])),
            "project": data.get("project_path"),
            "summary": data.get("summary") or _last_preview(data),
        })
    rows.sort(key=lambda r: r.get("created", ""), reverse=True)
    return rows


def session_menu(match_project=None, allow_new_option=True, header=None):
    rows = _collect_session_rows(match_project)
    if not rows:
        return "__new__" if allow_new_option else None
    header_text = header or tr("menu_header")
    print(f"\n{header_text}\n")
    if allow_new_option:
        print(tr("menu_new_opt"))
    turns_w = "turns" if CURRENT_LANG == "en" else "ходов"
    files_w = "files" if CURRENT_LANG == "en" else "файлов"
    proj_w = "project" if CURRENT_LANG == "en" else "проект"
    for i, r in enumerate(rows[:SESSION_MENU_LIMIT], 1):
        age = _human_age(r.get("created", ""))
        print(f"  {i:>2}) {r['session_id']}  "
              f"({age}, {r['n_turns']} {turns_w}, {r['n_files']} {files_w})")
        if r.get("summary"):
            print(f"      {r['summary']}")
        if r.get("project"):
            print(f"      {proj_w}: {r['project']}")
        print()
    if len(rows) > SESSION_MENU_LIMIT:
        print(tr("menu_more", count=len(rows) - SESSION_MENU_LIMIT))
    hint = tr("menu_hint_new") if allow_new_option else tr("menu_hint_cancel")
    while True:
        try:
            ans = input(hint).strip()
        except (EOFError, KeyboardInterrupt):
            print(); return "__new__" if allow_new_option else None
        if not ans:
            return "__new__" if allow_new_option else None
        if ans.isdigit():
            idx = int(ans)
            if idx == 0 and allow_new_option:
                return "__new__"
            if 1 <= idx <= min(len(rows), SESSION_MENU_LIMIT):
                return rows[idx - 1]["session_id"]
            print(tr("menu_invalid")); continue
        return ans


# ─── REPL ────────────────────────────────────────────────────────────────
def print_banner(session_id, manifest, args, project_root=None):
    summary = manifest.data.get("summary")
    print("\n" + "═" * 65)
    print(tr("banner_active", ver=__version__))
    print(f" Session ID:  {session_id}")
    if summary:
        print(f" Summary:     {summary}")
    print(f" Manifest:    {manifest.path}")
    print(f" Log:         {os.path.join(session_dir(session_id), LOG_FILE)}")
    print(f" Saved:       {os.path.join(session_dir(session_id), SAVED_SUBDIR)}")
    print(f" Media:       {os.path.join(session_dir(session_id), MEDIA_SUBDIR)}")
    print(f" Model:       {manifest.data.get('model', args.model)}   Temperature: {args.temperature}")
    proj = manifest.data.get("project_path")
    if proj:
        extra = ""
        if project_root and os.path.isdir(project_root) and \
           "project_extracted" in project_root and project_root != proj:
            extra = "  (extracted)"
        print(f" Project:     {proj}{extra}")
    print(f" Files:       {len(manifest.files())}")
    print("═" * 65)
    print(tr("banner_commands"))
    print(tr("banner_mentions"))
    print(tr("banner_shortcuts"))
    print("═" * 65)


def _process_response(response, manifest, log, sdir):
    text, media = extract_response_content(response)
    ts = datetime.now()
    history = manifest.data.get("history", [])
    turn_number = history[-1].get("turn", _next_turn(manifest)) if history else _next_turn(manifest)
    saved_media = save_response_media(manifest, sdir, media, turn_number, ts)
    LAST_RESPONSE["text"] = text
    LAST_RESPONSE["media"] = saved_media
    LAST_RESPONSE["turn"] = turn_number
    record_turn(manifest, log, "model", text, ts=ts, turn=turn_number)
    for m in saved_media:
        log.write("MEDIA", f"{m['name']} ({m['mime']}, {human_size(m['size'])})",
                  ts=ts, turn=turn_number)
    if text:
        print(f"\nGemini:\n{text}")
    if saved_media:
        print(tr("media_saved_notify", count=len(saved_media)))


def _rollback_last_user_turn(manifest):
    if manifest.data.get("history") and manifest.data["history"][-1].get("role") == "user":
        manifest.data["history"].pop()
        manifest.save()


def _send_with_retry_or_rollback(chat, payload, manifest, args):
    try:
        return send_message_with_retry(chat, payload,
                                       max_retries=args.send_retries,
                                       initial_delay=args.send_retry_delay)
    except (KeyboardInterrupt, Exception):
        _rollback_last_user_turn(manifest)
        raise


def _parse_apply_args(body):
    try:
        tokens = shlex.split(body)
    except ValueError:
        tokens = body.split()
    if not tokens:
        return "", None
    if len(tokens) == 1:
        return tokens[0], None
    return tokens[0], tokens[1]


def _create_prompt_session() -> PromptSession | None:
    if not HAS_PROMPT_TOOLKIT:
        return None

    bindings = KeyBindings()

    @bindings.add("escape", "c-m")
    @bindings.add("escape", "enter")
    @bindings.add("c-j")
    def _insert_newline(event):
        event.current_buffer.insert_text("\n")

    @bindings.add("c-m")
    @bindings.add("enter")
    def _submit(event):
        buf = event.current_buffer
        if buf.text.strip():
            buf.validate_and_handle()

    def get_continuation(width, line_number, is_soft_wrap):
        return "... "

    return PromptSession(
        history=InMemoryHistory(),
        multiline=True,
        key_bindings=bindings,
        prompt_continuation=get_continuation,
    )


def run_repl(client, chat, manifest, session_id, save_root, project_root, args, log):
    sdir = session_dir(session_id)
    print_banner(session_id, manifest, args, project_root)
    think = "Gemini is thinking..." if CURRENT_LANG == "en" else "Gemini отвечает..."

    prompt_session = _create_prompt_session()

    while True:
        try:
            if prompt_session:
                raw = prompt_session.prompt(tr("user_prompt")).strip()
            else:
                first_line = input(tr("user_prompt"))
                lines = [first_line]
                while lines[-1].endswith("\\"):
                    lines[-1] = lines[-1][:-1]
                    lines.append(input("... "))
                raw = "\n".join(lines).strip()
        except (EOFError, KeyboardInterrupt):
            _finalize_session(chat, manifest, args)
            print(tr("session_ended")); break

        if not raw:
            continue
        if raw.lower() in ("exit", "quit", "/exit"):
            _finalize_session(chat, manifest, args)
            print(tr("session_ended")); break

        try:
            if raw == "/help":
                print_help(); continue
            if raw == "/list" or raw.startswith("/list "):
                cmd_list(manifest); continue
            if raw == "/session":
                cmd_session_info(session_id, manifest, args, project_root); continue
            if raw == "/history":
                cmd_history(manifest); continue

            # /sync
            if raw == "/sync" or raw.startswith("/sync "):
                target_p = raw[5:].strip().strip("\"'") or None
                sync_session(client, manifest, args, dry_run=args.dry_run, extra_path=target_p)
                continue

            # /focus
            if raw == "/focus" or raw.startswith("/focus "):
                body = raw[6:].strip()
                if not body:
                    print(tr("focus_usage")); continue
                try:
                    tokens = shlex.split(body)
                except ValueError as e:
                    print(tr("parse_err_syntax", err=e)); continue
                pattern = tokens[0]
                txt = " ".join(tokens[1:]) if len(tokens) > 1 else ""
                parts = cmd_focus(client, manifest, pattern, txt, args)
                if not parts:
                    continue
                record_turn(manifest, log, "user", raw)
                print(think)
                response = _send_with_retry_or_rollback(chat, parts, manifest, args)
                _process_response(response, manifest, log, sdir)
                continue

            # /send
            if raw == "/send" or raw.startswith("/send "):
                body = raw[5:].strip()
                if not body:
                    print(tr("send_usage")); continue
                try:
                    paths, text_msg = parse_send_args(body)
                except ValueError as e:
                    print(tr("parse_err_syntax", err=e)); continue
                if not paths:
                    print(tr("send_no_files")); continue
                parts, unresolved = cmd_send(client, manifest, session_id, args, paths, text_msg)
                if parts is None:
                    continue
                if unresolved:
                    names = ", ".join(unresolved)
                    if not args.yes and not ask_yes_no(tr("unresolved_mentions", names=names), default=True):
                        continue
                record_turn(manifest, log, "user", raw)
                print(think)
                response = _send_with_retry_or_rollback(chat, parts, manifest, args)
                _process_response(response, manifest, log, sdir)
                continue

            # /save (сохраняет только блоки КОДА из ответа модели)
            if raw == "/save" or raw.startswith("/save "):
                body = raw[5:].strip()
                try:
                    tokens = shlex.split(body) if body else []
                except ValueError:
                    tokens = body.split() if body else []
                arg = tokens[0] if tokens else None
                cmd_save(manifest, save_root, arg, args); continue

            # /md (сохраняет полный ТЕКСТ сообщения модели)
            if raw == "/md" or raw.startswith("/md "):
                filename = raw[3:].strip()
                if not filename:
                    print(tr("md_usage")); continue
                if not LAST_RESPONSE["text"]:
                    print(tr("md_no_response")); continue
                if is_explicit_path(filename):
                    target = os.path.expanduser(filename)
                else:
                    target = os.path.join(save_root, filename)
                ensure_dir(os.path.dirname(os.path.abspath(target)))
                with open(target, "w", encoding="utf-8") as f:
                    f.write(LAST_RESPONSE["text"])
                size = human_size(len(LAST_RESPONSE["text"].encode("utf-8")))
                print(tr("md_success", path=os.path.abspath(target), size=size))
                continue

            # /apply
            if raw == "/apply" or raw.startswith("/apply "):
                body = raw[7:].strip()
                src, dst = _parse_apply_args(body)
                if not src:
                    print(tr("apply_usage")); continue
                cmd_apply(manifest, session_id, src, dst, project_root, args)
                continue

            # /forget
            if raw == "/forget" or raw.startswith("/forget "):
                body = raw[8:].strip()
                try:
                    tokens = shlex.split(body) if body else []
                except ValueError:
                    tokens = body.split() if body else []
                dry = "--dry-run" in tokens
                tokens = [t for t in tokens if t != "--dry-run"]
                if not tokens:
                    print(tr("forget_usage")); continue
                cmd_forget(client, manifest, tokens[0], args, dry_run=dry)
                continue

            if raw.startswith("/"):
                print(tr("unknown_cmd", cmd=raw.split()[0])); continue

            # Запрос с @mentions
            _, mention_parts, unresolved = resolve_mentions(client, manifest, raw, args)
            if unresolved:
                names = ", ".join(unresolved)
                if not args.yes and not ask_yes_no(tr("unresolved_mentions", names=names), default=True):
                    continue

            record_turn(manifest, log, "user", raw)
            print(think)
            if mention_parts:
                mention_parts.append(types.Part.from_text(text=raw))
                response = _send_with_retry_or_rollback(chat, mention_parts, manifest, args)
            else:
                response = _send_with_retry_or_rollback(chat, raw, manifest, args)
            _process_response(response, manifest, log, sdir)

        except KeyboardInterrupt:
            _rollback_last_user_turn(manifest)
            print(tr("operation_interrupted")); continue
        except Exception as e:
            _rollback_last_user_turn(manifest)
            print(tr("exec_error", err=e), file=sys.stderr)
            log.write("ERROR", str(e))


# ─── Main ────────────────────────────────────────────────────────────────
def _resolve_session_arg(args, match_project):
    sync_implicit_continue = (
        args.sync and not args.resume and not args.continue_last
        and not args.new and not args.project
    )

    if args.resume:
        sid = args.resume
        if sid == "__interactive__":
            chosen = session_menu(match_project=match_project,
                                  allow_new_option=False,
                                  header=tr("menu_header_resume"))
            if not chosen or chosen == "__new__":
                return None, None, False
            sid = chosen
        m = Manifest.load(session_dir(sid))
        if m is None and sid.startswith("replai_"):
            stripped = sid[len("replai_"):]
            m2 = Manifest.load(session_dir(stripped))
            if m2 is not None:
                print(f"⚠ --resume accepts session_id without 'replai_'. Using: {stripped}", file=sys.stderr)
                return stripped, m2, True
        if m is None:
            print(tr("session_not_found", id=sid), file=sys.stderr)
            return None, None, False
        return sid, m, True

    if args.continue_last or sync_implicit_continue:
        rows = _collect_session_rows(match_project)
        if not rows:
            print(tr("continue_no_session"), file=sys.stderr)
            return None, None, False
        latest = rows[0]["session_id"]
        m = Manifest.load(session_dir(latest))
        if m is None:
            print(tr("session_load_err", id=latest), file=sys.stderr)
            return None, None, False
        return latest, m, True

    if args.new:
        sid = make_session_id()
        m = Manifest.new(session_dir(sid), sid, args.model, args.project)
        m.save()
        return sid, m, False

    chosen = None
    if sys.stdin.isatty():
        chosen = session_menu(match_project=match_project,
                              allow_new_option=True,
                              header=tr("menu_header"))
    if chosen and chosen != "__new__":
        m = Manifest.load(session_dir(chosen))
        if m:
            return chosen, m, True
    sid = make_session_id()
    m = Manifest.new(session_dir(sid), sid, args.model, args.project)
    m.save()
    return sid, m, False


def main(argv=None):
    global STATE_DIR, CURRENT_LANG
    args = parse_args(argv)
    STATE_DIR = args.state_dir
    if args.lang:
        CURRENT_LANG = args.lang

    api_key = load_api_key(args.api_key)
    if not api_key:
        return 1
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(tr("client_init_err", err=e), file=sys.stderr); return 1

    match_project = os.path.normcase(os.path.abspath(args.project)) if args.project else None
    session_id, manifest, resumed = _resolve_session_arg(args, match_project)
    if session_id is None:
        return 0

    sdir = session_dir(session_id)
    log = SessionLog(os.path.join(sdir, LOG_FILE))
    save_root = ensure_dir(os.path.join(sdir, SAVED_SUBDIR))
    ensure_dir(os.path.join(sdir, MEDIA_SUBDIR))

    # Конфликт смены проекта
    stored_proj = manifest.data.get("project_path")
    if args.project:
        new_proj_abs = os.path.abspath(args.project)
        if stored_proj and os.path.normcase(stored_proj) != os.path.normcase(new_proj_abs):
            if ask_yes_no(tr("project_conflict_ask", old=stored_proj, new=new_proj_abs), default=True):
                manifest.data["project_path"] = new_proj_abs
                manifest.save()
            else:
                args.project = stored_proj

    active_project_path = args.project or manifest.data.get("project_path")
    project_files = []
    project_root = None

    if active_project_path:
        project_root = active_project_path
        if os.path.isfile(active_project_path) and zipfile.is_zipfile(active_project_path):
            extracted = os.path.join(sdir, "project_extracted")
            print(tr("extracting_zip", dir=extracted))
            project_root = extract_project_zip(active_project_path, extracted)
        elif os.path.isdir(active_project_path):
            project_root = os.path.abspath(active_project_path)
        elif os.path.isfile(active_project_path):
            project_root = os.path.abspath(active_project_path)

        if os.path.exists(project_root):
            print(tr("scanning_proj", path=active_project_path))
            include_ignored_flag = getattr(args, "project_include_ignored", False)
            scanned_files, _ = scan_project(
                project_root,
                max_file_bytes=args.project_max_file_bytes,
                max_total_bytes=args.project_max_total_bytes,
                max_files=args.project_max_files,
                follow_symlinks=args.project_follow_symlinks,
                include_ide=args.project_include_ide_dirs,
                include_ignored=include_ignored_flag,
            )
            print(tr("indexed_files", count=len(scanned_files)))
            for f in scanned_files:
                entry = {
                    "name": os.path.basename(f["abs_path"]),
                    "display_name": make_display_name(session_id, f["rel_path"]),
                    "local_path": f["abs_path"], "abs_path": f["abs_path"],
                    "local_sha256": sha256_of_file(f["abs_path"]),
                    "kind": f["kind"], "size": f["size"],
                    "mime": file_mime(f["abs_path"]),
                }
                manifest.add_file(entry)
            manifest.data["project_path"] = os.path.abspath(active_project_path)
            manifest.save()
            project_files = scanned_files

    if not project_files and manifest.files():
        for f in manifest.files():
            if f.get("source") != "generated" and f.get("kind") == "text":
                project_files.append({
                    "rel_path": normalize_display_name(f.get("display_name", f.get("name", ""))),
                    "abs_path": f.get("local_path"),
                    "local_path": f.get("local_path"),
                    "kind": "text",
                })
        if active_project_path is None and manifest.data.get("project_path"):
            active_project_path = manifest.data.get("project_path")
            project_root = active_project_path
            if os.path.isfile(project_root) and zipfile.is_zipfile(project_root):
                project_root = os.path.join(sdir, "project_extracted")

    # Обработка флага --sync
    if args.sync:
        sync_session(client, manifest, args, dry_run=args.dry_run)
        if not sys.stdin.isatty():
            log.close()
            return 0

    history_contents = []
    if resumed:
        for turn in manifest.data.get("history", []):
            role = "user" if turn.get("role") == "user" else "model"
            txt = turn.get("text", "")
            if not txt and role == "model":
                txt = "[Media response]" if CURRENT_LANG == "en" else "[Медиа ответ]"
            if txt:
                history_contents.append(types.Content(
                    role=role, parts=[types.Part.from_text(text=txt)],
                ))

    model_to_use = manifest.data.get("model") or args.model
    system_instruction = build_system_instruction(project_files, active_project_path)

    config_kwargs = {
        "system_instruction": system_instruction,
        "temperature": args.temperature,
    }
    if _is_image_model(model_to_use):
        config_kwargs["response_modalities"] = ["TEXT", "IMAGE"]
        print("  ⚙ Image model detected: response_modalities=['TEXT','IMAGE']", file=sys.stderr)

    try:
        try:
            chat = client.chats.create(
                model=model_to_use,
                history=history_contents if history_contents else None,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception:
            if "response_modalities" in config_kwargs:
                config_kwargs.pop("response_modalities")
                chat = client.chats.create(
                    model=model_to_use,
                    history=history_contents if history_contents else None,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            else:
                raise
    except Exception as e:
        print(tr("client_init_err", err=e), file=sys.stderr)
        log.close(); return 1

    try:
        run_repl(client, chat, manifest, session_id, save_root, project_root, args, log)
    finally:
        log.close()
        manifest.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
