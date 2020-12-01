import logging, threading, time, datetime
from config import token, admin
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardRemove, \
    ReplyKeyboardMarkup, KeyboardButton, \
    InlineKeyboardMarkup, InlineKeyboardButton
from python_mysql import read_db_config
from mysql.connector import MySQLConnection, Error
from aiogram.utils.exceptions import ChatNotFound
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import asyncio
from concurrent.futures import ProcessPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=token)
dp = Dispatcher(bot, storage=MemoryStorage())
btn = {'buy': "Купить💲", 'registration': "Регистрация✒", 'end_registration': "Завершить регистрацию📌",
       "add_channel": "Добавить еще канал➕", "set_channel": "Настройка каналов⚙"}

btn_admin = {'panel_administrator': 'Панель администратора 👨‍💻',
             'panel_custom': 'Панель пользователя 👨‍🦰'}


# state
class Registration(StatesGroup):
    url = State()


# keyaboard
def main_menu(user_id):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True).row(KeyboardButton(btn['buy']),
                                                             KeyboardButton(btn['registration']))
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("SELECT DISTINCT user_id FROM channel")
    all_user_id = c.fetchall()
    conn.commit()
    c.close()
    all_user_id = [int(i[0]) for i in all_user_id]
    if int(user_id) in all_user_id:
        keyboard.row(KeyboardButton(btn['set_channel']))
    if user_id == admin:
        keyboard.row(KeyboardButton(btn_admin['panel_administrator']))
    return keyboard


def registration_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).row(KeyboardButton(btn['end_registration']),
                                                         KeyboardButton(btn['add_channel']))


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    user_id = message.from_user.id
    c.execute("select * from users where user_id = %s", (user_id,))
    repeat = c.fetchall()
    if not repeat:
        try:
            c.execute("insert into users (user_id) values (%s)", (user_id,))
        except Exception as error:
            print("Error:", error)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    if int(possibility) == 0:
        await bot.send_message(message.from_user.id,
                               "После регистрации ваши каналы попадут на биржу продажи рекламы",
                               reply_markup=main_menu(user_id), parse_mode="HTML")
    conn.commit()
    c.close()


@dp.message_handler(
    lambda message: message.text in list(btn.values()) and message.from_user.id == message.chat.id)
