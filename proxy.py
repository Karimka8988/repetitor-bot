import requests
from aiohttp import web
import asyncio

async def forward_request(request):
    # Получаем данные из запроса
    try:
        data = await request.json()
    except:
        data = {}
    
    # Пересылаем запрос на локальный сервер
    response = requests.post('http://localhost:8081/yoomoney-notification', json=data)
    
    # Возвращаем ответ
    return web.Response(text=response.text, status=response.status_code)

app = web.Application()
app.router.add_post('/webhook', forward_request)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=80) 