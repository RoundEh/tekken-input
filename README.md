# Tekken Input Simulator

A simple frame-by-frame input tool for Tekken-style notation with two-player support.

## Features
- Two player timelines (P1/P2)
- Frame-by-frame input editing
- Tekken notation parsing (e.g. `f+2,1`)
- Input mapping to keyboard keys
- Keyboard emulation (via `pynput` if available; otherwise logs actions)
- Basic GUI (Tkinter)
- Startup delay, looping playback, and optional window focusing

## Run
```bash
python main.py
```

## Notes
- The app attempts to use `pynput` for keyboard emulation. If unavailable, it will log the intended key presses instead.
- Edit `mapping.json` in the UI to customize key mappings.
- Window focus uses OS tools (Windows API, `osascript`, or `wmctrl`). If unavailable, click the game window manually.
