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

API_TOKEN = "8096936066:AAFkTLz-jYh6RJtg47L2Dwqcm0v75P9mmgI"
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

# Уақытша файл (немесе file_id) сақтау
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
    # 8XXXXXXXXXX форматында тексеру
    if not re.fullmatch(r"8\d{10}", phone):
        await message.answer("📵 Телефон нөмірін 8XXXXXXXXXX форматында жазыңыз. Мысалы: 87015556677")
        return
    await state.update_data(phone=phone)
    await message.answer("🧾 Чек суретін немесе PDF файлын жіберіңіз:")
    await state.set_state(Registration.waiting_for_file)

@dp.message(Registration.waiting_for_file)
async def preview_file(message: Message, state: FSMContext):
    # Файлды тексереміз: тек PHOTO немесе DOCUMENT (.pdf) қабылданады
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

    # Егер "Дұрыс" таңдаған болса:
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

    # Атын қауіпсіз ету (бос орындар мен арнайы символдар ауыстырылды)
    safe_name = full_name.replace(" ", "_").replace("/", "_").replace("\\", "_")

    file_id, file_type = TEMP_FILES.get(user_id, (None, None))
    if not file_id:
        await callback.message.answer("Файл табылмады. Қайта жіберіп көріңіз.")
        await state.set_state(Registration.waiting_for_file)
        return

    # Файлды локалға жүктемей-ақ, file_id-ні базаға сақтаймыз
    cursor.execute("""
        INSERT INTO participants (
            participant_id, user_id, username, full_name, phone, file_path, file_type, ticket_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (participant_id, user_id, username, full_name, phone, file_id, file_type, ticket_number))
    conn.commit()
    conn.close()

    await callback.message.answer(f"✅ Сіз тіркелдіңіз!\n👤 Қатысушы ID: <b>{participant_id}</b>\n🎫 Ұтыс нөміріңіз: <b>{ticket_number}</b>")
    await state.clear()
    TEMP_FILES.pop(user_id, None)

@dp.message(F.text == "/list")
async def list_participants(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Қол жеткізу шектеулі.")
        return

    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT participant_id, full_name, phone, username, ticket_number, file_path, file_type FROM participants")
    participants = cursor.fetchall()
    conn.close()

    if not participants:
        await message.answer("Қатысушылар табылмады.")
        return

    for i, (pid, name, phone, username, ticket, file_id, file_type) in enumerate(participants, start=1):
        caption = (f"#{i} 👤 <b>{name}</b>\n🆔 ID: <b>{pid}</b>\n📞 {phone}\n🔗 @{username}\n🎫 Ұтыс нөмірі: <b>{ticket}</b>")
        try:
            if file_type == "photo":
                await message.answer_photo(file_id, caption=caption)
            else:
                await message.answer_document(file_id, caption=caption)
        except Exception as e:
            await message.answer(f"{i}. ⚠️ Файл жіберілмеді немесе жүктеу қатесі: {e}")

@dp.message(F.text == "/export")
async def export_to_excel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Бұл команда тек админге арналған.")
        return

    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()
    cursor.execute("SELECT participant_id, full_name, phone, username, ticket_number FROM participants")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("Экспорттайтын қатысушылар жоқ.")
        return

    wb = Workbook()
    ws = wb.active
    ws.append(["Қатысушы ID", "Аты-жөні", "Телефон", "Username", "Ұтыс нөмірі"])
    for row in rows:
        ws.append(row)

    os.makedirs("exports", exist_ok=True)
    filepath = "exports/participants.xlsx"
    wb.save(filepath)

    await message.answer_document(FSInputFile(filepath), caption="📄 Қатысушылар тізімі Excel форматында")

@dp.message(F.text.startswith("/edit"))
async def edit_participant(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Бұл команда тек админге арналған.")
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Қолданылуы:\n– Жаңарту: /edit <participant_id> <field> <new_value>\n– Өшіру: /edit <participant_id> delete")
        return

    pid = parts[1]
    action = parts[2]

    conn = sqlite3.connect("raffle.db")
    cursor = conn.cursor()

    if action == "delete":
        cursor.execute("SELECT file_path FROM participants WHERE participant_id = ?", (pid,))
        row = cursor.fetchone()
        # Егер сіз файлды жойғыңыз келсе, бірақ біз file_id сақтаймыз,
        # онда біз Telegram-нан қайта алуымыз керек. Бірақ әдетте file_id-де өшіру қажет емес.
        # Біз тек дерекқор жазбасын өшіреміз:
        cursor.execute("DELETE FROM participants WHERE participant_id = ?", (pid,))
        conn.commit()
        conn.close()
        await message.answer(f"🗑 Қатысушы ID {pid} деректері өшірілді.")
        return

    if len(parts) < 4:
        await message.answer("Жаңарту үшін жаңа мән көрсетіңіз: /edit <participant_id> <field> <new_value>")
        return

    field = action
    new_value = parts[3]
    allowed_fields = ["full_name", "phone", "username"]

    if field not in allowed_fields:
        await message.answer(f"Тек осы өрістерді өзгертуге болады: {', '.join(allowed_fields)}")
        return

    cursor.execute(f"UPDATE participants SET {field} = ? WHERE participant_id = ?", (new_value, pid))
    conn.commit()
    conn.close()

    await message.answer(f"✅ Қатысушы ID {pid} – {field} жаңартылды.")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())