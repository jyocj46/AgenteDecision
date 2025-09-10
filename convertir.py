import json

# Leer el archivo original
with open('dataset-original.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Convertir a formato Ollama
with open('ollama-dataset.jsonl', 'w', encoding='utf-8') as f_out:
    for line in lines:
        data = json.loads(line)
        new_data = {
            "prompt": data["question"],
            "response": data["answer"]
        }
        f_out.write(json.dumps(new_data, ensure_ascii=False) + '\n')

print("✅ Conversión completada: ollama-dataset.jsonl creado")