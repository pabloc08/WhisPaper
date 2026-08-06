# interface/dialogs/ffmpeg_missing_popup.py


import sys

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QWidget, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui  import QIcon, QPixmap

from settings.i18n             import t
from settings.config_manager   import carregar_config
from workers.ffmpeg_worker     import FFmpegWorker
from utils.ffmpeg_manager      import FFMPEG_TAMANHO_APROX
from utils.theme               import aplicar_flags_dialogo_secundario
from interface.dialogs.welcome_dialog import _CSS_BTN_AZUL, _CSS_BTN_SECUNDARIO


# ── Detecção de tema ─────────────────────────────────────────────────────────

def _is_dark() -> bool:
    try:
        return carregar_config().get("tema", "light") == "dark"
    except Exception:
        return False


# ── CSS dark-aware ────────────────────────────────────────────────────────────

def _css_icon_ring(dark: bool = False) -> str:
    if dark:
        return (
            "QLabel {"
            "  border-radius: 32px;"
            "  background-color: #2A2B30;"
            "  border: 1px solid #3A3B42;"
            "}"
        )
    return (
        "QLabel {"
        "  border-radius: 32px;"
        "  background-color: #f1f5f9;"
        "  border: 1px solid #cbd5e1;"
        "}"
    )


def _css_icon_ring_info(dark: bool = False) -> str:
    if dark:
        return (
            "QLabel {"
            "  border-radius: 32px;"
            "  background-color: #1E2B47;"
            "  border: 1px solid #3A4F7A;"
            "}"
        )
    return (
        "QLabel {"
        "  border-radius: 32px;"
        "  background-color: #dbeafe;"
        "  border: 1px solid #bfdbfe;"
        "}"
    )


def _css_icon_ring_error(dark: bool = False) -> str:
    if dark:
        return (
            "QLabel {"
            "  border-radius: 32px;"
            "  background-color: #2D1A1A;"
            "  border: 1px solid #5C2626;"
            "}"
        )
    return (
        "QLabel {"
        "  border-radius: 32px;"
        "  background-color: #fee2e2;"
        "  border: 1px solid #fecaca;"
        "}"
    )


def _css_badge(dark: bool = False) -> str:
    if dark:
        return (
            "QLabel {"
            "  background-color: #2A2B30;"
            "  color: #8B8F9A;"
            "  border: 1px solid #3A3B42;"
            "  border-radius: 12px;"
            "  font-size: 8pt;"
            "  padding: 3px 10px;"
            "}"
        )
    return (
        "QLabel {"
        "  background-color: #f8fafc;"
        "  color: #64748b;"
        "  border: 1px solid #e2e8f0;"
        "  border-radius: 12px;"
        "  font-size: 8pt;"
        "  padding: 3px 10px;"
        "}"
    )


def _css_progress_bar(dark: bool = False) -> str:
    track = "#2A2B30" if dark else "#e2e8f0"
    return (
        f"QProgressBar {{ background-color: {track}; border: none; border-radius: 3px; }}"
        "QProgressBar::chunk { background-color: #3b82f6; border-radius: 3px; }"
    )


def _css_progress_bar_indeterminate(dark: bool = False) -> str:
    track = "#2A2B30" if dark else "#e2e8f0"
    return (
        f"QProgressBar {{ background-color: {track}; border: none; border-radius: 3px; }}"
        "QProgressBar::chunk { background-color: #93c5fd; border-radius: 3px; }"
    )


def _css_separator(dark: bool = False) -> str:
    color = "#3A3B42" if dark else "#e2e8f0"
    return f"QFrame {{ color: {color}; max-height: 1px; }}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lbl(texto: str, bold=False, cor="", wrap=False, obj="", pt=0) -> QLabel:
    l = QLabel(texto)
    l.setWordWrap(wrap)
    if obj:
        l.setObjectName(obj)
    css = ""
    if bold: css += "font-weight:600;"
    if cor:  css += f"color:{cor};"
    if pt:   css += f"font-size:{pt}pt;"
    if css:  l.setStyleSheet(css)
    return l


