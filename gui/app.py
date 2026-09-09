import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from cleaner import browser_paths, blocklist_manager, engine
from utils import config


class MisClearApp:
    def __init__(self, root):
        self.root = root
        root.title("Mis-Clear — Online Activity Trace Cleaner")
        root.geometry("760x620")
        root.minsize(700, 560)

        self.cfg = config.load_config()
        self._busy = False
        self._events = queue.Queue()

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.scan_tab = ttk.Frame(nb)
        self.settings_tab = ttk.Frame(nb)
        nb.add(self.scan_tab, text="Scan & Clean")
        nb.add(self.settings_tab, text="Settings")

        self._build_scan_tab()
        self._build_settings_tab()

        # Thread-safe: worker threads push to queue; main thread polls.
        self._poll_events()

    # ---------- Scan & Clean tab ----------
    def _build_scan_tab(self):
        top = ttk.Frame(self.scan_tab)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Label(top, text="Detected Browsers:").grid(row=0, column=0, sticky="w")
        self.browser_vars = {}
        self.detected = browser_paths.detect_browsers()
        col = 1
        for b in self.detected:
            var = tk.BooleanVar(value=b.key in self.cfg["selected_browsers"])
            self.browser_vars[b.key] = var
            ttk.Checkbutton(top, text=b.name, variable=var).grid(row=0, column=col, padx=4)
            col += 1

        if not self.detected:
            ttk.Label(top, text="(No browsers detected yet)", foreground="gray").grid(
                row=0, column=1
            )

        btns = ttk.Frame(self.scan_tab)
        btns.pack(fill="x", padx=8, pady=4)
        self.scan_btn = ttk.Button(btns, text="Scan", command=self.do_scan)
        self.scan_btn.pack(side="left", padx=4)
        self.clean_btn = ttk.Button(btns, text="Clean", command=self.do_clean)
        self.clean_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Refresh Browsers", command=self.refresh_browsers).pack(
            side="right", padx=4
        )

        self.tree = ttk.Treeview(
            self.scan_tab,
            columns=("browser", "history", "cookies", "autofill", "cache"),
            show="headings",
            height=16,
        )
        self.tree.heading("browser", text="Browser / Profile")
        self.tree.heading("history", text="History")
        self.tree.heading("cookies", text="Cookies")
        self.tree.heading("autofill", text="Autofill")
        self.tree.heading("cache", text="Cache (KB)")
        self.tree.column("browser", width=360)
        self.tree.column("history", width=70, anchor="center")
        self.tree.column("cookies", width=70, anchor="center")
        self.tree.column("autofill", width=70, anchor="center")
        self.tree.column("cache", width=90, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self.scan_tab, textvariable=self.status).pack(
            side="bottom", fill="x", padx=8, pady=4
        )

    def _selected_browsers(self):
        out = []
        for b in self.detected:
            var = self.browser_vars.get(b.key)
            if var is not None and var.get():
                out.append(b)
        return out

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.scan_btn.config(state=state)
        self.clean_btn.config(state=state)

    def refresh_browsers(self):
        self.detected = browser_paths.detect_browsers()
        self.status.set("Browsers refreshed.")
        messagebox.showinfo("Refresh", "Restart the app to rebuild the browser list.")

    def _populate(self, results):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in results:
            self.tree.insert(
                "",
                "end",
                values=(
                    f"{r['browser']} — {r['profile']}",
                    r["history"],
                    r["cookies"],
                    r["autofill"],
                    f"{r['cache_bytes'] / 1024:.0f}",
                ),
            )

    def do_scan(self):
        browsers = self._selected_browsers()
        if not browsers:
            messagebox.showwarning("No browsers", "Select at least one browser.")
            return
        self._set_busy(True)
        self.status.set("Scanning... (window stays responsive)")
        kwargs = {
            "keywords": self._keywords(),
            "blocklist": self._blocklist(),
            "browsers": browsers,
        }

        def worker():
            try:
                results = engine.scan_all(**kwargs)
                self._events.put(("scan_done", results, None))
            except Exception as e:  # noqa: BLE001
                self._events.put(("scan_done", [], e))

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self, results, error):
        if error:
            self.status.set(f"Scan failed: {error}")
            self._set_busy(False)
            messagebox.showerror("Scan error", str(error))
            return
        self._populate(results)
        self._set_busy(False)
        self.status.set(f"Scan complete: {len(results)} profile(s).")

    def do_clean(self):
        browsers = self._selected_browsers()
        if not browsers:
            messagebox.showwarning("No browsers", "Select at least one browser.")
            return

        from cleaner import processes

        running = processes.running_browsers(browsers)
        if running:
            names = ", ".join(b.name for b in running)
            messagebox.showwarning(
                "Close Browsers First",
                f"Please close these browsers before cleaning:\n\n{names}\n\n"
                "Cleaning while a browser is open may not work.\n"
                "Close them and click Clean again.",
            )
            return

        if not messagebox.askyesno(
            "Confirm Clean",
            "This will permanently delete matched history, cookies, autofill and cache. Continue?",
        ):
            return

        self._set_busy(True)
        self.status.set("Cleaning... (window stays responsive)")
        kwargs = {
            "keywords": self._keywords(),
            "blocklist": self._blocklist(),
            "browsers": browsers,
        }

        def worker():
            try:
                summary, totals = engine.clean_all(**kwargs)
                self._events.put(("clean_done", summary, totals))
            except Exception as e:  # noqa: BLE001
                self._events.put(("clean_done", [], None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self):
        try:
            while True:
                ev = self._events.get_nowait()
                kind = ev[0]
                if kind == "scan_done":
                    self._scan_done(ev[1], ev[2])
                elif kind == "clean_done":
                    self._clean_done(ev[1], ev[2], ev[3] if len(ev) > 3 else None)
                elif kind == "blocklist_done":
                    self._blocklist_done(ev[1], ev[2])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _clean_done(self, summary, totals, error):
        if error:
            self.status.set(f"Clean failed: {error}")
            self._set_busy(False)
            messagebox.showerror("Clean error", str(error))
            return
        self._populate(summary)
        self._set_busy(False)
        self.status.set(
            f"Cleaned: {totals['history']} history, {totals['cookies']} cookies, "
            f"{totals['autofill']} autofill, {totals['cache_bytes'] / 1024:.0f} KB cache."
        )

    def _keywords(self):
        raw = self.keywords_entry.get()
        return [k.strip().lower() for k in raw.replace(",", " ").split() if k.strip()] or list(self.cfg["keywords"])

    def _blocklist(self):
        return blocklist_manager.load_blocklist()

    # ---------- Settings tab ----------
    def _build_settings_tab(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self.settings_tab)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Custom keywords (space/comma separated):").grid(
            row=0, column=0, sticky="w"
        )
        self.keywords_entry = ttk.Entry(top, width=60)
        self.keywords_entry.grid(row=1, column=0, sticky="ew", pady=4)
        self.keywords_entry.insert(0, " ".join(self.cfg["keywords"]))
        top.columnconfigure(0, weight=1)

        ttk.Button(
            top,
            text="Save Defaults",
            command=self.save_defaults,
        ).grid(row=2, column=0, sticky="w", **pad)

        blk = ttk.LabelFrame(self.settings_tab, text="Blocklist (StevenBlack adult domains)")
        blk.pack(fill="x", **pad)

        self.blk_label = tk.StringVar(value="Not loaded yet.")
        ttk.Label(blk, textvariable=self.blk_label).pack(side="left", padx=8)
        ttk.Button(blk, text="Download Blocklist", command=self.download_blocklist).pack(
            side="left", padx=4
        )
        ttk.Button(blk, text="Load from File", command=self.load_blocklist).pack(side="left", padx=4)

        bl_state = ttk.LabelFrame(self.settings_tab, text="Blocklist status")
        bl_state.pack(fill="x", **pad)
        self.blk_status = tk.StringVar(value="Not checked.")
        ttk.Label(bl_state, textvariable=self.blk_status).pack(side="left", padx=8)

    def save_defaults(self):
        kw = [k.strip().lower() for k in self.keywords_entry.get().replace(",", " ").split() if k.strip()]
        self.cfg["keywords"] = kw or list(self.cfg["keywords"])
        browsers = [b.key for b in self.detected if self.browser_vars.get(b.key).get()]
        if browsers:
            self.cfg["selected_browsers"] = browsers
        config.save_config(self.cfg)
        self.status.set("Settings saved.")

    def download_blocklist(self):
        self.blk_label.set("Downloading...")
        self.root.update_idletasks()

        def worker():
            ok, info = blocklist_manager.download_blocklist()
            self._events.put(("blocklist_done", ok, info))

        threading.Thread(target=worker, daemon=True).start()

    def _blocklist_done(self, ok, info):
        if ok:
            self.blk_label.set(f"Blocklist loaded ({info} domains).")
            self.blk_status.set(f"blocks: {len(blocklist_manager.load_blocklist())} domains loaded.")
            self.status.set(f"Blocklist ready: {info} domains.")
        else:
            msg = str(info)
            self.blk_label.set(f"Download failed: {msg[:60]}")
            self.status.set("Blocklist download failed.")

    def load_blocklist(self):
        path = filedialog.askopenfilename(
            filetypes=[("Blocklist", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        domains = blocklist_manager.load_blocklist(path)
        self.blk_label.set(f"Loaded {len(domains)} domains from file.")
        self.blk_status.set(f"blocks: {len(domains)} domains loaded.")
        self.status.set(f"Blocklist loaded: {len(domains)} domains.")


def run():
    root = tk.Tk()
    MisClearApp(root)
    root.mainloop()