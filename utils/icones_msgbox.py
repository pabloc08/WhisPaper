# utils/icones_msgbox.py
# Ícones desenhados via QPainter (não texto/glifo) pra ficarem idênticos em qualquer SO.

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPixmap, QPainterPath


def icone_info_circular(
    tamanho: int = 48,
    cor_fundo: str = "#3b82f6",
    cor_simbolo: str = "#ffffff",
) -> QPixmap:
    """Círculo com "i" de informação (bolinha + haste), glifo centralizado de verdade."""
    pm = QPixmap(tamanho, tamanho)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)

    p.setBrush(QColor(cor_fundo))
    p.drawEllipse(QRectF(tamanho * 0.02, tamanho * 0.02, tamanho * 0.96, tamanho * 0.96))

    p.setBrush(QColor(cor_simbolo))
    cx = tamanho / 2
    raio_ponto = tamanho * 0.085
    cy_ponto = tamanho * 0.30
    p.drawEllipse(QPointF(cx, cy_ponto), raio_ponto, raio_ponto)

    largura_haste = tamanho * 0.15
    y0 = cy_ponto + raio_ponto + tamanho * 0.05
    y1 = tamanho - (cy_ponto - raio_ponto)
    p.drawRoundedRect(
        QRectF(cx - largura_haste / 2, y0, largura_haste, y1 - y0),
        largura_haste / 2, largura_haste / 2,
    )

    p.end()
    return pm


def icone_pasta(tamanho: int = 18, cor: str = "#5b9bd5") -> QPixmap:
    """Pastinha flat de duas camadas (aba + corpo), mesmo tom do botão de transcrever."""
    pm = QPixmap(tamanho, tamanho)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)

    cor_corpo = QColor(cor)
    cor_aba = cor_corpo.darker(112)

    aba = QPainterPath()
    aba.addRoundedRect(QRectF(tamanho * 0.08, tamanho * 0.18, tamanho * 0.38, tamanho * 0.16), 2, 2)
    p.setBrush(cor_aba)
    p.drawPath(aba)

    corpo = QPainterPath()
    corpo.addRoundedRect(QRectF(tamanho * 0.08, tamanho * 0.30, tamanho * 0.84, tamanho * 0.56), 3, 3)
    p.setBrush(cor_corpo)
    p.drawPath(corpo)

    p.end()
    return pm
