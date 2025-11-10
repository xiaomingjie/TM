#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟器按键映射模块
专门针对Android模拟器的按键映射，确保与ADB完全适配
"""

import logging
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

class EmulatorKeyMapping:
    """模拟器按键映射类"""
    
    def __init__(self):
        # 标准Android按键码映射 - 经过实际测试验证
        self.ANDROID_KEY_CODES = {
            # === 字母键 ===
            'a': 29, 'b': 30, 'c': 31, 'd': 32, 'e': 33, 'f': 34, 'g': 35, 'h': 36,
            'i': 37, 'j': 38, 'k': 39, 'l': 40, 'm': 41, 'n': 42, 'o': 43, 'p': 44,
            'q': 45, 'r': 46, 's': 47, 't': 48, 'u': 49, 'v': 50, 'w': 51, 'x': 52,
            'y': 53, 'z': 54,
            
            # === 数字键 ===
            '0': 7, '1': 8, '2': 9, '3': 10, '4': 11, '5': 12, '6': 13, '7': 14, '8': 15, '9': 16,
            
            # === 基础功能键 ===
            'space': 62,        # 空格键 - 重点测试
            'enter': 66,        # 回车键
            'backspace': 67,    # 退格键
            'tab': 61,          # Tab键
            'escape': 111,      # ESC键
            'delete': 112,      # Delete键
            
            # === 系统导航键 ===
            'home': 3,          # Home键
            'back': 4,          # 返回键
            'menu': 82,         # 菜单键
            'recent': 187,      # 最近任务键
            'power': 26,        # 电源键
            'volume_up': 24,    # 音量+
            'volume_down': 25,  # 音量-
            
            # === 方向键 ===
            'up': 19, 'down': 20, 'left': 21, 'right': 22,
            'dpad_up': 19, 'dpad_down': 20, 'dpad_left': 21, 'dpad_right': 22,
            'dpad_center': 23,  # 方向键中心
            
            # === 修饰键 ===
            'shift': 59,        # 左Shift
            'shift_left': 59,   # 左Shift
            'shift_right': 60,  # 右Shift
            'ctrl': 113,        # 左Ctrl
            'ctrl_left': 113,   # 左Ctrl
            'ctrl_right': 114,  # 右Ctrl
            'alt': 57,          # 左Alt
            'alt_left': 57,     # 左Alt
            'alt_right': 58,    # 右Alt
            'meta': 117,        # Meta键
            'meta_left': 117,   # 左Meta
            'meta_right': 118,  # 右Meta
            
            # === F功能键 ===
            'f1': 131, 'f2': 132, 'f3': 133, 'f4': 134, 'f5': 135, 'f6': 136,
            'f7': 137, 'f8': 138, 'f9': 139, 'f10': 140, 'f11': 141, 'f12': 142,
            
            # === 编辑键 ===
            'insert': 124,      # Insert键
            'page_up': 92,      # Page Up
            'page_down': 93,    # Page Down
            'end': 123,         # End键
            'caps_lock': 115,   # Caps Lock
            'num_lock': 143,    # Num Lock
            'scroll_lock': 116, # Scroll Lock
            
            # === 符号键 ===
            'minus': 69,        # -
            'equals': 70,       # =
            'left_bracket': 71, # [
            'right_bracket': 72,# ]
            'backslash': 73,    # \
            'semicolon': 74,    # ;
            'apostrophe': 75,   # '
            'grave': 68,        # `
            'comma': 55,        # ,
            'period': 56,       # .
            'slash': 76,        # /
            
            # === 数字小键盘 ===
            'numpad_0': 144, 'numpad_1': 145, 'numpad_2': 146, 'numpad_3': 147,
            'numpad_4': 148, 'numpad_5': 149, 'numpad_6': 150, 'numpad_7': 151,
            'numpad_8': 152, 'numpad_9': 153,
            'numpad_divide': 154,    # /
            'numpad_multiply': 155,  # *
            'numpad_subtract': 156,  # -
            'numpad_add': 157,       # +
            'numpad_dot': 158,       # .
            'numpad_enter': 160,     # Enter
            'numpad_equals': 161,    # =
            
            # === 媒体控制键 ===
            'media_play': 126,       # 播放/暂停
            'media_pause': 127,      # 暂停
            'media_stop': 128,       # 停止
            'media_next': 87,        # 下一首
            'media_previous': 88,    # 上一首
            'media_rewind': 89,      # 快退
            'media_fast_forward': 90,# 快进
            'mute': 164,             # 静音
            
            # === 特殊键 ===
            'search': 84,        # 搜索键
            'camera': 27,        # 相机键
            'call': 5,           # 通话键
            'endcall': 6,        # 挂断键
            'star': 17,          # *键
            'pound': 18,         # #键
            'clear': 28,         # 清除键
            'focus': 80,         # 对焦键
            'notification': 83,  # 通知键
            'brightness_down': 220, # 亮度-
            'brightness_up': 221,   # 亮度+
        }
        
        # 按键别名映射 - 支持多种命名方式
        self.KEY_ALIASES = {
            # 空格键的多种表示
            ' ': 'space',
            'spacebar': 'space',
            'spc': 'space',
            
            # 回车键的多种表示
            'return': 'enter',
            'ret': 'enter',
            '\n': 'enter',
            '\r': 'enter',
            
            # 退格键的多种表示
            'bksp': 'backspace',
            'bs': 'backspace',
            '\b': 'backspace',
            
            # 删除键
            'del': 'delete',
            
            # ESC键
            'esc': 'escape',
            
            # 方向键别名
            'arrow_up': 'up',
            'arrow_down': 'down',
            'arrow_left': 'left',
            'arrow_right': 'right',
            
            # 修饰键别名
            'control': 'ctrl',
            'ctrl_l': 'ctrl_left',
            'ctrl_r': 'ctrl_right',
            'alt_l': 'alt_left',
            'alt_r': 'alt_right',
            'shift_l': 'shift_left',
            'shift_r': 'shift_right',
            'win': 'meta',
            'windows': 'meta',
            'cmd': 'meta',
            'command': 'meta',
            
            # 其他别名
            'pgup': 'page_up',
            'pgdn': 'page_down',
            'pageup': 'page_up',
            'pagedown': 'page_down',
            'ins': 'insert',
            'caps': 'caps_lock',
            'capslock': 'caps_lock',
            'numlock': 'num_lock',
            'scrolllock': 'scroll_lock',
        }
        
        # Android到Linux按键码映射 - 用于sendevent
        self.ANDROID_TO_LINUX_MAPPING = {
            # 字母键
            29: 30, 30: 48, 31: 46, 32: 32, 33: 18, 34: 33, 35: 34, 36: 35,  # A-H
            37: 23, 38: 36, 39: 37, 40: 38, 41: 50, 42: 49, 43: 24, 44: 25,  # I-P
            45: 16, 46: 19, 47: 31, 48: 20, 49: 22, 50: 47, 51: 17, 52: 45,  # Q-X
            53: 21, 54: 44,  # Y, Z
            
            # 数字键
            7: 11, 8: 2, 9: 3, 10: 4, 11: 5, 12: 6, 13: 7, 14: 8, 15: 9, 16: 10,  # 0-9
            
            # 功能键
            62: 57,   # SPACE -> KEY_SPACE (重点修复)
            66: 28,   # ENTER -> KEY_ENTER
            67: 14,   # BACKSPACE -> KEY_BACKSPACE
            61: 15,   # TAB -> KEY_TAB
            111: 1,   # ESCAPE -> KEY_ESC
            112: 111, # DELETE -> KEY_DELETE
            
            # 方向键
            19: 103,  # UP -> KEY_UP
            20: 108,  # DOWN -> KEY_DOWN
            21: 105,  # LEFT -> KEY_LEFT
            22: 106,  # RIGHT -> KEY_RIGHT
            23: 28,   # DPAD_CENTER -> KEY_ENTER
            
            # 修饰键
            59: 42,   # SHIFT_LEFT -> KEY_LEFTSHIFT
            60: 54,   # SHIFT_RIGHT -> KEY_RIGHTSHIFT
            113: 29,  # CTRL_LEFT -> KEY_LEFTCTRL
            114: 97,  # CTRL_RIGHT -> KEY_RIGHTCTRL
            57: 56,   # ALT_LEFT -> KEY_LEFTALT
            58: 100,  # ALT_RIGHT -> KEY_RIGHTALT
            117: 125, # META_LEFT -> KEY_LEFTMETA
            118: 126, # META_RIGHT -> KEY_RIGHTMETA
            
            # F键
            131: 59, 132: 60, 133: 61, 134: 62, 135: 63, 136: 64,  # F1-F6
            137: 65, 138: 66, 139: 67, 140: 68, 141: 87, 142: 88,  # F7-F12
            
            # 系统键
            3: 102,   # HOME -> KEY_HOME
            4: 158,   # BACK -> KEY_BACK
            82: 139,  # MENU -> KEY_MENU
            26: 116,  # POWER -> KEY_POWER
            24: 115,  # VOLUME_UP -> KEY_VOLUMEUP
            25: 114,  # VOLUME_DOWN -> KEY_VOLUMEDOWN
            
            # 编辑键
            124: 110, # INSERT -> KEY_INSERT
            92: 104,  # PAGE_UP -> KEY_PAGEUP
            93: 109,  # PAGE_DOWN -> KEY_PAGEDOWN
            123: 107, # END -> KEY_END
            115: 58,  # CAPS_LOCK -> KEY_CAPSLOCK
            
            # 符号键
            69: 12,   # MINUS -> KEY_MINUS
            70: 13,   # EQUALS -> KEY_EQUAL
            71: 26,   # LEFT_BRACKET -> KEY_LEFTBRACE
            72: 27,   # RIGHT_BRACKET -> KEY_RIGHTBRACE
            73: 43,   # BACKSLASH -> KEY_BACKSLASH
            74: 39,   # SEMICOLON -> KEY_SEMICOLON
            75: 40,   # APOSTROPHE -> KEY_APOSTROPHE
            68: 41,   # GRAVE -> KEY_GRAVE
            55: 51,   # COMMA -> KEY_COMMA
            56: 52,   # PERIOD -> KEY_DOT
            76: 53,   # SLASH -> KEY_SLASH
        }
    
    def get_android_key_code(self, key: str) -> Optional[int]:
        """获取Android按键码"""
        if not key:
            return None
        
        # 转换为小写
        key = str(key).lower().strip()
        
        # 直接查找
        if key in self.ANDROID_KEY_CODES:
            return self.ANDROID_KEY_CODES[key]
        
        # 查找别名
        if key in self.KEY_ALIASES:
            alias_key = self.KEY_ALIASES[key]
            if alias_key in self.ANDROID_KEY_CODES:
                return self.ANDROID_KEY_CODES[alias_key]
        
        # 特殊处理单字符
        if len(key) == 1:
            if key.isalpha():
                return self.ANDROID_KEY_CODES.get(key)
            elif key.isdigit():
                return self.ANDROID_KEY_CODES.get(key)
        
        logger.warning(f"未找到按键 '{key}' 的Android码")
        return None
    
    def get_linux_key_code(self, android_code: int) -> Optional[int]:
        """获取Linux按键码（用于sendevent）"""
        return self.ANDROID_TO_LINUX_MAPPING.get(android_code)
    
    def validate_key_mapping(self, key: str) -> Tuple[bool, str]:
        """验证按键映射"""
        android_code = self.get_android_key_code(key)
        if android_code is None:
            return False, f"按键 '{key}' 没有Android码映射"
        
        linux_code = self.get_linux_key_code(android_code)
        if linux_code is None:
            return False, f"Android码 {android_code} 没有Linux码映射"
        
        return True, f"按键 '{key}' -> Android({android_code}) -> Linux({linux_code})"
    
    def get_all_supported_keys(self) -> List[str]:
        """获取所有支持的按键列表"""
        keys = list(self.ANDROID_KEY_CODES.keys())
        keys.extend(self.KEY_ALIASES.keys())
        return sorted(set(keys))
    
    def test_space_key_mapping(self) -> Dict[str, any]:
        """专门测试空格键映射"""
        space_variants = ['space', ' ', 'spacebar', 'spc']
        results = {}
        
        for variant in space_variants:
            android_code = self.get_android_key_code(variant)
            linux_code = self.get_linux_key_code(android_code) if android_code else None
            results[variant] = {
                'android_code': android_code,
                'linux_code': linux_code,
                'valid': android_code is not None and linux_code is not None
            }
        
        return results

# 全局实例
emulator_key_mapping = EmulatorKeyMapping()

# 便捷函数
def get_android_key_code(key: str) -> Optional[int]:
    """获取Android按键码的便捷函数"""
    return emulator_key_mapping.get_android_key_code(key)

def get_linux_key_code(android_code: int) -> Optional[int]:
    """获取Linux按键码的便捷函数"""
    return emulator_key_mapping.get_linux_key_code(android_code)

def validate_key(key: str) -> Tuple[bool, str]:
    """验证按键的便捷函数"""
    return emulator_key_mapping.validate_key_mapping(key)

if __name__ == "__main__":
    # 测试模块
    mapping = EmulatorKeyMapping()
    
    print("=== 模拟器按键映射测试 ===")
    
    # 测试空格键
    print("\n空格键测试:")
    space_results = mapping.test_space_key_mapping()
    for variant, result in space_results.items():
        status = "✓" if result['valid'] else "✗"
        print(f"  {status} '{variant}' -> Android({result['android_code']}) -> Linux({result['linux_code']})")
    
    # 测试常用按键
    print("\n常用按键测试:")
    test_keys = ['a', 'space', 'enter', 'backspace', 'ctrl', 'shift', 'f1']
    for key in test_keys:
        valid, msg = mapping.validate_key_mapping(key)
        status = "✓" if valid else "✗"
        print(f"  {status} {msg}")
    
    print(f"\n总共支持 {len(mapping.get_all_supported_keys())} 个按键")
