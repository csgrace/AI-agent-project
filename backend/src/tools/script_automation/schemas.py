"""Pydantic parameter models for script automation tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateScriptParams(BaseModel):
    """参数模型：创建自动化脚本"""
    name: str = Field(..., description="脚本名称（唯一标识，不含 .py 后缀）")
    content: str = Field(..., description="脚本 Python 代码内容")
    description: str = Field(default="", description="脚本功能描述")
    category: str = Field(default="general", description="分类标签，如 file_operation / data_process / network")


class ReadScriptParams(BaseModel):
    """参数模型：查看脚本内容"""
    name: str = Field(..., description="脚本名称")


class UpdateScriptParams(BaseModel):
    """参数模型：更新脚本"""
    name: str = Field(..., description="脚本名称")
    content: Optional[str] = Field(default=None, description="新的脚本代码（不传则不修改）")
    description: Optional[str] = Field(default=None, description="新的描述（不传则不修改）")
    category: Optional[str] = Field(default=None, description="新的分类（不传则不修改）")


class DeleteScriptParams(BaseModel):
    """参数模型：删除脚本"""
    name: str = Field(..., description="脚本名称")


class ListScriptsParams(BaseModel):
    """参数模型：列出所有脚本"""
    pass


class ExecuteScriptParams(BaseModel):
    """参数模型：执行脚本"""
    name: str = Field(..., description="脚本名称")
    args: str = Field(default="", description="传递给脚本的命令行参数")


class InstallPackageParams(BaseModel):
    """参数模型：安装 Python 包到沙箱虚拟环境"""
    package_name: str = Field(..., description="包名，支持版本号如 requests==2.31.0")


class ListDirectoryParams(BaseModel):
    """参数模型：列出沙箱工作目录下的文件夹内容（ls）"""
    path: str = Field(default=".", description="要列出内容的目录路径（相对于沙箱目录的路径，或 '.' 表示沙箱根目录）")


class ReadFileParams(BaseModel):
    """参数模型：读取沙箱工作目录下的文件内容（cat）"""
    path: str = Field(..., description="要读取的文件路径（相对于沙箱目录的路径）")
