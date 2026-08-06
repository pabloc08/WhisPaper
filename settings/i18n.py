# settings/i18n.py
# Internacionalização — função t("chave") retorna string no idioma atual.
# Carregar idioma no boot via init_i18n() antes de criar qualquer janela.

import json
from pathlib import Path

_LOCALES_DIR  = Path(__file__).parent / "locales"
_IDIOMAS_DISP = {
    "pt_BR": "Português",
    "en_US": "English",
}
_IDIOMA_PADRAO = "pt_BR"

_strings: dict[str, str] = {}
_idioma_atual: str = _IDIOMA_PADRAO


def init_i18n(idioma: str) -> None:
    """
    Carrega as strings do idioma especificado.
    Deve ser chamado uma vez no boot, antes de criar qualquer janela.
    """
    global _strings, _idioma_atual

    if idioma not in _IDIOMAS_DISP:
        idioma = _IDIOMA_PADRAO

    arquivo = _LOCALES_DIR / f"{idioma}.json"
    if not arquivo.exists():
        idioma  = _IDIOMA_PADRAO
        arquivo = _LOCALES_DIR / f"{idioma}.json"

    with open(arquivo, "r", encoding="utf-8") as f:
        _strings = json.load(f)

    _idioma_atual = idioma


def t(chave: str, **kwargs) -> str:
    """
    Retorna a string localizada para a chave.
    Aceita kwargs para interpolação: t("popup.concluidos", n=3, total=3, tempo="5s")
    Fallback: retorna a própria chave se não encontrada.
    """
    texto = _strings.get(chave, chave)
    if kwargs:
        try:
            texto = texto.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return texto


def idioma_atual() -> str:
    """Retorna o código do idioma carregado (ex: 'pt_BR')."""
    return _idioma_atual


def idiomas_disponiveis() -> dict[str, str]:
    """Retorna dict {codigo: nome_exibicao} dos idiomas suportados."""
    return dict(_IDIOMAS_DISP)
