# interface/tray.py
# TrayMixin espera que a classe que o usa (App, em gui.py) forneça:
#   self.configs        — dict de configuração (usa "tema")
#   self._usando_tray    — bool, inicializado em False no __init__ da classe
#   self._tray_obj       — QSystemTrayIcon | None, inicializado em None no __init__
# E que a classe seja um QWidget/QMainWindow (usa self.setWindowFlag,
# self.showNormal, self.activateWindow, self.raise_, self.windowIcon()).

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from settings.i18n import t


class TrayMixin:
    def aplicar_minimizar(self, modo: str):
        """Configura o comportamento de minimizar: 'padrao' ou 'bandeja'."""
        if modo == "bandeja":
            if self._usando_tray:
                return  # já configurado
            if not QSystemTrayIcon.isSystemTrayAvailable():
                # Ambiente sem bandeja funcional (ex: GNOME sem extensão
                # AppIndicator) — cai pro minimizar padrão em vez de
                # esconder a janela sem forma de trazê-la de volta.
                self._usando_tray = False
                return
            _icon = QIcon(":/icons/whispaper.png")
            tray_icon = _icon if not _icon.isNull() else self.windowIcon()

            tray = QSystemTrayIcon(tray_icon, self)
            tray.setToolTip("WhisPaper")

            menu = QMenu(self)
            menu.setObjectName("tray_menu")

            tema = self.configs.get("tema", "light")
            if tema == "dark":
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #1e293b;
                        color: #f1f5f9;
                        border: 1px solid #334155;
                        border-radius: 6px;
                        padding: 4px;
                    }
                    QMenu::item {
                        padding: 6px 20px;
                        border-radius: 4px;
                    }
                    QMenu::item:selected {
                        background-color: #334155;
                    }
                    QMenu::separator {
                        height: 1px;
                        background: #334155;
                        margin: 4px 8px;
                    }
                """)
            else:
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #f8fafc;
                        color: #0f172a;
                        border: 1px solid #cbd5e1;
                        border-radius: 6px;
                        padding: 4px;
                    }
                    QMenu::item {
                        padding: 6px 20px;
                        border-radius: 4px;
                    }
                    QMenu::item:selected {
                        background-color: #e2e8f0;
                    }
                    QMenu::separator {
                        height: 1px;
                        background: #e2e8f0;
                        margin: 4px 8px;
                    }
                """)
            acao_restaurar = QAction(t("tray.restaurar"), self)
            acao_restaurar.triggered.connect(self._restaurar_janela)
            menu.addAction(acao_restaurar)
            menu.addSeparator()
            acao_sair = QAction(t("tray.sair"), self)
            acao_sair.triggered.connect(QApplication.instance().quit)
            menu.addAction(acao_sair)

            tray.setContextMenu(menu)
            tray.activated.connect(self._tray_ativado)
            tray.show()
            self._tray_obj    = tray
            self._usando_tray = True
        else:
            if not self._usando_tray:
                return
            if self._tray_obj is not None:
                self._tray_obj.hide()
                self._tray_obj = None
            self._usando_tray = False

    def _tray_ativado(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restaurar_janela()

    def _restaurar_janela(self):
        self.setWindowFlag(Qt.WindowType.Tool, False)
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def changeEvent(self, event):
        """Intercepta minimizar — manda para bandeja quando configurado."""
        if (event.type() == QEvent.Type.WindowStateChange
                and self.isMinimized()
                and self._usando_tray):
            event.ignore()
            self.setWindowFlag(Qt.WindowType.Tool, True)
            self.hide()
            return
        super().changeEvent(event)
