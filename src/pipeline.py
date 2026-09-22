import time
from pathlib import Path
from typing import Optional, List, Tuple
from tqdm import tqdm
from rich.console import Console

from src import config
from src.glossary import Glossary
from src.translator import NovelTranslator
from src.text_chunker import TextChunker
from src.tts import get_tts_provider, BaseTTSProvider
from src.audio_merger import AudioMerger

console = Console()


class NovelPipeline:
    """
    Quy trình tự động hóa toàn diện từ file text truyện tiếng Anh -> file audio tiếng Việt.
    """

    def __init__(
        self,
        translator: Optional[NovelTranslator] = None,
        tts_provider: Optional[BaseTTSProvider] = None,
        audio_merger: Optional[AudioMerger] = None,
        chunker: Optional[TextChunker] = None,
        concurrency: Optional[int] = None,
    ):
        self.translator = translator or NovelTranslator()
        self.tts_provider = tts_provider or get_tts_provider()
        self.audio_merger = audio_merger or AudioMerger()
        self.chunker = chunker or TextChunker(max_chars=config.MAX_CHUNK_CHARS)
        self.concurrency = concurrency or config.TTS_CONCURRENCY

    def translate_only(self, input_file: Path, output_file: Optional[Path] = None) -> Path:
        """Chỉ thực hiện bước dịch EN -> VI."""
        console.print(f"[bold cyan]>> Đang dịch file:[/bold cyan] {input_file.name}")
        vi_file = self.translator.translate_file(input_file, output_file)
        console.print(f"[bold green]✔ Đã dịch xong và lưu tại:[/bold green] {vi_file}")
        return vi_file

    def tts_only(
        self,
        vi_file: Path,
        output_audio: Optional[Path] = None,
        cleanup_temp: bool = True
    ) -> Path:
        """Chuyển đổi file tiếng Việt có sẵn thành audio MP3."""
        if not vi_file.exists():
            raise FileNotFoundError(f"File tiếng Việt không tồn tại: {vi_file}")

        text = vi_file.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"File {vi_file} rỗng, không có nội dung để đọc.")

        if output_audio is None:
            # Lược bỏ hậu tố _vi nếu có để tên file audio gọn gàng
            base_name = vi_file.stem
            if base_name.endswith("_vi"):
                base_name = base_name[:-3]
            output_audio = config.OUTPUT_DIR / f"{base_name}.mp3"

        chunks = self.chunker.chunk_text(text)
        console.print(f"[bold cyan]>> Tạo audio:[/bold cyan] {len(chunks)} đoạn văn bản (chạy song song {self.concurrency} luồng)...")

        temp_dir = config.TEMP_DIR / vi_file.stem
        temp_dir.mkdir(parents=True, exist_ok=True)

        tasks = [
            (chunk, temp_dir / f"chunk_{idx:04d}.mp3")
            for idx, chunk in enumerate(chunks, start=1)
        ]
        chunk_files = [path for _, path in tasks]

        try:
            self.tts_provider.generate_batch(
                tasks=tasks,
                max_concurrency=self.concurrency,
                show_progress=True
            )

            console.print("[bold cyan]>> Đang ghép nối các đoạn audio bằng ffmpeg...[/bold cyan]")
            final_audio = self.audio_merger.merge_mp3_files(
                audio_files=chunk_files,
                output_file=output_audio,
                cleanup_inputs=cleanup_temp
            )
            duration = self.audio_merger.get_duration(final_audio)
            duration_str = f" ({duration:.1f}s)" if duration else ""
            console.print(f"[bold green]✔ Đã tạo file audio thành công:[/bold green] {final_audio}{duration_str}")
            return final_audio

        finally:
            if cleanup_temp and temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def tts_batch(
        self,
        vi_files: List[Path],
        combine: bool = False,
        output_audio: Optional[Path] = None,
        cleanup_temp: bool = True
    ) -> List[Path]:
        """
        Xử lý TTS cho danh sách nhiều file tiếng Việt theo thứ tự tự nhiên.
        - combine=False (Mặc định): Mỗi file text tạo ra 1 file mp3 riêng biệt tương ứng.
        - combine=True: Gộp toàn bộ nội dung của tất cả các file thành 1 file mp3 duy nhất theo thứ tự.
        """
        from src.utils import natural_sort_paths
        sorted_files = natural_sort_paths(vi_files)

        if not combine:
            output_files = []
            for f in sorted_files:
                out = self.tts_only(vi_file=f, cleanup_temp=cleanup_temp)
                output_files.append(out)
            return output_files

        # Trường hợp combine=True: Gộp tất cả các file vào chung 1 file audio
        console.print(f"\n[bold cyan]>> Chế độ gộp (Combine): Ghép {len(sorted_files)} file thành 1 file audio duy nhất...[/bold cyan]")
        batch_temp_dir = config.TEMP_DIR / f"batch_combined_{int(time.time())}"
        batch_temp_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        chunk_global_idx = 1
        for f_idx, f in enumerate(sorted_files, start=1):
            text = f.read_text(encoding="utf-8").strip()
            if not text:
                continue
            chunks = self.chunker.chunk_text(text)
            for chunk in chunks:
                chunk_path = batch_temp_dir / f"chunk_{chunk_global_idx:05d}.mp3"
                tasks.append((chunk, chunk_path))
                chunk_global_idx += 1

        if not tasks:
            raise ValueError("Không có nội dung văn bản nào để tạo audio.")

        console.print(f"[bold cyan]>> Tổng cộng {len(tasks)} đoạn cần tạo TTS (chạy song song {self.concurrency} luồng)...[/bold cyan]")
        try:
            self.tts_provider.generate_batch(
                tasks=tasks,
                max_concurrency=self.concurrency,
                show_progress=True
            )
            all_chunk_files = [p for _, p in tasks]

            if output_audio is None:
                output_audio = config.OUTPUT_DIR / "combined_novel.mp3"

            console.print(f"[bold cyan]>> Đang ghép nối tất cả {len(all_chunk_files)} đoạn audio thành 1 file...[/bold cyan]")
            final_audio = self.audio_merger.merge_mp3_files(
                audio_files=all_chunk_files,
                output_file=output_audio,
                cleanup_inputs=cleanup_temp
            )
            duration = self.audio_merger.get_duration(final_audio)
            duration_str = f" ({duration:.1f}s)" if duration else ""
            console.print(f"[bold green]✔ Đã tạo file audio gộp thành công:[/bold green] {final_audio}{duration_str}\n")
            return [final_audio]

        finally:
            if cleanup_temp and batch_temp_dir.exists():
                import shutil
                shutil.rmtree(batch_temp_dir, ignore_errors=True)

    def process_file(
        self,
        input_file: Path,
        output_audio: Optional[Path] = None,
        save_translation: bool = True,
        cleanup_temp: bool = True
    ) -> Tuple[Path, Path]:
        """
        Quy trình đầy đủ từ file EN -> file dịch VI -> file audio MP3.
        Trả về tuple (vi_text_path, final_audio_path).
        """
        console.print(f"\n[bold magenta]═══════ Bắt đầu xử lý: {input_file.name} ═══════[/bold magenta]")
        start_time = time.time()

        # 1. Dịch thuật
        vi_text_path = self.translate_only(input_file)

        # 2. Text-to-Speech
        final_audio_path = self.tts_only(
            vi_file=vi_text_path,
            output_audio=output_audio,
            cleanup_temp=cleanup_temp
        )

        elapsed = time.time() - start_time
        console.print(f"[bold green] Hoàn tất toàn bộ quy trình trong {elapsed:.1f} giây.[/bold green]\n")
        return vi_text_path, final_audio_path

