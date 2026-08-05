import json
import os
import re
import time
import signal
import sys
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from dotenv import load_dotenv
load_dotenv()

SUCCESS = "[+] "
ERROR = "[x] "
INFO = "[!] "
DEBUG = "[~] "
WARNING = "[*] "


CREDENTIALS_DIR = os.path.join(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    ),
    "credentials"
)

PROFILE_PATH = os.path.join(
    CREDENTIALS_DIR,
    "profile.json"
)

_browser_manager = None


def signal_handler(signum, frame):
    print(f"\n{INFO}收到中断信号，正在清理资源...")
    global _browser_manager
    if _browser_manager:
        try:
            _browser_manager.close()
        except:
            pass
    print(f"{INFO}程序退出")
    sys.exit(0)


def load_profile():
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TISBrowser:
    """TIS 浏览器管理器"""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """启动浏览器"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False,
                slow_mo=300,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-gpu',
                    '--window-position=0,0',
                    '--window-size=1280,900',
                ]
            )
            self.context = self.browser.new_context(
                accept_downloads=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 900},
            )
            self.page = self.context.new_page()

            self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
            """)

            print(f"{INFO}浏览器启动成功 (1280x900)")
            return self.page
        except Exception as e:
            print(f"{ERROR}浏览器启动失败: {e}")
            time.sleep(3)
            raise

    def close(self):
        """关闭浏览器"""
        print(f"{INFO}关闭浏览器...")
        try:
            if self.browser:
                self.browser.close()
        except:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except:
            pass
        print(f"{INFO}浏览器已关闭")


def _remove_browser_warning(page):
    """移除 TIS 的'浏览器过时'警告弹窗 + 关闭可能遮挡内容的弹窗/模态框"""
    try:
        # 1) 关闭常见的弹窗/模态框（包括学籍编辑弹窗）
        page.evaluate("""
            () => {
                // 关闭 iView Modal / Element UI Dialog / Ant Design Modal
                const closeSelectors = [
                    '.ivu-modal-close',
                    '.el-dialog__close',
                    '.el-message-box__close',
                    '.ant-modal-close',
                    '.ivu-modal-footer .ivu-btn',
                    '.el-dialog__footer .el-button',
                    'button:has-text("取消")',
                    'button:has-text("关闭")',
                    'button:has-text("×")',
                    '[class*="close"]',
                ];
                closeSelectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        if (el.offsetParent !== null) {
                            el.click();
                        }
                    });
                });

                // 移除浏览器警告元素
                const allElements = document.querySelectorAll('div, section, article, aside');
                for (const el of allElements) {
                    const text = (el.innerText || '').trim();
                    if ((text.includes('浏览器已经过时') || text.includes('浏览器过时')) && text.length < 500) {
                        if (el.children.length < 10) {
                            el.remove();
                        }
                    }
                }

                // 移除遮罩层
                const masks = document.querySelectorAll('[class*="mask"], [class*="overlay"]');
                masks.forEach(mask => {
                    const text = (mask.innerText || '').toLowerCase();
                    if (text.includes('浏览器')) {
                        mask.remove();
                    }
                });

                document.body.style.overflow = '';
                document.body.style.position = '';
            }
        """)

        page.wait_for_timeout(800)

    except Exception:
        pass


def _scroll_to_element(page, element):
    """滚动到元素可见"""
    try:
        element.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
    except:
        pass


def _wait_for_stable_content(page, timeout=15):
    """等待页面内容稳定（持续 2 秒无变化）"""
    start = time.time()
    last_text = ""
    stable_count = 0

    while time.time() - start < timeout:
        try:
            current = page.evaluate("() => document.body.innerText")
        except:
            time.sleep(1)
            continue

        if current == last_text:
            stable_count += 1
            if stable_count >= 3:
                return True
        else:
            stable_count = 0
            last_text = current

        time.sleep(0.8)

    return False


