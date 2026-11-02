import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from src import config
from src.glossary import Glossary
from src.translator import NovelTranslator
from src.tts import get_tts_provider
from src.pipeline import NovelPipeline
from src.utils import natural_sort_paths
import logging

app = typer.Typer(
    name="novel2voice",
    help="Automation tool: Dịch truyện tiếng Anh sang tiếng Việt & Chuyển đổi thành giọng đọc Audio."
)
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


@app.command("youtube-auth")
def youtube_auth_command():
    """Đăng nhập Google bằng OAuth Desktop app và hiển thị ID kênh."""
    publisher = None
    try:
        from src.publishing.auth import login
        from src.publishing.youtube import YouTubePublisher
        login(config.YOUTUBE_CLIENT_SECRETS_FILE, config.YOUTUBE_TOKEN_FILE)
        publisher = YouTubePublisher(token_path=config.YOUTUBE_TOKEN_FILE)
        channel_id = publisher.channel_id()
        console.print(f"[green]✔ Đã kết nối kênh {channel_id}[/green]")
        console.print(f"Thêm vào .env: YOUTUBE_CHANNEL_ID={channel_id}")
    except ImportError:
        console.print("[red]Cần cài requirements-youtube.txt trước khi kết nối.[/red]")
        raise typer.Exit(code=1)
    except Exception as error:
        console.print(f"[red]✖ {error}[/red]")
        raise typer.Exit(code=1)
    finally:
        if publisher:
            publisher.close()


@app.command("youtube-status")
def youtube_status_command():
    """Xem tiến độ upload đã lưu, không gọi YouTube."""
    import sqlite3
    path = config.YOUTUBE_STATE_DIR / "uploads.sqlite3"
    if not path.is_file():
        console.print("Chưa có upload YouTube.")
        return
    table = Table(title="Upload YouTube (trạng thái lưu cục bộ)")
    for heading in ("Kênh", "Trạng thái", "Byte đã gửi", "Video", "Lỗi"):
        table.add_column(heading)
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for channel, status, offset, video_id, error in db.execute(
                "SELECT channel_id,status,offset,video_id,error FROM uploads ORDER BY updated_at DESC"):
            table.add_row(channel, status, str(offset),
                          f"https://www.youtube.com/watch?v={video_id}" if video_id else "", error or "")
    console.print(table)


