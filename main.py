"""Sistema de cortes automáticos.

Uso: .\\.venv\\Scripts\\python main.py [--canais dona coringa] [--nao-abrir] [--sem-painel]

Os canais ficam em canais.yaml e podem ser adicionados/parados/ajustados pelo painel
(http://localhost:8000). Sem --canais, inicia os que estão com ativo: true.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time

from app.estado import Estado
from app.fila import Fila
from app.gerenciador import Gerenciador
from app.transcricao import pre_carregar
from app.util import RAIZ, carregar_canais, carregar_config, configurar_logs


def impedir_suspensao():
    """Enquanto o sistema roda, o Windows não suspende/hiberna o notebook (a tela ainda pode apagar).
    Volta ao normal sozinho quando o programa fecha — não muda nenhuma configuração do Windows."""
    if sys.platform != "win32":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def limpar_orfaos(log):
    """streamlink/ffmpeg que sobraram de uma execução anterior que caiu (o pai não existe mais)."""
    try:
        import psutil
    except ImportError:
        return
    nomes = {"streamlink.exe", "ffmpeg.exe"}
    for p in psutil.process_iter(["name", "ppid", "cmdline"]):
        try:
            nome = (p.info["name"] or "").lower()
            cmd = " ".join(p.info["cmdline"] or [])
            eh_nosso = nome in nomes or (nome == "python.exe" and "Streamlink" in cmd)
            if eh_nosso and not psutil.pid_exists(p.info["ppid"]):
                log.info("encerrando processo órfão: %s (%s)", nome, p.pid)
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-painel", action="store_true")
    ap.add_argument("--nao-abrir", action="store_true", help="não abre o painel no navegador")
    ap.add_argument("--canais", nargs="*", help="iniciar só estes canais (ignora 'ativo')")
    args = ap.parse_args()

    log = configurar_logs("main")
    impedir_suspensao()
    limpar_orfaos(log)
    cfg = carregar_config()
    estado = Estado()
    estado.carregar_cortes_antigos(RAIZ / cfg["geral"]["pasta_cortes"])

    canais = carregar_canais(cfg)
    fila = Fila(cfg, {}, estado)
    fila.start()
    if cfg.get("legenda", {}).get("ativa", True):
        pre_carregar(cfg["legenda"])

    ger = Gerenciador(cfg, canais, estado, fila)
    iniciar = args.canais if args.canais else [c["nome"] for c in canais if c.get("ativo")]
    for nome in iniciar:
        if nome in ger.por_nome:
            ger.iniciar(nome)
        else:
            log.error("canal '%s' não existe em canais.yaml", nome)
    if not ger.rodando:
        log.warning("nenhum canal rodando. Adicione uma live pelo painel.")

    if not args.sem_painel:
        from app.painel import iniciar_painel
        iniciar_painel(cfg, estado, ger, abrir_navegador=not args.nao_abrir)

    def sair(*_):
        log.info("encerrando...")
        ger.encerrar_tudo()
        time.sleep(1)
        sys.exit(0)

    signal.signal(signal.SIGINT, sair)
    log.info("rodando. Ctrl+C para parar.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
