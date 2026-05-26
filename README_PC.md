# NeoBoX for PC/Laptop

This version of NeoBoX is configured to run on a standard computer for development and testing.

## Setup Instructions

1. **Install Python 3.10+** (if not already installed).
2. **Clone the repository:**
   ```bash
   git clone https://github.com/darkLabz001/NeoBoX.git
   cd NeoBoX
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the App

To launch the UI in a window:
```bash
python3 run.py --mode windowed --scale 2
```
*   `--scale 2`: Makes the 480x320 screen appear as 960x640 on your monitor.
*   `--no-intro`: (Optional) Skip the boot animation.

## Keyboard Controls

Since you don't have Game HAT buttons, use your keyboard:

| Game HAT Button | PC Keyboard |
| :--- | :--- |
| **UP / DOWN** | Arrow Keys |
| **LEFT / RIGHT** | Arrow Keys |
| **A** (Select) | **Z** or **Enter** |
| **B** (Back) | **X** or **Backspace** |
| **X** | **S** |
| **Y** | **A** |
| **L / R** (Shoulders) | **Q / W** |
| **START** | **Space** |
| **SELECT** | **Shift** |
| **MENU** | **M** |
| **EXIT** | **Esc** |

## Notes
- **Payloads:** Some payloads (like WiFi attacks) require specific hardware (like an Alfa adapter) and Linux. These may not work fully on Windows or macOS, but the UI itself will function perfectly.
- **Web UI:** To test the Web UI, run `python3 web/server.py` in a separate terminal.
