"""OpenAI implementation of the translation provider contract."""
from openai import OpenAI


class OpenAITranslationProvider:
    def __init__(self, *, api_key, base_url=None, model="gpt-4o-mini"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client = None

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._client is None:
            if not self.api_key:
                raise ValueError("Chưa cấu hình OPENAI_API_KEY để dịch bằng OpenAI.")
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    @property
    def conversation_limit(self) -> int:
        return 1

    def reset_conversation(self) -> None:
        # Requests are stateless: every request includes its instructions.
        pass

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
