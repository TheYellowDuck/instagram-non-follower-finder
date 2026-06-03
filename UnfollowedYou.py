import os
import platform
import re
import subprocess
import threading
import time
import traceback
from tkinter import messagebox

import customtkinter as ctk
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

LOGIN_TIMEOUT = 300  # seconds to wait for manual login

# Extract usernames from inside the open dialog (arguments[0] = own username to exclude).
_JS_EXTRACT = """
const dialog = document.querySelector('div[role="dialog"]');
const root = dialog || document;
const own = arguments[0];
const seen = new Set();
const users = [];
for (const a of root.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/^\\/([A-Za-z0-9_.]{1,30})\\/?$/);
    if (m && m[1] !== own) {
        if (!seen.has(m[1])) { seen.add(m[1]); users.push(m[1]); }
    }
}
return users;
"""


def _find_scroller(driver):
    """Return the true scrollable ancestor of the followers list, found via computed style."""
    return driver.execute_script("""
        const dialog = document.querySelector('div[role="dialog"]');
        if (!dialog) return null;
        const link = dialog.querySelector('a[href]');
        if (!link) return null;
        let el = link.parentElement;
        while (el && el !== document.body) {
            const oy = window.getComputedStyle(el).overflowY;
            if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 1) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    """)


def _scroll_list(driver):
    """Scroll the followers list using a real wheel event so Instagram's loader triggers."""
    scroller = _find_scroller(driver)
    if not scroller:
        return
    try:
        # scroll_from_origin fires a genuine browser wheel event on the element,
        # which Instagram's IntersectionObserver / scroll listener picks up.
        ActionChains(driver).scroll_from_origin(
            ScrollOrigin.from_element(scroller), 0, 10_000).perform()
    except Exception:
        # Fallback: direct scrollTop mutation + synthetic event
        driver.execute_script("""
            arguments[0].scrollTop = arguments[0].scrollHeight;
            arguments[0].dispatchEvent(new Event('scroll', {bubbles: true}));
            const inner = arguments[0].firstElementChild;
            if (inner && inner.lastElementChild)
                inner.lastElementChild.scrollIntoView({block: 'end'});
        """, scroller)


_BROWSER_HELP = {
    'Chrome': (
        'ChromeDriver failed to start.\n\n'
        'Chrome 115+ manages its driver automatically.\n'
        'If this keeps failing, make sure Chrome is up to date,\n'
        'or install the driver manually: https://chromedriver.chromium.org'
    ),
    'Firefox': (
        'GeckoDriver (Firefox) failed to start.\n\n'
        'Install GeckoDriver and make sure it is on your PATH:\n'
        '  macOS:   brew install geckodriver\n'
        '  Windows: download from https://github.com/mozilla/geckodriver/releases\n'
        '  Linux:   sudo apt install firefox-geckodriver'
    ),
    'Edge': (
        'EdgeDriver failed to start.\n\n'
        'EdgeDriver must match your Edge version.\n'
        'Download from: https://developer.microsoft.com/microsoft-edge/tools/webdriver\n'
        'Then add it to your PATH.'
    ),
    'Safari': (
        'Safari WebDriver failed to start.\n\n'
        'To enable it:\n'
        '  1. Safari → Settings → Advanced → check "Show Develop menu"\n'
        '  2. Develop → Allow Remote Automation'
    ),
}


_STEALTH_SCRIPT = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
)


def _chrome_major_version() -> int | None:
    """Return the installed Chrome major version, or None if undetectable."""
    try:
        sys = platform.system()
        if sys == 'Darwin':
            out = subprocess.check_output(
                ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                 '--version'], text=True, stderr=subprocess.DEVNULL)
        elif sys == 'Windows':
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SOFTWARE\Google\Chrome\BLBeacon')
            ver, _ = winreg.QueryValueEx(key, 'version')
            return int(ver.split('.')[0])
        else:
            out = subprocess.check_output(
                ['google-chrome', '--version'], text=True,
                stderr=subprocess.DEVNULL)
        m = re.search(r'(\d+)\.', out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _create_driver(browser: str):
    if browser not in _BROWSER_HELP:
        raise ValueError(f'Unknown browser: {browser}')
    try:
        match browser:
            case 'Chrome':
                import undetected_chromedriver as uc
                return uc.Chrome(version_main=_chrome_major_version())
            case 'Firefox':
                from selenium.webdriver.firefox.service import Service
                from webdriver_manager.firefox import GeckoDriverManager
                opts = webdriver.FirefoxOptions()
                opts.set_preference('dom.webdriver.enabled', False)
                opts.set_preference('useAutomationExtension', False)
                driver = webdriver.Firefox(
                    service=Service(GeckoDriverManager().install()), options=opts)
                driver.execute_script(_STEALTH_SCRIPT)
                return driver
            case 'Edge':
                from selenium.webdriver.edge.service import Service
                from webdriver_manager.microsoft import EdgeChromiumDriverManager
                opts = webdriver.EdgeOptions()
                opts.add_argument('--disable-blink-features=AutomationControlled')
                opts.add_experimental_option('excludeSwitches', ['enable-automation'])
                opts.add_experimental_option('useAutomationExtension', False)
                driver = webdriver.Edge(
                    service=Service(EdgeChromiumDriverManager().install()), options=opts)
                driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                                       {'source': _STEALTH_SCRIPT})
                return driver
            case 'Safari':
                return webdriver.Safari()
    except Exception as e:
        raise RuntimeError(f'{_BROWSER_HELP[browser]}\n\nOriginal error: {e}') from e


