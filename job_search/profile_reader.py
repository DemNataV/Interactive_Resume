# -*- coding: utf-8 -*-
"""Читает чистый карьерный профиль для поиска работы.

В отличие от личного `profile/*.md` (цифровой портрет, включающий
отношения, психологию, здоровье и т.д.), для поиска работы используется
только `career_profile.md` — сведения, полезные нанимающему.

Правки в этом файле подхватываются без перезапуска сервера.
"""
import config


def load_profile() -> str:
    """Возвращает карьерный профиль кандидата как единый текст."""
    path = config.BASE_DIR / "career_profile.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Профиль не найден: job_search/career_profile.md"
