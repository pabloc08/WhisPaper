# utils/theme.py

from settings.paths import ASSETS_DIR


def carregar_qss(tema: str = "light") -> str:
    """
    Lê o QSS do tema escolhido.
    - tema="dark"  → interface/assets/style_dark.qss
    - tema="light" → interface/assets/style.qss (padrão)
    Retorna string vazia se o arquivo não for encontrado.
    """
    nome_arquivo = "style_dark.qss" if tema == "dark" else "style.qss"
    qss_path = ASSETS_DIR / nome_arquivo
    try:
        return qss_path.read_text(encoding="utf-8")
    except OSError:
        try:
            return (ASSETS_DIR / "style.qss").read_text(encoding="utf-8")
        except OSError:
            return ""


def tema_inicial() -> str:
    try:
        from settings.config_manager import carregar_config
        return carregar_config().get("tema", "light")
    except Exception:
        return "light"


def aplicar_tema(tema: str) -> None:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.setStyleSheet(carregar_qss(tema))


def aplicar_flags_dialogo_secundario(widget) -> None:
    from PySide6.QtCore import Qt
    widget.setWindowFlags(
        Qt.WindowType.Dialog
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
    )
