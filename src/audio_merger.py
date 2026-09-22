import subprocess
from pathlib import Path
from typing import List, Optional


class AudioMerger:
    """
    Sử dụng ffmpeg để ghép các đoạn audio .mp3 thành một file audio duy nhất.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def merge_mp3_files(
        self,
        audio_files: List[Path],
        output_file: Path,
        cleanup_inputs: bool = False
    ) -> Path:
        """
        Ghép danh sách các file MP3 thành file output_file bằng ffmpeg concat demuxer.
        """
        if not audio_files:
            raise ValueError("Danh sách audio files trống, không thể ghép.")

        if len(audio_files) == 1:
            # Chỉ có 1 file, copy trực tiếp
            output_file.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(audio_files[0], output_file)
            if cleanup_inputs:
                audio_files[0].unlink(missing_ok=True)
            return output_file

        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Tạo file danh sách tạm thời cho ffmpeg concat demuxer
        list_file = output_file.parent / f"{output_file.stem}_concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for audio_path in audio_files:
                # ffmpeg concat yêu cầu escape dấu nháy đơn
                escaped_path = str(audio_path.resolve()).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        try:
            # Thử phương pháp copy stream nhanh nhất (-c copy)
            cmd_copy = [
                self.ffmpeg_path,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(output_file)
            ]
            result = subprocess.run(
                cmd_copy,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Nếu copy stream lỗi do thông số audio không đồng nhất, fallback sang re-encode
            if result.returncode != 0:
                cmd_reencode = [
                    self.ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(list_file),
                    "-c:a", "libmp3lame",
                    "-q:a", "2",
                    str(output_file)
                ]
                res_reencode = subprocess.run(
                    cmd_reencode,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if res_reencode.returncode != 0:
                    raise RuntimeError(f"Lỗi khi ghép audio bằng ffmpeg: {res_reencode.stderr}")

        finally:
            if list_file.exists():
                list_file.unlink()

        # Dọn dẹp các file chunk tạm nếu được yêu cầu
        if cleanup_inputs:
            for audio_path in audio_files:
                audio_path.unlink(missing_ok=True)

        return output_file

    def get_duration(self, audio_file: Path) -> Optional[float]:
        """
        Lấy thời lượng của file audio (tính bằng giây) qua ffprobe nếu có.
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_file)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
        return None

