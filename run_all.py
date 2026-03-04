import subprocess
import multiprocessing
import os
import time
import sys
import json
import glob
from datetime import datetime

# ===================== 配置项 =====================
# 定义四个爬虫脚本的名称（确保和实际文件名完全一致）
CRAWLER_SCRIPTS = [
    "sichuan crawler_platform.py",
    "chongqin crawler_platform.py",
    "guizhou crawler_platform.py",
    "quanguo crawler_platform.py"
]
# 爬虫生成JSON文件的目录（和爬虫代码里的导出目录保持一致）
CRAWLER_JSON_DIR = "data"
# 合并后JSON文件的保存目录
MERGED_JSON_DIR = "merged_data"
# 日志保存目录
LOG_DIR = "crawler_logs"
# Python解释器路径（自动获取当前环境，避免环境冲突）
PYTHON_EXEC = sys.executable
# 单个爬虫最大运行超时时间（秒），避免卡死
SCRIPT_TIMEOUT = 600
# 多进程打印锁（解决输出覆盖核心问题）
PRINT_LOCK = multiprocessing.Lock()

# ===================== 工具函数 =====================
def safe_print(content):
    """进程安全的打印函数，解决多进程输出覆盖问题"""
    with PRINT_LOCK:
        print(content)
        sys.stdout.flush()  # 强制刷新缓冲，确保输出立即写入

