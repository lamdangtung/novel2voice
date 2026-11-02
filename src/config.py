import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Directories
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = OUTPUT_DIR / ".temp"
GLOSSARY_PATH = BASE_DIR / "glossary.csv"

# LLM / Translation Settings
TRANSLATION_PROVIDER = os.getenv("TRANSLATION_PROVIDER", "openai")
DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION = int(os.getenv("DEEPSEEK_MAX_CHUNKS_PER_CONVERSATION", "5"))
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", None)
TRANSLATION_MODEL = os.getenv("TRANSLATION_MODEL", "gpt-4o-mini")

# TTS Settings
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge-tts")  # "edge-tts" or "openai"
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-HoaiMyNeural")  # e.g. vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural
TTS_RATE = os.getenv("TTS_RATE", "+0%")  # e.g. +10%, -5%
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")
TTS_PITCH = os.getenv("TTS_PITCH", "+0Hz")

# Chunking & Processing Settings
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "2000"))
PAUSE_BETWEEN_CHUNKS_MS = int(os.getenv("PAUSE_BETWEEN_CHUNKS_MS", "300"))
TTS_CONCURRENCY = int(os.getenv("TTS_CONCURRENCY", "3"))
PIPER_MODEL_PATH  = os.getenv("PIPER_MODEL_PATH", "models/piper/vi_VN-vais1000-medium.onnx") 
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "models/piper/vi_VN-vais1000-medium.onnx.json") 
PIPER_NUM_WORKERS = int(os.getenv("PIPER_NUM_WORKERS", "4"))

# VieNeu-TTS Settings
VIENEU_MODE = os.getenv("VIENEU_MODE", "v3turbo")  # "v3turbo", "standard", "fast", "remote"
VIENEU_VOICE = os.getenv("VIENEU_VOICE", None)  # e.g. "Minh Quân", "Ngọc Lan"; None = default voice
VIENEU_BACKBONE_REPO = os.getenv("VIENEU_BACKBONE_REPO", None)  # e.g. "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf"
VIENEU_BACKBONE_DEVICE = os.getenv("VIENEU_BACKBONE_DEVICE", "cpu")  # "cpu", "cuda", "mps"
VIENEU_PRECISION = os.getenv("VIENEU_PRECISION", None)  # None or "int8" for faster CPU inference
VIENEU_CODEC_REPO = os.getenv("VIENEU_CODEC_REPO", None)
VIENEU_CODEC_DEVICE = os.getenv("VIENEU_CODEC_DEVICE", "cpu")  # "cpu" or "cuda"
VIENEU_API_BASE = os.getenv("VIENEU_API_BASE", None)  # Remote mode only
VIENEU_MODEL_NAME = os.getenv("VIENEU_MODEL_NAME", None)  # Remote mode only

# HuggingFace Token (for private/gated models)
HF_TOKEN = os.getenv("HF_TOKEN", None)
# Automatic glossary learning (per glossary CSV).
GLOSSARY_AUTO_UPDATE = os.getenv("GLOSSARY_AUTO_UPDATE", "true").lower() in ("1", "true", "yes")
GLOSSARY_MIN_OCCURRENCES = int(os.getenv("GLOSSARY_MIN_OCCURRENCES", "3"))
GLOSSARY_MIN_DISTINCT_CHUNKS = int(os.getenv("GLOSSARY_MIN_DISTINCT_CHUNKS", "2"))
GLOSSARY_MAX_AUTO_ENTRIES = int(os.getenv("GLOSSARY_MAX_AUTO_ENTRIES", "500"))
GLOSSARY_MAX_PROMPT_ENTRIES = int(os.getenv("GLOSSARY_MAX_PROMPT_ENTRIES", "100"))
GLOSSARY_MAX_CANDIDATES = int(os.getenv("GLOSSARY_MAX_CANDIDATES", "2000"))

# Grouping for the video stage; chapter TXT/audio files stay separate.
VIDEO_CHAPTERS_PER_VIDEO = int(os.getenv("VIDEO_CHAPTERS_PER_VIDEO", "1"))

VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))
VIDEO_FONT_PATH = os.getenv("VIDEO_FONT_PATH") or None

# YouTube publishing is opt-in; OAuth secrets are local and git-ignored.
YOUTUBE_CLIENT_SECRETS_FILE = Path(os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", str(BASE_DIR / ".secrets/youtube/client_secret.json")))
YOUTUBE_TOKEN_FILE = Path(os.getenv("YOUTUBE_TOKEN_FILE", str(BASE_DIR / ".secrets/youtube/token.json")))
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "")
YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "private")
YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "22")
YOUTUBE_STATE_DIR = Path(os.getenv("YOUTUBE_STATE_DIR", str(OUTPUT_DIR / ".state/youtube")))

# Separate episode metadata calls; translation flow stays unchanged.
METADATA_MAX_INPUT_CHARS = int(os.getenv("METADATA_MAX_INPUT_CHARS", "60000"))
