# -*- coding: utf-8 -*-

"""
雷电模拟器应用管理任务模块
通过绑定的模拟器窗口自动获取app列表，并通过下拉框选择需要启动的应用
"""

import logging
import subprocess
import time
import os
import re
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

def _get_unique_instance_index():
    """获取唯一的实例索引分配器（用于存储全局状态）"""
    pass

def _interruptible_sleep(duration: float, stop_checker=None):
    """可中断的睡眠函数"""
    if duration <= 0:
        return

    elapsed_time = 0.0
    check_interval = 0.1  # 每100ms检查一次停止信号

    while elapsed_time < duration:
        if stop_checker and stop_checker():
            logger.info(f"延迟被用户中断，已延迟 {elapsed_time:.2f}/{duration:.2f} 秒")
            return

        sleep_time = min(check_interval, duration - elapsed_time)
        time.sleep(sleep_time)
        elapsed_time += sleep_time

def _handle_delay_after_operation(params, stop_checker=None):
    """处理操作后延迟"""
    try:
        import random

        delay_mode = params.get('delay_mode', '固定延迟')

        if delay_mode == '固定延迟':
            delay_time = params.get('fixed_delay', 2.0)
            logger.info(f"执行固定延迟: {delay_time} 秒")
            _interruptible_sleep(delay_time, stop_checker)
        elif delay_mode == '随机延迟':
            min_delay = params.get('min_delay', 1.0)
            max_delay = params.get('max_delay', 3.0)
            delay_time = random.uniform(min_delay, max_delay)
            logger.info(f"执行随机延迟: {delay_time:.2f} 秒 (范围: {min_delay}-{max_delay})")
            _interruptible_sleep(delay_time, stop_checker)
        else:
            logger.warning(f"未知的延迟模式: {delay_mode}")
    except Exception as e:
        logger.error(f"执行延迟时发生错误: {e}")

# 任务类型标识
TASK_TYPE = "雷电应用管理"
TASK_NAME = "雷电应用管理"

