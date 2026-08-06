# interface/dialogs/invalid_folder_popup.py

from PySide6.QtWidgets import (
    QDialog, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from settings.i18n import t


def _cores_tema(tema: str = "light") -> dict:
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


class PopupPastaInvalida(QDialog):
    """
    Aviso exibido no startup quando a pasta de saída salva não existe mais.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(t("pasta.invalida_titulo"))
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        tema = getattr(parent, "configs", {}).get("tema", "light")
        self._build(tema)
        self.adjustSize()
        self._centralizar(parent)

    def _build(self, tema: str = "light"):
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

        icone = QLabel("⚠️")
        f = QFont()
        f.setPointSize(16)
        icone.setFont(f)
        row_titulo.addWidget(icone)

        titulo = QLabel(t("pasta.invalida_titulo"))
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

        lbl_corpo = QLabel(t("pasta.invalida_corpo"))
        f_corpo = QFont()
        f_corpo.setPointSize(10)
        lbl_corpo.setFont(f_corpo)
        lbl_corpo.setStyleSheet(f"color: {c['corpo']};")
        lbl_corpo.setWordWrap(True)
        shadow_layout.addWidget(lbl_corpo)

        row_btns = QHBoxLayout()
        row_btns.setSpacing(8)
        row_btns.addStretch()

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
        btn_ok.clicked.connect(self.accept)
        btn_ok.setDefault(True)
        row_btns.addWidget(btn_ok)
        shadow_layout.addLayout(row_btns)

        outer.addWidget(card)

    def _centralizar(self, parent):
        self.adjustSize()
        pg = parent.geometry()
        x = pg.x() + (pg.width()  - self.width())  // 2
        y = pg.y() + (pg.height() - self.height()) // 2
        self.move(x, y)
