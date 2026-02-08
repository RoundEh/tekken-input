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
- Inputs are pressed for one frame by default, then released on the next frame (use separate frames for multi-step combos)
- Drag preset blocks (`QCF`, `QCB`, `EWGF`, `CROUCHDASH`) onto the P1 or P2 column to fill predefined multi-frame inputs (e.g., `QCF` = `d`, `df`, `f`; `QCB` = `d`, `db`, `b`; `EWGF` = `f`, neutral, `d`, `df+2`; `CROUCHDASH` = `f`, neutral, `d`, `df`) without extending the total frame count.

## Run
```bash
python main.py
```

## Notes
- The app attempts to use `pynput` for keyboard emulation. If unavailable, it will log the intended key presses instead.
- For some games, `pydirectinput` works better than `pynput`. You can switch the backend in the Playback section.
- Some anti-cheat or elevated games ignore synthetic input unless the tool is run with the same privileges (e.g., Run as Administrator).
- Open the Mapping menu to edit `mapping.json` in a separate editor window (supports distinct `p1` and `p2` mappings, including side-specific forward/back preferences).
- Special key names like `up`, `down`, `left`, `right`, `insert`, `delete`, `home`, and `end` are supported for P2 mappings.
- Window focus uses OS tools (Windows API, `osascript`, or `wmctrl`) and runs when playback starts. On Windows it matches window titles by substring (e.g., `TEKKEN™8`). If focus fails, click the game window manually.
