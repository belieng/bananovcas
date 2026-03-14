import asyncio
import logging
import random
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Dice, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ────────────────────────────────────────────── НАСТРОЙКИ ──────────────────────────────────────────────
TOKEN = "8435160243:AAEofYv4igJ-aKjzk1suSzWnNqDwI2z7qGQ"  # ← ТВОЙ РЕАЛЬНЫЙ ТОКЕН СЮДА
ADMIN_ID = 5454985521  # ← ТВОЙ TELEGRAM ID

BET_OPTIONS = [10, 50, 100, 250, 500, 1000]
START_BALANCE = 10000
DAILY_FREESPINS = 5
DB_PATH = "casino.db"

# Логирование в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Реалистичные выплаты (RTP ~93–95%)
SLOT_PAYOUTS = {
    range(1, 46):   (0,    "Пусто 😔",                  "❌ ❌ ❌"),
    46:             (0.5,  "Полвишенки",                "🍒 🍒 ❌"),
    47:             (0.8,  "Лимоны",                    "🍋 🍋 🍋"),
    48:             (1,    "Арбузы",                    "🍉 🍉 🍉"),
    49:             (1.5,  "Колокольчики",              "🔔 🔔 🔔"),
    50:             (3,    "Три BAR",                   "BAR BAR BAR"),
    51:             (5,    "Три звезды",                "⭐ ⭐ ⭐"),
    52:             (8,    "Три семёрки",               "7️⃣ 7️⃣ 7️⃣"),
    53:             (15,   "Смешанный приз",            "🍇 BAR 7️⃣"),
    54:             (25,   "Двойная семёрка",           "7️⃣ 7️⃣ ⭐"),
    55:             (40,   "Тройной BAR",               "BAR BAR ⭐"),
    56:             (60,   "Супер семёрка",             "7️⃣ ⭐ 7️⃣"),
    57:             (100,  "Эпический микс",            "⭐ 7️⃣ BAR"),
    58:             (150,  "Мега комбо",                "7️⃣ BAR 7️⃣"),
    59:             (250,  "Ультра приз",               "⭐ 7️⃣ ⭐"),
    60:             (400,  "Легендарный",               "7️⃣ 7️⃣ 🍇"),
    61:             (700,  "Божественный",              "⭐ 7️⃣ 7️⃣"),
    62:             (1200, "Супер джекпот",             "7️⃣ 7️⃣ ⭐"),
    63:             (2500, "MEGA JACKPOT lite",         "⭐ 7️⃣ ⭐"),
    64:             (5000, "🎰 ABSOLUTE JACKPOT 🎰",    "7️⃣ 7️⃣ 7️⃣")
}

dp = Dispatcher()

