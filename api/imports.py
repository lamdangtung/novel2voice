"""T06 bounded TXT preview/confirm. Uploaded names never become server paths."""
import base64
import binascii
import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import UUID, uuid4
from typing import Literal
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from api.books import BookError, safe_directory
from api.storage import session_scope
from api.storage.models import Book, Chapter, Artifact, ImportSession

MAX_FILE = 256 * 1024
MAX_TOTAL = 2 * 1024 * 1024


class UploadFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=200)
    content_base64: str = Field(max_length=350000)


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    files: list[UploadFile] = Field(min_length=1,max_length=20)


class TextPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: int = Field(ge=0,le=99999999)
    title: str = Field(default='',max_length=200)
    content: str = Field(min_length=1,max_length=MAX_FILE)


def preview_text(repo,book_id,body):
    if not body.content.strip() or '\x00' in body.content:
        raise BookError('Nhập nội dung chương; không nhận văn bản rỗng hoặc ký tự NUL.',422)
    title=body.title.strip()
    if any(ord(c)<32 for c in title):raise BookError('Tiêu đề không được chứa ký tự điều khiển.',422)
    try:content=body.content.encode('utf-8')
    except UnicodeEncodeError:raise BookError('Văn bản chứa ký tự Unicode không hợp lệ.',422)
    if len(content)>MAX_FILE:raise BookError('Văn bản vượt giới hạn 256 KiB UTF-8 mỗi chương.',413)
    upload=UploadFile(name=f'{body.number}.txt',content_base64=base64.b64encode(content).decode())
    return preview(repo,book_id,PreviewRequest(files=[upload]),direct_entry={'title':title})


class ImportChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_id: UUID
    number: int = Field(ge=0,le=99999999)
    action: Literal["import", "update"] = "import"


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[ImportChoice] = Field(min_length=1,max_length=20)


class PreviewItem(BaseModel):
    id: str
    name: str
    number: int | None
    status: str
    message: str
    sha256: str
    size: int
    excerpt: str


class ImportView(BaseModel):
    id: str
    book_id: str
    status: str
    items: list[PreviewItem]
    chapter_ids: list[str]
    outcomes: list[dict] = []


def view(session):
    result=json.loads(session.result_json)
    return ImportView(id=session.id,book_id=session.book_id,status=session.status,
                      items=json.loads(session.items_json),chapter_ids=result if isinstance(result,list) else result['chapter_ids'],
                      outcomes=[] if isinstance(result,list) else result.get('outcomes',[]))


def ensure_book(db, book_id):
    if db.get(Book,str(book_id)) is None:raise BookError('Không tìm thấy bộ truyện.',404)


def preview(repo, book_id, body, *, direct_entry=None):
    identifier=str(uuid4()); total=0; items=[]; contents={}
    for upload in body.files:
        name=upload.name
        if '/' in name or '\\' in name or any(ord(c)<32 for c in name) or not name.lower().endswith('.txt'):
            raise BookError('Chỉ nhận tên file TXT, không nhận đường dẫn.',422)
        try:content=base64.b64decode(upload.content_base64,validate=True)
        except (ValueError,binascii.Error):raise BookError('Nội dung upload không hợp lệ.',422)
        total+=len(content)
        if len(content)>MAX_FILE or total>MAX_TOTAL:raise BookError('Giới hạn: 256 KiB/file, tổng 2 MiB mỗi phiên.',413)
        item_id=str(uuid4()); match=re.search(r'(?<!\d)(\d{1,8})(?!\d)',Path(name).stem)
        number=int(match.group(1)) if match else None
        status='ready';message='Sẵn sàng xem trước.';text=''
        try:
            text=content.decode('utf-8-sig')
            if not text.strip():status,message='invalid','File rỗng.'
            elif '\x00' in text:status,message='invalid','TXT chứa ký tự NUL.'
            elif number is None:status,message='needs_number','Nhập số chương trước khi xác nhận.'
        except UnicodeDecodeError:status,message='invalid','Không đọc được UTF-8. Chuyển file sang UTF-8 rồi nhập lại.'
        items.append(dict(id=item_id,name=name,number=number,status=status,message=message,
                          sha256=hashlib.sha256(content).hexdigest(),size=len(content),excerpt=text[:300]))
        if direct_entry is not None:items[-1].update(input_method='direct_text',chapter_title=direct_entry['title'])
        contents[item_id]=content
    folder=safe_directory(repo.root/'imports'/identifier)
    try:
        with session_scope(repo.engine) as db:
            ensure_book(db,book_id)
            for item in items:
                if item['status']=='invalid' or item['number'] is None:continue
                existing=db.exec(select(Chapter).where(Chapter.book_id==str(book_id),Chapter.number==item['number'])).first()
                if existing:
                    item['existing_revision']=existing.revision
                    item['existing_id']=existing.id
                    item['status']='identical' if existing.source_hash==item['sha256'] else 'changed'
                    item['message']='Nội dung giống hệt; sẽ bỏ qua.' if item['status']=='identical' else 'Chương đã có nội dung khác; chỉ cập nhật khi bạn xác nhận.'
            for item in items:(folder/(item['id']+'.txt')).write_bytes(contents[item['id']])
            session=ImportSession(id=identifier,book_id=str(book_id),items_json=json.dumps(items,ensure_ascii=False))
            db.add(session)
        return view(session)
    except BaseException:
        shutil.rmtree(folder)
        raise


