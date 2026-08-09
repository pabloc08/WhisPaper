# settings/paths.py
# Todos os caminhos do app centralizados.
# Compatível com: desenvolvimento, PyInstaller, AppImage, Windows e Linux.
#
# Separação de responsabilidades:
#   - BASE_DIR    → onde está o código/executável (dentro do AppImage no Linux)
#   - APPDATA_DIR → dados do usuário: configs, logs, modelos, outputs
#                   Windows: %LOCALAPPDATA%\WhisPaper (NÃO Roaming — os
#                   binários do whisper.cpp + modelos podem passar de vários
#                   GB, e Roaming é sincronizado em perfis móveis
#                   corporativos; Local nunca é sincronizado pela rede)
#   - BINS_DIR    → binários do whisper-cli
#                   Windows : APPDATA_DIR/whisper/bin/  (instalador copia)
#                   Linux   : BASE_DIR/whisper/bin/     (embutido no AppImage)
#
# FFmpeg:
#   Windows → 1º shutil.which (sistema); 2º APPDATA_DIR/ffmpeg/bin/ (baixado)
#   Linux   → sempre shutil.which (sistema); app nunca gerencia

import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Base do programa (código / executável / AppImage)
# ---------------------------------------------------------------------------

if os.environ.get("APPIMAGE"):
    BASE_DIR = Path(os.environ["APPDIR"]) / "usr" / "share" / "whispaper"
elif getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# AppData — dados do usuário (configs, logs, modelos, outputs)
# ---------------------------------------------------------------------------

def _appdata_root() -> Path:
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))

APPDATA_DIR = _appdata_root() / "WhisPaper"
LOGS_DIR    = APPDATA_DIR / "logs"
TEMP_DIR    = APPDATA_DIR / "temp"
OUTPUT_DIR  = APPDATA_DIR / "output"
CONFIG_PATH = APPDATA_DIR / "config.json"

# Modelos — sempre em AppData (o usuário baixa/gerencia)
WHISPER_DIR        = APPDATA_DIR / "whisper"
MODELS_DIR         = WHISPER_DIR / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whispercpp"


def get_silero_model() -> Path | None:
    """
    Localiza o modelo Silero VAD (formato ggml, usado pelo whisper.cpp) em
    MODELS_DIR, sem depender de um nome de arquivo/versão fixo.

    Se houver mais de um arquivo (ex.: sobra de uma versão antiga não
    removida), usa o mais recente por data de modificação — não por ordem
    alfabética do nome, já que isso não reflete de forma confiável qual é
    a versão mais nova.
    """
    modelos = list(MODELS_DIR.glob("*silero*.bin"))
    if not modelos:
        return None
    return max(modelos, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Binários do whisper-cli
#
# Layout único: whisper-cli(.exe) + TODAS as .dll (ggml-cpu-*.dll,
# ggml-vulkan.dll etc.) juntos em WHISPER_BIN. Compilado com
# GGML_BACKEND_DL=ON + GGML_CPU_ALL_VARIANTS=ON — o próprio binário
# escolhe em runtime a melhor variante de CPU e usa Vulkan se disponível
# e solicitado (ggml_backend_load_all() procura as .dll na pasta do exe).
# A escolha GPU-sim/GPU-não é feita via flag de linha de comando (-ng),
# não por binário diferente — ver whispercpp_engine.py.
# ---------------------------------------------------------------------------

_EXE = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"

if sys.platform == "win32" or not os.environ.get("APPIMAGE"):
    _BIN_ROOT = APPDATA_DIR / "whisper" / "bin"
else:
    _BIN_ROOT = BASE_DIR / "whisper" / "bin"

WHISPER_BIN    = _BIN_ROOT
WHISPER_BINARY = WHISPER_BIN / _EXE


# ---------------------------------------------------------------------------
# FFmpeg
#
# Windows:
#   FFMPEG_LOCAL_DIR → pasta própria do app (usado quando não há no sistema)
#   FFMPEG_BIN / FFPROBE_BIN → resolvidos em runtime por ffmpeg_manager
#   (não defina o caminho final aqui — depende do que estiver disponível)
#
# Linux:
#   Sempre usa o binário do sistema. FFMPEG_LOCAL_DIR exportado apenas
#   para que imports de ffmpeg_manager não quebrem.
# ---------------------------------------------------------------------------

FFMPEG_LOCAL_DIR = APPDATA_DIR / "ffmpeg" / "bin"

if sys.platform == "win32":
    # Caminho local (usado se o sistema não tiver FFmpeg)
    FFMPEG_LOCAL_BIN  = FFMPEG_LOCAL_DIR / "ffmpeg.exe"
    FFMPEG_LOCAL_PROBE = FFMPEG_LOCAL_DIR / "ffprobe.exe"
else:
    # Linux — binários do sistema (resolvidos em runtime)
    FFMPEG_LOCAL_BIN   = Path("ffmpeg")   # placeholder; nunca usado diretamente
    FFMPEG_LOCAL_PROBE = Path("ffprobe")


# ---------------------------------------------------------------------------
# Assets do programa (ícones, sons, QSS)
# ---------------------------------------------------------------------------

ASSETS_DIR = BASE_DIR / "interface" / "assets"


# ---------------------------------------------------------------------------
# Criação automática dos diretórios de dados do usuário
# ---------------------------------------------------------------------------

def criar_diretorios() -> None:
    """Garante que todos os diretórios de runtime do usuário existam."""
    dirs = [
        LOGS_DIR,
        TEMP_DIR,
        OUTPUT_DIR,
        MODELS_DIR,
        WHISPER_MODELS_DIR,
    ]

    if sys.platform == "win32":
        dirs += [
            WHISPER_BIN,
            FFMPEG_LOCAL_DIR,   # criada antecipadamente para o download
        ]

    if sys.platform != "win32" and not os.environ.get("APPIMAGE"):
        dirs += [
            WHISPER_BIN,
        ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
