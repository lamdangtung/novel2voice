"""T25 sample job uses a dedicated cache and only a book-level artifact."""
import hashlib
import json
import os
from api.books import BookError,safe_directory
from api.storage import session_scope
from api.storage.models import BookArtifact
from api.merged_audio import media
from api.configuration import check_path
from api.verification.workspace import WorkspaceManager,atomic_json
from api.bridge_runtime import launch
from api.audio_imports import inspect_mp3,digest
from src.web_contract import tts_fingerprint


def perform_job(repo,job,verification):
    config=json.loads(job['config_json']);plan=config['plan'];values=plan['configuration']
    if tts_fingerprint(values,verification)!=plan['tts_fingerprint']:raise BookError('Runtime thay đổi; xem kế hoạch thử lại.')
    if plan.get('blocked'):raise BookError('Thiếu điều kiện thử giọng.')
    if plan.get('reuse_artifact_id'):
        with session_scope(repo.engine) as db:artifact,_=media(repo,db,job['book_id'],plan['reuse_artifact_id'],'voice_sample')
        return {'status':'completed','voice_artifact_id':artifact.id,'duration':artifact.duration,'sha256':artifact.sha256,'provider_calls':0,'reused':True,
                'steps':config['steps'],'completed_steps':config['steps'],'notice':'Tái sử dụng mẫu cùng câu/giọng/cấu hình; không tạo chương truyện.'}
    folder=safe_directory(repo.root/'job-results'/job['id']);source=folder/'sample.txt';check_path(source);source.write_text(plan['text'],encoding='utf-8')
    output=folder/'sample.mp3';state=safe_directory(repo.root/'books'/job['book_id']/'.voice-cache')
    request={'parent_pid':os.getpid(),'book_root':str(repo.root/'books'/job['book_id']),'source':str(source),'source_hash':hashlib.sha256(source.read_bytes()).hexdigest(),
             'output':str(output),'state_dir':str(state),'log':str(folder/'calls.jsonl'),'configuration':values,'fingerprint':plan['tts_fingerprint'],
             'verification':verification,'chapter_id':'voice-sample','force':plan['policies']['force'],'resume':True}
    if verification:
        manager=WorkspaceManager();manager.create('queue-fixture');request['fixture']=str(manager.target('queue-fixture')/'fixtures/tone.mp3')
    manifest=folder/'bridge-request.json';check_path(manifest);atomic_json(manifest,request)
    report=launch(repo,job,folder,'src.web_tts_bridge',manifest)
    if report['status']=='stopped':return report
    duration=inspect_mp3(output)
    if not duration or digest(output)!=report['output_sha256']:raise BookError('Mẫu giọng không qua kiểm tra audio.')
    with session_scope(repo.engine) as db:
        artifact=BookArtifact(book_id=job['book_id'],job_id=job['id'],kind='voice_sample',relative_path=output.relative_to(repo.root).as_posix(),sha256=report['output_sha256'],duration=duration,
                              source_signature=plan['source_signature'],source_manifest=json.dumps({'provider':values['provider'],'voice':values['voice'],'verification':verification,'tts_fingerprint':plan['tts_fingerprint'],'provider_signature':report['provider_signature']}))
        db.add(artifact);db.flush();identifier=artifact.id
    return {'status':'completed','voice_artifact_id':identifier,'duration':duration,'sha256':report['output_sha256'],'provider_calls':report['provider_calls'],'reused':False,
            'steps':config['steps'],'completed_steps':config['steps'],'notice':'Mẫu âm tone kiểm thử, không phải giọng thật.' if verification else 'Đã tạo mẫu giọng thật; chưa phải đánh giá chất lượng của người dùng.'}
