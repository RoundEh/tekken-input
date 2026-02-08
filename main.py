import json
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk

try:
    from pynput.keyboard import Controller as KeyboardController
    from pynput.keyboard import Key

    PYNPUT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    KeyboardController = None
    Key = None
    PYNPUT_AVAILABLE = False


DEFAULT_FPS = 60
MAPPING_PATH = "mapping.json"

DIRECTION_KEYS = {"u", "d", "b", "f", "uf", "ub", "df", "db"}


@dataclass
class FrameInput:
    p1: str = ""
    p2: str = ""


@dataclass
class Timeline:
    frames: list[FrameInput] = field(default_factory=list)

    def ensure_length(self, length: int) -> None:
        while len(self.frames) < length:
            self.frames.append(FrameInput())

    def set_input(self, frame_index: int, player: int, notation: str) -> None:
        self.ensure_length(frame_index + 1)
        if player == 1:
            self.frames[frame_index].p1 = notation
        else:
            self.frames[frame_index].p2 = notation

    def get_input(self, frame_index: int, player: int) -> str:
        if frame_index < 0 or frame_index >= len(self.frames):
            return ""
        frame = self.frames[frame_index]
        return frame.p1 if player == 1 else frame.p2


class InputMapper:
    def __init__(self, mapping_path: str = MAPPING_PATH) -> None:
        self.mapping_path = mapping_path
        self.mapping = {"directions": {}, "buttons": {}}
        self.load()

    def load(self) -> None:
        try:
            with open(self.mapping_path, "r", encoding="utf-8") as file:
                self.mapping = json.load(file)
        except FileNotFoundError:
            self.mapping = {"directions": {}, "buttons": {}}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid mapping JSON: {exc}") from exc

    def save(self, raw_text: str) -> None:
        parsed = json.loads(raw_text)
        self.mapping = parsed
        with open(self.mapping_path, "w", encoding="utf-8") as file:
            json.dump(self.mapping, file, indent=2)

    def resolve_key(self, token: str) -> list[str]:
        directions = self.mapping.get("directions", {})
        buttons = self.mapping.get("buttons", {})
        if token in directions:
            return directions[token].split("+")
        if token in buttons:
            return buttons[token].split("+")
        return []


class KeyboardEmulator:
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self.log_queue = log_queue
        self.controller = KeyboardController() if PYNPUT_AVAILABLE else None

    def press_keys(self, keys: list[str]) -> None:
        if not keys:
            return
        if not PYNPUT_AVAILABLE:
            self.log_queue.put(f"[NO EMU] Press: {keys}")
            return
        for key in keys:
            self.controller.press(self._convert_key(key))
        for key in keys:
            self.controller.release(self._convert_key(key))

    def _convert_key(self, key: str):
        special = {
            "space": " ",
            "enter": "\n",
            "tab": "\t",
        }
        return special.get(key, key)


class TekkenNotationParser:
    def __init__(self, mapper: InputMapper) -> None:
        self.mapper = mapper

    def parse(self, notation: str) -> list[list[str]]:
        if not notation:
            return []
        steps = [step.strip() for step in notation.replace(" ", "").split(",") if step.strip()]
        parsed_steps = []
        for step in steps:
            tokens = [token for token in step.split("+") if token]
            keys = []
            for token in tokens:
                token_keys = self.mapper.resolve_key(token)
                if not token_keys:
                    token_keys = [token]
                keys.extend(token_keys)
            parsed_steps.append(keys)
        return parsed_steps


class TekkenInputApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Tekken Input Simulator")
        self.timeline = Timeline()
        self.mapper = InputMapper()
        self.parser = TekkenNotationParser(self.mapper)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.emulator = KeyboardEmulator(self.log_queue)
        self.playback_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

        self._build_ui()
        self._poll_log()

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        control_frame = ttk.LabelFrame(main_frame, text="Playback")
        control_frame.grid(row=0, column=0, sticky="ew")
        control_frame.columnconfigure(7, weight=1)

        ttk.Label(control_frame, text="FPS:").grid(row=0, column=0, padx=4, pady=4)
        self.fps_var = tk.IntVar(value=DEFAULT_FPS)
        ttk.Entry(control_frame, textvariable=self.fps_var, width=6).grid(row=0, column=1)

        ttk.Label(control_frame, text="Total Frames:").grid(row=0, column=2, padx=4)
        self.total_frames_var = tk.IntVar(value=60)
        ttk.Entry(control_frame, textvariable=self.total_frames_var, width=8).grid(row=0, column=3)

        ttk.Button(control_frame, text="Apply", command=self._apply_total_frames).grid(row=0, column=4, padx=4)
        ttk.Button(control_frame, text="Play", command=self._start_playback).grid(row=0, column=5, padx=4)
        ttk.Button(control_frame, text="Stop", command=self._stop_playback).grid(row=0, column=6, padx=4)

        frame_control = ttk.LabelFrame(main_frame, text="Frame Editor")
        frame_control.grid(row=1, column=0, sticky="ew", pady=10)
        frame_control.columnconfigure(5, weight=1)

        ttk.Label(frame_control, text="Frame:").grid(row=0, column=0, padx=4, pady=4)
        self.current_frame_var = tk.IntVar(value=0)
        ttk.Entry(frame_control, textvariable=self.current_frame_var, width=8).grid(row=0, column=1)

        ttk.Button(frame_control, text="Prev", command=self._prev_frame).grid(row=0, column=2, padx=4)
        ttk.Button(frame_control, text="Next", command=self._next_frame).grid(row=0, column=3, padx=4)

        ttk.Label(frame_control, text="P1 Notation:").grid(row=1, column=0, padx=4)
        self.p1_entry = ttk.Entry(frame_control, width=30)
        self.p1_entry.grid(row=1, column=1, columnspan=3, sticky="ew")
        ttk.Button(frame_control, text="Set P1", command=lambda: self._set_frame_input(1)).grid(row=1, column=4, padx=4)

        ttk.Label(frame_control, text="P2 Notation:").grid(row=2, column=0, padx=4)
        self.p2_entry = ttk.Entry(frame_control, width=30)
        self.p2_entry.grid(row=2, column=1, columnspan=3, sticky="ew")
        ttk.Button(frame_control, text="Set P2", command=lambda: self._set_frame_input(2)).grid(row=2, column=4, padx=4)

        timeline_frame = ttk.LabelFrame(main_frame, text="Timeline (Frame : P1 | P2)")
        timeline_frame.grid(row=2, column=0, sticky="nsew")
        main_frame.rowconfigure(2, weight=1)
        timeline_frame.columnconfigure(0, weight=1)

        self.timeline_list = tk.Listbox(timeline_frame, height=12)
        self.timeline_list.grid(row=0, column=0, sticky="nsew")
        timeline_frame.rowconfigure(0, weight=1)

        mapping_frame = ttk.LabelFrame(main_frame, text="Input Mapping (JSON)")
        mapping_frame.grid(row=3, column=0, sticky="nsew", pady=10)
        mapping_frame.columnconfigure(0, weight=1)

        self.mapping_text = tk.Text(mapping_frame, height=10)
        self.mapping_text.grid(row=0, column=0, sticky="nsew")
        mapping_frame.rowconfigure(0, weight=1)

        ttk.Button(mapping_frame, text="Reload", command=self._reload_mapping).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Button(mapping_frame, text="Save", command=self._save_mapping).grid(row=1, column=0, sticky="e", padx=4, pady=4)

        log_frame = ttk.LabelFrame(main_frame, text="Log")
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_list = tk.Listbox(log_frame, height=8)
        self.log_list.grid(row=0, column=0, sticky="nsew")

        self._reload_mapping()
        self._apply_total_frames()

    def _apply_total_frames(self) -> None:
        total = max(1, self.total_frames_var.get())
        self.timeline.ensure_length(total)
        self._refresh_timeline()

    def _refresh_timeline(self) -> None:
        self.timeline_list.delete(0, tk.END)
        for idx, frame in enumerate(self.timeline.frames):
            self.timeline_list.insert(tk.END, f"{idx:03d}: {frame.p1 or '-'} | {frame.p2 or '-'}")

    def _set_frame_input(self, player: int) -> None:
        frame_index = self.current_frame_var.get()
        notation = self.p1_entry.get() if player == 1 else self.p2_entry.get()
        self.timeline.set_input(frame_index, player, notation)
        self._refresh_timeline()

    def _prev_frame(self) -> None:
        current = max(0, self.current_frame_var.get() - 1)
        self.current_frame_var.set(current)
        self._load_frame_inputs(current)

    def _next_frame(self) -> None:
        current = min(len(self.timeline.frames) - 1, self.current_frame_var.get() + 1)
        self.current_frame_var.set(current)
        self._load_frame_inputs(current)

    def _load_frame_inputs(self, frame_index: int) -> None:
        self.p1_entry.delete(0, tk.END)
        self.p2_entry.delete(0, tk.END)
        self.p1_entry.insert(0, self.timeline.get_input(frame_index, 1))
        self.p2_entry.insert(0, self.timeline.get_input(frame_index, 2))

    def _reload_mapping(self) -> None:
        try:
            self.mapper.load()
            self.mapping_text.delete("1.0", tk.END)
            self.mapping_text.insert(tk.END, json.dumps(self.mapper.mapping, indent=2))
            self._log("Mapping reloaded")
        except ValueError as exc:
            messagebox.showerror("Mapping Error", str(exc))

    def _save_mapping(self) -> None:
        raw = self.mapping_text.get("1.0", tk.END).strip()
        try:
            self.mapper.save(raw)
            self._log("Mapping saved")
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Mapping Error", str(exc))

    def _start_playback(self) -> None:
        if self.playback_thread and self.playback_thread.is_alive():
            return
        self.stop_event.clear()
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _stop_playback(self) -> None:
        self.stop_event.set()
        self._log("Playback stopped")

    def _playback_loop(self) -> None:
        fps = max(1, self.fps_var.get())
        frame_duration = 1.0 / fps
        self._log(f"Playback started at {fps} FPS")
        for idx, frame in enumerate(self.timeline.frames):
            if self.stop_event.is_set():
                break
            self._log(f"Frame {idx:03d} -> P1: {frame.p1 or '-'} | P2: {frame.p2 or '-'}")
            self._emit_inputs(frame)
            time.sleep(frame_duration)
        self._log("Playback finished")

    def _emit_inputs(self, frame: FrameInput) -> None:
        for label, notation in (("P1", frame.p1), ("P2", frame.p2)):
            steps = self.parser.parse(notation)
            if not steps:
                continue
            for step in steps:
                self._log(f"{label} step -> {step}")
                self.emulator.press_keys(step)

    def _log(self, message: str) -> None:
        self.log_queue.put(message)

    def _poll_log(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_list.insert(tk.END, msg)
                self.log_list.yview_moveto(1)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)


if __name__ == "__main__":
    root = tk.Tk()
    app = TekkenInputApp(root)
    root.mainloop()
