"""Lista e apaga cortes do disco (usado pela página /galeria do painel)."""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import capa
from .util import RAIZ

log = logging.getLogger("galeria")
RE_ID = re.compile(r"^[\w.-]+/[\w.-]+$")


def listar(pasta_cortes: Path) -> list[dict]:
    itens = []
    for mp4 in pasta_cortes.glob("*/*.mp4"):
        canal, base = mp4.parent.name, mp4.stem
        js = mp4.with_suffix(".json")
        # o .json só é gravado DEPOIS do vídeo ficar pronto: sem ele, o mp4 ainda está sendo montado
        # (listar antes disso mostrava vídeo preto travado em 0 s)
        if not js.exists():
            continue
        try:
            meta = json.loads(js.read_text(encoding="utf-8"))
        except ValueError:
            continue
        inicio = meta.get("inicio") or mp4.stat().st_mtime
        st = mp4.stat()
        fonte = meta.get("fonte")
        fonte_ok = bool(fonte) and (RAIZ / fonte["arquivo"]).exists()
        itens.append({
            "id": f"{canal}/{base}",
            "canal": canal,
            # ?v= muda quando o vídeo é refeito (ajuste/reversão) → o navegador não usa a versão antiga do cache
            "url": "/" + mp4.relative_to(RAIZ).as_posix() + f"?v={int(st.st_mtime)}",
            "versao": int(st.st_mtime),
            "pico": meta.get("hora"),
            "fonte": ({"url": "/" + Path(fonte["arquivo"]).as_posix(), "inicio": fonte["inicio"],
                       "duracao": fonte["duracao"]} if fonte_ok else None),
            "sobra_pronta_em": meta.get("sobra_pronta_em"),
            "editado": bool(meta.get("editado")),
            "assistido": bool(meta.get("assistido")),
            "postar": bool(meta.get("postar")),
            "capa": capa.info(f"{canal}/{base}", int(st.st_mtime), meta) if meta.get("postar") else None,
            "gatilho": meta.get("gatilho") or ("manual" if meta.get("manual") else "chat"),
            "mudo_inicio": meta.get("mudo_inicio") or 0,
            "pode_reverter": (mp4.parent / "_originais" / f"{base}.mp4").exists(),
            "inicio": inicio,
            "data_txt": datetime.fromtimestamp(inicio).strftime("%d/%m %H:%M:%S"),
            "relativo": meta.get("relativo", 0),
            "pontuacao": meta.get("pontuacao", 0),
            "manual": meta.get("manual", "manual" in base),
            "titulo": meta.get("sugestao_titulo", ""),
            "transcricao": meta.get("transcricao", ""),
            "top_msgs": (meta.get("top_msgs") or [])[:5],
            "falas_jogo": (meta.get("falas_jogo") or [])[:6],
            "grafico": meta.get("grafico") or [],
            "inicio_corte": meta.get("inicio"),
            "duracao_exata": meta.get("duracao"),
            "duracao": round(meta.get("duracao") or 0),
            "pronto_em_seg": meta.get("pronto_em_seg"),
            "tamanho_mb": round(st.st_size / 1e6, 1),
        })
    itens.sort(key=lambda i: i["inicio"], reverse=True)
    return itens


_cache_novos = {"t": 0.0, "n": 0}


def contar_novos(pasta_cortes: Path, validade: float = 3.0) -> int:
    """Quantos cortes ainda não foram assistidos (com cache curto: o painel pergunta a cada 2 s)."""
    if time.time() - _cache_novos["t"] < validade:
        return _cache_novos["n"]
    n = 0
    for js in pasta_cortes.glob("*/*.json"):
        if not js.with_suffix(".mp4").exists():
            continue
        try:
            if not json.loads(js.read_text(encoding="utf-8")).get("assistido"):
                n += 1
        except ValueError:
            pass
    _cache_novos.update(t=time.time(), n=n)
    return n


MARCACOES = ("assistido", "postar")   # marcações que o usuário liga/desliga na página Vídeos


def marcar(pasta_cortes: Path, corte_id: str, campo: str, valor: bool, lock) -> None:
    """Grava uma marcação (assistido/postar) no .json do corte (vale para qualquer navegador)."""
    if campo not in MARCACOES:
        raise ValueError("marcação desconhecida")
    if not RE_ID.match(corte_id or "") or corte_id.startswith("."):
        raise ValueError("id de corte inválido")
    canal, base = corte_id.split("/")
    js = (pasta_cortes / canal / f"{base}.json").resolve()
    if js.parent.parent != pasta_cortes.resolve() or not js.exists():
        raise ValueError("corte não encontrado")
    with lock:
        meta = json.loads(js.read_text(encoding="utf-8"))
        meta[campo] = bool(valor)
        if valor:
            meta[f"{campo}_em"] = time.time()
        else:
            meta.pop(f"{campo}_em", None)
        tmp = js.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(js)
    _cache_novos["t"] = 0.0   # contador de novos atualiza na hora


def apagar(pasta_cortes: Path, corte_id: str) -> list[str]:
    """Apaga o vídeo, o .json e a pasta temporária do corte. Devolve o que foi removido."""
    if not RE_ID.match(corte_id or ""):
        raise ValueError("id de corte inválido")
    canal, base = corte_id.split("/")
    if canal.startswith(".") or base.startswith("."):
        raise ValueError("id de corte inválido")
    raiz = pasta_cortes.resolve()
    alvos = [(pasta_cortes / canal / f"{base}.mp4").resolve(), (pasta_cortes / canal / f"{base}.json").resolve()]
    if any(a.parent.parent != raiz for a in alvos):
        raise ValueError("id de corte inválido")
    # sobra para edição e original guardado (se houver)
    alvos += [pasta_cortes / canal / "_fontes" / f"{base}.mp4",
              pasta_cortes / canal / "_originais" / f"{base}.mp4",
              pasta_cortes / canal / "_originais" / f"{base}.json"]
    removidos = []
    for alvo in alvos:
        if not alvo.exists():
            continue
        for tentativa in range(5):  # o player pode estar lendo o arquivo
            try:
                alvo.unlink()
                removidos.append(alvo.relative_to(pasta_cortes / canal).as_posix())
                break
            except PermissionError:
                time.sleep(0.4)
        else:
            raise RuntimeError(f"{alvo.name} está em uso; feche o vídeo e tente de novo")
    tmp = RAIZ / "tmp" / f"{canal}_{base}"
    if tmp.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
        removidos.append(f"tmp/{tmp.name}/")
    if not removidos:
        raise ValueError("corte não encontrado (já foi apagado?)")
    # obs.: a pasta do canal NÃO é removida mesmo vazia — um corte desse canal pode estar sendo
    # montado agora e falharia ao salvar ("No such file or directory"; perdeu um corte em 17/11)
    _cache_novos["t"] = 0.0
    log.info("corte apagado: %s (%s)", corte_id, ", ".join(removidos))
    return removidos
