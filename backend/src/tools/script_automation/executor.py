"""Script executor — runs Python scripts in the sandboxed subprocess.

流程：
  1. 从 storage 获取用户脚本路径
  2. 确保 .venv 虚拟环境就绪
  3. 调用 wrapper_builder 生成包装器
  4. 写入临时包装器文件到沙箱目录
  5. subprocess.run 执行包装器（或 Popen 流式执行）
  6. 清理临时文件
  7. 返回执行结果
"""

from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from . import sandbox_env
from . import storage
from . import wrapper_builder
from . import execution_manager
from .safety import get_sandbox_dir, MAX_EXECUTION_TIME, MAX_OUTPUT_CHARS


def execute_python_script(
    script_name: str,
    args: str = "",
) -> Dict:
    """在沙箱子进程中执行指定的 Python 脚本。

    Args:
        script_name: 脚本名称（不含 .py 后缀）。
        args: 传递给脚本的命令行参数（通过 sys.argv）。

    Returns:
        dict: {
            "stdout": str,       # 标准输出
            "stderr": str,       # 标准错误
            "returncode": int,   # 退出码（0 表示成功）
            "ok": bool,          # 是否成功
        }

    Raises:
        ValueError: 如果脚本不存在或沙箱未初始化。
        RuntimeError: 如果执行过程中发生系统级错误。
    """
    sandbox_dir = get_sandbox_dir()
    script_path = storage.get_script_path(script_name)

    # 1. 确保 .venv 存在
    sandbox_python = sandbox_env.ensure_sandbox_venv()

    # 2. 生成包装器
    wrapper_code = wrapper_builder.build_wrapper(script_path, sandbox_dir)

    # 3. 写入临时包装器文件
    # 使用 sandbox_dir 作为临时文件的目录（确保同分区，便于路径处理）
    wrapper_filename = f"._wrapper_{os.getpid()}_{_random_hex()}.py"
    wrapper_path = sandbox_dir / wrapper_filename
    try:
        wrapper_path.write_text(wrapper_code, encoding="utf-8")

        # 4. 构建命令：python wrapper.py [args...]
        cmd = [str(sandbox_python), str(wrapper_path)]
        if args:
            cmd.extend(args.split())

        # 5. 在沙箱目录中执行
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MAX_EXECUTION_TIME,
            cwd=str(sandbox_dir),
        )

        # 6. 截断过长的输出（保留尾部，确保错误信息不被截掉）
        stdout = result.stdout
        stderr = result.stderr
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = f"... (输出已截断，共 {len(stdout)} 字符，仅显示末尾 {MAX_OUTPUT_CHARS} 字符)\n" + stdout[-MAX_OUTPUT_CHARS:]
        if len(stderr) > MAX_OUTPUT_CHARS:
            stderr = f"... (输出已截断，共 {len(stderr)} 字符，仅显示末尾 {MAX_OUTPUT_CHARS} 字符)\n" + stderr[-MAX_OUTPUT_CHARS:]

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "ok": result.returncode == 0,
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"脚本执行超时（{MAX_EXECUTION_TIME} 秒）",
            "returncode": -1,
            "ok": False,
        }
    finally:
        # 7. 清理临时文件
        if wrapper_path.exists():
            try:
                wrapper_path.unlink()
            except OSError:
                pass  # 清理失败不影响主流程


