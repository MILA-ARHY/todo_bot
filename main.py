import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

# ТОКЕН БОТА (вставь свой!)
BOT_TOKEN = "8385469517:AAEbTF26qAmGYGBvxZ2cerqsKv1ku4u0fkQ"

# 🔥 РАБОЧИЙ АДРЕС (проверен сегодня)
API_BASE_URL = "https://tg-api.host"

session = AiohttpSession(api=TelegramAPIServer.from_base(API_BASE_URL))
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# Клавиатура
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="📋 Список задач")],
        [KeyboardButton(text="❌ Удалить задачу")]
    ],
    resize_keyboard=True
)

tasks = {}

@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    tasks[user_id] = []
    await message.answer(
        "👋 Привет! Я твой список дел.\n\n"
        "➕ Добавить задачу — введи текст\n"
        "📋 Список задач — показать все\n"
        "❌ Удалить задачу — введи номер",
        reply_markup=keyboard
    )

@dp.message(lambda msg: msg.text == "➕ Добавить задачу")
async def add_task_button(message: Message):
    await message.answer("✍️ Напиши текст задачи:")

@dp.message(lambda msg: msg.text and not msg.text.startswith('/') and msg.text not in [
    "➕ Добавить задачу", "📋 Список задач", "❌ Удалить задачу"
])
async def save_task(message: Message):
    user_id = message.from_user.id
    if user_id not in tasks:
        tasks[user_id] = []
    tasks[user_id].append(message.text)
    await message.answer(f"✅ Задача добавлена: «{message.text}»")

@dp.message(lambda msg: msg.text == "📋 Список задач")
async def list_tasks(message: Message):
    user_id = message.from_user.id
    if user_id not in tasks or not tasks[user_id]:
        await message.answer("📭 Список задач пуст.")
        return
    answer = "📌 Твои задачи:\n\n"
    for i, task in enumerate(tasks[user_id], start=1):
        answer += f"{i}. {task}\n"
    await message.answer(answer)

@dp.message(lambda msg: msg.text == "❌ Удалить задачу")
async def delete_task_button(message: Message):
    user_id = message.from_user.id
    if user_id not in tasks or not tasks[user_id]:
        await message.answer("📭 Нет задач для удаления.")
        return
    await message.answer("Введи номер задачи, которую нужно удалить:")

@dp.message(lambda msg: msg.text and msg.text.isdigit())
async def delete_task(message: Message):
    user_id = message.from_user.id
    if user_id not in tasks or not tasks[user_id]:
        await message.answer("📭 Список задач пуст.")
        return
    try:
        num = int(message.text)
        if 1 <= num <= len(tasks[user_id]):
            removed = tasks[user_id].pop(num - 1)
            await message.answer(f"🗑️ Задача «{removed}» удалена.")
        else:
            await message.answer("❌ Неверный номер.")
    except ValueError:
        pass

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())