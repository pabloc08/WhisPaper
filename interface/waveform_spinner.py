# interface/waveform_spinner.py
# Indicador de atividade em onda — substitui o spinner de texto (braille) durante a
# transcrição. Só animação em loop, sem progresso real (isso é o PainelProgresso).
# No cancelamento/erro, congela no formato atual e vira vermelho.

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QSizePolicy


class WaveformSpinner(QWidget):
    """Barrinhas de onda animadas, estilo equalizador — QPainter puro, retém tamanho quando escondido."""

    NUM_BARRAS    = 5
    LARGURA_BARRA = 4
    ESPACO        = 3
    PROP_MINIMA   = 0.28   # altura mínima da barra, proporção da altura total

    COR_LIGHT = QColor("#3b82f6")
    COR_DARK  = QColor("#5B8CFF")
    COR_ERRO_LIGHT = QColor("#f87171")
    COR_ERRO_DARK  = QColor("#FF6B6B")

    def __init__(self, parent=None):
        super().__init__(parent)
        largura_total = (
            self.NUM_BARRAS * self.LARGURA_BARRA
            + (self.NUM_BARRAS - 1) * self.ESPACO
        )
        self.setFixedSize(largura_total, 18)

        # mantém o espaço reservado no layout mesmo escondido, senão o container "pula" a cada transcrição
        politica = self.sizePolicy()
        politica.setRetainSizeWhenHidden(True)
        self.setSizePolicy(politica)

        self._fase  = 0.0
        self._tema  = "light"
        self._cor   = self.COR_LIGHT
        self._ativo = False

        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._avancar_fase)

        self.hide()

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    def set_tema(self, tema: str) -> None:
        self._tema = tema
        if self._ativo and self._timer.isActive():
            self._cor = self.COR_DARK if tema == "dark" else self.COR_LIGHT
            self.update()

    def start(self) -> None:
        self._ativo = True
        self._fase  = 0.0
        self._cor   = self.COR_DARK if self._tema == "dark" else self.COR_LIGHT
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._ativo = False
        self._timer.stop()
        self.hide()

    def congelar_erro(self) -> None:
        """Congela as barras no formato atual e muda pra vermelho."""
        self._timer.stop()
        self._cor   = self.COR_ERRO_DARK if self._tema == "dark" else self.COR_ERRO_LIGHT
        self._ativo = True
        self.show()
        self.update()

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _avancar_fase(self) -> None:
        self._fase += 0.35
        self.update()

    def paintEvent(self, event) -> None:
        if not self._ativo:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._cor)

        h_total = self.height()
        x = 0.0
        for i in range(self.NUM_BARRAS):
            onda = (math.sin(self._fase + i * 0.9) + 1) / 2   # 0..1
            prop = self.PROP_MINIMA + onda * (1 - self.PROP_MINIMA)
            h = h_total * prop
            y = (h_total - h) / 2
            painter.drawRoundedRect(
                round(x), round(y), self.LARGURA_BARRA, round(h),
                self.LARGURA_BARRA / 2, self.LARGURA_BARRA / 2,
            )
            x += self.LARGURA_BARRA + self.ESPACO
