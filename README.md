# Instagram Non-Follower Finder

A desktop app that automates finding Instagram accounts you follow that don't follow you back.

Built with Python, Selenium WebDriver, and CustomTkinter. Uses browser automation to scroll and extract follower/following lists, with a clean dark-mode GUI and cross-browser support.

## Features

- Cross-browser — Chrome, Firefox, Edge, Safari
- Stealth mode — bypasses Instagram's bot detection on all browsers
- Manual login flow with full 2FA and captcha support
- Auto-downloads browser drivers (no PATH setup required)
- Accumulates users across virtual-scroll batches so no one is missed
- Results copyable to clipboard

## Install & Run

Requires Python 3.10+.

```bash
git clone https://github.com/TheYellowDuck/instagram-non-follower-finder
cd instagram-non-follower-finder
python3 build.py
```

The app is output to `dist/`. On macOS, right-click → Open the first time to bypass Gatekeeper.

## Tech Stack

- **Python** — Selenium WebDriver, CustomTkinter, threading
- **undetected-chromedriver** — stealth Chrome driver that bypasses bot detection
- **PyInstaller** — packaged into a native clickable app
- **webdriver-manager** — automatic driver management for Firefox & Edge
