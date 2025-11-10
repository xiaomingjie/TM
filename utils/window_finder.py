#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的窗口查找工具
支持各种模拟器和应用程序的窗口查找
"""

import ctypes
from ctypes import wintypes
import logging
import win32gui

logger = logging.getLogger(__name__)

class WindowFinder:
    """统一的窗口查找器"""
    
    @staticmethod
    def find_window(window_title, emulator_type=None):
        """
        统一的窗口查找方法

        Args:
            window_title: 窗口标题
            emulator_type: 模拟器类型 ("ldplayer", "mumu", 等)

        Returns:
            窗口句柄 (HWND) 或 None
        """
        if not window_title:
            return None

        logger.info(f"查找窗口: '{window_title}', 模拟器类型: {emulator_type}")

        # 根据模拟器类型使用专门的查找方法
        if emulator_type == "ldplayer":
            return WindowFinder._find_ldplayer_window(window_title)
        elif emulator_type == "mumu":
            return WindowFinder._find_mumu_window(window_title)
        else:
            return WindowFinder._find_standard_window(window_title)
    
    @staticmethod
    def _find_ldplayer_window(window_title):
        """查找雷电模拟器窗口"""
        logger.info(f"使用雷电模拟器专用查找: '{window_title}'")
        
        user32 = ctypes.windll.user32
        
        # 如果直接是 TheRender，查找所有雷电模拟器的渲染窗口
        if window_title == "TheRender":
            return WindowFinder._find_ldplayer_render_window()
        
        # 方法1：直接查找窗口标题
        hwnd = user32.FindWindowW(None, window_title)
        if hwnd:
            logger.info(f"直接找到窗口: {hwnd}")
            return hwnd
        
        # 方法2：通过雷电模拟器主窗口查找
        found_windows = []
        
        def enum_callback(hwnd, lParam):
            try:
                # 获取窗口类名
                class_name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_name, 256)
                
                if class_name.value == "LDPlayerMainFrame":
                    # 获取窗口标题
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        title_buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, title_buff, length + 1)
                        
                        # 检查标题是否匹配（支持部分匹配）
                        if window_title in title_buff.value or title_buff.value in window_title:
                            logger.info(f"找到雷电模拟器主窗口: '{title_buff.value}' (HWND: {hwnd})")

                            # 查找渲染子窗口
                            render_hwnd = user32.FindWindowExW(hwnd, None, "RenderWindow", "TheRender")
                            if render_hwnd:
                                logger.info(f"找到雷电模拟器渲染窗口: {render_hwnd}")
                                # 修复：对于模拟器，优先返回主窗口而不是渲染窗口
                                # 因为按键消息通常需要发送到主窗口才能生效
                                logger.info(f"模拟器按键优化：返回主窗口 {hwnd} 而不是渲染窗口 {render_hwnd}")
                                found_windows.append(hwnd)
                                return False  # 停止枚举
                            else:
                                # 如果没找到渲染窗口，返回主窗口
                                found_windows.append(hwnd)
                                return False
            except Exception as e:
                logger.debug(f"枚举窗口时出错: {e}")
            return True
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        
        return found_windows[0] if found_windows else None
    
    @staticmethod
    def _find_ldplayer_render_window():
        """查找雷电模拟器的渲染窗口"""
        logger.info("查找雷电模拟器渲染窗口 TheRender")

        user32 = ctypes.windll.user32
        found_windows = []

        def enum_callback(hwnd, lParam):
            try:
                # 获取窗口类名
                class_name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_name, 256)

                if class_name.value == "LDPlayerMainFrame":
                    # 查找渲染子窗口
                    render_hwnd = user32.FindWindowExW(hwnd, None, "RenderWindow", "TheRender")
                    if render_hwnd:
                        logger.info(f"找到雷电模拟器渲染窗口: {render_hwnd}")
                        found_windows.append(render_hwnd)
            except Exception as e:
                logger.debug(f"枚举窗口时出错: {e}")
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        # 返回第一个找到的渲染窗口
        return found_windows[0] if found_windows else None

    @staticmethod
    def find_all_windows(window_title, emulator_type=None):
        """
        查找所有匹配的窗口

        Args:
            window_title: 窗口标题
            emulator_type: 模拟器类型

        Returns:
            List[int]: 所有匹配的窗口句柄列表
        """
        if not window_title:
            return []

        logger.info(f"查找所有窗口: '{window_title}', 模拟器类型: {emulator_type}")

        # 根据模拟器类型使用专门的查找方法
        if emulator_type == "ldplayer":
            return WindowFinder._find_all_ldplayer_windows(window_title)
        elif emulator_type == "mumu":
            return WindowFinder._find_all_mumu_windows(window_title)
        else:
            return WindowFinder._find_all_standard_windows(window_title)

    @staticmethod
    def _find_all_ldplayer_windows(window_title):
        """查找所有雷电模拟器窗口"""
        logger.info(f"查找所有雷电模拟器窗口: '{window_title}'")

        user32 = ctypes.windll.user32
        found_windows = []

        def enum_callback(hwnd, lParam):
            try:
                # 获取窗口类名和标题
                class_name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_name, 256)

                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    title_buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buff, length + 1)
                    current_title = title_buff.value
                else:
                    current_title = ""

                # 查找雷电模拟器主窗口
                if class_name.value == "LDPlayerMainFrame":
                    # 如果是查找TheRender，查找渲染子窗口
                    if window_title == "TheRender":
                        render_hwnd = user32.FindWindowExW(hwnd, None, "RenderWindow", "TheRender")
                        if render_hwnd:
                            logger.info(f"找到雷电模拟器渲染窗口: {render_hwnd}")
                            found_windows.append(render_hwnd)
                    else:
                        # 查找匹配标题的主窗口
                        if window_title in current_title or current_title in window_title:
                            logger.info(f"找到雷电模拟器主窗口: '{current_title}' (HWND: {hwnd})")
                            found_windows.append(hwnd)

                # 直接查找RenderWindow类的TheRender窗口
                elif class_name.value == "RenderWindow" and current_title == "TheRender":
                    if window_title == "TheRender":
                        logger.info(f"找到独立的TheRender窗口: {hwnd}")
                        found_windows.append(hwnd)

            except Exception as e:
                logger.debug(f"枚举窗口时出错: {e}")
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        logger.info(f"总共找到 {len(found_windows)} 个雷电模拟器窗口")
        return found_windows

    @staticmethod
    def _find_all_standard_windows(window_title):
        """查找所有标准窗口"""
        logger.info(f"使用标准方法查找所有窗口: '{window_title}'")

        import win32gui
        found_windows = []

        def enum_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                current_title = win32gui.GetWindowText(hwnd)
                if window_title.lower() in current_title.lower():
                    logger.info(f"找到匹配窗口: '{current_title}' (HWND: {hwnd})")
                    windows.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(enum_callback, found_windows)
        except Exception as e:
            logger.error(f"枚举窗口失败: {e}")

        return found_windows

    @staticmethod
    def _find_standard_window(window_title):
        """标准窗口查找"""
        logger.info(f"搜索 使用标准窗口查找: '{window_title}'")
        
        user32 = ctypes.windll.user32
        
        # 方法1：精确匹配
        hwnd = user32.FindWindowW(None, window_title)
        if hwnd:
            logger.info(f"成功 精确匹配找到窗口: {hwnd}")
            return hwnd
        
        # 方法2：模糊匹配
        found_windows = []
        
        def enum_callback(hwnd, lParam):
            try:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        
                        # 模糊匹配
                        if window_title.lower() in title.lower() or title.lower() in window_title.lower():
                            found_windows.append((hwnd, title))
            except Exception as e:
                logger.debug(f"枚举窗口时出错: {e}")
            return True
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        
        if found_windows:
            # 优先选择最匹配的窗口
            best_match = min(found_windows, key=lambda x: abs(len(x[1]) - len(window_title)))
            logger.info(f"成功 模糊匹配找到窗口: '{best_match[1]}' (HWND: {best_match[0]})")
            return best_match[0]
        
        logger.warning(f"错误 未找到窗口: '{window_title}'")
        return None
    
    @staticmethod
    def list_all_windows():
        """列出所有可见窗口"""
        user32 = ctypes.windll.user32
        windows = []
        
        def enum_callback(hwnd, lParam):
            try:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        
                        # 获取类名
                        class_name = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, class_name, 256)
                        
                        if title.strip():
                            windows.append({
                                'hwnd': hwnd,
                                'title': title,
                                'class_name': class_name.value
                            })
            except Exception as e:
                logger.debug(f"枚举窗口时出错: {e}")
            return True
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        
        return windows

    @staticmethod
    def _find_mumu_window(window_title):
        """查找MuMu模拟器窗口 - 直接返回渲染窗口"""
        logger.info(f"使用MuMu模拟器专用查找: '{window_title}'")

        import win32gui

        # 首先查找MuMu主窗口
        main_windows = []

        def enum_main_windows_callback(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                current_title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)

                # 检查是否是MuMu模拟器主窗口
                if (window_title in current_title or
                    ("MuMu" in current_title and window_title in current_title) or
                    (class_name in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and "MuMu" in current_title)):
                    lParam.append(hwnd)
                    logger.info(f"找到MuMu主窗口: {current_title} (HWND: {hwnd})")
            return True

        win32gui.EnumWindows(enum_main_windows_callback, main_windows)

        # 在主窗口中查找渲染子窗口
        for main_hwnd in main_windows:
            render_hwnd = WindowFinder._find_mumu_render_window(main_hwnd)
            if render_hwnd:
                logger.info(f"找到MuMu渲染窗口: HWND {render_hwnd}")
                return render_hwnd

        # 如果找不到渲染窗口，返回主窗口作为备选
        if main_windows:
            logger.warning(f"未找到MuMu渲染窗口，返回主窗口: HWND {main_windows[0]}")
            return main_windows[0]

        logger.error(f"未找到任何MuMu窗口: {window_title}")
        return None

    @staticmethod
    def _find_mumu_render_window(main_hwnd):
        """在MuMu主窗口中查找渲染子窗口"""
        import win32gui

        render_candidates = []

        def enum_child_callback(hwnd, lParam):
            try:
                class_name = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd)

                # 优先查找nemuwin类的渲染窗口
                if class_name == 'nemuwin' and 'display' in title.lower():
                    if win32gui.IsWindowVisible(hwnd):
                        rect = win32gui.GetClientRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]

                        if width > 100 and height > 100:
                            lParam.append((hwnd, width, height, class_name, title, 100))  # 最高优先级
                            logger.info(f"找到MuMu主渲染窗口: {class_name} '{title}' {width}x{height}")

                # 备选：其他可能的渲染窗口
                elif (class_name in ['Qt5156QWindowIcon'] and
                      ('device' in title.lower() or 'mumu' in title.lower())):
                    if win32gui.IsWindowVisible(hwnd):
                        rect = win32gui.GetClientRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]

                        if width > 100 and height > 100:
                            lParam.append((hwnd, width, height, class_name, title, 50))  # 中等优先级
                            logger.debug(f"找到MuMu备选渲染窗口: {class_name} '{title}' {width}x{height}")

            except:
                pass
            return True

        win32gui.EnumChildWindows(main_hwnd, enum_child_callback, render_candidates)

        if render_candidates:
            # 按优先级和大小排序：优先级高的优先，同优先级按大小排序
            render_candidates.sort(key=lambda x: (x[5], x[1] * x[2]), reverse=True)
            best_candidate = render_candidates[0]
            logger.info(f"选择MuMu渲染窗口: {best_candidate[3]} '{best_candidate[4]}' {best_candidate[1]}x{best_candidate[2]}")
            return best_candidate[0]

        logger.warning(f"未找到MuMu渲染窗口: HWND {main_hwnd}")
        return None

    @staticmethod
    def _find_all_mumu_windows(window_title):
        """查找所有MuMu模拟器窗口"""
        logger.info(f"查找所有MuMu模拟器窗口: '{window_title}'")

        found_windows = []

        def enum_windows_callback(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                current_title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)

                # 检查是否是MuMu模拟器窗口
                if (window_title in current_title or
                    ("MuMu" in current_title and window_title in current_title) or
                    (class_name in ["Qt5QWindowIcon", "Qt6QWindowIcon"] and "MuMu" in current_title)):
                    found_windows.append(hwnd)
                    logger.info(f"找到MuMu模拟器窗口: {current_title} (HWND: {hwnd})")
            return True

        win32gui.EnumWindows(enum_windows_callback, found_windows)

        logger.info(f"总共找到 {len(found_windows)} 个MuMu模拟器窗口")
        return found_windows


class LDPlayerBackgroundClicker:
    """雷电模拟器专用后台点击器"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.user32 = ctypes.windll.user32

        # Windows消息常量
        self.WM_LBUTTONDOWN = 0x0201
        self.WM_LBUTTONUP = 0x0202
        self.WM_MOUSEMOVE = 0x0200
        self.WM_SETCURSOR = 0x0020
        self.WM_MOUSEACTIVATE = 0x0021

        # 参数常量
        self.MK_LBUTTON = 0x0001
        self.HTCLIENT = 1
        self.MA_ACTIVATE = 1

    def click(self, x, y, delay=0.1):
        """
        雷电模拟器专用后台点击方法

        Args:
            x: X坐标
            y: Y坐标
            delay: 点击后延时（秒）
        """
        logger.info(f"游戏 雷电模拟器后台点击: ({x}, {y})")

        try:
            # 方法1：完整的消息序列（推荐）
            self._send_complete_click_sequence(x, y)

            if delay > 0:
                import time
                time.sleep(delay)

            return True

        except Exception as e:
            logger.error(f"雷电模拟器后台点击失败: {e}")
            return False

    def _send_complete_click_sequence(self, x, y):
        """发送完整的点击消息序列"""
        # 构造坐标参数
        lparam = (y << 16) | x

        # 1. 设置光标消息
        self._send_setcursor_message(self.WM_MOUSEACTIVATE)

        # 2. 鼠标移动到目标位置
        self.user32.PostMessageW(self.hwnd, self.WM_MOUSEMOVE, 0, lparam)

        # 3. 激活鼠标
        self._send_mouseactivate_message()

        # 4. 设置光标为按下状态
        self._send_setcursor_message(self.WM_LBUTTONDOWN)

        # 5. 鼠标按下（关键：使用MK_LBUTTON参数）
        self.user32.PostMessageW(self.hwnd, self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)

        # 6. 鼠标移动（保持按下状态）
        self.user32.PostMessageW(self.hwnd, self.WM_MOUSEMOVE, self.MK_LBUTTON, lparam)

        # 7. 鼠标释放
        self.user32.PostMessageW(self.hwnd, self.WM_LBUTTONUP, 0, lparam)

    def _send_setcursor_message(self, msg):
        """发送设置光标消息"""
        lparam = (msg << 16) | self.HTCLIENT
        self.user32.SendMessageW(self.hwnd, self.WM_SETCURSOR, self.hwnd, lparam)

    def _send_mouseactivate_message(self):
        """发送鼠标激活消息"""
        lparam = (self.WM_LBUTTONDOWN << 16) | self.HTCLIENT
        self.user32.SendMessageW(self.hwnd, self.WM_MOUSEACTIVATE, self.hwnd, lparam)




