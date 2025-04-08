"""
淘宝商品价格监控工具

功能：
1. 从CSV文件中读取商品信息（名称和链接）
2. 访问商品页面，提取价格信息
3. 比较价格变化，记录历史价格
4. 保存价格变动日志
"""

import math
import os
import json
import time
import datetime
import traceback
import random
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
import requests

# 尝试导入DrissionPage，如果不存在则提示安装
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("请先安装DrissionPage: pip install DrissionPage")
    exit(1)

# 定义数据目录，所有生成的文件都将放在这里
DATA_DIR = Path("taobao_monitor_data")
DATA_DIR.mkdir(exist_ok=True)

# 浏览器数据目录设置在用户目录下
BROWSER_DATA_DIR = Path(os.path.expanduser("~")) / ".taobao_browser_data"

# 配置文件路径
CONFIG_FILE = DATA_DIR / "config.json"

# 默认配置
DEFAULT_CONFIG = {
    "browser": {
        "headless": True,  # 是否启用无头模式
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    },
    "price_calculation": {
        "low_price_multiplier": 1.5,  # 单价小于等于阈值时的价格倍数
        "high_price_multiplier": 1.2,  # 单价大于阈值时的价格倍数
        "low_price_threshold": 2.0,  # 价格倍数的阈值
    },
    "directories": {
        "data_dir": str(DATA_DIR),  # 数据目录
        "browser_data_dir": str(BROWSER_DATA_DIR),  # 浏览器数据目录
    },
    "wx_push": {
        "default_spt": "SPT_cew27yNsXkXYXTVvtbLdxs1Iks05",  # 默认微信推送身份令牌
    },
}


