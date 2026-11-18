"""Aviso no Discord via webhook (opcional)."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger("discord")
LIMITE_UPLOAD = 9_500_000  # webhooks sem boost aceitam ~10 MB


def avisar(webhook: str, corte: dict, video: Path | None):
    if not webhook:
        return
    texto = (f"🎬 **Corte novo: {corte['canal']}** às {corte['hora_txt']}\n"
             f"Pontuação {corte['pontuacao']:.0f} ({corte['relativo']}x a base)\n"
             f"Título sugerido: *{corte.get('sugestao_titulo') or '-'}*\n"
             f"Arquivo: `{corte['arquivo']}`")
    try:
        if video and video.exists() and video.stat().st_size <= LIMITE_UPLOAD:
            with open(video, "rb") as f:
                requests.post(webhook, data={"content": texto}, files={"file": (video.name, f, "video/mp4")},
                              timeout=60).raise_for_status()
        else:
            requests.post(webhook, json={"content": texto}, timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("falha ao avisar no Discord: %s", e)
