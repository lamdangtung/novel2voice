"""T07 explicit server roots; preflight every link before reading file contents."""
import base64
import os
from pathlib import Path, PurePosixPath
from pydantic import BaseModel, ConfigDict, Field
from api.books import BookError
from api.verification.workspace import PROJECT_ROOT, WorkspaceManager


class FolderRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source: str = Field(max_length=80)
    directory: str = Field(default='',max_length=500)
    recursive: bool = False


def roots(verification):
    result={'input':PROJECT_ROOT/'input'}
    if verification:
        manager=WorkspaceManager()
        for item in manager.list():
            # manager.list returns workspace summaries, owned marker checked again below.
            name=item['name']
            result['fixture:'+name]=manager.target(name)/'fixtures'
    return result


def resolve_folder(source,directory,verification):
    available=roots(verification)
    if source not in available:raise BookError('Nguồn thư mục không được phép.',403)
    if '\\' in directory or '\x00' in directory or PurePosixPath(directory).is_absolute() or '..' in PurePosixPath(directory).parts:
        raise BookError('Chỉ chọn thư mục con trong vùng được phép.',403)
    if source.startswith('fixture:'):WorkspaceManager().describe(source.split(':',1)[1])
    root=available[source];folder=root/directory
    for p in (folder,*folder.parents):
        if p.is_symlink():raise BookError('Từ chối symlink trong đường dẫn nguồn.',403)
    if not folder.is_dir():raise BookError('Thư mục nguồn không tồn tại.',404)
    return root,folder


def scan(folder,recursive):
    files=[];folders=[];visited=0;pending=[folder]
    while pending:
        current=pending.pop()
        for entry in sorted(os.scandir(current),key=lambda e:e.name):
            visited+=1
            if visited>2000:raise BookError('Thư mục quá lớn; chọn phạm vi nhỏ hơn.',413)
            if entry.is_symlink():raise BookError('Thư mục có symlink; không đọc file trong phiên này.',403)
            path=Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if current==folder:folders.append(entry.name)
                if recursive:pending.append(path)
            elif entry.is_file(follow_symlinks=False) and path.suffix.lower()=='.txt':
                if path.stat().st_nlink>1:raise BookError('Từ chối TXT hardlink.',403)
                files.append(path)
            if len(files)>20:raise BookError('Tối đa 20 file TXT mỗi phiên; chọn thư mục nhỏ hơn.',413)
    return files,folders


def browse(source,directory,verification):
    root,folder=resolve_folder(source,directory,verification)
    files,folders=scan(folder,False)
    return {'source':source,'directory':'' if folder==root else folder.relative_to(root).as_posix(),
            'folders':folders,'txt_files':[p.name for p in files]}


def preview_folder(repo,book_id,body,verification):
    from api.imports import preview, PreviewRequest, UploadFile, MAX_FILE, MAX_TOTAL
    root,folder=resolve_folder(body.source,body.directory,verification)
    files,_=scan(folder,body.recursive)
    if not files:raise BookError('Không có TXT trong phạm vi đang chọn.',422)
    if any(p.stat().st_size>MAX_FILE for p in files) or sum(p.stat().st_size for p in files)>MAX_TOTAL:
        raise BookError('Giới hạn: 256 KiB/file, tổng 2 MiB.',413)
    # All candidates have passed path/link checks before any TXT content is read.
    upload=PreviewRequest(files=[UploadFile(name=p.name,content_base64=base64.b64encode(p.read_bytes()).decode()) for p in files])
    result=preview(repo,book_id,upload)
    from api.storage import session_scope
    from api.storage.models import ImportSession
    import json
    with session_scope(repo.engine) as db:
        session=db.get(ImportSession,result.id);items=json.loads(session.items_json)
        for item,path in zip(items,files):
            item['server_source']=body.source
            item['server_relative']=path.relative_to(root).as_posix()
        session.items_json=json.dumps(items,ensure_ascii=False);db.add(session)
    return result


def verify_source(item,verification):
    if 'server_source' not in item:return
    import hashlib
    relative=PurePosixPath(item['server_relative'])
    _,folder=resolve_folder(item['server_source'],str(relative.parent) if str(relative.parent)!='.' else '',verification)
    path=folder/relative.name
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink>1:
        raise BookError('Nguồn đã thay đổi hoặc không còn an toàn. Xem trước lại.')
    if path.stat().st_size>256*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise BookError('Nguồn đã thay đổi sau xem trước. Xem trước lại trước khi xác nhận.')
