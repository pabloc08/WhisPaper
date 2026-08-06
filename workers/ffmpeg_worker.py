# workers/ffmpeg_worker.py
# Worker Qt para download do FFmpeg em background.
import threading
from PySide6.QtCore import QThread, Signal

from utils.ffmpeg_manager import baixar_ffmpeg
from utils.downloader import DownloadCancelado

class FFmpegWorker(QThread):
    progresso = Signal(int, float)  # pct (0–100), MB baixados
    status = Signal(str)            # mensagens de estado ("extraindo", etc.)
    concluido = Signal()
    erro = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancel_event = threading.Event()

    def cancelar(self):
        self._cancel_event.set()

    def run(self):
        try:
            def cb_prog(baixado: int, total: int):
                if self._cancel_event.is_set():
                    return
                if total:
                    pct = int(baixado / total * 100)
                else:
                    pct = -1
                mb = baixado / 1024 / 1024
                self.progresso.emit(pct, mb)

            def cb_status(msg: str):
                if self._cancel_event.is_set():
                    return
                self.status.emit(msg)

            baixar_ffmpeg(
                callback_progresso=cb_prog,
                callback_status=cb_status,
                cancel_event=self._cancel_event
            )
            
            if not self._cancel_event.is_set():
                self.concluido.emit()
                
        except DownloadCancelado:
            # Cancelamento limpo pelo usuário
            pass
        except Exception as e:
            if not self._cancel_event.is_set():
                self.erro.emit(str(e))