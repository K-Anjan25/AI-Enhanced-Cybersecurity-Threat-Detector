import joblib
import pandas as pd
import os

# # Load trained IsolationForest model
# model = joblib.load("model/network_model.pkl")


# def predict_network(data: dict):
#     """
#     Predict anomaly for network traffic
#     """
#     data = data.dict()  # Convert Pydantic model to dict
#     # MUST match training feature names EXACTLY
#     features = pd.DataFrame(
#         [[
#             data.get("src_port", 0),
#             data.get("dst_port", 0),
#             data.get("bytes", 0),
#             data.get("duration", 0)
#         ]],
#         columns=[
#             "src_port",
#             "dst_port",
#             "bytes",
#             "duration"
#         ]
#     )

#     score = model.decision_function(features)[0]
#     prediction = model.predict(features)[0]

#     is_anomaly = prediction == -1

#     return float(score), bool(is_anomaly)

# Load trained IsolationForest model
model = joblib.load("model/network_model.pkl")

# Extract the feature names used during training
# feature_columns = model.named_steps["isolation"].feature_names_in_
TRAIN_COLUMNS = ["Destination Port", "Flow Duration",
                 "Total Length of Fwd Packets", "Flow Bytes/s"]


def predict_network(data: dict):
    """
    Predict anomaly for network traffic.
    Input dict must contain: src_port, dst_port, bytes, duration
    """

    # Convert Pydantic model to dict if needed
    if hasattr(data, "dict"):
        data = data.dict()

    # Start with all zeros for the expected feature columns
    row = {col: 0 for col in TRAIN_COLUMNS}

    # Map your API input fields to CICIDS features

    if "Destination Port" in row:
        row["Destination Port"] = data.get("dst_port", 0)

    if "Flow Duration" in row:
        row["Flow Duration"] = data.get("duration", 0)

    if "Total Length of Fwd Packets" in row:
        row["Total Length of Fwd Packets"] = data.get("bytes", 0)

    if "Flow Bytes/s" in row:
        duration = data.get("duration", 1) or 1
        row["Flow Bytes/s"] = data.get("bytes", 0) / duration

    # Build DataFrame in the correct order
    features = pd.DataFrame([row], columns=TRAIN_COLUMNS)

    score = model.decision_function(features)[0]
    prediction = model.predict(features)[0]

    is_anomaly = prediction == -1

    return float(score), bool(is_anomaly)
