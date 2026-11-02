<script setup>
import { computed, ref, watch } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
import ChapterTable from './ChapterTable.vue';
const props=defineProps({initialChapterId:{type:String,default:''},bookId:{type:String,required:true},externalRefresh:{type:Number,default:0}});
const inputMode=ref('files'),textNumber=ref(1),textTitle=ref(''),textContent=ref('');
const textBytes=computed(()=>new TextEncoder().encode(textContent.value).length);
const inputLocked=computed(()=>pending.value||session.value?.status==='preview');
const files=ref([]), session=ref(null), chapters=ref([]), selected=ref([]), pending=ref(false), error=ref('');
const sources=ref([]), source=ref('input'), directory=ref(''), folders=ref([]), recursive=ref(false), folderError=ref(''),folderPending=ref(false);
const selectable=computed(()=>session.value?.items.filter(x=>x.status!=='invalid')||[]);
async function refresh(){try{chapters.value=(await libraryRequest(`/${props.bookId}/chapters`)).items;}catch(e){error.value=e.message;}}
watch(()=>props.bookId,()=>{session.value=null;files.value=[];selected.value=[];textNumber.value=1;textTitle.value='';textContent.value='';inputMode.value='files';refresh();loadSources();},{immediate:true});
function choose(event){files.value=[...event.target.files];error.value='';}
async function encode(file){const bytes=new Uint8Array(await file.arrayBuffer());let s='';for(const byte of bytes)s+=String.fromCharCode(byte);return btoa(s);}
async function preview(){
  error.value='';
  if(!files.value.length||files.value.length>20){error.value='Chọn từ 1 đến 20 file TXT.';return;}
  if(files.value.some(f=>f.size>256*1024)||files.value.reduce((a,f)=>a+f.size,0)>2*1024*1024){error.value='Giới hạn: 256 KiB/file, tổng 2 MiB mỗi phiên.';return;}
  pending.value=true;
  try{
    const inputs=[];for(const file of files.value)inputs.push({name:file.name,content_base64:await encode(file)});
    session.value=await libraryRequest(`/${props.bookId}/imports`,{files:inputs});
    selected.value=selectable.value.filter(x=>x.number!==null&&x.status==='ready').map(x=>x.id);
  }catch(e){error.value=e.message;}finally{pending.value=false;}
}
async function previewText(){
  error.value='';
  if(!textContent.value.trim()){error.value='Nhập hoặc dán nội dung chương.';return;}
  if(!Number.isInteger(textNumber.value)||textNumber.value<0||textNumber.value>99999999){error.value='Số chương phải là số nguyên từ 0 đến 99999999.';return;}
  if(textBytes.value>256*1024){error.value='Văn bản vượt giới hạn 256 KiB UTF-8 mỗi chương.';return;}
  pending.value=true;
  try{session.value=await libraryRequest(`/${props.bookId}/text-imports`,{number:textNumber.value,title:textTitle.value,content:textContent.value});selected.value=selectable.value.filter(x=>x.number!==null&&x.status==='ready').map(x=>x.id);}
  catch(e){error.value=e.message;}finally{pending.value=false;}
}

