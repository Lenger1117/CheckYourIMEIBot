from telegram.ext import Updater, Filters, MessageHandler, CommandHandler, ConversationHandler, JobQueue
from telegram import ReplyKeyboardMarkup
import requests
import os
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv('B_TOKEN')
KEY_WEATHER = os.getenv('W_KEY')
IMEI_TOKEN = os.getenv('I_TOKEN')

updater = Updater(token=BOT_TOKEN)
job_queue = updater.job_queue  # Получаем очередь задач (JobQueue)

URL_CAT = 'https://api.thecatapi.com/v1/images/search'
URL_QUOTE = 'http://api.forismatic.com/api/1.0/?method=getQuote&format=json&lang=ru'
URL_WEATHER = 'https://api.openweathermap.org/data/2.5/weather?q={city_name}&APPID={api_key}&lang=ru'
URL_IMEI = 'https://api.imeicheck.net/v1/checks'

ASKING_CITY, ASKING_IMEI = range(2)


def is_valid_imei(imei: str) -> bool:
    if not imei.isdigit() or len(imei) != 15:
        return False
    digits = [int(d) for d in imei]
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


# Создание клавиатуры
def create_keyboard():
    keyboard = [['Покажи котика', 'Хочу цитату'],
                ['Покажи погоду', 'Проверить IMEI'],
                ['Начать']]  # Добавляем кнопку "Начать"
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# Запрос IMEI у пользователя
def ask_imei(update, context):
    chat = update.effective_chat
    try:
        context.bot.send_message(chat.id, 'Какой у вас IMEI? Его можно узнать, набрав на телефоне *#06#')
        # Планируем задачу на отправку уведомления о таймауте через 10 секунд
        job = job_queue.run_once(send_timeout_message, 10, context=(chat.id, context))
        context.user_data['timeout_job'] = job  # Сохраняем задачу в user_data
        context.user_data['current_state'] = ASKING_IMEI  # Сохраняем текущее состояние
        logger.info("Переход в состояние ASKING_IMEI")
        return ASKING_IMEI
    except Exception as e:
        logger.error(f"Ошибка в ask_imei: {e}")
        return ConversationHandler.END


# Обработка введенного IMEI
def handle_imei(update, context):
    try:
        user_input = update.message.text.strip()
        # Отменяем задачу таймаута, если она существует
        timeout_job = context.user_data.get('timeout_job')
        if timeout_job:
            try:
                timeout_job.schedule_removal()  # Удаляем задачу из очереди
            except Exception:
                pass  # Если задача уже выполнена или удалена, игнорируем ошибку
            del context.user_data['timeout_job']

        if not is_valid_imei(user_input):
            context.bot.send_message(update.effective_chat.id, "Неверный IMEI. Пожалуйста, попробуйте снова.")
            logger.info("Продолжаем ожидание корректного IMEI")
            return ASKING_IMEI  # Продолжаем ожидание корректного IMEI

        response = requests.post(URL_IMEI, json={
            "imei": user_input,
            "token": IMEI_TOKEN
        })
        if response.status_code == 200:
            data = response.json()
            reply = (
                f"Информация о IMEI:\n"
                f"Статус: {data.get('status', 'Неизвестно')}\n"
                f"Модель: {data.get('model', 'Неизвестно')}\n"
                f"Производитель: {data.get('manufacturer', 'Неизвестно')}\n"
                f"Серийный номер: {data.get('serial', 'Неизвестно')}"
            )
            context.bot.send_message(update.effective_chat.id, reply)
        else:
            context.bot.send_message(update.effective_chat.id, "Ошибка при получении информации о IMEI. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка в handle_imei: {e}")
        context.bot.send_message(update.effective_chat.id, f"Произошла ошибка: {str(e)}")
    finally:
        # Очищаем данные пользователя и завершаем диалог
        context.user_data.clear()
        logger.info("Завершение диалога (IMEI)")
        return ConversationHandler.END


# Запрос города у пользователя
def ask_city(update, context):
    chat = update.effective_chat
    try:
        context.bot.send_message(chat.id, 'Какой город вас интересует?')
        # Планируем задачу на отправку уведомления о таймауте через 10 секунд
        job = job_queue.run_once(send_timeout_message, 10, context=(chat.id, context))
        context.user_data['timeout_job'] = job  # Сохраняем задачу в user_data
        context.user_data['current_state'] = ASKING_CITY  # Сохраняем текущее состояние
        logger.info("Переход в состояние ASKING_CITY")
        return ASKING_CITY
    except Exception as e:
        logger.error(f"Ошибка в ask_city: {e}")
        return ConversationHandler.END


# Обработка введенного города
def handle_city(update, context):
    try:
        city_name = update.message.text
        # Отменяем задачу таймаута, если она существует
        timeout_job = context.user_data.get('timeout_job')
        if timeout_job:
            try:
                timeout_job.schedule_removal()  # Удаляем задачу из очереди
            except Exception:
                pass  # Если задача уже выполнена или удалена, игнорируем ошибку
            del context.user_data['timeout_job']

        weather_info = get_weather(city_name)
        if 'error' in weather_info:
            context.bot.send_message(update.effective_chat.id, weather_info['error'])
            logger.info("Продолжаем ожидание корректного города")
            return ASKING_CITY  # Продолжаем ожидание корректного города
        else:
            temperature = weather_info['temperature']
            description = weather_info['description']
            wind_speed = weather_info['wind_speed']
            context.bot.send_message(
                update.effective_chat.id,
                f'Погода в {city_name}:\nТемпература: {temperature}°C\nОписание: {description}\nСкорость ветра: {wind_speed} м/с'
            )
    except Exception as e:
        logger.error(f"Ошибка в handle_city: {e}")
        context.bot.send_message(update.effective_chat.id, f"Произошла ошибка: {str(e)}")
    finally:
        # Очищаем данные пользователя и завершаем диалог
        context.user_data.clear()
        logger.info("Завершение диалога (город)")
        return ConversationHandler.END


