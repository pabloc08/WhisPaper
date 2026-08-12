# interface/dialogs/welcome_dialog.py
# wizard de boas-vindas: FFmpeg (se ausente) + tutorial

import sys

from interface.combo_box import ComboBoxPosicaoFixa
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QProgressBar,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui  import QIcon, QPixmap

from settings.i18n           import t
from settings.config_manager import carregar_config, salvar_config
from utils.ffmpeg_manager    import ffmpeg_instalado, FFMPEG_TAMANHO_APROX
from utils.theme             import aplicar_flags_dialogo_secundario
from utils.flags             import icone_bandeira_brasil, icone_bandeira_eua
from workers.ffmpeg_worker   import FFmpegWorker


# ──────────────────────────────────────────────────────────────────────────────
# estilos de botão compartilhados
# ──────────────────────────────────────────────────────────────────────────────

_CSS_BTN_AZUL = (
    "QPushButton {"
    "  background-color: #3b82f6;"
    "  color: #ffffff;"
    "  border: none;"
    "  border-radius: 10px;"
    "  font-size: 9pt;"
    "  font-weight: 600;"
    "  padding: 0 16px;"
    "}"
    "QPushButton:hover   { background-color: #2563eb; }"
    "QPushButton:pressed { background-color: #1d4ed8; }"
)

# mesma tonalidade do botão "?"/engrenagens, pra não destoar
_CSS_BTN_AZUL_SUAVE = (
    "QPushButton {"
    "  background-color: #5b9bd5;"
    "  color: #ffffff;"
    "  border: none;"
    "  border-radius: 10px;"
    "  font-size: 9pt;"
    "  font-weight: 600;"
    "  padding: 0 16px;"
    "}"
    "QPushButton:hover   { background-color: #4a87c2; }"
    "QPushButton:pressed { background-color: #3a72a8; }"
)

_CSS_BTN_SECUNDARIO = (
    "QPushButton {"
    "  background-color: transparent;"
    "  color: #64748b;"
    "  border: 1.5px solid #cbd5e1;"
    "  border-radius: 10px;"
    "  font-size: 9pt;"
    "  font-weight: 600;"
    "  padding: 0 16px;"
    "}"
    "QPushButton:hover   { background-color: #f1f5f9; border-color: #94a3b8; }"
    "QPushButton:pressed { background-color: #e2e8f0; }"
)

# variante dark — a original não segue o tema e o hover ficava claro demais
_CSS_BTN_SECUNDARIO_DARK = (
    "QPushButton {"
    "  background-color: transparent;"
    "  color: #8B8F9A;"
    "  border: 1.5px solid #3A3B42;"
    "  border-radius: 10px;"
    "  font-size: 9pt;"
    "  font-weight: 600;"
    "  padding: 0 16px;"
    "}"
    "QPushButton:hover   { background-color: #2A2B30; border-color: #4A4F5C; }"
    "QPushButton:pressed { background-color: #212227; }"
)


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Plain)
    return f


def _lbl(texto: str, bold: bool = False, pt: int = 0,
         cor: str = "", wrap: bool = False,
         obj: str = "") -> QLabel:
    l = QLabel(texto)
    l.setWordWrap(wrap)
    l.setTextFormat(Qt.TextFormat.RichText)
    if obj:
        l.setObjectName(obj)
    css = ""
    if bold: css += "font-weight:600;"
    if pt:   css += f"font-size:{pt}pt;"
    if cor:  css += f"color:{cor};"
    if css:  l.setStyleSheet(css)
    return l


def _gear_icon() -> QIcon:
    icon = QIcon(":/icons/settings.png")
    return icon if not icon.isNull() else QIcon()


def _gear_pixmap(size: int = 14) -> QPixmap | None:
    pm = QPixmap(":/icons/settings.png")
    if not pm.isNull():
        return pm.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# indicador de passos
# ──────────────────────────────────────────────────────────────────────────────

class _Indicador(QWidget):
    _ATIVO        = "#3b82f6"
    _INATIVO      = "#cbd5e1"
    _ATIVO_DARK   = "#5B8CFF"
    _INATIVO_DARK = "#3A3B42"

    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self._atual = 0
        try:
            self._escuro = carregar_config().get("tema", "light") == "dark"
        except Exception:
            self._escuro = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dots: list[QLabel] = []
        for _ in range(total):
            d = QLabel()
            d.setFixedSize(8, 8)
            self._dots.append(d)
            lay.addWidget(d)
        from PySide6.QtWidgets import QSizePolicy as _SP
        self.setSizePolicy(_SP.Policy.Fixed, _SP.Policy.Fixed)
        self._refresh()

    def set_passo(self, idx: int):
        self._atual = idx
        self._refresh()

    def set_tema(self, escuro: bool):
        """Atualiza o tema em memória e repinta — sem leitura de disco."""
        self._escuro = escuro
        self._refresh()

    def _refresh(self):
        ca = self._ATIVO_DARK   if self._escuro else self._ATIVO
        ci = self._INATIVO_DARK if self._escuro else self._INATIVO
        for i, d in enumerate(self._dots):
            c = ca if i == self._atual else ci
            d.setStyleSheet(f"background:{c};border-radius:4px;")


