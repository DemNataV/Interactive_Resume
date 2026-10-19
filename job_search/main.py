# -*- coding: utf-8 -*-
"""CLI ассистента поиска работы (Mirra Job).

Примеры:
    python main.py search "QA lead"              # поиск вакансий на Хабр Карьере
    python main.py evaluate 123456789             # оценить вакансию по id
    python main.py apply 123456789                # полный отклик по id
    python main.py apply --text "текст вакансии"  # полный отклик из текста
"""
import argparse
import sys
from pathlib import Path

import config
import profile_reader
import habr_api
import apply as apply_mod


def _profile():
    p = profile_reader.load_profile()
    if not p.strip():
        print("Ошибка: профиль пуст. Проверь PROFILE_FILES в config.py.", file=sys.stderr)
        sys.exit(1)
    return p


def _vacancy_text(args):
    """Возвращает текст вакансии: из --text или по id с Хабр Карьеры."""
    if args.text:
        return args.text
    v = habr_api.get_vacancy(args.vacancy_id)
    return habr_api.format_vacancy(v)


def cmd_search(args):
    data = habr_api.search_vacancies(args.query, per_page=args.per_page)
    items = data.get("items", [])
    print(f"Найдено: {data.get('found', 0)} вакансий. Показываю первые {len(items)}:\n")
    for i, v in enumerate(items, 1):
        name = v.get("name", "")
        employer = (v.get("employer") or {}).get("name", "")
        salary = v.get("salary") or {}
        sal = ""
        if salary.get("from") or salary.get("to"):
            sal = _fmt_salary(salary)
        print(f"{i}. {name} | {employer} | {sal}")
        print(f"   id={v.get('id')}  {v.get('alternate_url', '')}")
    print("\nДальше: python main.py apply <id>  или  python main.py evaluate <id>")


def _fmt_salary(s):
    c = s.get("currency") or ""
    f = s.get("from")
    t = s.get("to")
    if f and t:
        return f"{f}–{t} {c}"
    if f:
        return f"от {f} {c}"
    if t:
        return f"до {t} {c}"
    return c or "з/п не указана"


def cmd_evaluate(args):
    profile = _profile()
    text = _vacancy_text(args)
    print("Оцениваю соответствие…\n")
    result = apply_mod.evaluate_fit(text, profile)
    print(result)


def cmd_apply(args):
    profile = _profile()
    text = _vacancy_text(args)

    print("1/4. Генерирую черновики (cover letter + CV)…")
    cover, cv = apply_mod.draft_application(text, profile)

    print("2/4. Ревьюер проверяет…")
    feedback = apply_mod.review_application(cover, cv, text, profile)

    print("3/4. Вношу правки…")
    final = apply_mod.revise_application(cover, cv, feedback)

    print("4/4. Сохраняю…")
    out = config.OUTPUT_DIR
    (out / "cover_letter_draft.md").write_text(cover, encoding="utf-8")
    (out / "cv_draft.md").write_text(cv, encoding="utf-8")
    (out / "review.md").write_text(feedback, encoding="utf-8")
    (out / "final.md").write_text(final, encoding="utf-8")

    print(f"\nГотово. Файлы в {out}/")
    print("\n========== ИТОГОВАЯ ВЕРСИЯ ==========\n")
    print(final)


def main():
    parser = argparse.ArgumentParser(description="Mirra Job — ассистент поиска работы")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="поиск вакансий на Хабр Карьере")
    p_search.add_argument("query")
    p_search.add_argument("--per-page", type=int, default=config.HABR_PER_PAGE)
    p_search.set_defaults(func=cmd_search)

    p_eval = sub.add_parser("evaluate", help="оценка соответствия вакансии")
    p_eval.add_argument("vacancy_id", nargs="?")
    p_eval.add_argument("--text", help="текст вакансии вместо id")
    p_eval.set_defaults(func=cmd_evaluate)

    p_apply = sub.add_parser("apply", help="полный отклик (cover letter + CV + review)")
    p_apply.add_argument("vacancy_id", nargs="?")
    p_apply.add_argument("--text", help="текст вакансии вместо id")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        print("\nОшибка: " + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
