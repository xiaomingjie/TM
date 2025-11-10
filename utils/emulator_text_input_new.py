#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟器文本输入增强器
集成ADB Shell Input作为模拟器兼容的文本输入方法
重构版本：删除ADB按键功能，保留文本输入功能
"""

import os
import time
import subprocess
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 导入新的按键映射模块
try:
    from .emulator_key_mapping import emulator_key_mapping, get_android_key_code, get_linux_key_code
    logger.info("成功导入新的模拟器按键映射模块")
    USE_NEW_MAPPING = True
except ImportError:
    logger.warning("无法导入新的按键映射模块，使用备用映射")
    USE_NEW_MAPPING = False

# Android按键码映射表
ANDROID_KEY_CODES = {
    # 字母键
    'a': 29, 'b': 30, 'c': 31, 'd': 32, 'e': 33, 'f': 34, 'g': 35, 'h': 36,
    'i': 37, 'j': 38, 'k': 39, 'l': 40, 'm': 41, 'n': 42, 'o': 43, 'p': 44,
    'q': 45, 'r': 46, 's': 47, 't': 48, 'u': 49, 'v': 50, 'w': 51, 'x': 52,
    'y': 53, 'z': 54,

    # 数字键
    '0': 7, '1': 8, '2': 9, '3': 10, '4': 11, '5': 12, '6': 13, '7': 14, '8': 15, '9': 16,

    # 功能键
    'space': 62, 'enter': 66, 'backspace': 67, 'tab': 61, 'escape': 111, 'delete': 112,
    'home': 3, 'back': 4, 'menu': 82,

    # 方向键
    'up': 19, 'down': 20, 'left': 21, 'right': 22,

    # 修饰键
    'shift': 59, 'ctrl': 113, 'alt': 57, 'meta': 117,
    'shift_left': 59, 'shift_right': 60,
    'ctrl_left': 113, 'ctrl_right': 114,
    'alt_left': 57, 'alt_right': 58,

    # F键
    'f1': 131, 'f2': 132, 'f3': 133, 'f4': 134, 'f5': 135, 'f6': 136,
    'f7': 137, 'f8': 138, 'f9': 139, 'f10': 140, 'f11': 141, 'f12': 142,

    # 其他常用键
    'insert': 124, 'page_up': 92, 'page_down': 93, 'end': 123,
    'caps_lock': 115, 'num_lock': 143, 'scroll_lock': 116,
    'pause': 121, 'print_screen': 120,

    # 符号键
    'minus': 69, 'equals': 70, 'left_bracket': 71, 'right_bracket': 72,
    'backslash': 73, 'semicolon': 74, 'apostrophe': 75, 'grave': 68,
    'comma': 55, 'period': 56, 'slash': 76,
}

class EmulatorTextInputManager:
    """模拟器文本输入管理器"""
    
    def __init__(self):
        self.adb_cache = {}  # 缓存ADB相关信息
        self.console_cache = {}  # 缓存控制台程序信息
        
    def is_emulator_window(self, hwnd: int) -> bool:
        """检测是否为模拟器窗口"""
        try:
            import win32gui
            
            # 获取窗口类名和标题
            class_name = win32gui.GetClassName(hwnd)
            window_title = win32gui.GetWindowText(hwnd)
            
            # 检测常见模拟器的窗口特征
            emulator_patterns = [
                'LDPlayerMainFrame',  # 雷电模拟器
                'NemuPlayer',         # MuMu模拟器
                'MEmuMainFrame',      # 逍遥模拟器
                'TitanEngine',        # 天天模拟器
            ]
            
            for pattern in emulator_patterns:
                if pattern.lower() in class_name.lower() or pattern.lower() in window_title.lower():
                    logger.debug(f"检测到模拟器窗口: {class_name} - {window_title}")
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"检测模拟器窗口失败: {e}")
            return False
    
    def get_emulator_type(self, hwnd: int) -> str:
        """获取模拟器类型"""
        try:
            import win32gui
            
            class_name = win32gui.GetClassName(hwnd)
            window_title = win32gui.GetWindowText(hwnd)
            
            # 根据窗口特征判断模拟器类型
            logger.debug(f"检测模拟器类型: 类名='{class_name}', 标题='{window_title}'")

            # 雷电模拟器
            if ('LDPlayerMainFrame' in class_name or
                'RenderWindow' in class_name or
                'ldplayer' in window_title.lower() or
                'TheRender' in window_title):
                return "ldplayer"
            # MuMu模拟器
            elif ('NemuPlayer' in class_name or
                  'mumu' in window_title.lower() or
                  'MuMu' in window_title):
                return "mumu"
            # 逍遥模拟器
            elif ('MEmuMainFrame' in class_name or
                  'memu' in window_title.lower()):
                return "memu"
            # 天天模拟器
            elif 'TitanEngine' in class_name:
                return "tiantian"
            else:
                logger.debug(f"未识别的模拟器类型: 类名='{class_name}', 标题='{window_title}'")
                return "unknown"
            
        except Exception as e:
            logger.debug(f"获取模拟器类型失败: {e}")
            return "unknown"
    
    def try_adb_shell_input(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """优化的多策略文本输入系统 - 基于开源最佳实践"""
        try:
            emulator_type = self.get_emulator_type(hwnd)
            logger.info(f"🚀 开始多策略文本输入: '{text}' (模式: {text_input_mode}, 模拟器: {emulator_type})")

            # 策略1: 增强ADBKeyboard (最佳中文支持，自动配置)
            if self._try_adb_keyboard_enhanced(hwnd, text, text_input_mode):
                logger.info(f"✅ 策略1成功 - ADBKeyboard增强输入: '{text}'")
                return True

            # 策略2: Base64编码输入 (解决Unicode问题)
            if self._try_base64_input(hwnd, text, text_input_mode):
                logger.info(f"✅ 策略2成功 - Base64编码输入: '{text}'")
                return True

            # 策略3: Unicode字符码输入 (字符级精确控制)
            if self._try_unicode_chars_input(hwnd, text, text_input_mode):
                logger.info(f"✅ 策略3成功 - Unicode字符输入: '{text}'")
                return True

            # 策略4: 传统ADB input text (英文数字回退)
            if self._try_generic_adb_input(hwnd, text, text_input_mode):
                logger.info(f"✅ 策略4成功 - 通用ADB输入: '{text}'")
                return True

            # 策略5: 原有的广播输入 (最后的回退)
            if self._try_broadcast_input(hwnd, text, text_input_mode):
                logger.info(f"✅ 策略5成功 - 广播输入: '{text}'")
                return True

            logger.error(f"❌ 所有5种输入策略都失败: '{text}'")
            return False

        except Exception as e:
            logger.error(f"多策略文本输入系统异常: {e}")
            import traceback
            logger.debug(f"异常详情: {traceback.format_exc()}")
            return False

    def _try_base64_input(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """使用Base64编码输入文本 - 解决Unicode字符问题"""
        try:
            import base64

            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 将文本编码为Base64
            text_bytes = text.encode('utf-8')
            text_b64 = base64.b64encode(text_bytes).decode('ascii')

            logger.debug(f"Base64编码: '{text}' -> '{text_b64}'")

            # 根据文本输入模式选择设备分配策略
            if text_input_mode == '单组文本':
                # 每个窗口给所有设备发送
                window_index = self._get_window_index_for_hwnd(hwnd)
                logger.info(f"Base64单组输入: 窗口{window_index}给所有{len(devices)}个设备发送")

                success_count = 0
                for device_id in devices:
                    try:
                        cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast',
                               '-a', 'ADB_INPUT_B64', '--es', 'msg', text_b64]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        if result.returncode == 0:
                            logger.info(f"✅ Base64输入成功: 窗口{window_index}->设备{device_id}")
                            success_count += 1
                        else:
                            logger.debug(f"设备 {device_id} Base64输入失败: {result.stderr}")

                    except Exception as e:
                        logger.debug(f"设备 {device_id} Base64处理异常: {e}")
                        continue

                return success_count > 0
            else:
                # 多组文字：根据窗口索引选择设备
                window_index = self._get_window_index_for_hwnd(hwnd)
                if window_index < len(devices):
                    device_id = devices[window_index]
                else:
                    device_id = devices[window_index % len(devices)]

                cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast',
                       '-a', 'ADB_INPUT_B64', '--es', 'msg', text_b64]
                # 使用更强力的方法隐藏窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

                creation_flags = (
                    subprocess.CREATE_NO_WINDOW |
                    subprocess.DETACHED_PROCESS |
                    subprocess.CREATE_NEW_PROCESS_GROUP
                )

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                      creationflags=creation_flags, startupinfo=startupinfo)

                if result.returncode == 0:
                    logger.info(f"✅ Base64多组输入成功: 窗口{window_index}->设备{device_id}")
                    return True
                else:
                    logger.debug(f"Base64多组输入失败: {result.stderr}")
                    return False

        except Exception as e:
            logger.debug(f"Base64输入异常: {e}")
            return False

    def _try_unicode_chars_input(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """使用Unicode字符码输入文本"""
        try:
            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 将文本转换为Unicode字符码
            char_codes = [str(ord(char)) for char in text]
            char_codes_str = ','.join(char_codes)

            logger.debug(f"Unicode编码: '{text}' -> '{char_codes_str}'")

            # 根据文本输入模式选择设备分配策略
            if text_input_mode == '单组文本':
                # 每个窗口给所有设备发送
                window_index = self._get_window_index_for_hwnd(hwnd)
                logger.info(f"Unicode单组输入: 窗口{window_index}给所有{len(devices)}个设备发送")

                success_count = 0
                for device_id in devices:
                    try:
                        cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast',
                               '-a', 'ADB_INPUT_CHARS', '--eia', 'chars', char_codes_str]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        if result.returncode == 0:
                            logger.info(f"✅ Unicode输入成功: 窗口{window_index}->设备{device_id}")
                            success_count += 1
                        else:
                            logger.debug(f"设备 {device_id} Unicode输入失败: {result.stderr}")

                    except Exception as e:
                        logger.debug(f"设备 {device_id} Unicode处理异常: {e}")
                        continue

                return success_count > 0
            else:
                # 多组文字：根据窗口索引选择设备
                window_index = self._get_window_index_for_hwnd(hwnd)
                if window_index < len(devices):
                    device_id = devices[window_index]
                else:
                    device_id = devices[window_index % len(devices)]

                cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast',
                       '-a', 'ADB_INPUT_CHARS', '--eia', 'chars', char_codes_str]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0:
                    logger.info(f"✅ Unicode多组输入成功: 窗口{window_index}->设备{device_id}")
                    return True
                else:
                    logger.debug(f"Unicode多组输入失败: {result.stderr}")
                    return False

        except Exception as e:
            logger.debug(f"Unicode输入异常: {e}")
            return False

    def _try_adb_keyboard_enhanced(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """增强的ADBKeyboard输入方法 - 智能多ADB连接"""
        try:
            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 根据文本输入模式选择策略
            if text_input_mode == '单组文本':
                # 单组文字：使用虚拟多设备策略
                return self._single_text_multi_device_input(hwnd, text, adb_path)
            else:
                # 多组文字：使用原有的设备分配策略
                return self._multi_text_device_input(hwnd, text, adb_path)

        except Exception as e:
            logger.debug(f"ADBKeyboard增强输入异常: {e}")
            return False

    def _single_text_multi_device_input(self, hwnd: int, text: str, adb_path: str) -> bool:
        """单组文字多设备输入 - 智能分配策略，避免重复输入"""
        try:
            import time

            window_index = self._get_window_index_for_hwnd(hwnd)

            # 获取实际的ADB设备
            real_devices = self._get_adb_devices(adb_path)
            if not real_devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 智能分配策略：
            # 如果有多个设备，每个窗口对应一个设备
            # 如果只有一个设备，只让第一个窗口发送，其他窗口模拟成功

            if len(real_devices) >= 3:
                # 多设备情况：每个窗口对应一个设备
                if window_index < len(real_devices):
                    target_device = real_devices[window_index]
                else:
                    target_device = real_devices[window_index % len(real_devices)]

                logger.info(f"多设备单组文字输入: 窗口{window_index}->设备{target_device}")

                # 确保ADBKeyboard已安装并设置
                if not self._ensure_adb_keyboard_ready(adb_path, target_device):
                    logger.debug(f"设备 {target_device} ADBKeyboard准备失败")
                    return False

                cmd = [adb_path, '-s', target_device, 'shell', 'am', 'broadcast',
                       '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0:
                    logger.info(f"✅ 多设备单组文字输入成功: 窗口{window_index}->设备{target_device}")
                    return True
                else:
                    logger.debug(f"多设备单组文字输入失败: {result.stderr}")
                    return False
            else:
                # 单设备情况：只让第一个窗口发送，其他窗口模拟成功
                base_device = real_devices[0]

                if window_index == 0:
                    # 第一个窗口：实际发送
                    logger.info(f"单设备单组文字输入: 窗口{window_index}实际发送到设备{base_device}")

                    # 确保ADBKeyboard已安装并设置
                    if not self._ensure_adb_keyboard_ready(adb_path, base_device):
                        logger.debug(f"设备 {base_device} ADBKeyboard准备失败")
                        return False

                    cmd = [adb_path, '-s', base_device, 'shell', 'am', 'broadcast',
                           '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                          creationflags=subprocess.CREATE_NO_WINDOW)

                    if result.returncode == 0:
                        logger.info(f"✅ 单设备单组文字输入成功: 窗口{window_index}->设备{base_device}")
                        return True
                    else:
                        logger.debug(f"单设备单组文字输入失败: {result.stderr}")
                        return False
                else:
                    # 其他窗口：模拟成功，避免重复输入
                    logger.info(f"单设备单组文字输入: 窗口{window_index}模拟成功(避免重复)")
                    return True

        except Exception as e:
            logger.debug(f"单组文字智能分配异常: {e}")
            return False

    def _multi_text_device_input(self, hwnd: int, text: str, adb_path: str) -> bool:
        """多组文字设备输入 - 原有逻辑"""
        try:
            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 多组文字：根据窗口索引选择设备
            window_index = self._get_window_index_for_hwnd(hwnd)
            if window_index < len(devices):
                device_id = devices[window_index]
            else:
                device_id = devices[window_index % len(devices)]

            # 确保ADBKeyboard已安装并设置
            if not self._ensure_adb_keyboard_ready(adb_path, device_id):
                logger.debug(f"设备 {device_id} ADBKeyboard准备失败")
                return False

            cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast',
                   '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                logger.info(f"✅ ADBKeyboard增强多组输入成功: 窗口{window_index}->设备{device_id}")
                return True
            else:
                logger.debug(f"ADBKeyboard增强多组输入失败: {result.stderr}")
                return False

        except Exception as e:
            logger.debug(f"ADBKeyboard增强输入异常: {e}")
            return False

    def _ensure_adb_keyboard_ready(self, adb_path: str, device_id: str) -> bool:
        """确保ADBKeyboard已安装、启用并设置为当前输入法"""
        try:
            # 检查是否已安装
            if not self._check_adb_keyboard_installed(adb_path, device_id):
                logger.debug(f"设备 {device_id} 上ADBKeyboard未安装")
                return False

            # 启用ADBKeyboard
            enable_cmd = [adb_path, '-s', device_id, 'shell', 'ime', 'enable', 'com.android.adbkeyboard/.AdbIME']
            result = subprocess.run(enable_cmd, capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            # 设置为当前输入法
            set_cmd = [adb_path, '-s', device_id, 'shell', 'ime', 'set', 'com.android.adbkeyboard/.AdbIME']
            result = subprocess.run(set_cmd, capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                logger.debug(f"设备 {device_id} ADBKeyboard设置成功")
                return True
            else:
                logger.debug(f"设备 {device_id} ADBKeyboard设置失败: {result.stderr}")
                return False

        except Exception as e:
            logger.debug(f"设备 {device_id} ADBKeyboard准备异常: {e}")
            return False

    def _create_virtual_adb_devices(self, adb_path: str, window_count: int) -> list:
        """创建虚拟ADB设备连接 - 通过端口转发实现多连接"""
        try:
            import time
            import threading

            # 获取基础设备
            real_devices = self._get_adb_devices(adb_path)
            if not real_devices:
                return []

            base_device = real_devices[0]
            virtual_devices = []

            # 为每个窗口创建虚拟设备连接
            base_port = 15555  # 起始端口

            for i in range(window_count):
                virtual_port = base_port + i
                virtual_device = f"127.0.0.1:{virtual_port}"

                try:
                    # 创建端口转发
                    forward_cmd = [adb_path, '-s', base_device, 'forward',
                                 f'tcp:{virtual_port}', f'tcp:5555']
                    result = subprocess.run(forward_cmd, capture_output=True, text=True, timeout=10,
                                          creationflags=subprocess.CREATE_NO_WINDOW)

                    if result.returncode == 0:
                        # 连接到虚拟设备
                        connect_cmd = [adb_path, 'connect', virtual_device]
                        result = subprocess.run(connect_cmd, capture_output=True, text=True, timeout=10,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        if result.returncode == 0:
                            virtual_devices.append(virtual_device)
                            logger.info(f"✅ 创建虚拟设备成功: {virtual_device} (窗口{i})")
                        else:
                            logger.debug(f"连接虚拟设备失败: {virtual_device}")
                    else:
                        logger.debug(f"端口转发失败: {virtual_port}")

                except Exception as e:
                    logger.debug(f"创建虚拟设备{i}异常: {e}")
                    continue

            if virtual_devices:
                logger.info(f"🚀 成功创建{len(virtual_devices)}个虚拟ADB设备")
                return virtual_devices
            else:
                logger.debug("未能创建任何虚拟设备，回退到原设备")
                return real_devices

        except Exception as e:
            logger.debug(f"创建虚拟ADB设备异常: {e}")
            return self._get_adb_devices(adb_path)

    def _cleanup_virtual_devices(self, adb_path: str, virtual_devices: list):
        """清理虚拟设备连接"""
        try:
            for device in virtual_devices:
                if '127.0.0.1:' in device:
                    try:
                        # 断开连接
                        disconnect_cmd = [adb_path, 'disconnect', device]
                        subprocess.run(disconnect_cmd, capture_output=True, text=True, timeout=5,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                        logger.debug(f"清理虚拟设备: {device}")
                    except:
                        pass
        except Exception as e:
            logger.debug(f"清理虚拟设备异常: {e}")

    def _try_generic_adb_input(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """通用ADB input text方法 - 适用于英文和数字"""
        try:
            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 转义特殊字符
            escaped_text = text.replace('"', '\\"').replace('\\', '\\\\').replace(' ', '\\ ')

            # 根据文本输入模式选择设备分配策略
            if text_input_mode == '单组文本':
                # 每个窗口给所有设备发送
                window_index = self._get_window_index_for_hwnd(hwnd)
                logger.info(f"通用ADB单组输入: 窗口{window_index}给所有{len(devices)}个设备发送")

                success_count = 0
                for device_id in devices:
                    try:
                        cmd = [adb_path, '-s', device_id, 'shell', 'input', 'text', escaped_text]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        if result.returncode == 0:
                            logger.info(f"✅ 通用ADB输入成功: 窗口{window_index}->设备{device_id}")
                            success_count += 1
                        else:
                            logger.debug(f"设备 {device_id} 通用ADB输入失败: {result.stderr}")

                    except Exception as e:
                        logger.debug(f"设备 {device_id} 通用ADB处理异常: {e}")
                        continue

                return success_count > 0
            else:
                # 多组文字：根据窗口索引选择设备
                window_index = self._get_window_index_for_hwnd(hwnd)
                if window_index < len(devices):
                    device_id = devices[window_index]
                else:
                    device_id = devices[window_index % len(devices)]

                cmd = [adb_path, '-s', device_id, 'shell', 'input', 'text', escaped_text]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0:
                    logger.info(f"✅ 通用ADB多组输入成功: 窗口{window_index}->设备{device_id}")
                    return True
                else:
                    logger.debug(f"通用ADB多组输入失败: {result.stderr}")
                    return False

        except Exception as e:
            logger.debug(f"通用ADB输入异常: {e}")
            return False

    def _ldplayer_adb_input(self, hwnd: int, text: str) -> bool:
        """雷电模拟器ADB输入"""
        try:
            # 获取雷电控制台程序路径
            console_path = self._get_ldplayer_console_path()
            if not console_path:
                logger.debug("未找到雷电模拟器控制台程序")
                return False

            # 获取实例信息
            instance_info = self._get_ldplayer_instance_info(hwnd, console_path)
            if not instance_info:
                logger.debug("无法获取雷电模拟器实例信息")
                return False

            instance_index = instance_info.get('index', 0)

            # 转义特殊字符
            escaped_text = text.replace('"', '\\"').replace('\\', '\\\\')

            # 执行ADB输入命令
            cmd = [console_path, "adb", "--index", str(instance_index), "--command",
                   f'shell input text "{escaped_text}"']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                logger.info(f"雷电ADB文本输入成功: {text}")
                return True
            else:
                logger.debug(f"雷电ADB文本输入失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"雷电模拟器ADB输入异常: {e}")
            return False

    def _generic_adb_input(self, hwnd: int, text: str) -> bool:
        """通用ADB输入（适用于其他模拟器）"""
        try:
            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 单组文字输入：根据窗口索引选择对应的设备
            window_index = self._get_window_index_for_hwnd(hwnd)

            # 根据窗口索引选择对应的设备
            if window_index < len(devices):
                device_id = devices[window_index]
                logger.info(f"通用ADB输入: 窗口索引{window_index} -> 设备{device_id}")
            else:
                device_index = window_index % len(devices)
                device_id = devices[device_index]
                logger.info(f"通用ADB输入: 窗口索引{window_index} -> 设备索引{device_index} -> 设备{device_id}")

            # 转义特殊字符
            escaped_text = text.replace('"', '\\"').replace('\\', '\\\\')

            # 执行ADB输入命令
            cmd = [adb_path, '-s', device_id, 'shell', 'input', 'text', escaped_text]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                logger.info(f"通用ADB文本输入成功: {text} -> 设备{device_id}")
                return True
            else:
                logger.debug(f"通用ADB文本输入失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"通用ADB输入异常: {e}")
            return False

    @staticmethod
    def convert_key_to_android_code(key: str) -> Optional[int]:
        """将按键名称转换为Android按键码 - 专用于模拟器窗口"""
        if USE_NEW_MAPPING:
            # 使用新的模拟器专用按键映射
            try:
                android_code = get_android_key_code(key)
                if android_code is not None:
                    logger.debug(f"模拟器Android映射: {key} -> {android_code}")
                    return android_code
                else:
                    logger.warning(f"模拟器Android映射失败: {key}")
            except Exception as e:
                logger.error(f"模拟器Android映射异常: {e}")
                # 回退到备用方法

        # 备用方法（保持原有逻辑）
        # 标准化按键名称
        key_lower = key.lower().strip()

        # 直接查找映射表
        if key_lower in ANDROID_KEY_CODES:
            android_code = ANDROID_KEY_CODES[key_lower]
            logger.debug(f"按键映射成功: {key} -> {android_code}")
            return android_code

        # 处理特殊情况
        special_mappings = {
            'return': 66,  # Enter
            'del': 112,    # Delete
            'esc': 111,    # Escape
            'pageup': 92,  # Page Up
            'pagedown': 93, # Page Down
            'capslock': 115, # Caps Lock
            'numlock': 143,  # Num Lock
            'scrolllock': 116, # Scroll Lock
            'printscreen': 120, # Print Screen
        }

        if key_lower in special_mappings:
            android_code = special_mappings[key_lower]
            logger.debug(f"特殊按键映射: {key} -> {android_code}")
            return android_code

        logger.debug(f"无法转换按键到Android码: {key}")
        return None

    @staticmethod
    def convert_key_combination_to_android_codes(keys: list) -> list:
        """将按键组合转换为Android按键码列表"""
        android_codes = []
        for key in keys:
            code = EmulatorTextInputManager.convert_key_to_android_code(key)
            if code is not None:
                android_codes.append(code)
            else:
                logger.warning(f"组合键中的按键无法转换: {key}")
        return android_codes

    def _contains_chinese(self, text: str) -> bool:
        """检测文本是否包含中文字符"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    def _try_adb_keyboard_input(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """尝试使用ADBKeyboard输入中文，严格分离单组和多组模式"""
        try:
            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 根据文本输入模式选择不同的设备分配策略
            if text_input_mode == '单组文本':
                # 单组文字输入：每个窗口都给所有设备发送相同的文字，确保所有模拟器都收到输入
                window_index = self._get_window_index_for_hwnd(hwnd)
                logger.info(f"单组文字输入: 窗口{window_index}给所有{len(devices)}个设备发送文字'{text}'")

                success_count = 0
                for i, device_id in enumerate(devices):
                    try:
                        # 检查ADBKeyboard是否已安装
                        if not self._check_adb_keyboard_installed(adb_path, device_id):
                            logger.warning(f"设备 {device_id} 上ADBKeyboard未安装，跳过")
                            continue

                        # 设置ADBKeyboard为当前输入法
                        if not self._set_adb_keyboard_ime(adb_path, device_id):
                            logger.warning(f"设备 {device_id} 设置ADBKeyboard输入法失败，跳过")
                            continue

                        # 发送中文文本
                        logger.info(f"窗口{window_index}向设备{device_id}发送文字: '{text}'")
                        cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        if result.returncode == 0:
                            logger.info(f"✅ 窗口{window_index}->设备{device_id}输入成功: '{text}'")
                            success_count += 1
                        else:
                            logger.error(f"❌ 窗口{window_index}->设备{device_id}输入失败: {result.stderr}")

                    except Exception as e:
                        logger.error(f"❌ 窗口{window_index}->设备{device_id}处理异常: {e}")
                        continue

                # 只要有一个设备成功就算成功
                return success_count > 0
                for device_id in devices:
                    try:
                        logger.info(f"=== 处理设备 {device_id} ===")

                        # 检查ADBKeyboard是否已安装
                        keyboard_installed = self._check_adb_keyboard_installed(adb_path, device_id)
                        logger.info(f"设备 {device_id} ADBKeyboard安装状态: {keyboard_installed}")
                        if not keyboard_installed:
                            logger.warning(f"设备 {device_id} 上ADBKeyboard未安装，跳过")
                            continue

                        # 设置ADBKeyboard为当前输入法
                        ime_set = self._set_adb_keyboard_ime(adb_path, device_id)
                        logger.info(f"设备 {device_id} ADBKeyboard输入法设置状态: {ime_set}")
                        if not ime_set:
                            logger.warning(f"设备 {device_id} 设置ADBKeyboard输入法失败，跳过")
                            continue

                        # 发送中文文本
                        logger.info(f"向设备 {device_id} 发送文字: '{text}'")
                        cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        logger.info(f"设备 {device_id} 命令执行结果: returncode={result.returncode}")
                        if result.stdout:
                            logger.info(f"设备 {device_id} stdout: {result.stdout}")
                        if result.stderr:
                            logger.info(f"设备 {device_id} stderr: {result.stderr}")

                        if result.returncode == 0:
                            logger.info(f"✅ 单组模式ADBKeyboard输入成功: 设备{device_id} <- '{text}'")
                            success_count += 1
                        else:
                            logger.error(f"❌ 设备 {device_id} ADBKeyboard输入失败: {result.stderr}")

                    except Exception as e:
                        logger.error(f"❌ 设备 {device_id} 处理异常: {e}")
                        import traceback
                        logger.debug(f"设备 {device_id} 异常详情: {traceback.format_exc()}")
                        continue

                # 只要有一个设备成功就算成功
                return success_count > 0

            else:
                # 多组文字输入：根据窗口索引选择对应的设备
                window_index = self._get_window_index_for_hwnd(hwnd)

                # 根据窗口索引选择对应的设备
                if window_index < len(devices):
                    device_id = devices[window_index]
                    logger.info(f"多组文字输入: 窗口索引{window_index} -> 设备{device_id}")
                else:
                    # 如果窗口索引超出设备数量，使用模运算分配
                    device_index = window_index % len(devices)
                    device_id = devices[device_index]
                    logger.info(f"多组文字输入: 窗口索引{window_index} -> 设备索引{device_index} -> 设备{device_id}")

                # 检查ADBKeyboard是否已安装
                if not self._check_adb_keyboard_installed(adb_path, device_id):
                    logger.debug(f"设备 {device_id} 上ADBKeyboard未安装")
                    return False

                # 设置ADBKeyboard为当前输入法
                if not self._set_adb_keyboard_ime(adb_path, device_id):
                    logger.debug(f"设备 {device_id} 设置ADBKeyboard输入法失败")
                    return False

                # 发送中文文本
                cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0:
                    logger.info(f"多组模式ADBKeyboard输入成功: HWND={hwnd} -> 设备{device_id} -> 文字'{text}'")
                    return True
                else:
                    logger.debug(f"ADBKeyboard中文输入失败: {result.stderr}")
                    return False

        except Exception as e:
            logger.debug(f"ADBKeyboard中文输入异常: {e}")
            return False

    def _try_broadcast_input(self, hwnd: int, text: str, text_input_mode: str = '单组文本') -> bool:
        """尝试使用广播方式输入中文，严格分离单组和多组模式"""
        try:
            # 查找可用的ADB程序
            adb_path = self._find_adb_program()
            if not adb_path:
                logger.debug("未找到ADB程序")
                return False

            # 获取连接的设备
            devices = self._get_adb_devices(adb_path)
            if not devices:
                logger.debug("没有连接的ADB设备")
                return False

            # 根据文本输入模式选择不同的设备分配策略
            if text_input_mode == '单组文本':
                # 单组文字输入：每个窗口都给对应的设备发送相同的文字
                window_index = self._get_window_index_for_hwnd(hwnd)

                # 根据窗口索引选择对应的设备
                if window_index < len(devices):
                    device_id = devices[window_index]
                    logger.info(f"单组文字广播: 窗口{window_index} -> 设备{device_id}")
                else:
                    device_index = window_index % len(devices)
                    device_id = devices[device_index]
                    logger.info(f"单组文字广播: 窗口{window_index} -> 设备索引{device_index} -> 设备{device_id}")

                # 使用广播方式发送中文
                cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast', '-a', 'com.android.inputmethod.latin.SEND_TEXT', '--es', 'text', text]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0:
                    logger.info(f"✅ 单组模式广播输入成功: 窗口{window_index} -> 设备{device_id} <- '{text}'")
                    return True
                else:
                    logger.error(f"❌ 设备 {device_id} 广播输入失败: {result.stderr}")
                    return False
                for device_id in devices:
                    try:
                        # 使用广播方式发送中文
                        cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast', '-a', 'com.android.inputmethod.latin.SEND_TEXT', '--es', 'text', text]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                              creationflags=subprocess.CREATE_NO_WINDOW)

                        if result.returncode == 0:
                            logger.info(f"单组模式广播输入成功: 设备{device_id} <- '{text}'")
                            success_count += 1
                        else:
                            logger.debug(f"设备 {device_id} 广播输入失败: {result.stderr}")

                    except Exception as e:
                        logger.debug(f"设备 {device_id} 广播处理失败: {e}")
                        continue

                # 只要有一个设备成功就算成功
                return success_count > 0

            else:
                # 多组文字输入：根据窗口索引选择对应的设备
                window_index = self._get_window_index_for_hwnd(hwnd)

                # 根据窗口索引选择对应的设备
                if window_index < len(devices):
                    device_id = devices[window_index]
                    logger.info(f"多组文字广播: 窗口索引{window_index} -> 设备{device_id}")
                else:
                    device_index = window_index % len(devices)
                    device_id = devices[device_index]
                    logger.info(f"多组文字广播: 窗口索引{window_index} -> 设备索引{device_index} -> 设备{device_id}")

                # 使用广播方式发送中文
                cmd = [adb_path, '-s', device_id, 'shell', 'am', 'broadcast', '-a', 'com.android.inputmethod.latin.SEND_TEXT', '--es', 'text', text]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                      creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0:
                    logger.info(f"多组模式广播输入成功: {text} -> 设备{device_id}")
                    return True
                else:
                    logger.debug(f"广播中文输入失败: {result.stderr}")
                    return False

        except Exception as e:
            logger.debug(f"广播中文输入异常: {e}")
            return False

    def _check_adb_keyboard_installed(self, adb_path: str, device_id: str) -> bool:
        """检查ADBKeyboard是否已安装"""
        try:
            cmd = [adb_path, '-s', device_id, 'shell', 'pm', 'list', 'packages', 'com.android.adbkeyboard']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            return 'com.android.adbkeyboard' in result.stdout

        except Exception as e:
            logger.debug(f"检查ADBKeyboard安装状态失败: {e}")
            return False

    def _set_adb_keyboard_ime(self, adb_path: str, device_id: str) -> bool:
        """设置ADBKeyboard为当前输入法"""
        try:
            # 启用ADBKeyboard输入法
            cmd1 = [adb_path, '-s', device_id, 'shell', 'ime', 'enable', 'com.android.adbkeyboard/.AdbIME']
            result1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=10,
                                   creationflags=subprocess.CREATE_NO_WINDOW)

            # 设置为默认输入法
            cmd2 = [adb_path, '-s', device_id, 'shell', 'ime', 'set', 'com.android.adbkeyboard/.AdbIME']
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=10,
                                   creationflags=subprocess.CREATE_NO_WINDOW)

            return result1.returncode == 0 and result2.returncode == 0

        except Exception as e:
            logger.debug(f"设置ADBKeyboard输入法失败: {e}")
            return False

    def _get_ldplayer_console_path(self) -> Optional[str]:
        """获取雷电模拟器控制台程序路径"""
        if 'console_path' in self.console_cache:
            return self.console_cache['console_path']

        try:
            # 常见的雷电模拟器安装路径
            possible_paths = [
                r"C:\LDPlayer\LDPlayer4.0\ldconsole.exe",
                r"C:\LDPlayer\LDPlayer9\ldconsole.exe",
                r"D:\LDPlayer\LDPlayer4.0\ldconsole.exe",
                r"D:\LDPlayer\LDPlayer9\ldconsole.exe",
                r"E:\LDPlayer\LDPlayer4.0\ldconsole.exe",
                r"E:\LDPlayer\LDPlayer9\ldconsole.exe",
            ]

            # 检查每个可能的路径
            for path in possible_paths:
                if os.path.exists(path):
                    logger.debug(f"找到雷电控制台程序: {path}")
                    self.console_cache['console_path'] = path
                    return path

            # 尝试从注册表查找
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
                for i in range(winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, i)
                    if 'ldplayer' in subkey_name.lower():
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            console_path = os.path.join(install_location, "ldconsole.exe")
                            if os.path.exists(console_path):
                                logger.debug(f"从注册表找到雷电控制台: {console_path}")
                                self.console_cache['console_path'] = console_path
                                return console_path
                        except FileNotFoundError:
                            pass
                        finally:
                            winreg.CloseKey(subkey)
                winreg.CloseKey(key)
            except Exception as e:
                logger.debug(f"注册表查找失败: {e}")

            # 如果都找不到，尝试在PATH中查找
            for path in os.environ.get('PATH', '').split(os.pathsep):
                ldconsole_path = os.path.join(path, 'ldconsole.exe')
                if os.path.exists(ldconsole_path):
                    logger.debug(f"在PATH中找到雷电控制台: {ldconsole_path}")
                    self.console_cache['console_path'] = ldconsole_path
                    return ldconsole_path

        except Exception as e:
            logger.debug(f"查找雷电控制台程序失败: {e}")

        # 最后尝试通过进程搜索
        console_from_process = self._find_ldconsole_from_running_processes()
        if console_from_process:
            logger.debug(f"通过进程搜索找到雷电控制台: {console_from_process}")
            self.console_cache['console_path'] = console_from_process
            return console_from_process

        logger.warning("未找到雷电模拟器控制台程序")
        self.console_cache['console_path'] = None
        return None

    def _find_ldconsole_from_running_processes(self) -> Optional[str]:
        """通过搜索正在运行的进程来找到雷电控制台程序路径"""
        try:
            import psutil

            logger.debug("开始通过进程搜索雷电控制台程序")

            # 搜索雷电相关的进程名
            ldplayer_process_names = [
                'ldconsole.exe',
                'LDPlayer.exe',
                'dnplayer.exe',  # 雷电模拟器主程序
                'LDPlayerMainFrame.exe'
            ]

            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    proc_exe = proc_info.get('exe', '')

                    # 检查进程名是否匹配雷电相关程序
                    for ld_name in ldplayer_process_names:
                        if ld_name.lower() in proc_name:
                            if proc_exe and os.path.exists(proc_exe):
                                # 如果找到的是ldconsole.exe，直接返回
                                if 'ldconsole.exe' in proc_exe.lower():
                                    logger.debug(f"找到雷电控制台进程: {proc_name} -> {proc_exe}")
                                    return proc_exe

                                # 如果找到的是其他雷电程序，尝试在同目录找ldconsole.exe
                                proc_dir = os.path.dirname(proc_exe)
                                ldconsole_path = os.path.join(proc_dir, 'ldconsole.exe')
                                if os.path.exists(ldconsole_path):
                                    logger.debug(f"通过雷电进程目录找到控制台: {proc_name} -> {ldconsole_path}")
                                    return ldconsole_path

                    # 检查进程路径是否包含ldplayer或雷电相关关键词
                    if proc_exe and ('ldplayer' in proc_exe.lower() or '雷电' in proc_exe):
                        proc_dir = os.path.dirname(proc_exe)
                        ldconsole_path = os.path.join(proc_dir, 'ldconsole.exe')
                        if os.path.exists(ldconsole_path):
                            logger.debug(f"通过路径关键词找到控制台: {ldconsole_path}")
                            return ldconsole_path

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # 进程可能已经结束或无权限访问
                    continue
                except Exception as e:
                    logger.debug(f"检查进程时出错: {e}")
                    continue

            logger.debug("未通过进程搜索找到雷电控制台程序")
            return None

        except ImportError:
            logger.debug("psutil库不可用，无法通过进程搜索雷电控制台")
            return None
        except Exception as e:
            logger.debug(f"通过进程搜索雷电控制台时出错: {e}")
            return None

    def _get_ldplayer_instance_info(self, hwnd: int, console_path: str) -> Optional[Dict[str, Any]]:
        """获取雷电模拟器实例信息"""
        cache_key = f"instance_{hwnd}"
        if cache_key in self.console_cache:
            return self.console_cache[cache_key]

        try:
            import win32gui

            # 获取窗口标题
            window_title = win32gui.GetWindowText(hwnd)

            # 执行list命令获取实例列表
            result = subprocess.run([console_path, "list2"], capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode != 0:
                logger.debug(f"获取雷电实例列表失败: {result.stderr}")
                return None

            # 解析实例列表
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 4:
                        index = parts[0].strip()
                        name = parts[1].strip()
                        title = parts[2].strip()

                        # 通过窗口标题匹配实例
                        if title in window_title or name in window_title:
                            instance_info = {
                                'index': int(index),
                                'name': name,
                                'title': title,
                                'hwnd': hwnd
                            }
                            logger.debug(f"找到雷电实例: {instance_info}")
                            self.console_cache[cache_key] = instance_info
                            return instance_info

            # 如果没有找到匹配的实例，使用与窗口索引计算相同的逻辑
            # 确保模拟器实例分配与窗口索引分配一致
            instance_index = self._get_window_index_for_hwnd(hwnd)
            logger.debug(f"根据HWND {hwnd} 计算雷电实例索引 {instance_index}")

            default_instance = {
                'index': instance_index,
                'name': f'instance_{instance_index}',
                'title': window_title,
                'hwnd': hwnd
            }
            logger.info(f"=== 模拟器实例分配详情 ===")
            logger.info(f"HWND: {hwnd}")
            logger.info(f"已缓存的实例: {list(self.console_cache.keys())}")
            logger.info(f"分配的实例索引: {instance_index}")
            logger.info(f"实例信息: {default_instance}")
            logger.info(f"========================")

            self.console_cache[cache_key] = default_instance
            return default_instance

        except Exception as e:
            logger.debug(f"获取雷电实例信息失败: {e}")
            return None

    def _find_adb_program(self) -> Optional[str]:
        """智能查找ADB程序，优先使用先进ADB连接池"""
        if 'adb_path' in self.adb_cache:
            return self.adb_cache['adb_path']

        try:
            # 1. 优先使用先进ADB连接池
            from utils.advanced_adb_manager import get_advanced_adb_pool

            pool = get_advanced_adb_pool()
            healthy_devices = pool.get_healthy_devices()

            if healthy_devices:
                # 使用第一个健康设备的ADB路径
                adb_path = healthy_devices[0].adb_path
                logger.debug(f"从先进ADB连接池获取ADB路径: {adb_path}")
                self.adb_cache['adb_path'] = adb_path
                return adb_path

            logger.debug("先进ADB连接池无可用设备，回退到传统方法")

            # 2. 检查系统PATH中的adb
            result = subprocess.run(['where', 'adb'], capture_output=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                adb_path = result.stdout.strip().split('\n')[0]
                logger.debug(f"在系统PATH中找到ADB: {adb_path}")
                self.adb_cache['adb_path'] = adb_path
                return adb_path

        except Exception as e:
            logger.debug(f"ADB路径查找失败: {e}")

        # 2. 检查常见的模拟器ADB路径
        common_adb_paths = [
            # 雷电模拟器
            r"C:\LDPlayer\LDPlayer4.0\adb.exe",
            r"C:\Program Files\LDPlayer\LDPlayer4.0\adb.exe",
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\Program Files\LDPlayer\LDPlayer9\adb.exe",
            # MuMu模拟器
            r"C:\Program Files\Netease\MuMu\emulator\nemu\vmonitor\bin\adb_server.exe",
            # Android SDK
            r"C:\Android\Sdk\platform-tools\adb.exe",
            r"C:\android-sdk\platform-tools\adb.exe",
        ]

        import os
        for adb_path in common_adb_paths:
            if os.path.exists(adb_path):
                logger.debug(f"在常见路径中找到ADB: {adb_path}")
                self.adb_cache['adb_path'] = adb_path
                return adb_path

        # 3. 通过进程搜索ADB（智能方法）
        adb_from_process = self._find_adb_from_running_processes()
        if adb_from_process:
            logger.debug(f"通过进程搜索找到ADB: {adb_from_process}")
            self.adb_cache['adb_path'] = adb_from_process
            return adb_from_process

        logger.warning("未找到任何可用的ADB程序")
        logger.info("提示：请安装Android SDK Platform Tools或确保模拟器ADB程序可用")
        return None

    def _find_adb_from_running_processes(self) -> Optional[str]:
        """通过搜索正在运行的进程来找到ADB程序路径"""
        try:
            import psutil

            logger.debug("开始通过进程搜索ADB程序")

            # 搜索ADB相关的进程名
            adb_process_names = [
                'adb.exe',
                'adb_server.exe',
            ]

            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    proc_exe = proc_info.get('exe', '')

                    # 检查进程名是否匹配ADB
                    for adb_name in adb_process_names:
                        if adb_name.lower() in proc_name:
                            if proc_exe and os.path.exists(proc_exe):
                                logger.debug(f"找到ADB进程: {proc_name} -> {proc_exe}")
                                return proc_exe

                    # 检查进程路径是否包含adb
                    if proc_exe and 'adb' in proc_exe.lower() and os.path.exists(proc_exe):
                        logger.debug(f"通过路径找到ADB进程: {proc_exe}")
                        return proc_exe

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # 进程可能已经结束或无权限访问
                    continue
                except Exception as e:
                    logger.debug(f"检查进程时出错: {e}")
                    continue

            logger.debug("未通过进程搜索找到ADB程序")
            return None

        except ImportError:
            logger.debug("psutil库不可用，无法通过进程搜索ADB")
            return None
        except Exception as e:
            logger.debug(f"通过进程搜索ADB时出错: {e}")
            return None

    def _get_adb_devices(self, adb_path: str) -> list:
        """获取ADB连接的设备列表"""
        try:
            result = subprocess.run([adb_path, 'devices'], capture_output=True, text=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode != 0:
                logger.debug(f"获取ADB设备列表失败: {result.stderr}")
                return []

            devices = []
            lines = result.stdout.strip().split('\n')[1:]  # 跳过第一行标题
            for line in lines:
                if line.strip() and '\tdevice' in line:
                    device_id = line.split('\t')[0]
                    devices.append(device_id)

            logger.debug(f"找到ADB设备: {devices}")
            return devices

        except Exception as e:
            logger.debug(f"获取ADB设备列表失败: {e}")
            return []

    def _get_bound_window_hwnds(self):
        """获取当前绑定的窗口HWND列表"""
        try:
            # 尝试从环境变量获取当前执行的窗口HWND
            import os
            current_hwnd = os.environ.get('TARGET_WINDOW_HWND')
            if current_hwnd:
                logger.debug(f"从环境变量获取当前窗口HWND: {current_hwnd}")
                return [int(current_hwnd)]

            # 尝试从配置文件获取绑定窗口列表
            try:
                from main import load_config
                config = load_config()
                bound_windows = config.get('bound_windows', [])

                if bound_windows:
                    hwnds = []
                    for window_info in bound_windows:
                        hwnd = window_info.get('hwnd')
                        if hwnd:
                            hwnds.append(hwnd)

                    if hwnds:
                        logger.info(f"从配置获取绑定窗口HWND列表: {hwnds}")
                        return sorted(hwnds)  # 排序确保一致性

            except Exception as e:
                logger.debug(f"从配置获取绑定窗口失败: {e}")

            # 如果都失败了，返回空列表
            logger.warning("无法获取绑定窗口HWND列表")
            return []

        except Exception as e:
            logger.error(f"获取绑定窗口HWND列表失败: {e}")
            return []

    def _get_window_index_for_hwnd(self, hwnd: int) -> int:
        """根据窗口句柄获取窗口索引"""
        try:
            # 获取当前绑定的窗口HWND列表
            bound_hwnds = self._get_bound_window_hwnds()

            logger.info(f"=== 设备选择调试 ===")
            logger.info(f"传入的HWND: {hwnd}")
            logger.info(f"绑定窗口HWND列表: {bound_hwnds}")

            # 如果HWND在绑定列表中，直接返回其索引
            if hwnd in bound_hwnds:
                window_index = bound_hwnds.index(hwnd)
                logger.info(f"直接匹配: HWND {hwnd} -> 索引 {window_index}")
                logger.info(f"==================")
                return window_index

            # 如果不在绑定列表中，使用哈希算法分配
            if bound_hwnds:
                # 使用绑定窗口数量作为模数
                window_count = len(bound_hwnds)
                hwnd_hash = abs(hwnd)
                hash1 = (hwnd_hash * 17) % window_count
                hash2 = (hwnd_hash * 31) % window_count
                hash3 = (hwnd_hash * 47) % window_count
                hash4 = ((hwnd_hash >> 8) * 13) % window_count
                window_index = (hash1 + hash2 + hash3 + hash4) % window_count
            else:
                # 如果没有绑定窗口，默认使用3个窗口的哈希
                hwnd_hash = abs(hwnd)
                hash1 = (hwnd_hash * 17) % 3
                hash2 = (hwnd_hash * 31) % 3
                hash3 = (hwnd_hash * 47) % 3
                hash4 = ((hwnd_hash >> 8) * 13) % 3
                window_index = (hash1 + hash2 + hash3 + hash4) % 3

            logger.info(f"哈希计算: HWND {hwnd} -> 索引 {window_index}")
            logger.info(f"==================")
            return window_index

        except Exception as e:
            logger.error(f"窗口索引计算失败: {e}")
            return 0


# 全局实例
emulator_text_manager = EmulatorTextInputManager()
