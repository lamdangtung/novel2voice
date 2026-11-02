"""Non-secret runtime identity shared by API planning and the CLI TTS bridge."""
import hashlib
import json
from pathlib import Path
from src.doctor import ROOT, read_config


def tts_fingerprint(values, verification=False):
    env=read_config()
    keys={
        'edge-tts':['TTS_VOICE','TTS_RATE','TTS_VOLUME','TTS_PITCH'],
        'openai':['OPENAI_BASE_URL'],
        'piper':['PIPER_MODEL_PATH','PIPER_CONFIG_PATH','PIPER_NUM_WORKERS'],
        'vieneu':['VIENEU_MODE','VIENEU_VOICE','VIENEU_BACKBONE_REPO','VIENEU_BACKBONE_DEVICE','VIENEU_PRECISION','VIENEU_CODEC_REPO','VIENEU_CODEC_DEVICE','VIENEU_API_BASE','VIENEU_MODEL_NAME'],
    }[values['provider']]
    runtime={k:env.get(k) for k in keys}
    for key,default in [('PIPER_MODEL_PATH','models/piper/vi_VN-vais1000-medium.onnx'),('PIPER_CONFIG_PATH','models/piper/vi_VN-vais1000-medium.onnx.json')]:
        if values['provider']=='piper':
            path=Path(env.get(key) or default);path=path if path.is_absolute() else ROOT/path
            try:stat=path.stat();runtime[key+':file']=[stat.st_size,stat.st_mtime_ns]
            except OSError:runtime[key+':file']=None
    # URLs and other server details are only hashed, never returned in the plan.
    identity={'provider':values['provider'],'voice':values['voice'],'chunk_chars':values['chunk_chars'],'verification':verification,'runtime':runtime}
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
