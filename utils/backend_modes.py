# -*- coding: utf-8 -*-

"""
多后台模式管理器
提供多种后台实现方法，针对不同应用和模拟器优化兼容性
"""

import logging
import time
import ctypes
from typing import Optional, Dict, Any, Tuple
from enum import Enum

# 导入新的输入模拟模块
try:
    from utils.input_simulation import global_input_simulator_manager, InputSimulatorType
    INPUT_SIMULATION_AVAILABLE = True
except ImportError:
    INPUT_SIMULATION_AVAILABLE = False
    logging.warning("输入模拟模块不可用，将使用传统方法")

try:
    import win32gui
    import win32con
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

logger = logging.getLogger(__name__)

class BackendMode(Enum):
    """后台模式枚举"""
    STANDARD_SENDMESSAGE = "后台模式一（标准SendMessage）"
    STANDARD_POSTMESSAGE = "后台模式二（PostMessage）"
    LDPLAYER_OPTIMIZED = "后台模式三（雷电模拟器专用）"
    MUMU_OPTIMIZED = "后台模式四（MuMu模拟器专用）"  # 新增：MuMu模拟器专用模式
    ENHANCED_COMPATIBILITY = "后台模式五（增强兼容）"
    HYBRID_MODE = "后台模式六（混合模式）"
    EMULATOR_ENHANCED = "后台模式七（模拟器增强ADB）"  # 模拟器增强模式

