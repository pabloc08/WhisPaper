# transcriber/result.py
# Resultado padronizado de uma transcrição.
# Retornado pelo pipeline — sem retornos implícitos.

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptionResult:
    arquivo_original: Path
    arquivo_txt:      Path
    engine_id:        str
    model_id:         str
    language:         str
    duracao_s:        float  # tempo total de processamento em segundos
