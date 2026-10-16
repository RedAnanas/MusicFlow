"""提供可双击的客户端授权窗口，也支持供后续工作进程调用的命令行模式。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import queue
import subprocess
import uuid
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prototype.client_authorization import authorize, BUNDLE, ClientAuthorizationError, default_library_file
from prototype.local_session import load_session


def authorize_and_export(library_file, output_directory, key_file=None, progress=None):
    """只在本次读取成功后导出，不回退使用旧授权。"""
    authorize(library_file or None, progress=progress)
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'export-server-authorization.py'),
               '--input', str(BUNDLE), '--output-directory', str(output_directory)]
    if key_file is not None:
        command += ['--key-file', str(key_file)]
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise ClientAuthorizationError('授权已保存在本机，但服务端导出失败；请检查原密钥、目标目录和执行器占用。')


def build_window(export_server=False):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("MusicFlow · 客户端授权")
    root.geometry("640x430")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="从 Apple Music 获取上传授权", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
    ttk.Label(frame, text="请在官方客户端完成登录，并开启“同步资料库”。\n工具会自动寻找客户端进程，不读取或保存密码。",
              wraplength=545).pack(anchor="w", pady=(12, 16))
    library = tk.StringVar(value="")
    try:
        library.set(str(default_library_file()))
    except ClientAuthorizationError:
        pass
    ttk.Label(frame, text="正在使用的资料库文件（默认自动定位）").pack(anchor="w")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(5, 16))
    ttk.Entry(row, textvariable=library).pack(side="left", fill="x", expand=True)

    def choose():
        value = filedialog.askopenfilename(parent=root, title="选择正在使用的 Library.musicdb",
            filetypes=[("Apple Music 资料库", "*.musicdb")])
        if value:
            library.set(value)

    ttk.Button(row, text="选择…", command=choose).pack(side="right", padx=(8, 0))
    status = tk.StringVar(value="点击下方按钮开始；未运行的客户端会自动打开。")
    if BUNDLE.exists():
        try:
            saved = load_session(BUNDLE)
            status.set("已有加密授权，保存于 " + datetime.fromtimestamp(saved["created_at"]).strftime("%m-%d %H:%M")
                       + "。可重新读取以更新。")
        except Exception:
            status.set("已有授权无法读取，请重新获取。")
    ttk.Label(frame, textvariable=status, wraplength=545).pack(anchor="w", pady=(0, 14))
    events = queue.Queue()

    def work(path, destination=None, key_file=None):
        try:
            progress = lambda message: events.put(("progress", message))
            if destination is not None:
                authorize_and_export(path, destination, key_file, progress)
                events.put(("done", f"服务端加密授权已导出到：{destination}\n将 state/account.mfup 和首次生成的 keys/store.key 导入系统设置。请保管原密钥，正常退出 Apple Music。"))
                return
            authorize(path or None, progress=progress)
            events.put(("done", "授权和资料库上下文已加密保存。\n独立上传前请正常退出 Apple Music；服务器有效性将在上传时检查。"))
        except ClientAuthorizationError as error:
            events.put(("done", str(error)))
        except Exception:
            events.put(("done", "读取失败；请确认客户端已登录并载入资料库，然后重试。原授权未覆盖。"))

    def start():
        destination = None
        key_file = None
        if export_server:
            reuse = messagebox.askyesnocancel('授权类型', '是否为已有服务端重新授权？\n是：选择原 store.key；否：首次生成新密钥；取消：返回。', parent=root)
            if reuse is None:
                return
            if reuse:
                key_file = filedialog.askopenfilename(parent=root, title='选择现有服务端的原 store.key', filetypes=[('服务端密钥', '*.key')])
                if not key_file:
                    return
            parent = filedialog.askdirectory(parent=root, title='选择私密导出目录（请勿选择共享或同步目录）')
            if not parent:
                return
            destination = Path(parent) / ('MusicFlow-authorization-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
        button.configure(state="disabled")
        threading.Thread(target=work, args=(library.get(), destination, key_file), daemon=True).start()

    button = ttk.Button(frame, text="读取并导出服务端授权" if export_server else "读取客户端授权", command=start)
    button.pack(anchor="w")
    ttk.Label(frame, text="本机授权使用 DPAPI 保护；服务端导出使用独立密钥加密。" if export_server else "授权使用当前 Windows 用户的 DPAPI 保护，仅保存在本机。",
              wraplength=545).pack(anchor="w", pady=(12, 0))

    def poll():
        try:
            while True:
                kind, message = events.get_nowait()
                status.set(message)
                if kind == "done":
                    button.configure(state="normal")
        except queue.Empty:
            pass
        root.after(100, poll)

    poll()
    root.update_idletasks()
    root.geometry(f"640x{max(430, root.winfo_reqheight())}")
    return root


def main():
    parser = argparse.ArgumentParser(description="自动从已登录 Apple Music 读取本机上传授权")
    parser.add_argument("--cli", action="store_true", help="命令行模式，不打开授权窗口")
    parser.add_argument("--library-file", type=Path, help="自定义位置的 Library.musicdb")
    parser.add_argument("--export-server", action="store_true", help="窗口读取成功后自动导出服务端加密授权")
    args = parser.parse_args()
    if args.cli and args.export_server:
        parser.error("--export-server 使用窗口选择密钥和输出目录，不能与 --cli 同用")
    if args.cli:
        result = authorize(args.library_file, progress=lambda message: print(
            json.dumps({"stage": message}, ensure_ascii=False), flush=True))
        print(json.dumps(result), flush=True)
    else:
        build_window(export_server=args.export_server).mainloop()


if __name__ == "__main__":
    try:
        main()
    except ClientAuthorizationError as error:
        print(json.dumps({"authorization_saved": False, "error": str(error)}, ensure_ascii=False), flush=True)
        raise SystemExit(1) from None
    except Exception as error:
        print(json.dumps({"authorization_saved": False, "error_type": type(error).__name__}), flush=True)
        raise SystemExit(1) from None
