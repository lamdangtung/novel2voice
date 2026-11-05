"""Execute the same pipeline services used by the existing CLI, one chapter/job."""
import time
import json
from pathlib import Path
from typing import Protocol

from src.glossary import Glossary
from src.pipeline import NovelPipeline
from src.progress import emit
from src.translator import NovelTranslator
from src.tts import get_tts_provider


class PipelineExecutor(Protocol):
    def run(self, settings: dict, chapter: int, progress) -> dict: ...


class FullPipelineExecutor:
    def run(self, settings, chapter, progress):
        from src.publishing.episode_metadata import atomic_json
        from src.tts_jobs import file_digest
        checkpoint = Path(settings['_job_dir']) / 'artifacts.json' if settings.get('_job_dir') else None
        saved = json.loads(checkpoint.read_text()) if checkpoint and checkpoint.is_file() else {}

        def artifacts(stage, paths=None):
            if paths is not None:
                saved[stage] = [{'path': str(Path(p).resolve()), 'hash': file_digest(Path(p))} for p in paths]
                if checkpoint:
                    atomic_json(checkpoint, saved)
            items = saved.get(stage)
            if items is None:
                return None
            for item in items:
                path = Path(item['path'])
                if not path.is_file() or file_digest(path) != item['hash']:
                    raise ValueError(f'Artifact của job đã bị sửa/xóa ở bước {stage}; dừng để tránh tạo upload trùng.')
            return [Path(item['path']) for item in items]

        if settings.get('youtube_publish_at') and not saved.get('video'):
            from src.publishing.schedule import require_future
            require_future(settings['youtube_publish_at'], buffer_seconds=900)
        translator, speech = None, None
        try:
            pipeline = NovelPipeline(progress=progress)
            emit(progress, 'fetch', 0, 1, 'chương')
            sources = artifacts('source')
            if sources is None:
                sources = pipeline.fetch_only(settings['chapter_url_template'].format(chapter=chapter), max_chapters=1)
                artifacts('source', sources)
            emit(progress, 'fetch', 1, 1, 'chương')
            texts = artifacts('translation')
            if texts is None:
                translator = NovelTranslator(provider_name=settings.get('translation_provider', 'deepseek'),
                    model=settings.get('translation_model'), glossary=Glossary(Path(settings['glossary'])), progress=progress)
                pipeline.translator = translator
                texts = [pipeline.translate_only(sources[0])]
                artifacts('translation', texts)
            emit(progress, 'translate', 1, 1, 'chương')
            audios = artifacts('audio')
            if audios is None:
                speech = get_tts_provider(provider_name=settings.get('tts_provider', 'vieneu'))
                pipeline.tts_provider = speech
                emit(progress, 'tts', 0, 1, 'chương')
                audios = [pipeline.tts_only(texts[0])]
                artifacts('audio', audios)
            emit(progress, 'tts', 1, 1, 'chương')
            videos = artifacts('video')
            if videos is None:
                videos = pipeline.render_videos(audios, Path(settings['background']), chapters_per_video=1,
                    story_config=Path(settings['story_config']), translated_files=texts,
                    metadata_provider=settings.get('translation_provider', 'deepseek'), metadata_model=settings.get('translation_model'))
                if settings.get('youtube_publish_at'):
                    for video in videos:
                        metadata_path = video.with_suffix('.youtube.json')
                        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                        metadata.update(privacy='private', publish_at=settings['youtube_publish_at'])
                        atomic_json(metadata_path, metadata)
                # Preserve upload metadata and thumbnail as well as the MP4 on retries.
                artifacts('video_sidecars', [p for v in videos for p in
                    (v.with_suffix('.youtube.json'), v.with_suffix('.jpg')) if p.is_file()])
                artifacts('video', videos)
            else:
                artifacts('video_sidecars')
            emit(progress, 'render', 1, 1, 'video')
            published_urls = saved.get('youtube')
            if settings.get('upload_youtube', True) and published_urls is None:
                emit(progress, 'upload', 0, 1, 'video')
                options = {}
                if settings.get('manual_upload_now'):
                    options = {'clear_publish_schedule': True}
                elif settings.get('youtube_publish_at'):
                    options = {'publish_at': settings['youtube_publish_at']}
                published = pipeline.upload_videos(videos, privacy=settings.get('youtube_privacy', 'private'), **options)
                published_urls = [p.url for p in published]
                saved['youtube'] = published_urls
                if checkpoint:
                    atomic_json(checkpoint, saved)
            return {'videos': [str(v) for v in videos], 'youtube': published_urls or []}
        finally:
            if translator:
                translator.close()
            if speech and hasattr(speech, 'close'):
                speech.close()


class ProgressTracker:
    WEIGHTS = {'fetch': .02, 'translate': .23, 'tts': .45, 'metadata': .05, 'render': .20, 'upload': .05}

    def __init__(self, store, job, *, notify_interval=30, clock=time.monotonic):
        self.store, self.job, self.clock = store, job, clock
        self.started = clock()
        self.notify_interval = notify_interval
        self.last_write = self.last_notice = -float('inf')
        self.last_stage = None
        self.history = store.historical_duration(job['profile'])
        self.upload_start = None
        self.upload_offset = 0
        self.maximum = 0.0

    def __call__(self, event):
        now = self.clock()
        changed = event.stage != self.last_stage
        fraction = max(0, min(event.current / event.total, 1)) if event.total > 0 else 0
        if event.stage == 'upload' and event.unit == 'byte' and self.upload_start is None:
            self.upload_start, self.upload_offset = now, event.current
        if not changed and now - self.last_write < 1 and fraction < 1:
            return
        self.last_write = now
        self.last_stage = event.stage
        before = 0
        for stage, weight in self.WEIGHTS.items():
            if stage == event.stage:
                break
            before += weight
        overall = before + self.WEIGHTS.get(event.stage, 0) * fraction
        self.maximum = min(.995, max(self.maximum, overall))
        elapsed = max(0, now - self.started)
        remaining = None
        if elapsed >= 5 and self.maximum >= .03:
            remaining = elapsed * (1 - self.maximum) / self.maximum
            if self.history:
                remaining = .7 * remaining + .3 * max(0, self.history - elapsed)
        upload_eta = None
        if self.upload_start is not None and event.unit == 'byte' and event.current > self.upload_offset:
            duration = now - self.upload_start
            if duration > 0:
                upload_eta = max(0, (event.total - event.current) * duration / (event.current - self.upload_offset))
                remaining = upload_eta
        notify = changed or now - self.last_notice >= self.notify_interval
        if notify:
            self.last_notice = now
        self.store.progress(self.job['id'], {'stage': event.stage, 'current': event.current, 'total': event.total,
            'unit': event.unit, 'fraction': fraction, 'overall': self.maximum, 'elapsed': elapsed,
            'eta_at': time.time() + remaining if remaining is not None else None,
            'upload_eta': upload_eta}, notify=notify)
