# EPI Guard — Monitoramento local de EPIs

Aplicação local FastAPI + React para monitorar capacete, luvas e óculos com um modelo YOLO carregado uma única vez no PC servidor.

## Como rodar em desenvolvimento

1. Backend:

```powershell
.\run_backend.ps1
```

2. Frontend, em outro terminal:

```powershell
.\run_frontend.ps1
```

3. Abra `http://localhost:5173`.

Usuários iniciais:

- Admin: `admin` / `admin123`
- Funcionário: `funcionario` / `func123`

## Como gerar uma versão servida pelo FastAPI

```powershell
npm --prefix frontend install
npm --prefix frontend run build
.\run_backend.ps1
```

Depois abra `http://localhost:8000`.

## Modelo e dados

- O único peso versionável é `backend/models/best.pt`.
- Dataset, resultados de treino, imagens, vídeos, checkpoints antigos e instaladores são ignorados pelo Git.
- Frames de câmera não são salvos em disco; são processados em memória via WebSocket.
- Dados operacionais ficam em `backend/data/store.json`, com escrita atômica.

## Política padrão

- Janela deslizante: 3 s.
- Presença confirmada: 60% das amostras.
- Ausência confirmada: abaixo de 40%.
- Nível 1: 2 s.
- Nível 2: 5 s, registra infração.
- Nível 3: 10 s, simula corte.
- Liberação após corte: somente reset manual e conformidade recuperada.

## Integração futura com ESP32

A interface está isolada em `MachineSafetyPort`. Hoje `SimulationAdapter` registra o corte; a futura `ESP32Adapter` pode internalizar o protocolo Wi-Fi sem alterar o restante do sistema.

