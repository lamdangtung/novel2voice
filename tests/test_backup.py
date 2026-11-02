"""Full library copy, integrity rejection and maintenance isolation."""
import json
from pathlib import Path
import test_chapters as fixtures
from api.backup import backup,restore
from api.maintenance import gate
from api.books import BookError

class BackupTests(fixtures.ChapterTests):
    test_natural_order_pages_filters_and_range=None
    test_detail_and_download_exact_bytes_and_isolation=None
    def test_copy_restore_and_tampered_backup(self):
        backup_root=self.root.parent/('backup-'+self.book);restored=self.root.parent/('restored-'+self.book)
        import shutil
        self.addCleanup(lambda:shutil.rmtree(backup_root,ignore_errors=True));self.addCleanup(lambda:shutil.rmtree(restored,ignore_errors=True))
        (self.root/'.env').write_text('SECRET=sentinel')
        with gate(self.root):
            with self.assertRaises(BookError):backup(self.root,backup_root)
        with gate(self.root,exclusive=True):
            self.assertEqual(self.c.get('/api/v1/books').status_code,503)
        self.assertEqual(backup(self.root,backup_root)['status'],'verified');self.assertFalse((backup_root/'.env').exists())
        self.assertEqual(restore(backup_root,restored)['status'],'verified')
        from api.books import BookRepository
        from api.chapters import listing
        repo=BookRepository(restored)
        try:self.assertEqual(listing(repo,self.book).total,45)
        finally:repo.engine.dispose()
        with self.assertRaises(ValueError):restore(backup_root,restored)
        (backup_root/'library.sqlite3').write_bytes(b'tampered')
        with self.assertRaises(ValueError):restore(backup_root,restored.with_name(restored.name+'bad'))
