#include <WiFi.h>
#include <WebServer.h>

// =====================================================
// WI-FI
// =====================================================
const char* ssid = "FIAP-IOT";
const char* password = "F!@p25.IOT";

// =====================================================
// RELE
// =====================================================
const int PIN_RELE = 26;
const bool RELE_ACTIVE_LOW = true;

// =====================================================
// SERVIDOR
// =====================================================
WebServer server(80);
bool bancadaBloqueada = false;

void aplicarRele(bool bloquear) {
  if (RELE_ACTIVE_LOW) {
    digitalWrite(PIN_RELE, bloquear ? LOW : HIGH);
  } else {
    digitalWrite(PIN_RELE, bloquear ? HIGH : LOW);
  }
  bancadaBloqueada = bloquear;
}

void liberarBancada() {
  aplicarRele(false);
  Serial.println("BANCADA LIBERADA - EPI OK");
}

void bloquearBancada() {
  aplicarRele(true);
  Serial.println("BANCADA BLOQUEADA - SEM EPI");
}

void enviarStatus(int statusCode = 200) {
  String resposta = "{";
  resposta += "\"bancada\":\"";
  resposta += bancadaBloqueada ? "BLOQUEADA" : "LIBERADA";
  resposta += "\",\"locked\":";
  resposta += bancadaBloqueada ? "true" : "false";
  resposta += "}";
  server.send(statusCode, "application/json", resposta);
}

void rotaLiberar() {
  liberarBancada();
  enviarStatus();
}

void rotaBloquear() {
  bloquearBancada();
  enviarStatus();
}

void rotaStatus() {
  enviarStatus();
}

void paginaInicial() {
  String statusTexto = bancadaBloqueada ? "BANCADA BLOQUEADA" : "BANCADA LIBERADA";
  String statusCor = bancadaBloqueada ? "#dc2626" : "#16a34a";
  String statusDescricao = bancadaBloqueada
    ? "Risco identificado: EPI nao detectado."
    : "EPI validado: bancada disponivel para uso.";

  String html = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<title>EPI Guard | Protecao Ativa</title>";
  html += "<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#111827;color:white;font-family:Arial,sans-serif;padding:20px}.card{width:100%;max-width:520px;background:#1f2937;padding:32px;border-radius:18px;box-shadow:0 12px 30px rgba(0,0,0,.35)}h1{margin:0 0 8px;font-size:30px}.subtitulo,.descricao-status,.rodape{color:#cbd5e1;line-height:1.45}.status{background:";
  html += statusCor;
  html += ";padding:20px;border-radius:12px;font-size:23px;font-weight:bold;margin-bottom:10px}button{width:100%;border:0;border-radius:12px;color:white;padding:19px;font-size:18px;font-weight:bold;cursor:pointer;margin-top:12px}.liberar{background:#16a34a}.bloquear{background:#dc2626}.rodape{font-size:13px;text-align:center;margin-top:26px;color:#94a3b8}</style></head><body><main class='card'>";
  html += "<h1>EPI Guard</h1><p class='subtitulo'>Prototipo de protecao ativa por visao computacional.</p>";
  html += "<div class='status'>" + statusTexto + "</div>";
  html += "<p class='descricao-status'>" + statusDescricao + "</p>";
  html += "<a href='/liberar'><button class='liberar'>COM EPI - LIBERAR BANCADA</button></a>";
  html += "<a href='/bloquear'><button class='bloquear'>SEM EPI - CORTAR BANCADA</button></a>";
  html += "<p class='rodape'>A API do backend chama /bloquear para corte e /liberar para reset manual.</p>";
  html += "</main></body></html>";
  server.send(200, "text/html", html);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELE, OUTPUT);
  liberarBancada();

  Serial.println();
  Serial.println("Iniciando EPI Guard ESP32...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Conectando ao Wi-Fi");
  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 30) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi conectado!");
    Serial.print("Acesse: http://");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Falha ao conectar no Wi-Fi.");
  }

  server.on("/", paginaInicial);
  server.on("/liberar", rotaLiberar);
  server.on("/bloquear", rotaBloquear);
  server.on("/status", rotaStatus);
  server.on("/api/reset", rotaLiberar);
  server.on("/api/cut", rotaBloquear);

  server.begin();
  Serial.println("Servidor iniciado.");
}

void loop() {
  server.handleClient();
}