def login():
    """登录 TIS，下载课表，然后爬取学业修读情况和学籍信息"""

    global _browser_manager

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    download_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../../../data/tis_download"
        )
    )

    os.makedirs(download_dir, exist_ok=True)
    schedule_dir = os.path.join(download_dir, "course_schedule")
    os.makedirs(schedule_dir, exist_ok=True)

    _browser_manager = TISBrowser()
    browser_manager = _browser_manager
    save_path = None

    try:
        page = browser_manager.start()

        # ==========================================
        # 步骤 1: 登录 TIS
        # ==========================================
        print(f"\n{INFO}打开 TIS...")
        page.goto("https://tis.sustech.edu.cn/", wait_until="networkidle")
        _remove_browser_warning(page)

        print()
        print("=" * 60)
        print("请手动登录 CAS")
        print("=" * 60)

        page.wait_for_function(
            "() => window.location.href.includes('authentication')",
            timeout=300000
        )

        print(f"{SUCCESS}登录成功")
        page.wait_for_timeout(3000)
        _remove_browser_warning(page)

        # ==========================================
        # 步骤 2: 下载当前学期课表
        # ==========================================
        print(f"\n{INFO}正在进入课表页面...")
        page.get_by_text("课表").first.click()
        page.wait_for_timeout(5000)
        print(f"{SUCCESS}已进入课表页面")
        _remove_browser_warning(page)

        print(f"{INFO}正在下载课表 Excel...")
        with page.expect_download() as download_info:
            page.get_by_text("导出").first.click()
            page.wait_for_timeout(1000)
            page.get_by_text("Excel").first.click()

        download = download_info.value
        save_path = os.path.join(schedule_dir, download.suggested_filename)
        download.save_as(save_path)
        print(f"{SUCCESS}课表已下载: {save_path}")

        # ==========================================
        # 步骤 3: 学业修读情况
        # ==========================================
        page.goto("https://tis.sustech.edu.cn/authentication/main", wait_until="networkidle")
        page.wait_for_timeout(3000)
        _remove_browser_warning(page)

        print("\n" + "=" * 60)
        print(f"{INFO}下一步：学业修读情况查询")
        print("=" * 60)
        print("请在浏览器中手动点击: 业务查询 → 学业修读情况查询")
        print("⚠️  如果页面弹出一个【编辑/填写信息】的窗口，请先点击【取消】或【关闭】把它关掉！")
        print()
        input("打开学业修读情况页面后，按回车继续爬取...")

        # 关闭可能弹出的编辑窗口
        _remove_browser_warning(page)
        print(f"{INFO}等待页面内容稳定...")
        _wait_for_stable_content(page, timeout=15)
        page.wait_for_timeout(3000)

        # 再次尝试关闭弹窗
        _remove_browser_warning(page)
        page.wait_for_timeout(2000)

        _extract_page_data(page, download_dir, "academic_progress", "学业修读情况")

        # ==========================================
        # 步骤 4: 学籍信息
        # ==========================================
        print("\n" + "=" * 60)
        print(f"{INFO}下一步：学籍信息")
        print("=" * 60)
        print("请在浏览器中手动操作：")
        print("  1. 点击菜单: 学籍信息 → 学籍卡片/基本信息")
        print("  2. ⚠️ 如果有弹窗，请点击【取消】或【关闭】关掉它！")
        print("  3. 确保能看到学籍信息表格后，按回车")
        print()
        input("打开学籍信息页面后，按回车继续...")

        _remove_browser_warning(page)
        print(f"{INFO}等待页面内容稳定...")
        _wait_for_stable_content(page, timeout=15)
        page.wait_for_timeout(3000)

        _remove_browser_warning(page)
        page.wait_for_timeout(2000)

        # 先提取页面上的学籍信息
        _extract_page_data(page, download_dir, "student_info", "学籍信息")

        # 自动查找并点击"查看学籍卡"按钮
        _click_student_card_button(page, download_dir)

        print(f"\n{SUCCESS}所有数据爬取完成！")
        print(f"{INFO}数据保存在: {download_dir}")
        print(f"  - 课表: {schedule_dir}/")
        print(f"  - 学业修读情况: {download_dir}/academic_progress_*.json")
        print(f"  - 学籍信息: {download_dir}/student_info_*.json")
        print(f"  - 学籍卡(如有下载): {download_dir}/student_card_*.*")

        input("\n按回车关闭浏览器...")

        return save_path

    except KeyboardInterrupt:
        print(f"\n{INFO}用户中断操作")
        return save_path
    except Exception as e:
        print(f"{ERROR}执行过程中出错: {e}")
        import traceback
        traceback.print_exc()
        input("按回车关闭浏览器...")
        return save_path
    finally:
        browser_manager.close()
        _browser_manager = None
        print(f"{INFO}程序结束")


