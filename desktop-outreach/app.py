"""Local desktop prototype. English Instagram UI required. No live sends tested."""
import queue
import re
import threading
import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core import Ledger, username, load_profiles

DATA = Path.home() / 'AraviOutreachData'
DATA.mkdir(exist_ok=True)
if getattr(sys, 'frozen', False):
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '0'

def blocked(page):
    if any(x in page.url for x in ['/accounts/login', '/challenge/', '/checkpoint/']):
        raise RuntimeError('Login or security challenge. Batch stopped; resolve manually.')
    body = page.locator('body').inner_text().lower()
    for text in ['try again later', 'we restrict certain activity', 'temporarily blocked', 'your account has been suspended', "couldn't send", 'failed to send']:
        if text in body:
            raise RuntimeError('Instagram restriction or send error. Batch stopped.')

def visible_one(locator, label):
    matches = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    if len(matches) != 1:
        raise RuntimeError(f'Cannot identify {label} uniquely. Inspect the browser manually.')
    return matches[0]

def worker(commands, events, stop):
    ledger = Ledger(DATA / 'outreach.sqlite3')
    context = None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            while True:
                command = commands.get()
                if command[0] == 'quit':
                    break
                try:
                    if command[0] == 'login':
                        if context is None:
                            context = p.chromium.launch_persistent_context(str(DATA / 'browser'), headless=False)
                        page = context.pages[0] if context.pages else context.new_page()
                        page.goto('https://www.instagram.com/', wait_until='domcontentloaded')
                        events.put('Log in yourself. Set Instagram language to English. Then return to this app.')
                    elif command[0] == 'run':
                        if context is None:
                            raise RuntimeError('Open the login browser first.')
                        _, sender, recipients, message, draft = command
                        stop.clear()
                        page = context.pages[0] if context.pages else context.new_page()
                        for recipient in recipients:
                            if stop.is_set():
                                break
                            if ledger.status(sender, recipient):
                                events.put(f'@{recipient}: skipped (already recorded; review ledger).')
                                continue
                            page.goto(f'https://www.instagram.com/{recipient}/', wait_until='domcontentloaded')
                            page.wait_for_timeout(2000)
                            blocked(page)
                            # Fail closed if logged-in account identity cannot be established.
                            switch = page.get_by_role('link', name='Profile', exact=True)
                            profile = visible_one(switch, 'logged-in profile link')
                            href = profile.get_attribute('href')
                            if not href or username('https://www.instagram.com' + href if href.startswith('/') else href) != sender:
                                raise RuntimeError('Logged-in account does not match Sender username.')
                            button = page.get_by_role('button', name='Message', exact=True)
                            visible_one(button, 'Message button').click()
                            box = page.locator('textarea[placeholder*="Message"], [contenteditable="true"][role="textbox"]')
                            box.first.wait_for(state='visible', timeout=15000)
                            blocked(page)
                            composer = visible_one(box, 'message composer')
                            # Verify conversation header before entering or sending a message.
                            if not page.url.startswith('https://www.instagram.com/direct/'):
                                raise RuntimeError('Conversation URL could not be verified.')
                            header = page.locator(f'a[href="/{recipient}/"]')
                            if not any(header.nth(i).is_visible() for i in range(header.count())):
                                raise RuntimeError('Recipient could not be verified in conversation header.')
                            if draft:
                                composer.fill(message)
                                events.put(f'@{recipient}: draft prepared; NOTHING sent. Clear it manually after reviewing.')
                                break
                            composer.fill(message)
                            if stop.is_set():
                                break
                            # Persist before the send attempt. Crash/error => never auto retry.
                            ledger.record(sender, recipient, 'uncertain', message)
                            composer.press('Enter')
                            page.wait_for_timeout(2500)
                            blocked(page)
                            # UI evidence is not a delivery receipt. Manual review remains necessary.
                            ledger.record(sender, recipient, 'send_attempted_review', message)
                            events.put(f'@{recipient}: send attempted; delivery not independently confirmed.')
                            if stop.wait(30):
                                break
                        events.put('Batch finished or stopped. Replies are handled manually in Instagram.')
                except Exception as e:
                    events.put(f'STOPPED: {e}')
                finally:
                    events.put('__idle__')
            if context:
                context.close()
    except Exception as e:
        events.put(f'Setup error: {e}. Install requirements and Playwright Chromium.')
        events.put('__idle__')
    finally:
        ledger.close()

