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