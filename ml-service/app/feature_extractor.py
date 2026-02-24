import numpy as np
import pandas as pd


def extract_features(log: dict):
    """
    Converts log data into numerical features
    """

    message = log.get("message", "").lower()

    features = [
        len(message),
        int("error" in message),
        int("failed" in message),
        int("unauthorized" in message),
        int("attack" in message)
    ]

    return pd.DataFrame([features], columns=[
        "length",
        "has_error",
        "has_failed",
        "has_unauthorized",
        "has_attack"
    ])