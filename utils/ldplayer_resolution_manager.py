"""
雷电模拟器分辨率和DPI管理器
支持通过ldconsole命令修改雷电模拟器的分辨率和DPI设置
"""

import logging
import subprocess
import os
import time
import threading
from typing import Optional, Tuple, Dict, Any, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, Future

try:
    import psutil
except ImportError:
    psutil = None
    logging.warning("psutil未安装，将跳过进程查找方法")

logger = logging.getLogger(__name__)

@dataclass
class LDPlayerResolutionResult:
    """雷电模拟器分辨率调整结果"""
    success: bool
    message: str
    instance_index: int
    target_resolution: Tuple[int, int]
    target_dpi: int
    before_resolution: Tuple[int, int] = (0, 0)
    after_resolution: Tuple[int, int] = (0, 0)
    restart_required: bool = True

class LDPlayerResolutionManager:
    """雷电模拟器分辨率和DPI管理器"""

    def __init__(self):
        self.console_path = self._find_console_path()
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="LDPlayer")
        self._lock = threading.RLock()
        logger.info(f"雷电模拟器分辨率管理器初始化，控制台路径: {self.console_path}")
    
    def _find_console_path(self) -> Optional[str]:
        """查找雷电模拟器控制台程序路径"""
        import winreg
        import psutil

        console_paths = []

        # 1. 通过进程查找（最准确的方法）
        if psutil:
            try:
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        proc_info = proc.info
                        if proc_info['name'] and proc_info['exe']:
                            # 查找雷电模拟器相关进程
                            if any(keyword in proc_info['name'].lower() for keyword in ['ldplayer', 'dnplayer', 'ld']):
                                exe_path = proc_info['exe']
                                if exe_path:
                                    # 从进程路径推断控制台程序路径
                                    install_dir = os.path.dirname(exe_path)
                                    console_path = os.path.join(install_dir, "ldconsole.exe")
                                    if os.path.exists(console_path) and console_path not in console_paths:
                                        console_paths.append(console_path)
                                        logger.info(f"通过进程查找到雷电控制台: {console_path}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            except Exception as e:
                logger.debug(f"通过进程查找雷电控制台失败: {e}")
        else:
            logger.debug("psutil不可用，跳过进程查找方法")

        # 2. 常见安装路径
        common_paths = [
            r"C:\LDPlayer\LDPlayer9\ldconsole.exe",
            r"C:\LDPlayer\LDPlayer4\ldconsole.exe",
            r"D:\LDPlayer\LDPlayer9\ldconsole.exe",
            r"D:\LDPlayer\LDPlayer4\ldconsole.exe",
            r"E:\LDPlayer\LDPlayer9\ldconsole.exe",
            r"E:\leidian\LDPlayer9\ldconsole.exe",  # 添加用户的路径
            r"F:\LDPlayer\LDPlayer9\ldconsole.exe",
            r"G:\LDPlayer\LDPlayer9\ldconsole.exe"
        ]

        for path in common_paths:
            if os.path.exists(path) and path not in console_paths:
                console_paths.append(path)

        # 3. 从注册表查找
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                if "雷电" in display_name or "LDPlayer" in display_name:
                                    install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                    console_path = os.path.join(install_location, "ldconsole.exe")
                                    if os.path.exists(console_path) and console_path not in console_paths:
                                        console_paths.append(console_path)
                            except FileNotFoundError:
                                pass
                        i += 1
                    except OSError:
                        break
        except Exception as e:
            logger.debug(f"从注册表查找雷电控制台失败: {e}")

        # 4. 搜索所有驱动器的常见目录
        try:
            import string
            drives = ['%s:' % d for d in string.ascii_uppercase if os.path.exists('%s:' % d)]

            for drive in drives:
                search_paths = [
                    os.path.join(drive, "LDPlayer", "LDPlayer9", "ldconsole.exe"),
                    os.path.join(drive, "leidian", "LDPlayer9", "ldconsole.exe"),
                    os.path.join(drive, "Program Files", "LDPlayer", "LDPlayer9", "ldconsole.exe"),
                    os.path.join(drive, "Program Files (x86)", "LDPlayer", "LDPlayer9", "ldconsole.exe")
                ]

                for path in search_paths:
                    if os.path.exists(path) and path not in console_paths:
                        console_paths.append(path)
        except Exception as e:
            logger.debug(f"搜索驱动器查找雷电控制台失败: {e}")

        if console_paths:
            logger.info(f"找到雷电控制台程序: {console_paths[0]}")
            return console_paths[0]
        else:
            logger.error("未找到雷电模拟器控制台程序")
            return None
    
    def get_instance_list(self) -> list:
        """获取雷电模拟器实例列表"""
        if not self.console_path:
            logger.error("未找到雷电模拟器控制台程序")
            return []
        
        try:
            # 尝试多种编码方式，雷电模拟器通常使用GBK编码
            encodings = ['gbk', 'gb2312', 'cp936', 'utf-8']
            result = None
            successful_encoding = None

            for encoding in encodings:
                try:
                    logger.debug(f"尝试使用编码 {encoding} 执行 ldconsole list2")
                    result = subprocess.run([self.console_path, "list2"],
                                          capture_output=True, text=True, encoding=encoding,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode == 0 and result.stdout:
                        successful_encoding = encoding
                        logger.debug(f"使用编码 {encoding} 成功获取输出")
                        break
                    else:
                        logger.debug(f"编码 {encoding}: 返回码={result.returncode}, 输出为空={not result.stdout}")
                except UnicodeDecodeError as e:
                    logger.debug(f"编码 {encoding} 解码失败: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"使用编码 {encoding} 执行命令失败: {e}")
                    continue

            if result and result.returncode == 0 and result.stdout:
                instances = []
                output_lines = result.stdout.strip().split('\n')
                logger.debug(f"雷电模拟器list2输出 ({successful_encoding}): {output_lines}")

                for line in output_lines:
                    if line.strip():
                        parts = line.split(',')
                        logger.debug(f"解析行: {line} -> {parts}")
                        if len(parts) >= 4:
                            try:
                                instances.append({
                                    'index': int(parts[0]),
                                    'title': parts[1],
                                    'top_hwnd': int(parts[2]) if parts[2].isdigit() else 0,
                                    'bind_hwnd': int(parts[3]) if parts[3].isdigit() else 0,
                                    'android_started': parts[4] if len(parts) > 4 else '0',
                                    'pid': parts[5] if len(parts) > 5 else '0'
                                })
                            except ValueError as e:
                                logger.warning(f"解析雷电模拟器实例行失败: {line}, 错误: {e}")
                                continue

                logger.info(f"成功获取 {len(instances)} 个雷电模拟器实例")
                return instances
            else:
                logger.warning("雷电模拟器list2命令返回空结果或执行失败")
                if result:
                    logger.debug(f"命令返回码: {result.returncode}")
                    logger.debug(f"stderr: {result.stderr}")
        except Exception as e:
            logger.error(f"获取雷电模拟器实例列表失败: {e}")

        return []
    
    def get_instance_by_hwnd(self, hwnd: int) -> Optional[Dict[str, Any]]:
        """根据窗口句柄获取实例信息"""
        instances = self.get_instance_list()
        for instance in instances:
            if instance['bind_hwnd'] == hwnd or instance['top_hwnd'] == hwnd:
                return instance
        return None
    
    def modify_resolution_and_dpi(self, instance_index: int, width: int, height: int, 
                                 dpi: int = 180) -> LDPlayerResolutionResult:
        """修改雷电模拟器实例的分辨率和DPI"""
        if not self.console_path:
            return LDPlayerResolutionResult(
                success=False,
                message="未找到雷电模拟器控制台程序",
                instance_index=instance_index,
                target_resolution=(width, height),
                target_dpi=dpi
            )
        
        try:
            logger.info(f"开始修改雷电模拟器实例 {instance_index} 的分辨率和DPI")
            logger.info(f"目标分辨率: {width}x{height}, DPI: {dpi}")
            
            # 构建modify命令
            # ldconsole modify --index <index> --resolution <width>,<height>,<dpi>
            cmd = [
                self.console_path, "modify",
                "--index", str(instance_index),
                "--resolution", f"{width},{height},{dpi}"
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  encoding='utf-8', timeout=30)
            
            if result.returncode == 0:
                logger.info(f"雷电模拟器实例 {instance_index} 分辨率修改成功")
                return LDPlayerResolutionResult(
                    success=True,
                    message="分辨率和DPI修改成功，需要重启模拟器生效",
                    instance_index=instance_index,
                    target_resolution=(width, height),
                    target_dpi=dpi,
                    restart_required=True
                )
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                logger.error(f"雷电模拟器实例 {instance_index} 分辨率修改失败: {error_msg}")
                return LDPlayerResolutionResult(
                    success=False,
                    message=f"修改失败: {error_msg}",
                    instance_index=instance_index,
                    target_resolution=(width, height),
                    target_dpi=dpi
                )
                
        except subprocess.TimeoutExpired:
            logger.error(f"雷电模拟器实例 {instance_index} 分辨率修改超时")
            return LDPlayerResolutionResult(
                success=False,
                message="修改超时",
                instance_index=instance_index,
                target_resolution=(width, height),
                target_dpi=dpi
            )
        except Exception as e:
            logger.error(f"雷电模拟器实例 {instance_index} 分辨率修改异常: {e}")
            return LDPlayerResolutionResult(
                success=False,
                message=f"修改异常: {str(e)}",
                instance_index=instance_index,
                target_resolution=(width, height),
                target_dpi=dpi
            )
    
    def restart_instance(self, instance_index: int) -> bool:
        """重启雷电模拟器实例"""
        if not self.console_path:
            logger.error("未找到雷电模拟器控制台程序")
            return False
        
        try:
            logger.info(f"重启雷电模拟器实例 {instance_index}")
            
            # 先关闭实例
            quit_cmd = [self.console_path, "quit", "--index", str(instance_index)]
            result = subprocess.run(quit_cmd, capture_output=True, text=True, 
                                  encoding='utf-8', timeout=30)
            
            if result.returncode == 0:
                logger.info(f"实例 {instance_index} 关闭成功，等待3秒")
                time.sleep(3)
                
                # 启动实例
                launch_cmd = [self.console_path, "launch", "--index", str(instance_index)]
                result = subprocess.run(launch_cmd, capture_output=True, text=True, 
                                      encoding='utf-8', timeout=60)
                
                if result.returncode == 0:
                    logger.info(f"实例 {instance_index} 启动成功")
                    return True
                else:
                    logger.error(f"实例 {instance_index} 启动失败: {result.stderr}")
                    return False
            else:
                logger.error(f"实例 {instance_index} 关闭失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"重启实例 {instance_index} 异常: {e}")
            return False

    def modify_resolution_and_dpi_async(self, instance_index: int, width: int, height: int,
                                       dpi: int = 240, callback: Optional[Callable] = None) -> Future:
        """异步修改雷电模拟器实例的分辨率和DPI"""
        def _async_modify():
            try:
                result = self.modify_resolution_and_dpi(instance_index, width, height, dpi)
                if callback:
                    callback(result)
                return result
            except Exception as e:
                logger.error(f"异步修改分辨率失败: {e}")
                error_result = LDPlayerResolutionResult(
                    success=False,
                    message=f"异步修改失败: {str(e)}",
                    instance_index=instance_index,
                    target_resolution=(width, height),
                    target_dpi=dpi
                )
                if callback:
                    callback(error_result)
                return error_result

        return self._executor.submit(_async_modify)

    def restart_instance_async(self, instance_index: int, callback: Optional[Callable] = None) -> Future:
        """异步重启雷电模拟器实例"""
        def _async_restart():
            try:
                result = self.restart_instance(instance_index)
                if callback:
                    callback(result)
                return result
            except Exception as e:
                logger.error(f"异步重启失败: {e}")
                if callback:
                    callback(False)
                return False

        return self._executor.submit(_async_restart)

    def get_instance_list_async(self, callback: Optional[Callable] = None) -> Future:
        """异步获取雷电模拟器实例列表"""
        def _async_get_list():
            try:
                result = self.get_instance_list()
                if callback:
                    callback(result)
                return result
            except Exception as e:
                logger.error(f"异步获取实例列表失败: {e}")
                if callback:
                    callback([])
                return []

        return self._executor.submit(_async_get_list)

    def shutdown(self):
        """关闭线程池"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)

# 全局实例
_ldplayer_resolution_manager = None

def get_ldplayer_resolution_manager() -> LDPlayerResolutionManager:
    """获取雷电模拟器分辨率管理器实例"""
    global _ldplayer_resolution_manager
    if _ldplayer_resolution_manager is None:
        _ldplayer_resolution_manager = LDPlayerResolutionManager()
    return _ldplayer_resolution_manager