def download_all_term_schedules() -> list[dict[str, str]]:
    """下载所有学期的课表"""
    from ...services.course_recommendation.excel_parser import parse_schedule_excel

    global _browser_manager

    download_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../../../data/tis_download"
        )
    )

    schedule_dir = os.path.join(download_dir, "course_schedule")
    os.makedirs(schedule_dir, exist_ok=True)

    results: list[dict[str, str]] = []
    _browser_manager = TISBrowser()
    browser_manager = _browser_manager

    try:
        page = browser_manager.start()

        print(f"\n{INFO}打开 TIS...")
        page.goto("https://tis.sustech.edu.cn/", wait_until="networkidle")
        _remove_browser_warning(page)

        print()
        print("=" * 60)
        print("请手动登录 CAS")
        print("=" * 60)

        page.wait_for_function(
            "() => window.location.href.includes('authentication')",
            timeout=300000
        )

        print(f"{SUCCESS}登录成功")
        page.wait_for_timeout(3000)
        _remove_browser_warning(page)

        print(f"{INFO}进入课表页面...")
        page.get_by_text("课表").first.click()
        page.wait_for_timeout(5000)
        _remove_browser_warning(page)
        print(f"{SUCCESS}已进入课表页面")

        print("\n" + "=" * 60)
        print(f"{INFO}下载所有学期课表")
        print("=" * 60)
        print("操作说明：")
        print("  1. 当前学期课表会先自动下载")
        print("  2. 每次下载后你可以手动输入课表名字")
        print("  3. 你切换到下一个学期后，程序再继续下载")
        print("  4. 输入 'done' 结束课表下载，随后继续学业修读情况等步骤")
        print()

        while True:
            _remove_browser_warning(page)
            print(f"{INFO}正在下载当前学期课表...")

            try:
                with page.expect_download(timeout=30000) as download_info:
                    page.get_by_text("导出").first.click()
                    page.wait_for_timeout(1000)
                    page.get_by_text("Excel").first.click()

                download = download_info.value

                term_label = page.evaluate("""
                    () => {
                        const selectors = [
                            '.ivu-select-selection span',
                            '.ivu-select-selected-value',
                            '[class*="term"]',
                            '[class*="semester"]',
                        ];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent.trim()) {
                                const text = el.textContent.trim();
                                const match = text.match(/(\\d{4}).*(春季|夏季|秋季|暑期|第.*学期)/);
                                if (match) return match[0];
                                return text.substring(0, 50);
                            }
                        }
                        return 'unknown_term';
                    }
                """)

                default_name = _sanitize_term_label(term_label)
                user_name = input(
                    f"{INFO}请输入课表名字，直接回车使用 '{default_name}': "
                ).strip()

                saved_name = user_name or default_name
                sanitized = _sanitize_term_label(saved_name)
                excel_path = os.path.join(schedule_dir, f"{sanitized}.xlsx")
                download.save_as(excel_path)
                print(f"{SUCCESS}已下载: {excel_path}")

                meetings = parse_schedule_excel(excel_path)
                if meetings:
                    json_path = os.path.join(schedule_dir, f"{sanitized}.json")
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "term_label": saved_name,
                                "meetings": meetings,
                            },
                            f, ensure_ascii=False, indent=2
                        )
                    print(f"{SUCCESS}已保存 JSON: {json_path}")
                    results.append({
                        "term_label": saved_name,
                        "excel_path": excel_path,
                        "json_path": json_path,
                    })
                else:
                    print(f"{WARNING}课表为空，删除 Excel")
                    os.remove(excel_path)

            except Exception as e:
                print(f"{ERROR}下载失败: {e}")

            continue_input = input(
                f"{INFO}是否继续爬取下一个课表？(y/N): "
            ).strip().lower()

            if continue_input not in {"y", "yes"}:
                break

            print(f"{INFO}请在浏览器中手动切换到下一个学期课表，然后按回车继续...")
            input("切换完成后按回车继续: ")

        # 爬取学业修读情况
        page.goto("https://tis.sustech.edu.cn/authentication/main", wait_until="networkidle")
        page.wait_for_timeout(3000)
        _remove_browser_warning(page)

        print("\n" + "=" * 60)
        print(f"{INFO}下一步：学业修读情况查询")
        print("=" * 60)
        print("请在浏览器中手动点击: 业务查询 → 学业修读情况查询")
        print("⚠️  如果弹出编辑窗口，请先点击【取消】关掉！")
        input("\n打开后按回车继续爬取...")

        _remove_browser_warning(page)
        _wait_for_stable_content(page, timeout=15)
        page.wait_for_timeout(3000)
        _remove_browser_warning(page)
        page.wait_for_timeout(2000)

        _extract_page_data(page, download_dir, "academic_progress", "学业修读情况")

        input("\n按回车关闭浏览器...")

    except KeyboardInterrupt:
        print(f"\n{INFO}用户中断操作")
    except Exception as e:
        print(f"{ERROR}执行过程中出错: {e}")
        import traceback
        traceback.print_exc()
        input("按回车关闭浏览器...")
    finally:
        browser_manager.close()
        _browser_manager = None
        print(f"{INFO}程序结束")

    return results


