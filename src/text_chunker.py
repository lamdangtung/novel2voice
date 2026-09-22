import re
from typing import List


class TextChunker:
    """
    Hỗ trợ chia nhỏ văn bản dài thành các đoạn (chunks) an toàn cho dịch thuật và Text-to-Speech.
    Ưu tiên ngắt theo đoạn văn, câu hoặc dấu ngắt câu, không ngắt giữa từ.
    """

    def __init__(self, max_chars: int = 1500):
        self.max_chars = max_chars

    def split_into_paragraphs(self, text: str) -> List[str]:
        # Tách theo 1 hoặc nhiều dòng trống
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text)]
        return [p for p in paragraphs if p]

    def split_into_sentences(self, text: str) -> List[str]:
        # Tách theo các dấu câu kết thúc (. ! ? …) kèm khoảng trắng
        sentence_endings = re.compile(r'(?<=[.!?…])\s+')
        sentences = sentence_endings.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def chunk_text(self, text: str) -> List[str]:
        """
        Chia văn bản thành danh sách các đoạn không vượt quá max_chars.
        """
        paragraphs = self.split_into_paragraphs(text)
        chunks: List[str] = []
        current_chunk = ""

        for para in paragraphs:
            # Nếu bản thân paragraph dài hơn max_chars, ta phải chia nhỏ paragraph đó theo câu
            if len(para) > self.max_chars:
                # Nếu current_chunk đã có nội dung, chốt chunk đó trước
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                sentences = self.split_into_sentences(para)
                sub_chunk = ""
                for sent in sentences:
                    # Nếu câu dài hơn max_chars (hiếm gặp), cắt theo từ
                    if len(sent) > self.max_chars:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                            sub_chunk = ""
                        words = sent.split()
                        w_chunk = ""
                        for word in words:
                            if len(w_chunk) + len(word) + 1 <= self.max_chars:
                                w_chunk = f"{w_chunk} {word}" if w_chunk else word
                            else:
                                if w_chunk:
                                    chunks.append(w_chunk.strip())
                                w_chunk = word
                        if w_chunk:
                            chunks.append(w_chunk.strip())
                    else:
                        cand = f"{sub_chunk} {sent}" if sub_chunk else sent
                        if len(cand) <= self.max_chars:
                            sub_chunk = cand
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk.strip())
                            sub_chunk = sent
                if sub_chunk:
                    chunks.append(sub_chunk.strip())

            else:
                # Nếu para vừa hoặc nhỏ
                cand = f"{current_chunk}\n\n{para}" if current_chunk else para
                if len(cand) <= self.max_chars:
                    current_chunk = cand
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