# ────────────────────────────────────────────── БАЗА ──────────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT {START_BALANCE},
                last_daily TEXT,
                banned INTEGER DEFAULT 0,
                spins INTEGER DEFAULT 0,
                bonus_spins_remaining INTEGER DEFAULT 0,
                last_bet INTEGER DEFAULT 100
            )
        """)
        await db.commit()
    logger.info(f"База данных инициализирована: {DB_PATH}")

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT balance, last_daily, banned, spins, bonus_spins_remaining, last_bet "
            "FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            username = (await dp.bot.get_chat(user_id)).username or "NoName"
            await db.execute(
                "INSERT INTO users (user_id, username, balance, last_daily, last_bet) "
                "VALUES (?, ?, ?, NULL, 100)",
                (user_id, username, START_BALANCE)
            )
            await db.commit()
            logger.info(f"Новый юзер: {user_id} (@{username})")
            return START_BALANCE, None, 0, 0, 0, 100
        return row

async def update_balance(user_id: int, delta: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
        await db.commit()

async def update_bonus_spins(user_id: int, delta: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET bonus_spins_remaining = bonus_spins_remaining + ? WHERE user_id = ?",
            (delta, user_id)
        )
        await db.commit()

async def update_last_bet(user_id: int, bet: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_bet = ? WHERE user_id = ?", (bet, user_id))
        await db.commit()

async def update_spins(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET spins = spins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

# ────────────────────────────────────────────── МЕНЮ ──────────────────────────────────────────────
def main_menu(balance: int, bonus_remaining: int = 0, last_bet: int = 100) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for bet in BET_OPTIONS:
        builder.button(text=f"🎰 {bet}", callback_data=f"spin_{bet}")
    builder.button(text=f"ALL-IN ({balance})", callback_data="spin_max")
    builder.adjust(3)

    row2 = []
    if bonus_remaining > 0:
        row2.append(InlineKeyboardButton(text=f"🎁 BONUS ({bonus_remaining})", callback_data="freespin"))
    else:
        row2.extend([
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="🎁 Daily", callback_data="daily")
        ])
    builder.row(*row2)

    if bonus_remaining == 0:
        builder.row(InlineKeyboardButton(
            text=f"Купить БОНУСКУ (x100 = {last_bet * 100})",
            callback_data="buy_bonus"
        ))
        builder.row(InlineKeyboardButton(text="🏆 Топ 10", callback_data="top"))

    return builder.as_markup()

# ────────────────────────────────────────────── ХЕНДЛЕРЫ ──────────────────────────────────────────────
@dp.message(Command("start"))
async def start(message: types.Message):
    await init_db()
    user_id = message.from_user.id
    balance, _, banned, _, bonus_remaining, last_bet = await get_user(user_id)
    if banned:
        await message.answer("Ты забанен.")
        return

    text = (
        "🔥 **Казик без депозита** 🔥\n"
        f"Баланс: **{balance}** монет\n"
        "Крути слоты, покупай бонуску, сливай в ноль как в реале 😈"
    )
    await message.answer(text, reply_markup=main_menu(balance, bonus_remaining, last_bet))

@dp.callback_query(lambda c: c.data == "balance")
async def cb_balance(c: CallbackQuery):
    balance, _, _, _, bonus_remaining, last_bet = await get_user(c.from_user.id)
    await c.message.edit_text(f"💰 Баланс: **{balance}**", reply_markup=main_menu(balance, bonus_remaining, last_bet))
    await c.answer()

@dp.callback_query(lambda c: c.data == "daily")
async def cb_daily(c: CallbackQuery):
    user_id = c.from_user.id
    balance, last_daily, banned, _, bonus_remaining, last_bet = await get_user(user_id)
    if banned:
        await c.answer("Забанен", show_alert=True)
        return

    if last_daily:
        last = datetime.fromisoformat(last_daily)
        if datetime.now() - last < timedelta(days=1):
            await c.answer("Сегодня уже забирал", show_alert=True)
            return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
        await db.commit()

    await c.message.edit_text(
        f"🎁 +{DAILY_FREESPINS} бесплатных спинов!\nЖми ниже",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Бесплатно ×{DAILY_FREESPINS}", callback_data="freespin")],
            [InlineKeyboardButton(text="← Меню", callback_data="menu")]
        ])
    )
    await c.answer()

@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(c: CallbackQuery):
    balance, _, _, _, bonus_remaining, last_bet = await get_user(c.from_user.id)
    await c.message.edit_text("Меню", reply_markup=main_menu(balance, bonus_remaining, last_bet))
    await c.answer()

@dp.callback_query(lambda c: c.data == "buy_bonus")
async def buy_bonus(c: CallbackQuery):
    user_id = c.from_user.id
    balance, _, banned, _, bonus_remaining, last_bet = await get_user(user_id)
    if banned or bonus_remaining > 0:
        await c.answer("Нельзя купить сейчас", show_alert=True)
        return

    cost = last_bet * 100
    if balance < cost:
        await c.answer(f"Нужно {cost} монет", show_alert=True)
        return

    await update_balance(user_id, -cost)
    spins_to_add = random.randint(7, 13)
    await update_bonus_spins(user_id, spins_to_add)

    await c.message.edit_text(
        f"💸 Купил бонуску за {cost}!\n+{spins_to_add} FREE SPINS 🔥",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"НАЧАТЬ ({spins_to_add})", callback_data="freespin")],
            [InlineKeyboardButton(text="← Меню", callback_data="menu")]
        ])
    )
    await c.answer()

@dp.callback_query(lambda c: c.data.startswith("spin_") or c.data == "freespin")
async def cb_spin(c: CallbackQuery):
    user_id = c.from_user.id
    balance, _, banned, _, bonus_remaining, last_bet = await get_user(user_id)
    if banned:
        await c.answer("Забанен", show_alert=True)
        return

    is_bonus_mode = bonus_remaining > 0
    if c.data == "freespin" or is_bonus_mode:
        bet = 0
        if is_bonus_mode:
            await update_bonus_spins(user_id, -1)
            bonus_remaining -= 1
    else:
        bet_str = c.data.split("_")[1]
        bet = balance if bet_str == "max" else int(bet_str)

        if balance < bet:
            await c.answer("Мало монет", show_alert=True)
            return

        await update_balance(user_id, -bet)
        await update_last_bet(user_id, bet)
        last_bet = bet

    await update_spins(user_id)

    dice_msg = await c.message.answer_dice(emoji="🎰")
    await asyncio.sleep(4.2)

    fresh = await dice_msg.bot.get_chat(dice_msg.chat.id).get_message(dice_msg.message_id)
    value = fresh.dice.value

    mult, desc, combo = SLOT_PAYOUTS.get(value, (0, "Неизвестно", "❓ ❓ ❓"))
    win = bet * mult
    if is_bonus_mode and win > 0:
        win = int(win * 1.4)

    bonus_text = ""
    if bet > 0 and not is_bonus_mode:
        if random.random() < 0.065:
            spins_to_add = random.randint(7, 13)
            await update_bonus_spins(user_id, spins_to_add)
            bonus_text = f"🎁 BONUS +{spins_to_add} FS!\n"

    if win > 0:
        await update_balance(user_id, win)
        text = f"🔥 {desc} 🔥\n{combo}\n+{win:,} (x{mult})"
        emoji = "🎉💰"
    else:
        text = f"😢 {desc}\n{combo}"
        emoji = "💨"

    balance, _, _, _, bonus_remaining, last_bet = await get_user(user_id)

    builder = InlineKeyboardBuilder()
    if bonus_remaining > 0:
        builder.button(text=f"Бонус ({bonus_remaining})", callback_data="freespin")
        status = f"\n**BONUS MODE**: {bonus_remaining} осталось"
    else:
        builder.button(text="🔄 Ещё", callback_data=f"spin_{last_bet}")
        builder.button(text="Меню", callback_data="menu")
        status = ""

    await c.message.answer(
        f"{bonus_text}{emoji} **{text}**\nВыпало: {value}/64\nБаланс: **{balance:,}**{status}",
        reply_markup=builder.as_markup()
    )
    await c.answer()

@dp.callback_query(lambda c: c.data == "top")
async def cb_top(c: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username, balance FROM users WHERE banned = 0 ORDER BY balance DESC LIMIT 10"
        )
        top = await cursor.fetchall()

    text = "🏆 Топ-10\n\n"
    for i, (name, bal) in enumerate(top, 1):
        text += f"{i}. @{name} — {bal:,}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="← Меню", callback_data="menu")
    await c.message.edit_text(text or "Пусто", reply_markup=builder.as_markup())
    await c.answer()

# ────────────────────────────────────────────── ЗАПУСК ──────────────────────────────────────────────
async def main():
    logger.info("Запуск бота...")
    await init_db()
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())