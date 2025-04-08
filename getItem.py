import pandas as pd
import time
from datetime import datetime
from common import (
    initialize_csv_files,
    get_first_row_data,
    setup_webdriver,
    print_with_timestamp,
    write_log_and_update_record,
)


def get_popup_content_and_close(page):
    """
    获取网页弹窗内容并关闭弹窗。

    参数:
    page (ChromiumPage): ChromiumPage 对象。
    """
    try:
        # 查找所有符合条件的弹窗元素
        popups = page.eles('css:div[id^="amsopenFrame_"]')

        if not popups:
            return "没有找到弹窗"

        # 获取当前时间戳
        current_timestamp = int(time.time() * 1000)

        # 找到离当前时间最近的弹窗元素
        closest_popup = min(
            popups,
            key=lambda popup: abs(
                int(popup.attr("id").split("_")[1]) - current_timestamp
            ),
        )

        # 获取弹窗内容
        content = closest_popup.ele("css:.amsdialog_content .amsdialog_cmain")

        # 关闭弹窗
        close_button = closest_popup.ele(
            "css:.amsdialog_content .amsdialog_footer .amsdialog_btn.amsdialog_bconfirm"
        )
        if close_button:
            close_button.click()

        return "网页消息：" + content.text

    except Exception as e:
        return f"弹窗内容异常: {str(e)}"


def execute_js_at_each_hour(page, js_code, df, row_index, csv_file_path):
    """
    每个整点执行 JavaScript 代码

    参数:
    page (ChromiumPage): ChromiumPage 对象。
    js_code (str): 要执行的 JavaScript 代码。
    df (DataFrame): CSV 文件的数据框。
    row_index (int): 当前行的索引。
    csv_file_path (str): CSV 文件路径。
    """
    while True:
        now = datetime.now()
        # 计算距离下一个整点的秒数
        seconds_until_next_hour = (60 - now.minute) * 60 - now.second
        print_with_timestamp(
            f"下一个整点是 {now.hour + 1} 点，还有 {seconds_until_next_hour // 60} 分钟 {seconds_until_next_hour % 60} 秒"
        )

        # 等待到接近整点
        time.sleep(seconds_until_next_hour - 1)

        # 精确等待到整点
        while True:
            now = datetime.now()
            if now.second == 0:
                break
            time.sleep(0.01)

        # 执行 JavaScript 代码
        page.run_js(js_code)

        # 等待几秒钟以确保 JavaScript 代码执行完毕
        time.sleep(1)

        # 获取弹窗内容
        context_text = get_popup_content_and_close(page)

        # 打印弹窗内容
        print_with_timestamp(context_text)

        # 判断content.text是否包含"恭喜"
        result_message = "success" if "恭喜" in context_text else "failed"

        # 更新记录
        write_log_and_update_record(
            df, row_index, js_code, context_text, result_message, csv_file_path
        )
        if result_message == "success":
            print_with_timestamp("领取成功")
            # 退出循环
            break
        else:
            print_with_timestamp("领取失败")
            # 继续循环


def run_item_retrieval():
    """
    运行领取道具的主流程。
    """
    # 初始化 CSV 文件
    initialize_csv_files()

    # 文件路径
    csv_file_path = "record.csv"

    # 读取 CSV 文件并获取 URL、JavaScript 代码和 cookie
    df = pd.read_csv(csv_file_path, encoding="utf-8")

    url, js_code, cookie_str = get_first_row_data(df)
    if not url or not js_code or not cookie_str:
        print_with_timestamp("没有在 record.csv 中找到待处理的数据")
        return

    # 获取 ChromiumPage 并打开目标网页
    page = setup_webdriver()

    # 设置全局超时
    page.set.timeouts(30)

    # 等待页面加载完成
    page.set.load_mode.normal()

    page.get(url)

    # 清除所有现有 cookie
    page.set.cookies.clear()

    # 添加指定的 cookie
    # DrissionPage 为每个网站使用单独的 cookie
    for cookie in cookie_str.split("; "):
        if "=" in cookie:
            name, value = cookie.split("=", 1)
            if name in ["openid", "access_token", "appid", "acctype"]:
                # 使用正确的方法添加 cookie
                page.run_js(f"document.cookie = '{name}={value}; path=/'")
                print_with_timestamp(f"添加 cookie: {name}={value}")

    page.refresh()

    print_with_timestamp("程序开始运行，按 Ctrl+C 退出")

    # 等待页面加载完成
    time.sleep(3)

    # 尝试打印弹窗内容
    print_with_timestamp(get_popup_content_and_close(page))

    # 保持浏览器打开状态并执行 JavaScript 代码
    try:
        execute_js_at_each_hour(
            page,
            js_code,
            df,
            df.index[0],
            csv_file_path,
        )
    except KeyboardInterrupt:
        print_with_timestamp("退出程序")

    page.quit()


if __name__ == "__main__":
    run_item_retrieval()
