import httpx
import pytest
from groq import APIConnectionError, APIStatusError

from app.config import Settings, configured_groq_keys
from app.groq_classifier import GroqFallbackClassifier, GroqUnavailable, KeyCooldowns


def status_error(status, retry_after=None):
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    response = httpx.Response(
        status, headers=headers, request=httpx.Request("POST", "https://example.test")
    )
    return APIStatusError("sensitive provider error", response=response, body=None)


def test_configured_keys_are_trimmed_and_deduplicated():
    settings = Settings(
        _env_file=None, groq_api_key=" first ", groq_api_keys="second, first, ,third"
    )
    assert configured_groq_keys(settings) == ("first", "second", "third")
    assert configured_groq_keys(Settings(_env_file=None, groq_api_keys="only")) == ("only",)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 429])
async def test_key_specific_errors_switch_key_and_cool_down(status):
    now = [100.0]
    cooldowns = KeyCooldowns(clock=lambda: now[0])
    calls = []

    class FakeClassifier:
        def __init__(self, key):
            self.key = key

        async def ainvoke(self, messages):
            calls.append(self.key)
            if self.key == "first":
                raise status_error(status, "15")
            return {"action": "consult"}

    classifier = GroqFallbackClassifier(("first", "second"), FakeClassifier, 3, cooldowns)
    assert await classifier.ainvoke([]) == {"action": "consult"}
    assert calls == ["first", "second"]
    calls.clear()
    await classifier.ainvoke([])
    assert calls == ["second"]
    now[0] += 301
    calls.clear()
    await classifier.ainvoke([])
    assert calls == ["first", "second"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 404, 422, 500, 503])
async def test_non_key_errors_are_not_retried_with_other_keys(status):
    calls = []

    class FakeClassifier:
        def __init__(self, key):
            self.key = key

        async def ainvoke(self, messages):
            calls.append(self.key)
            raise status_error(status)

    classifier = GroqFallbackClassifier(("first", "second"), FakeClassifier, 3, KeyCooldowns())
    with pytest.raises(APIStatusError):
        await classifier.ainvoke([])
    assert calls == ["first"]


@pytest.mark.asyncio
async def test_attempts_are_bounded_and_no_credentials_escape():
    calls = []

    class FakeClassifier:
        def __init__(self, key):
            self.key = key

        async def ainvoke(self, messages):
            calls.append(self.key)
            raise status_error(429, "not-a-number")

    classifier = GroqFallbackClassifier(
        ("secret-1", "secret-2", "secret-3"), FakeClassifier, 2, KeyCooldowns()
    )
    with pytest.raises(GroqUnavailable) as error:
        await classifier.ainvoke([])
    assert calls == ["secret-1", "secret-2"]
    assert "secret" not in str(error.value)
    assert "sensitive" not in str(error.value)


@pytest.mark.asyncio
async def test_retry_after_is_respected_and_all_cooling_keys_fail_without_calls():
    now = [100.0]
    cooldowns = KeyCooldowns(clock=lambda: now[0])
    calls = []

    class FakeClassifier:
        def __init__(self, key):
            self.key = key

        async def ainvoke(self, messages):
            calls.append(self.key)
            raise status_error(429, "7200")

    classifier = GroqFallbackClassifier(("first",), FakeClassifier, 3, cooldowns)
    with pytest.raises(GroqUnavailable):
        await classifier.ainvoke([])
    now[0] += 3600
    with pytest.raises(GroqUnavailable):
        await classifier.ainvoke([])
    assert calls == ["first"]
    now[0] += 3601
    with pytest.raises(GroqUnavailable):
        await classifier.ainvoke([])
    assert calls == ["first", "first"]


@pytest.mark.asyncio
async def test_connection_failure_does_not_retry_another_key():
    calls = []

    class FakeClassifier:
        def __init__(self, key):
            self.key = key

        async def ainvoke(self, messages):
            calls.append(self.key)
            raise APIConnectionError(request=httpx.Request("POST", "https://example.test"))

    classifier = GroqFallbackClassifier(("first", "second"), FakeClassifier, 3, KeyCooldowns())
    with pytest.raises(APIConnectionError):
        await classifier.ainvoke([])
    assert calls == ["first"]
