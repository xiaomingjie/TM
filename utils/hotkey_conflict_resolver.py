"""
热键冲突解决器
专门用于解决F12等热键被占用的问题
"""

import time
import logging
import ctypes
from ctypes import wintypes
import psutil
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

class HotkeyConflictResolver:
    """热键冲突解决器"""
    
    def __init__(self):
        self.user32 = ctypes.windll.user32
        
        # 常见占用F12热键的进程
        self.f12_conflict_processes = [
            'devenv.exe',        # Visual Studio (F12 = 转到定义)
            'code.exe',          # VS Code (F12 = 转到定义)
            'chrome.exe',        # Chrome (F12 = 开发者工具)
            'firefox.exe',       # Firefox (F12 = 开发者工具)
            'msedge.exe',        # Edge (F12 = 开发者工具)
            'opera.exe',         # Opera (F12 = 开发者工具)
            'fraps.exe',         # Fraps (F12 = 截图)
            'bandicam.exe',      # Bandicam (F12 = 录制)
            'obs64.exe',         # OBS (F12 = 录制)
            'obs32.exe',         # OBS (F12 = 录制)
            'xsplit.exe',        # XSplit (F12 = 录制)
            'nvidia-share.exe',  # NVIDIA GeForce Experience (F12 = 截图)
            'steam.exe',         # Steam (F12 = 截图)
            'discord.exe',       # Discord (可能占用)
            'teamspeak3.exe',    # TeamSpeak (可能占用)
            'skype.exe',         # Skype (可能占用)
        ]
        
        # F12的虚拟键码
        self.VK_F12 = 0x7B
        
        # 修饰键常量
        self.MOD_ALT = 0x0001
        self.MOD_CONTROL = 0x0002
        self.MOD_SHIFT = 0x0004
        self.MOD_WIN = 0x0008
    
    def detect_f12_conflicts(self) -> List[Tuple[str, int]]:
        """检测可能占用F12热键的进程"""
        conflicts = []
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_name = proc.info['name'].lower()
                    if proc_name in [p.lower() for p in self.f12_conflict_processes]:
                        conflicts.append((proc.info['name'], proc.info['pid']))
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.error(f"检测进程冲突时发生异常: {e}")
        
        return conflicts
    
    def force_unregister_f12(self, hotkey_id: int) -> bool:
        """强制注销F12热键"""
        try:
            success_count = 0
            
            # 尝试注销可能的热键ID范围
            for unregister_id in range(hotkey_id - 200, hotkey_id + 200):
                try:
                    if self.user32.UnregisterHotKey(None, unregister_id):
                        success_count += 1
                except:
                    pass
            
            # 尝试注销系统可能使用的F12热键
            system_ids = [0x7B, 123, 0xF12, 3852, 9003, 9012, 9021]
            for sys_id in system_ids:
                try:
                    if self.user32.UnregisterHotKey(None, sys_id):
                        success_count += 1
                except:
                    pass
            
            logger.info(f"强制注销了 {success_count} 个可能的F12热键")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"强制注销F12热键异常: {e}")
            return False
    
    def try_register_f12_variants(self, hotkey_id: int) -> Tuple[bool, str]:
        """尝试注册F12的各种变体"""
        
        # 尝试的组合列表 (修饰键, 描述)
        variants = [
            (0, "F12"),
            (self.MOD_CONTROL, "Ctrl+F12"),
            (self.MOD_ALT, "Alt+F12"),
            (self.MOD_SHIFT, "Shift+F12"),
            (self.MOD_CONTROL | self.MOD_ALT, "Ctrl+Alt+F12"),
            (self.MOD_CONTROL | self.MOD_SHIFT, "Ctrl+Shift+F12"),
            (self.MOD_ALT | self.MOD_SHIFT, "Alt+Shift+F12"),
        ]
        
        for modifier, description in variants:
            try:
                # 先尝试注销
                self.user32.UnregisterHotKey(None, hotkey_id)
                time.sleep(0.05)
                
                # 尝试注册
                if self.user32.RegisterHotKey(None, hotkey_id, modifier, self.VK_F12):
                    logger.info(f" {description} 热键注册成功")
                    return True, description
                    
            except Exception as e:
                logger.debug(f"注册 {description} 失败: {e}")
                continue
        
        return False, ""
    
    def try_alternative_keys(self, hotkey_id: int) -> Tuple[bool, str]:
        """尝试使用其他键作为F12的替代"""
        
        # 替代键列表 (虚拟键码, 描述)
        alternatives = [
            (0x7A, "F11"),      # F11
            (0x77, "F8"),       # F8
            (0x76, "F7"),       # F7
            (0x75, "F6"),       # F6
            (0x74, "F5"),       # F5
            (0x73, "F4"),       # F4
            (0x72, "F3"),       # F3
            (0x71, "F2"),       # F2
            (0x70, "F1"),       # F1
            (0x2D, "Insert"),   # Insert键
            (0x23, "End"),      # End键
            (0x22, "Page Down"), # Page Down键
        ]
        
        for vk_code, description in alternatives:
            try:
                # 先尝试注销
                self.user32.UnregisterHotKey(None, hotkey_id)
                time.sleep(0.05)
                
                # 尝试注册
                if self.user32.RegisterHotKey(None, hotkey_id, 0, vk_code):
                    logger.info(f" {description} 热键注册成功（作为F12替代）")
                    return True, description
                    
            except Exception as e:
                logger.debug(f"注册 {description} 失败: {e}")
                continue
        
        return False, ""
    
    def resolve_f12_conflict(self, hotkey_id: int) -> Tuple[bool, str]:
        """解决F12热键冲突的主方法"""
        logger.info(" 开始解决F12热键冲突...")
        
        # 1. 检测冲突进程
        conflicts = self.detect_f12_conflicts()
        if conflicts:
            logger.info(" 检测到可能占用F12热键的进程:")
            for proc_name, pid in conflicts:
                logger.info(f"  - {proc_name} (PID: {pid})")
        
        # 2. 强制注销现有的F12热键
        self.force_unregister_f12(hotkey_id)
        time.sleep(0.2)
        
        # 3. 尝试多次注册原始F12
        logger.info(" 尝试多次注册原始F12热键...")
        for attempt in range(10):
            try:
                if self.user32.RegisterHotKey(None, hotkey_id, 0, self.VK_F12):
                    logger.info(f" F12热键在第{attempt + 1}次尝试中注册成功")
                    return True, "F12"
            except:
                pass
            time.sleep(0.1 * (attempt + 1))
        
        # 4. 尝试F12的修饰键变体
        logger.info(" 尝试F12的修饰键变体...")
        success, description = self.try_register_f12_variants(hotkey_id)
        if success:
            return True, description
        
        # 5. 尝试其他键作为替代
        logger.info(" 尝试其他键作为F12替代...")
        success, description = self.try_alternative_keys(hotkey_id)
        if success:
            return True, description
        
        # 6. 最后的尝试 - 使用随机ID
        logger.info(" 最后尝试 - 使用不同的热键ID...")
        import random
        for _ in range(5):
            random_id = random.randint(10000, 99999)
            try:
                if self.user32.RegisterHotKey(None, random_id, self.MOD_CONTROL, self.VK_F12):
                    logger.info(f" Ctrl+F12热键使用随机ID {random_id} 注册成功")
                    return True, f"Ctrl+F12 (ID:{random_id})"
            except:
                continue
        
        logger.error(" 所有F12热键冲突解决方法都失败了")
        return False, ""
    
    def get_conflict_resolution_tips(self) -> List[str]:
        """获取冲突解决建议"""
        tips = [
            " F12热键冲突解决建议:",
            "",
            "1. 关闭可能占用F12的程序:",
            "   - 浏览器 (Chrome, Firefox, Edge等)",
            "   - 开发工具 (Visual Studio, VS Code等)",
            "   - 录屏软件 (OBS, Fraps, Bandicam等)",
            "   - 游戏平台 (Steam, NVIDIA GeForce Experience等)",
            "",
            "2. 如果无法关闭这些程序:",
            "   - 程序会自动尝试使用 Ctrl+F12 作为替代",
            "   - 或使用其他F键 (F11, F8等) 作为替代",
            "",
            "3. 手动解决方法:",
            "   - 在任务管理器中结束占用进程",
            "   - 重启计算机清除所有热键占用",
            "   - 修改其他程序的热键设置",
        ]
        return tips


# 全局实例
hotkey_resolver = HotkeyConflictResolver()

def resolve_f12_hotkey_conflict(hotkey_id: int) -> Tuple[bool, str]:
    """解决F12热键冲突的便捷函数"""
    return hotkey_resolver.resolve_f12_conflict(hotkey_id)

def get_f12_conflict_tips() -> List[str]:
    """获取F12冲突解决建议的便捷函数"""
    return hotkey_resolver.get_conflict_resolution_tips()
