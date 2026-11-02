"""T11 atomic local configuration with field inheritance; no secrets accepted."""
import fcntl
import json
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from api.books import BookError, safe_directory
from src.doctor import read_config


class Values(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    provider: Literal['vieneu','piper','edge-tts','openai']='vieneu'
    voice: str = Field(default='',max_length=100)
    chunk_chars: int = Field(default=2000,ge=100,le=10000)
    concurrency: int = Field(default=3,ge=1,le=16)
    retries: int = Field(default=2,ge=0,le=5)
    cleanup: bool = True
    translation_model: str = Field(default='gpt-4o-mini',min_length=1,max_length=100)


class SaveConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    values: dict


def check_path(path):
    if any(p.is_symlink() for p in (path,*path.parents)) or (path.is_file() and path.stat().st_nlink>1):
        raise BookError('File cấu hình không được là symlink/hardlink.')


def seed():
    env=read_config()
    provider=(env.get('TTS_PROVIDER') or 'edge-tts').lower()
    provider={'local':'piper','edge':'edge-tts','edge_tts':'edge-tts','vieneu-tts':'vieneu'}.get(provider,provider)
    try:
        return Values(provider=provider,voice='' if provider=='piper' else (env.get('VIENEU_VOICE') or '') if provider=='vieneu' else 'alloy' if provider=='openai' else env.get('TTS_VOICE') or '',
                      chunk_chars=int(env.get('MAX_CHUNK_CHARS','2000')),concurrency=int(env.get('TTS_CONCURRENCY','3')),
                      translation_model=env.get('TRANSLATION_MODEL') or 'gpt-4o-mini').model_dump()
    except (ValueError,ValidationError):raise BookError('Cấu hình server không hợp lệ. Mở Môi trường để kiểm tra trước.')


def read_file(path):
    check_path(path)
    if not path.exists():return {'revision':0,'values':{}}
    if path.stat().st_size>65536:raise BookError('File cấu hình vượt giới hạn.')
    try:
        value=json.loads(path.read_text())
        if not isinstance(value['revision'],int) or not isinstance(value['values'],dict):raise ValueError()
        return value
    except (ValueError,KeyError,TypeError):raise BookError('File cấu hình không hợp lệ; không tự ghi đè.')


def path_for(repo,book_id):
    if book_id:
        repo.get(book_id)
        return safe_directory(repo.root/'books'/str(book_id))/'settings.json'
    return repo.root/'settings.json'


def read(repo,book_id=None):
    base=seed();defaults=read_file(path_for(repo,None));base.update(defaults['values'])
    own=read_file(path_for(repo,book_id)) if book_id else defaults
    overrides=own['values'] if book_id else {}
    try:effective=Values(**{**base,**overrides}).model_dump()
    except ValidationError:raise BookError('Cấu hình đã lưu không hợp lệ. Kiểm tra file trước khi tiếp tục.')
    if effective['provider']=='piper' and effective['voice']:
        # Piper uses its model file, no voice selector. Ignore inherited voice only
        # when this scope explicitly selects Piper; never advertise unsupported voice.
        effective['voice']=''
    return {'revision':own['revision'],'values':own['values'],'effective':effective,
            'sources':{key:('book' if key in overrides else 'workspace' if key in defaults['values'] else 'server') for key in effective},
            'scope':str(book_id) if book_id else 'workspace'}


def save(repo,body,book_id=None):
    path=path_for(repo,book_id);lock=path.with_suffix('.lock');check_path(lock)
    with lock.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        current=read_file(path)
        if body.revision!=current['revision']:raise BookError('Cấu hình đã thay đổi. Tải lại trước khi lưu.')
        unknown=set(body.values)-set(Values.model_fields)
        if unknown:raise BookError('Cấu hình chứa trường không được hỗ trợ.',422)
        base=read(repo)['effective'] if book_id else seed()
        try:
            effective=Values(**{**base,**body.values})
        except ValidationError:raise BookError('Provider/giọng/chunk/concurrency/retry/model dịch không hợp lệ.',422)
        if effective.provider=='piper' and body.values.get('voice'):
            raise BookError('Piper dùng model server, không hỗ trợ chọn voice.',422)
        data={'revision':current['revision']+1,'values':body.values}
        temporary=path.with_suffix('.tmp');check_path(temporary)
        with temporary.open('w') as output:
            json.dump(data,output,ensure_ascii=False,indent=2);output.flush()
            import os
            os.fsync(output.fileno())
        temporary.replace(path)
    return read(repo,book_id)


def attach_routes(router,call):
    @router.get('/workspace/capabilities')
    def capabilities():
        return {'providers':[{'id':p,'voice':p!='piper','batch':True,'retry':True,'model_source':'server' if p=='piper' else 'provider'} for p in ['vieneu','piper','edge-tts','openai']],
                'notice':'Danh sách khả năng hỗ trợ; không xác minh provider sẵn sàng. Mở Môi trường để kiểm tra.'}
    @router.get('/workspace/settings')
    def defaults(request:Request):return call(request,lambda r:read(r))
    @router.put('/workspace/settings')
    def set_defaults(body:SaveConfig,request:Request):return call(request,lambda r:save(r,body))
    @router.get('/{book_id}/settings')
    def book_config(book_id:UUID,request:Request):return call(request,lambda r:read(r,book_id))
    @router.put('/{book_id}/settings')
    def set_book_config(book_id:UUID,body:SaveConfig,request:Request):return call(request,lambda r:save(r,body,book_id))