def load_config():
    """
    加载配置文件，如果不存在则生成默认配置。

    Returns:
        dict: 配置字典
    """
    if not CONFIG_FILE.exists():
        print("未找到配置文件，正在生成默认配置...")
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        print(f"默认配置已生成: {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# 加载配置
CONFIG = load_config()


class TaobaoScraper:
    """
    淘宝数据爬取模块，处理网页访问和数据提取。
    """

    def __init__(self):
        """
        初始化爬虫模块，设置请求头和浏览器实例。
        """
        self.user_agent = CONFIG["browser"]["user_agent"]
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Referer": "https://www.taobao.com/",
        }
        self.page = None  # 浏览器实例

    def init_browser(self):
        """
        初始化浏览器实例，支持无头模式和用户数据目录。

        Returns:
            bool: 浏览器初始化是否成功
        """
        if self.page is not None:
            try:
                self.page.quit()
            except Exception as e:
                print(f"关闭旧浏览器实例时出错: {e}")

        print("初始化浏览器...")

        try:
            # 创建浏览器配置
            co = ChromiumOptions().headless(CONFIG["browser"]["headless"])

            # 设置用户代理
            co.set_user_agent(self.headers["User-Agent"])

            # 设置浏览器参数
            co.set_argument("--remote-debugging-port=9222")
            co.set_argument("--disable-infobars")
            co.set_argument("--disable-blink-features=AutomationControlled")

            # 设置用户数据目录，保留登录状态
            BROWSER_DATA_DIR.mkdir(exist_ok=True, parents=True)
            co.set_user_data_path(str(BROWSER_DATA_DIR))
            print(f"浏览器数据目录: {BROWSER_DATA_DIR}")

            # 查找可用的浏览器路径
            browser_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]

            browser_found = False
            for path in browser_paths:
                expanded_path = os.path.expandvars(path)
                if os.path.exists(expanded_path):
                    print(f"使用浏览器: {expanded_path}")
                    co.set_browser_path(expanded_path)
                    browser_found = True
                    break

            if not browser_found:
                print("未找到可用的浏览器，请检查浏览器安装路径")
                return False

            # 创建浏览器实例
            self.page = ChromiumPage(co)
            print("浏览器初始化成功")
            return True

        except Exception as e:
            print(f"浏览器初始化错误: {e}")
            print(traceback.format_exc())
            self.page = None
            return False

    def get_page(self, url, max_retries=2):
        """
        访问页面，带有重试机制。

        Args:
            url (str): 要访问的URL
            max_retries (int): 最大重试次数

        Returns:
            bool: 页面加载是否成功
        """
        if self.page is None and not self.init_browser():
            return False

        for attempt in range(max_retries):
            try:
                print(f"正在加载页面 ({attempt + 1}/{max_retries}): {url}")
                self.page.get(url)

                # 等待页面加载完成
                time.sleep(3 + random.uniform(0, 2))
                return True
            except Exception as e:
                print(f"页面加载失败: {e}")
                if attempt < max_retries - 1:
                    print("等待后重试...")
                    time.sleep(5)
                else:
                    print("达到最大重试次数，放弃加载")
                    return False
        return False

    def extract_price(self, save_debug_info=True, product_name=None, product_id=None):
        """
        从加载的页面提取价格。

        Args:
            save_debug_info (bool): 是否保存调试信息（如页面源码和截图）
            product_name (str): 商品名称（用于调试信息）
            product_id (str): 商品ID（用于调试信息）

        Returns:
            tuple: (价格信息, 是否成功)
        """
        if self.page is None:
            return "浏览器未初始化", False

        # 保存页面源码以供调试
        if save_debug_info:
            debug_dir = DATA_DIR / "debug"
            debug_dir.mkdir(exist_ok=True)
            with open(debug_dir / "last_page.html", "w", encoding="utf-8") as f:
                f.write(self.page.html)

        # 价格提取策略列表
        extraction_strategies = [
            self._extract_price_strategy_1,
            self._extract_price_strategy_2,
            self._extract_price_strategy_3,
        ]

        # 依次尝试各种提取策略
        price = None
        for i, strategy in enumerate(extraction_strategies):
            try:
                price = strategy()
                if price:
                    # 校验提取的价格是否为有效数字
                    try:
                        # 尝试提取数字部分
                        price_match = re.search(r"(\d+(?:\.\d+)?)", price)
                        if price_match:
                            # 确保可以转换为浮点数
                            float(price_match.group(1))
                            print(f"策略 {i + 1} 成功提取价格: {price}")
                            break
                        else:
                            print(f"策略 {i + 1} 提取的价格无效: {price}")
                            price = None
                    except ValueError:
                        print(f"策略 {i + 1} 提取的价格无法转换为数字: {price}")
                        price = None
            except Exception as e:
                print(f"策略 {i + 1} 提取失败: {e}")

        # 截图页面（可选）
        if save_debug_info:
            try:
                screenshot_dir = DATA_DIR / "screenshots"
                screenshot_dir.mkdir(exist_ok=True)

                # 使用不带年份的时间，格式为 月日_时分
                timestamp = datetime.datetime.now().strftime("%m%d_%H%M")

                # 使用商品名称和ID构建文件名
                filename_parts = []

                # 添加商品名称（如果提供）
                if product_name:
                    # 清理商品名称，移除不适合文件名的字符
                    safe_name = re.sub(r'[\\/*?:"<>|]', "", product_name)
                    safe_name = (
                        safe_name[:30] if len(safe_name) > 30 else safe_name
                    )  # 限制长度
                    filename_parts.append(safe_name)

                # 添加商品ID（如果提供），不包含"ID"字样
                if product_id:
                    filename_parts.append(product_id)

                # 添加时间戳
                filename_parts.append(timestamp)

                # 构建完整文件名
                if filename_parts:
                    screenshot_file = screenshot_dir / f"{'_'.join(filename_parts)}.png"
                else:
                    screenshot_file = screenshot_dir / f"item_{timestamp}.png"

                self.page.get_screenshot(screenshot_file)
                print(f"已保存页面截图: {screenshot_file}")
            except Exception as e:
                print(f"截图失败: {e}")

        # 返回价格结果
        if price:
            return price, True
        else:
            return "未找到价格", False

    def _extract_price_strategy_1(self):
        """
        价格提取策略1: 使用XPath定位价格元素。

        Returns:
            str: 提取到的价格
        """
        # 尝试寻找价格元素
        price_selectors = [
            '//span[contains(@class, "text") and (contains(preceding-sibling::span/text(), "￥") or contains(preceding-sibling::span/text(), "¥"))]',
            '//span[contains(@class, "unit") and (contains(text(), "￥") or contains(text(), "¥"))]/following-sibling::span',
            '//div[contains(@class, "price") or contains(@class, "Price")]//span[contains(text(), "¥") or contains(text(), "￥")]',
            '//div[contains(@style, "color: rgb(255")]//span[contains(text(), "￥") or contains(@class, "text")]',
        ]

        for selector in price_selectors:
            elements = self.page.eles(f"xpath:{selector}")
            if elements:
                print(f"找到 {len(elements)} 个价格元素")
                for ele in elements:
                    text = ele.text
                    print(f"价格元素: '{text}'")
                    price_match = re.search(r"(\d+(?:\.\d+)?)", text)
                    if price_match:
                        return price_match.group(1)

                # 尝试获取父元素文本
                for ele in elements:
                    parent = ele.parent
                    if parent:
                        parent_text = parent.text
                        print(f"父元素文本: '{parent_text}'")
                        price_match = re.search(r"[¥￥\s]*(\d+(?:\.\d+)?)", parent_text)
                        if price_match:
                            return price_match.group(1)

        return None

    def _extract_price_strategy_2(self):
        """
        价格提取策略2: 使用JavaScript脚本提取价格。

        Returns:
            str: 提取到的价格
        """
        js_code = """
        function getPrice() {
            // 1. 直接获取价格元素
            let priceNodes = document.querySelectorAll('span.text--Mdqy24Ex, [class*="price"] span, [class*="Price"] span, span.tm-price, .tb-rmb-num');
            
            for (let el of priceNodes) {
                let text = el.textContent.trim();
                if (/\\d+(\\.\\d+)?/.test(text)) {
                    return text;
                }
            }
            
            // 2. 搜索包含￥或¥的元素
            let elementsWithYen = Array.from(document.querySelectorAll('*'))
                .filter(el => el.textContent && 
                      (el.textContent.includes('￥') || 
                       el.textContent.includes('¥')));
            
            for (let el of elementsWithYen) {
                let text = el.textContent.trim();
                let match = text.match(/[¥￥]\\s*(\\d+(?:\\.\\d+)?)/);
                if (match) {
                    return match[1];
                }
            }
            
            // 3. 查找任何看起来像价格的文本
            let allTexts = Array.from(document.querySelectorAll('div, span, p'))
                .map(el => el.textContent.trim())
                .filter(text => /^\\d+(\\.\\d+)?$/.test(text) && text.length < 10);
                
            if (allTexts.length > 0) {
                return allTexts.sort((a, b) => parseFloat(a) - parseFloat(b))[0];
            }
            
            return null;
        }
        return getPrice();
        """

        price_info = self.page.run_js(js_code)
        if price_info:
            print(f"JS获取价格文本: '{price_info}'")
            price_match = re.search(r"(\d+(?:\.\d+)?)", price_info)
            if price_match:
                return price_match.group(1)

        return None

    def _extract_price_strategy_3(self):
        """
        价格提取策略3: 分析页面文本查找价格模式。

        Returns:
            str: 提取到的价格
        """
        # 提取页面文本
        page_text = self.page.ele("tag:body").text

        # 价格模式列表
        price_patterns = [
            r"(?:¥|￥)\s*(\d+(?:\.\d+)?)",
            r"(?:价格|促销价|折后价).{0,10}?(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*(?:元|块钱)",
            r"(?:价格|价钱)\D*?(\d+(?:\.\d+)?)",
        ]

        for pattern in price_patterns:
            matches = re.findall(pattern, page_text)
            if matches:
                # 过滤可能的价格，去除异常值
                valid_prices = [
                    p for p in matches if float(p) > 0 and float(p) < 100000
                ]
                if valid_prices:
                    # 选择合理的价格（较小值更可能是价格）
                    return sorted(valid_prices, key=float)[0]

        return None


