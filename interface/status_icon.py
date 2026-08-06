# interface/status_icon.py

from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QImage, QPixmap, QBitmap, QRegion
from PySide6.QtCore import Qt

_cache_icones_status: dict = {}


def _pixmap_recortado(caminho_png: str) -> QPixmap | None:
    """Aceita tanto caminho de disco (str/Path) quanto recurso Qt (":/icons/...")."""
    chave = str(caminho_png)
    pix = _cache_icones_status.get(chave)
    if pix is not None:
        return pix

    img = QImage(str(caminho_png))
    if img.isNull():
        return None

    if img.hasAlphaChannel():
        mask = QBitmap.fromImage(img.createAlphaMask())
        rect = QRegion(mask).boundingRect()
        if not rect.isNull() and rect.width() > 0 and rect.height() > 0:
            img = img.copy(rect)

    pix = QPixmap.fromImage(img)
    if pix.isNull():
        return None
    _cache_icones_status[chave] = pix
    return pix


def criar_label_icone_status(
    caminho_png: str, tamanho: int = 12, tamanho_label: int = 16
) -> QLabel | None:
    """Cria um QLabel com o pixmap de status já recortado e escalado.

    Retorna None se o PNG não existir ou não puder ser carregado — quem
    chamar deve tratar esse caso (ex: não adicionar o widget ao layout).
    """
    pix = _pixmap_recortado(caminho_png)
    if pix is None:
        return None

    pix_escalado = pix.scaled(
        tamanho, tamanho,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    lbl = QLabel()
    lbl.setPixmap(pix_escalado)
    lbl.setFixedSize(tamanho_label, tamanho_label)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl
