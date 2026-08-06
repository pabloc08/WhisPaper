# utils/flags.py

from PySide6.QtCore import Qt, QSize, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPolygonF, QIcon

ratio = 3


def _novo_pixmap(size: QSize) -> QPixmap:
    pm = QPixmap(size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def gerar_bandeira_brasil(size: QSize = QSize(20, 14)) -> QPixmap:
    pm = _novo_pixmap(size)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    w, h = size.width(), size.height()
    rect = QRectF(0, 0, w, h)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#009739"))
    painter.drawRect(rect)

    losango = QPolygonF([
        QPointF(w * 0.5, h * 0.08),
        QPointF(w * 0.92, h * 0.5),
        QPointF(w * 0.5, h * 0.92),
        QPointF(w * 0.08, h * 0.5),
    ])
    painter.setBrush(QColor("#FEDD00"))
    painter.drawPolygon(losango)

    raio = h * 0.28
    centro = QPointF(w * 0.5, h * 0.5)

    from PySide6.QtGui import QPainterPath
    caminho_circulo = QPainterPath()
    caminho_circulo.addEllipse(centro, raio, raio)
    painter.setClipPath(caminho_circulo)

    painter.setBrush(QColor("#1B4B9C"))
    painter.drawEllipse(centro, raio, raio)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    faixa = QRectF(centro.x() - raio * 1.3, centro.y() - raio * 0.16, raio * 2.6, raio * 0.32)
    painter.save()
    painter.translate(centro)
    painter.rotate(14.5)
    painter.translate(-centro.x(), -centro.y())
    painter.drawRect(faixa)
    painter.restore()

    painter.setClipping(False)

    painter.end()
    return pm


def gerar_bandeira_eua(size: QSize = QSize(20, 14)) -> QPixmap:
    pm = _novo_pixmap(size)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    w, h = size.width(), size.height()
    n_listras = 7
    altura_listra = h / n_listras

    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(n_listras):
        cor = QColor("#B22234") if i % 2 == 0 else QColor("#FFFFFF")
        painter.setBrush(cor)
        painter.drawRect(QRectF(0, i * altura_listra, w, altura_listra + 0.5))

    cantao_altura = altura_listra * 4
    cantao_largura = w * 0.55
    painter.setBrush(QColor("#3C3B6E"))
    painter.drawRect(QRectF(0, 0, cantao_largura, cantao_altura))

    painter.setBrush(QColor("#FFFFFF"))
    linhas, colunas = 2, 3
    margem_x = cantao_largura / (colunas + 1)
    margem_y = cantao_altura / (linhas + 1)
    raio_estrela = min(margem_x, margem_y) * 0.16
    for lin in range(1, linhas + 1):
        for col in range(1, colunas + 1):
            centro = QPointF(margem_x * col, margem_y * lin)
            painter.drawEllipse(centro, raio_estrela, raio_estrela)

    painter.end()
    return pm


def icone_bandeira_brasil(size: QSize = QSize(20, 14)) -> QIcon:
    return QIcon(gerar_bandeira_brasil(size))


def icone_bandeira_eua(size: QSize = QSize(20, 14)) -> QIcon:
    return QIcon(gerar_bandeira_eua(size))
