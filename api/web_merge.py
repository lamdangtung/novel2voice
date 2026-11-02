"""T24 merge immutable selected audio into a separate book artifact."""
import json
import os
from sqlalchemy import text
from api.books import BookError,safe_directory
from api.storage import session_scope
from api.storage.models import Chapter,BookArtifact
from api.audio_imports import media,digest,inspect_mp3
from api.merged_audio import media as merged_media
from api.configuration import check_path
from api.verification.workspace import atomic_json
from api.bridge_runtime import launch


def inputs(repo,db,job,items):
    result=[]
    for item in items:
        chapter=db.get(Chapter,item['id']);audio,_,path=media(repo,db,job['book_id'],item['audio_id'])
        if not chapter or chapter.source_hash!=item['sha256'] or chapter.revision!=item['revision'] or not audio.verified or audio.sha256!=item['audio_sha256'] or not json.loads(audio.provenance).get('selected'):
            raise BookError('Chương/audio thay đổi sau xem trước; không ghép snapshot cũ.')
        result.append({'path':str(path),'sha256':audio.sha256})
    return result


def perform_job(repo,job,verification):
    config=json.loads(job['config_json']);plan=config['plan'];merge=plan['merge'];folder=safe_directory(repo.root/'job-results'/job['id'])
    with session_scope(repo.engine) as db:
        sources=inputs(repo,db,job,plan['chapters'])
        reuse=merge.get('reuse_artifact_id')
        if reuse:
            artifact,_=merged_media(repo,db,job['book_id'],reuse)
            return {'status':'completed','merged_artifact_id':artifact.id,'sha256':artifact.sha256,'duration':artifact.duration,'input_duration':merge['input_duration'],
                    'provider_calls':0,'reused':True,'steps':len(sources),'completed_steps':len(sources),'notice':'Tái sử dụng bản ghép cùng danh sách/hash; không gọi TTS.'}
    output=folder/'combined.mp3';state=safe_directory(repo.root/'books'/job['book_id']/'.merge-state')
    request={'parent_pid':os.getpid(),'inputs':sources,'output':str(output),'state_dir':str(state),'verification':verification,'force':plan['policies']['force'],
             'verification_failure':plan['policies'].get('verification_merge_failure',False)}
    manifest=folder/'bridge-request.json';check_path(manifest);atomic_json(manifest,request)
    report=launch(repo,job,folder,'src.web_merge_bridge',manifest)
    if report['status']=='stopped':return report
    if output.stat().st_size>512*1024*1024:raise BookError('File ghép vượt512MiB; chưa công bố.')
    duration=inspect_mp3(output)
    if not duration or digest(output)!=report['output_sha256'] or abs(duration-merge['input_duration'])>max(1,merge['input_duration']*.02):raise BookError('Audio ghép không khớp thời lượng/hash.')
    with session_scope(repo.engine) as db:
        db.exec(text('BEGIN IMMEDIATE'));inputs(repo,db,job,plan['chapters'])
        artifact=BookArtifact(book_id=job['book_id'],job_id=job['id'],relative_path=output.relative_to(repo.root).as_posix(),sha256=report['output_sha256'],duration=duration,
                              source_signature=merge['source_signature'],source_manifest=json.dumps(merge['manifest'],sort_keys=True))
        db.add(artifact);db.flush();identifier=artifact.id
    return {'status':'completed','merged_artifact_id':identifier,'sha256':report['output_sha256'],'duration':duration,'input_duration':merge['input_duration'],
            'provider_calls':0,'reused':False,'steps':len(sources),'completed_steps':len(sources),'order':[i['number'] for i in plan['chapters']],
            'notice':'Đã ghép theo thứ tự snapshot, giữ nguyên các file chương, không gọi TTS.'}
