import json
import os
import queue
import threading
import time
import tkinter as tk
from sys import platform
import ctypes.wintypes
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

try:
    import pydirectinput

    PYDIRECT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    pydirectinput = None
    PYDIRECT_AVAILABLE = False


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
        if length < 0:
            return
        if len(self.frames) > length:
            self.frames = self.frames[:length]
            return
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
        self.mapping = {"p1": {"directions": {}, "buttons": {}}, "p2": {"directions": {}, "buttons": {}}}
        self.load()

    def load(self) -> None:
        try:
            with open(self.mapping_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except FileNotFoundError:
            loaded = {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid mapping JSON: {exc}") from exc
        if "p1" in loaded or "p2" in loaded:
            self.mapping = loaded
        else:
            self.mapping = {
                "p1": loaded or {"directions": {}, "buttons": {}},
                "p2": loaded or {"directions": {}, "buttons": {}},
            }

    def save(self, raw_text: str) -> None:
        parsed = json.loads(raw_text)
        self.mapping = parsed
        with open(self.mapping_path, "w", encoding="utf-8") as file:
            json.dump(self.mapping, file, indent=2)

    def resolve_key(self, token: str, player: int) -> list[str]:
        player_key = "p1" if player == 1 else "p2"
        player_map = self.mapping.get(player_key, {})
        directions = player_map.get("directions", {})
        buttons = player_map.get("buttons", {})
        if token in directions:
            return directions[token].split("+")
        if token in buttons:
            return buttons[token].split("+")
        return []


class KeyboardEmulator:
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self.log_queue = log_queue
        self.controller = KeyboardController() if PYNPUT_AVAILABLE else None
        self.mode = "pynput"

    def key_down(self, keys: list[str]) -> None:
        if not keys:
            return
        if self.mode == "pydirectinput":
            if not PYDIRECT_AVAILABLE:
                self.log_queue.put("[NO EMU] pydirectinput not installed.")
                self.log_queue.put(f"[NO EMU] Press: {keys}")
                return
            for key in keys:
                pydirectinput.keyDown(self._convert_key(key))
            return
        if self.mode == "pynput":
            if not PYNPUT_AVAILABLE:
                self.log_queue.put("[NO EMU] pynput not installed.")
                self.log_queue.put(f"[NO EMU] Press: {keys}")
                return
            for key in keys:
                self.controller.press(self._convert_key(key))
            return
        self.log_queue.put(f"[LOG ONLY] Press: {keys}")

    def key_up(self, keys: list[str]) -> None:
        if not keys:
            return
        if self.mode == "pydirectinput":
            if not PYDIRECT_AVAILABLE:
                self.log_queue.put("[NO EMU] pydirectinput not installed.")
                self.log_queue.put(f"[NO EMU] Release: {keys}")
                return
            for key in keys:
                pydirectinput.keyUp(self._convert_key(key))
            return
        if self.mode == "pynput":
            if not PYNPUT_AVAILABLE:
                self.log_queue.put("[NO EMU] pynput not installed.")
                self.log_queue.put(f"[NO EMU] Release: {keys}")
                return
            for key in keys:
                self.controller.release(self._convert_key(key))
            return
        self.log_queue.put(f"[LOG ONLY] Release: {keys}")

    def _convert_key(self, key: str):
        special = {
            "space": " ",
            "enter": "\n",
            "tab": "\t",
            "up": Key.up if Key else "up",
            "down": Key.down if Key else "down",
            "left": Key.left if Key else "left",
            "right": Key.right if Key else "right",
            "insert": Key.insert if Key else "insert",
            "delete": Key.delete if Key else "delete",
            "home": Key.home if Key else "home",
            "end": Key.end if Key else "end",
        }
        return special.get(key, key)


class TekkenNotationParser:
    def __init__(self, mapper: InputMapper) -> None:
        self.mapper = mapper

    def parse(self, notation: str, player: int) -> list[list[str]]:
        if not notation:
            return []
        steps = [step.strip() for step in notation.replace(" ", "").split(",") if step.strip()]
        parsed_steps = []
        for step in steps:
            tokens = [token for token in step.split("+") if token]
            keys = []
            for token in tokens:
                token_keys = self.mapper.resolve_key(token, player)
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
        self.mapping_window: tk.Toplevel | None = None
        self.mapping_text: tk.Text | None = None
        self.backend_var = tk.StringVar(value="pynput")

        self._build_ui()
        self._poll_log()

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        menubar = tk.Menu(self.root)
        mapping_menu = tk.Menu(menubar, tearoff=False)
        mapping_menu.add_command(label="Open Mapping Editor", command=self._open_mapping_editor)
        menubar.add_cascade(label="Mapping", menu=mapping_menu)
        self.root.config(menu=menubar)

        control_frame = ttk.LabelFrame(main_frame, text="Playback")
        control_frame.grid(row=0, column=0, sticky="ew")
        control_frame.columnconfigure(12, weight=1)

        ttk.Label(control_frame, text="FPS:").grid(row=0, column=0, padx=4, pady=4)
        self.fps_var = tk.IntVar(value=DEFAULT_FPS)
        ttk.Entry(control_frame, textvariable=self.fps_var, width=6).grid(row=0, column=1)

        ttk.Label(control_frame, text="Total Frames:").grid(row=0, column=2, padx=4)
        self.total_frames_var = tk.IntVar(value=60)
        ttk.Entry(control_frame, textvariable=self.total_frames_var, width=8).grid(row=0, column=3)

        ttk.Label(control_frame, text="Startup Delay (s):").grid(row=0, column=4, padx=4)
        self.start_delay_var = tk.DoubleVar(value=0.0)
        ttk.Entry(control_frame, textvariable=self.start_delay_var, width=8).grid(row=0, column=5)

        ttk.Label(control_frame, text="Backend:").grid(row=0, column=6, padx=4)
        backend_menu = ttk.Combobox(
            control_frame,
            textvariable=self.backend_var,
            values=("pynput", "pydirectinput", "log"),
            width=12,
            state="readonly",
        )
        backend_menu.grid(row=0, column=7, padx=4)

        ttk.Button(control_frame, text="Apply", command=self._apply_total_frames).grid(row=0, column=8, padx=4)
        ttk.Button(control_frame, text="Play", command=self._start_playback).grid(row=0, column=9, padx=4)
        ttk.Button(control_frame, text="Stop", command=self._stop_playback).grid(row=0, column=10, padx=4)
        ttk.Button(control_frame, text="Focus Window", command=self._focus_window).grid(row=0, column=11, padx=4)

        loop_frame = ttk.LabelFrame(main_frame, text="Looping")
        loop_frame.grid(row=1, column=0, sticky="ew")
        loop_frame.columnconfigure(3, weight=1)
        self.loop_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(loop_frame, text="Enable Loop", variable=self.loop_enabled_var).grid(row=0, column=0, padx=4, pady=4)
        ttk.Label(loop_frame, text="Loop Count (0=infinite):").grid(row=0, column=1, padx=4)
        self.loop_count_var = tk.IntVar(value=0)
        ttk.Entry(loop_frame, textvariable=self.loop_count_var, width=8).grid(row=0, column=2)

        focus_frame = ttk.LabelFrame(main_frame, text="Window Focus")
        focus_frame.grid(row=2, column=0, sticky="ew", pady=10)
        focus_frame.columnconfigure(1, weight=1)
        ttk.Label(focus_frame, text="Window Title:").grid(row=0, column=0, padx=4, pady=4)
        self.window_title_var = tk.StringVar(value="TEKKEN™8")
        ttk.Entry(focus_frame, textvariable=self.window_title_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(focus_frame, text="Focus", command=self._focus_window).grid(row=0, column=2, padx=4)

        timeline_frame = ttk.LabelFrame(main_frame, text="Timeline (Frame | P1 | P2)")
        timeline_frame.grid(row=3, column=0, sticky="nsew")
        main_frame.rowconfigure(3, weight=1)
        timeline_frame.columnconfigure(0, weight=1)

        self.timeline_tree = ttk.Treeview(
            timeline_frame,
            columns=("frame", "p1", "p2"),
            show="headings",
            height=12,
        )
        self.timeline_tree.heading("frame", text="Frame")
        self.timeline_tree.heading("p1", text="P1 Input")
        self.timeline_tree.heading("p2", text="P2 Input")
        self.timeline_tree.column("frame", width=80, anchor="center", stretch=False)
        self.timeline_tree.column("p1", width=240, anchor="w", stretch=True)
        self.timeline_tree.column("p2", width=240, anchor="w", stretch=True)
        self.timeline_tree.grid(row=0, column=0, sticky="nsew")
        self.timeline_tree.bind("<Double-1>", self._start_edit_cell)
        timeline_frame.rowconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(main_frame, text="Log")
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_list = tk.Listbox(log_frame, height=8)
        self.log_list.grid(row=0, column=0, sticky="nsew")

        self._apply_total_frames()

    def _apply_total_frames(self) -> None:
        total = max(1, self.total_frames_var.get())
        self.timeline.ensure_length(total)
        self._refresh_timeline()

    def _refresh_timeline(self) -> None:
        for item in self.timeline_tree.get_children():
            self.timeline_tree.delete(item)
        for idx, frame in enumerate(self.timeline.frames):
            self.timeline_tree.insert(
                "",
                tk.END,
                values=(f"{idx:03d}", frame.p1, frame.p2),
            )

    def _start_edit_cell(self, event: tk.Event) -> None:
        region = self.timeline_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        item = self.timeline_tree.identify_row(event.y)
        column = self.timeline_tree.identify_column(event.x)
        if not item or column == "#1":
            return
        bbox = self.timeline_tree.bbox(item, column)
        if not bbox:
            return
        x, y, width, height = bbox
        value = self.timeline_tree.set(item, column)
        entry = ttk.Entry(self.timeline_tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, value)
        entry.focus_set()

        def save_edit(_: tk.Event | None = None) -> None:
            new_value = entry.get()
            self.timeline_tree.set(item, column, new_value)
            frame_str = self.timeline_tree.set(item, "frame")
            frame_index = int(frame_str)
            if column == "#2":
                self.timeline.set_input(frame_index, 1, new_value)
            elif column == "#3":
                self.timeline.set_input(frame_index, 2, new_value)
            entry.destroy()

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)

    def _open_mapping_editor(self) -> None:
        if self.mapping_window and tk.Toplevel.winfo_exists(self.mapping_window):
            self.mapping_window.focus_set()
            return
        self.mapping_window = tk.Toplevel(self.root)
        self.mapping_window.title("Input Mapping (JSON)")
        self.mapping_window.geometry("480x360")
        self.mapping_window.protocol("WM_DELETE_WINDOW", self._close_mapping_editor)

        frame = ttk.Frame(self.mapping_window, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.mapping_window.columnconfigure(0, weight=1)
        self.mapping_window.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.mapping_text = tk.Text(frame, height=12)
        self.mapping_text.grid(row=0, column=0, sticky="nsew")

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Button(buttons, text="Reload", command=self._reload_mapping).grid(row=0, column=0, sticky="w", padx=4)
        ttk.Button(buttons, text="Save", command=self._save_mapping).grid(row=0, column=1, sticky="w", padx=4)

        self._reload_mapping()

    def _close_mapping_editor(self) -> None:
        if self.mapping_window:
            self.mapping_window.destroy()
        self.mapping_window = None
        self.mapping_text = None

    def _reload_mapping(self) -> None:
        if not self.mapping_text:
            return
        try:
            self.mapper.load()
            self.mapping_text.delete("1.0", tk.END)
            self.mapping_text.insert(tk.END, json.dumps(self.mapper.mapping, indent=2))
            self._log("Mapping reloaded")
        except ValueError as exc:
            messagebox.showerror("Mapping Error", str(exc))

    def _save_mapping(self) -> None:
        if not self.mapping_text:
            return
        raw = self.mapping_text.get("1.0", tk.END).strip()
        try:
            self.mapper.save(raw)
            self._log("Mapping saved")
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Mapping Error", str(exc))

    def _start_playback(self) -> None:
        if self.playback_thread and self.playback_thread.is_alive():
            return
        self._apply_backend()
        self._focus_window(auto=True)
        self.stop_event.clear()
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _stop_playback(self) -> None:
        self.stop_event.set()
        self._log("Playback stopped")

    def _apply_backend(self) -> None:
        backend = self.backend_var.get()
        self.emulator.mode = backend
        if backend == "pydirectinput" and not PYDIRECT_AVAILABLE:
            self._log("pydirectinput not available; falling back to log-only.")
        elif backend == "pynput" and not PYNPUT_AVAILABLE:
            self._log("pynput not available; falling back to log-only.")

    def _playback_loop(self) -> None:
        fps = max(1, self.fps_var.get())
        frame_duration = 1.0 / fps
        start_delay = max(0.0, self.start_delay_var.get())
        loop_enabled = self.loop_enabled_var.get()
        loop_count = max(0, self.loop_count_var.get())
        loop_target = loop_count if loop_enabled else 1

        if start_delay:
            self._log(f"Startup delay: {start_delay:.2f}s")
            time.sleep(start_delay)

        loops_done = 0
        self._log(f"Playback started at {fps} FPS")
        while not self.stop_event.is_set():
            loops_done += 1
            self._log(f"Loop {loops_done}")
            for idx, frame in enumerate(self.timeline.frames):
                if self.stop_event.is_set():
                    break
                self._log(f"Frame {idx:03d} -> P1: {frame.p1 or '-'} | P2: {frame.p2 or '-'}")
                self._emit_inputs(frame, frame_duration)
            if not loop_enabled:
                break
            if loop_target and loops_done >= loop_target:
                break
        self._log("Playback finished")

    def _focus_window(self, auto: bool = False) -> None:
        title = self.window_title_var.get().strip()
        if not title:
            if not auto:
                messagebox.showwarning("Focus Window", "Please provide a window title.")
            return
        if platform.startswith("win"):
            success = self._focus_window_windows(title)
        elif platform == "darwin":
            success = self._focus_window_macos(title)
        else:
            success = self._focus_window_linux(title)
        if success:
            self._log(f"Focused window: {title}")
        else:
            self._log(f"Failed to focus window: {title}")
            if not auto:
                messagebox.showwarning(
                    "Focus Window",
                    "Unable to focus the window automatically. Try clicking the game window manually.",
                )

    def _focus_window_windows(self, title: str) -> bool:
        try:
            import ctypes
        except ImportError:
            return False

        user32 = ctypes.windll.user32
        user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]  # type: ignore[attr-defined]
        user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM), ctypes.wintypes.LPARAM]  # type: ignore[attr-defined]
        user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]  # type: ignore[attr-defined]
        user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]  # type: ignore[attr-defined]
        user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]  # type: ignore[attr-defined]

        matches: list[int] = []
        title_lower = title.lower()

        def enum_handler(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            window_title = buffer.value
            if title_lower in window_title.lower():
                matches.append(hwnd)
                return False
            return True

        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)(enum_handler)
        user32.EnumWindows(enum_proc, 0)

        if not matches:
            return False
        handle = matches[0]
        user32.ShowWindow(handle, 5)
        return bool(user32.SetForegroundWindow(handle))

    def _focus_window_macos(self, title: str) -> bool:
        script = f'tell application "System Events" to set frontmost of the first process whose name is "{title}" to true'
        result = os.system(f"osascript -e '{script}'")
        return result == 0

    def _focus_window_linux(self, title: str) -> bool:
        if os.system("command -v wmctrl >/dev/null 2>&1") != 0:
            return False
        result = os.system(f"wmctrl -a '{title}'")
        return result == 0

    def _emit_inputs(self, frame: FrameInput, frame_duration: float) -> None:
        keys_to_press: list[str] = []
        for label, player, notation in (("P1", 1, frame.p1), ("P2", 2, frame.p2)):
            steps = self.parser.parse(notation, player)
            if not steps:
                continue
            if len(steps) > 1:
                self._log(f"{label} warning: multiple steps in one frame, using first step only")
            step = steps[0]
            self._log(f"{label} step -> {step}")
            keys_to_press.extend(step)
        if keys_to_press:
            self.emulator.key_down(keys_to_press)
            time.sleep(frame_duration)
            self.emulator.key_up(keys_to_press)
        else:
            time.sleep(frame_duration)

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
