"""T26 read-only, redacted server connection state; never accept credentials."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from fastapi import Request
from api.configuration import read as read_configuration
from src.doctor import read_config


def endpoint(value,secrets=()):
    try:
        url=urlsplit(value or '')
        if url.scheme not in {'http','https'} or not url.hostname:return {'configured':False,'display':None,'valid':False}
        host=url.hostname
        if ':' in host:host='['+host+']'
        netloc=host+(':'+str(url.port) if url.port else '')
        safe=urlunsplit((url.scheme,netloc,url.path,'',''))
        for secret in secrets:
            if secret:safe=safe.replace(secret,'[redacted]')
        return {'configured':True,'display':safe,'valid':True}
    except ValueError:return {'configured':bool(value),'display':None,'valid':False}


def read(repo,book_id=None):
    values=read_configuration(repo,book_id)['effective'];env=read_config()
    key=env.get('OPENAI_API_KEY') or '';token=env.get('HF_TOKEN') or ''
    safe_endpoint=endpoint(env.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1',[key,token])
    translation={'provider':'openai-compatible','model':values['translation_model'],'endpoint':safe_endpoint,
                 'key_required':True,'key_configured':bool(key.strip()),'verified':False}
    provider=values['provider'];mode=env.get('VIENEU_MODE') or 'v3turbo'
    model='tts-1' if provider=='openai' else mode if provider=='vieneu' else Path(env.get('PIPER_MODEL_PATH') or 'models/piper/vi_VN-vais1000-medium.onnx').name if provider=='piper' else 'Edge TTS'
    connection=safe_endpoint if provider=='openai' else endpoint(env.get('VIENEU_API_BASE'),[key,token]) if provider=='vieneu' and mode=='remote' else None
    tts={'provider':provider,'model':model,'endpoint':connection,'key_required':provider=='openai',
         'key_configured':bool(key.strip()) if provider=='openai' else None,'hf_token_configured':bool(token.strip()) if provider=='vieneu' else None,'verified':False}
    return {'tts':tts,'translation':translation,'notice':'Chỉ đọc trạng thái cấu hình server; chưa gọi dịch vụ hoặc xác minh key/quota. Không trả key/token.',
            'how_to':'Cấu hình OPENAI_API_KEY / HF_TOKEN và endpoint tại .env gốc hoặc biến môi trường launcher. Biến môi trường được ưu tiên; restart launcher khi đổi biến của tiến trình.'}


def attach_routes(router,call):
    @router.get('/workspace/connections')
    def workspace_connections(request:Request):return call(request,lambda r:read(r))
    @router.get('/{book_id}/connections')
    def book_connections(book_id:UUID,request:Request):return call(request,lambda r:read(r,book_id))
