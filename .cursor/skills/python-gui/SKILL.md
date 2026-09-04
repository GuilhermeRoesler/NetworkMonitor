---
name: python-gui
description: >-
  Painel gráfico StatusWindow do Network Monitor (WebView2 / pywebview em
  python/gui.py + python/ui/): lista de peers, drag-and-drop, rename,
  hidden/muted, notificações. Use ao alterar a GUI, bridge JS↔Python ou assets HTML.
---

# Python GUI (`python/gui.py` + `python/ui/`)

## Modelo

- Classe `StatusWindow` + singleton `status_window`
- Bridge `GuiApi` exposta como `window.pywebview.api.*`
- **`run_main_loop()` na thread principal** (`webview.start` — exigência do pywebview)
- Modo bandeja: tray em daemon `radmin-tray`; painel inicia oculto até `show()`
- Frontend: `python/ui/index.html` + `app.css` + `app.js` (vanilla)
- Snapshot a cada ~3s via JS (`get_snapshot`) ou `refresh_now`
- Lê/grava estado via imports de `nm.*` (`config`, `state`, `history`, `network`, `identity`, `paths`, `win32_ui`)

## UI

- Lista: Nome · IP · Latência · Status (pills)
- Toolbar: Atualizar · Notificações · Mostrar ocultos · Histórico (retenção 1/3/7/14/30 dias)
- Tema dark utilitário
- Rename: duplo-clique ou F2; Enter confirma, Escape cancela
- Contexto: ver histórico, ocultar/mostrar, silenciar, mover ao topo
- Histórico: segundo clique no peer selecionado (ou menu) abre timeline CSS por dia (00:00–24:00)
- Drag-and-drop reordena via `move_peer` / `move_peer_to_end`
- Muted: badge “Silenciado” (sem emoji)

Fechar janela = `hide()` se `close_hides` (modo bandeja). Encerrar vem da bandeja.
`--gui` usa `close_hides=False` (destroy encerra o loop WebView).

## Thread-safety

- Persistência só via `GuiApi` → funções de `nm.config` / `nm.history` / etc.
- JS marca `busy` durante rename/drag e ignora snapshots nesse intervalo
- Histórico via `get_peer_history(ip)` (não no snapshot de 3s); expansão preservada no re-render
- `run_main_loop` / `webview.start` apenas na thread principal
- `show()` / `close()` podem ser chamados a partir da thread da bandeja

## Nova ação no painel

1. Função de persistência em `python/nm/` (ex.: `nm/config.py`)
2. Método em `GuiApi` + handler em `python/ui/app.js`
3. Incluir no snapshot se for estado exibido
4. Manter textos em português

## Ícone / favicon

- Taskbar (dev via `python.exe`): `ensure_win32_app_user_model_id()` (`Gui.NetworkMonitor`) **antes** de qualquer UI — sem isso o Windows usa o ícone do Python.
- Janela: `webview.start(icon=…)` + `_apply_window_icon` (Form.Icon, `WM_SETICON`, `GCLP_HICON` via HWND de `window.native.Handle`).
- Favicon do painel: `favicon.svg` (preferido na web) + `favicon.png` 32px + `favicon.ico`; gerados/atualizados por `assets/_generate_icon.py` (PNG/ICO — desenhar no tamanho alvo, sem downscale de 512).

## Build

- `python/build.py` empacota `ui/` (`--add-data`) e `--collect-all=webview`
- Runtime WebView2 necessário no Windows alvo
- **Demo estática:** `python/ui/demo-api.js` stubba `pywebview.api` em `*.github.io` ou `?demo=1` (não ativa no app real). Deploy: `.github/workflows/pages.yml`

## Não fazer

- Importar `gui` no top-level de `nm.cli` / `main.py` (só lazy em tray/cli)
- Duplicar I/O de config no JS ou em `gui.py` fora das APIs de `nm`
- Assumir que a janela está aberta — checar `is_open` / `_window`
- Migrar a UI C++ neste fluxo (permanece Win32)
