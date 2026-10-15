from app.llm.providers.base import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    base_url = "https://api.groq.com/openai/v1"
    # Strict json_schema is only available on some Groq models; json_object works on all,
    # and the client validates against the Pydantic schema anyway.
    supports_json_schema = False
