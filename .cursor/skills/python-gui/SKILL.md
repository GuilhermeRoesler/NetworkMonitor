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
- Lê/grava estado via imports **lazy** de `main` (dentro de `GuiApi` / `build_snapshot`)

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

- Persistência só via `GuiApi` → funções de `main.py`
- JS marca `busy` durante rename/drag e ignora snapshots nesse intervalo
- Histórico via `get_peer_history(ip)` (não no snapshot de 3s); expansão preservada no re-render
- `run_main_loop` / `webview.start` apenas na thread principal
- `show()` / `close()` podem ser chamados a partir da thread da bandeja

## Nova ação no painel

1. Função de persistência em `python/main.py`
2. Método em `GuiApi` + handler em `python/ui/app.js`
3. Incluir no snapshot se for estado exibido
4. Manter textos em português

## Ícone / favicon

- Janela/taskbar: `webview.start(icon=…)` com `assets/icon.ico` via `resolve_asset_path`; fallback Win32 em `_apply_window_icon` (HWND de `window.native.Handle`).
- Favicon do painel: `python/ui/favicon.ico` + `favicon.png` (gerados por `assets/_generate_icon.py`), linkados em `index.html`.

## Build

- `python/build.py` empacota `ui/` (`--add-data`) e `--collect-all=webview`
- Runtime WebView2 necessário no Windows alvo

## Não fazer

- Importar `gui` no top-level de `main.py`
- Duplicar I/O de config no JS ou em `gui.py` fora das APIs de `main`
- Assumir que a janela está aberta — checar `is_open` / `_window`
- Migrar a UI C++ neste fluxo (permanece Win32)
