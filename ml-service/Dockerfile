FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY train.py .

# Bake served models into the image at build time. The log/email classifiers
# train from their built-in corpora (deterministic, ~seconds); the network
# IsolationForest needs the CICIDS2017 dataset, which is NOT in the build
# context, so it is gracefully skipped here (see app/training.run_training).
# The resulting model/*.pkl + manifest.json make /benchmark and /explain work
# out of the box — no manual POST /retrain required.
RUN python train.py

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]