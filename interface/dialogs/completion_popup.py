# interface/dialogs/completion_popup.py
# Diálogo de conclusão de transcrição.

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from utils.platform import abrir_pasta
from settings.i18n import t


def _cores_tema(tema: str = "light") -> dict:
    """Retorna dicionário de cores adequado ao tema."""
    if tema == "dark":
        return {
            "bg":              "#1e293b",
            "border":          "#334155",
            "titulo":          "#f1f5f9",
            "corpo":           "#94a3b8",
            "sep":             "#334155",
            "btn_sec_bg":      "#334155",
            "btn_sec_fg":      "#cbd5e1",
            "btn_sec_border":  "#475569",
            "btn_sec_hover":   "#475569",
            "btn_sec_pressed": "#1e293b",
        }
    return {
        "bg":              "#f5f5f5",
        "border":          "#cbd5e1",
        "titulo":          "#0f172a",
        "corpo":           "#475569",
        "sep":             "#e2e8f0",
        "btn_sec_bg":      "#f1f5f9",
        "btn_sec_fg":      "#334155",
        "btn_sec_border":  "#cbd5e1",
        "btn_sec_hover":   "#e2e8f0",
        "btn_sec_pressed": "#cbd5e1",
    }


class PopupConclusao(QDialog):
    """
    Diálogo customizado de conclusão de transcrição.
    Modal e bloqueante — usa exec().
    """

    def __init__(self, parent, corpo: str, pasta_destino: str = "", on_ok: callable = None):
        super().__init__(parent)
        self._pasta_destino = pasta_destino
        self._on_ok = on_ok
        self.setWindowTitle(t("popup.titulo"))
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        tema = getattr(parent, "configs", {}).get("tema", "light")
        self._build(corpo, tema)
        self.adjustSize()
        self._centralizar(parent)
        self.exec()

    def _build(self, corpo: str, tema: str = "light"):
        c = _cores_tema(tema)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("popup_card")
        self.setStyleSheet("background-color: transparent;")
        card.setStyleSheet(f"""
            QFrame#popup_card {{
                background-color: {c['bg']};
                border-radius: 14px;
                border: 2px solid {c['border']};
            }}
        """)
        shadow_layout = QVBoxLayout(card)
        shadow_layout.setContentsMargins(28, 24, 28, 20)
        shadow_layout.setSpacing(12)

        row_titulo = QHBoxLayout()
        row_titulo.setSpacing(10)

        icone = QLabel("✅")
        f = QFont()
        f.setPointSize(16)
        icone.setFont(f)
        row_titulo.addWidget(icone)

        titulo = QLabel(t("popup.titulo"))
        ft = QFont()
        ft.setPointSize(14)
        ft.setWeight(QFont.Weight.DemiBold)
        titulo.setFont(ft)
        titulo.setStyleSheet(f"color: {c['titulo']};")
        row_titulo.addWidget(titulo, 1)
        shadow_layout.addLayout(row_titulo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {c['sep']};")
        shadow_layout.addWidget(sep)

        lbl_corpo = QLabel(corpo)
        f_corpo = QFont()
        f_corpo.setPointSize(10)
        lbl_corpo.setFont(f_corpo)
        lbl_corpo.setStyleSheet(f"color: {c['corpo']};")
        lbl_corpo.setWordWrap(True)
        lbl_corpo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        shadow_layout.addWidget(lbl_corpo)

        row_btns = QHBoxLayout()
        row_btns.setSpacing(8)
        row_btns.addStretch()

        if self._pasta_destino:
            btn_pasta = QPushButton(t("popup.abrir_pasta"))
            btn_pasta.setFixedHeight(34)
            btn_pasta.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c['btn_sec_bg']};
                    color: {c['btn_sec_fg']};
                    border: 1px solid {c['btn_sec_border']};
                    border-radius: 7px;
                    padding: 0 14px;
                    font-size: 11px;
                }}
                QPushButton:hover   {{ background-color: {c['btn_sec_hover']}; }}
                QPushButton:pressed {{ background-color: {c['btn_sec_pressed']}; }}
            """)
            btn_pasta.clicked.connect(self._abrir_pasta)
            row_btns.addWidget(btn_pasta)

        btn_ok = QPushButton(t("popup.ok"))
        btn_ok.setFixedHeight(34)
        btn_ok.setFixedWidth(80)
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover   { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        btn_ok.clicked.connect(self._fechar_ok)
        btn_ok.setDefault(True)
        row_btns.addWidget(btn_ok)
        shadow_layout.addLayout(row_btns)

        outer.addWidget(card)

    def _fechar_ok(self):
        self.close()
        if callable(self._on_ok):
            self._on_ok()

    def _centralizar(self, parent):
        self.adjustSize()
        pg = parent.geometry()
        x = pg.x() + (pg.width()  - self.width())  // 2
        y = pg.y() + (pg.height() - self.height()) // 2
        self.move(x, y)

    def _abrir_pasta(self):
        pasta = Path(self._pasta_destino) if self._pasta_destino else None
        if pasta and pasta.is_dir():
            abrir_pasta(pasta)
        else:
            QMessageBox.warning(self, t("erro.pasta_nao_encontrada"),
                                t("popup.erro_pasta"))
