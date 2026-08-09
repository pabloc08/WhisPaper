# utils/audio.py

from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl, QFile
from utils.logger import log_info, log_erro

_cache: dict[str, QSoundEffect] = {}


def tocar_som(nome: str) -> None:
    caminho = f":/sons/{nome}.wav"
    if not QFile.exists(caminho):
        log_info(f"Som não encontrado: {caminho}")
        return
    try:
        efeito = _cache.get(nome)
        # Recria se ainda não existe ou se o status não é Loading/Ready
        # (Status 0 = Null, 1 = Loading, 2 = Ready, 3 = Error)
        if efeito is None or efeito.status() == QSoundEffect.Status.Error \
                or efeito.status() == QSoundEffect.Status.Null:
            efeito = QSoundEffect()
            efeito.setSource(QUrl(f"qrc{caminho}"))
            efeito.setVolume(1.0)
            _cache[nome] = efeito
        efeito.play()
    except Exception as e:
        log_erro(e, contexto=f"tocar_som('{nome}')")


def pre_aquecer(nomes: list[str]) -> None:
    """Carrega (sem tocar) os efeitos sonoros informados, forçando a
    inicialização do backend de áudio do SO fora do caminho crítico.
    Chamado uma vez no startup — sem isso, a primeira chamada real de
    tocar_som() (ex: ao clicar em "Transcrever") trava a interface por
    uma fração de segundo enquanto o backend (WASAPI/CoreAudio/etc.)
    inicializa pela primeira vez no processo."""
    for nome in nomes:
        caminho = f":/sons/{nome}.wav"
        if not QFile.exists(caminho):
            continue
        try:
            efeito = QSoundEffect()
            efeito.setSource(QUrl(f"qrc{caminho}"))
            efeito.setVolume(1.0)
            _cache[nome] = efeito
        except Exception as e:
            log_erro(e, contexto=f"pre_aquecer('{nome}')")


def limpar_cache_audio() -> None:
    _cache.clear()
