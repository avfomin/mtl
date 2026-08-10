# -*- coding: utf-8 -*-
"""Сохранение результатов ассесмента в Google Sheets."""
import json
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER = [
    "timestamp_utc",
    "source",
    "participant_id",
    "username",
    "full_name",
    "email",
    "part1_score",
    "part1_max",
    "part2_score",
    "part2_max",
    "part3_score",
    "part3_max",
    "total_score",
    "total_max",
    "grade",
    "essay_word_count",
    "essay_text",
    "essay_comment",
    "part1_details_json",
    "part2_details_json",
    "part3_details_json",
]

_client = None
_worksheet = None


def _get_worksheet():
    global _client, _worksheet
    if _worksheet is not None:
        return _worksheet

    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID не задан в .env")

    if config.GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT:
        info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    _client = gspread.authorize(creds)
    spreadsheet = _client.open_by_key(config.GOOGLE_SHEET_ID)

    try:
        ws = spreadsheet.worksheet(config.GOOGLE_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=config.GOOGLE_SHEET_NAME, rows=1000, cols=len(HEADER))

    existing_header = ws.row_values(1)
    if existing_header != HEADER:
        if not existing_header and ws.row_count <= 1 or len(ws.get_all_values()) <= 1:
            ws.update("A1", [HEADER])
        else:
            logger.warning(
                "Заголовок листа '%s' не совпадает с текущей схемой HEADER, но в листе уже есть "
                "данные — заголовок НЕ перезаписан, чтобы не сломать раскладку старых строк. "
                "existing=%s expected=%s",
                config.GOOGLE_SHEET_NAME, existing_header, HEADER,
            )

    _worksheet = ws
    return _worksheet


def save_result(
    source: str,
    participant_id,
    username: str,
    full_name: str,
    email: str,
    essay_text: str,
    result: dict,
) -> None:
    """source: 'telegram' или 'web'. participant_id: telegram user id или произвольный id веб-сессии."""
    ws = _get_worksheet()

    row = [
        datetime.now(timezone.utc).isoformat(),
        source,
        participant_id,
        username or "",
        full_name,
        email or "",
        result["part1"]["total"],
        result["part1"]["max"],
        result["part2"]["total"],
        result["part2"]["max"],
        result["part3"]["total"],
        result["part3"]["max"],
        result["total"],
        result["max_total"],
        result["grade"],
        len(essay_text.split()),
        essay_text,
        result["part3"].get("overall_comment", ""),
        json.dumps(result["part1"]["details"], ensure_ascii=False),
        json.dumps(result["part2"]["details"], ensure_ascii=False),
        json.dumps(result["part3"].get("criteria", []), ensure_ascii=False),
    ]
    ws.append_row(row, value_input_option="RAW")
    logger.info("Saved assessment result for %s participant %s to Google Sheets", source, participant_id)