def get_import(db, book_id, import_id):
    session=db.get(ImportSession,str(import_id))
    if session is None or session.book_id!=str(book_id) or not isinstance(json.loads(session.items_json),list):raise BookError('Không tìm thấy phiên nhập.',404)
    return session


def confirm(repo,book_id,import_id,body,verification=False):
    # SQLite BEGIN IMMEDIATE serialises confirmations before reading session state.
    written=[];new_folders=[]
    selection=sorted([(str(c.item_id),c.number,c.action) for c in body.items])
    try:
        with session_scope(repo.engine) as db:
            from sqlalchemy import text
            db.exec(text('BEGIN IMMEDIATE'))
            session=get_import(db,book_id,import_id)
            if session.status=='confirmed':
                saved=json.loads(session.result_json)
                saved_ids=saved if isinstance(saved,list) else saved.get('chapter_ids',[])
                if any(db.get(Chapter,identifier) is None for identifier in saved_ids):raise BookError('Chương trong phiên đã bị xóa. Tạo phiên nhập mới.')
                if isinstance(saved,dict) and saved.get('selection')!=[list(x) for x in selection]:
                    raise BookError('Phiên đã xác nhận với lựa chọn khác. Tạo phiên xem trước mới.')
                return view(session)
            if session.status!='preview':raise BookError('Phiên nhập đã hủy; xem trước lại.')
            items={item['id']:item for item in json.loads(session.items_json)}
            numbers=[c.number for c in body.items]
            if len(set(numbers))!=len(numbers) or len({str(c.item_id) for c in body.items})!=len(body.items):
                raise BookError('Số chương hoặc file bị chọn trùng. Sửa lựa chọn rồi xác nhận.')
            ids=[];outcomes=[]
            for choice in body.items:
                item=items.get(str(choice.item_id))
                if item is None or item['status']=='invalid':raise BookError('File lỗi không thể nhập. Xem trước lại.')
                from api.import_sources import verify_source
                verify_source(item,verification)
                source=repo.root/'imports'/str(import_id)/(item['id']+'.txt')
                safe_directory(source.parent)
                if source.is_symlink() or not source.is_file() or source.stat().st_nlink>1:
                    raise BookError('Dữ liệu đã thay đổi sau xem trước. Tạo phiên mới.')
                content=source.read_bytes()
                if hashlib.sha256(content).hexdigest()!=item['sha256']:
                    raise BookError('Dữ liệu đã thay đổi sau xem trước. Tạo phiên mới.')
                chapter=db.exec(select(Chapter).where(Chapter.book_id==str(book_id),Chapter.number==choice.number)).first()
                if chapter and chapter.source_hash==item['sha256']:
                    ids.append(chapter.id);outcomes.append({'number':choice.number,'action':'skipped','chapter_id':chapter.id})
                    continue
                if chapter is None and item.get('existing_id'):raise BookError('Chương đã bị xóa sau xem trước. Tạo phiên nhập mới.')
                updating=chapter is not None
                if updating and (item.get('existing_id')!=chapter.id or item.get('existing_revision')!=chapter.revision):
                    raise BookError('Chương đã đổi sau xem trước hoặc số được ánh xạ sang chương khác. Xem trước lại.')
                if updating and choice.action!='update':
                    raise BookError('Nội dung chương đã khác. Chọn xác nhận cập nhật hoặc bỏ chọn file.')
                if not updating:
                    chapter=Chapter(book_id=str(book_id),number=choice.number,title=(item.get('chapter_title') or f'Chương {choice.number}') if item.get('input_method')=='direct_text' else Path(item['name']).stem,source_hash=item['sha256'])
                    db.add(chapter);db.flush()
                else:
                    chapter.source_hash=item['sha256'];chapter.revision+=1
                    if item.get('input_method')=='direct_text' and item.get('chapter_title'):chapter.title=item['chapter_title']
                    db.add(chapter)
                    for artifact in db.exec(select(Artifact).where(Artifact.chapter_id==chapter.id,Artifact.kind!='source_txt')).all():
                        artifact.verified=False;db.add(artifact)
                path=repo.root/'books'/str(book_id)/'chapters'/chapter.id
                folder=safe_directory(path)
                if not updating:new_folders.append(folder)
                output=folder/('source-'+str(uuid4())+'.txt' if updating else 'source.txt')
                with output.open('xb') as stream:stream.write(content)
                written.append(output)
                provenance={'method':'direct_text' if item.get('input_method')=='direct_text' else 'server_folder' if 'server_source' in item else 'browser_upload',
                            'filename':item['name'],'import_id':str(import_id),'revision':chapter.revision}
                if 'server_source' in item:provenance.update(source=item['server_source'],relative=item['server_relative'])
                db.add(Artifact(chapter_id=chapter.id,kind='source_txt',relative_path=output.relative_to(repo.root).as_posix(),
                                sha256=item['sha256'],provenance=json.dumps(provenance,ensure_ascii=False),verified=True))
                ids.append(chapter.id);outcomes.append({'number':choice.number,'action':'updated' if updating else 'created','chapter_id':chapter.id,
                                                       'revision':chapter.revision,'dependent_artifacts_need_refresh':updating})
            session.status='confirmed';session.result_json=json.dumps({'chapter_ids':ids,'outcomes':outcomes,'selection':selection});db.add(session)
            result=view(session)
        return result
    except BaseException:
        for output in written:output.unlink(missing_ok=True)
        for folder in new_folders:
            if folder.exists() and not any(folder.iterdir()):folder.rmdir()
        raise


