# utils/downloader.py

from __future__ import annotations

import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

# User-Agent genérico de navegador — máxima compatibilidade com CDNs,
# Hugging Face, gyan.dev, etc. Evita bloqueio por "bot detection".
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_CHUNK_SIZE      = 2*1024*1024          # 2 MB por leitura
_MAX_TENTATIVAS  = 5
_BACKOFF_BASE    = 2.0                  # segundos; dobra a cada tentativa
_BACKOFF_MAX     = 30.0
_NUM_CONEXOES    = 2                    # conexões paralelas no modo segmentado
_LIMIAR_PARALELO = 20*1024*1024        # só paraleliza acima de 20 MB
_MARGEM_DISCO    = 100*1024*1024       # folga mínima exigida no disco
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

_ERROS_TRANSITORIOS = (httpx.HTTPError, OSError)


class DownloadCancelado(Exception):
    """Levantada internamente quando o cancel_event é sinalizado."""


@dataclass
class Progresso:
    baixado: int
    total: int
    velocidade_bps: float
    eta_seg: Optional[float]


ProgressoCallback = Callable[[Progresso], None]


@dataclass
class _InfoRemota:
    total: int
    aceita_range: bool
    etag: Optional[str]
    last_modified: Optional[str]


# ---------------------------------------------------------------------------
# Medição de velocidade / ETA (thread-safe — usado também no modo paralelo)
# ---------------------------------------------------------------------------

class _MedidorVelocidade:
    """Velocidade média móvel (janela de ~2s) e ETA estimado."""

    def __init__(self, total: int, inicial: int = 0):
        self._total    = total
        self._lock     = threading.Lock()
        self._baixado  = inicial
        agora = time.monotonic()
        self._inicio    = agora
        self._amostras: list[tuple[float, int]] = [(agora, inicial)]

    def atualizar(self, incremento: int) -> Progresso:
        with self._lock:
            self._baixado += incremento
            agora = time.monotonic()
            self._amostras.append((agora, self._baixado))
            limite = agora - 2.0
            self._amostras = [a for a in self._amostras if a[0] >= limite] or [(agora, self._baixado)]

            t0, b0 = self._amostras[0]
            dt = agora - t0
            velocidade = (self._baixado - b0) / dt if dt > 0 else 0.0

            eta = None
            if velocidade > 0 and self._total:
                restante = max(self._total - self._baixado, 0)
                eta = restante / velocidade

            return Progresso(self._baixado, self._total, velocidade, eta)


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------

