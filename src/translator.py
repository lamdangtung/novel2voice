import os
from pathlib import Path
from typing import Optional, List
from openai import OpenAI
from src.glossary import Glossary
from src.text_chunker import TextChunker
from src import config


SYSTEM_TRANSLATE_PROMPT = """Bạn là một dịch giả tiểu thuyết chuyên nghiệp có văn phong điêu luyện và tinh tế.
Nhiệm vụ của bạn là dịch văn bản chương truyện từ tiếng Anh sang tiếng Việt.

Yêu cầu dịch thuật:
1. Văn phong: Tự nhiên, trôi chảy, đúng chất tiểu thuyết/văn học, không dịch thô kiểu "word-by-word".
2. Ngữ cảnh & Xưng hô: Linh hoạt và phù hợp với bối cảnh truyện (lịch sử, chiến tranh, huyền ảo, hoặc đời thường). Lời thoại cần phản ánh đúng tính cách, vị thế của từng nhân vật.
3. Định dạng: Giữ nguyên cấu trúc phân đoạn, dấu ngoặc kép hội thoại và nhịp văn của tác giả gốc.
4. Chỉ trả về duy nhất nội dung tiếng Việt đã dịch, tuyệt đối không thêm lời chào, giải thích, hay ghi chú bên ngoài."""


class NovelTranslator:
    """
    Dịch văn bản truyện từ tiếng Anh sang tiếng Việt qua OpenAI / OpenAI-compatible API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        glossary: Optional[Glossary] = None
    ):
        self.api_key = api_key or config.OPENAI_API_KEY
        self.base_url = base_url or config.OPENAI_BASE_URL
        self.model = model or config.TRANSLATION_MODEL
        self.glossary = glossary or Glossary(config.GLOSSARY_PATH)

        if not self.api_key:
            # Lưu ý: nếu chưa có key, sẽ thông báo khi gọi translate
            self.client = None
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    def _ensure_client(self):
        if not self.client:
            if not self.api_key:
                raise ValueError(
                    "Chưa cấu hình OPENAI_API_KEY. Vui lòng thiết lập trong file .env "
                    "hoặc truyền qua tham số dòng lệnh."
                )
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    def _build_system_prompt(self) -> str:
        prompt = SYSTEM_TRANSLATE_PROMPT
        glossary_prompt = self.glossary.to_prompt_instruction()
        if glossary_prompt:
            prompt += f"\n\n{glossary_prompt}"
        return prompt

    def translate_chunk(self, text_chunk: str) -> str:
        """
        Dịch một đoạn văn bản.
        """
        self._ensure_client()
        system_prompt = self._build_system_prompt()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Hãy dịch đoạn văn sau sang tiếng Việt:\n\n{text_chunk}"}
            ],
            temperature=0.3
        )
        translated = response.choices[0].message.content.strip()
        # Loại bỏ bọc markdown codeblock nếu model vô tình thêm vào
        if translated.startswith("```") and translated.endswith("```"):
            lines = translated.split("\n")
            translated = "\n".join(lines[1:-1]).strip()
        return translated

    def translate_text(self, text: str, max_chunk_chars: int = 4000) -> str:
        """
        Dịch toàn bộ văn bản (hỗ trợ chia nhỏ nếu văn bản quá dài).
        """
        self._ensure_client()
        if len(text) <= max_chunk_chars:
            return self.translate_chunk(text)

        # Nếu văn bản dài hơn max_chunk_chars, chia theo đoạn để dịch an toàn
        chunker = TextChunker(max_chars=max_chunk_chars)
        chunks = chunker.chunk_text(text)
        translated_chunks = []

        for idx, chunk in enumerate(chunks, start=1):
            translated_part = self.translate_chunk(chunk)
            translated_chunks.append(translated_part)

        return "\n\n".join(translated_chunks)

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

