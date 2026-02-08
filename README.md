# Tekken Input Simulator

A simple frame-by-frame input tool for Tekken-style notation with two-player support.

## Features
- Two player timelines (P1/P2)
- Timeline-based input editing
- Tekken notation parsing (e.g. `f+2,1`)
- Input mapping to keyboard keys
- Keyboard emulation (via `pynput` if available; otherwise logs actions)
- Basic GUI (Tkinter) with editable timeline columns
- Startup delay, looping playback, and auto window focusing on play
- Selectable input backend (pynput, pydirectinput, or log-only)
- Inputs are pressed for one frame by default, then released on the next frame

## Run
```bash
python main.py
```

## Notes
- The app attempts to use `pynput` for keyboard emulation. If unavailable, it will log the intended key presses instead.
- For some games, `pydirectinput` works better than `pynput`. You can switch the backend in the Playback section.
- Some anti-cheat or elevated games ignore synthetic input unless the tool is run with the same privileges (e.g., Run as Administrator).
- Open the Mapping menu to edit `mapping.json` in a separate editor window (supports distinct `p1` and `p2` mappings).
- Window focus uses OS tools (Windows API, `osascript`, or `wmctrl`) and runs when playback starts. On Windows it matches window titles by substring (e.g., `TEKKEN™8`). If focus fails, click the game window manually.