def get_ldplayer_console_path():
    """获取雷电模拟器控制台程序路径"""
    import winreg
    
    console_paths = []
    
    # 常见安装路径
    common_paths = [
        r"C:\LDPlayer\LDPlayer9\ldconsole.exe",
        r"C:\LDPlayer\LDPlayer4\ldconsole.exe", 
        r"C:\ChangZhi\dnplayer2\dnconsole.exe",
        r"D:\LDPlayer\LDPlayer9\ldconsole.exe",
        r"D:\LDPlayer\LDPlayer4\ldconsole.exe",
        r"E:\LDPlayer\LDPlayer9\ldconsole.exe",
        r"F:\LDPlayer\LDPlayer9\ldconsole.exe"
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            console_paths.append(path)
    
    # 尝试从注册表获取
    try:
        # 雷电模拟器9
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\雷电模拟器")
        install_location = winreg.QueryValueEx(key, "InstallLocation")[0]
        winreg.CloseKey(key)
        
        ldconsole_path = os.path.join(install_location, "ldconsole.exe")
        if os.path.exists(ldconsole_path) and ldconsole_path not in console_paths:
            console_paths.append(ldconsole_path)
    except:
        pass
    
    return console_paths[0] if console_paths else None

def find_parent_window(child_hwnd):
    """查找子窗口的父窗口"""
    try:
        import win32gui
        
        if not child_hwnd or not win32gui.IsWindow(child_hwnd):
            return None
            
        # 获取父窗口
        parent_hwnd = win32gui.GetParent(child_hwnd)
        if parent_hwnd and win32gui.IsWindow(parent_hwnd):
            parent_class = win32gui.GetClassName(parent_hwnd)
            parent_title = win32gui.GetWindowText(parent_hwnd)
            logger.info(f"找到父窗口: {parent_hwnd} (类名: {parent_class}, 标题: {parent_title})")
            
            # 如果父窗口是雷电模拟器主窗口，返回它
            if parent_class == "LDPlayerMainFrame":
                return parent_hwnd
                
            # 否则继续向上查找
            return find_parent_window(parent_hwnd)
        
        # 如果没有父窗口，检查当前窗口是否就是主窗口
        current_class = win32gui.GetClassName(child_hwnd)
        if current_class == "LDPlayerMainFrame":
            return child_hwnd
            
        return None
        
    except Exception as e:
        logger.error(f"查找父窗口时出错: {e}")
        return None

def get_ldplayer_instance_by_hwnd(target_hwnd):
    """根据窗口句柄获取雷电模拟器实例信息"""
    try:
        console_path = get_ldplayer_console_path()
        if not console_path:
            logger.warning("未找到雷电模拟器控制台程序")
            return None

        logger.info(f"使用控制台程序: {console_path}")

        # 获取所有实例
        result = subprocess.run([console_path, "list2"], capture_output=True, text=True, encoding='utf-8')
        logger.info(f"控制台命令返回码: {result.returncode}")
        logger.info(f"控制台命令输出: {result.stdout}")
        if result.stderr:
            logger.warning(f"控制台命令错误: {result.stderr}")

        if result.returncode != 0:
            logger.error(f"获取雷电模拟器实例列表失败: {result.stderr}")
            return None

        # 查找父窗口（如果绑定的是子窗口）
        parent_hwnd = find_parent_window(target_hwnd)
        search_hwnd = parent_hwnd if parent_hwnd else target_hwnd

        logger.info(f"搜索窗口句柄: {search_hwnd} (原始: {target_hwnd}, 父窗口: {parent_hwnd})")

        # 解析实例列表
        all_instances = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(',')
                logger.debug(f"解析实例行: {line} -> {parts}")
                if len(parts) >= 4:
                    instance = {
                        'index': parts[0],
                        'title': parts[1],
                        'top_hwnd': int(parts[2]) if parts[2].isdigit() else 0,
                        'bind_hwnd': int(parts[3]) if parts[3].isdigit() else 0,
                        'android_started': parts[4] if len(parts) > 4 else '0',
                        'pid': parts[5] if len(parts) > 5 else '0'
                    }
                    all_instances.append(instance)
                    logger.debug(f"解析得到实例: {instance}")

                    # 匹配窗口句柄
                    if (instance['top_hwnd'] == search_hwnd or
                        instance['bind_hwnd'] == search_hwnd or
                        instance['top_hwnd'] == target_hwnd or
                        instance['bind_hwnd'] == target_hwnd):
                        logger.info(f"找到匹配的雷电模拟器实例: {instance}")
                        return instance

        logger.warning(f"未找到匹配窗口句柄 {target_hwnd} 的雷电模拟器实例")
        logger.info(f"所有可用实例: {all_instances}")

        # 如果没有精确匹配，尝试使用第一个运行中的实例
        running_instances = [inst for inst in all_instances if inst['android_started'] == '1']
        if running_instances:
            logger.info(f"使用第一个运行中的实例: {running_instances[0]}")
            return running_instances[0]

        return None

    except Exception as e:
        logger.error(f"获取雷电模拟器实例信息失败: {e}")
        return None

def ensure_ldplayer_adb_connection(instance_index):
    """确保雷电模拟器ADB连接正常 - 使用先进ADB连接池"""
    try:
        # 使用先进ADB连接池
        from utils.advanced_adb_manager import get_advanced_adb_pool

        logger.info(f"使用先进ADB连接池检查雷电模拟器实例 {instance_index}")

        pool = get_advanced_adb_pool()
        healthy_devices = pool.get_healthy_devices()

        if healthy_devices:
            logger.info(f"✅ 先进ADB连接池发现 {len(healthy_devices)} 个健康设备")

            # 查找雷电模拟器设备
            ldplayer_devices = [d for d in healthy_devices if 'emulator-' in d.device_id or '5555' in d.device_id]

            if ldplayer_devices:
                logger.info(f"✅ 发现 {len(ldplayer_devices)} 个雷电设备")
                return True
            else:
                logger.info("⚠️ 未发现雷电设备，但有其他健康设备")
                return len(healthy_devices) > 0

        # 回退到传统方法
        logger.info("🔄 先进ADB连接池无设备，回退到传统方法")

        from utils.ldplayer_finder import get_adb_path
        adb_cmd = get_adb_path()

        if not adb_cmd:
            logger.error("未找到雷电模拟器的ADB命令")
            return False

        # 使用ADBCommand执行命令
        from utils.advanced_adb_manager import ADBCommand

        # 1. 启动ADB服务器
        start_cmd = ADBCommand(['start-server'], timeout=10.0)
        success, stdout, stderr = pool.execute_command_sync(start_cmd)
        logger.info(f"ADB start-server结果: {'成功' if success else '失败'}")

        # 2. 检查设备连接
        devices_cmd = ADBCommand(['devices'], timeout=5.0)
        success, stdout, stderr = pool.execute_command_sync(devices_cmd)

        if success:
            logger.info(f"ADB devices输出: {stdout}")

            # 解析设备列表
            devices = []
            for line in stdout.split('\n'):
                if 'emulator-' in line and 'device' in line:
                    devices.append(line.split()[0])

            if devices:
                logger.info(f"✅ 发现 {len(devices)} 个设备")
                return True

            # 3. 尝试连接雷电模拟器端口
            logger.info("没有发现ADB设备，尝试连接雷电模拟器ADB端口")
            base_port = 5555 + instance_index * 2
            connect_cmd = f"127.0.0.1:{base_port}"

            logger.info(f"尝试连接ADB端口: {connect_cmd}")
            connect_adb_cmd = ADBCommand(['connect', connect_cmd], timeout=10.0)
            success, stdout, stderr = pool.execute_command_sync(connect_adb_cmd)
            logger.info(f"ADB connect结果: {'成功' if success else '失败'}, 输出: {stdout}")

            # 再次检查设备
            devices_cmd2 = ADBCommand(['devices'], timeout=5.0)
            success, stdout, stderr = pool.execute_command_sync(devices_cmd2)

            if success:
                logger.info(f"连接后ADB devices输出: {stdout}")
                devices = []
                for line in stdout.split('\n'):
                    if 'emulator-' in line and 'device' in line:
                        devices.append(line.split()[0])

                return len(devices) > 0

        return len(devices) > 0

    except Exception as e:
        logger.error(f"确保ADB连接时出错: {e}")
        return False

def get_installed_apps(instance_index):
    """获取指定雷电模拟器实例中安装的应用列表（改进版）"""
    try:
        console_path = get_ldplayer_console_path()
        if not console_path:
            logger.warning("未找到雷电模拟器控制台程序")
            return []

        # 方法1：获取第三方应用（推荐）
        cmd = [console_path, "adb", "--index", str(instance_index), "--command", "shell pm list packages -3"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        apps = []
        if result.returncode == 0:
            logger.info("使用 pm list packages -3 获取第三方应用")
            for line in result.stdout.strip().split('\n'):
                if line.startswith('package:'):
                    package_name = line.replace('package:', '').strip()
                    if package_name:
                        app_info = _get_app_info_enhanced(console_path, instance_index, package_name)
                        if app_info:
                            apps.append(app_info)
        else:
            # 回退到原方法
            logger.info("回退到基础方法获取应用列表")
            cmd = [console_path, "adb", "--index", str(instance_index), "--command", "shell pm list packages"]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            if result.returncode != 0:
                logger.error(f"获取应用列表失败: {result.stderr}")
                return []

            for line in result.stdout.strip().split('\n'):
                if line.startswith('package:'):
                    package_name = line.replace('package:', '').strip()
                    if package_name:
                        # 过滤系统应用，只显示用户安装的应用
                        if not _is_system_package(package_name):
                            app_info = _get_app_info_enhanced(console_path, instance_index, package_name)
                            if app_info:
                                apps.append(app_info)

        # 按应用名称排序
        apps.sort(key=lambda x: x.get('name', x.get('package', '')))
        logger.info(f"获取到 {len(apps)} 个用户安装的应用")
        return apps

    except Exception as e:
        logger.error(f"获取应用列表时出错: {e}")
        return []

def _is_system_package(package_name):
    """判断是否为系统应用包"""
    system_prefixes = [
        'android.',
        'com.android.',
        'com.google.',
        'com.qualcomm.',
        'com.qti.',
        'org.chromium.',
        'com.changzhi.',  # 雷电模拟器相关
        'com.ldplayer.',  # 雷电模拟器相关
    ]
    
    return any(package_name.startswith(prefix) for prefix in system_prefixes)

def _get_app_info_enhanced(console_path, instance_index, package_name):
    """获取应用的详细信息（改进版）"""
    try:
        # 方法1：尝试获取应用标签（显示名称）
        cmd = [console_path, "adb", "--index", str(instance_index), "--command",
               f"shell pm dump {package_name} | grep -E 'applicationLabel|versionName'"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        app_name = package_name  # 默认使用包名
        version = ""

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split('\n'):
                if 'applicationLabel' in line:
                    # 提取应用名称
                    parts = line.split('=')
                    if len(parts) > 1:
                        app_name = parts[1].strip().strip('"')
                elif 'versionName' in line:
                    # 提取版本信息
                    parts = line.split('=')
                    if len(parts) > 1:
                        version = parts[1].strip()

        # 方法2：如果上面失败，尝试获取启动Activity
        if app_name == package_name:
            cmd = [console_path, "adb", "--index", str(instance_index), "--command",
                   f"shell pm dump {package_name} | grep -A 3 'android.intent.action.MAIN'"]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            if result.returncode == 0 and result.stdout:
                # 如果有MAIN activity，说明是可启动的应用
                pass

        # 构建显示名称
        if version:
            display_name = f"{app_name} v{version} ({package_name})"
        else:
            display_name = f"{app_name} ({package_name})"

        return {
            'package': package_name,
            'name': app_name,
            'version': version,
            'display_name': display_name,
            'is_launchable': _check_app_launchable(console_path, instance_index, package_name)
        }

    except Exception as e:
        logger.debug(f"获取应用 {package_name} 信息时出错: {e}")
        return {
            'package': package_name,
            'name': package_name,
            'version': '',
            'display_name': package_name,
            'is_launchable': False
        }

def _check_app_launchable(console_path, instance_index, package_name):
    """检查应用是否可启动"""
    try:
        cmd = [console_path, "adb", "--index", str(instance_index), "--command",
               f"shell pm dump {package_name} | grep -c 'android.intent.action.MAIN'"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0 and result.stdout.strip():
            count = int(result.stdout.strip())
            return count > 0
        return False

    except Exception:
        return False

def _get_app_info(console_path, instance_index, package_name):
    """获取应用的详细信息（兼容性方法）"""
    return _get_app_info_enhanced(console_path, instance_index, package_name)

def launch_app(instance_index, package_name):
    """启动指定的应用（改进版，多种方法尝试）"""
    try:
        console_path = get_ldplayer_console_path()
        if not console_path:
            logger.error("未找到雷电模拟器控制台程序")
            return False

        logger.info(f"尝试启动应用: {package_name}")

        # 方法1：使用runapp命令（雷电专用）
        logger.info("方法1: 使用 ldconsole runapp")
        cmd = [console_path, "runapp", "--index", str(instance_index), "--packagename", package_name]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            logger.info(f"runapp 成功启动应用: {package_name}")
            return True
        else:
            logger.warning(f"runapp 启动失败: {result.stderr}")

        # 方法2：使用 monkey 启动（最可靠）
        logger.info("方法2: 使用 monkey 启动")
        cmd = [console_path, "adb", "--index", str(instance_index), "--command",
               f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                               creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0 and "No activities found" not in result.stdout:
            logger.info(f"monkey 成功启动应用: {package_name}")
            return True
        else:
            logger.warning(f"monkey 启动失败: {result.stderr}")

        # 方法3：使用 am start 启动主Activity
        logger.info("方法3: 使用 am start 启动主Activity")
        cmd = [console_path, "adb", "--index", str(instance_index), "--command",
               f"shell am start -W -S -a android.intent.action.MAIN -c android.intent.category.LAUNCHER {package_name}"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                               creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0 and "Error" not in result.stdout:
            logger.info(f"am start 成功启动应用: {package_name}")
            return True
        else:
            logger.warning(f"am start 启动失败: {result.stderr}")

        # 方法4：尝试获取启动Activity并直接启动
        logger.info("方法4: 获取启动Activity并直接启动")
        main_activity = _get_main_activity(console_path, instance_index, package_name)
        if main_activity:
            cmd = [console_path, "adb", "--index", str(instance_index), "--command",
                   f"shell am start -W -S -n {package_name}/{main_activity}"]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            if result.returncode == 0:
                logger.info(f"直接启动Activity成功: {package_name}/{main_activity}")
                return True
            else:
                logger.warning(f"直接启动Activity失败: {result.stderr}")

        logger.error(f"所有方法都无法启动应用: {package_name}")
        return False

    except Exception as e:
        logger.error(f"启动应用时出错: {e}")
        return False

def close_app(instance_index, package_name):
    """关闭指定的应用（多种方法尝试）"""
    try:
        console_path = get_ldplayer_console_path()
        if not console_path:
            logger.error("未找到雷电模拟器控制台程序")
            return False

        logger.info(f"尝试关闭应用: {package_name}")

        # 方法1：使用 force-stop 强制停止应用
        logger.info(f" 方法1: 使用 force-stop 强制停止")
        cmd = [console_path, "adb", "--index", str(instance_index), "--command",
               f"shell am force-stop {package_name}"]
        logger.info(f" 执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            logger.info(f" force-stop 成功关闭应用: {package_name}")
            return True
        else:
            logger.warning(f" force-stop 关闭失败: {result.stderr}")

        # 方法2：使用 kill 命令杀死进程
        logger.info(" 方法2: 使用 kill 命令杀死进程")
        # 先获取进程列表
        cmd = [console_path, "adb", "--index", str(instance_index), "--command", "shell ps"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if package_name in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        pid = parts[1]  # 第二列通常是PID
                        logger.info(f"找到进程PID: {pid}")

                        # 杀死进程
                        kill_cmd = [console_path, "adb", "--index", str(instance_index), "--command",
                                   f"shell kill {pid}"]
                        kill_result = subprocess.run(kill_cmd, capture_output=True, text=True, encoding='utf-8')

                        if kill_result.returncode == 0:
                            logger.info(f"kill 成功关闭应用: {package_name} (PID: {pid})")
                            return True
                        else:
                            logger.warning(f"kill 关闭失败: {kill_result.stderr}")

        # 方法3：使用 killapp 命令（如果雷电支持）
        logger.info("方法3: 使用 killapp 命令")
        cmd = [console_path, "killapp", "--index", str(instance_index), "--packagename", package_name]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            logger.info(f"killapp 成功关闭应用: {package_name}")
            return True
        else:
            logger.warning(f"killapp 关闭失败: {result.stderr}")

        logger.error(f"所有方法都无法关闭应用: {package_name}")
        return False

    except Exception as e:
        logger.error(f"关闭应用时出错: {e}")
        return False

def _get_main_activity(console_path, instance_index, package_name):
    """获取应用的主Activity"""
    try:
        cmd = [console_path, "adb", "--index", str(instance_index), "--command",
               f"shell pm dump {package_name} | grep -A 5 'android.intent.action.MAIN'"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split('\n'):
                if 'Activity' in line and package_name in line:
                    # 提取Activity名称
                    parts = line.split()
                    for part in parts:
                        if package_name in part and '/' in part:
                            activity = part.split('/')[-1]
                            if activity.startswith('.'):
                                return activity
                            else:
                                return f".{activity}"
        return None

    except Exception as e:
        logger.debug(f"获取主Activity失败: {e}")
        return None

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """获取参数定义"""
    from .task_utils import get_standard_next_step_delay_params, merge_params_definitions

    # 原有的雷电应用管理参数
    ldplayer_params = {
        # 操作模式选择
        "operation_mode": {
            "label": "操作模式",
            "type": "select",
            "options": ["启动应用", "重启应用", "关闭应用"],
            "default": "启动应用",
            "tooltip": "选择要执行的应用操作"
        },
        
        # 应用选择
        "---app_selection---": {
            "type": "separator",
            "label": "应用选择"
        },
        "refresh_apps": {
            "label": "刷新应用列表",
            "type": "button",
            "button_text": "刷新",
            "tooltip": "重新获取模拟器中的应用列表",
            "widget_hint": "refresh_apps",
            "hide_in_preview": True
        },
        "selected_app": {
            "label": "选择应用",
            "type": "select",
            "options": ["请先刷新应用列表"],
            "default": "请先刷新应用列表",
            "tooltip": "选择要启动的应用",
            "widget_hint": "app_selector"
        },

        # 延迟参数
        "---delay_params---": {"type": "separator", "label": "延迟设置"},
        "delay_mode": {
            "label": "延迟模式",
            "type": "select",
            "options": ["固定延迟", "随机延迟"],
            "default": "固定延迟",
            "tooltip": "选择固定延迟时间还是随机延迟时间"
        },
        "fixed_delay": {
            "label": "固定延迟 (秒)",
            "type": "float",
            "default": 2.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置固定的延迟时间",
            "condition": {"param": "delay_mode", "value": "固定延迟"}
        },
        "min_delay": {
            "label": "最小延迟 (秒)",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置随机延迟的最小值",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        },
        "max_delay": {
            "label": "最大延迟 (秒)",
            "type": "float",
            "default": 3.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置随机延迟的最大值",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        },

        # 执行后操作
        "---post_execute---": {"type": "separator", "label": "执行后操作"},
        "on_success": {
            "label": "成功后操作",
            "type": "select",
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "操作成功后的行为"
        },
        "success_jump_target_id": {
            "label": "成功跳转目标ID",
            "type": "int",
            "default": 0,
            "min": 0,
            "widget_hint": "card_selector",
            "condition": {"param": "on_success", "value": "跳转到步骤"}
        },
        "on_failure": {
            "label": "失败后操作", 
            "type": "select",
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "操作失败后的行为"
        },
        "failure_jump_target_id": {
            "label": "失败跳转目标ID",
            "type": "int",
            "default": 0,
            "min": 0,
            "widget_hint": "card_selector",
            "condition": {"param": "on_failure", "value": "跳转到步骤"}
        }
    }

    # 合并延迟参数
    return merge_params_definitions(ldplayer_params, get_standard_next_step_delay_params())

def _handle_success(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理成功情况"""
    if action == "跳转到步骤" and jump_id is not None:
        logger.info(f"操作成功，跳转到步骤 {jump_id}")
        return True, "跳转到步骤", jump_id
    elif action == "停止工作流":
        logger.info("操作成功，停止工作流")
        return True, "停止工作流", None
    elif action == "继续执行本步骤":
        logger.info("操作成功，继续执行本步骤")
        return True, "继续执行本步骤", card_id
    else:  # "执行下一步"
        logger.info("操作成功，继续执行下一步")
        return True, "执行下一步", None

def _handle_failure(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理失败情况"""
    if action == "跳转到步骤" and jump_id is not None:
        logger.warning(f"操作失败，跳转到步骤 {jump_id}")
        return False, "跳转到步骤", jump_id
    elif action == "停止工作流":
        logger.warning("操作失败，停止工作流")
        return False, "停止工作流", None
    elif action == "继续执行本步骤":
        logger.warning("操作失败，继续执行本步骤")
        return False, "继续执行本步骤", card_id
    else:  # "执行下一步"
        logger.warning("操作失败，继续执行下一步")
        return False, "执行下一步", None

def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
                target_hwnd: Optional[int], window_region: Optional[tuple], card_id: Optional[int],
                get_image_data=None, **kwargs) -> Tuple[bool, str, Optional[int]]:
    """执行雷电模拟器应用管理任务 - execute_task 接口"""
    return execute(params, counters, execution_mode, target_hwnd, card_id, get_image_data, kwargs.get('stop_checker'))

def execute(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
           target_hwnd: Optional[int], card_id: Optional[int], get_image_data=None, stop_checker=None) -> Tuple[bool, str, Optional[int]]:
    """执行雷电模拟器应用管理任务"""

    # 获取基本参数
    operation_mode = params.get('operation_mode', '启动应用')
    on_success_action = params.get('on_success', '执行下一步')
    success_jump_id = params.get('success_jump_target_id')
    on_failure_action = params.get('on_failure', '执行下一步')
    failure_jump_id = params.get('failure_jump_target_id')

    logger.info(f" 开始执行雷电模拟器应用管理任务")
    logger.info(f" 操作模式: '{operation_mode}' (类型: {type(operation_mode)})")
    logger.info(f" 成功后操作: '{on_success_action}', 跳转目标ID: {success_jump_id}")
    logger.info(f" 失败后操作: '{on_failure_action}', 跳转目标ID: {failure_jump_id}")
    logger.info(f" 所有参数: {params}")

    # 验证操作模式
    valid_modes = ["启动应用", "重启应用", "关闭应用"]
    if operation_mode not in valid_modes:
        logger.error(f" 无效的操作模式: '{operation_mode}', 有效模式: {valid_modes}")
        from .task_utils import handle_failure_action
        return handle_failure_action(params, card_id)

    try:
        # 检查是否有绑定的窗口
        if not target_hwnd:
            logger.error("未提供目标窗口句柄，无法执行雷电模拟器应用管理")
            from .task_utils import handle_failure_action
            return handle_failure_action(params, card_id)

        # 尝试使用新的ADB方法
        try:
            from utils.ldplayer_finder import get_adb_path
            adb_cmd = get_adb_path()

            if adb_cmd:
                logger.info(f"使用ADB方法执行应用管理: {adb_cmd}")
                use_adb_method = True
            else:
                logger.warning("未找到ADB，回退到控制台方法")
                use_adb_method = False
        except Exception as e:
            logger.warning(f"ADB方法初始化失败: {e}，回退到控制台方法")
            use_adb_method = False

        # 获取实例信息
        if use_adb_method:
            # ADB方法：使用先进ADB连接池推断实例索引
            try:
                from utils.advanced_adb_manager import get_advanced_adb_pool, ADBCommand

                pool = get_advanced_adb_pool()
                healthy_devices = pool.get_healthy_devices()
                device_count = len(healthy_devices)

                if device_count == 0:
                    # 回退到传统方法
                    devices_cmd = ADBCommand(['devices'], timeout=5.0)
                    success, stdout, stderr = pool.execute_command_sync(devices_cmd)

                    if success:
                        for line in stdout.split('\n'):
                            if 'emulator-' in line and 'device' in line:
                                device_count += 1

                # 使用全局窗口分配器确保每个窗口分配到不同的实例
                if not hasattr(_get_unique_instance_index, 'hwnd_to_instance'):
                    _get_unique_instance_index.hwnd_to_instance = {}
                    _get_unique_instance_index.used_instances = set()

                # 如果这个HWND已经分配过实例，直接返回
                if target_hwnd in _get_unique_instance_index.hwnd_to_instance:
                    instance_index = _get_unique_instance_index.hwnd_to_instance[target_hwnd]
                    logger.info(f" [HWND:{target_hwnd}] 使用已分配的实例索引={instance_index}")
                else:
                    # 为新的HWND分配未使用的实例索引
                    if device_count > 0:
                        # 找到第一个未使用的实例索引
                        for i in range(device_count):
                            if i not in _get_unique_instance_index.used_instances:
                                instance_index = i
                                _get_unique_instance_index.hwnd_to_instance[target_hwnd] = instance_index
                                _get_unique_instance_index.used_instances.add(instance_index)
                                logger.info(f" [HWND:{target_hwnd}] 分配新的实例索引={instance_index} (共{device_count}个设备)")
                                break
                        else:
                            # 如果所有实例都被使用，重置并从0开始
                            instance_index = 0
                            _get_unique_instance_index.hwnd_to_instance[target_hwnd] = instance_index
                            _get_unique_instance_index.used_instances = {instance_index}
                            logger.warning(f" [HWND:{target_hwnd}] 所有实例已使用，重置并分配实例索引={instance_index}")
                    else:
                        instance_index = 0
                        logger.warning(f" [HWND:{target_hwnd}] 没有发现ADB设备，使用默认实例索引=0")

                logger.info(f" [HWND:{target_hwnd}] 最终实例索引={instance_index} (共{device_count}个设备)")
                logger.info(f" 当前分配状态: {dict(_get_unique_instance_index.hwnd_to_instance)}")

                # 尝试获取窗口标题作为参考信息
                try:
                    import win32gui
                    window_title = win32gui.GetWindowText(target_hwnd)
                    logger.info(f" [HWND:{target_hwnd}] 窗口标题: '{window_title}'")
                except:
                    logger.info(f" [HWND:{target_hwnd}] 无法获取窗口标题")

            except Exception as e:
                logger.warning(f"无法从窗口信息推断实例索引: {e}，使用默认值0")
                instance_index = 0
        else:
            # 传统方法：需要获取雷电模拟器实例信息
            instance = get_ldplayer_instance_by_hwnd(target_hwnd)
            if not instance:
                logger.error(f"无法找到窗口句柄 {target_hwnd} 对应的雷电模拟器实例")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            instance_index = instance['index']
            logger.info(f"传统方法：找到雷电模拟器实例: 索引={instance_index}, 标题={instance['title']}")

        if operation_mode == "启动应用":
            # 启动指定应用
            selected_app = params.get('selected_app', '')
            logger.info(f"获取到的selected_app参数: '{selected_app}'")
            logger.info(f"所有参数: {params}")

            if not selected_app or selected_app == "请先刷新应用列表":
                logger.error(f"未选择要启动的应用，当前值: '{selected_app}'")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            # 从显示名称中提取包名
            package_name = _extract_package_name(selected_app)
            if not package_name:
                logger.error(f"无法从选择的应用中提取包名: {selected_app}")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"准备启动应用: {selected_app} (包名: {package_name})")

            # 使用ADB方法启动应用
            if use_adb_method:
                success = _launch_app_with_adb(adb_cmd, package_name, instance_index)
            else:
                # 使用传统方法启动应用
                success = launch_app(instance_index, package_name)

            if success:
                logger.info(f"成功启动应用: {selected_app}")
                # 使用统一的成功处理（包含延迟）
                from .task_utils import handle_success_action
                return handle_success_action(params, card_id, stop_checker)
            else:
                logger.error(f"启动应用失败: {selected_app}")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

        elif operation_mode == "重启应用":
            # 重启指定应用
            selected_app = params.get('selected_app', '')
            logger.info(f"准备重启应用: '{selected_app}'")

            if not selected_app or selected_app == "请先刷新应用列表":
                logger.error(f"未选择要重启的应用，当前值: '{selected_app}'")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            # 从显示名称中提取包名
            package_name = _extract_package_name(selected_app)
            if not package_name:
                logger.error(f"无法从选择的应用中提取包名: {selected_app}")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"准备重启应用: {selected_app} (包名: {package_name})")

            # 使用ADB方法重启应用
            if use_adb_method:
                success = _restart_app_with_adb(adb_cmd, package_name, instance_index)
            else:
                # 传统方法：先关闭再启动
                logger.info("使用传统方法重启应用：先关闭再启动")
                close_success = close_app(instance_index, package_name)
                if close_success:
                    time.sleep(1)  # 等待应用完全关闭
                    success = launch_app(instance_index, package_name)
                else:
                    success = False

            if success:
                logger.info(f"成功重启应用: {selected_app}")
                # 使用统一的成功处理（包含延迟）
                from .task_utils import handle_success_action
                return handle_success_action(params, card_id, stop_checker)
            else:
                logger.error(f"重启应用失败: {selected_app}")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

        elif operation_mode == "关闭应用":
            # 关闭指定应用
            selected_app = params.get('selected_app', '')
            logger.info(f" 准备关闭应用: '{selected_app}'")

            if not selected_app or selected_app == "请先刷新应用列表":
                logger.error(f" 未选择要关闭的应用，当前值: '{selected_app}'")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            # 从显示名称中提取包名
            package_name = _extract_package_name(selected_app)
            if not package_name:
                logger.error(f" 无法从选择的应用中提取包名: {selected_app}")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f" 准备关闭应用: {selected_app} (包名: {package_name})")
            logger.info(f" 使用方法: {'ADB' if use_adb_method else '传统控制台'}")

            # 使用ADB方法关闭应用
            if use_adb_method:
                logger.info(f" 使用ADB方法关闭应用，实例索引: {instance_index}")
                success = _close_app_with_adb(adb_cmd, package_name, instance_index)
            else:
                # 使用传统方法关闭应用
                logger.info(f" 使用传统方法关闭应用，实例索引: {instance_index}")
                success = close_app(instance_index, package_name)

            # 如果第一次尝试失败，再试一次更强力的方法
            if not success:
                logger.warning(f" 第一次关闭失败，尝试更强力的方法")
                if use_adb_method:
                    # 尝试直接发送HOME键，然后强制关闭
                    success = _force_close_app_with_adb(adb_cmd, package_name, instance_index)
                else:
                    # 尝试使用ADB作为备用方法
                    try:
                        from utils.ldplayer_finder import get_adb_path
                        backup_adb = get_adb_path()
                        if backup_adb:
                            logger.info(f" 使用备用ADB方法关闭应用")
                            success = _close_app_with_adb(backup_adb, package_name, instance_index)
                    except Exception as e:
                        logger.warning(f"备用ADB方法失败: {e}")

            if success:
                logger.info(f" 成功关闭应用: {selected_app}")
                # 使用统一的成功处理（包含延迟）
                from .task_utils import handle_success_action
                return handle_success_action(params, card_id, stop_checker)
            else:
                logger.error(f" 关闭应用失败: {selected_app}")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

        else:
            logger.error(f" 未知的操作模式: '{operation_mode}' (类型: {type(operation_mode)})")
            logger.error(f" 有效的操作模式: ['启动应用', '重启应用', '关闭应用']")
            logger.error(f" 当前参数: {params}")
            from .task_utils import handle_failure_action
            return handle_failure_action(params, card_id)

    except Exception as e:
        logger.error(f"执行雷电模拟器应用管理任务时发生异常: {e}", exc_info=True)
        from .task_utils import handle_failure_action
        return handle_failure_action(params, card_id)

def _extract_package_name(display_name):
    """从显示名称中提取包名"""
    try:
        # 如果是旧格式 "AppName (com.package.name)"，提取括号中的包名
        if '(' in display_name and ')' in display_name:
            import re
            match = re.search(r'\(([^)]+)\)$', display_name)
            if match:
                package_name = match.group(1)
                logger.info(f"从旧格式提取包名: '{display_name}' -> '{package_name}'")
                return package_name

        # 如果是纯包名格式，直接返回
        if display_name.startswith('com.') or display_name.startswith('org.') or display_name.startswith('cn.'):
            return display_name

        # 其他情况，直接返回
        return display_name

    except Exception as e:
        logger.error(f"提取包名时出错: {e}")
        return None

# 提供给UI使用的函数
def refresh_app_list(target_hwnd: Optional[int]) -> List[Dict[str, str]]:
    """刷新应用列表，供UI调用"""
    try:
        if not target_hwnd:
            logger.warning("未提供目标窗口句柄")
            return []

        # 根据窗口句柄获取雷电模拟器实例信息
        instance = get_ldplayer_instance_by_hwnd(target_hwnd)
        if not instance:
            logger.warning(f"无法找到窗口句柄 {target_hwnd} 对应的雷电模拟器实例")
            return []

        logger.info(f"找到雷电模拟器实例: 索引={instance['index']}, 标题={instance['title']}")

        # 确保ADB连接正常
        if not ensure_ldplayer_adb_connection(int(instance['index'])):
            logger.warning(f"无法建立雷电模拟器实例 {instance['index']} 的ADB连接")
            # 即使ADB连接失败，也尝试获取应用列表（可能使用控制台方法）

        # 获取应用列表
        apps = get_installed_apps(instance['index'])
        logger.info(f"刷新应用列表完成，获取到 {len(apps)} 个应用")
        return apps

    except Exception as e:
        logger.error(f"刷新应用列表时出错: {e}")
        import traceback
        traceback.print_exc()
        return []


def _get_adb_device_for_instance(adb_cmd, instance_index):
    """获取指定实例对应的ADB设备ID - 使用先进ADB连接池"""
    try:
        from utils.advanced_adb_manager import get_advanced_adb_pool, ADBCommand

        pool = get_advanced_adb_pool()
        healthy_devices = pool.get_healthy_devices()

        # 优先使用先进ADB连接池的健康设备
        if healthy_devices:
            # 根据实例索引选择设备
            if instance_index < len(healthy_devices):
                device = healthy_devices[instance_index]
                logger.info(f"✅ 从连接池为实例 {instance_index} 选择设备: {device.device_id}")
                return device.device_id
            else:
                # 如果索引超出范围，使用第一个设备
                device = healthy_devices[0]
                logger.info(f"⚠️ 实例索引超出范围，使用第一个设备: {device.device_id}")
                return device.device_id

        # 回退到传统方法
        logger.info("🔄 连接池无设备，回退到传统ADB命令")

        devices_cmd = ADBCommand(['devices'], timeout=5.0)
        success, stdout, stderr = pool.execute_command_sync(devices_cmd)

        if not success:
            logger.error(f"获取ADB设备列表失败: {stderr}")
            return None

        # 解析设备列表
        devices = []
        for line in result.stdout.split('\n'):
            if 'emulator-' in line and 'device' in line:
                device_id = line.split()[0]
                devices.append(device_id)

        logger.info(f"发现 {len(devices)} 个ADB设备: {devices}")

        # 根据实例索引选择设备
        if len(devices) == 0:
            logger.error("没有发现任何ADB设备")
            return None
        elif len(devices) == 1:
            logger.info(f"只有一个设备，所有实例都使用: {devices[0]}")
            return devices[0]
        else:
            # 多设备情况：使用实例索引对设备数量取模，确保每个实例都有对应设备
            device_index = instance_index % len(devices)
            selected_device = devices[device_index]
            logger.info(f"为实例 {instance_index} 选择设备 {device_index}: {selected_device} (共{len(devices)}个设备)")
            return selected_device

    except Exception as e:
        logger.error(f"获取ADB设备失败: {e}")
        return None

def _restart_app_with_adb(adb_cmd, package_name, instance_index):
    """使用ADB重启应用"""
    try:
        import subprocess

        logger.info(f" [实例{instance_index}] 使用ADB重启应用: {package_name}")

        # 动态获取设备ID
        device_id = _get_adb_device_for_instance(adb_cmd, instance_index)
        if not device_id:
            logger.error(f" [实例{instance_index}] 无法获取有效的ADB设备ID")
            return False

        base_cmd = [adb_cmd, '-s', device_id]
        logger.info(f" [实例{instance_index}] 使用ADB设备: {device_id}")

        # 先关闭应用
        logger.info(f" [实例{instance_index}] 先关闭应用: {package_name}")
        close_result = subprocess.run(base_cmd + ['shell', 'am', 'force-stop', package_name],
                                    capture_output=True, text=True, timeout=10,
                                    creationflags=subprocess.CREATE_NO_WINDOW)

        if close_result.returncode == 0:
            logger.info(f" [实例{instance_index}] 应用关闭成功")
        else:
            logger.warning(f" [实例{instance_index}] 应用关闭失败，但继续启动: {close_result.stderr}")

        # 等待一秒
        time.sleep(1)

        # 再启动应用
        logger.info(f" [实例{instance_index}] 重新启动应用: {package_name}")
        launch_result = subprocess.run(base_cmd + ['shell', 'monkey', '-p', package_name, '-c', 'android.intent.category.LAUNCHER', '1'],
                                     capture_output=True, text=True, timeout=10,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

        if launch_result.returncode == 0:
            logger.info(f" [实例{instance_index}] ADB重启应用成功: {package_name}")
            logger.info(f" [实例{instance_index}] 启动输出: {launch_result.stdout.strip()}")
            return True
        else:
            logger.error(f" [实例{instance_index}] ADB重启应用失败: {launch_result.stderr}")
            return False

    except Exception as e:
        logger.error(f" [实例{instance_index}] ADB重启应用异常: {e}")
        return False

def _close_app_with_adb(adb_cmd, package_name, instance_index):
    """使用ADB关闭应用"""
    try:
        import subprocess

        logger.info(f" [实例{instance_index}] 使用ADB关闭应用: {package_name}")

        # 动态获取设备ID
        device_id = _get_adb_device_for_instance(adb_cmd, instance_index)
        if not device_id:
            logger.error(f" [实例{instance_index}] 无法获取有效的ADB设备ID")
            return False

        base_cmd = [adb_cmd, '-s', device_id]
        logger.info(f" [实例{instance_index}] 使用ADB设备: {device_id}")

        # 验证设备连接
        test_result = subprocess.run(base_cmd + ['shell', 'echo', 'test'],
                                   capture_output=True, text=True, timeout=5,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if test_result.returncode != 0:
            logger.error(f" [实例{instance_index}] 设备 {device_id} 连接测试失败: {test_result.stderr}")
            return False
        else:
            logger.info(f" [实例{instance_index}] 设备 {device_id} 连接正常")

        # 方法1：使用force-stop强制关闭应用
        logger.info(f" [实例{instance_index}] 方法1: 使用 force-stop 关闭应用")
        close_cmd = base_cmd + ['shell', 'am', 'force-stop', package_name]
        logger.info(f" [实例{instance_index}] 执行关闭命令: {' '.join(close_cmd)}")

        result = subprocess.run(close_cmd, capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0:
            logger.info(f" [实例{instance_index}] force-stop 执行成功")

            # 简化验证：force-stop 成功就认为关闭成功
            # Android的force-stop命令通常是可靠的
            logger.info(f" [实例{instance_index}] ADB关闭应用成功: {package_name}")
            return True
        else:
            logger.warning(f" [实例{instance_index}] force-stop 失败: {result.stderr}")

        # 方法2：使用 kill 命令杀死进程
        logger.info(f" [实例{instance_index}] 方法2: 使用 kill 命令杀死进程")
        ps_cmd = base_cmd + ['shell', 'ps']
        ps_result = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=5)

        if ps_result.returncode == 0 and ps_result.stdout:
            lines = ps_result.stdout.strip().split('\n')
            killed_any = False
            for line in lines:
                if package_name in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        pid = parts[1]  # 第二列通常是PID
                        logger.info(f" [实例{instance_index}] 找到进程PID: {pid}")

                        kill_cmd = base_cmd + ['shell', 'kill', '-9', pid]  # 使用 -9 强制杀死
                        kill_result = subprocess.run(kill_cmd, capture_output=True, text=True, timeout=5)

                        if kill_result.returncode == 0:
                            logger.info(f" [实例{instance_index}] 成功杀死进程: PID {pid}")
                            killed_any = True
                        else:
                            logger.warning(f" [实例{instance_index}] 杀死进程失败: {kill_result.stderr}")

            if killed_any:
                return True

        # 方法3：使用 pkill 命令
        logger.info(f" [实例{instance_index}] 方法3: 使用 pkill 命令")
        pkill_cmd = base_cmd + ['shell', 'pkill', '-f', package_name]
        pkill_result = subprocess.run(pkill_cmd, capture_output=True, text=True, timeout=5)

        if pkill_result.returncode == 0:
            logger.info(f" [实例{instance_index}] pkill 成功")
            return True
        else:
            logger.warning(f" [实例{instance_index}] pkill 失败: {pkill_result.stderr}")

        logger.error(f" [实例{instance_index}] 所有关闭方法都失败了")
        return False

    except Exception as e:
        logger.error(f" [实例{instance_index}] ADB关闭应用异常: {e}")
        return False

def _force_close_app_with_adb(adb_cmd, package_name, instance_index):
    """使用更强力的ADB方法关闭应用"""
    try:
        import subprocess

        logger.info(f" [实例{instance_index}] 使用强力方法关闭应用: {package_name}")

        # 动态获取设备ID
        device_id = _get_adb_device_for_instance(adb_cmd, instance_index)
        if not device_id:
            logger.error(f" [实例{instance_index}] 无法获取有效的ADB设备ID")
            return False

        base_cmd = [adb_cmd, '-s', device_id]
        logger.info(f" [实例{instance_index}] 使用ADB设备: {device_id}")

        # 方法1：先按HOME键回到桌面
        logger.info(f" [实例{instance_index}] 先按HOME键回到桌面")
        home_cmd = base_cmd + ['shell', 'input', 'keyevent', 'KEYCODE_HOME']
        home_result = subprocess.run(home_cmd, capture_output=True, text=True, timeout=5)

        if home_result.returncode == 0:
            logger.info(f" [实例{instance_index}] HOME键按下成功")
        else:
            logger.warning(f" [实例{instance_index}] HOME键按下失败: {home_result.stderr}")

        time.sleep(1)  # 等待回到桌面

        # 方法2：强制停止应用
        logger.info(f" [实例{instance_index}] 强制停止应用")
        force_stop_cmd = base_cmd + ['shell', 'am', 'force-stop', package_name]
        force_result = subprocess.run(force_stop_cmd, capture_output=True, text=True, timeout=10)

        # 方法3：清除应用数据（这会强制关闭应用）
        logger.info(f" [实例{instance_index}] 尝试清除应用任务")
        clear_cmd = base_cmd + ['shell', 'am', 'kill', package_name]
        clear_result = subprocess.run(clear_cmd, capture_output=True, text=True, timeout=10)

        # 方法4：使用killall命令
        logger.info(f"⚔ [实例{instance_index}] 使用killall命令")
        killall_cmd = base_cmd + ['shell', 'killall', package_name]
        killall_result = subprocess.run(killall_cmd, capture_output=True, text=True, timeout=5)

        # 验证是否关闭成功
        time.sleep(1)
        check_cmd = base_cmd + ['shell', 'ps']
        check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)

        if check_result.returncode == 0:
            if package_name not in check_result.stdout:
                logger.info(f" [实例{instance_index}] 强力关闭成功：应用已关闭")
                return True
            else:
                logger.warning(f" [实例{instance_index}] 强力关闭后应用仍在运行")
                return False
        else:
            logger.warning(f" [实例{instance_index}] 无法验证应用状态，假设关闭成功")
            return True

    except Exception as e:
        logger.error(f" [实例{instance_index}] 强力关闭应用异常: {e}")
        return False

def _launch_app_with_adb(adb_cmd, package_name, instance_index):
    """使用ADB启动应用"""
    try:
        import subprocess

        logger.info(f" [实例{instance_index}] 使用ADB启动应用: {package_name}")

        # 动态获取设备ID
        device_id = _get_adb_device_for_instance(adb_cmd, instance_index)
        if not device_id:
            logger.error(f" [实例{instance_index}] 无法获取有效的ADB设备ID")
            return False

        base_cmd = [adb_cmd, '-s', device_id]
        logger.info(f" [实例{instance_index}] 使用ADB设备: {device_id}")

        # 验证设备连接
        test_result = subprocess.run(base_cmd + ['shell', 'echo', 'test'],
                                   capture_output=True, text=True, timeout=5,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if test_result.returncode != 0:
            logger.error(f" [实例{instance_index}] 设备 {device_id} 连接测试失败: {test_result.stderr}")
            return False
        else:
            logger.info(f" [实例{instance_index}] 设备 {device_id} 连接正常")

        # 使用ADB启动应用
        launch_cmd = base_cmd + ['shell', 'monkey', '-p', package_name, '-c', 'android.intent.category.LAUNCHER', '1']
        logger.info(f" [实例{instance_index}] 执行启动命令: {' '.join(launch_cmd)}")

        result = subprocess.run(launch_cmd, capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0:
            logger.info(f" [实例{instance_index}] ADB启动应用成功: {package_name}")
            logger.info(f" [实例{instance_index}] 启动输出: {result.stdout.strip()}")
            return True
        else:
            logger.error(f" [实例{instance_index}] ADB启动应用失败: {result.stderr}")
            logger.error(f" [实例{instance_index}] 错误输出: {result.stdout.strip()}")

            # 尝试备用方法：使用am start
            logger.info("尝试备用方法启动应用...")
            result2 = subprocess.run(base_cmd + ['shell', 'am', 'start', '-n', f"{package_name}/.MainActivity"],
                                   capture_output=True, text=True, timeout=10,
                                   creationflags=subprocess.CREATE_NO_WINDOW)

            if result2.returncode == 0:
                logger.info(f"备用方法启动应用成功: {package_name}")
                return True
            else:
                # 尝试第三种方法：获取主Activity并启动
                logger.info("尝试获取主Activity并启动...")
                activity_result = subprocess.run(base_cmd + ['shell', 'pm', 'dump', package_name],
                                               capture_output=True, text=True, timeout=5)

                if activity_result.returncode == 0:
                    # 从dump信息中查找主Activity
                    for line in activity_result.stdout.split('\n'):
                        if 'android.intent.action.MAIN' in line and 'android.intent.category.LAUNCHER' in line:
                            # 查找Activity名称
                            import re
                            activity_match = re.search(r'(\S+)/(\S+)', line)
                            if activity_match:
                                activity_name = f"{package_name}/{activity_match.group(2)}"
                                logger.info(f"找到主Activity: {activity_name}")

                                result3 = subprocess.run(base_cmd + ['shell', 'am', 'start', '-n', activity_name],
                                                       capture_output=True, text=True, timeout=10)

                                if result3.returncode == 0:
                                    logger.info(f"通过主Activity启动应用成功: {package_name}")
                                    return True
                                break

                logger.error(f"所有方法都无法启动应用: {package_name}")
                return False

    except subprocess.TimeoutExpired:
        logger.error(f"ADB启动应用超时: {package_name}")
        return False
    except Exception as e:
        logger.error(f"ADB启动应用异常: {e}")
        return False
