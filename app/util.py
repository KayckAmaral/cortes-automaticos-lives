"""Utilidades comuns: caminhos, binários, config e logs."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent

# Evita abrir janelas de console para cada subprocesso no Windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


_LOCAL = Path(os.environ.get("LOCALAPPDATA", ""))


def _achar_bin(nome: str, extras: list[Path]) -> str:
    achado = shutil.which(nome)
    if achado:
        return achado
    for p in extras:
        if p.exists():
            return str(p)
    # PATH desatualizado (shell aberto antes da instalação): procura no winget
    for p in sorted((_LOCAL / "Microsoft/WinGet/Packages").glob(f"*/*/bin/{nome}.exe")):
        return str(p)
    raise FileNotFoundError(f"Não achei o executável '{nome}'. Ele está instalado?")


FFMPEG = _achar_bin("ffmpeg", [_LOCAL / "Microsoft/WinGet/Links/ffmpeg.exe"])
FFPROBE = _achar_bin("ffprobe", [_LOCAL / "Microsoft/WinGet/Links/ffprobe.exe"])
STREAMLINK = _achar_bin("streamlink", [_LOCAL / "Programs/Streamlink/bin/streamlink.exe"])


def carregar_config(caminho: Path | str = RAIZ / "config.yaml") -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


ARQ_CANAIS = RAIZ / "canais.yaml"


def carregar_canais(cfg: dict) -> list[dict]:
    """Canais ficam em canais.yaml (gerenciado pelo painel). Na 1ª vez, copia do config.yaml."""
    if ARQ_CANAIS.exists():
        with open(ARQ_CANAIS, encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("canais") or []
    return list(cfg.get("canais") or [])


def salvar_canais(canais: list[dict]):
    tmp = ARQ_CANAIS.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("# Gerenciado pelo painel (http://localhost:8000). Pode editar à mão com o sistema parado.\n")
        yaml.safe_dump({"canais": canais}, f, allow_unicode=True, sort_keys=False)
    tmp.replace(ARQ_CANAIS)


def config_canal(cfg: dict, canal: dict, secao: str) -> dict:
    """Mescla a seção global com a sobrescrita do canal (ex.: detector)."""
    base = dict(cfg.get(secao) or {})
    base.update(canal.get(secao) or {})
    return base


def configurar_logs(nome: str = "cortes") -> logging.Logger:
    pasta = RAIZ / "logs"
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y-%m-%d}.log"
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    raiz = logging.getLogger()
    if not raiz.handlers:
        raiz.setLevel(logging.INFO)
        fh = logging.FileHandler(arquivo, encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        raiz.addHandler(fh)
        raiz.addHandler(sh)
        # Bibliotecas barulhentas
        for lib in ("urllib3", "websocket", "faster_whisper", "chat_downloader"):
            logging.getLogger(lib).setLevel(logging.WARNING)
    return logging.getLogger(nome)


def rodar(cmd: list[str], cwd: Path | str | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Roda um comando e levanta erro com o stderr se falhar."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace")[-1500:]
        raise RuntimeError(f"Comando falhou ({r.returncode}): {' '.join(map(str, cmd[:6]))}...\n{err}")
    return r


def args_trecho(arquivo: Path | str, inicio: float, duracao: float) -> list[str]:
    """Argumentos do ffmpeg para ler EXATAMENTE [inicio, inicio + duracao] de um arquivo.

    Só '-ss' antes do '-i' em .ts de live pode cair alguns segundos DEPOIS do ponto (o arquivo não
    tem índice e o quadro-chave da Kick vem a cada ~4 s): o vídeo começava 1,8–3,3 s atrasado em
    relação ao áudio e a legenda desalinhava. Solução: pula rápido até 15 s antes e depois avança
    decodificando até o ponto exato ('-ss' depois do '-i').
    """
    margem = 15.0
    if inicio > margem + 1:
        return ["-ss", f"{inicio - margem:.3f}", "-i", str(arquivo), "-ss", f"{margem:.3f}", "-t", f"{duracao:.3f}"]
    return ["-i", str(arquivo), "-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}"]


def probe_video(caminho: Path | str) -> tuple[int, int]:
    r = rodar([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height", "-of", "csv=p=0:s=x", str(caminho)])
    w, h = r.stdout.decode().strip().splitlines()[0].split("x")[:2]
    return int(w), int(h)
