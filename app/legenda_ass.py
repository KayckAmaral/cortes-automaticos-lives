"""Gera legenda .ass estilo 'corte viral': poucas palavras, maiúsculas, palavra atual destacada.

Falas do jogo (palavras com quem='jogo') saem num estilo diferente: menores, itálico,
azul-claro, um pouco abaixo, sem destaque palavra a palavra. Assim quem assiste não confunde
com a fala do streamer.

modo (legenda.falas_jogo):
  desligado → tudo legendado no estilo do streamer (comportamento original)
  silencio  → fala do jogo aparece (estilo diferente) quando o streamer não está falando
  nunca     → fala do jogo é removida da legenda
"""
from __future__ import annotations

import re
from pathlib import Path

RE_PONT = re.compile(r"^[\"'(\[¿¡]+|[\"',.;:)\]]+$")


def _tempo(s: float) -> str:
    s = max(0.0, s)
    h = int(s // 3600)
    m = int(s % 3600 // 60)
    return f"{h}:{m:02d}:{s % 60:05.2f}"


def _limpar(p: str, maiusc=True) -> str:
    p = RE_PONT.sub("", p)
    p = p.upper() if maiusc else p
    return p.replace("{", "(").replace("}", ")").replace("\\", "")


def agrupar(palavras: list[dict], por_vez: int, pausa: float = 0.6) -> list[list[dict]]:
    """Agrupa palavras em blocos curtos; nunca mistura streamer e jogo no mesmo bloco.
    Fala do jogo fica agrupada por frase inteira (para poder trocar pela tradução)."""
    grupos, atual = [], []
    for w in palavras:
        jogo = w.get("quem", "streamer") == "jogo"
        if atual and (w.get("quem") != atual[-1].get("quem")
                      or (jogo and w.get("seg") != atual[-1].get("seg"))
                      or (not jogo and (len(atual) >= por_vez or w["ini"] - atual[-1]["fim"] > pausa))):
            grupos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        grupos.append(atual)
    return grupos


def _pedacos(texto: str, max_palavras: int = 7) -> list[str]:
    ps = texto.split()
    if len(ps) <= max_palavras + 2:
        return [texto]
    n = -(-len(ps) // max_palavras)  # divide em partes de tamanho parecido
    tam = -(-len(ps) // n)
    return [" ".join(ps[i:i + tam]) for i in range(0, len(ps), tam)]


def texto_credito(canal: dict, cfg: dict) -> str | None:
    """Crédito do streamer exibido no vídeo (ex.: 'kick.com/coringa'), ou None se desligado."""
    if not (cfg.get("saida") or {}).get("credito", True) or canal.get("credito_ativo") is False:
        return None
    t = (canal.get("credito_texto") or "").strip()
    if not t:
        url = canal.get("url") or ""
        t = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        t = re.sub(r"/live$", "", t)
    return t.replace("{", "(").replace("}", ")").replace("\\", "")[:60] or None


def gerar_ass(palavras: list[dict], destino: Path, cfg_leg: dict, largura=1080, altura=1920,
              traducoes: dict | None = None, credito: str | None = None, duracao: float = 0):
    modo = cfg_leg.get("falas_jogo", "silencio")
    if modo == "desligado":
        palavras = [{**w, "quem": "streamer"} for w in palavras]
    elif modo == "nunca":
        palavras = [w for w in palavras if w.get("quem", "streamer") == "streamer"]

    fonte = cfg_leg.get("fonte", "Arial Black")
    tam = int(cfg_leg.get("tamanho", 78))
    tam_jogo = int(tam * 0.6)
    y = int(altura * float(cfg_leg.get("posicao_y", 0.36)))
    y_jogo = y + int(tam * 0.9)
    destaque = cfg_leg.get("cor_destaque", "00FFFF")
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Corte,{fonte},{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,40,40,0,1
Style: Jogo,Arial,{tam_jogo},&H00FFE0A0,&H00FFE0A0,&H00000000,&H80000000,-1,-1,0,0,100,100,0,0,1,4,2,5,60,60,0,1
Style: Credito,Arial,34,&H38FFFFFF,&H38FFFFFF,&H70000000,&H00000000,-1,0,0,0,100,100,0,0,1,2.5,0,2,40,40,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    grupos = agrupar(palavras, int(cfg_leg.get("palavras_por_vez", 3)))
    for n, grupo in enumerate(grupos):
        # próximo grupo do MESMO estilo (mesma posição na tela): o atual tem que sumir antes dele
        # (senão os dois aparecem sobrepostos, ex.: "NÃ A GENTE NÃO E")
        mesmo = grupo[0].get("quem", "streamer")
        prox = next((g[0]["ini"] for g in grupos[n + 1:] if g[0].get("quem", "streamer") == mesmo), None)
        if grupo[0].get("quem", "streamer") == "jogo":
            trad = (traducoes or {}).get(grupo[0].get("seg"))
            texto = trad["traducao"] if trad else " ".join(w["palavra"] for w in grupo)
            texto = texto.replace("{", "(").replace("}", ")").replace("\\", "").strip()
            if texto:
                ini, fim = grupo[0]["ini"], max(grupo[-1]["fim"], grupo[0]["ini"] + 1.0)
                if prox is not None:
                    fim = max(ini + 0.3, min(fim, prox - 0.02))
                partes = _pedacos(texto)
                total = sum(len(p.split()) for p in partes)
                t = ini
                for p in partes:  # frase longa: divide o tempo proporcionalmente
                    dur = (fim - ini) * len(p.split()) / total
                    linhas.append(f"Dialogue: 0,{_tempo(t)},{_tempo(t + dur)},Jogo,,0,0,0,,"
                                  f"{{\\pos(540,{y_jogo})}}{p}")
                    t += dur
            continue
        textos = [_limpar(w["palavra"]) for w in grupo]
        for i, w in enumerate(grupo):
            ini = w["ini"]
            fim = grupo[i + 1]["ini"] if i + 1 < len(grupo) else max(w["fim"], ini + 0.25)
            if i + 1 == len(grupo) and prox is not None:
                fim = min(fim, prox - 0.02)
            if fim <= ini:   # palavras com o mesmo tempo (Whisper às vezes faz isso)
                fim = ini + 0.05
            partes = []
            for j, t in enumerate(textos):
                if not t:
                    continue
                partes.append(f"{{\\c&H{destaque}&}}{t}{{\\c&HFFFFFF&}}" if j == i else t)
            if not partes:
                continue
            # leve "pop" de escala no início de cada grupo
            efeito = "{\\fscx110\\fscy110\\t(0,80,\\fscx100\\fscy100)}" if i == 0 else ""
            linhas.append(f"Dialogue: 1,{_tempo(ini)},{_tempo(fim)},Corte,,0,0,0,,"
                          f"{{\\pos(540,{y})}}{efeito}{' '.join(partes)}")
    if credito and duracao > 0:
        # crédito do streamer: pequeno, semitransparente, embaixo, o vídeo inteiro
        linhas.append(f"Dialogue: 2,{_tempo(0)},{_tempo(duracao + 1)},Credito,,0,0,0,,{credito}")
    destino.write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")
    return destino
