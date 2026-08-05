"""Tests for script_automation sandbox — safety, wrapper_builder, and storage."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.global_state import set_script_sandbox_dir, get_script_sandbox_dir
from src.tools.script_automation.safety import (
    BLOCKED_MODULES,
    MAX_EXECUTION_TIME,
    MAX_OUTPUT_CHARS,
    scan_for_dangerous_patterns,
    validate_path,
    get_sandbox_dir,
)
from src.tools.script_automation.wrapper_builder import build_wrapper
from src.tools.script_automation.storage import (
    create_script_file,
    read_script_file,
    update_script_file,
    delete_script_file,
    list_script_files,
    get_script_path,
)
from src.tools.script_automation.schemas import (
    ListDirectoryParams,
    ReadFileParams,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def sandbox_dir(tmp_path: Path) -> Path:
    """Create a temporary sandbox directory and set it in global_state."""
    sb_dir = tmp_path / "sandbox"
    sb_dir.mkdir()
    set_script_sandbox_dir(str(sb_dir))
    yield sb_dir
    set_script_sandbox_dir("")


@pytest.fixture
def sample_script_content() -> str:
    return """
def main():
    return "hello"

if __name__ == "__main__":
    result = main()
    print(result)
"""


# =========================================================================
# safety.py — path validation
# =========================================================================


class TestValidatePath:
    def test_allowed_relative_path(self, sandbox_dir: Path):
        """相对路径在沙箱内应该通过。"""
        result = validate_path("subdir/file.txt", sandbox_dir=sandbox_dir)
        expected = str((sandbox_dir / "subdir" / "file.txt").resolve())
        assert result == expected

    def test_allowed_absolute_path_inside(self, sandbox_dir: Path):
        """沙箱内的绝对路径应该通过。"""
        target = sandbox_dir / "file.txt"
        target.touch()
        result = validate_path(str(target.resolve()), sandbox_dir=sandbox_dir)
        assert result == str(target.resolve())

    def test_blocked_path_traversal(self, sandbox_dir: Path):
        """../ 路径穿越应该被阻止。"""
        with pytest.raises(PermissionError, match="访问被拒绝"):
            validate_path("../../outside.txt", sandbox_dir=sandbox_dir)

    def test_blocked_absolute_path_outside(self, sandbox_dir: Path):
        """沙箱外的绝对路径应该被阻止。"""
        with pytest.raises(PermissionError, match="访问被拒绝"):
            if sys.platform == "win32":
                validate_path("C:\\Windows\\system32\\config", sandbox_dir=sandbox_dir)
            else:
                validate_path("/etc/passwd", sandbox_dir=sandbox_dir)

    def test_blocked_dot_dot_dot(self, sandbox_dir: Path):
        """复杂路径穿越应该被阻止。"""
        with pytest.raises(PermissionError, match="访问被拒绝"):
            validate_path("subdir/../../../etc/passwd", sandbox_dir=sandbox_dir)

    def test_get_sandbox_dir_not_set(self):
        """未设置沙箱目录时应该抛出 ValueError。"""
        set_script_sandbox_dir("")
        with pytest.raises(ValueError, match="not set"):
            get_sandbox_dir()


# =========================================================================
# safety.py — static analysis (scan_for_dangerous_patterns)
# =========================================================================


class TestScanForDangerousPatterns:
    def test_clean_code_no_issues(self):
        """干净的代码不应该有安全问题。"""
        code = """
import json
import os

def main():
    print("hello")
