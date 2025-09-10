import tkinter as tk
from tkinter import messagebox
import threading
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2:1.5b"  # cambia a "mi-analista-decisiones" si ya lo tienes
MAX_WORDS = 80  # límite de palabras de salida

# Mensaje de sistema para forzar respuesta analítica, breve y en un párrafo
ANALYST_SYSTEM = (
    "Eres un analista de decisiones. Responde SIEMPRE en un solo párrafo, breve (máx. 100 palabras), "
    "con estilo analítico y accionable. Estructura implícitamente: (1) Análisis breve, (2) Factores clave, "
    "(3) Recomendación concreta. Evita relleno y disculpas. No pidas más datos si no es crítico."
)

# --- Scrollable Frame helper (Canvas + Frame) ---
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vscroll = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.inner = tk.Frame(self.canvas)
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscroll.pack(side="right", fill="y")

        # Resize inner width to match canvas for proper wrapping
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_canvas_configure(self, event):
        canvas_width = event.width
        self.canvas.itemconfig(self.window_id, width=canvas_width)

    def yview_moveto_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)


class OllamaChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("TomaDecision")
        self.root.geometry("720x540")

        # --- Config de UI ---
        self.user_bg = "#D9FDD3"       # verde claro
        self.assistant_bg = "#D6E4FF"  # azul claro
        self.text_fg = "#101010"
        self.wrap_len = 520

        # Top bar
        top = tk.Frame(root)
        top.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.clear_btn = tk.Button(top, text="Limpiar chat", command=self.clear_chat)
        self.clear_btn.pack(side=tk.RIGHT)

        # Área de mensajes
        self.scroll_area = ScrollableFrame(root)
        self.scroll_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Mensaje inicial
        self._add_system_hint(
            "💡 Escribe abajo y presiona Enviar."
        )

        # Bottom input bar
        bottom = tk.Frame(root)
        bottom.pack(fill=tk.X, padx=10, pady=(5, 10))

        self.entry = tk.Entry(bottom)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda e: self.on_send())

        self.send_btn = tk.Button(bottom, text="Enviar", command=self.on_send)
        self.send_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Historial para /api/chat (INCLUYE system al inicio)
        self.history = [{"role": "system", "content": ANALYST_SYSTEM}]

    # --- Utilidades UI ---
    def _add_system_hint(self, text):
        row = tk.Frame(self.scroll_area.inner)
        row.pack(fill=tk.X, pady=(2, 6))
        hint = tk.Label(
            row, text=text, fg="#666", bg=self.scroll_area.inner.cget("bg"),
            wraplength=self.wrap_len, justify="center"
        )
        hint.pack(pady=2)
        self.scroll_area.yview_moveto_bottom()

    def _add_bubble(self, text, sender="user", stream_var=None):
        row = tk.Frame(self.scroll_area.inner)
        row.pack(fill=tk.X, padx=4, pady=6)

        if sender == "user":
            anchor_side = "e"
            bubble_bg = self.user_bg
            padx_outside = (120, 0)
        else:
            anchor_side = "w"
            bubble_bg = self.assistant_bg
            padx_outside = (0, 120)

        side_frame = tk.Frame(row)
        side_frame.pack(anchor=anchor_side, fill=None)

        text_var = stream_var if stream_var is not None else tk.StringVar(value=text)

        bubble = tk.Label(
            side_frame,
            textvariable=text_var,
            bg=bubble_bg,
            fg=self.text_fg,
            font=("Segoe UI", 10),
            wraplength=self.wrap_len,
            justify="left",
            padx=12,
            pady=8,
            bd=0,
        )
        bubble.pack(padx=padx_outside, pady=0)

        self.scroll_area.yview_moveto_bottom()
        return text_var

    def clear_chat(self):
        for child in self.scroll_area.inner.winfo_children():
            child.destroy()
        # Reinicia historial pero mantiene el system analítico
        self.history = [{"role": "system", "content": ANALYST_SYSTEM}]
        self._add_system_hint("💬 Chat limpiado.")

    # --- Interacción ---
    def on_send(self):
        prompt = self.entry.get().strip()
        if not prompt:
            return
        self.entry.delete(0, tk.END)

        # Burbuja del usuario
        self._add_bubble(prompt, sender="user")
        self.history.append({"role": "user", "content": prompt})

        # Burbuja del asistente (stream)
        assistant_var = tk.StringVar(value="")
        self._add_bubble("", sender="assistant", stream_var=assistant_var)

        # deshabilitar envío mientras hacemos stream
        self.send_btn.config(state=tk.DISABLED)
        self.entry.config(state=tk.DISABLED)

        threading.Thread(
            target=self.stream_response,
            args=(assistant_var,),
            daemon=True
        ).start()

    def _threadsafe_set(self, var, value):
        self.root.after(0, lambda: var.set(value))

    def _truncate_to_words(self, text, max_words=MAX_WORDS):
        words = text.split()
        if len(words) <= max_words:
            return text, False
        return " ".join(words[:max_words]).rstrip() + "…", True

    def stream_response(self, assistant_var):
        model = DEFAULT_MODEL
        payload = {
            "model": model,
            "messages": self.history,
            "stream": True,
            # Reducimos la generación para respuestas más cortas
            "options": {
                "num_predict": 120,   # límite “blando” de tokens
                "temperature": 0.1,
                "top_k": 20,
            }
        }

        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=600) as r:
                r.raise_for_status()

                assistant_text = []
                truncated = False

                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = data.get("message", {})
                    chunk = msg.get("content", "")
                    if chunk and not truncated:
                        assistant_text.append(chunk)
                        current = "".join(assistant_text)
                        # CORTA en caliente si supera MAX_WORDS
                        current, truncated = self._truncate_to_words(current, MAX_WORDS)
                        self._threadsafe_set(assistant_var, current)
                        self.scroll_area.yview_moveto_bottom()

                        if truncated:
                            # dejamos de leer más chunks para “cortar” la respuesta
                            break

                    if data.get("done"):
                        break

                final_text = assistant_var.get().strip()
                if final_text:
                    self.history.append({"role": "assistant", "content": final_text})

        except requests.exceptions.ConnectionError:
            err = ("⚠️")
            self._threadsafe_set(assistant_var, err)
        except Exception as e:
            self._threadsafe_set(assistant_var, f"⚠️ Error: {e}")
        finally:
            self.root.after(0, lambda: (
                self.send_btn.config(state=tk.NORMAL),
                self.entry.config(state=tk.NORMAL)
            ))

def main():
    root = tk.Tk()
    app = OllamaChatGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
