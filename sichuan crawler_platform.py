import json
import time
import re
import os
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ===================== 配置参数 =====================
TARGET_URL = "https://ggzyjy.sc.gov.cn/jyxx/transactionInfo.html"
BASE_URL = "https://ggzyjy.sc.gov.cn"
FIELDS = [
    "标题", "链接", "发布日期", "省份", "来源平台",
    "业务类型", "信息类型", "行业"
]
PAGE_WAIT = 2
MAX_RETRY = 3
ELEMENT_WAIT_TIMEOUT = 10

# ===================== 无头浏览器初始化 =====================
def init_driver():
    """初始化无头Edge浏览器（适用于GitHub Actions）"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    # 反爬优化：隐藏自动化特征
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0')
    driver = webdriver.Edge(options=options)
    print("✅ 无头Edge浏览器已启动，反爬配置已加载")
    return driver

# ===================== 解析函数（保持原逻辑不变，确保数据兼容性）=====================
def parse_notice_item(notice_soup):
    """解析单个公告条目"""
    item = {field: "" for field in FIELDS}
    item["省份"] = "四川省"
    
    try:
        title_p = notice_soup.find("p", class_="clearfix")
        if title_p:
            a_tag = title_p.find("a", class_="l")
            if a_tag:
                item["标题"] = a_tag.get_text(strip=True)
                href = a_tag.get("href", "").strip()
                item["链接"] = BASE_URL + href if href.startswith("/") else href
            
            date_tag = title_p.find("span", class_="fuInfoDate")
            if date_tag:
                item["发布日期"] = date_tag.get_text(strip=True)
        
        info_spans = notice_soup.find_all("span")
        for span in info_spans:
            span_text = span.get_text(strip=True)
            if "来源：" in span_text:
                source_tag = span.find("i", class_="fuZhuanzai")
                if source_tag:
                    item["来源平台"] = source_tag.get_text(strip=True)
            elif "业务类型：" in span_text:
                business_tag = span.find("i", class_="ywlx")
                if business_tag:
                    item["业务类型"] = business_tag.get_text(strip=True)
            elif "信息类型：" in span_text:
                info_type_tag = span.find("i")
                if info_type_tag:
                    item["信息类型"] = info_type_tag.get_text(strip=True)
        
        item["行业"] = ""
                
    except Exception as e:
        print(f"⚠️ 解析单条数据失败: {e}")
    
    return item

def parse_current_page(driver):
    """解析当前页面所有公告"""
    soup = BeautifulSoup(driver.page_source, "html.parser")
    notice_list = soup.select("ul#transactionInfo > li")
    page_data = []
    
    for notice in notice_list:
        item = parse_notice_item(notice)
        page_data.append(item)
    
    print(f"📄 当前页解析出 {len(page_data)} 条原始数据")
    return page_data

def get_total_pages(driver):
    """获取总页数"""
    try:
        total_text = driver.find_element(By.CSS_SELECTOR, "div.hedy_all").text
        match = re.search(r"总计(\d+)页", total_text)
        if match:
            total_pages = int(match.group(1))
            print(f"📊 检测到总页数为: {total_pages}")
            return total_pages
    except Exception as e:
        print(f"⚠️ 获取总页数失败: {e}")
    return None

def go_to_page_by_input(driver, page_num):
    """通过输入框直接跳转到指定页"""
    try:
        input_box = driver.find_element(By.CSS_SELECTOR, "div.m-pagination-jump input[data-page-btn='jump']")
        go_btn = driver.find_element(By.CSS_SELECTOR, "div.m-pagination-jump button[data-page-btn='jump']")
        input_box.clear()
        input_box.send_keys(str(page_num))
        go_btn.click()
        time.sleep(PAGE_WAIT)
        return True
    except Exception as e:
        print(f"⚠️ 跳转至第 {page_num} 页失败: {e}")
        return False

def has_next_page(driver):
    """判断是否有下一页"""
    try:
        next_btn_list = driver.find_elements(By.XPATH, "//div[@id='page']//ul[@class='m-pagination-page']//a[contains(text(),'下一页')]")
        if next_btn_list:
            next_btn = next_btn_list[0]
            if next_btn.is_enabled() and "disabled" not in (next_btn.get_attribute("class") or ""):
                return next_btn
        return None
    except Exception as e:
        print(f"⚠️ 检测下一页失败: {e}")
        return None

# ===================== JSON导出函数（替换原Excel导出）=====================
def export_to_json(data, filename=None):
    """导出数据到JSON文件，适配GitHub Actions，中文无乱码，自动创建目录"""
    if not data:
        print("❌ 无数据可导出")
        return
    
    # 生成默认文件名，与原命名规范保持一致
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"四川省公共资源交易数据_{timestamp}.json"
    
    # 确保data目录存在
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", filename)
    
    # 写入JSON文件，格式化输出，保证中文正常显示
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据已导出到: {filepath}")
    return filepath

# ===================== 主程序（新增日期停止逻辑）=====================
def main():
    try:
        driver = init_driver()
        driver.get(TARGET_URL)
        print(f"🌐 已导航到目标网址: {TARGET_URL}")
        
        # 等待页面初始加载完成
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "transactionInfo"))
        )
        
        # ===== 计算北京时间日期 =====
        # GitHub Actions 默认时区为 UTC，转换为北京时间（UTC+8）
        beijing_now = datetime.utcnow() + timedelta(hours=8)
        target_date = (beijing_now - timedelta(days=1)).strftime("%Y-%m-%d")  # 目标爬取：前一天（昨天）
        stop_date = (beijing_now - timedelta(days=2)).strftime("%Y-%m-%d")    # 停止触发：前天
        print(f"📅 目标爬取日期（昨天）: {target_date}")
        print(f"🛑 停止触发日期（前天）: {stop_date}")
        
        # ===== 点击“近一天”按钮，缩小数据范围 =====
        try:
            pre_oneday_btn = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "dd[data-id='preOneday']"))
            )
            # 如果未激活则点击
            if "active" not in pre_oneday_btn.get_attribute("class"):
                pre_oneday_btn.click()
                print("✅ 已点击“近一天”按钮")
                time.sleep(1)
            else:
                print("ℹ️ “近一天”已是激活状态")
            
            # 等待列表刷新（等待原有第一条数据消失）
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.staleness_of(driver.find_element(By.CSS_SELECTOR, "ul#transactionInfo > li:first-child"))
            )
            # 再等待新列表出现
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul#transactionInfo > li"))
            )
            print("✅ 数据列表已刷新为近一天数据")
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ 点击“近一天”失败，将使用当前页面继续爬取: {e}")
            # 失败时继续，不中断程序
        
        # 获取总页数
        total_pages = get_total_pages(driver)
        if not total_pages:
            print("⚠️ 无法获取总页数，将使用下一页兜底模式")
        
        all_data = []
        current_page_num = 1
        consecutive_failures = 0
        crawl_stop_flag = False  # 日期触发停止标记
        
        while True:
            print(f"\n🚀 正在爬取第 {current_page_num} 页...")
            
            # 解析当前页（带重试机制）
            page_raw_data = []
            for retry in range(MAX_RETRY):
                try:
                    page_raw_data = parse_current_page(driver)
                    if page_raw_data:
                        consecutive_failures = 0
                        break
                    else:
                        print(f"⚠️ 第 {current_page_num} 页数据为空，重试 ({retry+1}/{MAX_RETRY})...")
                        time.sleep(PAGE_WAIT)
                except Exception as e:
                    print(f"⚠️ 解析第 {current_page_num} 页失败，重试 ({retry+1}/{MAX_RETRY}): {e}")
                    time.sleep(PAGE_WAIT)
            
            # 核心逻辑1：先完成当前页目标数据采集
            if page_raw_data:
                # 过滤目标日期数据并汇总
                target_data = [item for item in page_raw_data if item["发布日期"] == target_date]
                all_data.extend(target_data)
                print(f"🔍 本页共 {len(page_raw_data)} 条，目标日期({target_date})数据 {len(target_data)} 条")
                
                # 核心逻辑2：检测停止日期，触发则标记终止（完成当前页后不再翻页）
                has_stop_date = any(item["发布日期"] == stop_date for item in page_raw_data)
                if has_stop_date:
                    print(f"🛑 检测到停止日期({stop_date})数据，完成当前页采集后终止爬取")
                    crawl_stop_flag = True
            else:
                consecutive_failures += 1
                print(f"❌ 第 {current_page_num} 页多次尝试后仍无数据")
            
            # 终止条件判断（日期停止规则优先级最高）
            if crawl_stop_flag:
                print("🔚 已触发日期停止规则，终止爬取")
                break
            if consecutive_failures >= MAX_RETRY:
                print("🔚 连续多次无数据，终止爬取")
                break
            if total_pages and current_page_num >= total_pages:
                print("🔚 已到达总页数，爬取完成")
                break
            
            # 翻页逻辑（与原代码完全兼容，保留双方案兜底）
            current_page_num += 1
            flip_success = False
            
            # 方式1：点击下一页
            next_btn = has_next_page(driver)
            if next_btn:
                try:
                    next_btn.click()
                    time.sleep(PAGE_WAIT)
                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.ID, "transactionInfo"))
                    )
                    flip_success = True
                except Exception as e:
                    print(f"⚠️ 点击下一页失败: {e}")
            
            # 方式2：输入框跳转兜底
            if not flip_success and total_pages:
                print(f"🔄 尝试通过输入框直接跳转至第 {current_page_num} 页...")
                flip_success = go_to_page_by_input(driver, current_page_num)
            
            # 两种方式都失败，终止爬取
            if not flip_success:
                print(f"❌ 无法翻至第 {current_page_num} 页，爬取终止")
                break
        
        # 导出最终JSON数据
        print(f"\n📊 爬取完成！共爬取 {current_page_num} 页，累计获取 {len(all_data)} 条目标日期({target_date})的数据")
        export_to_json(all_data)
        
    except Exception as e:
        print(f"❌ 程序异常: {e}")
        # 异常时自动备份已爬取数据，杜绝数据丢失
        if 'all_data' in locals() and all_data:
            backup_filename = f"四川省公共资源交易数据_异常备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            export_to_json(all_data, backup_filename)
    finally:
        if 'driver' in locals():
            print("\n🔌 关闭浏览器")
            driver.quit()

if __name__ == "__main__":
    main()
