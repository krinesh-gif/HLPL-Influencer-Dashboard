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
        root.title('Aravi Studio • Creator Outreach')
        root.geometry('1040x850')
        root.minsize(860, 640)
        root.configure(bg='#F5F3FA')
        root.option_add('*Font', ('Segoe UI', 10))
        canvas = tk.Canvas(root,bg='#F5F3FA',highlightthickness=0)
        scroll = ttk.Scrollbar(root,orient='vertical',command=canvas.yview)
        scroll.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        wrap = tk.Frame(canvas, bg='#F5F3FA', padx=28, pady=22)
        window = canvas.create_window((0,0),window=wrap,anchor='nw')
        wrap.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        header = tk.Frame(wrap, bg='#F5F3FA')
        header.pack(fill='x', pady=(0,18))
        tk.Label(header, text='aravi / studio', font=('Segoe UI',24,'bold'), fg='#211936', bg='#F5F3FA').pack(side='left')
        tk.Label(header, text=' CREATOR OUTREACH  /  BETA ', font=('Segoe UI',9,'bold'), fg='#5A36CD', bg='#EAE2FF', padx=12,pady=8).pack(side='right')
        hero = tk.Frame(wrap, bg='#6D43E5', padx=22,pady=16)
        hero.pack(fill='x', pady=(0,18))
        tk.Label(hero,text='Make the first hello count.',font=('Segoe UI',25,'bold'),fg='white',bg='#6D43E5').pack(anchor='w')
        tk.Label(hero,text='Your list. Your voice. One place to start creator conversations.',fg='#F0E9FF',bg='#6D43E5').pack(anchor='w',pady=(4,0))
        tk.Label(hero,text=' 01  CONNECT     /     02  CHECK A DRAFT     /     03  LAUNCH ',font=('Segoe UI',9,'bold'),fg='#D8FFA4',bg='#6D43E5').pack(anchor='w',pady=(12,0))
        card = tk.Frame(wrap,bg='white',padx=20,pady=16)
        card.pack(fill='x')
        tk.Label(card,text='Your sending account',font=('Segoe UI',11,'bold'),fg='#211936',bg='white').pack(anchor='w')
        tk.Label(card,text='Use the username of the account you will log into. Instagram language: English.',fg='#716A80',bg='white',font=('Segoe UI',9)).pack(anchor='w',pady=(2,6))
        self.sender = tk.Entry(card,bg='#F5F3FA',fg='#211936',relief='flat',font=('Segoe UI',11),insertbackground='#6D43E5')
        self.sender.pack(fill='x',ipady=7)
        columns = tk.Frame(wrap,bg='#F5F3FA')
        columns.pack(fill='x',pady=14)
        columns.columnconfigure(0,weight=1)
        columns.columnconfigure(1,weight=1)
        left = tk.Frame(columns,bg='white',padx=18,pady=16)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,7))
        right = tk.Frame(columns,bg='white',padx=18,pady=16)
        right.grid(row=0,column=1,sticky='nsew',padx=(7,0))
        tk.Label(left,text='01 / Creator list',font=('Segoe UI',13,'bold'),fg='#211936',bg='white').pack(anchor='w')
        tk.Label(left,text='One Instagram profile link per line • Up to 25 per batch',font=('Segoe UI',9),fg='#716A80',bg='white').pack(anchor='w',pady=(3,10))
        self.links = tk.Text(left,height=6,width=35,bg='#F5F3FA',fg='#211936',relief='flat',font=('Segoe UI',10),padx=10,pady=10,wrap='word',insertbackground='#6D43E5')
        self.links.pack(fill='x')
        self.button(left,'Import Excel / CSV',self.import_file,'#E7FFF3','#187A58').pack(anchor='w',pady=(10,0))
        tk.Label(right,text='02 / Your introduction',font=('Segoe UI',13,'bold'),fg='#211936',bg='white').pack(anchor='w')
        tk.Label(right,text='The exact message your creators will receive',font=('Segoe UI',9),fg='#716A80',bg='white').pack(anchor='w',pady=(3,10))
        self.message = tk.Text(right,height=6,width=35,bg='#F5F3FA',fg='#211936',relief='flat',font=('Segoe UI',11),padx=10,pady=10,wrap='word',insertbackground='#6D43E5')
        self.message.pack(fill='x')
        tk.Label(right,text='Start with one team-owned test profile.',fg='#9A5B35',bg='#FFF0E4',padx=10,pady=7,font=('Segoe UI',9)).pack(anchor='w',pady=(10,0))
        buttons = tk.Frame(wrap,bg='#F5F3FA')
        buttons.pack(fill='x',pady=(0,12))
        for label, action, bg, fg in [('Open login browser',self.login,'#EAE2FF','#5A36CD'),('Prepare one draft',lambda:self.run(True),'#EAE2FF','#5A36CD'),('Start batch',lambda:self.run(False),'#6D43E5','white'),('Stop',self.stop.set,'#FFE1E3','#B6374D'),('Export results',self.export,'#E7FFF3','#187A58')]:
            self.button(buttons,label,action,bg,fg).pack(side='left',padx=(0,8))
        activity = tk.Frame(wrap,bg='#211936',padx=18,pady=14)
        activity.pack(fill='both',expand=True)
        row = tk.Frame(activity,bg='#211936')
        row.pack(fill='x')
        tk.Label(row,text='Activity',font=('Segoe UI',12,'bold'),fg='white',bg='#211936').pack(side='left')
        self.status = tk.Label(row,text='READY',font=('Segoe UI',9,'bold'),fg='#D8FFA4',bg='#211936')
        self.status.pack(side='right')
        self.log = tk.Text(activity,height=6,state='disabled',bg='#211936',fg='#E4DEF4',relief='flat',font=('Segoe UI',10),wrap='word',pady=10)
        self.log.pack(fill='both',expand=True)
        tk.Label(wrap,text='Replies stay in Instagram. Results record send attempts, not delivery. Stop applies before the next send.\nAn in-progress send may complete. No account-safety guarantee; uncertain attempts are not retried automatically.',fg='#716A80',bg='#F5F3FA',font=('Segoe UI',9),justify='left').pack(anchor='w',pady=(10,0))
        threading.Thread(target=worker, args=(self.commands,self.events,self.stop), daemon=True).start()
        root.after(100, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def button(self, parent, label, action, bg, fg):
        return tk.Button(parent,text=label,command=action,bg=bg,fg=fg,
                         activebackground=bg,activeforeground=fg,relief='flat',
                         borderwidth=0,padx=14,pady=10,cursor='hand2',
                         font=('Segoe UI',10,'bold'))

    def poll(self):
        while not self.events.empty():
            text = self.events.get()
            if text == '__idle__':
                self.busy = False
                self.status.configure(text='READY',fg='#D8FFA4')
            else:
                self.log.configure(state='normal')
                self.log.insert('end', text + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
        self.root.after(100, self.poll)

    def login(self):
        if not self.busy:
            self.busy = True
            self.status.configure(text='CONNECTING',fg='#E4DEF4')
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
            self.status.configure(text='DRAFT CHECK' if draft else 'RUNNING',fg='#D8FFA4')
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
        App(probe)
        probe.update()
        assert probe.title() == 'Aravi Studio • Creator Outreach'
        assert probe.winfo_width() >= 860
        probe.destroy()
        with sync_playwright() as p:
            # Match the real login launch path, not the separate headless shell.
            import tempfile
            with tempfile.TemporaryDirectory() as profile_dir:
                browser = p.chromium.launch_persistent_context(profile_dir, headless=False)
                page = browser.new_page()
                page.set_content('<title>Aravi packaged browser test</title>')
                assert page.title() == 'Aravi packaged browser test'
                browser.close()
        sys.exit(0)
    root = tk.Tk()
    App(root)
    root.mainloop()
