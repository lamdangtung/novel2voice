import logging
from pathlib import Path
from typing import Optional
from src.translation_providers import TranslationProvider, get_translation_provider
from src.glossary import Glossary
from src.text_chunker import TextChunker
from src import config
from src.glossary_manager import GlossaryManager, ModelGlossaryExtractor

logger = logging.getLogger(__name__)


SYSTEM_TRANSLATE_PROMPT = """Bạn là một dịch giả tiểu thuyết chuyên nghiệp có văn phong điêu luyện và tinh tế.
Nhiệm vụ của bạn là dịch văn bản chương truyện từ ngôn ngữ gốc (bao gồm tiếng Anh hoặc tiếng Trung) sang tiếng Việt.

Yêu cầu dịch thuật:
1. Văn phong: Tự nhiên, trôi chảy, đúng chất tiểu thuyết/văn học, không dịch thô kiểu "word-by-word".
2. Ngữ cảnh & Xưng hô: Linh hoạt và phù hợp với bối cảnh truyện (lịch sử, chiến tranh, huyền ảo, hoặc đời thường). Lời thoại cần phản ánh đúng tính cách, vị thế của từng nhân vật.
3. Định dạng: Giữ nguyên cấu trúc phân đoạn, dấu ngoặc kép hội thoại và nhịp văn của tác giả gốc.
4. Chỉ trả về duy nhất nội dung tiếng Việt đã dịch, tuyệt đối không thêm lời chào, giải thích, hay ghi chú bên ngoài."""


class NovelTranslator:
    """
    Dịch văn bản truyện từ tiếng Anh sang tiếng Việt qua một TranslationProvider độc lập với nhà cung cấp.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        glossary: Optional[Glossary] = None,
        provider: Optional[TranslationProvider] = None,
        provider_name: Optional[str] = None,
        glossary_manager=None,
        glossary_extractor=None,
    ):
        self.glossary = glossary or Glossary(config.GLOSSARY_PATH)
        self.provider = provider if provider is not None else get_translation_provider(
            provider_name, model=model, api_key=api_key, base_url=base_url)
        self.glossary_manager = glossary_manager
        self.glossary_extractor = glossary_extractor
        # Explicitly injected providers remain isolated unless learning is injected too.
        if provider is None and config.GLOSSARY_AUTO_UPDATE and self.glossary.file_path:
            self.glossary_manager = glossary_manager or GlossaryManager(
                self.glossary, min_occurrences=config.GLOSSARY_MIN_OCCURRENCES,
                min_chunks=config.GLOSSARY_MIN_DISTINCT_CHUNKS,
                max_auto_entries=config.GLOSSARY_MAX_AUTO_ENTRIES,
                max_prompt_entries=config.GLOSSARY_MAX_PROMPT_ENTRIES,
                max_candidates=config.GLOSSARY_MAX_CANDIDATES)
            self.glossary_extractor = glossary_extractor or ModelGlossaryExtractor(
                lambda: get_translation_provider(provider_name, model=model,
                                                api_key=api_key, base_url=base_url))
        self._prompt_entries = None

    def close(self) -> None:
        self.provider.close()

    def _build_system_prompt(self) -> str:
        prompt = SYSTEM_TRANSLATE_PROMPT
        selected = self.glossary
        if self._prompt_entries is not None:
            selected = Glossary()
            selected.entries = self._prompt_entries
        glossary_prompt = selected.to_prompt_instruction()
        if glossary_prompt:
            prompt += f"\n\n{glossary_prompt}"
        return prompt

    def translate_chunk(self, text_chunk: str) -> str:
        """
        Dịch một đoạn văn bản.
        """
        translated = self.provider.generate(
            system_prompt=self._build_system_prompt(),
            user_prompt=f"Hãy dịch đoạn văn sau sang tiếng Việt:\n\n{text_chunk}",
        )
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("Model trả về bản dịch rỗng hoặc không hợp lệ.")
        translated = translated.strip()
        # Loại bỏ bọc markdown codeblock nếu model vô tình thêm vào
        if translated.startswith("```") and translated.endswith("```"):
            lines = translated.split("\n")
            translated = "\n".join(lines[1:-1]).strip()
        return translated

    def translate_text(self, text: str, max_chunk_chars: int = 4000) -> str:
        """
        Dịch toàn bộ văn bản (hỗ trợ chia nhỏ nếu văn bản quá dài).
        """
        self.provider.reset_conversation()
        try:
            chunker = TextChunker(max_chars=max_chunk_chars)
            chunks = chunker.chunk_text(text)
            translated_chunks = []
            limit = self.provider.conversation_limit
            if not isinstance(limit, int) or limit < 1:
                limit = 1
            for offset in range(0, len(chunks), limit):
                batch = chunks[offset:offset + limit]
                self.provider.reset_conversation()
                if self.glossary_manager:
                    self._prompt_entries = self.glossary_manager.select_entries(batch)
                pairs = []
                try:
                    for chunk in batch:
                        translated = self.translate_chunk(chunk)
                        translated_chunks.append(translated)
                        pairs.append((chunk, translated))
                finally:
                    # Persist evidence from successful chunks even if a later chunk fails.
                    self.provider.reset_conversation()
                    if pairs and self.glossary_manager and self.glossary_extractor:
                        try:
                            self.glossary_manager.record_evidence(pairs)
                            candidates = self.glossary_extractor.extract(pairs)
                            added = self.glossary_manager.update(pairs, candidates)
                            logger.info("Glossary: %d cặp đoạn, thêm %d thuật ngữ.", len(pairs), len(added))
                        except Exception as error:
                            logger.warning("Không cập nhật được glossary: %s", error)
            return "\n\n".join(translated_chunks)
        finally:
            self._prompt_entries = None
            self.provider.reset_conversation()

    def translate_file(self, input_file: Path, output_file: Optional[Path] = None) -> Path:
        """
        Đọc file EN, dịch sang tiếng Việt và lưu vào output_file.
        """
        if not input_file.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {input_file}")

        text = input_file.read_text(encoding="utf-8")
        translated_text = self.translate_text(text)

        if output_file is None:
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_file = config.OUTPUT_DIR / f"{input_file.stem}_vi.txt"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(translated_text, encoding="utf-8")
        return output_file

