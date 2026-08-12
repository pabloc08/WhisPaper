# interface/dialogs/engine_config_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox, QFrame, QToolButton, QWidget,
)
from interface.combo_box import ComboBoxPosicaoFixa
from PySide6.QtCore import Qt

from settings.constants import IDIOMAS_AUDIO_CODIGOS, TRADUCAO_OPCOES
from settings.i18n import t
from transcriber.managers.engine_manager import EngineManager
from utils.theme import aplicar_flags_dialogo_secundario

# Opções expostas no combo de Temperature (valor, é o padrão do whisper.cpp?)
_OPCOES_TEMPERATURE = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
_TEMPERATURE_PADRAO  = 0.0

# Opções expostas no combo de Beam Size (-1 = desativado/greedy decoding)
_OPCOES_BEAM_SIZE = [-1, 1, 3, 5, 8]
_BEAM_SIZE_PADRAO = 5


class JanelaConfigEngine(QDialog):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(t("config_engine.titulo"))
        self.setFixedWidth(560)
        self.setWindowIcon(parent.windowIcon())
        aplicar_flags_dialogo_secundario(self)
        self._construir()

    def _construir(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(6)
        # altura segue o conteúdo (painel avançado expande/recolhe); só a largura é fixa
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

        engine_id = self.app.engine_id
        tema      = self.app.configs.get("tema", "light")
        cor_hint  = "#64748b" if tema == "light" else "#7d8fa3"
        cor_sep   = "#cbd5e1" if tema == "light" else "#334155"

        # instância única, só pra checar supports_gpu/supports_vad
        try:
            engine_inst = EngineManager.get(engine_id)
        except Exception:
            engine_inst = None

        # ── Idioma do áudio ──────────────────────────────────────────────────
        lbl_idioma = QLabel(t("config_engine.idioma_audio"))
        lbl_idioma.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_idioma)

        self.combo_idioma = ComboBoxPosicaoFixa()
        self.combo_idioma.setFixedWidth(380)
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
        self.combo_traducao.setFixedWidth(380)
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
        layout.addSpacing(14)

        # ── Opções Avançadas (temperature / beam size) ──────────────────────
        self._texto_base_avancado = t("config_engine.opcoes_avancadas")

        self.btn_avancado = QToolButton()
        self.btn_avancado.setCheckable(True)
        self.btn_avancado.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_avancado.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.btn_avancado.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 0; }"
        )
        layout.addWidget(self.btn_avancado)

        self.painel_avancado = QWidget()
        painel_layout = QVBoxLayout(self.painel_avancado)
        painel_layout.setContentsMargins(0, 10, 0, 0)
        painel_layout.setSpacing(6)

        # Temperature
        lbl_temp = QLabel(t("config_engine.temperature"))
        lbl_temp.setStyleSheet("font-weight: bold;")
        painel_layout.addWidget(lbl_temp)

        palavra_padrao = t("config_engine.valor_padrao")

        self.combo_temperature = ComboBoxPosicaoFixa()
        self.combo_temperature.setFixedWidth(380)
        self.combo_temperature.setMinimumHeight(34)
        for valor in _OPCOES_TEMPERATURE:
            rotulo = f"{valor:.1f}"
            if valor == _TEMPERATURE_PADRAO:
                rotulo += f" ({palavra_padrao})"
            self.combo_temperature.addItem(rotulo, userData=valor)

        temperature_atual = float(getattr(self.app, "temperature", _TEMPERATURE_PADRAO))
        idx_temp = self.combo_temperature.findData(temperature_atual)
        self.combo_temperature.setCurrentIndex(idx_temp if idx_temp >= 0 else 0)
        self.combo_temperature.currentIndexChanged.connect(self._alterar_temperature)
        painel_layout.addWidget(self.combo_temperature)

        aviso_temp = QLabel(t("config_engine.temperature_aviso"))
        aviso_temp.setStyleSheet(f"color: {cor_hint}; font-size: 11px;")
        aviso_temp.setWordWrap(True)
        painel_layout.addWidget(aviso_temp)

        painel_layout.addSpacing(10)

        # Beam Size
        lbl_beam = QLabel(t("config_engine.beam_size"))
        lbl_beam.setStyleSheet("font-weight: bold;")
        painel_layout.addWidget(lbl_beam)

        self.combo_beam_size = ComboBoxPosicaoFixa()
        self.combo_beam_size.setFixedWidth(380)
        self.combo_beam_size.setMinimumHeight(34)
        for valor in _OPCOES_BEAM_SIZE:
            if valor == -1:
                rotulo = t("config_engine.beam_size_desativado")
            else:
                rotulo = str(valor)
                if valor == _BEAM_SIZE_PADRAO:
                    rotulo += f" ({palavra_padrao})"
            self.combo_beam_size.addItem(rotulo, userData=valor)

        beam_size_atual = int(getattr(self.app, "beam_size", _BEAM_SIZE_PADRAO))
        idx_beam = self.combo_beam_size.findData(beam_size_atual)
        self.combo_beam_size.setCurrentIndex(idx_beam if idx_beam >= 0 else 0)
        self.combo_beam_size.currentIndexChanged.connect(self._alterar_beam_size)
        painel_layout.addWidget(self.combo_beam_size)

        aviso_beam = QLabel(t("config_engine.beam_size_aviso"))
        aviso_beam.setStyleSheet(f"color: {cor_hint}; font-size: 11px;")
        aviso_beam.setWordWrap(True)
        painel_layout.addWidget(aviso_beam)

        layout.addWidget(self.painel_avancado)

        # expande sozinho se algum valor já estiver fora do padrão
        self.painel_avancado.setVisible(False)
        self.btn_avancado.toggled.connect(self._alternar_avancado)
        fora_do_padrao = (
            temperature_atual != _TEMPERATURE_PADRAO
            or beam_size_atual != _BEAM_SIZE_PADRAO
        )
        self.btn_avancado.setChecked(fora_do_padrao)
        self._atualizar_texto_avancado(fora_do_padrao)

        layout.addSpacing(14)

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

    def _alternar_avancado(self, expandido: bool) -> None:
        self.painel_avancado.setVisible(expandido)
        self._atualizar_texto_avancado(expandido)

    def _atualizar_texto_avancado(self, expandido: bool) -> None:
        seta = "▾" if expandido else "▸"
        self.btn_avancado.setText(f"{seta}  {self._texto_base_avancado}")

    def _alterar_temperature(self):
        self.app.temperature = float(self.combo_temperature.currentData())
        self.app.salvar_configuracoes()

    def _alterar_beam_size(self):
        self.app.beam_size = int(self.combo_beam_size.currentData())
        self.app.salvar_configuracoes()
