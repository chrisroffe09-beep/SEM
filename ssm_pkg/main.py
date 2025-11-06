#!/usr/bin/env python3
import psutil
import time
import socket
from datetime import timedelta
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.style import Style
import keyboard  # pip install keyboard

console = Console()
prev_net = None
prev_time = None

# ---------------- Helper Functions ----------------
def get_color(value: float) -> str:
    if value < 50:
        return "green"
    elif value < 80:
        return "yellow"
    else:
        return "red"

def format_bytes_per_sec(bps: float) -> str:
    kb = bps / 1024
    mb = kb / 1024
    gb = mb / 1024
    if gb >= 1:
        return f"{gb:.2f} GB/s"
    elif mb >= 1:
        return f"{mb:.2f} MB/s"
    elif kb >= 1:
        return f"{kb:.2f} KB/s"
    else:
        return f"{bps:.0f} B/s"

def get_system_stats():
    global prev_net, prev_time
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)
    uptime = str(timedelta(seconds=uptime_seconds)).split('.')[0]
    hostname = socket.gethostname()

    current_time = time.time()
    interval = current_time - prev_time if prev_time else 1
    if prev_net:
        sent_rate = (net.bytes_sent - prev_net.bytes_sent) / interval
        recv_rate = (net.bytes_recv - prev_net.bytes_recv) / interval
    else:
        sent_rate = 0
        recv_rate = 0

    prev_net = net
    prev_time = current_time

    return {
        "cpu": cpu,
        "mem_used": mem.percent,
        "disk_used": disk.percent,
        "net_sent_rate": sent_rate,
        "net_recv_rate": recv_rate,
        "uptime": uptime,
        "hostname": hostname
    }

def get_top_processes(limit=10):
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(p.info)
        except psutil.NoSuchProcess:
            continue
    procs = sorted(procs, key=lambda p: p['cpu_percent'], reverse=True)
    return procs[:limit]

# ---------------- Layout ----------------
def create_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="bars", size=6),
        Layout(name="network", size=3),
        Layout(name="bottom")
    )

    # 60/40 split for bottom row
    layout["bottom"].split_row(
        Layout(name="processes", ratio=3),
        Layout(name="disk_preview", ratio=2)
    )
    return layout

def build_bars(stats):
    cpu_color = get_color(stats["cpu"])
    mem_color = get_color(stats["mem_used"])
    disk_color = get_color(stats["disk_used"])

    cpu_bar = Progress(
        "[bold blue]CPU   ",
        BarColumn(bar_width=None, complete_style=Style(color=cpu_color)),
        TextColumn("{task.percentage:>3.0f}%")
    )
    mem_bar = Progress(
        "[bold magenta]Memory",
        BarColumn(bar_width=None, complete_style=Style(color=mem_color)),
        TextColumn("{task.percentage:>3.0f}%")
    )
    disk_bar = Progress(
        "[bold yellow]Disk  ",
        BarColumn(bar_width=None, complete_style=Style(color=disk_color)),
        TextColumn("{task.percentage:>3.0f}%")
    )

    cpu_bar.add_task("CPU", total=100, completed=stats["cpu"])
    mem_bar.add_task("Memory", total=100, completed=stats["mem_used"])
    disk_bar.add_task("Disk", total=100, completed=stats["disk_used"])

    bars_table = Table.grid(expand=True)
    bars_table.add_row(cpu_bar)
    bars_table.add_row(mem_bar)
    bars_table.add_row(disk_bar)
    return bars_table

def build_network_table(stats):
    net_table = Table.grid(expand=True)
    net_table.add_column(justify="right")
    net_table.add_column(justify="right")
    net_table.add_row("Upload", "Download")
    net_table.add_row(
        format_bytes_per_sec(stats["net_sent_rate"]),
        format_bytes_per_sec(stats["net_recv_rate"])
    )
    return Panel(net_table, title="Network Info", style="bold green")

def build_process_table(top_procs):
    proc_table = Table(expand=True, show_header=True, header_style="bold cyan")
    proc_table.add_column("No.", justify="right")
    proc_table.add_column("PID", justify="right")
    proc_table.add_column("Name")
    proc_table.add_column("CPU %", justify="right")
    proc_table.add_column("Memory %", justify="right")
    for i, p in enumerate(top_procs, 1):
        proc_table.add_row(
            str(i),
            str(p["pid"]),
            p["name"][:20] if p["name"] else "N/A",
            f"{p['cpu_percent']:.1f}",
            f"{p['memory_percent']:.1f}"
        )
    return proc_table

def build_disk_preview():
    disks = psutil.disk_partitions(all=False)
    table = Table(expand=True, show_header=True, header_style="bold magenta")
    table.add_column("Dev")
    table.add_column("Mount")
    table.add_column("Used %", justify="right")

    for d in disks:
        try:
            usage = psutil.disk_usage(d.mountpoint)
            table.add_row(
                d.device,
                d.mountpoint,
                f"{usage.percent:.0f}%"
            )
        except PermissionError:
            continue
    return Panel(table, title="Disk Preview", style="bold yellow")

def render_layout(layout, stats, top_procs):
    header_text = Text(f"Sour CLI Sys Monitor — {stats['hostname']} | Uptime: {stats['uptime']}", style="bold green")
    commands_text = Text("Commands: Ctrl+C = Exit | Press 'k' to kill a process", style="bold cyan")
    layout["header"].update(Panel(header_text + "\n" + commands_text, style="bold white"))

    layout["bars"].update(build_bars(stats))
    layout["network"].update(build_network_table(stats))
    layout["processes"].update(build_process_table(top_procs))
    layout["disk_preview"].update(build_disk_preview())

# ---------------- Kill Process ----------------
def kill_process_prompt(top_procs, live):
    """
    Stops live rendering temporarily to allow user input.
    """
    live.stop()
    console.print("\n[bold yellow]Kill a process[/bold yellow]")

    for i, p in enumerate(top_procs, 1):
        name = p["name"][:30] if p["name"] else "N/A"
        console.print(f"[cyan]{i}[/cyan]: {name} (PID {p['pid']}) CPU {p['cpu_percent']:.1f}%")

    try:
        choice = int(console.input("Enter process number to kill (0 to cancel): "))
        if choice == 0:
            console.print("[green]Cancelled[/green]")
            return
        proc_info = top_procs[choice - 1]
        proc = psutil.Process(proc_info['pid'])
        proc.terminate()
        console.print(f"[green]Sent terminate signal to {proc_info['name']} (PID {proc.pid})[/green]")
    except (ValueError, IndexError):
        console.print("[red]Invalid selection[/red]")
    except psutil.AccessDenied:
        console.print("[red]Permission denied[/red]")
    finally:
        live.start()

# ---------------- Main ----------------
def main():
    global prev_net, prev_time
    prev_net = psutil.net_io_counters()
    prev_time = time.time()
    time.sleep(1)

    layout = create_layout()

    with Live(layout, refresh_per_second=1, screen=True) as live:
        # Keyboard listener for 'k' key
        keyboard.add_hotkey('k', lambda: kill_process_prompt(get_top_processes(), live))

        try:
            while True:
                stats = get_system_stats()
                top_procs = get_top_processes()
                render_layout(layout, stats, top_procs)
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[red]Exiting Sour CLI Sys Monitor...[/red]")

if __name__ == "__main__":
    main()
