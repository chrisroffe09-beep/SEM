#!/usr/bin/env python3
import psutil
import time
import socket
import threading
import subprocess
from datetime import timedelta
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.style import Style
import keyboard

console = Console()
prev_net = None
prev_time = None
kill_requested = False

# NEW: network tab state and speedtest state
network_tab_active = False
speedtest_running = False
speedtest_result_text = ""
speedtest_error = None
speed_samples = []  # holds recent Mbps samples (download during test then upload)
speed_samples_lock = threading.Lock()

# ---------------- Key Listener ----------------
def listen_for_keys():
    global kill_requested, network_tab_active
    while True:
        event = keyboard.read_event()
        if event.event_type == keyboard.KEY_DOWN:
            if event.name == "k":
                kill_requested = True
            elif event.name == "n":
                network_tab_active = not network_tab_active

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

    now = time.time()
    if prev_net and prev_time:
        dt = now - prev_time
        if dt > 0:
            sent_rate = (net.bytes_sent - prev_net.bytes_sent) / dt
            recv_rate = (net.bytes_recv - prev_net.bytes_recv) / dt
        else:
            sent_rate = recv_rate = 0
    else:
        sent_rate = recv_rate = 0

    prev_net = net
    prev_time = now

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
    layout["bottom"].split_row(
        Layout(name="processes", ratio=60),
        Layout(name="disk_preview", ratio=40)
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
    net_table.add_column("Upload", justify="right")
    net_table.add_column("Download", justify="right")
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
    table.add_column("Device")
    table.add_column("Mountpoint")
    table.add_column("FS Type")
    table.add_column("Used %", justify="right")

    for d in disks:
        try:
            usage = psutil.disk_usage(d.mountpoint)
            table.add_row(
                d.device,
                d.mountpoint,
                d.fstype,
                f"{usage.percent:.0f}%"
            )
        except PermissionError:
            continue

    return Panel(table, title="Disk Preview", style="bold yellow")

# NEW: build the speedtest subpanel
def build_speedtest_panel():
    global speed_samples, speedtest_running, speedtest_result_text, speedtest_error

    panel_table = Table.grid(expand=True)
    panel_table.add_column("col", ratio=1)

    if speedtest_running:
        title_text = "[bold green]Network Speedtest (running) — press 'n' to close[/bold green]"
    else:
        title_text = "[bold green]Network Speedtest — press 'n' to close[/bold green]"

    with speed_samples_lock:
        samples = list(speed_samples)

    if len(samples) == 0:
        graph = "No samples yet. Start a test by toggling the network panel."
    else:
        max_mbps = max(max(samples), 1e-6)
        display = samples[-30:]
        bars = []
        for mbps in display:
            blocks = int((mbps / max_mbps) * 12)
            blocks = max(1, blocks) if mbps > 0 else 0
            bars.append("▁▂▃▄▅▆▇█"[min(7, blocks)])
        graph = "".join(bars)

    rows = []
    rows.append(Text(title_text))
    rows.append(Text("\nLive graph: " + graph))
    if samples:
        latest = samples[-1]
        rows.append(Text(f"\nLatest throughput: {latest:.2f} Mbps"))
    if speedtest_error:
        rows.append(Text(f"\n[red]Error: {speedtest_error}[/red]"))
    elif not speedtest_running and speedtest_result_text:
        rows.append(Text(f"\n{speedtest_result_text}"))

    for r in rows:
        panel_table.add_row(r)

    return Panel(panel_table, title="Speedtest (speedtest-cli)", style="bold green")

def render_layout(layout, stats, top_procs):
    header_text = Text(
        f"Sour CLI Sys Monitor — {stats['hostname']} | Uptime: {stats['uptime']}",
        style="bold green"
    )
    commands_text = Text(
        "Commands: Ctrl+C = Exit | Press 'k' to kill a process | Press 'n' to toggle network speedtest panel",
        style="bold cyan"
    )
    layout["header"].update(Panel(header_text + "\n" + commands_text, style="bold white"))
    layout["bars"].update(build_bars(stats))

    if network_tab_active:
        layout["network"].update(build_speedtest_panel())
    else:
        layout["network"].update(build_network_table(stats))

    layout["processes"].update(build_process_table(top_procs))
    layout["disk_preview"].update(build_disk_preview())

# ---------------- Kill Process ----------------
def kill_proc_tree(pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            child.kill()
        parent.kill()
        psutil.wait_procs(children, timeout=3)
    except Exception as e:
        console.print(f"[red]Error killing process: {e}[/red]")

def kill_process_prompt(top_procs, live):
    live.stop()
    console.clear()

    console.print("[bold yellow]Kill a process[/bold yellow]")
    for i, p in enumerate(top_procs, 1):
        console.print(f"[cyan]{i}[/cyan]: {p['name']} (PID {p['pid']}) CPU {p['cpu_percent']:.1f}%")

    try:
        console.print()
        choice = int(console.input("[bold white]Enter process number to kill (0 to cancel): [/bold white]"))
        if choice == 0:
            console.print("[yellow]Canceled.[/yellow]")
        else:
            proc = top_procs[choice - 1]
            kill_proc_tree(proc["pid"])
            console.print(f"[green]Killed {proc['name']} (PID {proc['pid']})[/green]")
    except:
        console.print("[red]Invalid selection[/red]")
    finally:
        time.sleep(1)
        live.start()

# ---------------- Speedtest Runner ----------------
def run_speedtest_background():
    """
    Starts speedtest-cli in a background thread, captures live output line by line,
    and updates the speed_samples for Ookla-style graph and result text.
    """
    global speedtest_running, speedtest_result_text, speedtest_error, speed_samples
    if speedtest_running:
        return

    def _worker():
        global speedtest_running, speedtest_result_text, speedtest_error, speed_samples
        speedtest_running = True
        speedtest_result_text = ""
        speedtest_error = None
        with speed_samples_lock:
            speed_samples = []

        try:
            proc = subprocess.Popen(
                ["speedtest-cli", "--simple"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # line buffered
            )
        except FileNotFoundError:
            speedtest_error = "speedtest-cli not found. Install it (pip install speedtest-cli or apt install speedtest-cli)."
            speedtest_running = False
            return
        except Exception as e:
            speedtest_error = f"Failed to start speedtest-cli: {e}"
            speedtest_running = False
            return

        last = psutil.net_io_counters()
        last_time = time.time()

        try:
            # read stdout line by line
            for line in proc.stdout:
                line = line.strip()
                if line:
                    with speed_samples_lock:
                        speedtest_result_text += line + "\n"

                # update graph sample based on network delta
                now = time.time()
                cur = psutil.net_io_counters()
                dt = max(now - last_time, 1e-6)
                down_bps = (cur.bytes_recv - last.bytes_recv) / dt
                up_bps = (cur.bytes_sent - last.bytes_sent) / dt
                sample_mbps = max(down_bps, up_bps) * 8.0 / 1_000_000.0
                with speed_samples_lock:
                    speed_samples.append(sample_mbps)
                    if len(speed_samples) > 200:
                        speed_samples = speed_samples[-200:]
                last = cur
                last_time = now
        except Exception as e:
            speedtest_error = f"Speedtest error: {e}"

        proc.wait(timeout=10)
        speedtest_running = False

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

# ---------------- Main ----------------
def main():
    global prev_net, prev_time, kill_requested, network_tab_active

    prev_net = psutil.net_io_counters()
    prev_time = time.time()

    threading.Thread(target=listen_for_keys, daemon=True).start()

    layout = create_layout()
    with Live(layout, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                stats = get_system_stats()
                top_procs = get_top_processes()
                render_layout(layout, stats, top_procs)

                if network_tab_active and not speedtest_running and not speedtest_result_text and not speedtest_error:
                    run_speedtest_background()

                if kill_requested:
                    kill_requested = False
                    kill_process_prompt(top_procs, live)

                time.sleep(0.2)

        except KeyboardInterrupt:
            console.print("\n[red]Exiting Sour CLI Sys Monitor...[/red]")

if __name__ == "__main__":
    main()
