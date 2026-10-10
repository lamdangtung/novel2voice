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


@app.command("process")
def process_command(
    input_path: Path = typer.Argument(
        ...,
        help="Đường dẫn file .txt truyện tiếng Anh hoặc thư mục chứa các file truyện."
    ),
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
    try:
        glossary = Glossary(glossary_path or config.GLOSSARY_PATH)
        translator = NovelTranslator(model=model, glossary=glossary)
        tts_prov = get_tts_provider(provider_name=provider, voice=voice, rate=rate)
        pipeline = NovelPipeline(
            translator=translator,
            tts_provider=tts_prov,
            concurrency=concurrency
        )

        if input_path.is_file():
            pipeline.process_file(
                input_file=input_path,
                output_audio=output_audio,
                cleanup_temp=cleanup_temp
            )
        elif input_path.is_dir():
            files = natural_sort_paths(list(input_path.glob("*.txt")))
            if not files:
                console.print(f"[bold red]Không tìm thấy file .txt nào trong thư mục:[/bold red] {input_path}")
                raise typer.Exit(code=1)

            console.print(f"[bold cyan]Tìm thấy {len(files)} files cần xử lý trong thư mục {input_path} (theo thứ tự tự nhiên)[/bold cyan]")
            for f in files:
                pipeline.process_file(input_file=f, cleanup_temp=cleanup_temp)
        else:
            console.print(f"[bold red]Đường dẫn không hợp lệ:[/bold red] {input_path}")
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"\n[bold red]✖ Lỗi:[/bold red] {e}")
        raise typer.Exit(code=1)


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
    glossary_path: Optional[Path] = typer.Option(
        None,
        "--glossary", "-g",
        help="Đường dẫn file glossary.csv."
    )
):
    """
    Chỉ thực hiện dịch file truyện từ tiếng Anh sang tiếng Việt.
    """
    try:
        glossary = Glossary(glossary_path or config.GLOSSARY_PATH)
        translator = NovelTranslator(model=model, glossary=glossary)
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

