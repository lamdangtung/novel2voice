import os,sys,time,json,base64
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,'/Users/lamdt/Desktop/novel2voice')
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
from api.verification.workspace import WorkspaceManager
from api.books import BookRepository,CreateBook
from api.voices import catalog,preview,VoiceRequest
from api.job_plans import confirm,preview as plan_preview,PlanRequest
from api.configuration import save,SaveConfig
from api.imports import preview as import_preview,confirm as import_confirm,PreviewRequest,ConfirmRequest
from api.worker import claim,execute
from api.storage import session_scope
from api.storage.models import Job
from api.jobs import job_view
m=WorkspaceManager();m.create('t31-real');repo=BookRepository(m.target('t31-real')/'web')
book=repo.create(CreateBook(name='T31 VieNeu thật offline',language='vi',request_id=uuid4())).id
voice=catalog('vieneu')['default_voice'];save(repo,SaveConfig(revision=0,values={'provider':'vieneu','voice':voice}),book)
text='Xin chào. Đây là bản đọc thử tiếng Việt của ứng dụng chuyển truyện thành giọng nói.'
results=[]
def run(plan):
 print('PLAN',plan['id'],plan['plan'].get('blocked_reasons',[]),flush=True);confirm(repo,plan['id']);start=time.monotonic();execute(repo,claim(repo),False)
 with session_scope(repo.engine) as db:value=job_view(db.get(Job,plan['id']),repo.root,True)
 results.append({'job':plan['id'],'status':value['status'],'seconds':round(time.monotonic()-start,2),'report':value['report']});print(json.dumps(results[-1],ensure_ascii=False),flush=True)
 return value
try:
 sample=run(preview(repo,book,VoiceRequest(request_id=uuid4(),provider='vieneu',voice=voice,text=text),False))
 if sample['status']=='completed':
  p=import_preview(repo,book,PreviewRequest(files=[{'name':'1.txt','content_base64':base64.b64encode(text.encode()).decode()}]));chapter=import_confirm(repo,book,p.id,ConfirmRequest(items=[{'item_id':p.items[0].id,'number':1}])).chapter_ids[0]
  run(plan_preview(repo,PlanRequest(request_id=uuid4(),book_id=book,chapter_ids=[chapter],action='tts'),False))
  run(plan_preview(repo,PlanRequest(request_id=uuid4(),book_id=book,chapter_ids=[chapter],action='tts'),False))
 folder=Path('docs/tasks/v1.1/evidence/T31');folder.mkdir(parents=True,exist_ok=True);(folder/'real-provider-report.json').write_text(json.dumps({'provider':'vieneu','voice':voice,'offline':True,'workspace':str(repo.root),'book':book,'results':results},ensure_ascii=False,indent=2))
finally:repo.engine.dispose()
