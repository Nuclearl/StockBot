import logging, threading, time, datetime, re, requests, json
from config import token, admin, YANDEX_TOKEN, yandex_number
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
import parse_telemetr
from concurrent.futures import ProcessPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=token)
dp = Dispatcher(bot, storage=MemoryStorage())
btn = {'buy': "Купить💲", 'registration': "Регистрация✒", 'end_registration': "Завершить регистрацию📌",
       "add_channel": "Добавить еще канал➕", "set_channel": "Настройка каналов⚙", "coverage": "Охват", "price": "Цена",
       "time": "Время", "end_set_channel": "Завершить редактирование📌", "morning": "Утро", "day": "День",
       "evening": "Вечер", "night": "Ночь", "dagger": "❌", "tick": "✅", "search_channel": "Найти каналы🔍",
       "end_shopping": "Завершить покупку📌", "any": "Любое", "end_connection": "Завершить разговор"
       }

btn_admin = {"panel_administrator": 'Панель администратора 👨‍💻',
             "panel_custom": 'Панель пользователя 👨‍🦰', "list_of_registered": "Список зарегистрированных📄",
             "post_payment": "Выставить оплату⚖", "statistics": 'Статистика📊'}

back_btn = '⬅️Назад'
main_back_btn = 'Вернуться в основное меню'
mail_but = "Рассылка"
backMail_but = 'Назад ◀️'
preMail_but = 'Предпросмотр 👁'
startMail_but = 'Старт 🏁'
textMail_but = 'Текст 📝'
butMail_but = 'Ссылка-кнопка ⏺'
photoMail_but = 'Фото 📸'


# state
class Registration(StatesGroup):
    url = State()


class SetChannel(StatesGroup):
    url = State()
    choice = State()
    coverage = State()
    price = State()
    time1 = State()
    time2 = State()


class Shopping(StatesGroup):
    choice = State()
    time = State()
    parameters = State()
    number = State()


class PostPayment(StatesGroup):
    data = State()


class Connection(StatesGroup):
    msg = State()


class MailingStates(StatesGroup):
    admin_mailing = State()


class ProcessTextMailing(StatesGroup):
    text = State()


class ProcessEditTextBut(StatesGroup):
    text = State()


class ProcessEditUrlBut(StatesGroup):
    text = State()


class WaitPhoto(StatesGroup):
    text = State()


class CheckerState(StatesGroup):
    check = State()


# оплата


async def unloading_goods(user_id):
    text = ""
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute(
        f"UPDATE users SET  possibility = 0 WHERE user_id = (%s)",
        (user_id,))
    await bot.send_message(user_id, "Доступ к боту восстановлен")
    c.close()
    conn.commit()
    conn.close()
    return text


