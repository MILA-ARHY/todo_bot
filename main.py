import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    BufferedInputFile



logging.basicConfig(level=logging.INFO)


# --- БАЗА ДАННЫХ ---
class Database:
    def __init__(self, db_file="tasks.db"):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                done BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_id INTEGER,
                task_text TEXT,
                remind_time TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (task_id) REFERENCES tasks (id)
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")

    def add_user(self, user_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

    def add_task(self, user_id, text):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO tasks (user_id, text) VALUES (?, ?)', (user_id, text))
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def get_tasks(self, user_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT id, text, done, created_at FROM tasks WHERE user_id = ? ORDER BY created_at', (user_id,))
        tasks = cursor.fetchall()
        conn.close()
        return tasks

    def update_task(self, task_id, new_text):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET text = ? WHERE id = ?', (new_text, task_id))
        conn.commit()
        conn.close()

    def delete_task(self, task_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

    def mark_task_done(self, task_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

    def add_reminder(self, user_id, task_id, task_text, remind_time):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO reminders (user_id, task_id, task_text, remind_time) VALUES (?, ?, ?, ?)',
                       (user_id, task_id, task_text, remind_time))
        conn.commit()
        conn.close()

    def get_active_reminders(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT id, user_id, task_text, remind_time FROM reminders WHERE is_active = 1')
        reminders = cursor.fetchall()
        conn.close()
        return reminders

    def deactivate_reminder(self, reminder_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('UPDATE reminders SET is_active = 0 WHERE id = ?', (reminder_id,))
        conn.commit()
        conn.close()


db = Database()

# --- БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="📋 Список задач")],
        [KeyboardButton(text="✏️ Редактировать задачу")],
        [KeyboardButton(text="❌ Удалить задачу")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📤 Экспорт")],
        [KeyboardButton(text="📩 Обратная связь")]
    ],
    resize_keyboard=True
)

reminder_quick_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⏰ Сегодня", callback_data="remind_today_quick")],
    [InlineKeyboardButton(text="⏰ Завтра", callback_data="remind_tomorrow_quick")],
    [InlineKeyboardButton(text="📅 Выбрать дату", callback_data="remind_choose_date_quick")],
    [InlineKeyboardButton(text="❌ Пропустить", callback_data="remind_skip")]
])

reminder_action_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Выполнено", callback_data="task_done")],
    [InlineKeyboardButton(text="🔕 Отключить", callback_data="remind_off")],
    [InlineKeyboardButton(text="⏰ Через час", callback_data="remind_in_hour")],
    [InlineKeyboardButton(text="📅 Завтра", callback_data="remind_tomorrow_again")]
])

# --- ХРАНИЛИЩА ---
user_state = {}
user_last_activity = {}
pending_task_for_reminder = {}
editing_task_id = {}


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_task_list(user_id):
    tasks = db.get_tasks(user_id)
    if not tasks:
        return "📭 Список задач пуст."
    answer = "📌 Твои задачи:\n\n"
    for i, (task_id, text, done, created_at) in enumerate(tasks, start=1):
        done_mark = "✅" if done else "⬜"
        date_str = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
        answer += f"{i}. {done_mark} {text}  (добавлена {date_str})\n"
    return answer


def parse_date(text):
    try:
        if len(text.split('.')) == 3:
            return datetime.strptime(text, "%d.%m.%Y").date()
        else:
            date_obj = datetime.strptime(text, "%d.%m").date()
            now = datetime.now()
            date_obj = date_obj.replace(year=now.year)
            if date_obj < now.date():
                date_obj = date_obj.replace(year=now.year + 1)
            return date_obj
    except ValueError:
        return None


def parse_time(text):
    try:
        clean_text = text.strip().replace('.', ':')
        if len(clean_text) != 5 or clean_text[2] != ':':
            return None
        hours, minutes = clean_text.split(':')
        if not (hours.isdigit() and minutes.isdigit()):
            return None
        return datetime.strptime(clean_text, "%H:%M").time()
    except ValueError:
        return None


# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    db.add_user(user_id)
    user_state[user_id] = None
    user_last_activity[user_id] = datetime.now()
    await message.answer(
        "👋 Привет! Я твой ассистент.\n\n"
        "➕ Добавить задачу\n"
        "📋 Список задач\n"
        "✏️ Редактировать задачу\n"
        "❌ Удалить задачу\n"
        "📊 Статистика\n"
        "📤 Экспорт\n"
        "📩 Обратная связь",
        reply_markup=main_keyboard
    )


