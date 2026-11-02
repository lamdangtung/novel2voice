<script setup>
import { computed, ref, watch, nextTick } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
import ChapterAudio from './ChapterAudio.vue';
import JobPlanWizard from './JobPlanWizard.vue';
import AudioBulkDownload from './AudioBulkDownload.vue';
const props=defineProps({initialChapterId:{type:String,default:''},bookId:{type:String,required:true},refreshKey:{type:String,default:''}});
const removeTarget=ref(null),deletePending=ref(false),deleteError=ref(''),deleteMessage=ref('');
let deleteReturnTarget=null;
const rows=ref([]),total=ref(0),offset=ref(0),q=ref(''),status=ref('all'),pending=ref(false),error=ref('');
const selected=ref({}),showSelected=ref(false),start=ref(1),end=ref(10),detail=ref(null);
const selectedItems=computed(()=>Object.values(selected.value).sort((a,b)=>a.number-b.number));
const statusLabels={source_ready:'Có văn bản gốc',audio_ready:'Có audio đã xác minh',needs_refresh:'Audio cần kiểm tra lại'};
let loadGeneration=0;
async function load(reset=false){
  const generation=++loadGeneration;if(reset)offset.value=0;pending.value=true;error.value='';
  const fetchPage=()=>libraryRequest(`/${props.bookId}/chapters?q=${encodeURIComponent(q.value)}&status=${status.value}&offset=${offset.value}&limit=20`);
  try{let result=await fetchPage();if(generation!==loadGeneration)return;
    if(offset.value>0&&offset.value>=result.total){offset.value=Math.max(0,Math.floor((result.total-1)/20)*20);result=await fetchPage();if(generation!==loadGeneration)return;}
    rows.value=result.items;total.value=result.total;
  }catch(e){if(generation===loadGeneration)error.value=e.message;}finally{if(generation===loadGeneration)pending.value=false;}
}
watch(()=>props.bookId,()=>{selected.value={};offset.value=0;detail.value=null;removeTarget.value=null;deleteMessage.value='';deleteError.value='';},{immediate:true});
watch(()=>[props.bookId,props.refreshKey],()=>{detail.value=null;load();},{immediate:true});
function toggle(row,checked){if(checked)selected.value[row.id]={id:row.id,number:row.number,title:row.title};else delete selected.value[row.id];}
function selectPage(){for(const row of rows.value)toggle(row,true);}
async function range(){pending.value=true;error.value='';try{const result=await libraryRequest(`/${props.bookId}/chapter-selection?start=${start.value}&end=${end.value}`);for(const row of result.items)selected.value[row.id]=row;showSelected.value=true;}catch(e){error.value=e.message;}finally{pending.value=false;}}
let detailGeneration=0,returnTarget=null;
async function open(row){const generation=++detailGeneration;returnTarget=document.activeElement;pending.value=true;error.value='';detail.value=null;try{const result=await libraryRequest(`/${props.bookId}/chapters/${row.id}`);if(generation!==detailGeneration)return;detail.value=result;await nextTick();document.getElementById('close-chapter')?.focus();}catch(e){if(generation===detailGeneration)error.value=e.message;}finally{if(generation===detailGeneration)pending.value=false;}}
function close(){++detailGeneration;detail.value=null;returnTarget?.isConnected&&returnTarget.focus();}
async function beginDelete(row){deleteReturnTarget=document.activeElement;removeTarget.value={id:row.id,number:row.number,title:row.title,revision:row.revision};deleteError.value='';deleteMessage.value='';await nextTick();document.getElementById('cancel-delete-chapter')?.focus();}
function cancelDelete(){if(deletePending.value)return;removeTarget.value=null;deleteError.value='';deleteReturnTarget?.isConnected&&deleteReturnTarget.focus();}
async function confirmDelete(){
  if(!removeTarget.value||deletePending.value)return;
  deletePending.value=true;deleteError.value='';
  try{
    const target=removeTarget.value;
    const result=await libraryRequest(`/${props.bookId}/chapters/${target.id}`,{revision:target.revision},'DELETE');
    ++detailGeneration;if(detail.value?.id===target.id)detail.value=null;
    delete selected.value[target.id];removeTarget.value=null;deleteMessage.value=result.notice;
    await load();await nextTick();document.getElementById('chapters-title')?.focus();
  }catch(e){deleteError.value=e.message;}finally{deletePending.value=false;}
}

