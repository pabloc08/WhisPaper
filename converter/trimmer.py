# converter/trimmer.py
# Recorte de intervalo de tempo em arquivos de áudio via FFmpeg.


import subprocess
from pathlib import Path

from utils.platform       import kwargs_processo
from utils.ffmpeg_manager import obter_caminhos
from settings.paths       import TEMP_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hhmmss_para_segundos(valor: str) -> int:
    """Converte string HH:MM:SS (ou MM:SS ou SS) para segundos inteiros."""
    try:
        partes = list(map(int, valor.strip().split(":")))
        if len(partes) == 3:
            h, m, s = partes
        elif len(partes) == 2:
            h, m, s = 0, *partes
        elif len(partes) == 1:
            h, m, s = 0, 0, partes[0]
        else:
            return 0
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def recortar(audio_path: Path, tempo_inicio: str = None, tempo_fim: str = None) -> Path:
    """
    Recorta um trecho do áudio entre tempo_inicio e tempo_fim usando FFmpeg.

    Parâmetros:
        audio_path   : Path do arquivo WAV de entrada
        tempo_inicio : string HH:MM:SS (ou None para início do arquivo)
        tempo_fim    : string HH:MM:SS (ou None para fim do arquivo)

    Retorna:
        Path do arquivo recortado salvo em TEMP_DIR.

    Levanta:
        FFmpegNaoEncontrado se o FFmpeg não estiver disponível.
        ValueError          se tempo_fim <= tempo_inicio.
        RuntimeError        se o FFmpeg retornar erro.
        FileNotFoundError   se o arquivo recortado não for gerado.
    """
    from exceptions.conversion_errors import FFmpegNaoEncontrado

    try:
        ffmpeg, _ = obter_caminhos()
    except RuntimeError as e:
        raise FFmpegNaoEncontrado(str(e)) from e

    audio_path = Path(audio_path)

    inicio_seg = _hhmmss_para_segundos(tempo_inicio) if tempo_inicio else 0
    fim_seg    = _hhmmss_para_segundos(tempo_fim)    if tempo_fim    else 0

    if fim_seg and fim_seg <= inicio_seg:
        raise ValueError("O tempo final deve ser maior que o tempo inicial.")

    saida = TEMP_DIR / (audio_path.stem + "_recorte.wav")

    comando = [
        str(ffmpeg), "-y",
        "-i", str(audio_path),
        "-ss", str(inicio_seg),
    ]

    if fim_seg:
        comando += ["-t", str(fim_seg - inicio_seg)]

    comando += [
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        str(saida),
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        **kwargs_processo(),
    )

    if resultado.returncode != 0:
        erro = resultado.stderr.decode(errors="replace")
        raise RuntimeError(f"Erro no recorte de áudio:\n{erro}")

    if not saida.exists():
        raise FileNotFoundError(f"Arquivo recortado não foi gerado: {saida}")

    return saida
