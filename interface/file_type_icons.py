# interface/file_type_icons.py
# Ícones de tipo de arquivo (áudio/vídeo) para a lista de fila.

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QLabel

# Azul clarinho do app — mais escuro que o fundo, mais claro que o azul
# primário (#3b82f6) usado nos botões. Ajuste só aqui se quiser outro tom.
COR_ICONE_TIPO = "#60a5fa"

_cache_pixmaps: dict = {}


def _desenhar_audio(painter: QPainter, cor: QColor, tam: int) -> None:
    """Ícone de áudio: 3 barrinhas estilo equalizador."""
    largura_barra = max(2, round(tam * 0.16))
    espaco = max(2, round(tam * 0.12))
    alturas = [0.45, 0.85, 0.6]  # proporção da altura total, por barra
    total_largura = len(alturas) * largura_barra + (len(alturas) - 1) * espaco
    x = (tam - total_largura) / 2

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    for h_prop in alturas:
        h = tam * h_prop
        y = (tam - h) / 2
        rect = QRectF(x, y, largura_barra, h)
        painter.drawRoundedRect(rect, largura_barra / 2, largura_barra / 2)
        x += largura_barra + espaco


def _desenhar_video(painter: QPainter, cor: QColor, tam: int) -> None:
    """Ícone de vídeo: moldura arredondada + triângulo de play."""
    margem = tam * 0.08
    rect = QRectF(margem, margem, tam - 2 * margem, tam - 2 * margem)
    raio = tam * 0.18

    pen = QPen(cor)
    pen.setWidthF(max(1.2, tam * 0.09))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, raio, raio)

    lado = tam * 0.30
    cx, cy = tam / 2 + tam * 0.03, tam / 2
    triangulo = QPolygonF([
        QPointF(cx - lado * 0.45, cy - lado * 0.55),
        QPointF(cx - lado * 0.45, cy + lado * 0.55),
        QPointF(cx + lado * 0.55, cy),
    ])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    painter.drawPolygon(triangulo)


_DESENHISTAS = {
    "audio": _desenhar_audio,
    "video": _desenhar_video,
}


def criar_pixmap_tipo_arquivo(
    tipo: str, cor: str = COR_ICONE_TIPO, tamanho: int = 16
) -> QPixmap:
    """Retorna (com cache) o pixmap do ícone de áudio ou vídeo, na cor dada."""
    chave = (tipo, cor, tamanho)
    pix = _cache_pixmaps.get(chave)
    if pix is not None:
        return pix

    desenhista = _DESENHISTAS.get(tipo, _DESENHISTAS["audio"])

    escala = 4  # desenha em resolução maior e reduz, pra ficar nítido
    pix_grande = QPixmap(tamanho * escala, tamanho * escala)
    pix_grande.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix_grande)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    desenhista(painter, QColor(cor), tamanho * escala)
    painter.end()

    pix = pix_grande.scaled(
        tamanho, tamanho,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _cache_pixmaps[chave] = pix
    return pix


def criar_label_tipo_arquivo(
    tipo: str, cor: str = COR_ICONE_TIPO, tamanho: int = 16, tamanho_label: int = 22
) -> QLabel:
    """QLabel pronto com o pixmap do ícone de áudio/vídeo já centralizado."""
    lbl = QLabel()
    lbl.setPixmap(criar_pixmap_tipo_arquivo(tipo, cor, tamanho))
    lbl.setFixedWidth(tamanho_label)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl
