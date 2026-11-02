"""Controlled SDK subprocess lifecycle shared by worker actions."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from api.books import BookError
from api.configuration import check_path
from api.verification.workspace import PROJECT_ROOT,atomic_json

MODULES={'src.web_tts_bridge','src.web_translate_bridge','src.web_merge_bridge'}


def launch(repo,job,folder,module,manifest):
    from api.job_control import stop_requested
    if module not in MODULES:raise BookError('Bridge không được hỗ trợ.')
    report_path=folder/'bridge-report.json';check_path(report_path)
    report_path.unlink(missing_ok=True)
    if stop_requested(repo,job['id']):return {'status':'stopped','provider_calls':0,'notice':'Đã dừng trước khi gọi provider.'}
    environment=os.environ.copy();environment['NOVEL2VOICE_BRIDGE_ROOT']=str(repo.root.resolve())
    process=subprocess.Popen([str(PROJECT_ROOT/'.venv/bin/python'),'-m',module,'--manifest',str(manifest)],cwd=PROJECT_ROOT,
                             env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    atomic_json(folder/'bridge-process.json',{'pid':process.pid,'parent_pid':os.getpid(),'module':module})
    deadline=time.monotonic()+600;sent_stop=False
    while process.poll() is None:
        if stop_requested(repo,job['id']) and not sent_stop:
            try:os.kill(process.pid,signal.SIGUSR1)
            except ProcessLookupError:pass
            sent_stop=True
        if time.monotonic()>deadline:
            process.kill();process.wait();raise BookError('Provider vượt thời gian cho phép.')
        time.sleep(.1)
    if not report_path.is_file():
        if sent_stop:return {'status':'stopped','provider_calls':0,'notice':'Đã dừng trước khi bridge hoàn tất khởi động.'}
        raise BookError('Bridge không trả báo cáo hợp lệ.')
    if report_path.stat().st_size>65536:raise BookError('Báo cáo bridge vượt giới hạn.')
    report=json.loads(report_path.read_text())
    if report['status']=='stopped':return report
    if process.returncode or report['status']!='completed':raise BookError('Provider thực thi thất bại; xem checkpoint và kiểm tra môi trường.')
    return report