"""
        issues = scan_for_dangerous_patterns(code)
        assert issues == []

    def test_detect_blocked_import(self):
        """应该检测到黑名单模块的导入。"""
        code = 'import subprocess\n'
        issues = scan_for_dangerous_patterns(code)
        assert any(
            iss["severity"] == "danger" and "subprocess" in iss["message"]
            for iss in issues
        )

    def test_detect_blocked_from_import(self):
        """应该检测到 from ... import 黑名单模块。"""
        code = 'from subprocess import Popen\n'
        issues = scan_for_dangerous_patterns(code)
        assert any(
            iss["severity"] == "danger" and "subprocess" in iss["message"]
            for iss in issues
        )

    @pytest.mark.parametrize("module_name", BLOCKED_MODULES)
    def test_detect_all_blocked_modules(self, module_name: str):
        """所有黑名单模块都应该被检测到。"""
        code = f'import {module_name}\n'
        issues = scan_for_dangerous_patterns(code)
        assert any(module_name in iss["message"] for iss in issues), (
            f"未检测到黑名单模块: {module_name}"
        )

    @pytest.mark.parametrize("func_name,code", [
        ("eval", 'eval("print(1)")\n'),
        ("exec", 'exec("print(1)")\n'),
        ("compile", 'compile("1+1", "", "eval")\n'),
    ])
    def test_detect_dangerous_function_call(self, func_name: str, code: str):
        """应该检测到 eval/exec/compile 调用。"""
        issues = scan_for_dangerous_patterns(code)
        assert any(
            iss["severity"] == "critical" and func_name in iss["message"]
            for iss in issues
        ), f"未检测到危险函数: {func_name}"

    def test_syntax_error_returns_error(self):
        """语法错误的代码应该返回 error 级别的问题。"""
        code = "def broken(\n"
        issues = scan_for_dangerous_patterns(code)
        assert any(iss["severity"] == "error" for iss in issues)

    def test_importlib_not_false_positive(self):
        """importlib 不在黑名单中，不应该被标记。"""
        code = "import importlib\n"
        issues = scan_for_dangerous_patterns(code)
        assert not any(
            "importlib" in iss["message"] for iss in issues
        )


# =========================================================================
# wrapper_builder.py — generated wrapper code inspection
# =========================================================================


class TestBuildWrapper:
    """验证生成的包装器代码结构。"""

    def test_contains_all_security_layers(self, tmp_path: Path):
        """生成的包装器应该包含全部 9 个安全策略。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        for i in range(1, 10):
            assert f"安全策略 {i}" in wrapper, f"缺少安全策略 {i}"

    def test_contains_sandbox_dir(self, tmp_path: Path):
        """应该包含沙箱目录路径（在 _SANDBOX_DIR 赋值中）。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_SANDBOX_DIR" in wrapper
        # tmp_path 在 Windows 上用 repr() 转义了反斜杠，用 os.path 规范化后匹配
        assert str(tmp_path.resolve()).replace("\\", "\\\\") in wrapper or \
               str(tmp_path.resolve()) in wrapper

    def test_contains_blocked_modules(self, tmp_path: Path):
        """应该包含黑名单模块列表。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        for mod in BLOCKED_MODULES:
            assert mod in wrapper, f"包装器中缺少黑名单模块: {mod}"

    def test_contains_script_path(self, tmp_path: Path):
        """应该包含用户脚本路径（在 _script_path 赋值中）。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_script_path" in wrapper
        assert str(script_path.resolve()).replace("\\", "\\\\") in wrapper or \
               str(script_path.resolve()) in wrapper

    def test_disabled_os_system(self, tmp_path: Path):
        """os.system 应该被设为 None。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "os.system" in wrapper or "_PATCHED_OS.system = None" in wrapper

    def test_disabled_os_popen(self, tmp_path: Path):
        """os.popen 应该被设为 None。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_PATCHED_OS.popen = None" in wrapper

    def test_contains_safe_rename(self, tmp_path: Path):
        """应该包含安全的 os.rename。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_safe_rename" in wrapper
        assert "_PATCHED_OS.rename = _safe_rename" in wrapper

    def test_contains_safe_os_open(self, tmp_path: Path):
        """应该包含安全的 os.open。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_safe_os_open" in wrapper
        assert "_PATCHED_OS.open = _safe_os_open" in wrapper

    def test_contains_safe_remove_unlink(self, tmp_path: Path):
        """应该包含安全的 os.remove 和 os.unlink。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_PATCHED_OS.remove = _safe_os_remove" in wrapper
        assert "_PATCHED_OS.unlink = _safe_os_unlink" in wrapper

    def test_contains_safe_chdir(self, tmp_path: Path):
        """应该包含安全的 os.chdir。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_PATCHED_OS.chdir = _safe_os_chdir" in wrapper

    def test_contains_symlink_patch(self, tmp_path: Path):
        """应该包含安全的 os.symlink。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_PATCHED_OS.symlink = _safe_os_symlink" in wrapper

    def test_contains_shutil_move_and_rmtree(self, tmp_path: Path):
        """应该包含 shutil.move 和 shutil.rmtree 的修补。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_PATCHED_SHUTIL.move = _safe_shutil_move" in wrapper
        assert "_PATCHED_SHUTIL.rmtree = _safe_shutil_rmtree" in wrapper

    def test_contains_eval_disabled(self, tmp_path: Path):
        """应该禁用 eval。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_builtins.eval = None" in wrapper

    def test_contains_safe_builtins_open(self, tmp_path: Path):
        """应该包含安全的 builtins.open。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_safe_open" in wrapper
        assert "_builtins.open = _safe_open" in wrapper

    def test_contains_input_disabled(self, tmp_path: Path):
        """应该禁用 input。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_builtins.input = lambda" in wrapper

    def test_contains_audit_hook(self, tmp_path: Path):
        """应该包含 audit hook。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "_sandbox_audit_hook" in wrapper
        assert "addaudithook" in wrapper

    def test_contains_hasattr_guard(self, tmp_path: Path):
        """audit hook 应该有 hasattr 保护（Python 3.7 兼容）。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "hasattr(_sys, \"addaudithook\")" in wrapper

    def test_contains_exec_user_script(self, tmp_path: Path):
        """包装器最后应该执行用户脚本。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "exec(_code, _global_vars)" in wrapper

    def test_wrapper_starts_with_imports(self, tmp_path: Path):
        """包装器应该以必要的 import 开头。"""
        script_path = tmp_path / ".scripts" / "test.py"
        script_path.parent.mkdir(parents=True)
        script_path.write_text("print('hello')")
        wrapper = build_wrapper(script_path, tmp_path)

        assert "import sys as _sys" in wrapper
        assert "import builtins as _builtins" in wrapper
        assert "import os as _real_os" in wrapper


# =========================================================================
# storage.py — CRUD operations
# =========================================================================


class TestStorage:
    """测试脚本文件的存储管理。"""

    def test_create_and_read_script(self, sandbox_dir: Path, sample_script_content: str):
        """创建后应该能读取到内容和元数据。"""
        msg = create_script_file(
            name="test_hello",
            content=sample_script_content,
            description="A test script",
            category="test",
        )
        assert "创建成功" in msg

        content, metadata = read_script_file("test_hello")
        assert content == sample_script_content
        assert metadata["name"] == "test_hello"
        assert metadata["description"] == "A test script"
        assert metadata["category"] == "test"
        assert "created_at" in metadata
        assert "updated_at" in metadata

    def test_create_duplicate_raises(self, sandbox_dir: Path, sample_script_content: str):
        """重复创建应该抛出 ValueError。"""
        create_script_file("dup", sample_script_content)
        with pytest.raises(ValueError, match="已存在"):
            create_script_file("dup", sample_script_content)

    def test_create_invalid_name_raises(self, sandbox_dir: Path, sample_script_content: str):
        """不合法的脚本名应该抛出 ValueError。"""
        with pytest.raises(ValueError, match="不合法"):
            create_script_file("../escape", sample_script_content)

    def test_read_nonexistent_raises(self, sandbox_dir: Path):
        """读取不存在的脚本应该抛出 ValueError。"""
        with pytest.raises(ValueError, match="不存在"):
            read_script_file("nonexistent")

    def test_update_content(self, sandbox_dir: Path, sample_script_content: str):
        """应该能更新脚本内容。"""
        create_script_file("update_test", sample_script_content)
        new_content = 'print("updated")\n'
        msg = update_script_file("update_test", content=new_content)
        assert "更新成功" in msg
        assert "内容" in msg

        content, _ = read_script_file("update_test")
        assert content == new_content

    def test_update_metadata(self, sandbox_dir: Path, sample_script_content: str):
        """应该能更新脚本的元数据。"""
        create_script_file("meta_test", sample_script_content, description="old", category="old_cat")
        update_script_file("meta_test", description="new desc", category="new_cat")

        _, metadata = read_script_file("meta_test")
        assert metadata["description"] == "new desc"
        assert metadata["category"] == "new_cat"

    def test_update_nonexistent_raises(self, sandbox_dir: Path):
        """更新不存在的脚本应该抛出 ValueError。"""
        with pytest.raises(ValueError, match="不存在"):
            update_script_file("nonexistent", content="x")

    def test_delete_script(self, sandbox_dir: Path, sample_script_content: str):
        """删除后脚本文件应该消失。"""
        create_script_file("to_delete", sample_script_content)
        msg = delete_script_file("to_delete")
        assert "已删除" in msg

        with pytest.raises(ValueError, match="不存在"):
            read_script_file("to_delete")

    def test_delete_nonexistent_raises(self, sandbox_dir: Path):
        """删除不存在的脚本应该抛出 ValueError。"""
        with pytest.raises(ValueError, match="不存在"):
            delete_script_file("nonexistent")

    def test_list_scripts(self, sandbox_dir: Path, sample_script_content: str):
        """列出脚本应该包含所有已创建的脚本。"""
        create_script_file("alpha", sample_script_content, description="first", category="demo")
        create_script_file("beta", sample_script_content, description="second", category="demo")
        listing = list_script_files()
        assert "alpha" in listing
        assert "beta" in listing
        assert "first" in listing
        assert "second" in listing

    def test_list_scripts_empty(self, sandbox_dir: Path):
        """空沙箱应该返回提示信息。"""
        listing = list_script_files()
        assert "没有" in listing or "可用" in listing

    def test_get_script_path(self, sandbox_dir: Path, sample_script_content: str):
        """get_script_path 应该返回正确的路径。"""
        create_script_file("path_test", sample_script_content)
        path = get_script_path("path_test")
        assert path.exists()
        assert path.name == "path_test.py"
        assert path.parent.name == ".scripts"

    def test_get_script_path_nonexistent_raises(self, sandbox_dir: Path):
        """不存在的脚本应该抛出 ValueError。"""
        with pytest.raises(ValueError, match="不存在"):
            get_script_path("nonexistent")

    def test_scripts_dir_created_automatically(self, sandbox_dir: Path, sample_script_content: str):
        """创建脚本时 .scripts/ 目录应该自动生成。"""
        scripts_dir = sandbox_dir / ".scripts"
        assert not scripts_dir.exists()
        create_script_file("auto_dir", sample_script_content)
        assert scripts_dir.is_dir()

    def test_metadata_persists_across_operations(self, sandbox_dir: Path, sample_script_content: str):
        """元数据应该在多次操作间保持一致。"""
        create_script_file("persist", sample_script_content, description="original", category="test")
        update_script_file("persist", description="modified")
        _, metadata = read_script_file("persist")
        assert metadata["description"] == "modified"
        assert metadata["category"] == "test"


# =========================================================================
# Constants verification
# =========================================================================


class TestConstants:
    def test_execution_time_limit(self):
        """超时时间应为 60 秒。"""
        assert MAX_EXECUTION_TIME == 60

    def test_output_chars_limit(self):
        """输出截断长度应为 5000 字符。"""
        assert MAX_OUTPUT_CHARS == 5000

    def test_blocked_modules_list(self):
        """黑名单模块列表应该有关键模块。"""
        assert "subprocess" in BLOCKED_MODULES
        assert "ctypes" in BLOCKED_MODULES
        assert "socket" in BLOCKED_MODULES
        assert "multiprocessing" in BLOCKED_MODULES

    def test_output_truncation_tail_based(self):
        """截断应保留尾部而非头部。"""
        from src.tools.script_automation import executor
        import inspect
        source = inspect.getsource(executor)
        # 截断使用 stdout[-MAX_OUTPUT_CHARS:]（保留尾部）
        assert "stdout[-MAX_OUTPUT_CHARS:]" in source, "stdout 截断应为尾截断"
        assert "stderr[-MAX_OUTPUT_CHARS:]" in source, "stderr 截断应为尾截断"
        # 截断提示包含"末尾"字样
        assert "仅显示末尾" in source
        # 常量值合理
        assert MAX_OUTPUT_CHARS > 100
        assert MAX_OUTPUT_CHARS <= 50000


# =========================================================================
# list_sandbox_directory / read_sandbox_file 文件系统查看工具
# =========================================================================


class TestListSandboxDirectory:
    """测试 list_sandbox_directory（ls）工具"""

    def _call_ls(self, params: ListDirectoryParams) -> dict:
        """通过 .func 调用 @tool 装饰的底层函数。"""
        from src.tools.script_automation.tool import list_sandbox_directory as tool
        return json.loads(tool.func(params))

    def test_list_root(self, sandbox_dir: Path):
        """列出沙箱根目录，应包含 .scripts/ 目录。"""
        # 先触发一次脚本操作，生成 .scripts/ 目录
        from src.tools.script_automation.storage import _get_scripts_dir
        _get_scripts_dir()

        result = self._call_ls(ListDirectoryParams(path="."))
        assert result["ok"] is True
        assert result["action"] == "list_directory"
        assert isinstance(result["entries"], list)
        names = [e["name"] for e in result["entries"]]
        assert ".scripts" in names

    def test_list_subdirectory(self, sandbox_dir: Path):
        """列出 .scripts/ 子目录。"""
        from src.tools.script_automation.storage import _get_scripts_dir
        scripts_dir = _get_scripts_dir()
        assert scripts_dir.exists()

        result = self._call_ls(ListDirectoryParams(path=".scripts"))
        assert result["ok"] is True
        entries = result["entries"]
        assert isinstance(entries, list)

    def test_list_nonexistent_path(self, sandbox_dir: Path):
        """不存在的路径应返回错误。"""
        result = self._call_ls(ListDirectoryParams(path="nonexistent_folder"))
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_list_path_is_file(self, sandbox_dir: Path):
        """路径是文件而非目录应返回错误。"""
        (sandbox_dir / "test.txt").write_text("hello", encoding="utf-8")

        result = self._call_ls(ListDirectoryParams(path="test.txt"))
        assert result["ok"] is False
        assert "不是目录" in result["error"]

    def test_list_outside_sandbox(self, sandbox_dir: Path):
        """路径越界应返回错误。"""
        result = self._call_ls(ListDirectoryParams(path="../outside"))
        assert result["ok"] is False
        assert "访问被拒绝" in result["error"]


class TestReadSandboxFile:
    """测试 read_sandbox_file（cat）工具"""

    def _call_cat(self, params: ReadFileParams) -> dict:
        """通过 .func 调用 @tool 装饰的底层函数。"""
        from src.tools.script_automation.tool import read_sandbox_file as tool
        return json.loads(tool.func(params))

    def test_read_text_file(self, sandbox_dir: Path):
        """读取沙箱内的文本文件。"""
        content = "Hello, World!\n第二行"
        (sandbox_dir / "test.txt").write_text(content, encoding="utf-8")

        result = self._call_cat(ReadFileParams(path="test.txt"))
        assert result["ok"] is True
        assert result["action"] == "read_file"
        assert result["content"] == content
        assert result["size"] == (sandbox_dir / "test.txt").stat().st_size
        assert result["truncated"] is False

    def test_read_nonexistent_file(self, sandbox_dir: Path):
        """不存在的文件应返回错误。"""
        result = self._call_cat(ReadFileParams(path="nope.txt"))
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_read_directory_as_file(self, sandbox_dir: Path):
        """路径是目录而非文件应返回错误。"""
        result = self._call_cat(ReadFileParams(path="."))
        assert result["ok"] is False
        assert "不是文件" in result["error"]

    def test_read_outside_sandbox(self, sandbox_dir: Path):
        """路径越界应返回错误。"""
        result = self._call_cat(
            ReadFileParams(path="../../windows/system32/drivers/etc/hosts")
        )
        assert result["ok"] is False
        assert "访问被拒绝" in result["error"]

    def test_read_large_file_truncated(self, sandbox_dir: Path):
        """大文件应被截断。"""
        large_content = "A" * 12000
        (sandbox_dir / "large.txt").write_text(large_content, encoding="utf-8")

        result = self._call_cat(ReadFileParams(path="large.txt"))
        assert result["ok"] is True
        assert result["truncated"] is True
        assert len(result["content"]) < 12000
        assert "已截断" in result["content"]
