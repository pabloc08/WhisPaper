# settings/config_manager.py

import json
from settings.paths import CONFIG_PATH

CONFIG_PADRAO = {
    "engine":               "whispercpp",
    "model_id":             "large-v3-turbo",
    "task":                 "transcribe",
    "language":             "auto",
    "som":                  True,
    "pasta_saida":          "",
    "inicio_personalizado": "",
    "fim_personalizado":    "",
    "idioma_app":           "pt_BR",
    "formato_saida":        "ambos",
    "tema":                 "light",
    "onboarding_concluido":  False,
    "onboarding_nao_mostrar": False,
    "minimizar":            "padrao",
    "window_geometry":      "",
    "vad_filter":           False,
    "usar_gpu":             False,
}

def carregar_config() -> dict:
    if not CONFIG_PATH.exists():
        salvar_config(CONFIG_PADRAO)
        return CONFIG_PADRAO.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        for chave, valor in CONFIG_PADRAO.items():
            if chave not in config:
                config[chave] = valor
        return config
    except Exception:
        return CONFIG_PADRAO.copy()

def salvar_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
