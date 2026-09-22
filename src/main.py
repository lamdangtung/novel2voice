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

app = typer.Typer(
    name="novel2voice",
    help="Automation tool: Dịch truyện tiếng Anh sang tiếng Việt & Chuyển đổi thành giọng đọc Audio."
)
console = Console()


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
        help=f"Số luồng xử lý TTS song song (mặc định: {config.TTS_CONCURRENCY})."
    )
):
    """
    Chuyển đổi file văn bản tiếng Việt sang file âm thanh MP3.
    """
    try:
        tts_prov = get_tts_provider(provider_name=provider, voice=voice, rate=rate)
        pipeline = NovelPipeline(tts_provider=tts_prov, concurrency=concurrency)

        if vi_path.is_file():
            pipeline.tts_only(vi_file=vi_path, output_audio=output_audio, cleanup_temp=cleanup_temp)
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
                cleanup_temp=cleanup_temp
            )
        else:
            console.print(f"[bold red]Đường dẫn không tồn tại:[/bold red] {vi_path}")
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"\n[bold red]✖ Lỗi:[/bold red] {e}")
        raise typer.Exit(code=1)


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

