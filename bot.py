import asyncio
import os
import random
import sqlite3
import logging
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from openpyxl import Workbook

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# Configure logging
logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# FSM күйі
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_file = State()
    waiting_for_confirmation = State()

TEMP_FILES = {}

def is_admin(user_id):
    return user_id in ADMIN_IDS

def init_db():
    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS participants (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      participant_id TEXT,
                      user_id INTEGER,
                      username TEXT,
                      full_name TEXT,
                      phone TEXT,
                      file_path TEXT,
                      file_type TEXT,
                      ticket_number TEXT)''')
    conn.commit()
    conn.close()

@dp.message(F.text == "/start")
async def start_registration(message: Message, state: FSMContext):
    if is_admin(message.from_user.id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Қатысушылар", callback_data="admin_list")],
            [InlineKeyboardButton(text="📤 Excel экспорт", callback_data="admin_export")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🎁 Ұтысты бастау", callback_data="admin_draw")]
        ])
        await message.answer("Админ панелі:", reply_markup=keyboard)
        return
    await message.answer("Аты-жөніңізді енгізіңіз:")
    await state.set_state(Registration.waiting_for_name)

@dp.message(Registration.waiting_for_name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("📞 Телефон нөміріңізді енгізіңіз:")
    await state.set_state(Registration.waiting_for_phone)

@dp.message(Registration.waiting_for_phone)
async def get_phone(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "").replace("-", "")
    if not re.fullmatch(r"8\d{10}", phone):
        await message.answer("📵 Телефон нөмірін 8XXXXXXXXXX форматында жазыңыз. Мысалы: 87015556677")
        return
    await state.update_data(phone=phone)
    await message.answer("🧾 Чек суретін немесе PDF файлын жіберіңіз:")
    await state.set_state(Registration.waiting_for_file)

@dp.message(Registration.waiting_for_file)
async def get_file(message: Message, state: FSMContext):
    if message.content_type == ContentType.PHOTO:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.content_type == ContentType.DOCUMENT:
        if not message.document.file_name.lower().endswith(".pdf"):
            await message.answer("❌ Қате! Тек .jpg (сурет) және .pdf файлдар ғана қабылданады.")
            return
        file_id = message.document.file_id
        file_type = "pdf"
    else:
        await message.answer("❌ Қате! Тек .jpg (сурет) және .pdf файлдар ғана қабылданады.")
        return

    TEMP_FILES[message.from_user.id] = (file_id, file_type)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Иә, дұрыс", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Қайта жіберем", callback_data="confirm_no")
        ]
    ])

    await state.set_state(Registration.waiting_for_confirmation)
    if file_type == "photo":
        await message.answer_photo(file_id, caption="📷 Бұл чек дұрыс па?", reply_markup=keyboard)
    else:
        await message.answer_document(file_id, caption="📄 Бұл чек дұрыс па?", reply_markup=keyboard)

@dp.callback_query(F.data.in_(["confirm_yes", "confirm_no"]))
async def confirm_file(callback: CallbackQuery, state: FSMContext):
    if callback.data == "confirm_no":
        await callback.message.answer("📤 Жаңа файл жіберіңіз:")
        await state.set_state(Registration.waiting_for_file)
        return

    user_id = callback.from_user.id
    data = await state.get_data()
    full_name = data['full_name']
    phone = data['phone']
    username = callback.from_user.username or "жоқ"
    ticket_number = f"ALM{random.randint(1000, 9999)}"

    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM participants")
    count = cursor.fetchone()[0]
    participant_id = f"P{count + 1:03d}"

    file_id, file_type = TEMP_FILES.get(user_id, (None, None))

    cursor.execute("""
        INSERT INTO participants (
            participant_id, user_id, username, full_name, phone, file_path, file_type, ticket_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (participant_id, user_id, username, full_name, phone, file_id, file_type, ticket_number))
    conn.commit()
    conn.close()

    await callback.message.answer(f"✅ Сіз тіркелдіңіз!\n👤 Қатысушы ID: <b>{participant_id}</b>\n🎫 Ұтыс нөміріңіз: <b>{ticket_number}</b>")
    await state.clear()

@dp.callback_query(F.data == "admin_list")
async def admin_list_callback(callback: CallbackQuery):
    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT participant_id, full_name, phone, username, ticket_number, file_path, file_type FROM participants")
    rows = cursor.fetchall()
    conn.close()

    for i, (pid, name, phone, username, ticket, file_id, file_type) in enumerate(rows, 1):
        caption = f"#{i} 👤 <b>{name}</b>\n🆔 ID: {pid}\n📞 {phone}\n🔗 @{username}\n🎫 Билет: {ticket}"
        try:
            if file_type == "photo":
                await callback.message.answer_photo(file_id, caption=caption)
            else:
                await callback.message.answer_document(file_id, caption=caption)
        except Exception:
            await callback.message.answer(caption + "\n⚠️ Файл жіберілмеді")

@dp.callback_query(F.data == "admin_export")
async def admin_export_callback(callback: CallbackQuery):
    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT participant_id, full_name, phone, username, ticket_number FROM participants")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await callback.message.answer("Экспорттайтын қатысушы жоқ.")
        return

    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Аты-жөні", "Телефон", "Username", "Билет"])
    for row in rows:
        ws.append(row)

    os.makedirs("exports", exist_ok=True)
    filepath = "exports/participants.xlsx"
    wb.save(filepath)

    await callback.message.answer_document(FSInputFile(filepath), caption="📄 Экспорт файл дайын")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM participants")
    total = cursor.fetchone()[0]
    conn.close()
    await callback.message.answer(f"📊 Барлық қатысушылар саны: <b>{total}</b>")

@dp.callback_query(F.data == "admin_draw")
async def admin_draw_callback(callback: CallbackQuery):
    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT participant_id, full_name, ticket_number, phone, username, file_path, file_type FROM participants")
    participants = cursor.fetchall()
    conn.close()

    if len(participants) < 1:
        await callback.message.answer("Қатысушылар жеткіліксіз.")
        return

    winner = random.choice(participants)
    pid, name, ticket, phone, username, file_id, file_type = winner
    caption = f"🎉 <b>Ұтыс жеңімпазы:</b>\n\n👤 <b>{name}</b>\n🆔 ID: {pid}\n📞 {phone}\n🔗 @{username}\n🎫 Билет: {ticket}"

    if file_type == "photo":
        await callback.message.answer_photo(file_id, caption=caption)
    else:
        await callback.message.answer_document(file_id, caption=caption)

@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Қол жеткізу шектеулі.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Қатысушылар", callback_data="admin_list")],
        [InlineKeyboardButton(text="📤 Excel экспорт", callback_data="admin_export")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎁 Ұтысты бастау", callback_data="admin_draw")]
    ])
    await message.answer("Админ панелі:", reply_markup=keyboard)

@dp.message(F.text.startswith("/delete"))
async def delete_selected_participants(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Қол жеткізу шектеулі.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Қолданылуы: /delete P001 P002 ...")
        return

    ids_to_delete = parts[1:]
    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()

    deleted = []
    for pid in ids_to_delete:
        cursor.execute("SELECT file_path FROM participants WHERE participant_id = ?", (pid,))
        row = cursor.fetchone()
        if row:
            deleted.append(pid)
            cursor.execute("DELETE FROM participants WHERE participant_id = ?", (pid,))

    conn.commit()
    conn.close()

    if deleted:
        await message.answer(f"🗑 Өшірілген қатысушылар: {', '.join(deleted)}")
    else:
        await message.answer("Тиісті ID табылмады немесе қате енгізілді.")


async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)  # ✅ Қорғау
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
