"""Capa para o TikTok dos cortes marcados ⭐ Postar.

Para cada corte da lista Postar gera, na pasta postar/:
  <canal>_<base>.jpg  a capa (quadro do momento do pico + frase em destaque + reação do chat)
  <canal>_<base>.mp4  o corte com a capa nos primeiros quadros (no TikTok: Capa → arrastar até o início)
  <canal>_<base>.json o que foi usado (versão do vídeo e texto), para saber quando refazer

Uma thread confere a lista a cada poucos segundos (e na hora em que um vídeo é marcado), então também
refaz a capa quando o corte é ajustado/revertido e apaga a capa quando o vídeo sai da lista ou é apagado.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

from .editor import H, W, codec_video, escolher_encoder
from .util import FFMPEG, RAIZ, rodar

log = logging.getLogger("capa")

PASTA = RAIZ / "postar"
FONTES = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
_erros: dict[str, tuple[str, str]] = {}    # corte_id → (chave do que falhou, mensagem)


def nome_saida(corte_id: str) -> str:
    canal, base = corte_id.split("/")
    return f"{canal}_{base}"


def texto_desejado(meta: dict) -> str:
    return (meta.get("capa_texto") or sugerir_texto(meta)).upper()


def info(corte_id: str, versao: int, meta: dict) -> dict:
    """Estado da capa de um corte da lista Postar, para a página Vídeos."""
    nome = nome_saida(corte_id)
    js, mp4, jpg = PASTA / f"{nome}.json", PASTA / f"{nome}.mp4", PASTA / f"{nome}.jpg"
    erro = _erros.get(corte_id)
    try:
        lado = json.loads(js.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        lado = {}
    texto = texto_desejado(meta)
    pronta = lado.get("versao") == versao and lado.get("texto") == texto and mp4.exists() and jpg.exists()
    v = int(jpg.stat().st_mtime) if jpg.exists() else 0
    return {"pronta": pronta, "texto": texto, "manual": bool(meta.get("capa_texto")),
            "jpg": f"/postar/{nome}.jpg?v={v}", "mp4": f"/postar/{nome}.mp4?v={v}",
            "erro": erro[1] if erro and erro[0] == f"{versao}|{texto}" else None}


# ---------------------------------------------------------------- texto da capa
ENCHIMENTO = {"mano", "cara", "velho", "véi", "vei", "né", "chat", "galera", "gente", "ah", "ó", "pô", "po", "tipo",
              "irmão", "bom", "então", "enfim", "aí", "tá", "ok", "beleza", "e", "mas", "porque", "pois", "ué"}
FORTES = ("meu deus", "não acredito", "caramba", "que isso", "olha isso", "socorro", "mentira", "absurdo", "loucura",
          "morri", "injogável", "insano", "bizarro", "ridículo", "não pode", "nossa", "que loucura", "perfeito",
          "acabou", "corre", "fugiu", "morreu", "rockstar", "gta")
EMOTES = {"pog", "pogchamp", "kappa", "monkas", "catjam", "dinodance", "pepega", "ez", "gg", "f", "w", "l", "o7"}


def _limpar(frase: str) -> str:
    palavras = frase.split()
    # tira enchimento do começo ("Mano, cara, olha...") e do fim ("..., mano.")
    while len(palavras) > 2 and palavras[0].strip(",.!?…").lower() in ENCHIMENTO:
        palavras.pop(0)
    while len(palavras) > 2 and palavras[-1].strip(",.!?…").lower() in ENCHIMENTO:
        fim = palavras.pop()[-1]
        if fim in "!?":
            palavras[-1] = palavras[-1].rstrip(",.") + fim
    frase = " ".join(palavras).strip(" ,")
    return frase[:1].upper() + frase[1:]


def sugerir_texto(meta: dict) -> str:
    """A frase mais forte da fala do streamer perto do pico (ou a reação do chat, se não houver fala)."""
    bruto = re.sub(r"\[jogo:[^\]]*\]", " ", meta.get("transcricao") or "")
    bruto = re.sub(r"\b[Kk]{3,}\b", " ", bruto)
    bruto = re.sub(r"\s+", " ", bruto).strip()
    frases, pos = [], 0
    for f in re.split(r"(?<=[.!?…])\s+", bruto):
        ini = bruto.find(f, pos)
        pos = ini + len(f)
        limpa = _limpar(f)
        if re.search(r"\w", limpa):
            frases.append({"txt": limpa, "pos": (ini + len(f) / 2) / max(1, len(bruto))})
    if not frases:
        selo = sugerir_selo(meta)
        return selo.removeprefix("CHAT: ") if selo else ""
    dur = meta.get("duracao") or 0
    pico = (meta.get("hora") or 0) - (meta.get("inicio") or 0)
    alvo = min(1.0, max(0.0, (pico - 2) / dur)) if dur and 0 < pico <= dur + 5 else 0.6  # a fala vem antes do chat
    for f in frases:
        n, baixo = len(f["txt"].split()), f["txt"].lower()
        s = 3 - 4 * abs(f["pos"] - alvo)
        s += 2 if 2 <= n <= 6 else 0.5 if n <= 9 else -2 - (n - 9) * 0.3
        s -= 3 if n < 2 else 0
        s += 2 if "!" in f["txt"] else 1 if "?" in f["txt"] else 0
        s += 1.5 if any(p in baixo for p in FORTES) else 0
        s -= 2.5 if f["txt"].endswith(("...", "…")) else 0   # frase cortada no meio
        f["nota"] = s
    i = max(range(len(frases)), key=lambda k: frases[k]["nota"])
    texto = frases[i]["txt"]
    # frase curta: junta com a vizinha curta ("É um rockstar! Ele dança!")
    exclama = lambda t: t.endswith(("!", "?"))
    if len(texto.split()) <= 4 and exclama(texto):
        for j in (i + 1, i - 1):
            if 0 <= j < len(frases) and len(frases[j]["txt"].split()) <= 4 and exclama(frases[j]["txt"]):
                par = (texto, frases[j]["txt"]) if j > i else (frases[j]["txt"], texto)
                texto = " ".join(par)
                break
    palavras = texto.split()
    if len(palavras) > 9:
        corte = next((k + 1 for k, p in enumerate(palavras[:9]) if p.endswith(",") and k >= 2), None)
        texto = " ".join(palavras[:corte]).rstrip(",") if corte else " ".join(palavras[:7]) + "…"
    return texto.rstrip(".").upper()


def sugerir_selo(meta: dict) -> str:
    """A reação mais repetida no chat ("CHAT: INJOGAVEL"); risada vira KKKKKKK."""
    for msg, _n in meta.get("top_msgs") or []:
        t = str(msg).strip()
        junto = t.replace(" ", "").lower()
        if re.fullmatch(r"(k{3,}|(ha){2,}h?|(rs){2,}|(hue){2,})", junto) or re.search(r"lul|kekw|laugh|icant", junto):
            return "CHAT: KKKKKKK"
        if not re.search(r"[^\W\d_]{2}", t) or junto in EMOTES or re.search(r"[a-z][A-Z]", t) or len(t) > 18:
            continue   # emote (alanzLUL, PogChamp), letra solta ou frase longa demais
        return "CHAT: " + t.upper()
    return ""


# ---------------------------------------------------------------- imagem
def _fonte(nome: str, tam: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(FONTES / nome), tam)
    except OSError:
        return ImageFont.truetype(str(FONTES / "arialbd.ttf"), tam)


def escolher_quadro(mp4: Path, meta: dict, trabalho: Path):
    """O quadro mais nítido entre os segundos antes do pico (a jogada costuma vir antes do chat reagir)."""
    from PIL import Image, ImageFilter, ImageStat
    dur = meta.get("duracao") or 10
    pico = (meta.get("hora") or 0) - (meta.get("inicio") or 0)
    if not 0 < pico <= dur:
        pico = dur * 0.6
    tempos = sorted({round(min(dur - 0.3, max(0.3, pico - d)), 2) for d in (3.5, 2.5, 1.5, 0.5)})
    melhor, nota_melhor = None, -1.0
    for k, t in enumerate(tempos):
        png = trabalho / f"q{k}.png"
        try:
            rodar([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4),
                   "-frames:v", "1", str(png)], timeout=60)
            img = Image.open(png).convert("RGB")
        except (RuntimeError, OSError):
            continue
        cinza = img.resize((270, 480)).convert("L")
        nota = ImageStat.Stat(cinza.filter(ImageFilter.FIND_EDGES)).stddev[0] + ImageStat.Stat(cinza).mean[0] * 0.1
        if nota > nota_melhor:
            melhor, nota_melhor = img, nota
    if melhor is None:
        raise RuntimeError("não consegui extrair nenhum quadro do vídeo")
    return melhor


def _quebrar(texto: str, fonte, largura: int, draw) -> list[str]:
    linhas, atual = [], ""
    for p in texto.split():
        teste = f"{atual} {p}".strip()
        if draw.textlength(teste, font=fonte) <= largura or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    return linhas + ([atual] if atual else [])


def _pilula(texto: str, fonte, cor_fundo, cor_texto, angulo: float = 0):
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=fonte)
    px, py = int(fonte.size * 0.55), int(fonte.size * 0.32)
    img = Image.new("RGBA", (x1 - x0 + 2 * px, y1 - y0 + 2 * py), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=img.height // 2, fill=cor_fundo,
                        outline=(0, 0, 0, 255), width=5)
    d.text((px - x0, py - y0), texto, font=fonte, fill=cor_texto)
    return img.rotate(angulo, resample=Image.BICUBIC, expand=True) if angulo else img


def desenhar(quadro, texto: str, selo: str, canal: str):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    fundo = quadro.convert("RGB").resize((W, H))
    fundo = ImageEnhance.Contrast(ImageEnhance.Color(fundo).enhance(1.35)).enhance(1.12).convert("RGBA")

    # ---- frase principal: Impact, o maior tamanho que caiba em até 3 linhas
    rasc = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    texto = texto or canal.upper()
    for tam in range(200, 89, -6):
        fonte = _fonte("impact.ttf", tam)
        # cada frase ("PUTA QUE PARIU!" / "MEU DEUS!") começa em linha nova, se couber
        linhas = [li for frase in re.split(r"(?<=[!?])\s+", texto) for li in _quebrar(frase, fonte, 960, rasc)]
        if len(linhas) > 3:
            linhas = _quebrar(texto, fonte, 960, rasc)
        if len(linhas) <= 3 and all(rasc.textlength(li, font=fonte) <= 1000 for li in linhas):
            break
    alt_linha = int(tam * 1.08)
    borda = max(8, tam // 11)
    bloco = Image.new("RGBA", (W, alt_linha * len(linhas) + 4 * borda), (0, 0, 0, 0))
    d = ImageDraw.Draw(bloco)
    for k, li in enumerate(linhas):
        cor = (255, 226, 26, 255) if k == len(linhas) - 1 and len(linhas) > 1 or len(linhas) == 1 else (255, 255, 255, 255)
        d.text((W // 2, 2 * borda + k * alt_linha), li, font=fonte, fill=cor, anchor="ma",
               stroke_width=borda, stroke_fill=(0, 0, 0, 255))
    bloco = _com_sombra(bloco).rotate(3, resample=Image.BICUBIC, expand=True)

    # ---- posição: centro da frase em ~41% da altura (cobre a legenda queimada e fica no recorte 3:4 do perfil)
    centro = int(H * 0.41)
    y_bloco = centro - bloco.height // 2
    selo_img = _pilula(selo, _fonte("ariblk.ttf", 64), (232, 17, 45, 255), (255, 255, 255, 255), -4) if selo else None
    canal_img = _pilula(f"{canal.upper()}  •  GTA 6", _fonte("ariblk.ttf", 50), (0, 0, 0, 235), (255, 226, 26, 255))
    topo = y_bloco - (selo_img.height - 10 if selo_img else 0)
    base = y_bloco + bloco.height + canal_img.height

    # faixa escura atrás de tudo (mais forte no meio, some nas bordas)
    faixa = Image.new("L", (1, H), 0)
    for y in range(H):
        if topo - 110 <= y <= base + 110:
            dist = max(0, max(topo - y, y - base)) / 110
            faixa.putpixel((0, y), int(255 * (1 - dist)))
    mascara = faixa.resize((W, H))
    # atrás do texto o fundo fica desfocado e escuro (some a legenda queimada do vídeo)
    fundo = Image.composite(fundo.filter(ImageFilter.GaussianBlur(14)), fundo, mascara)
    escuro = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    escuro.putalpha(mascara.point(lambda a: int(a * 0.62)))
    capa = Image.alpha_composite(fundo, escuro)

    capa.alpha_composite(bloco, ((W - bloco.width) // 2, y_bloco))
    if selo_img:
        capa.alpha_composite(selo_img, ((W - selo_img.width) // 2, y_bloco - selo_img.height + 30))
    capa.alpha_composite(canal_img, ((W - canal_img.width) // 2, y_bloco + bloco.height - 10))
    return capa.convert("RGB")


def _com_sombra(bloco):
    from PIL import Image, ImageFilter
    sombra = Image.new("RGBA", bloco.size, (0, 0, 0, 0))
    sombra.putalpha(bloco.getchannel("A").point(lambda a: int(a * 0.8)))
    sombra = sombra.filter(ImageFilter.GaussianBlur(9))
    deslocada = Image.new("RGBA", bloco.size, (0, 0, 0, 0))
    deslocada.alpha_composite(sombra, (10, 14))
    return Image.alpha_composite(deslocada, bloco)


# ---------------------------------------------------------------- vídeo com a capa no início
def embutir(mp4: Path, jpg: Path, saida: Path, cfg_saida: dict, seg: float, bitrate: str):
    enc = escolher_encoder(cfg_saida.get("encoder", "auto"))
    while True:
        fmt, vcod = codec_video(enc, bitrate)
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-nostdin", "-i", str(mp4),
               "-loop", "1", "-framerate", str(cfg_saida.get("fps", 30)), "-t", f"{seg:.3f}", "-i", str(jpg),
               "-filter_complex", f"[1:v]scale={W}:{H},setsar=1[c];[0:v][c]overlay=0:0:eof_action=pass,format={fmt}[v]",
               "-map", "[v]", "-map", "0:a?", "-c:a", "copy", *vcod, "-movflags", "+faststart", str(saida)]
        try:
            rodar(cmd, timeout=600)
            return
        except RuntimeError:
            if enc == "x264":
                raise
            log.warning("capa: %s falhou, tentando libx264", enc.upper())
            enc = "x264"


# ---------------------------------------------------------------- thread
class Capas(threading.Thread):
    def __init__(self, cfg: dict, lock_arquivos):
        super().__init__(daemon=True, name="capas")
        self.cfg = cfg
        self.c = cfg.get("capa", {})
        self.lock = lock_arquivos
        self.pasta_cortes = RAIZ / cfg["geral"]["pasta_cortes"]
        self.evento = threading.Event()
        PASTA.mkdir(exist_ok=True)

    def acordar(self):
        self.evento.set()

    def run(self):
        while True:
            try:
                self.sincronizar()
            except Exception:  # noqa: BLE001
                log.exception("capas: erro ao sincronizar")
            self.evento.wait(10)
            self.evento.clear()

    def definir_texto(self, corte_id: str, texto: str):
        """Texto escolhido pelo usuário ("" = volta para o automático). A capa é refeita em seguida."""
        canal, base = corte_id.split("/")
        js = self.pasta_cortes / canal / f"{base}.json"
        if js.parent.parent != self.pasta_cortes or not js.exists():
            raise ValueError("corte não encontrado")
        texto = re.sub(r"\s+", " ", texto or "").strip()[:80]
        with self.lock:
            meta = json.loads(js.read_text(encoding="utf-8"))
            if texto:
                meta["capa_texto"] = texto
            else:
                meta.pop("capa_texto", None)
            tmp = js.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(js)
        _erros.pop(corte_id, None)
        self.acordar()

    def sincronizar(self):
        if not self.c.get("ativa", True):
            return
        queridos = set()
        for js in self.pasta_cortes.glob("*/*.json"):
            mp4 = js.with_suffix(".mp4")
            if not mp4.exists():
                continue
            try:
                meta = json.loads(js.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if not meta.get("postar"):
                continue
            corte_id = f"{js.parent.name}/{js.stem}"
            queridos.add(nome_saida(corte_id))
            texto = texto_desejado(meta)
            versao = int(mp4.stat().st_mtime)
            lado = PASTA / f"{nome_saida(corte_id)}.json"
            try:
                feito = json.loads(lado.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                feito = {}
            pronto = (feito.get("versao") == versao and feito.get("texto") == texto
                      and lado.with_suffix(".mp4").exists() and lado.with_suffix(".jpg").exists())
            chave = f"{versao}|{texto}"
            if pronto or _erros.get(corte_id, ("",))[0] == chave:
                continue
            try:
                self._gerar(corte_id, mp4, meta, texto, versao)
                _erros.pop(corte_id, None)
            except Exception as e:  # noqa: BLE001
                log.warning("capa de %s falhou: %s", corte_id, e)
                _erros[corte_id] = (chave, str(e)[:200])
        # vídeo saiu da lista Postar ou foi apagado → apaga a capa (só o que foi gerado aqui: tem o .json)
        for lado in PASTA.glob("*.json"):
            if lado.stem not in queridos:
                for ext in (".mp4", ".jpg", ".json"):
                    try:
                        lado.with_suffix(ext).unlink(missing_ok=True)
                    except PermissionError:
                        pass   # aberto em algum lugar: tenta de novo na próxima volta

    def _gerar(self, corte_id: str, mp4: Path, meta: dict, texto: str, versao: int):
        t0 = time.time()
        nome = nome_saida(corte_id)
        trabalho = RAIZ / "tmp" / f"capa_{nome}"
        trabalho.mkdir(parents=True, exist_ok=True)
        try:
            quadro = escolher_quadro(mp4, meta, trabalho)
            capa = desenhar(quadro, texto, sugerir_selo(meta), meta.get("canal") or corte_id.split("/")[0])
            jpg_tmp, mp4_tmp = trabalho / "capa.jpg", trabalho / "video.mp4"
            capa.save(jpg_tmp, quality=92)
            embutir(mp4, jpg_tmp, mp4_tmp, self.cfg.get("saida", {}), float(self.c.get("duracao_seg", 0.1)),
                    self.c.get("bitrate", "8000k"))
            for tmp, ext in ((jpg_tmp, ".jpg"), (mp4_tmp, ".mp4")):
                for tentativa in range(5):   # o celular pode estar baixando a versão anterior
                    try:
                        os.replace(tmp, PASTA / f"{nome}{ext}")
                        break
                    except PermissionError:
                        time.sleep(0.5)
                else:
                    raise RuntimeError(f"{nome}{ext} está em uso; tento de novo depois")
            (PASTA / f"{nome}.json").write_text(json.dumps({"versao": versao, "texto": texto}, ensure_ascii=False),
                                               encoding="utf-8")
        finally:
            shutil.rmtree(trabalho, ignore_errors=True)
        log.info("🖼 capa pronta: %s (\"%s\", %.1fs)", corte_id, texto, time.time() - t0)