# URL fragments that indicate Instagram hasn't finished the auth flow yet.
_STILL_AUTHING = (
    '/accounts/login',
    '/challenge/',
    '/two_factor',
    '/accounts/onetap/',
    '/accounts/suspended/',
    '/captcha/',
)


def _wait_for_login(driver, on_status=None):
    """Poll until login completes, updating the status label so the user
    knows what to do at each step (login form, captcha, 2FA, etc.)."""
    deadline = time.time() + LOGIN_TIMEOUT
    while time.time() < deadline:
        url = driver.current_url
        if 'instagram.com' not in url or url in ('data:,', 'about:blank', ''):
            time.sleep(0.5)
            continue
        if '/accounts/login' in url:
            if on_status:
                on_status('Enter your Instagram credentials — solve any captcha if prompted...', 'orange')
        elif any(p in url for p in _STILL_AUTHING):
            if on_status:
                on_status('Complete the verification in the browser...', 'orange')
        else:
            # URL looks good — confirm the session cookie is actually set.
            # Instagram can land on a non-auth URL before the cookie is written.
            if any(c['name'] == 'sessionid' for c in driver.get_cookies()):
                return
            if on_status:
                on_status('Completing login...', 'orange')
        time.sleep(0.5)
    raise TimeoutError('Login timed out — please try again.')


def _dismiss_dialogs(driver):
    for label in ('Save Info', 'Not Now', 'Not now'):
        try:
            WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f'//button[text()="{label}"]'))).click()
            time.sleep(1)
        except Exception:
            pass


