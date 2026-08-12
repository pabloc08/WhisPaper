# main.py

import sys
import traceback
from pathlib import Path
from datetime import datetime


def salvar_erro_global(exc_type, exc_value, exc_traceback):
    """Handler de último recurso — roda antes de qualquer import do projeto."""
    try:
        from settings.paths import LOGS_DIR
        LOG_DIR = LOGS_DIR
    except Exception:
        import os
        if sys.platform == "win32":
            LOG_DIR = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "WhisPaper" / "logs"
        else:
            LOG_DIR = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "WhisPaper" / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    hora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = LOG_DIR / f"erro_FATAL_{hora}.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("❌ ERRO FATAL NÃO TRATADO:\n\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)


sys.excepthook = salvar_erro_global

# python main.py --reset-onboarding
if "--reset-onboarding" in sys.argv:
    from settings.config_manager import CONFIG_PADRAO, salvar_config
    salvar_config(CONFIG_PADRAO.copy())
    print("✅ Config resetado para os padrões de fábrica. Abra o app normalmente para ver o wizard.")
    sys.exit(0)

from settings.config_manager import carregar_config
from settings.i18n import init_i18n
_cfg = carregar_config()
init_i18n(_cfg.get("idioma_app", "pt_BR"))

from utils.logger import limpar_logs_antigos
limpar_logs_antigos(dias=7)

from settings.paths import criar_diretorios
criar_diretorios()


def _verificar_ffmpeg_linux(app) -> bool:
    """Retorna True se ok. False = encerrar."""
    import shutil
    from PySide6.QtWidgets import QMessageBox
    from settings.i18n import t

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True

    QMessageBox.critical(
        None,
        t("ffmpeg_popup.titulo"),
        t("ffmpeg_popup.instrucao_linux"),
    )
    return False


def _rodar_wizard(app) -> bool:
    from interface.dialogs.welcome_dialog import JanelaBoasVindas
    wizard = JanelaBoasVindas()
    return wizard.exec() == JanelaBoasVindas.DialogCode.Accepted


def _rodar_popup_ffmpeg(app) -> bool:
    from interface.dialogs.ffmpeg_missing_popup import PopupFFmpegAusente
    popup = PopupFFmpegAusente()
    return popup.exec() == PopupFFmpegAusente.DialogCode.Accepted


def _checar_ffmpeg_e_onboarding(app) -> bool:
    from utils.ffmpeg_manager import ffmpeg_instalado, limpar_arquivos_parciais
    from interface.dialogs.welcome_dialog import deve_mostrar_boas_vindas

    limpar_arquivos_parciais()

    if sys.platform != "win32":
        if deve_mostrar_boas_vindas():
            return _rodar_wizard(app)
        return _verificar_ffmpeg_linux(app)

    if deve_mostrar_boas_vindas():
        return _rodar_wizard(app)

    if not ffmpeg_instalado():
        return _rodar_popup_ffmpeg(app)

    return True


from interface.gui import iniciar_app

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    # sem isso, no Windows 11 a animação do combo interrompe o reposicionamento e o popup pisca
    from PySide6.QtCore import Qt as _Qt
    _app.setEffectEnabled(_Qt.UIEffect.UI_AnimateCombo, False)

    # QSS antes de qualquer janela (inclusive o wizard), senão o estilo só assenta após a primeira interação
    from utils.theme import carregar_qss, tema_inicial
    _app.setStyleSheet(carregar_qss(tema_inicial()))

    if not _checar_ffmpeg_e_onboarding(_app):
        sys.exit(1)

    # reaplica com o idioma final (pode ter mudado no wizard)
    init_i18n(carregar_config().get("idioma_app", "pt_BR"))

    iniciar_app()
