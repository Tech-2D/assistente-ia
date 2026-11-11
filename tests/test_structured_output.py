from langchain_groq import ChatGroq

from app.assistant import RequestIntent


def test_groq_strict_schema_contains_all_required_fields():
    """Inspect the actual LangChain request without contacting Groq."""
    model = ChatGroq(
        model="openai/gpt-oss-20b",
        api_key="offline-test-key",
        temperature=0.7,
        model_kwargs={"top_p": 0.95},
        max_retries=0,
    )
    chain = model.with_structured_output(RequestIntent, method="json_schema", strict=True)
    response_format = chain.first.kwargs["response_format"]
    schema = response_format["json_schema"]["schema"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["properties"]) == set(RequestIntent.model_fields)