async def take_massage(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    conn.commit()
    c.close()
    if int(possibility) == 0:
        username = f"@{message.from_user.username}"
        if message.text == btn['registration']:
            await bot.send_message(user_id,
                                   f"Приветствую {username}, что бы закрепить за вами права на канал <b>вышлите</b> его ссылку, после проверки того что вы являетесь Владельцем канала - Канал попадет на Биржу покупки.",
                                   parse_mode="HTML", reply_markup=registration_keyboard())
            await Registration.url.set()
        elif message.text == btn['add_channel']:
            await bot.send_message(user_id, "Вышлите ссылку на канал")
            await Registration.url.set()
        if message.text == btn['end_registration']:
            data = await state.get_data()
            url = data.get("url")
            if url:
                await bot.send_message(user_id, "Ожидайте завершения проверки", reply_markup=main_menu(user_id))
            else:
                await bot.send_message(user_id, "Регистрация не завершенна, каналы не добавлены",
                                       reply_markup=main_menu(user_id))
            await state.finish()



@dp.callback_query_handler(state="*")
async def process_callback_messages(callback_query: types.CallbackQuery, state: FSMContext):
    '''Обработка callback запросов'''
    user_id = callback_query.from_user.id
    query_id = callback_query.id
    # CONNECT TO DATABASE
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    try:
        message_id = callback_query.message.message_id
    except:
        message_id = callback_query.inline_message_id
    query_data = callback_query.data
    print(f'CallbackQuery: {user_id} -> {query_data}')
    start_data = query_data.split('_')[0]
    try:
        one_param = query_data.split('_')[1]
    except:
        one_param = None
    try:
        two_param = query_data.split('_')[2]
    except:
        two_param = None
    if start_data == "confirm":
        if one_param == "pool":
            if user_id == admin:
                c.execute("SELECT * FROM pool WHERE id = (%s)", (int(two_param),))
                pool_data = c.fetchone()
                c.execute("SELECT DISTINCT url FROM channel")
                all_url = c.fetchall()
                all_url = [i[0] for i in all_url]
                if pool_data[1] not in all_url:
                    c.execute("INSERT INTO channel (url, user_id) VALUES (%s, %s)", (pool_data[1], pool_data[2]))
                c.execute("DELETE FROM pool WHERE id = (%s)", (int(two_param),))
                try:
                    await bot.edit_message_text(
                        f"@{(await bot.get_chat(int(pool_data[2]))).username}\n{pool_data[1]}\nПодтверждено✅", user_id,
                        message_id)
                except:
                    await bot.delete_message(user_id, message_id)
                await bot.send_message(int(pool_data[2]), f"Канал {pool_data[1]} успешно подтвержден✅")
    elif start_data == "unconfirm":
        if one_param == "pool":
            if user_id == admin:
                c.execute("SELECT * FROM pool WHERE id = (%s)", (int(two_param),))
                pool_data = c.fetchone()
                c.execute("DELETE FROM pool WHERE id = (%s)", (int(two_param), ))
                try:
                    await bot.edit_message_text(
                        #f"@{(await bot.get_chat(int(pool_data[2]))).username}\n{pool_data[1]}\Отклонено❌", user_id,
                        #message_id)
                        f"@{(await bot.get_chat(int(pool_data[2]))).username}\nОтклонено❌", user_id,
                        message_id)
                except:
                    await bot.delete_message(user_id, message_id)
                await bot.send_message(int(pool_data[2]), f"Канал {pool_data[1]} не подтвержден❌")
    await bot.answer_callback_query(query_id)
    conn.commit()
    c.close()


@dp.message_handler(state=Registration)
async def get_registration_url(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    if text == btn['end_registration']:
        data = await state.get_data()
        url = data.get("url")
        if url:
            await bot.send_message(user_id, "Ожидайте завершения проверки", reply_markup=main_menu(user_id))
        else:
            await bot.send_message(user_id, "Регистрация не завершенна, каналы не добавлены",
                                   reply_markup=main_menu(user_id))
        await state.finish()
    elif text == btn['add_channel']:
        await bot.send_message(user_id, "Вышлите ссылку на канал")
        await Registration.url.set()
    elif text == '/start':
        await state.finish()
        await start(message)
    else:
        if text[0:13] == "https://t.me/":
            dbconfig = read_db_config()
            conn = MySQLConnection(**dbconfig)
            c = conn.cursor(buffered=True)
            c.execute("SELECT DISTINCT url FROM channel")
            all_url = c.fetchall()
            all_url = [i[0] for i in all_url]
            if text in all_url:
                await bot.send_message(user_id, "Такой канал уже есть на бирже. Вышлите новою ссылку на канал")
                await Registration.url.set()
            else:
                id = int(datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
                c.execute("INSERT INTO pool (id, url, user_id) VALUES (%s, %s, %s)",
                          (id, text, user_id))
                username = f"@{message.from_user.username}"
                keyboard = InlineKeyboardMarkup().row(
                    InlineKeyboardButton("Подтвердить✅", callback_data=f"confirm_pool_{str(id)}"),
                    InlineKeyboardButton("Отклонить❌", callback_data=f"unconfirm_pool_{str(id)}"))
                await state.update_data(url=text)
                await bot.send_message(admin, f"{username}\n{text}", reply_markup=keyboard)
                await bot.send_message(user_id, "Канал добавлен, ожидайте подтверждения")
            conn.commit()
            c.close()
        else:
            await bot.send_message(user_id, "Вышлите ссылку на канал")
            await Registration.url.set()


if __name__ == '__main__':
    executor.start_polling(dp)
