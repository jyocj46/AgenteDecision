import tkinter as tk
from tkinter import ttk
import threading
import requests
import json
import time

# ========= Config =========
OLLAMA_URL = "http://localhost:11434/api/chat"
HEALTH_URL = "http://localhost:11434/api/tags"  # ping simple
DEFAULT_MODEL = "qwen2:1.5b"
MAX_WORDS = 80

ANALYST_SYSTEM = (
    "Eres un analista de decisiones. Proporciona respuestas COMPLETAS en un solo párrafo conciso. "
    "Estructura implícitamente: (1) Análisis breve, (2) Factores clave, (3) Recomendación concreta. "
    "ES CRUCIAL que COMPLETES cada respuesta con una conclusión clara. "
    "NUNCA dejes frases a medias. Si necesitas acortar, hazlo eliminando detalles menos importantes, "
    "pero manteniendo la integridad del análisis y la recomendación final. "
    "Evita relleno y disculpas. No pidas más datos si no es crítico."
)

MAX_WORDS = 180  # Un poco más de espacio para respuestas completas

# Temas
LIGHT = {
    "bg": "#F7F7FA",
    "panel": "#FFFFFF",
    "text": "#101113",
    "muted": "#6A6F78",
    "accent": "#3B82F6",
    "user_bubble": "#D9FDD3",
    "bot_bubble": "#D6E4FF",
    "hint": "#666A73",
    "entry_bg": "#FFFFFF",
    "entry_bd": "#E5E7EB",
    "btn_bg": "#3B82F6",
    "btn_fg": "#FFFFFF",
    "header_grad": ("#EEF2FF", "#FFFFFF"),
    "scrollbar_trough": "#E5E7EB",
    "scrollbar_thumb": "#C7D2FE",
}

DARK = {
    "bg": "#0F1115",
    "panel": "#12151C",
    "text": "#E6E8EE",
    "muted": "#9CA3AF",
    "accent": "#60A5FA",
    "user_bubble": "#224030",
    "bot_bubble": "#1F2C48",
    "hint": "#9CA3AF",
    "entry_bg": "#1A1F2A",
    "entry_bd": "#2A3342",
    "btn_bg": "#2563EB",
    "btn_fg": "#E6E8EE",
    "header_grad": ("#0B1220", "#12151C"),
    "scrollbar_trough": "#1F2937",
    "scrollbar_thumb": "#374151",
}


# ========= UI Scrollable Frame =========
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, theme, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.theme = theme
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self.theme["panel"])
        self.vscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.inner = tk.Frame(self.canvas, bg=self.theme["panel"])
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscroll.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.window_id, width=event.width)

    def yview_moveto_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def apply_theme(self, theme):
        self.theme = theme
        self.configure(bg=self.theme["panel"])
        self.canvas.configure(bg=self.theme["panel"])
        self.inner.configure(bg=self.theme["panel"])


