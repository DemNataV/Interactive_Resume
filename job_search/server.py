# -*- coding: utf-8 -*-
"""Mirra Job — локальный веб-сервер (работает независимо от Veai).

Запуск из Терминала Mac:
    python3 job_search/server.py

Затем открой в браузере:  http://localhost:8765

Сервер проксирует запросы к LLM (RouterAI / DeepSeek) и к Хабр Карьере.
Ключ пользователь вводит в браузере; сервер его не хранит и не пишет в файлы.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config
import profile_reader
import apply as apply_mod
import habr_api
import debug_log

WEB_DIR = Path(__file__).resolve().parent / "web"
PORT = 8765
WATCH_DIR = Path(__file__).resolve().parent
WATCH_INTERVAL = 2  # секунды между проверками


def _snapshot_mtimes():
    """Снимок времени изменения всех .py-файлов в каталоге проекта."""
    snap = {}
    for p in WATCH_DIR.rglob("*.py"):
        try:
            snap[str(p)] = p.stat().st_mtime
        except OSError:
            pass
    return snap


def _serve():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("Mirra Job запущен: http://localhost:%d" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")


def _resolve_llm_params(body):
    provider = body.get("provider", "routerai")
    p = config.PROVIDERS.get(provider)
    if not p:
        raise RuntimeError("Неизвестный провайдер: " + str(provider))
    key = (body.get("key") or "").strip()
    model = (body.get("model") or "").strip() or p["default_model"]
    if not key:
        raise RuntimeError("Не указан API-ключ")
    return p["url"], key, model


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _html(self, content: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._html((WEB_DIR / "index.html").read_bytes())
            return

        if path.startswith("/api/profile"):
            self._json({"ok": True, "profile": profile_reader.load_profile()})
            return

        if path.startswith("/api/habr/search"):
            query = qs.get("query", [""])[0]
            per_page = int(qs.get("per_page", ["20"])[0])
            page = int(qs.get("page", ["1"])[0])
            debug_log.log("SERVER habr/search query=%s page=%s per_page=%s" % (query, page, per_page))
            try:
                data = habr_api.search_vacancies(query, per_page=per_page, page=page)
                self._json({"ok": True, "data": data})
            except RuntimeError as e:
                debug_log.log("SERVER habr/search ОШИБКА: %s" % e)
                self._json({"ok": False, "error": str(e)})
            return

        if path.startswith("/api/habr/vacancy/"):
            vid = path.rsplit("/", 1)[-1]
            debug_log.log("SERVER habr/vacancy id=%s" % vid)
            try:
                v = habr_api.get_vacancy(vid)
                text = habr_api.format_vacancy(v)
                self._json({"ok": True, "text": text, "url": v.get("alternate_url", "")})
            except Exception as e:
                debug_log.log("SERVER habr/vacancy id=%s ОШИБКА: %s" % (vid, e))
                self._json({"ok": False, "error": str(e)})
            return

        self._json({"ok": False, "error": "Not found: " + path}, status=404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        debug_log.log("SERVER POST %s" % path)

        if path == "/api/evaluate":
            try:
                body = self._read_body()
                url, key, model = _resolve_llm_params(body)
                profile = body.get("profile") or profile_reader.load_profile()
                result = apply_mod.evaluate_fit(
                    body.get("vacancy_text", ""), profile, url=url, key=key, model=model
                )
                self._json({"ok": True, "result": result})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/api/suggest_queries":
            try:
                body = self._read_body()
                url, key, model = _resolve_llm_params(body)
                profile = body.get("profile") or profile_reader.load_profile()
                mode = body.get("mode", "direct")
                if mode == "adjacent":
                    queries = apply_mod.suggest_adjacent_queries(
                        profile, preferences=body.get("preferences", ""), url=url, key=key, model=model
                    )
                else:
                    queries = apply_mod.suggest_queries(
                        profile, preferences=body.get("preferences", ""), url=url, key=key, model=model
                    )
                self._json({"ok": True, "queries": queries})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/api/rank_vacancies":
            try:
                body = self._read_body()
                url, key, model = _resolve_llm_params(body)
                profile = body.get("profile") or profile_reader.load_profile()
                vacancies = body.get("vacancies") or []
                debug_log.log("SERVER rank_vacancies: %d вакансий" % len(vacancies))
                ranked = apply_mod.rank_vacancies(
                    vacancies, profile, preferences=body.get("preferences", ""),
                    url=url, key=key, model=model
                )
                self._json({"ok": True, "vacancies": ranked})
            except Exception as e:
                debug_log.log("SERVER rank_vacancies ОШИБКА: %s" % e)
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/api/apply":
            try:
                body = self._read_body()
                url, key, model = _resolve_llm_params(body)
                profile = body.get("profile") or profile_reader.load_profile()
                vt = body.get("vacancy_text", "")
                cover, cv = apply_mod.draft_application(vt, profile, url=url, key=key, model=model)
                feedback = apply_mod.review_application(cover, cv, vt, profile, url=url, key=key, model=model)
                final = apply_mod.revise_application(cover, cv, feedback, url=url, key=key, model=model)
                self._json({
                    "ok": True,
                    "cover": cover,
                    "cv": cv,
                    "feedback": feedback,
                    "final": final,
                })
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/api/apply_light":
            try:
                body = self._read_body()
                url, key, model = _resolve_llm_params(body)
                profile = body.get("profile") or profile_reader.load_profile()
                vt = body.get("vacancy_text", "")
                mode = body.get("mode", "both")
                debug_log.log("SERVER apply_light mode=%s" % mode)
                if mode == "cover":
                    cover = apply_mod.draft_cover(vt, profile, url=url, key=key, model=model)
                    self._json({"ok": True, "cover": cover})
                elif mode == "cv":
                    cv = apply_mod.draft_cv(vt, profile, url=url, key=key, model=model)
                    self._json({"ok": True, "cv": cv})
                else:
                    cover, cv = apply_mod.draft_application(vt, profile, url=url, key=key, model=model)
                    self._json({"ok": True, "cover": cover, "cv": cv})
            except Exception as e:
                debug_log.log("SERVER apply_light ОШИБКА: %s" % e)
                self._json({"ok": False, "error": str(e)})
            return

        self._json({"ok": False, "error": "Not found: " + path}, status=404)

    def log_message(self, *args):
        pass  # не шумим в консоли


def main():
    # Дочерний процесс — просто сервер без надзора.
    if "--child" in sys.argv:
        _serve()
        return

    # Родитель: следит за .py-файлами и перезапускает сервер при изменениях.
    print("Автоперезагрузка .py-файлов включена. Остановка: Ctrl+C")
    while True:
        child = subprocess.Popen([sys.executable, __file__, "--child"])
        baseline = _snapshot_mtimes()
        try:
            while True:
                time.sleep(WATCH_INTERVAL)
                if child.poll() is not None:
                    break  # дочерний завершился сам — перезапустим
                if _snapshot_mtimes() != baseline:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    print("\n[auto-reload] Изменён .py-файл — перезапускаю сервер…\n")
                    break
        except KeyboardInterrupt:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
            print("\nОстановлено.")
            break


if __name__ == "__main__":
    main()
