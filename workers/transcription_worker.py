# workers/transcription_worker.py
# Worker Qt para executar o pipeline de transcrição em thread separada.

from pathlib import Path
from time import time

from PySide6.QtCore import QThread, Signal

from transcriber.managers.model_manager import ModelManager
from transcriber.pipeline               import TranscriptionPipeline
from transcriber.request                import TranscriptionRequest
from exceptions.engine_errors           import TranscricaoCancelada
from utils.logger                       import salvar_erro


class TranscricaoWorker(QThread):
    status_atualizado    = Signal(str)
    progresso_fila       = Signal(int, int)     # (idx, total) — emitido antes de cada arquivo
    progresso_transcricao = Signal(int, float, str)  # (segundos, percentual, texto_segmento)
    arquivo_concluido    = Signal(str)
    arquivo_erro         = Signal(str)
    finalizado           = Signal(int, int, float)
    cancelado            = Signal()
    erro_geral           = Signal(str)

    def __init__(self, fila: list[dict], request_base: TranscriptionRequest):
        """
        fila:         list[dict]  — cada item tem "path" e "nome"
        request_base: TranscriptionRequest — parâmetros comuns a todos os arquivos
        """
        super().__init__()
        self.fila         = fila
        self.request_base = request_base
        self._cancelado   = False
        self._pipeline    = TranscriptionPipeline()

    def cancelar(self):
        self._cancelado = True
        self._pipeline.cancelar()

    def run(self):
        total    = len(self.fila)
        erros    = 0
        t_inicio = time()

        try:
            manager    = ModelManager(self.request_base.engine_id)
            model_path = manager.get_path(self.request_base.model_id)

            for idx, entrada in enumerate(self.fila, start=1):
                if self._cancelado:
                    break

                self.progresso_fila.emit(idx, total)

                request = TranscriptionRequest(
                    arquivo              = Path(entrada["path"]),
                    engine_id            = self.request_base.engine_id,
                    model_id             = self.request_base.model_id,
                    language             = self.request_base.language,
                    task                 = self.request_base.task,
                    pasta_saida          = self.request_base.pasta_saida,
                    usar_tempo           = self.request_base.usar_tempo and total == 1,
                    inicio               = self.request_base.inicio,
                    fim                  = self.request_base.fim,
                    formato_saida        = self.request_base.formato_saida,
                    vad_filter           = self.request_base.vad_filter,
                    usar_gpu             = self.request_base.usar_gpu,
                    temperature          = self.request_base.temperature,
                    beam_size            = self.request_base.beam_size,
                )

                try:
                    self._pipeline.processar(
                        request    = request,
                        model_path = model_path,
                        on_status  = self.status_atualizado.emit,
                        on_segment = self.progresso_transcricao.emit,
                    )
                    self.arquivo_concluido.emit(entrada["path"])

                except TranscricaoCancelada:
                    # cancelamento não é erro — não loga, o flag _cancelado encerra o loop na próxima volta
                    self._cancelado = True
                    break

                except Exception as e:
                    salvar_erro(e, contexto=f"Erro ao transcrever '{entrada['nome']}'")
                    erros += 1
                    self.arquivo_erro.emit(entrada["path"])

            elapsed = time() - t_inicio
            if self._cancelado:
                self.cancelado.emit()
            else:
                self.finalizado.emit(total - erros, total, elapsed)

        except Exception as e:
            salvar_erro(e, contexto="Erro geral na thread de transcrição")
            self.erro_geral.emit(str(e))
