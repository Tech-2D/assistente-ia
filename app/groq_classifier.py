from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Callable

from groq import APIStatusError


class GroqUnavailable(Exception):
    """No configured key is currently available for classification."""


class KeyCooldowns:
    """Small, process-local cooldown registry; keys and error bodies are never logged."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._until: dict[bytes, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _fingerprint(key: str) -> bytes:
        return hashlib.sha256(key.encode("utf-8")).digest()

    def available(self, key: str) -> bool:
        now = self.clock()
        fingerprint = self._fingerprint(key)
        with self._lock:
            self._until = {k: until for k, until in self._until.items() if until > now}
            return fingerprint not in self._until

    def defer(self, key: str, seconds: float) -> None:
        with self._lock:
            self._until[self._fingerprint(key)] = self.clock() + seconds


COOLDOWNS = KeyCooldowns()


def _cooldown_seconds(exc: APIStatusError) -> float:
    if exc.status_code in (401, 403):
        return 300.0
    try:
        seconds = float(exc.response.headers.get("retry-after", "60"))
        if not math.isfinite(seconds):
            raise ValueError("invalid retry-after")
        return max(seconds, 1.0)
    except (TypeError, ValueError):
        return 60.0


class GroqFallbackClassifier:
    """Try distinct available keys only for authentication, permission or quota errors."""

    def __init__(self, keys, classifier_factory, max_attempts: int, cooldowns=COOLDOWNS):
        self.keys = keys
        self.classifier_factory = classifier_factory
        self.max_attempts = max_attempts
        self.cooldowns = cooldowns

    async def ainvoke(self, messages):
        attempts = 0
        for key in self.keys:
            if not self.cooldowns.available(key):
                continue
            if attempts >= self.max_attempts:
                break
            attempts += 1
            try:
                return await self.classifier_factory(key).ainvoke(messages)
            except APIStatusError as exc:
                if exc.status_code not in (401, 403, 429):
                    raise
                self.cooldowns.defer(key, _cooldown_seconds(exc))
        raise GroqUnavailable("Provedor de IA temporariamente indisponível.") from None
