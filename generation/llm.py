"""Appel au LLM : Ollama (local), API compatible OpenAI, ou API Anthropic.

Une seule fonction publique : call_llm(system, user) -> str
"""
import time

import requests

from .config import Settings, get_settings


class LLMError(RuntimeError):
    """Erreur lors de l'appel au LLM."""


def call_llm(system: str, user: str, *, temperature=None, max_tokens=None) -> str:
    s = get_settings()
    temperature = s.temperature if temperature is None else temperature
    max_tokens = max_tokens or s.max_tokens

    if s.provider != "ollama" and not s.api_key:
        raise LLMError("LLM_API_KEY est vide : définis la clé d'API dans l'environnement.")

    last_err = None
    for attempt in range(3):
        try:
            return _dispatch(s, system, user, temperature, max_tokens)
        except requests.HTTPError as e:
            last_err = e
            # Erreurs "définitives" : inutile de réessayer
            if e.response is not None and e.response.status_code in (400, 401, 403, 404):
                break
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            last_err = e
        time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"Échec de l'appel LLM ({s.provider}/{s.model}) : {last_err}")


def _dispatch(s: Settings, system: str, user: str, temperature: float, max_tokens: int) -> str:
    if s.provider == "ollama":
        r = requests.post(
            f"{s.base_url}/api/chat",
            json={
                "model": s.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=s.timeout,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    if s.provider == "openai":
        r = requests.post(
            f"{s.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {s.api_key}"},
            json={
                "model": s.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=s.timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    # anthropic
    r = requests.post(
        f"{s.base_url}/v1/messages",
        headers={"x-api-key": s.api_key, "anthropic-version": "2023-06-01"},
        json={
            "model": s.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=s.timeout,
    )
    r.raise_for_status()
    blocks = r.json()["content"]
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
