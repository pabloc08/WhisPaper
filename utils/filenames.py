# utils/filenames.py

import re
import unicodedata
import datetime
from pathlib import Path

from settings.constants import MAX_STEM_SAIDA


def _truncar_nome(nome: str, max_chars: int = 45) -> str:
    """
    Trunca um nome de arquivo longo inserindo '...' no meio do stem,
    preservando a extensão. Usado na lista de arquivos e nos logs do worker.

    Exemplo: 'MeuAudioMuitoLongo...Final.mp3' com max_chars=30
    """
    if len(nome) <= max_chars:
        return nome
    stem   = Path(nome).stem
    ext    = Path(nome).suffix
    metade = (max_chars - 3 - len(ext)) // 2
    return stem[:metade] + "..." + stem[-metade:] + ext


def gerar_nome_saida(
    nome_original: str,
    pasta_saida: Path,
    agora: datetime.datetime | None = None,
) -> Path:
    """
    Calcula o Path do .txt de saída direto na pasta do usuário.
    Verifica colisão para .txt, .srt e .vtt — o mesmo nome base nunca é
    reutilizado independentemente do formato de saída escolhido.

    """
    agora = agora or datetime.datetime.now()

    stem_raw   = Path(nome_original).stem
    # Normaliza unicode antes do regex: á→a, ç→c, ü→u, etc.
    stem_ascii = unicodedata.normalize("NFKD", stem_raw).encode("ascii", "ignore").decode()
    stem_limpo = re.sub(r"[^a-zA-Z0-9_-]", "", stem_ascii)
    stem_limpo = stem_limpo[:MAX_STEM_SAIDA] or "arquivo"

    sufixo_hr = agora.strftime("%Hh%M")

    contador = 1
    while True:
        nome_base = f"{stem_limpo}_{contador:02d}_{sufixo_hr}"
        txt_livre = not (pasta_saida / f"{nome_base}.txt").exists()
        srt_livre = not (pasta_saida / f"{nome_base}.srt").exists()
        vtt_livre = not (pasta_saida / f"{nome_base}.vtt").exists()
        if txt_livre and srt_livre and vtt_livre:
            return pasta_saida / f"{nome_base}.txt"
        contador += 1
