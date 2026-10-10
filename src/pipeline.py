import time
from pathlib import Path
from typing import Optional, List, Tuple
from rich.console import Console

from src import config
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
        self.translator = translator
        self.tts_provider = tts_provider or get_tts_provider()
        self.audio_merger = audio_merger or AudioMerger()
        self.chunker = chunker or TextChunker(max_chars=config.MAX_CHUNK_CHARS)
        self.concurrency = config.TTS_CONCURRENCY if concurrency is None else concurrency
        if self.concurrency < 1:
            raise ValueError("concurrency phải >= 1.")

    def translate_only(self, input_file: Path, output_file: Optional[Path] = None) -> Path:
        """Chỉ thực hiện bước dịch EN -> VI."""
        console.print(f"[bold cyan]>> Đang dịch file:[/bold cyan] {input_file.name}")
        if self.translator is None:
            self.translator = NovelTranslator()
        vi_file = self.translator.translate_file(input_file, output_file)
        console.print(f"[bold green]✔ Đã dịch xong và lưu tại:[/bold green] {vi_file}")
        return vi_file

    def _tts_runner(self, state_dir=None, retries=2):
        from src.tts_jobs import TTSJobRunner
        return TTSJobRunner(self.tts_provider, self.audio_merger, self.chunker,
                            state_dir or config.OUTPUT_DIR / ".state",
                            self.concurrency, retries)

    def tts_only(self, vi_file: Path, output_audio: Optional[Path] = None,
                 cleanup_temp: bool = True, resume: bool = True,
                 state_dir: Optional[Path] = None, retries: int = 2) -> Path:
        """Generate a Vietnamese chapter with durable checkpoints."""
        self.audio_merger.check_environment()
        base_name = vi_file.stem.removesuffix("_vi")
        output_audio = output_audio or config.OUTPUT_DIR / f"{base_name}.mp3"
        return self._tts_runner(state_dir, retries).run(
            vi_file, output_audio, resume=resume, cleanup=cleanup_temp)

    def tts_batch(self, vi_files: List[Path], combine: bool = False,
                  output_audio: Optional[Path] = None, cleanup_temp: bool = True,
                  resume: bool = True, state_dir: Optional[Path] = None,
                  retries: int = 2, continue_on_error: bool = True) -> List[Path]:
        """Checkpoint chapters independently; combine only a complete batch."""
        from src.utils import natural_sort_paths
        sorted_files = natural_sort_paths(vi_files)
        if not sorted_files:
            raise ValueError("Danh sách chương trống.")
        if output_audio and not combine:
            raise ValueError("--output cho thư mục yêu cầu --combine.")
        targets = [config.OUTPUT_DIR / f"{f.stem.removesuffix('_vi')}.mp3"
                   for f in sorted_files]
        if len(set(p.resolve() for p in targets)) != len(targets):
            raise ValueError("Tên chương trùng đường dẫn audio đầu ra.")
        self.audio_merger.check_environment()
        runner = self._tts_runner(state_dir, retries)
        output_files, failures = [], []
        self.last_batch_report = {"completed": [], "failed": [], "interrupted": []}
        self._save_batch_report(runner, sorted_files)
        for source, target in zip(sorted_files, targets):
            try:
                out = runner.run(source, target, resume=resume, cleanup=cleanup_temp)
                output_files.append(out)
                self.last_batch_report["completed"].append(str(source))
            except (KeyboardInterrupt, SystemExit):
                self.last_batch_report["interrupted"].append(str(source))
                self._save_batch_report(runner, sorted_files)
                raise
            except Exception as error:
                failures.append((source, str(error)))
                self.last_batch_report["failed"].append({"source": str(source), "error": str(error)})
                console.print(f"[red]✖ {source.name}: {error}[/red]")
                if not continue_on_error:
                    self._save_batch_report(runner, sorted_files)
                    break
            self._save_batch_report(runner, sorted_files)
        console.print(f"[cyan]Tổng kết: {len(output_files)}/{len(sorted_files)} chương hoàn thành; "
                      f"{len(failures)} lỗi; {len(sorted_files)-len(output_files)-len(failures)} chưa xử lý.[/cyan]")
        self._save_batch_report(runner, sorted_files)
        if failures:
            raise RuntimeError("Có chương thất bại. Chạy lại cùng lệnh để tiếp tục; "
                               "chương hoàn thành sẽ được tái sử dụng.")
        if combine:
            target = output_audio or config.OUTPUT_DIR / "combined_novel.mp3"
            if target.resolve() in {p.resolve() for p in output_files}:
                raise ValueError("File gộp phải khác file audio từng chương.")
            runner.combine(output_files, target, resume=resume)
            console.print(f"[green]✔ Audio gộp: {target}[/green]")
            return [target]
        return output_files

    def _save_batch_report(self, runner, sorted_files):
        import json
        report = self.last_batch_report
        processed = set(report["completed"] + report["interrupted"] +
                        [item["source"] for item in report["failed"]])
        report["unprocessed"] = [str(f) for f in sorted_files if str(f) not in processed]
        report_path = runner.store.directory / "last_batch_report.json"
        report_temp = report_path.with_suffix(".partial.json")
        report_temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report_temp.replace(report_path)

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

