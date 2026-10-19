# -*- coding: utf-8 -*-
"""Работа с открытым API hh.ru (без ключа)."""
import json
import urllib.error
import urllib.parse
import urllib.request

import config


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": config.HH_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                "Поиск вакансий через API hh.ru недоступен: поддержка API для "
                "соискателей прекращена 15.12.2025. Используй ручной ввод текста "
                "вакансии (вкладка «Вакансия») или другой источник поиска. "
                "Команды evaluate/apply с --text работают без поиска."
            ) from e
        raise


def search_vacancies(query, area=None, per_page=None, page=0):
    """Поиск вакансий. Возвращает сырой JSON от hh.ru."""
    params = {
        "text": query,
        "area": area or config.HH_AREA,
        "per_page": per_page or config.HH_PER_PAGE,
        "page": page,
    }
    url = config.HH_API_BASE + "/vacancies?" + urllib.parse.urlencode(params)
    return _get(url)


def get_vacancy(vacancy_id):
    """Скачивает одну вакансию по id."""
    return _get(config.HH_API_BASE + "/vacancies/" + str(vacancy_id))


def format_vacancy(v):
    """Превращает объект вакансии hh.ru в читаемый текст."""
    name = v.get("name", "")
    employer = (v.get("employer") or {}).get("name", "")
    area = (v.get("area") or {}).get("name", "")
    salary = v.get("salary")
    salary_text = ""
    if salary:
        salary_text = _format_salary(salary)

    description = v.get("description", "")
    # грубая очистка от HTML-тегов
    description = _strip_html(description)

    # ключевые навыки
    key_skills = [s.get("name", "") for s in v.get("key_skills", [])]

    lines = [
        f"# {name}",
        f"Компания: {employer}",
        f"Локация: {area}",
    ]
    if salary_text:
        lines.append(f"Зарплата: {salary_text}")
    if key_skills:
        lines.append("Ключевые навыки: " + ", ".join(key_skills))
    lines.append("\n## Описание\n" + description)
    return "\n".join(lines)


def _format_salary(s):
    cur = s.get("currency") or ""
    frm = s.get("from")
    to = s.get("to")
    if frm and to:
        return f"{frm}–{to} {cur}"
    if frm:
        return f"от {frm} {cur}"
    if to:
        return f"до {to} {cur}"
    return cur


def _strip_html(text):
    """Простая очистка HTML-разметки без сторонних библиотек."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#xa0;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
