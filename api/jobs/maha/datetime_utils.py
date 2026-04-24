from datetime import datetime, timedelta


# 1. 获取当前时间并转换为字符串
def get_current_time_as_string(format_str="%Y-%m-%d %H:%M:%S"):
    """
    获取当前时间并格式化为字符串。
    :param format_str: 时间格式，默认为 "%Y-%m-%d %H:%M:%S"
    :return: 当前时间的字符串
    """
    now = datetime.now()
    return now.strftime(format_str)

# 2. 将字符串转换为 datetime 对象
def string_to_datetime(time_str, format_str="%Y-%m-%d %H:%M:%S"):
    """
    将时间字符串转换为 datetime 对象。
    :param time_str: 时间字符串
    :param format_str: 时间格式，默认为 "%Y-%m-%d %H:%M:%S"
    :return: datetime 对象
    """
    return datetime.strptime(time_str, format_str)

# 3. 计算两个 datetime 对象的时间差
def calculate_time_diff(start_time, end_time) -> timedelta:
    """
    计算两个 datetime 对象的时间差。
    :param start_time: 开始时间（datetime 对象）
    :param end_time: 结束时间（datetime 对象）
    :return: 时间差（timedelta 对象）
    """
    return end_time - start_time

# 4. 将时间差格式化为 xxx小时xx分xx秒
def format_timedelta(td):
    """
    将时间差格式化为 xxx小时xx分xx秒。
    :param td: 时间差（timedelta 对象）
    :return: 格式化后的字符串
    """
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours}小时{minutes}分{seconds}秒"

# 5. 获取指定时间和当前时间差
def time_and_time_str_diff(time_str: str) -> str:
    if not time_str:
        return ""
    current_time = string_to_datetime(time_str)

    return time_and_time_diff(current_time)

# 6. 获取指定时间和当前时间差
def time_and_time_diff(current_time: datetime) -> str:

    # 计算时间差
    time_diff = calculate_time_diff(current_time, datetime.now())

    # 格式化时间差
    formatted_diff = format_timedelta(time_diff)
    return f"时间差: {formatted_diff}"

# 示例用法
if __name__ == "__main__":
    # 获取当前时间并转换为字符串
    current_time_str = get_current_time_as_string()
    print("当前时间（字符串）:", current_time_str)

    # 将字符串转换为 datetime 对象
    current_time = string_to_datetime(current_time_str)
    print("当前时间（datetime）:", current_time)

    # 假设另一个时间
    another_time_str = "2023-10-01 12:00:00"
    another_time = string_to_datetime(another_time_str)
    print("另一个时间（datetime）:", another_time)

    # 计算时间差
    time_diff = calculate_time_diff(another_time, current_time)
    print("时间差（timedelta）:", time_diff)

    # 格式化时间差
    formatted_diff = format_timedelta(time_diff)
    print("格式化后的时间差:", formatted_diff)

    print(time_and_time_str_diff(another_time_str))