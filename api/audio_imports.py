"""T13/T14 bounded MP3 import, explicit mapping and Range-capable owned media."""
import base64
import binascii
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from uuid import UUID, uuid4
from fastapi import Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import select
from sqlalchemy import text
from api.books import BookError, safe_directory
from api.storage import session_scope
from api.storage.models import Chapter, Artifact, ImportSession

MAX_AUDIO = 5 * 1024 * 1024


class AudioUpload(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=200)
    content_base64: str=Field(max_length=7_000_000)


class AudioPreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    files: list[AudioUpload]=Field(min_length=1,max_length=3)


class Mapping(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id: UUID
    chapter_id: UUID


class AudioConfirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items: list[Mapping]=Field(min_length=1,max_length=3)


class AudioSelection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    artifact_id: UUID


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def inspect_mp3(path):
    try:
        result=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=codec_name:format=format_name,duration','-of','json',str(path)],capture_output=True,text=True,timeout=3)
        data=json.loads(result.stdout);duration=float(data['format']['duration'])
        valid=(result.returncode==0 and data['streams'][0]['codec_name']=='mp3' and 'mp3' in data['format']['format_name'].split(',') and math.isfinite(duration) and duration>0)
        return duration if valid else None
    except (OSError,subprocess.TimeoutExpired,ValueError,KeyError,IndexError):return None


def preview(repo,book_id,body):
    repo.get(book_id)
    identifier=str(uuid4());folder=safe_directory(repo.root/'audio-imports'/identifier);items=[];total=0
    try:
        with session_scope(repo.engine) as db:
            chapters=db.exec(select(Chapter).where(Chapter.book_id==str(book_id)).order_by(Chapter.number).limit(5001)).all()
            if len(chapters)>5000:raise BookError('Truyện quá nhiều chương cho phiên import này.',413)
            for file in body.files:
                if '/' in file.name or '\\' in file.name or any(ord(c)<32 for c in file.name) or not file.name.lower().endswith('.mp3'):
                    raise BookError('Chỉ nhận tên file MP3, không nhận đường dẫn.',422)
                try:content=base64.b64decode(file.content_base64,validate=True)
                except (ValueError,binascii.Error):raise BookError('Nội dung MP3 upload không hợp lệ.',422)
                total+=len(content)
                if len(content)>MAX_AUDIO or total>MAX_AUDIO:raise BookError('Giới hạn MP3: tối đa3 file, tổng5MiB mỗi phiên.',413)
                item_id=str(uuid4());path=folder/(item_id+'.mp3');path.write_bytes(content)
                duration=inspect_mp3(path);match=re.search(r'(?<!\d)(\d{1,8})(?!\d)',Path(file.name).stem)
                candidates=[c for c in chapters if match and c.number==int(match.group(1))]
                ambiguous=Path(file.name).stem.isdigit() or len(candidates)!=1
                suggestion=candidates[0].id if len(candidates)==1 and not ambiguous else None
                items.append({'id':item_id,'name':file.name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'duration':duration,
                              'valid':duration is not None,'suggested_chapter_id':suggestion,'message':'Audio hỏng/không phải MP3 hợp lệ.' if duration is None else 'Cần chọn chương thủ công; tên file chưa đủ để xác nhận.' if ambiguous else 'Đề xuất ánh xạ; hãy kiểm tra rồi xác nhận.'})
            session=ImportSession(id=identifier,book_id=str(book_id),items_json=json.dumps({'kind':'audio','items':items}),result_json='[]')
            db.add(session)
        return {'id':identifier,'status':'preview','items':items,'chapters':[{'id':c.id,'number':c.number,'title':c.title} for c in chapters]}
    except BaseException:
        shutil.rmtree(folder);raise


def get_session(db,book_id,import_id):
    session=db.get(ImportSession,str(import_id))
    if not session or session.book_id!=str(book_id):raise BookError('Không tìm thấy phiên audio.',404)
    data=json.loads(session.items_json)
    if not isinstance(data,dict) or data.get('kind')!='audio':raise BookError('Không tìm thấy phiên audio.',404)
    return session,data['items']


def confirm(repo,book_id,import_id,body):
    written=[];selection=sorted([(str(x.item_id),str(x.chapter_id)) for x in body.items])
    try:
        with session_scope(repo.engine) as db:
            db.exec(text('BEGIN IMMEDIATE'));session,rows=get_session(db,book_id,import_id)
            if session.status=='confirmed':
                saved=json.loads(session.result_json)
                if any(db.get(Chapter,item['chapter_id']) is None for item in saved.get('outcomes',[])):raise BookError('Chương trong phiên audio đã bị xóa. Tạo phiên nhập mới.')
                if saved['selection']!=[list(x) for x in selection]:raise BookError('Phiên đã xác nhận với mapping khác.')
                return saved
            if session.status!='preview':raise BookError('Phiên đã hủy; xem trước lại.')
            if len({x.chapter_id for x in body.items})!=len(body.items) or len({x.item_id for x in body.items})!=len(body.items):
                raise BookError('Chọn tối đa một MP3 cho mỗi chương trong phiên này.')
            outcomes=[];items={r['id']:r for r in rows}
            for mapping in body.items:
                item=items.get(str(mapping.item_id));chapter=db.get(Chapter,str(mapping.chapter_id))
                if not item or not item['valid']:raise BookError('Audio lỗi không được nhập.')
                if not chapter or chapter.book_id!=str(book_id):raise BookError('Chương ánh xạ không thuộc bộ truyện.',404)
                source=repo.root/'audio-imports'/str(import_id)/(item['id']+'.mp3')
                safe_directory(source.parent)
                if source.is_symlink() or not source.is_file() or source.stat().st_nlink>1 or source.stat().st_size>MAX_AUDIO or digest(source)!=item['sha256']:
                    raise BookError('Audio đã thay đổi sau xem trước. Xem trước lại.')
                artifacts=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='audio')).all()
                chosen=None
                for artifact in artifacts:
                    provenance=json.loads(artifact.provenance)
                    if artifact.sha256==item['sha256']:chosen=artifact
                    provenance['selected']=False;artifact.provenance=json.dumps(provenance);db.add(artifact)
                if chosen is None:
                    folder=safe_directory(repo.root/'books'/str(book_id)/'chapters'/chapter.id/'audio')
                    output=folder/(str(uuid4())+'.mp3');shutil.copyfile(source,output);written.append(output)
                    chosen=Artifact(chapter_id=chapter.id,kind='audio',relative_path=output.relative_to(repo.root).as_posix(),sha256=item['sha256'],
                                    provenance=json.dumps({'method':'imported','filename':item['name'],'duration':item['duration'],'source_hash':chapter.source_hash,'selected':True}),verified=True)
                else:
                    provenance=json.loads(chosen.provenance);provenance['selected']=True;chosen.provenance=json.dumps(provenance)
                db.add(chosen);db.flush()
                outcomes.append({'chapter_id':chapter.id,'artifact_id':chosen.id,'label':'Audio nhập trước; chưa xác minh nội dung khớp từng từ.'})
            saved={'status':'confirmed','selection':selection,'outcomes':outcomes};session.status='confirmed';session.result_json=json.dumps(saved);db.add(session)
        return saved
    except BaseException:
        for path in written:path.unlink(missing_ok=True)
        raise


