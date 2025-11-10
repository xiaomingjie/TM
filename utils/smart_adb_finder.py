"""
智能ADB查找器
使用多种智能方法查找系统中的ADB工具，避免硬编码路径
"""

import os
import subprocess
import logging
import psutil
import shutil
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class SmartADBFinder:
    """智能ADB查找器"""
    
    def __init__(self):
        self.found_paths: Set[str] = set()
        self.cache_timeout = 300  # 5分钟缓存
        self._last_scan_time = 0
        self._cached_paths: List[str] = []
    
    def find_all_adb_paths(self) -> List[str]:
        """查找所有可用的ADB路径"""
        import time
        current_time = time.time()
        
        # 检查缓存是否有效
        if (current_time - self._last_scan_time < self.cache_timeout and 
            self._cached_paths):
            logger.debug("使用缓存的ADB路径")
            return self._cached_paths.copy()
        
        logger.debug(" 开始智能查找ADB工具...")
        self.found_paths.clear()

        # 1. 检查系统PATH环境变量 (有效)
        self._find_from_system_path()

        # 2. 通过运行进程查找 (有效 - 主要发现方式)
        self._find_from_running_processes()

        # 3. 验证所有找到的路径
        valid_paths = self._validate_adb_paths(list(self.found_paths))

        # 更新缓存
        self._cached_paths = valid_paths
        self._last_scan_time = current_time

        logger.info(f" 智能查找完成，找到 {len(valid_paths)} 个可用的ADB工具")
        return valid_paths
    
    def _find_from_system_path(self):
        """从系统PATH环境变量查找ADB"""
        logger.debug(" 检查系统PATH环境变量...")
        
        # 检查PATH中是否有adb命令
        adb_path = shutil.which('adb')
        if adb_path:
            self.found_paths.add(adb_path)
            logger.debug(f" 在系统PATH中找到ADB: {adb_path}")

        # 检查PATH中的每个目录
        path_env = os.getenv('PATH', '')
        for path_dir in path_env.split(os.pathsep):
            if not path_dir.strip():
                continue

            adb_exe = os.path.join(path_dir.strip(), 'adb.exe')
            if os.path.isfile(adb_exe):
                self.found_paths.add(adb_exe)
                logger.debug(f" 在PATH目录中找到ADB: {adb_exe}")
    

    
    def _find_from_running_processes(self):
        """通过运行进程查找ADB（主要方法）"""
        logger.debug(" 检查运行中的进程...")

        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    proc_exe = proc_info.get('exe', '')

                    if not proc_exe:
                        continue

                    # 直接查找ADB进程
                    if 'adb' in proc_name:
                        self.found_paths.add(proc_exe)
                        logger.debug(f" 从运行进程找到ADB: {proc_exe}")

                    # 查找模拟器进程，在其目录中查找ADB
                    emulator_keywords = ['ldplayer', 'memu', 'android']
                    if any(keyword in proc_name for keyword in emulator_keywords):
                        emulator_dir = os.path.dirname(proc_exe)
                        self._search_adb_in_emulator_directory(emulator_dir)

                        # 搜索父目录（模拟器安装根目录）
                        parent_dir = os.path.dirname(emulator_dir)
                        self._search_adb_in_emulator_directory(parent_dir)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    logger.debug(f"进程扫描异常: {e}")

        except Exception as e:
            logger.debug(f"进程扫描失败: {e}")

    def _search_adb_in_emulator_directory(self, directory: str):
        """在模拟器目录中搜索ADB（优化版本）"""
        if not directory or not os.path.isdir(directory):
            return

        try:
            # 直接检查目录中的adb.exe
            adb_path = os.path.join(directory, 'adb.exe')
            if os.path.isfile(adb_path):
                self.found_paths.add(adb_path)
                logger.info(f" 在目录中找到ADB: {adb_path}")

            # 检查常见的模拟器ADB子目录
            common_subdirs = ['platform-tools', 'tools', 'bin', 'adb', 'LDPlayer9', 'LDPlayer4', 'LDPlayer']
            for subdir in common_subdirs:
                subdir_path = os.path.join(directory, subdir)
                if os.path.isdir(subdir_path):
                    adb_path = os.path.join(subdir_path, 'adb.exe')
                    if os.path.isfile(adb_path):
                        self.found_paths.add(adb_path)
                        logger.info(f" 在子目录中找到ADB: {adb_path}")

        except Exception as e:
            logger.debug(f"模拟器目录搜索失败 {directory}: {e}")
    

    

    

    
    def _validate_adb_paths(self, paths: List[str]) -> List[str]:
        """验证ADB路径的有效性"""
        logger.debug(" 验证ADB路径有效性...")
        
        valid_paths = []
        for path in paths:
            if self._test_adb_executable(path):
                valid_paths.append(path)
                logger.info(f" ADB验证通过: {path}")
            else:
                logger.debug(f" ADB验证失败: {path}")
        
        # 按优先级排序：系统PATH > Android SDK > 模拟器自带
        return self._sort_adb_paths_by_priority(valid_paths)
    
    def _test_adb_executable(self, adb_path: str) -> bool:
        """测试ADB可执行文件是否有效"""
        try:
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
            return result.returncode == 0
        except Exception:
            return False
    
    def _sort_adb_paths_by_priority(self, paths: List[str]) -> List[str]:
        """按优先级排序ADB路径"""
        def get_priority(path: str) -> int:
            path_lower = path.lower()
            
            # 系统PATH中的ADB优先级最高
            if path == 'adb' or 'system32' in path_lower:
                return 0
            
            # Android SDK的ADB优先级较高
            if 'android' in path_lower and 'platform-tools' in path_lower:
                return 1
            
            # 其他Android SDK路径
            if 'android' in path_lower:
                return 2
            
            # 模拟器自带的ADB优先级较低
            return 3
        
        return sorted(paths, key=get_priority)


# 全局实例
smart_adb_finder = SmartADBFinder()


def find_adb_intelligently() -> Optional[str]:
    """智能查找最佳的ADB路径"""
    paths = smart_adb_finder.find_all_adb_paths()
    return paths[0] if paths else None


def get_all_adb_paths() -> List[str]:
    """获取所有可用的ADB路径"""
    return smart_adb_finder.find_all_adb_paths()