class HttpDownloader:

    def __init__(
        self,
        *,
        chunk_size: int = _CHUNK_SIZE,
        max_tentativas: int = _MAX_TENTATIVAS,
        num_conexoes: int = _NUM_CONEXOES,
        limiar_paralelo: int = _LIMIAR_PARALELO,
        timeout: httpx.Timeout = _TIMEOUT,
        cancel_event: Optional[threading.Event] = None,
    ):
        self.chunk_size      = chunk_size
        self.max_tentativas  = max_tentativas
        self.num_conexoes    = num_conexoes
        self.limiar_paralelo = limiar_paralelo
        self.timeout         = timeout
        self.cancel_event    = cancel_event or threading.Event()

    def cancelar(self) -> None:
        self.cancel_event.set()

    def _checar_cancelamento(self) -> None:
        if self.cancel_event.is_set():
            raise DownloadCancelado()

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------

    def baixar(
        self,
        url: str,
        destino: Path,
        callback_progresso: Optional[ProgressoCallback] = None,
    ) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial   = destino.with_name(destino.name + ".part")
        manifesto = destino.with_name(destino.name + ".part.json")

        with httpx.Client(
            follow_redirects=True,
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            info = self._info_remota(client, url)
            self._checar_espaco_disco(destino.parent, info.total, parcial)

            paralelo = (
                info.total > 0
                and info.aceita_range
                and info.total >= self.limiar_paralelo
                and self.num_conexoes > 1
            )
            if paralelo:
                self._baixar_paralelo(client, url, info, parcial, manifesto, callback_progresso)
            else:
                self._baixar_sequencial(client, url, info, parcial, manifesto, callback_progresso)

        if info.total and parcial.stat().st_size != info.total:
            raise RuntimeError(
                f"Download incompleto: {parcial.stat().st_size}/{info.total} bytes recebidos."
            )

        parcial.replace(destino)
        manifesto.unlink(missing_ok=True)
        return destino

    # ------------------------------------------------------------------
    # Descoberta de metadados remotos (tamanho, suporte a Range, validador)
    # ------------------------------------------------------------------

    def _info_remota(self, client: httpx.Client, url: str) -> _InfoRemota:
        with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as resp:
            headers = resp.headers
            aceita_range = resp.status_code == 206
            total = 0
            content_range = headers.get("Content-Range")
            if aceita_range and content_range and "/" in content_range:
                try:
                    total = int(content_range.rsplit("/", 1)[-1])
                except ValueError:
                    total = 0
            if not total:
                try:
                    total = int(headers.get("Content-Length", 0))
                except ValueError:
                    total = 0
                if aceita_range and not content_range:
                    aceita_range = False

            resp.close()

        return _InfoRemota(
            total=total,
            aceita_range=aceita_range,
            etag=headers.get("ETag"),
            last_modified=headers.get("Last-Modified"),
        )

    def _checar_espaco_disco(self, pasta: Path, total: int, parcial: Path) -> None:
        if not total:
            return
        ja_baixado = parcial.stat().st_size if parcial.exists() else 0
        necessario = max(total - ja_baixado, 0)
        livre = shutil.disk_usage(pasta).free
        if livre < necessario + _MARGEM_DISCO:
            raise RuntimeError(
                f"Espaço em disco insuficiente: necessário ~{necessario / 1024 / 1024:.0f} MB, "
                f"disponível ~{livre / 1024 / 1024:.0f} MB."
            )

    # ------------------------------------------------------------------
    # Manifesto (.part.json)
    # ------------------------------------------------------------------

    def _ler_manifesto(self, manifesto: Path) -> Optional[dict]:
        try:
            return json.loads(manifesto.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def _salvar_manifesto(self, manifesto: Path, info: _InfoRemota, segmentos=None) -> None:
        dados = {
            "etag": info.etag,
            "last_modified": info.last_modified,
            "total": info.total,
            "segmentos": segmentos,
        }
        try:
            manifesto.write_text(json.dumps(dados), encoding="utf-8")
        except OSError:
            pass

    def _resume_valido(self, antigo: Optional[dict], info: _InfoRemota) -> bool:
        sem_validador = info.etag is None and info.last_modified is None
        return (
            info.aceita_range
            and not sem_validador
            and antigo is not None
            and antigo.get("etag") == info.etag
            and antigo.get("last_modified") == info.last_modified
            and antigo.get("total") == info.total
        )

    # ------------------------------------------------------------------
    # Modo sequencial
    # ------------------------------------------------------------------

    def _baixar_sequencial(
        self, client, url, info, parcial: Path, manifesto: Path, callback
    ) -> None:
        if parcial.exists():
            antigo = self._ler_manifesto(manifesto)
            if not self._resume_valido(antigo, info):
                parcial.unlink(missing_ok=True)

        self._salvar_manifesto(manifesto, info)

        offset_inicial = parcial.stat().st_size if parcial.exists() else 0
        medidor = _MedidorVelocidade(info.total, inicial=offset_inicial)

        tentativa = 0
        while True:
            tentativa += 1
            self._checar_cancelamento()
            offset = parcial.stat().st_size if parcial.exists() else 0
            if info.total and offset >= info.total:
                return
            try:
                self._stream_sequencial(client, url, offset, parcial, medidor, callback)
                return
            except DownloadCancelado:
                raise
            except _ERROS_TRANSITORIOS as e:
                if tentativa >= self.max_tentativas:
                    raise RuntimeError(
                        f"Falha no download após {tentativa} tentativas: {e}"
                    ) from e
                self._aguardar_backoff(tentativa)

    def _stream_sequencial(self, client, url, offset, parcial: Path, medidor, callback) -> None:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        modo    = "r+b" if offset else "wb"

        with client.stream("GET", url, headers=headers) as resp:
            if offset and resp.status_code == 200:
                offset = 0
                modo   = "wb"
            resp.raise_for_status()

            with open(parcial, modo) as f:
                if offset:
                    f.seek(offset)
                for chunk in resp.iter_bytes(self.chunk_size):
                    self._checar_cancelamento()
                    f.write(chunk)
                    progresso = medidor.atualizar(len(chunk))
                    if callback:
                        callback(progresso)

    # ------------------------------------------------------------------
    # Modo paralelo (2 conexões)
    # ------------------------------------------------------------------

    def _gerar_segmentos(self, total: int, n: int) -> list[list[int]]:
        tamanho = total // n
        segmentos = []
        inicio = 0
        for i in range(n):
            fim = (total - 1) if i == n - 1 else (inicio + tamanho - 1)
            segmentos.append([inicio, fim, inicio])  # [inicio, fim, proximo_offset]
            inicio = fim + 1
        return segmentos

    def _baixar_paralelo(
        self, client, url, info, parcial: Path, manifesto: Path, callback
    ) -> None:
        antigo = self._ler_manifesto(manifesto) if parcial.exists() else None
        resume_ok = self._resume_valido(antigo, info) and antigo.get("segmentos")

        if resume_ok:
            segmentos = antigo["segmentos"]
        else:
            segmentos = self._gerar_segmentos(info.total, self.num_conexoes)
            with open(parcial, "wb") as f:
                f.truncate(info.total)

        self._salvar_manifesto(manifesto, info, segmentos=segmentos)

        baixado_inicial = sum(s[2] - s[0] for s in segmentos)
        medidor = _MedidorVelocidade(info.total, inicial=baixado_inicial)

        lock_manifesto = threading.Lock()
        ultimo_salvo   = {"t": 0.0}

        def salvar_throttled():
            agora = time.monotonic()
            with lock_manifesto:
                if agora - ultimo_salvo["t"] >= 1.0:
                    self._salvar_manifesto(manifesto, info, segmentos=segmentos)
                    ultimo_salvo["t"] = agora

        def baixar_segmento(idx: int) -> None:
            tentativa = 0
            while True:
                inicio, fim, proximo = segmentos[idx]
                if proximo > fim:
                    return
                tentativa += 1
                self._checar_cancelamento()
                try:
                    headers = {"Range": f"bytes={proximo}-{fim}"}
                    with client.stream("GET", url, headers=headers) as resp:
                        resp.raise_for_status()
                        with open(parcial, "r+b") as f:
                            f.seek(proximo)
                            for chunk in resp.iter_bytes(self.chunk_size):
                                self._checar_cancelamento()
                                f.write(chunk)
                                proximo += len(chunk)
                                segmentos[idx][2] = proximo
                                progresso = medidor.atualizar(len(chunk))
                                if callback:
                                    callback(progresso)
                                salvar_throttled()
                    with lock_manifesto:
                        self._salvar_manifesto(manifesto, info, segmentos=segmentos)
                    return
                except DownloadCancelado:
                    raise
                except _ERROS_TRANSITORIOS as e:
                    if tentativa >= self.max_tentativas:
                        raise RuntimeError(
                            f"Falha no segmento {idx} após {tentativa} tentativas: {e}"
                        ) from e
                    self._aguardar_backoff(tentativa)

        with ThreadPoolExecutor(max_workers=self.num_conexoes) as pool:
            futuros = [pool.submit(baixar_segmento, i) for i in range(len(segmentos))]
            erro = None
            for fut in as_completed(futuros):
                try:
                    fut.result()
                except Exception as e:
                    self.cancel_event.set()
                    if erro is None or isinstance(erro, DownloadCancelado):
                        erro = e
            if erro is not None and not isinstance(erro, DownloadCancelado):
                self.cancel_event.clear()
                raise erro
            if erro is not None:
                raise erro

        with lock_manifesto:
            self._salvar_manifesto(manifesto, info, segmentos=segmentos)

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    def _aguardar_backoff(self, tentativa: int) -> None:
        espera = min(_BACKOFF_BASE * (2 ** (tentativa - 1)), _BACKOFF_MAX)
        fim = time.monotonic() + espera
        while time.monotonic() < fim:
            self._checar_cancelamento()
            time.sleep(0.1)
