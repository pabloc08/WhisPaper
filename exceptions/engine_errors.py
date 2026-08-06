# exceptions/engine_errors.py


class EngineError(Exception):
    """Erro genérico de engine."""

class BinarioNaoEncontrado(EngineError):
    """Binário da engine não encontrado."""

class ModeloNaoEncontrado(EngineError):
    """Arquivo .bin do modelo não encontrado."""

class TranscricaoCancelada(EngineError):
    """Transcrição interrompida pelo usuário."""
