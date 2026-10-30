"""Call an OpenAI-compatible chat server: Ollama, llama.cpp's server, or vLLM.

The model is told to answer only from the facts it is given. It sees the facts as data
and never receives credentials. Nothing here runs a model in-process, so the backend
image stays small; the model runs wherever the server runs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

SYSTEM_PROMPT = (
    "You are the AEGIS assistant. Answer the user's question using only the FACTS, which "
    "are data from the system. If the facts do not answer the question, say so. You cannot "
    "change anything. Keep the answer under 80 words."
)


class ModelUnavailable(RuntimeError):
    """The server could not be reached, refused, or timed out."""


class ModelEmpty(RuntimeError):
    """The server answered without usable text."""


def ask(*, base_url: str, model: str, question: str, facts: str, timeout: float) -> str:
    """Send the question and facts to the server and return the reply text.

    Raises ModelUnavailable when the server cannot be reached, and ModelEmpty when it
    answers without usable text. The caller decides what to show in either case.
    """
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"FACTS:\n{facts}\n\nQUESTION:\n{question}"},
            ],
        }
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - the base URL is operator-configured
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ModelUnavailable(type(exc).__name__) from exc
    except ValueError as exc:
        raise ModelEmpty("the server's reply was not JSON") from exc
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelEmpty("the reply had no message") from exc
    if not isinstance(content, str):
        raise ModelEmpty("the reply had no text")
    return content
