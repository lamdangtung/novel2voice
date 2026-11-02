<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { libraryRequest } from '../lib/library-client.js';
const props=defineProps({bookId:{type:String,required:true},chapterId:{type:String,required:true}});
const items=ref([]),error=ref(''),pending=ref(false),audio=ref(null);
const selected=computed(()=>items.value.find(x=>x.selected));
const mediaUrl=computed(()=>selected.value?`${__API_ORIGIN__}/api/v1/books/${props.bookId}/audio/${selected.value.id}`:'');
function stop(){if(audio.value){audio.value.pause();audio.value.removeAttribute('src');audio.value.load();}}
async function load(){stop();items.value=[];error.value='';pending.value=true;try{items.value=(await libraryRequest(`/${props.bookId}/chapters/${props.chapterId}/audio`)).items;}catch(e){error.value=e.message;}finally{pending.value=false;}}
watch(()=>[props.bookId,props.chapterId],load,{immediate:true});onBeforeUnmount(stop);
async function choose(event){pending.value=true;error.value='';stop();try{items.value=(await libraryRequest(`/${props.bookId}/chapters/${props.chapterId}/audio-selection`,{artifact_id:event.target.value})).items;}catch(e){items.value=[];error.value=e.message;}finally{pending.value=false;}}
</script>
<template>
  <section class="mt-5 border-t border-line pt-4" aria-labelledby="chapter-audio-title"><h5 id="chapter-audio-title" class="text-sm font-medium">Audio của chương</h5><p v-if="!pending&&!items.length" class="mt-2 text-xs text-muted">Chưa có audio. Bạn có thể nhập MP3 đã có.</p><p v-if="error" role="alert" id="audio-error" class="mt-2 text-xs">{{error}} <button class="text-brand underline" @click="load">Kiểm tra lại</button></p>
    <label v-if="items.length" class="mt-3 grid gap-2 text-xs">Bản audio đang chọn<select id="selected-audio" :value="selected?.id||''" :disabled="pending" class="rounded border border-line bg-canvas p-2" @change="choose"><option value="" disabled>Chọn audio</option><option v-for="item in items" :key="item.id" :value="item.id">{{item.method==='imported'?'Nhập trước':'Tạo từ job'}} · {{item.id.slice(0,8)}} · {{item.stale?'cần kiểm tra lại':'file hợp lệ'}}</option></select></label>
    <div v-if="selected" class="mt-3"><p class="text-xs leading-5 text-muted">{{selected.method==='imported'?'Audio nhập trước chưa đảm bảo đọc khớp từng từ với TXT.':selected.verification?'Audio kiểm thử (âm tone), không phải giọng đọc.':'Audio tạo từ job đã xác minh file; chất lượng giọng chưa được xác nhận.'}} {{selected.stale?'Nội dung nguồn đã đổi hoặc bản audio cần kiểm tra lại.':''}}</p><audio v-if="!error" :key="mediaUrl" ref="audio" id="chapter-player" :src="mediaUrl" controls preload="metadata" class="mt-3 max-w-full" @error="error='Không phát được audio. File có thể mất hoặc checksum thay đổi.'"></audio><details v-if="selected.translation_sha256" class="mt-2 text-[10px] text-muted"><summary class="cursor-pointer">Bản dịch dùng để tạo audio</summary><p class="mt-2 break-all">SHA256 {{selected.translation_sha256}}</p></details><p class="mt-2 text-[10px] text-muted break-all">{{selected.duration?.toFixed(2)}} giây · SHA256 {{selected.sha256}}</p><a :href="`${mediaUrl}?download=true`" id="download-audio" class="mt-2 inline-block text-xs text-brand underline">Tải MP3</a></div>
  </section>
</template>
