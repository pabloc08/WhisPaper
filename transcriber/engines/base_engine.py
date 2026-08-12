# transcriber/engines/base_engine.py
# Contrato de engine via ABC — subclasse sem transcribe()/cancel() falha na
# instanciação, não em runtime.

from abc import ABC, abstractmethod
from pathlib import Path


class BaseEngine(ABC):
    """
    Classe base abstrata das engines de transcrição.

    Capabilities (sobrescreva na subclasse): supports_translation,
    supports_gpu, supports_word_timestamps.
    """

    supports_translation:     bool = False
    supports_gpu:             bool = False
    supports_word_timestamps: bool = False
    supports_vad:             bool = False

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
        Transcreve e retorna o Path do arquivo gerado (.txt ou .srt).

        output_path é o path base SEM extensão — a engine acrescenta a
        extensão certa. on_progress recebe (segundos_transcritos, texto_segmento)
        a cada segmento. Levanta TranscricaoCancelada, BinarioNaoEncontrado,
        ModeloNaoEncontrado ou RuntimeError conforme o erro.
        """

    @abstractmethod
    def cancel(self) -> None:
        """Sinaliza cancelamento; seguro chamar mesmo sem transcrição rodando."""
