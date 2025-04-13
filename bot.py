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

@dp.callback_query(F.data == "admin_list")
async def admin_list_callback(callback: CallbackQuery):
    message = callback.message
    await list_participants(message)

@dp.callback_query(F.data == "admin_export")
async def admin_export_callback(callback: CallbackQuery):
    message = callback.message
    await export_to_excel(message)

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
    cursor.execute("SELECT participant_id, full_name, ticket_number FROM participants")
    participants = cursor.fetchall()
    conn.close()

    if len(participants) < 1:
        await callback.message.answer("Қатысушылар жеткіліксіз.")
        return

    winner = random.choice(participants)
    pid, name, ticket = winner
    text = f"🎉 <b>Ұтыс жеңімпазы:</b>\n\n👤 <b>{name}</b>\n🆔 ID: {pid}\n🎫 Билет: {ticket}"
    await callback.message.answer(text)

# ... қалған код (registration, get_file, preview_file, т.б.) бұрынғыдай жалғасады ...

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
