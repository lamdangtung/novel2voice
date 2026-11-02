const {chromium}=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),assert=require('assert/strict');
const base=process.env.NOVEL2VOICE_PROJECT||'/Users/lamdt/Desktop/novel2voice';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});let child;
 try{
  child=spawn(base+'/api/.venv/bin/python',['-m','api.dev','--app-port','8100','--api-port','8101','--verification','--data-dir',base+'/.verification/delete-chapter-'+Date.now()],{cwd:base,stdio:['pipe','pipe','pipe']});
  let output='';child.stdout.on('data',x=>output+=x);child.stderr.on('data',x=>output+=x);
  for(let i=0;i<150&&!output.includes('App: http://127.0.0.1:8100');i++)await delay(100);
  assert.match(output,/App: http:\/\/127.0.0.1:8100/);
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],outside=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:810'))outside.push(r.url());});
  const url='http://127.0.0.1:8101/api/v1/',h={origin:'http://127.0.0.1:8100','x-novel2voice-client':'web'};
  async function post(path,data,method='post'){const r=await page.request[method](url+path,{headers:h,data});assert.ok(r.ok(),await r.text());return r.json();}
  async function get(path){return (await page.request.get(url+path)).json();}
  async function waitJob(id,status){for(let i=0;i<300;i++){const job=await get('jobs/'+id);if(job.status===status)return job;await delay(100);}throw Error('job timeout '+status);}
  const book=await post('books',{name:'Xóa chương QA '+Date.now(),language:'vi',request_id:crypto.randomUUID()});
  await post('books/'+book.id+'/settings',{revision:0,values:{provider:'edge-tts',voice:'vi-VN-HoaiMyNeural',chunk_chars:100,concurrency:1}},'put');
  const ids=[];
  for(let i=1;i<=2;i++){
   const p=await post('books/'+book.id+'/text-imports',{number:i,title:'Chương thử '+i,content:'Nội dung kiểm tra xóa chương và bảo toàn dữ liệu. '.repeat(20)});
   const r=await post('books/'+book.id+'/imports/'+p.id+'/confirm',{items:[{item_id:p.items[0].id,number:i}]});ids.push(r.chapter_ids[0]);
  }
  const good=await post('job-plans',{book_id:book.id,chapter_ids:[ids[0]],action:'tts',request_id:crypto.randomUUID()});
  await post('job-plans/'+good.id+'/confirm',{});const finished=await waitJob(good.id,'completed'),artifact=finished.report.artifact_id;
  await page.goto('http://127.0.0.1:8100/#library/'+book.id);await page.locator('.chapter-link').first().click();
  await page.locator('#chapter-player').evaluate(el=>el.play());await page.waitForFunction(()=>document.querySelector('#chapter-player').currentTime>0.1);
  await page.locator('[aria-label="Chọn chương 1"]').check();await page.locator('#delete-detail-chapter').click();
  assert.equal(await page.locator('#cancel-delete-chapter').evaluate(el=>el===document.activeElement),true);
  await page.keyboard.press('Escape');assert.equal(await page.locator('#delete-chapter-confirm').count(),0);
  await page.getByRole('button',{name:'Xóa chương 1',exact:true}).click();await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:base+'/docs/tasks/v1.1/evidence/delete-chapter/mobile-confirm.png',fullPage:true});
  await page.locator('#confirm-delete-chapter').click();await page.locator('#chapter-delete-success').waitFor();
  assert.equal(await page.locator('#chapter-player').count(),0);assert.equal(await page.locator('[data-chapter-number="1"]').count(),0);
  assert.equal(await page.locator('#plan-action').count(),0);assert.equal((await page.request.get(url+'books/'+book.id+'/audio/'+artifact)).status(),404);
  assert.equal((await get('jobs/'+good.id)).status,'completed');
  await page.reload();await page.locator('[data-chapter-number="2"]').waitFor();assert.equal(await page.locator('[data-chapter-number="1"]').count(),0);
  const active=await post('job-plans',{book_id:book.id,chapter_ids:[ids[1]],action:'tts',request_id:crypto.randomUUID(),policies:{verification_delay_ms:1000}});
  await post('job-plans/'+active.id+'/confirm',{});await waitJob(active.id,'running');
  await page.getByRole('button',{name:'Xóa chương 2',exact:true}).click();await page.locator('#confirm-delete-chapter').click();
  await page.locator('#chapter-delete-error').filter({hasText:'công việc'}).waitFor();
  await page.screenshot({path:base+'/docs/tasks/v1.1/evidence/delete-chapter/job-conflict.png',fullPage:true});
  await post('jobs/'+active.id+'/stop',{});await waitJob(active.id,'stopped');await page.locator('#confirm-delete-chapter').click();
  await page.locator('#chapter-delete-success').waitFor();assert.equal((await get('books/'+book.id+'/chapters')).total,0);
  assert.equal((await get('overview?book_id='+book.id)).counts.chapters,0);
  // Remove the last row of page2: the table must fall back to a valid page.
  for(const numbers of [Array.from({length:20},(_,i)=>i+1),[21]]){
   const p=await post('books/'+book.id+'/imports',{files:numbers.map(n=>({name:n+'.txt',content_base64:Buffer.from('Pagination '+n).toString('base64')}))});
   await post('books/'+book.id+'/imports/'+p.id+'/confirm',{items:p.items.map(x=>({item_id:x.id,number:x.number}))});
  }
  await page.reload();await page.locator('#next-chapters').click();await page.locator('[data-chapter-number="21"]').waitFor();
  await page.getByRole('button',{name:'Xóa chương 21',exact:true}).click();await page.locator('#confirm-delete-chapter').click();
  await page.locator('[data-chapter-number="1"]').waitFor();assert.equal(await page.locator('.chapter-link').count(),20);
  assert.equal(await page.locator('#next-chapters').count(),0);assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  fs.writeFileSync(base+'/docs/tasks/v1.1/evidence/delete-chapter/browser-report.json',JSON.stringify({passed:true,book:book.id,delete_from_detail:true,cancel_escape_focus:true,playing_audio_stopped:true,selection_cleared:true,artifact404:true,history_kept:true,reload_deleted:true,running_job409:true,stop_then_delete:true,empty_counts:true,last_page_fallback:true,mobile_no_overflow:true,js_errors:errors},null,2));
  console.log('PASS chapter deletion:cancel/focus/audio/delete/reload/job conflict/stop/delete/pagination/mobile');
 }finally{
  if(child){const p=child;p.stdin.write('quit\n');await Promise.race([new Promise(r=>p.on('exit',r)),delay(7000).then(()=>p.kill('SIGTERM'))]);}
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1});
