from app.llm.providers.base import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini through its OpenAI compatibility endpoint.

    Gemini 3 models attach thought signatures to tool calls; we resend the assistant
    message verbatim (`LLMResponse.raw_message`), which preserves them.
    """

    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    supports_json_schema = True