async function confirm(){
  if(!selected.value.length){error.value='Chọn ít nhất một file hợp lệ.';return;}
  pending.value=true;error.value='';
  try{
    const items=session.value.items.filter(x=>selected.value.includes(x.id)).map(x=>({item_id:x.id,number:x.number,action:x.update_confirm?'update':'import'}));
    if(items.some(x=>x.number===null||x.number===''||!Number.isInteger(Number(x.number))))throw new Error('Nhập số chương cho từng file đã chọn.');
    session.value=await libraryRequest(`/${props.bookId}/imports/${session.value.id}/confirm`,{items:items.map(x=>({...x,number:Number(x.number)}))});
    await refresh();
  }catch(e){error.value=e.message;}finally{pending.value=false;}
}
async function cancel(){pending.value=true;error.value='';try{session.value=await libraryRequest(`/${props.bookId}/imports/${session.value.id}/cancel`,{});}catch(e){error.value=e.message;}finally{pending.value=false;}}
async function loadSources(){
  try{sources.value=(await libraryRequest(`/${props.bookId}/import-sources`)).items;if(sources.value.length)source.value=sources.value[0].id;await browse('');}
  catch(e){folderError.value=e.message;}
}
async function browse(path=''){
  folderPending.value=true;folderError.value='';
  try{const value=await libraryRequest(`/${props.bookId}/folders?source=${encodeURIComponent(source.value)}&directory=${encodeURIComponent(path)}`);directory.value=value.directory;folders.value=value.folders;}
  catch(e){folderError.value=e.message;folders.value=[];}finally{folderPending.value=false;}
}
async function folderPreview(){
  pending.value=true;error.value='';
  try{session.value=await libraryRequest(`/${props.bookId}/folder-imports`,{source:source.value,directory:directory.value,recursive:recursive.value});selected.value=selectable.value.filter(x=>x.number!==null&&x.status==='ready').map(x=>x.id);}
  catch(e){error.value=e.message;}finally{pending.value=false;}
}
</script>
<template>
  <section class="rounded-xl border border-line bg-surface p-5 sm:p-7" aria-labelledby="import-title">
    <h2 id="import-title" class="font-semibold">Nhập nội dung chương</h2>
    <p class="mt-2 text-xs leading-5 text-muted">Chọn file, nhập văn bản trực tiếp hoặc chọn thư mục → xem trước → xác nhận. Nội dung chỉ được thêm vào truyện sau khi xác nhận.</p>
    <fieldset class="mt-4 flex flex-wrap gap-3 text-xs" :disabled="inputLocked"><legend class="mb-2 text-xs text-muted">Cách nhập</legend><label class="flex items-center gap-2 rounded-lg border border-line px-3 py-2"><input id="input-mode-files" v-model="inputMode" type="radio" value="files" name="chapter-input-mode" />File TXT</label><label class="flex items-center gap-2 rounded-lg border border-line px-3 py-2"><input id="input-mode-text" v-model="inputMode" type="radio" value="text" name="chapter-input-mode" />Nhập văn bản</label><label class="flex items-center gap-2 rounded-lg border border-line px-3 py-2"><input id="input-mode-folder" v-model="inputMode" type="radio" value="folder" name="chapter-input-mode" />Thư mục server</label></fieldset>
    <form v-show="inputMode==='text'" class="mt-5 space-y-4" @submit.prevent="previewText"><div class="flex flex-wrap gap-4"><label for="text-chapter-number" class="grid gap-2 text-xs">Số chương<input id="text-chapter-number" v-model.number="textNumber" type="number" required min="0" max="99999999" :disabled="inputLocked" class="w-28 rounded border border-line bg-canvas p-2" /></label><label for="text-chapter-title" class="grid min-w-0 flex-1 gap-2 text-xs">Tiêu đề (không bắt buộc)<input id="text-chapter-title" v-model="textTitle" maxlength="200" :disabled="inputLocked" class="min-w-0 rounded border border-line bg-canvas p-2" placeholder="Ví dụ: Cuộc gặp đầu tiên" /></label></div><label for="text-chapter-content" class="grid gap-2 text-sm">Nội dung chương<textarea id="text-chapter-content" v-model="textContent" required rows="10" :disabled="inputLocked" aria-describedby="text-content-help" class="w-full min-w-0 resize-y rounded-lg border border-line bg-canvas p-3 text-sm leading-6" placeholder="Nhập hoặc dán văn bản tại đây…"></textarea></label><p id="text-content-help" class="text-xs text-muted">{{textBytes.toLocaleString('vi-VN')}} / 262.144 byte UTF-8 · Mỗi lần nhập một chương. Giữ nguyên xuống dòng. Bản nháp ở trang này sẽ mất khi tải lại.</p><button id="preview-text" :disabled="inputLocked||!textContent.trim()||textBytes>262144" class="rounded-lg bg-brand px-4 py-2.5 text-sm text-brand-ink disabled:opacity-50">Xem trước văn bản</button></form>
    <p v-show="inputMode==='files'" class="mt-3 text-xs text-muted">TXT UTF-8, tối đa 20 file, 256 KiB/file, tổng 2 MiB. File gốc được giữ nguyên.</p>
    <div v-show="inputMode==='files'" class="mt-5 flex flex-wrap items-end gap-3"><label for="txt-files" class="grid min-w-0 gap-2 text-sm">File TXT<input id="txt-files" type="file" accept=".txt,text/plain" multiple :disabled="pending || session?.status === 'preview'" class="max-w-full rounded-lg border border-line p-2 text-xs" @change="choose" /></label><button id="preview-txt" :disabled="pending || !files.length || session?.status === 'preview'" class="rounded-lg bg-brand px-4 py-2.5 text-sm text-brand-ink disabled:opacity-50" @click="preview">Xem trước</button></div>
    <div v-show="inputMode==='folder'" class="mt-5 rounded-lg border border-line bg-canvas p-4">
      <h3 class="text-sm font-semibold">Hoặc chọn thư mục trên server</h3>
      <p class="mt-2 text-xs leading-5 text-muted">Đây là thư mục của server, khác với file chọn từ trình duyệt. Chỉ truy cập input/ và fixture được cho phép.</p>
      <label class="mt-3 grid gap-2 text-xs" for="import-source">Nguồn được phép<select id="import-source" v-model="source" :disabled="pending||folderPending||session?.status==='preview'" class="rounded border border-line bg-surface p-2" @change="directory='';browse('')"><option v-for="entry in sources" :key="entry.id" :value="entry.id">{{entry.label}}</option></select></label>
      <p class="mt-3 text-xs break-all">Thư mục: {{directory||'/'}}</p>
      <div class="mt-2 flex flex-wrap gap-2"><button v-if="directory" :disabled="pending||folderPending||session?.status==='preview'" class="rounded border border-line px-2 py-1 text-xs" @click="browse(directory.split('/').slice(0,-1).join('/'))">↑ Thư mục cha</button><button v-for="folder in folders" :key="folder" :disabled="pending||folderPending||session?.status==='preview'" class="folder-link rounded border border-line px-2 py-1 text-xs" @click="browse([directory,folder].filter(Boolean).join('/'))">{{folder}}/</button></div>
      <p v-if="folderError" role="alert" class="mt-3 text-xs">{{folderError}}</p>
      <label class="mt-4 flex items-center gap-2 text-xs"><input id="recursive-import" v-model="recursive" type="checkbox" :disabled="pending||folderPending||session?.status==='preview'" />Bao gồm thư mục con</label>
      <button id="preview-folder" :disabled="pending||folderPending||!!folderError||session?.status==='preview'" class="mt-4 rounded-lg border border-line bg-surface px-3 py-2 text-sm disabled:opacity-50" @click="folderPreview">Xem trước thư mục server</button>
    </div>
    <p v-if="pending" role="status" class="mt-4 text-sm text-muted">Đang xử lý…</p>
    <p v-if="error" id="import-error" role="alert" class="mt-4 text-sm">{{error}}</p>
    <div v-if="session" class="mt-5">
      <p id="import-status" class="text-sm font-medium">{{session.status==='confirmed' ? `Đã xác nhận ${session.chapter_ids.length} chương` : session.status==='cancelled' ? 'Đã hủy phiên; chưa tạo chương.' : 'Xem trước — chưa tạo chương'}}</p>
      <ul class="mt-3 divide-y divide-line">
        <li v-for="item in session.items" :key="item.id" class="py-4" :data-import-name="item.name">
          <div class="flex flex-wrap items-center gap-3">
            <input :id="`select-${item.id}`" v-model="selected" type="checkbox" :value="item.id" :disabled="pending||item.status==='invalid'||session.status!=='preview'" :aria-label="`Chọn ${item.name}`" />
            <label :for="`select-${item.id}`" class="min-w-0 flex-1 text-sm font-medium break-all">{{item.name}}</label>
            <label class="flex items-center gap-2 text-xs">Số chương<input v-model.number="item.number" type="number" min="0" max="99999999" :disabled="pending||item.status==='invalid'||session.status!=='preview'" class="w-24 rounded border border-line bg-canvas p-2" :aria-label="`Số chương ${item.name}`" /></label>
          </div>
          <label v-if="item.status==='changed'&&session.status==='preview'" class="mt-3 flex items-center gap-2 text-xs"><input v-model="item.update_confirm" type="checkbox" :disabled="pending" :aria-label="`Xác nhận cập nhật ${item.name}`" />Tôi xác nhận cập nhật nội dung chương này; giữ lại bản cũ.</label>
          <p class="mt-2 text-xs text-muted">{{item.message}} · {{item.size}} byte</p>
          <p v-if="item.excerpt" class="mt-2 line-clamp-3 text-xs leading-5 whitespace-pre-wrap text-muted">{{item.excerpt}}</p>
        </li>
      </ul>
      <ul v-if="session.outcomes?.length" id="import-outcomes" class="mt-4 space-y-2 text-xs"><li v-for="outcome in session.outcomes" :key="outcome.chapter_id">Chương {{outcome.number}}: {{outcome.action==='created'?'đã tạo':outcome.action==='updated'?'đã cập nhật; giữ bản cũ, audio/bản dịch cần kiểm tra lại':'bỏ qua vì nội dung giống hệt'}}</li></ul>
      <div v-if="session.status==='preview'" class="mt-4 flex flex-wrap gap-3"><button id="confirm-txt" :disabled="pending||!selected.length" class="rounded-lg bg-brand px-4 py-2.5 text-sm text-brand-ink disabled:opacity-50" @click="confirm">Xác nhận nhập {{selected.length}} {{inputMode==='text'?'chương':'file'}}</button><button id="cancel-txt" :disabled="pending" class="rounded-lg border border-line px-4 py-2.5 text-sm" @click="cancel">Hủy phiên nhập</button></div>
    </div>
    <ChapterTable :book-id="bookId" :initial-chapter-id="initialChapterId" :refresh-key="`${externalRefresh}:${session?.id||''}:${session?.status||''}`" />
  </section>
</template>
