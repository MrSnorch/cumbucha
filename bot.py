#!/usr/bin/env python3
"""
Kombucha Telegram Bot — полный гайд для новичков
Fermentation tracker with inline buttons, troubleshooting tips, beginner warnings.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STATE_FILE = Path("state.json")
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]  # e.g. @mychannel or -100xxxxxxxxx

# ---------------------------------------------------------------------------
# Schedules — (day_offset, step_key, emoji, title, body, buttons)
# ---------------------------------------------------------------------------

SCOBY_SCHEDULE = [
    (0, "scoby_d0", "🚀", "День 0 — ты только что запустил!",
     "Чек-лист перед стартом:\n\n"
     "🫙 Стеклянная банка (не пластик, не алюминий)\n"
     "🧻 Накрыто тканью или марлей в несколько слоёв\n"
     "💧 Чай полностью остужен до комнатной температуры перед добавлением SCOBY\n"
     "🍵 Добавил стартовую жидкость? (0,5 л комбучи из предыдущей варки — обязательно!)\n\n"
     "⚠️ ГЛАВНОЕ: не двигай и не трогай банку первые 5–7 дней. SCOBY только начинает формироваться.",
     [("✅ Всё сделал, поехали!", "done"), ("❓ Что такое стартер?", "what_is_starter")]),

    (3, "scoby_d3", "🔍", "День 3 — первый осмотр",
     "Смотри, не трогая:\n\n"
     "✅ Норма: тонкое желеобразное «облако» или плёнка на поверхности — начало SCOBY\n"
     "✅ Норма: пузырьки, коричневые нити снизу (дрожжи), лёгкий кисловатый запах\n"
     "✅ Норма: SCOBY тонет или висит посередине — он всё равно работает\n\n"
     "❌ Тревога: пушистые пятна ЗЕЛЁНОГО, ЧЁРНОГО, РОЗОВОГО цвета = плесень → выбрасывай всё",
     [("✅ Вижу плёнку, всё ок", "done"), ("😟 Ничего нет", "nothing_d3"), ("🆘 Вижу цветные пятна", "mold_alert"), ("⏰ Проверю позже", "snooze2h")]),

    (7, "scoby_d7", "🌱", "День 7 — SCOBY растёт",
     "К этому моменту должен быть заметный слой 1–3 мм.\n\n"
     "✅ Норма: слой неровный, с дырками, желтоватый или коричневатый — это нормально!\n"
     "✅ Норма: запах кисловатый, слегка уксусный\n\n"
     "Попробуй чай ложкой снизу: слегка кислый, ещё сладковатый — всё идёт хорошо.",
     [("✅ Слой есть, пахнет хорошо", "done"), ("📏 Слой очень тонкий", "thin_scoby"), ("⏰ Позже", "snooze2h")]),

    (10, "scoby_d10", "📏", "День 10 — проверка толщины",
     "SCOBY должен быть 3–5 мм — как плотный блин.\n\n"
     "Жидкость становится заметно кислее — хороший знак.\n"
     "Не пей пока — дай грибу набрать силу.\n\n"
     "Тоньше 3 мм? Не двигай банку ещё несколько дней — SCOBY дойдёт.",
     [("✅ 3–5 мм, отлично", "done"), ("📏 Тоньше, жду ещё", "thin_scoby"), ("⏰ Позже", "snooze2h")]),

    (14, "scoby_d14", "💪", "День 14 — SCOBY формируется",
     "К этому дню SCOBY обычно 5–8 мм — плотный, упругий диск.\n\n"
     "⚠️ Всё ещё тонкий? Проверь:\n"
     "• Добавлял ли стартовую жидкость? — без неё брожение сильно медленнее\n"
     "• Двигал банку? — это мешает SCOBY сформироваться\n\n"
     "При 20°C процесс просто медленнее — дай ещё неделю, 21 день нормальный срок.",
     [("✅ Выглядит отлично", "done"), ("📏 Тонковат, жду ещё", "thin_scoby"), ("⏰ Позже", "snooze2h")]),

    (21, "scoby_d21", "🏆", "День 21 — SCOBY готов!",
     "Если SCOBY 6–10 мм — он готов к первой полноценной варке! 🎉\n\n"
     "Что делать дальше:\n\n"
     "1️⃣ Чистыми руками достань SCOBY, положи в чистую миску\n"
     "2️⃣ Слей жидкость, ОСТАВИВ 10–20% (это твой стартер для следующей варки!)\n"
     "3️⃣ Вымой банку горячей водой БЕЗ мыла — мыло убивает культуру\n"
     "4️⃣ Завари новый чай (чёрный или зелёный), растори сахар, полностью остуди\n"
     "5️⃣ Перелей чай в банку, добавь стартер и SCOBY\n"
     "6️⃣ Используй /newbrew чтобы начать отслеживать первую ферментацию",
     [("🧼 Помыл, заливаю новую", "washed"), ("✅ Запустил /newbrew", "done"), ("⏰ Позже", "snooze2h")]),
]

BREW_SCHEDULE = [
    (0, "brew_d0", "⚗️", "Первая ферментация — День 0",
     "Чек-лист перед запуском:\n\n"
     "✅ Чай полностью остужен (выше 29°C убивает культуру)\n"
     "✅ Добавил стартовую жидкость (10–20% от объёма = ~200–400 мл на 2 л)\n"
     "✅ SCOBY помещён в банку\n"
     "✅ Накрыто тканью или марлей в несколько слоёв\n\n"
     "⏳ При ~20°C ферментация займёт около 10–14 дней. Пробуй на вкус с 5 дня.",
     [("✅ Всё готово, поехали!", "done"), ("⏰ Позже", "snooze2h")]),

    (2, "brew_d2", "🫗", "День 2 — проверь запах",
     "Не открывай часто — просто понюхай:\n\n"
     "✅ Норма: кисловатый, слегка уксусный аромат\n"
     "✅ Норма: пузырьки по стенкам, коричневые нити снизу (дрожжи)\n"
     "✅ Норма: новая тонкая плёнка сверху\n\n"
     "❌ Тревога: пушистые цветные пятна (зелёные, чёрные, розовые) = плесень",
     [("✅ Запах хороший", "done"), ("⚠️ Что-то странное", "suspicious"), ("🆘 Вижу плесень", "mold_alert"), ("⏰ Позже", "snooze2h")]),

    (5, "brew_d5", "🍵", "День 5 — первая проба вкуса",
     "Чистой ложкой попробуй жидкость снизу банки.\n\n"
     "🍋 Сладко-кислый → ещё 2–4 дня, брожение идёт\n"
     "✅ Приятно кислый с лёгкой сладостью → скоро готово!\n"
     "😬 Очень кислый / уксусный → перебродило. Сократи следующую варку на 2–3 дня\n\n"
     "Продолжай пробовать каждый день — момент готовности у всех разный.",
     [("🍋 Кисло, ещё жду", "done"), ("✅ Отличный вкус!", "done"), ("😬 Уксус...", "too_sour"), ("⏰ Позже", "snooze2h")]),

    (7, "brew_d7", "⚗️", "День 7 — основная проверка",
     "При 24–29°C обычно готово к 7–10 дням.\n\n"
     "Попробуй: должен быть баланс кислоты и лёгкой сладости.\n\n"
     "Готово? → разливай по плотным бутылкам и запускай /newf2\n"
     "Не готово? → пробуй ещё раз завтра и послезавтра\n\n"
     "💡 Чем дольше стоит — тем кислее. Не пропусти момент!",
     [("🍾 Готово, иду разливать!", "ready_to_bottle"), ("⏳ Ещё пару дней", "done"), ("⏰ Позже", "snooze2h")]),

    (10, "brew_d10", "🍾", "День 10 — финальный дедлайн",
     "Разлей СЕГОДНЯ, если ещё не сделал!\n"
     "Дольше 10–12 дней при 27°C = очень кислая / уксусная комбуча.\n\n"
     "Как разлить правильно:\n\n"
     "1️⃣ Достань SCOBY и положи в миску\n"
     "2️⃣ Оставь 10–20% жидкости как стартер для следующей варки\n"
     "3️⃣ Остальное разлей по стеклянным бутылкам с плотной крышкой\n"
     "4️⃣ Вымой банку горячей водой БЕЗ мыла\n"
     "5️⃣ Запускай /newf2 для второй ферментации (газирование)",
     [("🍾 Разлил по бутылкам!", "ready_to_bottle"), ("🧼 Помыл банку", "washed"), ("⏰ Позже", "snooze2h")]),
]

F2_SCHEDULE = [
    (0, "f2_d0", "🫧", "Вторая ферментация — День 0",
     "Вторая ферментация = газирование + вкус.\n\n"
     "Что добавить в бутылку (по желанию):\n"
     "🍓 Ягоды / фрукты — 1–2 ст.л. на бутылку\n"
     "🫚 Имбирь — 1–2 тонких ломтика\n"
     "🍋 Лимон / апельсин — 1–2 кружочка\n"
     "🌿 Мята — несколько листочков\n\n"
     "⚠️ Важно:\n"
     "• Оставь 2–3 см сверху в бутылке — нужно место для газа\n"
     "• Используй стеклянные бутылки с плотной крышкой (типа Grolsch)\n"
     "• НЕ пластик — он не выдержит давление\n"
     "• Температура 20–24°C",
     [("✅ Бутылки закрыты!", "done"), ("🍓 Добавил вкусняшки", "done"), ("⏰ Позже", "snooze2h")]),

    (1, "f2_d1", "💨", "Вторая ферментация — День 1, стравли давление",
     "Раз в день нужно АККУРАТНО стравливать давление:\n\n"
     "1️⃣ Держи бутылку над раковиной\n"
     "2️⃣ Медленно приоткрой крышку — услышишь шипение\n"
     "3️⃣ Сразу закрой обратно\n\n"
     "Это предотвращает взрыв бутылки и помогает контролировать газацию.\n\n"
     "Нажми на бутылку: мягкая = газа ещё мало, твёрдая = почти готово!",
     [("✅ Стравил, всё ок", "done"), ("💪 Бутылка уже твёрдая!", "fridge"), ("⏰ Позже", "snooze2h")]),

    (2, "f2_d2", "💥", "Вторая ферментация — День 2, проверь давление",
     "Нажми на бутылку:\n\n"
     "💪 Твёрдая и упругая → CO₂ накопился — готово!\n"
     "   → Сразу убери в холодильник. Холод останавливает брожение.\n\n"
     "😶 Мягкая → ещё 1–2 дня. Продолжай стравливать давление каждый день.\n\n"
     "⚠️ Не давай газу накапливаться слишком долго без стравливания — бутылка может взорваться!",
     [("💪 Твёрдая, убрал в холодильник!", "fridge"), ("😶 Мягкая, жду ещё", "done"), ("⏰ Позже", "snooze2h")]),

    (3, "f2_d3", "🎉", "Вторая ферментация — скорее всего готово!",
     "3 дня обычно хватает при 20–24°C.\n\n"
     "Если бутылки в холодильнике — отлично! Подожди ещё 12 часов и пробуй.\n"
     "Если ещё не убрал — нажми на бутылку: твёрдая = срочно в холодильник!\n\n"
     "Как открывать:\n"
     "🚿 Над раковиной\n"
     "🐌 Медленно, потихоньку откручивай\n"
     "🍵 Наслаждайся домашней комбучей!\n\n"
     "Не забудь сразу запустить новую варку — /newbrew 🔄",
     [("🍵 Попробовал — вкусно!", "done"), ("🔁 Запускаю новую варку", "done"), ("⏰ Позже", "snooze2h")]),
]

SCHEDULE_BY_MODE = {"scoby": SCOBY_SCHEDULE, "brew": BREW_SCHEDULE, "f2": F2_SCHEDULE}

CALLBACK_RESPONSES = {
    "done":             "✅ Отмечено! Хорошая работа 🍄",
    "washed":           "🧼 Отлично! Чистая банка = здоровый SCOBY. Можно заливать новую партию!",
    "thin_scoby":       "📏 Не переживай. Главное — температура 24–29°C и полный покой для банки. Дай ещё 5–7 дней.",
    "nothing_d3":       "😟 К дню 3 плёнка может ещё не образоваться — это нормально! Проверь температуру (нужно 24–29°C) и не двигай банку. Жди до дня 7.",
    "mold_alert":       "🆘 Плесень — это НЕ норма. Если видишь пушистые ЦВЕТНЫЕ пятна (зелёные, чёрные, розовые) — выбрасывай SCOBY и всю жидкость. Вымой банку с мылом, ошпарь кипятком. Начинай с нового SCOBY.",
    "suspicious":       "⚠️ Опиши что видишь:\n• Белые/кремовые пузыри или плёнка = НОРМА\n• Коричневые нити снизу = НОРМА (дрожжи)\n• Пушистые ЦВЕТНЫЕ пятна = ПЛЕСЕНЬ → выбрасывай\n\nПравило: если сомневаешься — понюхай. Хорошая комбуча пахнет кисло-уксусно, но приятно.",
    "too_sour":         "😬 Перебродило! Эту комбучу можно использовать как уксус для готовки или заправок. В следующий раз сократи время на 2–3 дня или следи с 5-го дня.",
    "ready_to_bottle":  "🍾 Время разливать! Не забудь оставить 10–20% жидкости как стартер. Запусти /newf2 для второй ферментации (газирование).",
    "fridge":           "❄️ В холодильнике брожение почти останавливается. Через 12+ часов можно пить — открывай медленно над раковиной!",
    "what_is_starter":  "💧 Стартовая жидкость — это уже готовая кислая комбуча из предыдущей варки.\n\nПочему она ОБЯЗАТЕЛЬНА:\n• Сразу снижает pH нового чая\n• Защищает brew от плесени в первые дни\n• Без неё риск заражения очень высок\n\nНорма: 10–20% от объёма (на 2 л чая — 200–400 мл стартера). У тебя уже было 0,5 л — это хорошо!",
    "snooze2h":         "⏰ Хорошо! Загляни попозже.",
}

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"brews": [], "pinned_message_id": None, "update_offset": 0}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def make_keyboard(buttons: list) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(label, callback_data=cb) for label, cb in buttons]
    rows = [row[i:i+2] for i in range(0, len(row), 2)]
    return InlineKeyboardMarkup(rows)


def build_pinned_message(state: dict) -> str:
    lines = ["🍄 *KOMBUCHA TRACKER*", ""]

    for brew in state["brews"]:
        start = datetime.fromisoformat(brew["started_at"])
        mode = brew["mode"]
        label = brew.get("label", f"Варка #{brew['id']}")

        mode_labels = {
            "scoby": "🌱 Выращивание SCOBY",
            "brew":  "⚗️ Первая ферментация",
            "f2":    "🫧 Вторая ферментация",
        }
        lines.append(f"*{label}*")
        lines.append(f"Начата: {start.strftime('%d.%m.%Y')} | {mode_labels[mode]}")

        now = datetime.now()
        done_steps = brew.get("done_steps_log", [])
        done_keys = {d.get("step_key") for d in done_steps}

        for day, step_key, emoji, title, _, _ in SCHEDULE_BY_MODE[mode]:
            target = start + timedelta(days=day)
            if step_key in done_keys:
                status = "✅"
            elif target.date() < now.date():
                status = "⚠️"
            elif target.date() == now.date():
                status = "⏰"
            else:
                status = "⏳"
            short_title = title.split(" — ", 1)[-1] if " — " in title else title
            lines.append(f"  {status} {emoji} {short_title} — {target.strftime('%d.%m')}")

        lines.append("")

    if not state["brews"]:
        lines.append("Нет активных варок.")
        lines.append("Напиши боту /start чтобы начать.")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"_Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

async def update_pinned_post(bot: Bot, state: dict):
    text = build_pinned_message(state)
    try:
        if state.get("pinned_message_id"):
            await bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=state["pinned_message_id"],
                text=text,
                parse_mode="Markdown",
            )
        else:
            msg = await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            await bot.pin_chat_message(chat_id=CHANNEL_ID, message_id=msg.message_id, disable_notification=True)
            state["pinned_message_id"] = msg.message_id
            save_state(state)
    except TelegramError as e:
        log.error(f"Pinned post error: {e}")


async def send_step_notification(bot: Bot, brew: dict, step_key: str, emoji: str, title: str, body: str, buttons: list):
    label = brew.get("label", f"Варка #{brew['id']}")
    text = f"🍄 *{label}*\n\n{emoji} *{title}*\n\n{body}"
    keyed_buttons = [(lbl, f"{brew['id']}:{step_key}:{cb}") for lbl, cb in buttons]
    keyboard = make_keyboard(keyed_buttons)
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except TelegramError as e:
        log.error(f"Notification error: {e}")


# ---------------------------------------------------------------------------
# Scheduler job
# ---------------------------------------------------------------------------

async def check_notifications(bot: Bot, state: dict):
    now = datetime.now()
    changed = False

    for brew in state["brews"]:
        start = datetime.fromisoformat(brew["started_at"])
        mode = brew["mode"]
        notified = brew.setdefault("notified", [])

        for day, step_key, emoji, title, body, buttons in SCHEDULE_BY_MODE[mode]:
            notify_key = f"sent_{step_key}"
            target = start + timedelta(days=day)
            if notify_key not in notified and target.date() == now.date():
                await send_step_notification(bot, brew, step_key, emoji, title, body, buttons)
                notified.append(notify_key)
                changed = True

    if changed:
        save_state(state)
        await update_pinned_post(bot, state)


# ---------------------------------------------------------------------------
# Callback query handler
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data  # format: "brew_id:step_key:action"

    parts = data.split(":", 2)
    if len(parts) != 3:
        await query.answer()
        return

    brew_id_str, step_key, action = parts
    state = load_state()
    brew = next((b for b in state["brews"] if str(b["id"]) == brew_id_str), None)

    if action == "snooze2h":
        await query.answer("⏰ Хорошо, загляни попозже!", show_alert=False)
        return

    # For informational callbacks, show alert without modifying state
    info_only = {"what_is_starter", "mold_alert", "suspicious", "nothing_d3", "thin_scoby", "too_sour"}
    response = CALLBACK_RESPONSES.get(action, "✅")
    user = query.from_user
    name = user.first_name or user.username or "Кто-то"

    if action not in info_only and brew:
        brew.setdefault("done_steps_log", []).append({
            "step_key": step_key,
            "action": action,
            "at": datetime.now().isoformat(),
            "by": name,
        })
        save_state(state)
        await update_pinned_post(context.bot, state)

    await query.answer(f"{response}", show_alert=True)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "🍄 *Kombucha Bot — справка*\n\n"
    "*Запуск варок:*\n"
    "/newscoby — выращивание SCOBY (с сегодня)\n"
    "/newbrew — первая ферментация\n"
    "/newf2 — вторая ферментация (газирование)\n\n"
    "*Управление:*\n"
    "/status — текущее состояние\n"
    "/tips — советы для новичков\n"
    "/clear — удалить все варки\n\n"
    "*Порядок процесса:*\n"
    "1️⃣ /newscoby — ждёшь 2–3 недели пока вырастет SCOBY\n"
    "2️⃣ /newbrew — первая ферментация 7–10 дней\n"
    "3️⃣ /newf2 — вторая ферментация (газирование) 2–3 дня\n"
    "4️⃣ Пьёшь и повторяешь с шага 2!"
)

TIPS_TEXT = (
    "📚 *Советы для новичков*\n\n"
    "🌡 *Температура — самое важное*\n"
    "Идеал 24–29°C. Холоднее 20°C = риск плесени.\n"
    "Зимой используй грелку для рассады.\n\n"
    "💧 *Стартовая жидкость обязательна*\n"
    "10–20% от объёма кислой готовой комбучи.\n"
    "Без неё brew уязвим для плесени первые дни.\n\n"
    "🫙 *Только стекло*\n"
    "Никакого пластика или алюминия.\n\n"
    "🧻 *Накрывай правильно*\n"
    "Плотная ткань или кофейный фильтр.\n"
    "Марля — слишком рыхлая, пролезут мушки!\n\n"
    "🍵 *Чай и сахар*\n"
    "Чёрный чай — надёжнее всего для начинающих.\n"
    "Белый сахар — идеален. Не мёд (убивает культуру).\n\n"
    "🚫 *Не делай это*\n"
    "• Не двигай банку первые 5–7 дней\n"
    "• Не ставь в холодильник во время Ф1\n"
    "• Не мой банку с мылом — только горячей водой\n"
    "• Не используй хлорированную воду без отстаивания\n\n"
    "🔍 *Плесень vs норма*\n"
    "НОРМА: белые пузыри, коричневые нити, неровная плёнка\n"
    "ПЛЕСЕНЬ: пушистые пятна ЛЮБОГО цвета кроме белого\n"
    "При плесени — выбрасывай всё, начинай заново."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_tips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TIPS_TEXT, parse_mode="Markdown")


async def _add_brew(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    state = load_state()
    label_map = {"scoby": "🌱 SCOBY", "brew": "⚗️ Ферментация", "f2": "🫧 Газирование"}
    brew_id = len(state["brews"]) + 1
    brew = {
        "id": brew_id,
        "mode": mode,
        "label": f"{label_map[mode]} #{brew_id}",
        "started_at": datetime.now().isoformat(),
        "notified": [],
        "done_steps_log": [],
    }
    state["brews"].append(brew)
    save_state(state)
    await update.message.reply_text(
        f"✅ *{brew['label']}* начата сегодня!\nУведомления придут по расписанию.\n\n"
        f"Напиши /tips чтобы увидеть советы для новичков.",
        parse_mode="Markdown",
    )
    await update_pinned_post(context.bot, state)


async def cmd_newscoby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _add_brew(update, context, "scoby")

async def cmd_newbrew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _add_brew(update, context, "brew")

async def cmd_newf2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _add_brew(update, context, "f2")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    await update.message.reply_text(build_pinned_message(state), parse_mode="Markdown")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["brews"] = []
    save_state(state)
    await update.message.reply_text("🗑 Все варки удалены.")
    await update_pinned_post(context.bot, state)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    state = load_state()

    if not state["brews"]:
        log.info("No brews — auto-starting SCOBY brew from today.")
        state["brews"].append({
            "id": 1,
            "mode": "scoby",
            "label": "🌱 SCOBY #1",
            "started_at": datetime.now().isoformat(),
            "notified": [],
            "done_steps_log": [],
        })
        save_state(state)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tips", cmd_tips))
    app.add_handler(CommandHandler("newscoby", cmd_newscoby))
    app.add_handler(CommandHandler("newbrew", cmd_newbrew))
    app.add_handler(CommandHandler("newf2", cmd_newf2))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(handle_callback))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_notifications, "interval", hours=1,
        args=[app.bot, state], next_run_time=datetime.now(),
    )
    scheduler.add_job(
        update_pinned_post, "interval", hours=6,
        args=[app.bot, state],
    )

    async def on_startup(application):
        scheduler.start()
        await update_pinned_post(application.bot, state)
        log.info("Bot started.")

    app.post_init = on_startup
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
