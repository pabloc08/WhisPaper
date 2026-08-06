# interface/dialogs/general_config_dialog.py

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox,
)
from PySide6.QtCore import Qt

from interface.combo_box import ComboBoxPosicaoFixa
from settings.config_manager import salvar_config
from settings.i18n import t, idiomas_disponiveis
from utils.theme import aplicar_flags_dialogo_secundario


class JanelaConfigGeral(QDialog):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(t("config_geral.titulo"))
        self.setFixedSize(396, 340)
        self.setWindowIcon(parent.windowIcon())
        aplicar_flags_dialogo_secundario(self)
        self._construir()

    def _construir(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        tema = self.app.configs.get("tema", "light")
        cor_hint = "#64748b" if tema == "light" else "#7d8fa3"

        def _row(texto: str, widget, align_top: bool = False) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setSpacing(12)
            lbl = QLabel(f"<b>{texto}</b>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setFixedWidth(176)
            if align_top:
                row.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignTop)
            else:
                row.addWidget(lbl)
            row.addWidget(widget)
            row.addStretch()
            return row

        # ── Tema ─────────────────────────────────────────────────────────
        self.combo_tema = ComboBoxPosicaoFixa()
        self.combo_tema.setFixedWidth(143)
        self.combo_tema.addItem(t("config_geral.tema_light"), userData="light")
        self.combo_tema.addItem(t("config_geral.tema_dark"),  userData="dark")
        idx_tema = self.combo_tema.findData(tema)
        if idx_tema >= 0:
            self.combo_tema.setCurrentIndex(idx_tema)
        self.combo_tema.currentIndexChanged.connect(self._alterar_tema)
        layout.addLayout(_row(t("config_geral.tema"), self.combo_tema))

        # ── Minimizar ────────────────────────────────────────────────────
        self.combo_minimizar = ComboBoxPosicaoFixa()
        self.combo_minimizar.setFixedWidth(143)
        self.combo_minimizar.addItem(t("config_geral.minimizar_padrao"), userData="padrao")
        self.combo_minimizar.addItem(t("config_geral.minimizar_bandeja"), userData="bandeja")
        idx_min = self.combo_minimizar.findData(self.app.configs.get("minimizar", "padrao"))
        if idx_min >= 0:
            self.combo_minimizar.setCurrentIndex(idx_min)
        self.combo_minimizar.currentIndexChanged.connect(self._alterar_minimizar)

        # Esconde a opção no GNOME — systray não é suportado nativamente
        _desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" not in _desktop:
            layout.addLayout(_row(t("config_geral.minimizar"), self.combo_minimizar))

        # ── Idioma do app ────────────────────────────────────────────────
        self.combo_idioma = ComboBoxPosicaoFixa()
        self.combo_idioma.setFixedWidth(143)
        for codigo, nome in idiomas_disponiveis().items():
            self.combo_idioma.addItem(nome, userData=codigo)
        idx = self.combo_idioma.findData(self.app.configs.get("idioma_app", "pt_BR"))
        if idx >= 0:
            self.combo_idioma.setCurrentIndex(idx)
        self.combo_idioma.currentIndexChanged.connect(self._alterar_idioma)
        layout.addLayout(_row(t("config_geral.idioma_app"), self.combo_idioma))

        # ── Sons de notificação ──────────────────────────────────────────
        self.combo_som = ComboBoxPosicaoFixa()
        self.combo_som.setFixedWidth(143)
        self.combo_som.addItem(t("config_geral.sons_desativado"), userData=False)
        self.combo_som.addItem(t("config_geral.sons_ativado"),    userData=True)
        idx_som = self.combo_som.findData(self.app.configs.get("som", True))
        if idx_som >= 0:
            self.combo_som.setCurrentIndex(idx_som)
        self.combo_som.currentIndexChanged.connect(self._alterar_som)
        layout.addLayout(_row(t("config_geral.sons"), self.combo_som))

        # ── Formato de saída ─────────────────────────────────────────────
        fmt_salvo = self.app.configs.get("formato_saida", "ambos")
        _tem_txt = fmt_salvo in ("txt", "ambos", "txt_vtt", "todos")
        _tem_srt = fmt_salvo in ("srt", "ambos", "srt_vtt", "todos")
        _tem_vtt = fmt_salvo in ("vtt", "srt_vtt", "txt_vtt", "todos")

        self.chk_txt = QCheckBox(".txt")
        self.chk_txt.setChecked(_tem_txt)
        self.chk_txt.toggled.connect(self._alterar_formato)

        self.chk_srt = QCheckBox(".srt")
        self.chk_srt.setChecked(_tem_srt)
        self.chk_srt.toggled.connect(self._alterar_formato)

        self.chk_vtt = QCheckBox(".vtt")
        self.chk_vtt.setChecked(_tem_vtt)
        self.chk_vtt.toggled.connect(self._alterar_formato)

        chk_row = QHBoxLayout()
        chk_row.setContentsMargins(0, 0, 0, 0)
        chk_row.setSpacing(10)
        chk_row.addWidget(self.chk_txt)
        chk_row.addWidget(self.chk_srt)
        chk_row.addWidget(self.chk_vtt)
        chk_row.addStretch()

        lbl_fmt = QLabel(f"<b>{t('config_geral.formato_saida')}</b>")
        lbl_fmt.setTextFormat(Qt.TextFormat.RichText)
        lbl_fmt.setFixedWidth(176)

        lbl_fmt_hint = QLabel(t("config_geral.formato_saida_hint"))
        lbl_fmt_hint.setStyleSheet(f"color: {cor_hint}; font-size: 11px;")
        lbl_fmt_hint.setWordWrap(True)
        lbl_fmt_hint.setFixedWidth(176)

        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(2)
        left_col.addWidget(lbl_fmt)
        left_col.addWidget(lbl_fmt_hint)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(12)
        fmt_row.addLayout(left_col)
        fmt_row.addLayout(chk_row)
        fmt_row.addStretch()

        layout.addSpacing(8)
        layout.addLayout(fmt_row)

    # ------------------------------------------------------------------
    # Handlers — aplicação imediata (sem Salvar/Cancelar)
    # ------------------------------------------------------------------

    def _alterar_tema(self):
        tema_novo = self.combo_tema.currentData()
        self.app.configs["tema"] = tema_novo
        salvar_config(self.app.configs)
        from utils.theme import aplicar_tema
        aplicar_tema(tema_novo)
        self.app.atualizar_estilo_rodape()

    def _alterar_minimizar(self):
        modo = self.combo_minimizar.currentData()
        self.app.configs["minimizar"] = modo
        salvar_config(self.app.configs)
        self.app.aplicar_minimizar(modo)

    def _alterar_idioma(self):
        idioma_novo = self.combo_idioma.currentData()
        if idioma_novo == self.app.configs.get("idioma_app", "pt_BR"):
            return
        self.app.configs["idioma_app"] = idioma_novo
        salvar_config(self.app.configs)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            t("config_geral.titulo"),
            t("config_geral.msg_reiniciar"),
        )

    def _alterar_som(self):
        self.app.configs["som"] = self.combo_som.currentData()
        self.app.som_ativado    = self.combo_som.currentData()
        salvar_config(self.app.configs)

    def _formato_para_config(self) -> str:
        txt = self.chk_txt.isChecked()
        srt = self.chk_srt.isChecked()
        vtt = self.chk_vtt.isChecked()
        if txt and srt and vtt:  return "todos"
        if txt and srt:          return "ambos"
        if srt and vtt:          return "srt_vtt"
        if txt and vtt:          return "txt_vtt"
        if txt:                  return "txt"
        if srt:                  return "srt"
        if vtt:                  return "vtt"
        return "txt"

    def _alterar_formato(self):
        if not any([self.chk_txt.isChecked(),
                    self.chk_srt.isChecked(),
                    self.chk_vtt.isChecked()]):
            self.chk_txt.setChecked(True)
            return
        fmt = self._formato_para_config()
        self.app.configs["formato_saida"] = fmt
        self.app.formato_saida            = fmt
        salvar_config(self.app.configs)