def cancel(repo,book_id,import_id):
    with session_scope(repo.engine) as db:
        from sqlalchemy import text
        db.exec(text('BEGIN IMMEDIATE'))
        session=get_import(db,book_id,import_id)
        if session.status=='confirmed':raise BookError('Phiên đã xác nhận không thể hủy.')
        session.status='cancelled';db.add(session);result=view(session)
    folder=repo.root/'imports'/str(import_id)
    if folder.exists():
        if folder.is_symlink():raise BookError('Thư mục phiên không hợp lệ.')
        shutil.rmtree(folder)
    return result


def attach_routes(router,call,verification=False):
    @router.post('/{book_id}/text-imports',response_model=ImportView,status_code=201)
    def create_text_preview(book_id:UUID,body:TextPreviewRequest,request:Request):
        return call(request,lambda r:preview_text(r,book_id,body))

    @router.post('/{book_id}/imports',response_model=ImportView,status_code=201)
    def create_preview(book_id:UUID,body:PreviewRequest,request:Request):
        return call(request,lambda r:preview(r,book_id,body))
    @router.get('/{book_id}/imports/{import_id}',response_model=ImportView)
    def detail(book_id:UUID,import_id:UUID,request:Request):
        def action(repo):
            with session_scope(repo.engine) as db:return view(get_import(db,book_id,import_id))
        return call(request,action)
    @router.post('/{book_id}/imports/{import_id}/confirm',response_model=ImportView)
    def confirm_preview(book_id:UUID,import_id:UUID,body:ConfirmRequest,request:Request):
        return call(request,lambda r:confirm(r,book_id,import_id,body,verification))
    @router.post('/{book_id}/imports/{import_id}/cancel',response_model=ImportView)
    def cancel_preview(book_id:UUID,import_id:UUID,request:Request):
        return call(request,lambda r:cancel(r,book_id,import_id))
    from api.import_sources import FolderRequest, roots, browse, preview_folder
    @router.get('/{book_id}/import-sources')
    def sources(book_id:UUID,request:Request):
        def action(repo):
            repo.get(book_id)
            return {'items':[{'id':key,'label':key} for key in roots(verification)]}
        return call(request,action)
    @router.get('/{book_id}/folders')
    def folders(book_id:UUID,request:Request,source:str,directory:str=''):
        def action(repo):
            repo.get(book_id)
            return browse(source,directory,verification)
        return call(request,action)
    @router.post('/{book_id}/folder-imports',response_model=ImportView,status_code=201)
    def folder_preview(book_id:UUID,body:FolderRequest,request:Request):
        return call(request,lambda r:preview_folder(r,book_id,body,verification))
    from api.chapters import attach_routes as attach_chapters
    attach_chapters(router, call)
