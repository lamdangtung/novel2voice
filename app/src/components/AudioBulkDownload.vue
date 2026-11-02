<script setup>
import {ref,watch,onBeforeUnmount} from 'vue';
import {libraryRequest} from '../lib/library-client.js';
const props=defineProps({bookId:{type:String,required:true},chapters:{type:Array,default:()=>[]},refreshKey:{type:String,default:''}});
const mode=ref('selected'),start=ref(1),end=ref(10),plan=ref(null),prepared=ref(null),pending=ref(false),error=ref(''),stage=ref('');
const apiOrigin=__API_ORIGIN__;
const bytes=n=>{const units=['B','KiB','MiB','GiB'];let unit=0;while(n>=1024&&unit<3){n/=1024;unit++;}return new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(n)+' '+units[unit];};
let generation=0;
onBeforeUnmount(()=>{++generation});
function reset(){++generation;plan.value=null;prepared.value=null;error.value='';}
watch([mode,start,end,()=>props.bookId,()=>props.chapters.map(c=>c.id).join(','),()=>props.refreshKey],reset);
async function preview(){
 const current=++generation;error.value='';prepared.value=null;plan.value=null;
 if(mode.value==='selected'&&(!props.chapters.length||props.chapters.length>500)){error.value='Chọn từ 1 đến 500 chương để tải.';return;}
 if(mode.value==='range'&&(!Number.isInteger(start.value)||!Number.isInteger(end.value)||start.value<0||end.value>99999999||start.value>end.value||end.value-start.value+1>500)){error.value='Nhập khoảng hợp lệ, tối đa 500 số chương mỗi lần.';return;}
 pending.value=true;stage.value='Đang kiểm tra audio…';
 try{const body=mode.value==='selected'?{mode:'selected',chapter_ids:props.chapters.map(c=>c.id)}:{mode:'range',start:start.value,end:end.value};const result=await libraryRequest(`/${props.bookId}/audio-downloads/preview`,body,'POST','books',{timeoutMs:120000});if(current===generation)plan.value=result;}
 catch(e){if(current===generation)error.value=e.message;}finally{pending.value=false;stage.value='';}
}
async function download(){
 if(!plan.value?.ready_count)return;
 const current=generation;pending.value=true;stage.value='Đang chuẩn bị ZIP…';error.value='';
 try{
  const result=await libraryRequest(`/${props.bookId}/audio-downloads/${plan.value.id}/prepare`,{},'POST','books',{timeoutMs:300000});if(current!==generation)return;prepared.value=result;
  const link=document.createElement('a');link.href=apiOrigin+prepared.value.download_path;document.body.append(link);link.click();link.remove();
 }catch(e){if(current===generation){error.value=e.message;prepared.value=null;}}finally{pending.value=false;stage.value='';}
}
</script>
<template>
<section class="mt-5 rounded-xl border border-line bg-canvas p-4" aria-labelledby="bulk-audio-title">
 <h4 id="bulk-audio-title" class="text-sm font-semibold">Tải audio hàng loạt</h4>
 <p class="mt-2 text-xs leading-5 text-muted">Tải từng MP3 trong một file ZIP, theo số chương. Dùng bản audio đang chọn và còn hợp lệ; không tạo lại giọng hoặc ghép audio. Tối đa 500 chương / 2 GiB mỗi lần.</p>
 <fieldset :disabled="pending" class="mt-4 flex flex-wrap gap-4 text-xs"><legend class="mb-2 text-xs text-muted">Phạm vi tải</legend><label class="flex items-center gap-2"><input id="audio-download-selected" v-model="mode" type="radio" value="selected" />Chương đang chọn ({{chapters.length}})</label><label class="flex items-center gap-2"><input id="audio-download-range" v-model="mode" type="radio" value="range" />Khoảng chương</label></fieldset>
 <form class="mt-4 space-y-3" @submit.prevent="preview"><div v-if="mode==='range'" class="flex flex-wrap gap-3"><label for="audio-download-start" class="grid gap-2 text-xs">Từ chương<input id="audio-download-start" v-model.number="start" :disabled="pending" type="number" min="0" max="99999999" required class="w-28 rounded border border-line bg-surface p-2" /></label><label for="audio-download-end" class="grid gap-2 text-xs">Đến chương<input id="audio-download-end" v-model.number="end" :disabled="pending" type="number" min="0" max="99999999" required class="w-28 rounded border border-line bg-surface p-2" /></label></div><p class="text-xs text-muted">{{mode==='range'?'Khoảng áp dụng toàn truyện, không theo bộ lọc hay checkbox đang chọn.':'Bao gồm lựa chọn ở các trang, không chỉ trang đang hiển thị.'}}</p><button id="preview-audio-download" :disabled="pending||(mode==='selected'&&!chapters.length)" class="rounded border border-line bg-surface px-3 py-2 text-xs disabled:opacity-50">Kiểm tra audio trước khi tải</button></form>
 <p v-if="pending" role="status" class="mt-3 text-xs text-muted">{{stage}}</p><p v-if="error" id="audio-download-error" role="alert" class="mt-3 text-xs text-danger">{{error}}</p>
 <div v-if="plan" id="audio-download-preview" class="mt-4 space-y-3"><p class="text-xs leading-5">{{plan.ready_count}} MP3 tải được · {{bytes(plan.bytes)}} · {{plan.skipped_count}} chương bỏ qua.</p><p class="text-xs leading-5 text-muted">{{plan.notice}}</p><details class="text-xs"><summary class="cursor-pointer text-brand">Xem danh sách {{plan.items.length}} chương</summary><ul class="mt-2 max-h-64 space-y-2 overflow-auto"><li v-for="item in plan.items" :key="item.number" class="break-words">{{item.number}} · {{item.title||'Chương không tồn tại'}} · {{item.status==='ready'?'Sẽ tải':'Bỏ qua'}} — {{item.reason}}</li></ul></details><p v-if="!plan.ready_count" class="text-xs text-muted">Không có audio hợp lệ trong phạm vi này. Chọn phạm vi khác hoặc tạo/chọn lại audio.</p><button id="download-audio-zip" :disabled="pending||!plan.ready_count" class="rounded-lg bg-brand px-4 py-2 text-xs text-brand-ink disabled:opacity-50" @click="download">Tải {{plan.ready_count}} MP3 (ZIP)</button><div v-if="prepared" id="audio-download-ready" role="status" class="text-xs leading-5"><p>ZIP đã sẵn sàng. Trình duyệt sẽ tải file vào thư mục tải xuống.</p><a id="audio-zip-link" :href="apiOrigin+prepared.download_path" class="mt-2 inline-block text-brand underline">Tải lại {{prepared.filename}}</a><p class="mt-1 text-muted">Liên kết có hiệu lực 30 phút kể từ lúc kiểm tra audio.</p></div></div>
</section>
</template>
