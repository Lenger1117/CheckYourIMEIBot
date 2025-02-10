from telegram.ext import Updater, Filters, MessageHandler, CommandHandler, ConversationHandler
from telegram import ReplyKeyboardMarkup
import requests
import os
from dotenv import load_dotenv


load_dotenv()
BOT_TOKEN = os.getenv('B_TOKEN')
KEY_WEATHER = os.getenv('W_KEY')
updater = Updater(token=BOT_TOKEN)
URL_CAT = 'https://api.thecatapi.com/v1/images/search'
URL_QUOTE = 'http://api.forismatic.com/api/1.0/?method=getQuote&format=json&lang=ru'
URL_WEATHER = 'https://api.openweathermap.org/data/2.5/weather?q={city_name}&APPID={api_key}&lang=ru'

ASKING_CITY = range(1)

def get_weather(city_name):
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

def ask_city(update, context):
    chat = update.effective_chat
    context.bot.send_message(chat.id, 'Какой город вас интересует?')
    return ASKING_CITY

def handle_city(update, context):
    city_name = update.message.text
    weather_info = get_weather(city_name)

    if 'error' in weather_info:
        context.bot.send_message(update.effective_chat.id, weather_info['error'])
    else:
        temperature = weather_info['temperature']
        description = weather_info['description']
        wind_speed = weather_info['wind_speed']
        context.bot.send_message(
            update.effective_chat.id,
            f'Погода в {city_name}:\nТемпература: {temperature}°C\nОписание: {description}\nСкорость ветра: {wind_speed} м/с'
        )
    
    return ConversationHandler.END

def get_new_quote():
    response = requests.get(URL_QUOTE).json()
    quote_text = response.get('quoteText')
    quote_author = response.get('quoteAuthor')
    if quote_author:
        return f'"{quote_text}" - {quote_author}'
    else:
        return f'"{quote_text}" - Автор неизвестен'

def new_quote(update, context):
    chat = update.effective_chat
    context.bot.send_message(chat.id, get_new_quote())

def get_new_image():
    response = requests.get(URL_CAT).json()
    random_cat = response[0].get('url')
    return random_cat

def new_cat(update, context):
    chat = update.effective_chat
    cat_image_url = get_new_image()
    if cat_image_url:
        context.bot.send_photo(chat.id, cat_image_url)
    else:
        context.bot.send_message(chat.id, "Не удалось получить изображение кота.")

def wake_up(update, context):
    chat = update.effective_chat
    name = update.message.chat.first_name
    buttons = ReplyKeyboardMarkup([
                ['Покажи котика', 'Хочу цитату', 'Покажи погоду']], resize_keyboard=True)
    context.bot.send_message(
        chat_id=chat.id,
        text='Привет, {}. Посмотри, какого котика я тебе нашёл'.format(name),
        reply_markup=buttons
    )
    context.bot.send_photo(chat.id, get_new_image())
    context.bot.send_message(chat.id, get_new_quote())

def button_handler(update, context):
    text = update.message.text
    if text == 'Покажи котика':
        new_cat(update, context)
    elif text == 'Хочу цитату':
        new_quote(update, context)
    elif text == 'Покажи погоду':
        return ask_city(update, context)

# Настройка ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[MessageHandler(Filters.text & ~Filters.command, button_handler)],
    states={
        ASKING_CITY: [MessageHandler(Filters.text & ~Filters.command, handle_city)],
    },
    fallbacks=[]
)

updater.dispatcher.add_handler(CommandHandler('start', wake_up))
updater.dispatcher.add_handler(conv_handler)

updater.start_polling()
updater.idle()
