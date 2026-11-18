# Projeto: cortes automáticos de lives da Twitch (lançamento GTA 6, 19/11/2026)

- **Leia `PLANO.md` primeiro.** Ele tem a arquitetura, as decisões, o cronograma e a tabela de status (seção 0). Atualize a tabela de status ao concluir etapas.
- **Prazo real: 18/11/2026 às 08:00 de Brasília** (streamers BR jogando pela região da Nova Zelândia). Segunda onda: 19/11 às 00:00. Priorize o MVP.
- Multiplataforma: Twitch, **Kick (prioridade)** e YouTube. Vídeo sempre via Streamlink; o chat tem um módulo por plataforma (PLANO.md, seção 5.0).
- Chat da Kick: o Pusher foi abandonado pela Kick. Lemos o chat com um Chrome headless (Playwright) que escuta o WebSocket `realtime...kick.com` (PLANO.md, 5.0).
- Rodar o sistema: `.\.venv\Scripts\python main.py [--canais dona] [--nao-abrir]`. Painel em http://localhost:8000. Teste sem chat: `testar_corte.py <canal>`.
- O usuário fala português (BR). Responda em português.
- O usuário deu permissão total para operar nesta pasta (D:\GTA6).
- Máquina: Windows 11, i5-8265U, 8 GB RAM, Intel UHD 620, **sem NVIDIA**. Whisper roda na CPU (`int8`), e o encode usa QuickSync (`h264_qsv`) com fallback para `libx264`.
- Python 3.12 com venv em `.venv`. Rode scripts com `.\.venv\Scripts\python`.
- Caminhos no filtro `ass=` do FFmpeg: rodar o ffmpeg com o cwd na pasta do corte e passar só o nome do arquivo (evita o problema do `C:\`).
- Quando algo depender do usuário (UAC, webhook, escolha de streamers, conferir calibração), avise claramente o que ele precisa fazer (ver PLANO.md, seção 8).
