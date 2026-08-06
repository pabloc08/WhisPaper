# transcriber/managers/model_manager.py
import shutil
import threading
from pathlib import Path
from typing import Optional, Callable

from settings.paths import MODELS_DIR
from utils.downloader import HttpDownloader, Progresso

# ---------------------------------------------------------------------------
# Modelos pré-configurados por engine
# ---------------------------------------------------------------------------
MODELOS_PREDEFINIDOS = {
    "whispercpp": [
        {
            "id": "small",
            "nome": "Small",
            "tamanho": "~488 MB",
            "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
            "arquivo": "ggml-small.bin",
        },
        {
            "id": "large-v3-turbo",
            "nome": "Large v3 Turbo",
            "tamanho": "~1.62 GB",
            "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin",
            "arquivo": "ggml-large-v3-turbo.bin",
        },
        {
            "id": "large-v3",
            "nome": "Large v3",
            "tamanho": "~3.1 GB",
            "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin",
            "arquivo": "ggml-large-v3.bin",
        },
    ]
}

_ARQUIVOS_PREDEFINIDOS = {
    m["arquivo"] for modelos in MODELOS_PREDEFINIDOS.values() for m in modelos
}

URL_HUGGINGFACE = "https://huggingface.co/ggerganov/whisper.cpp/tree/main"

# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class ModelManager:
    def __init__(self, engine_id: str):
        self.engine_id = engine_id
        self._models_dir = MODELS_DIR / engine_id
        self._models_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def listar_predefinidos(self) -> list[dict]:
        resultado = []
        for m in MODELOS_PREDEFINIDOS.get(self.engine_id, []):
            path = self._models_dir / m["arquivo"]
            resultado.append({**m, "instalado": path.exists(), "path": path})
        return resultado

    def listar_importados(self) -> list[dict]:
        resultado = []
        for path in sorted(self._models_dir.glob("*.bin")):
            if path.name not in _ARQUIVOS_PREDEFINIDOS:
                resultado.append({
                    "id": path.stem,
                    "nome": path.name,
                    "arquivo": path.name,
                    "path": path,
                    "importado": True,
                })
        return resultado

    def listar_instalados(self) -> list[dict]:
        predefinidos = [m for m in self.listar_predefinidos() if m["instalado"]]
        importados = self.listar_importados()
        return predefinidos + importados

    def get_path(self, model_id: str) -> Path:
        for m in MODELOS_PREDEFINIDOS.get(self.engine_id, []):
            if m["id"] == model_id:
                path = self._models_dir / m["arquivo"]
                if not path.exists():
                    raise FileNotFoundError(f"Modelo '{model_id}' não está instalado.")
                return path
        
        path = self._models_dir / f"{model_id}.bin"
        if path.exists():
            return path
        
        path2 = self._models_dir / model_id
        if path2.exists():
            return path2
            
        raise ValueError(f"Modelo '{model_id}' não encontrado para engine '{self.engine_id}'.")

    # ------------------------------------------------------------------
    # Download atômico com suporte a retomada (resume)
    # ------------------------------------------------------------------
    def baixar(
        self, 
        model_id: str, 
        callback_progresso: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None
    ) -> Path:
        """
        Baixa um modelo predefinido de forma atômica e com suporte a retomada.
        Utiliza o HttpDownloader robusto (retry, paralelismo, resume via .part.json).
        """
        modelos = MODELOS_PREDEFINIDOS.get(self.engine_id, [])
        modelo = next((m for m in modelos if m["id"] == model_id), None)
        
        if modelo is None:
            raise ValueError(f"Modelo '{model_id}' não encontrado para engine '{self.engine_id}'.")

        destino = self._models_dir / modelo["arquivo"]
        downloader = HttpDownloader(cancel_event=cancel_event)

        # Adaptador para manter compatibilidade com a assinatura antiga do callback (baixado, total)
        def _adaptador_progresso(prog: Progresso):
            if callback_progresso:
                callback_progresso(prog.baixado, prog.total)

        return downloader.baixar(modelo["url"], destino, callback_progresso=_adaptador_progresso)

    # ------------------------------------------------------------------
    # Importação manual
    # ------------------------------------------------------------------
    def importar(self, caminho_origem: Path) -> Path:
        caminho_origem = Path(caminho_origem)
        if not caminho_origem.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_origem}")
        if caminho_origem.suffix.lower() != ".bin":
            raise ValueError("Apenas arquivos .bin são suportados.")
        
        destino = self._models_dir / caminho_origem.name
        shutil.copy2(caminho_origem, destino)
        return destino

    # ------------------------------------------------------------------
    # Remoção
    # ------------------------------------------------------------------
    def remover(self, model_id: str) -> None:
        """Remove o arquivo .bin do modelo (predefinido ou importado)."""
        path = self.get_path(model_id)
        path.unlink()