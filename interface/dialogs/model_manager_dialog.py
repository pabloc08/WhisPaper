# interface/dialogs/model_manager_dialog.py
# Janela de gerenciamento de modelos (instalar, remover, importar).

import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QFrame,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QFont

from transcriber.managers.model_manager import ModelManager, URL_HUGGINGFACE
from workers.download_worker import DownloadWorker
from settings.i18n import t
from utils.theme import aplicar_flags_dialogo_secundario


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Plain)
    return f


class JanelaGerenciadorModelos(QDialog):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(t("gerenciador.titulo"))
        self.setFixedSize(500, 520)
        self.setWindowIcon(parent.windowIcon())
        aplicar_flags_dialogo_secundario(self)
        self._construir()

    def _construir(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        manager = ModelManager(self.app.engine_id)

        titulo_pre = QLabel(t("gerenciador.disponiveis"))
        titulo_pre.setFont(QFont("", -1, QFont.Weight.Bold))
        layout.addWidget(titulo_pre)

        self.widget_predefinidos = QWidget()
        self.layout_predefinidos = QVBoxLayout(self.widget_predefinidos)
        self.layout_predefinidos.setContentsMargins(0, 0, 0, 0)
        self.layout_predefinidos.setSpacing(4)
        self._renderizar_predefinidos(manager)
        layout.addWidget(self.widget_predefinidos)

        layout.addSpacing(8)
        layout.addWidget(_sep())
        layout.addSpacing(6)

        titulo_imp = QLabel(t("gerenciador.importados"))
        titulo_imp.setFont(QFont("", -1, QFont.Weight.Bold))
        layout.addWidget(titulo_imp)

        self.widget_importados = QWidget()
        self.layout_importados = QVBoxLayout(self.widget_importados)
        self.layout_importados.setContentsMargins(0, 0, 0, 0)
        self.layout_importados.setSpacing(4)
        self._renderizar_importados(manager)
        layout.addWidget(self.widget_importados)

        layout.addStretch()
        layout.addWidget(_sep())

        # Feedback + botão cancelar download
        row_feedback = QHBoxLayout()
        self.label_feedback = QLabel("")
        self.label_feedback.setObjectName("label_cinza")
        row_feedback.addWidget(self.label_feedback, 1)

        self.btn_cancelar_dl = QPushButton("✕")
        self.btn_cancelar_dl.setObjectName("btn_icone")
        self.btn_cancelar_dl.setFixedSize(24, 24)
        self.btn_cancelar_dl.setToolTip(t("gerenciador.cancelar_dl"))
        _tema = self.app.configs.get("tema", "light")
        if _tema == "light":
            self.btn_cancelar_dl.setStyleSheet(
                "QPushButton { color: #dc2626; }"
                "QPushButton:hover { color: #b91c1c; }"
            )
        self.btn_cancelar_dl.clicked.connect(self._cancelar_download)
        self.btn_cancelar_dl.hide()
        row_feedback.addWidget(self.btn_cancelar_dl)
        layout.addLayout(row_feedback)

        # Rodapé
        rodape = QHBoxLayout()
        rodape.setSpacing(12)

        btn_importar = QPushButton(t("gerenciador.importar"))
        btn_importar.setFixedHeight(32)
        btn_importar.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        btn_importar.clicked.connect(self._importar)
        rodape.addWidget(btn_importar)

        btn_link = QPushButton(t("gerenciador.outros_modelos"))
        btn_link.setObjectName("btn_link")
        from PySide6.QtCore import Qt
        btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_link.clicked.connect(lambda: webbrowser.open(URL_HUGGINGFACE))
        rodape.addWidget(btn_link)
        rodape.addStretch()

        layout.addLayout(rodape)

    def _renderizar_predefinidos(self, manager: ModelManager):
        while self.layout_predefinidos.count():
            item = self.layout_predefinidos.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for m in manager.listar_predefinidos():
            self.layout_predefinidos.addWidget(self._linha_predefinido(m))

    def _linha_predefinido(self, m: dict) -> QWidget:
        frame = QWidget()
        row   = QHBoxLayout(frame)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        info = QLabel(f"{m['nome']}  •  {m['tamanho']}")
        row.addWidget(info, 1)

        if m["instalado"]:
            lbl = QLabel(t("gerenciador.instalado"))
            lbl.setStyleSheet("color: #16a34a; font-size: 11px;")
            lbl.setFixedWidth(80)
            row.addWidget(lbl)
            btn = QPushButton(t("gerenciador.remover"))
            btn.setObjectName("btn_remover")
            btn.setFixedSize(80, 28)
            btn.clicked.connect(lambda checked=False, mid=m["id"]: self._remover(mid))
            row.addWidget(btn)
        else:
            ph = QWidget()
            ph.setFixedWidth(80)
            row.addWidget(ph)
            btn = QPushButton(t("gerenciador.instalar"))
            btn.setFixedSize(80, 28)
            btn.clicked.connect(lambda checked=False, mid=m["id"]: self._baixar(mid))
            row.addWidget(btn)

        return frame

    def _renderizar_importados(self, manager: ModelManager):
        while self.layout_importados.count():
            item = self.layout_importados.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        importados = manager.listar_importados()
        if not importados:
            lbl = QLabel(t("gerenciador.nenhum_importado"))
            lbl.setObjectName("label_cinza")
            self.layout_importados.addWidget(lbl)
            return

        for m in importados:
            frame = QWidget()
            row   = QHBoxLayout(frame)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(8)
            lbl = QLabel(m["nome"])
            row.addWidget(lbl, 1)
            btn = QPushButton(t("gerenciador.remover"))
            btn.setObjectName("btn_remover")
            btn.setFixedSize(80, 28)
            btn.clicked.connect(lambda checked=False, mid=m["id"]: self._remover(mid))
            row.addWidget(btn)
            self.layout_importados.addWidget(frame)

    def _baixar(self, model_id: str):
        if hasattr(self, "_dl") and self._dl.isRunning():
            return
        self.label_feedback.setText(t("gerenciador.baixando", model=model_id))
        self.btn_cancelar_dl.show()
        self._dl = DownloadWorker(self.app.engine_id, model_id)
        self._dl.progresso.connect(
            lambda pct, mb: self.label_feedback.setText(
                t("gerenciador.baixando", model=model_id) + f" {pct}% ({mb:.1f} MB)"
            )
        )
        self._dl.concluido.connect(self._on_download_ok)
        self._dl.erro.connect(self._on_download_erro)
        self._dl.start()

    def _cancelar_download(self):
        if hasattr(self, "_dl") and self._dl.isRunning():
            self._dl.cancelar()
            self._dl.wait(3000)
            self.label_feedback.setText(t("gerenciador.cancelar_dl"))
            self.btn_cancelar_dl.hide()

    def _on_download_ok(self, model_id: str):
        self.label_feedback.setText(t("gerenciador.instalado_ok"))
        self.btn_cancelar_dl.hide()
        manager = ModelManager(self.app.engine_id)
        self._renderizar_predefinidos(manager)
        self._renderizar_importados(manager)
        self.app._atualizar_combo_modelos()

    def _on_download_erro(self, msg: str):
        self.label_feedback.setText(t("erro.prefixo", msg=msg))
        self.btn_cancelar_dl.hide()

    def _remover(self, model_id: str):
        dlg = QMessageBox(self)
        dlg.setWindowTitle(t("gerenciador.remover_titulo"))
        dlg.setText(t("gerenciador.confirmar_remover", model=model_id))
        dlg.setIcon(QMessageBox.Icon.Question)
        btn_sim = dlg.addButton(t("gerenciador.sim"), QMessageBox.ButtonRole.YesRole)
        dlg.addButton(t("gerenciador.nao"), QMessageBox.ButtonRole.NoRole)
        dlg.exec()
        if dlg.clickedButton() != btn_sim:
            return
        try:
            ModelManager(self.app.engine_id).remover(model_id)
            self.label_feedback.setText(t("gerenciador.removido_ok", model=model_id))
            manager = ModelManager(self.app.engine_id)
            self._renderizar_predefinidos(manager)
            self._renderizar_importados(manager)
            self.app._atualizar_combo_modelos()
        except Exception as e:
            self.label_feedback.setText(t("erro.prefixo", msg=str(e)))

    def _importar(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, t("gerenciador.importar"), "", "Modelo Whisper (*.bin)"
        )
        if not caminho:
            return
        try:
            destino = ModelManager(self.app.engine_id).importar(Path(caminho))
            self.label_feedback.setText(t("gerenciador.importado_ok", nome=destino.name))
            manager = ModelManager(self.app.engine_id)
            self._renderizar_importados(manager)
            self.app._atualizar_combo_modelos()
        except Exception as e:
            self.label_feedback.setText(t("erro.prefixo", msg=str(e)))

    def closeEvent(self, event):
        if hasattr(self, "_dl") and self._dl.isRunning():
            self._dl.cancelar()
            self._dl.wait(3000)
        super().closeEvent(event)
