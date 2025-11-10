"""
普通窗口输入模拟模块
针对普通应用程序窗口的键盘鼠标模拟
"""

import time
import win32gui
import win32con
import win32api
from utils.interception_driver import get_driver
from typing import Optional, List
from .base import BaseInputSimulator


class StandardWindowInputSimulator(BaseInputSimulator):
    """普通窗口输入模拟器"""
    
    def __init__(self, hwnd: int, use_foreground: bool = False):
        """
        初始化普通窗口输入模拟器

        Args:
            hwnd: 目标窗口句柄
            use_foreground: 是否使用前台模式（驱动级）
        """
        super().__init__(hwnd)
        self.use_foreground = use_foreground
        self.driver = get_driver() if use_foreground else None
        
    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """鼠标点击"""
        try:
            if self.use_foreground:
                return self._foreground_click(x, y, button, clicks, interval)
            else:
                return self._background_click(x, y, button, clicks, interval)
        except Exception as e:
            self.logger.error(f"普通窗口点击失败: {e}")
            return False
    
    def _foreground_click(self, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
        """前台模式点击"""
        # 注意：x, y 应该是屏幕坐标（已经转换过的）
        try:
            if not self.driver:
                self.driver = get_driver()

            # 验证坐标是否在屏幕范围内
            screen_width, screen_height = self.driver.get_screen_size()
            if x < 0 or y < 0 or x > screen_width or y > screen_height:
                self.logger.error(f"坐标超出屏幕范围: ({x}, {y}), 屏幕大小: {screen_width}x{screen_height}")
                return False

            self.logger.info(f"[新模拟器前台点击] 屏幕坐标: ({x}, {y}), 按钮: {button}")

            # 使用驱动点击
            return self.driver.click_mouse(x, y, clicks=clicks, interval=interval, button=button)
        except Exception as e:
            self.logger.error(f"前台点击失败: {e}")
            return False
    
    def _background_click(self, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
        """后台模式点击"""
        button_map = {
            'left': (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
            'right': (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
            'middle': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
        }
        
        if button not in button_map:
            self.logger.error(f"不支持的鼠标按钮: {button}")
            return False
        
        down_msg, up_msg = button_map[button]
        lparam = win32api.MAKELONG(x, y)
        
        for i in range(clicks):
            # 发送按下消息
            win32gui.SendMessage(self.hwnd, down_msg, 0, lparam)
            time.sleep(0.01)  # 短暂延迟
            # 发送释放消息
            win32gui.SendMessage(self.hwnd, up_msg, 0, lparam)
            
            if i < clicks - 1:
                time.sleep(interval)
        
        return True
    
    def double_click(self, x: int, y: int, button: str = 'left') -> bool:
        """鼠标双击"""
        try:
            if self.use_foreground:
                screen_x, screen_y = self._client_to_screen(x, y)
                if screen_x is None or screen_y is None:
                    return False
                if not self.driver:
                    self.driver = get_driver()
                self.driver.click_mouse(screen_x, screen_y, clicks=2, button=button)
                return True
            else:
                # 后台模式双击
                return self.click(x, y, button, clicks=2, interval=0.1)
        except Exception as e:
            self.logger.error(f"普通窗口双击失败: {e}")
            return False
    
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, 
             duration: float = 1.0, button: str = 'left') -> bool:
        """鼠标拖拽"""
        try:
            if self.use_foreground:
                start_screen_x, start_screen_y = self._client_to_screen(start_x, start_y)
                end_screen_x, end_screen_y = self._client_to_screen(end_x, end_y)
                if None in (start_screen_x, start_screen_y, end_screen_x, end_screen_y):
                    return False
                
                if not self.driver:
                    self.driver = get_driver()
                self.driver.drag_mouse(start_screen_x, start_screen_y, end_screen_x, end_screen_y,
                                     button=button, duration=duration)
                return True
            else:
                # 后台模式拖拽
                return self._background_drag(start_x, start_y, end_x, end_y, duration, button)
        except Exception as e:
            self.logger.error(f"普通窗口拖拽失败: {e}")
            return False
    
    def _background_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, 
                        duration: float, button: str) -> bool:
        """后台模式拖拽"""
        button_map = {
            'left': (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
            'right': (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
            'middle': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
        }
        
        if button not in button_map:
            return False
        
        down_msg, up_msg = button_map[button]
        
        # 按下鼠标
        start_lparam = win32api.MAKELONG(start_x, start_y)
        win32gui.SendMessage(self.hwnd, down_msg, 0, start_lparam)
        
        # 移动到结束位置
        steps = max(10, int(duration * 30))  # 根据持续时间计算步数
        for i in range(steps + 1):
            progress = i / steps
            current_x = int(start_x + (end_x - start_x) * progress)
            current_y = int(start_y + (end_y - start_y) * progress)
            current_lparam = win32api.MAKELONG(current_x, current_y)
            win32gui.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, current_lparam)
            time.sleep(duration / steps)
        
        # 释放鼠标
        end_lparam = win32api.MAKELONG(end_x, end_y)
        win32gui.SendMessage(self.hwnd, up_msg, 0, end_lparam)
        
        return True
    
    def scroll(self, x: int, y: int, delta: int) -> bool:
        """鼠标滚轮"""
        try:
            if self.use_foreground:
                screen_x, screen_y = self._client_to_screen(x, y)
                if screen_x is None or screen_y is None:
                    return False
                if not self.driver:
                    self.driver = get_driver()
                direction = 'up' if delta > 0 else 'down'
                self.driver.scroll_mouse(direction, abs(delta), screen_x, screen_y)
                return True
            else:
                # 后台模式滚轮
                lparam = win32api.MAKELONG(x, y)
                wparam = win32api.MAKELONG(0, delta * 120)  # 滚轮增量通常是120的倍数
                win32gui.SendMessage(self.hwnd, win32con.WM_MOUSEWHEEL, wparam, lparam)
                return True
        except Exception as e:
            self.logger.error(f"普通窗口滚轮失败: {e}")
            return False
    
    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键"""
        try:
            if self.use_foreground:
                # 前台模式使用驱动
                if not self.driver:
                    self.driver = get_driver()
                key_name = self._vk_to_key_name(vk_code)
                if key_name:
                    return self.driver.press_key(key_name)
                return False
            else:
                # 后台模式发送按键
                return self._send_key_background(vk_code, scan_code, extended)
        except Exception as e:
            self.logger.error(f"普通窗口发送按键失败: {e}")
            return False
    
    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
            
            lparam = self._make_lparam(scan_code, extended, 1, False, False)
            
            if self.use_foreground:
                # 前台模式
                if not self.driver:
                    self.driver = get_driver()
                key_name = self._vk_to_key_name(vk_code)
                if key_name:
                    return self.driver.key_down(key_name)
                return False
            else:
                # 后台模式
                win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
                return True
        except Exception as e:
            self.logger.error(f"普通窗口发送按键按下失败: {e}")
            return False
    
    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)
            
            lparam = self._make_lparam(scan_code, extended, 1, True, True)
            
            if self.use_foreground:
                # 前台模式
                if not self.driver:
                    self.driver = get_driver()
                key_name = self._vk_to_key_name(vk_code)
                if key_name:
                    return self.driver.key_up(key_name)
                return False
            else:
                # 后台模式
                win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)
                return True
        except Exception as e:
            self.logger.error(f"普通窗口发送按键释放失败: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """发送文本"""
        try:
            if self.use_foreground:
                # 前台模式使用驱动
                if not self.driver:
                    self.driver = get_driver()
                return self.driver.type_text(text)
            else:
                # 后台模式逐字符发送 - 改进版本
                self.logger.info(f"[普通窗口后台文本输入] 开始发送文本: '{text}' (长度: {len(text)})")

                # 检测是否包含中文字符
                has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)

                # 寻找并定位实际的输入框子控件
                self.logger.info("=== 寻找并定位实际的输入框子控件 ===")
                self.logger.info("输入框是单独的子控件，需要找到具体的输入框控件而不是主窗口")
                return self._find_and_send_to_input_control(text)

                self.logger.info("[普通窗口后台文本输入] 文本发送完成")
                return True
        except Exception as e:
            self.logger.error(f"普通窗口发送文本失败: {e}")
            return False

    def send_key_combination(self, keys: list, hold_duration: float = 0.1) -> bool:
        """发送组合键"""
        try:
            if self.use_foreground:
                # 前台模式使用驱动
                if not self.driver:
                    self.driver = get_driver()
                key_names = [self._vk_to_key_name(key) for key in keys if self._vk_to_key_name(key)]
                if len(key_names) == len(keys):
                    return self.driver.hotkey(*key_names)
                return False
            else:
                # 后台模式按顺序按下所有键
                for key in keys:
                    self.send_key_down(key)

                time.sleep(hold_duration)

                # 按相反顺序释放所有键
                for key in reversed(keys):
                    self.send_key_up(key)

                return True
        except Exception as e:
            self.logger.error(f"普通窗口发送组合键失败: {e}")
            return False

    def _client_to_screen(self, x: int, y: int) -> tuple:
        """将客户区坐标转换为屏幕坐标"""
        try:
            point = win32gui.ClientToScreen(self.hwnd, (x, y))
            return point[0], point[1]
        except Exception as e:
            self.logger.error(f"坐标转换失败: {e}")
            return None, None

    def _send_key_background(self, vk_code: int, scan_code: int, extended: bool) -> bool:
        """后台模式发送完整按键（按下+释放）"""
        success = True
        success &= self.send_key_down(vk_code, scan_code, extended)
        time.sleep(0.01)  # 短暂延迟
        success &= self.send_key_up(vk_code, scan_code, extended)
        return success

    def _find_and_send_to_input_control(self, text: str) -> bool:
        """寻找并定位实际的输入框子控件"""
        try:
            self.logger.info(f"[寻找输入框] 开始寻找实际的输入框子控件: '{text}' (长度: {len(text)})")

            # 方法1：寻找当前有焦点的子控件
            focused_control = self._find_focused_child_control()
            if focused_control:
                self.logger.info(f"[寻找输入框] 找到有焦点的子控件: {focused_control}")
                success = self._send_text_to_specific_control(focused_control, text)
                if success:
                    return True

            # 方法2：枚举所有可能的输入框子控件
            input_controls = self._find_all_input_controls()
            if input_controls:
                self.logger.info(f"[寻找输入框] 找到 {len(input_controls)} 个可能的输入控件")

                for control_hwnd, class_name, window_text in input_controls:
                    self.logger.debug(f"[寻找输入框] 尝试控件 {control_hwnd} ({class_name}) 文本:'{window_text}'")
                    success = self._send_text_to_specific_control(control_hwnd, text)
                    if success:
                        self.logger.info(f"[寻找输入框] 成功发送到控件 {control_hwnd} ({class_name})")
                        return True

            self.logger.warning("[寻找输入框] 未找到有效的输入框控件")
            return False

        except Exception as e:
            self.logger.error(f"[寻找输入框] 失败: {e}")
            return False

    def _try_direct_setwindowtext(self, text: str) -> bool:
        """直接使用SetWindowText"""
        try:
            import win32gui

            self.logger.debug("[直接SetWindowText] 开始尝试")

            # 获取当前文本
            try:
                current_text = win32gui.GetWindowText(self.hwnd)
                self.logger.debug(f"[直接SetWindowText] 当前文本: '{current_text}'")
            except:
                current_text = ""

            # 设置新文本
            result = win32gui.SetWindowText(self.hwnd, text)

            if result:
                self.logger.info(f"[直接SetWindowText] 成功设置文本: '{text}'")
                return True
            else:
                self.logger.debug("[直接SetWindowText] SetWindowText调用失败")
                return False

        except Exception as e:
            self.logger.debug(f"[直接SetWindowText] 失败: {e}")
            return False

    def _try_em_replacesel(self, text: str) -> bool:
        """使用EM_REPLACESEL消息"""
        try:
            import win32gui
            import ctypes

            self.logger.debug("[EM_REPLACESEL] 开始尝试")

            # EM_REPLACESEL消息常量
            EM_REPLACESEL = 0x00C2

            # 尝试Unicode版本
            try:
                text_buffer = ctypes.create_unicode_buffer(text)
                result = win32gui.SendMessage(self.hwnd, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))

                if result == 0:
                    self.logger.info(f"[EM_REPLACESEL] 成功替换文本: '{text}'")
                    return True
            except Exception as unicode_error:
                self.logger.debug(f"[EM_REPLACESEL] Unicode版本失败: {unicode_error}")

            # 尝试ANSI版本
            try:
                text_buffer = ctypes.create_string_buffer(text.encode('utf-8'))
                result = win32gui.SendMessage(self.hwnd, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))

                if result == 0:
                    self.logger.info(f"[EM_REPLACESEL] ANSI版本成功: '{text}'")
                    return True
            except Exception as ansi_error:
                self.logger.debug(f"[EM_REPLACESEL] ANSI版本失败: {ansi_error}")

            return False

        except Exception as e:
            self.logger.debug(f"[EM_REPLACESEL] 失败: {e}")
            return False

    def _try_children_setwindowtext(self, text: str) -> bool:
        """对子控件使用SetWindowText"""
        try:
            import win32gui

            self.logger.debug("[子控件SetWindowText] 开始尝试")

            # 枚举子窗口
            child_windows = []

            def enum_child_proc(hwnd_child, lparam):
                try:
                    class_name = win32gui.GetClassName(hwnd_child)
                    input_classes = ['Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W']
                    if class_name in input_classes:
                        child_windows.append((hwnd_child, class_name))
                except:
                    pass
                return True

            try:
                win32gui.EnumChildWindows(self.hwnd, enum_child_proc, 0)
            except:
                pass

            self.logger.debug(f"[子控件SetWindowText] 找到 {len(child_windows)} 个控件")

            # 尝试设置每个子控件
            for child_hwnd, class_name in child_windows:
                try:
                    result = win32gui.SetWindowText(child_hwnd, text)
                    if result:
                        self.logger.info(f"[子控件SetWindowText] 成功设置子控件 {child_hwnd} ({class_name})")
                        return True
                except Exception as child_error:
                    self.logger.debug(f"[子控件SetWindowText] 子控件 {child_hwnd} 失败: {child_error}")
                    continue

            return False

        except Exception as e:
            self.logger.debug(f"[子控件SetWindowText] 失败: {e}")
            return False

    def _try_wm_settext(self, text: str) -> bool:
        """使用WM_SETTEXT消息"""
        try:
            import win32gui
            import win32con
            import ctypes

            self.logger.debug("[WM_SETTEXT] 开始尝试")

            # 创建Unicode文本缓冲区
            text_buffer = ctypes.create_unicode_buffer(text)

            # 发送WM_SETTEXT消息
            result = win32gui.SendMessage(self.hwnd, win32con.WM_SETTEXT, 0, ctypes.addressof(text_buffer))

            if result:
                self.logger.info(f"[WM_SETTEXT] 成功发送消息: '{text}'")
                return True
            else:
                self.logger.debug("[WM_SETTEXT] 消息发送失败")
                return False

        except Exception as e:
            self.logger.debug(f"[WM_SETTEXT] 失败: {e}")
            return False

    def _try_deep_search_controls(self, text: str) -> bool:
        """深度搜索所有可能的输入控件"""
        try:
            import win32gui
            import win32con
            import ctypes

            self.logger.debug("[深度搜索] 开始深度搜索输入控件")

            # 收集所有可能的控件
            all_controls = []

            def enum_all_proc(hwnd_child, lparam):
                try:
                    class_name = win32gui.GetClassName(hwnd_child)
                    window_text = win32gui.GetWindowText(hwnd_child)

                    # 扩展的控件类型列表
                    possible_classes = [
                        'Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W',
                        'Static', 'Button', 'ComboBox', 'ListBox',
                        'DirectUIHWND', 'Internet Explorer_Server',
                        'UnityWndClass', 'UnrealWindow', 'GameOverlayUI'
                    ]

                    if class_name in possible_classes or window_text:
                        all_controls.append((hwnd_child, class_name, window_text))

                except:
                    pass
                return True

            try:
                win32gui.EnumChildWindows(self.hwnd, enum_all_proc, 0)
            except:
                pass

            self.logger.debug(f"[深度搜索] 找到 {len(all_controls)} 个可能的控件")

            # 按优先级排序
            def control_priority(control):
                hwnd_child, class_name, window_text = control
                if 'Edit' in class_name or 'RichEdit' in class_name:
                    return 0
                elif class_name in ['Static', 'Button']:
                    return 1
                else:
                    return 2

            all_controls.sort(key=control_priority)

            # 尝试每个控件
            for hwnd_child, class_name, window_text in all_controls:
                try:
                    self.logger.debug(f"[深度搜索] 尝试控件 {hwnd_child} ({class_name}) 文本:'{window_text}'")

                    # 尝试多种方法
                    methods = [
                        self._try_setwindowtext_on_control,
                        self._try_em_replacesel_on_control,
                        self._try_wm_settext_on_control,
                        self._try_em_setsel_replacesel_on_control
                    ]

                    for method in methods:
                        try:
                            if method(hwnd_child, class_name, text):
                                return True
                        except:
                            continue

                except Exception as control_error:
                    self.logger.debug(f"[深度搜索] 控件 {hwnd_child} 处理失败: {control_error}")
                    continue

            self.logger.debug("[深度搜索] 所有控件都尝试失败")
            return False

        except Exception as e:
            self.logger.debug(f"[深度搜索] 失败: {e}")
            return False

    def _try_setwindowtext_on_control(self, hwnd_child: int, class_name: str, text: str) -> bool:
        """在特定控件上尝试SetWindowText"""
        try:
            import win32gui

            old_text = win32gui.GetWindowText(hwnd_child)
            result = win32gui.SetWindowText(hwnd_child, text)

            if result:
                new_text = win32gui.GetWindowText(hwnd_child)
                if new_text == text and new_text != old_text:
                    self.logger.info(f"[深度搜索] SetWindowText成功: 控件{hwnd_child} ({class_name})")
                    return True
            return False
        except:
            return False

    def _try_em_replacesel_on_control(self, hwnd_child: int, class_name: str, text: str) -> bool:
        """在特定控件上尝试EM_REPLACESEL"""
        try:
            import win32gui
            import ctypes

            EM_REPLACESEL = 0x00C2
            text_buffer = ctypes.create_unicode_buffer(text)
            result = win32gui.SendMessage(hwnd_child, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))

            if result == 0:
                self.logger.info(f"[深度搜索] EM_REPLACESEL成功: 控件{hwnd_child} ({class_name})")
                return True
            return False
        except:
            return False

    def _try_wm_settext_on_control(self, hwnd_child: int, class_name: str, text: str) -> bool:
        """在特定控件上尝试WM_SETTEXT"""
        try:
            import win32gui
            import win32con
            import ctypes

            text_buffer = ctypes.create_unicode_buffer(text)
            result = win32gui.SendMessage(hwnd_child, win32con.WM_SETTEXT, 0, ctypes.addressof(text_buffer))

            if result:
                self.logger.info(f"[深度搜索] WM_SETTEXT成功: 控件{hwnd_child} ({class_name})")
                return True
            return False
        except:
            return False

    def _try_em_setsel_replacesel_on_control(self, hwnd_child: int, class_name: str, text: str) -> bool:
        """在特定控件上尝试EM_SETSEL+EM_REPLACESEL组合"""
        try:
            import win32gui
            import ctypes

            EM_SETSEL = 0x00B1
            EM_REPLACESEL = 0x00C2

            # 选择所有文本
            win32gui.SendMessage(hwnd_child, EM_SETSEL, 0, -1)

            # 替换选中文本
            text_buffer = ctypes.create_unicode_buffer(text)
            result = win32gui.SendMessage(hwnd_child, EM_REPLACESEL, 1, ctypes.addressof(text_buffer))

            if result == 0:
                self.logger.info(f"[深度搜索] EM_SETSEL+EM_REPLACESEL成功: 控件{hwnd_child} ({class_name})")
                return True
            return False
        except:
            return False

    def _try_autohotkey_controlsend(self, text: str) -> bool:
        """尝试AutoHotkey的ControlSend方法"""
        try:
            self.logger.info(f"[AutoHotkey方法] 开始发送文本: '{text}' (长度: {len(text)})")

            # 策略1：发送到子控件
            success = self._ahk_send_to_child_controls(text)
            if success:
                return True

            # 策略2：特殊消息发送
            success = self._ahk_send_with_special_messages(text)
            if success:
                return True

            self.logger.warning("[AutoHotkey方法] 所有策略都失败")
            return False

        except Exception as e:
            self.logger.error(f"[AutoHotkey方法] 失败: {e}")
            return False

    def _ahk_send_to_child_controls(self, text: str) -> bool:
        """发送到子控件"""
        try:
            import win32gui
            import win32con

            self.logger.debug("[AHK子控件] 开始尝试")

            # 枚举子窗口
            child_windows = []

            def enum_child_proc(hwnd_child, lparam):
                try:
                    class_name = win32gui.GetClassName(hwnd_child)
                    # 寻找输入控件
                    input_classes = ['Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W']
                    if class_name in input_classes:
                        child_windows.append(hwnd_child)
                except:
                    pass
                return True

            try:
                win32gui.EnumChildWindows(self.hwnd, enum_child_proc, 0)
            except:
                pass

            self.logger.debug(f"[AHK子控件] 找到 {len(child_windows)} 个可能的输入控件")

            # 尝试向子控件发送
            for child_hwnd in child_windows:
                try:
                    self.logger.debug(f"[AHK子控件] 尝试向子控件 {child_hwnd} 发送文本")

                    for char in text:
                        win32gui.SendMessage(child_hwnd, win32con.WM_CHAR, ord(char), 0)

                    self.logger.info(f"[AHK子控件] 成功发送到子控件 {child_hwnd}")
                    return True

                except Exception as child_error:
                    self.logger.debug(f"[AHK子控件] 子控件 {child_hwnd} 发送失败: {child_error}")
                    continue

            return False

        except Exception as e:
            self.logger.debug(f"[AHK子控件] 失败: {e}")
            return False

    def _ahk_send_with_special_messages(self, text: str) -> bool:
        """特殊消息发送方式"""
        try:
            import win32gui
            import win32con
            import win32api

            self.logger.debug("[AHK特殊消息] 开始尝试")

            for char in text:
                char_code = ord(char)

                # AutoHotkey的特殊处理：完整的按键序列
                try:
                    vk_code = win32api.VkKeyScan(char)
                    if vk_code != -1:
                        vk = vk_code & 0xFF
                        scan_code = win32api.MapVirtualKey(vk, 0)

                        # 构造lParam
                        lparam_down = (scan_code << 16) | 1
                        lparam_up = (scan_code << 16) | 0xC0000001

                        # 发送完整的按键序列
                        win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
                        win32gui.SendMessage(self.hwnd, win32con.WM_CHAR, char_code, lparam_down)
                        win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk, lparam_up)

                        self.logger.debug(f"[AHK特殊消息] 发送完整按键序列: '{char}' (VK: {vk})")
                    else:
                        # 无法映射的字符，只发送WM_CHAR
                        win32gui.SendMessage(self.hwnd, win32con.WM_CHAR, char_code, 0)
                        self.logger.debug(f"[AHK特殊消息] 发送WM_CHAR: '{char}' (code: {char_code})")

                except Exception as char_error:
                    self.logger.debug(f"[AHK特殊消息] 字符 '{char}' 发送失败: {char_error}")
                    return False

            self.logger.info("[AHK特殊消息] 文本发送完成")
            return True

        except Exception as e:
            self.logger.debug(f"[AHK特殊消息] 失败: {e}")
            return False

    def _make_lparam(self, scan_code: int, extended: bool, repeat_count: int,
                     previous_state: bool, transition_state: bool) -> int:
        """构造LPARAM参数"""
        lparam = repeat_count & 0xFFFF
        lparam |= (scan_code & 0xFF) << 16
        if extended:
            lparam |= 0x01000000
        if previous_state:
            lparam |= 0x40000000
        if transition_state:
            lparam |= 0x80000000
        return lparam

    def _vk_to_key_name(self, vk_code: int) -> Optional[str]:
        """将虚拟键码转换为pyautogui键名"""
        vk_map = {
            win32con.VK_BACK: 'backspace',
            win32con.VK_TAB: 'tab',
            win32con.VK_RETURN: 'enter',
            win32con.VK_SHIFT: 'shift',
            win32con.VK_CONTROL: 'ctrl',
            win32con.VK_MENU: 'alt',
            win32con.VK_ESCAPE: 'esc',
            win32con.VK_SPACE: 'space',
            win32con.VK_LEFT: 'left',
            win32con.VK_UP: 'up',
            win32con.VK_RIGHT: 'right',
            win32con.VK_DOWN: 'down',
            win32con.VK_DELETE: 'delete',
            win32con.VK_HOME: 'home',
            win32con.VK_END: 'end',
            win32con.VK_PRIOR: 'pageup',
            win32con.VK_NEXT: 'pagedown',
            win32con.VK_INSERT: 'insert',
            win32con.VK_F1: 'f1', win32con.VK_F2: 'f2', win32con.VK_F3: 'f3',
            win32con.VK_F4: 'f4', win32con.VK_F5: 'f5', win32con.VK_F6: 'f6',
            win32con.VK_F7: 'f7', win32con.VK_F8: 'f8', win32con.VK_F9: 'f9',
            win32con.VK_F10: 'f10', win32con.VK_F11: 'f11', win32con.VK_F12: 'f12',
        }

        # 字母和数字键
        if 0x41 <= vk_code <= 0x5A:  # A-Z
            return chr(vk_code).lower()
        elif 0x30 <= vk_code <= 0x39:  # 0-9
            return chr(vk_code)

        return vk_map.get(vk_code)

    def _clipboard_paste_to_focused(self, text: str) -> bool:
        """剪贴板粘贴方法（针对有焦点的输入框）"""
        try:
            import pyperclip
            import win32gui
            import win32con
            import time

            self.logger.debug("[焦点剪贴板] 开始尝试剪贴板粘贴")

            # 备份剪贴板
            original_clipboard = ""
            try:
                original_clipboard = pyperclip.paste()
            except:
                pass

            try:
                # 复制文本到剪贴板
                pyperclip.copy(text)
                time.sleep(0.1)

                # 尝试WM_PASTE
                result = win32gui.SendMessage(self.hwnd, win32con.WM_PASTE, 0, 0)
                self.logger.debug(f"[焦点剪贴板] WM_PASTE结果: {result}")

                time.sleep(0.2)

                # 恢复剪贴板
                try:
                    if original_clipboard:
                        pyperclip.copy(original_clipboard)
                except:
                    pass

                self.logger.info("[焦点剪贴板] 剪贴板粘贴完成")
                return True

            except Exception as e:
                # 恢复剪贴板
                try:
                    if original_clipboard:
                        pyperclip.copy(original_clipboard)
                except:
                    pass
                self.logger.debug(f"[焦点剪贴板] 失败: {e}")
                return False

        except ImportError:
            self.logger.debug("[焦点剪贴板] pyperclip不可用")
            return False
        except Exception as e:
            self.logger.debug(f"[焦点剪贴板] 失败: {e}")
            return False

    def _char_messages_to_focused(self, text: str) -> bool:
        """直接字符消息（针对有焦点的输入框）"""
        try:
            import win32gui
            import win32con
            import time

            self.logger.debug("[焦点字符消息] 开始尝试字符消息")

            for char in text:
                char_code = ord(char)
                win32gui.SendMessage(self.hwnd, win32con.WM_CHAR, char_code, 0)
                self.logger.debug(f"[焦点字符消息] 发送字符 '{char}' (code: {char_code})")
                time.sleep(0.05)

            self.logger.info("[焦点字符消息] 字符消息发送完成")
            return True

        except Exception as e:
            self.logger.debug(f"[焦点字符消息] 失败: {e}")
            return False

    def _vk_to_focused(self, text: str) -> bool:
        """虚拟键码方法（针对有焦点的输入框）"""
        try:
            import win32api
            import win32con
            import win32gui
            import time

            self.logger.debug("[焦点VK码] 开始尝试虚拟键码")

            for char in text:
                vk_code = win32api.VkKeyScan(char)

                if vk_code != -1:
                    vk = vk_code & 0xFF
                    shift = (vk_code >> 8) & 0x01

                    try:
                        if shift:
                            # 需要Shift键
                            self.send_key_down(win32con.VK_SHIFT)
                            self.send_key(vk)
                            self.send_key_up(win32con.VK_SHIFT)
                        else:
                            self.send_key(vk)

                        self.logger.debug(f"[焦点VK码] 发送VK码字符 '{char}' (VK: {vk})")

                    except Exception as vk_error:
                        self.logger.debug(f"[焦点VK码] VK码失败，回退到WM_CHAR: {vk_error}")
                        win32gui.SendMessage(self.hwnd, win32con.WM_CHAR, ord(char), 0)
                else:
                    # 无法映射的字符
                    win32gui.SendMessage(self.hwnd, win32con.WM_CHAR, ord(char), 0)
                    self.logger.debug(f"[焦点VK码] 发送WM_CHAR字符 '{char}'")

                time.sleep(0.05)

            self.logger.info("[焦点VK码] VK码方法完成")
            return True

        except Exception as e:
            self.logger.debug(f"[焦点VK码] 失败: {e}")
            return False

    def _sendinput_to_focused(self, text: str) -> bool:
        """SendInput方法（全局输入，但输入框有焦点）"""
        try:
            import ctypes
            from ctypes import wintypes, Structure
            import time

            self.logger.debug("[焦点SendInput] 开始尝试SendInput")

            # 定义INPUT结构
            class KEYBDINPUT(Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]

            class INPUT(Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("_input", _INPUT)
                ]

            INPUT_KEYBOARD = 1
            KEYEVENTF_UNICODE = 0x0004

            for char in text:
                # 创建INPUT结构
                inputs = (INPUT * 1)()
                inputs[0].type = INPUT_KEYBOARD
                inputs[0].ki.wVk = 0
                inputs[0].ki.wScan = ord(char)
                inputs[0].ki.dwFlags = KEYEVENTF_UNICODE
                inputs[0].ki.time = 0
                inputs[0].ki.dwExtraInfo = None

                # 发送输入
                result = ctypes.windll.user32.SendInput(1, inputs, ctypes.sizeof(INPUT))

                if result:
                    self.logger.debug(f"[焦点SendInput] 成功发送字符 '{char}'")
                else:
                    self.logger.debug(f"[焦点SendInput] 发送字符 '{char}' 失败")
                    return False

                time.sleep(0.05)

            self.logger.info("[焦点SendInput] SendInput方法完成")
            return True

        except Exception as e:
            self.logger.debug(f"[焦点SendInput] 失败: {e}")
            return False

    def _find_focused_child_control(self) -> int:
        """寻找当前有焦点的子控件"""
        try:
            import win32gui
            import win32process
            import win32api
            import ctypes

            self.logger.debug("[寻找焦点控件] 开始寻找有焦点的子控件")

            # 通过AttachThreadInput获取焦点
            try:
                current_thread = win32api.GetCurrentThreadId()
                target_thread, _ = win32process.GetWindowThreadProcessId(self.hwnd)

                if current_thread != target_thread:
                    attach_result = ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, True)

                    if attach_result:
                        try:
                            focused_hwnd = win32gui.GetFocus()
                            if focused_hwnd and focused_hwnd != self.hwnd:
                                self.logger.debug(f"[寻找焦点控件] 找到焦点控件: {focused_hwnd}")
                                return focused_hwnd
                        finally:
                            ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
            except Exception as e:
                self.logger.debug(f"[寻找焦点控件] AttachThreadInput失败: {e}")

            return 0

        except Exception as e:
            self.logger.debug(f"[寻找焦点控件] 失败: {e}")
            return 0

    def _find_all_input_controls(self) -> list:
        """枚举所有可能的输入框子控件"""
        try:
            import win32gui

            self.logger.debug("[枚举输入控件] 开始枚举所有可能的输入控件")

            input_controls = []

            def enum_child_proc(hwnd_child, lparam):
                try:
                    class_name = win32gui.GetClassName(hwnd_child)
                    window_text = win32gui.GetWindowText(hwnd_child)

                    # 输入控件类名列表
                    input_classes = [
                        'Edit', 'RichEdit', 'RichEdit20A', 'RichEdit20W', 'RICHEDIT50W',
                        'ComboBox', 'ListBox', 'Static', 'Button'
                    ]

                    is_input_class = any(input_class in class_name for input_class in input_classes)
                    is_visible = win32gui.IsWindowVisible(hwnd_child)

                    if is_input_class or (is_visible and window_text):
                        input_controls.append((hwnd_child, class_name, window_text))
                        self.logger.debug(f"[枚举输入控件] 找到候选控件: {hwnd_child} ({class_name}) '{window_text}'")

                except:
                    pass

                return True

            try:
                win32gui.EnumChildWindows(self.hwnd, enum_child_proc, 0)
            except:
                pass

            # 按优先级排序
            def control_priority(control):
                hwnd_child, class_name, window_text = control
                if 'Edit' in class_name or 'RichEdit' in class_name:
                    return 0
                elif 'ComboBox' in class_name:
                    return 1
                elif window_text:
                    return 2
                else:
                    return 3

            input_controls.sort(key=control_priority)

            self.logger.debug(f"[枚举输入控件] 总共找到 {len(input_controls)} 个候选控件")
            return input_controls

        except Exception as e:
            self.logger.debug(f"[枚举输入控件] 失败: {e}")
            return []

    def _send_text_to_specific_control(self, control_hwnd: int, text: str) -> bool:
        """向特定的控件发送文本"""
        try:
            import win32gui
            import win32con
            import pyperclip
            import ctypes
            import time

            self.logger.debug(f"[发送到控件] 开始向控件 {control_hwnd} 发送文本: '{text}'")

            # 获取控件信息
            try:
                class_name = win32gui.GetClassName(control_hwnd)
                window_text = win32gui.GetWindowText(control_hwnd)
                self.logger.debug(f"[发送到控件] 控件信息: 类名={class_name}, 文本='{window_text}'")
            except:
                class_name = "Unknown"
                window_text = ""

            # 方法1：剪贴板粘贴
            try:
                self.logger.debug("[发送到控件] 尝试剪贴板粘贴")

                original_clipboard = ""
                try:
                    original_clipboard = pyperclip.paste()
                except:
                    pass

                pyperclip.copy(text)
                time.sleep(0.1)

                result = win32gui.SendMessage(control_hwnd, win32con.WM_PASTE, 0, 0)
                self.logger.debug(f"[发送到控件] WM_PASTE结果: {result}")

                time.sleep(0.2)

                try:
                    if original_clipboard:
                        pyperclip.copy(original_clipboard)
                except:
                    pass

                # 验证是否成功
                try:
                    new_text = win32gui.GetWindowText(control_hwnd)
                    if text in new_text or new_text != window_text:
                        self.logger.info(f"[发送到控件] 剪贴板粘贴成功，控件文本变为: '{new_text}'")
                        return True
                except:
                    pass

                self.logger.info(f"[发送到控件] 剪贴板粘贴方法完成")
                return True

            except Exception as clipboard_error:
                self.logger.debug(f"[发送到控件] 剪贴板方法失败: {clipboard_error}")

            # 方法2：SetWindowText
            try:
                self.logger.debug("[发送到控件] 尝试SetWindowText")

                result = win32gui.SetWindowText(control_hwnd, text)

                if result:
                    new_text = win32gui.GetWindowText(control_hwnd)
                    if new_text == text:
                        self.logger.info(f"[发送到控件] SetWindowText成功: '{new_text}'")
                        return True

            except Exception as settext_error:
                self.logger.debug(f"[发送到控件] SetWindowText失败: {settext_error}")

            # 方法3：WM_CHAR逐字符发送
            try:
                self.logger.debug("[发送到控件] 尝试WM_CHAR逐字符发送")

                for char in text:
                    char_code = ord(char)
                    win32gui.SendMessage(control_hwnd, win32con.WM_CHAR, char_code, 0)
                    time.sleep(0.05)

                self.logger.info(f"[发送到控件] WM_CHAR方法完成")
                return True

            except Exception as char_error:
                self.logger.debug(f"[发送到控件] WM_CHAR方法失败: {char_error}")

            return False

        except Exception as e:
            self.logger.debug(f"[发送到控件] 发送失败: {e}")
            return False
