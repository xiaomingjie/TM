"""
雷电模拟器路径查找工具
自动检测雷电模拟器的安装路径和相关工具
"""

import os
import subprocess
import winreg
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

class LDPlayerFinder:
    """雷电模拟器路径查找器"""
    
    def __init__(self):
        self.install_paths = []
        self.adb_paths = []
        self.console_paths = []
        
    def find_all_paths(self) -> Dict[str, List[str]]:
        """查找所有相关路径"""
        self.install_paths = self._find_install_paths()
        self.adb_paths = self._find_adb_paths()
        self.console_paths = self._find_console_paths()
        
        return {
            'install_paths': self.install_paths,
            'adb_paths': self.adb_paths,
            'console_paths': self.console_paths
        }
    
    def _find_install_paths(self) -> List[str]:
        """查找雷电模拟器安装路径"""
        paths = []
        
        # 方法1: 从注册表查找
        paths.extend(self._find_from_registry())
        
        # 方法2: 从桌面快捷方式查找
        paths.extend(self._find_from_shortcuts())
        
        # 方法3: 从开始菜单查找
        paths.extend(self._find_from_start_menu())
        
        # 方法4: 从环境变量查找
        paths.extend(self._find_from_environment())
        
        # 方法5: 从常见安装路径查找
        paths.extend(self._find_from_common_paths())
        
        # 去重并验证路径
        unique_paths = []
        for path in paths:
            if path and os.path.exists(path) and path not in unique_paths:
                unique_paths.append(path)
                logger.info(f"找到雷电安装目录: {path}")
        
        return unique_paths
    
    def _find_from_registry(self) -> List[str]:
        """从注册表查找安装路径"""
        paths = []
        
        try:
            # 查找卸载信息
            uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            
            # 检查32位和64位注册表
            registry_keys = [
                (winreg.HKEY_LOCAL_MACHINE, uninstall_key),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            
            for hkey, key_path in registry_keys:
                try:
                    with winreg.OpenKey(hkey, key_path) as key:
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as subkey:
                                    try:
                                        display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                        if any(keyword in display_name.lower() for keyword in ["ldplayer", "雷电", "leidian"]):
                                            try:
                                                install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                                if install_location:
                                                    paths.append(install_location.rstrip('\\'))
                                                    logger.info(f"从注册表找到: {display_name} -> {install_location}")
                                            except FileNotFoundError:
                                                # 尝试从UninstallString获取路径
                                                try:
                                                    uninstall_string = winreg.QueryValueEx(subkey, "UninstallString")[0]
                                                    if uninstall_string:
                                                        # 从卸载字符串中提取路径
                                                        install_path = os.path.dirname(uninstall_string.strip('"'))
                                                        paths.append(install_path)
                                                        logger.info(f"从卸载字符串获取路径: {install_path}")
                                                except FileNotFoundError:
                                                    pass
                                    except FileNotFoundError:
                                        pass
                                i += 1
                            except OSError:
                                break
                except Exception as e:
                    logger.debug(f"注册表查找失败 {key_path}: {e}")
                    
        except Exception as e:
            logger.error(f"注册表查找失败: {e}")
        
        return paths
    
    def _find_from_shortcuts(self) -> List[str]:
        """从桌面快捷方式查找"""
        paths = []
        
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            
            # 检查桌面快捷方式
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            public_desktop = r"C:\Users\Public\Desktop"
            
            for desktop in [desktop_path, public_desktop]:
                if os.path.exists(desktop):
                    for file in os.listdir(desktop):
                        if file.lower().endswith('.lnk') and any(keyword in file.lower() for keyword in ["ldplayer", "雷电", "leidian"]):
                            shortcut_path = os.path.join(desktop, file)
                            try:
                                shortcut = shell.CreateShortCut(shortcut_path)
                                target_path = shortcut.Targetpath
                                if target_path and os.path.exists(target_path):
                                    install_path = os.path.dirname(target_path)
                                    paths.append(install_path)
                                    logger.info(f"从桌面快捷方式找到: {file} -> {install_path}")
                            except Exception as e:
                                logger.debug(f"解析快捷方式失败 {file}: {e}")
                                
        except ImportError:
            logger.debug("win32com.client 不可用，跳过快捷方式查找")
        except Exception as e:
            logger.error(f"快捷方式查找失败: {e}")
        
        return paths
    
    def _find_from_start_menu(self) -> List[str]:
        """从开始菜单查找"""
        paths = []
        
        try:
            # 检查开始菜单路径
            start_menu_paths = [
                os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"),
                r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"
            ]
            
            for start_menu in start_menu_paths:
                if os.path.exists(start_menu):
                    for root, dirs, files in os.walk(start_menu):
                        for file in files:
                            if file.lower().endswith('.lnk') and any(keyword in file.lower() for keyword in ["ldplayer", "雷电", "leidian"]):
                                # 这里可以解析快捷方式，类似桌面快捷方式的处理
                                pass
                                
        except Exception as e:
            logger.error(f"开始菜单查找失败: {e}")
        
        return paths
    
    def _find_from_environment(self) -> List[str]:
        """从环境变量查找"""
        paths = []
        
        try:
            # 检查PATH环境变量
            path_env = os.environ.get('PATH', '')
            for path in path_env.split(';'):
                if path and any(keyword in path.lower() for keyword in ["ldplayer", "雷电", "leidian"]):
                    if os.path.exists(path):
                        paths.append(path)
                        logger.info(f"从环境变量找到: {path}")
                        
        except Exception as e:
            logger.error(f"环境变量查找失败: {e}")
        
        return paths
    
    def _find_from_common_paths(self) -> List[str]:
        """从常见安装路径查找"""
        common_paths = [
            r"C:\LDPlayer",
            r"D:\LDPlayer", 
            r"E:\LDPlayer",
            r"F:\LDPlayer",
            r"G:\LDPlayer",
            r"C:\Program Files\LDPlayer",
            r"C:\Program Files (x86)\LDPlayer",
            r"D:\Program Files\LDPlayer",
            r"C:\ChangZhi",  # 雷电旧版本
            r"D:\ChangZhi",
        ]
        
        paths = []
        for path in common_paths:
            if os.path.exists(path):
                paths.append(path)
                logger.info(f"从常见路径找到: {path}")
        
        return paths
    
    def _find_adb_paths(self) -> List[str]:
        """智能查找ADB路径"""
        from utils.smart_adb_finder import SmartADBFinder

        # 使用智能ADB查找器
        smart_finder = SmartADBFinder()
        adb_paths = smart_finder.find_all_adb_paths()

        # 记录找到的ADB路径
        for path in adb_paths:
            logger.info(f"找到ADB: {path}")

        return adb_paths
    
    def _find_console_paths(self) -> List[str]:
        """查找控制台程序路径"""
        console_paths = []
        
        for install_path in self.install_paths:
            # 在每个安装目录下查找控制台程序
            possible_paths = [
                os.path.join(install_path, "ldconsole.exe"),
                os.path.join(install_path, "LDPlayer9", "ldconsole.exe"),
                os.path.join(install_path, "LDPlayer4", "ldconsole.exe"),
                os.path.join(install_path, "LDPlayer", "ldconsole.exe"),
                os.path.join(install_path, "dnplayer2", "dnconsole.exe"),  # 旧版本
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    console_paths.append(path)
                    logger.info(f"找到控制台程序: {path}")
        
        return console_paths
    
    def get_best_adb_path(self) -> Optional[str]:
        """获取最佳的ADB路径（优先使用雷电模拟器的ADB）"""

        # 优先使用雷电模拟器的ADB
        ldplayer_adb_paths = [path for path in self.adb_paths if 'leidian' in path.lower() or 'ldplayer' in path.lower()]
        other_adb_paths = [path for path in self.adb_paths if path not in ldplayer_adb_paths]

        # 按优先级排序：雷电ADB > 其他ADB
        prioritized_paths = ldplayer_adb_paths + other_adb_paths

        logger.info(f"ADB路径优先级: 雷电={ldplayer_adb_paths}, 其他={other_adb_paths}")

        for adb_path in prioritized_paths:
            try:
                # 测试ADB是否可用
                result = subprocess.run([adb_path, 'version'],
                                      capture_output=True, text=True, timeout=5,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    logger.info(f"找到可用的ADB: {adb_path}")
                    return adb_path
            except Exception as e:
                logger.debug(f"ADB测试失败 {adb_path}: {e}")

        return None
    
    def get_best_console_path(self) -> Optional[str]:
        """获取最佳的控制台程序路径"""
        
        for console_path in self.console_paths:
            try:
                # 测试控制台程序是否可用
                result = subprocess.run([console_path, 'list2'],
                                      capture_output=True, text=True, timeout=5,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    logger.info(f"找到可用的控制台程序: {console_path}")
                    return console_path
            except Exception as e:
                logger.debug(f"控制台程序测试失败 {console_path}: {e}")
        
        return None


# 全局实例
ldplayer_finder = LDPlayerFinder()

def find_ldplayer_paths():
    """查找雷电模拟器相关路径的便捷函数"""
    return ldplayer_finder.find_all_paths()

def get_adb_path():
    """获取可用的ADB路径"""
    if not ldplayer_finder.adb_paths:
        ldplayer_finder.find_all_paths()
    return ldplayer_finder.get_best_adb_path()

def get_console_path():
    """获取可用的控制台程序路径"""
    if not ldplayer_finder.console_paths:
        ldplayer_finder.find_all_paths()
    return ldplayer_finder.get_best_console_path()
