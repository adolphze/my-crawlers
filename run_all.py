import subprocess
import multiprocessing
import os
import time
import sys
from datetime import datetime

# ===================== 配置项 =====================
# 定义四个爬虫脚本的名称（注意空格处理，确保路径正确）
CRAWLER_SCRIPTS = [
    "sichuan crawler_platform.py",
    "chongqin crawler_platform.py",
    "guizhou crawler_platform.py",
    "quanguo crawler_platform.py"
]

# 日志保存目录（自动创建）
LOG_DIR = "crawler_logs"
# Python解释器路径（适配不同环境，优先用当前环境的python）
PYTHON_EXEC = sys.executable  # 自动获取当前运行环境的python路径，避免环境冲突

# ===================== 工具函数 =====================
def create_log_dir():
    """创建日志目录，确保日志文件可正常保存"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    print(f"✅ 日志目录已准备就绪: {os.path.abspath(LOG_DIR)}")

def run_crawler(script_name):
    """运行单个爬虫脚本，捕获输出和错误，保存日志"""
    # 生成日志文件名（带时间戳，避免覆盖）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{script_name.replace(' ', '_')}_{timestamp}.log"
    log_path = os.path.join(LOG_DIR, log_filename)
    
    # 打印启动信息
    print(f"\n🚀 启动爬虫脚本: {script_name}")
    print(f"📝 日志将保存至: {log_path}")
    
    try:
        # 启动子进程运行爬虫脚本，捕获stdout和stderr
        # shell=True 处理脚本名称中的空格（Windows/Linux均兼容）
        process = subprocess.Popen(
            [PYTHON_EXEC, script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 将错误输出重定向到标准输出，统一记录
            text=True,
            shell=False,  # 关闭shell，避免安全风险，通过列表传参处理空格
            cwd=os.getcwd()  # 保持当前工作目录，确保脚本能找到依赖
        )
        
        # 实时输出并写入日志
        with open(log_path, "w", encoding="utf-8") as f:
            while True:
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break
                if output:
                    # 实时打印到控制台
                    print(f"[{script_name[:4]}] {output.strip()}")
                    # 写入日志文件
                    f.write(output)
                    f.flush()  # 立即刷新，避免日志丢失
        
        # 获取脚本退出码
        return_code = process.wait()
        if return_code == 0:
            status = "成功"
            print(f"✅ 爬虫脚本 {script_name} 运行完成")
        else:
            status = "失败"
            print(f"❌ 爬虫脚本 {script_name} 运行失败，退出码: {return_code}")
        
        # 记录最终状态到日志
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== 运行结束 =====\n状态: {status}\n退出码: {return_code}\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return (script_name, status, return_code)
    
    except Exception as e:
        error_msg = f"❌ 运行爬虫脚本 {script_name} 时发生异常: {str(e)}"
        print(error_msg)
        # 异常信息写入日志
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== 运行异常 =====\n异常信息: {str(e)}\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return (script_name, "异常", str(e))

# ===================== 主程序 =====================
def main():
    print("="*80)
    print("📢 公共资源交易平台爬虫集群主控程序启动")
    print(f"🕒 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # 1. 初始化日志目录
    create_log_dir()
    
    # 2. 检查爬虫脚本是否存在
    missing_scripts = []
    for script in CRAWLER_SCRIPTS:
        if not os.path.exists(script):
            missing_scripts.append(script)
    
    if missing_scripts:
        print(f"\n❌ 以下爬虫脚本不存在，无法运行:")
        for script in missing_scripts:
            print(f"   - {script}")
        print("\n请检查脚本文件名和路径是否正确，主控程序终止运行。")
        return
    
    print(f"\n✅ 检测到所有 {len(CRAWLER_SCRIPTS)} 个爬虫脚本，准备并行启动...")
    
    # 3. 并行运行所有爬虫脚本（使用多进程）
    start_time = time.time()
    with multiprocessing.Pool(processes=len(CRAWLER_SCRIPTS)) as pool:
        # 并行执行，获取每个脚本的运行结果
        results = pool.map(run_crawler, CRAWLER_SCRIPTS)
    
    # 4. 汇总运行结果
    print("\n" + "="*80)
    print("📊 爬虫集群运行结果汇总")
    print("="*80)
    
    success_count = 0
    fail_count = 0
    error_count = 0
    
    for script, status, code in results:
        print(f"🔹 {script:<30} 状态: {status:<6} 详情: {code}")
        if status == "成功":
            success_count += 1
        elif status == "失败":
            fail_count += 1
        else:
            error_count += 1
    
    # 计算总耗时
    total_time = time.time() - start_time
    print(f"\n📈 统计结果:")
    print(f"   ✅ 成功运行: {success_count} 个")
    print(f"   ❌ 运行失败: {fail_count} 个")
    print(f"   ⚠️  运行异常: {error_count} 个")
    print(f"   ⏱️  总耗时: {total_time:.2f} 秒")
    print(f"   📝 所有日志已保存至: {os.path.abspath(LOG_DIR)}")
    
    print("\n" + "="*80)
    print("🔚 主控程序运行完成")
    print("="*80)

if __name__ == "__main__":
    # Windows系统下多进程必须的保护措施
    if sys.platform == "win32":
        multiprocessing.freeze_support()
    
    # 启动主控程序
    main()



