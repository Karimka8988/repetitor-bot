import os
import json
import hashlib
import logging
import socket
from aiohttp import web
from dotenv import load_dotenv
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='yoomoney_notifications.log'
)

logger = logging.getLogger(__name__)

# Фиксированный секретный ключ
SECRET_KEY = "gLmPPE7Y09qDM2ZuVZQr4O3b"

def verify_sha1_hash(params: dict, secret_key: str) -> bool:
    """Проверка SHA-1 подписи уведомления"""
    param_list = [
        str(params.get('notification_type', '')),
        str(params.get('operation_id', '')),
        str(params.get('amount', '')),
        str(params.get('currency', '')),
        str(params.get('datetime', '')),
        str(params.get('sender', '')),
        str(params.get('codepro', '')),
        secret_key,
        str(params.get('label', ''))
    ]
    param_str = '&'.join(param_list)
    calculated_hash = hashlib.sha1(param_str.encode('utf-8')).hexdigest()
    return calculated_hash == params.get('sha1_hash', '')

async def verify_notification(request):
    """Обработчик HTTP-уведомлений от ЮMoney"""
    try:
        logger.info(f"Получен запрос: {request.method}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Пробуем получить данные в разных форматах
        try:
            data = await request.json()
            logger.info("Получены JSON данные")
        except:
            try:
                data = await request.post()
                logger.info("Получены POST данные")
            except:
                data = await request.text()
                logger.info(f"Получены текстовые данные: {data}")
                return web.Response(text="OK", status=200)

        # Логируем полученные данные
        logger.info(f"Получено уведомление от ЮMoney: {data}")

        # Если это тестовый запрос или пинг
        if isinstance(data, str) or not data:
            logger.info("Получен тестовый запрос")
            return web.Response(text="OK", status=200)

        # Проверяем подпись, если это не тестовое уведомление
        if not data.get('test_notification'):
            if not verify_sha1_hash(data, SECRET_KEY):
                logger.warning("Неверная подпись SHA-1")
                return web.Response(text="Invalid signature", status=400)

        # Извлекаем label из данных
        label = data.get('label', '')
        if not label:
            logger.warning("Label не найден в данных")
            return web.Response(text="OK", status=200)

        # Создаем информацию о платеже
        payment_info = {
            'operation_id': data.get('operation_id', f'manual_{int(datetime.now().timestamp())}'),
            'amount': data.get('amount', '10.00'),
            'datetime': data.get('datetime', datetime.now().isoformat()),
            'label': label,
            'status': 'success'
        }

        # Создаем директорию payments, если она не существует
        os.makedirs('payments', exist_ok=True)

        # Сохраняем информацию о платеже
        payment_file = f"payments/{label}.json"
        with open(payment_file, 'w') as f:
            json.dump(payment_info, f, indent=4)

        logger.info(f"Платеж успешно сохранен: {payment_info}")
        return web.Response(text="OK", status=200)

    except Exception as e:
        logger.error(f"Ошибка при обработке уведомления: {str(e)}")
        logger.exception("Полный стек ошибки:")
        return web.Response(text="Internal error", status=500)

async def test_payment(request):
    """Тестовый эндпоинт для симуляции платежей"""
    try:
        data = await request.json()
        label = data.get('label')
        
        if not label:
            return web.Response(text="Label is required", status=400)
        
        # Создаем тестовое уведомление
        now = datetime.now().isoformat()
        payment_info = {
            'operation_id': f'test_{int(datetime.now().timestamp())}',
            'amount': '10.00',
            'datetime': now,
            'label': label,
            'status': 'success'
        }
        
        # Создаем директорию payments, если она не существует
        os.makedirs('payments', exist_ok=True)
        
        # Сохраняем информацию о платеже
        with open(f"payments/{label}.json", 'w') as f:
            json.dump(payment_info, f)
        
        logger.info(f"Создан тестовый платеж: {payment_info}")
        return web.Response(text="Test payment created", status=200)
        
    except Exception as e:
        logger.error(f"Ошибка при создании тестового платежа: {str(e)}")
        return web.Response(text="Internal error", status=500)

def is_port_in_use(port):
    """Проверяет, занят ли порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except OSError:
            return True

async def init_app():
    """Инициализация веб-приложения"""
    app = web.Application()
    app.router.add_post('/yoomoney-notification', verify_notification)
    app.router.add_post('/test-payment', test_payment)
    app.router.add_get('/yoomoney-notification', verify_notification)  # Добавляем обработку GET-запросов
    return app

if __name__ == '__main__':
    # Создаем директорию для хранения информации о платежах
    os.makedirs('payments', exist_ok=True)
    
    # Пробуем разные порты, начиная с 8081
    port = 8081
    while is_port_in_use(port) and port < 8090:
        print(f"Порт {port} занят, пробуем следующий...")
        port += 1
    
    if port >= 8090:
        print("Не удалось найти свободный порт!")
        exit(1)
    
    print(f"Сервер запущен на http://0.0.0.0:{port}")
    print("Доступные эндпоинты:")
    print("- POST /yoomoney-notification - для уведомлений от YooMoney")
    print("- GET /yoomoney-notification - для проверки доступности")
    print("- POST /test-payment - для создания тестовых платежей")
    print("Для создания тестового платежа отправьте POST запрос на /test-payment с JSON: {'label': 'payment_id'}")
    
    try:
        # Запускаем веб-сервер
        web.run_app(init_app(), host='0.0.0.0', port=port, access_log=logger)
    except KeyboardInterrupt:
        print("\nСервер остановлен")
    except Exception as e:
        print(f"Ошибка при запуске сервера: {str(e)}") 