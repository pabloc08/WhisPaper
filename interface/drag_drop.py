# interface/drag_drop.py
# Implementada como um filtro de eventos na QApplication inteira, e não como
# dragEnterEvent/dropEvent normais do QMainWindow — no Windows, o QSS força
# criação de janelas nativas nos widgets filhos, que capturam os eventos de
# DnD antes deles chegarem ao QMainWindow. O filtro na QApplication intercepta
# tudo antes de qualquer widget filho processar, garantindo que o drop
# funcione independente de qual filho está sob o cursor.
#
# DragDropMixin espera que a classe que o usa (App, em gui.py) forneça:
#   self.drop_area       — widget com .highlight(bool, tema)
#   self.configs         — dict de configuração (usa "tema")
#   self.adicionar_arquivo(caminho) — método que processa cada arquivo solto

import os

from PySide6.QtCore import QEvent


class DragDropMixin:
    def eventFilter(self, obj, event):
        t_ev = event.type()
        if t_ev == QEvent.Type.DragEnter:
            if event.mimeData().hasUrls():
                self.drop_area.highlight(True, self.configs.get("tema", "light"))
                event.acceptProposedAction()
                return True
        elif t_ev == QEvent.Type.DragMove:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        elif t_ev == QEvent.Type.DragLeave:
            self.drop_area.highlight(False)
            return True
        elif t_ev == QEvent.Type.Drop:
            self.drop_area.highlight(False)
            caminhos = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.isLocalFile()
            ]
            for c in caminhos:
                if os.path.isfile(c):
                    self.adicionar_arquivo(c)
            event.acceptProposedAction()
            return True
        return super().eventFilter(obj, event)
