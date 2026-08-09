# transcriber/engines/base_engine.py
# Contrato formal de engine via ABC.
# Qualquer engine que não implemente transcribe() ou cancel() falha
# na instanciação — não em runtime — graças ao @abstractmethod.

from abc import ABC, abstractmethod
from pathlib import Path


class BaseEngine(ABC):
    """
    Classe base abstrata para todas as engines de transcrição.

    Capabilities (class attributes — sobrescreva na subclasse):
        supports_translation     : engine suporta task="translate"
        supports_gpu             : engine pode usar GPU
        supports_word_timestamps : engine gera timestamps por palavra
    """

    supports_translation:     bool = False
    supports_gpu:             bool = False
    supports_word_timestamps: bool = False
    supports_vad:             bool = False

    # ------------------------------------------------------------------
    # Interface obrigatória — Python levanta TypeError na instanciação
    # se a subclasse não implementar estes métodos.
    # ------------------------------------------------------------------

    @abstractmethod
    def transcribe(
        self,
        audio_path:    Path,
        model_path:    Path,
        task:          str = "transcribe",
        language:      str = "auto",
        output_path:   Path = None,
        formato_saida: str = "ambos",
        vad_filter:    bool = False,
        on_progress:   callable = None,
        temperature:   float = 0.0,
        beam_size:     int = 5,
    ) -> Path:
        """
        Executa a transcrição e retorna o Path do arquivo principal gerado.

        Parâmetros:
            audio_path    WAV de entrada (16kHz mono PCM)
            model_path    Path do modelo (.bin) ou identificador HuggingFace
            task          "transcribe" ou "translate"
            language      código ISO ("pt", "en"…) ou "auto"
            output_path   Path base SEM extensão — a engine acrescenta
                          .txt / .srt conforme formato_saida
            formato_saida "txt", "srt" ou "ambos"
            on_progress   callback(segundos_transcritos: int, texto_segmento: str),
                          chamado a cada segmento reconhecido pela engine
            temperature   temperatura de amostragem (0.0 = determinístico)
            beam_size     tamanho do beam search (-1 desativa, usa greedy)

        Retorna:
            Path do arquivo principal gerado (.txt ou .srt)

        Levanta:
            TranscricaoCancelada   se cancel() foi chamado durante execução
            BinarioNaoEncontrado   se binário/runtime não existe
            ModeloNaoEncontrado    se o arquivo de modelo não existe
            RuntimeError           qualquer outro erro de execução
        """

    @abstractmethod
    def cancel(self) -> None:
        """
        Sinaliza cancelamento e encerra a transcrição em andamento.
        Deve ser seguro chamar mesmo se transcribe() não estiver rodando.
        """
