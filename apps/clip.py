import pyperclip

import time

import os



CLIPBOARD_FILE = r"\\192.168.9.63\Shared\clipboard.txt"  # Update this path if needed



last_clipboard = ""



while True:

    clipboard_data = pyperclip.paste()

    

    if clipboard_data != last_clipboard:

        with open(CLIPBOARD_FILE, "w", encoding="utf-8") as f:

            f.write(clipboard_data)

        last_clipboard = clipboard_data



    try:

        with open(CLIPBOARD_FILE, "r", encoding="utf-8") as f:

            file_data = f.read().strip()

            if file_data != clipboard_data:

                pyperclip.copy(file_data)

    except FileNotFoundError:

        pass



    time.sleep(2)
