"""Create static backgrounds with a wrapped title, without FFmpeg font filters."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .base import VideoSpec


class PillowThumbnailGenerator:
    def _font(self, size, configured):
        if configured:
            return ImageFont.truetype(str(configured), size)
        candidates = (
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            'C:/Windows/Fonts/arial.ttf',
        )
        for path in candidates:
            if Path(path).is_file():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default(size=size)

    def generate(self, spec: VideoSpec, output: Path) -> None:
        with Image.open(spec.background) as source:
            image = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),
                                 (spec.width, spec.height), method=Image.Resampling.LANCZOS)
        if spec.title.strip():
            font_size = max(12, spec.height // 16)
            draw = ImageDraw.Draw(image)
            margin = max(8, spec.width // 20)
            # Shrink until the full title fits; reject pathological oversized titles.
            if len(spec.title) > 1000:
                raise ValueError('Tiêu đề video tối đa 1000 ký tự.')
            while True:
                font = self._font(font_size, spec.font_path)
                lines, line = [], ''
                for character in ' '.join(spec.title.split()):
                    if line and draw.textlength(line + character, font=font) > spec.width - 2 * margin:
                        lines.append(line.strip())
                        line = character
                    else:
                        line += character
                if line:
                    lines.append(line.strip())
                line_height = font_size + max(4, font_size // 4)
                if len(lines) * line_height <= spec.height // 2:
                    break
                font_size -= 1
                if font_size < 8:
                    raise ValueError('Tiêu đề quá dài cho kích thước video.')
            top = spec.height - len(lines) * line_height - 2 * margin
            draw.rectangle((0, top, spec.width, spec.height), fill=(15, 15, 20))
            for index, line in enumerate(lines):
                draw.text((margin, top + margin + index * line_height), line, font=font, fill='white')
        image.save(output)
