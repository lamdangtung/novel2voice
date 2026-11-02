"""Composition boundary: choose a provider without coupling the translator to it."""
from src import config
from .base import TranslationProvider


def get_translation_provider(provider_name=None, *, model=None, api_key=None,
                             base_url=None) -> TranslationProvider:
    name = (provider_name or config.TRANSLATION_PROVIDER).lower()
    if name == "openai":
        from .openai import OpenAITranslationProvider
        return OpenAITranslationProvider(
            api_key=api_key or config.OPENAI_API_KEY,
            base_url=base_url or config.OPENAI_BASE_URL,
            model=model or config.TRANSLATION_MODEL)
    if name == "deepseek":
        from .deepseek import DeepSeekTranslationProvider
        return DeepSeekTranslationProvider(
            model=model or config.DEEPSEEK_MODEL,
            max_chunks_per_conversation=config.DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION)
    raise ValueError(f"Translation provider không hợp lệ: {name}. Chọn openai hoặc deepseek.")
