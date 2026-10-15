from app.llm.providers.base import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    supports_json_schema = True

    def headers(self) -> dict[str, str]:
        h = super().headers()
        h["HTTP-Referer"] = "https://github.com/FelipeYabiko/FinancasAI"
        h["X-Title"] = "FinancasIA"
        return h
