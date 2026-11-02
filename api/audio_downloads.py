"""Reviewed, bounded audio exports. ZIP creation and delivery never load the ZIP in RAM."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import unicodedata
from uuid import UUID,uuid4
import zipfile
from fastapi import Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlmodel import select
from api.books import BookError,safe_directory
from api.configuration import check_path
from api.storage import session_scope
from api.storage.models import Chapter,Artifact
from api.audio_imports import media
from api.overview import audio_status,expected_tts
from api.verification.workspace import atomic_json

MAX_CHAPTERS=500
MAX_BYTES=2*1024**3
TTL=30*60
MAX_EXPORTS=20


class DownloadRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode:str=Field(pattern='^(selected|range)$')
    chapter_ids:list[UUID]=Field(default_factory=list,max_length=MAX_CHAPTERS)
    start:int|None=Field(default=None,ge=0,le=99999999)
    end:int|None=Field(default=None,ge=0,le=99999999)

    @model_validator(mode='after')
    def scope(self):
        if self.mode=='selected':
            if not self.chapter_ids or self.start is not None or self.end is not None:raise ValueError('Chọn chương hoặc nhập khoảng, không dùng cả hai.')
            if len(set(self.chapter_ids))!=len(self.chapter_ids):raise ValueError('Danh sách chương bị trùng.')
        elif self.chapter_ids or self.start is None or self.end is None or self.start>self.end or self.end-self.start+1>MAX_CHAPTERS:
            raise ValueError('Khoảng chương không hợp lệ hoặc vượt500chương.')
        return self


def safe_name(value):
    value=unicodedata.normalize('NFKC',value)
    return re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '-',value)[:80].strip(' .') or 'audio'


def folder_for(repo,identifier):
    directory=repo.root/'audio-downloads'/str(identifier)
    check_path(directory)
    if not directory.is_dir():raise BookError('Phiên tải không còn. Kiểm tra audio lại.',404)
    return directory


def read_plan(directory,book_id):
    path=directory/'plan.json';check_path(path)
    if not path.is_file() or path.stat().st_size>1024*1024:raise BookError('Phiên tải không hợp lệ. Kiểm tra audio lại.')
    plan=json.loads(path.read_text())
    if plan.get('format')!='audio-export-v1' or plan.get('book_id')!=str(book_id):raise BookError('Không tìm thấy phiên tải.',404)
    if time.time()>plan['expires_at']:raise BookError('Phiên tải đã hết hạn30phút. Kiểm tra audio lại.')
    return plan


@contextmanager
def locked(directory,shared=False):
    path=directory/'export.lock';check_path(path)
    stream=path.open('a')
    try:
        try:fcntl.flock(stream,(fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
        except BlockingIOError:raise BookError('ZIP đang được chuẩn bị hoặc tải. Chờ hoàn tất rồi thử lại.')
        yield stream
    finally:stream.close()


def cleanup(root):
    """Only remove expired marked exports, never exports being prepared or streamed."""
    root=safe_directory(root)
    for directory in root.iterdir():
        try:
            UUID(directory.name)
            check_path(directory)
            if not directory.is_dir():continue
            with locked(directory):
                path=directory/'plan.json';check_path(path)
                if not path.is_file() or path.stat().st_size>1024*1024:continue
                plan=json.loads(path.read_text())
                if plan.get('format')=='audio-export-v1' and time.time()>plan['expires_at']:shutil.rmtree(directory)
        except (ValueError,KeyError,TypeError,OSError,BookError):continue


def inspect_chapter(repo,db,chapter,expected):
    artifacts=db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id)).all()
    audios=[a for a in artifacts if a.kind=='audio']
    selected=[]
    for audio in audios:
        try:
            if json.loads(audio.provenance).get('selected'):selected.append(audio)
        except (ValueError,AttributeError,TypeError):raise BookError('Thông tin audio không hợp lệ.')
    if not selected:raise BookError('Chưa có audio đang chọn.')
    if len(selected)!=1:raise BookError('Có nhiều audio đang chọn; chọn lại một bản trong chi tiết chương.')
    audio,_,path=media(repo,db,chapter.book_id,selected[0].id)
    state=audio_status(repo,chapter,audios,expected,[a for a in artifacts if a.kind=='translation_txt'])
    if state!='audio_ready':raise BookError('Audio cũ hoặc khác nguồn/cấu hình; kiểm tra lại trong chi tiết chương.')
    return audio,path


def preview(repo,book_id,body):
    book=repo.get(book_id);root=safe_directory(repo.root/'audio-downloads');cleanup(root)
    if sum(p.is_dir() for p in root.iterdir())>=MAX_EXPORTS:raise BookError('Có nhiều phiên tải tạm. Thử lại khi phiên cũ hết hạn30phút.')
    with session_scope(repo.engine) as db:
        query=select(Chapter).where(Chapter.book_id==str(book_id))
        if body.mode=='selected':query=query.where(Chapter.id.in_([str(x) for x in body.chapter_ids]))
        else:query=query.where(Chapter.number>=body.start,Chapter.number<=body.end)
        chapters=db.exec(query.order_by(Chapter.number).limit(MAX_CHAPTERS+1)).all()
        if body.mode=='selected' and len(chapters)!=len(body.chapter_ids):raise BookError('Lựa chọn có chương đã xóa hoặc không thuộc truyện. Tải lại danh sách.')
        expected=expected_tts(repo,str(book_id));by_number={c.number:c for c in chapters}
        numbers=range(body.start,body.end+1) if body.mode=='range' else sorted(by_number)
        items=[];size=0;width=max(4,len(str(max(numbers,default=0))))
        for number in numbers:
            chapter=by_number.get(number)
            item={'number':number,'chapter_id':chapter.id if chapter else None,'title':chapter.title if chapter else '', 'status':'skipped'}
            if chapter is None:item['reason']='Không có chương này trong truyện.'
            else:
                try:
                    audio,path=inspect_chapter(repo,db,chapter,expected)
                    item.update(status='ready',reason='Audio hiện hành, file hợp lệ.',artifact_id=audio.id,sha256=audio.sha256,
                                revision=chapter.revision,source_hash=chapter.source_hash,bytes=path.stat().st_size,
                                filename=f'{number:0{width}d} - {safe_name(chapter.title)}.mp3')
                    size+=item['bytes']
                    if size>MAX_BYTES:raise BookError('Tổng audio vượt2GiB. Chọn phạm vi nhỏ hơn.',413)
                except BookError as exc:
                    if exc.status==413:raise
                    item['reason']=str(exc)
                except OSError:item['reason']='Không đọc được file audio; kiểm tra lại trong chi tiết chương.'
            items.append(item)
    identifier=str(uuid4());directory=safe_directory(root/identifier)
    plan={'format':'audio-export-v1','id':identifier,'book_id':str(book_id),'created_at':time.time(),'expires_at':time.time()+TTL,
          'filename':f'audio-{safe_name(book.name)}.zip','mode':body.mode,'items':items,'bytes':size}
    try:atomic_json(directory/'plan.json',plan)
    except BaseException:shutil.rmtree(directory);raise
    return public(plan)


def public(plan):
    return {'id':plan['id'],'items':[{k:v for k,v in i.items() if k in {'number','chapter_id','title','status','reason','bytes','filename'}} for i in plan['items']],
            'ready_count':sum(i['status']=='ready' for i in plan['items']),'skipped_count':sum(i['status']!='ready' for i in plan['items']),
            'bytes':plan['bytes'],'expires_at':plan['expires_at'],'filename':plan['filename'],
            'notice':'ZIP chỉ gồm audio hiện hành đang chọn, theo số chương. Chương thiếu/cũ/lỗi được liệt kê và bỏ qua. Không chạy TTS hoặc ghép MP3.'}


def validate_snapshot(repo,plan):
    expected=expected_tts(repo,plan['book_id'])
    with session_scope(repo.engine) as db:
        for item in plan['items']:
            if item['status']!='ready':continue
            chapter=db.get(Chapter,item['chapter_id'])
            if not chapter or chapter.book_id!=plan['book_id'] or chapter.revision!=item['revision'] or chapter.source_hash!=item['source_hash']:
                raise BookError('Chương đã thay đổi sau kiểm tra. Kiểm tra audio lại trước khi tải.')
            try:audio,path=inspect_chapter(repo,db,chapter,expected)
            except BookError as exc:raise BookError(f'Audio chương {item["number"]} không còn hợp lệ. Kiểm tra audio lại.') from exc
            if audio.id!=item['artifact_id'] or audio.sha256!=item['sha256'] or path.stat().st_size!=item['bytes']:
                raise BookError('Bản audio đang chọn đã thay đổi. Kiểm tra audio lại trước khi tải.')


def prepare(repo,book_id,identifier):
    repo.get(book_id);directory=folder_for(repo,identifier)
    with locked(directory):
        plan=read_plan(directory,book_id);ready=[i for i in plan['items'] if i['status']=='ready']
        if not ready:raise BookError('Không có audio hợp lệ để tải. Chọn phạm vi khác.')
        validate_snapshot(repo,plan)
        output=directory/'audio.zip';check_path(output)
        if not output.is_file():
            if shutil.disk_usage(directory).free<plan['bytes']+64*1024**2:raise BookError('Không đủ dung lượng tạm để tạo ZIP. Chọn phạm vi nhỏ hơn.')
            partial=directory/'audio.partial.zip';check_path(partial)
            try:
                with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                    for item in ready:
                        try:
                            with session_scope(repo.engine) as db:_,_,path=media(repo,db,book_id,item['artifact_id'])
                        except BookError as exc:raise BookError('Audio đã thay đổi trong lúc tạo ZIP. Kiểm tra audio lại.') from exc
                        h=hashlib.sha256();copied=0
                        with path.open('rb') as source,archive.open(item['filename'],'w',force_zip64=True) as dest:
                            for chunk in iter(lambda:source.read(1024*1024),b''):
                                copied+=len(chunk)
                                if copied>item['bytes']:raise BookError('Audio đã thay đổi trong lúc tạo ZIP. Kiểm tra lại.')
                                h.update(chunk);dest.write(chunk)
                        if copied!=item['bytes'] or h.hexdigest()!=item['sha256']:raise BookError('Audio đã thay đổi trong lúc tạo ZIP. Kiểm tra lại.')
                validate_snapshot(repo,plan)
                partial.replace(output)
            except OSError as exc:raise BookError('Không đọc được audio hoặc không ghi được ZIP. Kiểm tra dung lượng và thử lại.') from exc
            finally:partial.unlink(missing_ok=True)
        return {'id':plan['id'],'filename':plan['filename'],'ready_count':len(ready),'download_path':f"/api/v1/books/{book_id}/audio-downloads/{identifier}/file"}


class ExportResponse(FileResponse):
    def __init__(self,*args,lease,**kwargs):
        super().__init__(*args,**kwargs);self.lease=lease
    async def __call__(self,scope,receive,send):
        try:await super().__call__(scope,receive,send)
        finally:self.lease.close()


def download(repo,book_id,identifier):
    repo.get(book_id);directory=folder_for(repo,identifier)
    # Hold a shared lock until FileResponse finishes, protecting in-flight streams
    # from the expiration cleanup in another browser tab.
    lock_path=directory/'export.lock';check_path(lock_path);stream=lock_path.open('a')
    try:
        try:fcntl.flock(stream,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:raise BookError('ZIP đang được chuẩn bị. Chờ rồi tải lại.')
        plan=read_plan(directory,book_id);output=directory/'audio.zip';check_path(output)
        if not output.is_file():raise BookError('ZIP chưa sẵn sàng. Bấm tải từ màn hình kiểm tra audio.')
        return ExportResponse(output,media_type='application/zip',filename=plan['filename'],lease=stream)
    except BaseException:stream.close();raise


def attach_routes(router,call):
    @router.post('/{book_id}/audio-downloads/preview',status_code=201)
    def preview_audio(book_id:UUID,body:DownloadRequest,request:Request):return call(request,lambda r:preview(r,book_id,body))
    @router.post('/{book_id}/audio-downloads/{identifier}/prepare')
    def prepare_audio(book_id:UUID,identifier:UUID,request:Request):return call(request,lambda r:prepare(r,book_id,identifier))
    @router.get('/{book_id}/audio-downloads/{identifier}/file')
    def download_audio(book_id:UUID,identifier:UUID,request:Request):return call(request,lambda r:download(r,book_id,identifier))
