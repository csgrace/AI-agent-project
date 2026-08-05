---
name: script_automation
description: 创建、管理和执行位于沙箱工作目录中的 Python 自动化脚本。使用 create_script 创建脚本，install_sandbox_package 安装依赖，execute_script 在沙箱中执行。
---

# 脚本自动化（Script Automation）

## 技能描述

本技能指导如何利用沙箱工作目录创建、管理和执行 Python 自动化脚本。所有操作基于用户指定的工作目录，该目录自包含 `.scripts/`（脚本）和 `.venv/`（虚拟环境）。

## 前置条件

用户必须先通过 `set_script_sandbox_dir()` 设置沙箱工作目录。

## 工作流程

1. **创建脚本**
   - 使用 `create_script` 创建新的 Python 脚本
   - 指定脚本名称、代码内容、描述和分类
   - 脚本自动保存到 `{sandbox_dir}/.scripts/{name}.py`

2. **安装依赖（可选）**
   - 使用 `install_sandbox_package` 安装第三方包
   - 包安装在沙箱的 `.venv/` 中，不影响项目环境

3. **查看和管理脚本**
   - `list_scripts` — 列出所有脚本
   - `read_script` — 查看脚本源码和元数据
   - `update_script` — 修改脚本内容或描述
   - `delete_script` — 删除脚本

4. **执行脚本**
   - 使用 `execute_script` 在沙箱中执行脚本
   - 脚本运行在隔离环境，不能访问沙箱外的文件
   - 危险模块（subprocess/ctypes 等）被禁止

5. **独立运行（脱离 Agent）**
   - 脚本可通过终端直接运行：
   ```
   cd {sandbox_dir}
   .venv/Scripts/python .scripts/{name}.py
   ```

## 安全限制

- 脚本只能读写沙箱目录内的文件
- subprocess, ctypes, winreg, socket 等模块被禁止导入
- 脚本最多执行 60 秒
- eval() 函数被禁用