def execute_python_script_stream(
    script_name: str,
    args: str = "",
    output_callback: Optional[Callable[[str, str], None]] = None,
    execution_id: Optional[str] = None,
) -> Dict:
    """在沙箱子进程中执行脚本，并通过回调流式输出每一行。

    与 execute_python_script 功能相同，但使用 Popen 逐行读取输出，
    通过 output_callback(line, stream_name) 实时推送每行内容。

    Args:
        script_name: 脚本名称（不含 .py 后缀）。
        args: 传递给脚本的命令行参数。
        output_callback: 可选回调，每产生一行输出时调用。
                        参数为 (行内容, "stdout"|"stderr")。
        execution_id: 可选，用于在全局注册表中跟踪进程（支持 kill）。

    Returns:
        同 execute_python_script。
    """
    sandbox_dir = get_sandbox_dir()
    script_path = storage.get_script_path(script_name)

    sandbox_python = sandbox_env.ensure_sandbox_venv()
    wrapper_code = wrapper_builder.build_wrapper(script_path, sandbox_dir)

    wrapper_filename = f"._wrapper_{os.getpid()}_{_random_hex()}.py"
    wrapper_path = sandbox_dir / wrapper_filename
    try:
        wrapper_path.write_text(wrapper_code, encoding="utf-8")

        cmd = [str(sandbox_python), str(wrapper_path)]
        if args:
            cmd.extend(args.split())

        # 使用 Popen 逐行读取，支持流式回调
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(sandbox_dir),
        )

        # 注册进程到全局字典（支持 kill）
        if execution_id:
            execution_manager.register_execution(execution_id, process)

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # 使用线程安全队列，将子线程的输出转发到主线程处理
        # LangGraph 的 stream_writer 不是线程安全的，不能从子线程调用
        import time as _time
        output_queue: queue.Queue = queue.Queue()
        _start_time = _time.monotonic()

        def _reader(stream: subprocess.PIPE, lines: list[str], stream_name: str) -> None:
            """在独立线程中读取一个流，逐行追加到 lines 并放入队列。"""
            for line in iter(stream.readline, ""):
                lines.append(line)
                output_queue.put((line.rstrip("\n\r"), stream_name))
            stream.close()

        # 启动两个线程分别读取 stdout 和 stderr
        t_out = threading.Thread(target=_reader, args=(process.stdout, stdout_lines, "stdout"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(process.stderr, stderr_lines, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        # 轮询进程状态，同时从队列中取出输出行并回调（在主线程中调用 writer）
        timed_out = False
        while process.poll() is None:
            if _time.monotonic() - _start_time > MAX_EXECUTION_TIME:
                process.kill()
                timed_out = True
                break
            try:
                item = output_queue.get(timeout=0.1)
                if output_callback:
                    try:
                        output_callback(item[0], item[1])
                    except Exception:
                        pass
            except queue.Empty:
                pass

        if timed_out:
            t_out.join()
            t_err.join()
            return {
                "stdout": "",
                "stderr": f"脚本执行超时（{MAX_EXECUTION_TIME} 秒）",
                "returncode": -1,
                "ok": False,
            }

        # 进程已结束，等待读取线程完成
        t_out.join()
        t_err.join()

        # 排空队列中剩余的 line
        while not output_queue.empty():
            try:
                item = output_queue.get_nowait()
                if output_callback:
                    try:
                        output_callback(item[0], item[1])
                    except Exception:
                        pass
            except queue.Empty:
                break

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)

        # 截断过长的输出（保留尾部）
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = f"... (输出已截断，共 {len(stdout)} 字符，仅显示末尾 {MAX_OUTPUT_CHARS} 字符)\n" + stdout[-MAX_OUTPUT_CHARS:]
        if len(stderr) > MAX_OUTPUT_CHARS:
            stderr = f"... (输出已截断，共 {len(stderr)} 字符，仅显示末尾 {MAX_OUTPUT_CHARS} 字符)\n" + stderr[-MAX_OUTPUT_CHARS:]

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process.returncode,
            "ok": process.returncode == 0,
        }

    finally:
        # 从全局注册表中移除（无论正常结束、超时还是被 kill）
        if execution_id:
            execution_manager.unregister_execution(execution_id)
        if wrapper_path.exists():
            try:
                wrapper_path.unlink()
            except OSError:
                pass


def _random_hex(length: int = 8) -> str:
    """生成一个随机的十六进制字符串，用于临时文件名。"""
    import random
    return "".join(random.choice("0123456789abcdef") for _ in range(length))
