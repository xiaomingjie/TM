"""
模拟器窗口输入模拟模块
针对Android模拟器窗口的键盘鼠标模拟，支持ADB和传统方法
"""

import time
import win32gui
import win32con
import win32api
from typing import Optional, List
from .base import BaseInputSimulator


class EmulatorWindowInputSimulator(BaseInputSimulator):
    """模拟器窗口输入模拟器"""
    
    def __init__(self, hwnd: int, emulator_type: str = "auto", execution_mode: str = "background"):
        """
        初始化模拟器窗口输入模拟器

        Args:
            hwnd: 目标窗口句柄
            emulator_type: 模拟器类型 ("ldplayer", "mumu", "auto")
            execution_mode: 执行模式 ("foreground", "background", "emulator_xxx")
        """
        super().__init__(hwnd)
        self.emulator_type = emulator_type

        # 标准化执行模式：将7种模式转换为基础的 foreground/background/emulator
        self.original_execution_mode = execution_mode  # 保留原始模式
        if execution_mode.startswith('foreground'):
            self.execution_mode = 'foreground'
        elif execution_mode.startswith('background'):
            self.execution_mode = 'background'
        elif execution_mode.startswith('emulator_'):
            self.execution_mode = 'background'  # 模拟器模式作为后台模式处理
        else:
            self.execution_mode = execution_mode

        self._emulator_manager = None
        self._init_emulator_manager()

        # 缓存相关变量，避免重复计算
        self._cached_emulator_type = None
        self._cached_mumu_parent_hwnd = None
        self._cached_mumu_simulator = None

        # 获取实际检测到的模拟器类型
        detected_type = self.get_emulator_type()
        self.logger.info(f"模拟器输入模拟器初始化: 原始类型={emulator_type}, 检测类型={detected_type}, 执行模式={self.original_execution_mode} (标准化为: {self.execution_mode})")

        # 工具 修复：设置绑定会话，用于检测重新绑定
        if detected_type == "mumu":
            self._set_mumu_binding_session()
        
    def _init_emulator_manager(self):
        """初始化模拟器管理器"""
        try:
            from utils.emulator_text_input_new import EmulatorTextInputManager
            self._emulator_manager = EmulatorTextInputManager()
            self.logger.debug("成功导入并初始化模拟器文本输入管理器")
        except ImportError as e:
            self.logger.warning(f"无法导入模拟器文本输入管理器: {e}")
            self._emulator_manager = None
        except Exception as e:
            self.logger.error(f"初始化模拟器文本输入管理器失败: {e}")
            self._emulator_manager = None
    
    def click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """鼠标点击 - 根据执行模式选择方法"""
        try:
            self.logger.debug(f"模拟器点击: 坐标=({x}, {y}), 按钮={button}, 执行模式={self.execution_mode}")

            # 检查模拟器类型并使用专用方法
            emulator_type = self.get_emulator_type()
            self.logger.info(f"模拟器点击: 检测到类型={emulator_type}, 执行模式={self.execution_mode}, 原始模式={self.original_execution_mode}")

            # 只有emulator_xxx专用模式才使用模拟器专用方法
            # 纯后台模式(background/background_sendmessage等)应该使用传统PostMessage方法
            is_emulator_dedicated_mode = self.original_execution_mode.startswith('emulator_')

            # MuMu模拟器专用处理 - 仅限emulator_mumu模式
            if emulator_type == "mumu" and is_emulator_dedicated_mode:
                self.logger.info("使用MuMu专用点击方法（模拟器专用模式）")
                return self._mumu_click(x, y, button, clicks, interval)

            # 雷电模拟器专用处理 - 仅限emulator_ldplayer模式
            elif emulator_type == "ldplayer" and is_emulator_dedicated_mode:
                self.logger.info("使用雷电模拟器专用点击方法（模拟器专用模式）")
                return self._ldplayer_click(x, y, button, clicks, interval)

            # 前台模式
            elif self.execution_mode == "foreground":
                self.logger.info(f"使用前台点击方法（模拟器类型: {emulator_type}）")
                return self._foreground_click(x, y, button, clicks, interval)

            # 其他情况使用传统方法（包括纯后台模式）
            else:
                self.logger.info("使用传统PostMessage点击方法")
                return self._traditional_click(x, y, button, clicks, interval)
        except Exception as e:
            self.logger.error(f"模拟器窗口点击失败: {e}")
            return False

    def _mumu_click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """MuMu模拟器专用点击方法（优化版，支持坐标转换）"""
        try:
            # 使用缓存的MuMu输入模拟器
            if self._cached_mumu_simulator is None:
                from utils.mumu_input_simulator import get_mumu_input_simulator
                self._cached_mumu_simulator = get_mumu_input_simulator()

            # 使用缓存的父窗口句柄
            if self._cached_mumu_parent_hwnd is None:
                self._cached_mumu_parent_hwnd = self._get_mumu_parent_window()
                if not self._cached_mumu_parent_hwnd:
                    self.logger.warning("无法找到MuMu父窗口，回退到传统方法")
                    return self._traditional_click(x, y, button, clicks, interval)

                # 只在第一次获取时记录详细信息
                try:
                    import win32gui
                    parent_title = win32gui.GetWindowText(self._cached_mumu_parent_hwnd)
                    parent_class = win32gui.GetClassName(self._cached_mumu_parent_hwnd)
                    self.logger.info(f"MuMu点击目标缓存: 渲染窗口({self.hwnd}) -> 父窗口({self._cached_mumu_parent_hwnd}) '{parent_title}' ({parent_class})")
                except:
                    self.logger.info(f"MuMu点击目标缓存: 渲染窗口({self.hwnd}) -> 父窗口({self._cached_mumu_parent_hwnd})")

            parent_hwnd = self._cached_mumu_parent_hwnd

            # 坐标转换：将Windows客户区坐标转换为模拟器内部坐标
            # 这是关键修复：图片点击传入的是客户区坐标，需要转换为模拟器坐标
            mumu_x, mumu_y = self._convert_to_mumu_coordinates(x, y)

            if mumu_x != x or mumu_y != y:
                self.logger.debug(f"MuMu坐标转换: 客户区({x}, {y}) -> 模拟器({mumu_x}, {mumu_y})")

            for i in range(clicks):
                # 使用转换后的模拟器坐标进行点击
                result = self._cached_mumu_simulator.mouse_click(parent_hwnd, mumu_x, mumu_y, button)
                if not result.success:
                    self.logger.error(f"MuMu模拟器点击失败: {result.message}")
                    return False

                if i < clicks - 1:
                    time.sleep(interval)

            # 只在调试模式下输出详细日志
            self.logger.debug(f"MuMu模拟器点击完成: 原始坐标({x}, {y}) -> 模拟器坐标({mumu_x}, {mumu_y}), 次数: {clicks}")
            return True

        except ImportError:
            self.logger.warning("MuMu输入模拟器不可用，回退到传统方法")
            return self._traditional_click(x, y, button, clicks, interval)
        except Exception as e:
            self.logger.error(f"MuMu模拟器点击异常: {e}")
            return False

    def _ldplayer_click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """雷电模拟器专用点击方法 - 使用与后台模式完全相同的实现"""
        try:
            # 雷电模拟器使用SendMessage到当前窗口（渲染窗口）
            # 关键修复：与后台模式一模一样的实现，因为后台模式对雷电有效
            button_map = {
                'left': (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
                'right': (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
                'middle': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
            }

            if button not in button_map:
                self.logger.error(f"不支持的鼠标按钮: {button}")
                return False

            down_msg, up_msg = button_map[button]
            # 关键修复1：确保坐标转换为整数（与后台模式一致）
            lParam = win32api.MAKELONG(int(x), int(y))

            for i in range(clicks):
                # 关键修复2：使用SendMessage而非PostMessage（与后台模式一致）
                win32gui.SendMessage(self.hwnd, down_msg, 0, lParam)
                time.sleep(0.01)
                win32gui.SendMessage(self.hwnd, up_msg, 0, lParam)

                if i < clicks - 1:
                    time.sleep(interval)

            self.logger.debug(f"雷电模拟器点击完成: 坐标({x}, {y}), 次数: {clicks}")
            return True

        except Exception as e:
            self.logger.error(f"雷电模拟器点击异常: {e}")
            return False

    def _traditional_click(self, x: int, y: int, button: str, clicks: int, interval: float) -> bool:
        """传统方法点击（PostMessage）"""
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
            # 使用PostMessage而不是SendMessage，对模拟器更有效
            win32gui.PostMessage(self.hwnd, down_msg, 0, lparam)
            time.sleep(0.01)
            win32gui.PostMessage(self.hwnd, up_msg, 0, lparam)
            
            if i < clicks - 1:
                time.sleep(interval)
        
        return True
    
    def double_click(self, x: int, y: int, button: str = 'left') -> bool:
        """鼠标双击"""
        return self.click(x, y, button, clicks=2, interval=0.1)
    
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
             duration: float = 1.0, button: str = 'left') -> bool:
        """鼠标拖拽 - 根据模拟器类型选择方法"""
        try:
            # 检查是否为MuMu模拟器，使用专用方法
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                return self._mumu_drag(start_x, start_y, end_x, end_y, duration, button)
            else:
                # 直接使用PostMessage方法
                return self._traditional_drag(start_x, start_y, end_x, end_y, duration, button)
        except Exception as e:
            self.logger.error(f"模拟器窗口拖拽失败: {e}")
            return False

    def _mumu_drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
                   duration: float = 1.0, button: str = 'left') -> bool:
        """MuMu模拟器专用拖拽方法"""
        try:
            # 导入MuMu输入模拟器
            from utils.mumu_input_simulator import get_mumu_input_simulator
            mumu_simulator = get_mumu_input_simulator()

            # 获取当前渲染窗口对应的MuMu父窗口句柄
            parent_hwnd = self._get_mumu_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到MuMu父窗口，回退到传统方法")
                return self._traditional_drag(start_x, start_y, end_x, end_y, duration, button)

            # 将duration转换为毫秒
            duration_ms = int(duration * 1000)

            result = mumu_simulator.mouse_swipe(parent_hwnd, start_x, start_y, end_x, end_y, duration_ms)
            if result.success:
                self.logger.debug(f"MuMu模拟器拖拽成功: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                return True
            else:
                self.logger.error(f"MuMu模拟器拖拽失败: {result.message}")
                return False

        except ImportError:
            self.logger.warning("MuMu输入模拟器不可用，回退到传统方法")
            return self._traditional_drag(start_x, start_y, end_x, end_y, duration, button)
        except Exception as e:
            self.logger.error(f"MuMu模拟器拖拽异常: {e}")
            return False

    def drag_path(self, path_points: list, duration: float = 1.0) -> bool:
        """多点路径拖拽 - 根据模拟器类型选择方法

        Args:
            path_points: 路径点列表，格式: [(x1, y1), (x2, y2), (x3, y3), ...]
            duration: 总持续时间（秒）

        Returns:
            bool: 是否执行成功
        """
        try:
            if not path_points or len(path_points) < 2:
                self.logger.error("路径点数量不足，至少需要2个点")
                return False

            # 检查是否为MuMu模拟器，使用专用方法
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                return self._mumu_drag_path(path_points, duration)
            else:
                # 其他模拟器回退到分段拖拽
                return self._traditional_drag_path(path_points, duration)
        except Exception as e:
            self.logger.error(f"模拟器窗口多点拖拽失败: {e}")
            return False

    def _mumu_drag_path(self, path_points: list, duration: float = 1.0) -> bool:
        """MuMu模拟器专用多点路径拖拽方法"""
        try:
            # 导入MuMu输入模拟器
            from utils.mumu_input_simulator import get_mumu_input_simulator
            mumu_simulator = get_mumu_input_simulator()

            # 获取当前渲染窗口对应的MuMu父窗口句柄
            parent_hwnd = self._get_mumu_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到MuMu父窗口，回退到传统方法")
                return self._traditional_drag_path(path_points, duration)

            # 将duration转换为毫秒
            duration_ms = int(duration * 1000)

            result = mumu_simulator.mouse_swipe_path(parent_hwnd, path_points, duration_ms)
            if result.success:
                self.logger.debug(f"MuMu模拟器多点拖拽成功: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) {len(path_points)}个点")
                return True
            else:
                self.logger.error(f"MuMu模拟器多点拖拽失败: {result.message}")
                return False

        except ImportError:
            self.logger.warning("MuMu输入模拟器不可用，回退到传统方法")
            return self._traditional_drag_path(path_points, duration)
        except Exception as e:
            self.logger.error(f"MuMu模拟器多点拖拽异常: {e}")
            return False

    def _traditional_drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
                         duration: float, button: str) -> bool:
        """传统方法拖拽"""
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
        win32gui.PostMessage(self.hwnd, down_msg, 0, start_lparam)
        
        # 移动到结束位置
        steps = max(10, int(duration * 30))
        for i in range(steps + 1):
            progress = i / steps
            current_x = int(start_x + (end_x - start_x) * progress)
            current_y = int(start_y + (end_y - start_y) * progress)
            current_lparam = win32api.MAKELONG(current_x, current_y)
            win32gui.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, current_lparam)
            time.sleep(duration / steps)
        
        # 释放鼠标
        end_lparam = win32api.MAKELONG(end_x, end_y)
        win32gui.PostMessage(self.hwnd, up_msg, 0, end_lparam)
        
        return True

    def _traditional_drag_path(self, path_points: list, duration: float) -> bool:
        """传统方法多点路径拖拽 - 分段执行多个拖拽操作"""
        try:
            if len(path_points) < 2:
                return False

            # 计算每段的持续时间
            segment_count = len(path_points) - 1
            segment_duration = duration / segment_count

            self.logger.debug(f"传统多点拖拽: {len(path_points)}个点, 分{segment_count}段, 每段{segment_duration:.2f}秒")

            # 分段执行拖拽
            success_count = 0
            for i in range(segment_count):
                start_x, start_y = path_points[i]
                end_x, end_y = path_points[i + 1]

                # 执行单段拖拽
                if self._traditional_drag(start_x, start_y, end_x, end_y, segment_duration, 'left'):
                    success_count += 1
                    self.logger.debug(f"段{i+1}拖拽成功: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                else:
                    self.logger.warning(f"段{i+1}拖拽失败: ({start_x}, {start_y}) -> ({end_x}, {end_y})")

                # 段间短暂延迟，避免操作过快
                if i < segment_count - 1:
                    import time
                    time.sleep(0.05)

            # 如果大部分段都成功，认为整体成功
            success_rate = success_count / segment_count
            if success_rate >= 0.7:  # 70%以上成功率
                self.logger.info(f"传统多点拖拽完成: {success_count}/{segment_count}段成功")
                return True
            else:
                self.logger.error(f"传统多点拖拽失败: 仅{success_count}/{segment_count}段成功")
                return False

        except Exception as e:
            self.logger.error(f"传统多点拖拽异常: {e}")
            return False

    def scroll(self, x: int, y: int, delta: int) -> bool:
        """鼠标滚轮 - 根据模拟器类型选择方法"""
        try:
            # 检查模拟器类型，使用对应的滚轮方法
            emulator_type = self.get_emulator_type()

            if emulator_type == "mumu":
                # MuMu模拟器：发送到父窗口
                return self._mumu_scroll(x, y, delta)
            elif emulator_type == "ldplayer":
                # 雷电模拟器：使用和MuMu相同的方式（发送到父窗口）
                return self._ldplayer_scroll(x, y, delta)
            else:
                # 其他模拟器：使用传统PostMessage方法
                return self._traditional_scroll(x, y, delta)
        except Exception as e:
            self.logger.error(f"模拟器窗口滚轮失败: {e}")
            return False

    def _mumu_scroll(self, x: int, y: int, delta: int) -> bool:
        """MuMu模拟器专用滚轮方法 - 发送到父窗口"""
        try:
            # 获取MuMu父窗口句柄
            parent_hwnd = self._get_mumu_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到MuMu父窗口，回退到传统方法")
                return self._traditional_scroll(x, y, delta)

            # 发送滚轮事件到父窗口
            lparam = win32api.MAKELONG(x, y)
            wparam = win32api.MAKELONG(0, delta * 120)
            win32gui.PostMessage(parent_hwnd, win32con.WM_MOUSEWHEEL, wparam, lparam)

            self.logger.debug(f"MuMu模拟器滚轮: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) ({x}, {y}) delta={delta}")
            return True
        except Exception as e:
            self.logger.error(f"MuMu模拟器滚轮失败: {e}")
            return self._traditional_scroll(x, y, delta)

    def _ldplayer_scroll(self, x: int, y: int, delta: int) -> bool:
        """雷电模拟器专用滚轮方法 - 使用和MuMu相同的方式（发送到父窗口）"""
        try:
            # 获取雷电模拟器的父窗口句柄
            parent_hwnd = self._get_ldplayer_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到雷电模拟器父窗口，回退到传统方法")
                return self._traditional_scroll(x, y, delta)

            # 发送滚轮事件到父窗口（和MuMu相同的方式）
            lparam = win32api.MAKELONG(x, y)
            wparam = win32api.MAKELONG(0, delta * 120)
            win32gui.PostMessage(parent_hwnd, win32con.WM_MOUSEWHEEL, wparam, lparam)

            self.logger.debug(f"雷电模拟器滚轮: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) ({x}, {y}) delta={delta}")
            return True
        except Exception as e:
            self.logger.error(f"雷电模拟器滚轮失败: {e}")
            return self._traditional_scroll(x, y, delta)

    def _traditional_scroll(self, x: int, y: int, delta: int) -> bool:
        """传统滚轮方法（适用于其他模拟器）"""
        try:
            # 传统PostMessage方法
            lparam = win32api.MAKELONG(x, y)
            wparam = win32api.MAKELONG(0, delta * 120)
            win32gui.PostMessage(self.hwnd, win32con.WM_MOUSEWHEEL, wparam, lparam)

            self.logger.debug(f"传统滚轮: ({x}, {y}) delta={delta}")
            return True
        except Exception as e:
            self.logger.error(f"传统滚轮失败: {e}")
            return False

    def send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False, hold_duration: float = 0.0) -> bool:
        """发送按键 - 根据模拟器类型选择方法"""
        try:
            # 检查是否为MuMu模拟器，使用专用方法
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                return self._mumu_send_key(vk_code, scan_code, extended, hold_duration)
            elif hold_duration > 0:
                # 支持按键持续时间
                return self._send_key_with_duration(vk_code, scan_code, extended, hold_duration)
            else:
                # 直接使用PostMessage方法
                return self._traditional_send_key(vk_code, scan_code, extended)
        except Exception as e:
            self.logger.error(f"模拟器窗口发送按键失败: {e}")
            return False

    def _mumu_send_key(self, vk_code: int, scan_code: int = 0, extended: bool = False, hold_duration: float = 0.0) -> bool:
        """MuMu模拟器专用按键发送方法 - 发送到父窗口（测试证明必须发送到父窗口）"""
        try:
            # 获取MuMu父窗口句柄
            parent_hwnd = self._get_mumu_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到MuMu父窗口，回退到当前窗口")
                parent_hwnd = self.hwnd

            # 使用PostMessage方式发送按键到父窗口
            # 测试证明必须发送到父窗口才有效果
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            # 按下
            lparam_down = self._make_lparam(scan_code, extended, 1, False, False)
            win32gui.PostMessage(parent_hwnd, win32con.WM_KEYDOWN, vk_code, lparam_down)

            # 处理按键持续时间
            if hold_duration > 0:
                time.sleep(hold_duration)
            else:
                time.sleep(0.01)

            # 释放
            lparam_up = self._make_lparam(scan_code, extended, 1, True, True)
            win32gui.PostMessage(parent_hwnd, win32con.WM_KEYUP, vk_code, lparam_up)

            self.logger.debug(f"MuMu模拟器PostMessage发送按键到父窗口成功: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) VK={vk_code}")
            return True

        except Exception as e:
            self.logger.error(f"MuMu模拟器PostMessage按键发送异常: {e}")
            return False

    def _vk_code_to_mumu_key_command(self, vk_code: int) -> Optional[str]:
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

    def _send_key_with_duration(self, vk_code: int, scan_code: int, extended: bool, hold_duration: float) -> bool:
        """发送带持续时间的按键"""
        try:
            # 按下按键
            success = self.send_key_down(vk_code, scan_code, extended)
            if not success:
                return False

            # 持续时间
            time.sleep(hold_duration)

            # 释放按键
            return self.send_key_up(vk_code, scan_code, extended)
        except Exception as e:
            self.logger.error(f"模拟器窗口发送持续按键失败: {e}")
            return False



    def _traditional_send_key(self, vk_code: int, scan_code: int, extended: bool) -> bool:
        """传统方法发送按键（PostMessage）"""
        success = True
        success &= self.send_key_down(vk_code, scan_code, extended)
        time.sleep(0.01)
        success &= self.send_key_up(vk_code, scan_code, extended)
        return success
    
    def send_key_down(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键按下"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            lparam = self._make_lparam(scan_code, extended, 1, False, False)

            # 根据模拟器类型选择发送方式
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                # MuMu模拟器使用SendMessage
                win32gui.SendMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
            else:
                # 其他模拟器使用PostMessage
                win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
            return True
        except Exception as e:
            self.logger.error(f"模拟器窗口发送按键按下失败: {e}")
            return False
    
    def send_key_up(self, vk_code: int, scan_code: int = 0, extended: bool = False) -> bool:
        """发送按键释放"""
        try:
            if scan_code == 0:
                scan_code = win32api.MapVirtualKey(vk_code, 0)

            lparam = self._make_lparam(scan_code, extended, 1, True, True)

            # 根据模拟器类型选择发送方式
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                # MuMu模拟器使用SendMessage
                win32gui.SendMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)
            else:
                # 其他模拟器使用PostMessage
                win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk_code, lparam)
            return True
        except Exception as e:
            self.logger.error(f"模拟器窗口发送按键释放失败: {e}")
            return False
    
    def send_text(self, text: str) -> bool:
        """发送文本"""
        try:
            # 检查是否为MuMu模拟器，使用专用方法
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                return self._mumu_send_text(text)

            # 优先尝试ADB文本输入
            if self._try_adb_text(text):
                return True

            # 回退到传统方法
            return self._traditional_send_text(text)
        except Exception as e:
            self.logger.error(f"模拟器窗口发送文本失败: {e}")
            return False

    def _mumu_send_text(self, text: str) -> bool:
        """MuMu模拟器专用文本发送方法 - 使用简化高效版本"""
        try:
            # 导入简化的MuMu输入模拟器
            from utils.mumu_input_simulator import get_simple_mumu_input_simulator
            simple_simulator = get_simple_mumu_input_simulator()

            # 获取当前渲染窗口对应的MuMu父窗口句柄
            parent_hwnd = self._get_mumu_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到MuMu父窗口，回退到传统方法")
                return self._traditional_send_text(text)

            result = simple_simulator.input_text(parent_hwnd, text)
            if result.success:
                self.logger.debug(f"MuMu模拟器简化文本发送成功: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) 文本: {text}")
                return True
            else:
                self.logger.error(f"MuMu模拟器简化文本发送失败: {result.message}")
                # 回退到传统方法
                return self._traditional_send_text(text)

        except ImportError:
            self.logger.warning("MuMu输入模拟器不可用，回退到传统方法")
            return self._traditional_send_text(text)
        except Exception as e:
            self.logger.error(f"MuMu模拟器ADB文本发送异常: {e}")
            return False

    def _set_mumu_binding_session(self):
        """设置MuMu绑定会话（用于检测重新绑定）"""
        try:
            from utils.mumu_input_simulator import get_simple_mumu_input_simulator
            import time

            # 生成基于时间和窗口句柄的会话ID
            session_id = f"binding_{int(time.time())}_{self.hwnd}"

            simple_simulator = get_simple_mumu_input_simulator()
            simple_simulator.set_binding_session(session_id)

            self.logger.info(f"设置MuMu绑定会话: {session_id}")

        except Exception as e:
            self.logger.warning(f"设置MuMu绑定会话失败: {e}")

    def _try_adb_text(self, text: str) -> bool:
        """尝试使用ADB发送文本"""
        if not self._emulator_manager:
            return False

        try:
            return self._emulator_manager.try_adb_shell_input(self.hwnd, text)
        except Exception as e:
            self.logger.debug(f"ADB文本输入失败: {e}")
            return False

    def _traditional_send_text(self, text: str) -> bool:
        """传统方法发送文本"""
        for char in text:
            # 获取字符的虚拟键码
            vk_code = win32api.VkKeyScan(char)
            if vk_code != -1:
                # 提取虚拟键码和修饰键
                vk = vk_code & 0xFF
                shift = (vk_code >> 8) & 0x01

                if shift:
                    # 需要按住Shift键
                    self.send_key_down(win32con.VK_SHIFT)
                    self.send_key(vk)
                    self.send_key_up(win32con.VK_SHIFT)
                else:
                    self.send_key(vk)
            else:
                # 无法映射的字符，使用WM_CHAR消息
                win32gui.PostMessage(self.hwnd, win32con.WM_CHAR, ord(char), 0)
        return True

    def send_key_combination(self, keys: list, hold_duration: float = 0.1) -> bool:
        """发送组合键 - 根据模拟器类型选择方法"""
        try:
            # 检查是否为MuMu模拟器，使用专用方法
            emulator_type = self.get_emulator_type()
            if emulator_type == "mumu":
                return self._mumu_send_key_combination(keys, hold_duration)
            else:
                # 其他模拟器使用传统PostMessage方法
                return self._traditional_send_key_combination(keys, hold_duration)
        except Exception as e:
            self.logger.error(f"模拟器窗口发送组合键失败: {e}")
            return False



    def _mumu_send_key_combination(self, keys: list, hold_duration: float) -> bool:
        """MuMu模拟器专用组合键发送方法 - 发送到父窗口"""
        try:
            # 获取MuMu父窗口句柄
            parent_hwnd = self._get_mumu_parent_window()
            if not parent_hwnd:
                self.logger.warning("无法找到MuMu父窗口，回退到传统方法")
                return self._traditional_send_key_combination(keys, hold_duration)

            # 使用PostMessage方式发送组合键到父窗口
            # 按顺序按下所有键
            for key in keys:
                scan_code = win32api.MapVirtualKey(key, 0)
                lparam_down = self._make_lparam(scan_code, False, 1, False, False)
                win32gui.PostMessage(parent_hwnd, win32con.WM_KEYDOWN, key, lparam_down)
                time.sleep(0.01)

            # 保持按键状态
            time.sleep(hold_duration)

            # 按相反顺序释放所有键
            for key in reversed(keys):
                scan_code = win32api.MapVirtualKey(key, 0)
                lparam_up = self._make_lparam(scan_code, False, 1, True, True)
                win32gui.PostMessage(parent_hwnd, win32con.WM_KEYUP, key, lparam_up)
                time.sleep(0.01)

            self.logger.debug(f"MuMu模拟器PostMessage发送组合键到父窗口成功: 渲染窗口({self.hwnd}) -> 父窗口({parent_hwnd}) 按键: {keys}")
            return True

        except Exception as e:
            self.logger.error(f"MuMu模拟器组合键发送异常: {e}")
            return False

    def _traditional_send_key_combination(self, keys: list, hold_duration: float) -> bool:
        """传统方法发送组合键"""
        # 按顺序按下所有键
        for key in keys:
            self.send_key_down(key)

        time.sleep(hold_duration)

        # 按相反顺序释放所有键
        for key in reversed(keys):
            self.send_key_up(key)

        return True

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

    def _vk_to_android_key(self, vk_code: int) -> Optional[int]:
        """将Windows虚拟键码转换为Android键码"""
        vk_to_android_map = {
            win32con.VK_BACK: 4,        # KEYCODE_BACK
            win32con.VK_HOME: 3,        # KEYCODE_HOME
            win32con.VK_MENU: 82,       # KEYCODE_MENU
            win32con.VK_RETURN: 66,     # KEYCODE_ENTER
            win32con.VK_SPACE: 62,      # KEYCODE_SPACE
            win32con.VK_LEFT: 21,       # KEYCODE_DPAD_LEFT
            win32con.VK_UP: 19,         # KEYCODE_DPAD_UP
            win32con.VK_RIGHT: 22,      # KEYCODE_DPAD_RIGHT
            win32con.VK_DOWN: 20,       # KEYCODE_DPAD_DOWN
            win32con.VK_DELETE: 67,     # KEYCODE_DEL
            win32con.VK_TAB: 61,        # KEYCODE_TAB
            win32con.VK_ESCAPE: 111,    # KEYCODE_ESCAPE
            win32con.VK_VOLUME_UP: 24,  # KEYCODE_VOLUME_UP
            win32con.VK_VOLUME_DOWN: 25, # KEYCODE_VOLUME_DOWN
        }

        # 数字键 0-9
        if 0x30 <= vk_code <= 0x39:
            return vk_code - 0x30 + 7  # KEYCODE_0 = 7

        # 字母键 A-Z
        if 0x41 <= vk_code <= 0x5A:
            return vk_code - 0x41 + 29  # KEYCODE_A = 29

        return vk_to_android_map.get(vk_code)

    def _foreground_click(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1) -> bool:
        """前台模式点击"""
        try:
            import time

            self.logger.debug(f"[前台点击] 开始前台模式点击: ({x}, {y})")

            # 方法1：优先尝试ADB点击（如果可用）
            if self._emulator_manager and hasattr(self._emulator_manager, 'click'):
                try:
                    success = self._emulator_manager.click(x, y)
                    if success:
                        self.logger.info(f"[前台点击] ADB点击成功: ({x}, {y})")
                        return True
                    else:
                        self.logger.debug(f"[前台点击] ADB点击失败，尝试其他方法")
                except Exception as adb_error:
                    self.logger.debug(f"[前台点击] ADB点击异常: {adb_error}")

            # 方法2：使用pyautogui前台点击
            # 注意：前台模式下，坐标点击任务已经通过通用坐标系统转换为屏幕坐标
            # 这里直接使用传入的坐标，避免双重转换
            try:
                from utils.interception_driver import get_driver
                driver = get_driver()

                self.logger.debug(f"[前台点击] 直接使用屏幕坐标（避免双重转换）: ({x}, {y})")

                # 执行点击
                result = driver.click_mouse(x, y, button=button, clicks=clicks, interval=interval)
                if result:
                    self.logger.info(f"[前台点击] 驱动点击成功: ({x}, {y})")
                else:
                    self.logger.error(f"[前台点击] 驱动点击失败: ({x}, {y})")
                return True

            except ImportError:
                self.logger.debug("[前台点击] pyautogui不可用")
            except Exception as pyautogui_error:
                self.logger.debug(f"[前台点击] pyautogui点击失败: {pyautogui_error}")

            # 方法3：回退到PostMessage方法
            self.logger.debug("[前台点击] 回退到PostMessage方法")
            return self._traditional_click(x, y, button, clicks, interval)

        except Exception as e:
            self.logger.error(f"[前台点击] 前台点击失败: {e}")
            return False

    def get_emulator_type(self) -> str:
        """获取模拟器类型（带缓存优化）"""
        # 如果已经缓存了检测结果，直接返回
        if self._cached_emulator_type is not None:
            return self._cached_emulator_type

        if self.emulator_type != "auto":
            self._cached_emulator_type = self.emulator_type
            return self.emulator_type

        # 自动检测模拟器类型
        try:
            # 使用统一的模拟器检测器
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(self.hwnd)

            if is_emulator and emulator_type:
                self._cached_emulator_type = emulator_type
                return emulator_type

            # 回退到原有逻辑
            window_text = win32gui.GetWindowText(self.hwnd)
            class_name = win32gui.GetClassName(self.hwnd)

            if "雷电" in window_text or "LDPlayer" in window_text or "TheRender" in class_name:
                detected_type = "ldplayer"
            elif "MuMu" in window_text:
                detected_type = "mumu"
            else:
                detected_type = "unknown"

            self._cached_emulator_type = detected_type
            return detected_type
        except Exception:
            self._cached_emulator_type = "unknown"
            return "unknown"

    def _get_mumu_parent_window(self) -> Optional[int]:
        """获取当前MuMu渲染窗口对应的顶级主窗口句柄"""
        try:
            import win32gui

            # 从当前窗口开始，向上查找所有MuMu窗口，优先查找"MuMu安卓设备"主窗口
            current_hwnd = self.hwnd
            mumu_windows = []  # 存储找到的所有MuMu窗口
            main_device_window = None  # 专门存储"MuMu安卓设备"窗口

            while current_hwnd:
                # 获取父窗口
                parent_hwnd = win32gui.GetParent(current_hwnd)
                if not parent_hwnd:
                    break

                # 检查父窗口是否是MuMu窗口
                try:
                    parent_title = win32gui.GetWindowText(parent_hwnd)
                    parent_class = win32gui.GetClassName(parent_hwnd)

                    # 检查是否是MuMu窗口（包含"mumu"且是Qt窗口）
                    if (parent_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and
                        ("mumu" in parent_title.lower() or "mumu" in parent_class.lower())):

                        window_info = {
                            'hwnd': parent_hwnd,
                            'title': parent_title,
                            'class': parent_class,
                            'title_has_mumu': "mumu" in parent_title.lower(),
                            'is_main_device': "MuMu安卓设备" in parent_title
                        }

                        mumu_windows.append(window_info)

                        # 如果是"MuMu安卓设备"窗口，优先记录
                        if "MuMu安卓设备" in parent_title:
                            main_device_window = window_info
                            self.logger.debug(f"找到MuMu主设备窗口: {parent_title} ({parent_class}) HWND:{parent_hwnd}")
                        else:
                            self.logger.debug(f"发现MuMu窗口: {parent_title} ({parent_class}) HWND:{parent_hwnd}")
                except:
                    pass

                # 继续向上查找
                current_hwnd = parent_hwnd

            # 优先选择"MuMu安卓设备"主窗口
            if main_device_window:
                # 验证主设备窗口是否能获取VM索引
                try:
                    from utils.mumu_input_simulator import get_mumu_input_simulator
                    mumu_simulator = get_mumu_input_simulator()
                    vm_index = mumu_simulator.get_vm_index_from_hwnd(main_device_window['hwnd'])

                    if vm_index is not None:
                        self.logger.info(f"选择MuMu主设备窗口: {main_device_window['title']} HWND:{main_device_window['hwnd']} VM索引:{vm_index}")
                        return main_device_window['hwnd']
                    else:
                        self.logger.warning(f"MuMu主设备窗口无法获取VM索引: {main_device_window['title']}")
                except Exception as e:
                    self.logger.warning(f"验证主设备窗口VM索引时出错: {e}")

            # 如果没有找到主设备窗口或主设备窗口无效，选择其他能够获取VM索引的窗口
            if mumu_windows:
                # 导入MuMu输入模拟器来测试VM索引
                try:
                    from utils.mumu_input_simulator import get_mumu_input_simulator
                    mumu_simulator = get_mumu_input_simulator()

                    # 测试每个窗口是否能获取VM索引
                    valid_windows = []
                    for window in mumu_windows:
                        if window.get('is_main_device'):
                            continue  # 主设备窗口已经测试过了

                        vm_index = mumu_simulator.get_vm_index_from_hwnd(window['hwnd'])
                        if vm_index is not None:
                            window['vm_index'] = vm_index
                            valid_windows.append(window)
                            self.logger.debug(f"窗口 {window['title']} (HWND:{window['hwnd']}) 可获取VM索引: {vm_index}")
                        else:
                            self.logger.debug(f"窗口 {window['title']} (HWND:{window['hwnd']}) 无法获取VM索引")

                    # 如果有能获取VM索引的窗口，优先选择
                    if valid_windows:
                        selected_window = valid_windows[0]  # 选择第一个有效的
                        self.logger.info(f"选择有效MuMu窗口: {selected_window['title']} HWND:{selected_window['hwnd']} VM索引:{selected_window['vm_index']}")
                        return selected_window['hwnd']
                except Exception as e:
                    self.logger.warning(f"测试VM索引时出错: {e}")

                # 回退到原有逻辑
                title_mumu_windows = [w for w in mumu_windows if w['title_has_mumu']]
                if title_mumu_windows:
                    selected_window = title_mumu_windows[-1]  # 选择最顶层的
                else:
                    selected_window = mumu_windows[-1]  # 如果没有标题包含mumu的，选择最顶层的

                self.logger.info(f"选择MuMu窗口(回退): {selected_window['title']} HWND:{selected_window['hwnd']} (从{len(mumu_windows)}个候选中选择)")
                return selected_window['hwnd']

            self.logger.warning(f"无法找到渲染窗口 {self.hwnd} 对应的MuMu主窗口")
            return None

        except Exception as e:
            self.logger.error(f"获取MuMu父窗口失败: {e}")
            return None

    def _convert_to_mumu_coordinates(self, x: int, y: int) -> tuple[int, int]:
        """将Windows客户区坐标转换为MuMu模拟器内部坐标"""
        try:
            import win32gui

            # 获取渲染窗口的客户区大小
            client_rect = win32gui.GetClientRect(self.hwnd)
            client_width = client_rect[2] - client_rect[0]
            client_height = client_rect[3] - client_rect[1]

            # 获取MuMu模拟器的分辨率设置
            # 大多数MuMu模拟器默认分辨率是720x1280或1080x1920
            # 我们需要根据实际情况进行缩放

            # 方法1：直接使用客户区坐标（适用于大多数情况）
            # 如果客户区坐标和模拟器坐标是1:1对应的
            if 0 <= x <= client_width and 0 <= y <= client_height:
                # 坐标在有效范围内，直接使用
                return x, y

            # 方法2：如果需要缩放转换
            # 这里可以根据实际测试结果调整缩放比例
            # 暂时先直接返回原坐标，如果有问题再调整

            self.logger.debug(f"MuMu坐标转换: 客户区大小({client_width}x{client_height}), 坐标({x}, {y})")
            return x, y

        except Exception as e:
            self.logger.warning(f"MuMu坐标转换失败，使用原坐标: {e}")
            return x, y

    def _get_ldplayer_parent_window(self) -> Optional[int]:
        """获取当前雷电模拟器渲染窗口对应的顶级主窗口句柄"""
        try:
            import win32gui

            # 从当前窗口开始，向上查找雷电模拟器的主窗口
            current_hwnd = self.hwnd
            max_depth = 10  # 限制查找深度，避免无限循环

            for depth in range(max_depth):
                # 获取父窗口
                parent_hwnd = win32gui.GetParent(current_hwnd)
                if not parent_hwnd:
                    break

                try:
                    parent_title = win32gui.GetWindowText(parent_hwnd)
                    parent_class = win32gui.GetClassName(parent_hwnd)

                    # 检查是否是雷电模拟器主窗口
                    # 雷电模拟器的主窗口通常包含"雷电"、"LDPlayer"等关键词
                    if (("雷电" in parent_title or
                         "LDPlayer" in parent_title or
                         "TheRender" in parent_title) and
                        parent_class != "RenderWindow"):  # 排除渲染窗口本身

                        self.logger.debug(f"找到雷电模拟器父窗口: {parent_title} (类名: {parent_class}, HWND: {parent_hwnd})")
                        return parent_hwnd

                except Exception as e:
                    self.logger.debug(f"检查父窗口时出错: {e}")

                current_hwnd = parent_hwnd

            # 如果没有找到特定的父窗口，返回顶级父窗口
            if current_hwnd and current_hwnd != self.hwnd:
                try:
                    parent_title = win32gui.GetWindowText(current_hwnd)
                    self.logger.debug(f"使用顶级父窗口作为雷电模拟器父窗口: {parent_title} (HWND: {current_hwnd})")
                    return current_hwnd
                except Exception:
                    pass

            self.logger.warning("未找到雷电模拟器父窗口")
            return None

        except Exception as e:
            self.logger.error(f"获取雷电模拟器父窗口失败: {e}")
            return None