@app.command("youtube-upload")
def youtube_upload_command(
    video_files: list[Path] = typer.Argument(..., help="Các MP4 đã render."),
    title: Optional[str] = typer.Option(None, "--title"),
    description: Optional[str] = typer.Option(None, "--description"),
    metadata_file: Optional[Path] = typer.Option(None, "--metadata-file", exists=True, dir_okay=False),
    privacy: Optional[str] = typer.Option(None, "--privacy", help="private, unlisted hoặc public; mặc định từ .env."),
    channel_id: Optional[str] = typer.Option(None, "--channel-id"),
    tags: Optional[list[str]] = typer.Option(None, "--tag"),
    made_for_kids: Optional[bool] = typer.Option(None, "--made-for-kids/--not-made-for-kids"),
    thumbnail: Optional[bool] = typer.Option(None, "--thumbnail/--no-thumbnail"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Xem metadata, không đăng nhập hoặc gọi YouTube."),
):
    """Upload video + thumbnail qua OAuth, có checkpoint chống tải trùng."""
    try:
        if dry_run:
            import json
            from dataclasses import asdict
            from src.publishing.metadata import build_upload_spec
            for video in video_files:
                spec = build_upload_spec(video, channel_id=channel_id or config.YOUTUBE_CHANNEL_ID,
                    title=title, description=description, privacy=privacy, default_privacy=config.YOUTUBE_PRIVACY,
                    tags=tags, made_for_kids=made_for_kids, category_id=config.YOUTUBE_CATEGORY_ID,
                    use_thumbnail=thumbnail, metadata_file=metadata_file)
                from src.publishing.jobs import PublishingRunner
                PublishingRunner._validate(spec, require_channel=False)
                console.print_json(json.dumps(asdict(spec), default=str, ensure_ascii=False))
            return
        NovelPipeline().upload_videos(video_files, title=title, description=description,
            privacy=privacy, channel_id=channel_id, tags=tags, made_for_kids=made_for_kids,
            use_thumbnail=thumbnail, metadata_file=metadata_file)
    except ImportError:
        console.print("[red]Cần cài requirements-youtube.txt trước khi upload.[/red]")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        console.print("[yellow]Đã dừng. Chạy lại cùng lệnh để tiếp tục phiên upload.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as error:
        console.print(f"[red]✖ {error}[/red]")
        raise typer.Exit(code=1)


@app.command("render-video")
def render_video_command(
    audio_files: list[Path] = typer.Argument(..., help="Các audio chương thuộc cùng bộ truyện."),
    story_config: Optional[Path] = typer.Option(None, "--story-config", exists=True, dir_okay=False),
    translated_files: Optional[list[Path]] = typer.Option(None, "--translated-file", exists=True, dir_okay=False),
    metadata_provider: Optional[str] = typer.Option(None, "--metadata-provider"),
    metadata_model: Optional[str] = typer.Option(None, "--metadata-model"),
    background: Path = typer.Option(..., "--background", exists=True, file_okay=True, dir_okay=False),
    title: str = typer.Option("", "--title"),
    chapters_per_video: Optional[int] = typer.Option(None, "--chapters-per-video", min=1),
    output_dir: Path = typer.Option(config.OUTPUT_DIR / "videos", "--output-dir"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
):
    """Render MP4, thumbnail JPG và metadata từ audio + ảnh nền."""
    try:
        metadata_options = {} if story_config is None else dict(story_config=story_config,
            translated_files=translated_files, metadata_provider=metadata_provider, metadata_model=metadata_model)
        NovelPipeline().render_videos(audio_files, background, output_dir=output_dir,
                                     title=title, chapters_per_video=chapters_per_video, resume=resume, **metadata_options)
    except KeyboardInterrupt:
        console.print("[yellow]Đã dừng render. Chạy lại để tiếp tục các video còn thiếu.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as error:
        console.print(f"[red]✖ {error}[/red]")
        raise typer.Exit(code=1)


@app.command("plan-videos")
def plan_videos_command(
    audio_files: list[Path] = typer.Argument(..., help="Các file audio chương thuộc cùng một bộ truyện."),
    chapters_per_video: Optional[int] = typer.Option(None, "--chapters-per-video", min=1),
):
    """Xem cách chia chương thành video; chưa render MP4."""
    try:
        for path in audio_files:
            if not path.is_file() or path.suffix.lower() != ".mp3" or path.stat().st_size == 0:
                raise ValueError(f"Audio chương không tồn tại, rỗng hoặc không phải MP3: {path}")
        episodes = NovelPipeline().plan_videos(audio_files, chapters_per_video=chapters_per_video)
        table = Table(title="Kế hoạch video (chưa render)")
        table.add_column("Video")
        table.add_column("Audio chương theo thứ tự")
        for episode in episodes:
            table.add_row(str(episode.number), "\n".join(str(path) for path in episode.chapter_audio))
        console.print(table)
    except Exception as error:
        console.print(f"[red]✖ {error}[/red]")
        raise typer.Exit(code=1)


@app.command("fetch")
def fetch_command(
    url: str = typer.Argument(..., help="URL chương đầu cần lấy."),
    max_chapters: int = typer.Option(1, "--max-chapters", min=1),
    output_dir: Path = typer.Option(config.INPUT_DIR / "web", "--output-dir"),
):
    """Lấy nội dung gốc từ website, chưa dịch hoặc tạo audio."""
    try:
        paths = NovelPipeline().fetch_only(url, max_chapters=max_chapters, output_dir=output_dir)
        for path in paths:
            console.print(f"[green]✔ Đã lưu: {path}[/green]")
    except Exception as error:
        console.print(f"[red]✖ Lỗi lấy truyện: {error}[/red]")
        raise typer.Exit(code=1)


@app.command("process")
def process_command(
    input_path: str = typer.Argument(
        ...,
        help="File TXT, thư mục chứa truyện hoặc URL chương ixdzs8.com."
    ),
    story_config: Optional[Path] = typer.Option(None, "--story-config", exists=True, dir_okay=False),
    upload_youtube: bool = typer.Option(False, "--upload-youtube", help="Upload video sau render; cần OAuth và channel ID."),
    youtube_metadata_file: Optional[Path] = typer.Option(None, "--youtube-metadata-file", exists=True, dir_okay=False),
    youtube_privacy: Optional[str] = typer.Option(None, "--youtube-privacy"),
    background: Optional[Path] = typer.Option(None, "--background", exists=True, dir_okay=False,
                                            help="Ảnh nền; có tùy chọn này sẽ render video sau TTS."),
    video_title: str = typer.Option("", "--video-title"),
    video_output_dir: Path = typer.Option(config.OUTPUT_DIR / "videos", "--video-output-dir"),
    chapters_per_video: Optional[int] = typer.Option(None, "--chapters-per-video", min=1),
    max_chapters: int = typer.Option(1, "--max-chapters", min=1, help="Số chương tối đa khi đầu vào là URL."),
    output_audio: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Đường dẫn file .mp3 đầu ra (nếu xử lý 1 file)."
    ),
    voice: Optional[str] = typer.Option(
        None,
        "--voice", "-v",
        help=f"Giọng đọc TTS (mặc định: {config.TTS_VOICE})."
    ),
    rate: Optional[str] = typer.Option(
        None,
        "--rate", "-r",
        help=f"Tốc độ đọc, ví dụ '+10%', '-5%' (mặc định: {config.TTS_RATE})."
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider", "-p",
        help=f"Nhà cung cấp TTS ('edge-tts' hoặc 'openai', mặc định: {config.TTS_PROVIDER})."
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help=f"Model dịch thuật (mặc định: {config.TRANSLATION_MODEL})."
    ),
    translation_provider: Optional[str] = typer.Option(
        None, "--translation-provider", help="Provider dịch: openai hoặc deepseek (native)."
    ),
    glossary_path: Optional[Path] = typer.Option(
        None,
        "--glossary", "-g",
        help="Đường dẫn file glossary.csv để chuẩn hóa thuật ngữ."
    ),
    cleanup_temp: bool = typer.Option(
        True,
        "--cleanup/--no-cleanup",
        help="Xóa các file audio chunks tạm thời sau khi ghép."
    ),
    concurrency: int = typer.Option(
        config.TTS_CONCURRENCY,
        "--concurrency", "-j",
        help=f"Số luồng xử lý TTS song song (mặc định: {config.TTS_CONCURRENCY})."
    )
):
    """
    Thực hiện trọn gói quy trình: Dịch file EN -> Lưu bản dịch VI -> Tạo audio MP3.
    """
    translator = None
    try:
        if story_config is not None:
            from src.publishing.episode_metadata import load_story_config
            load_story_config(story_config)
            if background is None:
                raise ValueError("--story-config cần --background để tạo metadata và video.")
            if youtube_metadata_file is not None:
                raise ValueError("Chọn --story-config hoặc --youtube-metadata-file, không dùng đồng thời.")
        if upload_youtube:
            if background is None:
                raise ValueError("--upload-youtube cần --background để render video.")
            if not config.YOUTUBE_CHANNEL_ID or not config.YOUTUBE_TOKEN_FILE.is_file():
                raise ValueError("Chạy youtube-auth và cấu hình YOUTUBE_CHANNEL_ID trước khi chạy pipeline upload.")
        glossary = Glossary(glossary_path or config.GLOSSARY_PATH)
        translator = NovelTranslator(model=model, glossary=glossary, provider_name=translation_provider)
        tts_prov = get_tts_provider(provider_name=provider, voice=voice, rate=rate)
        pipeline = NovelPipeline(
            translator=translator,
            tts_provider=tts_prov,
            concurrency=concurrency
        )

        if input_path.startswith(("https://", "http://")):
            results = pipeline.process_url(input_path, max_chapters=max_chapters,
                                 output_audio=output_audio, cleanup_temp=cleanup_temp)
            if background:
                metadata_options = {} if story_config is None else dict(story_config=story_config,
                    translated_files=[text for text, _ in results], metadata_provider=translation_provider, metadata_model=model)
                videos = pipeline.render_videos([audio for _, audio in results], background,
                    output_dir=video_output_dir, title=video_title, chapters_per_video=chapters_per_video, **metadata_options)
                if upload_youtube:
                    pipeline.upload_videos(videos, privacy=youtube_privacy, metadata_file=youtube_metadata_file)
            return
        input_path = Path(input_path)
        results = []
        if input_path.is_file():
            results.append(pipeline.process_file(
                input_file=input_path,
                output_audio=output_audio,
                cleanup_temp=cleanup_temp
            ))
        elif input_path.is_dir():
            files = natural_sort_paths(list(input_path.glob("*.txt")))
            if not files:
                console.print(f"[bold red]Không tìm thấy file .txt nào trong thư mục:[/bold red] {input_path}")
                raise typer.Exit(code=1)

            console.print(f"[bold cyan]Tìm thấy {len(files)} files cần xử lý trong thư mục {input_path} (theo thứ tự tự nhiên)[/bold cyan]")
            for f in files:
                results.append(pipeline.process_file(input_file=f, cleanup_temp=cleanup_temp))
        else:
            console.print(f"[bold red]Đường dẫn không hợp lệ:[/bold red] {input_path}")
            raise typer.Exit(code=1)
        if background:
            metadata_options = {} if story_config is None else dict(story_config=story_config,
                translated_files=[text for text, _ in results], metadata_provider=translation_provider, metadata_model=model)
            videos = pipeline.render_videos([audio for _, audio in results], background,
                output_dir=video_output_dir, title=video_title, chapters_per_video=chapters_per_video, **metadata_options)
            if upload_youtube:
                pipeline.upload_videos(videos, privacy=youtube_privacy, metadata_file=youtube_metadata_file)

    except Exception as e:
        console.print(f"\n[bold red]✖ Lỗi:[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        if translator is not None:
            translator.close()


@app.command("translate")
def translate_command(
    input_path: Path = typer.Argument(
        ...,
        help="Đường dẫn file .txt tiếng Anh hoặc thư mục chứa các file truyện."
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Đường dẫn file bản dịch tiếng Việt đầu ra."
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help=f"Model dịch thuật (mặc định: {config.TRANSLATION_MODEL})."
    ),
    translation_provider: Optional[str] = typer.Option(
        None, "--translation-provider", help="Provider dịch: openai hoặc deepseek (native)."
    ),
    glossary_path: Optional[Path] = typer.Option(
        None,
        "--glossary", "-g",
        help="Đường dẫn file glossary.csv."
    )
):
    """
    Chỉ thực hiện dịch file truyện từ tiếng Anh sang tiếng Việt.
    """
    translator = None
    try:
        glossary = Glossary(glossary_path or config.GLOSSARY_PATH)
        translator = NovelTranslator(model=model, glossary=glossary, provider_name=translation_provider)
        pipeline = NovelPipeline(translator=translator)

        if input_path.is_file():
            pipeline.translate_only(input_file=input_path, output_file=output_file)
        elif input_path.is_dir():
            files = natural_sort_paths(list(input_path.glob("*.txt")))
            if not files:
                console.print(f"[bold red]Không tìm thấy file .txt nào trong thư mục:[/bold red] {input_path}")
                raise typer.Exit(code=1)

            console.print(f"[bold cyan]Tìm thấy {len(files)} files cần dịch trong thư mục {input_path} (theo thứ tự tự nhiên)[/bold cyan]")
            for f in files:
                pipeline.translate_only(input_file=f)
        else:
            console.print(f"[bold red]Đường dẫn không tồn tại:[/bold red] {input_path}")
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"\n[bold red]✖ Lỗi:[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        if translator is not None:
            translator.close()


@app.command("tts")
def tts_command(
    vi_path: Path = typer.Argument(
        ...,
        help="Đường dẫn file .txt tiếng Việt hoặc thư mục chứa các file tiếng Việt."
    ),
    output_audio: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Đường dẫn file .mp3 đầu ra."
    ),
    voice: Optional[str] = typer.Option(
        None,
        "--voice", "-v",
        help="Giọng đọc theo provider; VieNeu mặc định dùng VIENEU_VOICE."
    ),
    rate: Optional[str] = typer.Option(
        None,
        "--rate", "-r",
        help=f"Tốc độ đọc, ví dụ '+10%', '-5%' (mặc định: {config.TTS_RATE})."
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider", "-p",
        help=f"Nhà cung cấp TTS ('vieneu', 'piper', 'edge-tts', 'openai', mặc định: {config.TTS_PROVIDER})."
    ),
    cleanup_temp: bool = typer.Option(
        True,
        "--cleanup/--no-cleanup",
        help="Xóa các file audio chunks tạm thời sau khi ghép."
    ),
    combine: bool = typer.Option(
        False,
        "--combine", "-c",
        help="Gộp tất cả các file trong thư mục thành 1 file MP3 duy nhất theo đúng thứ tự số chương."
    ),
    concurrency: int = typer.Option(
        config.TTS_CONCURRENCY,
        "--concurrency", "-j",
        min=1,
        help=f"Số luồng xử lý TTS song song (mặc định: {config.TTS_CONCURRENCY})."
    ),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Tái sử dụng kết quả hợp lệ; --no-resume tạo lại audio."),
    state_dir: Path = typer.Option(config.OUTPUT_DIR / ".state", "--state-dir", help="Thư mục checkpoint SQLite và audio tạm."),
    retries: int = typer.Option(2, "--retries", min=0, help="Số lần thử lại đoạn lỗi trong một lần chạy."),
    continue_on_error: bool = typer.Option(True, "--continue-on-error/--fail-fast", help="Tiếp tục các chương khác khi một chương lỗi."),
):
    """
    Chuyển đổi file văn bản tiếng Việt sang file âm thanh MP3.
    """
    tts_prov = None
    try:
        tts_prov = get_tts_provider(provider_name=provider, voice=voice, rate=rate)
        pipeline = NovelPipeline(tts_provider=tts_prov, concurrency=concurrency)

        if vi_path.is_file():
            pipeline.tts_only(vi_file=vi_path, output_audio=output_audio, cleanup_temp=cleanup_temp, resume=resume, state_dir=state_dir, retries=retries)
        elif vi_path.is_dir():
            files = natural_sort_paths(list(vi_path.glob("*.txt")))
            if not files:
                console.print(f"[bold red]Không tìm thấy file .txt nào trong thư mục:[/bold red] {vi_path}")
                raise typer.Exit(code=1)

            console.print(f"[bold cyan]Tìm thấy {len(files)} files cần tạo TTS trong thư mục {vi_path} (theo thứ tự tự nhiên)[/bold cyan]")
            pipeline.tts_batch(
                vi_files=files,
                combine=combine,
                output_audio=output_audio,
                cleanup_temp=cleanup_temp,
                resume=resume, state_dir=state_dir, retries=retries,
                continue_on_error=continue_on_error
            )
        else:
            console.print(f"[bold red]Đường dẫn không tồn tại:[/bold red] {vi_path}")
            raise typer.Exit(code=1)

    except KeyboardInterrupt:
        console.print("[yellow]Đã dừng. Checkpoint được giữ; chạy lại cùng lệnh để tiếp tục.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as e:
        console.print(f"\n[bold red]✖ Lỗi:[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        if tts_prov is not None and hasattr(tts_prov, "close"):
            tts_prov.close()


@app.command("doctor")
def doctor_command(
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
):
    """Kiểm tra dependency và cấu hình TTS, không nạp model hay gọi mạng."""
    import importlib.util
    from src.audio_merger import AudioMerger
    tts_prov = None
    try:
        AudioMerger().check_environment()
        tts_prov = get_tts_provider(provider_name=provider)
        modules = {"VieNeuTTSProvider": "vieneu", "EdgeTTSProvider": "edge_tts",
                   "LocalTTSProvider": "piper", "OpenAITTSProvider": "openai"}
        module = modules[type(tts_prov).__name__]
        if importlib.util.find_spec(module) is None:
            raise RuntimeError(f"Chưa cài dependency: {module}")
        if getattr(tts_prov, "mode", None) == "remote":
            if not tts_prov.api_base or not tts_prov.model_name:
                raise ValueError("Remote mode cần VIENEU_API_BASE và VIENEU_MODEL_NAME.")
        console.print(f"[green]✔ ffmpeg, ffprobe, dependency: {type(tts_prov).__name__}[/green]")
        console.print(f"Chunk: {config.MAX_CHUNK_CHARS} ký tự; batch: {config.TTS_CONCURRENCY} đoạn.")
        console.print("Kiểm tra này chưa xác nhận model nạp được hoặc chất lượng giọng đọc.")
    except Exception as error:
        console.print(f"[red]✖ {error}[/red]")
        raise typer.Exit(code=1)
    finally:
        if tts_prov is not None and hasattr(tts_prov, "close"):
            tts_prov.close()


@app.command("status")
def status_command(
    state_dir: Path = typer.Option(config.OUTPUT_DIR / ".state", "--state-dir"),
):
    """Xem trạng thái các phiên tạo audio đã lưu."""
    from src.tts_jobs import JobStore
    if not (state_dir / "jobs.sqlite3").exists():
        console.print("Chưa có job TTS.")
        return
    table = Table(title="Trạng thái TTS")
    for column in ("Chương", "Trạng thái", "Cập nhật", "Lỗi"):
        table.add_column(column)
    for row in JobStore(state_dir).rows():
        table.add_row(row["source"], row["status"], row["updated_at"], row["error"] or "")
    console.print(table)


@app.command("voices")
def list_voices():
    """
    Hiển thị danh sách các giọng đọc tiếng Việt được hỗ trợ mặc định bởi Edge-TTS.
    """
    table = Table(title="Giọng đọc Tiếng Việt (Edge-TTS)")
    table.add_column("Tên giọng (Voice ID)", style="cyan", no_wrap=True)
    table.add_column("Giới tính", style="magenta")
    table.add_column("Mô tả / Đánh giá", style="green")

    table.add_row(
        "vi-VN-HoaiMyNeural",
        "Nữ",
        "Giọng truyền cảm, diễn cảm tốt, rất thích hợp đọc tiểu thuyết, truyện tình cảm/hồi ký"
    )
    table.add_row(
        "vi-VN-NamMinhNeural",
        "Nam",
        "Giọng trầm ấm, chững chạc, thích hợp cho truyện lịch sử, kiếm hiệp, trinh thám, phóng sự"
    )

    console.print(table)


if __name__ == "__main__":
    app()

