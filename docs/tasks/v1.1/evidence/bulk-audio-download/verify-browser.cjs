const {chromium}=require('playwright');
const {spawn,execFileSync}=require('child_process');
const fs=require('fs'),assert=require('assert/strict');
const base=process.env.NOVEL2VOICE_PROJECT||'/Users/lamdt/Desktop/novel2voice';
const evidence=base+'/docs/tasks/v1.1/evidence/bulk-audio-download';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function zipInfo(path){return JSON.parse(execFileSync(base+'/api/.venv/bin/python',['-c','import zipfile,json,hashlib,sys\nwith zipfile.ZipFile(sys.argv[1]) as z: print(json.dumps({"names":z.namelist(),"hashes":[hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()]}))',path],{encoding:'utf8'}));}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});let child;
 try{
  child=spawn(base+'/api/.venv/bin/python',['-m','api.dev','--app-port','8100','--api-port','8101','--verification','--data-dir',base+'/.verification/bulk-audio-'+Date.now()],{cwd:base,stdio:['pipe','pipe','pipe']});
  let output='';child.stdout.on('data',x=>output+=x);child.stderr.on('data',x=>output+=x);
  for(let i=0;i<150&&!output.includes('App: http://127.0.0.1:8100');i++)await delay(100);
  assert.match(output,/App: http:\/\/127.0.0.1:8100/);
  const page=await browser.newPage({viewport:{width:1440,height:1100},acceptDownloads:true}),errors=[],outside=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:810'))outside.push(r.url());});
  const url='http://127.0.0.1:8101/api/v1/',h={origin:'http://127.0.0.1:8100','x-novel2voice-client':'web'};
  async function post(path,data){const r=await page.request.post(url+path,{headers:h,data});assert.ok(r.ok(),await r.text());return r.json();}
  async function get(path){return (await page.request.get(url+path)).json();}
  const book=await post('books',{name:'Audio ZIP QA '+Date.now(),language:'vi',request_id:crypto.randomUUID()});
  for(let start=1;start<=45;start+=20){const numbers=Array.from({length:Math.min(20,46-start)},(_,i)=>i+start);const p=await post('books/'+book.id+'/imports',{files:numbers.map(n=>({name:n+'.txt',content_base64:Buffer.from('Nội dung chương '+n).toString('base64')}))});await post('books/'+book.id+'/imports/'+p.id+'/confirm',{items:p.items.map(x=>({item_id:x.id,number:x.number}))});}
  const chapters=(await get('books/'+book.id+'/chapters?limit=100')).items;
  const tone=fs.readFileSync(base+'/.verification/workspaces/queue-fixture/fixtures/tone.mp3'),expectedHash=require('crypto').createHash('sha256').update(tone).digest('hex');
  for(const number of [1,2,10,21,45]){const p=await post('books/'+book.id+'/audio-imports',{files:[{name:number+'.mp3',content_base64:tone.toString('base64')}]});await post('books/'+book.id+'/audio-imports/'+p.id+'/confirm',{items:[{item_id:p.items[0].id,chapter_id:chapters.find(c=>c.number===number).id}]});}
  await page.goto('http://127.0.0.1:8100/#library/'+book.id);await page.locator('[aria-label="Chọn chương 1"]').check();await page.locator('#next-chapters').click();await page.locator('[aria-label="Chọn chương 21"]').check();await page.locator('#next-chapters').click();await page.locator('[aria-label="Chọn chương 45"]').check();
  await page.locator('#preview-audio-download').click();await page.locator('#audio-download-preview').filter({hasText:'3 MP3 tải được'}).waitFor();
  let downloaded=page.waitForEvent('download');await page.locator('#download-audio-zip').click();let file=await downloaded;await file.saveAs(evidence+'/selected.zip');
  const selected=zipInfo(evidence+'/selected.zip');assert.deepEqual(selected.names.map(n=>Number(n.split(' - ')[0])),[1,21,45]);assert.ok(selected.hashes.every(x=>x===expectedHash));assert.ok(page.url().includes('#library/'+book.id));
  await page.locator('#audio-download-range').check();await page.locator('#audio-download-start').fill('1');await page.locator('#audio-download-end').fill('10');await page.locator('#preview-audio-download').click();await page.locator('#audio-download-preview').filter({hasText:'7 chương bỏ qua'}).waitFor();
  await page.locator('#audio-download-preview summary').click();await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:evidence+'/range-mobile.png',fullPage:true});
  downloaded=page.waitForEvent('download');await page.locator('#download-audio-zip').click();file=await downloaded;await file.saveAs(evidence+'/range.zip');
  const range=zipInfo(evidence+'/range.zip');assert.deepEqual(range.names.map(n=>Number(n.split(' - ')[0])),[1,2,10]);assert.ok(range.hashes.every(x=>x===expectedHash));
  await page.locator('#audio-download-start').fill('3');await page.locator('#audio-download-end').fill('4');await page.locator('#preview-audio-download').click();await page.locator('#audio-download-preview').filter({hasText:'0 MP3 tải được'}).waitFor();assert.equal(await page.locator('#download-audio-zip').isDisabled(),true);
  await page.locator('#audio-download-start').fill('10');await page.locator('#audio-download-end').fill('1');await page.locator('#preview-audio-download').click();await page.locator('#audio-download-error').filter({hasText:'khoảng hợp lệ'}).waitFor();
  await page.locator('#audio-download-start').fill('1');await page.locator('#audio-download-end').fill('2');await page.locator('#preview-audio-download').click();await page.locator('#audio-download-preview').filter({hasText:'2 MP3 tải được'}).waitFor();
  const first=chapters.find(c=>c.number===1);const removed=await page.request.delete(url+'books/'+book.id+'/chapters/'+first.id,{headers:h,data:{revision:first.revision}});assert.ok(removed.ok());
  await page.locator('#download-audio-zip').click();await page.locator('#audio-download-error').filter({hasText:'đã thay đổi'}).waitFor();await page.screenshot({path:evidence+'/stale-preview-blocked.png',fullPage:true});
  assert.equal((await get('jobs?book_id='+book.id)).total,0);assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  fs.writeFileSync(evidence+'/browser-report.json',JSON.stringify({passed:true,book:book.id,selected_across_pages:[1,21,45],range_chapters:[1,2,10],range_skipped:7,exact_mp3_hashes:true,native_browser_download:true,missing_all_disabled:true,invalid_range:true,deleted_after_preview_blocked:true,no_tts_jobs:true,mobile_no_overflow:true,js_errors:errors},null,2));
  console.log('PASS ZIP browser:selected across pages/range/native download/exact hashes/missing/stale/mobile');
 }finally{if(child){const p=child;p.stdin.write('quit\n');await Promise.race([new Promise(r=>p.on('exit',r)),delay(7000).then(()=>p.kill('SIGTERM'))]);}await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
