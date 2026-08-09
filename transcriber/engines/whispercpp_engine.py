# transcriber/engines/whispercpp_engine.py

import os
import sys
import re
import signal
import subprocess
import threading
from pathlib import Path
from time import sleep, monotonic

from settings.paths import WHISPER_BINARY, get_silero_model
from utils.platform import flags_processo_oculto
from utils.logger import (
    log_engine_inicio, log_engine_fim, log_engine_cancelado, log_subprocess,
    log_info,
)
from transcriber.engines.base_engine import BaseEngine
from exceptions.engine_errors import (
    TranscricaoCancelada, BinarioNaoEncontrado, ModeloNaoEncontrado
)

# Timeout para as threads de leitura de stdout/stderr do whisper-cli.
# No Windows, o pipe às vezes não fecha mesmo após terminate()/kill() do
# processo (handle herdado por um processo neto que sobrevive) — sem esse
# timeout, .join() trava para sempre, o que por sua vez trava indefinidamente
# TranscricaoWorker.run() e, com isso, o self._worker.wait() do closeEvent
# da janela principal — a app inteira congela ao fechar (X não funciona).
_TIMEOUT_LEITURA_PIPE = 3.0

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

VERSAO_BINARIO = "1.9.0"

# ---------------------------------------------------------------------------
# Resolução do binário
#
# Binário único (whisper-cli + todas as .dll juntos em WHISPER_BIN).
# A escolha de backend não é mais "qual exe rodar", e sim "qual flag
# passar": o próprio whisper-cli (compilado com GGML_BACKEND_DL=ON +
# GGML_CPU_ALL_VARIANTS=ON) carrega as .dll de backend disponíveis na
# sua própria pasta e escolhe a melhor automaticamente — usa Vulkan se
# a .dll estiver presente e não for pedido -ng, senão cai na melhor
# variante de CPU. Ver _montar_comando() para a flag -ng.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class WhisperCppEngine(BaseEngine):

    supports_translation = True
    supports_gpu         = True
    supports_vad         = True

    def __init__(self):
        self._processo  = None
        self._cancelado = False

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_path:    Path,
        model_path:    Path,
        task:          str = "transcribe",
        language:      str = "auto",
        output_path:   Path = None,
        formato_saida: str = "ambos",
        vad_filter:    bool = False,
        on_progress:   callable = None,
        usar_gpu:      bool = False,
        temperature:   float = 0.0,
        beam_size:     int = 5,
    ) -> Path:
        self._cancelado = False

        binario = WHISPER_BINARY
        self._validar(model_path, binario)

        log_engine_inicio("whispercpp", model_path.name, str(audio_path))

        comando = self._montar_comando(
            binario, audio_path, model_path, task, language,
            output_path, formato_saida, vad_filter, usar_gpu,
            temperature, beam_size,
        )

        _t0 = monotonic()

        kwargs = self._popen_kwargs()

        self._processo = subprocess.Popen(comando, **kwargs)

        # Os segmentos reconhecidos ("[hh:mm:ss --> hh:mm:ss]  texto") são
        # impressos pelo whisper-cli no STDOUT (printf) — só logs de
        # diagnóstico (carregamento de modelo, system_info etc.) vão pro
        # stderr (fprintf(stderr, ...)). Ver whisper.cpp/examples/cli/cli.cpp.
        _RE_TIMESTAMP = re.compile(
            r"\[(\d{2}):(\d{2}):(\d{2})\.\d+ --> (\d{2}):(\d{2}):(\d{2})\.\d+\]\s*(.*)"
        )

        # stdout em thread separada, lido linha a linha (para progresso em
        # tempo real) — não bloquear o cancelamento. No Windows, a leitura
        # pode travar mesmo após terminate()/kill() enquanto o pipe não for
        # fechado pelo processo filho; por isso o timeout no .join() abaixo.
        stdout_lines: list[str] = []

        def _ler_stdout():
            for linha in self._processo.stdout:
                stdout_lines.append(linha)
                if on_progress is None:
                    continue
                m = _RE_TIMESTAMP.search(linha)
                if m:
                    h2, m2, s2 = int(m.group(4)), int(m.group(5)), int(m.group(6))
                    texto_segmento = m.group(7).strip()
                    on_progress(h2 * 3600 + m2 * 60 + s2, texto_segmento)

        t_stdout = threading.Thread(target=_ler_stdout, daemon=True)
        t_stdout.start()

        stderr_chunks: list[str] = []

        def _ler_stderr():
            try:
                stderr_chunks.append(self._processo.stderr.read())
            except Exception:
                pass

        t_stderr = threading.Thread(target=_ler_stderr, daemon=True)
        t_stderr.start()

        t_stdout.join(_TIMEOUT_LEITURA_PIPE)
        t_stderr.join(_TIMEOUT_LEITURA_PIPE)
        returncode = self._processo.wait()

        stdout_data = "".join(stdout_lines)
        stderr_data = "".join(stderr_chunks)
        elapsed = monotonic() - _t0

        log_subprocess("whispercpp", returncode, stdout_data, stderr_data)
        log_engine_fim("whispercpp", returncode, elapsed)

        if returncode != 0 and self._cancelado:
            raise TranscricaoCancelada("Transcrição cancelada pelo usuário.")

        if returncode != 0:
            # Vulkan foi pedido e falhou (driver ausente, init da GPU
            # quebrou etc.) → reexecuta o mesmo binário forçando -ng
            # (CPU only), silenciosamente.
            if usar_gpu and not self._cancelado:
                log_info(
                    "whisper-cli falhou com GPU habilitada "
                    f"(código {returncode}) — tentando novamente em CPU."
                )
                return self._transcrever_com_binario(
                    binario, audio_path, model_path, task, language,
                    output_path, formato_saida, vad_filter, on_progress,
                    usar_gpu=False, temperature=temperature, beam_size=beam_size,
                )
            detalhe = stderr_data.strip() or stdout_data.strip() or "(sem mensagem)"
            raise RuntimeError(
                f"whisper-cli encerrou com código {returncode}:\n{detalhe}"
            )

        return self._verificar_saida(output_path, formato_saida)

    def _transcrever_com_binario(
        self, binario, audio_path, model_path, task, language,
        output_path, formato_saida, vad_filter, on_progress,
        usar_gpu: bool = False, temperature: float = 0.0, beam_size: int = 5,
    ) -> Path:
        """Executa uma segunda tentativa (fallback), tipicamente forçando -ng."""
        comando = self._montar_comando(
            binario, audio_path, model_path, task, language,
            output_path, formato_saida, vad_filter, usar_gpu,
            temperature, beam_size,
        )

        _t0 = monotonic()
        kwargs = self._popen_kwargs()

        self._processo = subprocess.Popen(comando, **kwargs)

        # Mesma observação de transcribe(): segmentos vêm no STDOUT.
        _RE_TIMESTAMP = re.compile(
            r"\[(\d{2}):(\d{2}):(\d{2})\.\d+ --> (\d{2}):(\d{2}):(\d{2})\.\d+\]\s*(.*)"
        )
        stdout_lines: list[str] = []

        def _ler():
            for linha in self._processo.stdout:
                stdout_lines.append(linha)
                if on_progress is None:
                    continue
                m = _RE_TIMESTAMP.search(linha)
                if m:
                    h2, m2, s2 = int(m.group(4)), int(m.group(5)), int(m.group(6))
                    texto_segmento = m.group(7).strip()
                    on_progress(h2 * 3600 + m2 * 60 + s2, texto_segmento)

        t = threading.Thread(target=_ler, daemon=True)
        t.start()

        stderr_chunks2: list[str] = []

        def _ler_stderr2():
            try:
                stderr_chunks2.append(self._processo.stderr.read())
            except Exception:
                pass

        t_stderr2 = threading.Thread(target=_ler_stderr2, daemon=True)
        t_stderr2.start()

        t_stderr2.join(_TIMEOUT_LEITURA_PIPE)
        t.join(_TIMEOUT_LEITURA_PIPE)
        returncode = self._processo.wait()
        stdout_data = "".join(stdout_lines)
        stderr_data = "".join(stderr_chunks2)
        elapsed = monotonic() - _t0

        log_subprocess("whispercpp[cpu-fallback]", returncode, stdout_data, stderr_data)
        log_engine_fim("whispercpp[cpu-fallback]", returncode, elapsed)

        if returncode != 0 and self._cancelado:
            raise TranscricaoCancelada("Transcrição cancelada pelo usuário.")
        if returncode != 0:
            detalhe = stderr_data.strip() or stdout_data.strip() or "(sem mensagem)"
            raise RuntimeError(
                f"whisper-cli (cpu fallback) encerrou com código {returncode}:\n{detalhe}"
            )

        return self._verificar_saida(output_path, formato_saida)

    def _verificar_saida(self, output_path: Path, formato_saida: str) -> Path:
        if formato_saida in ("srt", "srt_vtt", "todos"):
            arquivo_verificar = output_path.with_suffix(".srt")
        elif formato_saida in ("vtt",):
            arquivo_verificar = output_path.with_suffix(".vtt")
        else:
            arquivo_verificar = output_path.with_suffix(".txt")

        if not arquivo_verificar.exists():
            raise FileNotFoundError(
                f"Arquivo de saída não gerado: {arquivo_verificar}"
            )
        return arquivo_verificar

    def cancel(self) -> None:
        self._cancelado = True
        log_engine_cancelado("whispercpp")
        proc = self._processo
        if proc is None or proc.poll() is not None:
            return
        try:
            if sys.platform != "win32":
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                sleep(0.5)
                if proc.poll() is None:
                    os.killpg(pgid, signal.SIGKILL)
            else:
                proc.terminate()
                sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
        except ProcessLookupError:
            pass

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _popen_kwargs(self) -> dict:
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text":   True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = flags_processo_oculto()
        else:
            kwargs["start_new_session"] = True
        return kwargs

    def _validar(self, model_path: Path, binario: Path = None) -> None:
        if binario is None:
            binario = WHISPER_BINARY
        if not binario.exists():
            raise BinarioNaoEncontrado(
                f"whisper-cli não encontrado em: {binario}"
            )
        if sys.platform != "win32" and not os.access(binario, os.X_OK):
            try:
                binario.chmod(binario.stat().st_mode | 0o111)
            except Exception as exc:
                raise BinarioNaoEncontrado(
                    f"whisper-cli sem permissão de execução: {exc}"
                )
        if not model_path.exists():
            raise ModeloNaoEncontrado(f"Modelo não encontrado: {model_path}")

    def _montar_comando(
        self,
        binario:       Path,
        audio_path:    Path,
        model_path:    Path,
        task:          str,
        language:      str,
        output_path:   Path,
        formato_saida: str,
        vad_filter:    bool = False,
        usar_gpu:      bool = False,
        temperature:   float = 0.0,
        beam_size:     int = 5,
    ) -> list:
        cmd = [
            str(binario),
            "-m", str(model_path),
            "-f", str(audio_path),
            "-of", str(output_path),
        ]

        # Binário único carrega todas as .dll de backend disponíveis na
        # própria pasta (Vulkan incluída) e usa GPU por padrão quando há
        # uma. -ng força CPU mesmo com a ggml-vulkan.dll presente —
        # é assim que o checkbox "usar_gpu" da UI é aplicado aqui.
        if not usar_gpu:
            cmd.append("-ng")
        if formato_saida in ("txt", "ambos", "txt_vtt", "todos"):
            cmd.append("-otxt")
        if formato_saida in ("srt", "ambos", "srt_vtt", "todos"):
            cmd.append("-osrt")
        if formato_saida in ("vtt", "srt_vtt", "txt_vtt", "todos"):
            cmd.append("-ovtt")

        lang = language.lower().strip() if language and language.strip() else "auto"

        if task == "translate":
            cmd.append("-tr")

        if lang != "auto":
            cmd += ["-l", lang]

        if vad_filter:
            cmd.append("--vad")
            modelo_silero = get_silero_model()
            if modelo_silero:
                cmd += ["-vm", str(modelo_silero)]
            else:
                log_info(
                    "VAD solicitado, mas nenhum modelo Silero (*silero*.bin) "
                    "foi encontrado em MODELS_DIR — seguindo sem VAD."
                )

        # -tp/-bs só são passados quando diferentes do padrão do próprio
        # whisper-cli (0.0 / 5) — evita poluir o comando à toa.
        if temperature != 0.0:
            cmd += ["-tp", str(temperature)]
        if beam_size != 5:
            # O whisper.cpp tem um teto rígido de decoders simultâneos (8) —
            # pedir mais que isso derruba o processo com "too many decoders
            # requested". Trava aqui como segurança, mesmo que a UI já limite
            # as opções, pra nunca mais quebrar por causa disso.
            beam_size_efetivo = min(beam_size, 8) if beam_size > 0 else beam_size
            if beam_size_efetivo != beam_size:
                log_info(
                    f"beam_size {beam_size} excede o máximo de decoders "
                    f"do whisper.cpp (8) — usando {beam_size_efetivo}."
                )
            cmd += ["-bs", str(beam_size_efetivo)]

        return cmd
