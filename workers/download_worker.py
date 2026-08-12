# workers/download_worker.py
# Worker Qt para download de modelos em background.
import threading
from PySide6.QtCore import QThread, Signal

from transcriber.managers.model_manager import ModelManager
from utils.downloader import DownloadCancelado

class DownloadWorker(QThread):
    progresso = Signal(int, float)  # pct (0-100), MB baixados
    concluido = Signal(str)         # model_id
    erro = Signal(str)

    def __init__(self, engine_id: str, model_id: str):
        super().__init__()
        self.engine_id = engine_id
        self.model_id = model_id
        # evento de cancelamento cooperativo nativo do downloader
        self._cancel_event = threading.Event()

    def cancelar(self):
        self._cancel_event.set()

    def run(self):
        try:
            manager = ModelManager(self.engine_id)
            
            def cb_prog(baixado: int, total: int):
                # downloader já checa cancel_event, isso é só pra não emitir sinal depois de cancelar
                if self._cancel_event.is_set():
                    return
                
                if total:
                    pct = int(baixado / total * 100)
                else:
                    pct = -1
                mb = baixado / 1024 / 1024
                self.progresso.emit(pct, mb)

            # downloader cuida de .part, .part.json, retry e resume sozinho
            manager.baixar(
                self.model_id, 
                callback_progresso=cb_prog, 
                cancel_event=self._cancel_event
            )
            
            if not self._cancel_event.is_set():
                self.concluido.emit(self.model_id)
                
        except DownloadCancelado:
            pass   # cancelamento limpo — .part fica preservado pra retomar depois
        except Exception as e:
            if not self._cancel_event.is_set():
                self.erro.emit(str(e))
