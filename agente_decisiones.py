import requests
import json
import sys
import time

def consultar_analista_stream(pregunta):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "mi-analista-decisiones",
        "prompt": pregunta,
        "stream": True,               # <- streaming activado
        "keep_alive": "10m",          # <- deja el modelo caliente 10 minutos
        "options": {
            "num_predict": 120,       # menos tokens = más rápido
            "temperature": 0.1,
            "top_k": 20,
            "num_ctx": 1536,          # si tu prompt es corto, baja el contexto
            "num_thread": 8,          # AJUSTA a tu CPU (ej.: 8, 12, 16...)
            # "low_vram": True,       # si te quedas corto de VRAM/ram (puede afectar velocidad)
        }
    }

    t0 = time.time()
    with requests.post(url, json=payload, stream=True, timeout=120) as r:
        r.raise_for_status()
        print("🔹 Respuesta:", end=" ", flush=True)
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line.decode("utf-8"))
            if "response" in chunk and chunk["response"]:
                # imprime a medida que llegan los tokens
                sys.stdout.write(chunk["response"])
                sys.stdout.flush()
            if chunk.get("done"):
                break
    print(f"\n Latencia total: {time.time() - t0:.2f}s")

if __name__ == "__main__":
    consultar_analista_stream("Dime cómo puedo mejorar mis ventas en mi negocio de bienes raíces.")
