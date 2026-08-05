# -*- coding: utf-8 -*-
"""Веб-версия ассесмента: та же логика вопросов/проверки/сохранения, что и в Telegram-боте."""
import logging
import uuid

from flask import Flask, jsonify, render_template, request

import questions
import scoring
import sheets

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def _public_questions() -> dict:
    return {
        "part1": [{"id": it["id"], "statement": it["statement"]} for it in questions.PART1],
        "part2": [
            {
                "id": it["id"],
                "question": it["question"],
                "options": it["options"],
                "multiple": it["multiple"],
            }
            for it in questions.PART2
        ],
        "essay": {
            "topic": questions.ESSAY_TOPIC,
            "min_words": questions.ESSAY_MIN_WORDS,
            "max_words": questions.ESSAY_MAX_WORDS,
            "structure": questions.ESSAY_STRUCTURE,
        },
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/questions")
def api_questions():
    return jsonify(_public_questions())


def _validate_submission(payload: dict):
    full_name = (payload.get("full_name") or "").strip()
    if not full_name:
        return "Укажите ФИО."

    p1_by_id = {a.get("id"): a for a in payload.get("part1", [])}
    for item in questions.PART1:
        ans = p1_by_id.get(item["id"])
        if not ans or ans.get("choice") not in ("agree", "disagree"):
            return f"Не заполнен ответ на утверждение №{item['id']} (Часть 1)."
        if not (ans.get("justification") or "").strip():
            return f"Не заполнено обоснование к утверждению №{item['id']} (Часть 1)."

    p2_by_id = {a.get("id"): a for a in payload.get("part2", [])}
    for item in questions.PART2:
        ans = p2_by_id.get(item["id"])
        selected = (ans or {}).get("selected") or []
        if not selected:
            return f"Не выбран ответ на вопрос №{item['id']} (Часть 2)."

    essay_text = (payload.get("essay_text") or "").strip()
    if not essay_text:
        return "Не заполнено эссе (Часть 3)."

    return None


@app.post("/api/submit")
async def api_submit():
    payload = request.get_json(force=True, silent=True) or {}
    error = _validate_submission(payload)
    if error:
        return jsonify({"error": error}), 400

    full_name = payload["full_name"].strip()
    email = (payload.get("email") or "").strip()
    essay_text = payload["essay_text"].strip()

    p1_by_id = {a["id"]: a for a in payload["part1"]}
    part1_answers = [
        {
            "id": item["id"],
            "choice": p1_by_id[item["id"]]["choice"],
            "justification": p1_by_id[item["id"]]["justification"],
        }
        for item in questions.PART1
    ]

    p2_by_id = {a["id"]: a for a in payload["part2"]}
    part2_answers = [p2_by_id[item["id"]]["selected"] for item in questions.PART2]

    try:
        result = await scoring.grade_all(part1_answers, part2_answers, essay_text)
    except Exception:
        logger.exception("Grading failed for web submission (%s)", full_name)
        return jsonify({"error": "Ошибка автоматической проверки. Попробуйте отправить ещё раз чуть позже."}), 500

    participant_id = str(uuid.uuid4())
    try:
        sheets.save_result("web", participant_id, "", full_name, email, essay_text, result)
    except Exception:
        logger.exception("Failed to save web result to Google Sheets (%s)", full_name)
        result["save_warning"] = "Не удалось сохранить результат в Google Sheets."

    return jsonify(
        {
            "part1": {"total": result["part1"]["total"], "max": result["part1"]["max"]},
            "part2": {"total": result["part2"]["total"], "max": result["part2"]["max"]},
            "part3": {
                "total": result["part3"]["total"],
                "max": result["part3"]["max"],
                "comment": result["part3"].get("overall_comment", ""),
            },
            "total": result["total"],
            "max_total": result["max_total"],
            "grade": result["grade"],
            "save_warning": result.get("save_warning"),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
