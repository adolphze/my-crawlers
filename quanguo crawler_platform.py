import json
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ===================== 核心配置（与原代码完全兼容）=====================
TARGET_URL = "https://www.ggzy.gov.cn/deal/dealList.html"
BASE_URL = "https://www.ggzy.gov.cn"
# 跨平台统一字段规范，完全兼容所有历史版本
FIELDS = [
    "标题", "链接", "发布日期", "省份", "来源平台",
    "业务类型", "信息类型", "行业"
]
# 页面等待与重试配置
PAGE_WAIT = 2
MAX_RETRY = 3
ELEMENT_WAIT_TIMEOUT = 15  # 元素加载超时时间，适配网络波动与反爬延迟

# ===================== 无头浏览器初始化（反爬增强）=====================
def init_driver():
    """初始化无头Edge浏览器，适配GitHub Actions Ubuntu环境，绕过平台反爬检测"""
    edge_options = Options()
    
    # 无头模式核心配置（Ubuntu环境必须参数）
    edge_options.add_argument("--headless=new")  # Edge新版无头模式，大幅降低被检测概率
    edge_options.add_argument("--no-sandbox")  # 解决Ubuntu非root用户运行权限问题
    edge_options.add_argument("--disable-dev-shm-usage")  # 解决共享内存不足导致的崩溃
    edge_options.add_argument("--disable-gpu")  # 无头环境禁用GPU渲染
    edge_options.add_argument("--window-size=1920,1080")  # 固定桌面级分辨率，规避分辨率检测
    
    # 反爬核心配置：彻底隐藏selenium自动化特征
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option("useAutomationExtension", False)
    
    # 真实浏览器指纹配置
    edge_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0")
    edge_options.add_argument("--accept-language=zh-CN,zh;q=0.9,en;q=0.8")
    edge_options.add_argument("--disable-extensions")
    edge_options.add_argument("--disable-plugins-discovery")
    
    # 启动浏览器
    driver = webdriver.Edge(options=edge_options)
    driver.maximize_window()
    
    # 执行JS脚本，深度隐藏自动化特征，绕过平台反爬检测
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            // 隐藏webdriver核心检测属性
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            // 伪造浏览器插件信息
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            // 伪造语言环境
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            // 伪造chrome内核对象
            window.chrome = { runtime: {} };
            // 伪造权限查询结果
            Object.defineProperty(navigator, 'permissions', {
                get: () => ({
                    query: () => Promise.resolve({ state: 'granted' })
                })
            });
            // 覆盖selenium专属特征标识
            Object.defineProperty(window, 'cdc_adoQpoasnfa76pfcZLmcfl_', {
                get: () => undefined
            });
        """
    })
    
    print("✅ 无头Edge浏览器已启动，反爬防护配置已加载")
    return driver

# ===================== 数据解析函数（100%适配页面DOM结构）=====================
def parse_notice_item(notice_soup):
    """解析单个公告条目，完全兼容原有字段规范，确保数据完整性"""
    item = {field: "" for field in FIELDS}
    
    try:
        # 1. 解析标题、完整链接、发布日期
        h4_tag = notice_soup.find("h4")
        if h4_tag:
            a_tag = h4_tag.find("a")
            if a_tag:
                # 标题优先取title属性，兜底取文本内容
                item["标题"] = a_tag.get("title", "").strip() or a_tag.get_text(strip=True)
                # 修复相对链接，拼接完整可访问地址
                href = a_tag.get("href", "").strip()
                item["链接"] = BASE_URL + href if href.startswith("/") else href
            
            # 发布日期提取
            date_tag = h4_tag.find("span", class_="span_o")
            if date_tag:
                item["发布日期"] = date_tag.get_text(strip=True)
        
        # 2. 解析省份、来源平台、业务类型、信息类型、行业（完全适配页面成对标签结构）
        p_tag = notice_soup.find("p", class_="p_tw")
        if p_tag:
            span_list = p_tag.find_all("span")
            current_key = None
            # 成对匹配字段名和对应值，解决解析错位问题
            for span in span_list:
                span_text = span.get_text(strip=True)
                # 匹配字段名
                if "省份：" in span_text:
                    current_key = "省份"
                elif "来源平台：" in span_text:
                    current_key = "来源平台"
                elif "业务类型：" in span_text:
                    current_key = "业务类型"
                elif "信息类型：" in span_text:
                    current_key = "信息类型"
                elif "行业：" in span_text:
                    current_key = "行业"
                # 匹配对应字段值
                elif "span_on" in span.get("class", []) and current_key:
                    item[current_key] = span_text
                    current_key = None
                
    except Exception as e:
        print(f"⚠️ 解析单条数据失败: {e}")
    
    return item

def parse_current_page(driver):
    """解析当前页面所有公告，带重试机制，解决页面加载不完整导致的空数据问题"""
    try:
        # 等待列表容器加载完成，避免提前解析空页面
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "toview"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        notice_list = soup.find_all("div", class_="publicont")
        page_data = []
        
        for notice in notice_list:
            item = parse_notice_item(notice)
            page_data.append(item)
        
        print(f"📄 当前页解析完成，共获取 {len(page_data)} 条数据")
        return page_data
    except Exception as e:
        print(f"⚠️ 解析当前页失败: {e}")
        return []

def get_total_pages(driver):
    """获取总页数，精准控制翻页次数，解决原代码提前终止的问题"""
    try:
        # 优先从页面右上角页码提取（格式：当前页/总页数）
        top_right_text = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "topRight"))
        ).text
        match = re.search(r"\d+/(\d+)", top_right_text)
        if match:
            total_pages = int(match.group(1))
            print(f"📊 检测到总页数为: {total_pages}")
            return total_pages
        
        # 兜底从分页区提取
        paging_text = driver.find_element(By.ID, "paging").text
        match = re.search(r"共\s*(\d+)\s*页", paging_text)
        if match:
            total_pages = int(match.group(1))
            print(f"📊 检测到总页数为: {total_pages}")
            return total_pages
    except Exception as e:
        print(f"⚠️ 获取总页数失败: {e}")
    return None

def has_next_page(driver):
    """检测下一页按钮是否可点击，适配平台分页结构，修复原代码参数错误问题"""
    try:
        # 精准定位目标网站的下一页按钮
        next_btn = driver.find_element(By.XPATH, "//div[@id='paging']//a[contains(text(),'下一页')]")
        # 校验按钮是否可点击：有有效跳转链接、未禁用
        href_attr = next_btn.get_attribute("href") or ""
        if next_btn.is_enabled() and "javascript:getList" in href_attr:
            return next_btn
        return None
    except Exception as e:
        print(f"⚠️ 检测下一页按钮失败: {e}")
        return None

def check_captcha_modal(driver):
    """检测验证码弹窗，自动化环境触发时直接终止并备份数据（无法人工处理）"""
    try:
        modal = driver.find_element(By.ID, "verifyCodeModal")
        if modal.is_displayed():
            print("\n❌ 触发平台反爬验证码，自动化环境无法手动处理，爬取终止")
            return True
    except:
        pass
    return False

# ===================== JSON导出函数（适配GitHub Actions）=====================
def export_to_json(data, filename=None):
    """导出数据到JSON文件，统一保存到data/目录，自动创建文件夹，中文无乱码"""
    if not data:
        print("❌ 无有效数据可导出")
        return
    
    # 生成默认文件名，与原命名规范保持一致
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"全国公共资源交易数据_{timestamp}.json"
    
    # 确保data目录存在（GitHub Actions自动创建）
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", filename)
    
    # 写入JSON文件，格式化输出，保证中文正常显示
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据已导出到: {filepath}")
    return filepath

# ===================== 主程序（全自动无人工干预）=====================
def main():
    print("="*60)
    print("📢 全国公共资源交易平台全自动爬虫启动")
    print("="*60)
    
    # 计算北京时间（适配GitHub Actions UTC时区）
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    target_date = (beijing_now - timedelta(days=1)).strftime("%Y-%m-%d")  # 目标爬取：前一天数据
    stop_date = (beijing_now - timedelta(days=2)).strftime("%Y-%m-%d")    # 停止触发：前天数据
    print(f"📅 目标爬取日期（前一天）: {target_date}")
    print(f"🛑 停止触发日期（前天）: {stop_date}")
    
    all_data = []
    total_pages = None
    current_page_num = 1
    consecutive_failures = 0
    driver = None
    crawl_stop_flag = False  # 日期触发停止标记
    
    try:
        # 1. 初始化无头浏览器
        driver = init_driver()
        
        # 2. 导航到目标交易页面
        driver.get(TARGET_URL)
        print(f"🌐 已导航到目标网址: {TARGET_URL}")
        
        # 3. 等待页面核心元素加载完成
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "toview"))
        )
        print("✅ 页面核心元素加载完成")
        
        # 4. 自动点击「近三天」按钮，缩小数据范围，提升爬取效率
        try:
            three_days_btn = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.ID, "choose_time_02"))
            )
            three_days_btn.click()
            print("✅ 已点击「近三天」筛选按钮")
            
            # 等待页面列表刷新完成
            time.sleep(PAGE_WAIT)
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.staleness_of(driver.find_element(By.CSS_SELECTOR, "div.publicont:first-child"))
            )
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.publicont"))
            )
            print("✅ 数据列表已刷新完成")
            
        except Exception as e:
            print(f"⚠️ 点击筛选按钮失败，将使用全量数据过滤: {e}")
        
        # 5. 获取总页数
        total_pages = get_total_pages(driver)
        if not total_pages:
            print("⚠️ 无法获取总页数，将使用下一页兜底模式爬取")
        
        # 6. 循环爬取所有页面，新增日期停止逻辑
        while True:
            print(f"\n🚀 正在爬取第 {current_page_num} 页...")
            
            # 检测验证码弹窗，触发则终止爬取
            if check_captcha_modal(driver):
                break
            
            # 带重试机制解析当前页
            page_data = []
            for retry in range(MAX_RETRY):
                page_data = parse_current_page(driver)
                if page_data:
                    consecutive_failures = 0
                    break
                print(f"⚠️ 第 {current_page_num} 页解析为空，重试 ({retry+1}/{MAX_RETRY})...")
                time.sleep(PAGE_WAIT)
            
            # 核心逻辑：先完成当前页目标数据采集，再判断停止规则
            if page_data:
                # 过滤目标日期数据，累加有效数据
                target_data = [item for item in page_data if item["发布日期"] == target_date]
                all_data.extend(target_data)
                print(f"🔍 本页共 {len(page_data)} 条，目标日期({target_date})数据 {len(target_data)} 条")
                
                # 检测到停止日期，标记终止，完成当前页后不再翻页
                has_stop_date = any(item["发布日期"] == stop_date for item in page_data)
                if has_stop_date:
                    print(f"🛑 检测到停止日期({stop_date})数据，完成当前页采集后终止爬取")
                    crawl_stop_flag = True
            else:
                consecutive_failures += 1
                print(f"❌ 第 {current_page_num} 页多次重试后仍无数据")
            
            # 终止条件判断（日期停止规则优先级最高）
            if crawl_stop_flag:
                print("🔚 已触发日期停止规则，终止爬取")
                break
            if consecutive_failures >= MAX_RETRY:
                print("🔚 连续多次无数据，终止爬取")
                break
            
            # 已知总页数模式，精准控制终止
            if total_pages:
                if current_page_num >= total_pages:
                    print("🔚 已爬取完成所有页面，到达总页数上限")
                    break
                
                # 翻页逻辑
                current_page_num += 1
                flip_success = False
                next_btn = has_next_page(driver)
                
                if next_btn:
                    for retry in range(MAX_RETRY):
                        try:
                            next_btn.click()
                            time.sleep(PAGE_WAIT)
                            # 等待页面列表刷新完成
                            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                                EC.presence_of_element_located((By.ID, "toview"))
                            )
                            flip_success = True
                            break
                        except Exception as e:
                            print(f"⚠️ 点击下一页失败，重试 ({retry+1}/{MAX_RETRY}): {e}")
                            time.sleep(PAGE_WAIT)
                
                # 翻页失败则终止
                if not flip_success:
                    print(f"❌ 无法跳转至第 {current_page_num} 页，爬取终止")
                    break
            else:
                # 未知总页数兜底模式
                next_btn = has_next_page(driver)
                if next_btn and consecutive_failures < MAX_RETRY:
                    try:
                        next_btn.click()
                        time.sleep(PAGE_WAIT)
                        current_page_num += 1
                    except Exception as e:
                        print(f"⚠️ 点击下一页失败: {e}")
                        break
                else:
                    print("🔚 已爬取到最后一页，或连续失败次数过多，爬取终止")
                    break
        
        # 7. 导出最终JSON数据
        print(f"\n📊 爬取任务完成！共爬取 {current_page_num} 页，累计获取 {len(all_data)} 条目标日期({target_date})有效数据")
        export_to_json(all_data)
        
    except Exception as e:
        print(f"❌ 程序运行异常: {e}")
        # 异常时自动备份已爬取数据，杜绝数据丢失
        if 'all_data' in locals() and all_data:
            backup_filename = f"全国公共资源交易数据_异常备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            export_to_json(all_data, backup_filename)
    finally:
        if driver:
            print("\n🔌 已关闭浏览器")
            driver.quit()

if __name__ == "__main__":
    main()
