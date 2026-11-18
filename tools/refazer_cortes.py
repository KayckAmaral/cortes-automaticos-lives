"""Refaz cortes com o MESMO trecho (usa a sobra), para corrigir cortes montados com algum bug.

Uso: python tools/refazer_cortes.py <canal>/<base> [<canal>/<base> ...] [--manter-original]
Por padrão, se o corte NÃO tinha sido ajustado pelo usuário, apaga a cópia "_originais" criada pelo
refazer (senão o "Reverter" voltaria para a versão com bug) e tira a marca de editado.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.util import RAIZ  # noqa: E402

API = "http://127.0.0.1:8000"
ids = [a for a in sys.argv[1:] if not a.startswith("--")]


def post(p, d):
    req = urllib.request.Request(API + p, data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def lista():
    with urllib.request.urlopen(API + "/api/cortes", timeout=30) as r:
        return {c["id"]: c for c in json.load(r)}


for cid in ids:
    canal, base = cid.split("/")
    js = RAIZ / "cortes" / canal / f"{base}.json"
    meta = json.loads(js.read_text(encoding="utf-8"))
    ja_editado = bool(meta.get("editado"))
    s = meta["inicio"] - meta["fonte"]["inicio"]
    e = s + meta["duracao"]
    if not meta.get("editado") and meta["duracao"] < 29:   # corte que saiu curto pelo bug: volta aos 30 s
        e = s + 30
    v0 = lista()[cid]["versao"]
    print(time.strftime("%H:%M:%S"), cid, f"refazendo trecho {s:.1f}–{e:.1f}s ({e - s:.1f}s):", post("/api/editar", {"id": cid, "inicio": s, "fim": e}))
    t = time.time()
    while time.time() - t < 300:
        c = lista().get(cid)
        if c and c["versao"] != v0 and not c["editando"]:
            break
        time.sleep(3)
    print(time.strftime("%H:%M:%S"), "   pronto em", round(time.time() - t), "s")
    if not ja_editado and "--manter-original" not in sys.argv:
        for ext in (".mp4", ".json"):
            (RAIZ / "cortes" / canal / "_originais" / f"{base}{ext}").unlink(missing_ok=True)
        meta = json.loads(js.read_text(encoding="utf-8"))
        meta.pop("editado", None)
        meta.pop("edicoes", None)
        js.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("   (não era um corte ajustado: cópia com bug descartada, continua como original)")
