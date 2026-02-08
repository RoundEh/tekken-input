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

## Run
```bash
python main.py
```

## Notes
- The app attempts to use `pynput` for keyboard emulation. If unavailable, it will log the intended key presses instead.
- Open the Mapping menu to edit `mapping.json` in a separate editor window.
- Window focus uses OS tools (Windows API, `osascript`, or `wmctrl`) and runs when playback starts. If unavailable, click the game window manually.