async def yandex_dep():
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    records = 10
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    sess = requests.Session()
    sess.headers = {'Content-type': 'application/x-www-form-urlencoded'}
    sess.headers['Authorization'] = 'Bearer ' + YANDEX_TOKEN
    settings_h = {'records': records}
    history = sess.post('https://money.yandex.ru/api/operation-history', data=settings_h)
    hist = json.loads(history.text)
    for rec in range(records):
        try:
            id = hist['operations'][rec]['operation_id']
            history = sess.post('https://money.yandex.ru/api/operation-details', data={'operation_id': id})
            hist = json.loads(history.text)
            status = hist['status']
            date = hist['datetime']
            amount = hist['amount']
            tip = hist['direction']
            try:
                old_comment = hist['message']
            except KeyError:
                old_comment = ''
            if status == 'success' and tip == 'in':
                try:
                    comment = ''
                    try:
                        int(old_comment)
                        comment = old_comment
                        comment = int(comment)
                    except:
                        old_comment = str(old_comment)
                        for i in range(len(old_comment)):
                            comment = str(comment)
                            try:
                                int(old_comment[i])
                                comment += str(old_comment[i])
                            except:
                                pass
                            print("comment ", comment)
                    result = c.execute(
                        f"SELECT * FROM payments WHERE id = {id}").fetchone()  # достаем данные из таблицы
                    if result is None:
                        print("11321")
                        # добавляем платеж в БД
                        c.execute(
                            """INSERT INTO payments (id, sum, comment, type, date, number, PS) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (id, amount, comment, 'IN', date, '-', 'yandex'))
                        conn.commit()
                        try:
                            # отправляем юзеру уведомление с тем, что платеж получен
                            user_id = int(comment)
                            await bot.send_message(user_id, f"Платеж на сумму {amount} успешно получен")
                            get_paid_request_id(amount, user_id)
                        except Exception as e:
                            search_paid_request(amount, 'yandex')
                    conn.commit()
                except Exception as e:
                    print("Error6532 ", e)
            history = sess.post('https://money.yandex.ru/api/operation-history', data=settings_h)
            hist = json.loads(history.text)
        except Exception as e:
            print('error ', e)
    c.close()
    conn.commit()
    conn.close()


async def get_paid_request_id(sum_paid, user_id):
    request = None
    try:
        dbconfig = read_db_config()
        conn_new = MySQLConnection(**dbconfig)
        c_new = conn_new.cursor()
        sql = "SELECT * FROM requests WHERE id_user=%s"
        results = c_new.execute(sql, [user_id]).fetchall()
        for line in results:
            id_request = line[0]
            req_sum = int(float(line[1]))
            status = line[4]
            ps = line[5]
            if status == 'processing':
                if req_sum <= sum_paid:
                    request = id_request
                    sql_update_query = """Update requests set status = %s where id = %s"""
                    data = ("accept", id_request)
                    c_new.execute(sql_update_query, data)
                    try:
                        unloading_goods(user_id)
                    except Exception as e:
                        print("Error uploading12 ", e)
                    try:
                        await bot.send_message(admin,
                                               '💰*Пополнение счета!💰*\n\n'
                                               '*🆔:* `{0}`\n'
                                               '*💸Сумма: *`{1}`₽\n'
                                               '[Отправитель](tg://user?id={0})'.format(
                                                   str(user_id), str(sum_paid)),
                                               parse_mode='Markdown')
                    except:
                        pass
        conn_new.commit()
        c_new.close()
    except Error as error:
        print("Failed to update sqlite table", error)
    finally:
        if conn_new:
            conn_new.close()
            # print("The SQLite connection is closed")
    return request


def search_paid_request(sum_paid, type_bank):
    request = None
    sum_paid = int(float(sum_paid))
    try:
        dbconfig = read_db_config()
        conn_new = MySQLConnection(**dbconfig)
        c_new = conn_new.cursor()
        sql = "SELECT * FROM requests WHERE status=%s"
        list_sum = []
        results = c_new.execute(sql, ['processing']).fetchall()
        for line in results:
            req_sum = int(float(line[1]))
            bank = line[5]
            if req_sum <= sum_paid:
                if bank == type_bank:
                    list_sum.append(req_sum)
        if list_sum:
            sort_sum = sorted(list_sum, key=lambda x: abs(sum_paid - x))
            nearest_sum = sort_sum[0]
            index_request_search = list_sum.index(nearest_sum)
            result = results[index_request_search]
            id_request = result[0]
            request = id_request
            sql_update_query = """Update requests set status = %s where id = %s"""
            data = ("accept", id_request)
            c_new.execute(sql_update_query, data)
            conn_new.commit()
            sql = "SELECT * FROM requests WHERE id=%s"
            result = c_new.execute(sql, [f"{id_request}"]).fetchone()  # .fetchall()
            user_id = result[3]
            ps = result[5]
            try:
                unloading_goods(user_id)
            except Exception as e:
                print("Error uploading1212 ", e)
            try:
                bot.send_message(admin,
                                 '💰*Пополнение счета!💰*\n\n'
                                 '*🆔:* `{0}`\n'
                                 '*💸Сумма: *`{1}`₽\n'
                                 '[Отправитель](tg://user?id={0})'.format(
                                     str(user_id), str(sum_paid)),
                                 parse_mode='Markdown')
            except:
                pass
        c_new.close()
    except Error as error:
        print("Failed to update sqlite table12", error)
    finally:
        if conn_new:
            conn_new.close()
            # print("The SQLite connection is closed")
    return request


async def mailing(user_ids, lively, banned, deleted, chat_id, mail_text, mail_photo, mail_link, mail_link_text):
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    users_block = []
    start_mail_time = time.time()
    c.execute('''SELECT COUNT(*) FROM users''')
    allusers = int(c.fetchone()[0])
    for user_id in user_ids:
        try:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(text=mail_link_text, url=mail_link))
            if str(mail_photo) != '0':
                if str(mail_link_text) != '0':
                    await bot.send_photo(user_id, caption=mail_text, photo=mail_photo, parse_mode='HTML',
                                         reply_markup=keyboard)
                else:
                    await bot.send_photo(user_id, caption=mail_text, parse_mode='HTML', photo=mail_photo)
            else:
                if str(mail_link_text) not in '0':
                    await bot.send_message(user_id, text=mail_text, parse_mode='HTML',
                                           reply_markup=keyboard)
                else:
                    await bot.send_message(user_id, parse_mode='HTML', text=mail_text)
            lively += 1
        except Exception as e:
            if 'bot was blocked by the user' in str(e):
                users_block.append(user_id)
                banned += 1
                # database is locked
    for user_id in users_block:
        c.execute("UPDATE users SET lively = (%s) WHERE user_id = (%s)", ('block', user_id,))
    admin_text = '*Рассылка окончена! ✅\n\n' \
                 '🙂 Количество живых пользователей:* {0}\n' \
                 '*% от числа всех:* {1}%\n' \
                 '*💩 Количество заблокировавших:* {3}\n' \
                 '*🕓 Время рассылки:* {2}'.format(str(lively), str(round(lively / allusers * 100, 2)),
                                                   str(round(time.time() - start_mail_time, 2)) + ' сек', str(banned))
    await bot.send_message(chat_id, admin_text, parse_mode='Markdown', reply_markup=admin_keyboard())
    c.close()
    conn.commit()


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


def set_channel_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(btn["coverage"]), KeyboardButton(btn["price"]), KeyboardButton(btn["time"]))
    keyboard.row(KeyboardButton(btn["end_set_channel"]))
    return keyboard


def registration_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).row(KeyboardButton(btn['end_registration']),
                                                         KeyboardButton(btn['add_channel']))


def time_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(btn["morning"]), KeyboardButton(btn["day"]))
    keyboard.row(KeyboardButton(btn["evening"]), KeyboardButton(btn["night"]))
    return keyboard


def action_time_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(btn["tick"]), KeyboardButton(btn["dagger"]))
    return keyboard


def shopping_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(btn["search_channel"]), KeyboardButton(btn["end_shopping"]))
    return keyboard


def admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(btn_admin["list_of_registered"]), KeyboardButton(btn_admin["post_payment"]))
    keyboard.add(*[KeyboardButton(name) for name in [mail_but, btn_admin["statistics"]]])
    keyboard.row(btn_admin["panel_custom"])
    return keyboard


mail_menu = ReplyKeyboardMarkup(resize_keyboard=True)
mail_menu.add(*[KeyboardButton(name) for name in [textMail_but, photoMail_but]])
mail_menu.add(*[KeyboardButton(name) for name in [butMail_but, preMail_but]])
mail_menu.add(*[KeyboardButton(name) for name in [backMail_but, startMail_but]])


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


@dp.message_handler(lambda m: m.text == mail_but and m.chat.id == admin and m.from_user.id == m.chat.id)
async def cheker(message: types.Message):
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)

    async def admin_mailing(message: types.Message):
        chat_id = message.chat.id
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        msgtext = message.text
        c.execute("""select textMail,photoMail,butTextMail,butUrlMail from users where user_id = %s""" % chat_id)
        data = c.fetchone()
        textMailUser = str(data[0])
        photoMailUser = str(data[1])
        butTextMail = str(data[2])
        butUrlMail = str(data[3])
        if msgtext == mail_but:
            await bot.send_message(chat_id, '*Вы попали в меню рассылки *📢\n\n'
                                            'Для возврата нажмите *{0}*\n\n'
                                            'Для отмены какой-либо операции нажмите /start\n\n'
                                            'Используйте *{1}* для предварительного просмотра рассылки, а *{2}* для начала'
                                            ' рассылки\n\n'
                                            'Текст рассылки поддерживает разметку *HTML*, то есть:\n'
                                            '<b>*Жирный*</b>\n'
                                            '<i>_Курсив_</i>\n'
                                            '<pre>`Моноширный`</pre>\n'
                                            '<a href="ссылка-на-сайт">[Обернуть текст в ссылку](test.ru)</a>'.format(
                backMail_but, preMail_but, startMail_but
            ),
                                   parse_mode="markdown", reply_markup=mail_menu)
            await MailingStates.admin_mailing.set()

        elif msgtext == backMail_but:
            await bot.send_message(chat_id, backMail_but, reply_markup=admin_keyboard())
            # bot.clear_step_handler(message)

        elif msgtext == preMail_but:
            try:
                if butTextMail == '0' and butUrlMail == '0':
                    if photoMailUser == '0':
                        await bot.send_message(chat_id, textMailUser, parse_mode='html', reply_markup=mail_menu)
                    else:
                        await bot.send_photo(chat_id, caption=textMailUser, photo=photoMailUser, parse_mode='html',
                                             reply_markup=mail_menu)
                else:
                    keyboard = InlineKeyboardMarkup()
                    keyboard.add(InlineKeyboardButton(text=butTextMail, url=butUrlMail))
                    if photoMailUser == '0':
                        await bot.send_message(chat_id, textMailUser, parse_mode='html',
                                               reply_markup=keyboard)
                    else:
                        await bot.send_photo(chat_id, caption=textMailUser, photo=photoMailUser, parse_mode='html',
                                             reply_markup=keyboard)
            except:
                await bot.send_message(chat_id, "Упс..проверьте правильность введения данных")
            await MailingStates.admin_mailing.set()

        elif msgtext == startMail_but:
            c.execute(
                """update users set textMail = 0, photoMail = 0,butTextMail = 0,butUrlMail = 0  where user_id = %s""" % chat_id)

            user_ids = []
            c.execute("""select user_id from users""")
            user_id = c.fetchone()
            while user_id is not None:
                user_ids.append(user_id[0])
                user_id = c.fetchone()
            c.close()
            mail_thread = threading.Thread(target=mailing, args=(
                user_ids, 0, 0, 0, chat_id, textMailUser, photoMailUser, butUrlMail, butTextMail))
            mail_thread.start()
            await bot.send_message(chat_id, 'Рассылка началась!',
                                   reply_markup=admin_keyboard())

        elif textMail_but == msgtext:
            await bot.send_message(chat_id,
                                   'Введите текст рассылки. Допускаются теги HTML. Для отмены ввода нажите /start',
                                   reply_markup=mail_menu)
            await ProcessTextMailing.text.set()

        elif photoMail_but == msgtext:
            keyboard = InlineKeyboardMarkup()
            keyboard.row(InlineKeyboardButton(text='Добавить фото 📝', callback_data='editPhotoMail'))
            keyboard.row(InlineKeyboardButton(text='Удалить фото ❌', callback_data='deletePhoto'))
            await bot.send_message(chat_id, 'Выберите действие ⤵', reply_markup=keyboard)
            await MailingStates.admin_mailing.set()

        elif butMail_but == msgtext:
            keyboard = InlineKeyboardMarkup()
            keyboard.row(InlineKeyboardButton(text='Изменить текст кнопки 📝', callback_data='editTextBut'))
            keyboard.row(InlineKeyboardButton(text='Изменить ссылку кнопки 🔗', callback_data='editUrlBut'))
            keyboard.row(InlineKeyboardButton(text='Убрать всё к чертям 🙅‍♂', callback_data='deleteBut'))
            await bot.send_message(chat_id, 'Выберите действие ⤵', reply_markup=keyboard)
            await MailingStates.admin_mailing.set()

        elif msgtext == "/start":
            # bot.clear_step_handler(message)
            await start(message)

        else:
            # bot.clear_step_handler(message)
            await MailingStates.admin_mailing.set()

    user_id = message.chat.id
    c = conn.cursor(buffered=True)
    c.execute("select * from users where user_id = %s" % user_id)
    point = c.fetchone()
    if point is None:
        c.execute("insert into users (user_id, state) values (%s, %s)",
                  (user_id, 0))
        conn.commit()
    c.close()
    # bot.clear_step_handler(message)
    await admin_mailing(message)


@dp.message_handler(lambda message: message.text in list(
    btn_admin.values()) and message.from_user.id == message.chat.id and message.from_user.id == admin)
async def take_massage_admin(message: types.Message):
    user_id = message.from_user.id
    if message.text == btn_admin["panel_custom"]:
        await bot.send_message(user_id, btn_admin["panel_custom"],
                               reply_markup=main_menu(user_id))
    elif message.text == btn_admin["panel_administrator"]:
        await bot.send_message(user_id, btn_admin["panel_administrator"],
                               reply_markup=admin_keyboard())
    elif message.text == btn_admin["list_of_registered"]:
        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        c.execute("SELECT DISTINCT user_id FROM channel")
        all_user = c.fetchall()
        all_user = [int(i[0]) for i in all_user]
        count = 1
        text = ""
        for user in all_user:
            print(await bot.get_chat(user))
            c.execute("SELECT DISTINCT url, date FROM channel WHERE user_id = (%s)", (user,))
            url_list = c.fetchall()
            data_user = await bot.get_chat(user)
            name = f"{data_user.first_name + ' ' + data_user.last_name}"
            text += f"{count}. {'@' + data_user.username if data_user.username else str(data_user.id) + f' [{name}]'}\n"
            for url in url_list:
                text += f' {url[0]}  ->{url[1].strftime("%H:%M %d-%m-%y")}\n'
            if count % 5 == 0:
                await bot.send_message(admin, text)
                text = ""
            count += 1
        limit = 1
        while True:
            if len(text) > (4096 * limit):
                await bot.send_message(admin, text[(limit - 1) * 4096:(4096 * limit)])
                limit += 1
            else:
                await bot.send_message(admin, text[(limit - 1) * 4096:(4096 * limit)])
                break

        conn.commit()
        c.close()
    elif message.text == btn_admin["post_payment"]:
        await bot.send_message(user_id,
                               "Вышлите @username или id, и сумму оплаты\n\n<b>Пример:</b>\n<i>@username123 800\n123456789 800</i>",
                               parse_mode="HTML")
        await PostPayment.data.set()
    elif message.text == btn_admin["statistics"]:
        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        c.execute('''SELECT COUNT(*) FROM users''')
        allusers = int(c.fetchone()[0])
        c.execute('''SELECT COUNT(*) FROM users WHERE lively = 1''')
        banned = int(c.fetchone()[0])
        c.close()
        conn.commit()
        lively = allusers - banned
        admin_text = '*🙂 Количество живых пользователей:* {0}\n' \
                     '*% от числа всех:* {1}%\n' \
                     '*💩 Количество заблокировавших:* {2}'.format(str(lively), str(round(lively / allusers * 100, 2)),
                                                                   str(banned))
        await bot.send_message(user_id, admin_text, parse_mode='Markdown', reply_markup=admin_keyboard())


@dp.message_handler(
    lambda message: message.text in list(btn.values()) and message.from_user.id == message.chat.id)
async def take_massage(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]

    if int(possibility) == 0:
        username = f"{'@' + message.from_user.username if message.from_user.username else message.from_user.first_name}"
        if message.text == btn['registration']:
            await bot.send_message(user_id,
                                   f"Приветствую {username}, что бы закрепить за вами права на канал <b>вышлите</b> его ссылку или username, после проверки того что вы являетесь Владельцем канала - Канал попадет на Биржу покупки.",
                                   parse_mode="HTML", reply_markup=registration_keyboard())
            await Registration.url.set()
        elif message.text == btn['add_channel']:
            await bot.send_message(user_id, "Вышлите ссылку на канал или username")
            await Registration.url.set()
        elif message.text == btn['end_registration']:
            data = await state.get_data()
            url = data.get("url")
            if url:
                await bot.send_message(user_id, "Ожидайте завершения проверки", reply_markup=main_menu(user_id))
            else:
                await bot.send_message(user_id, "Регистрация не завершенна, каналы не добавлены",
                                       reply_markup=main_menu(user_id))
            await state.finish()
        elif message.text == btn['set_channel']:
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            c.execute("SELECT DISTINCT url FROM channel WHERE user_id = %s", (user_id,))
            all_url = c.fetchall()
            if all_url:
                for url in all_url:
                    keyboard.row(KeyboardButton(url[0]))
                await bot.send_message(user_id, "Вышлите ссылку на канал, который хотите редактировать",reply_markup=keyboard)
            else:
                await bot.send_message(user_id, "Вышлите ссылку на канал, который хотите редактировать")
            await SetChannel.url.set()
        elif message.text == btn['buy']:

            await bot.send_message(user_id, "Раздел покупки",
                                   reply_markup=shopping_keyboard())
            await Shopping.choice.set()
    conn.commit()
    c.close()


@dp.callback_query_handler(state="*")
async def process_callback_messages(callback_query: types.CallbackQuery, state: FSMContext):
    '''Обработка callback запросов'''
    user_id = callback_query.from_user.id
    query_id = callback_query.id
    # CONNECT TO DATABASE
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]

    if int(possibility) == 0:
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
                        user_data = await bot.get_chat(int(pool_data[2]))
                        await bot.edit_message_text(
                            f"{'@' + user_data.username if user_data.username else user_data.first_name + ' ' + user_data.last_name if user_data.last_name else user_data.first_name}\n{pool_data[1]}\nПодтверждено✅",
                            user_id,
                            message_id)
                    except:
                        await bot.delete_message(user_id, message_id)
                    await bot.send_message(int(pool_data[2]), f"Канал {pool_data[1]} успешно подтвержден✅")
        elif start_data == "unconfirm":
            if one_param == "pool":
                if user_id == admin:
                    c.execute("SELECT * FROM pool WHERE id = (%s)", (int(two_param),))
                    pool_data = c.fetchone()
                    c.execute("DELETE FROM pool WHERE id = (%s)", (int(two_param),))
                    try:
                        user_data = await bot.get_chat(int(pool_data[2]))
                        await bot.edit_message_text(
                            f"{'@' + user_data.username if user_data.username else user_data.first_name + ' ' + user_data.last_name if user_data.last_name else user_data.first_name}\n{pool_data[1]}\nОтклонено❌",
                            user_id,
                            message_id)
                    except:
                        await bot.delete_message(user_id, message_id)
                    await bot.send_message(int(pool_data[2]), f"Канал {pool_data[1]} не подтвержден❌")
        elif start_data == "connection":
            recipient_id = int(one_param)
            await bot.send_message(user_id, "Введите свой @username и сообщение")
            await state.update_data(recipient_id=recipient_id)
            await Connection.msg.set()
        elif 'editTextBut' == start_data:
            # bot.clear_step_handler(callback_query.message)
            await bot.send_message(user_id, "Введите текст для кнопки")
            # bot.register_next_step_handler(callback_query.message, process_editTextBut)
            await ProcessEditTextBut.text.set()

        elif 'editUrlBut' == start_data:
            # bot.clear_step_handler(callback_query.message)
            await bot.send_message(user_id, 'Введите ссылку 📝', reply_markup=mail_menu)
            await ProcessEditUrlBut.text.set()

        elif 'deleteBut' == start_data:
            c = conn.cursor(buffered=True)
            c.execute("""update users set butUrlMail = 0, butTextMail = 0 where user_id = (%s)""", (user_id,))
            conn.commit()
            c.close()
            await bot.send_message(user_id, 'Удалено! 🗑', reply_markup=mail_menu)
            await cheker(callback_query.message)

        elif 'editPhotoMail' == start_data:

            # bot.clear_step_handler(callback_query.message)
            await bot.send_message(user_id, 'Отправьте фотографию', reply_markup=mail_menu)
            await WaitPhoto.text.set()

        elif 'deletePhoto' == start_data:
            c = conn.cursor(buffered=True)
            c.execute("""update users set photoMail = 0 where user_id = (%s)""", (user_id,))
            conn.commit()
            c.close()
            await bot.send_message(user_id, 'Фото удалено! ✅', reply_markup=mail_menu)
            await cheker(callback_query.message)

        await bot.answer_callback_query(query_id)
        conn.commit()
        c.close()


@dp.message_handler(state=Registration.url)
async def get_registration_url(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    if int(possibility) == 0:
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
            await bot.send_message(user_id, "Вышлите ссылку на канал или username")
            await Registration.url.set()
        elif text == '/start':
            await state.finish()
            await start(message)
        else:
            if re.match("^@\w+$", text) or re.match("^t\.me/\w+$", text) or re.match("^https://t\.me/\w+$", text):
                if re.match("^@\w+$", text):
                    text = text.replace("@", "https://t.me/")
                if re.match("^t\.me/\w+$", text):
                    text = text.replace("t.me/", "https://t.me/")
                dbconfig = read_db_config()
                conn = MySQLConnection(**dbconfig)
                c = conn.cursor(buffered=True)
                c.execute("SELECT DISTINCT url FROM channel")
                all_url = c.fetchall()
                all_url = [i[0] for i in all_url]
                if text in all_url:
                    await bot.send_message(user_id, "Такой канал уже есть на бирже. Вышлите новою ссылку на канал или username")
                    await Registration.url.set()
                else:
                    id = int(datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
                    c.execute("INSERT INTO pool (id, url, user_id) VALUES (%s, %s, %s)",
                              (id, text, user_id))
                    username = f"{'@' + message.from_user.username if message.from_user.username else message.from_user.first_name + ' ' + message.from_user.last_name if message.from_user.last_name else message.from_user.first_name}"
                    keyboard = InlineKeyboardMarkup().row(
                        InlineKeyboardButton("Подтвердить✅", callback_data=f"confirm_pool_{str(id)}"),
                        InlineKeyboardButton("Отклонить❌", callback_data=f"unconfirm_pool_{str(id)}"))
                    await state.update_data(url=text)
                    await bot.send_message(admin, f"{username}\n{text}", reply_markup=keyboard)
                    await bot.send_message(user_id, "Канал добавлен, ожидайте подтверждения")
                conn.commit()
                c.close()
            else:
                await bot.send_message(user_id, "Вышлите ссылку на канал или username")
                await Registration.url.set()


@dp.message_handler(state=SetChannel.url)
async def get_set_url(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    username = f"{'@' + message.from_user.username if message.from_user.username else message.from_user.first_name}"
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif re.match("^https://t\.me/\w+$", text):

            dbconfig = read_db_config()
            conn = MySQLConnection(**dbconfig)
            c = conn.cursor(buffered=True)
            c.execute("SELECT DISTINCT url FROM channel WHERE user_id = (%s)", (user_id,))
            all_url = c.fetchall()
            conn.commit()
            c.close()
            all_url = [i[0] for i in all_url]
            if text in all_url:
                await bot.send_message(user_id, "Теперь выберите, что хотите редактировать",
                                       reply_markup=set_channel_keyboard())
                await state.update_data(url=text)
                await SetChannel.choice.set()
            else:
                await bot.send_message(user_id, "Такого канала нет на бирже!")
                await state.finish()
                await take_massage(message, state)

        else:
            await bot.send_message(user_id, "Вышлите ссылку на канал")
            await SetChannel.url.set()


@dp.message_handler(state=SetChannel.choice)
async def get_set_choice(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    conn.commit()
    c.close()
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif text == btn["coverage"]:
            await bot.send_message(user_id, "Введите дипазон охвата вашего канала\nПример:10000-11000")
            await SetChannel.coverage.set()
        elif text == btn["price"]:
            await bot.send_message(user_id, "Введите цену")
            await SetChannel.price.set()
        elif text == btn["time"]:
            await bot.send_message(user_id, "Вышлите время суток", reply_markup=time_keyboard())
            await SetChannel.time1.set()
        elif text == btn["end_set_channel"]:
            await bot.send_message(user_id, "Редактирования завершено",
                                   reply_markup=main_menu(user_id))
            await state.finish()


@dp.message_handler(state=SetChannel.coverage)
async def get_set_coverage(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif re.match("^\d+-{1}\d+$", text):
            number1 = int(text.split('-')[0])
            number2 = int(text.split('-')[1])
            if number1 < number2:
                dbconfig = read_db_config()
                conn = MySQLConnection(**dbconfig)
                c = conn.cursor(buffered=True)
                data = await state.get_data()
                url = data.get("url")
                print("1111")
                c.execute("UPDATE channel SET coverage1 = (%s), coverage2 = (%s) WHERE url = (%s) and user_id = (%s)",
                          (number1, number2, url, user_id,))
                conn.commit()
                c.close()
                await bot.send_message(user_id, 'Охват сохранен')
                await SetChannel.choice.set()
            else:
                await bot.send_message(user_id, "Введите дипазон охвата вашего канала\nПример:10000-11000")
                await SetChannel.coverage.set()
        elif text == btn["coverage"]:
            await bot.send_message(user_id, "Введите дипазон охвата вашего канала\nПример:10000-11000")
            await SetChannel.coverage.set()
        elif text == btn["price"]:
            await bot.send_message(user_id, "Введите цену")
            await SetChannel.price.set()
        elif text == btn["time"]:
            await bot.send_message(user_id, "Вышлите время суток", reply_markup=time_keyboard())
            await SetChannel.time1.set()
        elif text == btn["end_set_channel"]:
            await bot.send_message(user_id, "Редактирования завершено",
                                   reply_markup=main_menu(user_id))
            await state.finish()
        else:
            await bot.send_message(user_id, "Введите дипазон охвата вашего канала\nПример:10000-11000")
            await SetChannel.coverage.set()


@dp.message_handler(state=SetChannel.price)
async def get_set_price(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    conn.commit()
    c.close()
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif re.match("^\d+$", text):
            dbconfig = read_db_config()
            conn = MySQLConnection(**dbconfig)
            c = conn.cursor(buffered=True)
            data = await state.get_data()
            url = data.get("url")
            c.execute("UPDATE channel SET price = (%s) WHERE url = (%s) and user_id = (%s)",
                      (message.text, url, user_id,))
            conn.commit()
            c.close()
            await bot.send_message(user_id, 'Цена сохранена')
            await SetChannel.choice.set()
        elif text == btn["coverage"]:
            await bot.send_message(user_id, "Введите дипазон охвата вашего канала\nПример:10000-11000")
            await SetChannel.coverage.set()
        elif text == btn["price"]:
            await bot.send_message(user_id, "Введите цену")
            await SetChannel.price.set()
        elif text == btn["time"]:
            await bot.send_message(user_id, "Вышлите время суток", reply_markup=time_keyboard())
            await SetChannel.time1.set()
        elif text == btn["end_set_channel"]:
            await bot.send_message(user_id, "Редактирования завершено",
                                   reply_markup=main_menu(user_id))
            await state.finish()
        else:
            await bot.send_message(user_id, "Введите цену")
            await SetChannel.price.set()


@dp.message_handler(state=SetChannel.time1)
async def get_set_time1(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif text in [btn["morning"], btn["day"], btn["evening"], btn["night"]]:
            await bot.send_message(user_id, f"Вышлите {btn['tick']}(свободно) или {btn['dagger']}(занято)",
                                   reply_markup=action_time_keyboard())
            if text == btn["morning"]:
                await state.update_data(time_choice=1)
            elif text == btn["day"]:
                await state.update_data(time_choice=2)
            elif text == btn["evening"]:
                await state.update_data(time_choice=3)
            elif text == btn["night"]:
                await state.update_data(time_choice=4)

            await SetChannel.time2.set()
        else:
            await bot.send_message(user_id, "Вышлите время суток", reply_markup=time_keyboard())
            await SetChannel.time1.set()


@dp.message_handler(state=SetChannel.time2)
async def get_set_time2(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        if text in [btn['tick'], btn['dagger']]:
            dbconfig = read_db_config()
            conn = MySQLConnection(**dbconfig)
            c = conn.cursor(buffered=True)
            data = await state.get_data()
            url = data.get("url")
            time_choice = data.get("time_choice")
            c.execute(
                f"UPDATE channel SET {'morning' if time_choice == 1 else 'day' if time_choice == 2 else 'evening' if time_choice == 3 else 'night'} = (%s) WHERE url = (%s) and user_id = (%s)",
                (1 if text == btn['tick'] else 0, url, user_id,))
            conn.commit()
            c.close()
            await bot.send_message(user_id, "Ответ сохранен", reply_markup=set_channel_keyboard())
            await SetChannel.choice.set()
        else:
            await bot.send_message(user_id, "Ответ не сохранен", reply_markup=set_channel_keyboard())
            await SetChannel.choice.set()


@dp.message_handler(state=PostPayment.data)
async def get_post_payment(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    if text == '/start':
        await state.finish()
        await start(message)
    elif message.text in [btn_admin["panel_custom"], btn_admin["panel_administrator"], btn_admin["list_of_registered"]]:
        await state.finish()
        await take_massage_admin(message)
    else:
        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        c.execute("SELECT DISTINCT user_id FROM users")
        users = c.fetchall()
        users = [int(i[0]) for i in users]
        user_id_payer = None
        price = 0
        if re.match("^\@\w+ \d+$", text):
            username = text.split(" ")[0].replace("@", "")
            price = int(text.split(" ")[1])
            for user in users:
                data_user = await bot.get_chat(user)
                if data_user.username == username:
                    user_id_payer = user
                    break
        elif re.match("^\d{6,} \d+$", text):
            text_user_id = int(text.split(" ")[0])
            price = int(text.split(" ")[1])
            if text_user_id in users:
                user_id_payer = text_user_id

        if user_id_payer and price != 0:
            id = int(time.time())
            c.execute(
                """INSERT INTO requests (id, sum, date, id_user, status, ps) VALUES (%s,%s,%s,%s,%s,%s)""",
                (id, price, time.time(), user_id_payer, 'processing', "yandex"))
            url = f'https://money.yandex.ru/to/{yandex_number}/{int(float(price))}'
            keyboard = InlineKeyboardMarkup().row(InlineKeyboardButton(text="Оплатить", url=url))

            text = f"Переведите {price} ₽ на `{yandex_number}`, чтобы восстановить доступ к бота.\n" \
                   f"❗️*Обязательно* укажите коментарий к оплате: `{user_id_payer}`❗️" \
                   f"Платеж подтвердится автоматически.\n\n" \
                   f"*Если ваш платежный оператор берет комиссию, то вам необходимо самостоятельно " \
                   f"заложить ее в перевод, что бы фактическая сумма перевода не была меньше.\n\n" \
                   f"Заявка актуальна 10 минут*"
            await bot.send_message(user_id_payer, text, parse_mode="Markdown", reply_markup=keyboard)
            c.execute(
                f"UPDATE users SET  possibility = 1 WHERE user_id = (%s)",
                (user_id_payer,))
            conn.commit()
            c.close()
            await state.finish()
        else:
            await bot.send_message(user_id,
                                   "Введены невалидные данные. Вышлите @username или id, и сумму оплаты",
                                   parse_mode="HTML")
            await PostPayment.data.set()
        conn.commit()
        c.close()


@dp.message_handler(state=Shopping.choice)
async def get_set_choice(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    conn.commit()
    c.close()
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif text == btn["search_channel"]:
            await bot.send_message(user_id, "Выберите желамое время размещения вашего поста",
                                   reply_markup=time_keyboard().row(KeyboardButton(btn["any"])))
            await Shopping.time.set()
        elif text == btn["end_shopping"]:
            await bot.send_message(user_id, "Покупка завершена",
                                   reply_markup=main_menu(user_id))
            await state.finish()


@dp.message_handler(state=Shopping.time)
async def get_shopping_time(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    conn.commit()
    c.close()
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif text == btn["search_channel"]:

            await bot.send_message(user_id, "Выберите желамое время размещения вашего поста",
                                   reply_markup=time_keyboard().row(KeyboardButton(btn["any"])))
            await Shopping.time.set()
        elif text == btn["end_shopping"]:
            await bot.send_message(user_id, "Покупка завершена",
                                   reply_markup=main_menu(user_id))
            await state.finish()
        elif text in [btn["morning"], btn["day"], btn["evening"], btn["night"], btn['any']]:
            await bot.send_message(user_id,
                                   f"Для поиска подходящего канал исполюзуйте один из Диапазонов: Охват или Цена",
                                   reply_markup=shopping_keyboard())
            await bot.send_message(user_id,
                                   f"<b>Пример:</b>\nЦена:500-1000\n-----------\nОхват:1000-10000\n-----------\nЦена:500-1000\nОхват:1000-10000",
                                   reply_markup=shopping_keyboard(), parse_mode="HTML")
            if text == btn["morning"]:
                await state.update_data(time_choice=1)
            elif text == btn["day"]:
                await state.update_data(time_choice=2)
            elif text == btn["evening"]:
                await state.update_data(time_choice=3)
            elif text == btn["night"]:
                await state.update_data(time_choice=4)
            elif text == btn["any"]:
                await state.update_data(time_choice=5)

            await Shopping.parameters.set()
        else:
            await bot.send_message(user_id, "Выберите желамое время размещения вашего поста",
                                   reply_markup=time_keyboard().row(KeyboardButton(btn["any"])))
            await Shopping.time.set()


@dp.message_handler(state=Shopping.parameters)
async def get_shopping_parameters(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    text = text.replace("\n", "")
    data = await state.get_data()
    time_choice = data.get("time_choice")
    sql_time = ""
    if time_choice == 1:
        sql_time = "and morning = 1"
    elif time_choice == 2:
        sql_time = "and day = 1"
    elif time_choice == 3:
        sql_time = "and evening = 1"
    elif time_choice == 4:
        sql_time = "and night = 1"
    elif time_choice == 5:
        sql_time = "and (morning = 1 or day = 1 or evening = 1 or night = 1)"
    if int(possibility) == 0:
        print(text)
        if text == '/start':
            await state.finish()
            await start(message)
        elif text == btn["search_channel"]:
            await bot.send_message(user_id, "Выберите желамое время размещения вашего поста",
                                   reply_markup=time_keyboard().row(KeyboardButton(btn["any"])))
            await Shopping.time.set()
        elif text == btn["end_shopping"]:
            await bot.send_message(user_id, "Покупка завершена",
                                   reply_markup=main_menu(user_id))
            await state.finish()
        elif re.match("^Охват:\d+-\d+$", text.replace(" ", "")) or re.match("^Цена:\d+-\d+$",
                                                                            text.replace(" ", "")) or re.match(
            "^Охват:\d+-\d+Цена:\d+-\d+$", text.replace(" ", "")) or re.match("^Цена:\d+-\d+Охват:\d+-\d+$",
                                                                              text.replace(" ", "")):
            msg_text = "Выберете номер для подробной информации\n"
            available = []
            conformity = {}
            if re.match("^Охват:\d+-\d+$", text.replace(" ", "")):
                text = text.replace(" ", "")
                text = text.replace("Охват:", "")
                num1 = int(text.split("-")[0])
                num2 = int(text.split("-")[1])
                if num2 >= num1:
                    c.execute(f"SELECT * FROM channel WHERE coverage1 < {num2} and  coverage2 > {num1} {sql_time}")
                    available = c.fetchall()
                else:
                    await bot.send_message(user_id,
                                           f"Для поиска подходящего канал исполюзуйте один из Диапазонов: Охват или Цена",
                                           reply_markup=shopping_keyboard())
                    await Shopping.parameters.set()
            elif re.match("^Цена:\d+-\d+$", text.replace(" ", "")):
                text = text.replace(" ", "")
                text = text.replace("Цена:", "")
                num1 = int(text.split("-")[0])
                num2 = int(text.split("-")[1])
                if num2 >= num1:
                    c.execute(f"SELECT * FROM channel WHERE price <= {num2} and  price >= {num1} {sql_time}")
                    available = c.fetchall()
                else:
                    await bot.send_message(user_id,
                                           f"Для поиска подходящего канал исполюзуйте один из Диапазонов: Охват или Цена",
                                           reply_markup=shopping_keyboard())
                    await Shopping.parameters.set()
            elif re.match(
                    "^Охват:\d+-\d+Цена:\d+-\d+$", text.replace(" ", "")):
                text = text.replace(" ", "")
                text = text.replace("Цена", "").replace("Охват:", "")
                coverage1 = int(text.split(":")[0].split("-")[0])
                coverage2 = int(text.split(":")[0].split("-")[1])
                price1 = int(text.split(":")[1].split("-")[0])
                price2 = int(text.split(":")[1].split("-")[1])
                if coverage1 <= coverage2 and price1 <= price2:
                    c.execute(
                        f"SELECT * FROM channel WHERE price <= {price2} and  price >= {price1} and coverage1 < {coverage2} and  coverage2 > {coverage1} {sql_time}")
                    available = c.fetchall()
                else:
                    await bot.send_message(user_id,
                                           f"Для поиска подходящего канал исполюзуйте один из Диапазонов: Охват или Цена",
                                           reply_markup=shopping_keyboard())
                    await Shopping.parameters.set()
            elif re.match("^Цена:\d+-\d+Охват:\d+-\d+$", text.replace(" ", "")):
                text = text.replace(" ", "")
                text = text.replace("Цена:", "").replace("Охват", "")
                coverage1 = int(text.split(":")[1].split("-")[0])
                coverage2 = int(text.split(":")[1].split("-")[1])
                price1 = int(text.split(":")[0].split("-")[0])
                price2 = int(text.split(":")[0].split("-")[1])
                if coverage1 <= coverage2 and price1 <= price2:
                    c.execute(
                        f"SELECT * FROM channel WHERE price <= {price2} and  price >= {price1} and coverage1 < {coverage2} and  coverage2 > {coverage1} {sql_time}")
                    available = c.fetchall()
                else:
                    await bot.send_message(user_id,
                                           f"Для поиска подходящего канал исполюзуйте один из Диапазонов: Охват или Цена",
                                           reply_markup=shopping_keyboard())
                    await Shopping.parameters.set()
            print(available)
            if available:
                count = 1
                for item in available:
                    conformity[count] = item[0]
                    msg_text += f"\n{count}. {item[1]}"
                    msg_text += f"\nОхват: {item[3]}-{item[4]}"
                    msg_text += f"\nЦена: {item[5]}"
                    count += 1
                msg_text+="\n\nДля нового поиска введите запрос по диапазонам"
                await state.update_data(dict=conformity)
                limit = 1
                while True:
                    if len(msg_text) > (4096 * limit):
                        await bot.send_message(user_id, msg_text[(limit - 1) * 4096:(4096 * limit)])
                        limit += 1
                    else:
                        await bot.send_message(user_id, msg_text[(limit - 1) * 4096:(4096 * limit)])
                        break
                await Shopping.number.set()
            else:
                await bot.send_message(user_id, "Совпадений не найдено")
                await Shopping.choice.set()
        else:
            await bot.send_message(user_id,
                                   f"Для поиска подходящего канал исполюзуйте один из Диапазонов: Охват или Цена",
                                   reply_markup=shopping_keyboard())
            await Shopping.parameters.set()


@dp.message_handler(state=Shopping.number)
async def get_shopping_number(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]

    data = await state.get_data()
    conformity = data.get("dict")
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif text == btn["search_channel"]:
            await bot.send_message(user_id, "Выберите желамое время размещения вашего поста",
                                   reply_markup=time_keyboard().row(KeyboardButton(btn["any"])))
            await Shopping.time.set()
        elif text == btn["end_shopping"]:
            await bot.send_message(user_id, "Покупка завершена",
                                   reply_markup=main_menu(user_id))
            await state.finish()
        elif re.match("^\d+$", text.replace(" ", "")):

            id = int(message.text)
            try:
                sql_id = conformity[id]
            except:
                await bot.send_message(user_id, "Выберете номер для подробной информации")
                await Shopping.number.set()
            c.execute("SELECT url, user_id FROM channel WHERE id = %s", (sql_id,))

            data = c.fetchone()
            msg_st = await bot.send_message(user_id, "Форимируем статистику...")
            try:
                url_image = parse_telemetr.get_image(data[0])
            except Exception as e:
                print(e)
                try:
                    url_image = parse_telemetr.get_image(data[0])
                except:
                    url_image = None
            await bot.delete_message(user_id, msg_st.message_id)
            keyboard = InlineKeyboardMarkup().row(
                InlineKeyboardButton("Связаться через бот", callback_data=f"connection_{data[1]}"))
            await bot.send_message(user_id, data[0], reply_markup=keyboard)

            if url_image:
                await bot.send_message(user_id, url_image)
            await state.finish()
            await Shopping.choice.set()
        elif re.match("^Охват:\d+-\d+$", text.replace(" ", "")) or re.match("^Цена:\d+-\d+$",
                                                                            text.replace(" ", "")) or re.match(
            "^Охват:\d+-\d+Цена:\d+-\d+$", text.replace(" ", "")) or re.match("^Цена:\d+-\d+Охват:\d+-\d+$",
                                                                              text.replace(" ", "")):
            await get_shopping_parameters(message, state)
        else:
            await bot.send_message(user_id, "Выберете номер для подробной информации")
            await Shopping.number.set()
    conn.commit()
    c.close()


@dp.message_handler(state=Connection.msg)
async def get_connection_msg(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    c.execute("select possibility from users where user_id = %s", (user_id,))
    possibility = c.fetchone()[0]
    conn.commit()
    c.close()
    data = await state.get_data()
    recipient_id = data.get("recipient_id")
    if int(possibility) == 0:
        if text == '/start':
            await state.finish()
            await start(message)
        elif text == btn["search_channel"]:
            await bot.send_message(user_id, "Выберите желамое время размещения вашего поста",
                                   reply_markup=time_keyboard().row(KeyboardButton(btn["any"])))
            await Shopping.time.set()
        elif text == btn["end_shopping"]:
            await bot.send_message(user_id, "Покупка завершена",
                                   reply_markup=main_menu(user_id))
            await state.finish()
        elif '@' in text:
            keyboard = InlineKeyboardMarkup().row(
                InlineKeyboardButton("Связаться через бот", callback_data=f"connection_{user_id}"))
            await bot.send_message(user_id, "Отправлено")
            await bot.send_message(recipient_id, text, reply_markup=keyboard)
            await state.finish()
            await Shopping.choice.set()
        else:
            await bot.send_message(user_id, "Введите свой @username и сообщение")
            await state.update_data(recipient_id=recipient_id)
            await Connection.msg.set()


@dp.message_handler(state=MailingStates.admin_mailing)
async def get_telegram_id(message: types.Message, state: FSMContext):
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    chat_id = message.chat.id
    msgtext = message.text
    c.execute("""select textMail,photoMail,butTextMail,butUrlMail from users where user_id = %s""" % chat_id)
    data = c.fetchone()
    textMailUser = str(data[0])
    photoMailUser = str(data[1])
    butTextMail = str(data[2])
    butUrlMail = str(data[3])
    if msgtext == mail_but:
        await bot.send_message(chat_id, '*Вы попали в меню рассылки *📢\n\n'
                                        'Для возврата нажмите *{0}*\n\n'
                                        'Для отмены какой-либо операции нажмите /start\n\n'
                                        'Используйте *{1}* для предварительного просмотра рассылки, а *{2}* для начала'
                                        ' рассылки\n\n'
                                        'Текст рассылки поддерживает разметку *HTML*, то есть:\n'
                                        '<b>*Жирный*</b>\n'
                                        '<i>_Курсив_</i>\n'
                                        '<pre>`Моноширный`</pre>\n'
                                        '<a href="ссылка-на-сайт">[Обернуть текст в ссылку](test.ru)</a>'.format(
            backMail_but, preMail_but, startMail_but
        ),
                               parse_mode="markdown", reply_markup=mail_menu)
        await MailingStates.admin_mailing.set()

    elif msgtext == backMail_but:
        await bot.send_message(chat_id, backMail_but, reply_markup=admin_keyboard())
        # bot.clear_step_handler(message)

    elif msgtext == preMail_but:
        try:
            if butTextMail == '0' and butUrlMail == '0':
                if photoMailUser == '0':
                    await bot.send_message(chat_id, textMailUser, parse_mode='html', reply_markup=mail_menu)
                else:
                    await bot.send_photo(chat_id, caption=textMailUser, photo=photoMailUser, parse_mode='html',
                                         reply_markup=mail_menu)
            else:
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton(text=butTextMail, url=butUrlMail))
                if photoMailUser == '0':
                    await bot.send_message(chat_id, textMailUser, parse_mode='html',
                                           reply_markup=keyboard)
                else:
                    await bot.send_photo(chat_id, caption=textMailUser, photo=photoMailUser, parse_mode='html',
                                         reply_markup=keyboard)
        except:
            await bot.send_message(chat_id, "Упс..проверьте правильность введения данных")
        await MailingStates.admin_mailing.set()

    elif msgtext == startMail_but:
        c.execute(
            """update users set textMail = 0, photoMail = 0,butTextMail = 0,butUrlMail = 0  where user_id = %s""" % chat_id)
        user_ids = []
        c.execute("""select user_id from users""")
        user_id = c.fetchone()
        while user_id is not None:
            user_ids.append(user_id[0])
            user_id = c.fetchone()
        c.close()
        """
        mail_thread = threading.Thread(target=mailing, args=(
            user_ids, 0, 0, 0, chat_id, textMailUser, photoMailUser, butUrlMail, butTextMail))
        mail_thread.start()
        """
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                mailing(user_ids, 0, 0, 0, chat_id, textMailUser, photoMailUser, butUrlMail, butTextMail))
            await bot.send_message(chat_id, 'Рассылка началась!',
                                   reply_markup=admin_keyboard())
        except:
            pass
    elif textMail_but == msgtext:
        await bot.send_message(chat_id,
                               'Введите текст рассылки. Допускаются теги HTML. Для отмены ввода нажите /start',
                               reply_markup=mail_menu)
        await ProcessTextMailing.text.set()

    elif photoMail_but == msgtext:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton(text='Добавить фото 📝', callback_data='editPhotoMail'))
        keyboard.row(InlineKeyboardButton(text='Удалить фото ❌', callback_data='deletePhoto'))
        await bot.send_message(chat_id, 'Выберите действие ⤵', reply_markup=keyboard)
        await MailingStates.admin_mailing.set()

    elif butMail_but == msgtext:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton(text='Изменить текст кнопки 📝', callback_data='editTextBut'))
        keyboard.row(InlineKeyboardButton(text='Изменить ссылку кнопки 🔗', callback_data='editUrlBut'))
        keyboard.row(InlineKeyboardButton(text='Убрать всё к чертям 🙅‍♂', callback_data='deleteBut'))
        await bot.send_message(chat_id, 'Выберите действие ⤵', reply_markup=keyboard)
        await MailingStates.admin_mailing.set()

    elif msgtext == "/start":
        # bot.clear_step_handler(message)
        await state.finish()
        await start(message)
    else:
        # bot.clear_step_handler(message)
        await MailingStates.admin_mailing.set()


@dp.message_handler(state=ProcessTextMailing.text)
async def get_telegram_id(message: types.Message, state: FSMContext):
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    chat_id = message.from_user.id
    if message.text:
        if message.text == "/start":
            await bot.send_message(chat_id, "Действие отменено")
        else:
            c = conn.cursor(buffered=True)
            c.execute("update users set textMail = (%s) where user_id = (%s)", (message.text,
                                                                                chat_id))
            conn.commit()
            c.close()
            await bot.send_message(chat_id, "Текст успешно установлен")
            await state.finish()
        await MailingStates.admin_mailing.set()


@dp.message_handler(state=ProcessEditTextBut.text)
async def get_telegram_id(message: types.Message, state: FSMContext):
    chat_id = message.from_user.id
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)
    c = conn.cursor(buffered=True)
    # c.execute("""update users set state = 0 where user_id = %s""" % (chat_id))
    c.execute("update users set butTextMail = (%s) where user_id = (%s)", (message.text,
                                                                           chat_id))
    conn.commit()
    c.close()
    await bot.send_message(chat_id, 'Текст кнопки обновлен! ✅', reply_markup=mail_menu)
    await state.finish()


@dp.message_handler(state=ProcessEditUrlBut.text)
async def get_telegram_id(message: types.Message, state: FSMContext):
    if message.text:
        chat_id = message.from_user.id
        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        c.execute("update users set butUrlMail = (%s) where user_id = (%s)", (message.text,
                                                                              chat_id))
        conn.commit()
        c.close()
        await bot.send_message(chat_id, 'Ссылка кнопки обновлена! ✅', reply_markup=mail_menu)
        await state.finish()
        await cheker(message)


@dp.message_handler(state=CheckerState.check)
async def get_telegram_id(message: types.Message, state: FSMContext):
    dbconfig = read_db_config()
    conn = MySQLConnection(**dbconfig)

    async def admin_mailing(message: types.Message):
        chat_id = message.chat.id
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        msgtext = message.text
        c.execute("""select textMail,photoMail,butTextMail,butUrlMail from users where user_id = %s""" % chat_id)
        data = c.fetchone()
        textMailUser = str(data[0])
        photoMailUser = str(data[1])
        butTextMail = str(data[2])
        butUrlMail = str(data[3])
        if msgtext == mail_but:
            await bot.send_message(chat_id, '*Вы попали в меню рассылки *📢\n\n'
                                            'Для возврата нажмите *{0}*\n\n'
                                            'Для отмены какой-либо операции нажмите /start\n\n'
                                            'Используйте *{1}* для предварительного просмотра рассылки, а *{2}* для начала'
                                            ' рассылки\n\n'
                                            'Текст рассылки поддерживает разметку *HTML*, то есть:\n'
                                            '<b>*Жирный*</b>\n'
                                            '<i>_Курсив_</i>\n'
                                            '<pre>`Моноширный`</pre>\n'
                                            '<a href="ссылка-на-сайт">[Обернуть текст в ссылку](test.ru)</a>'.format(
                backMail_but, preMail_but, startMail_but
            ),
                                   parse_mode="markdown", reply_markup=mail_menu)
            await MailingStates.admin_mailing.set()

        elif msgtext == backMail_but:
            await bot.send_message(chat_id, backMail_but, reply_markup=admin_keyboard())
            # bot.clear_step_handler(message)

        elif msgtext == preMail_but:
            try:
                if butTextMail == '0' and butUrlMail == '0':
                    if photoMailUser == '0':
                        await bot.send_message(chat_id, textMailUser, parse_mode='html', reply_markup=mail_menu)
                    else:
                        await bot.send_photo(chat_id, caption=textMailUser, photo=photoMailUser, parse_mode='html',
                                             reply_markup=mail_menu)
                else:
                    keyboard = InlineKeyboardMarkup()
                    keyboard.add(InlineKeyboardButton(text=butTextMail, url=butUrlMail))
                    if photoMailUser == '0':
                        await bot.send_message(chat_id, textMailUser, parse_mode='html',
                                               reply_markup=keyboard)
                    else:
                        await bot.send_photo(chat_id, caption=textMailUser, photo=photoMailUser, parse_mode='html',
                                             reply_markup=keyboard)
            except:
                await bot.send_message(chat_id, "Упс..проверьте правильность введения данных")
            await MailingStates.admin_mailing.set()

        elif msgtext == startMail_but:
            c.execute(
                """update users set textMail = 0, photoMail = 0,butTextMail = 0,butUrlMail = 0  where user_id = %s""" % chat_id)
            user_ids = []
            c.execute("""select user_id from users""")
            user_id = c.fetchone()
            while user_id is not None:
                user_ids.append(user_id[0])
                user_id = c.fetchone()
            c.close()
            """
            mail_thread = threading.Thread(target=mailing, args=(
                user_ids, 0, 0, 0, chat_id, textMailUser, photoMailUser, butUrlMail, butTextMail))
            mail_thread.start()
            """
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(
                    mailing(user_ids, 0, 0, 0, chat_id, textMailUser, photoMailUser, butUrlMail, butTextMail))
                await bot.send_message(chat_id, 'Рассылка началась!',
                                       reply_markup=admin_keyboard())
            except:
                pass

        elif textMail_but == msgtext:
            await bot.send_message(chat_id,
                                   'Введите текст рассылки. Допускаются теги HTML. Для отмены ввода нажите /start',
                                   reply_markup=mail_menu)
            await ProcessTextMailing.text.set()

        elif photoMail_but == msgtext:
            keyboard = InlineKeyboardMarkup()
            keyboard.row(InlineKeyboardButton(text='Добавить фото 📝', callback_data='editPhotoMail'))
            keyboard.row(InlineKeyboardButton(text='Удалить фото ❌', callback_data='deletePhoto'))
            await bot.send_message(chat_id, 'Выберите действие ⤵', reply_markup=keyboard)
            await MailingStates.admin_mailing.set()

        elif butMail_but == msgtext:
            keyboard = InlineKeyboardMarkup()
            keyboard.row(InlineKeyboardButton(text='Изменить текст кнопки 📝', callback_data='editTextBut'))
            keyboard.row(InlineKeyboardButton(text='Изменить ссылку кнопки 🔗', callback_data='editUrlBut'))
            keyboard.row(InlineKeyboardButton(text='Убрать всё к чертям 🙅‍♂', callback_data='deleteBut'))
            await bot.send_message(chat_id, 'Выберите действие ⤵', reply_markup=keyboard)
            await MailingStates.admin_mailing.set()

        elif msgtext == "/start":
            # bot.clear_step_handler(message)
            await start(message)

        else:
            # bot.clear_step_handler(message)
            await MailingStates.admin_mailing.set()

    user_id = message.chat.id
    c = conn.cursor(buffered=True)
    c.execute("select * from users where user_id = %s" % user_id)
    point = c.fetchone()
    if point is None:
        c.execute("insert into users (user_id, state) values (%s, %s)",
                  (user_id, 0))
        conn.commit()
    c.close()
    # bot.clear_step_handler(message)
    await state.finish()
    await admin_mailing(message)


@dp.message_handler(state=WaitPhoto.text, content_types=['photo'])
async def get_telegram_id(message: types.Message, state: FSMContext):
    print("photo")
    chat_id = message.from_user.id
    if message.content_type == 'photo':
        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        c = conn.cursor(buffered=True)
        # msgphoto = message.json['photo'][0]['file_id']
        msgphoto = message.photo[0].file_id
        c.execute("""update users set photoMail = (%s) where user_id = (%s)""", (msgphoto, chat_id,))
        await bot.send_message(chat_id, 'Фото прикреплено! ✅', reply_markup=mail_menu)
        conn.commit()
        c.close()
        # bot.register_next_step_handler(message, cheker)
        await state.finish()
        await CheckerState.check.set()
    else:
        await bot.send_message(chat_id, "Упс...", reply_markup=mail_menu)
        await CheckerState.check.set()
        # bot.register_next_step_handler(message, cheker)


def repeat(coro, loop):
    asyncio.ensure_future(coro(), loop=loop)
    loop.call_later(30, repeat, coro, loop)


if __name__ == '__main__':
    # loop = asyncio.get_event_loop()
    # loop.call_later(30, repeat, yandex_dep, loop)
    executor.start_polling(dp)
