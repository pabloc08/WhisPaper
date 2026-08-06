# exceptions/conversion_errors.py


class ConversionError(Exception):
    """Erro durante conversão de áudio."""

class FFmpegNaoEncontrado(ConversionError):
    """FFmpeg não encontrado no caminho esperado."""
