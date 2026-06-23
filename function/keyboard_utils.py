import sys
import time

def handle_key(key, sender):
    """Handles a key press for pausing or quitting."""
    if key == 'p':
        if sender.paused.is_set():
            sender.paused.clear()
            print("\n[Keyboard] Resumed sending.")
        else:
            sender.paused.set()
            print("\n[Keyboard] Paused sending. Press 'p' again to resume.")
    elif key == 'q':
        print("\n[Keyboard] Quit signal received. Stopping sender...")
        sender.shutdown_event.set()

def keyboard_listener(sender):
    """A non-blocking listener for 'p' (pause) and 'q' (quit) commands."""
    print("[Keyboard] Press 'p' to pause/resume, 'q' to quit.")
    if sys.platform == 'win32':
        import msvcrt
        # "World-Class" Fix: No special handling needed for Windows as msvcrt does not alter terminal state.
        # The loop is sufficient.
        try:
            while not sender.shutdown_event.is_set():
                if msvcrt.kbhit():
                    try:
                        key = msvcrt.getch().decode('utf-8').lower()
                        handle_key(key, sender)
                    except (UnicodeDecodeError, AttributeError):
                        pass # Ignore non-character keys
                time.sleep(0.1)
        finally:
            pass # No cleanup needed for msvcrt
    else:
        # Non-blocking listener for Linux/macOS
        import tty
        import termios
        import select
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        # --- "World-Class" Fix: Use a try...finally block to GUARANTEE terminal restoration ---
        # This prevents the menu from crashing on the next input() call.
        try:
            tty.setcbreak(fd)
            while not sender.shutdown_event.is_set():
                # Use select to wait for input without blocking
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1)
                    if key:
                        handle_key(key.lower(), sender)
        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)