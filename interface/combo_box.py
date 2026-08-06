# interface/combo_box.py
# ComboBox com popup 100% customizado — não usa mais o popup nativo do
# QComboBox (QComboBoxPrivateContainer). Isso existe porque o popup
# nativo, no Windows, causava uma moldura preta visível ao redor do
# dropdown (ver histórico de investigação: margem interna de ~5px
# reservada pelo Qt na QListView, sem relação com o QBoxLayout; frame
# nativo do QFrame interno; timing de resize inconsistente). Depois de
# tentar várias camadas de correção em cima do widget privado do Qt
# (máscara, fundo, frame, eventFilter de resize), a solução definitiva
# foi parar de usar esse widget interno e desenhar o dropdown do zero,
# com controle total sobre geometria, transparência e renderização.
#
# A classe ainda desenha o item selecionado/hover com cantos
# arredondados — o Qt ignora border-radius em ::item:selected via QSS
# em vários estilos (Fusion, Breeze, windowsvista/windows11), então o
# retângulo de seleção sempre pintava quadrado por baixo,
# independente do QSS.

from PySide6.QtWidgets import (
    QComboBox, QApplication, QStyledItemDelegate, QStyle,
    QStyleOptionViewItem, QWidget,
)
from PySide6.QtCore import QPoint, QModelIndex, QEvent, Qt, QRect, QSize, QTimer
from PySide6.QtGui import QPainter, QColor, QPalette, QPen, QFontMetrics

from settings.config_manager import carregar_config


def _tema_atual() -> str:
    return carregar_config().get("tema", "light")


def _cores_selecao():
    """Cor de fundo e de texto do item selecionado/hover, conforme o tema atual."""
    if _tema_atual() == "dark":
        return QColor("#2C3A5E"), QColor("#7AABFF")
    return QColor("#eaf1ff"), QColor("#1a1a1a")  # azul bem sutil no tema claro


def _cor_fundo_popup() -> QColor:
    """Mesma cor de fundo usada em 'QComboBox QAbstractItemView' no QSS
    de cada tema (style.qss / style_dark.qss)."""
    if _tema_atual() == "dark":
        return QColor("#212227")
    return QColor("white")


def _cor_borda_popup() -> QColor:
    if _tema_atual() == "dark":
        return QColor("#3A3B42")
    return QColor("#cbd5e1")


