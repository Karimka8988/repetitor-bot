import logging
import os
import aiohttp
import io
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, PreCheckoutQueryHandler, MessageHandler, filters
from course_content import COURSE_CONTENT
from urllib.parse import urlencode
import asyncio
import time
from yoomoney import Client, Quickpay
import hashlib
import telegram.error
import shutil
from pathlib import Path

# Константы
BACKUP_DIR = 'backups'
USERS_DATA_FILE = 'users_data.json'
COURSE_PRICE = 1900
YOOMONEY_WALLET = "4100117110526370"
ADMIN_USER_ID = 7762388025

# Состояния разговора
CHOOSING_LEVEL, PAYMENT, SHOWING_LESSON, WAITING_HOMEWORK, CHOOSING_SUBSCRIPTION = range(5)

# Настройки ЮMoney
LEVELS = {
    'A1': {'name': 'Beginner - уровень выживания', 'price': COURSE_PRICE},
    'A2': {'name': 'Elementary - предпороговый уровень', 'price': COURSE_PRICE},
    'B1': {'name': 'Intermediate - пороговый уровень', 'price': COURSE_PRICE},
    'B2': {'name': 'Upper-Intermediate - пороговый продвинутый уровень', 'price': COURSE_PRICE},
    'C1': {'name': 'Advanced - уровень профессионального владения', 'price': COURSE_PRICE},
    'C2': {'name': 'Proficiency - уровень владения в совершенстве', 'price': COURSE_PRICE}
}

# Загрузка переменных окружения
try:
    load_dotenv()
except Exception as e:
    print(f"Ошибка при загрузке .env файла: {e}")

# Создаем директории для логов и бэкапов
log_dir = Path('logs')
backup_dir = Path(BACKUP_DIR)
try:
    log_dir.mkdir(exist_ok=True)
    backup_dir.mkdir(exist_ok=True)
except Exception as e:
    print(f"Ошибка при создании директорий: {e}")

