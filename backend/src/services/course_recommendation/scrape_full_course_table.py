#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
手动翻页版：
全校课表截图工具

使用方法：

1. 登录 CAS
2. 进入 TIS
3. 打开【全校课表】
4. 每翻一页按一次回车
5. 自动截图保存

保存位置：

backend/data/tis_downloads/full_course_table/screenshots
"""

import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

INFO = "[!] "
SUCCESS = "[+] "
ERROR = "[x] "

DEFAULT_ZOOM = 0.85


# ============================================================
# backend 根目录
# ============================================================

CURRENT_FILE = Path(__file__).resolve()

# backend/src/services/course_recommendation/xxx.py
# 往上 4 层回到 backend
BACKEND_ROOT = CURRENT_FILE.parents[3]

DATA_DIR = (
    BACKEND_ROOT
    / "data"
    / "tis_download"
    / "full_course_table"
)

SCREENSHOT_DIR = DATA_DIR / "screenshots"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 截图函数
# ============================================================

def save_screenshot(page, index):
    path = SCREENSHOT_DIR / f"page_{index}.png"

    page.screenshot(
        path=str(path),
        full_page=True
    )

    print(f"{SUCCESS} 已保存:")
    print(path)

    return path


# ============================================================
# 主流程
# ============================================================

def main():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )

        context = browser.new_context(
            no_viewport=True
        )

        page = context.new_page()

        print(INFO + "浏览器启动成功")

        print("\n======================================================")
        print("请手动登录 CAS")
        print("然后进入【全校课表】页面")
        print("======================================================\n")

        page.goto(
            "https://tis.sustech.edu.cn",
            wait_until="networkidle"
        )

        # Zoom out slightly so the pagination area is visible.
        page.evaluate(
            "(zoom) => { document.body.style.zoom = String(zoom); }",
            DEFAULT_ZOOM
        )

        input("进入全校课表页面后按回车继续...")

        print("\n======================================================")
        print("开始截图")
        print("规则：")
        print("1. 你手动翻页")
        print("2. 每翻完一页按一次回车")
        print("3. 输入 q 退出")
        print("======================================================\n")

        index = 1

        while True:

            cmd = input(
                f"\n当前准备截图第 {index} 页 "
                f"(直接回车截图 / 输入 q 退出)："
            ).strip().lower()

            if cmd == "q":
                break

            print(INFO + f"正在截图 page_{index}.png")

            try:

                # 等页面稳定
                time.sleep(1.5)

                save_screenshot(page, index)

                print(
                    SUCCESS +
                    f"第 {index} 页截图完成"
                )

                index += 1

            except Exception as e:

                print(ERROR + f"截图失败: {e}")

        print("\n======================================================")
        print(f"{SUCCESS} 全部截图完成")
        print("保存目录:")
        print(SCREENSHOT_DIR)
        print("======================================================\n")

        print(INFO + "关闭浏览器...")

        browser.close()

        print(INFO + "浏览器已关闭")


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    main()