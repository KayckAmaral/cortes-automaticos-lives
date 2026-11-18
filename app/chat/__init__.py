"""Leitores de chat. Todos chamam callback(hora_epoch, usuario, texto)."""
from __future__ import annotations


def criar_leitor(canal: dict, callback, estado):
    plat = canal["plataforma"]
    if plat == "twitch":
        from .twitch import ChatTwitch
        return ChatTwitch(canal, callback, estado)
    if plat == "kick":
        from .kick import ChatKick
        return ChatKick(canal, callback, estado)
    if plat == "youtube":
        from .youtube import ChatYouTube
        return ChatYouTube(canal, callback, estado)
    raise ValueError(f"plataforma desconhecida: {plat}")
