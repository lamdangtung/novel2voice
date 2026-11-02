<script setup>
import { ref,watch } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
const props=defineProps({bookId:{type:String,default:''}}),record=ref(null),error=ref(''),pending=ref(false);
async function load(){pending.value=true;error.value='';try{record.value=await libraryRequest(props.bookId?`/${props.bookId}/connections`:'/workspace/connections');}catch(e){error.value=e.message;}finally{pending.value=false;}}
watch(()=>props.bookId,load,{immediate:true});
</script>
<template>
  <section class="mt-6 border-t border-line pt-5" aria-labelledby="connections-title"><div class="flex items-start justify-between gap-3"><h3 id="connections-title" class="text-sm font-semibold">Kết nối và key tại server</h3><button :disabled="pending" class="text-xs text-brand underline" @click="load">Kiểm tra lại</button></div><p v-if="error" role="alert" class="mt-3 text-xs">{{error}}</p><div v-if="record" id="connection-settings" class="mt-3 space-y-4"><p class="text-xs leading-5 text-muted">{{record.notice}}</p><div v-for="(label,key) in {tts:'Giọng đọc',translation:'Dịch thuật'}" :key="key" class="rounded-lg bg-canvas p-3"><h4 class="text-xs font-semibold">{{label}} · {{record[key].provider}}</h4><p class="mt-2 text-xs break-all">Model: {{record[key].model}}</p><p v-if="record[key].endpoint" class="mt-2 text-xs break-all">Endpoint: {{record[key].endpoint.display||'Cấu hình endpoint không hợp lệ'}}</p><p v-if="record[key].key_required" :id="`key-status-${key}`" class="mt-2 text-xs">OPENAI_API_KEY: {{record[key].key_configured?'đã cấu hình, chưa xác minh':'chưa cấu hình — thao tác dịch vụ sẽ bị chặn'}}</p><p v-if="record[key].hf_token_configured!==undefined&&record[key].hf_token_configured!==null" class="mt-2 text-xs">HF_TOKEN: {{record[key].hf_token_configured?'đã cấu hình':'chưa cấu hình (tùy chọn)'}}</p></div><p class="text-xs leading-5 text-muted">{{record.how_to}}</p></div></section>
</template>
