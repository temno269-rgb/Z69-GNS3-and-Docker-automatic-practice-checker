from flask import Flask
import requests

app = Flask(__name__)

# Координаты городов
CITIES = {
    "Москва": {"lat": 55.75, "lon": 37.61},
    "Самара": {"lat": 53.19, "lon": 50.10}
}

def get_temperature(lat, lon):
    """Получает текущую температуру через Open-Meteo API."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data['current_weather']['temperature']
    except Exception as e:
        return "Ошибка получения данных"

@app.route('/')
def index():
    html_response = "<h1>Температура воздуха</h1>"
    
    for city_name, coords in CITIES.items():
        temp = get_temperature(coords['lat'], coords['lon'])
        html_response += f"<p><b>{city_name}:</b> {temp} °C</p>"
        
    return html_response

if __name__ == '__main__':
    # Важно: host='0.0.0.0' делает сервер доступным извне контейнера
    app.run(host='0.0.0.0', port=2020)
