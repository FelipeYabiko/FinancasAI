from app.config import get_settings
from app.llm.providers.base import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    base_url = "https://api.groq.com/openai/v1"
    # Strict json_schema is only available on some Groq models; json_object works on all,
    # and the client validates against the Pydantic schema anyway.
    supports_json_schema = False

    def build_payload(self, messages, model, tools, response_schema, temperature):
        payload = super().build_payload(messages, model, tools, response_schema, temperature)
        effort = get_settings().llm_reasoning_effort
        if effort and "gpt-oss" in model:
            # gpt-oss is a reasoning model: with long outputs (a statement with 40+ rows) the
            # default effort can spend the whole budget on reasoning and return empty content.
            payload["reasoning_effort"] = effort
        return payload