class BackendModeManager:
    """后台模式管理器"""

    def __init__(self):
        self.current_mode = BackendMode.STANDARD_SENDMESSAGE
        self.window_type_cache = {}  # 缓存窗口类型检测结果
        self._forced_message_mode = None  # 强制消息模式：'sendmessage' 或 'postmessage'

    def set_forced_message_mode(self, mode: str):
        """
        设置强制消息模式

        Args:
            mode: 'sendmessage' 或 'postmessage' 或 None（自动）
        """
        self._forced_message_mode = mode
        if mode == 'sendmessage':
            self.current_mode = BackendMode.STANDARD_SENDMESSAGE
            logger.info("[后台模式] 强制使用 SendMessage")
        elif mode == 'postmessage':
            self.current_mode = BackendMode.STANDARD_POSTMESSAGE
            logger.info("[后台模式] 强制使用 PostMessage")
        else:
            logger.info("[后台模式] 自动选择消息模式")

    def set_mode(self, mode_name: str):
        """设置后台模式"""
        for mode in BackendMode:
            if mode.value == mode_name:
                self.current_mode = mode
                logger.info(f"切换到后台模式: {mode_name}")
                return
        logger.warning(f"未知的后台模式: {mode_name}")
    
    def get_mouse_clicker(self, hwnd: int) -> 'BaseMouseClicker':
        """根据当前模式获取鼠标点击器"""
        if self.current_mode == BackendMode.STANDARD_SENDMESSAGE:
            return SendMessageMouseClicker(hwnd)
        elif self.current_mode == BackendMode.STANDARD_POSTMESSAGE:
            return PostMessageMouseClicker(hwnd)
        elif self.current_mode == BackendMode.LDPLAYER_OPTIMIZED:
            return LDPlayerMouseClicker(hwnd)
        elif self.current_mode == BackendMode.ENHANCED_COMPATIBILITY:
            return EnhancedMouseClicker(hwnd)
        elif self.current_mode == BackendMode.HYBRID_MODE:
            return HybridMouseClicker(hwnd)
        else:
            return SendMessageMouseClicker(hwnd)  # 默认模式
    
    def get_keyboard_sender(self, hwnd: int) -> 'BaseKeyboardSender':
        """根据当前模式获取键盘发送器"""
        if self.current_mode == BackendMode.STANDARD_SENDMESSAGE:
            return SendMessageKeyboardSender(hwnd)
        elif self.current_mode == BackendMode.STANDARD_POSTMESSAGE:
            return PostMessageKeyboardSender(hwnd)
        elif self.current_mode == BackendMode.LDPLAYER_OPTIMIZED:
            return LDPlayerKeyboardSender(hwnd)
        elif self.current_mode == BackendMode.MUMU_OPTIMIZED:
            return MuMuKeyboardSender(hwnd)
        elif self.current_mode == BackendMode.ENHANCED_COMPATIBILITY:
            return EnhancedKeyboardSender(hwnd)
        elif self.current_mode == BackendMode.HYBRID_MODE:
            return HybridKeyboardSender(hwnd)
        elif self.current_mode == BackendMode.EMULATOR_ENHANCED:
            return EmulatorEnhancedKeyboardSender(hwnd)
        else:
            return SendMessageKeyboardSender(hwnd)  # 默认模式

    def get_input_simulator(self, hwnd: int, operation_mode: str = None, execution_mode: str = None):
        """
        获取新的输入模拟器（推荐使用）

        Args:
            hwnd: 窗口句柄
            operation_mode: 操作模式 ("standard_window", "emulator_window", "auto")
            execution_mode: 执行模式 ("foreground", "background")
        """
        if INPUT_SIMULATION_AVAILABLE:
            return global_input_simulator_manager.get_simulator(hwnd, operation_mode, execution_mode)
        else:
            # 回退到传统方法
            logger.warning("新输入模拟模块不可用，使用传统鼠标点击器")
            return self.get_mouse_clicker(hwnd)

    def set_global_operation_mode(self, operation_mode: str):
        """设置全局操作模式"""
        if INPUT_SIMULATION_AVAILABLE:
            global_input_simulator_manager.set_default_operation_mode(operation_mode)
            logger.info(f"全局操作模式已设置为: {operation_mode}")
        else:
            logger.warning("新输入模拟模块不可用，无法设置全局操作模式")

    def set_global_execution_mode(self, execution_mode: str):
        """设置全局执行模式"""
        if INPUT_SIMULATION_AVAILABLE:
            global_input_simulator_manager.set_default_execution_mode(execution_mode)
            logger.info(f"全局执行模式已设置为: {execution_mode}")
        else:
            logger.warning("新输入模拟模块不可用，无法设置全局执行模式")

    def detect_window_type(self, hwnd: int) -> str:
        """检测窗口类型"""
        if hwnd in self.window_type_cache:
            return self.window_type_cache[hwnd]
        
        try:
            class_name = win32gui.GetClassName(hwnd)
            window_title = win32gui.GetWindowText(hwnd)
            
            # 雷电模拟器
            if (class_name == "RenderWindow" or
                "TheRender" in window_title or
                "雷电" in window_title or
                "LDPlayer" in window_title):
                window_type = "ldplayer"

            # MuMu模拟器 - 使用专门的检测器
            elif self._is_mumu_window(hwnd, class_name, window_title):
                window_type = "mumu"
            
            # 游戏窗口
            elif (class_name in ["UnityWndClass", "CryENGINE", "Valve001"] or
                  any(keyword in window_title.lower() for keyword in ["game", "游戏"])):
                window_type = "game"
            
            # 办公软件
            elif any(keyword in window_title for keyword in ["Word", "Excel", "PowerPoint", "记事本"]):
                window_type = "office"
            
            # 浏览器
            elif any(keyword in window_title for keyword in ["Chrome", "Firefox", "Edge"]):
                window_type = "browser"
            
            else:
                window_type = "standard"
            
            # 缓存结果
            self.window_type_cache[hwnd] = window_type
            logger.debug(f"检测窗口类型: {window_type} (类名: {class_name}, 标题: {window_title})")
            return window_type
            
        except Exception as e:
            logger.error(f"检测窗口类型失败: {e}")
            return "standard"

    def _is_mumu_window(self, hwnd: int, class_name: str, window_title: str) -> bool:
        """专门检测MuMu模拟器窗口"""
        try:
            # 使用专门的模拟器检测器
            from utils.emulator_detector import EmulatorDetector
            detector = EmulatorDetector()
            is_emulator, emulator_type, _ = detector.detect_emulator_type(hwnd)
            return is_emulator and emulator_type == "mumu"
        except ImportError:
            # 回退到基本检测
            return ("MuMu" in window_title or
                    "MuMu模拟器" in window_title or
                    "MuMuNxDevice" in window_title or
                    "安卓设备" in window_title)
        except Exception:
            return False

