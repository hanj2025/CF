import os
import csv
import pandas as pd
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions


def initialize_csv_files():
    """
    检查 log.csv 和 record.csv 是否存在，不存在则新建并写入表头。
    """
    if not os.path.exists("log.csv"):

        with open("log.csv", mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file, fieldnames=["time", "url", "jsCode", "message", "state", "cookie"]
            )
            writer.writeheader()
            print_with_timestamp("log.csv 不存在，新建文件并写入表头")

    if not os.path.exists("record.csv"):
        with open("record.csv", mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "startTime",
                    "endTime",
                    "url",
                    "jsCode",
                    "state1",
                    "state2",
                    "state3",
                    "cookie",
                ],
            )
            writer.writeheader()
            print_with_timestamp("record.csv 不存在，新建文件并写入表头")


def get_first_row_data(df):
    """
    获取 CSV 文件的第一行数据，state2 列不为 'Successfully obtained props' 且 cookie 不为空。

    参数:
    df (DataFrame): CSV 文件的数据框。

    返回:
    tuple: 包含 URL、JavaScript 代码和 cookie 的元组。
    """
    filtered_df = df[
        (df["state2"] != "Successfully obtained props")
        & (df["cookie"].notna())
        & (df["cookie"] != "")
    ]
    if filtered_df.empty:
        return None, None, None
    row = filtered_df.iloc[0]
    return row["url"], row["jsCode"], row["cookie"]


def setup_webdriver():
    """
    设置并返回DrissionPage对象。

    返回:
    ChromiumPage: 配置好的ChromiumPage对象。
    """
    # 创建浏览器配置
    co = ChromiumOptions()
    co.headless(False)  # 可以根据需要设置为True

    # 设置浏览器参数
    co.set_argument("--disable-gpu")  # 禁用GPU加速
    co.set_argument("--disable-infobars")
    co.set_argument("--disable-blink-features=AutomationControlled")

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
            print_with_timestamp(f"使用浏览器: {expanded_path}")
            co.set_browser_path(expanded_path)
            browser_found = True
            break

    if not browser_found:
        print_with_timestamp("未找到可用的浏览器，使用默认浏览器")

    # 创建浏览器实例 - 正确传递 ChromiumOptions 对象
    page = ChromiumPage(co)
    print_with_timestamp("浏览器初始化成功")

    return page


def print_with_timestamp(message):
    """
    打印带有时间戳的消息。

    参数:
    message (str): 要打印的消息。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}")


def log_to_csv(time, url, js_code, message, state, cookie):
    """
    将日志记录到 log.csv 文件。

    参数:
    time (str): 时间戳。
    url (str): URL。
    js_code (str): JavaScript 代码。
    message (str): 消息。
    state (str): 状态。
    cookie (str): Cookie。
    """
    with open("log.csv", mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file, fieldnames=["time", "url", "jsCode", "message", "state", "cookie"]
        )
        if file.tell() == 0:
            writer.writeheader()  # 写入表头
        writer.writerow(
            {
                "time": time,
                "url": url,
                "jsCode": js_code,
                "message": message,
                "state": state,
                "cookie": cookie,
            }
        )


def get_cookie_empty_row(df):
    """
    找到 url 有内容但 cookie 为空的第一行数据。

    参数:
    df (DataFrame): CSV 文件的数据框。

    返回:
    tuple: 包含行索引和行数据的元组。
    """
    cookie_empty_rows = df[
        (df["url"] != "") & ((df["cookie"] == "") | (df["cookie"].isna()))
    ]
    if cookie_empty_rows.empty:
        return None, None
    row_index = cookie_empty_rows.index[0]
    row = df.loc[row_index]
    return row_index, row


def update_record_csv(df, row_index, state2, csv_file_path):
    """
    更新 record.csv 文件中的 state2 列。

    参数:
    df (DataFrame): CSV 文件的数据框。
    row_index (int): 当前行的索引。
    state2 (str): 要更新的 state2 值。
    csv_file_path (str): CSV 文件路径。
    """
    df.at[row_index, "state2"] = state2
    df.to_csv(csv_file_path, index=False, encoding="utf-8")


def read_csv(csv_file_path):
    """
    读取 CSV 文件。

    参数:
    csv_file_path (str): CSV 文件路径。

    返回:
    DataFrame: CSV 文件的数据框。
    """
    return pd.read_csv(csv_file_path, encoding="utf-8")


def write_log_and_update_record(
    df, row_index, js_code, div_text, result_message, csv_file_path
):
    """
    记录领取结果到 log.csv 并更新 record.csv 中的 state2 列。

    参数:
    df (DataFrame): CSV 文件的数据框。
    row_index (int): 当前行的索引。
    js_code (str): JavaScript 代码。
    div_text (str): div 的文本内容。
    result_message (str): 结果消息。
    csv_file_path (str): CSV 文件路径。
    """
    log_to_csv(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        df.at[row_index, "url"],
        js_code,
        div_text,
        result_message,
        df.at[row_index, "cookie"],
    )
    if result_message == "success":
        update_record_csv(df, row_index, "Successfully obtained props", csv_file_path)