class App:
    def __init__(self, root):
        self.root = root
        self.commands, self.events, self.stop = queue.Queue(), queue.Queue(), threading.Event()
        self.busy = False
        root.title('Aravi • Instagram First Outreach — Prototype')
        root.geometry('850x760')
        wrap = ttk.Frame(root, padding=20)
        wrap.pack(fill='both', expand=True)
        ttk.Label(wrap, text='Instagram First Outreach', font=('Arial', 22, 'bold')).pack(anchor='w')
        ttk.Label(wrap, text='Local browser • One first message • Manual replies • English Instagram UI').pack(anchor='w', pady=8)
        ttk.Label(wrap, text='Sender Instagram username (must match the logged-in account)').pack(anchor='w')
        self.sender = ttk.Entry(wrap)
        self.sender.pack(fill='x', pady=4)
        ttk.Label(wrap, text='Profile links — one per line, maximum 25 per batch').pack(anchor='w')
        self.links = tk.Text(wrap, height=7)
        self.links.pack(fill='x', pady=4)
        ttk.Button(wrap, text='Import Excel / CSV', command=self.import_file).pack(anchor='w')
        ttk.Label(wrap, text='Your exact introduction message').pack(anchor='w', pady=(10,0))
        self.message = tk.Text(wrap, height=5)
        self.message.pack(fill='x', pady=4)
        buttons = ttk.Frame(wrap)
        buttons.pack(fill='x', pady=10)
        for label, action in [('1. Open login browser', self.login), ('2. Prepare one draft', lambda:self.run(True)), ('3. Start batch', lambda:self.run(False)), ('Stop', self.stop.set), ('Export results', self.export)]:
            ttk.Button(buttons, text=label, command=action).pack(side='left', padx=3)
        ttk.Label(wrap, text='Stop takes effect before the next send; an in-progress send may complete.\nNo account-safety guarantee. Unknown outcomes are never automatically retried.').pack(anchor='w')
        self.log = tk.Text(wrap, height=12, state='disabled')
        self.log.pack(fill='both', expand=True, pady=10)
        threading.Thread(target=worker, args=(self.commands,self.events,self.stop), daemon=True).start()
        root.after(100, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def poll(self):
        while not self.events.empty():
            text = self.events.get()
            if text == '__idle__':
                self.busy = False
            else:
                self.log.configure(state='normal')
                self.log.insert('end', text + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
        self.root.after(100, self.poll)

    def login(self):
        if not self.busy:
            self.busy = True
            self.commands.put(('login',))

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[('Excel / CSV', '*.xlsx *.csv')])
        if path:
            try:
                profiles, invalid = load_profiles(path)
                self.links.delete('1.0','end')
                self.links.insert('1.0', '\n'.join('https://www.instagram.com/'+u+'/' for u in profiles))
                messagebox.showinfo('Imported', f'{len(profiles)} unique profiles; {len(invalid)} invalid URLs. Review before sending.')
            except Exception as e:
                messagebox.showerror('Import failed', str(e))

    def run(self, draft):
        if self.busy:
            return
        try:
            sender = username(self.sender.get())
            profiles = list(dict.fromkeys(username(x) for x in self.links.get('1.0','end').splitlines() if x.strip()))
            message = self.message.get('1.0','end').strip()
            if not profiles or len(profiles)>25 or not message or len(message)>1000:
                raise ValueError('Provide 1–25 valid profiles and a message of 1–1000 characters.')
            if not draft and not messagebox.askyesno('Review batch before sending', f'Sender: @{sender}\nRecipients ({len(profiles)}):\n'+', '.join('@'+u for u in profiles)+'\n\nExact message:\n'+message+'\n\nAttempt these first DMs now?'):
                return
            self.busy = True
            self.commands.put(('run',sender,profiles,message,draft))
        except ValueError as e:
            messagebox.showerror('Check input', str(e))

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='Aravi_Outreach_Results.csv')
        if path:
            ledger = Ledger(DATA / 'outreach.sqlite3')
            try:
                ledger.export(path)
            finally:
                ledger.close()

    def close(self):
        self.stop.set()
        self.commands.put(('quit',))
        self.root.destroy()

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        from playwright.sync_api import sync_playwright
        import openpyxl
        probe = tk.Tk()
        probe.withdraw()
        probe.update()
        probe.destroy()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content('<title>Aravi packaged browser test</title>')
            assert page.title() == 'Aravi packaged browser test'
            browser.close()
        sys.exit(0)
    root = tk.Tk()
    App(root)
    root.mainloop()
