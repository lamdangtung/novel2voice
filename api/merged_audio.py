"""T24 book-level merged artifacts: scoped, checksum checked and Range capable."""
import json
from pathlib import Path
from uuid import UUID
from fastapi import Request
from fastapi.responses import FileResponse
from sqlmodel import select
from api.books import BookError
from api.storage import session_scope
from api.storage.models import BookArtifact
from api.audio_imports import digest


def media(repo,db,book_id,artifact_id,kind='merged_audio'):
    artifact=db.get(BookArtifact,str(artifact_id))
    if not artifact or artifact.book_id!=str(book_id) or artifact.kind!=kind:raise BookError('Không tìm thấy audio ghép.',404)
    relative=Path(artifact.relative_path)
    if relative.is_absolute() or '..' in relative.parts:raise BookError('Đường dẫn audio ghép không hợp lệ.')
    path=repo.root/relative
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_nlink>1:raise BookError('File audio ghép mất hoặc không an toàn.',404)
    if path.stat().st_size>512*1024*1024 or digest(path)!=artifact.sha256:raise BookError('Checksum audio ghép không khớp.')
    return artifact,path


def attach_routes(router,call):
    @router.get('/{book_id}/merged')
    def listing(book_id:UUID,request:Request):
        def action(repo):
            repo.get(book_id)
            with session_scope(repo.engine) as db:
                return {'items':[{'id':a.id,'sha256':a.sha256,'duration':a.duration,'job_id':a.job_id} for a in db.exec(select(BookArtifact).where(BookArtifact.book_id==str(book_id),BookArtifact.kind=='merged_audio').order_by(BookArtifact.created_at.desc()).limit(20)).all()]}
        return call(request,action)
    @router.get('/{book_id}/merged/{artifact_id}')
    def stream(book_id:UUID,artifact_id:UUID,request:Request,download:bool=False):
        def action(repo):
            with session_scope(repo.engine) as db:
                artifact,path=media(repo,db,book_id,artifact_id)
                return FileResponse(path,media_type='audio/mpeg',filename='book-'+str(book_id)[:8]+'-merged.mp3' if download else None)
        return call(request,action)
