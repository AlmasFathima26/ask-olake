import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")  # auto | openai | ollama | none
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY", "")
OPENAI_API_KEY = OPENROUTER_API_KEY
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "z-ai/glm-4.7-flash")
OPENROUTER_FALLBACK_MODELS = (
    "google/gemini-2.5-flash-lite",
    "deepseek/deepseek-v4.1-flash",
)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CORPUS_DIR = os.getenv("CORPUS_DIR", "corpus")
INDEX_PATH = os.getenv("INDEX_PATH", "index.npz")
TOP_K = int(os.getenv("TOP_K", "5"))
SIM_THRESHOLD = float(os.getenv("SIM_THRESHOLD", "0.35"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "6000"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "0"))
