# settings/constants.py
# Dados estáticos do app — sem dependência de GUI ou engines.

VERSAO_APP   = "1.0.0"
PROJECT_URL  = "https://github.com/pabloc08/WhisPaper"

MAX_STEM_SAIDA = 12  # caracteres do nome original no arquivo de saída

FORMATOS_VALIDOS = {
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma",
    ".aiff", ".opus", ".amr", ".mp4", ".mov", ".avi", ".mkv",
    ".webm", ".3gp",
}

# Lista ordenada de códigos ISO dos idiomas de áudio suportados.
# Os nomes de exibição ficam nos arquivos de locale (chave "idioma.<codigo>").
IDIOMAS_AUDIO_CODIGOS: list[str] = [
    "auto",
    "pt", "en", "es", "fr", "de", "it", "ja", "zh", "ar",
    "ru", "ko", "nl", "pl", "tr", "sv", "no", "da", "fi",
    "el", "he", "hi", "id", "ro", "uk", "vi",
]

# Opções de tradução por engine (id_engine → lista de códigos ISO de destino,
# ou "disabled" como primeiro elemento para indicar "sem tradução").
# A UI traduz esses valores via t("idioma.<codigo>") e t("config_engine.desativado").
TRADUCAO_OPCOES: dict[str, list[str]] = {
    "whispercpp": ["disabled", "en"],
}
