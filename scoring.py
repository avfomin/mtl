# -*- coding: utf-8 -*-
"""Подсчёт баллов по всем трём частям ассесмента."""
import asyncio
import logging
import re

import config
import questions
from llm_client import LLMError, ask_llm

logger = logging.getLogger(__name__)

LABELS = {"agree": "Согласен", "disagree": "Не согласен"}


async def grade_part1_item(item: dict, user_choice: str, justification: str) -> dict:
    """Возвращает {points, correct_choice, comment} для одного утверждения Части 1."""
    correct_choice = item["correct"] == user_choice

    if not correct_choice:
        return {
            "points": 0,
            "correct_choice": False,
            "llm_verdict": None,
            "comment": "Неверный выбор ответа.",
        }

    prompt = questions.PART1_JUSTIFICATION_PROMPT_TEMPLATE.format(
        statement=item["statement"],
        correct_label=LABELS[item["correct"]],
        key_arguments=item["key_arguments"],
        user_label=LABELS[user_choice],
        choice_correctness="верно",
        justification=justification.strip() or "(обоснование не предоставлено)",
    )

    if not justification.strip():
        return {
            "points": 1,
            "correct_choice": True,
            "llm_verdict": False,
            "comment": "Выбор верный, но обоснование отсутствует.",
        }

    try:
        raw = await ask_llm(prompt)
    except LLMError as exc:
        logger.warning("LLM grading failed for part1 item %s: %s", item["id"], exc)
        return {
            "points": 1,
            "correct_choice": True,
            "llm_verdict": None,
            "comment": f"Не удалось автоматически проверить обоснование ({exc}). Начислен 1 балл, требуется ручная проверка.",
        }

    verdict_match = re.search(r"Вердикт:\s*(ВЕРНО|НЕВЕРНО)", raw, re.IGNORECASE)
    comment_match = re.search(r"Комментарий:\s*(.+)", raw, re.DOTALL)
    verdict_ok = bool(verdict_match) and verdict_match.group(1).upper() == "ВЕРНО"
    comment = comment_match.group(1).strip() if comment_match else raw.strip()

    return {
        "points": 2 if verdict_ok else 1,
        "correct_choice": True,
        "llm_verdict": verdict_ok,
        "comment": comment,
    }


async def grade_part1(answers: list) -> dict:
    """answers: список {id, choice, justification} по порядку questions.PART1."""
    sem = asyncio.Semaphore(config.LLM_CONCURRENCY)

    async def bound_grade(item, ans):
        async with sem:
            return await grade_part1_item(item, ans["choice"], ans["justification"])

    tasks = [bound_grade(item, ans) for item, ans in zip(questions.PART1, answers)]
    results = await asyncio.gather(*tasks)

    total = sum(r["points"] for r in results)
    return {"total": total, "max": questions.TOTAL_MAX["part1"], "details": results}


def grade_part2(answers: list) -> dict:
    """answers: список списков выбранных индексов (int) по порядку questions.PART2."""
    details = []
    total = 0
    for item, selected in zip(questions.PART2, answers):
        selected_set = set(selected or [])
        correct_set = set(item["correct"])
        is_correct = selected_set == correct_set
        points = 1 if is_correct else 0
        total += points
        details.append({"id": item["id"], "correct": is_correct, "selected": sorted(selected_set)})
    return {"total": total, "max": questions.TOTAL_MAX["part2"], "details": details}


async def grade_essay(essay_text: str) -> dict:
    prompt = questions.ESSAY_GRADING_PROMPT_TEMPLATE.format(essay_text=essay_text)
    try:
        raw = await ask_llm(prompt, max_tokens=900)
    except LLMError as exc:
        logger.warning("LLM grading failed for essay: %s", exc)
        return {
            "total": 0,
            "max": questions.TOTAL_MAX["part3"],
            "criteria": [],
            "overall_comment": f"Не удалось автоматически оценить эссе ({exc}). Требуется ручная проверка.",
            "raw": None,
        }

    criteria = []
    for i in range(1, 5):
        m = re.search(rf"Критерий\s*{i}:\s*(\d+)\s*[–-]\s*(.+)", raw)
        if m:
            criteria.append({"criterion": i, "score": int(m.group(1)), "comment": m.group(2).strip()})
        else:
            criteria.append({"criterion": i, "score": 0, "comment": "не удалось распарсить ответ модели"})

    total_match = re.search(r"Итоговый балл:\s*(\d+)", raw)
    comment_match = re.search(r"Общий комментарий:\s*(.+)", raw, re.DOTALL)

    total = int(total_match.group(1)) if total_match else sum(c["score"] for c in criteria)
    overall_comment = comment_match.group(1).strip() if comment_match else ""

    return {
        "total": total,
        "max": questions.TOTAL_MAX["part3"],
        "criteria": criteria,
        "overall_comment": overall_comment,
        "raw": raw,
    }


async def grade_all(part1_answers: list, part2_answers: list, essay_text: str) -> dict:
    part1_task = grade_part1(part1_answers)
    essay_task = grade_essay(essay_text)
    part1_result, essay_result = await asyncio.gather(part1_task, essay_task)
    part2_result = grade_part2(part2_answers)

    total = part1_result["total"] + part2_result["total"] + essay_result["total"]
    grade = questions.score_to_grade(total)

    return {
        "part1": part1_result,
        "part2": part2_result,
        "part3": essay_result,
        "total": total,
        "max_total": questions.TOTAL_MAX["overall"],
        "grade": grade,
    }
