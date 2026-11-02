"""T12 validated, versioned per-book CSV; never replaces valid data on error."""
import base64
import binascii
import csv
import fcntl
import hashlib
import io
import json
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from fastapi import Request
from api.books import BookError, safe_directory
from api.configuration import check_path
from api.storage.models import now
from api.verification.workspace import PROJECT_ROOT, atomic_json


class GlossaryUpload(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=200)
    content_base64: str = Field(max_length=350000)
    revision: int = Field(ge=0)


def parse(content, *, legacy=False):
    if len(content)>256*1024:raise BookError('Glossary tối đa 256 KiB.',413)
    try:
        text=content.decode('utf-8-sig')
        if '\x00' in text:raise ValueError()
    except (UnicodeDecodeError,ValueError):raise BookError('Glossary phải là CSV UTF-8, không chứa NUL.',422)
    reader=csv.reader(io.StringIO(text,newline=''),strict=True);entries=[];seen=set()
    try:
        header=next(reader,None)
        if header is None or [c.strip().lower() for c in header]!=['en','vi']:
            raise BookError('Dòng 1: cần đúng hai cột en,vi.',422)
        for row in reader:
            line=reader.line_num
            if not row:continue
            if len(row)!=2 or any(not c.strip() for c in row):raise BookError(f'Dòng {line}: cần đủ hai giá trị en,vi.',422)
            en,vi=(c.strip() for c in row)
            if max(len(en),len(vi))>300:raise BookError(f'Dòng {line}: thuật ngữ tối đa 300 ký tự.',422)
            if en in seen:
                if not legacy:raise BookError(f'Dòng {line}: thuật ngữ EN bị trùng.',422)
                next(item for item in entries if item['en']==en)['vi']=vi
            else:
                seen.add(en);entries.append({'en':en,'vi':vi})
            if len(entries)>2000:raise BookError('Glossary tối đa 2000 thuật ngữ.',413)
    except csv.Error:raise BookError(f'Dòng {reader.line_num}: cú pháp CSV không hợp lệ.',422)
    if not entries:raise BookError('Glossary cần ít nhất một thuật ngữ.',422)
    return entries


def folder(repo,book_id):
    repo.get(book_id)
    return safe_directory(repo.root/'books'/str(book_id)/'glossary')


def metadata(path):
    check_path(path)
    if not path.exists():return {'revision':0,'versions':[]}
    if path.stat().st_size>65536:raise BookError('Metadata glossary vượt giới hạn.')
    try:
        value=json.loads(path.read_text())
        if not isinstance(value['revision'],int) or not isinstance(value['versions'],list):raise ValueError()
        return value
    except (ValueError,KeyError,TypeError):raise BookError('Metadata glossary không hợp lệ.')


def read(repo,book_id):
    directory=folder(repo,book_id);saved=metadata(directory/'versions.json')
    if saved['versions']:
        current=saved['versions'][-1]
        try:UUID(current['id'])
        except (KeyError,ValueError,TypeError):raise BookError('ID phiên bản glossary không hợp lệ.')
        path=directory/(current['id']+'.csv');check_path(path)
        if not path.is_file():raise BookError('File glossary không còn.')
        if path.stat().st_size>256*1024:raise BookError('Glossary vượt giới hạn.',413)
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=current['sha256']:raise BookError('Checksum glossary không khớp.')
        return {**saved,'source':'book','sha256':current['sha256'],'entries':parse(content)}
    default=PROJECT_ROOT/'glossary.csv';check_path(default)
    if default.is_file() and default.stat().st_size>256*1024:raise BookError('Glossary mặc định vượt giới hạn.',413)
    content=default.read_bytes() if default.is_file() else b''
    warning='Glossary mặc định theo quy tắc CLI: EN trùng dùng giá trị cuối.' if content else ''
    try:entries=parse(content,legacy=True) if content else []
    except BookError:
        entries=[];warning='Glossary mặc định không hợp lệ; có thể upload bản riêng hợp lệ cho truyện.'
    return {**saved,'source':'server' if content else 'empty','sha256':hashlib.sha256(content).hexdigest() if content else None,'entries':entries,'notice':warning}


def save(repo,book_id,body):
    if '/' in body.name or '\\' in body.name or not body.name.lower().endswith('.csv') or any(ord(c)<32 for c in body.name):
        raise BookError('Chỉ nhận tên file CSV, không nhận đường dẫn.',422)
    try:content=base64.b64decode(body.content_base64,validate=True)
    except (ValueError,binascii.Error):raise BookError('Nội dung upload không hợp lệ.',422)
    parse(content)  # Validate all rows before touching current version.
    directory=folder(repo,book_id);lock=directory/'glossary.lock';check_path(lock)
    with lock.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        saved=metadata(directory/'versions.json')
        if saved['revision']!=body.revision:raise BookError('Glossary đã thay đổi. Tải lại trước khi thay bản mới.')
        if len(saved['versions'])>=200:raise BookError('Đã đạt giới hạn 200 phiên bản glossary.')
        identifier=str(uuid4());version={'id':identifier,'filename':body.name,'sha256':hashlib.sha256(content).hexdigest(),'created_at':now(),'revision':saved['revision']+1}
        with (directory/(identifier+'.csv')).open('xb') as out:out.write(content)
        path=directory/'versions.json';check_path(path.with_suffix('.json.tmp'))
        atomic_json(path,{'revision':version['revision'],'versions':saved['versions']+[version]})
    return read(repo,book_id)


def attach_routes(router,call):
    @router.get('/{book_id}/glossary')
    def get_glossary(book_id:UUID,request:Request):return call(request,lambda r:read(r,book_id))
    @router.put('/{book_id}/glossary')
    def upload_glossary(book_id:UUID,body:GlossaryUpload,request:Request):return call(request,lambda r:save(r,book_id,body))
