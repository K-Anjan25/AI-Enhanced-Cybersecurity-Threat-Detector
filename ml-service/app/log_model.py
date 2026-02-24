from cmath import log

import joblib
import pandas as pd
import os


# MODEL_PATH = "model/log_model.pkl"

# # Load model once
# model = joblib.load(MODEL_PATH)


# def extract_features(log: dict):
#     """
#     Convert log dictionary into numerical features
#     """

#     message = log.get("message", "").lower()
#     level = log.get("level", "").lower()

#     features = [
#         len(message),
#         int(level == "error"),
#         int(level == "warning"),
#         int("failed" in message),
#         int("unauthorized" in message),
#         int("attack" in message),
#     ]

#     return pd.DataFrame([features], columns=[
#         "length",
#         "is_error_level",
#         "is_warning_level",
#         "has_failed",
#         "has_unauthorized",
#         "has_attack",
#     ])


# def predict_log(data):
#     """
#     Predict anomaly for log
#     """

#     features = extract_features(data.dict())

#     score = model.decision_function(features)[0]
#     is_anomaly = model.predict(features)[0] == -1

#     return float(score), bool(is_anomaly)

LOG_MODEL_PATH = "model/log_model.pkl"

log_model = joblib.load(LOG_MODEL_PATH)


def predict_log(log: dict):
    """
    Predict attack probability for system log
    """
    log = log.dict()  # Convert Pydantic model to dict
    message = log.get("message", "")
    level = log.get("level", "")

    # TF-IDF pipeline handles text directly
    probability = log_model.predict_proba([message])[0][1]
    is_attack = probability >= 0.6

    return float(probability), bool(is_attack)

 # "model": "log_classifier"