def _click_student_card_button(page, download_dir: str):
    """
    自动查找并点击'查看学籍卡'按钮，下载学籍卡文件。
    会先关闭所有弹窗，再尝试点击按钮。
    """
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"{INFO}正在准备查找'查看学籍卡'按钮...")

    # 先关闭所有弹窗
    _remove_browser_warning(page)
    page.wait_for_timeout(1500)

    # 再次确认没有弹窗
    _remove_browser_warning(page)
    page.wait_for_timeout(1500)

    print(f"{INFO}开始查找'查看学籍卡'按钮...")

    button_selectors = [
        "button:has-text('查看学籍卡')",
        "button:has-text('学籍卡片')",
        "a:has-text('查看学籍卡')",
        "a:has-text('学籍卡片')",
        "button:has-text('学籍卡')",
        "a:has-text('学籍卡')",
        "button:has-text('下载学籍卡')",
        "a:has-text('下载学籍卡')",
        "button:has-text('打印学籍卡')",
        "a:has-text('打印学籍卡')",
        "[title*='学籍卡']",
        "span:has-text('查看学籍卡')",
        "span:has-text('学籍卡片')",
    ]

    clicked = False

    for selector in button_selectors:
        try:
            elements = page.locator(selector)
            count = elements.count()

            for i in range(count):
                el = elements.nth(i)

                if not el.is_visible():
                    _scroll_to_element(page, el)
                    page.wait_for_timeout(500)

                if el.is_visible():
                    text = el.inner_text() if hasattr(el, 'inner_text') else ''
                    print(f"{INFO}找到按钮: '{text}' ({selector})")

                    try:
                        # ⭐ 方法1：监听下载事件
                        with page.expect_download(timeout=15000) as download_info:
                            el.click()

                        download = download_info.value
                        ext = download.suggested_filename.split('.')[-1] if '.' in download.suggested_filename else 'pdf'
                        save_path = os.path.join(download_dir, f"student_card_{timestamp}.{ext}")
                        download.save_as(save_path)
                        print(f"{SUCCESS}学籍卡已下载: {save_path}")
                        clicked = True
                        break

                    except PlaywrightTimeout:
                        # ⭐ 方法2：没有触发下载，检查是否打开了新标签页
                        print(f"{INFO}未触发下载，检查是否打开新页面...")
                        page.wait_for_timeout(2000)

                        if len(page.context.pages) > 1:
                            new_page = page.context.pages[-1]
                            new_page.wait_for_load_state("networkidle")
                            new_page.bring_to_front()
                            print(f"{INFO}检测到新页面: {new_page.url}")

                            # 在新页面上也关闭弹窗
                            _remove_browser_warning(new_page)
                            new_page.wait_for_timeout(2000)

                            _extract_page_data(new_page, download_dir, "student_card", "学籍卡")
                            clicked = True
                            break

                    except Exception as e:
                        print(f"{DEBUG}点击 {selector} 异常: {e}")
                        continue

            if clicked:
                break

        except Exception:
            continue

    if not clicked:
        # ⭐ 方法3：使用 JavaScript 查找所有可点击元素
        print(f"{INFO}使用 JavaScript 深度搜索学籍卡按钮...")

        js_result = page.evaluate("""
            () => {
                const keywords = ['学籍卡', '查看学籍', '学籍卡片', '下载学籍', '打印学籍'];

                // 遍历所有元素
                const allElements = document.querySelectorAll('button, a, span, div, li');
                for (const el of allElements) {
                    const text = (el.textContent || '').trim();
                    for (const kw of keywords) {
                        if (text.includes(kw) && text.length < 30) {
                            // 确保元素可见
                            if (el.offsetParent !== null) {
                                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                el.click();
                                return { found: true, text: text, tag: el.tagName };
                            }
                        }
                    }
                }

                // 如果没找到可见的，也尝试不可见的
                for (const el of allElements) {
                    const text = (el.textContent || '').trim();
                    for (const kw of keywords) {
                        if (text.includes(kw) && text.length < 30) {
                            el.style.display = 'block';
                            el.style.visibility = 'visible';
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            el.click();
                            return { found: true, text: text, tag: el.tagName, forced: true };
                        }
                    }
                }

                return { found: false };
            }
        """)

        if js_result.get('found'):
            print(f"{INFO}JavaScript 点击了: {js_result.get('text')} (tag: {js_result.get('tag')})")
            page.wait_for_timeout(3000)

            # 检查结果
            if len(page.context.pages) > 1:
                new_page = page.context.pages[-1]
                new_page.wait_for_load_state("networkidle")
                new_page.bring_to_front()
                _remove_browser_warning(new_page)
                new_page.wait_for_timeout(2000)
                _extract_page_data(new_page, download_dir, "student_card", "学籍卡")
            else:
                # 可能触发了下载（已经保存在临时目录）
                _extract_page_data(page, download_dir, "student_card", "学籍卡")
        else:
            print(f"{WARNING}未找到'查看学籍卡'按钮")
            print(f"{INFO}请手动点击'查看学籍卡'按钮")
            print(f"{INFO}如果按钮打开了新页面或下载了文件，程序会尝试捕获")
            input("手动操作完成后按回车继续...")

            # 检查是否有新页面
            if len(page.context.pages) > 1:
                new_page = page.context.pages[-1]
                new_page.wait_for_load_state("networkidle")
                new_page.bring_to_front()
                _remove_browser_warning(new_page)
                new_page.wait_for_timeout(2000)
                _extract_page_data(new_page, download_dir, "student_card", "学籍卡")


