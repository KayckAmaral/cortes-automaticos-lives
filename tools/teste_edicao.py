"""Teste ponta a ponta da edição de tempo: corte manual → sobra → estender fim +10 s → reverter → apagar."""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.fila import duracao_video  # noqa: E402
from app.util import RAIZ  # noqa: E402

API = "http://127.0.0.1:8000"
CANAL = sys.argv[1] if len(sys.argv) > 1 else "dona"


def get(p):
    with urllib.request.urlopen(API + p, timeout=30) as r:
        return json.load(r)


def post(p, d=None):
    req = urllib.request.Request(API + p, data=json.dumps(d or {}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def esperar(cond, limite, passo=3):
    t = time.time()
    while time.time() - t < limite:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# 1) espera gravar e pede corte manual
esperar(lambda: any(c["nome"] == CANAL and c["gravando"] for c in get("/api/estado")["canais"]), 90)
antes = {c["id"] for c in get("/api/cortes")}
log("corte manual:", post(f"/api/cortar/{CANAL}"))
novo = esperar(lambda: next((c for c in get("/api/cortes") if c["id"] not in antes and c["canal"] == CANAL), None), 180)
if not novo:
    raise SystemExit("corte não ficou pronto")
cid = novo["id"]
mp4 = RAIZ / "cortes" / (cid + ".mp4")
log("corte pronto:", cid, f"duração {duracao_video(mp4):.1f}s | sobra pronta em",
    round((novo["sobra_pronta_em"] or time.time()) - time.time()), "s")

# 2) espera a sobra
c = esperar(lambda: next((x for x in get("/api/cortes") if x["id"] == cid and x["fonte"]), None), 200)
if not c:
    raise SystemExit("sobra não foi guardada")
log("sobra guardada:", c["fonte"]["url"], f"{c['fonte']['duracao']:.0f}s")

# 3) estende o fim em +10 s
s = c["inicio_corte"] - c["fonte"]["inicio"]
e = s + c["duracao_exata"] + 10
log(f"pedindo ajuste: s={s:.1f} e={e:.1f} (dur {e - s:.1f}s)", post("/api/editar", {"id": cid, "inicio": s, "fim": e}))
v0 = c["versao"]
c2 = esperar(lambda: next((x for x in get("/api/cortes") if x["id"] == cid and x["versao"] != v0 and not x["editando"]), None), 240)
if not c2:
    raise SystemExit("ajuste não terminou")
log(f"ajustado: duração {duracao_video(mp4):.1f}s | editado={c2['editado']} pode_reverter={c2['pode_reverter']}")

# 4) reverte
time.sleep(1.5)
log("reverter:", post("/api/reverter", {"id": cid}))
c3 = next(x for x in get("/api/cortes") if x["id"] == cid)
log(f"revertido: duração {duracao_video(mp4):.1f}s | editado={c3['editado']} pode_reverter={c3['pode_reverter']}")

# 5) apaga o corte de teste
log("apagar:", post("/api/apagar", {"id": cid}))
print("sobras restantes:", list((RAIZ / "cortes" / CANAL / "_fontes").glob(Path(cid).name + "*")),
      list((RAIZ / "cortes" / CANAL / "_originais").glob(Path(cid).name + "*")))