# ──────────────────────────────────────────────────────────────────────────────
# passo 0 — preferências (idioma + tema)
# ──────────────────────────────────────────────────────────────────────────────

class _PassoPreferencias(QWidget):
    def __init__(self, on_tema_mudou=None, on_idioma_mudou=None):
        super().__init__()
        self._on_tema_mudou   = on_tema_mudou
        self._on_idioma_mudou = on_idioma_mudou
        self._build()

    # ── build (executado uma única vez) ───────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Stretch pequeno: logo fica no terço superior ───────────────
        lay.addStretch(1)

        # ── Ícone ─────────────────────────────────────────────────────
        ico = QLabel()
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(":/icons/whispaper.png")
        if not pm.isNull():
            pm = pm.scaled(
                80, 80,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ico.setPixmap(pm)
        else:
            ico.setText("🎙️")
            ico.setObjectName("label_app_icon")
        lay.addWidget(ico, alignment=Qt.AlignmentFlag.AlignHCenter)

        lay.addSpacing(8)

        # ── Nome ──────────────────────────────────────────────────────
        nome = QLabel("WhisPaper")
        nome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nome.setObjectName("label_app_nome")
        lay.addWidget(nome)

        lay.addSpacing(4)

        # ── Hint / tagline ────────────────────────────────────────────
        self._lbl_hint = QLabel(t("boas_vindas.prefs.hint"))
        self._lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_hint.setWordWrap(True)
        self._lbl_hint.setObjectName("label_app_hint")
        lay.addWidget(self._lbl_hint)

        # ── Stretch maior: separa logo dos controles ───────────────────
        lay.addStretch(2)

        # ── Controles ─────────────────────────────────────────────────
        try:
            cfg           = carregar_config()
            _idioma_atual = cfg.get("idioma_app", "pt_BR")
            _tema_atual   = cfg.get("tema", "light")
        except Exception:
            _idioma_atual = "pt_BR"
            _tema_atual   = "light"

        form = QVBoxLayout()
        form.setSpacing(10)
        form.setContentsMargins(24, 0, 24, 0)

        # — Card idioma —
        card_idioma = QFrame()
        card_idioma.setObjectName("prefs_card")
        ci_lay = QVBoxLayout(card_idioma)
        ci_lay.setContentsMargins(14, 10, 14, 10)
        ci_lay.setSpacing(6)
        self._lbl_idioma = QLabel(t("boas_vindas.prefs.idioma"))
        self._lbl_idioma.setObjectName("label_prefs_secao")
        ci_lay.addWidget(self._lbl_idioma)
        self._combo_idioma = ComboBoxPosicaoFixa()
        # bandeiras via QPainter, não emoji — Qt não compõe os regional indicators certo no Windows
        _tamanho_bandeira = QSize(20, 14)
        self._combo_idioma.setIconSize(_tamanho_bandeira)
        self._combo_idioma.addItem(icone_bandeira_brasil(_tamanho_bandeira), "  Português", "pt_BR")
        self._combo_idioma.addItem(icone_bandeira_eua(_tamanho_bandeira),    "  English",   "en_US")
        self._combo_idioma.setCurrentIndex(0 if _idioma_atual == "pt_BR" else 1)
        self._combo_idioma.currentIndexChanged.connect(self._sel_idioma)
        ci_lay.addWidget(self._combo_idioma)
        form.addWidget(card_idioma)

        # — Card tema —
        card_tema = QFrame()
        card_tema.setObjectName("prefs_card")
        ct_lay = QVBoxLayout(card_tema)
        ct_lay.setContentsMargins(14, 10, 14, 10)
        ct_lay.setSpacing(6)
        self._lbl_tema = QLabel(t("boas_vindas.prefs.tema"))
        self._lbl_tema.setObjectName("label_prefs_secao")
        ct_lay.addWidget(self._lbl_tema)
        self._combo_tema = ComboBoxPosicaoFixa()
        self._combo_tema.addItem(t("boas_vindas.prefs.tema_claro"), "light")
        self._combo_tema.addItem(t("boas_vindas.prefs.tema_escuro"), "dark")
        self._combo_tema.setCurrentIndex(0 if _tema_atual == "light" else 1)
        self._combo_tema.currentIndexChanged.connect(self._sel_tema)
        ct_lay.addWidget(self._combo_tema)
        form.addWidget(card_tema)

        lay.addLayout(form)
        lay.addStretch(2)

    # ── atualizar textos sem reconstruir o widget ─────────────────────

    def atualizar_textos(self):
        """Atualiza apenas os strings que dependem do idioma. Sem rebuild."""
        self._lbl_hint.setText(t("boas_vindas.prefs.hint"))
        self._lbl_idioma.setText(t("boas_vindas.prefs.idioma"))
        self._lbl_tema.setText(t("boas_vindas.prefs.tema"))
        # Itens do combo de tema também são traduzíveis
        self._combo_tema.setItemText(0, t("boas_vindas.prefs.tema_claro"))
        self._combo_tema.setItemText(1, t("boas_vindas.prefs.tema_escuro"))

    # ── slots ─────────────────────────────────────────────────────────

    def _sel_idioma(self, idx: int):
        codigo = self._combo_idioma.itemData(idx)
        cfg = carregar_config()
        cfg["idioma_app"] = codigo
        salvar_config(cfg)
        from settings.i18n import init_i18n
        init_i18n(codigo)
        # Atualiza apenas os textos que mudaram — sem reconstruir nada
        self.atualizar_textos()
        if self._on_idioma_mudou:
            self._on_idioma_mudou(codigo)

    def _sel_tema(self, idx: int):
        tema = self._combo_tema.itemData(idx)
        cfg = carregar_config()
        cfg["tema"] = tema
        salvar_config(cfg)
        # Aplica o QSS globalmente (inclui o próprio wizard)
        from utils.theme import carregar_qss as _carregar_qss
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.setStyleSheet(_carregar_qss(tema))
        if self._on_tema_mudou:
            self._on_tema_mudou(tema)


# ──────────────────────────────────────────────────────────────────────────────
# passo 1 — FFmpeg (visual idêntico ao PopupFFmpegAusente)
# ──────────────────────────────────────────────────────────────────────────────

# ── CSS dos anéis de ícone (dark-aware) ──────────────────────────────────────

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


def _css_code_block(dark: bool = False) -> str:
    if dark:
        return (
            "QLabel {"
            "  background-color: #0D1117;"
            "  color: #C9CDD4;"
            "  border-radius: 6px;"
            "  font-family: 'Consolas', 'Courier New', monospace;"
            "  font-size: 9pt;"
            "  padding: 8px 12px;"
            "}"
        )
    return (
        "QLabel {"
        "  background-color: #1e293b;"
        "  color: #e2e8f0;"
        "  border-radius: 6px;"
        "  font-family: 'Consolas', 'Courier New', monospace;"
        "  font-size: 9pt;"
        "  padding: 8px 12px;"
        "}"
    )


def _is_dark() -> bool:
    try:
        return carregar_config().get("tema", "light") == "dark"
    except Exception:
        return False


def _icon_ring_lbl(icon_path, size: int = 64, css: str = "") -> QLabel:
    """Cria um label circular com ícone centralizado (aceita path de disco ou recurso Qt)."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(css)
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
        lbl.setStyleSheet(css + "font-size: 20pt;")
    return lbl


class _PassoFFmpeg(QWidget):
    def __init__(self, dlg: "JanelaBoasVindas"):
        super().__init__()
        self._dlg    = dlg
        self._worker: FFmpegWorker | None = None
        self._build()

    def _build(self):
        # Layout externo: centraliza o bloco verticalmente
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Bloco com altura fixa — igual em todos os estados, ícone nunca se move
        self._bloco = QWidget()
        self._bloco.setFixedHeight(300)
        self._lay = QVBoxLayout(self._bloco)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        # ── Ícone fixo: ancorado ao topo do bloco ─────────────────────
        _icon_path = ":/icons/ffmpeg.png"
        self._ring = _icon_ring_lbl(_icon_path, size=64, css=_css_icon_ring(False))
        row_ico = QHBoxLayout()
        row_ico.addStretch()
        row_ico.addWidget(self._ring)
        row_ico.addStretch()
        self._lay.addLayout(row_ico)
        self._lay.addSpacing(24)

        # ── Área dinâmica (título, desc, barra, botões) ───────────────
        self._area = QVBoxLayout()
        self._area.setContentsMargins(16, 0, 16, 0)
        self._area.setSpacing(0)
        self._lay.addLayout(self._area)

        # Absorve o espaço sobrante dentro do bloco (abaixo do conteúdo)
        self._lay.addStretch(1)

        outer.addStretch(1)
        outer.addWidget(self._bloco)
        outer.addStretch(1)

        self._render()

    def _set_ring_css(self, css: str):
        """Atualiza apenas o CSS do anel — sem mover nem recriar o widget."""
        self._ring.setStyleSheet(css)

    # ── Limpar ────────────────────────────────────────────────────────

    def _clear(self):
        while self._area.count():
            item = self._area.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                self._clear_layout(item.layout())

    @staticmethod
    def _clear_layout(lay):
        while lay.count():
            s = lay.takeAt(0)
            if s.widget():
                s.widget().setParent(None)
            elif s.layout():
                _PassoFFmpeg._clear_layout(s.layout())

    # ── Helpers de layout ─────────────────────────────────────────────

    def _add_titulo(self, texto: str, bold: bool = True, cor: str = "", pt: int = 12):
        t_lbl = _lbl(texto, bold=bold, cor=cor, pt=pt)
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._area.addWidget(t_lbl)

    def _add_desc(self, texto: str, dark: bool = False):
        cor = "#8B8F9A" if dark else "#64748b"
        d = QLabel(texto)
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setStyleSheet(f"color: {cor}; font-size: 9pt;")
        self._area.addWidget(d)

    # ── Estados ───────────────────────────────────────────────────────

    def _render(self):
        self._clear()
        if ffmpeg_instalado():
            self._state_ok()
            self._dlg._set_ffmpeg_ok(True)
        else:
            self._dlg._set_ffmpeg_ok(False)
            self._state_absent()

    def _state_ok(self):
        dark = _is_dark()
        self._set_ring_css(_css_icon_ring_info(dark))
        cor_ok = "#4A9EFF" if dark else "#4f86c6"
        self._add_titulo(t("boas_vindas.ffmpeg.ok"), cor=cor_ok, pt=11)
        self._area.addSpacing(24)

    def _state_absent(self):
        dark = _is_dark()
        self._set_ring_css(_css_icon_ring(dark))
        self._add_titulo(t("boas_vindas.ffmpeg.titulo") if self._has_t("boas_vindas.ffmpeg.titulo") else "FFmpeg")
        self._area.addSpacing(14)
        self._add_desc(t("boas_vindas.ffmpeg.desc"), dark=dark)
        self._area.addSpacing(28)

        if sys.platform == "win32":
            self._render_absent_windows(dark)
        else:
            self._render_absent_linux(dark)

    def _render_absent_windows(self, dark: bool):
        # Badge com tamanho real do download
        badge = QLabel(f"⬇  {FFMPEG_TAMANHO_APROX()} · gyan.dev")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(_css_badge(dark))
        badge.setFixedHeight(22)
        row_badge = QHBoxLayout()
        row_badge.addStretch()
        row_badge.addWidget(badge)
        row_badge.addStretch()
        self._area.addLayout(row_badge)
        self._area.addSpacing(24)

        self._btn_dl = QPushButton(t("boas_vindas.ffmpeg.btn_baixar"))
        self._btn_dl.setFixedWidth(200)
        self._btn_dl.setFixedHeight(36)
        self._btn_dl.setStyleSheet(_CSS_BTN_AZUL)
        self._btn_dl.clicked.connect(self._start)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self._btn_dl)
        row.addStretch()
        self._area.addLayout(row)

    def _render_absent_linux(self, dark: bool):
        inst = QLabel(t("boas_vindas.ffmpeg.instrucao_linux"))
        inst.setWordWrap(True)
        inst.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cor = "#8B8F9A" if dark else "#64748b"
        inst.setStyleSheet(f"color: {cor}; font-size: 9pt;")
        self._area.addWidget(inst)

    def _state_downloading(self):
        dark = _is_dark()
        self._set_ring_css(_css_icon_ring_info(dark))
        self._add_titulo(t("boas_vindas.ffmpeg.baixando"))
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

        # Linha dupla: MB à esquerda, % à direita
        self._prog_row = QHBoxLayout()
        mb_cor   = "#8B8F9A" if dark else "#94a3b8"
        pct_cor  = "#C9CDD4" if dark else "#64748b"

        self._lbl_mb = QLabel("")
        self._lbl_mb.setStyleSheet(f"color: {mb_cor}; font-size: 8pt;")
        self._lbl_pct = QLabel("")
        self._lbl_pct.setStyleSheet(f"color: {pct_cor}; font-size: 8pt; font-weight: 600;")
        self._lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._prog_row.addWidget(self._lbl_mb)
        self._prog_row.addStretch()
        self._prog_row.addWidget(self._lbl_pct)
        self._area.addLayout(self._prog_row)

        self._area.addSpacing(20)

        # Cancelar
        self._btn_cancel = QPushButton(t("boas_vindas.ffmpeg.btn_cancelar"))
        self._btn_cancel.setFixedWidth(200)
        self._btn_cancel.setFixedHeight(36)
        self._btn_cancel.setStyleSheet(_CSS_BTN_SECUNDARIO)
        self._btn_cancel.clicked.connect(self._cancel)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self._btn_cancel)
        row.addStretch()
        self._area.addLayout(row)

    # ── Download ──────────────────────────────────────────────────────

    def _parar_worker(self):
        """Sinaliza cancelamento e aguarda encerramento da thread."""
        if self._worker is not None:
            self._worker.cancelar()
            self._worker.wait(3000)
            self._worker = None

    def _start(self):
        if self._worker is not None:
            return
        self._clear()
        self._state_downloading()
        self._dlg._set_ant_enabled(False)

        self._worker = FFmpegWorker()
        self._worker.progresso.connect(self._on_prog)
        self._worker.status.connect(self._on_status)
        self._worker.concluido.connect(self._on_done)
        self._worker.erro.connect(self._on_err)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _cancel(self):
        """Cancela de forma não-bloqueante: desabilita o botão e aguarda finished."""
        if self._worker is not None:
            if hasattr(self, "_btn_cancel"):
                self._btn_cancel.setEnabled(False)
            self._worker.cancelar()
        else:
            self._dlg._set_ant_enabled(True)
            self._render()

    def _on_worker_finished(self):
        """Chamado quando a QThread encerra — re-renderiza apenas se foi cancelamento."""
        was_cancelled = self._worker is not None and not ffmpeg_instalado()
        self._worker = None
        self._dlg._set_ant_enabled(True)
        if was_cancelled:
            self._render()

    def _on_prog(self, pct: int, mb: float):
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
        self._clear()
        self._state_ok()
        self._dlg._set_ffmpeg_ok(True)
        self._dlg._atualizar_botoes()

    def _on_err(self, msg: str):
        dark = _is_dark()
        self._dlg._set_ant_enabled(True)
        self._clear()

        self._set_ring_css(_css_icon_ring_error(dark))

        cor_err = "#FF6B6B" if dark else "#dc2626"
        self._add_titulo(
            t("boas_vindas.ffmpeg.erro_titulo") if self._has_t("boas_vindas.ffmpeg.erro_titulo") else t("ffmpeg_popup.erro_titulo") if self._has_t("ffmpeg_popup.erro_titulo") else "Falha no download",
            cor=cor_err, pt=11,
        )

        self._area.addSpacing(6)
        self._add_desc(msg, dark=dark)
        self._area.addSpacing(20)

        btn = QPushButton(t("boas_vindas.ffmpeg.btn_tentar_novamente"))
        btn.setFixedWidth(200)
        btn.setFixedHeight(36)
        btn.setStyleSheet(_CSS_BTN_AZUL)
        btn.clicked.connect(self._render)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        self._area.addLayout(row)

        self._dlg._set_ffmpeg_ok(False)
        self._dlg._atualizar_botoes()

    def atualizar_tema(self, _tema: str = ""):
        """Re-renderiza o passo FFmpeg com o tema atual, se não há download em andamento."""
        if self._worker is None:
            self._render()

    @staticmethod
    def _has_t(key: str) -> bool:
        try:
            return t(key) != key
        except Exception:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# helper — imagem dinâmica por idioma/tema
# ──────────────────────────────────────────────────────────────────────────────

def _img_tutorial(pt_light: str, pt_dark: str,
                  en_light: str, en_dark: str) -> QLabel | None:
    try:
        cfg    = carregar_config()
        dark   = cfg.get("tema", "light") == "dark"
        idioma = cfg.get("idioma_app", "pt_BR")
    except Exception:
        dark   = False
        idioma = "pt_BR"

    nome = (pt_dark if dark else pt_light) if idioma.startswith("pt") \
           else (en_dark if dark else en_light)

    pm = QPixmap(f":/imgs/{nome}")
    if not pm.isNull():
        lbl = QLabel()
        lbl.setPixmap(pm)
        lbl.setStyleSheet("background:transparent;")
        lbl.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        return lbl
    return None


# ──────────────────────────────────────────────────────────────────────────────
# passo 1 — tutorial (scroll único)
# ──────────────────────────────────────────────────────────────────────────────

class _PassoTutorial(QWidget):
    def __init__(self):
        super().__init__()
        self._outer_lay = QVBoxLayout(self)
        self._outer_lay.setContentsMargins(0, 0, 0, 0)
        self._build()

    def _build(self):
        # Remove widgets anteriores imediatamente (setParent evita o flicker do deleteLater assíncrono)
        while self._outer_lay.count():
            item = self._outer_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._outer_lay.addWidget(scroll)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 4, 10, 4)
        lay.setSpacing(0)
        scroll.setWidget(body)

        # ── Título ───────────────────────────────────────────────────
        try:
            _dark = carregar_config().get("tema", "light") == "dark"
        except Exception:
            _dark = False

        titulo_frame = QFrame()
        titulo_frame.setObjectName("tutorial_header")
        if _dark:
            titulo_frame.setStyleSheet(
                "QFrame#tutorial_header {"
                "  background-color: #1E2B47;"
                "  border: 1.5px solid #3A4F7A;"
                "  border-radius: 8px;"
                "}"
            )
        else:
            titulo_frame.setStyleSheet(
                "QFrame#tutorial_header {"
                "  background-color: #f0f7ff;"
                "  border: 1.5px solid #bfdbfe;"
                "  border-radius: 8px;"
                "}"
            )
        titulo_lay = QHBoxLayout(titulo_frame)
        titulo_lay.setContentsMargins(14, 10, 14, 10)

        titulo = QLabel(t("boas_vindas.tutorial.como_usar").upper())
        titulo.setStyleSheet(
            f"background:transparent;"
            f"color:{'#93b8e8' if _dark else '#4f86c6'};"
            f"font-weight:700;"
            f"font-size:10pt;"
            f"letter-spacing:2px;"
        )
        titulo_lay.addWidget(titulo)
        titulo_lay.addStretch()

        lay.addWidget(titulo_frame)
        lay.addSpacing(16)

        # ── Seção: Arquivos ──────────────────────────────────────────
        lay.addWidget(self._arquivos())
        lay.addSpacing(22)
        lay.addWidget(self._divisor())
        lay.addSpacing(18)

        # ── Seção: Engine e Modelos ──────────────────────────────────
        lay.addWidget(self._engine_modelos())
        lay.addSpacing(22)
        lay.addWidget(self._divisor())
        lay.addSpacing(18)

        # ── Seção: Preferências ──────────────────────────────────────
        lay.addWidget(self._preferencias())
        lay.addSpacing(28)
        lay.addWidget(self._frase_final())
        lay.addStretch()

    def atualizar_tema(self, _tema: str = ""):
        """Reconstrói o tutorial inteiro com o tema atual do config."""
        self._build()

    def _frase_final(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addStretch()

        try:
            _dark = carregar_config().get("tema", "light") == "dark"
        except Exception:
            _dark = False

        frase = QLabel(t("boas_vindas.tutorial.frase_final"))
        frase.setStyleSheet(
            f"background:transparent;"
            f"color:{'#93b8e8' if _dark else '#4f86c6'};"
            f"font-weight:600;"
            f"font-size:10pt;"
        )
        lay.addWidget(frase)

        pm = QPixmap(":/icons/feather.png")
        if not pm.isNull():
            pm = pm.scaled(
                18, 18,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ico = QLabel()
            ico.setPixmap(pm)
            ico.setStyleSheet("background:transparent;")
            lay.addWidget(ico)

        lay.addStretch()
        return w

    # ── Seção: Arquivos ───────────────────────────────────────────────

    def _arquivos(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        desc = _lbl(t("boas_vindas.tutorial.arquivos_desc"), wrap=True)
        lay.addWidget(desc)

        return w

    # ── Seção: Engine e Modelos ───────────────────────────────────────

    def _engine_modelos(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        desc = _lbl(t("boas_vindas.tutorial.engine_desc"), wrap=True)
        lay.addWidget(desc)

        lay.addSpacing(2)

        img_lbl = _img_tutorial(
            pt_light="Engine_models_portuguese.png",
            pt_dark="Engine_models_portuguese_dark.png",
            en_light="Engine_models_english.png",
            en_dark="Engine_models_english_dark.png",
        )
        if img_lbl:
            lay.addWidget(img_lbl)
        else:
            lay.addWidget(self._linha("Engine:", "whisper.cpp"))
            lay.addSpacing(6)
            lay.addWidget(self._linha("Modelo:", "large-v3-turbo"))

        lay.addSpacing(6)

        # hint box com a cor de identidade do app, texto com mais contraste que o cinza padrão
        hint = QFrame()
        hint.setObjectName("caixa_dica")
        hl = QHBoxLayout(hint)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(10)

        pm = _gear_pixmap(14)
        if pm:
            gear_lbl = QLabel()
            gear_lbl.setPixmap(pm)
            gear_lbl.setFixedSize(18, 18)
            gear_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gear_lbl.setStyleSheet("background:transparent;")
            hl.addWidget(gear_lbl)
        else:
            hl.addWidget(_lbl("⚙", obj="label_dica"))

        txt = _lbl(t("boas_vindas.tutorial.hint"), obj="label_dica", wrap=True)
        hl.addWidget(txt, stretch=1)

        lay.addWidget(hint)

        return w

    def _divisor(self) -> QFrame:
        """Linha sutil de separação — mais discreta que QFrame HLine padrão."""
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(
            "background-color: rgba(100, 116, 139, 0.18);"
            "border: none;"
        )
        return f

    def _linha(self, label: str, valor: str) -> QFrame:
        f = QFrame()
        f.setObjectName("linha_arquivo")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 9, 10, 9)
        lay.setSpacing(8)

        lbl = _lbl(label, bold=True, obj="label_cinza")
        lbl.setFixedWidth(58)
        lay.addWidget(lbl)

        lay.addWidget(_lbl(valor), stretch=1)

        btn = QPushButton()
        btn.setObjectName("btn_icone")
        btn.setFixedSize(28, 28)
        btn.setEnabled(False)
        btn.setToolTip("Configurações")
        ic = _gear_icon()
        if not ic.isNull():
            btn.setIcon(ic)
            btn.setIconSize(QSize(15, 15))
        else:
            btn.setText("⚙")
        lay.addWidget(btn)

        return f

    # ── Seção: Preferências ───────────────────────────────────────────

    def _preferencias(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        desc = _lbl(t("boas_vindas.tutorial.prefs_desc"), wrap=True)
        lay.addWidget(desc)

        img_lbl = _img_tutorial(
            pt_light="confg buttom_portuguese.png",
            pt_dark="confg buttom_portuguese_dark.png",
            en_light="confg buttom_english.png",
            en_dark="confg buttom_english_dark.png",
        )
        if img_lbl:
            lay.addWidget(img_lbl)

        return w


# ──────────────────────────────────────────────────────────────────────────────
# janela principal
# ──────────────────────────────────────────────────────────────────────────────

class JanelaBoasVindas(QDialog):
    def __init__(self, parent=None, modo_consulta: bool = False):
        super().__init__(parent)
        self.setWindowTitle(t("boas_vindas.titulo"))
        aplicar_flags_dialogo_secundario(self)
        self.setFixedSize(480, 580)

        # Ícone da janela — whispaper.png
        _icon = QIcon(":/icons/whispaper.png")
        if not _icon.isNull():
            self.setWindowIcon(_icon)

        self._modo_consulta = modo_consulta
        self._ffmpeg_ja_ok  = ffmpeg_instalado()
        self._ffmpeg_ok     = self._ffmpeg_ja_ok
        self._passo_atual   = 0

        self._build()
        self._ir_para(0)

    def closeEvent(self, event):
        # Cancela download em andamento antes de fechar
        if self._ffmpeg_p is not None:
            self._ffmpeg_p._parar_worker()
        # No wizard de onboarding (não modo_consulta), fechar = sair do app
        if not self._modo_consulta:
            import sys
            event.accept()
            sys.exit(0)
        super().closeEvent(event)

    # ── Build ─────────────────────────────────────────────────────────

    def _build(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 20)
        raiz.setSpacing(0)

        self._area = QVBoxLayout()
        self._area.setSpacing(0)
        raiz.addLayout(self._area, stretch=1)

        raiz.addSpacing(12)

        self._sep_rodape = _sep()
        raiz.addWidget(self._sep_rodape)
        raiz.addSpacing(10)

        # ── Rodapé: será preenchido em _build_rodape() ────────────────
        self._widget_rodape = QWidget()
        self._rodape_lay = QVBoxLayout(self._widget_rodape)
        self._rodape_lay.setContentsMargins(0, 0, 0, 0)
        self._rodape_lay.setSpacing(0)
        raiz.addWidget(self._widget_rodape)

        # Em modo_consulta: esconde separador e rodapé inteiro
        if self._modo_consulta:
            self._sep_rodape.hide()
            self._widget_rodape.hide()

        # inicializa antes de instanciar _PassoFFmpeg, que pode disparar _atualizar_botoes cedo
        self._btn_ant  = None
        self._btn_prox = None

        # Passo 0 — Preferências (sempre presente no onboarding)
        self._prefs_p  = _PassoPreferencias(
            on_tema_mudou=lambda tema: (
                self._tutorial.atualizar_tema(tema),
                self._ffmpeg_p.atualizar_tema(tema) if self._ffmpeg_p is not None else None,
                self._indicador.set_tema(tema == "dark"),
            ),
            on_idioma_mudou=self._on_idioma_mudou,
        ) if not self._modo_consulta else None
        self._tutorial = _PassoTutorial()
        self._ffmpeg_p = None

        if self._modo_consulta:
            self._passos = [self._tutorial]
        elif self._ffmpeg_ja_ok:
            # Preferências → Tutorial  (2 dots)
            self._passos = [self._prefs_p, self._tutorial]
        else:
            # _passos provisório até instanciar _PassoFFmpeg
            self._passos = [self._tutorial]
            self._ffmpeg_p = _PassoFFmpeg(self)
            self._passos = [self._prefs_p, self._ffmpeg_p, self._tutorial]

        self._build_rodape()

    def _build_rodape(self):
        """Constrói o rodapé correto conforme o número de passos."""
        # Limpa layout anterior (se houver)
        while self._rodape_lay.count():
            item = self._rodape_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    s = item.layout().takeAt(0)
                    if s.widget():
                        s.widget().deleteLater()

        if len(self._passos) == 1:
            # ── Passo único: botão "Entendido" centralizado ───────────
            self._btn_ant  = None
            self._btn_prox = None
            self._indicador = _Indicador(1)  # inerte, nunca exibido

            btn = QPushButton(t("boas_vindas.btn_concluir"))
            btn.setFixedWidth(120)
            btn.clicked.connect(self._concluir)

            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(btn)
            row.addStretch()
            self._rodape_lay.addLayout(row)

        else:
            # ── Múltiplos passos: navegação normal ────────────────────
            nav = QHBoxLayout()
            nav.setSpacing(0)

            # QStackedWidget ocupa o mesmo espaço sempre: fantasma no passo 0 (sem "Anterior"),
            # botão real depois — assim o indicador fica sempre centralizado
            from PySide6.QtWidgets import QStackedWidget
            self._btn_ant_stack = QStackedWidget()
            self._btn_ant_stack.setFixedWidth(90)
            self._btn_ant_stack.setFixedHeight(32)

            self._btn_ant_ghost = QWidget()          # idx 0 — invisível, só ocupa espaço
            self._btn_ant_stack.addWidget(self._btn_ant_ghost)

            self._btn_ant = QPushButton(t("boas_vindas.btn_anterior"))
            self._btn_ant.setObjectName("btn_config_geral")
            self._btn_ant.setFixedWidth(90)
            self._btn_ant.setFixedHeight(32)
            self._btn_ant.clicked.connect(self._prev)
            self._btn_ant_stack.addWidget(self._btn_ant)         # idx 1 — real

            self._btn_ant_stack.setCurrentIndex(0)               # começa no fantasma
            nav.addWidget(self._btn_ant_stack)

            nav.addStretch(1)

            self._indicador = _Indicador(len(self._passos))
            nav.addWidget(self._indicador, alignment=Qt.AlignmentFlag.AlignCenter)

            nav.addStretch(1)

            self._btn_prox = QPushButton(t("boas_vindas.btn_proximo"))
            self._btn_prox.setFixedWidth(90)
            self._btn_prox.setFixedHeight(32)
            self._btn_prox.clicked.connect(self._next)
            nav.addWidget(self._btn_prox)

            self._rodape_lay.addLayout(nav)

    # ── Navegação ─────────────────────────────────────────────────────

    def _ir_para(self, idx: int):
        while self._area.count():
            item = self._area.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._passo_atual = idx
        self._area.addWidget(self._passos[idx])
        self._indicador.set_passo(idx)
        self._atualizar_botoes()

    def _next(self):
        if self._passo_atual == len(self._passos) - 1:
            self._concluir()
        else:
            self._ir_para(self._passo_atual + 1)

    def _prev(self):
        if self._passo_atual > 0:
            self._ir_para(self._passo_atual - 1)

    def _atualizar_botoes(self):
        if self._modo_consulta:
            return
        if self._btn_ant is None or self._btn_prox is None:
            return

        ultimo = self._passo_atual == len(self._passos) - 1

        # alterna entre fantasma e botão real, mantendo os dots centrados
        self._btn_ant_stack.setCurrentIndex(1 if self._passo_atual > 0 else 0)

        self._btn_prox.setText(
            t("boas_vindas.btn_concluir") if ultimo else t("boas_vindas.btn_proximo")
        )

        passo_ffmpeg = self._ffmpeg_p is not None and self._passos[self._passo_atual] is self._ffmpeg_p
        bloqueado = passo_ffmpeg and not self._ffmpeg_ja_ok and not self._ffmpeg_ok
        self._btn_prox.setEnabled(not bloqueado)

    def _set_ffmpeg_ok(self, ok: bool):
        self._ffmpeg_ok = ok
        self._atualizar_botoes()

    def _set_ant_enabled(self, enabled: bool):
        """Habilita ou desabilita o botão Anterior (usado durante o download)."""
        if self._btn_ant is not None:
            self._btn_ant.setEnabled(enabled)

    def _on_idioma_mudou(self, _codigo: str):
        """Atualiza título da janela e reconstrói o tutorial com o novo idioma."""
        self.setWindowTitle(t("boas_vindas.titulo"))
        # Atualiza texto dos botões de navegação
        if self._btn_ant is not None:
            self._btn_ant.setText(t("boas_vindas.btn_anterior"))
        if self._btn_prox is not None:
            ultimo = self._passo_atual == len(self._passos) - 1
            self._btn_prox.setText(
                t("boas_vindas.btn_concluir") if ultimo else t("boas_vindas.btn_proximo")
            )
        # Reconstrói o tutorial e o passo FFmpeg (textos dependem do idioma)
        self._tutorial.atualizar_tema()
        if self._ffmpeg_p is not None and self._ffmpeg_p._worker is None:
            self._ffmpeg_p.atualizar_tema()

    # ── Conclusão ─────────────────────────────────────────────────────

    def _concluir(self):
        cfg = carregar_config()
        cfg["onboarding_concluido"] = True
        salvar_config(cfg)
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# utilitário — main.py
# ──────────────────────────────────────────────────────────────────────────────

def deve_mostrar_boas_vindas() -> bool:
    cfg = carregar_config()
    if not cfg.get("onboarding_concluido", False):
        return True   # primeira vez → wizard sempre
    return False      # já abriu antes → deixa o main.py decidir pelo ffmpeg
