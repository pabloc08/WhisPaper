# interface/drag_drop.py
# Filtro de eventos na QApplication inteira em vez de dragEnterEvent/dropEvent do
# QMainWindow — no Windows o QSS cria janelas nativas nos filhos, que capturam o
# DnD antes de chegar ao QMainWindow. O filtro na app intercepta tudo antes.
#
# DragDropMixin espera que a classe (App, em gui.py) tenha:
#   self.drop_area, self.configs, self.adicionar_arquivo(caminho)

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
