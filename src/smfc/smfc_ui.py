#!/usr/bin/env python3
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from configparser import ConfigParser

from .ipmi import Ipmi
from .log import Log


class FanControlUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SMFC Fan Control UI")
        self.root.geometry("650x550")

        # Initialize Backend
        try:
            self.ipmi = self.init_ipmi()
            self.status_msg = "IPMI Initialized Successfully"
        except Exception as e:
            self.ipmi = None
            self.status_msg = f"Error initializing IPMI: {str(e)}\n(Make sure you run with sudo)"

        # Style
        style = ttk.Style()
        style.configure("TLabel", font=("Helvetica", 11))
        style.configure("TButton", font=("Helvetica", 11))

        # --- Status Section ---
        self.status_var = tk.StringVar(value=self.status_msg)
        status_label = ttk.Label(root, textvariable=self.status_var, wraplength=600, foreground="red" if self.ipmi is None else "black")
        status_label.pack(pady=10)

        if self.ipmi is None:
            return

        # --- Fan Mode Section ---
        mode_frame = ttk.LabelFrame(root, text="Fan Mode", padding=(10, 10))
        mode_frame.pack(fill="x", padx=10, pady=5)

        self.modes = [
            ("Standard", Ipmi.STANDARD_MODE),
            ("Full", Ipmi.FULL_MODE),
            ("Optimal", Ipmi.OPTIMAL_MODE),
            ("PUE", Ipmi.PUE_MODE),
            ("Heavy IO", Ipmi.HEAVY_IO_MODE)
        ]

        self.mode_var = tk.IntVar(value=Ipmi.STANDARD_MODE)

        # Grid for mode buttons
        for i, (name, val) in enumerate(self.modes):
            rb = ttk.Radiobutton(mode_frame, text=name, variable=self.mode_var, value=val, command=self.set_mode)
            rb.grid(row=0, column=i, padx=5, sticky="w")

        # --- Fan Level Section ---
        level_frame = ttk.LabelFrame(root, text="Fan Levels (%)", padding=(10, 10))
        level_frame.pack(fill="x", padx=10, pady=10)

        # CPU Zone
        level_frame.columnconfigure(1, weight=1)

        ttk.Label(level_frame, text="CPU Zone (0):").grid(row=0, column=0, sticky="w")
        self.cpu_scale_var = tk.IntVar(value=50)
        self.cpu_scale = ttk.Scale(level_frame, from_=0, to=100, orient="horizontal", length=200, variable=self.cpu_scale_var)
        self.cpu_scale.grid(row=0, column=1, padx=10, sticky="ew")
        self.cpu_label = ttk.Label(level_frame, textvariable=self.cpu_scale_var, width=4)
        self.cpu_label.grid(row=0, column=2)

        self.btn_set_cpu = ttk.Button(level_frame, text="Set CPU", command=self.set_cpu_level)
        self.btn_set_cpu.grid(row=0, column=3, padx=5)

        # HD Zone
        ttk.Label(level_frame, text="HD Zone (1):").grid(row=1, column=0, sticky="w", pady=10)
        self.hd_scale_var = tk.IntVar(value=50)
        self.hd_scale = ttk.Scale(level_frame, from_=0, to=100, orient="horizontal", length=200, variable=self.hd_scale_var)
        self.hd_scale.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.hd_label = ttk.Label(level_frame, textvariable=self.hd_scale_var, width=4)
        self.hd_label.grid(row=1, column=2, pady=10)

        self.btn_set_hd = ttk.Button(level_frame, text="Set HD", command=self.set_hd_level)
        self.btn_set_hd.grid(row=1, column=3, padx=5, pady=10)

        # --- Temperature Section ---
        temp_frame = ttk.LabelFrame(root, text="System Temperatures (Live)", padding=(10, 10))
        temp_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.temp_text = tk.Text(temp_frame, height=8, width=40, state='disabled', bg="#f0f0f0", font=("Consolas", 10))
        self.temp_text.pack(fill="both", expand=True)

        # --- Refresh Button ---
        self.btn_refresh = ttk.Button(root, text="Refresh Current State", command=self.refresh_state)
        self.btn_refresh.pack(pady=10)

        # Initial Refresh
        self.root.after(100, self.refresh_state)
        # Start Temperature Auto-Refresh
        self.root.after(1000, self.auto_refresh_temps)

    def init_ipmi(self):
        # Create minimal dependencies for Ipmi class
        log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        config = ConfigParser()
        config.add_section(Ipmi.CS_IPMI)

        # Use existing Ipmi class with sudo=True
        # This allows the UI to run as regular user, while ipmitool runs with sudo
        print("Initializing IPMI interface... (Check terminal if sudo password is requested)")
        return Ipmi(log, config, sudo=True)

    def _run_async(self, target_func, *args):
        """Helper to run a function in a separate thread."""
        threading.Thread(target=target_func, args=args, daemon=True).start()

    def set_mode(self):
        mode = self.mode_var.get()
        self.status_var.set(f"Setting mode to {self.ipmi.get_fan_mode_name(mode)}...")
        self._run_async(self._set_mode_thread, mode)

    def _set_mode_thread(self, mode):
        try:
            self.ipmi.set_fan_mode(mode)
            msg = f"Mode set to: {self.ipmi.get_fan_mode_name(mode)}"
            self.root.after(0, lambda: self.status_var.set(msg))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, lambda: self.status_var.set("Error setting mode"))

    def set_cpu_level(self):
        level = self.cpu_scale_var.get()
        self.status_var.set(f"Setting CPU Zone to {level}%...")
        self.btn_set_cpu.state(['disabled'])
        self._run_async(self._set_cpu_level_thread, level)

    def _set_cpu_level_thread(self, level):
        try:
            self.ipmi.set_fan_level(Ipmi.CPU_ZONE, level)
            self.root.after(0, lambda: self.status_var.set(f"CPU Zone Level set to {level}%"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, lambda: self.status_var.set("Error setting CPU level"))
        finally:
             self.root.after(0, lambda: self.btn_set_cpu.state(['!disabled']))

    def set_hd_level(self):
        level = self.hd_scale_var.get()
        self.status_var.set(f"Setting HD Zone to {level}%...")
        self.btn_set_hd.state(['disabled'])
        self._run_async(self._set_hd_level_thread, level)

    def _set_hd_level_thread(self, level):
        try:
            self.ipmi.set_fan_level(Ipmi.HD_ZONE, level)
            self.root.after(0, lambda: self.status_var.set(f"HD Zone Level set to {level}%"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, lambda: self.status_var.set("Error setting HD level"))
        finally:
            self.root.after(0, lambda: self.btn_set_hd.state(['!disabled']))

    def refresh_state(self):
        if not self.ipmi:
            return

        self.status_var.set("Refreshing state from IPMI...")
        self.btn_refresh.state(['disabled'])
        self._run_async(self._refresh_state_thread)

    def _refresh_state_thread(self):
        try:
            # Get Mode
            current_mode = self.ipmi.get_fan_mode()

            # Get Levels
            # Note: get_fan_level might be slow as it calls ipmitool
            cpu_level = self.ipmi.get_fan_level(Ipmi.CPU_ZONE)
            hd_level = self.ipmi.get_fan_level(Ipmi.HD_ZONE)

            # Update UI on main thread
            def update_ui():
                self.mode_var.set(current_mode)
                self.cpu_scale_var.set(cpu_level)
                self.hd_scale_var.set(hd_level)
                self.status_var.set("Refreshed state successfully.")
                self.btn_refresh.state(['!disabled'])

            self.root.after(0, update_ui)

        except Exception as e:
            def show_error():
                self.status_var.set(f"Error refreshing state: {str(e)}")
                self.btn_refresh.state(['!disabled'])
            self.root.after(0, show_error)

    def get_hwmon_temps(self):
        """Scans /sys/class/hwmon for temperature sensors."""
        temps = []
        base_dir = '/sys/class/hwmon'
        if not os.path.exists(base_dir):
            return ["No HWMON interface found."]

        try:
            for hwmon in sorted(os.listdir(base_dir)):
                path = os.path.join(base_dir, hwmon)
                # Get name
                name = hwmon
                name_path = os.path.join(path, 'name')
                if os.path.exists(name_path):
                    with open(name_path, 'r') as f:
                        name = f.read().strip()

                # Find temp inputs
                found_sensor = False
                for entry in sorted(os.listdir(path)):
                    if entry.startswith('temp') and entry.endswith('_input'):
                        try:
                            # Read value (millidegree Celsius)
                            with open(os.path.join(path, entry), 'r') as f:
                                t_str = f.read().strip()
                                if not t_str: continue
                                t = int(t_str) / 1000.0

                            # Read label if exists
                            label = entry.split('_')[0] # default temp1
                            label_path = os.path.join(path, entry.replace('_input', '_label'))
                            if os.path.exists(label_path):
                                with open(label_path, 'r') as f:
                                    l_str = f.read().strip()
                                    if l_str: label = l_str

                            temps.append(f"[{name}] {label}: {t:.1f}°C")
                            found_sensor = True
                        except Exception:
                            continue

                # Some drivers (like simple ACPI) rely just on name or other attributes if no tempX_input,
                # but standard hwmon usually has tempX_input.
        except Exception as e:
            temps.append(f"Error scanning temps: {e}")

        return temps if temps else ["No temperature sensors found."]

    def auto_refresh_temps(self):
        """Periodically refreshes temperatures."""
        try:
            # Run in a separate thread to prevent any file IO stutter
            self._run_async(self._refresh_temps_thread)
        except Exception:
            pass # App might be closing

        # Schedule next update (2 seconds)
        self.root.after(2000, self.auto_refresh_temps)

    def _refresh_temps_thread(self):
        temps = self.get_hwmon_temps()

        def update_text():
            if self.temp_text.winfo_exists():
                self.temp_text.config(state='normal')
                self.temp_text.delete(1.0, tk.END)
                for t in temps:
                    self.temp_text.insert(tk.END, t + "\n")
                self.temp_text.config(state='disabled')

        self.root.after(0, update_text)


def main():
    # The UI should be run as a regular user to access the Display (X11/Wayland).
    # The Ipmi class handles sudo internally for the ipmitool commands.
    if os.geteuid() == 0:
        print("Warning: Running as root might cause issues with connecting to the X display.")
        print("Recommended: Run as regular user. You will be prompted for sudo password if needed.")
    root = tk.Tk()
    FanControlUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
