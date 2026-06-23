# EPI Guard — Monitoramento local de EPIs

Aplicação local FastAPI + React para monitorar capacete, luvas e óculos com um modelo YOLO carregado uma única vez no PC servidor.

O navegador captura a câmera, envia amostras ao backend por WebSocket e recebe as detecções em tempo real. Frames, vídeos e recortes não são salvos em disco.

## Pré-requisitos

- Git
- Python 3.11
- Node.js LTS
- Webcam
- Windows PowerShell

## Como rodar após clonar o repositório

```powershell
git clone URL_DO_REPOSITORIO
cd ChallengeFiap2026_ABDI_modeloIA
```

Em um terminal, inicie o backend:

```powershell
.\run_backend.ps1
```

Em outro terminal, inicie o frontend:

```powershell
.\run_frontend.ps1
```

Depois abra:

```text
http://localhost:5173
```

Usuários iniciais:

- Admin: `admin` / `admin123`
- Funcionário: `funcionario` / `func123`

Se o PowerShell bloquear os scripts, execute uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Como gerar uma versão servida pelo FastAPI

```powershell
npm --prefix frontend install
npm --prefix frontend run build
.\run_backend.ps1
```

Depois abra:

```text
http://localhost:8000
```

## Modelo e dados

- O peso final do modelo fica em `backend/models/best.pt`.
- Dataset, resultados de treino, imagens, vídeos, checkpoints antigos e instaladores são ignorados pelo Git.
- Frames de câmera não são salvos em disco; são processados em memória via WebSocket.
- Dados operacionais ficam em `backend/data/store.json`, com escrita atômica.
- Cada computador cria seu próprio `store.json` local.

## Política padrão

- Janela deslizante: 3 s.
- Presença confirmada: 60% das amostras.
- Ausência confirmada: abaixo de 40%.
- Nível 1: 2 s.
- Nível 2: 5 s, registra infração.
- Nível 3: 10 s, simula corte.
- Liberação após corte: somente reset manual e conformidade recuperada.

## Uso em outros aparelhos

Em `localhost`, a câmera funciona normalmente. Para acessar de outro dispositivo na rede, como um celular, pode ser necessário configurar HTTPS, porque navegadores costumam bloquear `getUserMedia` fora de contextos seguros.

## Integração futura com ESP32

A interface está isolada em `MachineSafetyPort`. Hoje `SimulationAdapter` registra o corte; a futura `ESP32Adapter` pode internalizar o protocolo Wi-Fi sem alterar o restante do sistema.