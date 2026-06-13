# Instagram Non-Follower Finder

A desktop app that automates finding Instagram accounts you follow that don't follow you back. Built with **Python**, Selenium WebDriver, and CustomTkinter — it drives a real browser to scroll and extract your follower/following lists, applies hand-rolled anti-bot stealth, and presents the diff in a clean dark-mode GUI with cross-browser support.

[![Demo](thumbnail.jpg)](https://youtu.be/CibVM3FueDY)

## Features

- Cross-browser — Chrome, Firefox, Edge, Safari
- Stealth mode — patches automation fingerprints to reduce bot detection across browsers
- Manual login flow with full 2FA and captcha support
- Auto-downloads browser drivers (no PATH setup required)
- Accumulates users across virtual-scroll batches so no one is missed
- Results copyable to clipboard

## How It Works

The app launches a real browser through Selenium WebDriver and lets you log in manually (so 2FA and captchas just work). To reduce automation detection, it injects a small stealth script that redefines `navigator.webdriver` — via the Chrome DevTools Protocol (`Page.addScriptToEvaluateOnNewDocument`) on Chromium browsers and `execute_script` on Firefox — alongside flags like `--disable-blink-features=AutomationControlled` and Firefox's `dom.webdriver.enabled = false`.

It then opens your followers and following dialogs and uses `ActionChains` with `ScrollOrigin` to scroll the virtual-scrolling lists, accumulating usernames across batches until the full list is captured. A set difference between *following* and *followers* yields the accounts that don't follow you back. All of this runs on a background `threading` worker so the CustomTkinter UI stays responsive, with per-browser error dialogs when a driver fails to start.

## Skills Demonstrated

- Browser automation — Selenium WebDriver driving Chrome, Firefox, Edge, and Safari
- Cross-browser abstraction — per-browser options and driver setup behind one flow (`match`/`case`)
- Anti-bot stealth — CDP `navigator.webdriver` patching and disabling automation fingerprints
- Dynamic web scraping — `ActionChains` + `ScrollOrigin` to drive virtual-scroll list extraction
- Set operations — diff of following vs. followers to surface non-followers
- Multithreading & concurrency — background `threading` worker keeps the GUI responsive
- GUI development — CustomTkinter dark-mode desktop interface
- Robust error handling — per-browser driver-failure dialogs and captcha/2FA-friendly login
- Automatic driver management — `webdriver-manager` for Firefox/Edge; Chrome 115+ self-manages
- Clipboard integration — one-click copy of results
- Application packaging — PyInstaller native build via `build.py`

## Tech Stack

- Python 3.10+ (`match`/`case`)
- Selenium WebDriver (Chrome, Firefox, Edge, Safari)
- CustomTkinter (dark-mode GUI)
- webdriver-manager (Firefox / Edge driver management)
- Chrome DevTools Protocol (stealth script injection)
- `threading` (responsive UI)
- PyInstaller (native app packaging)

## Getting Started

Requires Python 3.10+.

```bash
git clone https://github.com/TheYellowDuck/instagram-non-follower-finder
cd instagram-non-follower-finder
python3 build.py
```

The app is output to `dist/`. On macOS, right-click → Open the first time to bypass Gatekeeper.
