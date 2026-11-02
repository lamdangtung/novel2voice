"""Provider-independent contract for translation model calls."""
from typing import Protocol


class TranslationProvider(Protocol):
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        ...

    @property
    def conversation_limit(self) -> int:
        ...

    def reset_conversation(self) -> None:
        """Start a fresh document; stateless implementations may do nothing."""
        ...

    def close(self) -> None:
        ...
