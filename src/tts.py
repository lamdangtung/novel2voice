"""TTS provider factory and backward-compatible public imports."""
from typing import Optional

from src import config
from src.tts_providers.base import BaseTTSProvider
from src.tts_providers.edge import EdgeTTSProvider
from src.tts_providers.openai import OpenAITTSProvider
from src.tts_providers.local import LocalTTSProvider
from src.tts_providers.vieneu import VieNeuTTSProvider

__all__ = [
    "BaseTTSProvider", "EdgeTTSProvider", "OpenAITTSProvider",
    "LocalTTSProvider", "VieNeuTTSProvider", "get_tts_provider",
]


def get_tts_provider(
    provider_name: Optional[str] = None,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    piper_model_path: Optional[str] = None,
    piper_config_path: Optional[str] = None,
    piper_num_workers: Optional[int] = None,
    vieneu_mode: Optional[str] = None,
    vieneu_backbone_repo: Optional[str] = None,
    vieneu_backbone_device: Optional[str] = None,
    vieneu_precision: Optional[str] = None,
) -> BaseTTSProvider:
    """Factory hàm khởi tạo TTS provider theo cấu hình."""
    provider_name = (provider_name or config.TTS_PROVIDER).lower()

    if provider_name == "openai":
        return OpenAITTSProvider(
            api_key=api_key,
            base_url=base_url,
            voice=voice or "alloy"
        )
    elif provider_name in ("edge-tts", "edge_tts", "edge"):
        return EdgeTTSProvider(
            voice=voice or config.TTS_VOICE,
            rate=rate or config.TTS_RATE
        )
    elif provider_name in ("local", "piper"):
        return LocalTTSProvider(
            model_path=piper_model_path or config.PIPER_MODEL_PATH,
            config_path=piper_config_path or config.PIPER_CONFIG_PATH,
            num_workers=piper_num_workers or config.PIPER_NUM_WORKERS,
        )
    elif provider_name in ("vieneu", "vieneu-tts"):
        return VieNeuTTSProvider(
            mode=vieneu_mode,
            voice=voice,
            backbone_repo=vieneu_backbone_repo,
            backbone_device=vieneu_backbone_device,
            precision=vieneu_precision,
        )
    else:
        raise ValueError(
            f"Không hỗ trợ TTS provider: {provider_name}. "
            f"Hãy chọn 'edge-tts', 'openai', 'local', hoặc 'vieneu'."
        )
