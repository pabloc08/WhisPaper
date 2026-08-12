import os
import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QCheckBox, QLineEdit, QFileDialog,
    QScrollArea, QVBoxLayout, QHBoxLayout,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QByteArray, QRegularExpression
from PySide6.QtGui import QIcon, QPixmap, QFont, QRegularExpressionValidator

from utils.audio import tocar_som, limpar_cache_audio
from utils.logger import log_info
from converter.converter import obter_duracao
from utils.filenames import _truncar_nome
from interface.waveform_spinner import WaveformSpinner
from interface.combo_box import ComboBoxPosicaoFixa
from interface.status_icon import criar_label_icone_status as _criar_label_icone_status
from interface.file_type_icons import criar_label_tipo_arquivo as _criar_label_tipo_arquivo
from interface.drag_drop import DragDropMixin
from interface.tray import TrayMixin
from interface.transcription_panel import SetaExpansao, PainelProgresso

from settings.config_manager import carregar_config, salvar_config
from settings.i18n import t
from settings.constants import FORMATOS_VALIDOS
from settings.paths import (
    TEMP_DIR,
    criar_diretorios,
)

# registra os recursos Qt embutidos (ícones, sons, fontes)
from interface.assets import assets_rc  # noqa: F401

# popup de conclusão
from interface.dialogs.completion_popup          import PopupConclusao

criar_diretorios()


def _icone_engrenagem() -> QIcon:
    icon = QIcon(":/icons/settings.png")
    return icon if not icon.isNull() else QIcon()


# tema/QSS; aliases mantidos por compatibilidade com main.py e dialogs
from utils.theme import carregar_qss as _carregar_qss          # noqa: E402
from utils.theme import tema_inicial as _tema_inicial          # noqa: E402


# worker de transcrição
from workers.transcription_worker import TranscricaoWorker
from transcriber.request          import TranscriptionRequest
from transcriber.managers.engine_manager import EngineManager
from transcriber.managers.model_manager  import ModelManager


def _duracao_str(elapsed: float) -> str:
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    partes = []
    if h: partes.append(f"{h}h")
    if m: partes.append(f"{m}min")
    partes.append(f"{s}s")
    return " ".join(partes)


# janelas de diálogo
from interface.dialogs.engine_config_dialog       import JanelaConfigEngine
from interface.dialogs.general_config_dialog      import JanelaConfigGeral
from interface.dialogs.model_manager_dialog       import JanelaGerenciadorModelos


