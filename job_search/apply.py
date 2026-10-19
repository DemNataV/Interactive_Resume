# -*- coding: utf-8 -*-
"""Оценка fit и генерация отклика (cover letter + CV + reviewer).

Все функции принимают url/key/model, чтобы работать и из CLI, и из веб-сервера.
Если url/key/model не переданы — берутся значения по умолчанию из config.
"""
import config
import llm


def evaluate_fit(vacancy_text, profile, url=None, key=None, model=None):
    messages = [
        {"role": "system", "content": config.FIT_SYSTEM_PROMPT},
        {"role": "user", "content": "ПРОФИЛЬ КАНДИДАТА:\n\n" + profile + "\n\nВАКАНСИЯ:\n\n" + vacancy_text},
    ]
    return llm.chat(messages, temperature=0.3, url=url, key=key, model=model)


def suggest_queries(profile, preferences="", url=None, key=None, model=None):
    """На основе профиля (и пожеланий) предлагает список поисковых запросов.

    Возвращает список словарей [{"query": ..., "reason": ...}].
    """
    user = "ПРОФИЛЬ КАНДИДАТА:\n\n" + profile
    if preferences and preferences.strip():
        user += "\n\nПОЖЕЛАНИЯ КАНДИДАТА:\n" + preferences.strip()
    text = llm.chat([
        {"role": "system", "content": config.SUGGEST_QUERIES_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ], temperature=0.5, url=url, key=key, model=model)

    queries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # убираем возможные маркеры списка, если модель их всё же добавила
        line = line.lstrip("-*•1234567890. ").strip()
        if not line:
            continue
        if "|" in line:
            query, reason = line.split("|", 1)
            queries.append({"query": query.strip(), "reason": reason.strip()})
        else:
            queries.append({"query": line, "reason": ""})
    return queries


def rank_vacancies(vacancies, profile, preferences="", url=None, key=None, model=None):
    """Ранжирует список вакансий по соответствию кандидату.

    vacancies — список dict (уже нормализованных из habr_api), каждому добавляются
    score (int), fit (good/partial/poor), why (str). Возвращает отсортированный список.

    Разбивает список на батчи по RANK_BATCH вакансий: reasoner-модель при большом
    списке тратит max_tokens на размышления и возвращает пустой content.
    """
    import debug_log

    batch = config.RANK_BATCH
    all_scored = {}

    for i in range(0, len(vacancies), batch):
        chunk = vacancies[i:i + batch]
        rows = []
        for v in chunk:
            comp = (v.get("employer") or {}).get("name", "")
            skills = v.get("skills") or ""
            rows.append(
                f"id={v.get('id')} | {v.get('name','')} | {comp} | {skills} | "
                f"{v.get('qualification','')} | {v.get('location','')}"
            )
        listing = "\n".join(rows)

        user = "ПРОФИЛЬ КАНДИДАТА:\n\n" + profile
        if preferences and preferences.strip():
            user += "\n\nПОЖЕЛАНИЯ:\n" + preferences.strip()
        user += "\n\nВАКАНСИИ:\n\n" + listing

        text = llm.chat([
            {"role": "system", "content": config.RANK_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ], temperature=0.2, max_tokens=config.RANK_MAX_TOKENS, url=url, key=key, model=model)

        debug_log.log_separator("RANK: batch %d вакансий" % len(chunk))
        debug_log.log("RAW TEXT (первые 800 симв): " + repr(text[:800]))

        scored = _parse_ranked(text)
        debug_log.log("PARSED: распознано %d из %d" % (len(scored), len(chunk)))
        all_scored.update(scored)

    for v in vacancies:
        s = all_scored.get(v.get("id"))
        if s:
            v["score"] = s["score"]
            v["fit"] = s["fit"]
            v["why"] = s["why"]
        else:
            v["score"] = 0
            v["fit"] = "partial"
            v["why"] = ""

    ranked = sorted(vacancies, key=lambda x: x.get("score", 0), reverse=True)
    return ranked


def _parse_ranked(text):
    """Парсит ответ LLM в {id: {score, fit, why}}.

    Сначала пробует JSON (как просит промпт), затем — построчный fallback
    вида `id | score | fit | why` для случаев, когда reasoner-модель
    не вернула чистый JSON.
    """
    import json as _json
    import re as _re

    # 1) Чистый JSON-массив.
    try:
        data = _json.loads(text)
        if isinstance(data, list):
            return _parse_json_list(data)
    except (ValueError, TypeError):
        pass

    # 2) JSON внутри markdown-блока ```json ... ```.
    m = _re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, _re.S)
    if m:
        try:
            data = _json.loads(m.group(1))
            if isinstance(data, list):
                return _parse_json_list(data)
        except (ValueError, TypeError):
            pass

    # 3) Первый найденный JSON-массив [ ... ].
    m = _re.search(r"\[.*\]", text, _re.S)
    if m:
        try:
            data = _json.loads(m.group(0))
            if isinstance(data, list):
                return _parse_json_list(data)
        except (ValueError, TypeError):
            pass

    # 4) Построчный fallback: id | score | fit | why
    return _parse_lines(text)


def _normalize_fit(value):
    """Приводит fit к одному из 'good'/'partial'/'poor', понимая и русские значения."""
    v = str(value or "").strip().lower()
    if v in ("good", "подходит", "подходит хорошо", "да", "high", "сильно подходит"):
        return "good"
    if v in ("poor", "не подходит", "нет", "low", "слабо"):
        return "poor"
    return "partial"


def _parse_json_list(data):
    scored = {}
    for it in data:
        if not isinstance(it, dict):
            continue
        try:
            vid = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        score = it.get("score", 0)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 0
        fit = _normalize_fit(it.get("fit", "partial"))
        why = str(it.get("why", "") or "")
        scored[vid] = {"score": score, "fit": fit, "why": why}
    return scored


def _parse_lines(text):
    scored = {}
    for line in text.splitlines():
        line = line.strip().lstrip("-*• ").strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        try:
            vid = int(parts[0])
        except ValueError:
            continue
        score = 0
        try:
            score = int(parts[1])
        except ValueError:
            pass
        fit = _normalize_fit(parts[2]) if len(parts) > 2 else "partial"
        why = parts[3] if len(parts) > 3 else ""
        scored[vid] = {"score": score, "fit": fit, "why": why}
    return scored


def draft_application(vacancy_text, profile, url=None, key=None, model=None):
    cover = llm.chat([
        {"role": "system", "content": config.COVER_SYSTEM_PROMPT},
        {"role": "user", "content": "ПРОФИЛЬ:\n\n" + profile + "\n\nВАКАНСИЯ:\n\n" + vacancy_text},
    ], temperature=0.7, url=url, key=key, model=model)

    cv = llm.chat([
        {"role": "system", "content": config.CV_SYSTEM_PROMPT},
        {"role": "user", "content": "ПРОФИЛЬ:\n\n" + profile + "\n\nВАКАНСИЯ:\n\n" + vacancy_text},
    ], temperature=0.4, url=url, key=key, model=model)

    return cover, cv


def review_application(cover, cv, vacancy_text, profile, url=None, key=None, model=None):
    text = (
        "ВАКАНСИЯ:\n\n" + vacancy_text +
        "\n\nПРОФИЛЬ:\n\n" + profile +
        "\n\nСОПРОВОДИТЕЛЬНОЕ (черновик):\n\n" + cover +
        "\n\nРЕЗЮМЕ (черновик):\n\n" + cv
    )
    return llm.chat([
        {"role": "system", "content": config.REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ], temperature=0.3, url=url, key=key, model=model)


def revise_application(cover, cv, review_feedback, url=None, key=None, model=None):
    text = (
        "СОПРОВОДИТЕЛЬНОЕ (черновик):\n\n" + cover +
        "\n\nРЕЗЮМЕ (черновик):\n\n" + cv +
        "\n\nЗАМЕЧАНИЯ РЕВЬЮЕРА:\n\n" + review_feedback
    )
    return llm.chat([
        {"role": "system", "content": config.REVISE_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ], temperature=0.4, url=url, key=key, model=model)
