#!/usr/bin/env python3
"""
Run this script once to produce a clickable app for your OS:

    python3 build.py          # macOS / Linux
    python  build.py          # Windows

Output:
    macOS   → dist/Instagram Non-Follower Finder.app   (drag to Applications)
    Windows → dist/Instagram Non-Follower Finder/Instagram Non-Follower Finder.exe
    Linux   → dist/Instagram Non-Follower Finder/Instagram Non-Follower Finder
"""
import os
import platform
import subprocess
import sys


def main():
    # Install / upgrade build dependencies.
    # --break-system-packages is needed on Homebrew-managed Python (macOS).
    pip_flags = ['--break-system-packages'] if platform.system() == 'Darwin' else []
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install', *pip_flags, '-r', 'requirements.txt'],
        check=True,
    )

    import customtkinter  # available now that requirements are installed
    ctk_path = os.path.dirname(customtkinter.__file__)

    # PyInstaller uses ':' on macOS/Linux and ';' on Windows as the separator
    # inside --add-data values.
    sep = ';' if platform.system() == 'Windows' else ':'

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--windowed',                        # no terminal window
        '--name', 'Instagram Non-Follower Finder',
        '--add-data', f'{ctk_path}{sep}customtkinter',
        # webdriver_manager sub-modules are imported dynamically; list them explicitly
        # so PyInstaller bundles them.
        '--hidden-import', 'webdriver_manager.chrome',
        '--hidden-import', 'webdriver_manager.firefox',
        '--hidden-import', 'webdriver_manager.microsoft',
        '--hidden-import', 'selenium.webdriver.chrome.service',
        '--hidden-import', 'selenium.webdriver.firefox.service',
        '--hidden-import', 'selenium.webdriver.edge.service',
        'UnfollowedYou.py',
    ]

    print('\nBuilding — this takes about a minute...\n')
    subprocess.run(cmd, check=True)

    system = platform.system()
    if system == 'Darwin':
        out = 'dist/Instagram Non-Follower Finder.app'
        note = (
            'Drag it to /Applications.\n'
            'First launch: right-click → Open to bypass Gatekeeper.'
        )
    elif system == 'Windows':
        out = r'dist\Instagram Non-Follower Finder\Instagram Non-Follower Finder.exe'
        note = 'Double-click the .exe to run.'
    else:
        out = 'dist/Instagram Non-Follower Finder/Instagram Non-Follower Finder'
        note = 'Mark executable with: chmod +x "' + out + '"'

    print(f'\nBuild complete!\n  {out}\n  {note}\n')
    print('Note: the browser driver is downloaded automatically on first run.')


if __name__ == '__main__':
    main()
