# transcriber/pipeline.py
# Orquestra o fluxo completo de transcrição — puro Python, sem Qt.
# O worker chama processar() e só cuida de threading e signals.

import datetime
from pathlib import Path
from time import time

from converter.converter import precisa_converter, converter_para_wav, obter_duracao_segundos
from converter.trimmer   import recortar
from transcriber.managers.engine_manager import EngineManager
from transcriber.request import TranscriptionRequest
from transcriber.result  import TranscriptionResult
from utils.filenames     import gerar_nome_saida
from utils.logger        import (
    log_pipeline_inicio, log_pipeline_fim, log_pipeline_erro, log_cancelamento
)
from settings.i18n       import t


class TranscriptionPipeline:
    """
    Executa o pipeline completo para um único arquivo.
    Não conhece Qt — pode ser testado sem QApplication.
    """

    def __init__(self):
        self._engine_ativa = None
        self._cancelado    = False

    def cancelar(self):
        """Chamado pelo worker via signal de cancelamento do usuário."""
        self._cancelado = True
        log_cancelamento("usuario")
        engine = self._engine_ativa
        if engine:
            engine.cancel()

    def processar(
        self,
        request:    TranscriptionRequest,
        model_path: Path,
        on_status:  callable = None,
        on_segment: callable = None,
    ) -> TranscriptionResult:
        """
        Processa um arquivo completo:
          converter → recortar → transcrever → cleanup

        on_segment: callback(segundos: int, percentual: float, texto: str),
                    chamado a cada segmento reconhecido — usado pelo painel
                    de progresso em tempo real. Opcional.

        Raises:
            qualquer exceção da engine ou conversor — tratamento no worker
        """
        t_inicio        = time()
        wav_convertido  = None
        arquivo_recorte = None

        log_pipeline_inicio(
            request.arquivo.name, request.engine_id,
            request.task, request.language
        )

        try:
            # ── 1. Converter para WAV ────────────────────────────────────────
            if precisa_converter(str(request.arquivo), forcar=True):
                wav_str = converter_para_wav(
                    str(request.arquivo),
                    atualizar_status=None,
                    aprimorada=True,
                )
                if not wav_str:
                    raise RuntimeError(
                        f"Falha ao converter '{request.arquivo.name}' para WAV."
                    )
                audio_path     = Path(wav_str)
                wav_convertido = audio_path          # marcar para cleanup
            else:
                # Já é WAV compatível — whisper-cli só lê, nunca escreve no original
                audio_path     = request.arquivo
                wav_convertido = None                # nada para limpar

            # ── 2. Recortar (só com arquivo único e tempo configurado) ───────
            if request.usar_tempo:
                ini = (request.inicio or "").strip()
                fim = (request.fim    or "").strip()
                if ini or fim:
                    audio_path      = recortar(audio_path, ini or None, fim or None)
                    arquivo_recorte = audio_path     # marcar para cleanup

            # ── 3. Instanciar engine e transcrever ───────────────────────────
            engine             = EngineManager.get(request.engine_id)
            self._engine_ativa = engine              # expõe para cancelar()

            # Se cancelamento chegou antes da engine ser instanciada
            if self._cancelado:
                engine.cancel()
                from exceptions.engine_errors import TranscricaoCancelada
                raise TranscricaoCancelada("Cancelado antes da transcrição.")

            agora       = datetime.datetime.now()

            # Validar pasta de saída antes de prosseguir
            if not request.pasta_saida.is_dir():
                raise FileNotFoundError(
                    f"Pasta de destino não encontrada: {request.pasta_saida}"
                )

            # gerar_nome_saida devolve sempre um path .txt como base de nome.
            # Retiramos o sufixo para que a engine adicione .txt ou .srt conforme o formato.
            destino_base = gerar_nome_saida(
                request.arquivo.name, request.pasta_saida, agora
            )
            output_path = destino_base.with_suffix("")  # engine adiciona .txt / .srt

            if on_status:
                on_status(t("status.transcrevendo"))

            # Duração total do áudio (segundos) — usada só para calcular o
            # percentual mostrado no painel de progresso. Falha em obter
            # (ffprobe ausente, etc.) não impede a transcrição — o painel
            # simplesmente fica sem percentual nesse caso.
            duracao_total = obter_duracao_segundos(str(audio_path)) if on_segment else None

            def _progresso(segundos: int, texto_segmento: str):
                if on_segment:
                    percentual = (
                        min(100.0, (segundos / duracao_total) * 100)
                        if duracao_total else 0.0
                    )
                    on_segment(segundos, percentual, texto_segmento)

            engine.transcribe(
                audio_path       = audio_path,
                model_path       = model_path,
                task             = request.task,
                language         = request.language,
                output_path      = output_path,
                formato_saida    = request.formato_saida,
                vad_filter       = request.vad_filter,
                usar_gpu         = getattr(request, "usar_gpu", False),
                temperature      = getattr(request, "temperature", 0.0),
                beam_size        = getattr(request, "beam_size", 5),
                on_progress      = _progresso if (on_status or on_segment) else None,
            )

            # Determina o arquivo principal gerado para o resultado.
            if request.formato_saida in ("srt", "srt_vtt", "todos"):
                arquivo_saida = destino_base.with_suffix(".srt")
            elif request.formato_saida == "vtt":
                arquivo_saida = destino_base.with_suffix(".vtt")
            else:
                arquivo_saida = destino_base.with_suffix(".txt")

            resultado = TranscriptionResult(
                arquivo_original = request.arquivo,
                arquivo_txt      = arquivo_saida,
                engine_id        = request.engine_id,
                model_id         = request.model_id,
                language         = request.language,
                duracao_s        = time() - t_inicio,
            )
            log_pipeline_fim(
                request.arquivo.name,
                resultado.duracao_s,
                str(arquivo_saida),
            )
            return resultado

        except Exception as e:
            log_pipeline_erro(request.arquivo.name, e)
            raise

        finally:
            self._engine_ativa = None
            # Cleanup do WAV recortado
            if arquivo_recorte and Path(arquivo_recorte).exists():
                try:
                    Path(arquivo_recorte).unlink()
                except Exception:
                    pass
            # Cleanup do WAV convertido (só se for diferente do recorte)
            if (wav_convertido
                    and wav_convertido != arquivo_recorte
                    and Path(wav_convertido).exists()):
                try:
                    Path(wav_convertido).unlink()
                except Exception:
                    pass
