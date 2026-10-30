"""AEGIS assistant: answers questions about alerts and capture, read-only.

Order of work for every question, and why:

1. ``guardrails.classify`` runs first. Secret requests and requests to change state are
   refused here, before any tool or model sees them.
2. The matching read-only tools run (``tools``). They reuse the alert store and the
   capture control; the assistant holds no write path.
3. An answer is produced from the tool facts. The rule backend builds it directly. The
   model backend (an OpenAI-compatible server, for example Ollama or llama.cpp running a
   Hugging Face model) is asked to answer from those facts only, and falls back to the
   rule answer if it is unreachable.
"""
