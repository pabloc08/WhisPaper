# settings/paths.py
# Todos os caminhos do app, centralizados. Compatível com dev, PyInstaller,
# AppImage, Windows e Linux.
#
#   BASE_DIR    → onde está o código/executável
#   APPDATA_DIR → dados do usuário (configs, logs, modelos, outputs);
#                 no Windows usa Local (não Roaming) porque os binários
#                 e modelos podem passar de vários GB
#   BINS_DIR    → binários do whisper-cli
#   FFmpeg      → Windows: sistema, senão baixa pra APPDATA_DIR; Linux: sempre sistema

import os
import sys
from pathlib import Path


# base do programa (código / executável / AppImage)

if os.environ.get("APPIMAGE"):
    BASE_DIR = Path(os.environ["APPDIR"]) / "usr" / "share" / "whispaper"
elif getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent


# appdata — dados do usuário (configs, logs, modelos, outputs)

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

# modelos — sempre em AppData (o usuário baixa/gerencia)
WHISPER_DIR        = APPDATA_DIR / "whisper"
MODELS_DIR         = WHISPER_DIR / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whispercpp"


def get_silero_model() -> Path | None:
    """Localiza o modelo Silero VAD em MODELS_DIR; se houver mais de um, usa o mais recente por data."""
    modelos = list(MODELS_DIR.glob("*silero*.bin"))
    if not modelos:
        return None
    return max(modelos, key=lambda p: p.stat().st_mtime)


# binários do whisper-cli — layout único: exe + todas as .dll juntos em
# WHISPER_BIN. Compilado com GGML_BACKEND_DL + GGML_CPU_ALL_VARIANTS, então
# o binário escolhe a variante de CPU e usa Vulkan em runtime. GPU sim/não
# é flag de linha de comando (-ng), não binário diferente — ver whispercpp_engine.py.

_EXE = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"

if sys.platform == "win32" or not os.environ.get("APPIMAGE"):
    _BIN_ROOT = APPDATA_DIR / "whisper" / "bin"
else:
    _BIN_ROOT = BASE_DIR / "whisper" / "bin"

WHISPER_BIN    = _BIN_ROOT
WHISPER_BINARY = WHISPER_BIN / _EXE


# ffmpeg — Windows: pasta própria em APPDATA_DIR usada só se não houver no
# sistema (caminho final resolvido em runtime por ffmpeg_manager); Linux:
# sempre binário do sistema, FFMPEG_LOCAL_DIR só existe pra import não quebrar

FFMPEG_LOCAL_DIR = APPDATA_DIR / "ffmpeg" / "bin"

if sys.platform == "win32":
    FFMPEG_LOCAL_BIN  = FFMPEG_LOCAL_DIR / "ffmpeg.exe"  # usado se o sistema não tiver FFmpeg
    FFMPEG_LOCAL_PROBE = FFMPEG_LOCAL_DIR / "ffprobe.exe"
else:
    FFMPEG_LOCAL_BIN   = Path("ffmpeg")   # placeholder; nunca usado diretamente — sempre do sistema
    FFMPEG_LOCAL_PROBE = Path("ffprobe")


# assets do programa (ícones, sons, QSS)

ASSETS_DIR = BASE_DIR / "interface" / "assets"


# criação automática dos diretórios de dados do usuário

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
            FFMPEG_LOCAL_DIR,   # criada antes, pro download
        ]

    if sys.platform != "win32" and not os.environ.get("APPIMAGE"):
        dirs += [
            WHISPER_BIN,
        ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
