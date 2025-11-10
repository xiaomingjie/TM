"""
Windows API组合键实现 - 不依赖ADB的雷电模拟器组合键方案
支持多种Windows API方法实现组合键发送
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
import win32gui
import win32api
import win32con
import ctypes
from ctypes import wintypes

logger = logging.getLogger(__name__)

class WindowsCombinationKeys:
    """Windows API组合键实现类"""
    
    def __init__(self):
        # Android键码到Windows虚拟键码的映射
        self.android_to_vk_mapping = {
            # 修饰键
            113: win32con.VK_LCONTROL,    # 左Ctrl
            114: win32con.VK_RCONTROL,    # 右Ctrl  
            57: win32con.VK_LMENU,        # 左Alt
            58: win32con.VK_RMENU,        # 右Alt
            59: win32con.VK_LSHIFT,       # 左Shift
            60: win32con.VK_RSHIFT,       # 右Shift
            117: win32con.VK_LWIN,        # 左Win
            118: win32con.VK_RWIN,        # 右Win
            
            # 字母键 (A-Z)
            29: 0x41, 30: 0x42, 31: 0x43, 32: 0x44, 33: 0x45, 34: 0x46, 35: 0x47, 36: 0x48,
            37: 0x49, 38: 0x4A, 39: 0x4B, 40: 0x4C, 41: 0x4D, 42: 0x4E, 43: 0x4F, 44: 0x50,
            45: 0x51, 46: 0x52, 47: 0x53, 48: 0x54, 49: 0x55, 50: 0x56, 51: 0x57, 52: 0x58,
            53: 0x59, 54: 0x5A,
            
            # 数字键 (0-9)
            7: 0x30, 8: 0x31, 9: 0x32, 10: 0x33, 11: 0x34,
            12: 0x35, 13: 0x36, 14: 0x37, 15: 0x38, 16: 0x39,
            
            # 功能键
            62: win32con.VK_SPACE,        # 空格
            66: win32con.VK_RETURN,       # 回车
            67: win32con.VK_BACK,         # 退格
            61: win32con.VK_TAB,          # Tab
            111: win32con.VK_ESCAPE,      # Esc
            112: win32con.VK_DELETE,      # Delete
            
            # 方向键
            19: win32con.VK_UP,           # 上
            20: win32con.VK_DOWN,         # 下
            21: win32con.VK_LEFT,         # 左
            22: win32con.VK_RIGHT,        # 右
            
            # F键
            131: win32con.VK_F1, 132: win32con.VK_F2, 133: win32con.VK_F3, 134: win32con.VK_F4,
            135: win32con.VK_F5, 136: win32con.VK_F6, 137: win32con.VK_F7, 138: win32con.VK_F8,
            139: win32con.VK_F9, 140: win32con.VK_F10, 141: win32con.VK_F11, 142: win32con.VK_F12,
        }
        
        # 常用组合键预定义
        self.common_combinations = {
            'ctrl+a': [113, 29],      # 全选
            'ctrl+c': [113, 31],      # 复制
            'ctrl+v': [113, 50],      # 粘贴
            'ctrl+x': [113, 52],      # 剪切
            'ctrl+z': [113, 54],      # 撤销
            'ctrl+y': [113, 53],      # 重做
            'ctrl+s': [113, 47],      # 保存
            'ctrl+n': [113, 42],      # 新建
            'ctrl+o': [113, 43],      # 打开
            'ctrl+f': [113, 33],      # 查找
            'alt+tab': [57, 61],      # 切换应用
            'alt+f4': [57, 134],      # 关闭窗口
            'shift+tab': [59, 61],    # 反向切换
        }
    
    def send_combination(self, hwnd: int, android_codes: List[int], method: str = 'auto') -> bool:
        """发送组合键到指定窗口
        
        Args:
            hwnd: 目标窗口句柄
            android_codes: Android按键码列表
            method: 发送方法 ('auto', 'sendinput', 'postmessage', 'sendmessage', 'keybd_event')
        
        Returns:
            bool: 是否成功
        """
        try:
            # 转换为Windows虚拟键码
            vk_codes = self._convert_android_to_vk(android_codes)
            if not vk_codes:
                logger.warning(f"无法转换Android码为VK码: {android_codes}")
                return False
            
            logger.info(f"发送组合键: Android{android_codes} -> VK{vk_codes}")
            
            if method == 'auto':
                return self._send_auto_method(hwnd, vk_codes)
            elif method == 'sendinput':
                return self._send_input_method(hwnd, vk_codes)
            elif method == 'postmessage':
                return self._post_message_method(hwnd, vk_codes)
            elif method == 'sendmessage':
                return self._send_message_method(hwnd, vk_codes)
            elif method == 'keybd_event':
                return self._keybd_event_method(hwnd, vk_codes)
            else:
                logger.error(f"不支持的发送方法: {method}")
                return False
                
        except Exception as e:
            logger.error(f"发送组合键异常: {e}")
            return False
    
    def send_combination_by_name(self, hwnd: int, combination_name: str, method: str = 'auto') -> bool:
        """通过组合键名称发送
        
        Args:
            hwnd: 目标窗口句柄
            combination_name: 组合键名称 (如 'ctrl+c')
            method: 发送方法
        
        Returns:
            bool: 是否成功
        """
        combination_lower = combination_name.lower().strip()
        if combination_lower in self.common_combinations:
            android_codes = self.common_combinations[combination_lower]
            return self.send_combination(hwnd, android_codes, method)
        else:
            logger.warning(f"未知的组合键名称: {combination_name}")
            return False
    
    def _convert_android_to_vk(self, android_codes: List[int]) -> List[int]:
        """转换Android键码为Windows虚拟键码"""
        vk_codes = []
        for android_code in android_codes:
            vk_code = self.android_to_vk_mapping.get(android_code)
            if vk_code is not None:
                vk_codes.append(vk_code)
            else:
                logger.warning(f"未找到Android码 {android_code} 的VK映射")
        return vk_codes
    
    def _send_auto_method(self, hwnd: int, vk_codes: List[int]) -> bool:
        """自动选择最佳方法"""
        methods = [
            ('sendinput', self._send_input_method),
            ('postmessage', self._post_message_method),
            ('sendmessage', self._send_message_method),
            ('keybd_event', self._keybd_event_method),
        ]
        
        for method_name, method_func in methods:
            try:
                if method_func(hwnd, vk_codes):
                    logger.info(f"组合键使用 {method_name} 方法成功")
                    return True
            except Exception as e:
                logger.debug(f"{method_name} 方法失败: {e}")
                continue
        
        logger.warning("所有Windows API方法都失败")
        return False
    
    def _send_input_method(self, hwnd: int, vk_codes: List[int]) -> bool:
        """使用SendInput发送组合键（需要窗口为前台）"""
        try:
            # 检查窗口是否存在
            if not win32gui.IsWindow(hwnd):
                return False
            
            # 尝试将窗口设为前台
            current_hwnd = win32gui.GetForegroundWindow()
            if current_hwnd != hwnd:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)  # 等待窗口激活
            
            # 使用keybd_event发送组合键
            # 按下所有键
            for vk_code in vk_codes:
                win32api.keybd_event(vk_code, 0, 0, 0)
                time.sleep(0.01)
            
            # 短暂保持
            time.sleep(0.05)
            
            # 释放所有键（逆序）
            for vk_code in reversed(vk_codes):
                win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.01)
            
            # 恢复原来的前台窗口
            if current_hwnd != hwnd and win32gui.IsWindow(current_hwnd):
                time.sleep(0.1)
                win32gui.SetForegroundWindow(current_hwnd)
            
            return True
            
        except Exception as e:
            logger.debug(f"SendInput方法异常: {e}")
            return False
    
    def _post_message_method(self, hwnd: int, vk_codes: List[int]) -> bool:
        """使用PostMessage发送组合键（后台方式）"""
        try:
            # 检查窗口是否存在
            if not win32gui.IsWindow(hwnd):
                return False
            
            # 按下所有键
            for vk_code in vk_codes:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                lparam = self._make_lparam(scan_code, False, 0, False, False)
                win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
                time.sleep(0.01)
            
            # 短暂保持
            time.sleep(0.05)
            
            # 释放所有键（逆序）
            for vk_code in reversed(vk_codes):
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                lparam = self._make_lparam(scan_code, False, 1, True, True)
                win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lparam)
                time.sleep(0.01)
            
            return True
            
        except Exception as e:
            logger.debug(f"PostMessage方法异常: {e}")
            return False
    
    def _send_message_method(self, hwnd: int, vk_codes: List[int]) -> bool:
        """使用SendMessage发送组合键（同步方式）"""
        try:
            # 检查窗口是否存在
            if not win32gui.IsWindow(hwnd):
                return False
            
            # 按下所有键
            for vk_code in vk_codes:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                lparam = self._make_lparam(scan_code, False, 0, False, False)
                win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
                time.sleep(0.01)
            
            # 短暂保持
            time.sleep(0.05)
            
            # 释放所有键（逆序）
            for vk_code in reversed(vk_codes):
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                lparam = self._make_lparam(scan_code, False, 1, True, True)
                win32gui.SendMessage(hwnd, win32con.WM_KEYUP, vk_code, lparam)
                time.sleep(0.01)
            
            return True
            
        except Exception as e:
            logger.debug(f"SendMessage方法异常: {e}")
            return False
    
    def _keybd_event_method(self, hwnd: int, vk_codes: List[int]) -> bool:
        """使用keybd_event发送组合键（全局方式）"""
        try:
            # 检查窗口是否存在
            if not win32gui.IsWindow(hwnd):
                return False
            
            # 尝试将窗口设为前台
            current_hwnd = win32gui.GetForegroundWindow()
            if current_hwnd != hwnd:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)
            
            # 按下所有键
            for vk_code in vk_codes:
                win32api.keybd_event(vk_code, 0, 0, 0)
                time.sleep(0.01)
            
            # 短暂保持
            time.sleep(0.05)
            
            # 释放所有键（逆序）
            for vk_code in reversed(vk_codes):
                win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.01)
            
            # 恢复原来的前台窗口
            if current_hwnd != hwnd and win32gui.IsWindow(current_hwnd):
                time.sleep(0.1)
                win32gui.SetForegroundWindow(current_hwnd)
            
            return True
            
        except Exception as e:
            logger.debug(f"keybd_event方法异常: {e}")
            return False
    
    def _make_lparam(self, scan_code: int, extended: bool, repeat_count: int, 
                     context_code: bool, previous_state: bool) -> int:
        """构造LPARAM参数"""
        lparam = repeat_count & 0xFFFF
        lparam |= (scan_code & 0xFF) << 16
        if extended:
            lparam |= 0x01000000
        if context_code:
            lparam |= 0x20000000
        if previous_state:
            lparam |= 0x40000000
        return lparam


# 全局实例
windows_combination_keys = WindowsCombinationKeys()

def send_windows_combination(hwnd: int, android_codes: List[int], method: str = 'auto') -> bool:
    """发送Windows API组合键的便捷函数"""
    return windows_combination_keys.send_combination(hwnd, android_codes, method)

def send_windows_combination_by_name(hwnd: int, combination_name: str, method: str = 'auto') -> bool:
    """通过名称发送Windows API组合键的便捷函数"""
    return windows_combination_keys.send_combination_by_name(hwnd, combination_name, method)
