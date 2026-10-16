"""Local embedding providers.

- `hash` (default): deterministic feature-hashing embedder over word unigrams/bigrams and
  character trigrams. Fully local, zero downloads, reproducible in tests. It captures *lexical*
  similarity only — it is not a semantic model, and the docs say so.
- `fastembed`: optional local ONNX sentence-embedding model (multilingual MiniLM, 384-d).
  Falls back to `hash` if the package or model is unavailable.
"""
import hashlib
import logging
import math
import re
from functools import lru_cache

from app.config import get_settings
from app.models import EMBEDDING_DIM

log = logging.getLogger(__name__)
_WORD = re.compile(r"[\w֐-׿]+", re.UNICODE)


class HashEmbedder:
    name = "hash-v1"

    def _features(self, text: str):
        words = [w.lower() for w in _WORD.findall(text)]
        for w in words:
            yield "w:" + w, 1.0
            if len(w) > 3:
                for i in range(len(w) - 2):
                    yield "c:" + w[i:i + 3], 0.3
        for a, b in zip(words, words[1:]):
            yield f"b:{a}_{b}", 0.6

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            vec = [0.0] * EMBEDDING_DIM
            for feat, weight in self._features(t):
                h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % EMBEDDING_DIM
                sign = 1.0 if h[4] & 1 else -1.0
                vec[idx] += sign * weight
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedEmbedder:
    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding  # optional dependency

        self._model = TextEmbedding(model_name=model_name)
        self.name = f"fastembed:{model_name}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


@lru_cache
def get_embedder():
    s = get_settings()
    if s.embedding_provider == "fastembed":
        try:
            emb = FastEmbedEmbedder(s.fastembed_model)
            if len(emb.embed(["probe"])[0]) == EMBEDDING_DIM:
                return emb
            log.warning("fastembed model dimension mismatch; falling back to hash embedder")
        except Exception as exc:  # package missing, model download blocked, etc.
            log.warning("fastembed unavailable (%s); falling back to hash embedder", type(exc).__name__)
    return HashEmbedder()
