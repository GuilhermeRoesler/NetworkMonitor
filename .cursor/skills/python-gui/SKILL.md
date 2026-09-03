---
name: python-gui
description: >-
  Painel gráfico StatusWindow do Network Monitor (tkinter em python/gui.py):
  Treeview, drag-and-drop de ordem, rename, hidden/muted, notificações.
  Use ao alterar a GUI, thread-safety do painel ou ações de contexto dos peers.
---

# Python GUI (`python/gui.py`)

## Modelo

- Classe `StatusWindow` + singleton `status_window`
- Roda em thread daemon `radmin-gui` com seu próprio `tk.Tk().mainloop()`
- Refresh a cada `REFRESH_MS` (3000)
- Lê estado via imports **lazy** de `main` (dentro de métodos)

## UI

- Treeview: Nome · IP · Status
- Toolbar: Atualizar · Notificações · Mostrar ocultos
- Rename: duplo-clique ou F2; Enter confirma, Escape cancela
- Contexto: ocultar/mostrar, silenciar, etc.
- Drag-and-drop reordena via `move_peer` / `save_peer_order`
- Cores em `COLORS` (online verde, offline vermelho, oculto cinza, muted âmbar)

Fechar janela = `withdraw` (não mata o monitor). Encerrar vem da bandeja.

## Thread-safety

- Mutações de widgets só no thread tk (`root.after`)
- `_refresh_data` **adia** refresh se `_edit_entry` ativo ou drag em andamento
- Lock `_lock` protege start/show da thread

## Nova ação no painel

1. Função de persistência em `python/main.py`
2. Handler em `StatusWindow` chamando essa função
3. Atualizar menu de contexto / toolbar se necessário
4. Manter textos em português

## Não fazer

- Importar `gui` no top-level de `main.py`
- Bloquear o mainloop com I/O longo (usar after / threads já existentes do monitor)
- Assumir que a janela está aberta — checar `is_open` / `_root`