def _separador(dark: bool = False) -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(_css_separator(dark))
    return sep


def _icon_ring(icon_path, size=64, css=None) -> QLabel:
    """Cria um label circular com ícone centralizado.

    Aceita tanto caminho de disco (str/Path) quanto recurso Qt (":/icons/...").
    """
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(css or _css_icon_ring())

    pm = QPixmap(str(icon_path)) if icon_path else QPixmap()
    if not pm.isNull():
        pm = pm.scaled(
            size - 20, size - 20,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        lbl.setPixmap(pm)
    else:
        lbl.setText("🎬")
        lbl.setStyleSheet((css or _css_icon_ring()) + "font-size: 20pt;")
    return lbl


class PopupFFmpegAusente(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("ffmpeg_popup.titulo"))
        self.setFixedWidth(380)
        self.setContentsMargins(0, 0, 0, 0)

        aplicar_flags_dialogo_secundario(self)

        _icon = QIcon(":/icons/whispaper.png")
        if not _icon.isNull():
            self.setWindowIcon(_icon)

        self._worker: FFmpegWorker | None = None
        self._baixando = False
        self._build()

    def closeEvent(self, event):
        self._parar_worker()
        event.accept()
        sys.exit(0)

    # ── Estrutura fixa ────────────────────────────────────────────────

    def _build(self):
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        # Área dinâmica
        self._area_widget = QWidget()
        self._area = QVBoxLayout(self._area_widget)
        self._area.setContentsMargins(32, 28, 32, 28)
        self._area.setSpacing(0)
        self._lay.addWidget(self._area_widget)

        self._render()

    # ── Área dinâmica ─────────────────────────────────────────────────

    def _clear(self):
        while self._area.count():
            item = self._area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    s = item.layout().takeAt(0)
                    if s.widget():
                        s.widget().deleteLater()

    def _add_icon_centered(self, icon_path, css=None):
        """Adiciona anel de ícone centralizado."""
        ring = _icon_ring(icon_path, size=64, css=css)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(ring)
        row.addStretch()
        self._area.addLayout(row)
        self._area.addSpacing(16)

    def _add_titulo(self, texto, pt=12):
        t_lbl = _lbl(texto, bold=True, pt=pt)
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._area.addWidget(t_lbl)

    def _add_desc(self, texto, dark: bool = False):
        cor = "#8B8F9A" if dark else "#64748b"
        d = _lbl(texto, wrap=True)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setStyleSheet(f"color: {cor}; font-size: 9pt;")
        self._area.addWidget(d)

    def _render(self):
        """Estado inicial: botão de download (ou instrução Linux)."""
        self._baixando = False
        self._clear()
        dark = _is_dark()

        _ffmpeg_icon = ":/icons/ffmpeg.png"
        self._add_icon_centered(_ffmpeg_icon, css=_css_icon_ring(dark))
        self._add_titulo(t("ffmpeg_popup.titulo"))

        self._area.addSpacing(6)
        self._add_desc(t("ffmpeg_popup.desc"), dark=dark)
        self._area.addSpacing(12)

        if sys.platform == "win32":
            self._render_windows(dark)
        else:
            self._render_linux(dark)

        self.adjustSize()

    def _render_windows(self, dark: bool):
        # Badge com tamanho real do arquivo
        badge = QLabel(f"⬇  {FFMPEG_TAMANHO_APROX()} · gyan.dev")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(_css_badge(dark))
        badge.setFixedHeight(22)
        row_badge = QHBoxLayout()
        row_badge.addStretch()
        row_badge.addWidget(badge)
        row_badge.addStretch()
        self._area.addLayout(row_badge)
        self._area.addSpacing(20)

        btn = QPushButton(t("ffmpeg_popup.btn_baixar"))
        btn.setFixedWidth(200)
        btn.setFixedHeight(36)
        btn.setStyleSheet(_CSS_BTN_AZUL)
        btn.clicked.connect(self._start)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        self._area.addLayout(row)

    def _render_linux(self, dark: bool):
        inst = _lbl(t("ffmpeg_popup.instrucao_linux"), wrap=True)
        inst.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor = "#8B8F9A" if dark else "#64748b"
        inst.setStyleSheet(f"color: {cor}; font-size: 9pt;")
        self._area.addWidget(inst)

        self._area.addSpacing(16)

        btn = QPushButton(t("ffmpeg_popup.btn_fechar"))
        btn.setFixedWidth(200)
        btn.setFixedHeight(36)
        btn.setStyleSheet(_CSS_BTN_SECUNDARIO)
        btn.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        self._area.addLayout(row)

    def _render_baixando(self):
        """Estado de download em andamento."""
        self._baixando = True
        self._clear()
        dark = _is_dark()

        # Ícone de download (anel azul)
        _ffmpeg_icon = ":/icons/ffmpeg.png"
        self._add_icon_centered(_ffmpeg_icon, css=_css_icon_ring_info(dark))

        self._add_titulo(t("ffmpeg_popup.baixando"))
        self._area.addSpacing(16)

        # Barra de progresso
        self._barra = QProgressBar()
        self._barra.setRange(0, 100)
        self._barra.setValue(0)
        self._barra.setFixedHeight(6)
        self._barra.setTextVisible(False)
        self._barra.setStyleSheet(_css_progress_bar(dark))
        self._area.addWidget(self._barra)

        self._area.addSpacing(6)

        # Linha de progresso: MB baixados + percentual
        self._prog_row = QHBoxLayout()
        self._prog_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        mb_cor  = "#8B8F9A" if dark else "#94a3b8"
        pct_cor = "#C9CDD4" if dark else "#64748b"
        self._lbl_mb = QLabel("")
        self._lbl_mb.setStyleSheet(f"color: {mb_cor}; font-size: 8pt;")
        self._lbl_mb.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._lbl_pct = QLabel("")
        self._lbl_pct.setStyleSheet(f"color: {pct_cor}; font-size: 8pt; font-weight: 600;")
        self._lbl_pct.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._prog_row.addWidget(self._lbl_mb)
        self._prog_row.addStretch()
        self._prog_row.addWidget(self._lbl_pct)
        self._area.addLayout(self._prog_row)

        self._area.addSpacing(20)

        btn_cancel = QPushButton(t("ffmpeg_popup.btn_cancelar"))
        btn_cancel.setFixedWidth(200)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(_CSS_BTN_SECUNDARIO)
        btn_cancel.clicked.connect(self._cancel)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_cancel)
        row.addStretch()
        self._area.addLayout(row)

        self.adjustSize()

    # ── Download ──────────────────────────────────────────────────────

    def _parar_worker(self):
        """Sinaliza cancelamento sem bloquear a UI."""
        if self._worker is not None:
            self._worker.cancelar()
            self._worker = None

    def _start(self):
        if self._worker is not None:
            return
        self._render_baixando()

        self._worker = FFmpegWorker()
        self._worker.progresso.connect(self._on_prog)
        self._worker.status.connect(self._on_status)
        self._worker.concluido.connect(self._on_done)
        self._worker.erro.connect(self._on_err)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _cancel(self):
        """Cancela de forma não-bloqueante."""
        if self._worker is not None:
            for i in range(self._area.count()):
                item = self._area.itemAt(i)
                if item and item.layout():
                    lay = item.layout()
                    for j in range(lay.count()):
                        w = lay.itemAt(j)
                        if w and w.widget():
                            w.widget().setEnabled(False)
            self._worker.cancelar()
        else:
            self._render()

    def _on_worker_finished(self):
        was_downloading = self._baixando
        self._baixando = False
        self._worker = None
        if was_downloading:
            self._render()

    def _on_prog(self, pct: int, mb: float):
        if not self._baixando:
            return
        dark = _is_dark()
        if pct >= 0:
            self._barra.setRange(0, 100)
            self._barra.setStyleSheet(_css_progress_bar(dark))
            self._barra.setValue(pct)
            self._lbl_pct.setText(f"{pct}%")
            self._lbl_mb.setText(f"{mb:.1f} MB de {FFMPEG_TAMANHO_APROX()}")
        else:
            self._barra.setRange(0, 0)
            self._barra.setStyleSheet(_css_progress_bar_indeterminate(dark))
            self._lbl_mb.setText(t("ffmpeg.status.baixando_sem_total"))
            self._lbl_pct.setText(f"{mb:.1f} MB")

    def _on_status(self, msg: str):
        if not self._baixando:
            return
        dark = _is_dark()
        if msg == "extraindo":
            self._barra.setRange(0, 0)
            self._barra.setStyleSheet(_css_progress_bar_indeterminate(dark))
            self._lbl_mb.setText(t("ffmpeg.status.extraindo"))
            self._lbl_pct.setText("")
        elif msg.startswith("tentativa:"):
            _, n, total = msg.split(":")
            self._barra.setRange(0, 100)
            self._barra.setStyleSheet(_css_progress_bar(dark))
            self._barra.setValue(0)
            self._lbl_mb.setText(t("ffmpeg.status.tentativa", n=n, total=total))
            self._lbl_pct.setText("")
        elif msg.startswith("aguardando:"):
            s = msg.split(":")[1]
            self._lbl_mb.setText(t("ffmpeg.status.aguardando", s=s))
            self._lbl_pct.setText("")

    def _on_done(self):
        self._baixando = False
        self._clear()
        dark = _is_dark()

        # Ícone de conclusão: anel azul (mesmo tom do "Baixando") — sem verde
        _ffmpeg_icon = ":/icons/ffmpeg.png"
        self._add_icon_centered(_ffmpeg_icon, css=_css_icon_ring_info(dark))

        # Texto "FFmpeg pronto!" na cor azul temática do app
        cor_ok = "#4A9EFF" if dark else "#4f86c6"
        ok = _lbl(t("ffmpeg_popup.ok"), bold=True, cor=cor_ok, pt=11)
        ok.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._area.addWidget(ok)

        self._area.addSpacing(4)

        sub = _lbl(t("ffmpeg_popup.desc_ok") if self._has_translation("ffmpeg_popup.desc_ok")
                   else "Tudo pronto. Você já pode continuar suas transcrições.", wrap=True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor_sub = "#8B8F9A" if dark else "#64748b"
        sub.setStyleSheet(f"color: {cor_sub}; font-size: 9pt;")
        self._area.addWidget(sub)

        self._area.addSpacing(20)

        btn = QPushButton(t("ffmpeg_popup.btn_continuar"))
        btn.setFixedWidth(200)
        btn.setFixedHeight(36)
        btn.setStyleSheet(_CSS_BTN_AZUL)
        btn.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        self._area.addLayout(row)

        self.adjustSize()

    def _on_err(self, msg: str):
        self._baixando = False
        self._clear()
        dark = _is_dark()

        # Ícone de erro
        _ffmpeg_icon = ":/icons/ffmpeg.png"
        self._add_icon_centered(_ffmpeg_icon, css=_css_icon_ring_error(dark))

        cor_err = "#FF6B6B" if dark else "#dc2626"
        err_title = _lbl(t("ffmpeg_popup.erro_titulo") if self._has_translation("ffmpeg_popup.erro_titulo")
                         else "Falha no download", bold=True, cor=cor_err, pt=11)
        err_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._area.addWidget(err_title)

        self._area.addSpacing(6)

        err_desc = _lbl(msg, wrap=True)
        err_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor_desc = "#8B8F9A" if dark else "#94a3b8"
        err_desc.setStyleSheet(f"color: {cor_desc}; font-size: 9pt;")
        self._area.addWidget(err_desc)

        self._area.addSpacing(20)

        btn = QPushButton(t("ffmpeg_popup.btn_tentar_novamente"))
        btn.setFixedWidth(200)
        btn.setFixedHeight(36)
        btn.setStyleSheet(_CSS_BTN_AZUL)
        btn.clicked.connect(self._render)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        self._area.addLayout(row)

        self.adjustSize()

    @staticmethod
    def _has_translation(key: str) -> bool:
        """Verifica se uma chave i18n existe sem lançar exceção."""
        try:
            result = t(key)
            return result != key
        except Exception:
            return False
