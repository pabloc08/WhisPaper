# converter/converter.py
# Converte arquivos de mídia para WAV 16kHz mono PCM usando FFmpeg.


import subprocess
import time as _time
from pathlib import Path
from random  import randint

from utils.platform      import kwargs_processo
from utils.logger        import log_ffmpeg_inicio, log_ffmpeg_fim, log_ffmpeg_erro
from utils.ffmpeg_manager import obter_caminhos
from settings.paths      import TEMP_DIR


# ---------------------------------------------------------------------------
# Formatos suportados
# ---------------------------------------------------------------------------

FORMATOS_SUPORTADOS = {
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".aiff", ".opus", ".amr",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"
}


# ---------------------------------------------------------------------------
# Verificação
# ---------------------------------------------------------------------------

def precisa_converter(caminho: str, forcar: bool = False) -> bool:
    """
    Retorna True se o arquivo precisa ser convertido para WAV 16kHz mono PCM.
    Se forcar=False e o arquivo já for .wav, retorna False sem inspecionar.
    """
    caminho = str(caminho)
    if not caminho.lower().endswith(".wav"):
        return True
    if not forcar:
        return False

    try:
        _, ffprobe = obter_caminhos()
        resultado = subprocess.run(
            [
                str(ffprobe),
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,channels,codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                caminho,
            ],
            capture_output=True,
            text=True,
            **kwargs_processo(),
        )
        if resultado.returncode != 0:
            return True

        linhas = resultado.stdout.strip().splitlines()
        if len(linhas) < 3:
            return True

        codec       = linhas[0].strip()
        sample_rate = int(linhas[1])
        channels    = int(linhas[2])

        return sample_rate != 16000 or channels != 1 or codec != "pcm_s16le"

    except Exception:
        return True


# ---------------------------------------------------------------------------
# Conversão
# ---------------------------------------------------------------------------

def converter_para_wav(
    caminho_original: str,
    atualizar_status=None,
    aprimorada: bool = True,
) -> str | None:
    """
    Converte um arquivo de mídia para WAV usando FFmpeg.

    Parâmetros:
        caminho_original  : caminho do arquivo de origem
        atualizar_status  : callback(str) opcional para exibir progresso na UI
        aprimorada        : se True, converte para 16kHz mono PCM (ideal para Whisper)
                            se False, converte para 44100Hz estéreo (genérico)

    Retorna:
        str com o caminho do WAV temporário, ou None em caso de erro.

    Levanta:
        FFmpegNaoEncontrado se o FFmpeg não estiver disponível.
    """
    from exceptions.conversion_errors import FFmpegNaoEncontrado

    caminho_original = str(caminho_original)
    ext = Path(caminho_original).suffix.lower()

    if ext not in FORMATOS_SUPORTADOS:
        _log(atualizar_status, f"[ERRO] Formato não suportado: {ext}")
        return None

    if not Path(caminho_original).is_file():
        _log(atualizar_status, "[ERRO] Arquivo não encontrado.")
        return None

    try:
        ffmpeg, _ = obter_caminhos()
    except RuntimeError as e:
        raise FFmpegNaoEncontrado(str(e)) from e

    # Nome temporário curto e único
    nome_base  = Path(caminho_original).stem[:12]
    nome_saida = f"{nome_base}_temp_{randint(1000, 9999)}.wav"
    destino    = TEMP_DIR / nome_saida

    comando = [str(ffmpeg), "-y", "-i", caminho_original]
    if aprimorada:
        comando += ["-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le"]
    else:
        comando += ["-ar", "44100"]
    comando.append(str(destino))

    _log(atualizar_status, "[INFO] Convertendo com FFmpeg...")
    log_ffmpeg_inicio(caminho_original, str(destino))
    t0 = _time.monotonic()

    try:
        resultado = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs_processo(),
        )
        elapsed = _time.monotonic() - t0
        log_ffmpeg_fim(str(destino), elapsed, resultado.returncode)

        if resultado.returncode != 0:
            erro = resultado.stderr.decode(errors="replace").strip()
            log_ffmpeg_erro(erro)
            _log(atualizar_status, f"[ERRO] Falha na conversão:\n{erro}")
            return None

        return str(destino) if destino.exists() else None

    except Exception as e:
        _log(atualizar_status, f"[EXCEÇÃO] {e}")
        return None


# ---------------------------------------------------------------------------
# Duração
# ---------------------------------------------------------------------------

def obter_duracao(caminho: str) -> str:
    """
    Retorna a duração do arquivo de mídia no formato "H:MM:SS" ou "MM:SS".
    Retorna "" em caso de falha (ffprobe ausente, arquivo inválido, etc.).
    """
    try:
        _, ffprobe = obter_caminhos()
    except RuntimeError:
        return ""

    try:
        resultado = subprocess.run(
            [
                str(ffprobe),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(caminho),
            ],
            capture_output=True,
            text=True,
            **kwargs_processo(),
        )
        if resultado.returncode != 0:
            return ""
        texto = resultado.stdout.strip()
        if not texto:
            return ""
        segundos_total = int(float(texto))
        h, resto = divmod(segundos_total, 3600)
        m, s     = divmod(resto, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------

def _log(func, mensagem: str):
    if func:
        func(mensagem)
    else:
        print(mensagem)