def _extract_page_data(page, download_dir: str, prefix: str, description: str) -> dict:
    """提取当前页面的数据，保存 JSON 和 TXT"""
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"{INFO}正在提取{description}数据...")
    print(f"{INFO}当前 URL: {page.url}")
    print(f"{INFO}页面标题: {page.title()}")

    # 关闭弹窗
    _remove_browser_warning(page)
    page.wait_for_timeout(2000)

    # 等待内容稳定
    _wait_for_stable_content(page, timeout=10)

    # 再次关闭弹窗
    _remove_browser_warning(page)
    page.wait_for_timeout(1000)

    # 提取数据 - 增强版
    data = page.evaluate("""
        () => {
            const results = {
                page_title: document.title,
                url: window.location.href,
                tables: [],
                raw_text: '',
                module_requirements: []
            };

            // ===== 1. 获取主要内容区域 =====
            const contentSelectors = [
                '.ivu-card-body',
                '.main-content',
                '#app',
                'main',
                '.content',
                '.el-main',
                '[class*="content"]',
                '[class*="main"]',
                '.ivu-tabs-tabpane',
                '.el-tab-pane',
            ];

            let contentArea = document.body;
            let maxLen = 0;

            for (const selector of contentSelectors) {
                const els = document.querySelectorAll(selector);
                for (const el of els) {
                    const text = (el.innerText || '');
                    if (text.includes('浏览器已经过时') || text.includes('Internet Explorer 9')) {
                        continue;
                    }
                    // 排除弹窗/模态框
                    if (el.closest('.ivu-modal, .el-dialog, .ant-modal, .ivu-message-box')) {
                        continue;
                    }
                    const len = text.length;
                    if (len > maxLen) {
                        contentArea = el;
                        maxLen = len;
                    }
                }
            }

            // ===== 2. 获取原始文本（排除弹窗） =====
            let rawText = '';
            const walker = document.createTreeWalker(
                contentArea,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            let node;
            const textParts = [];
            while (node = walker.nextNode()) {
                // 排除弹窗内的文本
                if (node.parentElement && node.parentElement.closest('.ivu-modal, .el-dialog, .ant-modal, .ivu-message-box')) {
                    continue;
                }
                const t = node.textContent.trim();
                if (t) {
                    textParts.push(t);
                }
            }
            rawText = textParts.join('\\n');

            // 如果文本太少，可能是被弹窗挡住了，尝试获取整个 body
            if (rawText.length < 100) {
                const bodyText = document.body.innerText || '';
                // 尝试移除弹窗文本
                const lines = bodyText.split('\\n').filter(line => {
                    const trimmed = line.trim();
                    return trimmed.length > 0 &&
                           !trimmed.includes('浏览器已经过时') &&
                           !trimmed.includes('Internet Explorer') &&
                           !trimmed.includes('非威海校区') &&
                           !trimmed.includes('博士生信息填写');
                });
                rawText = lines.join('\\n');
            }

            results.raw_text = rawText;

            // ===== 3. 提取表格 =====
            // 从内容区域提取
            let tables = contentArea.querySelectorAll('table');
            // 如果内容区域没有表格，从整个 body 提取
            if (tables.length === 0) {
                tables = document.querySelectorAll('table');
            }

            tables.forEach((table, index) => {
                // 排除弹窗内的表格
                if (table.closest('.ivu-modal, .el-dialog, .ant-modal, .ivu-message-box')) {
                    return;
                }
                const tableData = { index, rows: [] };
                const rows = table.querySelectorAll('tr');
                rows.forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td, th'))
                        .map(c => (c.innerText || '').trim());
                    if (cells.length > 0) {
                        tableData.rows.push(cells);
                    }
                });
                if (tableData.rows.length > 0) {
                    results.tables.push(tableData);
                }
            });

            // ===== 4. 尝试提取"模块要求"相关数据 =====
            const moduleKeywords = ['通识选修课', '模块要求', '人文类', '社科类', '艺术类', '国学类', '美育类', '外语类', '专业导论'];
            const lines = rawText.split('\\n');
            let inModuleSection = false;
            const moduleLines = [];

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                // 检测模块要求区域的开始
                if (moduleKeywords.some(kw => trimmed.includes(kw))) {
                    inModuleSection = true;
                }

                if (inModuleSection) {
                    moduleLines.push(trimmed);
                }
            }

            if (moduleLines.length > 0) {
                results.module_requirements = moduleLines;
            }

            return results;
        }
    """)

    # ===== 保存 JSON =====
    json_path = os.path.join(download_dir, f"{prefix}_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"{SUCCESS}JSON 已保存: {json_path}")

    # ===== 保存 TXT =====
    txt_path = os.path.join(download_dir, f"{prefix}_{timestamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"页面标题: {data.get('page_title', 'Unknown')}\n")
        f.write(f"页面URL: {data.get('url', 'Unknown')}\n")
        f.write(f"提取时间: {timestamp}\n")
        f.write(f"描述: {description}\n")
        f.write("=" * 60 + "\n\n")

        # 模块要求
        module_reqs = data.get('module_requirements', [])
        if module_reqs:
            f.write("📋 模块要求 / 通识选修课:\n")
            f.write("-" * 40 + "\n")
            for line in module_reqs:
                f.write(line + "\n")
            f.write("\n" + "=" * 60 + "\n\n")

        # 表格
        tables = data.get('tables', [])
        if tables:
            f.write(f"找到 {len(tables)} 个表格:\n")
            for i, table in enumerate(tables):
                f.write(f"\n--- 表格 {i+1} ({len(table['rows'])} 行) ---\n")
                for row in table['rows']:
                    f.write(" | ".join(row) + "\n")
        else:
            f.write("未找到结构化表格数据\n\n")

        f.write("\n" + "=" * 60 + "\n")
        f.write("完整文本内容:\n")
        f.write("-" * 40 + "\n")
        f.write(data.get("raw_text", "无内容"))

    print(f"{SUCCESS}TXT 已保存: {txt_path}")

    # ===== 摘要 =====
    module_reqs = data.get('module_requirements', [])
    tables = data.get('tables', [])

    if module_reqs:
        print(f"{SUCCESS}提取到模块要求数据 ({len(module_reqs)} 行)")
        for line in module_reqs[:5]:
            print(f"  - {line[:80]}")

    if tables:
        total_rows = sum(len(t['rows']) for t in tables)
        print(f"{SUCCESS}提取到 {len(tables)} 个表格，共 {total_rows} 行数据")
    elif not module_reqs:
        text_preview = data.get('raw_text', '')[:300].replace('\n', ' ').strip()
        text_preview = text_preview.replace('浏览器已经过时', '').strip()
        print(f"{INFO}文本预览: {text_preview[:200]}...")

    print(f"{SUCCESS}{description}数据提取完成\n")

    return data


def _sanitize_term_label(label: str) -> str:
    """清理学期标签为合法文件名"""
    safe = re.sub(r"[\\/:*?\"<>|]", "_", label)
    safe = safe.replace(" ", "")
    return safe or "unknown"