class PriceHistoryManager:
    """价格历史管理模块，处理价格记录的保存和比较"""

    def __init__(self, history_file=None):
        """初始化价格历史管理器"""
        if history_file is None:
            history_file = DATA_DIR / "price_history.json"
        self.history_file = history_file
        self.price_history = self.load_history()

    def get_price_history(self):
        """获取价格历史数据

        Returns:
            dict: 价格历史数据字典
        """
        return self.price_history

    def load_history(self):
        """加载历史价格数据"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                print(f"历史文件损坏，创建新的历史记录")
                return {}
        return {}

    def save_history(self):
        """保存历史价格数据"""
        # 确保父目录存在
        self.history_file.parent.mkdir(exist_ok=True, parents=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.price_history, f, ensure_ascii=False, indent=2)

    def check_price_change(self, item_id, product_name, current_price):
        """检查价格是否变化并记录历史"""
        result = {
            "is_new_item": False,
            "has_changed": False,
            "old_price": None,
        }

        # 更新时间戳
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 检查是否是新商品
        if item_id not in self.price_history:
            self.price_history[item_id] = {
                "name": product_name,
                "price": current_price,
                "last_update": timestamp,
            }
            result["is_new_item"] = True
        else:
            # 总是更新商品名称，使用CSV中的名称
            self.price_history[item_id]["name"] = product_name

            # 检查价格是否变化
            old_price = self.price_history[item_id]["price"]
            result["old_price"] = old_price

            if old_price != current_price:
                # 价格变化，更新记录
                self.price_history[item_id]["price"] = current_price
                self.price_history[item_id]["last_update"] = timestamp
                result["has_changed"] = True

        return result


class PriceLogger:
    """价格日志模块，处理价格变动日志的记录"""

    def __init__(self, log_dir=None, log_file=None):
        """初始化价格日志记录器"""
        if log_dir is None:
            log_dir = DATA_DIR / "price_logs"
        else:
            log_dir = Path(log_dir)

        if log_file is None:
            log_file = "price_changes.log"

        self.log_dir = log_dir
        self.log_dir.mkdir(exist_ok=True, parents=True)
        self.log_path = self.log_dir / log_file

    def log_price_change(self, product_name, product_id, old_price, new_price):
        """记录价格变化"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {product_name} (ID: {product_id})\n"
        log_entry += f"价格变化: {old_price} → {new_price}\n"
        log_entry += f"商品链接: https://item.taobao.com/item.htm?id={product_id}\n\n"

        # 追加到日志文件
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

        # 打印到控制台
        print(f"价格变化: {old_price} → {new_price}")

    def log_event(self, message):
        """记录一般事件"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        # 追加到日志文件
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)


class ProductExtractor:
    """商品信息提取模块，从HTML提取商品数据并保存到CSV"""

    @staticmethod
    def extract_product_info(html_file, output_csv=None):
        """从HTML文件中提取商品名称和链接，并生成CSV文件"""
        # 处理输出文件路径
        if output_csv is None:
            # 创建输出目录
            output_dir = DATA_DIR / "extracted_data"
            output_dir.mkdir(exist_ok=True, parents=True)

            # 生成文件名（日期+时间）
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_csv = output_dir / f"products_{timestamp}.csv"
        else:
            output_csv = Path(output_csv)
            # 确保父目录存在
            output_csv.parent.mkdir(exist_ok=True, parents=True)

        print(f"开始从HTML提取商品信息...")

        # 读取HTML文件
        try:
            with open(html_file, "r", encoding="utf-8") as f:
                html_content = f.read()
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试使用其他编码
            with open(html_file, "r", encoding="gbk") as f:
                html_content = f.read()

        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # 查找所有商品容器，采用更宽松的查找策略
        card_containers = []

        # 1. 首先尝试使用class包含cardContainer的div
        card_containers = soup.find_all(
            "div", class_=lambda x: x and "cardContainer" in x
        )

        # 2. 如果没找到，尝试其他可能的容器类名
        if not card_containers:
            possible_containers = [
                soup.find_all(
                    "div", class_=lambda x: x and ("card" in x.lower() if x else False)
                ),
                soup.find_all(
                    "div", class_=lambda x: x and ("item" in x.lower() if x else False)
                ),
                soup.find_all(
                    "div",
                    class_=lambda x: x and ("product" in x.lower() if x else False),
                ),
            ]
            for containers in possible_containers:
                if containers:
                    card_containers = containers
                    break

        # 3. 如果仍然没找到，尝试找包含商品链接的容器
        if not card_containers:
            # 找出所有指向淘宝商品的链接
            product_links = soup.find_all(
                "a", href=lambda x: x and "item.taobao.com" in x
            )

            # 对于每个链接，找到其父容器
            for link in product_links:
                parent = link.parent
                # 向上查找最多3层
                for _ in range(3):
                    if parent and parent.name == "div":
                        card_containers.append(parent)
                        break
                    parent = parent.parent if parent else None

        total = len(card_containers)
        print(f"总共找到 {total} 个商品卡片")

        # 创建结果列表
        results = []

        # 处理每个商品
        for i, card in enumerate(card_containers, 1):
            try:
                # 提取商品链接
                link_tag = card.find("a", href=lambda x: x and "item.taobao.com" in x)
                item_url = link_tag.get("href", "") if link_tag else ""

                # 提取商品ID并创建简化链接
                item_id = None
                if item_url:
                    if "id=" in item_url:
                        # 从URL中提取ID
                        id_part = item_url.split("id=")[1]
                        item_id = id_part.split("&")[0] if "&" in id_part else id_part
                        # 创建简化链接
                        simplified_url = (
                            f"https://item.taobao.com/item.htm?id={item_id}"
                        )
                    else:
                        simplified_url = item_url
                else:
                    continue  # 如果没有链接，跳过此卡片

                # 提取商品标题
                title = ""

                # 尝试多种方法查找标题
                title_candidates = [
                    # 1. 查找具有"title"部分类名的div
                    card.find("div", class_=lambda x: x and "title" in x.lower()),
                    # 2. 查找具有"Title"部分类名的任何元素
                    card.find(class_=lambda x: x and "Title" in x),
                    # 3. 查找一般的标题类
                    card.find(class_=lambda x: x and "title" in x.lower()),
                    # 4. 尝试查找内容较长的div或span
                    card.find("div", string=lambda s: s and len(s.strip()) > 10),
                    card.find("span", string=lambda s: s and len(s.strip()) > 10),
                ]

                # 使用找到的第一个有效标题
                for candidate in title_candidates:
                    if candidate and candidate.text.strip():
                        title = candidate.text.strip()
                        break

                # 如果标题和链接都存在，添加到结果
                if title and simplified_url:
                    result_string = f"{title},{simplified_url}"
                    results.append(result_string)
                    print(
                        f"[{i}/{total}] 已提取: {title[:30]}..."
                        if len(title) > 30
                        else f"[{i}/{total}] 已提取: {title}"
                    )
                elif simplified_url:
                    # 如果只有链接没有标题，使用商品ID作为标题的一部分
                    title = f"商品_{item_id}"
                    result_string = f"{title},{simplified_url}"
                    results.append(result_string)
                    print(f"[{i}/{total}] 已提取: {title} (无标题)")

            except Exception as e:
                print(f"处理卡片 {i} 时出错: {str(e)}")

        # 写入CSV文件 - 不再使用CSV模块，直接写入文本行
        with open(output_csv, "w", encoding="utf-8-sig") as f:
            # 不写入表头，直接写入数据
            for result in results:
                f.write(f"{result}\n")

        print(f"\n提取完成！成功提取 {len(results)}/{total} 个商品信息")
        print(f"CSV文件已保存到: {output_csv}")

        return output_csv


class PriceMonitor:
    """价格监控主类，协调其他模块工作"""

    def __init__(self):
        """初始化价格监控器"""
        self.scraper = TaobaoScraper()
        self.history_manager = PriceHistoryManager()
        self.logger = PriceLogger()
        self.wx_reporter = SimplePushReporter()
        self.price_changes = []

    def get_latest_csv(self):
        """获取最新的商品CSV文件"""
        csv_dir = DATA_DIR / "extracted_data"
        if not csv_dir.exists():
            raise FileNotFoundError(f"找不到{csv_dir}文件夹")

        csv_files = list(csv_dir.glob("products_*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"{csv_dir}文件夹中没有找到products_*.csv文件")

        # 按文件修改时间排序，获取最新的文件
        latest_file = max(csv_files, key=lambda x: x.stat().st_mtime)
        print(f"找到最新CSV文件: {latest_file}")
        return latest_file

    def extract_item_id(self, url):
        """从淘宝URL中提取商品ID"""
        parsed = urlparse(url)
        if "taobao.com" in parsed.netloc:
            query_params = parse_qs(parsed.query)
            if "id" in query_params:
                return query_params["id"][0]
        return None

    # 修改PriceMonitor类的monitor_prices方法定义
    def monitor_prices(self, wx_push=False, spt=None):
        """监控价格变化的主函数

        Args:
            wx_push (bool): 是否推送到微信
            spt (str): 极简推送的SPT令牌
        """
        self.price_changes = []  # 用于记录价格变动

        try:
            # 初始化浏览器
            if not self.scraper.init_browser():
                print("浏览器初始化失败，无法继续监控")
                return

            # 获取最新的CSV文件
            latest_csv = self.get_latest_csv()

            # 读取CSV文件 - 修改为直接按行读取，每行用第一个逗号分隔
            products = []
            with open(latest_csv, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",", 1)  # 只在第一个逗号处分隔
                    if len(parts) == 2:
                        products.append({"name": parts[0], "url": parts[1]})

            print(f"共读取到 {len(products)} 个商品")

            # 记录开始监控
            self.logger.log_event(f"开始监控 {len(products)} 个商品")

            # 遍历所有商品
            for i, product in enumerate(products, 1):
                product_name = product["name"]
                product_url = product["url"]

                # 提取商品ID
                product_id = self.extract_item_id(product_url)
                if not product_id:
                    print(
                        f"[{i}/{len(products)}] 跳过: 无法从URL提取商品ID: {product_url}"
                    )
                    continue

                # 显示当前处理的商品
                display_name = (
                    f"{product_name[:30]}..."
                    if len(product_name) > 30
                    else product_name
                )
                print(f"\n[{i}/{len(products)}] 正在检查: {display_name}")

                try:
                    # 访问商品页面
                    if not self.scraper.get_page(product_url):
                        print(f"无法加载页面: {product_url}")
                        continue

                    # 提取价格
                    current_price, success = self.scraper.extract_price(
                        product_name=product_name, product_id=product_id
                    )
                    if not success:
                        print(f"无法提取价格: {current_price}")
                        continue

                    # 检查价格变化
                    result = self.history_manager.check_price_change(
                        product_id, product_name, current_price
                    )

                    if result["is_new_item"]:
                        print(f"新商品: {current_price}")
                    elif result["has_changed"]:
                        # 计算价格变化百分比
                        try:
                            old_price_value = float(result["old_price"])
                            new_price_value = float(current_price)
                            change_rate = (
                                (new_price_value - old_price_value) / old_price_value
                            ) * 100
                            change_rate_str = (
                                f"{change_rate:+.1f}%" if change_rate else "0%"
                            )
                        except Exception as e:
                            print(f"计算价格变化率出错: {e}")
                            change_rate_str = "未知"

                        # 记录价格变化
                        self.logger.log_price_change(
                            product_name, product_id, result["old_price"], current_price
                        )

                        # 添加到价格变动列表
                        self.price_changes.append(
                            {
                                "name": product_name,
                                "id": product_id,
                                "old_price": result["old_price"],
                                "new_price": current_price,
                                "change_rate": change_rate_str,
                            }
                        )
                    else:
                        print(f"价格未变: {current_price}")

                    # 间隔一段时间，避免频繁请求
                    if i < len(products):  # 如果不是最后一个商品
                        wait_time = random.uniform(2, 4)
                        print(f"等待 {wait_time:.1f} 秒后继续...")
                        time.sleep(wait_time)

                except Exception as e:
                    print(f"处理出错: {str(e)}")
                    print(traceback.format_exc())
                    time.sleep(random.uniform(3, 6))  # 出错时稍微多等一会

            # 保存更新后的历史记录
            self.history_manager.save_history()
            self.logger.log_event("监控完成")
            print("\n监控完成，结果已保存")

            # 如果启用微信推送，则发送报告
            if wx_push and spt:
                print("正在发送价格报告到微信...")
                push_result = self.wx_reporter.send_price_report(
                    spt, self.history_manager, self.price_changes
                )
                if push_result:
                    print("价格报告已成功推送到微信!")
                else:
                    print("微信推送失败，请检查SPT和网络连接")

        except Exception as e:
            print(f"发生错误: {str(e)}")
            print(traceback.format_exc())
            self.logger.log_event(f"监控异常: {str(e)}")

        finally:
            # 关闭浏览器
            if self.scraper.page is not None:
                try:
                    self.scraper.page.quit()
                    print("浏览器已关闭")
                except:
                    pass


# 在文件末尾修改main部分


# 添加极简推送类
class SimplePushReporter:
    """极简推送报告模块，通过WxPusher极简推送功能发送价格报告"""

    def __init__(self, spt=None):
        """初始化极简推送模块"""
        self.spt = spt or CONFIG["wx_push"]["default_spt"]
        self.api_url = "https://wxpusher.zjiecode.com/api/send/message/simple-push"

    def calculate_suggested_price(self, current_price):
        """计算建议售价
        单价小于等于2的，建议价格是1.5倍，向上保留一位小数
        单价大于2的，建议价格是1.2倍
        """
        try:
            # 处理价格后可能有的"(需登录查看完整价格)"
            price_text = current_price.split("(")[0]
            price_float = float(price_text)

            if price_float <= CONFIG["price_calculation"]["low_price_threshold"]:
                # 向上保留一位小数 (例如：1.5倍的1.33元 = 1.995元，向上保留一位小数 = 2.0元)
                suggested = (
                    math.ceil(
                        price_float
                        * CONFIG["price_calculation"]["low_price_multiplier"]
                        * 10
                    )
                    / 10
                )
            else:
                suggested = (
                    math.ceil(
                        price_float
                        * CONFIG["price_calculation"]["high_price_multiplier"]
                        * 10
                    )
                    / 10
                )

            return f"{suggested:.1f}"
        except Exception as e:
            print(f"计算建议售价出错: {e}")
            return "无法计算"

    def generate_price_report(self, history_manager, price_changes=None):
        # 获取价格历史记录
        price_history = history_manager.get_price_history()
        timestamp = datetime.datetime.now().strftime("%m月%d日 %H:%M")

        # 使用自适应颜色方案，确保在深色或浅色背景下都可读
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 15px; background-color: #2d2d2d; color: #e0e0e0; border-radius: 8px;">
            <h2 style="color: #e0e0e0; border-bottom: 2px solid #555; padding-bottom: 10px; margin-top: 0;">
                淘宝商品价格报告 ({timestamp})
            </h2>
        """

        # 添加价格变动摘要
        if price_changes and len(price_changes) > 0:
            html += """
            <div style="margin: 15px 0; padding: 15px; background-color: rgba(52, 152, 219, 0.2); border-radius: 5px;">
                <h3 style="color: #3498db; margin-top: 0;">价格变动</h3>
                <ul style="list-style-type: none; padding: 0;">
            """

            for change in price_changes:
                # 计算建议售价
                suggested_price = self.calculate_suggested_price(change["new_price"])

                html += f"""
                <li style="margin-bottom: 10px; padding-left: 5px; border-left: 3px solid #3498db;">
                    <span style="color: #e0e0e0;">{change['name']}</span>: 
                    <span style="color: #e74c3c; text-decoration: line-through;">{change['old_price']}</span> → 
                    <span style="color: #2ecc71; font-weight: bold;">{change['new_price']}</span>
                    <span style="color: #e0e0e0; margin-left: 5px;">({change['change_rate']})</span>
                    <span style="color: #f39c12; margin-left: 8px;">建议售价: {suggested_price}</span>
                </li>
                """

            html += """
                </ul>
            </div>
            """

        # 添加详细价格列表
        html += """
        <h3 style="color: #3498db; margin-top: 20px;">商品价格详情</h3>
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; background-color: #2d2d2d;">
            <tr style="background-color: #444;">
                <th style="padding: 8px; text-align: left; border-bottom: 1px solid #666; color: #e0e0e0;">商品名称</th>
                <th style="padding: 8px; text-align: center; border-bottom: 1px solid #666; color: #e0e0e0;">当前价格</th>
                <th style="padding: 8px; text-align: center; border-bottom: 1px solid #666; color: #e0e0e0;">建议售价</th>
                <th style="padding: 8px; text-align: center; border-bottom: 1px solid #666; color: #e0e0e0;">更新时间</th>
            </tr>
        """

        # 按价格从低到高排序
        try:
            sorted_items = sorted(
                [(k, v) for k, v in price_history.items()],
                key=lambda x: (
                    float(x[1]["price"].split("(")[0])
                    if x[1]["price"].split("(")[0].replace(".", "", 1).isdigit()
                    else 999999
                ),
            )

            for item_id, info in sorted_items:
                name = info["name"]
                price = info["price"]
                last_update = info["last_update"].split()[0]  # 只保留日期部分
                suggested_price = self.calculate_suggested_price(price)

                # 名称太长则截断
                display_name = name[:25] + "..." if len(name) > 28 else name

                # 生成表格行 - 交替行颜色以提高可读性
                row_style = (
                    "background-color: #333;"
                    if sorted_items.index((item_id, info)) % 2 == 0
                    else "background-color: #3a3a3a;"
                )

                html += f"""
                <tr style="{row_style} border-bottom: 1px solid #444;">
                    <td style="padding: 8px; text-align: left; color: #e0e0e0;">{display_name}</td>
                    <td style="padding: 8px; text-align: center; font-weight: bold; color: #e0e0e0;">{price}</td>
                    <td style="padding: 8px; text-align: center; color: #f39c12; font-weight: bold;">{suggested_price}</td>
                    <td style="padding: 8px; text-align: center; color: #aaa; font-size: 0.9em;">{last_update}</td>
                </tr>
                """

            html += """
            </table>
            <p style="color: #aaa; font-size: 0.8em; margin-top: 20px; text-align: center;">
                * 价格建议：单价≤{0}元按{1}倍计算，>{0}元按{2}倍计算
            </p>
            """.format(
                CONFIG["price_calculation"]["low_price_threshold"],
                CONFIG["price_calculation"]["low_price_multiplier"],
                CONFIG["price_calculation"]["high_price_multiplier"],
            )

        except Exception as e:
            html += f"""
            <tr>
                <td colspan="4" style="padding: 15px; text-align: center; color: #ff6b6b;">
                    生成报告时发生错误: {str(e)}
                </td>
            </tr>
            </table>
            """

        html += "</div>"
        return html

    def send_price_report(self, spt, history_manager, price_changes=None):
        """发送价格报告到微信"""
        if not spt:
            spt = self.spt

        if not spt:
            print("错误：未设置SPT (Simple Push Token)")
            return False

        # 生成报告内容
        content = self.generate_price_report(history_manager, price_changes)
        timestamp = datetime.datetime.now().strftime("%m-%d %H:%M")

        # 准备请求数据
        data = {
            "content": content,
            "summary": f"淘宝价格监控报告 {timestamp}",
            "contentType": 2,  # 2表示HTML
            "spt": spt,
        }

        try:
            response = requests.post(self.api_url, json=data)
            result = response.json()

            if result.get("success"):
                print("微信推送成功!")
                return True
            else:
                print(f"微信推送失败: {result.get('msg')}")
                return False

        except Exception as e:
            print(f"微信推送请求异常: {e}")
            return False


