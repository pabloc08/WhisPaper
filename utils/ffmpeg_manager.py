# utils/ffmpeg_manager.py
# Gerencia a detecção e instalação do FFmpeg.


import sys
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Optional, Callable

import httpx

from settings.paths import FFMPEG_LOCAL_DIR, FFMPEG_LOCAL_BIN, FFMPEG_LOCAL_PROBE
from utils.downloader import HttpDownloader, Progresso, DownloadCancelado

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# Tamanho em cache: obtido via HEAD request na primeira chamada.
_ffmpeg_tamanho_cache: Optional[str] = None

def _obter_tamanho_ffmpeg() -> str:
    """Faz um HEAD request para obter o tamanho real do arquivo FFmpeg."""
    global _ffmpeg_tamanho_cache
    if _ffmpeg_tamanho_cache is not None:
        return _ffmpeg_tamanho_cache
    
    try:
        resp = httpx.head(
            FFMPEG_URL, timeout=10,
            headers={"User-Agent": "WhisPaper/1.0 (FFmpeg size check)"},
            follow_redirects=True,
        )
        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > 0:
            mb = content_length / 1024 / 1024
            _ffmpeg_tamanho_cache = f"~{mb:.0f} MB"
            return _ffmpeg_tamanho_cache
    except Exception:
        pass
    
    _ffmpeg_tamanho_cache = "~101 MB"
    return _ffmpeg_tamanho_cache

def FFMPEG_TAMANHO_APROX() -> str:  # noqa: N802
    """Retorna o tamanho real do zip do FFmpeg (com cache)."""
    return _obter_tamanho_ffmpeg()

# ---------------------------------------------------------------------------
# Detecção
# ---------------------------------------------------------------------------
def _which(nome: str) -> Optional[Path]:
    """Retorna o Path do binário se encontrado no sistema, ou None."""
    resultado = shutil.which(nome)
    return Path(resultado) if resultado else None

def ffmpeg_instalado() -> bool:
    """Retorna True se ffmpeg e ffprobe estão disponíveis."""
    return _resolver_ffmpeg() is not None and _resolver_ffprobe() is not None

def _resolver_ffmpeg() -> Optional[Path]:
    sistema = _which("ffmpeg")
    if sistema:
        return sistema
    if sys.platform == "win32" and FFMPEG_LOCAL_BIN.exists():
        return FFMPEG_LOCAL_BIN
    return None

def _resolver_ffprobe() -> Optional[Path]:
    sistema = _which("ffprobe")
    if sistema:
        return sistema
    if sys.platform == "win32" and FFMPEG_LOCAL_PROBE.exists():
        return FFMPEG_LOCAL_PROBE
    return None

def obter_caminhos() -> tuple[Path, Path]:
    """Retorna (ffmpeg_path, ffprobe_path) prontos para uso."""
    ff = _resolver_ffmpeg()
    ffp = _resolver_ffprobe()
    if not ff or not ffp:
        raise RuntimeError("FFmpeg não encontrado. Instale-o antes de continuar.")
    return ff, ffp

# ---------------------------------------------------------------------------
# Download + extração (Windows apenas)
# ---------------------------------------------------------------------------
def limpar_arquivos_parciais() -> None:
    """Remove qualquer arquivo .part deixado por uma instalação interrompida."""
    if sys.platform != "win32":
        return
    for f in FFMPEG_LOCAL_DIR.glob("*.part"):
        _tentar_remover(f)
    for f in FFMPEG_LOCAL_DIR.glob("*.part.json"):
        _tentar_remover(f)

def baixar_ffmpeg(
    callback_progresso: Optional[Callable[[int, int], None]] = None,
    callback_status: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> None:
    """Baixa o zip do gyan.dev e extrai só ffmpeg.exe/ffprobe.exe (retry/resume via HttpDownloader)."""
    if sys.platform != "win32":
        return

    FFMPEG_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    limpar_arquivos_parciais()

    zip_destino = FFMPEG_LOCAL_DIR / "ffmpeg-release-essentials.zip"
    downloader = HttpDownloader(cancel_event=cancel_event, max_tentativas=3)

    def _adaptador_progresso(prog: Progresso):
        if callback_progresso:
            callback_progresso(prog.baixado, prog.total)

    try:
        # O downloader baixa atomicamente para .part e renomeia para o destino final
        downloader.baixar(FFMPEG_URL, zip_destino, callback_progresso=_adaptador_progresso)
        
        if callback_status:
            callback_status("extraindo")
            
        _extrair_binarios(zip_destino, FFMPEG_LOCAL_DIR)
        
        # Limpa o zip após extração bem-sucedida para economizar espaço
        _tentar_remover(zip_destino)
        
    except DownloadCancelado:
        # Cancelamento limpo. O .part é preservado pelo downloader para retomada.
        raise
    except Exception as e:
        raise RuntimeError(f"Falha no download ou extração do FFmpeg: {e}")

def _extrair_binarios(zip_path: Path, destino: Path) -> None:
    """Extrai ffmpeg.exe e ffprobe.exe do zip para destino/ de forma atômica."""
    if not zip_path.exists():
        raise FileNotFoundError(f"Arquivo zip não encontrado: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise RuntimeError("Arquivo baixado está corrompido (não é um zip válido).")

    alvos = {"ffmpeg.exe", "ffprobe.exe"}
    extraidos = set()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for membro in zf.namelist():
            nome = Path(membro).name
            if nome not in alvos:
                continue
            
            dest_final = destino / nome
            dest_parcial = destino / f"{nome}.part"
            
            with zf.open(membro) as src, open(dest_parcial, "wb") as dst:
                while True:
                    chunk = src.read(256 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            
            # Escrita atômica do binário extraído
            dest_parcial.replace(dest_final)
            extraidos.add(nome)

    if extraidos != alvos:
        faltando = alvos - extraidos
        raise RuntimeError(f"Zip do FFmpeg não continha os binários esperados: {faltando}")

def _tentar_remover(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
