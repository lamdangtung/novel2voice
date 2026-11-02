"""T09/T10 paged chapter queries and owned, hash-checked TXT artifacts."""
import hashlib
import json
from pathlib import Path
from uuid import UUID
from fastapi import Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, or_
from sqlmodel import select, func
from api.books import BookError
from api.storage import session_scope
from api.storage.models import Chapter, Artifact


class DeleteChapterRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)


class ChapterView(BaseModel):
    id: str
    number: int
    title: str
    revision: int
    status: str


class ChapterPage(BaseModel):
    items: list[ChapterView]
    total: int
    offset: int
    limit: int


def statuses(chapter,artifacts):
    audio=[a for a in artifacts if a.kind=='audio']
    return 'audio_ready' if any(a.verified for a in audio) else 'needs_refresh' if audio else 'source_ready'


def listing(repo,book_id,q='',status='all',offset=0,limit=20):
    repo.get(book_id)
    query=select(Chapter).where(Chapter.book_id==str(book_id))
    if q:
        query=query.where(or_(Chapter.title.contains(q,autoescape=True),Chapter.number==int(q)) if q.isdigit() and len(q)<9 else Chapter.title.contains(q,autoescape=True))
    if status not in {'all','audio_ready','needs_refresh','source_ready'}:raise BookError('Bộ lọc trạng thái không hợp lệ.',422)
    from api.overview import audio_status,expected_tts
    expected=expected_tts(repo,book_id)
    with session_scope(repo.engine) as db:
        rows=db.exec(query.order_by(Chapter.number,Chapter.id).limit(5001)).all()
        if len(rows)>5000:raise BookError('Phạm vi có quá5000 chương; thu hẹp tìm kiếm.',413)
        ids=[c.id for c in rows]
        artifacts=db.exec(select(Artifact).where(Artifact.chapter_id.in_(ids))).all() if ids else []
        grouped={c.id:[] for c in rows}
        for a in artifacts:grouped[a.chapter_id].append(a)
        result=[]
        for c in rows:
            state=audio_status(repo,c,[a for a in grouped[c.id] if a.kind=='audio'],expected,[a for a in grouped[c.id] if a.kind=='translation_txt'])
            if status=='all' or state==status:result.append(ChapterView(id=c.id,number=c.number,title=c.title,revision=c.revision,status=state))
        return ChapterPage(items=result[offset:offset+limit],total=len(result),offset=offset,limit=limit)


def owned_artifact(repo,db,book_id,artifact_id):
    artifact=db.get(Artifact,str(artifact_id))
    if artifact is None:raise BookError('Không tìm thấy nội dung.',404)
    chapter=db.get(Chapter,artifact.chapter_id)
    if chapter is None or chapter.book_id!=str(book_id):raise BookError('Không tìm thấy nội dung.',404)
    if artifact.kind not in {'source_txt','translation_txt'}:raise BookError('Nội dung không phải TXT.',404)
    relative=Path(artifact.relative_path)
    if relative.is_absolute() or '..' in relative.parts:raise BookError('Đường dẫn nội dung không hợp lệ.')
    path=repo.root/relative
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_nlink>1:
        raise BookError('File nội dung không còn hoặc đường dẫn không an toàn.')
    if path.stat().st_size>(2*1024*1024 if artifact.kind=='translation_txt' else 256*1024):raise BookError('File TXT vượt giới hạn.')
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=artifact.sha256:raise BookError('Checksum nội dung không khớp. Kiểm tra lại bản nhập.')
    return artifact,chapter,path,content


def detail(repo,book_id,chapter_id,include_translation=True):
    with session_scope(repo.engine) as db:
        chapter=db.get(Chapter,str(chapter_id))
        if chapter is None or chapter.book_id!=str(book_id):raise BookError('Không tìm thấy chương.',404)
        source=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='source_txt',Artifact.sha256==chapter.source_hash).order_by(Artifact.created_at.desc())).first()
        translated=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='translation_txt',Artifact.verified==True).order_by(Artifact.created_at.desc())).first() if include_translation else None
        result={'id':chapter.id,'number':chapter.number,'title':chapter.title,'revision':chapter.revision,'source':None,'translation':None}
        for key,artifact in [('source',source),('translation',translated)]:
            if artifact:
                _,_,_,content=owned_artifact(repo,db,book_id,artifact.id)
                try:text=content.decode('utf-8-sig')
                except UnicodeDecodeError:raise BookError('Nội dung không còn là UTF-8 hợp lệ.')
                result[key]={'artifact_id':artifact.id,'sha256':artifact.sha256,'bytes':len(content),'text':text,'metadata':json.loads(artifact.provenance)}
        return result


def attach_routes(router,call):
    @router.delete('/{book_id}/chapters/{chapter_id}')
    def delete_chapter(book_id:UUID,chapter_id:UUID,body:DeleteChapterRequest,request:Request):
        from api.chapter_deletion import remove
        return call(request,lambda r:remove(r,book_id,chapter_id,body.revision))

    @router.get('/{book_id}/chapters',response_model=ChapterPage)
    def chapters(book_id:UUID,request:Request,q:str=Query(default='',max_length=200),status:str='all',offset:int=Query(default=0,ge=0),limit:int=Query(default=20,ge=1,le=100)):
        return call(request,lambda r:listing(r,book_id,q,status,offset,limit))

    @router.get('/{book_id}/chapter-selection')
    def selection(book_id:UUID,request:Request,start:int=Query(ge=0,le=99999999),end:int=Query(ge=0,le=99999999)):
        def action(repo):
            repo.get(book_id)
            if start>end:raise BookError('Số chương bắt đầu phải nhỏ hơn hoặc bằng kết thúc.',422)
            with session_scope(repo.engine) as db:
                rows=db.exec(select(Chapter).where(Chapter.book_id==str(book_id),Chapter.number>=start,Chapter.number<=end).order_by(Chapter.number).limit(5001)).all()
                if len(rows)>5000:raise BookError('Chọn tối đa 5000 chương mỗi lần.',413)
                return {'items':[{'id':c.id,'number':c.number,'title':c.title} for c in rows],'scope':'Khoảng chương trong bộ truyện hiện tại, không áp dụng bộ lọc tìm kiếm.'}
        return call(request,action)

    @router.get('/{book_id}/chapters/{chapter_id}')
    def chapter_detail(book_id:UUID,chapter_id:UUID,request:Request):
        return call(request,lambda r:detail(r,book_id,chapter_id))

    @router.get('/{book_id}/artifacts/{artifact_id}/download')
    def download(book_id:UUID,artifact_id:UUID,request:Request):
        def action(repo):
            with session_scope(repo.engine) as db:
                artifact,chapter,path,_=owned_artifact(repo,db,book_id,artifact_id)
                if artifact.kind not in {'source_txt','translation_txt'}:raise BookError('Nội dung không phải TXT.',404)
                return FileResponse(path,media_type='text/plain; charset=utf-8',filename=f'chapter-{chapter.number}.txt')
        return call(request,action)