# ========= App =========
class OllamaChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Analista de Decisiones")
        self.root.geometry("820x600")
        self.root.minsize(720, 520)
        self.theme = LIGHT

        # Fuente base
        self.base_font = ("Segoe UI", 11)
        self.small_font = ("Segoe UI", 9)

        # === Contenedor base ===
        self.root.configure(bg=self.theme["bg"])

        # Header
        self.header = tk.Frame(self.root, bg=self.theme["panel"])
        self.header.pack(fill=tk.X, padx=12, pady=(12, 6))
        self._build_header(self.header)

        # Panel principal
        self.main = tk.Frame(self.root, bg=self.theme["panel"], bd=0, highlightthickness=0)
        self.main.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))

        # Área scroll
        self.scroll_area = ScrollableFrame(self.main, self.theme)
        self.scroll_area.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Hint inicial
        self.wrap_len = 620
        self._add_system_hint("💡 Escribe abajo y presiona Enviar.")

        # Footer (input)
        self.footer = tk.Frame(self.root, bg=self.theme["panel"])
        self.footer.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._build_footer(self.footer)

        # Historial
        self.history = [{"role": "system", "content": ANALYST_SYSTEM}]

        # Pings de estado
        

        # Ajustar wrap al cambiar tamaño
        self.root.bind("<Configure>", self._on_resize)

    # ---------- Header ----------
    def _build_header(self, parent):
        parent.configure(bg=self.theme["panel"])

        left = tk.Frame(parent, bg=self.theme["panel"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.title_lbl = tk.Label(
            left, text="Analista de Decisiones",
            bg=self.theme["panel"], fg=self.theme["text"],
            font=("Segoe UI Semibold", 13)
        )
        self.title_lbl.pack(anchor="w")

        self.subtitle_lbl = tk.Label(
            left, text="Respuestas cortas, analíticas y accionables",
            bg=self.theme["panel"], fg=self.theme["muted"],
            font=self.small_font
        )
        self.subtitle_lbl.pack(anchor="w", pady=(2, 0))

        right = tk.Frame(parent, bg=self.theme["panel"])
        right.pack(side=tk.RIGHT)

        # Estado de conexión (dot + texto)
        self.status_dot = tk.Canvas(right, width=10, height=10, bg=self.theme["panel"], highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6))

        # 👇 Crear primero el label y LUEGO llamar a _set_status
        self.status_lbl = tk.Label(
            right, text="", bg=self.theme["panel"], fg=self.theme["muted"], font=self.small_font
        )
        self.status_lbl.pack(side=tk.LEFT)

        # Ahora sí, ya existe status_lbl
        self._set_status(False)

        # Toggle tema
        self.theme_var = tk.BooleanVar(value=False)  # False=Light, True=Dark
        self.theme_switch = ttk.Checkbutton(
            right, text="Oscuro", variable=self.theme_var, command=self.toggle_theme
        )
        self.theme_switch.pack(side=tk.LEFT, padx=(14, 0))


    def _set_status(self, ok: bool):
        self.status_dot.delete("all")
        color = "#FFFFFF" if ok else "#FFFFFF"
        self.status_dot.create_oval(2, 2, 10, 10, fill=color, outline=color)

        self.status_lbl.configure(
            text="" if ok else "",
            fg=("#000000" if ok else "#000000") if self.theme is DARK else ( "#000000" if ok else "#000000")
        )

    # ---------- Footer ----------
    def _build_footer(self, parent):
        parent.configure(bg=self.theme["panel"])

        container = tk.Frame(parent, bg=self.theme["panel"])
        container.pack(fill=tk.X)

        # Entry con placeholder
        self.entry = tk.Entry(
            container, font=self.base_font,
            bg=self.theme["entry_bg"], fg=self.theme["text"],
            bd=1, relief="solid", highlightthickness=0,
            insertbackground=self.theme["text"]
        )
        self.entry.configure(highlightcolor=self.theme["entry_bd"], highlightbackground=self.theme["entry_bd"])
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipadx=8, ipady=8)

        self.placeholder = "Escribe tu mensaje…"
        self._set_placeholder()
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._set_placeholder)
        self.entry.bind("<Return>", lambda e: self.on_send())

        # Botón enviar
        self.send_btn = tk.Button(
            container, text="Enviar ▶", font=("Segoe UI Semibold", 10),
            bg=self.theme["btn_bg"], fg=self.theme["btn_fg"],
            activebackground=self.theme["btn_bg"], activeforeground=self.theme["btn_fg"],
            bd=0, relief="flat", cursor="hand2", command=self.on_send, padx=16, pady=10
        )
        self.send_btn.pack(side=tk.LEFT, padx=(8, 0))

    def _set_placeholder(self, *_):
        if not self.entry.get():
            self.entry.insert(0, self.placeholder)
            self.entry.config(fg=self.theme["muted"])

    def _clear_placeholder(self, *_):
        if self.entry.get() == self.placeholder:
            self.entry.delete(0, tk.END)
            self.entry.config(fg=self.theme["text"])

    # ---------- Utilidades ----------
    def _apply_theme_to_children(self, widget):
        for w in widget.winfo_children():
            if isinstance(w, tk.Frame):
                w.configure(bg=self.theme["panel"])
            elif isinstance(w, tk.Label):
                # hints y textos
                current_fg = w.cget("fg")
                if current_fg == "#666" or "💡" in (w.cget("text") or ""):
                    w.configure(bg=self.theme["panel"], fg=self.theme["hint"])
                else:
                    w.configure(bg=self.theme["panel"], fg=self.theme["text"])
            elif isinstance(w, tk.Entry):
                w.configure(bg=self.theme["entry_bg"], fg=self.theme["text"], insertbackground=self.theme["text"])
            elif isinstance(w, tk.Button):
                w.configure(bg=self.theme["btn_bg"], fg=self.theme["btn_fg"], activebackground=self.theme["btn_bg"],
                            activeforeground=self.theme["btn_fg"])
            elif isinstance(w, tk.Canvas):
                w.configure(bg=self.theme["panel"])
            self._apply_theme_to_children(w)

    def toggle_theme(self):
        self.theme = DARK if self.theme_var.get() else LIGHT
        # fondo base
        self.root.configure(bg=self.theme["bg"])
        # header/footer/main
        self.header.configure(bg=self.theme["panel"])
        self.main.configure(bg=self.theme["panel"])
        self.footer.configure(bg=self.theme["panel"])
        # status dot y labels
        self._set_status("Conectado" in self.status_lbl.cget("text"))
        self.title_lbl.configure(bg=self.theme["panel"], fg=self.theme["text"])
        self.subtitle_lbl.configure(bg=self.theme["panel"], fg=self.theme["muted"])

        # entry y botón
        self.entry.configure(bg=self.theme["entry_bg"])
        self.entry.configure(insertbackground=self.theme["text"])
        self.entry.configure(highlightcolor=self.theme["entry_bd"], highlightbackground=self.theme["entry_bd"])
        if self.entry.get() == self.placeholder:
            self.entry.configure(fg=self.theme["muted"])
        else:
            self.entry.configure(fg=self.theme["text"])
        self.send_btn.configure(bg=self.theme["btn_bg"], fg=self.theme["btn_fg"],
                                activebackground=self.theme["btn_bg"], activeforeground=self.theme["btn_fg"])

        # scroll area
        self.scroll_area.apply_theme(self.theme)
        # burbujas existentes y otros widgets
        self._apply_theme_to_children(self.scroll_area.inner)

    def _on_resize(self, event):
        # calcula wrap aproximado en función del ancho
        self.wrap_len = max(420, int(self.root.winfo_width() * 0.72))

    def _add_system_hint(self, text):
        row = tk.Frame(self.scroll_area.inner, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=(6, 8))
        hint = tk.Label(
            row, text=text, fg=self.theme["hint"], bg=self.theme["panel"],
            wraplength=self.wrap_len, justify="center", font=self.small_font
        )
        hint.pack(pady=2)
        self.scroll_area.yview_moveto_bottom()

    def _add_bubble(self, text, sender="user", stream_var=None):
        row = tk.Frame(self.scroll_area.inner, bg=self.theme["panel"])
        row.pack(fill=tk.X, padx=4, pady=6)

        if sender == "user":
            anchor_side = "e"
            bubble_bg = self.theme["user_bubble"]
            padx_outside = (160, 8)
        else:
            anchor_side = "w"
            bubble_bg = self.theme["bot_bubble"]
            padx_outside = (8, 160)

        side = tk.Frame(row, bg=self.theme["panel"])
        side.pack(anchor=anchor_side, fill=None)

        text_var = stream_var if stream_var is not None else tk.StringVar(value=text)

        bubble = tk.Label(
            side,
            textvariable=text_var,
            bg=bubble_bg,
            fg=self.theme["text"],
            font=self.base_font,
            wraplength=self.wrap_len,
            justify="left",
            padx=14,
            pady=10,
            bd=0,
        )
        bubble.pack(padx=padx_outside, pady=0)
        self.scroll_area.yview_moveto_bottom()
        return text_var

    def clear_chat(self):
        for child in self.scroll_area.inner.winfo_children():
            child.destroy()
        self.history = [{"role": "system", "content": ANALYST_SYSTEM}]
        self._add_system_hint("💬 Chat limpiado.")

    # ---------- Lógica ----------
    def on_send(self):
        prompt = self.entry.get().strip()
        if not prompt or prompt == self.placeholder:
            return
        self.entry.delete(0, tk.END)
        self._set_placeholder()

        # Burbuja user
        self._add_bubble(prompt, sender="user")
        self.history.append({"role": "user", "content": prompt})

        # Burbuja asistente (stream)
        assistant_var = tk.StringVar(value="")
        self._add_bubble("", sender="assistant", stream_var=assistant_var)

        # deshabilitar mientras responde
        self.send_btn.config(state=tk.DISABLED)
        self.entry.config(state=tk.DISABLED)

        threading.Thread(target=self.stream_response, args=(assistant_var,), daemon=True).start()

    def _truncate_to_words(self, text, max_words=MAX_WORDS):
        words = text.split()
        if len(words) <= max_words:
            return text, False
        
        # Encontrar el último punto dentro del límite para no cortar oraciones a medias
        truncated_text = " ".join(words[:max_words])
        last_period = truncated_text.rfind('.')
        
        if last_period > 0:
            # Si encontramos un punto, truncar allí para mantener la oración completa
            return truncated_text[:last_period + 1], True
        else:
            # Si no hay puntos, simplemente añadir ellipsis
            return truncated_text.rstrip() + "…", True

    def stream_response(self, assistant_var):
        payload = {
            "model": DEFAULT_MODEL,
            "messages": self.history,
            "stream": True,
            "options": {
                "num_predict": 200,  # Aumentado para permitir respuestas más largas
                "temperature": 0.1,
                "top_k": 20,
            }
        }

        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=600) as r:
                r.raise_for_status()
                assistant_text = []
                full_response = ""
                sentence_endings = ['.', '!', '?', '。', '…']  # Caracteres que indican fin de oración

                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = data.get("message", {})
                    chunk = msg.get("content", "")
                    if chunk:
                        assistant_text.append(chunk)
                        full_response = "".join(assistant_text)
                        
                        # Verificar si tenemos una oración completa
                        current_text = full_response
                        
                        # Mostrar el texto actual
                        self.root.after(0, lambda: assistant_var.set(current_text))
                        self.scroll_area.yview_moveto_bottom()

                    if data.get("done"):
                        # Cuando la respuesta está completa, asegurarnos de que termina adecuadamente
                        if full_response and full_response[-1] not in sentence_endings:
                            full_response = full_response.rstrip() + "."
                        break

                # Guardar la respuesta completa
                self.root.after(0, lambda: assistant_var.set(full_response))
                if full_response.strip():
                    self.history.append({"role": "assistant", "content": full_response.strip()})

        except requests.exceptions.ConnectionError:
            err = "⚠️"
            self.root.after(0, lambda: assistant_var.set(err))
        except Exception as e:
            self.root.after(0, lambda: assistant_var.set(f"⚠️ Error: {e}"))
        finally:
            self.root.after(0, lambda: (
                self.send_btn.config(state=tk.NORMAL),
                self.entry.config(state=tk.NORMAL)
            ))


# ========= Main =========
def main():
    root = tk.Tk()
    # Mejor scrollbar ttk look
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = OllamaChatGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
