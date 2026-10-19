# -*- coding: utf-8 -*-
"""Простое файловое логирование для диагностики.

Пишет в job_search/logs/debug.log (создаёт папку при необходимости).
Используется только для отладки — не влияет на работу приложения.
"""
import os
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "debug.log"


def log(msg):
    """Дописывает строку с меткой времени в лог-файл."""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def log_separator(title=""):
    log("=" * 60)
    if title:
        log(title)
