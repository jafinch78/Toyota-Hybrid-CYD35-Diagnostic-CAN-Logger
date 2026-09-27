from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from .model import ExpansionOptions
from .native import load_native_session
from .packaging import expand_native_session


@dataclass
class GuiModel:
    status: str = "READY"
    stage: str = "Idle"
    session_id: str = ""
    raw_record_count: int = 0
    closed_cleanly: bool | None = None
    warnings: list[str] = field(default_factory=list)
    output_folder: str = ""

    def validate(self, source: Path) -> bool:
        self.stage = "Validating native session"
        self.status = "RUNNING"
        self.warnings.clear()
        self.output_folder = ""
        try:
            session = load_native_session(Path(source))
            try:
                self.session_id = session.session_id
                self.raw_record_count = session.can_stream.record_count if session.can_stream else 0
                self.closed_cleanly = bool(session.meta.clean_close)
                recovery = session.meta.recovery
                if recovery.truncated_tail_bytes:
                    self.warnings.append(
                        f"SESSION.META recovered {recovery.truncated_tail_bytes} truncated tail byte(s)")
                if recovery.crc_error_offsets:
                    self.warnings.append(
                        f"SESSION.META CRC errors at offsets {list(recovery.crc_error_offsets)}")
                if recovery.sequence_gaps:
                    self.warnings.append(
                        f"SESSION.META sequence gaps: {list(recovery.sequence_gaps)}")
                if not self.closed_cleanly:
                    self.warnings.append("Session has no valid clean SESSION_CLOSE record")
            finally:
                session.close()
            self.stage = "Validation complete"
            self.status = "PASS"
            return True
        except Exception as error:
            self.stage = "Validation failed"
            self.status = "FAIL"
            self.warnings = [str(error)]
            return False

    def expand(self, source: Path, output_parent: Path, *, make_zip: bool = True) -> bool:
        self.stage = "Expanding native session"
        self.status = "RUNNING"
        self.warnings.clear()
        try:
            result = expand_native_session(
                Path(source), Path(output_parent),
                options=ExpansionOptions(make_zip=make_zip),
            )
            self.session_id = result.session_id
            self.output_folder = str(result.output_root.resolve())
            self.stage = "Expansion complete"
            self.status = "PASS"
            return True
        except Exception as error:
            self.stage = "Expansion failed"
            self.status = "FAIL"
            self.warnings = [str(error)]
            return False


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    model = GuiModel()
    root = tk.Tk()
    root.title("Toyota Vehicle Bus Session Preprocessor")
    root.geometry("820x470")
    root.minsize(720, 400)

    source_var = tk.StringVar()
    output_var = tk.StringVar()
    status_var = tk.StringVar(value="READY — Idle")
    details_var = tk.StringVar(value="Select a native SESSION.META folder or ZIP.")

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text="Native session / ZIP:").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=source_var).grid(row=0, column=1, sticky="ew", padx=6)

    def browse_source() -> None:
        selected = filedialog.askopenfilename(
            title="Select native session ZIP",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
        )
        if not selected:
            selected = filedialog.askdirectory(title="Select native session folder")
        if selected:
            source_var.set(selected)

    ttk.Button(frame, text="Browse", command=browse_source).grid(row=0, column=2)

    ttk.Label(frame, text="Output folder:").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=output_var).grid(row=1, column=1, sticky="ew", padx=6)

    def browse_output() -> None:
        selected = filedialog.askdirectory(title="Select output folder")
        if selected:
            output_var.set(selected)

    ttk.Button(frame, text="Browse", command=browse_output).grid(row=1, column=2)

    ttk.Separator(frame).grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
    ttk.Label(frame, textvariable=status_var, font=("Segoe UI", 11, "bold")).grid(
        row=3, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, textvariable=details_var, justify="left", wraplength=760).grid(
        row=4, column=0, columnspan=3, sticky="nw", pady=8)

    log = tk.Text(frame, height=12, wrap="word", state="disabled")
    log.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=6)
    frame.rowconfigure(5, weight=1)

    def render() -> None:
        status_var.set(f"{model.status} — {model.stage}")
        clean = "unknown" if model.closed_cleanly is None else ("clean" if model.closed_cleanly else "unclean")
        details_var.set(
            f"Session: {model.session_id or '-'}    RAW records: {model.raw_record_count:,}    "
            f"Close state: {clean}\nOutput: {model.output_folder or '-'}")
        log.configure(state="normal")
        log.delete("1.0", "end")
        if model.warnings:
            log.insert("end", "Warnings / errors:\n")
            for item in model.warnings:
                log.insert("end", f"- {item}\n")
        else:
            log.insert("end", "No warnings.\n")
        log.configure(state="disabled")
        root.update_idletasks()

    def validate_action() -> None:
        source = source_var.get().strip()
        if not source:
            messagebox.showerror("Missing input", "Select a native session folder or ZIP.")
            return
        model.validate(Path(source))
        render()

    def expand_action() -> None:
        source = source_var.get().strip()
        output = output_var.get().strip()
        if not source or not output:
            messagebox.showerror("Missing input", "Select both the native session and output folder.")
            return
        model.expand(Path(source), Path(output))
        render()

    def open_output_action() -> None:
        path = Path(model.output_folder or output_var.get().strip())
        if not path.exists():
            messagebox.showerror("Output unavailable", "No existing output folder is available yet.")
            return
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Output folder", str(path.resolve()))

    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Button(buttons, text="Validate", command=validate_action).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Expand", command=expand_action).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Open Output Folder", command=open_output_action).pack(side="left")

    render()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
