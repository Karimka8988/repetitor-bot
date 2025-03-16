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

# РљРѕРЅСЃС‚Р°РЅС‚С‹
BACKUP_DIR = 'backups'
USERS_DATA_FILE = 'users_data.json'
COURSE_PRICE = 1900
YOOMONEY_WALLET = "4100117110526370"
ADMIN_USER_ID = 7762388025

# РЎРѕСЃС‚РѕСЏРЅРёСЏ СЂР°Р·РіРѕРІРѕСЂР°
CHOOSING_LEVEL, PAYMENT, SHOWING_LESSON, WAITING_HOMEWORK, CHOOSING_SUBSCRIPTION = range(5)

# РќР°СЃС‚СЂРѕР№РєРё Р®Money
LEVELS = {
    'A1': {'name': 'Beginner - СѓСЂРѕРІРµРЅСЊ РІС‹Р¶РёРІР°РЅРёСЏ', 'price': COURSE_PRICE},
    'A2': {'name': 'Elementary - РїСЂРµРґРїРѕСЂРѕРіРѕРІС‹Р№ СѓСЂРѕРІРµРЅСЊ', 'price': COURSE_PRICE},
    'B1': {'name': 'Intermediate - РїРѕСЂРѕРіРѕРІС‹Р№ СѓСЂРѕРІРµРЅСЊ', 'price': COURSE_PRICE},
    'B2': {'name': 'Upper-Intermediate - РїРѕСЂРѕРіРѕРІС‹Р№ РїСЂРѕРґРІРёРЅСѓС‚С‹Р№ СѓСЂРѕРІРµРЅСЊ', 'price': COURSE_PRICE},
    'C1': {'name': 'Advanced - СѓСЂРѕРІРµРЅСЊ РїСЂРѕС„РµСЃСЃРёРѕРЅР°Р»СЊРЅРѕРіРѕ РІР»Р°РґРµРЅРёСЏ', 'price': COURSE_PRICE},
    'C2': {'name': 'Proficiency - СѓСЂРѕРІРµРЅСЊ РІР»Р°РґРµРЅРёСЏ РІ СЃРѕРІРµСЂС€РµРЅСЃС‚РІРµ', 'price': COURSE_PRICE}
}

# Р—Р°РіСЂСѓР·РєР° РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ
try:
    load_dotenv()
except Exception as e:
    print(f"РћС€РёР±РєР° РїСЂРё Р·Р°РіСЂСѓР·РєРµ .env С„Р°Р№Р»Р°: {e}")

# РЎРѕР·РґР°РµРј РґРёСЂРµРєС‚РѕСЂРёРё РґР»СЏ Р»РѕРіРѕРІ Рё Р±СЌРєР°РїРѕРІ
log_dir = Path('logs')
backup_dir = Path(BACKUP_DIR)
try:
    log_dir.mkdir(exist_ok=True)
    backup_dir.mkdir(exist_ok=True)
except Exception as e:
    print(f"РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё РґРёСЂРµРєС‚РѕСЂРёР№: {e}")

# РќР°СЃС‚СЂРѕР№РєР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ
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
    print(f"РћС€РёР±РєР° РїСЂРё РЅР°СЃС‚СЂРѕР№РєРµ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ: {e}")

logger = logging.getLogger(__name__)

# РџСЂРѕРІРµСЂРєР° РЅРµРѕР±С…РѕРґРёРјС‹С… РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ
REQUIRED_ENV_VARS = {
    'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
    'VOICERSS_API_KEY': os.getenv('VOICERSS_API_KEY')
}

for var_name, var_value in REQUIRED_ENV_VARS.items():
    if not var_value:
        logger.error(f"вќЊ РћС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РѕР±СЏР·Р°С‚РµР»СЊРЅР°СЏ РїРµСЂРµРјРµРЅРЅР°СЏ РѕРєСЂСѓР¶РµРЅРёСЏ: {var_name}")
        raise EnvironmentError(f"РћС‚СЃСѓС‚СЃС‚РІСѓРµС‚ {var_name}")

def backup_users_data():
    """РЎРѕР·РґР°РµС‚ СЂРµР·РµСЂРІРЅСѓСЋ РєРѕРїРёСЋ С„Р°Р№Р»Р° СЃ РґР°РЅРЅС‹РјРё РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№"""
    try:
        # РЎРѕР·РґР°РµРј РґРёСЂРµРєС‚РѕСЂРёСЋ РґР»СЏ СЂРµР·РµСЂРІРЅС‹С… РєРѕРїРёР№, РµСЃР»Рё РµС‘ РЅРµС‚
        Path(BACKUP_DIR).mkdir(exist_ok=True)
        
        if not os.path.exists(USERS_DATA_FILE):
            logger.warning("вљ пёЏ РќРµС‚ С„Р°Р№Р»Р° РґР»СЏ СЃРѕР·РґР°РЅРёСЏ СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё")
            return False
            
        # Р¤РѕСЂРјРёСЂСѓРµРј РёРјСЏ С„Р°Р№Р»Р° СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё СЃ С‚РµРєСѓС‰РµР№ РґР°С‚РѕР№ Рё РІСЂРµРјРµРЅРµРј
        backup_file = f"{BACKUP_DIR}/users_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # РљРѕРїРёСЂСѓРµРј С„Р°Р№Р»
        shutil.copy2(USERS_DATA_FILE, backup_file)
        logger.info(f"вњ… РЎРѕР·РґР°РЅР° СЂРµР·РµСЂРІРЅР°СЏ РєРѕРїРёСЏ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№: {backup_file}")
        
        # РЈРґР°Р»СЏРµРј СЃС‚Р°СЂС‹Рµ СЂРµР·РµСЂРІРЅС‹Рµ РєРѕРїРёРё (РѕСЃС‚Р°РІР»СЏРµРј С‚РѕР»СЊРєРѕ РїРѕСЃР»РµРґРЅРёРµ 5)
        try:
            backup_files = sorted(Path(BACKUP_DIR).glob('users_data_*.json'))
            if len(backup_files) > 5:
                for old_file in backup_files[:-5]:
                    old_file.unlink()
                    logger.info(f"рџ—‘пёЏ РЈРґР°Р»РµРЅР° СЃС‚Р°СЂР°СЏ СЂРµР·РµСЂРІРЅР°СЏ РєРѕРїРёСЏ: {old_file}")
        except Exception as e:
            logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё РѕС‡РёСЃС‚РєРµ СЃС‚Р°СЂС‹С… СЂРµР·РµСЂРІРЅС‹С… РєРѕРїРёР№: {e}")
        
        return True
    except Exception as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё: {e}")
        return False

