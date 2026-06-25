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


## Integração com ESP32

A interface está isolada em `MachineSafetyPort`. Por padrão, o backend usa o ESP32 em `http://172.22.0.13/`.

Para usar o corte real, carregue o sketch em `esp32/epi_guard_relay.ino` e confirme que o ESP32 está acessível nesse endereço:

```text
http://172.22.0.13/
```

Depois inicie normalmente:

```powershell
.
un_backend.ps1
```

Se precisar trocar o IP futuramente, use a variável `ESP32_BASE_URL` antes de iniciar o backend:

```powershell
$env:ESP32_BASE_URL = "http://NOVO_IP_DO_ESP32"
.
un_backend.ps1
```

Rotas usadas pelo backend:

- `GET /bloquear`: aciona o relé e corta a bancada.
- `GET /liberar`: desaciona o relé e libera a bancada após reset manual.
- `GET /status`: retorna o estado atual em JSON.

## Modelo de postura ergonômica

O backend também pode carregar o modelo MultiPose3D para análise ergonômica de postura. Por padrão, ele procura o peso em `backend/models/posture/final.pth`; se esse arquivo não existir neste PC, usa o caminho local `C:\Users\Pichau\Downloads\projetos\projetos\MultiPose3D\checkpoints\final.pth` como fallback.

Em outro computador, copie o `final.pth` para `backend/models/posture/final.pth` ou defina a variável de ambiente antes de iniciar o backend:

```powershell
$env:POSTURE_MODEL_PATH="C:\caminho\para\final.pth"
.\run_backend.ps1
```

Para desativar temporariamente a análise de postura:

```powershell
$env:POSTURE_ENABLED="0"
.\run_backend.ps1
```

A postura é amostrada a cada 1 segundo por pessoa por padrão (`POSTURE_INTERVAL_SECONDS=1.0`). O sistema salva apenas dados estruturais da pose, como score, REBA, penalidades e keypoints 3D compactos. Frames, fotos e recortes da câmera não são gravados em disco.

No relatório em PDF, as imagens de postura são renderizações vetoriais geradas em memória a partir desses keypoints, não fotos da câmera.
