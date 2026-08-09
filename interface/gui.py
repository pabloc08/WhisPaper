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
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QFont

from utils.audio import tocar_som, limpar_cache_audio
from utils.logger import log_info
from converter.converter import obter_duracao
from utils.filenames import _truncar_nome
from interface.progress_bar import BarraAnimada
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

# Registra os recursos Qt embutidos (ícones, imgs, sons, fontes) — o import
# em si é o que importa (efeito colateral de registro), por isso o noqa.
from interface.assets import assets_rc  # noqa: F401

# ---------------------------------------------------------------------------
# Popup de Conclusão
# ---------------------------------------------------------------------------

from interface.dialogs.completion_popup          import PopupConclusao

# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------

criar_diretorios()


# ---------------------------------------------------------------------------
# Ícone de engrenagem
# ---------------------------------------------------------------------------

def _icone_engrenagem() -> QIcon:
    icon = QIcon(":/icons/settings.png")
    return icon if not icon.isNull() else QIcon()


# ---------------------------------------------------------------------------
# QSS / tema — implementação em utils/theme.py (sem dependência Qt no import)
# Os aliases com underscore preservam compatibilidade com main.py e dialogs
# que ainda importam daqui.
# ---------------------------------------------------------------------------

from utils.theme import carregar_qss as _carregar_qss          # noqa: E402
from utils.theme import tema_inicial as _tema_inicial          # noqa: E402


# ---------------------------------------------------------------------------
# Worker de transcrição
# ---------------------------------------------------------------------------

from workers.transcription_worker import TranscricaoWorker
from transcriber.request          import TranscriptionRequest
from transcriber.managers.engine_manager import EngineManager
from transcriber.managers.model_manager  import ModelManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _duracao_str(elapsed: float) -> str:
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    partes = []
    if h: partes.append(f"{h}h")
    if m: partes.append(f"{m}min")
    partes.append(f"{s}s")
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Janelas de diálogo
# ---------------------------------------------------------------------------

from interface.dialogs.engine_config_dialog       import JanelaConfigEngine
from interface.dialogs.general_config_dialog      import JanelaConfigGeral
from interface.dialogs.model_manager_dialog       import JanelaGerenciadorModelos


# ---------------------------------------------------------------------------
# Drop Area — apenas visual; DnD é tratado no QMainWindow
# ---------------------------------------------------------------------------

