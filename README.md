# Telegram English Learning Bot

Бот для изучения английского языка с разными уровнями сложности (A1-C2).

## Функционал

- Уроки для разных уровней владения языком
- Аудио произношение слов
- Система отслеживания прогресса
- Интегрированная система оплаты

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/YOUR_USERNAME/repetitor.git
cd repetitor
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл .env и добавьте необходимые токены:
```
TELEGRAM_TOKEN=your_token
VOICERSS_API_KEY=your_key
YOOMONEY_TOKEN=your_token
```

4. Запустите бота:
```bash
python bot.py
```

## Docker

Для запуска через Docker:

```bash
docker build -t repetitor-bot .
docker run -d --env-file .env repetitor-bot
```

## Структура проекта

- `bot.py` - основной файл бота
- `course_content.py` - содержимое курса
- `requirements.txt` - зависимости проекта
- `Dockerfile` - файл для сборки Docker образа

## Особенности
- 6 уровней владения языком (A1, A2, B1, B2, C1, C2)
- 14-дневный курс для каждого уровня
- Ежедневные уроки включают:
  - Новую тему
  - Словарный запас
  - Грамматику
  - Практические задания

## Использование

1. Найдите бота в Telegram
2. Отправьте команду `/start`