# -*- coding: utf-8 -*-
"""Универсальный вызов OpenAI-совместимых LLM API (RouterAI / DeepSeek).

Ключ, URL и модель передаются параметрами — так один и тот же код
работает и из CLI (берёт настройки из config), и из веб-сервера
(пользователь вводит ключ/провайдера в браузере).
"""
import json
import urllib.request

import config
import debug_log


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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))

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