class DropArea(QFrame):
    """
    Widget visual da zona de drop. Não lida com DnD diretamente —
    o QMainWindow (App) instala setAcceptDrops e implementa os eventos,
    garantindo que o drop funcione independentemente de qual filho está sob o cursor.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop_area")
        self.setMinimumHeight(150)
        # Impede que a área cresça indefinidamente quando a lista de arquivos
        # (QScrollArea, com size policy Expanding) está visível — sem este
        # limite, o QFrame "herda" o comportamento expansivo do filho e passa
        # a disputar espaço extra do redimensionamento da janela, empurrando/
        # sobrepondo visualmente os controles abaixo (ex.: botão de pasta).
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


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------

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
        # Timer cancelável para reset da barra — evita que um reset agendado
        # de uma transcrição anterior dispare no meio de uma nova.
        self._timer_reset_barra   = None

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
        self._seta_painel.clicked.connect(self._alternar_painel_progresso)
        # O mínimo é calculado a partir do próprio layout (e não um valor
        # fixo "chutado"). Um valor fixo menor do que o real acabava
        # permitindo encolher a janela além do que os widgets suportam,
        # o que fazia a área de arraste sobrepor visualmente os controles
        # abaixo dela (ex.: botão de pasta de destino) ao redimensionar
        # a janela para baixo.
        self.setMinimumSize(self.centralWidget().minimumSizeHint())
        self._duracao_pronta.connect(self._aplicar_duracao)
        # Instala filtro de eventos na aplicação inteira — única forma confiável
        # de capturar DnD no Windows quando há widgets filhos com QSS
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
        """Reaplica a cor dos botões do rodapé da lista — chamar após troca
        de tema em tempo real (sem isso, eles ficam presos à cor do tema
        com que a janela foi aberta)."""
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

        # Mesmo padrão de bug do estado de erro: cores fixas no código
        # sobrescrevem o QSS do tema. No dark, o cinza claro usado para
        # "disabled" (#cbd5e1) tinha alto contraste com o fundo escuro e
        # ficava parecido demais com a cor normal do texto — dando a
        # impressão de que os botões ainda eram clicáveis.
        _estilo_rodape = self._estilo_rodape_lista()

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

        self.label_inicio = QLabel(t("tempo.inicio") + ":")
        row_tempo.addWidget(self.label_inicio)
        self.entry_inicio = QLineEdit()
        self.entry_inicio.setPlaceholderText("00:00")
        self.entry_inicio.setFixedWidth(80)
        self.entry_inicio.setEnabled(False)
        row_tempo.addWidget(self.entry_inicio)

        self.label_fim = QLabel(t("tempo.fim") + ":")
        row_tempo.addWidget(self.label_fim)
        self.entry_fim = QLineEdit()
        self.entry_fim.setPlaceholderText("00:00")
        self.entry_fim.setFixedWidth(80)
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
        # ── Progresso ────────────────────────────────────────────────
        self.barra_animada = BarraAnimada()
        root.addWidget(self.barra_animada)

        # Row: [spinner] [status text]  — o spinner gira num label próprio
        # para não piscar o texto de progresso a cada frame.
        row_status = QHBoxLayout()
        row_status.setSpacing(4)
        row_status.setContentsMargins(0, 0, 0, 0)

        self.label_spinner = QLabel("")
        self.label_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_spinner.setFixedWidth(20)
        self.label_spinner.setObjectName("label_status")
        row_status.addWidget(self.label_spinner)

        self.label_status = QLabel(t("status.aguardando"))
        self.label_status.setObjectName("label_status")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_status.addWidget(self.label_status, 1)

        # widget-contêiner centralizado
        _status_container = QWidget()
        _status_container.setLayout(row_status)
        root.addWidget(_status_container, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spinner — anima apenas o label_spinner, não toca o label_status
        self._spinner_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spinner_idx    = 0
        self._spinner_timer  = QTimer(self)
        self._spinner_timer.setInterval(105)
        self._spinner_timer.timeout.connect(self._animar_spinner)

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

            # Status — antes da duração, alinhado à direita
            # PNG em vez de glifo de texto (✓ / !): a Noto Sans embutida não
            # contém esses glifos, e no Linux o fallback via fontconfig nem
            # sempre substitui por algo visível.
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

        # Cancela reset pendente de uma transcrição anterior e limpa os ícones
        # residuais (✓/!) que ela deixou na fila — sem isso, clicar "transcrever"
        # de novo antes dos 5s do reset automático deixava esses ícones visíveis
        # misturados com os arquivos da nova sessão.
        if self._timer_reset_barra is not None:
            self._timer_reset_barra.stop()
        for e in self.fila_arquivos:
            e.pop("status", None)

        self._desabilitar_controles()
        self.barra_animada.reset()
        # Delay proposital: sem ele, a barra começa a "surgir" no exato
        # instante do clique, quase junto com o resto da rajada de trabalho
        # síncrono deste método. Esperar um pouco antes de iniciar dá uma
        # pausa perceptível antes dela aparecer.
        QTimer.singleShot(
            300,
            lambda: self.barra_animada.start(self.configs.get("tema", "light")),
        )
        self.transcrevendo   = True
        self._seta_painel.reposicionar(self)
        self._seta_painel.raise_()
        # Pequeno delay proposital: sem ele, o fade-in começa no meio da
        # rajada de trabalho síncrono deste método (desabilitar controles,
        # renderizar lista, iniciar o worker) e a transição soma à travadinha
        # em vez de suavizá-la.
        QTimer.singleShot(150, self._seta_painel.aparecer_animado)
        self._renderizar_lista()   # bloqueia os ✕ imediatamente
        self._fila_idx       = 1
        self._fila_total     = len(self.fila_arquivos)
        self._spinner_idx    = 0
        self.label_spinner.setText(self._spinner_frames[0])
        self.label_status.setText(t("status.transcrevendo_spinner"))
        self._spinner_timer.start()

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
        self.barra_animada.cancel()
        if self._worker:
            self._worker.cancelar()
        if self.som_ativado:
            tocar_som("som_cancelar")

    def _on_progresso_fila(self, idx: int, total: int):
        self._fila_idx   = idx
        self._fila_total = total
        if self._painel_progresso is not None and 1 <= idx <= len(self.fila_arquivos):
            nome = self.fila_arquivos[idx - 1].get("nome", "")
            self._painel_progresso.reset(nome)

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
        self._spinner_timer.stop()
        self.label_spinner.setText("")
        self.transcrevendo = False
        self._esconder_painel_lateral()
        self._reativar_controles()
        dur = _duracao_str(elapsed)
        if concluidos < total:
            self.barra_animada.cancel()
            self.atualizar_status(t("status.concluidos_parcial",
                                    concluidos=concluidos, total=total, dur=dur))
            if self.som_ativado:
                tocar_som("som_cancelar")
            self._agendar_reset_barra(self._resetar_barra)
        else:
            self.barra_animada.complete()
            self.atualizar_status(t("status.concluido"))
            if self.som_ativado:
                tocar_som("som_notificacao")
            if total > 1:
                nomes = "\n".join(
                    f"• {e['nome']}" for e in self.fila_arquivos
                )
                corpo = f"{t('popup.tempo_decorrido', dur=dur)}\n\n{nomes}"
            else:
                nome = self.fila_arquivos[0]["nome"] if self.fila_arquivos else ""
                corpo = f"{t('popup.tempo_decorrido', dur=dur)}\n\n{nome}"

            PopupConclusao(self, corpo, self.pasta_saida, on_ok=self._resetar_barra)

    def _on_cancelado(self):
        self._spinner_timer.stop()
        self.label_spinner.setText("")
        self.transcrevendo = False
        self._esconder_painel_lateral()
        self.barra_animada.cancel()
        self.atualizar_status(t("status.cancelado"))
        self._reativar_controles()
        # Marca os itens não concluídos como erro JÁ AQUI, e renderiza —
        # é isso que deixa o ícone "!" visível. Antes, essa marcação e a
        # limpeza dela (via _resetar_barra) aconteciam nas duas linhas
        # seguintes, na mesma função, sem nenhum repaint entre elas — o
        # ícone nunca chegava a aparecer na tela.
        for e in self.fila_arquivos:
            if e.get("status") != "concluido":
                e["status"] = "erro"
        self._renderizar_lista()   # libera os ✕ e mostra os ícones de status
        self._agendar_reset_barra(self._resetar_barra)

    def _on_erro_geral(self, msg: str):
        self._spinner_timer.stop()
        self.label_spinner.setText("")
        self.transcrevendo = False
        self._esconder_painel_lateral()
        self.barra_animada.cancel()
        self.atualizar_status(f"Erro: {msg}")
        if self.som_ativado:
            tocar_som("som_cancelar")
        self._reativar_controles()
        self._agendar_reset_barra(self._resetar_barra)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resetar_barra(self):
        """Reseta barra, status e ícones da lista — sincronizados."""
        self.barra_animada.reset()
        self.label_spinner.setText("")
        self.label_status.setText(t("status.aguardando"))
        for e in self.fila_arquivos:
            e.pop("status", None)
        self._renderizar_lista()

    def _agendar_reset_barra(self, callback):
        """
        Agenda reset da barra em 5 s usando um QTimer reutilizável.
        Se já houver um reset pendente, cancela-o antes de agendar o novo —
        evita que um timer de transcrição anterior dispare no meio de uma nova.
        """
        if self._timer_reset_barra is None:
            self._timer_reset_barra = QTimer(self)
            self._timer_reset_barra.setSingleShot(True)
        else:
            self._timer_reset_barra.stop()
            # Desconecta todos os slots anteriores para não acumular callbacks
            try:
                self._timer_reset_barra.timeout.disconnect()
            except RuntimeError:
                pass
        self._timer_reset_barra.timeout.connect(callback)
        self._timer_reset_barra.start(5000)

    def atualizar_status(self, texto: str):
        self.label_status.setText(texto)

    def _animar_spinner(self):
        frame = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
        self.label_spinner.setText(frame)
        self._spinner_idx += 1
        # Atualiza o texto de fila apenas quando necessário (não sobrescreve progresso)
        if self._fila_total > 1:
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
        # Atualiza self.configs no lugar (para preservar idioma_app, formato_saida,
        # e quaisquer chaves futuras gerenciadas por outras janelas).
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

    def _alternar_painel_progresso(self):
        if self._painel_progresso is None:
            self._painel_progresso = PainelProgresso(self.configs.get("tema", "light"))
            self._painel_progresso.fechar_solicitado.connect(self._fechar_painel_progresso)
            if 1 <= self._fila_idx <= len(self.fila_arquivos):
                nome = self.fila_arquivos[self._fila_idx - 1].get("nome", "")
                self._painel_progresso.reset(nome)

        if self._painel_progresso.isVisible():
            self._fechar_painel_progresso()
        else:
            self._painel_progresso.abrir_animado(self)
            self._seta_painel.set_aberta(True)

    def _fechar_painel_progresso(self):
        if self._painel_progresso is not None:
            self._painel_progresso.fechar_animado()
        self._seta_painel.set_aberta(False)

    def _esconder_painel_lateral(self):
        """Chamado ao fim/cancelamento/erro de uma transcrição — some com
        a seta e fecha o painel, se estiver aberto."""
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
        # Cobre tanto minimizar para a bandeja quanto minimizar normal — o
        # painel (janela top-level própria) não deve ficar flutuando com a
        # principal escondida. O botão embutido já some sozinho, por ser
        # filho de verdade da janela.
        if self._painel_progresso is not None:
            self._painel_progresso.hide()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._reposicionar_painel_lateral()

    def closeEvent(self, event):
        # Fecha o painel — ainda é uma janela top-level própria, não filha,
        # então não some sozinho. O botão embutido é filho de verdade da
        # janela e é destruído junto automaticamente.
        if self._painel_progresso is not None:
            self._painel_progresso.close()

        # Cancela reset pendente para não disparar após destruição da janela
        if self._timer_reset_barra is not None:
            self._timer_reset_barra.stop()

        # Se o worker ainda está rodando, cancela e aguarda o encerramento
        # antes de apagar os arquivos temporários que ele pode estar usando.
        # wait() tem timeout de propósito: se o subprocesso do whisper-cli
        # ficar preso (pipe que não fecha no Windows, ver comentário em
        # whispercpp_engine.py), a app não pode travar pra sempre ao fechar —
        # melhor fechar mesmo assim do que virar um processo zumbi.
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
            # Limpa a pasta inválida para não tentar transcrever para lá
            self.pasta_saida = ""
            self.label_saida.setText(t("pasta.nenhuma"))
            self.salvar_configuracoes()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _calcular_pointsize(app) -> int:
    """
    Calcula o point size base de forma confiável para Windows e Linux,
    incluindo ambientes sem compositor (Openbox, i3, etc.).

    Ordem de prioridade:
      1. QT_FONT_DPI definido pelo usuário → respeita diretamente
      2. QT_SCALE_FACTOR definido pelo usuário → escala sobre 10pt base
      3. DPI lógico reportado pela tela principal
      4. Fallback seguro: 10pt (equivale a 96 DPI)

    Fórmula: pointSize = round(10 * dpi / 96)
      - 96 DPI  → 10pt  (Windows padrão, maioria dos Linux)
      - 120 DPI → 13pt  (125% no Windows)
      - 144 DPI → 15pt  (150% no Windows / HiDPI comum)
      - 192 DPI → 20pt  (200% / Retina)
    """
    # 1. Usuário forçou DPI de fonte explicitamente — honrar sem discussão
    font_dpi = os.environ.get("QT_FONT_DPI")
    if font_dpi:
        try:
            return round(10 * int(font_dpi) / 96)
        except ValueError:
            pass

    # 2. Usuário forçou fator de escala — aplicar sobre base 10pt
    scale = os.environ.get("QT_SCALE_FACTOR")
    if scale:
        try:
            return round(10 * float(scale))
        except ValueError:
            pass

    # 3. Ler DPI lógico da tela principal via Qt
    #    logicalDotsPerInchX é o mais confiável; cobre Xorg e Wayland.
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

    # 4. Fallback seguro
    return 10


def iniciar_app():
    # HiDPI: AA_EnableHighDpiScaling e AA_UseHighDpiPixmaps foram removidos
    # no PySide6 6.x — o comportamento é ativado por padrão automaticamente.
    # No Linux sem compositor (Openbox, i3...) use a variável de ambiente:
    #   QT_ENABLE_HIGHDPI_SCALING=1  antes de iniciar o app.

    app = QApplication.instance() or QApplication(sys.argv)

    # Fusion em todas as plataformas: evita que o Windows use o estilo
    # nativo (windowsvista / windows11 a partir do Qt 6.7), cujo popup de
    # combobox/menu é desenhado via Mica/DWM e ignora o background-color
    # do QSS (aparecia branco no Windows 11). No Linux isso já era
    # essencialmente o comportamento padrão na ausência de um tema de
    # plataforma específico — aqui fica explícito e não depende disso.
    app.setStyle("Fusion")

    # --- Fonte ---
    # Registra Noto Sans embutida via QRC (interface/assets/assets_rc.py,
    # compilado a partir de interface/assets/assets.qrc — prefixo /fonts).
    # Fallback automático para fontes do sistema se o recurso não existir.
    nome_fonte = None
    try:
        from PySide6.QtGui import QFontDatabase
        id1 = QFontDatabase.addApplicationFont(":/fonts/NotoSans-Regular.ttf")
        # Registro do peso Bold: só o efeito colateral importa (o Qt passa
        # a ter o arquivo Bold real disponível para a família), o retorno
        # não é consultado — daí o descarte explícito.
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

    # Pré-aquece o ffprobe logo após a janela aparecer.
    # Na primeira execução o SO ainda não tem o executável em cache de memória,
    # o que causa um delay visível ao arrastar o primeiro arquivo.
    # Rodar ffprobe -version em background "esquenta" o processo sem custo para o usuário.
    def _warmup_ffprobe():
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

    # Pré-aquece os sons (QSoundEffect) — evita que a primeira chamada real
    # de tocar_som() trave a interface ao inicializar o backend de áudio do SO.
    # QSoundEffect precisa rodar na thread da GUI, então usamos QTimer em vez
    # de uma thread — o singleShot(0, ...) só espera o loop de eventos girar
    # uma vez, então o custo cai fora do clique do usuário.
    from utils.audio import pre_aquecer
    QTimer.singleShot(
        0,
        lambda: pre_aquecer(["som_transcricao", "som_cancelar", "som_notificacao"]),
    )

    sys.exit(app.exec())
