<script setup>
import { ref,watch } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
const props=defineProps({bookId:{type:String,required:true}});
const record=ref(null),file=ref(null),pending=ref(false),error=ref('');
async function load(){pending.value=true;error.value='';try{record.value=await libraryRequest(`/${props.bookId}/glossary`);}catch(e){error.value=e.message;}finally{pending.value=false;}}
watch(()=>props.bookId,load,{immediate:true});
async function save(){if(!file.value)return;pending.value=true;error.value='';try{if(file.value.size>256*1024)throw new Error('Glossary tối đa 256 KiB.');const bytes=new Uint8Array(await file.value.arrayBuffer());let content='';for(const b of bytes)content+=String.fromCharCode(b);record.value=await libraryRequest(`/${props.bookId}/glossary`,{name:file.value.name,content_base64:btoa(content),revision:record.value.revision},'PUT');}catch(e){error.value=e.message;}finally{pending.value=false;}}
</script>
<template>
  <section class="mt-5 rounded-xl border border-line bg-surface p-5" aria-labelledby="glossary-title">
    <h2 id="glossary-title" class="text-sm font-semibold">Thuật ngữ riêng cho truyện</h2>
    <p class="mt-2 text-xs leading-5 text-muted">CSV UTF-8 với hai cột en,vi. Tối đa 256 KiB/2000 thuật ngữ; bản lỗi không thay bản đang dùng. Bước dịch sẽ sử dụng glossary này khi được triển khai.</p>
    <p v-if="error" id="glossary-error" role="alert" class="mt-3 text-sm">{{error}}</p>
    <div v-if="record" class="mt-4">
      <p id="glossary-status" class="text-xs">Nguồn: {{record.source==='book'?'riêng cho truyện':record.source==='server'?'mặc định server':'chưa có'}} · Phiên bản {{record.revision}} · {{record.entries.length}} thuật ngữ</p><p v-if="record.notice" class="mt-2 text-xs text-muted">{{record.notice}}</p><p v-if="record.sha256" class="mt-2 text-[10px] text-muted break-all">SHA256 {{record.sha256}}</p>
      <form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="save"><label for="glossary-file" class="grid min-w-0 gap-2 text-xs">File CSV<input id="glossary-file" type="file" accept=".csv,text/csv" :disabled="pending" class="max-w-full rounded border border-line p-2" @change="file=$event.target.files[0]" /></label><button id="save-glossary" :disabled="pending||!file" class="rounded-lg bg-brand px-4 py-2.5 text-sm text-brand-ink disabled:opacity-50">{{pending?'Đang xử lý…':'Lưu phiên bản glossary'}}</button><button type="button" :disabled="pending" class="text-xs text-brand underline" @click="load">Tải lại</button></form>
      <ul class="mt-4 max-h-64 divide-y divide-line overflow-auto text-xs"><li v-for="entry in record.entries" :key="entry.en" class="py-2 break-words">{{entry.en}} → {{entry.vi}}</li></ul>
      <details v-if="record.versions.length" class="mt-4"><summary class="cursor-pointer text-xs text-brand">{{record.versions.length}} phiên bản đã lưu</summary><ul class="mt-2 space-y-2 text-[10px] text-muted"><li v-for="version in record.versions" :key="version.id" class="break-all">Bản {{version.revision}} · {{version.filename}} · {{version.sha256}}</li></ul></details>
    </div>
  </section>
</template>
