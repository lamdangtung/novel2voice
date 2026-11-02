"""T27 live overview. Only selected, current and hash-valid audio counts as current."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from uuid import UUID
from fastapi import APIRouter,Request,HTTPException,Query
from sqlalchemy import func
from sqlmodel import select
from api.books import BookError
from api.storage import session_scope
from api.storage.models import Book,Chapter,Artifact,BookArtifact,Job
from api.jobs import job_view
from api.verification.workspace import PROJECT_ROOT


@lru_cache(maxsize=4096)
def _verified(path,expected,size,mtime,inode):
    h=hashlib.sha256();p=Path(path)
    try:
        with p.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
        stat=p.stat()
        return h.hexdigest()==expected and (stat.st_size,stat.st_mtime_ns,stat.st_ino)==(size,mtime,inode)
    except OSError:return False


def valid_file(root,relative,expected):
    relative=Path(relative)
    if relative.is_absolute() or '..' in relative.parts:return False
    path=root/relative
    try:
        if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():return False
        stat=path.stat()
        if stat.st_nlink>1 or stat.st_size>512*1024*1024:return False
        return _verified(str(path),expected,stat.st_size,stat.st_mtime_ns,stat.st_ino)
    except OSError:return False


def expected_tts(repo,book_id):
    try:
        from api.configuration import read
        from src.web_contract import tts_fingerprint
        return tts_fingerprint(read(repo,book_id)['effective'],getattr(repo,'verification_enabled',repo.root.is_relative_to(PROJECT_ROOT/'.verification')))
    except Exception:return None


def audio_status(repo,chapter,audios,expected=None,translations=None):
    selected=[]
    for audio in audios:
        try:data=json.loads(audio.provenance)
        except ValueError:return 'needs_refresh'
        if data.get('selected'):selected.append((audio,data))
    if not selected:return 'source_ready'
    if len(selected)!=1:return 'needs_refresh'
    audio,data=selected[0]
    if not audio.verified or data.get('source_hash')!=chapter.source_hash:return 'needs_refresh'
    if data.get('method')=='generated' and data.get('tts_fingerprint')!=expected:return 'needs_refresh'
    if data.get('translation_sha256') and not any(t.verified and t.sha256==data['translation_sha256'] and valid_file(repo.root,t.relative_path,t.sha256) for t in (translations or [])):return 'needs_refresh'
    return 'audio_ready' if valid_file(repo.root,audio.relative_path,audio.sha256) else 'needs_refresh'


def read(repo,book_id=None,resource='',offset=0,limit=20):
    if book_id:repo.get(book_id)
    with session_scope(repo.engine) as db:
        books=db.exec(select(Book).where(Book.id==str(book_id)) if book_id else select(Book)).all();book_map={b.id:b for b in books}
        ids=list(book_map)
        chapters=db.exec(select(Chapter).where(Chapter.book_id.in_(ids)).order_by(Chapter.book_id,Chapter.number)).all() if ids else []
        chapter_ids=[c.id for c in chapters]
        artifacts=db.exec(select(Artifact).where(Artifact.chapter_id.in_(chapter_ids))).all() if chapter_ids else []
        grouped={c.id:[] for c in chapters}
        for artifact in artifacts:grouped[artifact.chapter_id].append(artifact)
        fingerprints={identifier:expected_tts(repo,identifier) for identifier in ids}
        rows=[];current=[];attention=[]
        for chapter in chapters:
            all_artifacts=grouped[chapter.id]
            state=audio_status(repo,chapter,[a for a in all_artifacts if a.kind=='audio'],fingerprints[chapter.book_id],[a for a in all_artifacts if a.kind=='translation_txt'])
            row={'id':chapter.id,'book_id':chapter.book_id,'book_name':book_map[chapter.book_id].name,'number':chapter.number,'title':chapter.title,'status':state}
            rows.append(row)
            if state=='audio_ready':current.append(row)
            elif state=='needs_refresh':attention.append(row)
        merge_records=db.exec(select(BookArtifact).where(BookArtifact.book_id.in_(ids),BookArtifact.kind=='merged_audio').order_by(BookArtifact.created_at.desc())).all() if ids else []
        merged=[{'id':a.id,'book_id':a.book_id,'book_name':book_map[a.book_id].name,'duration':a.duration,'job_id':a.job_id} for a in merge_records if valid_file(repo.root,a.relative_path,a.sha256)]
        jobs_query=select(Job).where(Job.status!='preview')
        if book_id:jobs_query=jobs_query.where(Job.book_id==str(book_id))
        jobs=db.exec(jobs_query.order_by(Job.created_at.desc(),Job.id)).all()
        needs_attention=[j for j in jobs if j.status in {'failed','stopped','interrupted'}]
        data={'chapters':rows,'audio':current,'attention':attention,'merged':merged}.get(resource,[])
        return {'counts':{'books':len(books),'chapters':len(chapters),'current_audio':len(current),'audio_attention':len(attention),'merged_saved':len(merged),'jobs_attention':len(needs_attention)},
                'recent_jobs':[job_view(j,repo.root) for j in jobs[:5]],'resource':resource,'items':data[offset:offset+limit],'total':len(data),
                'scope':str(book_id) if book_id else 'workspace','notice':'Audio hiện hành: đã chọn, đúng nguồn/cấu hình và file/hash hợp lệ. Job lỗi/đã dừng không đồng nghĩa audio trước đó bị mất.'}


def create_router(settings,provider):
    router=APIRouter(prefix='/api/v1/overview',tags=['Overview'])
    @router.get('')
    def overview(request:Request,book_id:UUID|None=None,resource:str=Query(default='',pattern='^(|chapters|audio|attention|merged)$'),offset:int=Query(default=0,ge=0),limit:int=Query(default=20,ge=1,le=100)):
        try:return read(provider(request),book_id,resource,offset,limit)
        except BookError as exc:raise HTTPException(exc.status,str(exc))
    return router
