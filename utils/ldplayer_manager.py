"""
雷电模拟器管理器
用于动态获取雷电模拟器实例信息和ADB端口
"""

import os
import logging
import subprocess
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)

class LDPlayerManager:
    """雷电模拟器管理器"""
    
    def __init__(self):
        self.console_path = None
        self._find_console_path()
        
    def _find_console_path(self):
        """查找雷电模拟器控制台程序路径"""
        try:
            from utils.ldplayer_finder import ldplayer_finder
            ldplayer_finder.find_all_paths()
            self.console_path = ldplayer_finder.get_best_console_path()
            
            if self.console_path:
                logger.info(f"找到雷电控制台程序: {self.console_path}")
            else:
                logger.warning("未找到雷电模拟器控制台程序")
                
        except Exception as e:
            logger.error(f"查找雷电控制台程序失败: {e}")
    
    def is_available(self) -> bool:
        """检查雷电管理器是否可用"""
        return self.console_path is not None and os.path.exists(self.console_path)
    
    def get_all_instances(self) -> List[Dict[str, Any]]:
        """获取所有雷电模拟器实例信息"""
        if not self.is_available():
            logger.warning("雷电管理器不可用")
            return []
            
        try:
            # 使用list2命令获取详细信息
            result = subprocess.run(
                [self.console_path, "list2"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='gbk',  # 雷电控制台输出GBK编码
                errors='ignore',  # 忽略编码错误
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode != 0:
                logger.error(f"获取雷电实例列表失败: {result.stderr}")
                return []
                
            instances = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 4:
                        instance = {
                            'index': int(parts[0]) if parts[0].isdigit() else -1,
                            'title': parts[1],
                            'top_hwnd': int(parts[2]) if parts[2].isdigit() else 0,
                            'bind_hwnd': int(parts[3]) if parts[3].isdigit() else 0,
                            'android_started': parts[4] if len(parts) > 4 else '0',
                            'pid': int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0,
                            'adb_port': self._calculate_adb_port(int(parts[0]) if parts[0].isdigit() else 0)
                        }
                        instances.append(instance)
                        
            logger.info(f"获取到 {len(instances)} 个雷电模拟器实例")
            return instances
            
        except Exception as e:
            logger.error(f"获取雷电实例信息异常: {e}")
            return []
    
    def _calculate_adb_port(self, instance_index: int) -> int:
        """根据实例索引计算ADB端口"""
        # 雷电模拟器的端口计算规则：5555 + index * 2
        return 5555 + instance_index * 2
    
    def get_instance_by_hwnd(self, hwnd: int) -> Optional[Dict[str, Any]]:
        """根据窗口句柄获取实例信息"""
        instances = self.get_all_instances()
        
        for instance in instances:
            if instance['top_hwnd'] == hwnd or instance['bind_hwnd'] == hwnd:
                logger.info(f"找到匹配的雷电实例: 索引={instance['index']}, 端口={instance['adb_port']}")
                return instance
                
        logger.warning(f"未找到匹配窗口句柄 {hwnd} 的雷电实例")
        return None
    
    def get_instance_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """根据窗口标题获取实例信息"""
        instances = self.get_all_instances()
        
        for instance in instances:
            if title in instance['title'] or instance['title'] in title:
                logger.info(f"找到匹配的雷电实例: 标题={instance['title']}, 端口={instance['adb_port']}")
                return instance
                
        logger.warning(f"未找到匹配标题 '{title}' 的雷电实例")
        return None
    
    def get_active_ports(self) -> List[int]:
        """获取所有活跃的雷电模拟器ADB端口"""
        instances = self.get_all_instances()
        active_ports = []
        
        for instance in instances:
            # 只返回已启动的实例端口
            if instance['android_started'] == '1' and instance['adb_port'] > 0:
                active_ports.append(instance['adb_port'])
                
        logger.info(f"雷电模拟器活跃端口: {active_ports}")
        return active_ports
    
    def start_instance(self, instance_index: int) -> bool:
        """启动指定实例"""
        if not self.is_available():
            return False
            
        try:
            result = subprocess.run(
                [self.console_path, "launch", "--index", str(instance_index)],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            success = result.returncode == 0
            if success:
                logger.info(f"雷电实例 {instance_index} 启动成功")
            else:
                logger.error(f"雷电实例 {instance_index} 启动失败: {result.stderr}")
                
            return success
            
        except Exception as e:
            logger.error(f"启动雷电实例 {instance_index} 异常: {e}")
            return False
    
    def stop_instance(self, instance_index: int) -> bool:
        """停止指定实例"""
        if not self.is_available():
            return False
            
        try:
            result = subprocess.run(
                [self.console_path, "quit", "--index", str(instance_index)],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            success = result.returncode == 0
            if success:
                logger.info(f"雷电实例 {instance_index} 停止成功")
            else:
                logger.error(f"雷电实例 {instance_index} 停止失败: {result.stderr}")
                
            return success
            
        except Exception as e:
            logger.error(f"停止雷电实例 {instance_index} 异常: {e}")
            return False


# 全局实例
_ldplayer_manager = None

def get_ldplayer_manager() -> LDPlayerManager:
    """获取雷电模拟器管理器实例"""
    global _ldplayer_manager
    if _ldplayer_manager is None:
        _ldplayer_manager = LDPlayerManager()
    return _ldplayer_manager
