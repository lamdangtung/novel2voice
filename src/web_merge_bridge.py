"""Merge existing audio only; this process never constructs a TTS provider."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from src.web_tts_bridge import checked,manifest_root,watch_parent
from src.audio_merger import AudioMerger
from src.tts_jobs import TTSJobRunner,file_digest
from src.text_chunker import TextChunker


class NoTTS:
    def generate_batch(self,*args,**kwargs):raise AssertionError('Merge must not invoke TTS')


class InjectedMerger(AudioMerger):
    def merge_mp3_files(self,paths,output_file,cleanup_inputs=False):
        Path(output_file).write_bytes(b'partial QA only')
        raise RuntimeError('INJECTED_MERGE_FAILURE')


def run(request,root):
    paths=[]
    for item in request['inputs']:
        path=checked(item['path'],root)
        if not path.is_file() or file_digest(path)!=item['sha256']:raise ValueError('Input changed')
        paths.append(path)
    output=checked(request['output'],root);state=checked(request['state_dir'],root)
    merger=InjectedMerger() if request.get('verification_failure') and request['verification'] else AudioMerger()
    runner=TTSJobRunner(NoTTS(),merger,TextChunker(),state,concurrency=1,retries=0)
    runner.combine(paths,output,resume=not request.get('force',False))
    return {'status':'completed','output_sha256':file_digest(output),'duration':merger.get_duration(output),
            'input_duration':sum(merger.get_duration(p) for p in paths),'provider_calls':0,'notice':'Đã ghép audio hiện có, không gọi TTS.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);args=parser.parse_args()
    path=Path(args.manifest).absolute();root=manifest_root(path);request=json.loads(path.read_text());watch_parent(request.get('parent_pid',os.getppid()))
    try:report=run(request,root)
    except KeyboardInterrupt:report={'status':'stopped','provider_calls':0,'notice':'Đã dừng ghép; giữ nguyên file chương và bản ghép trước.'}
    except Exception:report={'status':'failed','error':'MERGE_FAILED','provider_calls':0,'notice':'Ghép lỗi; chưa công bố file mới, nguồn và bản trước giữ nguyên.'}
    output=path.with_name('bridge-report.json');temporary=checked(output.with_suffix('.tmp'),root);temporary.write_text(json.dumps(report));temporary.replace(output)
    return 0 if report['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
