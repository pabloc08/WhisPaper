# transcriber/request.py
# Contrato explícito de uma requisição de transcrição.
# A GUI monta este objeto e passa ao worker — sem parâmetros soltos.

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptionRequest:
    arquivo:       Path
    engine_id:     str
    model_id:      str
    language:      str        # código ISO ou "auto"
    task:          str        # "transcribe" ou "translate"
    pasta_saida:   Path
    usar_tempo:    bool = False
    inicio:        str | None = None
    fim:           str | None = None
    formato_saida: str = "ambos"   # "txt", "srt", "vtt", "srt_vtt", "todos" ou "ambos"
    vad_filter:    bool = False
    usar_gpu:      bool = False