class DelegateItemArredondado(QStyledItemDelegate):
    """
    Desenha o item da lista com cantos arredondados quando selecionado/
    destacado (seleção via mouse ou teclado — ver _ListaPopup, que unifica
    os dois num único estado de "realce", pintado aqui sempre como
    State_Selected).
    """

    def sizeHint(self, option, index):
        """
        Altura fixa do item, independente do estilo nativo da plataforma.

        Sem isso, a altura vem do cálculo padrão do QStyledItemDelegate,
        que no Windows (estilo windowsvista/windows11) reserva bem mais
        espaço vertical por item do que no Linux (Fusion/Breeze) — daí as
        opções aparecerem bem mais altas no Windows com o mesmo QSS.
        """
        tamanho = super().sizeHint(option, index)
        altura_texto = option.fontMetrics.height()
        tamanho.setHeight(altura_texto + 14)  # ~7px de respiro em cima/embaixo
        return tamanho

    def paint(self, painter: QPainter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        selecionado = bool(opt.state & QStyle.StateFlag.State_Selected)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if selecionado:
            cor_bg, cor_texto = _cores_selecao()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(cor_bg)
            rect = opt.rect.adjusted(2, 1, -2, -1)
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(cor_texto)
        else:
            painter.setPen(opt.palette.color(QPalette.ColorRole.Text))

        texto = index.data(Qt.ItemDataRole.DisplayRole)
        rect_conteudo = opt.rect.adjusted(8, 0, -8, 0)

        icone = index.data(Qt.ItemDataRole.DecorationRole)
        if icone is not None and not icone.isNull():
            tamanho_icone = opt.decorationSize if not opt.decorationSize.isEmpty() else QSize(16, 16)
            rect_icone = QStyle.alignedRect(
                Qt.LayoutDirection.LeftToRight,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                tamanho_icone,
                rect_conteudo,
            )
            icone.paint(painter, rect_icone)
            rect_conteudo = rect_conteudo.adjusted(tamanho_icone.width() + 8, 0, 0, 0)

        painter.drawText(
            rect_conteudo,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            str(texto) if texto is not None else "",
        )

        painter.restore()


class _ListaPopup(QWidget):
    """
    Popup do dropdown, desenhado inteiramente por nós — sem depender do
    QComboBoxPrivateContainer interno do Qt. Suporta rolagem (necessário
    pra listas longas, ex.: seletor de idioma com ~99 itens), navegação
    por teclado (setas/Enter/Esc) e busca por digitação (type-ahead).
    """

    _RAIO = 8
    _MARGEM = 6

    def __init__(self, combo: "ComboBoxPosicaoFixa"):
        super().__init__(
            None,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._combo = combo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._scroll = 0
        self._indice_realce = -1
        self._buffer_busca = ""
        self._timer_busca = QTimer(self)
        self._timer_busca.setSingleShot(True)
        self._timer_busca.timeout.connect(lambda: setattr(self, "_buffer_busca", ""))

    # ── geometria/dimensões ─────────────────────────────────────────
    def _altura_item(self) -> int:
        return self.fontMetrics().height() + 14

    def _num_itens(self) -> int:
        return self._combo.count()

    def _altura_conteudo(self) -> int:
        return self._altura_item() * self._num_itens()

    def _area_disponivel(self) -> QRect:
        tela = self._combo.screen() if hasattr(self._combo, "screen") else QApplication.primaryScreen()
        return tela.availableGeometry() if tela else QRect(0, 0, 800, 600)

    def _altura_maxima_permitida(self) -> int:
        return max(self._altura_item() * 3, int(self._area_disponivel().height() * 0.6))

    def sizeHint(self) -> QSize:
        largura = max(self._combo.width(), 140)
        altura = min(self._altura_conteudo(), self._altura_maxima_permitida()) + self._MARGEM * 2
        return QSize(largura, altura)

    def _area_visivel(self) -> int:
        return self.height() - self._MARGEM * 2

    def _precisa_scroll(self) -> bool:
        return self._altura_conteudo() > self._area_visivel()

    def _scroll_maximo(self) -> int:
        return max(0, self._altura_conteudo() - self._area_visivel())

    def _rect_item(self, i: int) -> QRect:
        y = self._MARGEM + i * self._altura_item() - self._scroll
        return QRect(self._MARGEM, y, self.width() - self._MARGEM * 2, self._altura_item())

    def _indice_no_y(self, y: int) -> int:
        y_conteudo = y - self._MARGEM + self._scroll
        i = int(y_conteudo // self._altura_item())
        return i if 0 <= i < self._num_itens() else -1

    def _garantir_item_visivel(self, i: int) -> None:
        if i < 0:
            return
        y_item = i * self._altura_item()
        area_visivel = self._area_visivel()
        if y_item < self._scroll:
            self._scroll = y_item
        elif y_item + self._altura_item() > self._scroll + area_visivel:
            self._scroll = y_item + self._altura_item() - area_visivel
        self._scroll = max(0, min(self._scroll, self._scroll_maximo()))

    def preparar_para_abrir(self) -> None:
        """Chamado antes de mostrar: posiciona o scroll no item atual."""
        self._indice_realce = self._combo.currentIndex()
        self._scroll = 0
        self._garantir_item_visivel(self._indice_realce)

    # ── pintura ──────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(_cor_fundo_popup())
        painter.setPen(QPen(_cor_borda_popup(), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), self._RAIO, self._RAIO)

        painter.setClipRect(self.rect().adjusted(1, 1, -1, -1))

        delegate = self._combo.itemDelegate()
        modelo = self._combo.model()
        fm = QFontMetrics(self.font())

        for i in range(modelo.rowCount()):
            rect = self._rect_item(i)
            if rect.bottom() < 0 or rect.top() > self.height():
                continue
            index = modelo.index(i, 0)
            opt = QStyleOptionViewItem()
            opt.rect = rect
            opt.state = QStyle.StateFlag.State_Enabled
            if i == self._indice_realce:
                opt.state |= QStyle.StateFlag.State_Selected
            opt.font = self.font()
            opt.fontMetrics = fm
            opt.palette = self.palette()
            opt.decorationSize = self._combo.iconSize()
            delegate.paint(painter, opt, index)

        if self._precisa_scroll():
            self._desenhar_barra_scroll(painter)

    def _desenhar_barra_scroll(self, painter: QPainter) -> None:
        altura_total = self._altura_conteudo()
        area_visivel = self._area_visivel()
        if altura_total <= 0:
            return
        proporcao = area_visivel / altura_total
        altura_barra = max(20, int(area_visivel * proporcao))
        maximo = self._scroll_maximo()
        pos_barra = int((self._scroll / maximo) * (area_visivel - altura_barra)) if maximo else 0
        rect_barra = QRect(self.width() - 6, self._MARGEM + pos_barra, 3, altura_barra)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(128, 128, 128, 110))
        painter.drawRoundedRect(rect_barra, 1, 1)

    # ── interação: mouse ─────────────────────────────────────────────
    def wheelEvent(self, event) -> None:
        if not self._precisa_scroll():
            return
        self._scroll -= event.angleDelta().y() // 2
        self._scroll = max(0, min(self._scroll, self._scroll_maximo()))
        self.update()

    def mouseMoveEvent(self, event) -> None:
        y = int(event.position().y()) if hasattr(event, "position") else event.y()
        i = self._indice_no_y(y)
        if i != self._indice_realce:
            self._indice_realce = i
            self.update()

    def leaveEvent(self, event) -> None:
        self._indice_realce = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        y = int(event.position().y()) if hasattr(event, "position") else event.y()
        i = self._indice_no_y(y)
        if i >= 0:
            self._combo.setCurrentIndex(i)
        self.close()

    # ── interação: teclado (setas, Enter, Esc, busca por digitação) ──
    def keyPressEvent(self, event) -> None:
        tecla = event.key()

        if tecla == Qt.Key.Key_Down:
            novo = min(self._num_itens() - 1, max(0, self._indice_realce) + 1)
            self._indice_realce = novo
            self._garantir_item_visivel(novo)
            self.update()
        elif tecla == Qt.Key.Key_Up:
            novo = max(0, self._indice_realce - 1) if self._indice_realce >= 0 else self._num_itens() - 1
            self._indice_realce = novo
            self._garantir_item_visivel(novo)
            self.update()
        elif tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._indice_realce >= 0:
                self._combo.setCurrentIndex(self._indice_realce)
            self.close()
        elif tecla == Qt.Key.Key_Escape:
            self.close()
        elif event.text().isalnum():
            self._buscar_por_digitacao(event.text())
        else:
            super().keyPressEvent(event)

    def _buscar_por_digitacao(self, caractere: str) -> None:
        self._buffer_busca += caractere.lower()
        self._timer_busca.start(700)  # reseta o buffer se parar de digitar

        modelo = self._combo.model()
        for i in range(modelo.rowCount()):
            texto = str(modelo.index(i, 0).data(Qt.ItemDataRole.DisplayRole) or "").lower().lstrip()
            if texto.startswith(self._buffer_busca):
                self._indice_realce = i
                self._garantir_item_visivel(i)
                self.update()
                return


class ComboBoxPosicaoFixa(QComboBox):
    """QComboBox com popup 100% customizado (ver _ListaPopup) — não usa
    mais o mecanismo nativo de popup do Qt."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(DelegateItemArredondado(self))
        self._popup = None

    def _obter_popup(self) -> _ListaPopup:
        if self._popup is None:
            self._popup = _ListaPopup(self)
        return self._popup

    def showPopup(self) -> None:
        # Não chama super().showPopup() de propósito — o popup nativo do
        # Qt não é usado. Ver comentário no topo do arquivo.
        popup = self._obter_popup()
        popup.preparar_para_abrir()
        popup.resize(popup.sizeHint())

        ponto_abaixo = self.mapToGlobal(QPoint(0, self.height()))
        x, y = ponto_abaixo.x(), ponto_abaixo.y()

        tela = self.screen() if hasattr(self, "screen") else QApplication.primaryScreen()
        area = tela.availableGeometry() if tela else None

        if area is not None:
            popup_altura = popup.height()
            popup_largura = popup.width()

            if y + popup_altura > area.bottom():
                ponto_acima = self.mapToGlobal(QPoint(0, 0))
                y = ponto_acima.y() - popup_altura

            if x + popup_largura > area.right():
                x = area.right() - popup_largura
            if x < area.left():
                x = area.left()

        popup.move(x, y)
        popup.show()
        popup.setFocus(Qt.FocusReason.PopupFocusReason)

    def hidePopup(self) -> None:
        # Idem: não chama super().hidePopup() — sem popup nativo pra fechar.
        if self._popup is not None and self._popup.isVisible():
            self._popup.close()
