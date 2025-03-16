from pyngrok import ngrok
import time

# Запускаем туннель на порт 8081
public_url = ngrok.connect(8081)
print(f"Публичный URL: {public_url}")

# Держим скрипт запущенным
while True:
    time.sleep(1) 