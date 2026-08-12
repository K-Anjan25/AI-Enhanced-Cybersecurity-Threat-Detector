import glob
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ==============================
# CONFIG
# ==============================

CICIDS_PATH = "../datasets/CICIDS2017/*.csv"
MODEL_DIR = "model"
os.makedirs(MODEL_DIR, exist_ok=True)

NETWORK_FEATURES = [
    "Destination Port",
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",
    "Fwd Packet Length Mean",
    "Bwd Packet Length Mean",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Average Packet Size",
    "Init_Win_bytes_forward",
]

print("Loading datasets...")

# ==============================
# 1. NETWORK ANOMALY MODEL (IsolationForest on CICIDS2017)
# ==============================

cic_files = glob.glob(CICIDS_PATH)
if not cic_files:
    raise FileNotFoundError(f"No CSV datasets found at {CICIDS_PATH}")

cic_dfs = []
for file in cic_files:
    df = pd.read_csv(file)
    df.columns = df.columns.str.strip()
    cic_dfs.append(df)

cic_data = pd.concat(cic_dfs, ignore_index=True)
print(f"CICIDS loaded: {cic_data.shape}")

missing = [c for c in NETWORK_FEATURES if c not in cic_data.columns]
if missing:
    raise KeyError(f"Missing expected columns in dataset: {missing}")

X_raw = cic_data[NETWORK_FEATURES].copy()
X_raw.replace([np.inf, -np.inf], np.nan, inplace=True)
X_clean = X_raw.dropna()

if len(X_clean) > 200000:
    print(f"Subsampling 200,000 rows from {len(X_clean)} total...")
    X = X_clean.sample(n=200000, random_state=42)
else:
    X = X_clean

print(f"Network training shape: {X.shape}")

network_pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("isolation", IsolationForest(
        contamination=0.05, n_estimators=100, random_state=42, n_jobs=-1
    )),
])

print("Training IsolationForest network model...")
network_pipeline.fit(X)
joblib.dump(network_pipeline, os.path.join(MODEL_DIR, "network_model.pkl"))
print("Network model saved.")

# ==============================
# 2. LOG ATTACK CLASSIFIER (supervised, TF-IDF + LogisticRegression)
# ==============================

print("Training log classification model...")

log_samples = [
    # Normal
    ("INFO", "User login successful", 0),
    ("INFO", "File accessed normally", 0),
    ("INFO", "System started successfully", 0),
    ("INFO", "Scheduled backup completed", 0),
    ("INFO", "Configuration reloaded", 0),
    ("INFO", "Heartbeat received from node", 0),
    ("INFO", "Email queued for delivery", 0),
    ("INFO", "Metrics collected", 0),
    ("INFO", "Session established", 0),
    ("INFO", "Request completed in 42ms", 0),
    # Attack
    ("ERROR", "Multiple failed login attempts detected", 1),
    ("WARNING", "Unauthorized access attempt detected", 1),
    ("CRITICAL", "Database brute force attack detected", 1),
    ("ERROR", "SQL injection attempt blocked", 1),
    ("CRITICAL", "Kernel memory corruption exploit", 1),
    ("WARNING", "Privilege escalation detected", 1),
    ("CRITICAL", "Ransomware encryption activity on filesystem", 1),
    ("ERROR", "Malware signature matched: trojan.win32", 1),
    ("WARNING", "Port scan activity from external host", 1),
    ("CRITICAL", "Data exfiltration via DNS tunneling suspected", 1),
    ("ERROR", "Buffer overflow attempt on service port", 1),
    ("WARNING", "Phishing link detected in inbound email", 1),
] * 400

messages = [f"[{level}] {msg}" for level, msg, label in log_samples]
labels = [label for _level, _msg, label in log_samples]

X_train, X_test, y_train, y_test = train_test_split(messages, labels, test_size=0.2, random_state=42)

log_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
    ("classifier", LogisticRegression(max_iter=1000)),
])
log_pipeline.fit(X_train, y_train)
joblib.dump(log_pipeline, os.path.join(MODEL_DIR, "log_model.pkl"))
print(f"Log model saved (test accuracy {log_pipeline.score(X_test, y_test):.3f}).")

# ==============================
# 3. EMAIL PHISHING CLASSIFIER (supervised, TF-IDF + LogisticRegression)
# ==============================

print("Training email phishing classifier...")

email_samples = [
    # Legitimate
    ("Your monthly statement is ready", "Dear customer, your invoice for March is now available in your portal. Please review at your convenience.", 0),
    ("Re: Project status update", "Hi team, here is the updated status report for the security dashboard project. Let me know your feedback.", 0),
    ("Meeting invitation", "You are invited to a meeting tomorrow at 10am in room B4. Please confirm attendance.", 0),
    ("Build notification", "The nightly build completed successfully with zero failing tests. Artifacts are published.", 0),
    ("Newsletter", "Here is this week's security briefing covering the latest advisories and patch guidance.", 0),
    ("Receipt", "Thank you for your purchase. Your order has shipped and will arrive within 3 business days.", 0),
    ("Password reset confirmation", "Your password was successfully changed. If this was not you, contact support.", 0),
    ("Onboarding doc", "Welcome aboard! Please review the employee handbook and complete your onboarding tasks.", 0),
    # Phishing
    ("URGENT: Account verification required", "We detected unusual activity on your account. Click here to verify your credentials immediately or your account will be suspended within 24 hours.", 1),
    ("Your account has been locked", "Dear customer, your account has been locked. Visit http://secure-verify-now.com/login to unlock with your password and credit card details.", 1),
    ("Unusual sign-in detected", "Click the link below to confirm it was you. Do not reply to this email. Update your SSN and bank details now.", 1),
    ("Wire transfer confirmation", "Your transfer of $9,500 is pending. Click here with your banking password to confirm. Hurry, limited time!", 1),
    ("Prize claim", "Congratulations! You won $1,000,000. Send your bank account and SSN to claim your prize before midnight.", 1),
    ("Invoice attached", "Please download the attached invoice at 209.85.233.81/pay to settle your overdue balance immediately.", 1),
    ("Security alert - respond now", "Your mailbox exceeded its quota. Click immediately to re-verify with your password to avoid deletion.", 1),
    ("CFO request: urgent transfer", "I am in a meeting. Wire $25,000 to this account today and send the receipt. Do not discuss with anyone.", 1),
] * 300

texts = [f"[SUBJECT] {subj} [BODY] {body}" for subj, body, label in email_samples]
email_labels = [label for _s, _b, label in email_samples]

Xe_train, Xe_test, ye_train, ye_test = train_test_split(texts, email_labels, test_size=0.2, random_state=42)

email_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
    ("classifier", LogisticRegression(max_iter=1000)),
])
email_pipeline.fit(Xe_train, ye_train)
joblib.dump(email_pipeline, os.path.join(MODEL_DIR, "email_model.pkl"))
print(f"Email model saved (test accuracy {email_pipeline.score(Xe_test, ye_test):.3f}).")

print("All models trained and saved.")