# 导出工具函数
def extract_product_info(html_file, output_csv=None):
    """从HTML文件中提取商品名称和链接"""
    return ProductExtractor.extract_product_info(html_file, output_csv)


# 运行价格监控
if __name__ == "__main__":
    # 创建基本数据目录
    DATA_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print("淘宝商品价格监控工具")
    print("=" * 50)
    print("1. 提取商品信息")
    print("2. 开始价格监控")
    print("3. 监控价格并推送到微信")
    print("=" * 50)

    try:
        choice = input("请选择操作 [1/2/3]: ").strip()

        if choice == "1":
            # 提取商品信息
            html_file = Path("taoBaoPageData.html")
            if not html_file.exists():
                print(f"错误: 找不到文件 {html_file}")
                print("请确保taoBaoPageData.html文件存在于程序同级目录下")
                exit(1)

            print(f"正在从 {html_file} 提取商品信息...")
            output_file = extract_product_info(html_file)
            print(f"提取完成! 结果已保存到: {output_file}")

        elif choice in ["2", "3"]:
            # 初始化监控器
            monitor = PriceMonitor()

            # 检查是否已经有提取的CSV文件
            csv_dir = DATA_DIR / "extracted_data"
            if not csv_dir.exists() or not list(csv_dir.glob("products_*.csv")):
                print("警告: 未找到商品数据文件。")
                print(
                    "请先选择选项1提取商品信息，或者确认taobao_monitor_data/extracted_data目录中有products_*.csv文件"
                )
                proceed = input("是否继续监控价格? [y/N]: ").strip().lower()
                if proceed != "y":
                    print("已取消监控")
                    exit(0)

            # 如果选择了推送到微信，获取SPT
            wx_push = choice == "3"
            spt = CONFIG["wx_push"]["default_spt"] if wx_push else None

            # 开始监控价格
            print("开始监控商品价格...")
            monitor.monitor_prices(wx_push=wx_push, spt=spt)

        else:
            print("无效的选择")

    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"\n发生错误: {str(e)}")
        print(traceback.format_exc())
    finally:
        # 确保浏览器正常关闭
        if "monitor" in locals() and monitor.scraper.page is not None:
            try:
                monitor.scraper.page.quit()
            except:
                pass
        print("程序已结束")
        exit(0)