@dp.message(lambda msg: msg.text == "➕ Добавить задачу")
async def add_task_button(message: Message):
    user_id = message.from_user.id
    user_state[user_id] = "waiting_for_task"
    user_last_activity[user_id] = datetime.now()
    await message.answer("✍️ Напиши текст задачи:")


@dp.message(lambda msg: msg.text == "📋 Список задач")
async def list_tasks(message: Message):
    user_id = message.from_user.id
    user_last_activity[user_id] = datetime.now()
    await message.answer(get_task_list(user_id))


@dp.message(lambda msg: msg.text == "✏️ Редактировать задачу")
async def edit_task_button(message: Message):
    user_id = message.from_user.id
    user_last_activity[user_id] = datetime.now()
    tasks = db.get_tasks(user_id)
    if not tasks:
        await message.answer("📭 Нет задач для редактирования.")
        return
    user_state[user_id] = "waiting_for_edit"
    await message.answer("Введи номер задачи для редактирования:")


@dp.message(lambda msg: msg.text == "❌ Удалить задачу")
async def delete_task_button(message: Message):
    user_id = message.from_user.id
    user_last_activity[user_id] = datetime.now()
    tasks = db.get_tasks(user_id)
    if not tasks:
        await message.answer("📭 Нет задач для удаления.")
        return
    user_state[user_id] = "waiting_for_delete"
    await message.answer("Введи номер задачи для удаления:")


@dp.message(lambda msg: msg.text == "📊 Статистика")
async def stats_button(message: Message):
    user_id = message.from_user.id
    user_last_activity[user_id] = datetime.now()
    tasks = db.get_tasks(user_id)
    if not tasks:
        await message.answer("📭 Нет задач для статистики.")
        return
    total = len(tasks)
    done = sum(1 for t in tasks if t[2])
    pending = total - done
    completion_rate = (done / total * 100) if total > 0 else 0
    stats = (
        f"📊 Статистика задач:\n\n"
        f"📌 Всего: {total}\n"
        f"✅ Выполнено: {done}\n"
        f"⬜ Осталось: {pending}\n"
        f"📈 Прогресс: {completion_rate:.1f}%\n"
    )
    await message.answer(stats)


@dp.message(lambda msg: msg.text == "📤 Экспорт")
async def export_button(message: Message):
    user_id = message.from_user.id
    user_last_activity[user_id] = datetime.now()
    tasks = db.get_tasks(user_id)
    if not tasks:
        await message.answer("📭 Нет задач для экспорта.")
        return
    export_text = "📋 Экспорт задач:\n\n"
    done_tasks = []
    pending_tasks = []
    for task_id, text, done, created_at in tasks:
        date_str = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
        task_data = {"text": text, "date": date_str}
        if done:
            done_tasks.append(task_data)
        else:
            pending_tasks.append(task_data)
    if done_tasks:
        export_text += "✅ Выполненные:\n"
        for task in done_tasks:
            export_text += f"  • {task['text']} ({task['date']})\n"
    if pending_tasks:
        export_text += "\n⬜ Активные:\n"
        for task in pending_tasks:
            export_text += f"  • {task['text']} ({task['date']})\n"
    await message.answer_document(
        document=BufferedInputFile(
            export_text.encode('utf-8'),
            filename=f"tasks_{datetime.now().strftime('%Y%m%d')}.txt"
        )
    )


@dp.message(lambda msg: msg.text == "📩 Обратная связь")
async def feedback_button(message: Message):
    user_id = message.from_user.id
    user_state[user_id] = "waiting_for_feedback"
    await message.answer("✍️ Напиши свой отзыв, предложение или вопрос.")


