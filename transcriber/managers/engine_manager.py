# transcriber/managers/engine_manager.py

from transcriber.engines.whispercpp_engine import WhisperCppEngine

# Stubs para engines futuras
# from transcriber.engines.faster_engine import FasterWhisperEngine
# from transcriber.engines.transformers_engine import TransformersEngine

# ---------------------------------------------------------------------------
# Registro de engines disponíveis
# ID interno → (nome de exibição, classe)
# ---------------------------------------------------------------------------

ENGINES = {
    "whispercpp": ("Whisper.cpp", WhisperCppEngine),
    # "faster-whisper": ("Faster Whisper", FasterWhisperEngine),
    # "transformers":   ("Transformers",   TransformersEngine),
}

# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class EngineManager:

    @staticmethod
    def get(engine_id: str):
        """
        Instancia e retorna a engine solicitada.
        Levanta ValueError se a engine não estiver registrada.
        """
        entrada = ENGINES.get(engine_id)
        if entrada is None:
            disponiveis = ", ".join(ENGINES.keys())
            raise ValueError(f"Engine '{engine_id}' não reconhecida. Disponíveis: {disponiveis}")
        _, cls = entrada
        return cls()

    @staticmethod
    def listar() -> list[str]:
        """Retorna lista de IDs internos das engines registradas."""
        return list(ENGINES.keys())

    @staticmethod
    def nome_exibicao(engine_id: str) -> str:
        """Retorna o nome de exibição da engine (ex: 'whispercpp' → 'Whisper.cpp')."""
        entrada = ENGINES.get(engine_id)
        return entrada[0] if entrada else engine_id

    @staticmethod
    def id_por_nome(nome: str) -> str:
        """Retorna o ID interno a partir do nome de exibição (inverso de nome_exibicao)."""
        for eid, (enome, _) in ENGINES.items():
            if enome == nome:
                return eid
        return nome  # fallback: devolve o próprio valor

    @staticmethod
    def suporta_traducao(engine_id: str) -> bool:
        """Consulta se a engine suporta tradução, sem instanciá-la."""
        entrada = ENGINES.get(engine_id)
        if entrada is None:
            return False
        _, cls = entrada
        return getattr(cls, "supports_translation", False)
