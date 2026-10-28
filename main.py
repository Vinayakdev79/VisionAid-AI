import base64
import queue
import threading
import time
from datetime import datetime

import cv2
import requests
import customtkinter as ctk
import pythoncom
import win32com.client
import numpy as np
from PIL import Image

# ---------------- CONFIGURATION ----------------
MODEL = "qwen3.5:4b"
API_URL = "http://localhost:11434/api/chat"
CAMERA_INDEX = 0
FRAME_CHECK_SECONDS = 1.0       # Cheap local frame-change check
VISION_COOLDOWN_SECONDS = 15.0  # Avoid repeated slow vision requests
MIN_CHANGE_SCORE = 10.0         # Ignore small lighting/noise changes
MAX_SPOKEN_CHARS = 260          # Keep spoken updates short

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
BG, PANEL, CARD = "#0B1120", "#111827", "#172033"
TEXT, MUTED, GREEN, RED, ACCENT = "#F1F5F9", "#94A3B8", "#34D399", "#F87171", "#3B82F6"


class VisionAidDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VisionAid AI — Real-time Voice Assistant")
        self.geometry("1200x780")
        self.minsize(900, 650)
        self.configure(fg_color=BG)

        self.closing = False
        self.stop_event = threading.Event()
        self.monitoring = threading.Event()
        self.frame_lock = threading.Lock()
        self.analysis_lock = threading.Lock()
        self.latest_frame = None
        self.previous_small_frame = None
        self.previous_description = ""
        self.last_vision_time = 0.0
        self.last_analysis = "Not analyzed yet"
        self.speech_queue = queue.Queue()
        # Event used by the speech worker to indicate active playback.
        # It must exist before the worker thread starts.
        self.speaking = threading.Event()
        self.camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            self.camera.release()
            self.camera = None

        self.build_dashboard()
        threading.Thread(target=self.speech_worker, daemon=True).start()
        if self.camera is not None:
            threading.Thread(target=self.camera_worker, daemon=True).start()
            self.after(100, self.update_camera_preview)
        else:
            self.camera_status.configure(text="Camera unavailable", text_color=RED)

        threading.Thread(target=self.monitor_worker, daemon=True).start()
        threading.Thread(target=self.check_ollama_worker, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.after(1200, lambda: self.speak("VisionAid AI is starting. Automatic scene monitoring will begin shortly."))

    # ---------------- UI ----------------
    def build_dashboard(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="◈  VisionAid AI", font=ctk.CTkFont(size=26, weight="bold"), text_color="#60A5FA").grid(row=0, column=0, padx=25, pady=(13, 0), sticky="w")
        ctk.CTkLabel(header, text="Real-time visual assistance • automatic scene descriptions", text_color=MUTED).grid(row=1, column=0, padx=27, pady=(0, 12), sticky="w")
        self.ollama_status = ctk.CTkLabel(header, text="● Checking Ollama...", text_color="#FBBF24")
        self.ollama_status.grid(row=0, column=1, padx=25, pady=25, sticky="e")

        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)
        camera_panel = ctk.CTkFrame(content, fg_color=PANEL, corner_radius=16)
        camera_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        camera_panel.grid_columnconfigure(0, weight=1)
        camera_panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(camera_panel, text="Live camera", font=ctk.CTkFont(size=19, weight="bold")).grid(row=0, column=0, padx=18, pady=15, sticky="w")
        self.camera_view = ctk.CTkLabel(camera_panel, text="Waiting for camera...", fg_color="#050914", corner_radius=12)
        self.camera_view.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 12))
        self.camera_status = ctk.CTkLabel(camera_panel, text="● Camera initializing", text_color=MUTED)
        self.camera_status.grid(row=2, column=0, padx=18, pady=(0, 15), sticky="w")

        right = ctk.CTkFrame(content, fg_color=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        status = ctk.CTkFrame(right, fg_color=PANEL, corner_radius=16)
        status.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        status.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(status, text="LIVE ASSISTANT", font=ctk.CTkFont(size=11, weight="bold"), text_color=MUTED).grid(row=0, column=0, padx=16, pady=(14, 3), sticky="w")
        self.monitor_status = ctk.CTkLabel(status, text="Starting...", font=ctk.CTkFont(size=20, weight="bold"), text_color="#FBBF24")
        self.monitor_status.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")
        ctk.CTkButton(status, text="Start real-time monitoring", command=self.start_monitoring).grid(row=2, column=0, padx=14, pady=5, sticky="ew")
        ctk.CTkButton(status, text="Pause monitoring", fg_color="#374151", hover_color="#4B5563", command=self.stop_monitoring).grid(row=3, column=0, padx=14, pady=5, sticky="ew")
        ctk.CTkButton(status, text="Describe scene now", fg_color="#2563EB", hover_color="#1D4ED8", command=self.analyze_now).grid(row=4, column=0, padx=14, pady=(5, 8), sticky="ew")
        ctk.CTkLabel(status, text="Scene changes are detected automatically and described aloud.", text_color=MUTED, wraplength=330).grid(row=5, column=0, padx=14, pady=(0, 12), sticky="w")

        updates = ctk.CTkFrame(right, fg_color=PANEL, corner_radius=16)
        updates.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(updates, text="STATUS / LAST CHANGE", font=ctk.CTkFont(size=11, weight="bold"), text_color=MUTED).grid(row=0, column=0, padx=15, pady=(12, 4), sticky="w")
        self.change_label = ctk.CTkLabel(updates, text="Starting automatic scene monitoring...", text_color=TEXT, wraplength=340, justify="left")
        self.change_label.grid(row=1, column=0, padx=15, pady=(0, 12), sticky="w")
        desc = ctk.CTkFrame(right, fg_color=PANEL, corner_radius=16)
        desc.grid(row=2, column=0, sticky="nsew")
        desc.grid_columnconfigure(0, weight=1)
        desc.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(desc, text="Latest scene description", font=ctk.CTkFont(size=17, weight="bold")).grid(row=0, column=0, padx=15, pady=12, sticky="w")
        self.description_box = ctk.CTkTextbox(desc, fg_color=CARD, text_color=TEXT, wrap="word", corner_radius=10)
        self.description_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.description_box.insert("1.0", "VisionAid AI will automatically describe the scene and speak meaningful changes.")
        self.description_box.configure(state="disabled")
        ctk.CTkLabel(self, text=f"Ollama • {MODEL} • automatic vision monitoring • Windows SAPI speech", text_color=MUTED, font=ctk.CTkFont(size=11)).grid(row=2, column=0, pady=(0, 12))

    # ---------------- CAMERA ----------------
    def camera_worker(self):
        while not self.stop_event.is_set() and self.camera is not None:
            ok, frame = self.camera.read()
            if ok:
                with self.frame_lock:
                    self.latest_frame = frame.copy()
            else:
                time.sleep(0.1)

    def update_camera_preview(self):
        if self.closing:
            return
        with self.frame_lock:
            frame = self.latest_frame.copy() if self.latest_frame is not None else None
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            image.thumbnail((720, 460))
            self.preview_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            self.camera_view.configure(image=self.preview_image, text="")
            self.camera_status.configure(text="● Camera connected", text_color=GREEN)
        self.after(40, self.update_camera_preview)

    # ---------------- SPEECH OUTPUT ----------------
    def speech_worker(self):
        speaker = None
        com_initialized = False
        try:
            # SAPI5 uses Windows COM. Initialize COM explicitly on this worker thread.
            pythoncom.CoInitialize()
            com_initialized = True
            # Use Windows SAPI directly through pywin32; no pyttsx3 dependency.
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate = 0
            speaker.Volume = 100
            voices = speaker.GetVoices()
            for keyword in ("zira", "aria", "jenny", "hazel", "david"):
                match = None
                for i in range(voices.Count):
                    candidate = voices.Item(i)
                    description = str(candidate.GetDescription())
                    if keyword in description.lower():
                        match = candidate
                        break
                if match is not None:
                    speaker.Voice = match
                    print("SAPI voice selected:", match.GetDescription(), flush=True)
                    break
            print("Windows SAPI speech ready. Waiting for text.", flush=True)
            self.ui(self.set_change, "Speech output ready. Automatic scene descriptions are enabled.")
        except Exception as exc:
            print("Windows SAPI initialization error:", repr(exc), flush=True)
            self.ui(self.set_change, f"Speech initialization failed: {exc}")
        while not self.stop_event.is_set():
            try:
                text = self.speech_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if text is None:
                self.speech_queue.task_done()
                break
            if speaker is None:
                print("Cannot speak: Windows SAPI is unavailable.", flush=True)
                self.speech_queue.task_done()
                continue
            try:
                self.speaking.set()
                print("Speaking:", text[:120])
                # SVSFlagsAsync=1 prevents the worker from blocking until speech ends.
                # WaitForCompletion below keeps this dedicated worker in sync.
                speaker.Speak(text, 0)
            except Exception as exc:
                print("Windows SAPI playback error:", repr(exc), flush=True)
                self.ui(self.set_change, f"Speech playback error: {exc}")
            finally:
                self.speaking.clear()
                self.speech_queue.task_done()
        if speaker is not None:
            try:
                speaker.Speak("", 3)  # purge queued speech during shutdown
            except Exception:
                pass
        if com_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def speak(self, text):
        text = " ".join((text or "").split()).strip()
        if not text or self.closing:
            return
        # Never speak model control markers or empty-change messages.
        if "NO_SIGNIFICANT_CHANGE" in text.upper():
            return
        # Keep the UI description detailed, but speech concise and accessible.
        if len(text) > MAX_SPOKEN_CHARS:
            clipped = text[:MAX_SPOKEN_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:")
            text = clipped + "."
        print(f"[SAPI QUEUED] {text}", flush=True)
        # New meaningful update replaces waiting updates; don't build a stale backlog.
        try:
            while True:
                old = self.speech_queue.get_nowait()
                self.speech_queue.task_done()
                if old is None:
                    self.speech_queue.put_nowait(None)
                    return
        except queue.Empty:
            pass
        self.speech_queue.put(text)

    # ---------------- OLLAMA / VISION ----------------
    def ui(self, function, *args, **kwargs):
        if not self.closing:
            try:
                self.after(0, lambda: function(*args, **kwargs))
            except Exception:
                pass

    def check_ollama_worker(self):
        while not self.stop_event.is_set():
            try:
                r = requests.get("http://localhost:11434/api/tags", timeout=3)
                r.raise_for_status()
                models = [m.get("name", "") for m in r.json().get("models", [])]
                available = any(name == MODEL or name.startswith(MODEL + ":") for name in models)
                msg, color = ("● Ollama connected", GREEN) if available else (f"● Model not found: {MODEL}", "#FBBF24")
            except Exception:
                msg, color = ("● Ollama offline", RED)
            self.ui(self.ollama_status.configure, text=msg, text_color=color)
            self.stop_event.wait(15)

    def ask_qwen(self, image, question=None, previous_scene=None):
        # Smaller image reduces CPU vision latency. Keep enough detail for everyday objects.
        h, w = image.shape[:2]
        scale = min(1.0, 640 / max(w, h))
        if scale < 1.0:
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if not ok:
            return None
        image_b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")
        if question:
            prompt = ("You are VisionAid, a voice assistant for a visually impaired person. "
                      "Answer the user's question using only what is visible in this image. "
                      "Be concise, clear, and suitable to read aloud. Do not claim certainty about unclear details. "
                      "If asked to locate an object, describe its position relative to other visible objects. "
                      "Never claim a route is safe.\nUser question: " + question)
        elif previous_scene is None:
            prompt = ("Describe the visible scene for a visually impaired person in 2 to 4 concise sentences. "
                      "Mention important nearby objects, people, visible text, and approximate positions. "
                      "Be factual, do not guess, and write naturally for speech. Do not claim the scene is safe.")
        else:
            prompt = ("Compare this image with the previous scene summary. Identify only important changes. "
                      "If there is no clear meaningful change, return exactly NO_SIGNIFICANT_CHANGE. "
                      "Otherwise give one concise spoken sentence describing the change. Do not guess.\n"
                      "Previous scene summary: " + previous_scene)
        payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                   "stream": False, "think": False,
                   "options": {"num_gpu": 0, "num_ctx": 2048, "temperature": 0.2}}
        try:
            response = requests.post(API_URL, json=payload, timeout=180)
            response.raise_for_status()
            result = response.json().get("message", {}).get("content", "").strip()
            print(f"[OLLAMA RESPONSE] {result or '<empty response>'}", flush=True)
            return result or None
        except Exception as exc:
            print("Ollama vision request failed:", repr(exc))
            self.ui(self.set_change, f"Vision model error: {exc}")
            return None

    # ---------------- REAL-TIME MONITORING ----------------
    def start_monitoring(self):
        if self.camera is None:
            self.set_change("Camera is unavailable.")
            self.speak("The camera is unavailable.")
            return
        self.monitoring.set()
        self.monitor_status.configure(text="Monitoring live scene", text_color=GREEN)
        self.set_change("Real-time monitoring enabled. Scene changes will be checked automatically.")
        self.speak("Real-time monitoring started.")

    def stop_monitoring(self):
        self.monitoring.clear()
        self.monitor_status.configure(text="Monitoring paused", text_color=RED)
        self.set_change("Scene-change monitoring paused.")
        self.speak("Scene monitoring paused.")

    def analyze_now(self):
        if self.camera is None:
            self.set_change("Camera is unavailable.")
            return
        if not self.analysis_lock.acquire(blocking=False):
            self.set_change("AI is currently analyzing the scene.")
            return
        with self.frame_lock:
            frame = self.latest_frame.copy() if self.latest_frame is not None else None
        if frame is None:
            self.analysis_lock.release()
            self.set_change("No camera frame available yet.")
            return
        threading.Thread(target=self.initial_or_manual_analysis, args=(frame,), daemon=True).start()

    def initial_or_manual_analysis(self, frame):
        try:
            answer = self.ask_qwen(frame)
            if answer:
                print(f"[MANUAL ANALYSIS] {answer}", flush=True)
                self.previous_description = answer
                self.last_vision_time = time.monotonic()
                self.ui(self.set_description, answer, datetime.now().strftime("%H:%M:%S"))
                self.ui(self.set_change, "Scene description updated.")
                self.speak(answer)
        finally:
            self.analysis_lock.release()

    def monitor_worker(self):
        # Start automatically: no Analyze button required.
        self.monitoring.set()
        self.ui(self.monitor_status.configure, text="Monitoring live scene", text_color=GREEN)
        self.ui(self.set_change, "Automatic scene monitoring is active.")
        first_pass = True
        while not self.stop_event.is_set():
            if not self.monitoring.is_set():
                self.stop_event.wait(0.25)
                continue
            now = time.monotonic()
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None
            if frame is None:
                self.stop_event.wait(0.5)
                continue
            # Compare downscaled grayscale frames locally; do not call the LLM for every camera frame.
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
            changed = False
            if self.previous_small_frame is not None:
                delta = cv2.absdiff(small, self.previous_small_frame)
                score = float(np.mean(delta))
                changed = score >= MIN_CHANGE_SCORE
            self.previous_small_frame = small
            due_first_description = first_pass and (now - self.last_vision_time >= 0)
            should_analyze = (due_first_description or (changed and now - self.last_vision_time >= VISION_COOLDOWN_SECONDS))
            if should_analyze and self.analysis_lock.acquire(blocking=False):
                first_pass = False
                self.last_vision_time = now
                threading.Thread(target=self.monitor_analysis_task, args=(frame,), daemon=True).start()
            self.stop_event.wait(FRAME_CHECK_SECONDS)

    def monitor_analysis_task(self, frame):
        try:
            previous = self.previous_description
            answer = self.ask_qwen(frame, previous_scene=previous if previous else None)
            if not answer:
                print("[MONITOR] No response received from vision model.", flush=True)
                self.ui(self.set_change, "No AI response received. Check the terminal for an Ollama error.")
                return
            print(f"[MONITOR] Analysis result: {answer}", flush=True)
            if not previous:
                self.previous_description = answer
                self.ui(self.set_description, answer, datetime.now().strftime("%H:%M:%S"))
                self.ui(self.set_change, "Initial scene description ready.")
                self.speak(answer)
            elif "NO_SIGNIFICANT_CHANGE" not in answer.upper():
                # Keep the original full scene as comparison context; don't replace it
                # with a one-line change summary, which causes comparison drift.
                self.ui(self.set_description, answer, datetime.now().strftime("%H:%M:%S"))
                self.ui(self.set_change, "Scene change detected: " + answer)
                self.speak(answer)
        finally:
            self.analysis_lock.release()

    def set_change(self, message):
        if not self.closing:
            self.change_label.configure(text=message)

    def set_description(self, description, timestamp):
        if self.closing:
            return
        self.description_box.configure(state="normal")
        self.description_box.delete("1.0", "end")
        self.description_box.insert("1.0", f"Updated: {timestamp}\n\n{description}")
        self.description_box.configure(state="disabled")

    def close_app(self):
        self.closing = True
        self.stop_event.set()
        self.monitoring.clear()
        try:
            self.speech_queue.put_nowait(None)
        except queue.Full:
            pass
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.destroy()


if __name__ == "__main__":
    app = VisionAidDashboard()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        # Ctrl+C is a manual stop, not an application inference error.
        try:
            app.close_app()
        except Exception:
            pass