def load_users_data():
    """Р—Р°РіСЂСѓР·РєР° РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ РёР· С„Р°Р№Р»Р°"""
    try:
        if not os.path.exists(USERS_DATA_FILE):
            logger.warning("вљ пёЏ Р¤Р°Р№Р» РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ РЅРµ РЅР°Р№РґРµРЅ, СЃРѕР·РґР°РµРј РЅРѕРІС‹Р№")
            return {}
            
        with open(USERS_DATA_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if not isinstance(data, dict):
                logger.error("вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ С„РѕСЂРјР°С‚ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№")
                return {}
            return data
    except json.JSONDecodeError as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё С‡С‚РµРЅРёРё JSON: {e}")
        # РџСЂРѕР±СѓРµРј РІРѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ РёР· РїРѕСЃР»РµРґРЅРµР№ СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё
        try:
            backup_files = sorted(Path(BACKUP_DIR).glob('users_data_*.json'))
            if backup_files:
                latest_backup = backup_files[-1]
                with open(latest_backup, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    if not isinstance(data, dict):
                        raise ValueError("РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ С„РѕСЂРјР°С‚ РґР°РЅРЅС‹С… РІ СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё")
                logger.info(f"вњ… Р”Р°РЅРЅС‹Рµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅС‹ РёР· СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё: {latest_backup}")
                return data
            else:
                logger.warning("вљ пёЏ Р РµР·РµСЂРІРЅС‹Рµ РєРѕРїРёРё РЅРµ РЅР°Р№РґРµРЅС‹")
                return {}
        except Exception as backup_error:
            logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРё РёР· СЂРµР·РµСЂРІРЅРѕР№ РєРѕРїРёРё: {backup_error}")
            return {}
    except Exception as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё Р·Р°РіСЂСѓР·РєРµ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№: {e}")
        return {}

def save_users_data(data):
    """РЎРѕС…СЂР°РЅРµРЅРёРµ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ РІ С„Р°Р№Р»"""
    if not isinstance(data, dict):
        logger.error("вќЊ РџРѕРїС‹С‚РєР° СЃРѕС…СЂР°РЅРёС‚СЊ РЅРµРєРѕСЂСЂРµРєС‚РЅС‹Рµ РґР°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№")
        return False
        
    try:
        # РЎРѕР·РґР°РµРј СЂРµР·РµСЂРІРЅСѓСЋ РєРѕРїРёСЋ РїРµСЂРµРґ СЃРѕС…СЂР°РЅРµРЅРёРµРј
        backup_users_data()
        
        # РЎРѕС…СЂР°РЅСЏРµРј РІРѕ РІСЂРµРјРµРЅРЅС‹Р№ С„Р°Р№Р»
        temp_file = f"{USERS_DATA_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
            
        # Р•СЃР»Рё СЃРѕС…СЂР°РЅРµРЅРёРµ РїСЂРѕС€Р»Рѕ СѓСЃРїРµС€РЅРѕ, Р·Р°РјРµРЅСЏРµРј РѕСЃРЅРѕРІРЅРѕР№ С„Р°Р№Р»
        os.replace(temp_file, USERS_DATA_FILE)
        logger.info("вњ… Р”Р°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ СѓСЃРїРµС€РЅРѕ СЃРѕС…СЂР°РЅРµРЅС‹")
        return True
    except Exception as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё СЃРѕС…СЂР°РЅРµРЅРёРё РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№: {e}")
        # РЈРґР°Р»СЏРµРј РІСЂРµРјРµРЅРЅС‹Р№ С„Р°Р№Р» РІ СЃР»СѓС‡Р°Рµ РѕС€РёР±РєРё
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False

def get_user_data(user_id):
    """РџРѕР»СѓС‡РµРЅРёРµ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ"""
    users_data = load_users_data()
    return users_data.get(str(user_id), {})

def update_user_data(user_id, data):
    """РћР±РЅРѕРІР»РµРЅРёРµ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ"""
    users_data = load_users_data()
    users_data[str(user_id)] = data
    save_users_data(users_data)

def can_access_next_lesson(user_id):
    """РџСЂРѕРІРµСЂРєР° РІРѕР·РјРѕР¶РЅРѕСЃС‚Рё РґРѕСЃС‚СѓРїР° Рє СЃР»РµРґСѓСЋС‰РµРјСѓ СѓСЂРѕРєСѓ"""
    user_data = get_user_data(user_id)
    if not user_data:
        return True
    
    last_lesson_date = datetime.fromisoformat(user_data.get('last_lesson_date', '2000-01-01'))
    current_date = datetime.now()
    
    # РџСЂРѕРІРµСЂСЏРµРј, РїСЂРѕС€Р»Рё Р»Рё СЃСѓС‚РєРё СЃ РїРѕСЃР»РµРґРЅРµРіРѕ СѓСЂРѕРєР°
    return (current_date - last_lesson_date).days >= 1

async def get_pronunciation_audio(text: str) -> bytes:
    """РџРѕР»СѓС‡РµРЅРёРµ Р°СѓРґРёРѕ СЃ РїСЂРѕРёР·РЅРѕС€РµРЅРёРµРј РѕС‚ Text-to-Speech СЃРµСЂРІРёСЃР°"""
    if not text or not isinstance(text, str):
        logger.error("вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ С‚РµРєСЃС‚ РґР»СЏ РїСЂРѕРёР·РЅРѕС€РµРЅРёСЏ")
        return None
        
    if not REQUIRED_ENV_VARS['VOICERSS_API_KEY']:
        logger.error("вќЊ API РєР»СЋС‡ РґР»СЏ Text-to-Speech СЃРµСЂРІРёСЃР° РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ")
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
                        logger.info(f"вњ… РђСѓРґРёРѕ СѓСЃРїРµС€РЅРѕ РїРѕР»СѓС‡РµРЅРѕ, СЂР°Р·РјРµСЂ: {len(audio_content)} Р±Р°Р№С‚")
                        return audio_content
                    else:
                        error_text = audio_content.decode('utf-8', errors='ignore')
                        logger.error(f"вќЊ РћС€РёР±РєР° РІ РѕС‚РІРµС‚Рµ API: {error_text}")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё Р°СѓРґРёРѕ: {response.status} - {error_text}")
                    return None
    except aiohttp.ClientError as e:
        logger.error(f"вќЊ РћС€РёР±РєР° СЃРµС‚Рё РїСЂРё РїРѕР»СѓС‡РµРЅРёРё Р°СѓРґРёРѕ: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"вќЊ РќРµРѕР¶РёРґР°РЅРЅР°СЏ РѕС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё Р°СѓРґРёРѕ: {str(e)}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РќР°С‡Р°Р»Рѕ СЂР°Р±РѕС‚С‹ СЃ Р±РѕС‚РѕРј"""
    user_id = update.effective_user.id
    logger.info(f"рџљЂ РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {user_id} Р·Р°РїСѓСЃС‚РёР» Р±РѕС‚Р°")
    user_data = get_user_data(user_id)
    
    # Р•СЃР»Рё РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓР¶Рµ РЅР°С‡Р°Р» РєСѓСЂСЃ, РїРѕРєР°Р·С‹РІР°РµРј С‚РµРєСѓС‰РёР№ СѓСЂРѕРє
    if user_data and user_data.get('level'):
        context.user_data.update(user_data)
        message = f"""
рџЋ“ *Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РѕР±СЂР°С‚РЅРѕ РІ English Learning Bot!*

рџ“Љ *Р’Р°С€ С‚РµРєСѓС‰РёР№ РїСЂРѕРіСЂРµСЃСЃ:*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
рџЋЇ РЈСЂРѕРІРµРЅСЊ: {user_data['level']} {get_level_emoji(user_data['level'])}
рџ“… Р”РµРЅСЊ: {user_data['day']} РёР· 14
вЏ° РџРѕСЃР»РµРґРЅРёР№ СѓСЂРѕРє: {user_data['last_lesson_date']}
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

вљ пёЏ _РџР»Р°РЅ РѕР±СѓС‡РµРЅРёСЏ РЅРµР»СЊР·СЏ РёР·РјРµРЅРёС‚СЊ РґРѕ Р·Р°РІРµСЂС€РµРЅРёСЏ С‚РµРєСѓС‰РµРіРѕ РєСѓСЂСЃР°._

рџ•’ *Р’С‹Р±РµСЂРёС‚Рµ СѓРґРѕР±РЅРѕРµ РІСЂРµРјСЏ РґР»СЏ СѓСЂРѕРєР°:*
"""
        keyboard = [
            [
                InlineKeyboardButton("рџЊ… РЈС‚СЂРµРЅРЅРёР№ СѓСЂРѕРє", callback_data="time:morning"),
                InlineKeyboardButton("вЂпёЏ Р”РЅРµРІРЅРѕР№ СѓСЂРѕРє", callback_data="time:afternoon"),
            ],
            [
                InlineKeyboardButton("рџЊ™ Р’РµС‡РµСЂРЅРёР№ СѓСЂРѕРє", callback_data="time:evening")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        # РЎРѕС…СЂР°РЅСЏРµРј С‚РµРєСѓС‰РёР№ РґРµРЅСЊ Рё РІСЂРµРјСЏ РІ РєРѕРЅС‚РµРєСЃС‚Рµ
        context.user_data['current_day'] = user_data['day']
        context.user_data['time_of_day'] = user_data.get('time_of_day', 'morning')
        
        return SHOWING_LESSON
    
    # Р”Р»СЏ РЅРѕРІС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ РїРѕРєР°Р·С‹РІР°РµРј РїСЂРёРІРµС‚СЃС‚РІРёРµ
    welcome_message = """
рџЊџ *Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ English Learning Bot!* рџЊџ
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ“љ Р’Р°С€ РїРµСЂСЃРѕРЅР°Р»СЊРЅС‹Р№ РїРѕРјРѕС‰РЅРёРє РІ РёР·СѓС‡РµРЅРёРё Р°РЅРіР»РёР№СЃРєРѕРіРѕ СЏР·С‹РєР°! 

*Р§С‚Рѕ РІР°СЃ Р¶РґС‘С‚:*
рџЋЇ 14 РґРЅРµР№ РёРЅС‚РµРЅСЃРёРІРЅРѕРіРѕ РѕР±СѓС‡РµРЅРёСЏ
рџ“ќ Р•Р¶РµРґРЅРµРІРЅС‹Рµ СѓСЂРѕРєРё Рё РїСЂР°РєС‚РёРєР°
рџ“– РР·СѓС‡РµРЅРёРµ РЅРѕРІС‹С… СЃР»РѕРІ Рё РіСЂР°РјРјР°С‚РёРєРё
рџЋ§ РђСѓРґРёРѕ РїСЂРѕРёР·РЅРѕС€РµРЅРёРµ РѕС‚ РЅРѕСЃРёС‚РµР»РµР№ СЏР·С‹РєР°
рџЋ® РРЅС‚РµСЂР°РєС‚РёРІРЅС‹Рµ Р·Р°РґР°РЅРёСЏ

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вљ пёЏ *Р’РђР–РќРћР• РџР Р•Р”РЈРџР Р•Р–Р”Р•РќРР•:*
РџРѕСЃР»Рµ РІС‹Р±РѕСЂР° СѓСЂРѕРІРЅСЏ РѕР±СѓС‡РµРЅРёСЏ РµРіРѕ РЅРµР»СЊР·СЏ Р±СѓРґРµС‚ РёР·РјРµРЅРёС‚СЊ РґРѕ Р·Р°РІРµСЂС€РµРЅРёСЏ 14-РґРЅРµРІРЅРѕРіРѕ РєСѓСЂСЃР°. 

рџ’« *Р“РѕС‚РѕРІС‹ РЅР°С‡Р°С‚СЊ СѓРІР»РµРєР°С‚РµР»СЊРЅРѕРµ РїСѓС‚РµС€РµСЃС‚РІРёРµ РІ РјРёСЂ Р°РЅРіР»РёР№СЃРєРѕРіРѕ СЏР·С‹РєР°?*
"""
    keyboard = [
        [InlineKeyboardButton("вњЁ Р”Р°, С…РѕС‡Сѓ РІС‹Р±СЂР°С‚СЊ СѓСЂРѕРІРµРЅСЊ!", callback_data="ready_to_choose")],
        [InlineKeyboardButton("рџ¤” РќРµС‚, РјРЅРµ РЅСѓР¶РЅРѕ РїРѕРґСѓРјР°С‚СЊ", callback_data="not_ready")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return CHOOSING_LEVEL

def get_level_emoji(level: str) -> str:
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЌРјРѕРґР·Рё РґР»СЏ РєР°Р¶РґРѕРіРѕ СѓСЂРѕРІРЅСЏ"""
    emoji_map = {
        'A1': 'рџЊ±',  # РќР°С‡РёРЅР°СЋС‰РёР№
        'A2': 'рџЊї',  # Р­Р»РµРјРµРЅС‚Р°СЂРЅС‹Р№
        'B1': 'рџЊє',  # РЎСЂРµРґРЅРёР№
        'B2': 'рџЊё',  # Р’С‹С€Рµ СЃСЂРµРґРЅРµРіРѕ
        'C1': 'рџЊі',  # РџСЂРѕРґРІРёРЅСѓС‚С‹Р№
        'C2': 'рџЋ“'   # РџСЂРѕС„РµСЃСЃРёРѕРЅР°Р»СЊРЅС‹Р№
    }
    return emoji_map.get(level, '')

async def handle_ready_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° РіРѕС‚РѕРІРЅРѕСЃС‚Рё Рє РІС‹Р±РѕСЂСѓ СѓСЂРѕРІРЅСЏ"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "not_ready":
        message = """
рџ¤” *РќРµ С‚РѕСЂРѕРїРёС‚РµСЃСЊ СЃ РІС‹Р±РѕСЂРѕРј!*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ’Ў *Р РµРєРѕРјРµРЅРґР°С†РёРё РїРѕ РІС‹Р±РѕСЂСѓ СѓСЂРѕРІРЅСЏ:*

рџЊ± *A1 - Beginner*
вЂў РўРѕР»СЊРєРѕ РЅР°С‡РёРЅР°РµС‚Рµ РёР·СѓС‡Р°С‚СЊ СЏР·С‹Рє
вЂў Р—РЅР°РµС‚Рµ Р°Р»С„Р°РІРёС‚ Рё Р±Р°Р·РѕРІС‹Рµ СЃР»РѕРІР°
вЂў РҐРѕС‚РёС‚Рµ РЅР°СѓС‡РёС‚СЊСЃСЏ РїСЂРµРґСЃС‚Р°РІР»СЏС‚СЊСЃСЏ

рџЊї *A2 - Elementary*
вЂў Р—РЅР°РµС‚Рµ Р±Р°Р·РѕРІС‹Рµ С„СЂР°Р·С‹
вЂў РџРѕРЅРёРјР°РµС‚Рµ РїСЂРѕСЃС‚С‹Рµ С‚РµРєСЃС‚С‹
вЂў РњРѕР¶РµС‚Рµ СЂР°СЃСЃРєР°Р·Р°С‚СЊ Рѕ СЃРµР±Рµ

рџЊє *B1 - Intermediate*
вЂў РћР±С‰Р°РµС‚РµСЃСЊ РЅР° Р±С‹С‚РѕРІС‹Рµ С‚РµРјС‹
вЂў РџРѕРЅРёРјР°РµС‚Рµ РјРµРґР»РµРЅРЅСѓСЋ СЂРµС‡СЊ
вЂў Р§РёС‚Р°РµС‚Рµ РїСЂРѕСЃС‚С‹Рµ СЃС‚Р°С‚СЊРё

рџЊё *B2 - Upper-Intermediate*
вЂў РЎРІРѕР±РѕРґРЅРѕ РіРѕРІРѕСЂРёС‚Рµ РЅР° РјРЅРѕРіРёРµ С‚РµРјС‹
вЂў РЎРјРѕС‚СЂРёС‚Рµ С„РёР»СЊРјС‹ РІ РѕСЂРёРіРёРЅР°Р»Рµ
вЂў Р§РёС‚Р°РµС‚Рµ РєРЅРёРіРё РЅР° Р°РЅРіР»РёР№СЃРєРѕРј

рџЊі *C1 - Advanced*
вЂў Р’Р»Р°РґРµРµС‚Рµ СЏР·С‹РєРѕРј РїРѕС‡С‚Рё РєР°Рє РЅРѕСЃРёС‚РµР»СЊ
вЂў РџРѕРЅРёРјР°РµС‚Рµ СЃР»РѕР¶РЅС‹Рµ С‚РµРєСЃС‚С‹
вЂў Р“РѕРІРѕСЂРёС‚Рµ Р±РµРіР»Рѕ Рё СЃРїРѕРЅС‚Р°РЅРЅРѕ

рџЋ“ *C2 - Proficiency*
вЂў РџСЂРѕС„РµСЃСЃРёРѕРЅР°Р»СЊРЅРѕРµ РІР»Р°РґРµРЅРёРµ
вЂў РџРѕРЅРёРјР°РµС‚Рµ Р»СЋР±СѓСЋ СЂРµС‡СЊ
вЂў РџРёС€РµС‚Рµ СЃР»РѕР¶РЅС‹Рµ С‚РµРєСЃС‚С‹

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вњЁ РљРѕРіРґР° Р±СѓРґРµС‚Рµ РіРѕС‚РѕРІС‹ РЅР°С‡Р°С‚СЊ РѕР±СѓС‡РµРЅРёРµ,
РїСЂРѕСЃС‚Рѕ РЅР°Р¶РјРёС‚Рµ /start
"""
        await query.edit_message_text(
            message,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # РџРѕРєР°Р·С‹РІР°РµРј РІС‹Р±РѕСЂ СѓСЂРѕРІРЅРµР№
    message = """
рџ“љ *Р’С‹Р±РµСЂРёС‚Рµ РІР°С€ СѓСЂРѕРІРµРЅСЊ Р°РЅРіР»РёР№СЃРєРѕРіРѕ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

вњЁ *РљР°Р¶РґС‹Р№ СѓСЂРѕРІРµРЅСЊ РІРєР»СЋС‡Р°РµС‚:*
рџ“… 14 РґРЅРµР№ РёРЅС‚РµРЅСЃРёРІРЅРѕРіРѕ РѕР±СѓС‡РµРЅРёСЏ
рџЋЇ 3 СѓСЂРѕРєР° РєР°Р¶РґС‹Р№ РґРµРЅСЊ
рџЋ§ РђСѓРґРёРѕ РѕС‚ РЅРѕСЃРёС‚РµР»РµР№ СЏР·С‹РєР°
рџ“ќ РџСЂР°РєС‚РёС‡РµСЃРєРёРµ Р·Р°РґР°РЅРёСЏ
рџ“Љ РћС‚СЃР»РµР¶РёРІР°РЅРёРµ РїСЂРѕРіСЂРµСЃСЃР°

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вљ пёЏ *Р’РђР–РќРћ:* 
вЂў РЈСЂРѕРІРµРЅСЊ РЅРµР»СЊР·СЏ РёР·РјРµРЅРёС‚СЊ РґРѕ РєРѕРЅС†Р° РєСѓСЂСЃР°
вЂў Р’С‹Р±РµСЂРёС‚Рµ РїРѕРґС…РѕРґСЏС‰РёР№ РґР»СЏ РІР°СЃ СѓСЂРѕРІРµРЅСЊ
вЂў Р‘СѓРґСЊС‚Рµ РіРѕС‚РѕРІС‹ Р·Р°РЅРёРјР°С‚СЊСЃСЏ 14 РґРЅРµР№

*Р”РѕСЃС‚СѓРїРЅС‹Рµ СѓСЂРѕРІРЅРё:*
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
    """РћР±СЂР°Р±РѕС‚РєР° РІС‹Р±РѕСЂР° СѓСЂРѕРІРЅСЏ"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('confirm_'):
        return CHOOSING_LEVEL
    
    level = query.data.split('_')[1]  # confirm_A1 -> A1
    
    # РџСЂРѕРІРµСЂСЏРµРј, СЃСѓС‰РµСЃС‚РІСѓРµС‚ Р»Рё РІС‹Р±СЂР°РЅРЅС‹Р№ СѓСЂРѕРІРµРЅСЊ РІ COURSE_CONTENT
    if level not in COURSE_CONTENT:
        await query.edit_message_text(
            f"""
вќЊ *РћС€РёР±РєР°: СѓСЂРѕРІРµРЅСЊ РЅРµРґРѕСЃС‚СѓРїРµРЅ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

РЈСЂРѕРІРµРЅСЊ {level} РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ.
РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РІС‹Р±РµСЂРёС‚Рµ РґСЂСѓРіРѕР№ СѓСЂРѕРІРµРЅСЊ.

рџ”„ РќР°Р¶РјРёС‚Рµ /start РґР»СЏ РІС‹Р±РѕСЂР° СѓСЂРѕРІРЅСЏ
""",
            parse_mode='Markdown'
        )
        return CHOOSING_LEVEL
    
    context.user_data['temp_level'] = level  # Р’СЂРµРјРµРЅРЅРѕ СЃРѕС…СЂР°РЅСЏРµРј РІС‹Р±СЂР°РЅРЅС‹Р№ СѓСЂРѕРІРµРЅСЊ
    
    # РџРѕРєР°Р·С‹РІР°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ РѕР± РѕРїР»Р°С‚Рµ
    payment_message = f"""
вњЁ *РћС‚Р»РёС‡РЅС‹Р№ РІС‹Р±РѕСЂ - СѓСЂРѕРІРµРЅСЊ {level}!*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ“љ *Р’Р°С€ РєСѓСЂСЃ РІРєР»СЋС‡Р°РµС‚:*
вЂў РџРѕР»РЅС‹Р№ РґРѕСЃС‚СѓРї РЅР° 14 РґРЅРµР№
вЂў Р’СЃРµ РјР°С‚РµСЂРёР°Р»С‹ Рё Р°СѓРґРёРѕ СѓСЂРѕРєРё
вЂў РџСЂРѕРІРµСЂРєР° РґРѕРјР°С€РЅРёС… Р·Р°РґР°РЅРёР№
вЂў РћС‚СЃР»РµР¶РёРІР°РЅРёРµ РїСЂРѕРіСЂРµСЃСЃР°
вЂў РџРѕРґРґРµСЂР¶РєР° РїСЂРµРїРѕРґР°РІР°С‚РµР»СЏ

рџ’° *РЎС‚РѕРёРјРѕСЃС‚СЊ:* {LEVELS[level]['price']} СЂСѓР±.

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
рџ’« Р”Р»СЏ РЅР°С‡Р°Р»Р° РѕР±СѓС‡РµРЅРёСЏ РЅРµРѕР±С…РѕРґРёРјРѕ РѕРїР»Р°С‚РёС‚СЊ РєСѓСЂСЃ
"""
    keyboard = [
        [InlineKeyboardButton("рџ’і РћРїР»Р°С‚РёС‚СЊ РєСѓСЂСЃ", callback_data=f"pay_{level}")],
        [InlineKeyboardButton("рџ”™ Р’С‹Р±СЂР°С‚СЊ РґСЂСѓРіРѕР№ СѓСЂРѕРІРµРЅСЊ", callback_data="ready_to_choose")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        payment_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return PAYMENT

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° Р·Р°РїСЂРѕСЃР° РЅР° РѕРїР»Р°С‚Сѓ"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"рџ’і РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {user_id} РёРЅРёС†РёРёСЂРѕРІР°Р» РѕРїР»Р°С‚Сѓ")
    
    if not query.data.startswith('pay_'):
        return PAYMENT
    
    level = query.data.split('_')[1]
    price = LEVELS[level]['price']
    
    # РЎРѕР·РґР°РµРј СѓРЅРёРєР°Р»СЊРЅС‹Р№ РёРґРµРЅС‚РёС„РёРєР°С‚РѕСЂ РїР»Р°С‚РµР¶Р°
    payment_id = f"eng_course_{level}_{user_id}_{int(datetime.now().timestamp())}"
    context.user_data['payment_id'] = payment_id
    logger.info(f"рџ’° РЎРѕР·РґР°РЅ РїР»Р°С‚РµР¶ {payment_id} РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id}")
    
    # Р¤РѕСЂРјРёСЂСѓРµРј URL РґР»СЏ С„РѕСЂРјС‹ РѕРїР»Р°С‚С‹
    params = {
        'receiver': YOOMONEY_WALLET,
        'quickpay-form': 'shop',
        'targets': f'РћРїР»Р°С‚Р° РєСѓСЂСЃР° Р°РЅРіР»РёР№СЃРєРѕРіРѕ {level}',
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
рџ’і *РћРїР»Р°С‚Р° РєСѓСЂСЃР° СѓСЂРѕРІРЅСЏ {level}*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ’° *РЎС‚РѕРёРјРѕСЃС‚СЊ:* {price} СЂСѓР±.

вњЁ *Р§С‚Рѕ РІРєР»СЋС‡РµРЅРѕ:*
рџ“љ 14 РґРЅРµР№ РёРЅС‚РµРЅСЃРёРІРЅРѕРіРѕ РѕР±СѓС‡РµРЅРёСЏ
рџЋЇ 42 РёРЅС‚РµСЂР°РєС‚РёРІРЅС‹С… СѓСЂРѕРєР°
рџЋ§ РђСѓРґРёРѕ РјР°С‚РµСЂРёР°Р»С‹ РѕС‚ РЅРѕСЃРёС‚РµР»РµР№
рџ“ќ РџСЂРѕРІРµСЂРєР° РґРѕРјР°С€РЅРёС… Р·Р°РґР°РЅРёР№
рџ‘ЁвЂЌрџЏ« РџРѕРґРґРµСЂР¶РєР° РїСЂРµРїРѕРґР°РІР°С‚РµР»СЏ

рџ“± *РљР°Рє РѕРїР»Р°С‚РёС‚СЊ:*
1пёЏвѓЈ РќР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ "РћРїР»Р°С‚РёС‚СЊ РєР°СЂС‚РѕР№"
2пёЏвѓЈ Р’РІРµРґРёС‚Рµ РґР°РЅРЅС‹Рµ Р±Р°РЅРєРѕРІСЃРєРѕР№ РєР°СЂС‚С‹
3пёЏвѓЈ РџРѕРґС‚РІРµСЂРґРёС‚Рµ РѕРїР»Р°С‚Сѓ
4пёЏвѓЈ РќР°РїРёС€РёС‚Рµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ @renatblizkiy

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вљ пёЏ *Р’Р°Р¶РЅР°СЏ РёРЅС„РѕСЂРјР°С†РёСЏ:*
вЂў РћРїР»Р°С‚Р° РїСЂРѕС…РѕРґРёС‚ С‡РµСЂРµР· Р·Р°С‰РёС‰РµРЅРЅРѕРµ СЃРѕРµРґРёРЅРµРЅРёРµ
вЂў Р”РѕСЃС‚СѓРї РѕС‚РєСЂРѕРµС‚СЃСЏ РїРѕСЃР»Рµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РѕРїР»Р°С‚С‹
вЂў РЎРѕС…СЂР°РЅРёС‚Рµ ID РїР»Р°С‚РµР¶Р°: `{payment_id}`
"""
    
    keyboard = [
        [InlineKeyboardButton("рџ’і РћРїР»Р°С‚РёС‚СЊ РєР°СЂС‚РѕР№", url=payment_url)],
        [InlineKeyboardButton("вњЌпёЏ РќР°РїРёСЃР°С‚СЊ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ", url="https://t.me/renatblizkiy")],
        [InlineKeyboardButton("рџ”™ Р’РµСЂРЅСѓС‚СЊСЃСЏ РЅР°Р·Р°Рґ", callback_data=f"confirm_{level}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        yoomoney_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return PAYMENT

async def show_daily_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРѕРєР°Р·С‹РІР°РµС‚ СѓСЂРѕРє РЅР° РІС‹Р±СЂР°РЅРЅРѕРµ РІСЂРµРјСЏ РґРЅСЏ"""
    query = update.callback_query
    selected_time = "morning"  # Р·РЅР°С‡РµРЅРёРµ РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ
    
    if query and query.data:
        if ":" in query.data:
            selected_time = query.data.split(":")[1]
        elif "_" in query.data:
            selected_time = query.data.split("_")[1]
            
        # РСЃРїСЂР°РІР»СЏРµРј РЅРµРєРѕСЂСЂРµРєС‚РЅРѕРµ РІСЂРµРјСЏ РґРЅСЏ
        if selected_time == "day":
            selected_time = "afternoon"
            
        await query.answer()
    
    # РџРѕР»СѓС‡Р°РµРј С‚РµРєСѓС‰РёР№ РґРµРЅСЊ Рё СѓСЂРѕРІРµРЅСЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data or 'level' not in user_data:
        message = """
вќЊ *РћС€РёР±РєР°:* РЈСЂРѕРІРµРЅСЊ РѕР±СѓС‡РµРЅРёСЏ РЅРµ РІС‹Р±СЂР°РЅ

рџ”„ РСЃРїРѕР»СЊР·СѓР№С‚Рµ /start РґР»СЏ РЅР°С‡Р°Р»Р° РѕР±СѓС‡РµРЅРёСЏ
"""
        if query:
            await query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        return CHOOSING_LEVEL
    
    # РћР±РЅРѕРІР»СЏРµРј РґР°РЅРЅС‹Рµ РІ РєРѕРЅС‚РµРєСЃС‚Рµ
    context.user_data.update(user_data)
    current_day = int(user_data.get('current_day', 1))
    user_level = user_data['level']
    
    try:
        # РЈРґР°Р»СЏРµРј РїСЂРµРґС‹РґСѓС‰РёРµ РіРѕР»РѕСЃРѕРІС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ
        try:
            # РџРѕР»СѓС‡Р°РµРј РїРѕСЃР»РµРґРЅРёРµ СЃРѕРѕР±С‰РµРЅРёСЏ
            if 'last_voice_message_id' in context.user_data:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['last_voice_message_id']
                    )
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РїСЂРё СѓРґР°Р»РµРЅРёРё РїСЂРµРґС‹РґСѓС‰РµРіРѕ РіРѕР»РѕСЃРѕРІРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё СѓРґР°Р»РµРЅРёРё РіРѕР»РѕСЃРѕРІС‹С… СЃРѕРѕР±С‰РµРЅРёР№: {e}")
        
        # РџСЂРµРѕР±СЂР°Р·СѓРµРј current_day РІ int РґР»СЏ РґРѕСЃС‚СѓРїР° Рє СЃР»РѕРІР°СЂСЋ
        current_lesson = COURSE_CONTENT[user_level][int(current_day)][selected_time]
        logger.info(f"вњ… Р—Р°РіСЂСѓР¶РµРЅ СѓСЂРѕРє: СѓСЂРѕРІРµРЅСЊ {user_level}, РґРµРЅСЊ {current_day}, РІСЂРµРјСЏ {selected_time}")
        
        # РћР±РЅРѕРІР»СЏРµРј РІСЂРµРјСЏ РґРЅСЏ РІ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        user_data['time_of_day'] = selected_time
        update_user_data(user_id, user_data)
        context.user_data['time_of_day'] = selected_time
        
        # Р¤РѕСЂРјРёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ СЃ СѓСЂРѕРєРѕРј
        time_emoji = {"morning": "рџЊ…", "afternoon": "вЂпёЏ", "evening": "рџЊ™"}
        time_names = {"morning": "РЈС‚СЂРµРЅРЅРёР№", "afternoon": "Р”РЅРµРІРЅРѕР№", "evening": "Р’РµС‡РµСЂРЅРёР№"}
        
        message = f"""
вљ пёЏ *РЈ РІР°СЃ СѓР¶Рµ РµСЃС‚СЊ Р°РєС‚РёРІРЅС‹Р№ РїР»Р°РЅ РѕР±СѓС‡РµРЅРёСЏ!*

*Р’Р°С€ С‚РµРєСѓС‰РёР№ РїР»Р°РЅ:*
вЂў РЈСЂРѕРІРµРЅСЊ: {user_level} {get_level_emoji(user_level)}
вЂў Р”РµРЅСЊ: {current_day} РёР· 14 рџ“…
вЂў РџРѕСЃР»РµРґРЅРёР№ СѓСЂРѕРє: {user_data.get('last_lesson_date')} рџ“†

РџР»Р°РЅ РѕР±СѓС‡РµРЅРёСЏ РЅРµР»СЊР·СЏ РёР·РјРµРЅРёС‚СЊ РґРѕ Р·Р°РІРµСЂС€РµРЅРёСЏ С‚РµРєСѓС‰РµРіРѕ РєСѓСЂСЃР°

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ“љ Р”РµРЅСЊ {current_day} РёР· 14
в””в”Ђ РЈСЂРѕРІРµРЅСЊ: {user_level} {get_level_emoji(user_level)}
в””в”Ђ {time_emoji.get(selected_time, '')} {time_names.get(selected_time, '')} СѓСЂРѕРє

рџЋЇ РўРµРјР°:
в””в”Ђ {current_lesson.get('topic', '')}

рџ“ќ РќРѕРІС‹Рµ СЃР»РѕРІР°:
"""
        # Р”РѕР±Р°РІР»СЏРµРј СЃР»РѕРІР° СЃ С‚СЂР°РЅСЃРєСЂРёРїС†РёРµР№ Рё РїРµСЂРµРІРѕРґРѕРј
        for i, word_data in enumerate(current_lesson.get('vocabulary', []), 1):
            if isinstance(word_data, dict):
                word = word_data.get('word', '')
                transcription = word_data.get('transcription', '')
                translation = word_data.get('translation', '')
                message += f"в””в”Ђ {i}. {word} [{transcription}] - {translation}\n"
            else:
                # Р”Р»СЏ РѕР±СЂР°С‚РЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё СЃРѕ СЃС‚Р°СЂС‹Рј С„РѕСЂРјР°С‚РѕРј
                message += f"в””в”Ђ {i}. {word_data}\n"

        message += f"""
рџ”¤ Р“СЂР°РјРјР°С‚РёРєР°:
в””в”Ђ {current_lesson.get('grammar', '')}

вњЌпёЏ РџСЂР°РєС‚РёС‡РµСЃРєРѕРµ Р·Р°РґР°РЅРёРµ:
в””в”Ђ {current_lesson.get('practice', '')}

"""
        if 'pronunciation' in current_lesson:
            message += f"""
рџЋµ РџСЂРѕСЃР»СѓС€Р°Р№С‚Рµ РїСЂР°РІРёР»СЊРЅРѕРµ РїСЂРѕРёР·РЅРѕС€РµРЅРёРµ
в””в”Ђ {time_emoji.get(selected_time, '')} РЈСЂРѕРє РґР»СЏ РїРµСЂРёРѕРґР°: {time_names.get(selected_time, '')} СѓСЂРѕРє
в””в”Ђ РџРѕРІС‚РѕСЂСЏР№С‚Рµ РІСЃР»СѓС… РґР»СЏ Р»СѓС‡С€РµРіРѕ Р·Р°РїРѕРјРёРЅР°РЅРёСЏ!
"""
        
        message += "\nвЏ° Р’С‹Р±РµСЂРёС‚Рµ РІСЂРµРјСЏ РґРЅСЏ РёР»Рё РїРµСЂРµР№РґРёС‚Рµ Рє СЃР»РµРґСѓСЋС‰РµРјСѓ СѓСЂРѕРєСѓ"
        
        # РћР±РЅРѕРІР»СЏРµРј РёР»Рё РѕС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ
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
        
        # Р•СЃР»Рё РµСЃС‚СЊ Р°СѓРґРёРѕ РґР»СЏ РїСЂРѕРёР·РЅРѕС€РµРЅРёСЏ, РїРѕР»СѓС‡Р°РµРј Рё РѕС‚РїСЂР°РІР»СЏРµРј РµРіРѕ
        if 'pronunciation' in current_lesson and 'text' in current_lesson['pronunciation']:
            try:
                audio_data = await get_pronunciation_audio(current_lesson['pronunciation']['text'])
                if audio_data:
                    caption = f"""
рџЋµ РџСЂРѕСЃР»СѓС€Р°Р№С‚Рµ РїСЂР°РІРёР»СЊРЅРѕРµ РїСЂРѕРёР·РЅРѕС€РµРЅРёРµ
в””в”Ђ {time_emoji.get(selected_time, '')} РЈСЂРѕРє РґР»СЏ РїРµСЂРёРѕРґР°: {time_names.get(selected_time, '')} СѓСЂРѕРє
в””в”Ђ РџРѕРІС‚РѕСЂСЏР№С‚Рµ РІСЃР»СѓС… РґР»СЏ Р»СѓС‡С€РµРіРѕ Р·Р°РїРѕРјРёРЅР°РЅРёСЏ!"""
                    sent_message = await context.bot.send_voice(
                        chat_id=update.effective_chat.id,
                        voice=io.BytesIO(audio_data),
                        caption=caption
                    )
                    # РЎРѕС…СЂР°РЅСЏРµРј ID РѕС‚РїСЂР°РІР»РµРЅРЅРѕРіРѕ РіРѕР»РѕСЃРѕРІРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ
                    context.user_data['last_voice_message_id'] = sent_message.message_id
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ Р°СѓРґРёРѕ: {str(e)}")
                
    except (KeyError, TypeError) as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё СѓСЂРѕРєР°: {str(e)}, level={user_level}, day={current_day}, time={selected_time}")
        error_message = f"""
вљ пёЏ *РЈ РІР°СЃ СѓР¶Рµ РµСЃС‚СЊ Р°РєС‚РёРІРЅС‹Р№ РїР»Р°РЅ РѕР±СѓС‡РµРЅРёСЏ!*

*Р’Р°С€ С‚РµРєСѓС‰РёР№ РїР»Р°РЅ:*
вЂў РЈСЂРѕРІРµРЅСЊ: {user_level} {get_level_emoji(user_level)}
вЂў Р”РµРЅСЊ: {current_day} РёР· 14 рџ“…
вЂў РџРѕСЃР»РµРґРЅРёР№ СѓСЂРѕРє: {user_data.get('last_lesson_date')} рџ“†

РџР»Р°РЅ РѕР±СѓС‡РµРЅРёСЏ РЅРµР»СЊР·СЏ РёР·РјРµРЅРёС‚СЊ РґРѕ Р·Р°РІРµСЂС€РµРЅРёСЏ С‚РµРєСѓС‰РµРіРѕ РєСѓСЂСЃР°
"""
        if query:
            await query.edit_message_text(error_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(error_message, parse_mode='Markdown')
            
    return SHOWING_LESSON

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° РІС‹Р±РѕСЂР° РІСЂРµРјРµРЅРё РґРЅСЏ"""
    query = update.callback_query
    if not query:
        return SHOWING_LESSON
    await query.answer()
    
    try:
        # РџРѕР»СѓС‡Р°РµРј РІС‹Р±СЂР°РЅРЅРѕРµ РІСЂРµРјСЏ РґРЅСЏ РёР· callback_data
        if ":" in query.data:
            time_of_day = query.data.split(":")[1]
        else:
            time_of_day = query.data.split("_")[1]
        
        # РџСЂРѕРІРµСЂСЏРµРј РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚СЊ РІСЂРµРјРµРЅРё РґРЅСЏ
        if time_of_day not in ["morning", "afternoon", "evening"]:
            logger.error(f"вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅРѕРµ РІСЂРµРјСЏ РґРЅСЏ: {time_of_day}")
            return SHOWING_LESSON
        
        # РћР±РЅРѕРІР»СЏРµРј РІСЂРµРјСЏ РґРЅСЏ РІ РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        context.user_data['time_of_day'] = time_of_day
        
        await show_daily_lesson(update, context)
    except Exception as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ РІС‹Р±РѕСЂР° РІСЂРµРјРµРЅРё: {e}")
        return SHOWING_LESSON
    
    return SHOWING_LESSON

async def next_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРµСЂРµС…РѕРґ Рє СЃР»РµРґСѓСЋС‰РµРјСѓ СѓСЂРѕРєСѓ"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not can_access_next_lesson(user_id):
        # РџРѕР»СѓС‡Р°РµРј РІСЂРµРјСЏ РґРѕ СЃР»РµРґСѓСЋС‰РµРіРѕ СѓСЂРѕРєР°
        user_data = get_user_data(user_id)
        last_lesson_date = datetime.fromisoformat(user_data.get('last_lesson_date', '2000-01-01'))
        next_lesson_time = last_lesson_date + timedelta(days=1)
        time_left = next_lesson_time - datetime.now()
        hours_left = int(time_left.total_seconds() / 3600)
        minutes_left = int((time_left.total_seconds() % 3600) / 60)
        
        message = f"""
вЏі *РЎР»РµРґСѓСЋС‰РёР№ СѓСЂРѕРє РїРѕРєР° РЅРµРґРѕСЃС‚СѓРїРµРЅ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

вЊ›пёЏ *Р”Рѕ СЃР»РµРґСѓСЋС‰РµРіРѕ СѓСЂРѕРєР° РѕСЃС‚Р°Р»РѕСЃСЊ:*
рџ•ђ {hours_left} С‡Р°СЃРѕРІ Рё {minutes_left} РјРёРЅСѓС‚

рџ’Ў *Р РµРєРѕРјРµРЅРґР°С†РёРё:*
вЂў РџРѕРІС‚РѕСЂРёС‚Рµ РјР°С‚РµСЂРёР°Р» С‚РµРєСѓС‰РµРіРѕ СѓСЂРѕРєР°
вЂў Р’С‹РїРѕР»РЅРёС‚Рµ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ
вЂў РџСЂР°РєС‚РёРєСѓР№С‚Рµ РЅРѕРІС‹Рµ СЃР»РѕРІР°
вЂў РЎР»СѓС€Р°Р№С‚Рµ Р°СѓРґРёРѕ РјР°С‚РµСЂРёР°Р»С‹

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вњЁ Р’РѕР·РІСЂР°С‰Р°Р№С‚РµСЃСЊ Р·Р°РІС‚СЂР° РґР»СЏ РїСЂРѕРґРѕР»Р¶РµРЅРёСЏ РѕР±СѓС‡РµРЅРёСЏ!
"""
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("рџ”„ Р’РµСЂРЅСѓС‚СЊСЃСЏ Рє С‚РµРєСѓС‰РµРјСѓ СѓСЂРѕРєСѓ", callback_data="return_current")
            ]])
        )
        return SHOWING_LESSON
    
    # РћР±РЅРѕРІР»СЏРµРј РґРµРЅСЊ Рё РґР°С‚Сѓ РїРѕСЃР»РµРґРЅРµРіРѕ СѓСЂРѕРєР°
    current_day = int(context.user_data.get('day', 1))
    context.user_data['day'] = current_day + 1
    
    if context.user_data['day'] > 14:
        completion_message = """
рџЋ‰ *РџРѕР·РґСЂР°РІР»СЏРµРј СЃ Р·Р°РІРµСЂС€РµРЅРёРµРј РєСѓСЂСЃР°!* рџЋ‰
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

вњЁ Р’С‹ СѓСЃРїРµС€РЅРѕ РїСЂРѕС€Р»Рё 14-РґРЅРµРІРЅС‹Р№ РєСѓСЂСЃ Р°РЅРіР»РёР№СЃРєРѕРіРѕ СЏР·С‹РєР°! 

рџ“Љ *Р’Р°С€Рё РґРѕСЃС‚РёР¶РµРЅРёСЏ:*
рџ“љ РР·СѓС‡РµРЅРѕ РјРЅРѕР¶РµСЃС‚РІРѕ РЅРѕРІС‹С… СЃР»РѕРІ
рџ“ќ РћСЃРІРѕРµРЅС‹ РІР°Р¶РЅС‹Рµ РіСЂР°РјРјР°С‚РёС‡РµСЃРєРёРµ С‚РµРјС‹
рџЋ§ РЈР»СѓС‡С€РµРЅРѕ РїСЂРѕРёР·РЅРѕС€РµРЅРёРµ
рџ’­ РџРѕР»СѓС‡РµРЅР° РїСЂР°РєС‚РёРєР° РІ СЂР°Р·РіРѕРІРѕСЂРЅРѕР№ СЂРµС‡Рё

рџЊџ *Р§С‚Рѕ РґР°Р»СЊС€Рµ?*
вЂў РџСЂРѕРґРѕР»Р¶Р°Р№С‚Рµ РїСЂР°РєС‚РёРєРѕРІР°С‚СЊ СЏР·С‹Рє
вЂў РЎРјРѕС‚СЂРёС‚Рµ С„РёР»СЊРјС‹ РЅР° Р°РЅРіР»РёР№СЃРєРѕРј
вЂў Р§РёС‚Р°Р№С‚Рµ РєРЅРёРіРё Рё СЃС‚Р°С‚СЊРё
вЂў РћР±С‰Р°Р№С‚РµСЃСЊ СЃ РЅРѕСЃРёС‚РµР»СЏРјРё СЏР·С‹РєР°

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
рџ”„ Р”Р»СЏ РЅР°С‡Р°Р»Р° РЅРѕРІРѕРіРѕ РєСѓСЂСЃР° РёСЃРїРѕР»СЊР·СѓР№С‚Рµ /start

_Р–РµР»Р°РµРј РґР°Р»СЊРЅРµР№С€РёС… СѓСЃРїРµС…РѕРІ РІ РёР·СѓС‡РµРЅРёРё Р°РЅРіР»РёР№СЃРєРѕРіРѕ СЏР·С‹РєР°!_ рџљЂ
"""
        # РћС‡РёС‰Р°РµРј РґР°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        update_user_data(user_id, {})
        
        await query.edit_message_text(
            completion_message,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # РћР±РЅРѕРІР»СЏРµРј РґР°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    user_data = context.user_data.copy()
    user_data['last_lesson_date'] = datetime.now().isoformat()
    update_user_data(user_id, user_data)
    
    # РћР±РЅРѕРІР»СЏРµРј current_day РІ РєРѕРЅС‚РµРєСЃС‚Рµ РґР»СЏ РїСЂР°РІРёР»СЊРЅРѕРіРѕ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ СѓСЂРѕРєР°
    context.user_data['current_day'] = context.user_data['day']
    
    await show_daily_lesson(update, context)
    return SHOWING_LESSON

async def return_to_current_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Р’РѕР·РІСЂР°С‚ Рє С‚РµРєСѓС‰РµРјСѓ СѓСЂРѕРєСѓ"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    # РџРѕР»СѓС‡Р°РµРј С‚РµРєСѓС‰РµРµ РІСЂРµРјСЏ РґРЅСЏ РёР· РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    time_of_day = user_data.get('time_of_day', 'morning')
    
    # РћР±РЅРѕРІР»СЏРµРј callback_data РґР»СЏ РїСЂР°РІРёР»СЊРЅРѕРіРѕ РІСЂРµРјРµРЅРё РґРЅСЏ
    context.user_data['callback_query'] = f"time:{time_of_day}"
    
    await show_daily_lesson(update, context)
    return SHOWING_LESSON

async def activate_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РђРєС‚РёРІР°С†РёСЏ РґРѕСЃС‚СѓРїР° Рє РєСѓСЂСЃСѓ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРј"""
    # РџСЂРѕРІРµСЂСЏРµРј, СЏРІР»СЏРµС‚СЃСЏ Р»Рё РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРј
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text(
            "вќЊ РЈ РІР°СЃ РЅРµС‚ РїСЂР°РІ РґР»СЏ РІС‹РїРѕР»РЅРµРЅРёСЏ СЌС‚РѕР№ РєРѕРјР°РЅРґС‹.",
            parse_mode='Markdown'
        )
        return

    # РџСЂРѕРІРµСЂСЏРµРј С„РѕСЂРјР°С‚ РєРѕРјР°РЅРґС‹
    try:
        # Р¤РѕСЂРјР°С‚: /activate USER_ID LEVEL
        _, user_id, level = update.message.text.split()
        user_id = int(user_id)
    except ValueError:
        await update.message.reply_text(
            "вќЊ *РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РєРѕРјР°РЅРґС‹*\nРСЃРїРѕР»СЊР·СѓР№С‚Рµ: `/activate USER_ID LEVEL`\nРџСЂРёРјРµСЂ: `/activate 123456789 A1`",
            parse_mode='Markdown'
        )
        return

    # РџСЂРѕРІРµСЂСЏРµРј РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚СЊ СѓСЂРѕРІРЅСЏ
    if level not in LEVELS:
        await update.message.reply_text(
            f"вќЊ *РќРµРІРµСЂРЅС‹Р№ СѓСЂРѕРІРµРЅСЊ*\nР”РѕСЃС‚СѓРїРЅС‹Рµ СѓСЂРѕРІРЅРё: {', '.join(LEVELS.keys())}",
            parse_mode='Markdown'
        )
        return

    # РђРєС‚РёРІРёСЂСѓРµРј РґРѕСЃС‚СѓРї Рє РєСѓСЂСЃСѓ
    user_data = {
        'level': level,
        'current_day': 1,
        'day': 1,
        'max_day': 1,  # Р”РѕР±Р°РІР»СЏРµРј РѕС‚СЃР»РµР¶РёРІР°РЅРёРµ РјР°РєСЃРёРјР°Р»СЊРЅРѕРіРѕ РґРЅСЏ
        'last_lesson_date': (datetime.now() - timedelta(days=1)).isoformat(),  # РџРѕР·РІРѕР»СЏРµС‚ РЅР°С‡Р°С‚СЊ РѕР±СѓС‡РµРЅРёРµ СЃСЂР°Р·Сѓ
        'time_of_day': 'morning'
    }
    update_user_data(user_id, user_data)

    # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ
    await update.message.reply_text(
        f"""
вњ… *Р”РѕСЃС‚СѓРї СѓСЃРїРµС€РЅРѕ Р°РєС‚РёРІРёСЂРѕРІР°РЅ*

*Р”РµС‚Р°Р»Рё:*
вЂў ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ: `{user_id}`
вЂў РЈСЂРѕРІРµРЅСЊ РєСѓСЂСЃР°: {level} {get_level_emoji(level)}
вЂў РќР°С‡Р°Р»СЊРЅС‹Р№ РґРµРЅСЊ: 1
вЂў Р”РѕСЃС‚СѓРї Рє СѓСЂРѕРєР°Рј: РђРєС‚РёРІРёСЂРѕРІР°РЅ

РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РјРѕР¶РµС‚ РЅР°С‡Р°С‚СЊ РѕР±СѓС‡РµРЅРёРµ, РѕС‚РїСЂР°РІРёРІ РєРѕРјР°РЅРґСѓ /start
""",
        parse_mode='Markdown'
    )

    # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"""
рџЋ‰ *РџРѕР·РґСЂР°РІР»СЏРµРј! Р’Р°С€ РєСѓСЂСЃ СѓСЃРїРµС€РЅРѕ Р°РєС‚РёРІРёСЂРѕРІР°РЅ!* рџЋ‰

*Р”РµС‚Р°Р»Рё РІР°С€РµРіРѕ РєСѓСЂСЃР°:*
вЂў РЈСЂРѕРІРµРЅСЊ: {level} {get_level_emoji(level)}
вЂў Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: 14 РґРЅРµР№
вЂў Р¤РѕСЂРјР°С‚: 3 СѓСЂРѕРєР° РєР°Р¶РґС‹Р№ РґРµРЅСЊ (СѓС‚СЂРѕ/РґРµРЅСЊ/РІРµС‡РµСЂ)
вЂў Р”РѕСЃС‚СѓРї: РџРѕР»РЅС‹Р№ РґРѕСЃС‚СѓРї РєРѕ РІСЃРµРј РјР°С‚РµСЂРёР°Р»Р°Рј

*Р§С‚Рѕ РґР°Р»СЊС€Рµ?*
1. РћС‚РїСЂР°РІСЊС‚Рµ РєРѕРјР°РЅРґСѓ /start
2. РќР°С‡РЅРёС‚Рµ РѕР±СѓС‡РµРЅРёРµ СЃ РїРµСЂРІРѕРіРѕ СѓСЂРѕРєР°
3. Р—Р°РЅРёРјР°Р№С‚РµСЃСЊ РІ СѓРґРѕР±РЅРѕРµ РґР»СЏ РІР°СЃ РІСЂРµРјСЏ

*РћСЃРѕР±РµРЅРЅРѕСЃС‚Рё РєСѓСЂСЃР°:*
вЂў РРЅС‚РµСЂР°РєС‚РёРІРЅС‹Рµ СѓСЂРѕРєРё
вЂў РђСѓРґРёРѕ СЃ РїСЂРѕРёР·РЅРѕС€РµРЅРёРµРј
вЂў РџСЂР°РєС‚РёС‡РµСЃРєРёРµ Р·Р°РґР°РЅРёСЏ
вЂў Р“СЂР°РјРјР°С‚РёРєР° Рё РЅРѕРІС‹Рµ СЃР»РѕРІР°

Р–РµР»Р°РµРј СѓСЃРїРµС…РѕРІ РІ РёР·СѓС‡РµРЅРёРё Р°РЅРіР»РёР№СЃРєРѕРіРѕ СЏР·С‹РєР°! рџ“љвњЁ
""",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            f"вљ пёЏ *РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ:* РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ СѓРІРµРґРѕРјР»РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ.\nР’РѕР·РјРѕР¶РЅРѕ, РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°С‡Р°Р» РґРёР°Р»РѕРі СЃ Р±РѕС‚РѕРј.",
            parse_mode='Markdown'
        )

async def handle_homework_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° Р·Р°РїСЂРѕСЃР° РЅР° РѕС‚РїСЂР°РІРєСѓ РґРѕРјР°С€РЅРµРіРѕ Р·Р°РґР°РЅРёСЏ"""
    query = update.callback_query
    await query.answer()
    
    time_of_day = query.data.split('_')[2] if len(query.data.split('_')) > 2 else 'morning'
    level = context.user_data['level']
    day = context.user_data['day']
    
    # РЎРѕС…СЂР°РЅСЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ С‚РµРєСѓС‰РµРј Р·Р°РґР°РЅРёРё РІ РєРѕРЅС‚РµРєСЃС‚Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    context.user_data['homework_info'] = {
        'level': level,
        'day': day,
        'time_of_day': time_of_day
    }
    
    await query.edit_message_text(
        f"""
рџ“ќ *РћС‚РїСЂР°РІРєР° РґРѕРјР°С€РЅРµРіРѕ Р·Р°РґР°РЅРёСЏ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџЋ¤ Р—Р°РїРёС€РёС‚Рµ РіРѕР»РѕСЃРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РІС‹РїРѕР»РЅРµРЅРЅС‹Рј Р·Р°РґР°РЅРёРµРј
Рё РѕС‚РїСЂР°РІСЊС‚Рµ РµРіРѕ РІ СЌС‚РѕС‚ С‡Р°С‚.

*РРЅС„РѕСЂРјР°С†РёСЏ РѕР± СѓСЂРѕРєРµ:*
рџ“љ РЈСЂРѕРІРµРЅСЊ: {level} {get_level_emoji(level)}
рџ“… Р”РµРЅСЊ: {day} РёР· 14
вЏ° Р’СЂРµРјСЏ: {time_of_day}

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вљ пёЏ _РћС‚РїСЂР°РІСЊС‚Рµ РіРѕР»РѕСЃРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РїСЂСЏРјРѕ СЃРµР№С‡Р°СЃ._
_Р‘РѕС‚ РѕР¶РёРґР°РµС‚ РІР°С€Сѓ Р·Р°РїРёСЃСЊ..._
""",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("рџ”™ Р’РµСЂРЅСѓС‚СЊСЃСЏ Рє СѓСЂРѕРєСѓ", callback_data=f"time_{time_of_day}")
        ]])
    )
    return WAITING_HOMEWORK

async def handle_homework_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° РїРѕР»СѓС‡РµРЅРЅРѕРіРѕ РіРѕР»РѕСЃРѕРІРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ СЃ РґРѕРјР°С€РЅРёРј Р·Р°РґР°РЅРёРµРј"""
    user_id = update.effective_user.id
    logger.info(f"рџ“ќ РџРѕР»СѓС‡РµРЅРѕ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ РѕС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id}")
    
    if not update.message.voice:
        await update.message.reply_text(
            """
вќЊ *РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ Р·Р°РґР°РЅРёСЏ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РѕС‚РїСЂР°РІСЊС‚Рµ РіРѕР»РѕСЃРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
СЃ РІС‹РїРѕР»РЅРµРЅРЅС‹Рј Р·Р°РґР°РЅРёРµРј.

рџ’Ў *РљР°Рє Р·Р°РїРёСЃР°С‚СЊ РіРѕР»РѕСЃРѕРІРѕРµ:*
1пёЏвѓЈ РќР°Р¶РјРёС‚Рµ Рё СѓРґРµСЂР¶РёРІР°Р№С‚Рµ РєРЅРѕРїРєСѓ РјРёРєСЂРѕС„РѕРЅР°
2пёЏвѓЈ Р—Р°РїРёС€РёС‚Рµ РІР°С€ РѕС‚РІРµС‚
3пёЏвѓЈ РћС‚РїСѓСЃС‚РёС‚Рµ РєРЅРѕРїРєСѓ РґР»СЏ РѕС‚РїСЂР°РІРєРё
""",
            parse_mode='Markdown'
        )
        return WAITING_HOMEWORK
    
    homework_info = context.user_data.get('homework_info', {})
    if not homework_info:
        await update.message.reply_text(
            """
вќЊ *РћС€РёР±РєР° РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ Р·Р°РґР°РЅРёСЏ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РЅР°С‡РЅРёС‚Рµ РѕС‚РїСЂР°РІРєСѓ Р·Р°РґР°РЅРёСЏ Р·Р°РЅРѕРІРѕ.

рџ”„ Р’РµСЂРЅРёС‚РµСЃСЊ Рє СѓСЂРѕРєСѓ Рё РЅР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ
"РћС‚РїСЂР°РІРёС‚СЊ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ"
""",
            parse_mode='Markdown'
        )
        return SHOWING_LESSON
    
    # РџРѕР»СѓС‡Р°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ С„Р°Р№Р»Рµ
    file_id = update.message.voice.file_id
    
    try:
        # РЎРѕР·РґР°РµРј СЃРѕРѕР±С‰РµРЅРёРµ РґР»СЏ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°
        admin_message = f"""
рџ“¬ *РќРѕРІРѕРµ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ‘¤ *РРЅС„РѕСЂРјР°С†РёСЏ Рѕ СЃС‚СѓРґРµРЅС‚Рµ:*
вЂў ID: `{update.effective_user.id}`
вЂў РРјСЏ: {update.effective_user.first_name}
вЂў Username: @{update.effective_user.username or 'РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚'}

рџ“љ *РРЅС„РѕСЂРјР°С†РёСЏ РѕР± СѓСЂРѕРєРµ:*
вЂў РЈСЂРѕРІРµРЅСЊ: {homework_info['level']} {get_level_emoji(homework_info['level'])}
вЂў Р”РµРЅСЊ: {homework_info['day']} РёР· 14
вЂў Р’СЂРµРјСЏ: {homework_info['time_of_day']}

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вњЌпёЏ РћС†РµРЅРёС‚Рµ РІС‹РїРѕР»РЅРµРЅРёРµ Р·Р°РґР°РЅРёСЏ:
"""
        # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=admin_message,
            parse_mode='Markdown'
        )
        
        # РћС‚РїСЂР°РІР»СЏРµРј РіРѕР»РѕСЃРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ
        await context.bot.send_voice(
            chat_id=ADMIN_USER_ID,
            voice=file_id,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("рџ‘Ќ РћРґРѕР±СЂРёС‚СЊ", callback_data=f"hw_approve_{update.effective_user.id}"),
                    InlineKeyboardButton("рџ‘Ћ РћС‚РєР»РѕРЅРёС‚СЊ", callback_data=f"hw_reject_{update.effective_user.id}")
                ]
            ])
        )
        
        # РћС‚РїСЂР°РІР»СЏРµРј РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ СЃС‚СѓРґРµРЅС‚Сѓ
        await update.message.reply_text(
            """
вњ… *Р”РѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ РѕС‚РїСЂР°РІР»РµРЅРѕ!*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ“ќ Р’Р°С€Рµ Р·Р°РґР°РЅРёРµ РѕС‚РїСЂР°РІР»РµРЅРѕ РЅР° РїСЂРѕРІРµСЂРєСѓ
рџ‘ЁвЂЌрџЏ« РџСЂРµРїРѕРґР°РІР°С‚РµР»СЊ РїСЂРѕРІРµСЂРёС‚ РµРіРѕ Рё РґР°СЃС‚ РѕР±СЂР°С‚РЅСѓСЋ СЃРІСЏР·СЊ
рџ”” Р’С‹ РїРѕР»СѓС‡РёС‚Рµ СѓРІРµРґРѕРјР»РµРЅРёРµ СЃ СЂРµР·СѓР»СЊС‚Р°С‚РѕРј

рџ’Ў *Р§С‚Рѕ РґР°Р»СЊС€Рµ?*
вЂў РџСЂРѕРґРѕР»Р¶Р°Р№С‚Рµ РѕР±СѓС‡РµРЅРёРµ
вЂў РР·СѓС‡Р°Р№С‚Рµ РЅРѕРІС‹Рµ РјР°С‚РµСЂРёР°Р»С‹
вЂў РџСЂР°РєС‚РёРєСѓР№С‚Рµ СЏР·С‹Рє

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
рџ”„ РќР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ РЅРёР¶Рµ, С‡С‚РѕР±С‹ РІРµСЂРЅСѓС‚СЊСЃСЏ Рє СѓСЂРѕРєСѓ
""",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("рџ”™ Р’РµСЂРЅСѓС‚СЊСЃСЏ Рє СѓСЂРѕРєСѓ", callback_data=f"time_{homework_info['time_of_day']}")
            ]])
        )
        
        return SHOWING_LESSON
        
    except telegram.error.Unauthorized:
        logger.error("РћС€РёР±РєР°: Р‘РѕС‚ РЅРµ РјРѕР¶РµС‚ РѕС‚РїСЂР°РІРёС‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ (Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ)")
        await update.message.reply_text(
            """
вќЊ *РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ Р·Р°РґР°РЅРёСЏ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

РџСЂРѕРёР·РѕС€Р»Р° С‚РµС…РЅРёС‡РµСЃРєР°СЏ РѕС€РёР±РєР°.
РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.

рџ’Ў РџСЂРё РїРѕРІС‚РѕСЂРµРЅРёРё РѕС€РёР±РєРё РѕР±СЂР°С‚РёС‚РµСЃСЊ
Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ @renatblizkiy
""",
            parse_mode='Markdown'
        )
        return WAITING_HOMEWORK
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ РґРѕРјР°С€РЅРµРіРѕ Р·Р°РґР°РЅРёСЏ: {str(e)}")
        await update.message.reply_text(
            """
вќЊ *РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ Р·Р°РґР°РЅРёСЏ*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

РџСЂРѕРёР·РѕС€Р»Р° С‚РµС…РЅРёС‡РµСЃРєР°СЏ РѕС€РёР±РєР°.
РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.

рџ’Ў РџСЂРё РїРѕРІС‚РѕСЂРµРЅРёРё РѕС€РёР±РєРё РѕР±СЂР°С‚РёС‚РµСЃСЊ
Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ @renatblizkiy
""",
            parse_mode='Markdown'
        )
        return WAITING_HOMEWORK

async def handle_homework_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° РѕС†РµРЅРєРё РґРѕРјР°С€РЅРµРіРѕ Р·Р°РґР°РЅРёСЏ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРј"""
    query = update.callback_query
    admin_id = query.from_user.id
    
    if admin_id != ADMIN_USER_ID:
        logger.warning(f"вљ пёЏ РџРѕРїС‹С‚РєР° РЅРµСЃР°РЅРєС†РёРѕРЅРёСЂРѕРІР°РЅРЅРѕРіРѕ РґРѕСЃС‚СѓРїР° Рє РѕС†РµРЅРєРµ Р”Р— РѕС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {admin_id}")
        await query.answer("вќЊ РЈ РІР°СЃ РЅРµС‚ РїСЂР°РІ РґР»СЏ РІС‹РїРѕР»РЅРµРЅРёСЏ СЌС‚РѕРіРѕ РґРµР№СЃС‚РІРёСЏ")
        return
    
    # РџРѕР»СѓС‡Р°РµРј РґРµР№СЃС‚РІРёРµ (approve/reject) Рё ID СЃС‚СѓРґРµРЅС‚Р° РёР· callback_data
    action, student_id = query.data.split('_')[1:3]
    student_id = int(student_id)
    
    # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ СЃС‚СѓРґРµРЅС‚Сѓ РІ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ РѕС†РµРЅРєРё
    if action == 'approve':
        message = """
вњ… *Р”РѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ РїСЂРѕРІРµСЂРµРЅРѕ!*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџЊџ РћС‚Р»РёС‡РЅР°СЏ СЂР°Р±РѕС‚Р°! РџСЂРµРїРѕРґР°РІР°С‚РµР»СЊ РѕРґРѕР±СЂРёР»
РІР°С€Рµ РІС‹РїРѕР»РЅРµРЅРёРµ Р·Р°РґР°РЅРёСЏ.

рџ’Ў *Р РµРєРѕРјРµРЅРґР°С†РёРё:*
вЂў РџСЂРѕРґРѕР»Р¶Р°Р№С‚Рµ РІ С‚РѕРј Р¶Рµ РґСѓС…Рµ
вЂў РџСЂР°РєС‚РёРєСѓР№С‚Рµ РЅРѕРІС‹Рµ СЃР»РѕРІР°
вЂў Р’С‹РїРѕР»РЅСЏР№С‚Рµ РІСЃРµ Р·Р°РґР°РЅРёСЏ
вЂў РЎР»РµРґРёС‚Рµ Р·Р° РїСЂРѕРёР·РЅРѕС€РµРЅРёРµРј

вњЁ РЈСЃРїРµС…РѕРІ РІ РґР°Р»СЊРЅРµР№С€РµРј РѕР±СѓС‡РµРЅРёРё!
"""
    else:
        message = """
вљ пёЏ *Р”РѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ С‚СЂРµР±СѓРµС‚ РґРѕСЂР°Р±РѕС‚РєРё*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ’Ў *Р РµРєРѕРјРµРЅРґР°С†РёРё РїСЂРµРїРѕРґР°РІР°С‚РµР»СЏ:*
вЂў Р’РЅРёРјР°С‚РµР»СЊРЅРµРµ СЃР»РµРґРёС‚Рµ Р·Р° РїСЂРѕРёР·РЅРѕС€РµРЅРёРµРј
вЂў РџРѕРІС‚РѕСЂРёС‚Рµ РіСЂР°РјРјР°С‚РёС‡РµСЃРєРёРµ РїСЂР°РІРёР»Р°
вЂў РџСЂР°РєС‚РёРєСѓР№С‚Рµ РЅРѕРІС‹Рµ СЃР»РѕРІР°
вЂў Р—Р°РїРёС€РёС‚Рµ Р·Р°РґР°РЅРёРµ РµС‰Рµ СЂР°Р·

рџ“ќ *Р§С‚Рѕ РґРµР»Р°С‚СЊ РґР°Р»СЊС€Рµ:*
1пёЏвѓЈ Р’РµСЂРЅРёС‚РµСЃСЊ Рє РјР°С‚РµСЂРёР°Р»Р°Рј СѓСЂРѕРєР°
2пёЏвѓЈ РР·СѓС‡РёС‚Рµ СЂРµРєРѕРјРµРЅРґР°С†РёРё
3пёЏвѓЈ Р—Р°РїРёС€РёС‚Рµ Р·Р°РґР°РЅРёРµ Р·Р°РЅРѕРІРѕ
4пёЏвѓЈ РћС‚РїСЂР°РІСЊС‚Рµ РЅР° РїСЂРѕРІРµСЂРєСѓ

вњЁ РњС‹ РІРµСЂРёРј РІ РІР°С€ СѓСЃРїРµС…!
"""
    
    try:
        # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ СЃС‚СѓРґРµРЅС‚Сѓ
        await context.bot.send_message(
            chat_id=student_id,
            text=message,
            parse_mode='Markdown'
        )
        
        # РЈРґР°Р»СЏРµРј РєРЅРѕРїРєРё РёР· СЃРѕРѕР±С‰РµРЅРёСЏ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("вњ… РћС†РµРЅРєР° РѕС‚РїСЂР°РІР»РµРЅР° СЃС‚СѓРґРµРЅС‚Сѓ")
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ РѕС†РµРЅРєРё: {e}")
        await query.answer("вќЊ РџСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ РѕС†РµРЅРєРё")

async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° РїСЂРµ-С‡РµРєР°СѓС‚Р° РїР»Р°С‚РµР¶Р°"""
    query = update.pre_checkout_query
    await query.answer(ok=True)
    return PAYMENT

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° СѓСЃРїРµС€РЅРѕРіРѕ РїР»Р°С‚РµР¶Р°"""
    payment_info = update.message.successful_payment
    user_id = update.effective_user.id
    logger.info(f"вњ… РЈСЃРїРµС€РЅР°СЏ РѕРїР»Р°С‚Р° РѕС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id}")
    
    # РђРєС‚РёРІРёСЂСѓРµРј РєСѓСЂСЃ РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    level = context.user_data.get('temp_level')
    if not level:
        await update.message.reply_text(
            """
вќЊ *РћС€РёР±РєР° Р°РєС‚РёРІР°С†РёРё РєСѓСЂСЃР°*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РЅР°С‡РЅРёС‚Рµ СЂРµРіРёСЃС‚СЂР°С†РёСЋ Р·Р°РЅРѕРІРѕ,
РёСЃРїРѕР»СЊР·СѓСЏ РєРѕРјР°РЅРґСѓ /start

рџ’Ў РџСЂРё РїРѕРІС‚РѕСЂРµРЅРёРё РѕС€РёР±РєРё РѕР±СЂР°С‚РёС‚РµСЃСЊ
Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ @renatblizkiy
""",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # РЎРѕС…СЂР°РЅСЏРµРј РґР°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    user_data = {
        'level': level,
        'day': 1,
        'max_day': 1,  # Р”РѕР±Р°РІР»СЏРµРј РѕС‚СЃР»РµР¶РёРІР°РЅРёРµ РјР°РєСЃРёРјР°Р»СЊРЅРѕРіРѕ РґРЅСЏ
        'last_lesson_date': (datetime.now() - timedelta(days=1)).isoformat(),
        'time_of_day': 'morning'
    }
    update_user_data(user_id, user_data)
    context.user_data.update(user_data)
    
    # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РѕР± СѓСЃРїРµС€РЅРѕР№ Р°РєС‚РёРІР°С†РёРё
    success_message = f"""
рџЋ‰ *РџРѕР·РґСЂР°РІР»СЏРµРј! Р’Р°С€ РєСѓСЂСЃ Р°РєС‚РёРІРёСЂРѕРІР°РЅ!* рџЋ‰
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

рџ“љ *РРЅС„РѕСЂРјР°С†РёСЏ Рѕ РєСѓСЂСЃРµ:*
вЂў РЈСЂРѕРІРµРЅСЊ: {level} {get_level_emoji(level)}
вЂў Р”Р»РёС‚РµР»СЊРЅРѕСЃС‚СЊ: 14 РґРЅРµР№
вЂў Р¤РѕСЂРјР°С‚: 3 СѓСЂРѕРєР° РІ РґРµРЅСЊ
вЂў Р”РѕСЃС‚СѓРї: РџРѕР»РЅС‹Р№

вњЁ *Р§С‚Рѕ РІРєР»СЋС‡РµРЅРѕ:*
вЂў Р’СЃРµ РјР°С‚РµСЂРёР°Р»С‹ Рё СѓСЂРѕРєРё
вЂў РђСѓРґРёРѕ РѕС‚ РЅРѕСЃРёС‚РµР»РµР№ СЏР·С‹РєР°
вЂў РџСЂРѕРІРµСЂРєР° РґРѕРјР°С€РЅРёС… Р·Р°РґР°РЅРёР№
вЂў РџРѕРґРґРµСЂР¶РєР° РїСЂРµРїРѕРґР°РІР°С‚РµР»СЏ
вЂў РћС‚СЃР»РµР¶РёРІР°РЅРёРµ РїСЂРѕРіСЂРµСЃСЃР°

рџ’Ў *РљР°Рє РЅР°С‡Р°С‚СЊ РѕР±СѓС‡РµРЅРёРµ:*
1пёЏвѓЈ РќР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ "РќР°С‡Р°С‚СЊ РѕР±СѓС‡РµРЅРёРµ"
2пёЏвѓЈ Р’С‹Р±РµСЂРёС‚Рµ СѓРґРѕР±РЅРѕРµ РІСЂРµРјСЏ РґР»СЏ СѓСЂРѕРєР°
3пёЏвѓЈ РЎР»РµРґСѓР№С‚Рµ РёРЅСЃС‚СЂСѓРєС†РёСЏРј РІ СѓСЂРѕРєРµ
4пёЏвѓЈ Р’С‹РїРѕР»РЅСЏР№С‚Рµ РґРѕРјР°С€РЅРёРµ Р·Р°РґР°РЅРёСЏ

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вњЁ Р–РµР»Р°РµРј СѓСЃРїРµС…РѕРІ РІ РёР·СѓС‡РµРЅРёРё Р°РЅРіР»РёР№СЃРєРѕРіРѕ СЏР·С‹РєР°!
"""
    keyboard = [[InlineKeyboardButton("рџљЂ РќР°С‡Р°С‚СЊ РѕР±СѓС‡РµРЅРёРµ", callback_data="time:morning")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        success_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return SHOWING_LESSON

def create_lesson_navigation(current_day: int, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """РЎРѕР·РґР°РµС‚ РєР»Р°РІРёР°С‚СѓСЂСѓ РґР»СЏ РЅР°РІРёРіР°С†РёРё РїРѕ СѓСЂРѕРєР°Рј"""
    keyboard = [
        [
            InlineKeyboardButton("рџЊ… РЈС‚СЂРµРЅРЅРёР№ СѓСЂРѕРє", callback_data="time:morning"),
            InlineKeyboardButton("вЂпёЏ Р”РЅРµРІРЅРѕР№ СѓСЂРѕРє", callback_data="time:afternoon"),
        ],
        [
            InlineKeyboardButton("рџЊ™ Р’РµС‡РµСЂРЅРёР№ СѓСЂРѕРє", callback_data="time:evening")
        ],
        [InlineKeyboardButton("рџ“ќ РћС‚РїСЂР°РІРёС‚СЊ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ", callback_data=f"homework_{context.user_data.get('time_of_day', 'morning')}")]
    ]
    
    # Р”РѕР±Р°РІР»СЏРµРј РєРЅРѕРїРєРё РЅР°РІРёРіР°С†РёРё РїРѕ РґРЅСЏРј
    nav_buttons = []
    if current_day > 1:
        nav_buttons.append(InlineKeyboardButton("в¬…пёЏ Р”РµРЅСЊ РЅР°Р·Р°Рґ", callback_data="prev_day"))
    if current_day < 14:
        nav_buttons.append(InlineKeyboardButton("Р”РµРЅСЊ РІРїРµСЂРµРґ вћЎпёЏ", callback_data="next_day"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

def get_lesson_keyboard(time_of_day: str, current_day: int) -> InlineKeyboardMarkup:
    """РЎРѕР·РґР°РµС‚ РєР»Р°РІРёР°С‚СѓСЂСѓ РґР»СЏ РЅР°РІРёРіР°С†РёРё РїРѕ СѓСЂРѕРєР°Рј"""
    keyboard = [
        [
            InlineKeyboardButton("рџЊ… РЈС‚СЂРµРЅРЅРёР№ СѓСЂРѕРє", callback_data="time:morning"),
            InlineKeyboardButton("вЂпёЏ Р”РЅРµРІРЅРѕР№ СѓСЂРѕРє", callback_data="time:afternoon"),
        ],
        [
            InlineKeyboardButton("рџЊ™ Р’РµС‡РµСЂРЅРёР№ СѓСЂРѕРє", callback_data="time:evening")
        ]
    ]
    
    # Р”РѕР±Р°РІР»СЏРµРј РєРЅРѕРїРєСѓ РґРѕРјР°С€РЅРµРіРѕ Р·Р°РґР°РЅРёСЏ
    keyboard.append([InlineKeyboardButton("рџ“ќ РћС‚РїСЂР°РІРёС‚СЊ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ", callback_data=f"homework_{time_of_day}")])
    
    # Р”РѕР±Р°РІР»СЏРµРј РєРЅРѕРїРєРё РЅР°РІРёРіР°С†РёРё РїРѕ РґРЅСЏРј
    nav_buttons = []
    if current_day > 1:
        nav_buttons.append(InlineKeyboardButton("в¬…пёЏ РџСЂРµРґС‹РґСѓС‰РёР№ РґРµРЅСЊ", callback_data="prev_day"))
    if current_day < 14:
        nav_buttons.append(InlineKeyboardButton("РЎР»РµРґСѓСЋС‰РёР№ РґРµРЅСЊ вћЎпёЏ", callback_data="next_day"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

async def handle_prev_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РїРµСЂРµС…РѕРґР° Рє РїСЂРµРґС‹РґСѓС‰РµРјСѓ РґРЅСЋ"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    current_day = int(user_data.get('current_day', 1))
    max_day = int(user_data.get('max_day', current_day))  # РџРѕР»СѓС‡Р°РµРј РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№ РґРѕСЃС‚РёРіРЅСѓС‚С‹Р№ РґРµРЅСЊ
    time_of_day = user_data.get('time_of_day', 'morning')
    
    if current_day > 1:
        current_day -= 1
        user_data['current_day'] = current_day
        user_data['day'] = current_day
        # РЎРѕС…СЂР°РЅСЏРµРј РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№ РґРѕСЃС‚РёРіРЅСѓС‚С‹Р№ РґРµРЅСЊ
        user_data['max_day'] = max_day
        update_user_data(user_id, user_data)
        
        # РћР±РЅРѕРІР»СЏРµРј РґР°РЅРЅС‹Рµ РІ РєРѕРЅС‚РµРєСЃС‚Рµ
        context.user_data.update(user_data)
        
        await show_daily_lesson(update, context)
    else:
        await query.answer("вќЊ Р’С‹ СѓР¶Рµ РЅР° РїРµСЂРІРѕРј РґРЅРµ РѕР±СѓС‡РµРЅРёСЏ")
    return SHOWING_LESSON

async def handle_next_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РїРµСЂРµС…РѕРґР° Рє СЃР»РµРґСѓСЋС‰РµРјСѓ РґРЅСЋ"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    current_day = int(user_data.get('current_day', 1))
    max_day = int(user_data.get('max_day', current_day))
    time_of_day = user_data.get('time_of_day', 'morning')
    
    # Р•СЃР»Рё РїС‹С‚Р°РµРјСЃСЏ РїРµСЂРµР№С‚Рё Рє РЅРѕРІРѕРјСѓ РґРЅСЋ (РїСЂРµРІС‹С€Р°СЋС‰РµРјСѓ РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№)
    if current_day >= max_day:
        # РџСЂРѕРІРµСЂСЏРµРј, РїСЂРѕС€Р»Рѕ Р»Рё 24 С‡Р°СЃР° СЃ РїРѕСЃР»РµРґРЅРµРіРѕ СѓСЂРѕРєР°
        last_lesson_date = datetime.fromisoformat(user_data.get('last_lesson_date', '2000-01-01'))
        time_since_last_lesson = datetime.now() - last_lesson_date
        seconds_left = 24 * 3600 - time_since_last_lesson.total_seconds()
        
        if seconds_left > 0:
            hours_left = int(seconds_left // 3600)
            minutes_left = int((seconds_left % 3600) // 60)
            seconds = int(seconds_left % 60)
            
            keyboard = [
                [InlineKeyboardButton("рџ”„ Р’РµСЂРЅСѓС‚СЊСЃСЏ Рє С‚РµРєСѓС‰РµРјСѓ СѓСЂРѕРєСѓ", callback_data=f"time:{time_of_day}")],
                [InlineKeyboardButton("рџ“ќ РћС‚РїСЂР°РІРёС‚СЊ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ", callback_data=f"homework_{time_of_day}")]
            ]
            
            message = f"""
вЏі *Р”Рѕ СЃР»РµРґСѓСЋС‰РµРіРѕ СѓСЂРѕРєР° РѕСЃС‚Р°Р»РѕСЃСЊ:*
в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ

вЊ›пёЏ {hours_left:02d}:{minutes_left:02d}:{seconds:02d}

*Р’Р°С€ РїСЂРѕРіСЂРµСЃСЃ:*
рџ“љ РЈСЂРѕРІРµРЅСЊ: {user_data['level']} {get_level_emoji(user_data['level'])}
рџ“… РўРµРєСѓС‰РёР№ РґРµРЅСЊ: {current_day} РёР· 14
рџ“Љ РњР°РєСЃРёРјР°Р»СЊРЅС‹Р№ РґРµРЅСЊ: {max_day}

рџ’Ў *Р РµРєРѕРјРµРЅРґР°С†РёРё:*
вЂў РџРѕРІС‚РѕСЂРёС‚Рµ РјР°С‚РµСЂРёР°Р» С‚РµРєСѓС‰РµРіРѕ СѓСЂРѕРєР°
вЂў Р’С‹РїРѕР»РЅРёС‚Рµ РґРѕРјР°С€РЅРµРµ Р·Р°РґР°РЅРёРµ
вЂў РџСЂР°РєС‚РёРєСѓР№С‚Рµ РЅРѕРІС‹Рµ СЃР»РѕРІР°
вЂў РЎР»СѓС€Р°Р№С‚Рµ Р°СѓРґРёРѕ РјР°С‚РµСЂРёР°Р»С‹

в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ
вњЁ Р’РѕР·РІСЂР°С‰Р°Р№С‚РµСЃСЊ РїРѕР·Р¶Рµ РґР»СЏ РїСЂРѕРґРѕР»Р¶РµРЅРёСЏ РѕР±СѓС‡РµРЅРёСЏ!
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
        
        # РћР±РЅРѕРІР»СЏРµРј РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№ РґРѕСЃС‚РёРіРЅСѓС‚С‹Р№ РґРµРЅСЊ, РµСЃР»Рё С‚РµРєСѓС‰РёР№ РґРµРЅСЊ Р±РѕР»СЊС€Рµ
        if current_day > max_day:
            user_data['max_day'] = current_day
            user_data['last_lesson_date'] = datetime.now().isoformat()
        
        update_user_data(user_id, user_data)
        context.user_data.update(user_data)
        
        await show_daily_lesson(update, context)
    else:
        await query.answer("вќЊ Р’С‹ СѓР¶Рµ РЅР° РїРѕСЃР»РµРґРЅРµРј РґРЅРµ РѕР±СѓС‡РµРЅРёСЏ")
    return SHOWING_LESSON

def check_environment():
    """РџСЂРѕРІРµСЂСЏРµС‚ РЅР°Р»РёС‡РёРµ РІСЃРµС… РЅРµРѕР±С…РѕРґРёРјС‹С… С„Р°Р№Р»РѕРІ Рё РґРёСЂРµРєС‚РѕСЂРёР№"""
    try:
        # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ .env С„Р°Р№Р»Р°
        if not os.path.exists('.env'):
            logger.warning("вљ пёЏ Р¤Р°Р№Р» .env РЅРµ РЅР°Р№РґРµРЅ")
            
        # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ РґРёСЂРµРєС‚РѕСЂРёРё РґР»СЏ СЂРµР·РµСЂРІРЅС‹С… РєРѕРїРёР№
        Path(BACKUP_DIR).mkdir(exist_ok=True)
        logger.info("вњ… Р”РёСЂРµРєС‚РѕСЂРёСЏ РґР»СЏ СЂРµР·РµСЂРІРЅС‹С… РєРѕРїРёР№ РіРѕС‚РѕРІР°")
        
        # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ С„Р°Р№Р»Р° СЃ РґР°РЅРЅС‹РјРё РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№
        if not os.path.exists(USERS_DATA_FILE):
            # РЎРѕР·РґР°РµРј РїСѓСЃС‚РѕР№ С„Р°Р№Р»
            save_users_data({})
            logger.info("вњ… РЎРѕР·РґР°РЅ РЅРѕРІС‹Р№ С„Р°Р№Р» РґР°РЅРЅС‹С… РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№")
        
        # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ Рё СЃРѕРґРµСЂР¶РёРјРѕРµ С„Р°Р№Р»Р° course_content.py
        if not os.path.exists('course_content.py'):
            logger.error("вќЊ Р¤Р°Р№Р» course_content.py РЅРµ РЅР°Р№РґРµРЅ")
            raise FileNotFoundError("РћС‚СЃСѓС‚СЃС‚РІСѓРµС‚ С„Р°Р№Р» course_content.py")
            
        # РџСЂРѕРІРµСЂСЏРµРј СЃС‚СЂСѓРєС‚СѓСЂСѓ COURSE_CONTENT
        if not isinstance(COURSE_CONTENT, dict):
            logger.error("вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ СЃС‚СЂСѓРєС‚СѓСЂР° COURSE_CONTENT")
            raise ValueError("COURSE_CONTENT РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ СЃР»РѕРІР°СЂРµРј")
            
        # РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ РІСЃРµС… СѓСЂРѕРІРЅРµР№
        for level in LEVELS.keys():
            if level not in COURSE_CONTENT:
                logger.warning(f"вљ пёЏ Р’ COURSE_CONTENT РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ СѓСЂРѕРІРµРЅСЊ {level}")
                
        # РџСЂРѕРІРµСЂСЏРµРј СЃС‚СЂСѓРєС‚СѓСЂСѓ СѓСЂРѕРєРѕРІ
        for level, days in COURSE_CONTENT.items():
            if not isinstance(days, dict):
                logger.error(f"вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ СЃС‚СЂСѓРєС‚СѓСЂР° РґРЅРµР№ РґР»СЏ СѓСЂРѕРІРЅСЏ {level}")
                continue
                
            for day, times in days.items():
                if not isinstance(times, dict):
                    logger.error(f"вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ СЃС‚СЂСѓРєС‚СѓСЂР° РІСЂРµРјРµРЅРё РґР»СЏ СѓСЂРѕРІРЅСЏ {level}, РґРµРЅСЊ {day}")
                    continue
                    
                for time_of_day, lesson in times.items():
                    if not isinstance(lesson, dict):
                        logger.error(f"вќЊ РќРµРєРѕСЂСЂРµРєС‚РЅР°СЏ СЃС‚СЂСѓРєС‚СѓСЂР° СѓСЂРѕРєР° РґР»СЏ СѓСЂРѕРІРЅСЏ {level}, РґРµРЅСЊ {day}, РІСЂРµРјСЏ {time_of_day}")
                        continue
                        
                    # РџСЂРѕРІРµСЂСЏРµРј РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ РїРѕР»СЏ СѓСЂРѕРєР°
                    required_fields = ['topic', 'vocabulary', 'grammar', 'practice']
                    missing_fields = [field for field in required_fields if field not in lesson]
                    if missing_fields:
                        logger.warning(f"вљ пёЏ РћС‚СЃСѓС‚СЃС‚РІСѓСЋС‚ РїРѕР»СЏ {', '.join(missing_fields)} РІ СѓСЂРѕРєРµ {level}, РґРµРЅСЊ {day}, РІСЂРµРјСЏ {time_of_day}")
        
        logger.info("вњ… РџСЂРѕРІРµСЂРєР° РѕРєСЂСѓР¶РµРЅРёСЏ Р·Р°РІРµСЂС€РµРЅР° СѓСЃРїРµС€РЅРѕ")
        return True
    except Exception as e:
        logger.error(f"вќЊ РћС€РёР±РєР° РїСЂРё РїСЂРѕРІРµСЂРєРµ РѕРєСЂСѓР¶РµРЅРёСЏ: {e}")
        return False

def main():
    """Р—Р°РїСѓСЃРєР°РµС‚ Р±РѕС‚Р°"""
    try:
        # Р—Р°РіСЂСѓР¶Р°РµРј РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ
        load_dotenv()
        
        # РџСЂРѕРІРµСЂСЏРµРј РѕРєСЂСѓР¶РµРЅРёРµ
        if not check_environment():
            logger.error("вќЊ РћС€РёР±РєР° РїСЂРё РїСЂРѕРІРµСЂРєРµ РѕРєСЂСѓР¶РµРЅРёСЏ")
            return
        
        # РџРѕР»СѓС‡Р°РµРј С‚РѕРєРµРЅ Р±РѕС‚Р° РёР· РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ
        token = os.getenv('TELEGRAM_TOKEN')
        
        if not token:
            logger.error("вќЊ РўРѕРєРµРЅ РЅРµ РЅР°Р№РґРµРЅ РІ С„Р°Р№Р»Рµ .env")
            return
        
        # РЎРѕР·РґР°РµРј Рё РЅР°СЃС‚СЂР°РёРІР°РµРј Р±РѕС‚Р°
        application = Application.builder().token(token).build()
        
        # Р”РѕР±Р°РІР»СЏРµРј РѕР±СЂР°Р±РѕС‚С‡РёРєРё РєРѕРјР°РЅРґ
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
        
        # Р”РѕР±Р°РІР»СЏРµРј РѕР±СЂР°Р±РѕС‚С‡РёРєРё
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler('activate', activate_course))
        application.add_handler(CallbackQueryHandler(handle_homework_feedback, pattern="^hw_(approve|reject)_"))  # Р”РѕР±Р°РІР»СЏРµРј РіР»РѕР±Р°Р»СЊРЅС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РєРЅРѕРїРѕРє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°
        
        logger.info("рџљЂ Р‘РѕС‚ СѓСЃРїРµС€РЅРѕ РЅР°СЃС‚СЂРѕРµРЅ Рё РіРѕС‚РѕРІ Рє Р·Р°РїСѓСЃРєСѓ")
        
        # Р—Р°РїСѓСЃРєР°РµРј Р±РѕС‚Р°
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"вќЊ РљСЂРёС‚РёС‡РµСЃРєР°СЏ РѕС€РёР±РєР° РїСЂРё Р·Р°РїСѓСЃРєРµ Р±РѕС‚Р°: {e}")
        raise

if __name__ == '__main__':
    main() 
