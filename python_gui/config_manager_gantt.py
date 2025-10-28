#!/usr/bin/env python3
"""
ESP32 Dynamic Task Configuration Manager with Gantt Chart Visualization
Tkinter UI for creating, loading, and sending task configurations to ESP32
Real-time Gantt chart showing task execution timeline
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import json
import serial
import serial.tools.list_ports
import threading
import time
from datetime import datetime
from collections import defaultdict, deque
import re

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


class TaskExecutionTracker:
    """Tracks task execution events for Gantt chart visualization"""
    
    def __init__(self, time_window=10.0):
        self.time_window = time_window  # seconds
        self.task_events = defaultdict(deque)  # task_name -> [(timestamp, duration), ...]
        self.start_time = None
        self.task_colors = {}
        self.color_palette = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
            '#F7DC6F', '#BB8FCE', '#85C1E2', '#F8B739', '#52B788',
            '#E76F51', '#2A9D8F', '#E9C46A', '#F4A261', '#8338EC',
            '#3A86FF', '#FB5607', '#FF006E', '#8AC926', '#FFBE0B'
        ]
        self.next_color_idx = 0
        
    def reset(self):
        """Reset tracking data"""
        self.task_events.clear()
        self.start_time = None
        self.task_colors.clear()
        self.next_color_idx = 0
        
    def add_event(self, task_name, timestamp=None):
        """Add a task execution event"""
        if timestamp is None:
            timestamp = time.time()
            
        if self.start_time is None:
            self.start_time = timestamp
            
        # Assign color to new tasks
        if task_name not in self.task_colors:
            self.task_colors[task_name] = self.color_palette[self.next_color_idx % len(self.color_palette)]
            self.next_color_idx += 1
            
        # Store relative time
        relative_time = timestamp - self.start_time
        
        # Add event with estimated duration (will be updated on next event)
        self.task_events[task_name].append(relative_time)
        
        # Clean old events outside time window
        cutoff_time = relative_time - self.time_window
        while self.task_events[task_name] and self.task_events[task_name][0] < cutoff_time:
            self.task_events[task_name].popleft()
            
    def get_gantt_data(self):
        """Get data formatted for Gantt chart plotting"""
        if not self.start_time:
            return [], []
            
        current_time = time.time() - self.start_time
        start_window = max(0, current_time - self.time_window)
        
        task_names = sorted(self.task_events.keys())
        data = []
        
        for task_name in task_names:
            events = [t for t in self.task_events[task_name] if t >= start_window]
            data.append({
                'task': task_name,
                'events': events,
                'color': self.task_colors[task_name]
            })
            
        return data, (start_window, current_time)


class TaskConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32 Dynamic Task Manager with Gantt Chart")
        self.root.geometry("1400x900")
        
        self.tasks = []
        self.serial_port = None
        self.serial_thread = None
        self.running = False
        
        self.tracker = TaskExecutionTracker(time_window=10.0)
        self.gantt_update_interval = 200  # ms
        
        self.setup_ui()
        self.start_gantt_updates()
        
    def setup_ui(self):
        # Main container with two panes
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left pane - Configuration
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=2)
        
        # Right pane - Gantt Chart
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=3)
        
        # Setup left side
        self.setup_left_pane(left_frame)
        
        # Setup right side (Gantt chart)
        self.setup_gantt_pane(right_frame)
        
    def setup_left_pane(self, parent):
        # Serial Port Section
        self.setup_serial_section(parent)
        
        # Task Configuration Section
        self.setup_task_section(parent)
        
        # Task List Section
        self.setup_tasklist_section(parent)
        
        # Log Display Section
        self.setup_log_section(parent)
        
        # Control Buttons Section
        self.setup_control_buttons(parent)
        
    def setup_gantt_pane(self, parent):
        gantt_frame = ttk.LabelFrame(parent, text="Real-Time Task Execution Gantt Chart", padding="10")
        gantt_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create matplotlib figure
        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor='#f0f0f0')
        self.ax = self.fig.add_subplot(111)
        
        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=gantt_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Control buttons
        control_frame = ttk.Frame(gantt_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(control_frame, text="Reset Chart", command=self.reset_gantt).pack(side=tk.LEFT, padx=2)
        ttk.Label(control_frame, text="Time Window:").pack(side=tk.LEFT, padx=5)
        
        self.time_window_var = tk.StringVar(value="10")
        time_entry = ttk.Entry(control_frame, textvariable=self.time_window_var, width=5)
        time_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(control_frame, text="seconds").pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Apply", command=self.update_time_window).pack(side=tk.LEFT, padx=5)
        
        # Initial empty chart
        self.update_gantt_chart()
        
    def setup_serial_section(self, parent):
        serial_frame = ttk.LabelFrame(parent, text="Serial Connection", padding="5")
        serial_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(serial_frame, text="Port:").grid(row=0, column=0, padx=5)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(serial_frame, textvariable=self.port_var, width=15)
        self.port_combo.grid(row=0, column=1, padx=5)
        
        ttk.Button(serial_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=5)
        
        ttk.Label(serial_frame, text="Baud:").grid(row=0, column=3, padx=5)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Entry(serial_frame, textvariable=self.baud_var, width=8).grid(row=0, column=4, padx=5)
        
        self.connect_btn = ttk.Button(serial_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5)
        
        self.status_label = ttk.Label(serial_frame, text="Disconnected", foreground="red")
        self.status_label.grid(row=0, column=6, padx=5)
        
        self.refresh_ports()
        
    def setup_task_section(self, parent):
        task_frame = ttk.LabelFrame(parent, text="Add New Task", padding="10")
        task_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Task Name
        ttk.Label(task_frame, text="Task Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.task_name_var = tk.StringVar()
        ttk.Entry(task_frame, textvariable=self.task_name_var, width=20).grid(row=0, column=1, pady=2)
        
        # Priority
        ttk.Label(task_frame, text="Priority (1-10):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.priority_var = tk.IntVar(value=5)
        ttk.Spinbox(task_frame, from_=1, to=10, textvariable=self.priority_var, width=18).grid(row=1, column=1, pady=2)
        
        # Period
        ttk.Label(task_frame, text="Period (ms):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.period_var = tk.IntVar(value=1000)
        ttk.Entry(task_frame, textvariable=self.period_var, width=20).grid(row=2, column=1, pady=2)
        
        # Sensors
        ttk.Label(task_frame, text="Sensors (max 3):").grid(row=3, column=0, sticky=tk.W, pady=2)
        
        sensor_frame = ttk.Frame(task_frame)
        sensor_frame.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        self.sensor_vars = {
            "dht11": tk.BooleanVar(),
            "ultrasonic": tk.BooleanVar(),
            "mpu6050": tk.BooleanVar()
        }
        
        ttk.Checkbutton(sensor_frame, text="DHT11", variable=self.sensor_vars["dht11"]).pack(anchor=tk.W)
        ttk.Checkbutton(sensor_frame, text="Ultrasonic", variable=self.sensor_vars["ultrasonic"]).pack(anchor=tk.W)
        ttk.Checkbutton(sensor_frame, text="MPU6050", variable=self.sensor_vars["mpu6050"]).pack(anchor=tk.W)
        
        # Add Task Button
        ttk.Button(task_frame, text="Add Task", command=self.add_task).grid(row=4, column=0, columnspan=2, pady=10)
        
    def setup_tasklist_section(self, parent):
        list_frame = ttk.LabelFrame(parent, text="Task List", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview for tasks
        columns = ("Name", "Priority", "Period", "Sensors")
        self.task_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=6)
        
        for col in columns:
            self.task_tree.heading(col, text=col)
            self.task_tree.column(col, width=80)
        
        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        
        # Buttons
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="Remove", command=self.remove_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_tasks).pack(side=tk.LEFT, padx=2)
        
    def setup_log_section(self, parent):
        log_frame = ttk.LabelFrame(parent, text="ESP32 Log Output", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=8, font=("Courier", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Log controls
        log_ctrl_frame = ttk.Frame(log_frame)
        log_ctrl_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(log_ctrl_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_ctrl_frame, text="Save Log", command=self.save_log).pack(side=tk.LEFT, padx=2)
        
    def setup_control_buttons(self, parent):
        control_frame = ttk.Frame(parent, padding="5")
        control_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(control_frame, text="Load Config", command=self.load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Send to ESP32", command=self.send_config).pack(side=tk.LEFT, padx=5)
        
    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports and not self.port_var.get():
            self.port_combo.current(0)
            
    def toggle_connection(self):
        if self.serial_port and self.serial_port.is_open:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self):
        try:
            port = self.port_var.get()
            baud = int(self.baud_var.get())
            
            self.serial_port = serial.Serial(port, baud, timeout=0.1)
            self.status_label.config(text="Connected", foreground="green")
            self.connect_btn.config(text="Disconnect")
            
            # Start reading thread
            self.running = True
            self.serial_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.serial_thread.start()
            
            self.log_message("Connected to " + port)
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
            
    def disconnect(self):
        self.running = False
        if self.serial_thread:
            self.serial_thread.join(timeout=1)
        
        if self.serial_port:
            self.serial_port.close()
            
        self.status_label.config(text="Disconnected", foreground="red")
        self.connect_btn.config(text="Connect")
        self.log_message("Disconnected")
        
    def read_serial(self):
        while self.running and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        self.root.after(0, self.log_message, line)
                        self.root.after(0, self.parse_task_event, line)
            except Exception as e:
                self.root.after(0, self.log_message, f"Serial read error: {str(e)}")
                break
            time.sleep(0.01)
            
    def parse_task_event(self, line):
        """Parse log line to extract task execution events"""
        # Look for pattern: [TaskName] ...
        match = re.match(r'\[([^\]]+)\]', line)
        if match:
            task_name = match.group(1)
            self.tracker.add_event(task_name)
            
    def add_task(self):
        name = self.task_name_var.get().strip()
        if not name:
            messagebox.showwarning("Invalid Input", "Please enter a task name")
            return
            
        if len(self.tasks) >= 32:
            messagebox.showwarning("Limit Reached", "Maximum 32 tasks allowed")
            return
            
        sensors = [s for s, v in self.sensor_vars.items() if v.get()]
        if len(sensors) == 0:
            messagebox.showwarning("Invalid Input", "Please select at least one sensor")
            return
            
        if len(sensors) > 3:
            messagebox.showwarning("Invalid Input", "Maximum 3 sensors per task")
            return
            
        task = {
            "name": name,
            "priority": self.priority_var.get(),
            "period_ms": self.period_var.get(),
            "sensors": sensors
        }
        
        self.tasks.append(task)
        self.task_tree.insert("", tk.END, values=(
            name, 
            task["priority"], 
            task["period_ms"], 
            ", ".join(sensors)
        ))
        
        # Reset form
        self.task_name_var.set("")
        for var in self.sensor_vars.values():
            var.set(False)
            
        self.log_message(f"Added task: {name}")
        
    def remove_task(self):
        selected = self.task_tree.selection()
        if not selected:
            return
            
        idx = self.task_tree.index(selected[0])
        self.task_tree.delete(selected[0])
        del self.tasks[idx]
        self.log_message(f"Removed task at index {idx}")
        
    def clear_tasks(self):
        if messagebox.askyesno("Confirm", "Clear all tasks?"):
            self.tasks.clear()
            for item in self.task_tree.get_children():
                self.task_tree.delete(item)
            self.log_message("Cleared all tasks")
            
    def load_config(self):
        filename = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filename:
            return
            
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
                
            self.clear_tasks()
            
            for task in config.get("tasks", []):
                self.tasks.append(task)
                self.task_tree.insert("", tk.END, values=(
                    task["name"],
                    task["priority"],
                    task["period_ms"],
                    ", ".join(task["sensors"])
                ))
                
            self.log_message(f"Loaded config from {filename}")
            messagebox.showinfo("Success", f"Loaded {len(self.tasks)} tasks")
            
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load config: {str(e)}")
            
    def save_config(self):
        if not self.tasks:
            messagebox.showwarning("No Tasks", "No tasks to save")
            return
            
        filename = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filename:
            return
            
        try:
            config = {"tasks": self.tasks}
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
                
            self.log_message(f"Saved config to {filename}")
            messagebox.showinfo("Success", "Configuration saved")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save config: {str(e)}")
            
    def send_config(self):
        if not self.serial_port or not self.serial_port.is_open:
            messagebox.showwarning("Not Connected", "Please connect to ESP32 first")
            return
            
        if not self.tasks:
            messagebox.showwarning("No Tasks", "No tasks to send")
            return
            
        try:
            # Reset tracker when sending new config
            self.tracker.reset()
            
            config = {"tasks": self.tasks}
            json_str = json.dumps(config, separators=(',', ':'))
            
            self.log_message("Sending START signal...")
            self.serial_port.write(b"START\n")
            time.sleep(0.5)
            
            self.log_message("Sending config...")
            self.serial_port.write(json_str.encode('utf-8'))
            time.sleep(0.5)
            
            self.log_message("Sending END signal...")
            self.serial_port.write(b"END\n")
            
            self.log_message("Config sent successfully")
            messagebox.showinfo("Success", "Configuration sent to ESP32")
            
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to send config: {str(e)}")
            
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        
    def save_log(self):
        filename = filedialog.asksaveasfilename(
            title="Save Log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Success", "Log saved")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save log: {str(e)}")
                
    def reset_gantt(self):
        """Reset Gantt chart data"""
        self.tracker.reset()
        self.update_gantt_chart()
        self.log_message("Gantt chart reset")
        
    def update_time_window(self):
        """Update time window for Gantt chart"""
        try:
            window = float(self.time_window_var.get())
            if window > 0:
                self.tracker.time_window = window
                self.log_message(f"Time window updated to {window}s")
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid number")
            
    def start_gantt_updates(self):
        """Start periodic Gantt chart updates"""
        self.update_gantt_chart()
        self.root.after(self.gantt_update_interval, self.start_gantt_updates)
        
    def update_gantt_chart(self):
        """Update the Gantt chart with latest data"""
        self.ax.clear()
        
        data, time_range = self.tracker.get_gantt_data()
        
        if not data:
            self.ax.text(0.5, 0.5, 'Waiting for task execution data...',
                        ha='center', va='center', transform=self.ax.transAxes,
                        fontsize=12, color='gray')
            self.ax.set_xlim(0, 10)
            self.ax.set_ylim(0, 1)
        else:
            # Plot each task's events
            y_pos = 0
            y_labels = []
            y_ticks = []
            
            bar_height = 0.8
            
            for task_data in data:
                task_name = task_data['task']
                events = task_data['events']
                color = task_data['color']
                
                # Plot each event as a small bar
                for event_time in events:
                    # Show as 50ms bar (visual representation)
                    self.ax.barh(y_pos, 0.05, left=event_time, height=bar_height,
                               color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
                
                y_labels.append(task_name)
                y_ticks.append(y_pos)
                y_pos += 1
            
            # Set labels and limits
            self.ax.set_yticks(y_ticks)
            self.ax.set_yticklabels(y_labels, fontsize=9)
            self.ax.set_xlabel('Time (seconds)', fontsize=10)
            self.ax.set_title('Real-Time Task Execution Timeline', fontsize=12, fontweight='bold')
            
            # Set x-axis range
            if time_range[1] > time_range[0]:
                self.ax.set_xlim(time_range[0], time_range[1])
            else:
                self.ax.set_xlim(0, self.tracker.time_window)
                
            # Grid
            self.ax.grid(True, axis='x', alpha=0.3, linestyle='--')
            self.ax.set_axisbelow(True)
            
            # Invert y-axis so first task is on top
            self.ax.invert_yaxis()
        
        self.fig.tight_layout()
        self.canvas.draw()
        
    def on_closing(self):
        if self.serial_port and self.serial_port.is_open:
            self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = TaskConfigApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