# --- ОБРАБОТКА INLINE-КНОПОК ---
@dp.callback_query(lambda c: c.data.startswith("remind_") or c.data == "remind_skip")
async def handle_quick_reminder(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data
    now = datetime.now()

    if action == "remind_skip":
        await callback.message.edit_text("✅ Задача добавлена без напоминания.")
        await callback.answer()
        return

    if action == "remind_today_quick":
        date_str = now.strftime("%Y-%m-%d")
        user_state[user_id] = f"waiting_for_reminder_time|{date_str}"
        await callback.message.edit_text("⏰ Введи **время** (ЧЧ:ММ или ЧЧ.ММ):")
        await callback.answer()
        return

    if action == "remind_tomorrow_quick":
        tomorrow = now + timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")
        user_state[user_id] = f"waiting_for_reminder_time|{date_str}"
        await callback.message.edit_text(f"⏰ Напомню **завтра ({tomorrow.strftime('%d.%m.%Y')})**. Введи **время**:")
        await callback.answer()
        return

    if action == "remind_choose_date_quick":
        user_state[user_id] = "waiting_for_reminder_date"
        await callback.message.edit_text("📅 Введи **дату** в формате ДД.ММ (например, 09.08):")
        await callback.answer()
        return


@dp.callback_query(lambda c: c.data.startswith("remind_") and not c.data.endswith("_quick") and c.data != "remind_skip")
async def handle_reminder_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data
    now = datetime.now()

    if action == "remind_today":
        date_str = now.strftime("%Y-%m-%d")
        user_state[user_id] = f"waiting_for_reminder_time|{date_str}"
        await callback.message.edit_text("⏰ Введи **время** (ЧЧ:ММ или ЧЧ.ММ):")
        await callback.answer()

    elif action == "remind_tomorrow" or action == "remind_tomorrow_again":
        tomorrow = now + timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")
        user_state[user_id] = f"waiting_for_reminder_time|{date_str}"
        await callback.message.edit_text(f"⏰ Напомню **завтра ({tomorrow.strftime('%d.%m.%Y')})**. Введи **время**:")
        await callback.answer()

    elif action == "remind_choose_date":
        user_state[user_id] = "waiting_for_reminder_date"
        await callback.message.edit_text("📅 Введи **дату** в формате ДД.ММ (например, 09.08):")
        await callback.answer()

    elif action == "remind_off":
        reminders = db.get_active_reminders()
        for r_id, u_id, _, _ in reminders:
            if u_id == user_id:
                db.deactivate_reminder(r_id)
        await callback.message.edit_text("🔕 Напоминания отключены.")
        await callback.answer()

    elif action == "remind_in_hour":
        hour_later = now + timedelta(hours=1)
        reminders = db.get_active_reminders()
        user_reminders = [r for r in reminders if r[1] == user_id]
        if user_reminders:
            reminder_id = user_reminders[-1][0]
            conn = sqlite3.connect(db.db_file)
            cursor = conn.cursor()
            cursor.execute('UPDATE reminders SET remind_time = ? WHERE id = ?',
                           (hour_later.strftime("%Y-%m-%d %H:%M:%S"), reminder_id))
            conn.commit()
            conn.close()
            await callback.message.edit_text(f"⏰ Напомню через час — в **{hour_later.strftime('%H:%M')}**")
        else:
            await callback.message.edit_text("❌ Нет активных напоминаний.")
        await callback.answer()


@dp.callback_query(lambda c: c.data == "task_done")
async def handle_task_done(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tasks = db.get_tasks(user_id)
    if tasks:
        for task in reversed(tasks):
            if not task[2]:
                db.mark_task_done(task[0])
                await callback.message.edit_text(f"✅ Задача «{task[1]}» отмечена как выполненная!")
                break
        else:
            await callback.message.edit_text("✅ Все задачи уже выполнены!")
    else:
        await callback.message.edit_text("❌ Нет задач для отметки.")
    await callback.answer()


# --- УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ТЕКСТА ---
@dp.message(lambda msg: msg.text and not msg.text.startswith('/') and msg.text not in [
    "➕ Добавить задачу", "📋 Список задач", "✏️ Редактировать задачу",
    "❌ Удалить задачу", "📊 Статистика", "📤 Экспорт", "📩 Обратная связь"
])
async def handle_text(message: Message):
    user_id = message.from_user.id
    text = message.text
    user_last_activity[user_id] = datetime.now()

    if user_state.get(user_id) == "waiting_for_task":
        db.add_user(user_id)
        task_id = db.add_task(user_id, text)
        user_state[user_id] = None
        pending_task_for_reminder[user_id] = {"task_id": task_id, "text": text}
        await message.answer(
            f"✅ Задача добавлена: «{text}»\n\nХочешь установить напоминание?",
            reply_markup=reminder_quick_keyboard
        )

    elif user_state.get(user_id) == "waiting_for_edit":
        tasks = db.get_tasks(user_id)
        try:
            num = int(text)
            if 1 <= num <= len(tasks):
                task_id = tasks[num - 1][0]
                editing_task_id[user_id] = task_id
                user_state[user_id] = "waiting_for_edit_text"
                await message.answer(f"✏️ Введи новый текст для задачи #{num}:")
            else:
                await message.answer("❌ Неверный номер.")
                user_state[user_id] = None
        except ValueError:
            await message.answer("❌ Введи число.")
            user_state[user_id] = None

    elif user_state.get(user_id) == "waiting_for_edit_text":
        if user_id in editing_task_id:
            task_id = editing_task_id[user_id]
            db.update_task(task_id, text)
            del editing_task_id[user_id]
            user_state[user_id] = None
            await message.answer(f"✅ Задача обновлена: «{text}»")

    elif user_state.get(user_id) == "waiting_for_delete":
        tasks = db.get_tasks(user_id)
        if not tasks:
            await message.answer("📭 Нет задач.")
            user_state[user_id] = None
            return
        try:
            num = int(text)
            if 1 <= num <= len(tasks):
                task_id = tasks[num - 1][0]
                task_text = tasks[num - 1][1]
                db.delete_task(task_id)
                user_state[user_id] = None
                await message.answer(f"🗑️ Задача «{task_text}» удалена.")
            else:
                await message.answer("❌ Неверный номер.")
        except ValueError:
            await message.answer("❌ Введи число.")
        user_state[user_id] = None

    elif user_state.get(user_id) == "waiting_for_feedback":
        user_state[user_id] = None
        YOUR_TELEGRAM_ID = 1077780527
        try:
            await bot.send_message(YOUR_TELEGRAM_ID, f"📩 Новое сообщение от пользователя {user_id}:\n\n{text}")
            await message.answer("✅ Спасибо! Твоё сообщение отправлено разработчику.")
        except Exception:
            await message.answer("❌ Произошла ошибка при отправке. Попробуй позже.")

    elif user_state.get(user_id) == "waiting_for_reminder_date":
        parsed_date = parse_date(text)
        if parsed_date:
            user_state[user_id] = f"waiting_for_reminder_time|{parsed_date.strftime('%Y-%m-%d')}"
            await message.answer(
                f"📅 Отлично, дата **{parsed_date.strftime('%d.%m.%Y')}**. Теперь введи **время** (ЧЧ:ММ):")
        else:
            await message.answer("❌ Неверный формат. Введи дату как ДД.ММ (например, 09.08)")

    elif user_state.get(user_id) and user_state[user_id].startswith("waiting_for_reminder_time|"):
        reminder_time = parse_time(text)
        if reminder_time:
            date_str = user_state[user_id].split("|")[1]
            reminder_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            reminder_datetime = datetime.combine(reminder_date, reminder_time)
            if reminder_datetime < datetime.now():
                reminder_datetime = reminder_datetime + timedelta(days=1)

            if user_id in pending_task_for_reminder:
                task_info = pending_task_for_reminder[user_id]
                task_id = task_info["task_id"]
                task_text = task_info["text"]
                del pending_task_for_reminder[user_id]
            else:
                tasks = db.get_tasks(user_id)
                if tasks:
                    task_id = tasks[-1][0]
                    task_text = tasks[-1][1]
                else:
                    task_text = "задача"
                    task_id = None

            db.add_reminder(user_id, task_id, task_text, reminder_datetime.strftime("%Y-%m-%d %H:%M:%S"))
            user_state[user_id] = None
            await message.answer(
                f"✅ Напомню о задаче «{task_text}» **{reminder_datetime.strftime('%d.%m.%Y в %H:%M')}**")
        else:
            await message.answer("❌ Неверный формат времени. Введи как ЧЧ:ММ (например, 18:30)")

    else:
        await message.answer("❓ Неизвестная команда. Используй кнопки меню.")


# --- ФОНОВЫЕ ЗАДАЧИ ---
async def check_reminders():
    while True:
        now = datetime.now()
        reminders = db.get_active_reminders()
        for reminder_id, user_id, task_text, remind_time in reminders:
            remind_datetime = datetime.strptime(remind_time, "%Y-%m-%d %H:%M:%S")
            if remind_datetime <= now:
                try:
                    await bot.send_message(
                        user_id,
                        f"🔔 НАПОМИНАНИЕ!\nВы просили напомнить: «{task_text}»\n\n"
                        f"📋 Ваш список дел:\n{get_task_list(user_id)}",
                        reply_markup=reminder_action_keyboard
                    )
                except Exception:
                    pass
                db.deactivate_reminder(reminder_id)
        await asyncio.sleep(60)


async def check_inactivity():
    while True:
        now = datetime.now()
        for user_id, last_time in list(user_last_activity.items()):
            if now - last_time > timedelta(hours=1):
                tasks = db.get_tasks(user_id)
                if tasks:
                    pending = [t for t in tasks if not t[2]]
                    if pending:
                        try:
                            await bot.send_message(
                                user_id,
                                f"👋 Вы давно не заходили!\n\n📋 Ваш список дел:\n{get_task_list(user_id)}"
                            )
                        except Exception:
                            pass
                user_last_activity[user_id] = now
        await asyncio.sleep(60)


# --- ЗАПУСК ---
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
