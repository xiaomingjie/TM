"""
MuMu模拟器路径查找器
用于查找MuMu模拟器的安装路径和ADB路径
"""

import os
import logging
import subprocess
from typing import Optional, List

logger = logging.getLogger(__name__)

class MuMuFinder:
    """MuMu模拟器路径查找器"""
    
    def __init__(self):
        self.install_paths = []
        self.adb_paths = []
        
    def find_all_paths(self):
        """查找所有MuMu相关路径"""
        self.install_paths.clear()
        self.adb_paths.clear()
        
        # 1. 从注册表查找
        self._find_from_registry()
        
        # 2. 从常见安装位置查找
        self._find_from_common_locations()
        
        # 3. 从运行进程查找
        self._find_from_running_processes()
        
        # 4. 查找ADB路径
        self._find_adb_paths()
        
        logger.info(f"MuMu查找完成: 安装路径={len(self.install_paths)}, ADB路径={len(self.adb_paths)}")
        
    def _find_from_registry(self):
        """从注册表查找MuMu安装路径"""
        try:
            import winreg
            
            # 查找卸载信息
            uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall_key) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                if "mumu" in display_name.lower() or "网易" in display_name:
                                    try:
                                        install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                        if install_location and os.path.exists(install_location):
                                            self.install_paths.append(install_location)
                                            logger.info(f"从注册表找到MuMu安装路径: {install_location}")
                                    except FileNotFoundError:
                                        pass
                            except FileNotFoundError:
                                pass
                        i += 1
                    except OSError:
                        break
                        
        except Exception as e:
            logger.debug(f"从注册表查找MuMu路径失败: {e}")
    
    def _find_from_common_locations(self):
        """从常见安装位置查找"""
        common_paths = [
            r"C:\Program Files\Netease\MuMu Player 12",
            r"C:\Program Files (x86)\Netease\MuMu Player 12",
            r"D:\Program Files\Netease\MuMu Player 12",
            r"E:\Program Files\Netease\MuMu Player 12",
            r"C:\MuMuPlayer",
            r"D:\MuMuPlayer",
            r"E:\MuMuPlayer",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                self.install_paths.append(path)
                logger.info(f"从常见位置找到MuMu: {path}")
    
    def _find_from_running_processes(self):
        """从运行进程查找MuMu路径"""
        try:
            import psutil
            
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['name'] and 'mumu' in proc.info['name'].lower():
                        exe_path = proc.info['exe']
                        if exe_path:
                            install_dir = os.path.dirname(exe_path)
                            if install_dir not in self.install_paths:
                                self.install_paths.append(install_dir)
                                logger.info(f"从运行进程找到MuMu: {install_dir}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except ImportError:
            logger.debug("psutil不可用，跳过进程查找")
        except Exception as e:
            logger.debug(f"从进程查找MuMu路径失败: {e}")
    
    def _find_adb_paths(self):
        """查找MuMu的ADB路径"""
        for install_path in self.install_paths:
            # MuMu 12的ADB路径
            possible_adb_paths = [
                os.path.join(install_path, "shell", "adb.exe"),
                os.path.join(install_path, "nx_device", "12.0", "shell", "adb.exe"),
                os.path.join(install_path, "adb.exe"),
            ]
            
            for adb_path in possible_adb_paths:
                if os.path.exists(adb_path):
                    self.adb_paths.append(adb_path)
                    logger.info(f"找到MuMu ADB: {adb_path}")
    
    def get_best_adb_path(self) -> Optional[str]:
        """获取最佳的MuMu ADB路径"""
        for adb_path in self.adb_paths:
            try:
                # 测试ADB是否可用
                # 使用更强力的方法隐藏窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

                creation_flags = (
                    subprocess.CREATE_NO_WINDOW |
                    subprocess.DETACHED_PROCESS |
                    subprocess.CREATE_NEW_PROCESS_GROUP
                )

                result = subprocess.run([adb_path, 'version'],
                                      capture_output=True, text=True, timeout=5,
                                      creationflags=creation_flags, startupinfo=startupinfo)
                if result.returncode == 0:
                    logger.info(f"找到可用的MuMu ADB: {adb_path}")
                    return adb_path
            except Exception as e:
                logger.debug(f"MuMu ADB测试失败 {adb_path}: {e}")
        
        return None

# 全局实例
mumu_finder = MuMuFinder()

def find_mumu_paths():
    """查找MuMu模拟器相关路径的便捷函数"""
    return mumu_finder.find_all_paths()

def get_mumu_adb_path():
    """获取MuMu的ADB路径"""
    if not mumu_finder.adb_paths:
        mumu_finder.find_all_paths()
    return mumu_finder.get_best_adb_path()

def get_mumu_install_paths():
    """获取MuMu安装路径列表"""
    if not mumu_finder.install_paths:
        mumu_finder.find_all_paths()
    return mumu_finder.install_paths
