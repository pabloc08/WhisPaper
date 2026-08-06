# interface/dialogs/engine_config_dialog.py

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QCheckBox, QFrame
from interface.combo_box import ComboBoxPosicaoFixa
from PySide6.QtCore import Qt

from settings.constants import IDIOMAS_AUDIO_CODIGOS, TRADUCAO_OPCOES
from settings.i18n import t
from transcriber.managers.engine_manager import EngineManager
from utils.theme import aplicar_flags_dialogo_secundario


class JanelaConfigEngine(QDialog):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(t("config_engine.titulo"))
        self.setFixedSize(380, 440)
        self.setWindowIcon(parent.windowIcon())
        aplicar_flags_dialogo_secundario(self)
        self._construir()

    def _construir(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(6)

        engine_id = self.app.engine_id
        tema      = self.app.configs.get("tema", "light")
        cor_hint  = "#64748b" if tema == "light" else "#7d8fa3"
        cor_sep   = "#cbd5e1" if tema == "light" else "#334155"

        # Instância única da engine — usada para checar supports_gpu e supports_vad
        try:
            engine_inst = EngineManager.get(engine_id)
        except Exception:
            engine_inst = None

        # ── Idioma do áudio ──────────────────────────────────────────────────
        lbl_idioma = QLabel(t("config_engine.idioma_audio"))
        lbl_idioma.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_idioma)

        self.combo_idioma = ComboBoxPosicaoFixa()
        self.combo_idioma.setFixedWidth(220)
        self.combo_idioma.setMinimumHeight(34)
        for codigo in IDIOMAS_AUDIO_CODIGOS:
            self.combo_idioma.addItem(t(f"idioma.{codigo}"), userData=codigo)

        idx = self.combo_idioma.findData(self.app.language)
        if idx >= 0:
            self.combo_idioma.setCurrentIndex(idx)

        self.combo_idioma.currentIndexChanged.connect(self._alterar_idioma)
        layout.addWidget(self.combo_idioma)

        layout.addSpacing(14)

        # ── Tradução ─────────────────────────────────────────────────────────
        lbl_trad = QLabel(t("config_engine.traducao"))
        lbl_trad.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_trad)

        codigos = TRADUCAO_OPCOES.get(engine_id, ["disabled"])

        self.combo_traducao = ComboBoxPosicaoFixa()
        self.combo_traducao.setFixedWidth(220)
        self.combo_traducao.setMinimumHeight(34)
        for codigo in codigos:
            if codigo == "disabled":
                self.combo_traducao.addItem(t("config_engine.desativado"), userData="disabled")
            else:
                self.combo_traducao.addItem(t(f"idioma.{codigo}"), userData=codigo)

        alvo = "en" if self.app.task == "translate" else "disabled"
        idx_trad = self.combo_traducao.findData(alvo)
        if idx_trad >= 0:
            self.combo_traducao.setCurrentIndex(idx_trad)

        self.combo_traducao.currentIndexChanged.connect(self._alterar_traducao)

        if len(codigos) == 1:
            self.combo_traducao.setEnabled(False)
        layout.addWidget(self.combo_traducao)

        if len(codigos) == 1:
            aviso = QLabel(t("config_engine.sem_traducao"))
            aviso.setObjectName("label_cinza")
            layout.addWidget(aviso)

        layout.addSpacing(8)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"color: {cor_sep};")
        layout.addWidget(sep)
        layout.addSpacing(10)

        # ── Aceleração GPU ───────────────────────────────────────────────────
        if engine_inst is not None and getattr(engine_inst, "supports_gpu", False):
            lbl_gpu = QLabel(t("config_engine.gpu"))
            lbl_gpu.setStyleSheet("font-weight: bold;")
            layout.addWidget(lbl_gpu)

            self.chk_gpu = QCheckBox(t("config_engine.gpu_desc"))
            self.chk_gpu.setChecked(bool(self.app.usar_gpu))
            self.chk_gpu.toggled.connect(self._alterar_gpu)
            layout.addWidget(self.chk_gpu)

            aviso_gpu = QLabel(t("config_engine.gpu_aviso"))
            aviso_gpu.setStyleSheet(f"color: {cor_hint}; font-size: 11px;")
            aviso_gpu.setWordWrap(True)
            layout.addWidget(aviso_gpu)

            layout.addSpacing(12)

        # ── VAD filter ───────────────────────────────────────────────────────
        if engine_inst is not None and getattr(engine_inst, "supports_vad", False):
            layout.addSpacing(4)

            lbl_vad = QLabel(t("config_engine.vad"))
            lbl_vad.setStyleSheet("font-weight: bold;")
            layout.addWidget(lbl_vad)

            self.chk_vad = QCheckBox(t("config_engine.vad_desc"))
            self.chk_vad.setChecked(bool(self.app.vad_filter))
            self.chk_vad.toggled.connect(self._alterar_vad)
            layout.addWidget(self.chk_vad)

            aviso_vad = QLabel(t("config_engine.vad_aviso"))
            aviso_vad.setStyleSheet(f"color: {cor_hint}; font-size: 11px;")
            aviso_vad.setWordWrap(True)
            layout.addWidget(aviso_vad)

        layout.addSpacing(12)
        layout.addSpacing(8)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        sep2.setStyleSheet(f"color: {cor_sep};")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        # ── Versão do binário ────────────────────────────────────────────────
        if engine_id == "whispercpp":
            from transcriber.engines.whispercpp_engine import VERSAO_BINARIO
            versao = QLabel(f"Whisper.cpp v{VERSAO_BINARIO}")
            versao.setStyleSheet("color: #94a3b8; font-size: 11px;")
            layout.addWidget(versao, alignment=Qt.AlignmentFlag.AlignLeft)

    def _alterar_idioma(self):
        codigo = self.combo_idioma.currentData()
        self.app.language = codigo
        self.app.salvar_configuracoes()

    def _alterar_traducao(self):
        codigo = self.combo_traducao.currentData()
        self.app.task = "translate" if codigo != "disabled" else "transcribe"
        self.app.salvar_configuracoes()

    def _alterar_vad(self, ativo: bool):
        self.app.vad_filter = ativo
        self.app.salvar_configuracoes()

    def _alterar_gpu(self, ativo: bool):
        self.app.usar_gpu = ativo
        self.app.salvar_configuracoes()
