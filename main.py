import logging, threading, time
from config import token, admins
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
       "add_channel": "Добавить еще канал➕"}

btn_admin = {'panel_administrator': 'Панель администратора 👨‍💻',
             'panel_custom': 'Панель пользователя 👨‍🦰'}


# state
class Registration(StatesGroup):
    url = State()


# keyaboard
def main_menu(user_id):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True).row(KeyboardButton(btn['buy']),
                                                             KeyboardButton(btn['registration']))
    if user_id in admins:
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
async def take_massage(message: types.Message):
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
                                   f"Приветствую {username}, что бы закрепить за вами права на канал <b>вышлите</b> его ссылку, после проверки того что вы являетесь Владельцем канала - Канал попадет на Биржу покупки.", parse_mode="HTML", reply_markup=registration_keyboard())
            await Registration.url.set()


@dp.message_handler(state=Registration)
async def get_registration_url(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    if text  == btn['end_registration']:
        data = await state.get_data()
        url = data.get("url")
        if url:
            await bot.send_message(user_id, "Ожидайте завершения проверки", reply_markup=main_menu(user_id))
        else:
            await bot.send_message(user_id, "Регистрация не завершенна, каналы не добавлены", reply_markup=main_menu(user_id))
        await state.finish()
    elif text == btn['add_channel']:
        await bot.send_message(user_id, "Вышлите ссылку на канал")
        await Registration.url.set()
    elif text == '/start':
        await state.finish()
        await start(message)
    else:
        if text[0:12] == "https://t.me/":
            pass
        else:
            await bot.send_message(user_id, "Вышлите ссылку на канал")
            await Registration.url.set()




if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
