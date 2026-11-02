"""Remove a chapter from the library atomically, preserving files and job history."""
import json
from uuid import uuid4
from sqlalchemy import text,delete,update
from sqlmodel import select
from api.books import BookError,safe_directory
from api.configuration import check_path
from api.storage import session_scope
from api.storage.models import Chapter,Artifact,Job,now
from api.verification.workspace import atomic_json


def remove(repo,book_id,chapter_id,revision):
    archive=None
    try:
        with session_scope(repo.engine) as db:
            db.exec(text('BEGIN IMMEDIATE'))
            chapter=db.get(Chapter,str(chapter_id))
            if not chapter or chapter.book_id!=str(book_id):raise BookError('Không tìm thấy chương.',404)
            if chapter.revision!=revision:raise BookError('Chương đã thay đổi. Hủy thao tác, tải lại danh sách rồi kiểm tra trước khi xóa.')
            jobs=db.exec(select(Job).where(Job.book_id==str(book_id),Job.status.in_(['pending','queued','running','stop_requested']))).all()
            for job in jobs:
                if job.kind=='voice_sample':continue
                try:
                    targets=json.loads(job.config_json).get('plan',{}).get('chapters',[])
                    used=not targets or any(item['id']==chapter.id for item in targets)
                except (ValueError,TypeError,KeyError):used=True
                if job.chapter_id==chapter.id or used:
                    raise BookError(f'Chương đang được công việc {job.id} sử dụng. Dừng công việc và đợi dừng xong trước khi xóa.')
            artifacts=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id)).all()
            archive=safe_directory(repo.root/'deleted-chapters')/(str(uuid4())+'.json');check_path(archive)
            atomic_json(archive,{'format':'deleted-chapter-v1','deleted_at':now(),'chapter':chapter.model_dump(),
                                 'artifacts':[a.model_dump() for a in artifacts],
                                 'notice':'Chương đã rời thư viện; file và lịch sử được giữ, không tự khôi phục qua giao diện.'})
            # Historic immutable snapshots retain their original chapter IDs. Only
            # the optional relational pointer is detached so history and merges survive.
            db.exec(update(Job).where(Job.chapter_id==chapter.id).values(chapter_id=None))
            db.exec(delete(Artifact).where(Artifact.chapter_id==chapter.id))
            db.delete(chapter)
            result={'id':chapter.id,'number':chapter.number,'status':'deleted','artifact_count':len(artifacts),'files_removed':False,
                    'notice':'Đã xóa chương khỏi truyện. File, lịch sử công việc và bản ghép đã lưu được giữ trên máy.'}
        return result
    except BaseException:
        if archive is not None:archive.unlink(missing_ok=True)
        raise