def create_dirs():
    """创建所有必需的目录，确保文件可正常保存"""
    for dir_path in [LOG_DIR, CRAWLER_JSON_DIR, MERGED_JSON_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    safe_print(f"✅ 所有目录已准备就绪")
    safe_print(f"   日志目录: {os.path.abspath(LOG_DIR)}")
    safe_print(f"   爬虫JSON目录: {os.path.abspath(CRAWLER_JSON_DIR)}")
    safe_print(f"   合并JSON目录: {os.path.abspath(MERGED_JSON_DIR)}")

def run_crawler(script_name):
    """运行单个爬虫脚本，进程安全输出，捕获所有异常和超时"""
    # 预生成日志文件名（主进程统一时间前缀，避免并行冲突）
    start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{script_name.replace(' ', '_')}_{start_timestamp}.log"
    log_path = os.path.join(LOG_DIR, log_filename)
    
    # 进程安全打印启动信息
    safe_print(f"\n🚀 启动爬虫脚本: {script_name}")
    safe_print(f"📝 日志保存路径: {log_path}")
    
    try:
        # 启动子进程运行爬虫脚本
        process = subprocess.Popen(
            [PYTHON_EXEC, script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 错误输出合并到标准输出，统一记录
            text=True,
            shell=False,
            cwd=os.getcwd(),
            bufsize=1,  # 行缓冲，确保实时输出
            encoding="utf-8"
        )
        
        # 实时输出并写入日志，带超时保护
        output_lines = []
        start_time = time.time()
        with open(log_path, "w", encoding="utf-8") as f:
            while True:
                # 超时判断
                if time.time() - start_time > SCRIPT_TIMEOUT:
                    process.kill()
                    timeout_msg = f"❌ 爬虫脚本 {script_name} 运行超时（{SCRIPT_TIMEOUT}秒），已强制终止"
                    safe_print(timeout_msg)
                    f.write(timeout_msg)
                    return (script_name, "超时", f"运行超过{SCRIPT_TIMEOUT}秒")
                
                # 读取输出行
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break
                if output:
                    output_stripped = output.strip()
                    output_lines.append(output_stripped)
                    # 进程安全打印
                    safe_print(f"[{script_name.split(' ')[0]}] {output_stripped}")
                    # 写入日志并立即刷新
                    f.write(output)
                    f.flush()
        
        # 获取脚本退出码
        return_code = process.wait()
        if return_code == 0:
            status = "成功"
            safe_print(f"✅ 爬虫脚本 {script_name} 运行完成")
        else:
            status = "失败"
            safe_print(f"❌ 爬虫脚本 {script_name} 运行失败，退出码: {return_code}")
        
        # 记录最终状态到日志
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== 运行结束 =====\n状态: {status}\n退出码: {return_code}\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return (script_name, status, return_code)
    
    except Exception as e:
        error_msg = f"❌ 运行爬虫脚本 {script_name} 时发生异常: {str(e)}"
        safe_print(error_msg)
        # 异常信息写入日志
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== 运行异常 =====\n异常信息: {str(e)}\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return (script_name, "异常", str(e))

def merge_crawler_json():
    """合并四个爬虫生成的最新JSON文件，以当天日期命名"""
    safe_print("\n" + "="*80)
    safe_print("📦 开始合并爬虫JSON文件")
    safe_print("="*80)
    
    # 获取当天日期，作为合并后的文件名
    today_str = datetime.now().strftime("%Y-%m-%d")
    merged_filename = f"{today_str}.json"
    merged_filepath = os.path.join(MERGED_JSON_DIR, merged_filename)
    
    # 查找data目录下所有本次运行生成的JSON文件（匹配爬虫命名规则）
    json_pattern = os.path.join(CRAWLER_JSON_DIR, "*公共资源交易数据_*.json")
    json_files = glob.glob(json_pattern)
    
    # 按修改时间排序，取最新的4个文件（对应本次运行的4个爬虫）
    if not json_files:
        safe_print("❌ 未找到任何爬虫生成的JSON文件，合并终止")
        return None
    json_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_json_files = json_files[:4]  # 取最新的4个
    
    # 合并所有数据
    all_merged_data = []
    success_count = 0
    fail_count = 0
    
    for json_file in latest_json_files:
        try:
            safe_print(f"🔍 读取文件: {os.path.basename(json_file)}")
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_merged_data.extend(data)
                    success_count += 1
                    safe_print(f"   成功读取 {len(data)} 条数据")
                else:
                    safe_print(f"⚠️  文件 {os.path.basename(json_file)} 格式不符合要求，跳过")
                    fail_count += 1
        except Exception as e:
            safe_print(f"❌ 读取文件 {os.path.basename(json_file)} 失败: {str(e)}")
            fail_count += 1
    
    # 写入合并后的文件
    if all_merged_data:
        with open(merged_filepath, "w", encoding="utf-8") as f:
            json.dump(all_merged_data, f, ensure_ascii=False, indent=2)
        
        safe_print(f"\n✅ JSON合并完成！")
        safe_print(f"   成功合并 {success_count} 个文件，跳过 {fail_count} 个文件")
        safe_print(f"   累计合并数据条数: {len(all_merged_data)}")
        safe_print(f"   合并文件保存路径: {os.path.abspath(merged_filepath)}")
        return merged_filepath
    else:
        safe_print("❌ 无有效数据可合并，合并终止")
        return None

# ===================== 主程序 =====================
def main():
    safe_print("="*80)
    safe_print("📢 公共资源交易平台爬虫集群主控程序")
    safe_print(f"🕒 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print("="*80)
    
    # 1. 初始化所有目录
    create_dirs()
    
    # 2. 检查爬虫脚本是否存在且为有效文件
    missing_scripts = []
    for script in CRAWLER_SCRIPTS:
        if not os.path.isfile(script):
            missing_scripts.append(script)
    
    if missing_scripts:
        safe_print(f"\n❌ 以下爬虫脚本不存在，无法运行:")
        for script in missing_scripts:
            safe_print(f"   - {script}")
        safe_print("\n请检查脚本文件名和路径是否正确，主控程序终止运行。")
        return
    
    safe_print(f"\n✅ 检测到所有 {len(CRAWLER_SCRIPTS)} 个爬虫脚本，准备并行启动...")
    
    # 3. 并行运行所有爬虫脚本
    start_time = time.time()
    # 固定进程数，避免资源占用过高
    with multiprocessing.Pool(processes=len(CRAWLER_SCRIPTS)) as pool:
        results = pool.map(run_crawler, CRAWLER_SCRIPTS)
    # 确保进程池完全关闭
    pool.close()
    pool.join()
    
    # 4. 汇总运行结果
    safe_print("\n" + "="*80)
    safe_print("📊 爬虫集群运行结果汇总")
    safe_print("="*80)
    
    success_count = 0
    fail_count = 0
    error_count = 0
    
    for script, status, code in results:
        safe_print(f"🔹 {script:<35} 状态: {status:<6} 详情: {code}")
        if status == "成功":
            success_count += 1
        elif status == "失败":
            fail_count += 1
        else:
            error_count += 1
    
    # 计算总耗时
    total_time = time.time() - start_time
    safe_print(f"\n📈 统计结果:")
    safe_print(f"   ✅ 成功运行: {success_count} 个")
    safe_print(f"   ❌ 运行失败: {fail_count} 个")
    safe_print(f"   ⚠️  运行异常: {error_count} 个")
    safe_print(f"   ⏱️  总耗时: {total_time:.2f} 秒")
    safe_print(f"   📝 所有日志已保存至: {os.path.abspath(LOG_DIR)}")
    
    # 5. 执行JSON合并功能
    merge_crawler_json()
    
    safe_print("\n" + "="*80)
    safe_print("🔚 主控程序全部运行完成")
    safe_print("="*80)

if __name__ == "__main__":
    # Windows系统多进程必需的保护措施
    if sys.platform == "win32":
        multiprocessing.freeze_support()
    
    # 启动主控程序
    main()
