# interface/progress_bar.py

from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve,
    QSequentialAnimationGroup, QParallelAnimationGroup,
    Property, QRect
)
from PySide6.QtGui import QPainter, QColor


class BarraAnimada(QWidget):
    """
    Barra de progresso animada — bloco deslizando com cor pulsando
    suavemente entre azul claro e azul escuro em sincronia.
    """

    ALTURA        = 3
    LARGURA_BLOCO = 70

    COR_CLARA       = QColor("#bae6fd")
    COR_ESCURA      = QColor("#60a5fa")
    COR_CLARA_DARK  = QColor("#1e4870")   # azul escuro, sem verde

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.ALTURA)

        self._cor      = QColor(0, 0, 0, 0)
        self._pos_x    = 0.0
        self._ativo    = False
        self._estatico = False

        # ── Fade-in de opacidade (widget inteiro) ──────────────────────
        self._efeito_opacidade = QGraphicsOpacityEffect(self)
        self._efeito_opacidade.setOpacity(0.0)
        self.setGraphicsEffect(self._efeito_opacidade)
        self._anim_opacidade = None   # mantém viva a animação em curso

        # ── Animação de posição (ida) ─────────────────────────────────
        pos_ida = QPropertyAnimation(self, b"posX", self)
        pos_ida.setStartValue(0.0)
        pos_ida.setEndValue(1.0)
        pos_ida.setDuration(2800)
        pos_ida.setEasingCurve(QEasingCurve.Type.InOutSine)

        # ── Animação de cor na ida: claro → escuro ────────────────────
        cor_ida = QPropertyAnimation(self, b"corBloco", self)
        cor_ida.setStartValue(self.COR_CLARA)
        cor_ida.setEndValue(self.COR_ESCURA)
        cor_ida.setDuration(2800)
        cor_ida.setEasingCurve(QEasingCurve.Type.InOutSine)

        # ── Paralelo ida ──────────────────────────────────────────────
        paralelo_ida = QParallelAnimationGroup(self)
        paralelo_ida.addAnimation(pos_ida)
        paralelo_ida.addAnimation(cor_ida)

        # ── Animação de posição (volta) ───────────────────────────────
        pos_volta = QPropertyAnimation(self, b"posX", self)
        pos_volta.setStartValue(1.0)
        pos_volta.setEndValue(0.0)
        pos_volta.setDuration(2800)
        pos_volta.setEasingCurve(QEasingCurve.Type.InOutSine)

        # ── Animação de cor na volta: escuro → claro ──────────────────
        cor_volta = QPropertyAnimation(self, b"corBloco", self)
        cor_volta.setStartValue(self.COR_ESCURA)
        cor_volta.setEndValue(self.COR_CLARA)
        cor_volta.setDuration(2800)
        cor_volta.setEasingCurve(QEasingCurve.Type.InOutSine)

        # ── Paralelo volta ────────────────────────────────────────────
        paralelo_volta = QParallelAnimationGroup(self)
        paralelo_volta.addAnimation(pos_volta)
        paralelo_volta.addAnimation(cor_volta)

        # ── Sequência infinita ────────────────────────────────────────
        self._anim = QSequentialAnimationGroup(self)
        self._anim.addAnimation(paralelo_ida)
        self._anim.addAnimation(paralelo_volta)
        self._anim.setLoopCount(-1)

    # ------------------------------------------------------------------
    # Properties Qt
    # ------------------------------------------------------------------

    def _get_pos_x(self) -> float:
        return self._pos_x

    def _set_pos_x(self, valor: float):
        self._pos_x = valor
        self.update()

    posX = Property(float, _get_pos_x, _set_pos_x)

    def _get_cor(self) -> QColor:
        return self._cor

    def _set_cor(self, cor: QColor):
        self._cor = cor
        self.update()

    corBloco = Property(QColor, _get_cor, _set_cor)

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    def start(self, tema: str = "light"):
        clara = self.COR_CLARA_DARK if tema == "dark" else self.COR_CLARA

        # Reconfigura os valores das animações de cor para o tema atual.
        seq       = self._anim
        p_ida     = seq.animationAt(0)   # QParallelAnimationGroup ida
        p_volta   = seq.animationAt(1)   # QParallelAnimationGroup volta
        cor_ida   = p_ida.animationAt(1)
        cor_volta = p_volta.animationAt(1)

        cor_ida.setStartValue(clara)
        cor_ida.setEndValue(self.COR_ESCURA)
        cor_volta.setStartValue(self.COR_ESCURA)
        cor_volta.setEndValue(clara)

        self._estatico = False
        self._ativo    = True
        self._cor      = clara

        # Fade-in suave da barra inteira
        self._efeito_opacidade.setOpacity(0.0)
        anim_fade = QPropertyAnimation(self._efeito_opacidade, b"opacity", self)
        anim_fade.setDuration(350)
        anim_fade.setStartValue(0.0)
        anim_fade.setEndValue(1.0)
        anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_opacidade = anim_fade
        anim_fade.start()

        self._anim.start()
        self.update()

    def complete(self):
        self._parar_animacao()
        self._cor = QColor("#60a5fa")
        self.update()

    def cancel(self):
        self._parar_animacao()
        self._cor = QColor("#f87171")
        self.update()

    def reset(self):
        self._parar_animacao()
        self._cor   = QColor(0, 0, 0, 0)
        self._pos_x = 0.0
        self.update()

    # ------------------------------------------------------------------
    # Pintura
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        if self._cor.alpha() == 0:
            return

        w = self.width()
        h = self.ALTURA

        if self._estatico:
            painter.fillRect(QRect(0, 0, w, h), self._cor)
        else:
            espaco = max(w - self.LARGURA_BLOCO, 0)
            x      = int(self._pos_x * espaco)
            painter.fillRect(QRect(x, 0, self.LARGURA_BLOCO, h), self._cor)

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _parar_animacao(self):
        self._anim.stop()
        if self._anim_opacidade is not None:
            self._anim_opacidade.stop()
        self._efeito_opacidade.setOpacity(1.0)
        self._ativo    = False
        self._estatico = True
