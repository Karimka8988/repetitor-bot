import requests
import json

url = 'http://localhost:8081/test-payment'
data = {
    'label': 'eng_course_A1_7783551682_1742002119'
}
headers = {
    'Content-Type': 'application/json'
}

response = requests.post(url, json=data, headers=headers)
print(f"Статус: {response.status_code}")
print(f"Ответ: {response.text}") 