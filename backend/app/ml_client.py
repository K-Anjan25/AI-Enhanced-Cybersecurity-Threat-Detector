import requests
from app.config import ML_SERVICE_URL


def predict_network(data: dict):
    response = requests.post(
        f"{ML_SERVICE_URL}/predict/network",
        json=data
    )
    response.raise_for_status()
    return response.json()


def predict_log(data: dict):
    response = requests.post(
        f"{ML_SERVICE_URL}/predict/log",
        json=data
    )
    response.raise_for_status()
    return response.json()
