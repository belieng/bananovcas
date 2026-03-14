import asyncio
import logging
import aiosqlite
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Dice, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ────────────────────────────────────────────── НАСТРОЙКИ ──────────────────────────────────────────────
TOKEN = "8380708250:AAFFOiKj0ubJIiDBWtfZU4g_A8BxPgVezak"  # ← ТВОЙ ТОКЕН СЮДА
ADMIN_ID = 5454985521  # ← ТВОЙ TELEGRAM ID !!!!!!

BET_OPTIONS = [10, 50, 100, 250, 500, 1000]
START_BALANCE = 10000
DAILY_FREESPINS = 5
DB_PATH = "casino_realistic_2026.db"

# Реалистичные выплаты — RTP ~93–95%, как в нормальных онлайн-слотах
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

# ────────────────────────────────────────────── БАЗА ДАННЫХ ──────────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT ?,
                last_daily TEXT,
                banned INTEGER DEFAULT 0,
                spins INTEGER DEFAULT 0,
                bonus_spins_remaining INTEGER DEFAULT 0,
                last_bet INTEGER DEFAULT 100
            )
        """, (START_BALANCE,))
        await db.commit()

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

# ────────────────────────────────────────────── ПОМОЩНИКИ ──────────────────────────────────────────────
def get_payout(value: int):
    for k, v in SLOT_PAYOUTS.items():
        if (isinstance(k, range) and value in k) or k == value:
            return v
    return 0, "Неизвестно", "❓ ❓ ❓"

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
async def start(message: types.Message, command: CommandObject):
    await init_db()
    user_id = message.from_user.id
    balance, _, banned, _, bonus_remaining, last_bet = await get_user(user_id)
    if banned:
        await message.answer("Ты забанен в этом казике.")
        return

    # Рефералка (опционально)
    if command.args and command.args.isdigit():
        ref_id = int(command.args)
        if ref_id != user_id:
            await update_balance(ref_id, 300)
            try:
                await message.bot.send_message(ref_id, "+300 монет от реферала 🎉")
            except:
                pass

    text = (
        "🔥 **Элитный Казино 2026** 🔥\n"
        "Без реальных денег, чистый азарт и слив в ноль как в настоящем!\n\n"
        f"Баланс: **{balance}** монет\n"
        "Крути, покупай бонуски, лови редкие 7️⃣7️⃣7️⃣"
    )
    await message.answer(text, reply_markup=main_menu(balance, bonus_remaining, last_bet))

@dp.callback_query(lambda c: c.data == "balance")
async def cb_balance(c: CallbackQuery):
    balance, _, _, _, bonus_remaining, last_bet = await get_user(c.from_user.id)
    await c.message.edit_text(
        f"💰 Баланс: **{balance}** монет",
        reply_markup=main_menu(balance, bonus_remaining, last_bet)
    )
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
            await c.answer("Сегодня уже забирал! Завтра снова", show_alert=True)
            return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_daily = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        await db.commit()

    await c.message.edit_text(
        f"🎁 Daily бонус!\n+{DAILY_FREESPINS} бесплатных спинов на сегодня!\n"
        "Жми ниже, чтобы начать",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Бесплатные спины ×{DAILY_FREESPINS}", callback_data="freespin")],
            [InlineKeyboardButton(text="← Меню", callback_data="menu")]
        ])
    )
    await c.answer()

@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(c: CallbackQuery):
    balance, _, _, _, bonus_remaining, last_bet = await get_user(c.from_user.id)
    await c.message.edit_text("Главное меню", reply_markup=main_menu(balance, bonus_remaining, last_bet))
    await c.answer()

@dp.callback_query(lambda c: c.data == "buy_bonus")
async def buy_bonus(c: CallbackQuery):
    user_id = c.from_user.id
    balance, _, banned, _, bonus_remaining, last_bet = await get_user(user_id)
    if banned or bonus_remaining > 0:
        await c.answer("Нельзя купить бонуску сейчас", show_alert=True)
        return

    cost = last_bet * 100
    if balance < cost:
        await c.answer(f"Недостаточно! Нужно {cost} монет", show_alert=True)
        return

    await update_balance(user_id, -cost)
    spins_to_add = random.randint(7, 13)
    await update_bonus_spins(user_id, spins_to_add)

    await c.message.edit_text(
        f"💸 БОНУСКА КУПЛЕНА за {cost} монет!\n"
        f"Получаешь **{spins_to_add} FREE SPINS** 🔥\n"
        "Жми ниже, чтобы начать бонус-раунд!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"НАЧАТЬ БОНУС ({spins_to_add} спинов)", callback_data="freespin")],
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
        if bet_str == "max":
            bet = balance
        else:
            bet = int(bet_str)

        if balance < bet:
            await c.answer("Недостаточно монет!", show_alert=True)
            return

        await update_balance(user_id, -bet)
        await update_last_bet(user_id, bet)
        last_bet = bet

    await update_spins(user_id)

    dice_msg = await c.message.answer_dice(emoji="🎰")
    await asyncio.sleep(4.2)

    fresh = await dice_msg.bot.get_chat(dice_msg.chat.id).get_message(dice_msg.message_id)
    value = fresh.dice.value

    mult, desc, combo = get_payout(value)
    win = bet * mult
    if is_bonus_mode and win > 0:
        win = int(win * 1.4)  # небольшой буст в бонуске, но не слишком жирный

    bonus_text = ""
    if bet > 0 and not is_bonus_mode:
        if random.random() < 0.065:  # ~6.5% шанс на бонуску на обычном спине
            spins_to_add = random.randint(7, 13)
            await update_bonus_spins(user_id, spins_to_add)
            bonus_text = f"🎁 BONUS MODE! +{spins_to_add} FREE SPINS!\n"

    if win > 0:
        await update_balance(user_id, win)
        text = f"🔥 **{desc}** 🔥\n{combo}\n+{win:,} монет! x{mult}"
        emoji = "🎉💰"
    else:
        text = f"😢 {desc}\n{combo}\nПопробуй ещё!"
        emoji = "💨"

    balance, _, _, _, bonus_remaining, last_bet = await get_user(user_id)

    builder = InlineKeyboardBuilder()
    if bonus_remaining > 0:
        builder.button(text=f"Бонус спин ({bonus_remaining} осталось)", callback_data="freespin")
        status = f"\n\n**BONUS MODE**: {bonus_remaining} спинов осталось 🔥"
    else:
        builder.button(text="🔄 Ещё раз", callback_data=f"spin_{last_bet}")
        builder.button(text="Меню", callback_data="menu")
        status = ""

    await c.message.answer(
        f"{bonus_text}{emoji} **{text}**\n\nВыпало: **{value}/64**\nБаланс: **{balance:,}**{status}",
        reply_markup=builder.as_markup()
    )
    await c.answer()

@dp.callback_query(lambda c: c.data == "top")
async def cb_top(c: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username, balance FROM users "
            "WHERE banned = 0 AND balance > 0 ORDER BY balance DESC LIMIT 10"
        )
        top = await cursor.fetchall()

    text = "🏆 **Топ-10 богачей** 🏆\n\n"
    for i, (name, bal) in enumerate(top, 1):
        text += f"{i}. @{name} — {bal:,} монет\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="← Меню", callback_data="menu")
    await c.message.edit_text(text or "Пока пусто...", reply_markup=builder.as_markup())
    await c.answer()

# ────────────────────────────────────────────── АДМИНКА (базовая) ──────────────────────────────────────────────
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="Статистика", callback_data="admin_stats")
    builder.button(text="Топ игроков", callback_data="top")
    builder.adjust(2)
    await message.answer("Админ-панель", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        total_balance = (await (await db.execute("SELECT SUM(balance) FROM users")).fetchone())[0] or 0
        total_spins = (await (await db.execute("SELECT SUM(spins) FROM users")).fetchone())[0] or 0

    text = (
        f"📊 Статистика казика:\n"
        f"Пользователей: {total_users}\n"
        f"Всего монет в обороте: {total_balance:,}\n"
        f"Всего спинов: {total_spins:,}"
    )
    await c.message.edit_text(text)
    await c.answer()

# ────────────────────────────────────────────── ЗАПУСК ──────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())