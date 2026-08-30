from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .processor import ProcessingOptions, process


class Application(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Toyota CAN Evidence Builder 1.0.2")
        self.geometry("850x650")
        self.minsize(720, 560)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.logger = tk.StringVar()
        self.companion = tk.StringVar()
        self.video = tk.StringVar()
        self.output = tk.StringVar(value=str(Path.home() / "Documents"))
        self.raw = tk.BooleanVar(value=False)
        self.ocr = tk.BooleanVar(value=False)
        self.transcribe = tk.BooleanVar(value=False)
        self.profile = tk.StringVar(value="AUTO")
        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Toyota Hybrid CAN + BLE Evidence Builder",
                  font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 14))
        self._picker(frame, "CYD CANLOG ZIP or folder (required)", self.logger, self._choose_logger)
        self._picker(frame, "Android capture ZIP or folder", self.companion, self._choose_companion)
        self._picker(frame, "Video override (Android or Techstream MP4)", self.video, self._choose_video)
        self._picker(frame, "Output parent folder", self.output, self._choose_output)
        options = ttk.LabelFrame(frame, text="Processing", padding=10)
        options.pack(fill="x", pady=8)
        ttk.Checkbutton(options, text="Expand TCB1 to full CAN_RAW.csv", variable=self.raw).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="OCR video (requires FFmpeg and Tesseract)", variable=self.ocr).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(options, text="Transcribe narration (requires faster-whisper)", variable=self.transcribe).grid(row=2, column=0, sticky="w")
        ttk.Label(options, text="OCR layout:").grid(row=0, column=1, padx=(30, 6))
        ttk.Combobox(options, textvariable=self.profile, state="readonly", width=22,
                     values=["AUTO", "HYBRID_ASSISTANT_BATTERY_CHECK",
                             "DR_PRIUS_BATTERY_MONITOR", "AUTEL_MAXIAP200",
                             "TECHSTREAM"]).grid(row=0, column=2)
        self.run_button = ttk.Button(frame, text="PROCESS CAPTURE", command=self._start)
        self.run_button.pack(anchor="w", pady=8)
        self.log = tk.Text(frame, height=14, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)

    def _picker(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=42).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse", command=command).pack(side="right")

    def _choose_logger(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")])
        if not selected:
            selected = filedialog.askdirectory()
        if selected: self.logger.set(selected)

    def _choose_companion(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("ZIP archive", "*.zip"), ("JSON", "*.json"), ("All files", "*.*")])
        if not selected:
            selected = filedialog.askdirectory()
        if selected: self.companion.set(selected)

    def _choose_video(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("MP4 video", "*.mp4"), ("All video", "*.mkv *.mov *.avi"), ("All files", "*.*")])
        if selected: self.video.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory()
        if selected: self.output.set(selected)

    def _start(self) -> None:
        if not self.logger.get():
            messagebox.showerror("Missing input", "Select the CYD CANLOG ZIP or folder.")
            return
        self.run_button.configure(state="disabled")
        self._append("Starting processing...\n")
        options = ProcessingOptions(self.raw.get(), self.ocr.get(), self.transcribe.get(), self.profile.get())
        thread = threading.Thread(target=self._worker, args=(options,), daemon=True)
        thread.start()

    def _worker(self, options: ProcessingOptions) -> None:
        try:
            result = process(Path(self.logger.get()), Path(self.output.get()),
                             Path(self.companion.get()) if self.companion.get() else None,
                             Path(self.video.get()) if self.video.get() else None,
                             options, lambda text: self.messages.put(("log", text)))
            self.messages.put(("done", result["output"]))
        except Exception as error:
            self.messages.put(("error", str(error)))

    def _poll(self) -> None:
        try:
            while True:
                kind, text = self.messages.get_nowait()
                if kind == "log": self._append(text + "\n")
                elif kind == "done":
                    self._append("Complete: " + text + "\n")
                    self.run_button.configure(state="normal")
                    messagebox.showinfo("Complete", "Evidence package created at:\n" + text)
                elif kind == "error":
                    self._append("ERROR: " + text + "\n")
                    self.run_button.configure(state="normal")
                    messagebox.showerror("Processing failed", text)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    Application().mainloop()