# Функция для отправки уведомления о таймауте
def send_timeout_message(context):
    try:
        chat_id, ctx = context.job.context  # Получаем chat_id и контекст
        ctx.bot.send_message(chat_id, "Время ожидания истекло. Вы можете продолжить взаимодействие с ботом.")
        # Очищаем данные пользователя и завершаем диалог
        ctx.user_data.clear()
        logger.info("Завершение диалога по таймауту")
    except Exception as e:
        logger.error(f"Ошибка в send_timeout_message: {e}")


# Получение данных о погоде
def get_weather(city_name):
    try:
        url = URL_WEATHER.format(city_name=city_name.replace(' ', '+'), api_key=KEY_WEATHER)
        response = requests.get(url)
        if response.status_code == 200:
            weather_data = response.json()
            temperature_kelvin = weather_data['main']['temp']
            temperature_celsius = temperature_kelvin - 273.15
            weather_description = weather_data['weather'][0]['description']
            wind_speed = weather_data['wind']['speed']
            return {
                'temperature': round(temperature_celsius, 2),
                'description': weather_description,
                'wind_speed': wind_speed
            }
        else:
            return {'error': 'Не удалось получить данные о погоде'}
    except Exception as e:
        logger.error(f"Ошибка в get_weather: {e}")
        return {'error': f'Ошибка при получении данных о погоде: {str(e)}'}


# Получение новой цитаты
def get_new_quote():
    try:
        response = requests.get(URL_QUOTE).json()
        quote_text = response.get('quoteText')
        quote_author = response.get('quoteAuthor')
        if quote_author:
            return f'"{quote_text}" - {quote_author}'
        else:
            return f'"{quote_text}" - Автор неизвестен'
    except Exception as e:
        logger.error(f"Ошибка в get_new_quote: {e}")
        return f'Ошибка при получении цитаты: {str(e)}'


# Получение нового изображения кота
def get_new_image():
    try:
        response = requests.get(URL_CAT)
        if response.status_code == 200:
            data = response.json()
            return data[0].get('url')
        else:
            return None
    except Exception as e:
        logger.error(f"Ошибка в get_new_image: {e}")
        return None


def new_cat(update, context):
    try:
        cat_image_url = get_new_image()
        if cat_image_url:
            context.bot.send_photo(update.effective_chat.id, cat_image_url)
        else:
            context.bot.send_message(update.effective_chat.id, "Не удалось получить изображение кота.")
    except Exception as e:
        logger.error(f"Ошибка в new_cat: {e}")
        context.bot.send_message(update.effective_chat.id, f"Произошла ошибка: {str(e)}")


def new_quote(update, context):
    try:
        quote = get_new_quote()
        context.bot.send_message(update.effective_chat.id, quote)
    except Exception as e:
        logger.error(f"Ошибка в new_quote: {e}")
        context.bot.send_message(update.effective_chat.id, f"Произошла ошибка: {str(e)}")


def wake_up(update, context):
    try:
        chat = update.effective_chat
        name = update.message.chat.first_name
        context.bot.send_message(
            chat_id=chat.id,
            text=f'Привет, {name}. Посмотри, какого котика я тебе нашёл',
            reply_markup=create_keyboard()  # Добавляем клавиатуру
        )
        context.bot.send_photo(chat.id, get_new_image())
        context.bot.send_message(chat.id, get_new_quote())
    except Exception as e:
        logger.error(f"Ошибка в wake_up: {e}")
        context.bot.send_message(update.effective_chat.id, f"Произошла ошибка: {str(e)}")


# Обработчик кнопок
def button_handler(update, context):
    try:
        text = update.message.text

        # Проверяем текущее состояние диалога
        current_state = context.user_data.get('current_state')
        if current_state:
            logger.info(f"Завершаем текущий диалог (состояние: {current_state})")
            context.bot.send_message(update.effective_chat.id, "Текущий диалог завершён. Выберите новое действие.")
            context.user_data.clear()  # Очищаем данные пользователя
            return ConversationHandler.END

        # Обработка кнопок
        if text == 'Покажи котика':
            new_cat(update, context)
        elif text == 'Хочу цитату':
            new_quote(update, context)
        elif text == 'Покажи погоду':
            return ask_city(update, context)
        elif text == 'Проверить IMEI':
            return ask_imei(update, context)
        elif text == 'Начать':  # Обработка кнопки "Начать"
            wake_up(update, context)
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        context.bot.send_message(update.effective_chat.id, f"Произошла ошибка: {str(e)}")
        return ConversationHandler.END


# Настройка ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[MessageHandler(Filters.text & ~Filters.command, button_handler)],
    states={
        ASKING_CITY: [MessageHandler(Filters.text & ~Filters.command, handle_city)],
        ASKING_IMEI: [MessageHandler(Filters.text & ~Filters.command, handle_imei)],
    },
    fallbacks=[]
)

# Добавление обработчиков
updater.dispatcher.add_handler(CommandHandler('start', wake_up))
updater.dispatcher.add_handler(conv_handler)

# Запуск бота
try:
    updater.start_polling()
    updater.idle()
except Exception as e:
    logger.error(f"Критическая ошибка при запуске бота: {e}")