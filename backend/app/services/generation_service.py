"""LLM client interface, Groq implementation, answer parsing and URL/leak post-processing."""
import json
import logging
import re
import time
from abc import ABC, abstractmethod

import requests

from app.core.config import Settings
from app.core.errors import AppError
from app.prompts import system_prompt as sp
from app.services.retrieval_service import RetrievedChunk

log = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")


class LLMClient(ABC):
    @abstractmethod
    def complete(self, messages: list[dict]) -> str: ...


class GroqLLMClient(LLMClient):
    def __init__(self, settings: Settings, http_post=requests.post, sleep=time.sleep):
        self.s, self._post, self._sleep = settings, http_post, sleep

    def complete(self, messages: list[dict]) -> str:
        s = self.s
        if not s.groq_api_key:
            raise AppError(503, "llm_not_configured", "GROQ_API_KEY is not set. Add it to backend/.env and restart the server.")
        payload = {"model": s.groq_model, "messages": messages, "temperature": s.llm_temperature, "max_completion_tokens": s.llm_max_tokens}
        headers = {"Authorization": f"Bearer {s.groq_api_key}", "Content-Type": "application/json"}
        for attempt in (1, 2):
            try:
                r = self._post(f"{s.groq_base_url}/chat/completions", json=payload, headers=headers, timeout=s.llm_timeout_seconds)
            except requests.Timeout as e:
                raise AppError(504, "llm_timeout", "The language model timed out. Please try again.") from e
            except requests.RequestException as e:
                raise AppError(502, "llm_unreachable", "Could not reach the language model provider.") from e
            if r.status_code == 429:
                wait = _retry_after(r)
                if attempt == 1 and wait is not None and wait <= s.llm_retry_max_wait_seconds:
                    self._sleep(wait)
                    continue
                raise AppError(429, "llm_rate_limited", "The language model is rate limited. Please retry shortly.", retry_after=wait)
            break
        if r.status_code in (401, 403):
            raise AppError(502, "llm_auth_failed", "The language model provider rejected GROQ_API_KEY.")
        if r.status_code in (400, 404) and _mentions_model(r):
            raise AppError(502, "llm_model_rejected", f"The provider does not accept the model '{s.groq_model}'. Change GROQ_MODEL in backend/.env.")
        if r.status_code != 200:
            raise AppError(502, "llm_error", f"The language model provider returned an error (HTTP {r.status_code}).")
        try:
            content = r.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty")
            return content
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise AppError(502, "llm_bad_response", "The language model returned a malformed response.") from e


class OllamaLLMClient(LLMClient):
    def __init__(self, settings: Settings, http_post=requests.post, sleep=time.sleep):
        self.s, self._post, self._sleep = settings, http_post, sleep

    def complete(self, messages: list[dict]) -> str:
        s = self.s
        url = f"{s.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": s.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": s.llm_temperature,
                "num_predict": s.llm_max_tokens,
            },
        }
        for attempt in (1, 2):
            try:
                r = self._post(url, json=payload, timeout=s.llm_timeout_seconds)
            except requests.Timeout as e:
                raise AppError(504, "llm_timeout", "Ollama timed out. Please try again.") from e
            except requests.RequestException as e:
                raise AppError(502, "llm_unreachable", f"Could not reach Ollama at {s.ollama_base_url}. Make sure Ollama is running.") from e
            if r.status_code == 404 and _mentions_model(r):
                raise AppError(502, "llm_model_rejected", f"Ollama model '{s.ollama_model}' not found. Run 'ollama pull {s.ollama_model}'.")
            if r.status_code != 200:
                raise AppError(502, "llm_error", f"Ollama returned HTTP {r.status_code}.")
            break

        try:
            content = r.json()["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty")
            return content
        except (KeyError, ValueError, TypeError) as e:
            raise AppError(502, "llm_bad_response", "Ollama returned a malformed response.") from e


def _retry_after(r) -> float | None:
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError, AttributeError):
        return None


def _mentions_model(r) -> bool:
    try:
        err = r.json().get("error", {})
        return "model" in (str(err.get("code", "")) + str(err.get("message", ""))).lower()
    except Exception:
        return r.status_code == 404


def parse_llm_output(raw: str) -> tuple[str, list[str]]:
    """Expect {"answer", "follow_up_questions"}; fall back to the raw text as the answer."""
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    for candidate in [text] + ([m.group(0)] if m else []):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and isinstance(obj.get("answer"), str) and obj["answer"].strip():
                fu = obj.get("follow_up_questions") or []
                return obj["answer"].strip(), [str(q).strip() for q in fu if str(q).strip()][:4] if isinstance(fu, list) else []
        except ValueError:
            continue
    return raw.strip(), []


def _canon(u: str) -> str:
    return u.rstrip("/.,;:!?").lower()


def sanitize_urls(answer: str, allowed: set[str]) -> tuple[str, list[str]]:
    """Replace any URL not present in retrieved sources / catalog with a placeholder."""
    allowed_c = {_canon(u) for u in allowed}
    removed: list[str] = []

    def repl(m: re.Match) -> str:
        url = m.group(0)
        if _canon(url) in allowed_c:
            return url
        removed.append(url)
        return "[link removed]"

    return URL_RE.sub(repl, answer), removed


def leaks_system_prompt(answer: str) -> bool:
    low = answer.lower()
    for prompt in (sp.SYSTEM_PROMPT_GROUNDED, sp.SYSTEM_PROMPT_GENERAL):
        for line in prompt.splitlines():
            line = line.strip().lower()
            if len(line) >= 50 and line in low:
                return True
    return False


class GenerationService:
    def __init__(self, settings: Settings, llm: LLMClient):
        self.s, self.llm = settings, llm

    def generate(self, question: str, history: list[dict], chunks: list[RetrievedChunk], course, subject, topic,
                 extra_allowed_urls: set[str]) -> tuple[str, list[str]]:
        msgs = sp.build_messages(question, history, chunks, course, subject, topic)
        answer, follow_ups = parse_llm_output(self.llm.complete(msgs))
        allowed = {c.url for c in chunks} | extra_allowed_urls
        answer, removed = sanitize_urls(answer, allowed)
        if removed:
            log.warning("Removed %d unverified URL(s) from the generated answer", len(removed))
        if leaks_system_prompt(answer):
            answer = "I can't share my internal instructions, but I'm happy to help with your GATE DA question."
        follow_ups = [sanitize_urls(q, allowed)[0] for q in follow_ups]
        return answer, follow_ups
