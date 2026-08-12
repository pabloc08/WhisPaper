# interface/transcription_panel.py
# botão de expansão (SetaExpansao) + painel lateral de progresso (PainelProgresso).
# PainelProgresso não tem parent Qt (fica fora da geometria da janela principal);
# sua posição é sincronizada manualmente via moveEvent/resizeEvent de App (gui.py).

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QAbstractButton,
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QPoint,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve,
)
from PySide6.QtGui import QPainter, QPainterPath, QColor

from settings.i18n import t


def _formatar_tempo(segundos: int) -> str:
    """Formata segundos decorridos como 'MM:SS' (ou 'H:MM:SS' se passar de 1h)."""
    h, resto = divmod(int(segundos), 3600)
    m, s     = divmod(resto, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class SetaExpansao(QAbstractButton):
    """Triângulo desenhado à mão, encostado na borda direita da janela — aponta pra fora
    quando fechado, pra dentro quando o painel está aberto."""

    LARGURA      = 22
    ALTURA       = 60
    MARGEM_BORDA = 10   # distância até a borda direita da janela principal

    _COR       = QColor("#3b82f6")   # mesmo azul usado no resto do app
    _COR_HOVER = QColor("#2563eb")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.LARGURA, self.ALTURA)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._aberta = False

        self._efeito_opacidade = QGraphicsOpacityEffect(self)
        self._efeito_opacidade.setOpacity(1.0)
        self.setGraphicsEffect(self._efeito_opacidade)
        self._anim_opacidade = None   # mantém viva a animação em curso

    def set_aberta(self, aberta: bool):
        self._aberta = aberta
        self.update()

    def aparecer_animado(self):
        """Mostra o botão com fade-in suave, ao iniciar uma transcrição."""
        self.show()
        self._efeito_opacidade.setOpacity(0.0)
        anim = QPropertyAnimation(self._efeito_opacidade, b"opacity", self)
        anim.setDuration(700)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_opacidade = anim
        anim.start()

    def desaparecer_animado(self):
        """Esconde o botão com fade-out suave, ao terminar/cancelar/dar erro."""
        anim = QPropertyAnimation(self._efeito_opacidade, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(self._efeito_opacidade.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        self._anim_opacidade = anim
        anim.start()

    def reposicionar(self, janela):
        """Posiciona por dentro da borda direita, centralizado verticalmente."""
        x = janela.width() - self.LARGURA - self.MARGEM_BORDA
        y = (janela.height() - self.ALTURA) // 2
        self.move(x, y)

    # ------------------------------------------------------------------
    # Hover — força repintura pra atualizar cor/realce
    # ------------------------------------------------------------------

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        em_hover = self.underMouse()
        w, h     = self.width(), self.height()

        # cápsula de fundo, mais visível no hover
        alpha = 70 if em_hover else 38
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(59, 130, 246, alpha))
        painter.drawRoundedRect(self.rect(), 10, 10)

        # triângulo vira conforme o estado: fechado aponta pra fora, aberto pra dentro
        painter.setBrush(self._COR_HOVER if em_hover else self._COR)

        base_altura = 22
        comprimento = 10
        cy = h / 2

        path = QPainterPath()
        if self._aberta:
            base_x  = w * 0.68
            ponta_x = base_x - comprimento
        else:
            base_x  = w * 0.32
            ponta_x = base_x + comprimento

        path.moveTo(base_x, cy - base_altura / 2)
        path.lineTo(base_x, cy + base_altura / 2)
        path.lineTo(ponta_x, cy)
        path.closeSubpath()
        painter.drawPath(path)


class NavegadorFila(QWidget):
    """Navegador discreto '‹ N/T ›' pra circular entre os textos da fila; só aparece com >1 arquivo."""

    anterior_solicitado = Signal()
    proximo_solicitado  = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.btn_anterior = QPushButton("‹")
        self.btn_anterior.setObjectName("btn_navegador_fila")
        self.btn_anterior.setFixedSize(18, 18)
        self.btn_anterior.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_anterior.clicked.connect(self.anterior_solicitado.emit)
        layout.addWidget(self.btn_anterior)

        self.label_posicao = QLabel("1/1")
        self.label_posicao.setObjectName("label_navegador_fila")
        self.label_posicao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_posicao.setFixedWidth(34)
        layout.addWidget(self.label_posicao)

        self.btn_proximo = QPushButton("›")
        self.btn_proximo.setObjectName("btn_navegador_fila")
        self.btn_proximo.setFixedSize(18, 18)
        self.btn_proximo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_proximo.clicked.connect(self.proximo_solicitado.emit)
        layout.addWidget(self.btn_proximo)

    def definir_posicao(self, atual: int, total: int):
        self.label_posicao.setText(f"{atual}/{total}")
        self.btn_anterior.setEnabled(atual > 1)
        self.btn_proximo.setEnabled(atual < total)


class PainelProgresso(QWidget):
    """Janela lateral sem moldura: barra de progresso, tempo decorrido e
    transcrição sendo escrita em tempo real, efeito "máquina de escrever"."""

    fechar_solicitado = Signal()

    LARGURA           = 340
    MARGEM_SOMBRA      = 12   # espaço reservado pra sombra "vazar" por fora do card
    GAP_VERTICAL       = 40   # folga simétrica topo/baixo, painel "flutua" no meio
    ALTURA_MINIMA      = 220
    VELOCIDADE_CHARS  = 2     # caracteres inseridos por tick
    INTERVALO_TICK_MS = 16

    def __init__(self, tema: str = "light"):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._fila_texto   = ""
        self._texto_atual  = ""
        self._anim         = None   # mantém viva a animação de abrir/fechar

        # histórico por arquivo — navega entre transcrições sem esperar reset a cada arquivo
        self._historico          = []   # list[dict]: nome/texto/percentual/segundos
        self._indice_ativo       = None # índice que o worker está transcrevendo agora
        self._indice_visualizado = 0    # índice mostrado na tela
        self._seguir_ativo       = True # True = acompanha o arquivo ativo automaticamente

        self._construir()

        self._timer_digitacao = QTimer(self)
        self._timer_digitacao.setInterval(self.INTERVALO_TICK_MS)
        self._timer_digitacao.timeout.connect(self._tick_digitacao)

    # ------------------------------------------------------------------

    def _construir(self):
        m = self.MARGEM_SOMBRA

        # widget externo transparente só existe pra dar espaço à sombra;
        # o visual real mora no "container", estilizado via QSS
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(m, m, m, m)

        self.container = QWidget()
        self.container.setObjectName("painel_progresso")
        layout_externo.addWidget(self.container)

        sombra = QGraphicsDropShadowEffect(self.container)
        sombra.setBlurRadius(28)
        sombra.setOffset(0, 3)
        sombra.setColor(QColor(0, 0, 0, 80))
        self.container.setGraphicsEffect(sombra)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # ── Topo: título + fechar ────────────────────────────────────
        row_topo = QHBoxLayout()
        self.label_titulo = QLabel(t("painel_progresso.titulo"))
        self.label_titulo.setObjectName("label_painel_titulo")
        row_topo.addWidget(self.label_titulo, 1)

        btn_fechar = QPushButton("✕")
        btn_fechar.setObjectName("btn_painel_fechar")
        btn_fechar.setFixedSize(22, 22)
        btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fechar.clicked.connect(self.fechar_solicitado.emit)
        row_topo.addWidget(btn_fechar)
        layout.addLayout(row_topo)

        # ── Barra de progresso (%) colada + tempo mais discreto ─────
        row_barra = QHBoxLayout()
        row_barra.setSpacing(0)

        self.barra = QProgressBar()
        self.barra.setObjectName("barra_painel_progresso")
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        row_barra.addWidget(self.barra, 1)

        row_barra.addSpacing(6)
        self.label_percentual = QLabel("0%")
        self.label_percentual.setObjectName("label_painel_percentual")
        self.label_percentual.setFixedWidth(32)
        self.label_percentual.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_barra.addWidget(self.label_percentual)

        row_barra.addSpacing(14)
        self.label_tempo = QLabel("00:00")
        self.label_tempo.setObjectName("label_painel_tempo")
        self.label_tempo.setFixedWidth(52)  # cabe 'H:MM:SS', ex: '1:30:00'
        self.label_tempo.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_barra.addWidget(self.label_tempo)
        layout.addLayout(row_barra)

        # ── Texto da transcrição, ao vivo ────────────────────────────
        self.texto = QTextEdit()
        self.texto.setObjectName("texto_painel_transcricao")
        self.texto.setReadOnly(True)
        self.texto.setFrameShape(QTextEdit.Shape.NoFrame)
        layout.addWidget(self.texto, 1)

        # ── Rodapé: navegador da fila, discreto, alinhado à direita ──
        row_rodape = QHBoxLayout()
        row_rodape.setContentsMargins(0, 0, 0, 0)

        self.navegador = NavegadorFila()
        self.navegador.setVisible(False)   # só aparece com mais de 1 arquivo
        self.navegador.anterior_solicitado.connect(self._ir_anterior)
        self.navegador.proximo_solicitado.connect(self._ir_proximo)
        row_rodape.addStretch()
        row_rodape.addWidget(self.navegador)
        layout.addLayout(row_rodape)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def iniciar_fila(self, nomes: list):
        """Chamado uma vez no início da transcrição: prepara o histórico e mostra
        o navegador se houver mais de um arquivo."""
        self._historico = [
            {"nome": nome, "texto": "", "percentual": 0, "segundos": 0}
            for nome in nomes
        ]
        self._indice_ativo       = None
        self._indice_visualizado = 0
        self._seguir_ativo       = True
        self.navegador.setVisible(len(nomes) > 1)
        self._atualizar_navegador()

    def iniciar_arquivo(self, indice: int, nome: str = ""):
        """Chamado a cada novo arquivo do worker; só limpa a tela se o painel
        estiver acompanhando o arquivo ativo — senão o usuário mantém a navegação."""
        self._timer_digitacao.stop()
        self._fila_texto = ""

        while len(self._historico) <= indice:
            self._historico.append({"nome": "", "texto": "", "percentual": 0, "segundos": 0})
        if nome:
            self._historico[indice]["nome"] = nome

        self._indice_ativo = indice
        if self._seguir_ativo:
            self._indice_visualizado = indice
            self._renderizar_indice(indice)
        self._atualizar_navegador()

    def atualizar_progresso(self, segundos: int, percentual: float, texto_segmento: str):
        if self._indice_ativo is None:
            return
        item = self._historico[self._indice_ativo]

        pct = max(0, min(100, round(percentual)))
        item["percentual"] = pct
        item["segundos"]   = segundos

        texto_segmento = (texto_segmento or "").strip()
        if texto_segmento:
            prefixo = "\n\n" if item["texto"] else ""
            pedaco  = prefixo + texto_segmento
            item["texto"] += pedaco

            if self._indice_visualizado == self._indice_ativo:
                self._fila_texto += pedaco
                if not self._timer_digitacao.isActive():
                    self._timer_digitacao.start()

        if self._indice_visualizado == self._indice_ativo:
            self.barra.setValue(pct)
            self.label_percentual.setText(f"{pct}%")
            self.label_tempo.setText(_formatar_tempo(segundos))

    def posicionar_ao_lado(self, janela):
        """Reposiciona sem animação (drag/resize com o painel já aberto),
        centralizado verticalmente com folga simétrica em cima/embaixo."""
        m = self.MARGEM_SOMBRA
        altura_conteudo = max(self.ALTURA_MINIMA, janela.height() - 2 * self.GAP_VERTICAL)

        self.setFixedWidth(self.LARGURA + 2 * m)
        self.setFixedHeight(altura_conteudo + 2 * m)

        x = janela.x() + janela.width() - m
        y = janela.y() + (janela.height() - altura_conteudo) // 2 - m
        self.move(x, y)

    def abrir_animado(self, janela):
        """Mostra o painel com slide + fade a partir da borda da janela principal."""
        self.posicionar_ao_lado(janela)
        pos_final   = self.pos()
        pos_inicial = QPoint(pos_final.x() - 24, pos_final.y())

        self.move(pos_inicial)
        self.setWindowOpacity(0.0)
        self.show()

        anim_pos = QPropertyAnimation(self, b"pos", self)
        anim_pos.setDuration(350)
        anim_pos.setStartValue(pos_inicial)
        anim_pos.setEndValue(pos_final)
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_opacidade = QPropertyAnimation(self, b"windowOpacity", self)
        anim_opacidade.setDuration(325)
        anim_opacidade.setStartValue(0.0)
        anim_opacidade.setEndValue(1.0)
        anim_opacidade.setEasingCurve(QEasingCurve.Type.OutCubic)

        grupo = QParallelAnimationGroup(self)
        grupo.addAnimation(anim_pos)
        grupo.addAnimation(anim_opacidade)
        self._anim = grupo   # sem essa referência o GC mata a animação no meio
        grupo.start()

    def fechar_animado(self):
        """Esconde o painel com slide + fade reverso."""
        pos_atual   = self.pos()
        pos_destino = QPoint(pos_atual.x() - 24, pos_atual.y())

        anim_pos = QPropertyAnimation(self, b"pos", self)
        anim_pos.setDuration(300)
        anim_pos.setStartValue(pos_atual)
        anim_pos.setEndValue(pos_destino)
        anim_pos.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_opacidade = QPropertyAnimation(self, b"windowOpacity", self)
        anim_opacidade.setDuration(275)
        anim_opacidade.setStartValue(1.0)
        anim_opacidade.setEndValue(0.0)
        anim_opacidade.setEasingCurve(QEasingCurve.Type.InCubic)

        grupo = QParallelAnimationGroup(self)
        grupo.addAnimation(anim_pos)
        grupo.addAnimation(anim_opacidade)
        grupo.finished.connect(self.hide)
        self._anim = grupo
        grupo.start()

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _ir_anterior(self):
        self._seguir_ativo = False
        novo_indice = max(0, self._indice_visualizado - 1)
        self._navegar_para(novo_indice)

    def _ir_proximo(self):
        ultimo_indice = len(self._historico) - 1
        novo_indice   = min(ultimo_indice, self._indice_visualizado + 1)
        # volta a acompanhar automaticamente se alcançar o arquivo ativo
        self._seguir_ativo = (novo_indice == self._indice_ativo)
        self._navegar_para(novo_indice)

    def _navegar_para(self, indice: int):
        self._timer_digitacao.stop()
        self._fila_texto = ""
        self._indice_visualizado = indice
        self._renderizar_indice(indice)
        self._atualizar_navegador()

    def _renderizar_indice(self, indice: int):
        item = self._historico[indice]
        self._texto_atual = item["texto"]
        self.texto.setPlainText(item["texto"])
        cursor = self.texto.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.texto.setTextCursor(cursor)
        self.barra.setValue(item["percentual"])
        self.label_percentual.setText(f"{item['percentual']}%")
        self.label_tempo.setText(_formatar_tempo(item["segundos"]))
        self.label_titulo.setText(item["nome"] or t("painel_progresso.titulo"))

    def _atualizar_navegador(self):
        total = len(self._historico)
        if total <= 1:
            self.navegador.setVisible(False)
            return
        self.navegador.setVisible(True)
        self.navegador.definir_posicao(self._indice_visualizado + 1, total)

    def _tick_digitacao(self):
        if not self._fila_texto:
            self._timer_digitacao.stop()
            return
        n = self.VELOCIDADE_CHARS
        pedaco, self._fila_texto = self._fila_texto[:n], self._fila_texto[n:]
        self._texto_atual += pedaco
        cursor = self.texto.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(pedaco)
        self.texto.setTextCursor(cursor)
        self.texto.ensureCursorVisible()
