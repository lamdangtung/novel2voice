import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from typer.testing import CliRunner

from src.main import app
from src.pipeline import NovelPipeline
from src.source_fetcher import fetch_chapters
from src.sources.base import Chapter
from src.sources.ixdzs8 import Ixdzs8Source
from src.glossary_manager import occurrences

URL = 'https://ixdzs8.com/read/644938/p1.html'
HTML = '''<h1 class="page-d-name">第1章 测试</h1>
<article class="page-content"><h3>Duplicate title</h3><section>
<p>陈啸打开书。<span>然后微笑。</span></p><p>Second &amp; third.</p>
<script>noise()</script><div class="ad"><p>Advertisement</p></div></section></article>
<nav><p>Menu</p><a class="chapter-next" href="/read/644938/p2.html">Next</a></nav>'''


class SourceTests(unittest.TestCase):
    def test_parse_selects_story_and_next_link(self):
        source = Ixdzs8Source(client=Mock())
        chapter = source.parse_chapter(HTML, URL)
        self.assertEqual(chapter.title, '第1章 测试')
        self.assertEqual(chapter.language, 'zh')
        self.assertIn('Second & third.', chapter.text)
        for noise in ('Advertisement', 'Duplicate title', 'Menu', 'noise'):
            self.assertNotIn(noise, chapter.text)
        self.assertEqual(chapter.next_url, URL.replace('p1', 'p2'))

    def test_invalid_page_and_empty_story_fail(self):
        source = Ixdzs8Source(client=Mock())
        for html in ('<h1>Verify human</h1>', HTML.replace('<p>陈啸打开书。<span>然后微笑。</span></p><p>Second &amp; third.</p>', '')):
            with self.assertRaises(ValueError):
                source.parse_chapter(html, URL)

    def test_url_validation_and_navigation(self):
        source = Ixdzs8Source(client=Mock())
        for url in ('https://evil.test/read/644938/p1.html', 'http://ixdzs8.com/read/644938/p1.html',
                    'https://ixdzs8.com/read/644938/', URL + '?a=1'):
            self.assertFalse(source.supports(url))
        for next_path in ('/read/999/p2.html', '/read/644938/p1.html'):
            with self.assertRaises(ValueError):
                source.parse_chapter(HTML.replace('/read/644938/p2.html', next_path), URL)
        chapter = source.parse_chapter(HTML.replace('/read/644938/p2.html', '/read/644938/'), URL)
        self.assertIsNone(chapter.next_url)

    def test_real_http_adapter_and_http_errors(self):
        def handle(request):
            return httpx.Response(200, text=HTML)
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            source = Ixdzs8Source(client=client, request_interval=0)
            self.assertEqual(source.fetch_chapter(URL).chapter_id, '1')
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                Ixdzs8Source(client=client).fetch_chapter(URL)

    def test_unsafe_redirect_is_rejected(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda r: httpx.Response(302, headers={'location': 'https://evil.test/'}))) as client:
            with self.assertRaises(ValueError):
                Ixdzs8Source(client=client).fetch_chapter(URL)

    def test_fetch_bounded_sequence_and_metadata(self):
        source = Mock()
        source.fetch_chapter.side_effect = [
            Chapter('ixdzs8', '644938', '1', 'First', 'Text one', URL, 'zh', URL.replace('p1', 'p2')),
            Chapter('ixdzs8', '644938', '2', 'Second', 'Text two', URL.replace('p1', 'p2'), 'zh')]
        with tempfile.TemporaryDirectory() as directory:
            paths = fetch_chapters(URL, Path(directory), max_chapters=2, source=source)
            self.assertEqual(len(paths), 2)
            self.assertEqual(paths[0].read_text(), 'First\n\nText one\n')
            metadata = json.loads(paths[0].with_suffix('.json').read_text())
            self.assertEqual(metadata['url'], URL)
            self.assertIn('fetched_at', metadata)
            self.assertNotIn('text', metadata)
        source.close.assert_not_called()

    def test_failure_preserves_previous_chapter(self):
        source = Mock()
        source.fetch_chapter.side_effect = [
            Chapter('ixdzs8', '1', '1', 'First', 'Text', URL, 'zh', URL.replace('p1', 'p2')),
            RuntimeError('offline')]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                fetch_chapters(URL, Path(directory), max_chapters=2, source=source)
            self.assertEqual(len(list(Path(directory).rglob('*.txt'))), 1)

    def test_fetch_cli_and_url_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('src.source_fetcher.get_novel_source') as factory:
                factory.return_value.fetch_chapter.return_value = Chapter(
                    'ixdzs8', '1', '1', 'First', 'Text', URL, 'zh')
                result = CliRunner().invoke(app, ['fetch', URL, '--output-dir', directory])
                self.assertEqual(result.exit_code, 0, result.output)
                factory.return_value.close.assert_called_once()
        pipeline = NovelPipeline()
        with patch.object(pipeline, 'fetch_only', return_value=[Path('chapter.txt')]), \
             patch.object(pipeline, 'process_file', return_value=('vi.txt', 'audio.mp3')) as process:
            self.assertEqual(pipeline.process_url(URL), [('vi.txt', 'audio.mp3')])
            process.assert_called_once()
        with self.assertRaises(ValueError):
            pipeline.process_url(URL, max_chapters=2, output_audio=Path('audio.mp3'))

    def test_cjk_glossary_frequency(self):
        self.assertEqual(occurrences('陈啸', '陈啸拿起书，陈啸笑了。'), 2)
        self.assertEqual(occurrences('John', 'Johnny John'), 1)
