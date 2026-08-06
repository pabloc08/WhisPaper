# utils/platform.py

import os
import sys
import subprocess
from pathlib import Path


def _env_sistema() -> dict:
    env = os.environ.copy()
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def abrir_pasta(path: Path | str) -> None:
    """Abre o explorador de arquivos na pasta indicada."""
    path = Path(path)
    if not path.is_dir():
        return
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], env=_env_sistema())
    else:
        subprocess.Popen(["xdg-open", str(path)], env=_env_sistema())


def nome_executavel(base: str) -> str:
    """Retorna 'base.exe' no Windows, 'base' nos demais."""
    return f"{base}.exe" if sys.platform == "win32" else base


def flags_processo_oculto() -> int:
    """Retorna CREATE_NO_WINDOW no Windows, 0 nos demais."""
    if sys.platform == "win32":
        import subprocess as _sp
        return _sp.CREATE_NO_WINDOW
    return 0


def kwargs_processo() -> dict:
    """
    Retorna kwargs adicionais para subprocess.run/Popen.

    - Windows: creationflags=CREATE_NO_WINDOW (oculta a janela do console)
    - Linux/macOS: start_new_session=True (isola o processo filho em um novo
      process group, evitando processos órfãos caso o pai encerre abruptamente)

    Nota: creationflags e start_new_session são mutuamente exclusivos no
    Python — não podem ser usados juntos, daí a separação por plataforma.
    """
    if sys.platform == "win32":
        import subprocess as _sp
        return {"creationflags": _sp.CREATE_NO_WINDOW}
    return {"start_new_session": True}
