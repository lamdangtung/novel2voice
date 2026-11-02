<script setup>
import { computed, ref, watch } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
import ConnectionSettings from './ConnectionSettings.vue';
const props=defineProps({bookId:{type:String,default:''}});
const capabilities=ref([]);
const record=ref(null),values=ref({}),overrides=ref({}),pending=ref(false),error=ref(''),message=ref('');
const fields=[{key:'provider',label:'Provider',type:'provider'},{key:'voice',label:'Voice ID / tên giọng',type:'text'},{key:'chunk_chars',label:'Ký tự mỗi đoạn',type:'number',min:100,max:10000},{key:'concurrency',label:'Số đoạn đồng thời',type:'number',min:1,max:16},{key:'retries',label:'Số lần thử lại',type:'number',min:0,max:5},{key:'cleanup',label:'Dọn audio đoạn sau khi ghép',type:'boolean'},{key:'translation_model',label:'Model dịch',type:'text'}];
const visible=computed(()=>fields.filter(f=>f.key!=='voice'||capabilities.value.find(p=>p.id===values.value.provider)?.voice!==false));
const path=computed(()=>props.bookId?`/${props.bookId}/settings`:'/workspace/settings');
async function load(){pending.value=true;error.value='';message.value='';try{const [saved,caps]=await Promise.all([libraryRequest(path.value),libraryRequest('/workspace/capabilities')]);capabilities.value=caps.providers;record.value=saved;values.value={...record.value.effective};overrides.value=Object.fromEntries(Object.keys(record.value.values).map(k=>[k,true]));}catch(e){error.value=e.message;}finally{pending.value=false;}}
watch(()=>props.bookId,load,{immediate:true});
watch(()=>values.value.provider,p=>{if(p==='piper'){values.value.voice='';overrides.value.voice=false;}});
async function save(){pending.value=true;error.value='';message.value='';try{const data=props.bookId?Object.fromEntries(Object.entries(values.value).filter(([k])=>overrides.value[k])):{...values.value};record.value=await libraryRequest(path.value,{revision:record.value.revision,values:data},'PUT');values.value={...record.value.effective};message.value='Đã lưu cấu hình.';}catch(e){error.value=e.message;}finally{pending.value=false;}}
</script>
<template>
  <section class="mt-5 rounded-xl border border-line bg-surface p-5 sm:p-7" aria-labelledby="config-title">
    <h2 id="config-title" class="font-semibold">{{bookId?'Cấu hình riêng cho truyện':'Cấu hình mặc định workspace'}}</h2>
    <p class="mt-2 text-xs leading-5 text-muted">{{bookId?'Tick từng trường muốn đặt riêng. Trường không tick sẽ kế thừa mặc định workspace.':'Áp dụng cho truyện chưa có giá trị riêng. Không ghi đè cấu hình đã đặt riêng cho truyện.'}} API key và đường dẫn model cấu hình ở server.</p>
    <p v-if="error" role="alert" class="mt-4 text-sm">{{error}}</p><p v-if="message" role="status" class="mt-4 text-sm text-brand">{{message}}</p>
    <form v-if="record" class="mt-5 space-y-4" @submit.prevent="save">
      <div v-for="field in visible" :key="field.key" class="grid items-center gap-2 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div><label :for="`config-${field.key}`" class="text-sm">{{field.label}}</label><p class="mt-1 text-[10px] text-muted">Nguồn: {{record.sources[field.key]}}</p></div>
        <div class="flex min-w-0 flex-wrap items-center gap-3">
          <label v-if="bookId" class="flex items-center gap-1 text-xs"><input :id="`override-${field.key}`" v-model="overrides[field.key]" type="checkbox" :disabled="pending" />Đặt riêng</label>
          <select v-if="field.type==='provider'" :id="`config-${field.key}`" v-model="values[field.key]" :disabled="pending||(!!bookId&&!overrides[field.key])" class="min-w-0 rounded border border-line bg-canvas p-2 text-sm"><option v-for="provider in capabilities" :key="provider.id" :value="provider.id">{{provider.id}}</option></select>
          <input v-else-if="field.type==='boolean'" :id="`config-${field.key}`" v-model="values[field.key]" type="checkbox" :disabled="pending||(!!bookId&&!overrides[field.key])" />
          <input v-else-if="field.type==='number'" :id="`config-${field.key}`" v-model.number="values[field.key]" type="number" :min="field.min" :max="field.max" required :disabled="pending||(!!bookId&&!overrides[field.key])" class="w-28 rounded border border-line bg-canvas p-2 text-sm" />
          <input v-else :id="`config-${field.key}`" v-model="values[field.key]" type="text" maxlength="100" :disabled="pending||(!!bookId&&!overrides[field.key])" class="min-w-0 flex-1 rounded border border-line bg-canvas p-2 text-sm" />
        </div>
      </div>
      <p v-if="values.provider==='piper'" class="text-xs text-muted">Piper dùng model/JSON tại server; không hỗ trợ chọn Voice ID.</p>
      <div class="flex flex-wrap gap-3"><button id="save-config" :disabled="pending" class="rounded-lg bg-brand px-4 py-2.5 text-sm text-brand-ink disabled:opacity-50">{{pending?'Đang xử lý…':'Lưu cấu hình'}}</button><button type="button" :disabled="pending" class="rounded-lg border border-line px-3 py-2 text-sm" @click="load">Tải lại cấu hình</button></div>
    </form>
    <ConnectionSettings :book-id="bookId" />
  </section>
</template>