watch(()=>[props.bookId,props.initialChapterId],()=>{if(props.initialChapterId)open({id:props.initialChapterId});},{immediate:true});
const downloadUrl=id=>`${__API_ORIGIN__}/api/v1/books/${props.bookId}/artifacts/${id}/download`;
</script>
<template>
  <section class="mt-7 border-t border-line pt-5" aria-labelledby="chapters-title">
    <h3 id="chapters-title" tabindex="-1" class="text-sm font-semibold">Chương đã nhập · {{total}}</h3>
    <form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="load(true)">
      <label class="grid min-w-0 gap-2 text-xs" for="chapter-search">Tìm số hoặc tên chương<input id="chapter-search" v-model="q" maxlength="200" class="rounded border border-line bg-canvas p-2" /></label>
      <label class="grid gap-2 text-xs" for="chapter-status">Trạng thái<select id="chapter-status" v-model="status" class="rounded border border-line bg-canvas p-2"><option value="all">Tất cả</option><option v-for="(label,key) in statusLabels" :key="key" :value="key">{{label}}</option></select></label>
      <button id="filter-chapters" :disabled="pending" class="rounded border border-line px-3 py-2 text-sm">Áp dụng</button>
    </form>
    <p v-if="error" role="alert" class="mt-3 text-sm">{{error}} <button class="text-brand underline" @click="load()">Thử lại</button></p>
    <p v-if="pending" role="status" class="mt-3 text-xs text-muted">Đang tải…</p>
    <div class="mt-4 flex flex-wrap items-center gap-3 text-xs"><button id="select-page" :disabled="pending||!rows.length" class="text-brand underline" @click="selectPage">Chọn tất cả trên trang này ({{rows.length}})</button><button id="clear-selection" class="text-brand underline" @click="selected={}">Bỏ chọn tất cả</button><button id="show-selection" class="text-brand underline" @click="showSelected=!showSelected">Đã chọn {{selectedItems.length}} chương · xem ID</button></div>
    <form class="mt-4 flex flex-wrap items-end gap-2" @submit.prevent="range"><label class="grid gap-1 text-xs">Từ chương<input id="range-start" v-model.number="start" type="number" min="0" max="99999999" required class="w-24 rounded border border-line bg-canvas p-2" /></label><label class="grid gap-1 text-xs">Đến chương<input id="range-end" v-model.number="end" type="number" min="0" max="99999999" required class="w-24 rounded border border-line bg-canvas p-2" /></label><button id="select-range" :disabled="pending" class="rounded border border-line px-3 py-2 text-xs">Thêm khoảng vào lựa chọn</button><p class="w-full text-[11px] text-muted">Khoảng áp dụng toàn bộ truyện hiện tại, không theo bộ lọc tìm kiếm. Tối đa 5000 chương.</p></form>
    <AudioBulkDownload :book-id="bookId" :chapters="selectedItems" :refresh-key="`${props.refreshKey}:${deleteMessage}`" />
    <ul v-if="showSelected" id="selected-chapter-ids" class="mt-4 max-h-52 overflow-auto rounded bg-canvas p-3 text-xs"><li v-for="item in selectedItems" :key="item.id" class="py-1 break-all">{{item.number}} · {{item.title}} · {{item.id}}</li></ul>
    <p v-if="deleteMessage" id="chapter-delete-success" role="status" class="mt-4 rounded-lg border border-line bg-canvas p-3 text-xs text-brand">{{deleteMessage}}</p>
    <section v-if="removeTarget" id="delete-chapter-confirm" aria-labelledby="delete-chapter-title" class="mt-4 rounded-lg border border-danger bg-surface p-4" @keydown.esc.stop.prevent="cancelDelete"><h4 id="delete-chapter-title" class="text-sm font-semibold break-words">Xóa chương {{removeTarget.number}} · {{removeTarget.title}}?</h4><p class="mt-2 text-xs leading-5 text-muted">Chương, bản dịch và audio liên quan sẽ không còn truy cập trong truyện. File đã tạo, lịch sử công việc và bản ghép đã lưu vẫn được giữ trên máy. Chưa có nút khôi phục trong giao diện.</p><p v-if="deleteError" id="chapter-delete-error" role="alert" class="mt-3 text-xs text-danger">{{deleteError}}</p><div class="mt-4 flex flex-wrap gap-3"><button id="cancel-delete-chapter" :disabled="deletePending" class="rounded border border-line px-3 py-2 text-xs disabled:opacity-50" @click="cancelDelete">Hủy</button><button id="confirm-delete-chapter" :disabled="deletePending" class="rounded bg-danger px-3 py-2 text-xs text-canvas disabled:opacity-50" @click="confirmDelete">{{deletePending?'Đang xóa…':'Xác nhận xóa chương'}}</button><a v-if="deleteError" :href="`#jobs?book=${bookId}`" class="self-center text-xs text-brand underline">Xem công việc của truyện</a></div></section>
    <JobPlanWizard v-if="selectedItems.length" :book-id="bookId" :chapters="selectedItems" />
    <p v-if="!pending&&!rows.length" class="mt-5 text-sm text-muted">{{total===0&&!q&&status==='all'?'Chưa có chương. Xem trước TXT rồi xác nhận để nhập nội dung.':'Không có chương khớp bộ lọc.'}}</p>
    <ul class="mt-3 divide-y divide-line"><li v-for="row in rows" :key="row.id" :data-chapter-number="row.number" class="flex min-w-0 flex-wrap items-center gap-3 py-3"><input type="checkbox" :checked="!!selected[row.id]" :aria-label="`Chọn chương ${row.number}`" @change="toggle(row,$event.target.checked)" /><button :disabled="deletePending" class="chapter-link min-w-0 flex-1 text-left text-sm text-brand break-words" @click="open(row)">{{row.number}} · {{row.title}}</button><span class="max-w-28 text-right text-[11px] text-muted">{{statusLabels[row.status]}}</span><button :aria-label="`Xóa chương ${row.number}`" :disabled="pending||deletePending" class="shrink-0 rounded border border-line px-2 py-1 text-xs text-danger disabled:opacity-50" @click="beginDelete(row)">Xóa</button></li></ul>
    <div v-if="total>20" class="mt-4 flex justify-between text-xs"><button id="previous-chapters" :disabled="pending||offset===0" @click="offset-=20;load()">← Trước</button><span>{{offset+1}}–{{Math.min(offset+20,total)}} / {{total}}</span><button id="next-chapters" :disabled="pending||offset+20>=total" @click="offset+=20;load()">Sau →</button></div>
    <article v-if="detail" id="chapter-detail" @keydown.esc.stop.prevent="close" class="mt-6 rounded-lg border border-line p-4">
      <div class="flex items-start justify-between gap-3"><h4 class="text-sm font-semibold break-words">{{detail.number}} · {{detail.title}} · bản {{detail.revision}}</h4><button class="shrink-0 text-xs text-brand" id="close-chapter" @click="close">Đóng</button></div>
      <template v-for="(label,key) in {source:'Văn bản gốc',translation:'Bản dịch'}" :key="key"><h5 class="mt-5 text-sm font-medium">{{label}}</h5><template v-if="detail[key]"><p v-if="key==='translation'&&detail[key].metadata?.model" class="mt-2 text-[10px] text-muted break-all">Model {{detail[key].metadata.model}} · Prompt {{detail[key].metadata.prompt_hash}} · Glossary {{detail[key].metadata.glossary_hash}} {{detail[key].metadata.verification?'· BẢN DỊCH KIỂM THỬ':''}}</p><p class="mt-2 text-[11px] text-muted break-all">{{detail[key].bytes}} byte · SHA256 {{detail[key].sha256}}</p><a :id="`download-${key}`" :href="downloadUrl(detail[key].artifact_id)" class="mt-2 inline-block text-xs text-brand underline">Tải TXT {{label.toLowerCase()}}</a><pre class="mt-3 max-h-80 overflow-auto rounded bg-canvas p-3 text-xs leading-6 whitespace-pre-wrap break-words">{{detail[key].text}}</pre></template><p v-else class="mt-2 text-xs text-muted">{{key==='translation'?'Chưa có bản dịch đã xác minh cho nội dung hiện tại.':'Không tìm thấy văn bản gốc của phiên bản hiện tại.'}}</p></template>
      <ChapterAudio :book-id="bookId" :chapter-id="detail.id" />
      <button id="delete-detail-chapter" :disabled="pending||deletePending" class="mt-4 rounded border border-line px-3 py-2 text-xs text-danger disabled:opacity-50" @click="beginDelete(detail)">Xóa chương này</button>
    </article>
  </section>
</template>
