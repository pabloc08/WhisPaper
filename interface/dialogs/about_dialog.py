# interface/dialogs/about_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui  import QIcon, QPixmap, QDesktopServices

from settings.i18n        import t
from settings.constants   import VERSAO_APP, PROJECT_URL
from utils.theme          import aplicar_flags_dialogo_secundario

# Reutiliza os botões já definidos no wizard
from interface.dialogs.welcome_dialog import (
    _CSS_BTN_AZUL,
    _CSS_BTN_AZUL_SUAVE,
    _CSS_BTN_SECUNDARIO,
    _CSS_BTN_SECUNDARIO_DARK,
    JanelaBoasVindas,
)




# ── Janela ────────────────────────────────────────────────────────────────────

class JanelaSobre(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("sobre.titulo") if self._has_t("sobre.titulo") else "Sobre")
        self.setFixedWidth(380)
        self.setSizeGripEnabled(False)

        aplicar_flags_dialogo_secundario(self)

        _icon = QIcon(":/icons/whispaper.png")
        if not _icon.isNull():
            self.setWindowIcon(_icon)

        self._build()

    # ── Construção ────────────────────────────────────────────────────

    def _build(self):
        dark = getattr(self.parent(), "configs", {}).get("tema", "light") == "dark"

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 28)
        root.setSpacing(0)

        # ── Ícone do app ──────────────────────────────────────────────
        icon_path = ":/icons/whispaper.png"
        pm = QPixmap(icon_path)
        if not pm.isNull():
            pm = pm.scaled(
                72, 72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_lbl = QLabel()
            icon_lbl.setPixmap(pm)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent;")
            root.addWidget(icon_lbl)
            root.addSpacing(14)

        # ── Nome + versão ─────────────────────────────────────────────
        nome = QLabel("WhisPaper")
        nome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor_nome = "#E8EAF0" if dark else "#1e293b"
        nome.setStyleSheet(
            f"font-size: 16pt; font-weight: 700; color: {cor_nome}; background: transparent;"
        )
        root.addWidget(nome)

        root.addSpacing(4)

        versao = QLabel(f"v{VERSAO_APP}")
        versao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor_versao = "#6B7280" if dark else "#94a3b8"
        versao.setStyleSheet(
            f"font-size: 8pt; color: {cor_versao}; background: transparent;"
        )
        root.addWidget(versao)

        root.addSpacing(20)

        # ── Divisor ───────────────────────────────────────────────────
        from PySide6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        cor_sep = "#3A3B42" if dark else "#e2e8f0"
        sep.setStyleSheet(f"color: {cor_sep}; max-height: 1px;")
        root.addWidget(sep)

        root.addSpacing(20)

        # ── Descrição ─────────────────────────────────────────────────
        desc_txt = (
            t("sobre.desc")
            if self._has_t("sobre.desc")
            else "Feito por Pablo C. Um projeto pessoal em Python que virou open source\n"
                 "— transcrição local, simples e offline."
        )
        desc = QLabel(desc_txt)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor_desc = "#8B8F9A" if dark else "#64748b"
        desc.setStyleSheet(
            f"font-size: 9pt; color: {cor_desc}; background: transparent; line-height: 1.5;"
        )
        root.addWidget(desc)

        root.addSpacing(28)

        # ── Botões ────────────────────────────────────────────────────
        btn_como_usar = QPushButton(
            t("sobre.btn_como_usar") if self._has_t("sobre.btn_como_usar") else "Como usar"
        )
        btn_como_usar.setFixedHeight(36)
        btn_como_usar.setStyleSheet(_CSS_BTN_AZUL_SUAVE)
        btn_como_usar.clicked.connect(self._abrir_tutorial)

        btn_docs = QPushButton(
            t("sobre.btn_docs") if self._has_t("sobre.btn_docs") else "Ver no GitHub"
        )
        btn_docs.setFixedHeight(36)
        btn_docs.setStyleSheet(_CSS_BTN_SECUNDARIO_DARK if dark else _CSS_BTN_SECUNDARIO)
        btn_docs.clicked.connect(self._abrir_docs)

        row_btns = QHBoxLayout()
        row_btns.setSpacing(10)
        row_btns.addWidget(btn_como_usar)
        row_btns.addWidget(btn_docs)
        root.addLayout(row_btns)

        self.adjustSize()

    # ── Ações ─────────────────────────────────────────────────────────

    def _abrir_tutorial(self):
        self.accept()
        dlg = JanelaBoasVindas(self.parent(), modo_consulta=True)
        dlg.exec()

    def _abrir_docs(self):
        QDesktopServices.openUrl(QUrl(PROJECT_URL))

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _has_t(key: str) -> bool:
        try:
            return t(key) != key
        except Exception:
            return False