def _js_click(driver, xpath: str):
    """Find element by xpath and click via JS — works on non-button elements like spans."""
    el = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, xpath)))
    driver.execute_script('arguments[0].click();', el)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('Instagram Non-Follower Finder')
        self.geometry('560x710')
        self.resizable(False, False)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            self, text='Instagram Non-Follower Finder',
            font=ctk.CTkFont(size=22, weight='bold'),
        ).grid(row=0, column=0, padx=30, pady=(28, 18), sticky='ew')

        # Settings card
        card = ctk.CTkFrame(self)
        card.grid(row=1, column=0, padx=30, pady=(0, 8), sticky='ew')
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text='Your Instagram username', anchor='w').grid(
            row=0, column=0, padx=20, pady=(14, 2), sticky='w')
        self.username_entry = ctk.CTkEntry(card, placeholder_text='your_username')
        self.username_entry.grid(row=1, column=0, padx=20, pady=(0, 10), sticky='ew')
        self.username_entry.insert(0, os.environ.get('INSTAGRAM_USERNAME', ''))

        ctk.CTkLabel(card, text='Browser', anchor='w').grid(
            row=2, column=0, padx=20, pady=(0, 2), sticky='w')
        self.browser_menu = ctk.CTkOptionMenu(
            card, values=['Chrome', 'Firefox', 'Edge', 'Safari'])
        self.browser_menu.grid(row=3, column=0, padx=20, pady=(0, 10), sticky='w')
        self.browser_menu.set('Chrome')

        ctk.CTkLabel(
            card,
            text='A browser will open — log in there, then the scan starts automatically.',
            text_color='gray', font=ctk.CTkFont(size=12), anchor='w', wraplength=460,
        ).grid(row=4, column=0, padx=20, pady=(0, 14), sticky='w')

        # Start button
        self.run_btn = ctk.CTkButton(
            self, text='Open Browser & Start',
            font=ctk.CTkFont(size=14, weight='bold'),
            height=44, command=self._start,
        )
        self.run_btn.grid(row=2, column=0, padx=30, pady=(0, 10), sticky='ew')

        # Status label — row 3
        self.status_lbl = ctk.CTkLabel(self, text='', text_color='gray', anchor='w')
        self.status_lbl.grid(row=3, column=0, padx=32, pady=(0, 2), sticky='ew')

        # Progress bar — row 4
        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(row=4, column=0, padx=30, pady=(0, 12), sticky='ew')
        self.progress.set(0)

        # Results panel — row 5
        panel = ctk.CTkFrame(self)
        panel.grid(row=5, column=0, padx=30, pady=(0, 10), sticky='nsew')
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        self.results_title = ctk.CTkLabel(
            panel, text='Results',
            font=ctk.CTkFont(size=14, weight='bold'), anchor='w')
        self.results_title.grid(row=0, column=0, padx=15, pady=(12, 4), sticky='w')

        self.results_box = ctk.CTkTextbox(panel, state='disabled')
        self.results_box.grid(row=1, column=0, padx=15, pady=(0, 14), sticky='nsew')

        # Copy button — row 6
        self.copy_btn = ctk.CTkButton(
            self, text='Copy to Clipboard',
            state='disabled', command=self._copy)
        self.copy_btn.grid(row=6, column=0, padx=30, pady=(0, 24), sticky='ew')

    # ── Thread-safe UI helpers ─────────────────────────────────────────────

    def _set_status(self, msg: str, color: str = 'gray'):
        self.after(0, lambda: self.status_lbl.configure(text=msg, text_color=color))

    def _set_progress(self, val: float):
        self.after(0, lambda: self.progress.set(val))

    def _set_title(self, text: str):
        self.after(0, lambda: self.results_title.configure(text=text))

    def _append(self, text: str):
        def _do():
            self.results_box.configure(state='normal')
            self.results_box.insert('end', text + '\n')
            self.results_box.configure(state='disabled')
            self.results_box.see('end')
        self.after(0, _do)

    def _clear(self):
        def _do():
            self.results_box.configure(state='normal')
            self.results_box.delete('1.0', 'end')
            self.results_box.configure(state='disabled')
        self.after(0, _do)

    def _copy(self):
        content = self.results_box.get('1.0', 'end').strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self._set_status('Copied to clipboard!', 'green')

    # ── Scan ──────────────────────────────────────────────────────────────

    def _start(self):
        username = self.username_entry.get().strip()
        if not username:
            messagebox.showerror('Missing username', 'Enter your Instagram username.')
            return
        browser = self.browser_menu.get()
        self.after(0, lambda: self.run_btn.configure(state='disabled'))
        self.after(0, lambda: self.copy_btn.configure(state='disabled'))
        self._clear()
        self._set_title('Results')
        self._set_progress(0)
        threading.Thread(target=self._scan, args=(username, browser), daemon=True).start()

    def _scan(self, username: str, browser: str):
        driver = None
        try:
            self._set_status(f'Opening {browser}...')
            driver = _create_driver(browser)
            driver.get('https://www.instagram.com/accounts/login')

            self._set_status('Enter your Instagram credentials in the browser...', 'orange')
            _wait_for_login(driver, on_status=self._set_status)
            _dismiss_dialogs(driver)

            self._set_progress(0.1)

            self._set_status('Loading profile...')
            driver.get(f'https://www.instagram.com/{username}/')
            # Wait for the followers link to appear
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//a[.//span[contains(text(),"followers")]]')))
            self._set_progress(0.15)

            self._set_status('Opening followers list...')
            _js_click(driver, '//a[.//span[contains(text(),"followers")]]')
            followers = self._load_list(driver, username, 'followers', 0.15, 0.5)

            # Navigate back to profile to close the dialog
            driver.get(f'https://www.instagram.com/{username}/')
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//a[.//span[contains(text(),"following")]]')))

            self._set_status('Opening following list...')
            _js_click(driver, '//a[.//span[contains(text(),"following")]]')
            following = self._load_list(driver, username, 'following', 0.5, 0.9)

            non_followers = [u for u in following if u not in set(followers)]

            self._set_progress(1.0)
            self._set_status(f'Done — {len(non_followers)} non-followers found.', 'green')
            self._set_title(f"Results  ·  {len(non_followers)} don't follow back")
            self._append(f'Followers:     {len(followers)}')
            self._append(f'Following:     {len(following)}')
            self._append(f'Non-followers: {len(non_followers)}\n')
            for u in non_followers:
                self._append(f'  {u}')
            self.after(0, lambda: self.copy_btn.configure(state='normal'))

        except Exception:
            err = traceback.format_exc()
            self._set_status('Error — see results box for details.', 'red')
            self._append('\n── Error ──────────────────────────')
            for line in err.strip().splitlines():
                self._append(line)
        finally:
            if driver:
                driver.quit()
            self.after(0, lambda: self.run_btn.configure(state='normal'))

    def _load_list(self, driver, own_username: str, label: str,
                   p_start: float, p_end: float) -> list[str]:
        # Wait for at least one user link inside the dialog before starting.
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, '//div[@role="dialog"]//a[@href]')))

        # Accumulate into a set so virtual-scroll removals don't lose already-seen users.
        all_users: set[str] = set()
        stalls = 0
        scroll_steps = 0

        while stalls < 3:
            # Scroll the true scrollable ancestor (found at runtime by computed style).
            _scroll_list(driver)

            # Poll every 0.2 s for up to 2 s for Instagram to load the next batch.
            # Break immediately when new users appear so we can scroll again right away.
            snapshot = len(all_users)
            deadline = time.time() + 2.0
            while time.time() < deadline:
                all_users.update(driver.execute_script(_JS_EXTRACT, own_username))
                if len(all_users) > snapshot:
                    break
                time.sleep(0.2)

            if len(all_users) > snapshot:
                stalls = 0
                scroll_steps += 1
            else:
                stalls += 1

            self._set_status(f'Loading {label}... ({len(all_users)} loaded)')
            frac = min(0.95, scroll_steps * 0.08 + stalls * 0.04)
            self._set_progress(p_start + (p_end - p_start) * frac)

        return list(all_users)


if __name__ == '__main__':
    App().mainloop()
