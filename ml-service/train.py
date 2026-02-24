# import os
# import numpy as np
# import pandas as pd
# import joblib

# from sklearn.ensemble import IsolationForest
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.pipeline import Pipeline


# # Create model directory if not exists
# os.makedirs("model", exist_ok=True)


# # =========================
# # 1️⃣ TRAIN NETWORK MODEL
# # =========================

# print("Training Network Model...")

# # Simulated network data
# network_data = pd.DataFrame({
#     "src_port": np.random.randint(1, 65535, 500),
#     "dst_port": np.random.randint(1, 65535, 500),
#     "bytes": np.random.normal(5000, 2000, 500),
#     "duration": np.random.normal(5, 2, 500)
# })

# network_features = network_data[["src_port", "dst_port", "bytes", "duration"]]

# network_model = IsolationForest(contamination=0.1, random_state=42)
# network_model.fit(network_features)

# joblib.dump(network_model, "model/network_model.pkl")

# print("Network model saved ✔")


# # =========================
# # 2️⃣ TRAIN LOG MODEL
# # =========================

# print("Training Log Model...")


# def extract_features(log: dict):
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

#     return features


# # Normal logs only (important!)
# logs = [
#     # Normal
#     {"level": "INFO", "message": "User login successful"},
#     {"level": "INFO", "message": "File accessed normally"},
#     {"level": "INFO", "message": "System started successfully"},

#     # Suspicious
#     {"level": "ERROR", "message": "Multiple failed login attempts"},
#     {"level": "WARNING", "message": "Unauthorized access attempt detected"},
#     {"level": "CRITICAL", "message": "Database connection brute force detected"},
#     {"level": "ERROR", "message": "SQL injection attempt blocked"}
# ] * 300


# feature_rows = [extract_features(log) for log in logs]

# log_df = pd.DataFrame(feature_rows, columns=[
#     "length",
#     "is_error_level",
#     "is_warning_level",
#     "has_failed",
#     "has_unauthorized",
#     "has_attack",
# ])

# log_model = IsolationForest(contamination=0.05, random_state=42)
# log_model.fit(log_df)

# joblib.dump(log_model, "model/log_model.pkl")

# print("Log model saved ✔")

# print("\n🎉 Training complete.")

import os
import glob
import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split

# ==============================
# CONFIG
# ==============================

CICIDS_PATH = "../datasets/CICIDS2017/*.csv"
UNSW_PATH = "../datasets/UNSW-NB15.csv"
MODEL_DIR = "model"
os.makedirs(MODEL_DIR, exist_ok=True)

print("🔄 Loading datasets...")

# ==============================
# 1️⃣ LOAD CICIDS DATA
# ==============================

cic_files = glob.glob(CICIDS_PATH)
cic_dfs = []

for file in cic_files:
    print(f"Loading {file}")
    df = pd.read_csv(file)
    cic_dfs.append(df)

cic_data = pd.concat(cic_dfs, ignore_index=True)

print("✔ CICIDS loaded")

# ==============================
# 2️⃣ LOAD UNSW DATA
# ==============================

# unsw_data = pd.read_csv(UNSW_PATH)
# print("✔ UNSW-NB15 loaded")

# ==============================
# 3️⃣ SELECT COMMON NUMERIC FEATURES
# ==============================

# Keep only numeric columns
cic_numeric = cic_data.select_dtypes(include=[np.number])
# unsw_numeric = unsw_data.select_dtypes(include=[np.number])

# # Align columns intersection
# common_columns = list(set(cic_numeric.columns))

# if len(common_columns) < 5:
#     raise Exception("Not enough common numeric features between datasets")

# print(f"✔ Using {len(common_columns)} common features")

# cic_final = cic_numeric[common_columns]
# unsw_final = unsw_numeric[common_columns]

# # Combine both datasets
# combined_data = pd.concat([cic_final], ignore_index=True)

# Remove NaN / infinite values
cic_numeric.replace([np.inf, -np.inf], np.nan, inplace=True)
cic_numeric.dropna(inplace=True)

print(f"✔ Final training shape: {cic_numeric.shape}")

combined_data = cic_numeric

# After loading and before selecting columns
combined_data.columns = combined_data.columns.str.strip()

print("Numeric columns in dataset:")
print(combined_data.columns.tolist())

selected_cols = ["Destination Port", "Flow Duration",
                 "Total Length of Fwd Packets", "Flow Bytes/s"]
X = combined_data[selected_cols]
# ==============================
# 4️⃣ TRAIN ISOLATION FOREST
# ==============================

network_pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("isolation", IsolationForest(
        contamination=0.05,
        n_estimators=200,
        random_state=42
    ))
])

print("🔄 Training model...")
network_pipeline.fit(X)

joblib.dump(network_pipeline, f"{MODEL_DIR}/network_model.pkl")

print("✅ Network model trained and saved!")


# os.makedirs("model", exist_ok=True)

# # =====================================================
# # 1️⃣ NETWORK MODEL (UNSUPERVISED ANOMALY DETECTION)
# # =====================================================

# print("Training Network Anomaly Model...")

# # Simulated NORMAL traffic only
# network_data = pd.DataFrame({
#     "src_port": np.random.randint(1024, 65535, 1000),
#     "dst_port": np.random.randint(20, 443, 1000),
#     "bytes": np.random.normal(5000, 800, 1000),
#     "duration": np.random.normal(3, 0.8, 1000)
# })

# network_features = network_data[["src_port", "dst_port", "bytes", "duration"]]

# network_pipeline = Pipeline([
#     ("scaler", StandardScaler()),
#     ("isolation", IsolationForest(
#         contamination=0.05,
#         n_estimators=200,
#         random_state=42
#     ))
# ])

# network_pipeline.fit(network_features)

# joblib.dump(network_pipeline, "model/network_model.pkl")

# print("✔ Network model saved")


# =====================================================
# 2️⃣ LOG MODEL (SUPERVISED ATTACK CLASSIFIER)
# =====================================================

print("Training Log Classification Model...")

# Proper labeled dataset
log_samples = [
    # Normal logs
    ("INFO", "User login successful", 0),
    ("INFO", "File accessed normally", 0),
    ("INFO", "System started successfully", 0),
    ("INFO", "Scheduled backup completed", 0),

    # Attack logs
    ("ERROR", "Multiple failed login attempts", 1),
    ("WARNING", "Unauthorized access attempt detected", 1),
    ("CRITICAL", "Database brute force attack detected", 1),
    ("ERROR", "SQL injection attempt blocked", 1),
    ("CRITICAL", "Kernel memory corruption exploit", 1),
    ("WARNING", "Privilege escalation detected", 1)
] * 300


messages = [x[1] for x in log_samples]
labels = [x[2] for x in log_samples]

X_train, X_test, y_train, y_test = train_test_split(
    messages,
    labels,
    test_size=0.2,
    random_state=42
)

log_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=5000
    )),
    ("classifier", LogisticRegression(max_iter=1000))
])

log_pipeline.fit(X_train, y_train)

joblib.dump(log_pipeline, "model/log_model.pkl")

print("✔ Log model saved")

print("\n🎉 Training complete.")