# Настройка логирования
try:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.FileHandler(log_dir / 'bot.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
except Exception as e:
    print(f"Ошибка при настройке логирования: {e}")

logger = logging.getLogger(__name__)

# Проверка необходимых переменных окружения
REQUIRED_ENV_VARS = {
    'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
    'VOICERSS_API_KEY': os.getenv('VOICERSS_API_KEY')
}

for var_name, var_value in REQUIRED_ENV_VARS.items():
    if not var_value:
        logger.error(f"❌ Отсутствует обязательная переменная окружения: {var_name}")
        raise EnvironmentError(f"Отсутствует {var_name}")

def backup_users_data():
    """Создает резервную копию файла с данными пользователей"""
    try:
        # Создаем директорию для резервных копий, если её нет
        Path(BACKUP_DIR).mkdir(exist_ok=True)
        
        if not os.path.exists(USERS_DATA_FILE):
            logger.warning("⚠️ Нет файла для создания резервной копии")
            return False
            
        # Формируем имя файла резервной копии с текущей датой и временем
        backup_file = f"{BACKUP_DIR}/users_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Копируем файл
        shutil.copy2(USERS_DATA_FILE, backup_file)
        logger.info(f"✅ Создана резервная копия данных пользователей: {backup_file}")
        
        # Удаляем старые резервные копии (оставляем только последние 5)
        try:
            backup_files = sorted(Path(BACKUP_DIR).glob('users_data_*.json'))
            if len(backup_files) > 5:
                for old_file in backup_files[:-5]:
                    old_file.unlink()
                    logger.info(f"🗑️ Удалена старая резервная копия: {old_file}")
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке старых резервных копий: {e}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при создании резервной копии: {e}")
        return False

def load_users_data():
    """Загрузка данных пользователей из файла"""
    try:
        if not os.path.exists(USERS_DATA_FILE):
            logger.warning("⚠️ Файл данных пользователей не найден, создаем новый")
            return {}
            
        with open(USERS_DATA_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if not isinstance(data, dict):
                logger.error("❌ Некорректный формат данных пользователей")
                return {}
            return data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка при чтении JSON: {e}")
        # Пробуем восстановить из последней резервной копии
        try:
            backup_files = sorted(Path(BACKUP_DIR).glob('users_data_*.json'))
            if backup_files:
                latest_backup = backup_files[-1]
                with open(latest_backup, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    if not isinstance(data, dict):
                        raise ValueError("Некорректный формат данных в резервной копии")
                logger.info(f"✅ Данные восстановлены из резервной копии: {latest_backup}")
                return data
            else:
                logger.warning("⚠️ Резервные копии не найдены")
                return {}
        except Exception as backup_error:
            logger.error(f"❌ Ошибка при восстановлении из резервной копии: {backup_error}")
            return {}
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке данных пользователей: {e}")
        return {}

def save_users_data(data):
    """Сохранение данных пользователей в файл"""
    if not isinstance(data, dict):
        logger.error("❌ Попытка сохранить некорректные данные пользователей")
        return False
        
    try:
        # Создаем резервную копию перед сохранением
        backup_users_data()
        
        # Сохраняем во временный файл
        temp_file = f"{USERS_DATA_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
            
        # Если сохранение прошло успешно, заменяем основной файл
        os.replace(temp_file, USERS_DATA_FILE)
        logger.info("✅ Данные пользователей успешно сохранены")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении данных пользователей: {e}")
        # Удаляем временный файл в случае ошибки
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False

def get_user_data(user_id):
    """Получение данных пользователя"""
    users_data = load_users_data()
    return users_data.get(str(user_id), {})

def update_user_data(user_id, data):
    """Обновление данных пользователя"""
    users_data = load_users_data()
    users_data[str(user_id)] = data
    save_users_data(users_data)

def can_access_next_lesson(user_id):
    """Проверка возможности доступа к следующему уроку"""
    user_data = get_user_data(user_id)
    if not user_data:
        return True
    
    last_lesson_date = datetime.fromisoformat(user_data.get('last_lesson_date', '2000-01-01'))
    current_date = datetime.now()
    
    # Проверяем, прошли ли сутки с последнего урока
    return (current_date - last_lesson_date).days >= 1

async def get_pronunciation_audio(text: str) -> bytes:
    """Получение аудио с произношением от Text-to-Speech сервиса"""
    if not text or not isinstance(text, str):
        logger.error("❌ Некорректный текст для произношения")
        return None
        
    if not REQUIRED_ENV_VARS['VOICERSS_API_KEY']:
        logger.error("❌ API ключ для Text-to-Speech сервиса не установлен")
        return None
        
    try:
        params = {
            'key': REQUIRED_ENV_VARS['VOICERSS_API_KEY'],
            'hl': 'en-us',
            'v': 'Mary',
            'src': text,
            'c': 'MP3',
            'f': '44khz_16bit_stereo',
            'r': '0',
            'b64': 'false'
        }
        
        url = 'https://api.voicerss.org/'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params) as response:
                if response.status == 200:
                    audio_content = await response.read()
                    content_type = response.headers.get('Content-Type', '')
                    
                    if len(audio_content) > 1000 and 'audio' in content_type:
                        logger.info(f"✅ Аудио успешно получено, размер: {len(audio_content)} байт")
                        return audio_content
                    else:
                        error_text = audio_content.decode('utf-8', errors='ignore')
                        logger.error(f"❌ Ошибка в ответе API: {error_text}")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка при получении аудио: {response.status} - {error_text}")
                    return None
    except aiohttp.ClientError as e:
        logger.error(f"❌ Ошибка сети при получении аудио: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при получении аудио: {str(e)}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом"""
    user_id = update.effective_user.id
    logger.info(f"🚀 Пользователь {user_id} запустил бота")
    user_data = get_user_data(user_id)
    
    # Если пользователь уже начал курс, показываем текущий урок
    if user_data and user_data.get('level'):
        context.user_data.update(user_data)
        message = f"""
🎓 *Добро пожаловать обратно в English Learning Bot!*

📊 *Ваш текущий прогресс:*
━━━━━━━━━━━━━━━━━━━━━
🎯 Уровень: {user_data['level']} {get_level_emoji(user_data['level'])}
📅 День: {user_data['day']} из 14
⏰ Последний урок: {user_data['last_lesson_date']}
━━━━━━━━━━━━━━━━━━━━━

⚠️ _План обучения нельзя изменить до завершения текущего курса._

🕒 *Выберите удобное время для урока:*
"""
        keyboard = [
            [
                InlineKeyboardButton("🌅 Утренний урок", callback_data="time:morning"),
                InlineKeyboardButton("☀️ Дневной урок", callback_data="time:afternoon"),
            ],
            [
                InlineKeyboardButton("🌙 Вечерний урок", callback_data="time:evening")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        # Сохраняем текущий день и время в контексте
        context.user_data['current_day'] = user_data['day']
        context.user_data['time_of_day'] = user_data.get('time_of_day', 'morning')
        
        return SHOWING_LESSON
    
    # Для новых пользователей показываем приветствие
    welcome_message = """
🌟 *Добро пожаловать в English Learning Bot!* 🌟
━━━━━━━━━━━━━━━━━━━━━

📚 Ваш персональный помощник в изучении английского языка! 

*Что вас ждёт:*
🎯 14 дней интенсивного обучения
📝 Ежедневные уроки и практика
📖 Изучение новых слов и грамматики
🎧 Аудио произношение от носителей языка
🎮 Интерактивные задания

━━━━━━━━━━━━━━━━━━━━━
⚠️ *ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ:*
После выбора уровня обучения его нельзя будет изменить до завершения 14-дневного курса. 

💫 *Готовы начать увлекательное путешествие в мир английского языка?*
"""
    keyboard = [
        [InlineKeyboardButton("✨ Да, хочу выбрать уровень!", callback_data="ready_to_choose")],
        [InlineKeyboardButton("🤔 Нет, мне нужно подумать", callback_data="not_ready")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CHOOSING_LEVEL

def get_level_emoji(level: str) -> str:
    """Возвращает эмодзи для каждого уровня"""
    emoji_map = {
        'A1': '🌱',  # Начинающий
        'A2': '🌿',  # Элементарный
        'B1': '🌺',  # Средний
        'B2': '🌸',  # Выше среднего
        'C1': '🌳',  # Продвинутый
        'C2': '🎓'   # Профессиональный
    }
    return emoji_map.get(level, '')

async def handle_ready_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка готовности к выбору уровня"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "not_ready":
        message = """
🤔 *Не торопитесь с выбором!*
━━━━━━━━━━━━━━━━━━━━━

💡 *Рекомендации по выбору уровня:*

🌱 *A1 - Beginner*
• Только начинаете изучать язык
• Знаете алфавит и базовые слова
• Хотите научиться представляться

🌿 *A2 - Elementary*
• Знаете базовые фразы
• Понимаете простые тексты
• Можете рассказать о себе

🌺 *B1 - Intermediate*
• Общаетесь на бытовые темы
• Понимаете медленную речь
• Читаете простые статьи

🌸 *B2 - Upper-Intermediate*
• Свободно говорите на многие темы
• Смотрите фильмы в оригинале
• Читаете книги на английском

🌳 *C1 - Advanced*
• Владеете языком почти как носитель
• Понимаете сложные тексты
• Говорите бегло и спонтанно

🎓 *C2 - Proficiency*
• Профессиональное владение
• Понимаете любую речь
• Пишете сложные тексты

━━━━━━━━━━━━━━━━━━━━━
✨ Когда будете готовы начать обучение,
просто нажмите /start
"""
        await query.edit_message_text(
            message,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Показываем выбор уровней
    message = """
📚 *Выберите ваш уровень английского*
━━━━━━━━━━━━━━━━━━━━━

✨ *Каждый уровень включает:*
📅 14 дней интенсивного обучения
🎯 3 урока каждый день
🎧 Аудио от носителей языка
📝 Практические задания
📊 Отслеживание прогресса

━━━━━━━━━━━━━━━━━━━━━
⚠️ *ВАЖНО:* 
• Уровень нельзя изменить до конца курса
• Выберите подходящий для вас уровень
• Будьте готовы заниматься 14 дней

*Доступные уровни:*
"""
    keyboard = []
    for level, info in LEVELS.items():
        keyboard.append([InlineKeyboardButton(
            f"{get_level_emoji(level)} {level} - {info['name']}", 
            callback_data=f"confirm_{level}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CHOOSING_LEVEL

async def level_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора уровня"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('confirm_'):
        return CHOOSING_LEVEL
    
    level = query.data.split('_')[1]  # confirm_A1 -> A1
    
    # Проверяем, существует ли выбранный уровень в COURSE_CONTENT
    if level not in COURSE_CONTENT:
        await query.edit_message_text(
            f"""
❌ *Ошибка: уровень недоступен*
━━━━━━━━━━━━━━━━━━━━━

Уровень {level} временно недоступен.
Пожалуйста, выберите другой уровень.

🔄 Нажмите /start для выбора уровня
""",
            parse_mode='Markdown'
        )
        return CHOOSING_LEVEL
    
    context.user_data['temp_level'] = level  # Временно сохраняем выбранный уровень
    
    # Показываем информацию об оплате
    payment_message = f"""
✨ *Отличный выбор - уровень {level}!*
━━━━━━━━━━━━━━━━━━━━━

📚 *Ваш курс включает:*
• Полный доступ на 14 дней
• Все материалы и аудио уроки
• Проверка домашних заданий
• Отслеживание прогресса
• Поддержка преподавателя

💰 *Стоимость:* {LEVELS[level]['price']} руб.

━━━━━━━━━━━━━━━━━━━━━
💫 Для начала обучения необходимо оплатить курс
"""
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить курс", callback_data=f"pay_{level}")],
        [InlineKeyboardButton("🔙 Выбрать другой уровень", callback_data="ready_to_choose")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        payment_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return PAYMENT

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на оплату"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"💳 Пользователь {user_id} инициировал оплату")
    
    if not query.data.startswith('pay_'):
        return PAYMENT
    
    level = query.data.split('_')[1]
    price = LEVELS[level]['price']
    
    # Создаем уникальный идентификатор платежа
    payment_id = f"eng_course_{level}_{user_id}_{int(datetime.now().timestamp())}"
    context.user_data['payment_id'] = payment_id
    logger.info(f"💰 Создан платеж {payment_id} для пользователя {user_id}")
    
    # Формируем URL для формы оплаты
    params = {
        'receiver': YOOMONEY_WALLET,
        'quickpay-form': 'shop',
        'targets': f'Оплата курса английского {level}',
        'paymentType': 'AC',
        'sum': price,
        'label': payment_id,
        'successURL': 'https://webhook.site/e5a7fe2c-4d55-4a15-bb11-9459fb2e4f03',
        'need-fio': 'false',
        'need-email': 'false',
        'need-phone': 'false',
        'need-address': 'false'
    }
    
    payment_url = f"https://yoomoney.ru/quickpay/confirm?{urlencode(params)}"
    
    yoomoney_message = f"""
💳 *Оплата курса уровня {level}*
━━━━━━━━━━━━━━━━━━━━━

💰 *Стоимость:* {price} руб.

✨ *Что включено:*
📚 14 дней интенсивного обучения
🎯 42 интерактивных урока
🎧 Аудио материалы от носителей
📝 Проверка домашних заданий
👨‍🏫 Поддержка преподавателя

📱 *Как оплатить:*
1️⃣ Нажмите кнопку "Оплатить картой"
2️⃣ Введите данные банковской карты
3️⃣ Подтвердите оплату
4️⃣ Напишите администратору @renatblizkiy

━━━━━━━━━━━━━━━━━━━━━
⚠️ *Важная информация:*
• Оплата проходит через защищенное соединение
• Доступ откроется после подтверждения оплаты
• Сохраните ID платежа: `{payment_id}`
"""
    
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить картой", url=payment_url)],
        [InlineKeyboardButton("✍️ Написать администратору", url="https://t.me/renatblizkiy")],
        [InlineKeyboardButton("🔙 Вернуться назад", callback_data=f"confirm_{level}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        yoomoney_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return PAYMENT

async def show_daily_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает урок на выбранное время дня"""
    query = update.callback_query
    selected_time = "morning"  # значение по умолчанию
    
    if query and query.data:
        if ":" in query.data:
            selected_time = query.data.split(":")[1]
        elif "_" in query.data:
            selected_time = query.data.split("_")[1]
            
        # Исправляем некорректное время дня
        if selected_time == "day":
            selected_time = "afternoon"
            
        await query.answer()
    
    # Получаем текущий день и уровень пользователя
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data or 'level' not in user_data:
        message = """
❌ *Ошибка:* Уровень обучения не выбран

🔄 Используйте /start для начала обучения
"""
        if query:
            await query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        return CHOOSING_LEVEL
    
    # Обновляем данные в контексте
    context.user_data.update(user_data)
    current_day = int(user_data.get('current_day', 1))
    user_level = user_data['level']
    
    try:
        # Удаляем предыдущие голосовые сообщения
        try:
            # Получаем последние сообщения
            if 'last_voice_message_id' in context.user_data:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['last_voice_message_id']
                    )
                except Exception as e:
                    logger.error(f"Ошибка при удалении предыдущего голосового сообщения: {e}")
        except Exception as e:
            logger.error(f"Ошибка при удалении голосовых сообщений: {e}")
        
        # Преобразуем current_day в int для доступа к словарю
        current_lesson = COURSE_CONTENT[user_level][int(current_day)][selected_time]
        logger.info(f"✅ Загружен урок: уровень {user_level}, день {current_day}, время {selected_time}")
        
        # Обновляем время дня в данных пользователя
        user_data['time_of_day'] = selected_time
        update_user_data(user_id, user_data)
        context.user_data['time_of_day'] = selected_time
        
        # Формируем сообщение с уроком
        time_emoji = {"morning": "🌅", "afternoon": "☀️", "evening": "🌙"}
        time_names = {"morning": "Утренний", "afternoon": "Дневной", "evening": "Вечерний"}
        
        message = f"""
⚠️ *У вас уже есть активный план обучения!*

*Ваш текущий план:*
• Уровень: {user_level} {get_level_emoji(user_level)}
• День: {current_day} из 14 📅
• Последний урок: {user_data.get('last_lesson_date')} 📆

План обучения нельзя изменить до завершения текущего курса

━━━━━━━━━━━━━━━━━━━━━

📚 День {current_day} из 14
└─ Уровень: {user_level} {get_level_emoji(user_level)}
└─ {time_emoji.get(selected_time, '')} {time_names.get(selected_time, '')} урок

🎯 Тема:
└─ {current_lesson.get('topic', '')}

📝 Новые слова:
"""
        # Добавляем слова с транскрипцией и переводом
        for i, word_data in enumerate(current_lesson.get('vocabulary', []), 1):
            if isinstance(word_data, dict):
                word = word_data.get('word', '')
                transcription = word_data.get('transcription', '')
                translation = word_data.get('translation', '')
                message += f"└─ {i}. {word} [{transcription}] - {translation}\n"
            else:
                # Для обратной совместимости со старым форматом
                message += f"└─ {i}. {word_data}\n"

        message += f"""
🔤 Грамматика:
└─ {current_lesson.get('grammar', '')}

✍️ Практическое задание:
└─ {current_lesson.get('practice', '')}

"""
        if 'pronunciation' in current_lesson:
            message += f"""
🎵 Прослушайте правильное произношение
└─ {time_emoji.get(selected_time, '')} Урок для периода: {time_names.get(selected_time, '')} урок
└─ Повторяйте вслух для лучшего запоминания!
"""
        
        message += "\n⏰ Выберите время дня или перейдите к следующему уроку"
        
        # Обновляем или отправляем сообщение
        if query:
            await query.edit_message_text(
                text=message,
                parse_mode='Markdown',
                reply_markup=get_lesson_keyboard(selected_time, current_day)
            )
        else:
            await update.message.reply_text(
                text=message,
                parse_mode='Markdown',
                reply_markup=get_lesson_keyboard(selected_time, current_day)
            )
        
        # Если есть аудио для произношения, получаем и отправляем его
        if 'pronunciation' in current_lesson and 'text' in current_lesson['pronunciation']:
            try:
                audio_data = await get_pronunciation_audio(current_lesson['pronunciation']['text'])
                if audio_data:
                    caption = f"""
🎵 Прослушайте правильное произношение
└─ {time_emoji.get(selected_time, '')} Урок для периода: {time_names.get(selected_time, '')} урок
└─ Повторяйте вслух для лучшего запоминания!"""
                    sent_message = await context.bot.send_voice(
                        chat_id=update.effective_chat.id,
                        voice=io.BytesIO(audio_data),
                        caption=caption
                    )
                    # Сохраняем ID отправленного голосового сообщения
                    context.user_data['last_voice_message_id'] = sent_message.message_id
            except Exception as e:
                logger.error(f"Ошибка при отправке аудио: {str(e)}")
                
    except (KeyError, TypeError) as e:
        logger.error(f"❌ Ошибка при получении урока: {str(e)}, level={user_level}, day={current_day}, time={selected_time}")
        error_message = f"""
⚠️ *У вас уже есть активный план обучения!*

*Ваш текущий план:*
• Уровень: {user_level} {get_level_emoji(user_level)}
• День: {current_day} из 14 📅
• Последний урок: {user_data.get('last_lesson_date')} 📆

План обучения нельзя изменить до завершения текущего курса
"""
        if query:
            await query.edit_message_text(error_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(error_message, parse_mode='Markdown')
            
    return SHOWING_LESSON

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора времени дня"""
    query = update.callback_query
    if not query:
        return SHOWING_LESSON
    await query.answer()
    
    try:
        # Получаем выбранное время дня из callback_data
        if ":" in query.data:
            time_of_day = query.data.split(":")[1]
        else:
            time_of_day = query.data.split("_")[1]
        
        # Проверяем корректность времени дня
        if time_of_day not in ["morning", "afternoon", "evening"]:
            logger.error(f"❌ Некорректное время дня: {time_of_day}")
            return SHOWING_LESSON
        
        # Обновляем время дня в данных пользователя
        context.user_data['time_of_day'] = time_of_day
        
        await show_daily_lesson(update, context)
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке выбора времени: {e}")
        return SHOWING_LESSON
    
    return SHOWING_LESSON

async def next_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к следующему уроку"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not can_access_next_lesson(user_id):
        # Получаем время до следующего урока
        user_data = get_user_data(user_id)
        last_lesson_date = datetime.fromisoformat(user_data.get('last_lesson_date', '2000-01-01'))
        next_lesson_time = last_lesson_date + timedelta(days=1)
        time_left = next_lesson_time - datetime.now()
        hours_left = int(time_left.total_seconds() / 3600)
        minutes_left = int((time_left.total_seconds() % 3600) / 60)
        
        message = f"""
⏳ *Следующий урок пока недоступен*
━━━━━━━━━━━━━━━━━━━━━

⌛️ *До следующего урока осталось:*
🕐 {hours_left} часов и {minutes_left} минут

💡 *Рекомендации:*
• Повторите материал текущего урока
• Выполните домашнее задание
• Практикуйте новые слова
• Слушайте аудио материалы

━━━━━━━━━━━━━━━━━━━━━
✨ Возвращайтесь завтра для продолжения обучения!
"""
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к текущему уроку", callback_data="return_current")
            ]])
        )
        return SHOWING_LESSON
    
    # Обновляем день и дату последнего урока
    current_day = int(context.user_data.get('day', 1))
    context.user_data['day'] = current_day + 1
    
    if context.user_data['day'] > 14:
        completion_message = """
🎉 *Поздравляем с завершением курса!* 🎉
━━━━━━━━━━━━━━━━━━━━━

✨ Вы успешно прошли 14-дневный курс английского языка! 

📊 *Ваши достижения:*
📚 Изучено множество новых слов
📝 Освоены важные грамматические темы
🎧 Улучшено произношение
💭 Получена практика в разговорной речи

🌟 *Что дальше?*
• Продолжайте практиковать язык
• Смотрите фильмы на английском
• Читайте книги и статьи
• Общайтесь с носителями языка

━━━━━━━━━━━━━━━━━━━━━
🔄 Для начала нового курса используйте /start

_Желаем дальнейших успехов в изучении английского языка!_ 🚀
"""
        # Очищаем данные пользователя
        update_user_data(user_id, {})
        
        await query.edit_message_text(
            completion_message,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Обновляем данные пользователя
    user_data = context.user_data.copy()
    user_data['last_lesson_date'] = datetime.now().isoformat()
    update_user_data(user_id, user_data)
    
    # Обновляем current_day в контексте для правильного отображения урока
    context.user_data['current_day'] = context.user_data['day']
    
    await show_daily_lesson(update, context)
    return SHOWING_LESSON

async def return_to_current_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к текущему уроку"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    # Получаем текущее время дня из данных пользователя
    time_of_day = user_data.get('time_of_day', 'morning')
    
    # Обновляем callback_data для правильного времени дня
    context.user_data['callback_query'] = f"time:{time_of_day}"
    
    await show_daily_lesson(update, context)
    return SHOWING_LESSON

async def activate_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация доступа к курсу администратором"""
    # Проверяем, является ли пользователь администратором
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text(
            "❌ У вас нет прав для выполнения этой команды.",
            parse_mode='Markdown'
        )
        return

    # Проверяем формат команды
    try:
        # Формат: /activate USER_ID LEVEL
        _, user_id, level = update.message.text.split()
        user_id = int(user_id)
    except ValueError:
        await update.message.reply_text(
            "❌ *Неверный формат команды*\nИспользуйте: `/activate USER_ID LEVEL`\nПример: `/activate 123456789 A1`",
            parse_mode='Markdown'
        )
        return

    # Проверяем корректность уровня
    if level not in LEVELS:
        await update.message.reply_text(
            f"❌ *Неверный уровень*\nДоступные уровни: {', '.join(LEVELS.keys())}",
            parse_mode='Markdown'
        )
        return

    # Активируем доступ к курсу
    user_data = {
        'level': level,
        'current_day': 1,
        'day': 1,
        'max_day': 1,  # Добавляем отслеживание максимального дня
        'last_lesson_date': (datetime.now() - timedelta(days=1)).isoformat(),  # Позволяет начать обучение сразу
        'time_of_day': 'morning'
    }
    update_user_data(user_id, user_data)

    # Отправляем сообщение администратору
    await update.message.reply_text(
        f"""
✅ *Доступ успешно активирован*

*Детали:*
• ID пользователя: `{user_id}`
• Уровень курса: {level} {get_level_emoji(level)}
• Начальный день: 1
• Доступ к урокам: Активирован

Пользователь может начать обучение, отправив команду /start
""",
        parse_mode='Markdown'
    )

    # Отправляем сообщение пользователю
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"""
🎉 *Поздравляем! Ваш курс успешно активирован!* 🎉

*Детали вашего курса:*
• Уровень: {level} {get_level_emoji(level)}
• Длительность: 14 дней
• Формат: 3 урока каждый день (утро/день/вечер)
• Доступ: Полный доступ ко всем материалам

*Что дальше?*
1. Отправьте команду /start
2. Начните обучение с первого урока
3. Занимайтесь в удобное для вас время

*Особенности курса:*
• Интерактивные уроки
• Аудио с произношением
• Практические задания
• Грамматика и новые слова

Желаем успехов в изучении английского языка! 📚✨
""",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ *Предупреждение:* Не удалось отправить уведомление пользователю.\nВозможно, пользователь не начал диалог с ботом.",
            parse_mode='Markdown'
        )

async def handle_homework_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на отправку домашнего задания"""
    query = update.callback_query
    await query.answer()
    
    time_of_day = query.data.split('_')[2] if len(query.data.split('_')) > 2 else 'morning'
    level = context.user_data['level']
    day = context.user_data['day']
    
    # Сохраняем информацию о текущем задании в контексте пользователя
    context.user_data['homework_info'] = {
        'level': level,
        'day': day,
        'time_of_day': time_of_day
    }
    
    await query.edit_message_text(
        f"""
📝 *Отправка домашнего задания*
━━━━━━━━━━━━━━━━━━━━━

🎤 Запишите голосовое сообщение с выполненным заданием
и отправьте его в этот чат.

*Информация об уроке:*
📚 Уровень: {level} {get_level_emoji(level)}
📅 День: {day} из 14
⏰ Время: {time_of_day}

━━━━━━━━━━━━━━━━━━━━━
⚠️ _Отправьте голосовое сообщение прямо сейчас._
_Бот ожидает вашу запись..._
""",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Вернуться к уроку", callback_data=f"time_{time_of_day}")
        ]])
    )
    return WAITING_HOMEWORK

async def handle_homework_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученного голосового сообщения с домашним заданием"""
    user_id = update.effective_user.id
    logger.info(f"📝 Получено домашнее задание от пользователя {user_id}")
    
    if not update.message.voice:
        await update.message.reply_text(
            """
❌ *Ошибка при отправке задания*
━━━━━━━━━━━━━━━━━━━━━

Пожалуйста, отправьте голосовое сообщение
с выполненным заданием.

💡 *Как записать голосовое:*
1️⃣ Нажмите и удерживайте кнопку микрофона
2️⃣ Запишите ваш ответ
3️⃣ Отпустите кнопку для отправки
""",
            parse_mode='Markdown'
        )
        return WAITING_HOMEWORK
    
    homework_info = context.user_data.get('homework_info', {})
    if not homework_info:
        await update.message.reply_text(
            """
❌ *Ошибка при обработке задания*
━━━━━━━━━━━━━━━━━━━━━

Пожалуйста, начните отправку задания заново.

🔄 Вернитесь к уроку и нажмите кнопку
"Отправить домашнее задание"
""",
            parse_mode='Markdown'
        )
        return SHOWING_LESSON
    
    # Получаем информацию о файле
    file_id = update.message.voice.file_id
    
    try:
        # Создаем сообщение для администратора
        admin_message = f"""
📬 *Новое домашнее задание*
━━━━━━━━━━━━━━━━━━━━━

👤 *Информация о студенте:*
• ID: `{update.effective_user.id}`
• Имя: {update.effective_user.first_name}
• Username: @{update.effective_user.username or 'отсутствует'}

📚 *Информация об уроке:*
• Уровень: {homework_info['level']} {get_level_emoji(homework_info['level'])}
• День: {homework_info['day']} из 14
• Время: {homework_info['time_of_day']}

━━━━━━━━━━━━━━━━━━━━━
✍️ Оцените выполнение задания:
"""
        # Отправляем сообщение администратору
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=admin_message,
            parse_mode='Markdown'
        )
        
        # Отправляем голосовое сообщение администратору
        await context.bot.send_voice(
            chat_id=ADMIN_USER_ID,
            voice=file_id,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👍 Одобрить", callback_data=f"hw_approve_{update.effective_user.id}"),
                    InlineKeyboardButton("👎 Отклонить", callback_data=f"hw_reject_{update.effective_user.id}")
                ]
            ])
        )
        
        # Отправляем подтверждение студенту
        await update.message.reply_text(
            """
✅ *Домашнее задание отправлено!*
━━━━━━━━━━━━━━━━━━━━━

📝 Ваше задание отправлено на проверку
👨‍🏫 Преподаватель проверит его и даст обратную связь
🔔 Вы получите уведомление с результатом

💡 *Что дальше?*
• Продолжайте обучение
• Изучайте новые материалы
• Практикуйте язык

━━━━━━━━━━━━━━━━━━━━━
🔄 Нажмите кнопку ниже, чтобы вернуться к уроку
""",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Вернуться к уроку", callback_data=f"time_{homework_info['time_of_day']}")
            ]])
        )
        
        return SHOWING_LESSON
        
    except telegram.error.Unauthorized:
        logger.error("Ошибка: Бот не может отправить сообщение администратору (заблокирован)")
        await update.message.reply_text(
            """
❌ *Ошибка при отправке задания*
━━━━━━━━━━━━━━━━━━━━━

Произошла техническая ошибка.
Пожалуйста, попробуйте позже.

💡 При повторении ошибки обратитесь
к администратору @renatblizkiy
""",
            parse_mode='Markdown'
        )
        return WAITING_HOMEWORK
        
    except Exception as e:
        logger.error(f"Ошибка при отправке домашнего задания: {str(e)}")
        await update.message.reply_text(
            """
❌ *Ошибка при отправке задания*
━━━━━━━━━━━━━━━━━━━━━

Произошла техническая ошибка.
Пожалуйста, попробуйте позже.

💡 При повторении ошибки обратитесь
к администратору @renatblizkiy
""",
            parse_mode='Markdown'
        )
        return WAITING_HOMEWORK

async def handle_homework_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка оценки домашнего задания администратором"""
    query = update.callback_query
    admin_id = query.from_user.id
    
    if admin_id != ADMIN_USER_ID:
        logger.warning(f"⚠️ Попытка несанкционированного доступа к оценке ДЗ от пользователя {admin_id}")
        await query.answer("❌ У вас нет прав для выполнения этого действия")
        return
    
    # Получаем действие (approve/reject) и ID студента из callback_data
    action, student_id = query.data.split('_')[1:3]
    student_id = int(student_id)
    
    # Отправляем сообщение студенту в зависимости от оценки
    if action == 'approve':
        message = """
✅ *Домашнее задание проверено!*
━━━━━━━━━━━━━━━━━━━━━

🌟 Отличная работа! Преподаватель одобрил
ваше выполнение задания.

💡 *Рекомендации:*
• Продолжайте в том же духе
• Практикуйте новые слова
• Выполняйте все задания
• Следите за произношением

✨ Успехов в дальнейшем обучении!
"""
    else:
        message = """
⚠️ *Домашнее задание требует доработки*
━━━━━━━━━━━━━━━━━━━━━

💡 *Рекомендации преподавателя:*
• Внимательнее следите за произношением
• Повторите грамматические правила
• Практикуйте новые слова
• Запишите задание еще раз

📝 *Что делать дальше:*
1️⃣ Вернитесь к материалам урока
2️⃣ Изучите рекомендации
3️⃣ Запишите задание заново
4️⃣ Отправьте на проверку

✨ Мы верим в ваш успех!
"""
    
    try:
        # Отправляем сообщение студенту
        await context.bot.send_message(
            chat_id=student_id,
            text=message,
            parse_mode='Markdown'
        )
        
        # Удаляем кнопки из сообщения администратора
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("✅ Оценка отправлена студенту")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке оценки: {e}")
        await query.answer("❌ Произошла ошибка при отправке оценки")

async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка пре-чекаута платежа"""
    query = update.pre_checkout_query
    await query.answer(ok=True)
    return PAYMENT

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешного платежа"""
    payment_info = update.message.successful_payment
    user_id = update.effective_user.id
    logger.info(f"✅ Успешная оплата от пользователя {user_id}")
    
    # Активируем курс для пользователя
    level = context.user_data.get('temp_level')
    if not level:
        await update.message.reply_text(
            """
❌ *Ошибка активации курса*
━━━━━━━━━━━━━━━━━━━━━

Пожалуйста, начните регистрацию заново,
используя команду /start

💡 При повторении ошибки обратитесь
к администратору @renatblizkiy
""",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Сохраняем данные пользователя
    user_data = {
        'level': level,
        'day': 1,
        'max_day': 1,  # Добавляем отслеживание максимального дня
        'last_lesson_date': (datetime.now() - timedelta(days=1)).isoformat(),
        'time_of_day': 'morning'
    }
    update_user_data(user_id, user_data)
    context.user_data.update(user_data)
    
    # Отправляем сообщение об успешной активации
    success_message = f"""
🎉 *Поздравляем! Ваш курс активирован!* 🎉
━━━━━━━━━━━━━━━━━━━━━

📚 *Информация о курсе:*
• Уровень: {level} {get_level_emoji(level)}
• Длительность: 14 дней
• Формат: 3 урока в день
• Доступ: Полный

✨ *Что включено:*
• Все материалы и уроки
• Аудио от носителей языка
• Проверка домашних заданий
• Поддержка преподавателя
• Отслеживание прогресса

💡 *Как начать обучение:*
1️⃣ Нажмите кнопку "Начать обучение"
2️⃣ Выберите удобное время для урока
3️⃣ Следуйте инструкциям в уроке
4️⃣ Выполняйте домашние задания

━━━━━━━━━━━━━━━━━━━━━
✨ Желаем успехов в изучении английского языка!
"""
    keyboard = [[InlineKeyboardButton("🚀 Начать обучение", callback_data="time:morning")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        success_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SHOWING_LESSON

def create_lesson_navigation(current_day: int, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Создает клавиатуру для навигации по урокам"""
    keyboard = [
        [
            InlineKeyboardButton("🌅 Утренний урок", callback_data="time:morning"),
            InlineKeyboardButton("☀️ Дневной урок", callback_data="time:afternoon"),
        ],
        [
            InlineKeyboardButton("🌙 Вечерний урок", callback_data="time:evening")
        ],
        [InlineKeyboardButton("📝 Отправить домашнее задание", callback_data=f"homework_{context.user_data.get('time_of_day', 'morning')}")]
    ]
    
    # Добавляем кнопки навигации по дням
    nav_buttons = []
    if current_day > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ День назад", callback_data="prev_day"))
    if current_day < 14:
        nav_buttons.append(InlineKeyboardButton("День вперед ➡️", callback_data="next_day"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

def get_lesson_keyboard(time_of_day: str, current_day: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для навигации по урокам"""
    keyboard = [
        [
            InlineKeyboardButton("🌅 Утренний урок", callback_data="time:morning"),
            InlineKeyboardButton("☀️ Дневной урок", callback_data="time:afternoon"),
        ],
        [
            InlineKeyboardButton("🌙 Вечерний урок", callback_data="time:evening")
        ]
    ]
    
    # Добавляем кнопку домашнего задания
    keyboard.append([InlineKeyboardButton("📝 Отправить домашнее задание", callback_data=f"homework_{time_of_day}")])
    
    # Добавляем кнопки навигации по дням
    nav_buttons = []
    if current_day > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущий день", callback_data="prev_day"))
    if current_day < 14:
        nav_buttons.append(InlineKeyboardButton("Следующий день ➡️", callback_data="next_day"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

async def handle_prev_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для перехода к предыдущему дню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    current_day = int(user_data.get('current_day', 1))
    max_day = int(user_data.get('max_day', current_day))  # Получаем максимальный достигнутый день
    time_of_day = user_data.get('time_of_day', 'morning')
    
    if current_day > 1:
        current_day -= 1
        user_data['current_day'] = current_day
        user_data['day'] = current_day
        # Сохраняем максимальный достигнутый день
        user_data['max_day'] = max_day
        update_user_data(user_id, user_data)
        
        # Обновляем данные в контексте
        context.user_data.update(user_data)
        
        await show_daily_lesson(update, context)
    else:
        await query.answer("❌ Вы уже на первом дне обучения")
    return SHOWING_LESSON

async def handle_next_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для перехода к следующему дню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    current_day = int(user_data.get('current_day', 1))
    max_day = int(user_data.get('max_day', current_day))
    time_of_day = user_data.get('time_of_day', 'morning')
    
    # Если пытаемся перейти к новому дню (превышающему максимальный)
    if current_day >= max_day:
        # Проверяем, прошло ли 24 часа с последнего урока
        last_lesson_date = datetime.fromisoformat(user_data.get('last_lesson_date', '2000-01-01'))
        time_since_last_lesson = datetime.now() - last_lesson_date
        seconds_left = 24 * 3600 - time_since_last_lesson.total_seconds()
        
        if seconds_left > 0:
            hours_left = int(seconds_left // 3600)
            minutes_left = int((seconds_left % 3600) // 60)
            seconds = int(seconds_left % 60)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Вернуться к текущему уроку", callback_data=f"time:{time_of_day}")],
                [InlineKeyboardButton("📝 Отправить домашнее задание", callback_data=f"homework_{time_of_day}")]
            ]
            
            message = f"""
⏳ *До следующего урока осталось:*
━━━━━━━━━━━━━━━━━━━━━

⌛️ {hours_left:02d}:{minutes_left:02d}:{seconds:02d}

*Ваш прогресс:*
📚 Уровень: {user_data['level']} {get_level_emoji(user_data['level'])}
📅 Текущий день: {current_day} из 14
📊 Максимальный день: {max_day}

💡 *Рекомендации:*
• Повторите материал текущего урока
• Выполните домашнее задание
• Практикуйте новые слова
• Слушайте аудио материалы

━━━━━━━━━━━━━━━━━━━━━
✨ Возвращайтесь позже для продолжения обучения!
"""
            await query.edit_message_text(
                message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SHOWING_LESSON
    
    if current_day < 14:
        current_day += 1
        user_data['current_day'] = current_day
        user_data['day'] = current_day
        
        # Обновляем максимальный достигнутый день, если текущий день больше
        if current_day > max_day:
            user_data['max_day'] = current_day
            user_data['last_lesson_date'] = datetime.now().isoformat()
        
        update_user_data(user_id, user_data)
        context.user_data.update(user_data)
        
        await show_daily_lesson(update, context)
    else:
        await query.answer("❌ Вы уже на последнем дне обучения")
    return SHOWING_LESSON

def check_environment():
    """Проверяет наличие всех необходимых файлов и директорий"""
    try:
        # Проверяем наличие .env файла
        if not os.path.exists('.env'):
            logger.warning("⚠️ Файл .env не найден")
            
        # Проверяем наличие директории для резервных копий
        Path(BACKUP_DIR).mkdir(exist_ok=True)
        logger.info("✅ Директория для резервных копий готова")
        
        # Проверяем наличие файла с данными пользователей
        if not os.path.exists(USERS_DATA_FILE):
            # Создаем пустой файл
            save_users_data({})
            logger.info("✅ Создан новый файл данных пользователей")
        
        # Проверяем наличие и содержимое файла course_content.py
        if not os.path.exists('course_content.py'):
            logger.error("❌ Файл course_content.py не найден")
            raise FileNotFoundError("Отсутствует файл course_content.py")
            
        # Проверяем структуру COURSE_CONTENT
        if not isinstance(COURSE_CONTENT, dict):
            logger.error("❌ Некорректная структура COURSE_CONTENT")
            raise ValueError("COURSE_CONTENT должен быть словарем")
            
        # Проверяем наличие всех уровней
        for level in LEVELS.keys():
            if level not in COURSE_CONTENT:
                logger.warning(f"⚠️ В COURSE_CONTENT отсутствует уровень {level}")
                
        # Проверяем структуру уроков
        for level, days in COURSE_CONTENT.items():
            if not isinstance(days, dict):
                logger.error(f"❌ Некорректная структура дней для уровня {level}")
                continue
                
            for day, times in days.items():
                if not isinstance(times, dict):
                    logger.error(f"❌ Некорректная структура времени для уровня {level}, день {day}")
                    continue
                    
                for time_of_day, lesson in times.items():
                    if not isinstance(lesson, dict):
                        logger.error(f"❌ Некорректная структура урока для уровня {level}, день {day}, время {time_of_day}")
                        continue
                        
                    # Проверяем обязательные поля урока
                    required_fields = ['topic', 'vocabulary', 'grammar', 'practice']
                    missing_fields = [field for field in required_fields if field not in lesson]
                    if missing_fields:
                        logger.warning(f"⚠️ Отсутствуют поля {', '.join(missing_fields)} в уроке {level}, день {day}, время {time_of_day}")
        
        logger.info("✅ Проверка окружения завершена успешно")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке окружения: {e}")
        return False

def main():
    """Запускает бота"""
    try:
        # Загружаем переменные окружения
        load_dotenv()
        
        # Проверяем окружение
        if not check_environment():
            logger.error("❌ Ошибка при проверке окружения")
            return
        
        # Получаем токен бота из переменных окружения
        token = os.getenv('TELEGRAM_TOKEN')
        
        if not token:
            logger.error("❌ Токен не найден в файле .env")
            return
        
        # Создаем и настраиваем бота
        application = Application.builder().token(token).build()
        
        # Добавляем обработчики команд
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                CHOOSING_LEVEL: [
                    CallbackQueryHandler(handle_ready_choice, pattern="^(ready_to_choose|not_ready)$"),
                    CallbackQueryHandler(level_chosen, pattern="^confirm_")
                ],
                PAYMENT: [
                    PreCheckoutQueryHandler(handle_pre_checkout),
                    MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment),
                    CallbackQueryHandler(handle_payment, pattern="^pay_"),
                    CallbackQueryHandler(handle_ready_choice, pattern="^ready_to_choose$")
                ],
                SHOWING_LESSON: [
                    CallbackQueryHandler(handle_time_selection, pattern="^time[_:]"),
                    CallbackQueryHandler(handle_prev_day, pattern="^prev_day$"),
                    CallbackQueryHandler(handle_next_day, pattern="^next_day$"),
                    CallbackQueryHandler(handle_homework_request, pattern="^homework_"),
                    CallbackQueryHandler(return_to_current_lesson, pattern="^return_current$"),
                    CallbackQueryHandler(handle_homework_feedback, pattern="^hw_(approve|reject)_"),
                    MessageHandler(filters.VOICE, handle_homework_voice)
                ],
                WAITING_HOMEWORK: [
                    MessageHandler(filters.VOICE, handle_homework_voice),
                    CallbackQueryHandler(handle_time_selection, pattern="^time[_:]")
                ]
            },
            fallbacks=[CommandHandler('start', start)],
            per_message=False,
            per_chat=False
        )
        
        # Добавляем обработчики
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler('activate', activate_course))
        application.add_handler(CallbackQueryHandler(handle_homework_feedback, pattern="^hw_(approve|reject)_"))  # Добавляем глобальный обработчик для кнопок администратора
        
        logger.info("🚀 Бот успешно настроен и готов к запуску")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    main() 