class DropArea(QFrame):
    """Zona de drop visual — o DnD real é tratado pelo QMainWindow."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop_area")
        self.setMinimumHeight(150)
        # limita altura pra não disputar espaço com a lista de arquivos expandida
        self.setMaximumHeight(280)

    def highlight(self, on: bool, tema: str = "light"):
        if on:
            if tema == "dark":
                self.setStyleSheet(
                    "QFrame#drop_area { background-color: #1E2B47; "
                    "border: 2px solid #5B8CFF; border-radius: 16px; }"
                )
            else:
                self.setStyleSheet(
                    "QFrame#drop_area { background-color: #dbeafe; "
                    "border: 2px solid #60a5fa; border-radius: 16px; }"
                )
        else:
            self.setStyleSheet("")

    def erro(self, tema: str = "light"):
        """Estado visual de erro (arquivo incompatível), com cores por tema."""
        if tema == "dark":
            self.setStyleSheet(
                "QFrame#drop_area { background-color: #3A1F24; "
                "border: 2px solid #f87171; border-radius: 16px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame#drop_area { background-color: #fff5f5; "
                "border: 2px solid #e53e3e; border-radius: 16px; }"
            )


class App(DragDropMixin, TrayMixin, QMainWindow):
    _duracao_pronta = Signal(str, str)  # (caminho, duracao)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("app.titulo"))
        self.resize(640, 480)

        icon = QIcon(":/icons/whispaper.png")
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.configs              = carregar_config()
        self.transcrevendo        = False
        self.fila_arquivos        = []
        self._worker              = None
        self._fila_idx            = 0   # atualizado via signal progresso_fila do worker
        self._fila_total          = 0
        self._timer_reset_barra   = None  # cancelável, evita reset de transcrição antiga disparar numa nova

        self.engine_id            = self.configs.get("engine", "whispercpp")
        self.model_id             = self.configs.get("model_id", "large-v3-turbo")
        self.task                 = self.configs.get("task", "transcribe")
        self.language             = self.configs.get("language", "auto")
        self.som_ativado          = self.configs.get("som", True)
        self.pasta_saida          = self.configs.get("pasta_saida", "")
        self.formato_saida        = self.configs.get("formato_saida", "ambos")
        self.vad_filter           = self.configs.get("vad_filter", False)
        self.usar_gpu             = self.configs.get("usar_gpu", False)
        self.temperature          = self.configs.get("temperature", 0.0)
        self.beam_size            = self.configs.get("beam_size", 5)
        self._usando_tray         = False
        self._tray_obj            = None

        self._icone_gear = _icone_engrenagem()
        self._construir_interface()
        self._seta_painel      = SetaExpansao(self)
        self._seta_painel.hide()   # filho de verdade herda visibilidade do pai por padrão
        self._painel_progresso = None
        self._painel_estava_visivel_antes_de_esconder = False  # p/ reabrir o painel ao restaurar a janela
        self._seta_painel.clicked.connect(self._alternar_painel_progresso)
        self.setMinimumSize(self.centralWidget().minimumSizeHint())  # calculado do layout, não um valor fixo
        self._duracao_pronta.connect(self._aplicar_duracao)
        # única forma confiável de capturar DnD no Windows com widgets filhos usando QSS
        QApplication.instance().installEventFilter(self)

        # Restaura posicao/tamanho da sessao anterior
        geometria = self.configs.get("window_geometry", "")
        if geometria:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometria.encode()))
            except Exception:
                pass

        # Minimizar para bandeja se configurado
        if self.configs.get("minimizar", "padrao") == "bandeja":
            self.aplicar_minimizar("bandeja")

        # Valida pasta de saida salva (timer para janela ja visivel)
        QTimer.singleShot(200, self._validar_pasta_saida)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _estilo_rodape_lista(self) -> str:
        """Cor dos botões 'adicionar'/'limpar lista', ajustada por tema."""
        if self.configs.get("tema", "light") == "dark":
            return (
                "QPushButton#btn_link { color: #8B8F9A; font-size: 11px; }"
                "QPushButton#btn_link:hover { color: #B7BBC5; }"
                "QPushButton#btn_link:disabled { color: #4A4F5C; }"
            )
        return (
            "QPushButton#btn_link { color: #94a3b8; font-size: 11px; }"
            "QPushButton#btn_link:hover { color: #64748b; }"
            "QPushButton#btn_link:disabled { color: #cbd5e1; }"
        )

    def atualizar_estilo_rodape(self):
        """Reaplica a cor dos botões do rodapé após troca de tema em tempo real."""
        estilo = self._estilo_rodape_lista()
        self.btn_adicionar_lista.setStyleSheet(estilo)
        self.btn_limpar_lista.setStyleSheet(estilo)

    def _construir_interface(self):
        central = QWidget()
        central.setObjectName("central_widget")
        central.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 8)
        root.setSpacing(6)

        self._construir_area_arraste(root)
        self._construir_pasta_saida(root)
        self._construir_config_tempo(root)
        self._construir_engine(root)
        self._construir_modelo(root)
        self._construir_botoes_principais(root)
        self._construir_progresso(root)

    def _construir_area_arraste(self, root):
        # ── Drop area ────────────────────────────────────────────────
        self.drop_area = DropArea()
        root.addWidget(self.drop_area)
        root.addSpacing(8)

        drop_layout = QVBoxLayout(self.drop_area)
        drop_layout.setContentsMargins(0, 0, 0, 0)
        drop_layout.setSpacing(0)

        # Zona vazia
        self.widget_vazio = QWidget()
        vazio_layout = QVBoxLayout(self.widget_vazio)
        vazio_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vazio_layout.setSpacing(6)

        icone_pasta = QLabel()
        icone_pasta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _pm = QPixmap(":/icons/folder.png")
        if not _pm.isNull():
            _pm = _pm.scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icone_pasta.setPixmap(_pm)
        else:
            icone_pasta.setText("📂")
            f = QFont(); f.setPointSize(36); icone_pasta.setFont(f)
        vazio_layout.addWidget(icone_pasta)

        lbl_arraste = QLabel(t("drop.instrucao"))
        lbl_arraste.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _fa = QFont(); _fa.setPointSize(11)
        lbl_arraste.setFont(_fa)
        vazio_layout.addWidget(lbl_arraste)

        btn_sel = QPushButton(t("drop.clique"))   # "ou clique para selecionar"
        btn_sel.setObjectName("btn_link")
        btn_sel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sel.clicked.connect(self.selecionar_arquivo)
        vazio_layout.addWidget(btn_sel, alignment=Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.widget_vazio)

        # Lista de arquivos
        self.scroll_lista = QScrollArea()
        self.scroll_lista.setWidgetResizable(True)
        self.scroll_lista.hide()

        self.widget_lista  = QWidget()
        self.layout_lista  = QVBoxLayout(self.widget_lista)
        self.layout_lista.setContentsMargins(6, 6, 6, 6)
        self.layout_lista.setSpacing(4)
        self.layout_lista.addStretch()
        self.scroll_lista.setWidget(self.widget_lista)
        drop_layout.addWidget(self.scroll_lista)

        # Rodapé da lista: botão limpar alinhado à direita
        self.widget_rodape_lista = QWidget()
        rodape_layout = QHBoxLayout(self.widget_rodape_lista)
        rodape_layout.setContentsMargins(12, 2, 12, 4)
        rodape_layout.addStretch()

        _estilo_rodape = self._estilo_rodape_lista()  # cor fixa no dark deixava "disabled" parecido com clicável

        self.btn_adicionar_lista = QPushButton(t("fila.adicionar"))
        self.btn_adicionar_lista.setObjectName("btn_link")
        self.btn_adicionar_lista.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_adicionar_lista.setStyleSheet(_estilo_rodape)
        self.btn_adicionar_lista.clicked.connect(self.selecionar_arquivo)
        rodape_layout.addWidget(self.btn_adicionar_lista)

        self.btn_limpar_lista = QPushButton(t("fila.limpar"))
        self.btn_limpar_lista.setObjectName("btn_link")
        self.btn_limpar_lista.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limpar_lista.setStyleSheet(_estilo_rodape)
        self.btn_limpar_lista.clicked.connect(self._limpar_fila)
        rodape_layout.addWidget(self.btn_limpar_lista)

        drop_layout.addWidget(self.widget_rodape_lista)
        self.widget_rodape_lista.hide()

    def _construir_pasta_saida(self, root):
        # ── Pasta de saída ───────────────────────────────────────────
        row_saida = QHBoxLayout()
        row_saida.setSpacing(8)
        self.btn_pasta = QPushButton(t("pasta.label"))
        self.btn_pasta.setObjectName("btn_pasta")
        self.btn_pasta.setFixedWidth(150)
        self.btn_pasta.clicked.connect(self.selecionar_pasta)
        row_saida.addWidget(self.btn_pasta)
        self.label_saida = QLabel(self.pasta_saida or t("pasta.nenhuma"))
        self.label_saida.setObjectName("label_cinza")
        row_saida.addWidget(self.label_saida)
        row_saida.addStretch()
        root.addLayout(row_saida)

    def _construir_config_tempo(self, root):
        # ── Customizar tempo ─────────────────────────────────────────
        row_tempo = QHBoxLayout()
        row_tempo.setSpacing(8)
        self.checkbox_tempo = QCheckBox(t("tempo.label"))
        self.checkbox_tempo.toggled.connect(self._toggle_tempo)
        row_tempo.addWidget(self.checkbox_tempo)

        # aceita H, MM:SS ou HH:MM:SS enquanto digita; "fim > início" é validado no trimmer
        validador_tempo = QRegularExpressionValidator(
            QRegularExpression(r"^([0-9]{1,2})?(:([0-5]?[0-9])?)?(:([0-5]?[0-9])?)?$")
        )

        self.label_inicio = QLabel(t("tempo.inicio") + ":")
        row_tempo.addWidget(self.label_inicio)
        self.entry_inicio = QLineEdit()
        self.entry_inicio.setPlaceholderText("h:mm:ss")
        self.entry_inicio.setValidator(validador_tempo)
        self.entry_inicio.setFixedWidth(90)
        self.entry_inicio.setEnabled(False)
        row_tempo.addWidget(self.entry_inicio)

        self.label_fim = QLabel(t("tempo.fim") + ":")
        row_tempo.addWidget(self.label_fim)
        self.entry_fim = QLineEdit()
        self.entry_fim.setPlaceholderText("h:mm:ss")
        self.entry_fim.setValidator(validador_tempo)
        self.entry_fim.setFixedWidth(90)
        self.entry_fim.setEnabled(False)
        row_tempo.addWidget(self.entry_fim)
        row_tempo.addStretch()
        root.addLayout(row_tempo)

        self.label_tempo_lote = QLabel(t("fila.aviso_tempo"))
        self.label_tempo_lote.setObjectName("label_cinza")
        self.label_tempo_lote.hide()
        root.addWidget(self.label_tempo_lote)

    def _construir_engine(self, root):
        # ── Engine ───────────────────────────────────────────────────
        root.addWidget(QLabel(t("engine.label")))
        row_engine = QHBoxLayout()
        row_engine.setSpacing(6)

        engines_disp = EngineManager.listar()
        nomes_engine = [EngineManager.nome_exibicao(e) for e in engines_disp]
        self.combo_engine = ComboBoxPosicaoFixa()
        self.combo_engine.addItems(nomes_engine)
        self.combo_engine.setCurrentText(EngineManager.nome_exibicao(self.engine_id))
        self.combo_engine.setFixedWidth(169)
        self.combo_engine.currentTextChanged.connect(self._alterar_engine)
        row_engine.addWidget(self.combo_engine)

        self.btn_config_engine = QPushButton()
        self.btn_config_engine.setObjectName("btn_icone")
        self.btn_config_engine.setFixedSize(32, 32)
        self.btn_config_engine.setIcon(self._icone_gear)
        self.btn_config_engine.setIconSize(QSize(20, 20))
        self.btn_config_engine.clicked.connect(self._abrir_config_engine)
        row_engine.addWidget(self.btn_config_engine)
        row_engine.addStretch()
        root.addLayout(row_engine)

    def _construir_modelo(self, root):
        # ── Modelo ───────────────────────────────────────────────────
        root.addWidget(QLabel(t("modelo.label")))
        row_modelo = QHBoxLayout()
        row_modelo.setSpacing(6)

        self.combo_modelo = ComboBoxPosicaoFixa()
        self.combo_modelo.setFixedWidth(169)
        self.combo_modelo.currentTextChanged.connect(self._alterar_modelo)
        row_modelo.addWidget(self.combo_modelo)

        self.btn_config_modelo = QPushButton()
        self.btn_config_modelo.setObjectName("btn_icone")
        self.btn_config_modelo.setFixedSize(32, 32)
        self.btn_config_modelo.setIcon(self._icone_gear)
        self.btn_config_modelo.setIconSize(QSize(20, 20))
        self.btn_config_modelo.clicked.connect(self._abrir_gerenciador_modelos)
        row_modelo.addWidget(self.btn_config_modelo)
        row_modelo.addStretch()
        root.addLayout(row_modelo)
        self._atualizar_combo_modelos()

    def _construir_botoes_principais(self, root):
        # ── Botões principais ────────────────────────────────────────
        root.addSpacing(20)
        row_botoes = QHBoxLayout()
        row_botoes.setSpacing(12)
        self.btn_iniciar = QPushButton(t("btn.transcrever"))
        self.btn_iniciar.setObjectName("btn_transcrever")
        self.btn_iniciar.clicked.connect(self.executar_transcricao)
        row_botoes.addWidget(self.btn_iniciar)

        self.btn_cancelar = QPushButton(t("btn.cancelar"))
        self.btn_cancelar.setObjectName("btn_cancelar")
        self.btn_cancelar.clicked.connect(self.cancelar_transcricao)
        row_botoes.addWidget(self.btn_cancelar)

        row_botoes.addStretch()

        self.btn_config_geral = QPushButton(t("config_geral.btn"))
        self.btn_config_geral.setObjectName("btn_config_geral")
        self.btn_config_geral.clicked.connect(self._abrir_config_geral)
        row_botoes.addWidget(self.btn_config_geral)

        self.btn_como_usar = QPushButton("?")
        self.btn_como_usar.setObjectName("btn_como_usar")
        self.btn_como_usar.setFixedSize(32, 32)
        self.btn_como_usar.setToolTip("Como usar?")
        self.btn_como_usar.clicked.connect(self._abrir_como_usar)
        row_botoes.addWidget(self.btn_como_usar)

        root.addLayout(row_botoes)

        root.addStretch()

    def _construir_progresso(self, root):
        # waveform em cima, status embaixo — waveform só mostra atividade, não progresso real
        col_status = QVBoxLayout()
        col_status.setSpacing(4)
        col_status.setContentsMargins(0, 0, 0, 0)
        col_status.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.waveform_spinner = WaveformSpinner()
        col_status.addWidget(self.waveform_spinner, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.label_status = QLabel(t("status.aguardando"))
        self.label_status.setObjectName("label_status")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_status.addWidget(self.label_status)

        # widget-contêiner centralizado
        _status_container = QWidget()
        _status_container.setLayout(col_status)
        root.addWidget(_status_container, alignment=Qt.AlignmentFlag.AlignCenter)

    # ------------------------------------------------------------------
    # Arquivo
    # ------------------------------------------------------------------

    def selecionar_arquivo(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, t("dialogo.selecionar_midia"), "",
            "Arquivos de mídia (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma "
            "*.aiff *.opus *.amr *.mp4 *.mov *.avi *.mkv *.webm *.3gp)"
        )
        for c in caminhos:
            self.adicionar_arquivo(c)

    def selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, t("dialogo.selecionar_pasta"))
        if pasta:
            self.pasta_saida = pasta
            self.label_saida.setText(pasta)
            self.salvar_configuracoes()

    def adicionar_arquivo(self, caminho: str):
        ext  = Path(caminho).suffix.lower()
        nome = Path(caminho).name

        if ext not in FORMATOS_VALIDOS:
            self._flash_erro(t("erro.formato_invalido", ext=ext))
            return
        if any(a["path"] == caminho for a in self.fila_arquivos):
            return

        tipo = "audio" if ext in {
            ".mp3",".wav",".flac",".ogg",".m4a",".aac",".wma",".aiff",".opus",".amr"
        } else "video"

        self.fila_arquivos.append({
            "path": caminho, "nome": nome, "tipo": tipo,
            "status": "pendente", "duracao": "",
        })
        self._renderizar_lista()
        self._atualizar_estado_tempo()
        self.atualizar_status(t("fila.contagem", n=len(self.fila_arquivos)))

        def _buscar():
            dur = obter_duracao(caminho)
            self._duracao_pronta.emit(caminho, dur)

        threading.Thread(target=_buscar, daemon=True).start()

    def _aplicar_duracao(self, caminho: str, duracao: str):
        """Slot chamado pelo signal _duracao_pronta — sempre na thread principal."""
        for e in self.fila_arquivos:
            if e["path"] == caminho:
                e["duracao"] = duracao
                break
        self._renderizar_lista()

    def _remover_arquivo(self, caminho: str):
        self.fila_arquivos = [a for a in self.fila_arquivos if a["path"] != caminho]
        self._renderizar_lista()
        self._atualizar_estado_tempo()
        if self.fila_arquivos:
            self.atualizar_status(t("fila.contagem", n=len(self.fila_arquivos)))
        else:
            self._resetar_barra()

    def _limpar_fila(self):
        self.fila_arquivos = []
        self._renderizar_lista()
        self._atualizar_estado_tempo()
        self.atualizar_status(t("status.aguardando"))

    def _renderizar_lista(self):
        # Remove tudo exceto o stretch final
        while self.layout_lista.count() > 1:
            item = self.layout_lista.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.fila_arquivos:
            self.scroll_lista.hide()
            self.widget_vazio.show()
            self.widget_rodape_lista.hide()
            return

        self.widget_vazio.hide()
        self.scroll_lista.show()
        self.widget_rodape_lista.show()

        for entrada in self.fila_arquivos:
            frame = QFrame()
            frame.setObjectName("linha_arquivo")
            row   = QHBoxLayout(frame)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(6)

            # ✕ remover — esquerda
            btn_rem = QPushButton("✕")
            btn_rem.setObjectName("btn_icone")
            btn_rem.setFixedSize(26, 26)
            btn_rem.setStyleSheet("QPushButton#btn_icone { color: #94a3b8; }")
            btn_rem.setEnabled(not self.transcrevendo)
            btn_rem.clicked.connect(
                lambda checked=False, p=entrada["path"]: self._remover_arquivo(p)
            )
            row.addWidget(btn_rem)

            icone_lbl = _criar_label_tipo_arquivo(entrada["tipo"])
            row.addWidget(icone_lbl)

            nome_lbl = QLabel(_truncar_nome(entrada["nome"]))
            _f = QFont(); _f.setPointSize(10); nome_lbl.setFont(_f)
            row.addWidget(nome_lbl, 1)

            # PNG em vez de glifo — a fonte embutida não tem ✓/!, e o fallback do Linux é inconsistente
            if entrada.get("status") == "concluido":
                st = _criar_label_icone_status(":/icons/success.png")
                if st:
                    row.addWidget(st)
            elif entrada.get("status") == "erro":
                st = _criar_label_icone_status(":/icons/warning.png")
                if st:
                    row.addWidget(st)

            # Duração — extrema direita
            dur = entrada.get("duracao", "")
            if dur:
                dur_lbl = QLabel(dur)
                _fd = QFont(); _fd.setPointSize(9); dur_lbl.setFont(_fd)
                dur_lbl.setObjectName("label_cinza")
                dur_lbl.setFixedWidth(52)
                dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row.addWidget(dur_lbl)

            self.layout_lista.insertWidget(self.layout_lista.count() - 1, frame)

    def _flash_erro(self, msg: str):
        self.drop_area.erro(self.configs.get("tema", "light"))
        self.atualizar_status(f"❌ {msg}")
        QTimer.singleShot(3000, lambda: (
            self.drop_area.setStyleSheet(""),
            self.atualizar_status(t("status.aguardando")),
        ))

    # ------------------------------------------------------------------
    # Engine / Modelo
    # ------------------------------------------------------------------

    def _alterar_engine(self, nome):
        self.engine_id = EngineManager.id_por_nome(nome)
        self._atualizar_combo_modelos()
        self.salvar_configuracoes()

    def _alterar_modelo(self, model_id):
        if model_id and not model_id.startswith("—"):
            self.model_id = model_id
            self.salvar_configuracoes()

    def _atualizar_combo_modelos(self):
        manager    = ModelManager(self.engine_id)
        instalados = manager.listar_instalados()
        nomes      = [m["id"] for m in instalados]

        self.combo_modelo.blockSignals(True)
        self.combo_modelo.clear()
        if nomes:
            self.combo_modelo.addItems(nomes)
            self.combo_modelo.setEnabled(True)
            if self.model_id in nomes:
                self.combo_modelo.setCurrentText(self.model_id)
            else:
                self.combo_modelo.setCurrentIndex(0)
                self.model_id = nomes[0]
        else:
            self.combo_modelo.addItem(t("modelo.nenhum"))
            self.combo_modelo.setEnabled(False)
            self.model_id = ""
        self.combo_modelo.blockSignals(False)

    def _abrir_config_engine(self):
        JanelaConfigEngine(self, self).exec()

    def _abrir_gerenciador_modelos(self):
        JanelaGerenciadorModelos(self, self).exec()

    # ------------------------------------------------------------------
    # Tempo
    # ------------------------------------------------------------------

    def _toggle_tempo(self, ativo: bool):
        self.entry_inicio.setEnabled(ativo)
        self.entry_fim.setEnabled(ativo)

    def _atualizar_estado_tempo(self):
        lote = len(self.fila_arquivos) > 1
        self.checkbox_tempo.setEnabled(not lote)
        self.label_inicio.setVisible(not lote)
        self.entry_inicio.setVisible(not lote)
        self.label_fim.setVisible(not lote)
        self.entry_fim.setVisible(not lote)
        self.label_tempo_lote.setVisible(lote)

    # ------------------------------------------------------------------
    # Controles
    # ------------------------------------------------------------------

    def _desabilitar_controles(self):
        for w in (self.btn_iniciar, self.combo_engine, self.combo_modelo,
                  self.btn_config_engine, self.btn_config_modelo,
                  self.btn_pasta, self.checkbox_tempo,
                  self.entry_inicio, self.entry_fim,
                  self.btn_adicionar_lista, self.btn_limpar_lista,
                  self.btn_config_geral):
            w.setEnabled(False)

    def _reativar_controles(self):
        for w in (self.btn_iniciar, self.combo_engine,
                  self.btn_config_engine, self.btn_config_modelo,
                  self.btn_pasta, self.checkbox_tempo,
                  self.btn_adicionar_lista, self.btn_limpar_lista,
                  self.btn_config_geral, self.btn_cancelar):
            w.setEnabled(True)
        self._atualizar_combo_modelos()
        self._atualizar_estado_tempo()

    # ------------------------------------------------------------------
    # Transcrição
    # ------------------------------------------------------------------

    def executar_transcricao(self):
        if self.transcrevendo:
            return
        if not self.fila_arquivos:
            self.atualizar_status(t("erro.nenhum_arquivo"))
            QTimer.singleShot(3000, lambda: self.label_status.setText(t("status.aguardando")))
            return
        if not self.model_id:
            self.atualizar_status(t("erro.modelo_nao_instalado"))
            QTimer.singleShot(3000, lambda: self.label_status.setText(t("status.aguardando")))
            return
        if not self.pasta_saida:
            self.atualizar_status(t("erro.pasta_destino"))
            QTimer.singleShot(3000, lambda: self.label_status.setText(t("status.aguardando")))
            return

        # Limpa qualquer estado visual de erro anterior (flash de drop, borda vermelha)
        self.drop_area.setStyleSheet("")
        self.drop_area.highlight(False)

        # cancela reset pendente e limpa ícones residuais (✓/!) da sessão anterior
        if self._timer_reset_barra is not None:
            self._timer_reset_barra.stop()
        for e in self.fila_arquivos:
            e.pop("status", None)

        self._desabilitar_controles()
        self.transcrevendo   = True
        self._seta_painel.reposicionar(self)
        self._seta_painel.raise_()
        # prepara o painel síncrono, antes do worker, pra não perder o 1º sinal de progresso
        self._preparar_painel_progresso()
        # delay proposital pro fade-in não somar com a travadinha do trabalho síncrono acima
        QTimer.singleShot(150, self._seta_painel.aparecer_animado)
        QTimer.singleShot(150, self._abrir_painel_progresso)
        self._renderizar_lista()   # bloqueia os ✕ imediatamente
        self._fila_idx       = 1
        self._fila_total     = len(self.fila_arquivos)
        self.waveform_spinner.set_tema(self.configs.get("tema", "light"))
        self.waveform_spinner.start()
        self.label_status.setText(t("status.transcrevendo_spinner"))

        if self.som_ativado:
            tocar_som("som_transcricao")

        request = TranscriptionRequest(
            arquivo              = Path(self.fila_arquivos[0]["path"]),  # placeholder; worker usa fila
            engine_id            = self.engine_id,
            model_id             = self.model_id,
            language             = self.language,
            task                 = self.task,
            pasta_saida          = Path(self.pasta_saida),
            formato_saida        = self.formato_saida,
            vad_filter           = self.vad_filter,
            usar_gpu             = self.usar_gpu,
            temperature          = self.temperature,
            beam_size            = self.beam_size,
            usar_tempo           = self.checkbox_tempo.isChecked(),
            inicio               = self.entry_inicio.text(),
            fim                  = self.entry_fim.text(),
        )
        self._worker = TranscricaoWorker(
            fila         = list(self.fila_arquivos),
            request_base = request,
        )
        self._worker.status_atualizado.connect(self.atualizar_status)
        self._worker.progresso_fila.connect(self._on_progresso_fila)
        self._worker.progresso_transcricao.connect(self._on_progresso_transcricao)
        self._worker.arquivo_concluido.connect(self._on_arquivo_concluido)
        self._worker.arquivo_erro.connect(self._on_arquivo_erro)
        self._worker.finalizado.connect(self._on_finalizado)
        self._worker.cancelado.connect(self._on_cancelado)
        self._worker.erro_geral.connect(self._on_erro_geral)
        self._worker.start()

    def cancelar_transcricao(self):
        if not self.transcrevendo:
            self.atualizar_status(t("status.nenhuma_transcricao"))
            QTimer.singleShot(3000, lambda: self.label_status.setText(t("status.aguardando")))
            return
        self.atualizar_status(t("status.cancelando"))
        self.btn_cancelar.setEnabled(False)
        self.waveform_spinner.congelar_erro()
        if self._worker:
            self._worker.cancelar()
        if self.som_ativado:
            tocar_som("som_cancelar")

    def _on_progresso_fila(self, idx: int, total: int):
        self._fila_idx   = idx
        self._fila_total = total
        if self._painel_progresso is not None and 1 <= idx <= len(self.fila_arquivos):
            nome = self.fila_arquivos[idx - 1].get("nome", "")
            self._painel_progresso.iniciar_arquivo(idx - 1, nome)

    def _on_progresso_transcricao(self, segundos: int, percentual: float, texto: str):
        if self._painel_progresso is not None:
            self._painel_progresso.atualizar_progresso(segundos, percentual, texto)

    def _on_arquivo_concluido(self, path: str):
        for e in self.fila_arquivos:
            if e["path"] == path:
                e["status"] = "concluido"
        self._renderizar_lista()

    def _on_arquivo_erro(self, path: str):
        for e in self.fila_arquivos:
            if e["path"] == path:
                e["status"] = "erro"
        self._renderizar_lista()

    def _on_finalizado(self, concluidos: int, total: int, elapsed: float):
        self.transcrevendo = False
        self._esconder_painel_lateral()
        self._reativar_controles()
        self._fila_total = 0  # zera antes de atualizar_status, senão fica preso em "Transcrevendo (X de Y)"
        dur = _duracao_str(elapsed)
        if concluidos < total:
            self.waveform_spinner.congelar_erro()
            self.atualizar_status(t("status.concluidos_parcial",
                                    concluidos=concluidos, total=total, dur=dur))
            if self.som_ativado:
                tocar_som("som_cancelar")
            self._agendar_reset_barra(self._resetar_barra)
        else:
            self.waveform_spinner.stop()
            # texto vazio: o popup de conclusão já comunica o resultado (evita reescrita em lote)
            self.label_status.setText("")
            if self.som_ativado:
                tocar_som("som_notificacao")
            resumo = t('popup.tempo_decorrido', dur=dur)
            nomes  = [e['nome'] for e in self.fila_arquivos]
            PopupConclusao(self, resumo, nomes, self.pasta_saida, on_ok=self._resetar_barra)

    def _on_cancelado(self):
        self.waveform_spinner.congelar_erro()
        self.transcrevendo = False
        self._esconder_painel_lateral()
        self._fila_total = 0  # idem _on_finalizado, senão "Cancelado" nasce mascarado
        self.atualizar_status(t("status.cancelado"))
        self._reativar_controles()
        # marca erro e renderiza antes do reset, senão o ícone "!" nunca chega a pintar
        for e in self.fila_arquivos:
            if e.get("status") != "concluido":
                e["status"] = "erro"
        self._renderizar_lista()   # libera os ✕ e mostra os ícones de status
        self._agendar_reset_barra(self._resetar_barra)

    def _on_erro_geral(self, msg: str):
        self.waveform_spinner.congelar_erro()
        self.transcrevendo = False
        self._esconder_painel_lateral()
        self._fila_total = 0
        self.atualizar_status(t("erro.prefixo", msg=msg))
        if self.som_ativado:
            tocar_som("som_cancelar")
        self._reativar_controles()
        self._agendar_reset_barra(self._resetar_barra)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resetar_barra(self):
        """Reseta o waveform, status e ícones da lista — sincronizados."""
        self.waveform_spinner.stop()
        self.label_status.setText(t("status.aguardando"))
        self._fila_total = 0   # rede de segurança, além do reset em _on_*
        for e in self.fila_arquivos:
            e.pop("status", None)
        self._renderizar_lista()

    def _agendar_reset_barra(self, callback):
        """Agenda reset da barra em 5s, cancelando um reset pendente anterior."""
        if self._timer_reset_barra is None:
            self._timer_reset_barra = QTimer(self)
            self._timer_reset_barra.setSingleShot(True)
        else:
            self._timer_reset_barra.stop()
            try:  # desconecta slots antigos p/ não acumular callbacks
                self._timer_reset_barra.timeout.disconnect()
            except RuntimeError:
                pass
        self._timer_reset_barra.timeout.connect(callback)
        self._timer_reset_barra.start(5000)

    def atualizar_status(self, texto: str):
        self.label_status.setText(texto)

        if self._fila_total > 1:  # sobrescreve com contagem da fila
            msg = t("status.transcrevendo_fila", idx=self._fila_idx, total=self._fila_total)
            self.label_status.setText(msg)

    def _abrir_config_geral(self):
        dlg = JanelaConfigGeral(self, self)
        dlg.exec()

    def _abrir_como_usar(self):
        from interface.dialogs.about_dialog import JanelaSobre
        dlg = JanelaSobre(self)
        dlg.exec()

    def salvar_configuracoes(self):
        # atualiza no lugar p/ preservar chaves geridas por outras janelas
        self.configs.update({
            "engine":               self.engine_id,
            "model_id":             self.model_id,
            "task":                 self.task,
            "language":             self.language,
            "som":                  self.som_ativado,
            "pasta_saida":          self.pasta_saida,
            "vad_filter":           self.vad_filter,
            "usar_gpu":             self.usar_gpu,
            "temperature":          self.temperature,
            "beam_size":            self.beam_size,
            "inicio_personalizado": self.entry_inicio.text(),
            "fim_personalizado":    self.entry_fim.text(),
        })
        salvar_config(self.configs)

    def limpar_temp(self):
        for item in TEMP_DIR.glob("*"):
            try: item.unlink()
            except Exception: pass

    # ------------------------------------------------------------------
    # Painel lateral de progresso
    # ------------------------------------------------------------------

    def _preparar_painel_progresso(self):
        """Cria o painel (se preciso) e reinicia o histórico da fila; não mexe em visibilidade."""
        if self._painel_progresso is None:
            self._painel_progresso = PainelProgresso(self.configs.get("tema", "light"))
            self._painel_progresso.fechar_solicitado.connect(self._fechar_painel_progresso)
        self._painel_progresso.iniciar_fila([e.get("nome", "") for e in self.fila_arquivos])

    def _abrir_painel_progresso(self):
        """Mostra/anima o painel sem reiniciar os dados da fila."""
        if self._painel_progresso is None:
            self._preparar_painel_progresso()

        if not self._painel_progresso.isVisible():
            self._painel_progresso.abrir_animado(self)
            self._seta_painel.set_aberta(True)

    def _alternar_painel_progresso(self):
        if self._painel_progresso is not None and self._painel_progresso.isVisible():
            self._fechar_painel_progresso()
        else:
            self._abrir_painel_progresso()

    def _fechar_painel_progresso(self):
        if self._painel_progresso is not None:
            self._painel_progresso.fechar_animado()
        self._seta_painel.set_aberta(False)

    def _esconder_painel_lateral(self):
        """Some com a seta e fecha o painel — chamado ao fim/erro/cancelamento."""
        self._seta_painel.desaparecer_animado()
        self._fechar_painel_progresso()

    def _reposicionar_painel_lateral(self):
        if self._seta_painel.isVisible():
            self._seta_painel.reposicionar(self)
        if self._painel_progresso is not None and self._painel_progresso.isVisible():
            self._painel_progresso.posicionar_ao_lado(self)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._reposicionar_painel_lateral()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_painel_lateral()

    def hideEvent(self, event):
        # cobre minimizar normal e pra bandeja — o painel é janela própria, não filha
        if self._painel_progresso is not None:
            self._painel_estava_visivel_antes_de_esconder = self._painel_progresso.isVisible()
            self._painel_progresso.hide()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # traz o painel de volta com a mesma animação de abertura, não um show() cru
        if self._painel_estava_visivel_antes_de_esconder and self._painel_progresso is not None:
            self._painel_estava_visivel_antes_de_esconder = False
            QTimer.singleShot(150, lambda: self._painel_progresso.abrir_animado(self))
            self._seta_painel.set_aberta(True)
        self._reposicionar_painel_lateral()

    def closeEvent(self, event):
        # painel é top-level próprio, não filho — precisa fechar manualmente
        if self._painel_progresso is not None:
            self._painel_progresso.close()

        if self._timer_reset_barra is not None:  # evita disparar após destruir a janela
            self._timer_reset_barra.stop()

        # timeout de propósito: se o whisper-cli travar, melhor fechar do que virar zumbi
        if self._worker and self._worker.isRunning():
            self._worker.cancelar()
            if not self._worker.wait(6000):
                log_info(
                    "closeEvent — timeout aguardando encerramento do worker "
                    "de transcrição (subprocesso do whisper-cli pode ter "
                    "ficado preso); fechando a app mesmo assim."
                )

        # Salva posição e tamanho da janela
        self.configs["window_geometry"] = self.saveGeometry().toBase64().data().decode()
        salvar_config(self.configs)

        # Remove o ícone da bandeja ao fechar
        if self._usando_tray and self._tray_obj is not None:
            self._tray_obj.hide()

        limpar_cache_audio()
        self.limpar_temp()
        event.accept()

    # ------------------------------------------------------------------
    # Validação da pasta de saída
    # ------------------------------------------------------------------

    def _validar_pasta_saida(self):
        """Exibe popup se a pasta de saída salva não existe mais."""
        if not self.pasta_saida:
            return
        if not Path(self.pasta_saida).is_dir():
            from interface.dialogs.invalid_folder_popup import PopupPastaInvalida
            dlg = PopupPastaInvalida(self)
            dlg.exec()
            self.pasta_saida = ""  # limpa pra não tentar transcrever pra lá
            self.label_saida.setText(t("pasta.nenhuma"))
            self.salvar_configuracoes()


def _calcular_pointsize(app) -> int:
    """Point size base confiável pra Windows e Linux (mesmo sem compositor)."""
    # 1. QT_FONT_DPI do usuário tem prioridade
    font_dpi = os.environ.get("QT_FONT_DPI")
    if font_dpi:
        try:
            return round(10 * int(font_dpi) / 96)
        except ValueError:
            pass

    # 2. QT_SCALE_FACTOR do usuário, sobre base 10pt
    scale = os.environ.get("QT_SCALE_FACTOR")
    if scale:
        try:
            return round(10 * float(scale))
        except ValueError:
            pass

    # 3. DPI lógico da tela principal (cobre Xorg e Wayland)
    try:
        from PySide6.QtGui import QScreen
        screen: QScreen = app.primaryScreen()
        if screen:
            dpi = screen.logicalDotsPerInchX()
            if 60 <= dpi <= 600:          # sanity check — valores absurdos viram fallback
                pt = round(10 * dpi / 96)
                return max(8, min(pt, 24)) # limita entre 8pt e 24pt por segurança
    except Exception:
        pass

    return 10  # fallback: 10pt (96 DPI)


def iniciar_app():
    # PySide6 6.x já ativa HiDPI por padrão; sem compositor no Linux, usar
    # QT_ENABLE_HIGHDPI_SCALING=1 antes de iniciar o app.

    app = QApplication.instance() or QApplication(sys.argv)

    app.setStyle("Fusion")  # evita o estilo nativo do Windows

    # fonte Noto Sans embutida via QRC; cai pra fonte do sistema se faltar
    nome_fonte = None
    try:
        from PySide6.QtGui import QFontDatabase
        id1 = QFontDatabase.addApplicationFont(":/fonts/NotoSans-Regular.ttf")
        _ = QFontDatabase.addApplicationFont(":/fonts/NotoSans-Bold.ttf")  # só o registro importa
        _ = QFontDatabase.addApplicationFont(":/fonts/NotoSans-Bold.ttf")
        if id1 >= 0:
            familias = QFontDatabase.applicationFontFamilies(id1)
            if familias:
                nome_fonte = familias[0]
    except Exception:
        pass

    if not nome_fonte:
        # QRC ausente ou falha no registro — melhor opção disponível no SO
        nome_fonte = "Segoe UI" if sys.platform == "win32" else "sans-serif"

    pt = _calcular_pointsize(app)
    fonte_base = QFont(nome_fonte, pt)
    fonte_base.setStyleHint(QFont.StyleHint.SansSerif)  # fallback genérico do SO
    app.setFont(fonte_base)

    app.setStyleSheet(_carregar_qss(_tema_inicial()))
    janela = App()
    janela.show()

    def _warmup_ffprobe():  # pré-aquece o ffprobe logo após a janela aparecer
        try:
            from converter.converter import obter_caminhos
            import subprocess
            from utils.platform import kwargs_processo
            _, ffprobe = obter_caminhos()
            subprocess.run(
                [str(ffprobe), "-version"],
                capture_output=True,
                timeout=10,
                **kwargs_processo(),
            )
        except Exception:
            pass
    threading.Thread(target=_warmup_ffprobe, daemon=True).start()

    # Pré-aquece os sons (QSoundEffect)
    from utils.audio import pre_aquecer
    QTimer.singleShot(
        0,
        lambda: pre_aquecer(["som_transcricao", "som_cancelar", "som_notificacao"]),
    )

    sys.exit(app.exec())
