# -*- coding: utf-8 -*-
"""Универсальный вызов OpenAI-совместимых LLM API (RouterAI / DeepSeek).

Ключ, URL и модель передаются параметрами — так один и тот же код
работает и из CLI (берёт настройки из config), и из веб-сервера
(пользователь вводит ключ/провайдера в браузере).
"""
import json
import time
import urllib.error
import urllib.request

import config
import debug_log

# Защита от 429 (Too Many Requests) со стороны LLM-провайдера (RouterAI и др.):
# при rate-limit делаем паузу и повторяем с нарастающей задержкой.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # секунд; нарастает: 5, 10, 15


def chat(messages, temperature=0.6, max_tokens=4000, url=None, key=None, model=None):
    url = url or config.ROUTERAI_URL
    key = key or config.ROUTERAI_KEY
    model = model or config.ROUTERAI_MODEL

    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    }

    debug_log.log("LLM REQ model=%s url=%s max_tokens=%s" % (model, url, max_tokens))

    data = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            # Лимит расходов на ключе — это не rate-limit частоты: повторы не помогут.
            if e.code == 429 and "spending limit" in body.lower():
                debug_log.log("LLM 429 лимит расходов исчерпан url=%s body=%s" % (url, body))
                raise RuntimeError("Лимит расходов на API-ключ исчерпан (RouterAI). Подними лимит в кабинете или смени ключ/провайдера.") from e
            if e.code == 429 and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (attempt + 1)
                debug_log.log("LLM 429 (попытка %d/%d) url=%s — пауза %dс и повтор" % (attempt + 1, MAX_RETRIES, url, delay))
                time.sleep(delay)
                continue
            debug_log.log("LLM HTTP %d url=%s body=%s" % (e.code, url, body))
            raise RuntimeError("LLM вернул ошибку HTTP %d" % e.code) from e
        except (urllib.error.URLError, OSError) as e:
            debug_log.log("LLM сетевая ошибка url=%s: %s" % (url, e))
            raise RuntimeError("Сетевая ошибка при вызове LLM: %s" % e) from e

    if data is None:
        debug_log.log("LLM исчерпаны повторы 429 url=%s" % url)
        raise RuntimeError("LLM: превышен лимит запросов (HTTP 429)")

    try:
        message = data["choices"][0]["message"]
        content = message.get("content")
        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""

        debug_log.log(
            "LLM model=%s | content пустой=%s | len(content)=%s | len(reasoning)=%s | max_tokens=%s"
            % (model, not content, len(content or ""), len(reasoning), max_tokens)
        )

        # Reasoner-модели (DeepSeek V4 Pro и др.) могут вернуть пустой content,
        # потратив лимит на размышления. Для обычных задач берём content;
        # если пуст — пробуем reasoning как fallback.
        if not content:
            content = reasoning
        if not content:
            raise RuntimeError("API вернул пустой ответ: " + json.dumps(data, ensure_ascii=False)[:500])
        return content
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Неожиданный ответ API: " + json.dumps(data, ensure_ascii=False)[:500])