class BaseMouseClicker:
    """鼠标点击器基类"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.user32 = ctypes.windll.user32

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """点击方法"""
        raise NotImplementedError

    def _get_button_messages(self, button: str) -> Tuple[int, int]:
        """获取按钮对应的消息"""
        if button == 'left':
            return win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP
        elif button == 'right':
            return win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP
        elif button == 'middle':
            return win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP
        else:
            raise ValueError(f"不支持的按钮类型: {button}")

class BaseKeyboardSender:
    """键盘发送器基类"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.user32 = ctypes.windll.user32

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键"""
        raise NotImplementedError

    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下"""
        raise NotImplementedError

    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放"""
        raise NotImplementedError

    def send_text(self, text: str) -> bool:
        """发送文本"""
        raise NotImplementedError

    def _make_lparam(self, scan_code: int, extended: bool, repeat_count: int = 1,
                     previous_state: bool = False, transition_state: bool = False) -> int:
        """构造lParam参数"""
        lparam = repeat_count & 0xFFFF  # 0-15位：重复次数
        lparam |= (scan_code & 0xFF) << 16  # 16-23位：扫描码
        if extended:
            lparam |= 1 << 24  # 24位：扩展键标志
        if previous_state:
            lparam |= 1 << 30  # 30位：之前的按键状态
        if transition_state:
            lparam |= 1 << 31  # 31位：转换状态
        return lparam

# 全局实例
backend_manager = BackendModeManager()

def get_backend_manager() -> BackendModeManager:
    """获取后台模式管理器实例"""
    return backend_manager

def set_backend_mode(mode_name: str):
    """设置全局后台模式"""
    backend_manager.set_mode(mode_name)

def get_current_backend_mode() -> str:
    """获取当前后台模式"""
    return backend_manager.current_mode.value

class SendMessageMouseClicker(BaseMouseClicker):
    """标准SendMessage鼠标点击器"""

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """使用SendMessage发送点击消息"""
        try:
            # 使用简化的坐标验证
            try:
                from main import mouse_move_fixer
                corrected_x, corrected_y = mouse_move_fixer.validate_client_coordinates(self.hwnd, x, y)
                logger.debug(f"SendMessage客户区坐标: ({x}, {y}) -> ({corrected_x}, {corrected_y})")
            except ImportError:
                corrected_x, corrected_y = x, y
                logger.debug("坐标修复器不可用，使用原始坐标")

            down_msg, up_msg = self._get_button_messages(button)
            lParam = win32api.MAKELONG(corrected_x, corrected_y)

            for i in range(clicks):
                # 发送按下消息
                win32gui.SendMessage(self.hwnd, down_msg, 0, lParam)
                time.sleep(0.01)

                # 发送释放消息
                win32gui.SendMessage(self.hwnd, up_msg, 0, lParam)

                if i < clicks - 1:
                    time.sleep(interval)

            logger.debug(f"SendMessage点击成功: ({corrected_x}, {corrected_y}), 按钮: {button}, 次数: {clicks}")
            return True

        except Exception as e:
            logger.error(f"SendMessage点击失败: {e}")
            return False

class PostMessageMouseClicker(BaseMouseClicker):
    """标准PostMessage鼠标点击器"""

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """使用PostMessage发送点击消息"""
        try:
            # 使用简化的坐标验证
            try:
                from main import mouse_move_fixer
                corrected_x, corrected_y = mouse_move_fixer.validate_client_coordinates(self.hwnd, x, y)
                logger.debug(f"PostMessage客户区坐标: ({x}, {y}) -> ({corrected_x}, {corrected_y})")
            except ImportError:
                corrected_x, corrected_y = x, y
                logger.debug("坐标修复器不可用，使用原始坐标")

            down_msg, up_msg = self._get_button_messages(button)
            lParam = win32api.MAKELONG(corrected_x, corrected_y)

            for i in range(clicks):
                # 发送按下消息
                win32gui.PostMessage(self.hwnd, down_msg, 0, lParam)
                time.sleep(0.01)

                # 发送释放消息
                win32gui.PostMessage(self.hwnd, up_msg, 0, lParam)

                if i < clicks - 1:
                    time.sleep(interval)

            logger.debug(f"PostMessage点击成功: ({corrected_x}, {corrected_y}), 按钮: {button}, 次数: {clicks}")
            return True

        except Exception as e:
            logger.error(f"PostMessage点击失败: {e}")
            return False

class SendMessageKeyboardSender(BaseKeyboardSender):
    """标准SendMessage键盘发送器"""

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """使用SendMessage发送按键"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            # 按下
            lparam_down = self._make_lparam(scan_code, extended, 1, False, False)
            win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)

            time.sleep(0.01)

            # 释放
            lparam_up = self._make_lparam(scan_code, extended, 1, True, True)
            win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam_up)

            logger.debug(f"SendMessage发送按键成功: VK={vk_code}, 扫描码={scan_code}")
            return True

        except Exception as e:
            logger.error(f"SendMessage发送按键失败: {e}")
            return False

    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
            lparam = self._make_lparam(scan_code, extended, 1, False, False)
            win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
            return True
        except Exception as e:
            logger.error(f"SendMessage发送按键按下失败: {e}")
            return False

    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
            lparam = self._make_lparam(scan_code, extended, 1, True, True)
            win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)
            return True
        except Exception as e:
            logger.error(f"SendMessage发送按键释放失败: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """使用SendMessage发送文本"""
        try:
            for char in text:
                char_code = ord(char)
                win32gui.SendMessage(self.hwnd, win32con.WM_CHAR, char_code, 0)
                time.sleep(0.01)

            logger.debug(f"SendMessage发送文本成功: {text}")
            return True

        except Exception as e:
            logger.error(f"SendMessage发送文本失败: {e}")
            return False

class PostMessageKeyboardSender(BaseKeyboardSender):
    """标准PostMessage键盘发送器"""

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """使用PostMessage发送按键"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            # 按下
            lparam_down = self._make_lparam(scan_code, extended, 1, False, False)
            win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)

            time.sleep(0.01)

            # 释放
            lparam_up = self._make_lparam(scan_code, extended, 1, True, True)
            win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam_up)

            logger.debug(f"PostMessage发送按键成功: VK={vk_code}, 扫描码={scan_code}")
            return True

        except Exception as e:
            logger.error(f"PostMessage发送按键失败: {e}")
            return False

    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
            lparam = self._make_lparam(scan_code, extended, 1, False, False)
            win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
            return True
        except Exception as e:
            logger.error(f"PostMessage发送按键按下失败: {e}")
            return False

    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
            lparam = self._make_lparam(scan_code, extended, 1, True, True)
            win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)
            return True
        except Exception as e:
            logger.error(f"PostMessage发送按键释放失败: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """使用PostMessage发送文本"""
        try:
            for char in text:
                char_code = ord(char)
                win32gui.PostMessage(self.hwnd, win32con.WM_CHAR, char_code, 0)
                time.sleep(0.01)

            logger.debug(f"PostMessage发送文本成功: {text}")
            return True

        except Exception as e:
            logger.error(f"PostMessage发送文本失败: {e}")
            return False

class LDPlayerKeyboardSender(PostMessageKeyboardSender):
    """雷电模拟器专用键盘发送器（继承PostMessage实现）"""

    def send_text(self, text: str) -> bool:
        """雷电模拟器专用文本发送方法"""
        try:
            for char in text:
                char_code = ord(char)

                # 对于ASCII字符，尝试使用虚拟键码方式
                if 32 <= char_code <= 126:  # 可打印ASCII字符
                    # 尝试转换为虚拟键码
                    vk_code = None
                    if 'a' <= char <= 'z':
                        vk_code = ord(char.upper())
                    elif 'A' <= char <= 'Z':
                        vk_code = ord(char)
                    elif '0' <= char <= '9':
                        vk_code = ord(char)

                    if vk_code:
                        # 使用按键方式发送
                        self.send_key(vk_code)
                    else:
                        # 回退到WM_CHAR方式
                        win32gui.PostMessage(self.hwnd, win32con.WM_CHAR, char_code, 0)
                else:
                    # 非ASCII字符使用WM_CHAR方式
                    win32gui.PostMessage(self.hwnd, win32con.WM_CHAR, char_code, 0)

                time.sleep(0.02)  # 稍微增加延迟以提高稳定性

            logger.debug(f"雷电模拟器发送文本成功: {text}")
            return True

        except Exception as e:
            logger.error(f"雷电模拟器发送文本失败: {e}")
            return False

class LDPlayerMouseClicker(BaseMouseClicker):
    """雷电模拟器专用鼠标点击器"""

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """雷电模拟器专用点击方法"""
        if button != 'left':
            logger.warning(f"雷电模拟器专用点击暂不支持 '{button}' 按钮")
            return False

        try:
            for i in range(clicks):
                self._send_ldplayer_click_sequence(x, y)

                if i < clicks - 1:
                    time.sleep(interval)

            logger.debug(f"雷电模拟器点击成功: ({x}, {y}), 次数: {clicks}")
            return True

        except Exception as e:
            logger.error(f"雷电模拟器点击失败: {e}")
            return False

    def _send_ldplayer_click_sequence(self, x: int, y: int):
        """发送雷电模拟器专用点击序列"""
        lParam = (y << 16) | x

        # 1. 鼠标移动到目标位置
        self.user32.PostMessageW(self.hwnd, win32con.WM_MOUSEMOVE, 0, lParam)

        # 2. 鼠标激活
        self.user32.PostMessageW(self.hwnd, win32con.WM_MOUSEACTIVATE, self.hwnd,
                                win32api.MAKELONG(1, win32con.WM_LBUTTONDOWN))

        # 3. 设置光标
        self.user32.PostMessageW(self.hwnd, win32con.WM_SETCURSOR, self.hwnd,
                                win32api.MAKELONG(1, win32con.WM_LBUTTONDOWN))

        # 4. 鼠标按下
        self.user32.PostMessageW(self.hwnd, win32con.WM_LBUTTONDOWN, 1, lParam)

        # 5. 鼠标移动（保持按下状态）
        self.user32.PostMessageW(self.hwnd, win32con.WM_MOUSEMOVE, 1, lParam)

        # 6. 鼠标释放
        self.user32.PostMessageW(self.hwnd, win32con.WM_LBUTTONUP, 0, lParam)


class MuMuMouseClicker(BaseMouseClicker):
    """MuMu模拟器专用鼠标点击器"""

    def __init__(self, hwnd: int):
        super().__init__(hwnd)
        try:
            from .mumu_input_simulator import get_mumu_input_simulator
            self.mumu_simulator = get_mumu_input_simulator()
        except ImportError:
            logger.error("无法导入MuMu输入模拟器")
            self.mumu_simulator = None

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """MuMu模拟器专用点击方法"""
        if not self.mumu_simulator:
            logger.warning("MuMu输入模拟器不可用，回退到标准方法")
            return super().click(x, y, button, clicks, interval)

        if button != 'left':
            logger.warning(f"MuMu模拟器专用点击暂不支持 '{button}' 按钮")
            return False

        try:
            for i in range(clicks):
                result = self.mumu_simulator.mouse_click(self.hwnd, x, y, button)

                if not result.success:
                    logger.error(f"MuMu模拟器点击失败: {result.message}")
                    return False

                if i < clicks - 1:
                    time.sleep(interval)

            logger.debug(f"MuMu模拟器点击成功: ({x}, {y}), 次数: {clicks}")
            return True

        except Exception as e:
            logger.error(f"MuMu模拟器点击失败: {e}")
            return False


class MuMuKeyboardSender(SendMessageKeyboardSender):
    """MuMu模拟器专用键盘发送器（继承SendMessage实现，测试显示MuMu需要SendMessage而不是PostMessage）"""

    def __init__(self, hwnd: int):
        super().__init__(hwnd)
        try:
            from .mumu_input_simulator import get_mumu_input_simulator
            self.mumu_simulator = get_mumu_input_simulator()
        except ImportError:
            logger.debug("无法导入MuMu输入模拟器，将使用SendMessage方法")
            self.mumu_simulator = None

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False, hold_duration: float = 0.0) -> bool:
        """MuMu模拟器专用按键发送方法 - 使用SendMessage方式（测试证明比PostMessage有效）"""
        try:
            # 使用SendMessage方式发送按键，测试证明这对MuMu模拟器有效
            # 这比ADB shell命令方式快得多
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            # 按下
            lparam_down = self._make_lparam(scan_code, extended, 1, False, False)
            win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)

            # 处理按键持续时间
            if hold_duration > 0:
                time.sleep(hold_duration)
            else:
                time.sleep(0.01)

            # 释放
            lparam_up = self._make_lparam(scan_code, extended, 1, True, True)
            win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam_up)

            logger.debug(f"MuMu模拟器SendMessage发送按键成功: VK={vk_code}, 扫描码={scan_code}")
            return True

        except Exception as e:
            logger.error(f"MuMu模拟器SendMessage按键发送失败: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """MuMu模拟器专用文本发送方法 - 使用ADB命令方式（保持原有实现）"""
        if not self.mumu_simulator:
            logger.warning("MuMu输入模拟器不可用，回退到标准方法")
            return SendMessageKeyboardSender(self.hwnd).send_text(text)

        try:
            result = self.mumu_simulator.input_text(self.hwnd, text)
            if result.success:
                logger.debug(f"MuMu模拟器ADB文本发送成功: {text}")
                return True
            else:
                logger.error(f"MuMu模拟器ADB文本发送失败: {result.message}")
                return False

        except Exception as e:
            logger.error(f"MuMu模拟器ADB文本发送失败: {e}")
            return False

    def _vk_code_to_key_command(self, vk_code: int) -> Optional[str]:
        """将VK码转换为MuMu支持的按键命令"""
        # VK码到MuMu按键命令的映射
        vk_mapping = {
            # 系统按键
            0x08: "back",        # VK_BACK -> 返回键
            0x24: "home",        # VK_HOME -> 主页键
            0x5D: "menu",        # VK_APPS -> 菜单键

            # 音量按键
            0xAF: "volume_up",   # VK_VOLUME_UP
            0xAE: "volume_down", # VK_VOLUME_DOWN
            0xAD: "volume_mute", # VK_VOLUME_MUTE
        }

        return vk_mapping.get(vk_code)


class EnhancedKeyboardSender(BaseKeyboardSender):
    """增强兼容性键盘发送器"""

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """尝试多种方法发送按键"""
        methods = [
            lambda: SendMessageKeyboardSender(self.hwnd).send_key(vk_code, scan_code, extended),
            lambda: PostMessageKeyboardSender(self.hwnd).send_key(vk_code, scan_code, extended)
        ]

        for method in methods:
            try:
                if method():
                    return True
            except:
                continue
        return False

    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """尝试多种方法发送按键按下"""
        methods = [
            lambda: SendMessageKeyboardSender(self.hwnd).send_key_down(vk_code, scan_code, extended),
            lambda: PostMessageKeyboardSender(self.hwnd).send_key_down(vk_code, scan_code, extended)
        ]

        for method in methods:
            try:
                if method():
                    return True
            except:
                continue
        return False

    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """尝试多种方法发送按键释放"""
        methods = [
            lambda: SendMessageKeyboardSender(self.hwnd).send_key_up(vk_code, scan_code, extended),
            lambda: PostMessageKeyboardSender(self.hwnd).send_key_up(vk_code, scan_code, extended)
        ]

        for method in methods:
            try:
                if method():
                    return True
            except:
                continue
        return False

    def send_text(self, text: str) -> bool:
        """尝试多种方法发送文本"""
        methods = [
            lambda: SendMessageKeyboardSender(self.hwnd).send_text(text),
            lambda: PostMessageKeyboardSender(self.hwnd).send_text(text)
        ]

        for method in methods:
            try:
                if method():
                    return True
            except:
                continue
        return False

class EnhancedMouseClicker(BaseMouseClicker):
    """增强兼容性鼠标点击器"""

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """增强兼容性点击方法"""
        methods = [
            self._try_sendmessage,
            self._try_postmessage,
            self._try_ldplayer_sequence
        ]

        for method in methods:
            try:
                if method(x, y, button, clicks, interval):
                    logger.debug(f"增强兼容性点击成功: 方法={method.__name__}")
                    return True
            except Exception as e:
                logger.debug(f"增强兼容性点击方法失败: {method.__name__}, 错误: {e}")
                continue

        logger.error("所有增强兼容性点击方法都失败了")
        return False

    def _try_sendmessage(self, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
        """尝试SendMessage方法"""
        clicker = SendMessageMouseClicker(self.hwnd)
        return clicker.click(x, y, button, clicks, interval)

    def _try_postmessage(self, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
        """尝试PostMessage方法"""
        clicker = PostMessageMouseClicker(self.hwnd)
        return clicker.click(x, y, button, clicks, interval)

    def _try_ldplayer_sequence(self, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
        """尝试雷电模拟器序列方法"""
        clicker = LDPlayerMouseClicker(self.hwnd)
        return clicker.click(x, y, button, clicks, interval)

class HybridMouseClicker(BaseMouseClicker):
    """混合模式鼠标点击器"""

    def __init__(self, hwnd: int):
        super().__init__(hwnd)
        self.manager = backend_manager

    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """根据窗口类型自动选择最佳点击方法"""
        window_type = self.manager.detect_window_type(self.hwnd)

        if window_type == "ldplayer":
            clicker = LDPlayerMouseClicker(self.hwnd)
        elif window_type == "mumu":
            clicker = MuMuMouseClicker(self.hwnd)
        elif window_type == "game":
            clicker = PostMessageMouseClicker(self.hwnd)
        else:
            clicker = SendMessageMouseClicker(self.hwnd)

        logger.debug(f"混合模式选择点击器: {clicker.__class__.__name__} (窗口类型: {window_type})")
        return clicker.click(x, y, button, clicks, interval)

class HybridKeyboardSender(BaseKeyboardSender):
    """混合模式键盘发送器"""

    def __init__(self, hwnd: int):
        super().__init__(hwnd)
        self.manager = backend_manager
        self._emulator_manager = None

    def _get_emulator_manager(self):
        """延迟加载模拟器管理器"""
        if self._emulator_manager is None:
            try:
                from utils.emulator_text_input_new import emulator_text_manager
                self._emulator_manager = emulator_text_manager
            except ImportError:
                self._emulator_manager = False
        return self._emulator_manager

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """根据窗口类型自动选择最佳键盘发送方法"""
        window_type = self.manager.detect_window_type(self.hwnd)

        if window_type == "mumu":
            sender = MuMuKeyboardSender(self.hwnd)
        elif window_type == "ldplayer":
            sender = PostMessageKeyboardSender(self.hwnd)
        elif window_type == "game":
            sender = PostMessageKeyboardSender(self.hwnd)
        else:
            sender = SendMessageKeyboardSender(self.hwnd)

        return sender.send_key(vk_code, scan_code, extended)

    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下消息"""
        window_type = self.manager.detect_window_type(self.hwnd)

        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            if window_type == "ldplayer":
                # 对模拟器使用PostMessage
                lparam = self._make_lparam(scan_code, extended, 1, False, False)
                win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
            else:
                # 对普通应用使用SendMessage
                lparam = self._make_lparam(scan_code, extended, 1, False, False)
                win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)

            logger.debug(f"发送按键按下: VK={vk_code}, 窗口类型={window_type}")
            return True

        except Exception as e:
            logger.error(f"发送按键按下失败: {e}")
            return False

    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放消息"""
        window_type = self.manager.detect_window_type(self.hwnd)

        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            if window_type == "ldplayer":
                # 对模拟器使用PostMessage
                lparam = self._make_lparam(scan_code, extended, 1, True, True)
                win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)
            else:
                # 对普通应用使用SendMessage
                lparam = self._make_lparam(scan_code, extended, 1, True, True)
                win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)

            logger.debug(f"发送按键释放: VK={vk_code}, 窗口类型={window_type}")
            return True

        except Exception as e:
            logger.error(f"发送按键释放失败: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """根据窗口类型自动选择最佳文本发送方法"""
        window_type = self.manager.detect_window_type(self.hwnd)

        # 对于模拟器窗口，优先尝试ADB Shell Input
        emulator_manager = self._get_emulator_manager()
        if emulator_manager and window_type in ["ldplayer", "mumu"]:
            # 检测是否为模拟器窗口
            if emulator_manager.is_emulator_window(self.hwnd):
                logger.debug(f"检测到模拟器窗口，尝试ADB Shell Input: '{text}'")
                if emulator_manager.try_adb_shell_input(self.hwnd, text):
                    logger.info(f"ADB Shell Input成功发送文本: '{text}'")
                    return True
                else:
                    logger.debug("ADB Shell Input失败，回退到传统方法")

        # 回退到传统方法
        if window_type == "mumu":
            sender = MuMuKeyboardSender(self.hwnd)
        elif window_type == "ldplayer":
            sender = PostMessageKeyboardSender(self.hwnd)
        elif window_type == "game":
            sender = PostMessageKeyboardSender(self.hwnd)
        else:
            sender = SendMessageKeyboardSender(self.hwnd)

        return sender.send_text(text)


class EmulatorEnhancedKeyboardSender(BaseKeyboardSender):
    """模拟器增强键盘发送器 - 集成ADB Shell Input"""

    def __init__(self, hwnd: int):
        super().__init__(hwnd)
        self._emulator_manager = None
        self._fallback_sender = None

    def _get_emulator_manager(self):
        """延迟加载模拟器管理器"""
        if self._emulator_manager is None:
            try:
                from utils.emulator_text_input_new import emulator_text_manager
                self._emulator_manager = emulator_text_manager
            except ImportError:
                logger.warning("无法导入模拟器文本输入管理器")
                self._emulator_manager = False
        return self._emulator_manager

    def _get_fallback_sender(self):
        """获取回退发送器"""
        if self._fallback_sender is None:
            self._fallback_sender = PostMessageKeyboardSender(self.hwnd)
        return self._fallback_sender

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键 - 使用回退方法"""
        return self._get_fallback_sender().send_key(vk_code, scan_code, extended)

    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下 - 使用回退方法"""
        return self._get_fallback_sender().send_key_down(vk_code, scan_code, extended)

    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放 - 使用回退方法"""
        return self._get_fallback_sender().send_key_up(vk_code, scan_code, extended)

    def send_text(self, text: str) -> bool:
        """发送文本 - 优先使用ADB Shell Input"""
        emulator_manager = self._get_emulator_manager()

        # 尝试ADB Shell Input
        if emulator_manager:
            if emulator_manager.is_emulator_window(self.hwnd):
                logger.debug(f"模拟器增强发送器：尝试ADB Shell Input: '{text}'")
                if emulator_manager.try_adb_shell_input(self.hwnd, text):
                    logger.info(f"模拟器增强发送器：ADB Shell Input成功: '{text}'")
                    return True
                else:
                    logger.debug("模拟器增强发送器：ADB Shell Input失败，使用回退方法")

        # 回退到传统方法
        return self._get_fallback_sender().send_text(text)
