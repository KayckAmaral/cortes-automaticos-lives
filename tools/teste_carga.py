"""Teste de carga: 3 canais ao mesmo tempo + 3 cortes manuais simultâneos.

Mede CPU/RAM e o tempo de cada corte. No fim apaga os cortes de teste e devolve os canais ao
estado anterior (ligado/parado).
Uso: python tools/teste_carga.py dona gabepeixe coreano
"""
import json
import statistics
import sys
import time
import urllib.request

API = "http://127.0.0.1:8000"
CANAIS = sys.argv[1:] or ["dona", "gabepeixe", "coreano"]


def get(p):
    with urllib.request.urlopen(API + p, timeout=30) as r:
        return json.load(r)


def post(p, d=None):
    req = urllib.request.Request(API + p, data=json.dumps(d or {}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


estado0 = {c["nome"]: c["rodando"] for c in get("/api/estado")["canais"]}
log("estado inicial:", {n: estado0.get(n) for n in CANAIS})
for n in CANAIS:
    if not estado0.get(n):
        post(f"/api/iniciar/{n}")
        log("ligado:", n)

amostras = []


def amostrar(rotulo=""):
    e = get("/api/estado")
    s = e.get("sistema", {})
    ch = {c["nome"]: ("grav" if c["gravando"] else "-") + "/" + ("chat" if c["chat_ok"] else "-")
          for c in e["canais"] if c["nome"] in CANAIS}
    amostras.append((s.get("cpu", 0), s.get("ram", 0), s.get("ram_livre_gb", 0)))
    log(f"CPU {s.get('cpu')}% RAM {s.get('ram')}% ({s.get('ram_livre_gb')} GB livres) | {ch} {rotulo}")
    return e


# aquece 100 s (gravação + chat + 1 min de áudio para a linha de base)
for _ in range(10):
    amostrar()
    time.sleep(10)

antes = {c["id"] for c in get("/api/cortes")}
for n in CANAIS:
    post(f"/api/cortar/{n}")
log("3 cortes manuais pedidos ao mesmo tempo")
t_pedido = time.time()
prontos = {}
while time.time() - t_pedido < 300 and len(prontos) < len(CANAIS):
    e = amostrar("| fila: " + ", ".join(f"{i['canal']}:{i['status']}" for i in e_fila) if (e_fila := get("/api/estado")["fila"]) else "")
    for c in get("/api/cortes"):
        # só os cortes MANUAIS pedidos por este teste (um corte automático real que aparecer no meio fica)
        if c["id"] not in antes and c["id"] not in prontos and c["manual"] and c["canal"] in CANAIS:
            prontos[c["id"]] = time.time() - t_pedido
            log(f"✅ pronto: {c['id']} em {prontos[c['id']]:.0f}s após o pedido")
    time.sleep(8)

# detalhes das etapas
for cid in prontos:
    canal, base = cid.split("/")
    meta = json.load(open(f"cortes/{canal}/{base}.json", encoding="utf-8"))
    log(f"   {cid}: etapas {meta.get('etapas')}")

cpu = [a[0] for a in amostras]
ram = [a[1] for a in amostras]
livre = [a[2] for a in amostras]
log(f"RESUMO: CPU média {statistics.mean(cpu):.0f}% (pico {max(cpu)}%) | RAM média {statistics.mean(ram):.0f}% "
    f"(pico {max(ram)}%, mínimo livre {min(livre)} GB) | cortes: {len(prontos)}/{len(CANAIS)}")

# limpeza: apaga os cortes de teste e devolve o estado dos canais
time.sleep(3)
for cid in prontos:
    post("/api/apagar", {"id": cid})
log("cortes de teste apagados:", list(prontos))
for n in CANAIS:
    if not estado0.get(n):
        post(f"/api/parar/{n}")
        log("devolvido para parado:", n)
