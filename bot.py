# -*- coding: utf-8 -*-
"""Telegram-бот для проведения письменного ассесмента и сохранения результатов в Google Sheets."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import questions
import scoring
import sheets

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

NAME, PART1, PART2, ESSAY = range(4)

LABELS = {"agree": "✅ Согласен", "disagree": "❌ Не согласен"}


def part1_keyboard(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Согласен", callback_data=f"p1c|{idx}|agree"),
                InlineKeyboardButton("❌ Не согласен", callback_data=f"p1c|{idx}|disagree"),
            ]
        ]
    )


def part2_keyboard(idx: int, item: dict, selected=None) -> InlineKeyboardMarkup:
    selected = selected or set()
    rows = []
    if item["multiple"]:
        for i, opt in enumerate(item["options"]):
            prefix = "☑️ " if i in selected else "⬜️ "
            rows.append([InlineKeyboardButton(prefix + opt, callback_data=f"p2t|{idx}|{i}")])
        rows.append([InlineKeyboardButton("✅ Готово", callback_data=f"p2d|{idx}")])
    else:
        for i, opt in enumerate(item["options"]):
            rows.append([InlineKeyboardButton(opt, callback_data=f"p2s|{idx}|{i}")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    text = (
        "📋 <b>Ассесмент по применению ИИ в научных исследованиях</b>\n\n"
        f"Формат: дистанционный, письменный. Время выполнения: 2,5 часа.\n"
        f"Дедлайн: {config.ASSESSMENT_DEADLINE}\n\n"
        "Ассесмент состоит из трёх частей:\n"
        "• Часть 1 – 15 утверждений («Согласен»/«Не согласен» + обоснование)\n"
        "• Часть 2 – 15 закрытых вопросов (в некоторых несколько верных ответов)\n"
        "• Часть 3 – эссе на 500–700 слов\n\n"
        "В любой момент можно прервать прохождение командой /cancel.\n\n"
        "Для начала укажите, пожалуйста, ваше ФИО:"
    )
    await update.message.reply_html(text, reply_markup=ReplyKeyboardRemove())
    return NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text.strip()
    if not full_name:
        await update.message.reply_text("Пожалуйста, введите ФИО текстом.")
        return NAME

    context.user_data["full_name"] = full_name
    context.user_data["p1_idx"] = 0
    context.user_data["p1_answers"] = []

    await update.message.reply_text(
        "Спасибо! Начинаем Часть 1 — «Согласись или опровергни».\n"
        "Для каждого утверждения выберите вариант, затем в отдельном сообщении дайте краткое "
        "обоснование (1–2 предложения)."
    )
    await send_part1_item(update.effective_chat.id, context)
    return PART1


async def send_part1_item(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["p1_idx"]
    item = questions.PART1[idx]
    text = f"<b>Утверждение {idx + 1} из {len(questions.PART1)}</b>\n\n{item['statement']}"
    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=part1_keyboard(idx)
    )


async def part1_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, idx_str, choice = query.data.split("|")
    idx = int(idx_str)

    if idx != context.user_data.get("p1_idx"):
        return PART1  # устаревшая кнопка от предыдущего сообщения

    context.user_data["p1_pending_choice"] = choice
    item = questions.PART1[idx]
    await query.edit_message_text(
        f"<b>Утверждение {idx + 1} из {len(questions.PART1)}</b>\n\n{item['statement']}\n\n"
        f"Ваш выбор: {LABELS[choice]}",
        parse_mode="HTML",
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Кратко обоснуйте свой ответ (1–2 предложения):",
    )
    return PART1


async def part1_justify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "p1_pending_choice" not in context.user_data:
        await update.message.reply_text(
            "Сначала выберите «Согласен» или «Не согласен» кнопкой выше."
        )
        return PART1

    idx = context.user_data["p1_idx"]
    item = questions.PART1[idx]
    justification = update.message.text.strip()

    context.user_data["p1_answers"].append(
        {"id": item["id"], "choice": context.user_data.pop("p1_pending_choice"), "justification": justification}
    )
    context.user_data["p1_idx"] += 1

    if context.user_data["p1_idx"] < len(questions.PART1):
        await send_part1_item(update.effective_chat.id, context)
        return PART1

    context.user_data["p2_idx"] = 0
    context.user_data["p2_answers"] = []
    context.user_data["p2_selected"] = set()
    await update.message.reply_text(
        "Часть 1 завершена ✅\n\nПереходим к Части 2 — закрытые вопросы. "
        "В некоторых вопросах может быть несколько правильных вариантов — тогда отмечайте их "
        "и нажимайте «Готово»."
    )
    await send_part2_item(update.effective_chat.id, context)
    return PART2


async def send_part2_item(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["p2_idx"]
    item = questions.PART2[idx]
    context.user_data["p2_selected"] = set()
    text = f"<b>Вопрос {idx + 1} из {len(questions.PART2)}</b>\n\n{item['question']}"
    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=part2_keyboard(idx, item)
    )


async def part2_single_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, idx_str, opt_str = query.data.split("|")
    idx, opt = int(idx_str), int(opt_str)

    if idx != context.user_data.get("p2_idx"):
        return PART2

    item = questions.PART2[idx]
    context.user_data["p2_answers"].append([opt])
    await query.edit_message_text(
        f"<b>Вопрос {idx + 1} из {len(questions.PART2)}</b>\n\n{item['question']}\n\n"
        f"Ваш выбор: {item['options'][opt]}",
        parse_mode="HTML",
    )
    return await advance_part2(query.message.chat_id, context)


async def part2_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, idx_str, opt_str = query.data.split("|")
    idx, opt = int(idx_str), int(opt_str)

    if idx != context.user_data.get("p2_idx"):
        return PART2

    selected = context.user_data.setdefault("p2_selected", set())
    if opt in selected:
        selected.remove(opt)
    else:
        selected.add(opt)

    item = questions.PART2[idx]
    await query.edit_message_reply_markup(reply_markup=part2_keyboard(idx, item, selected))
    return PART2


async def part2_multi_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, idx_str = query.data.split("|")
    idx = int(idx_str)

    if idx != context.user_data.get("p2_idx"):
        return PART2

    item = questions.PART2[idx]
    selected = sorted(context.user_data.get("p2_selected", set()))
    context.user_data["p2_answers"].append(selected)
    chosen_text = ", ".join(item["options"][i] for i in selected) if selected else "(ничего не выбрано)"
    await query.edit_message_text(
        f"<b>Вопрос {idx + 1} из {len(questions.PART2)}</b>\n\n{item['question']}\n\n"
        f"Ваш выбор: {chosen_text}",
        parse_mode="HTML",
    )
    return await advance_part2(query.message.chat_id, context)


async def advance_part2(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["p2_idx"] += 1
    if context.user_data["p2_idx"] < len(questions.PART2):
        await send_part2_item(chat_id, context)
        return PART2

    context.user_data["essay_parts"] = []
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Часть 2 завершена ✅\n\n"
            f"<b>Часть 3. Эссе ({questions.ESSAY_MIN_WORDS}–{questions.ESSAY_MAX_WORDS} слов)</b>\n\n"
            f"Тема: «{questions.ESSAY_TOPIC}»\n\n"
            f"Рекомендуемая структура:\n{questions.ESSAY_STRUCTURE}\n\n"
            "Можно отправить эссе одним или несколькими сообщениями подряд. "
            "Когда закончите — отправьте команду /done."
        ),
        parse_mode="HTML",
    )
    return ESSAY


async def essay_collect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("essay_parts", []).append(update.message.text)
    words_so_far = len(" ".join(context.user_data["essay_parts"]).split())
    await update.message.reply_text(
        f"Принято. Слов пока: {words_so_far}. Продолжайте писать или отправьте /done, когда закончите."
    )
    return ESSAY


async def essay_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    essay_text = "\n\n".join(context.user_data.get("essay_parts", [])).strip()
    word_count = len(essay_text.split()) if essay_text else 0

    if word_count == 0:
        await update.message.reply_text("Вы ещё не написали эссе. Отправьте текст, затем /done.")
        return ESSAY

    if word_count < questions.ESSAY_MIN_WORDS or word_count > questions.ESSAY_MAX_WORDS:
        await update.message.reply_text(
            f"⚠️ В эссе {word_count} слов — вне рекомендованного диапазона "
            f"{questions.ESSAY_MIN_WORDS}–{questions.ESSAY_MAX_WORDS}. "
            "Всё равно завершаю проверку с текущим текстом."
        )

    await update.message.reply_text(
        "Спасибо! Ассесмент завершён. Обрабатываю и оцениваю ваши ответы, это может занять "
        "до минуты…"
    )

    try:
        result = await scoring.grade_all(
            context.user_data["p1_answers"], context.user_data["p2_answers"], essay_text
        )
    except Exception:
        logger.exception("Grading failed for user %s", update.effective_user.id)
        await update.message.reply_text(
            "Произошла ошибка при автоматической проверке. Ваши ответы сохранены, "
            "результат будет проверен вручную."
        )
        return ConversationHandler.END

    try:
        sheets.save_result(
            "telegram",
            update.effective_user.id,
            update.effective_user.username or "",
            context.user_data["full_name"],
            "",
            essay_text,
            result,
        )
    except Exception:
        logger.exception("Failed to save result to Google Sheets for user %s", update.effective_user.id)
        await update.message.reply_text(
            "⚠️ Не удалось сохранить результат в Google Sheets (проверьте настройки доступа). "
            "Результат показан ниже, но не сохранён."
        )

    summary = (
        "📊 <b>Результаты ассесмента</b>\n\n"
        f"Часть 1: {result['part1']['total']} / {result['part1']['max']}\n"
        f"Часть 2: {result['part2']['total']} / {result['part2']['max']}\n"
        f"Часть 3 (эссе): {result['part3']['total']} / {result['part3']['max']}\n\n"
        f"<b>Итого: {result['total']} / {result['max_total']}</b>\n"
        f"<b>Оценка: {result['grade']}</b>"
    )
    if result["part3"].get("overall_comment"):
        summary += f"\n\n<i>Комментарий по эссе:</i> {result['part3']['overall_comment']}"

    await update.message.reply_html(summary)
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Прохождение ассесмента прервано. Чтобы начать заново, отправьте /start.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            PART1: [
                CallbackQueryHandler(part1_choice, pattern=r"^p1c\|"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, part1_justify),
            ],
            PART2: [
                CallbackQueryHandler(part2_single_choice, pattern=r"^p2s\|"),
                CallbackQueryHandler(part2_toggle, pattern=r"^p2t\|"),
                CallbackQueryHandler(part2_multi_done, pattern=r"^p2d\|"),
            ],
            ESSAY: [
                CommandHandler("done", essay_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, essay_collect),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
