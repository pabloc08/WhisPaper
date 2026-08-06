# utils/logger.py

import traceback
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")

def _hoje() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _append(log_path: Path, linha: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass  # nunca crashar por causa de log


def _log_dir() -> Path:
    # Import tardio para evitar dependência circular na inicialização
    from settings.paths import LOGS_DIR
    return LOGS_DIR


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def log_erro(e: Exception, contexto: str = "Erro não especificado") -> None:
    """Salva traceback completo de uma exceção."""
    hora     = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = _log_dir() / f"erro_{_hoje()}.log"
    _append(log_path,
        f"\n[{hora}] ❌ {contexto}\n"
        + traceback.format_exc().strip()
        + "\n" + "-" * 60
    )


def log_info(mensagem: str) -> None:
    """Evento de lifecycle genérico."""
    log_path = _log_dir() / f"info_{_hoje()}.log"
    _append(log_path, f"[{_now()}] {mensagem}")


def limpar_logs_antigos(dias: int = 7) -> None:
    """
    Remove arquivos de log com mais de `dias` dias.
    Chamada uma vez na inicialização do app — silenciosa em caso de falha.
    Padrões cobertos: erro_*, info_*, subprocess_*, erro_FATAL_*.
    """
    try:
        from datetime import timedelta
        limite = datetime.now() - timedelta(days=dias)
        log_dir = _log_dir()
        for arq in log_dir.glob("*.log"):
            try:
                if datetime.fromtimestamp(arq.stat().st_mtime) < limite:
                    arq.unlink()
            except OSError:
                pass
    except Exception:
        pass  # nunca crashar por causa de limpeza de log


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def log_pipeline_inicio(arquivo: str, engine_id: str, task: str, language: str) -> None:
    log_info(
        f"PIPELINE INÍCIO  arquivo={arquivo!r}  engine={engine_id}"
        f"  task={task}  lang={language}"
    )

def log_pipeline_fim(arquivo: str, elapsed: float, caminho_saida: str) -> None:
    log_info(
        f"PIPELINE FIM     arquivo={arquivo!r}  elapsed={elapsed:.1f}s"
        f"  saída={caminho_saida!r}"
    )

def log_pipeline_erro(arquivo: str, erro: Exception) -> None:
    log_info(f"PIPELINE ERRO    arquivo={arquivo!r}  erro={type(erro).__name__}: {erro}")
    log_erro(erro, contexto=f"pipeline — {arquivo}")


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------

def log_engine_inicio(engine_id: str, model_id: str, audio: str) -> None:
    log_info(
        f"ENGINE INÍCIO    engine={engine_id}  model={model_id!r}"
        f"  audio={audio!r}"
    )

def log_engine_fim(engine_id: str, returncode: int, elapsed: float) -> None:
    log_info(
        f"ENGINE FIM       engine={engine_id}  returncode={returncode}"
        f"  elapsed={elapsed:.1f}s"
    )

def log_engine_cancelado(engine_id: str) -> None:
    log_info(f"ENGINE CANCELADO engine={engine_id}")


# ---------------------------------------------------------------------------
# Subprocess (stdout / stderr brutos do whisper-cli e similares)
# ---------------------------------------------------------------------------

def log_subprocess(engine_id: str, returncode: int,
                   stdout: str, stderr: str) -> None:
    """Salva stdout/stderr completos do subprocess em arquivo próprio."""
    log_path = _log_dir() / f"subprocess_{_hoje()}.log"
    hora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bloco = (
        f"\n[{hora}] engine={engine_id}  returncode={returncode}\n"
        f"--- STDOUT ---\n{stdout.strip() or '(vazio)'}\n"
        f"--- STDERR ---\n{stderr.strip() or '(vazio)'}\n"
        + "-" * 60
    )
    _append(log_path, bloco)


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------

def log_ffmpeg_inicio(arquivo_entrada: str, arquivo_saida: str) -> None:
    log_info(
        f"FFMPEG INÍCIO    entrada={arquivo_entrada!r}"
        f"  saída={arquivo_saida!r}"
    )

def log_ffmpeg_fim(arquivo_saida: str, elapsed: float, returncode: int) -> None:
    log_info(
        f"FFMPEG FIM       saída={arquivo_saida!r}"
        f"  elapsed={elapsed:.1f}s  returncode={returncode}"
    )

def log_ffmpeg_erro(stderr: str) -> None:
    log_path = _log_dir() / f"subprocess_{_hoje()}.log"
    hora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _append(log_path,
        f"\n[{hora}] FFMPEG ERRO\n{stderr.strip()}\n" + "-" * 60
    )


# ---------------------------------------------------------------------------
# Cancelamento
# ---------------------------------------------------------------------------

def log_cancelamento(origem: str) -> None:
    """origem: 'usuario', 'timeout', 'shutdown', etc."""
    log_info(f"CANCELAMENTO     origem={origem!r}")


# ---------------------------------------------------------------------------
# Retrocompatibilidade — nomes usados no código existente
# ---------------------------------------------------------------------------

def salvar_erro(e: Exception, contexto: str = "Erro não especificado") -> None:
    log_erro(e, contexto)

def salvar_info(mensagem: str) -> None:
    log_info(mensagem)