def media(repo,db,book_id,artifact_id):
    artifact=db.get(Artifact,str(artifact_id));chapter=db.get(Chapter,artifact.chapter_id) if artifact else None
    if not artifact or artifact.kind!='audio' or not chapter or chapter.book_id!=str(book_id):raise BookError('Không tìm thấy audio.',404)
    relative=Path(artifact.relative_path)
    if relative.is_absolute() or '..' in relative.parts:raise BookError('Đường dẫn audio không hợp lệ.')
    path=repo.root/relative
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_nlink>1:raise BookError('File audio mất hoặc đường dẫn không an toàn.',404)
    if path.stat().st_size>512*1024*1024 or digest(path)!=artifact.sha256:raise BookError('Checksum audio không khớp.')
    return artifact,chapter,path


def listing(repo,book_id,chapter_id):
    with session_scope(repo.engine) as db:
        chapter=db.get(Chapter,str(chapter_id))
        if not chapter or chapter.book_id!=str(book_id):raise BookError('Không tìm thấy chương.',404)
        rows=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='audio').order_by(Artifact.created_at)).all()
        items=[]
        for a in rows:
            provenance=json.loads(a.provenance)
            items.append({'id':a.id,'sha256':a.sha256,'selected':provenance.get('selected',False),'duration':provenance.get('duration'),
                          'translation_sha256':provenance.get('translation_sha256'),'verification':provenance.get('verification',False),'stale':not a.verified or provenance.get('source_hash')!=chapter.source_hash,'method':provenance.get('method','unknown')})
        return {'items':items,'notice':'Audio nhập trước chỉ xác minh file hợp lệ; chưa đảm bảo đọc khớp nội dung.'}


def choose(repo,book_id,chapter_id,body):
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));artifact,chapter,_=media(repo,db,book_id,body.artifact_id)
        if chapter.id!=str(chapter_id):raise BookError('Audio không thuộc chương.',404)
        for row in db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind=='audio')).all():
            data=json.loads(row.provenance);data['selected']=row.id==artifact.id;row.provenance=json.dumps(data);db.add(row)
    return listing(repo,book_id,chapter_id)


def attach_routes(router,call):
    @router.post('/{book_id}/audio-imports',status_code=201)
    def audio_preview(book_id:UUID,body:AudioPreview,request:Request):return call(request,lambda r:preview(r,book_id,body))
    @router.post('/{book_id}/audio-imports/{import_id}/confirm')
    def audio_confirm(book_id:UUID,import_id:UUID,body:AudioConfirm,request:Request):return call(request,lambda r:confirm(r,book_id,import_id,body))
    @router.post('/{book_id}/audio-imports/{import_id}/cancel')
    def audio_cancel(book_id:UUID,import_id:UUID,request:Request):
        def action(repo):
            with session_scope(repo.engine) as db:
                db.exec(text('BEGIN IMMEDIATE'));session,_=get_session(db,book_id,import_id)
                if session.status=='confirmed':raise BookError('Phiên đã xác nhận không thể hủy.')
                session.status='cancelled';db.add(session)
            path=repo.root/'audio-imports'/str(import_id)
            safe_directory(path)
            shutil.rmtree(path)
            return {'status':'cancelled'}
        return call(request,action)
    @router.get('/{book_id}/chapters/{chapter_id}/audio')
    def chapter_audio(book_id:UUID,chapter_id:UUID,request:Request):return call(request,lambda r:listing(r,book_id,chapter_id))
    @router.post('/{book_id}/chapters/{chapter_id}/audio-selection')
    def select_audio(book_id:UUID,chapter_id:UUID,body:AudioSelection,request:Request):return call(request,lambda r:choose(r,book_id,chapter_id,body))
    @router.get('/{book_id}/audio/{artifact_id}')
    def stream_audio(book_id:UUID,artifact_id:UUID,request:Request,download:bool=False):
        def action(repo):
            with session_scope(repo.engine) as db:
                _,chapter,path=media(repo,db,book_id,artifact_id)
                return FileResponse(path,media_type='audio/mpeg',filename=f'chapter-{chapter.number}.mp3' if download else None)
        return call(request,action)
