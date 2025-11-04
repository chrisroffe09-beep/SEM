#!/usr/bin/env python3
import psutil
import time
import socket
from datetime import timedelta
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, ProgressColumn
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.style import Style

console = Console()
prev_net = None  # previous net counters

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
    global prev_net
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)
    uptime = str(timedelta(seconds=uptime_seconds)).split('.')[0]
    hostname = socket.gethostname()

    if prev_net:
        sent_rate = net.bytes_sent - prev_net.bytes_sent
        recv_rate = net.bytes_recv - prev_net.bytes_recv
    else:
        sent_rate = 0
        recv_rate = 0
    prev_net = net

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

def create_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="bars", size=9),
        Layout(name="network", size=3),
        Layout(name="processes")
    )
    return layout

def render_layout(layout, stats, top_procs, progress):
    # Header
    header_text = Text(f"Sour CLI Sys Monitor — {stats['hostname']} | Uptime: {stats['uptime']}", style="bold green")
    commands_text = Text("Commands: Ctrl+C = Exit", style="bold cyan")
    layout["header"].update(Panel(header_text + "\n" + commands_text, style="bold white"))

    # Update bars
    progress["cpu"].update(stats["cpu"])
    progress["mem"].update(stats["mem_used"])
    progress["disk"].update(stats["disk_used"])
    layout["bars"].update(progress.renderable())

    # Network Table
    net_table = Table.grid()
    net_table.add_column(justify="right")
    net_table.add_column(justify="right")
    net_table.add_row("Upload", "Download")
    net_table.add_row(
        format_bytes_per_sec(stats["net_sent_rate"]),
        format_bytes_per_sec(stats["net_recv_rate"])
    )
    layout["network"].update(Panel(net_table, title="Network Info", style="bold green"))

    # Processes Table
    proc_table = Table(show_header=True, header_style="bold cyan")
    proc_table.add_column("PID", justify="right")
    proc_table.add_column("Name")
    proc_table.add_column("CPU %", justify="right")
    proc_table.add_column("Memory %", justify="right")
    for p in top_procs:
        proc_table.add_row(
            str(p["pid"]),
            p["name"][:20] if p["name"] else "N/A",
            f"{p['cpu_percent']:.1f}",
            f"{p['memory_percent']:.1f}"
        )
    layout["processes"].update(proc_table)

def main():
    global prev_net
    prev_net = psutil.net_io_counters()
    time.sleep(1)  # prime network counters

    # Initialize progress bars
    progress = {
        "cpu": Progress(
            "[bold blue]CPU   ",
            BarColumn(bar_width=None, complete_style=Style(color="green")),
            TextColumn("{task.percentage:>3.0f}%"),
            transient=False
        ).add_task("CPU", total=100, completed=0),
        "mem": Progress(
            "[bold magenta]Memory",
            BarColumn(bar_width=None, complete_style=Style(color="green")),
            TextColumn("{task.percentage:>3.0f}%"),
            transient=False
        ).add_task("Memory", total=100, completed=0),
        "disk": Progress(
            "[bold yellow]Disk  ",
            BarColumn(bar_width=None, complete_style=Style(color="green")),
            TextColumn("{task.percentage:>3.0f}%"),
            transient=False
        ).add_task("Disk", total=100, completed=0)
    }

    layout = create_layout()

    with Live(layout, refresh_per_second=1, screen=True):
        try:
            while True:
                stats = get_system_stats()
                top_procs = get_top_processes()
                render_layout(layout, stats, top_procs, progress)
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[red]Exiting Sour CLI Sys Monitor...[/red]")

if __name__ == "__main__":
    main()
