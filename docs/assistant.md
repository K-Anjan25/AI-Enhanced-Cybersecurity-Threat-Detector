# AEGIS assistant

A read-only helper in the dashboard API. It answers questions about alerts and packet
capture. It cannot change anything, and it refuses requests to change state or to reveal
secrets.

## How a question is handled

1. **Guardrails first.** Secret requests (passwords, tokens, keys) and requests to change
   something (stop, delete, revoke, mark, erase) are refused before any data is read or
   any model is called.
2. **Read-only tools.** `count_alerts`, `recent_alerts`, and `capture_status` read the alert
   store and the capture request. The time window comes from the question ("last 3 days",
   capped at one week).
3. **An answer from the facts.** Backend `rules` (the default) builds the answer directly.
   Backend `openai` sends the facts to a model server and asks it to answer from them only.
   If the server is down, the answer falls back to the rule answer and says so.

Endpoint: `GET /api/v1/assistant/ask?question=...` (any signed-in role). Response:
`{"answer", "backend", "sources"}`.

## Evaluation

    PYTHONPATH=backend python scripts/assistant_eval.py \
        --base-url http://localhost:8000 --email admin@aegis.local --password "<password>"

The script runs the 15 cases in `backend/app/services/assistant/eval_set.py` and reports
the pass rate. The rule backend should score 100%. Run it after changing the model, so a
model is only used if it passes.

## Option B: a Hugging Face model on your own machine

The model runs on your computer, not in AEGIS, so the AEGIS image stays small and the
data stays local. The server must speak the OpenAI chat API. Two common choices:

### Ollama (simplest on Windows)

1. Install Ollama from https://ollama.com (Windows installer).
2. Pull a small instruction-tuned model. Pick a size your RAM can hold:

       ollama pull qwen2.5:1.5b

   (`qwen2.5:3b` gives better answers if you have 8 GB of free RAM.)
3. Check it answers:

       curl http://localhost:11434/v1/chat/completions -H "Content-Type: application/json" -d "{\"model\":\"qwen2.5:1.5b\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"

4. Let the AEGIS backend container reach it. In `docker/.env` add:

       AEGIS_ASSISTANT_BACKEND=openai
       AEGIS_ASSISTANT_BASE_URL=http://host.docker.internal:11434/v1
       AEGIS_ASSISTANT_MODEL=qwen2.5:1.5b

   Then `docker compose up -d backend`. (`host.docker.internal` works on Docker Desktop.)
5. Run the evaluation (above) and compare the pass rate with the rule backend.

### llama.cpp server (any Hugging Face GGUF model)

1. Download a GGUF build of a small instruct model from Hugging Face, for example a
   `Qwen2.5-1.5B-Instruct-GGUF` repository. Save the `.gguf` file to a folder.
2. Run the llama.cpp server (`llama-server`, from the llama.cpp releases) on port 8080:

       llama-server -m path\to\model.Q4_K_M.gguf --port 8080

3. Point AEGIS at it, the same way as Ollama, with
   `AEGIS_ASSISTANT_BASE_URL=http://host.docker.internal:8080/v1`.

### Notes

- Keep the model small. The assistant only summarises a few facts, so a 1.5B to 3B model
  is usually enough. Larger models are slower on a laptop.
- If answers look wrong, check the evaluation first. A fallback answer says "Model
  unavailable", so a silent failure is not possible.
- Fine-tuning is not part of this setup. It needs a GPU and a labelled dataset, neither of
  which is in place.
