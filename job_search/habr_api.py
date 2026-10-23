# -*- coding: utf-8 -*-
"""Работа с Хабр Карьерой (career.habr.com) без API-ключа.

Публичный поиск вакансий через api.hh.ru закрыт для соискателей с 15.12.2025,
поэтому используем Хабр Карьеру (открытый JSON-эндпоинт списка + JSON-LD в HTML).

Возвращаемый формат нормализован под структуру, которую ожидает веб-интерфейс:
items[] с полями id, name, employer.name, salary {from,to,currency}, alternate_url.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import debug_log

BASE = "https://career.habr.com"

# Защита от сбоев при серии запросов: 429 (Too Many Requests),
# сброс соединения / таймауты и временные 5xx. Повторяем с нарастающей паузой.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 3  # секунд; множитель нарастает: 3, 6, 9
RETRYABLE_HTTP = {429, 502, 503, 504}


def _get_bytes(url, retries=MAX_RETRIES):
    req = urllib.request.Request(url, headers={"User-Agent": config.HABR_USER_AGENT})
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_HTTP and attempt < retries:
                delay = RETRY_BASE_DELAY * (attempt + 1)
                debug_log.log("HABR HTTP %d (попытка %d/%d) url=%s — пауза %dс и повтор" % (e.code, attempt + 1, retries, url, delay))
                time.sleep(delay)
                last_err = e
                continue
            debug_log.log("HABR HTTP %d url=%s" % (e.code, url))
            raise RuntimeError("Хабр Карьера вернула ошибку HTTP %d" % e.code) from e
        except (urllib.error.URLError, OSError) as e:
            if attempt < retries:
                delay = RETRY_BASE_DELAY * (attempt + 1)
                debug_log.log("HABR сетевая ошибка (попытка %d/%d) url=%s: %s — пауза %dс и повтор" % (attempt + 1, retries, url, e, delay))
                time.sleep(delay)
                last_err = e
                continue
            debug_log.log("HABR сетевая ошибка исчерпаны повторы url=%s: %s" % (url, e))
            raise RuntimeError("Сетевая ошибка при обращении к Хабр Карьере: %s" % e) from e
    debug_log.log("HABR исчерпаны повторы url=%s (последняя ошибка: %s)" % (url, last_err))
    raise RuntimeError("Хабр Карьера не отвечает: %s" % last_err) from last_err


def _get_json(url):
    raw = _get_bytes(url).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("Хабр Карьера вернула некорректный JSON: %s" % e) from e


def search_vacancies(query, page=1, per_page=20):
    """Поиск вакансий. Возвращает {"found": N, "items": [...]}."""
    params = {
        "q": query,
        "type": "all",
        "page": page,
        "per_page": per_page,
    }
    url = BASE + "/api/frontend/vacancies?" + urllib.parse.urlencode(params)
    data = _get_json(url)
    meta = data.get("meta") or {}
    items = [_normalize(v) for v in data.get("list", [])]
    return {"found": meta.get("totalResults", len(items)), "items": items}


def _normalize(v):
    company_obj = v.get("company") or {}
    company = company_obj.get("title", "")
    company_href = company_obj.get("href", "")
    company_url = (BASE + company_href) if isinstance(company_href, str) and company_href else ""
    salary = v.get("salary") or {}
    pred = v.get("predictedSalary") or {}
    from_ = salary.get("from") or pred.get("from")
    to_ = salary.get("to") or pred.get("to")
    cur = (salary.get("currency") or pred.get("currency") or "").upper()
    locations = ", ".join(
        loc.get("title", "") for loc in (v.get("locations") or []) if loc.get("title")
    )
    skills = ", ".join(s.get("title", "") for s in (v.get("skills") or []))
    vid = v.get("id")
    ext = v.get("externalLink")
    external_link = (BASE + ext) if isinstance(ext, str) and ext else ""
    return {
        "id": vid,
        "name": v.get("title", ""),
        "employer": {"name": company, "url": company_url},
        "salary": {"from": from_, "to": to_, "currency": cur},
        "alternate_url": BASE + (v.get("href") or ("/vacancies/" + str(vid))),
        "external_link": external_link,
        "company_url": company_url,
        "location": locations,
        "skills": skills,
        "qualification": v.get("qualification", ""),
        "published": (v.get("publishedDate") or {}).get("title", ""),
    }


def get_vacancy(vid):
    """Скачивает одну вакансию по id. Возвращает dict из JSON-LD (JobPosting)."""
    url = BASE + "/vacancies/" + str(vid)
    html = _get_bytes(url).decode("utf-8")
    ld = _extract_jobposting(html)
    if not ld:
        raise RuntimeError("Не удалось извлечь описание вакансии из страницы")
    ld["alternate_url"] = url
    return ld


def _extract_jobposting(html):
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    for s in scripts:
        t = s.strip()
        if t.startswith("{") and "JobPosting" in t:
            try:
                return json.loads(t)
            except json.JSONDecodeError:
                continue
    return {}


def format_vacancy(v):
    """Превращает dict вакансии (JSON-LD) в читаемый текст для LLM."""
    title = _as_str(v.get("title", ""))
    org = _as_str((v.get("hiringOrganization") or {}).get("name", ""))
    loc = _extract_location(v.get("jobLocation"))
    desc = _strip_html(_as_str(v.get("description", "")))

    lines = [
        "# " + title,
        "Компания: " + org,
    ]
    if loc:
        lines.append("Локация: " + loc)
    lines.append("\n## Описание\n" + desc)
    return "\n".join(lines)


def _as_str(value):
    """Безопасно приводит любое значение к строке (dict/list -> JSON-строку)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _extract_location(job_location):
    """Достаёт читаемую локацию из jobLocation (может быть list, dict или отсутствовать)."""
    items = job_location if isinstance(job_location, list) else [job_location]
    parts = []
    for jl in items:
        if not isinstance(jl, dict):
            continue
        addr = jl.get("address")
        if isinstance(addr, str):
            parts.append(addr)
        elif isinstance(addr, dict):
            # schema.org PostalAddress
            city = _as_str(addr.get("addressLocality", ""))
            street = _as_str(addr.get("streetAddress", ""))
            if street and city and street != city:
                parts.append(city + ", " + street)
            else:
                parts.append(city or street)
        else:
            name = _as_str(jl.get("name", ""))
            if name:
                parts.append(name)
    return ", ".join(x for x in parts if x)


def _strip_html(text):
    # Блочные теги -> переносы строк, чтобы сохранить абзацы и списки.
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|ul|ol|section|article)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)<(p|div|h[1-6])[^>]*>", "", text)
    # Остальные теги убираем.
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;|&#xa0;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    # Схлопываем множественные пробелы и пустые строки.
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    return text.strip()
