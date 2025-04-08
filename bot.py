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

API_TOKEN = "7733431801:AAGU2McuBMXM1b2NI9BtGbjzgwFkEDB4Ckg"
ADMIN_IDS = [7913314152]  # Админ Telegram ID-лерін осында жазыңыз

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

# Уақытша файл сақтау
TEMP_FILES = {}

# Admin check
def is_admin(user_id):
    return user_id in ADMIN_IDS

# Database initialization
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
async def preview_file(message: Message, state: FSMContext):
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
            InlineKeyboardButton(text="✅ Дұрыс", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Қайта жіберем", callback_data="confirm_no")
        ]
    ])

    await state.set_state(Registration.waiting_for_confirmation)

    if file_type == "photo":
        await message.answer_photo(file_id, caption="🧐 Бұл чек дұрыс па?", reply_markup=keyboard)
    else:
        await message.answer_document(file_id, caption="🧐 Бұл чек дұрыс па?", reply_markup=keyboard)

@dp.callback_query(F.data.in_(["confirm_yes", "confirm_no"]))
async def handle_confirmation(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if callback.data == "confirm_no":
        await state.set_state(Registration.waiting_for_file)
        await callback.message.answer("📤 Жаңа чек файлын жібере аласыз.")
        return

    # ✅ Дұрыс деп таңдаған болса:
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

    safe_name = full_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    os.makedirs("files", exist_ok=True)

    file_id, file_type = TEMP_FILES.get(user_id, (None, None))
    if not file_id:
        await callback.message.answer("Файл табылмады. Қайта жіберіп көріңіз.")
        await state.set_state(Registration.waiting_for_file)
        return

    ext = ".jpg" if file_type == "photo" else ".pdf"
    file_name = f"files/{participant_id}_{safe_name}{ext}"

    file = await bot.get_file(file_id)
    downloaded = await bot.download_file(file.file_path)

    with open(file_name, "wb") as f:
        f.write(downloaded.read())

    cursor.execute("""
        INSERT INTO participants (
            participant_id, user_id, username, full_name, phone, file_path, file_type, ticket_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (participant_id, user_id, username, full_name, phone, file_name, file_type, ticket_number))
    conn.commit()
    conn.close()

    await callback.message.answer(f"✅ Сіз тіркелдіңіз!\n👤 Қатысушы ID: <b>{participant_id}</b>\n🎫 Ұтыс нөміріңіз: <b>{ticket_number}</b>")
    await state.clear()
    TEMP_FILES.pop(user_id, None)

# Қалған командалар (list, export, edit) бұрынғыдай жұмыс істейді...
# (қаласаңыз, оларды да жаңартып толық көшіріп бере аламын)

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
