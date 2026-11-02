import time
from pathlib import Path
from typing import Optional, List, Tuple
from rich.console import Console

from src import config
from src.progress import emit
from src.translator import NovelTranslator
from src.text_chunker import TextChunker
from src.tts import get_tts_provider, BaseTTSProvider
from src.audio_merger import AudioMerger
from src.video.base import VideoRenderer

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
        progress=None,
    ):
        self.progress = progress
        self.translator = translator
        self.tts_provider = tts_provider
        self.audio_merger = audio_merger or AudioMerger()
        self.chunker = chunker or TextChunker(max_chars=config.MAX_CHUNK_CHARS)
        self.concurrency = config.TTS_CONCURRENCY if concurrency is None else concurrency
        if self.concurrency < 1:
            raise ValueError("concurrency phải >= 1.")

    def translate_only(self, input_file: Path, output_file: Optional[Path] = None) -> Path:
        """Chỉ thực hiện bước dịch EN -> VI."""
        console.print(f"[bold cyan]>> Đang dịch file:[/bold cyan] {input_file.name}")
        if self.translator is None:
            self.translator = NovelTranslator(progress=self.progress)
        vi_file = self.translator.translate_file(input_file, output_file)
        console.print(f"[bold green]✔ Đã dịch xong và lưu tại:[/bold green] {vi_file}")
        return vi_file

    def _tts_runner(self, state_dir=None, retries=2):
        from src.tts_jobs import TTSJobRunner
        if self.tts_provider is None:
            self.tts_provider = get_tts_provider()
        return TTSJobRunner(self.tts_provider, self.audio_merger, self.chunker,
                            state_dir or config.OUTPUT_DIR / ".state",
                            self.concurrency, retries, progress=self.progress)

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

    def fetch_only(self, url: str, *, max_chapters: int = 1,
                   output_dir: Optional[Path] = None, source=None) -> List[Path]:
        from src.source_fetcher import fetch_chapters
        return fetch_chapters(url, output_dir or config.INPUT_DIR / "web",
                              max_chapters=max_chapters, source=source)

    def process_url(self, url: str, *, max_chapters: int = 1,
                    output_audio: Optional[Path] = None, cleanup_temp: bool = True,
                    source=None) -> List[Tuple[Path, Path]]:
        if output_audio is not None and max_chapters != 1:
            raise ValueError("--output chỉ dùng khi lấy một chương.")
        sources = self.fetch_only(url, max_chapters=max_chapters, source=source)
        return [self.process_file(path, output_audio=output_audio, cleanup_temp=cleanup_temp)
                for path in sources]

    def plan_videos(self, chapter_audio: List[Path], *, chapters_per_video: Optional[int] = None):
        """Group existing chapter audio for future rendering; do not merge TXT/audio."""
        from src.video.planner import plan_videos
        count = config.VIDEO_CHAPTERS_PER_VIDEO if chapters_per_video is None else chapters_per_video
        return plan_videos(chapter_audio, chapters_per_video=count)

    def render_videos(self, chapter_audio: List[Path], background: Path, *,
                      output_dir: Optional[Path] = None, title: str = "",
                      chapters_per_video: Optional[int] = None, resume: bool = True,
                      renderer: Optional[VideoRenderer] = None,
                      translated_files: Optional[List[Path]] = None, story_config: Optional[Path] = None,
                      metadata_generator=None, metadata_provider=None, metadata_model=None) -> List[Path]:
        from src.video.base import VideoSpec
        from src.video.ffmpeg import FFmpegVideoRenderer
        episodes = self.plan_videos(chapter_audio, chapters_per_video=chapters_per_video)
        if not episodes:
            raise ValueError("Không có audio chương để render.")
        directory = output_dir or config.OUTPUT_DIR / "videos"
        renderer = renderer if renderer is not None else FFmpegVideoRenderer(
            state_dir=config.OUTPUT_DIR / ".state" / "video", progress=self.progress)
        service, story = None, None
        translation_map = {}
        if story_config is not None:
            from src.publishing.episode_metadata import (EpisodeMetadataService,
                LLMEpisodeMetadataGenerator, load_story_config)
            from src.publishing.metadata import load_metadata
            story = load_story_config(story_config)
            if translated_files is None or len(translated_files) != len(chapter_audio):
                raise ValueError("Cần bản dịch tương ứng với từng audio chương để tạo metadata.")
            translation_map = {Path(audio).resolve(): Path(text)
                               for audio, text in zip(chapter_audio, translated_files)}
            generator = metadata_generator if metadata_generator is not None else LLMEpisodeMetadataGenerator(
                provider_name=metadata_provider, model=metadata_model,
                max_input_chars=config.METADATA_MAX_INPUT_CHARS)
            service = EpisodeMetadataService(generator)
        outputs = []
        for episode in episodes:
            first, last = episode.chapter_audio[0].stem, episode.chapter_audio[-1].stem
            stem = first if first == last else f"{first}__to__{last}"
            label = title or first
            if title and len(episodes) > 1:
                label = f"{title} — Tập {episode.number}"
            output_path = Path(directory) / f"{stem}.mp4"
            thumbnail_text = None
            if service is not None:
                emit(self.progress, "metadata", 0, 1, "tập")
                dynamic, metadata_path = service.prepare(output_path,
                    [translation_map[Path(audio).resolve()] for audio in episode.chapter_audio], story, resume=resume)
                emit(self.progress, "metadata", 1, 1, "tập")
                if not title:
                    label = load_metadata(metadata_path, output_path)['title']
                thumbnail_text = dynamic.thumbnail_text
            spec = VideoSpec(episode.chapter_audio, Path(background), output_path,
                             label, config.VIDEO_WIDTH, config.VIDEO_HEIGHT, config.VIDEO_FPS,
                             Path(config.VIDEO_FONT_PATH) if config.VIDEO_FONT_PATH else None, thumbnail_text)
            output = renderer.render(spec, resume=resume)
            outputs.append(output)
            console.print(f"[green]✔ Video: {output}[/green]")
        return outputs

    def upload_videos(self, videos: List[Path], *, title: Optional[str] = None,
                      description: Optional[str] = None, privacy: Optional[str] = None,
                      channel_id: Optional[str] = None, tags=None, made_for_kids=None,
                      use_thumbnail=None, metadata_file: Optional[Path] = None, publisher=None):
        from src.publishing.metadata import build_upload_spec
        from src.publishing.jobs import PublishingRunner
        channel_id = channel_id if channel_id is not None else config.YOUTUBE_CHANNEL_ID
        if not channel_id:
            raise ValueError("Cần YOUTUBE_CHANNEL_ID; chạy youtube-auth để xem kênh.")
        if not videos:
            raise ValueError("Không có video để upload.")
        specs = [build_upload_spec(video, channel_id=channel_id, title=title,
            description=description, privacy=privacy, default_privacy=config.YOUTUBE_PRIVACY, tags=tags,
            category_id=config.YOUTUBE_CATEGORY_ID, made_for_kids=made_for_kids,
            use_thumbnail=use_thumbnail, metadata_file=metadata_file) for video in videos]
        for spec in specs:
            PublishingRunner._validate(spec)
        owned = publisher is None
        if publisher is None:
            from src.publishing.youtube import YouTubePublisher
            publisher = YouTubePublisher(token_path=config.YOUTUBE_TOKEN_FILE)
        try:
            runner = PublishingRunner(publisher, config.YOUTUBE_STATE_DIR, progress=self.progress)
            results = []
            for spec in specs:
                result = runner.publish(spec)
                results.append(result)
                console.print(f"[green]✔ YouTube: {result.url}[/green]")
            return results
        finally:
            if owned:
                publisher.close()

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

