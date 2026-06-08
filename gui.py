import tkinter as tk
from tkinter import messagebox, scrolledtext
import json
import os
import sys
import subprocess
import threading
import queue

class ModernButton(tk.Label):
    """A custom flat-design button built on tk.Label for modern aesthetics on macOS."""
    def __init__(self, parent, text, command, bg="#007acc", fg="white", hover_bg="#005999", font=("Helvetica", 10, "bold"), **kwargs):
        super().__init__(parent, text=text, bg=bg, fg=fg, relief="flat", padx=15, pady=8, cursor="hand2", font=font, **kwargs)
        self.command = command
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.is_disabled = False
        
        self.bind("<Button-1>", lambda e: self.click())
        self.bind("<Enter>", lambda e: self.on_enter())
        self.bind("<Leave>", lambda e: self.on_leave())
        
    def click(self):
        if not self.is_disabled:
            self.command()
            
    def on_enter(self):
        if not self.is_disabled:
            self.config(bg=self.hover_bg)
            
    def on_leave(self):
        if not self.is_disabled:
            self.config(bg=self.default_bg)
            
    def disable(self):
        self.is_disabled = True
        self.config(bg="#3a3a3a", fg="#777777", cursor="arrow")
        
    def enable(self):
        self.is_disabled = False
        self.config(bg=self.default_bg, fg="white", cursor="hand2")

class TechWatchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tech Watch Assistant Dashboard")
        self.root.geometry("820x680")
        self.root.configure(bg="#121212")
        
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        self.last_run_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_run.json")
        self.install_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_and_install.sh")
        self.agent_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.py")
        
        self.log_queue = queue.Queue()
        self.active_thread = None
        
        self.load_config()
        self.build_ui()
        self.poll_logs()
        
    def load_config(self):
        """Loads configuration from config.json."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config.json: {e}")
                self.config = self.get_default_config()
        else:
            self.config = self.get_default_config()
            
    def get_default_config(self):
        return {
            "gemini_api_key": "",
            "discord_webhook_url": "",
            "docs_to_monitor": [
                {"name": "GitLab Releases", "feed_url": "https://about.gitlab.com/releases/categories/releases.xml"},
                {"name": "GitHub Changelog", "feed_url": "https://github.blog/changelog/feed/"}
            ],
            "keywords": ["Generative AI", "Agentic Workflow", "Platform Engineering"],
            "check_interval_hours": 6
        }
        
    def save_config(self):
        """Saves current GUI configuration back to config.json."""
        self.config["gemini_api_key"] = self.api_key_entry.get().strip()
        self.config["discord_webhook_url"] = self.webhook_entry.get().strip()
        
        kw_text = self.keywords_entry.get("1.0", tk.END).strip()
        self.config["keywords"] = [k.strip() for k in kw_text.split(",") if k.strip()]
        
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {e}")
            return False

    def build_ui(self):
        """Builds the main graphical interface using standard Tkinter (100% reliable on macOS)."""
        # Padding Frame
        container = tk.Frame(self.root, bg="#121212", padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = tk.Frame(container, bg="#121212")
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        title_label = tk.Label(header_frame, text="📊 Tech Watch Assistant", fg="#00e5ff", bg="#121212", font=("Helvetica", 18, "bold"))
        title_label.pack(side=tk.LEFT)
        
        subtitle_label = tk.Label(header_frame, text="  (Competitor & Trend Scanning Agent)", fg="#888888", bg="#121212", font=("Helvetica", 11, "italic"))
        subtitle_label.pack(side=tk.LEFT, fill=tk.Y, pady=6)
        
        # Section: Config
        config_frame = tk.LabelFrame(container, text=" Configuration Settings ", bg="#1a1a1a", fg="#00e5ff", font=("Helvetica", 11, "bold"), bd=1, relief="solid", padx=15, pady=10)
        config_frame.pack(fill=tk.X, pady=5)
        
        # API Key
        tk.Label(config_frame, text="Gemini API Key:", fg="#e0e0e0", bg="#1a1a1a", font=("Helvetica", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        api_border = tk.Frame(config_frame, bg="#333333", bd=1)
        api_border.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        self.api_key_entry = tk.Entry(api_border, bg="#121212", fg="#ffffff", insertbackground="white", relief="flat", width=60, font=("Helvetica", 10))
        self.api_key_entry.pack(fill=tk.X, padx=5, pady=3)
        self.api_key_entry.insert(0, self.config.get("gemini_api_key", ""))
        
        # Webhook
        tk.Label(config_frame, text="Discord Webhook:", fg="#e0e0e0", bg="#1a1a1a", font=("Helvetica", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        webhook_border = tk.Frame(config_frame, bg="#333333", bd=1)
        webhook_border.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        self.webhook_entry = tk.Entry(webhook_border, bg="#121212", fg="#ffffff", insertbackground="white", relief="flat", width=60, font=("Helvetica", 10))
        self.webhook_entry.pack(fill=tk.X, padx=5, pady=3)
        self.webhook_entry.insert(0, self.config.get("discord_webhook_url", ""))
        
        config_frame.columnconfigure(1, weight=1)
        
        # Section: Keywords & Competitors (Side-by-side)
        split_frame = tk.Frame(container, bg="#121212")
        split_frame.pack(fill=tk.BOTH, expand=False, pady=5)
        
        # Keywords (Left)
        kw_frame = tk.LabelFrame(split_frame, text=" Search Keywords (Comma separated) ", bg="#1a1a1a", fg="#00e5ff", font=("Helvetica", 11, "bold"), bd=1, relief="solid", padx=10, pady=10)
        kw_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.keywords_entry = scrolledtext.ScrolledText(kw_frame, height=5, bg="#121212", fg="#ffffff", insertbackground="white", borderwidth=0, font=("Helvetica", 10))
        self.keywords_entry.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.keywords_entry.insert(tk.END, ", ".join(self.config.get("keywords", [])))
        
        # Competitors (Right)
        comp_frame = tk.LabelFrame(split_frame, text=" Competitors / References to Monitor ", bg="#1a1a1a", fg="#00e5ff", font=("Helvetica", 11, "bold"), bd=1, relief="solid", padx=10, pady=10)
        comp_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        list_container = tk.Frame(comp_frame, bg="#1a1a1a")
        list_container.pack(fill=tk.BOTH, expand=True)
        
        self.comp_listbox = tk.Listbox(list_container, height=5, bg="#121212", fg="#ffffff", selectbackground="#007acc", selectforeground="white", borderwidth=0, highlightthickness=0, font=("Helvetica", 10))
        self.comp_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        comp_scroll = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.comp_listbox.yview)
        comp_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        self.comp_listbox.config(yscrollcommand=comp_scroll.set)
        
        self.refresh_competitor_list()
        
        # Competitor buttons
        comp_buttons_frame = tk.Frame(comp_frame, bg="#1a1a1a")
        comp_buttons_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.add_btn = ModernButton(comp_buttons_frame, text="+ Add Feed", command=self.add_competitor, bg="#2a2a2a", hover_bg="#3d3d3d")
        self.add_btn.pack(side=tk.LEFT, padx=2)
        
        self.remove_btn = ModernButton(comp_buttons_frame, text="- Remove", command=self.remove_competitor, bg="#2a2a2a", hover_bg="#3d3d3d")
        self.remove_btn.pack(side=tk.LEFT, padx=2)
        
        # Action Buttons
        actions_frame = tk.Frame(container, bg="#121212")
        actions_frame.pack(fill=tk.X, pady=10)
        
        self.scan_btn = ModernButton(actions_frame, text="▶️ Run Monitoring Scan", command=self.trigger_scan, bg="#007acc", hover_bg="#005999")
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.report_btn = ModernButton(actions_frame, text="📊 Generate Strategy Report", command=self.trigger_report, bg="#9b59b6", hover_bg="#8e44ad")
        self.report_btn.pack(side=tk.LEFT, padx=5)
        
        self.save_btn = ModernButton(actions_frame, text="💾 Save Config", command=self.action_save, bg="#2a2a2a", hover_bg="#3d3d3d")
        self.save_btn.pack(side=tk.RIGHT, padx=5)
        
        # Logs Section
        logs_frame = tk.LabelFrame(container, text=" Scan Execution Logs ", bg="#1a1a1a", fg="#00e5ff", font=("Helvetica", 11, "bold"), bd=1, relief="solid", padx=10, pady=10)
        logs_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.status_label = tk.Label(logs_frame, text="Status: Idle", fg="#aaaaaa", bg="#1a1a1a", font=("Helvetica", 10))
        self.status_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, bg="#0d0d0d", fg="#00ff66", insertbackground="white", borderwidth=0, font=("Menlo", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Diagnostic prints to debug Rosetta translation state
        import platform
        self.log_text.insert(tk.END, f"System Platform: {platform.platform()}\n")
        self.log_text.insert(tk.END, f"Python Executable: {sys.executable}\n")
        self.log_text.insert(tk.END, f"Python Machine Arch: {platform.machine()}\n")
        self.log_text.insert(tk.END, "Tech Watch Dashboard initialized.\nReady to monitor competitor & trend data.\n\n")
        
        # Auto-run buttons (Bottom)
        autorun_frame = tk.Frame(container, bg="#121212")
        autorun_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.enable_autorun_btn = ModernButton(autorun_frame, text="✔️ Enable Auto-Run on Boot", command=self.enable_autorun, bg="#2a2a2a", hover_bg="#3d3d3d")
        self.enable_autorun_btn.pack(side=tk.LEFT, padx=5)
        
        self.disable_autorun_btn = ModernButton(autorun_frame, text="❌ Disable Auto-Run", command=self.disable_autorun, bg="#2a2a2a", hover_bg="#3d3d3d")
        self.disable_autorun_btn.pack(side=tk.LEFT, padx=5)

    def refresh_competitor_list(self):
        """Refreshes the competitor Listbox."""
        self.comp_listbox.delete(0, tk.END)
        for doc in self.config.get("docs_to_monitor", []):
            self.comp_listbox.insert(tk.END, f"{doc['name']} - {doc['feed_url']}")
            
    def add_competitor(self):
        """Opens dialog to add competitor documentation feed."""
        add_win = tk.Toplevel(self.root)
        add_win.title("Add Feed")
        add_win.geometry("420x200")
        add_win.configure(bg="#1a1a1a")
        add_win.transient(self.root)
        add_win.grab_set()
        
        tk.Label(add_win, text="Competitor Name:", fg="#e0e0e0", bg="#1a1a1a", font=("Helvetica", 10)).pack(anchor=tk.W, padx=20, pady=(15, 2))
        name_border = tk.Frame(add_win, bg="#333333", bd=1)
        name_border.pack(padx=20, pady=2, fill=tk.X)
        name_entry = tk.Entry(name_border, bg="#121212", fg="#ffffff", insertbackground="white", relief="flat", font=("Helvetica", 10))
        name_entry.pack(fill=tk.X, padx=5, pady=3)
        
        tk.Label(add_win, text="RSS Feed URL:", fg="#e0e0e0", bg="#1a1a1a", font=("Helvetica", 10)).pack(anchor=tk.W, padx=20, pady=(10, 2))
        url_border = tk.Frame(add_win, bg="#333333", bd=1)
        url_border.pack(padx=20, pady=2, fill=tk.X)
        url_entry = tk.Entry(url_border, bg="#121212", fg="#ffffff", insertbackground="white", relief="flat", font=("Helvetica", 10))
        url_entry.pack(fill=tk.X, padx=5, pady=3)
        
        def save_feed():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            if not name or not url:
                messagebox.showerror("Error", "Both fields are required.", parent=add_win)
                return
            self.config["docs_to_monitor"].append({"name": name, "feed_url": url})
            self.refresh_competitor_list()
            add_win.destroy()
            
        btn_frame = tk.Frame(add_win, bg="#1a1a1a")
        btn_frame.pack(pady=15)
        ModernButton(btn_frame, text="Add Feed", command=save_feed, bg="#007acc", hover_bg="#005999").pack()
        
    def remove_competitor(self):
        """Removes the selected competitor documentation feed."""
        selected = self.comp_listbox.curselection()
        if not selected:
            messagebox.showwarning("Warning", "Select a feed to remove.")
            return
        idx = selected[0]
        del self.config["docs_to_monitor"][idx]
        self.refresh_competitor_list()
        
    def action_save(self):
        """Saves config and alerts user."""
        if self.save_config():
            messagebox.showinfo("Success", "Configuration saved successfully!")
            
    def enable_autorun(self):
        """Registers launchd background plist service."""
        if not self.save_config():
            return
            
        self.log_text.insert(tk.END, "\nEnabling Auto-Run on boot (Registering macOS LaunchAgent)...\n")
        self.run_background_command(["bash", self.install_script_path], "Registering LaunchAgent...")
        
    def disable_autorun(self):
        """Unloads macOS launchd daemon."""
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.user.techwatchassistant.plist")
        
        if os.path.exists(plist_path):
            self.log_text.insert(tk.END, "\nDisabling Auto-Run (Removing macOS LaunchAgent)...\n")
            try:
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                os.remove(plist_path)
                self.log_text.insert(tk.END, "Successfully disabled Auto-Run and removed LaunchAgent plist.\n")
                messagebox.showinfo("Success", "Auto-Run has been disabled.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to disable Auto-Run: {e}")
        else:
            messagebox.showinfo("Info", "Auto-Run daemon is not installed.")

    def trigger_scan(self):
        """Runs the monitoring agent, or stops it if already running."""
        if self.active_thread and self.active_thread.is_alive():
            if getattr(self, "current_action", None) == "scan":
                if messagebox.askyesno("Confirm Stop", "Do you want to stop the running scan?"):
                    self.log_text.insert(tk.END, "\n🛑 Stopping scan process...\n")
                    self.active_thread.terminate_process()
            return
            
        if not self.save_config():
            return
        self.log_text.delete("1.0", tk.END)
        
        # Output debug diagnostics to log text area right before running
        import platform
        self.log_text.insert(tk.END, f"[Debug] System Platform: {platform.platform()}\n")
        self.log_text.insert(tk.END, f"[Debug] Python Executable: {sys.executable}\n")
        self.log_text.insert(tk.END, f"[Debug] Python Machine Arch: {platform.machine()}\n")
        self.log_text.insert(tk.END, f"[Debug] Platform Processor: {platform.processor()}\n")
        
        self.log_text.insert(tk.END, "Starting monitoring scan for competitor updates and keywords...\n")
        
        # Execute the agent script with -u to force unbuffered stdout (real-time logs in GUI)
        python_bin = sys_python_bin()
        self.current_action = "scan"
        self.run_background_command([python_bin, "-u", self.agent_path], "Running Scan...")
        
    def trigger_report(self):
        """Generates strategic report immediately, or stops it if already running."""
        if self.active_thread and self.active_thread.is_alive():
            if getattr(self, "current_action", None) == "report":
                if messagebox.askyesno("Confirm Stop", "Do you want to stop report generation?"):
                    self.log_text.insert(tk.END, "\n🛑 Stopping report generation...\n")
                    self.active_thread.terminate_process()
            return
            
        if not self.save_config():
            return
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "Triggering immediate Strategic Report compilation...\n")
        
        # Execute the agent script with -u to force unbuffered stdout (real-time logs in GUI)
        python_bin = sys_python_bin()
        self.current_action = "report"
        self.run_background_command([python_bin, "-u", self.agent_path, "--report-only"], "Compiling Report...")

    def run_background_command(self, cmd_args, status_text):
        """Spawns thread to execute background process and pipes stdout to log queue."""
        if self.active_thread and self.active_thread.is_alive():
            messagebox.showwarning("Warning", "An agent process is already running.")
            return
            
        # Safeguard: Force arm64 native execution on Apple Silicon to prevent Rosetta architecture clashes
        import platform
        cmd = cmd_args.copy()
        is_arm64_hw = False
        
        # Try absolute path for sysctl to prevent PATH resolution issues in Finder
        sysctl_paths = ["/usr/sbin/sysctl", "sysctl"]
        for sysctl_path in sysctl_paths:
            try:
                res = subprocess.run([sysctl_path, "-n", "hw.optional.arm64"], capture_output=True, text=True)
                if res.stdout.strip() == "1":
                    is_arm64_hw = True
                    break
            except Exception:
                pass
            
        if is_arm64_hw or platform.machine() == "arm64" or (hasattr(os, "uname") and os.uname().machine == "arm64"):
            if cmd[0] != "arch" and cmd[0] != "/usr/bin/arch":
                # Use absolute path for arch to prevent PATH resolution issues in Finder
                arch_path = "/usr/bin/arch" if os.path.exists("/usr/bin/arch") else "arch"
                cmd = [arch_path, "-arm64"] + cmd
            
        # UI Toggles: Set the active button to a red Cancel button
        if self.current_action == "scan":
            self.scan_btn.config(text="🛑 Stop Running Scan", bg="#e74c3c", fg="white")
            self.scan_btn.default_bg = "#e74c3c"
            self.scan_btn.hover_bg = "#c0392b"
            self.report_btn.disable()
        elif self.current_action == "report":
            self.report_btn.config(text="🛑 Stop Report Gen", bg="#e74c3c", fg="white")
            self.report_btn.default_bg = "#e74c3c"
            self.report_btn.hover_bg = "#c0392b"
            self.scan_btn.disable()
            
        self.enable_autorun_btn.disable()
        self.disable_autorun_btn.disable()
        self.status_label.config(text=f"Status: {status_text}", fg="#00e5ff")
        
        self.active_thread = ProcessThread(cmd, self.log_queue)
        self.active_thread.start()
        
    def poll_logs(self):
        """Polls log_queue and writes lines to log box."""
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line == "===FINISHED===":
                    self.status_label.config(text="Status: Idle", fg="#aaaaaa")
                    
                    # Reset scan button
                    self.scan_btn.config(text="▶️ Run Monitoring Scan", bg="#007acc", fg="white")
                    self.scan_btn.default_bg = "#007acc"
                    self.scan_btn.hover_bg = "#005999"
                    self.scan_btn.enable()
                    
                    # Reset report button
                    self.report_btn.config(text="📊 Generate Strategy Report", bg="#9b59b6", fg="white")
                    self.report_btn.default_bg = "#9b59b6"
                    self.report_btn.hover_bg = "#8e44ad"
                    self.report_btn.enable()
                    
                    self.enable_autorun_btn.enable()
                    self.disable_autorun_btn.enable()
                    self.current_action = None
                    break
                else:
                    self.log_text.insert(tk.END, line)
                    self.log_text.see(tk.END)
        except queue.Empty:
            pass
            
        # Poll again in 100ms
        self.root.after(100, self.poll_logs)

class ProcessThread(threading.Thread):
    def __init__(self, cmd, log_queue):
        super().__init__()
        self.cmd = cmd
        self.log_queue = log_queue
        self.process = None
        
    def run(self):
        try:
            env = os.environ.copy()
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            for line in self.process.stdout:
                self.log_queue.put(line)
            self.process.wait()
        except Exception as e:
            self.log_queue.put(f"ERROR executing process: {e}\n")
        finally:
            self.log_queue.put("===FINISHED===")
            
    def terminate_process(self):
        """Kills the active subprocess."""
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass

def sys_python_bin():
    """Locates python3 path, defaulting to the absolute python3 installation."""
    target_path = "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
    if os.path.exists(target_path):
        return target_path
    return sys.executable

if __name__ == "__main__":
    root = tk.Tk()
    app = TechWatchApp(root)
    root.mainloop()
