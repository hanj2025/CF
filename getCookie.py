import pandas as pd
import time
import traceback
from datetime import datetime
from common import (
    initialize_csv_files,
    setup_webdriver,
    print_with_timestamp,
    get_cookie_empty_row,
)


def main():
    """
    主函数，获取 cookie 并写入 CSV 文件。
    只保存关键 cookie: openid, access_token, appid, acctype
    """
    # 初始化 CSV 文件
    initialize_csv_files()

    # 文件路径
    csv_file_path = "record.csv"

    # 读取 CSV 文件，使用 UTF-8 编码
    df = pd.read_csv(csv_file_path, encoding="utf-8")

    # 找到 url 有内容但 cookie 为空的第一行数据
    row_index, row = get_cookie_empty_row(df)

    if row is None:
        print_with_timestamp("没有找到 url 有内容但 cookie 为空的行")
        return

    print_with_timestamp(f"正在处理第 {row_index + 2} 行数据，URL: {row['url']}")

    # 获取 URL
    url = row["url"]

    # 获取 DrissionPage 对象
    page = setup_webdriver()

    # 设置全局超时
    page.set.timeouts(30)

    # 等待页面加载完成
    page.set.load_mode.normal()

    # 在同一行的startTime写入当前时间，并且将同一行的state1值改为处理中
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.at[row_index, "startTime"] = start_time
    df.at[row_index, "state1"] = "Getting cookie"
    df.to_csv("record.csv", index=False, encoding="utf-8")

    # 定义关键 cookie 列表
    KEY_COOKIES = ["openid", "access_token", "appid", "acctype"]

    try:
        # 先打开一个临时页面，防止清除cookie时出错
        print_with_timestamp("正在打开临时页面...")
        page.get("about:blank")

        # 清除所有cookie
        print_with_timestamp("清除所有现有cookie...")
        try:
            page.set.cookies.clear()
            print_with_timestamp("已清除所有cookie")
        except Exception as e:
            print_with_timestamp(f"清除cookie时出错: {str(e)}")

        # 打开目标网页
        print_with_timestamp(f"正在打开目标URL: {url}")
        page.get(url)

        # 使用动态等待而不是固定等待时间
        max_wait_time = 600  # 最大等待时间（秒）
        check_interval = 1  # 检查间隔（秒）
        wait_count = 0
        login_detected = False

        # 记录找到的关键 cookie
        found_key_cookies = set()

        while wait_count < max_wait_time:
            # 检查是否已经登录成功（基于cookie来判断）
            current_cookies = page.cookies()

            # 检查关键cookie是否存在，避免重复计数
            current_cookie_names = set(
                c.get("name") for c in current_cookies if c.get("name") in KEY_COOKIES
            )
            new_key_cookies = current_cookie_names - found_key_cookies

            if new_key_cookies:
                for name in new_key_cookies:
                    print_with_timestamp(f"发现新的关键cookie: {name}")
                found_key_cookies.update(new_key_cookies)

            # 检查是否获取了access_token
            if "access_token" in found_key_cookies:
                print_with_timestamp("已获取到 access_token，登录成功！")
                login_detected = True
                # 给用户额外时间以确保所有cookie都已设置
                print_with_timestamp("等待5秒钟以确保所有cookie都已设置...")
                time.sleep(5)
                break

            # 调试输出当前cookie情况
            if wait_count % 5 == 0:  # 每5秒输出一次当前cookie
                print_with_timestamp(f"当前已获取cookie: {list(found_key_cookies)}")

            # 每次检查后短暂等待
            time.sleep(check_interval)
            wait_count += check_interval

            if wait_count % 10 == 0:  # 每10秒打印一次等待信息
                print_with_timestamp(
                    f"仍在等待获取完整cookie，已等待 {wait_count} 秒..."
                )

        # 如果超时了还没检测到登录
        if not login_detected:
            print_with_timestamp(
                f"等待登录超时({max_wait_time}秒)，将继续处理当前页面的cookie..."
            )

        # 再次获取cookies，确保获取最新状态
        print_with_timestamp("获取最终cookie状态...")
        current_cookies = page.cookies()

        # 构建cookie字典，只保存关键cookie，避免重复
        cookies_dict = {}
        processed_names = set()  # 用于记录已处理的cookie名称

        for cookie in current_cookies:
            cookie_name = cookie.get("name", "")
            cookie_value = cookie.get("value", "")

            # 只保存关键cookie且避免重复
            if (
                cookie_name in KEY_COOKIES
                and cookie_value
                and cookie_name not in processed_names
            ):
                cookies_dict[cookie_name] = cookie_value
                print_with_timestamp(f"保存关键cookie: {cookie_name}={cookie_value}")
                processed_names.add(cookie_name)  # 标记为已处理

        # 输出获取到的关键cookie数量
        key_cookies_found = len(cookies_dict)
        print_with_timestamp(
            f"总共获取到 {key_cookies_found}/{len(KEY_COOKIES)} 个关键cookie"
        )

        # 检查是否获取到了所有关键cookie
        missing_cookies = [name for name in KEY_COOKIES if name not in cookies_dict]
        if missing_cookies:
            print_with_timestamp(f"警告：缺少关键cookie: {', '.join(missing_cookies)}")

        # 将关键Cookie转换为字符串
        if cookies_dict:
            cookie_value = "; ".join(
                [f"{name}={value}" for name, value in cookies_dict.items()]
            )

            # 将Cookie值写入CSV文件
            df.at[row_index, "cookie"] = cookie_value

            # 设置状态，根据是否包含access_token判断是否成功
            if "access_token" in cookies_dict:
                df.at[row_index, "state1"] = "Successfully obtained cookie"
                print_with_timestamp(
                    f"成功获取access_token: {cookies_dict['access_token'][:10]}..."
                )
            else:
                df.at[row_index, "state1"] = "Missing access_token"
                print_with_timestamp("警告: 未获取到access_token")
        else:
            print_with_timestamp("未获取到任何关键cookie")
            df.at[row_index, "state1"] = "No key cookies obtained"
            df.at[row_index, "cookie"] = ""

    except Exception as e:
        print_with_timestamp(f"处理过程中发生错误: {str(e)}")
        print_with_timestamp(traceback.format_exc())
        df.at[row_index, "state1"] = f"Error: {str(e)}"
        df.at[row_index, "cookie"] = ""  # 将cookie置空

    finally:
        # 在endTime写入当前时间
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.at[row_index, "endTime"] = end_time
        # 保存CSV
        df.to_csv("record.csv", index=False, encoding="utf-8")

        try:
            # 退出浏览器
            page.quit()
            print_with_timestamp("浏览器已关闭")
        except Exception as e:
            print_with_timestamp(f"关闭浏览器时出错: {str(e)}")

    print_with_timestamp(f"程序终止，已处理第 {row_index + 2} 行数据")


if __name__ == "__main__":
    main()
