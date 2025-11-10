#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
坐标选择器 - 支持窗口激活的坐标获取工具
"""

import logging
import ctypes
from ctypes import wintypes
import sys
import os
from typing import Optional, Tuple, List
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QMessageBox, QApplication
from PySide6.QtCore import Signal, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QBrush

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.window_finder import WindowFinder

# 导入通用坐标系统
from utils.universal_coordinate_system import (
    get_universal_coordinate_system, create_coordinate_from_selector,
    CoordinateSource
)
from utils.universal_resolution_adapter import get_universal_adapter

logger = logging.getLogger(__name__)

try:
    import win32gui
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    logger.warning("pywin32 not available, coordinate selector may not work properly")

class CoordinateSelectorOverlay(QWidget):
    """坐标选择器覆盖层"""
    
    coordinate_selected = Signal(int, int)  # x, y
    
    def __init__(self, target_window_hwnd: int, parent=None):
        super().__init__(None)  # 独立窗口
        self.target_window_hwnd = target_window_hwnd  # 目标窗口句柄
        self.target_hwnd = None
        self.window_info = None
        self.target_window_title = ""  # 从句柄获取的窗口标题，仅用于显示
        
        # 选择状态
        self.selecting = False
        self.click_pos = QPoint()
        
        # 设置窗口属性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint
        )
        
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        logger.info("靶心 创建坐标选择器覆盖层")
        
        # 初始化
        self.setup_target_window()
        
        # 显示提示信息
        logger.info("靶心 坐标选择器已启动")
        logger.info("编辑 使用说明:")
        logger.info("   - 在绿色边框的目标窗口内点击选择坐标")
        logger.info("   - 右键点击或按ESC键取消选择")
        logger.info("   - 选择完成后会自动填充坐标参数")
    
    def setup_target_window(self):
        """设置目标窗口"""
        if not PYWIN32_AVAILABLE:
            logger.error("需要安装pywin32库")
            return False
        
        # 使用传入的窗口句柄
        target_hwnd = self.target_window_hwnd
        if not target_hwnd:
            logger.error(f"无效的窗口句柄: {target_hwnd}")
            return False

        # 获取窗口标题用于显示
        try:
            import win32gui
            self.target_window_title = win32gui.GetWindowText(target_hwnd)
            logger.info(f"使用窗口句柄: {target_hwnd}, 标题: {self.target_window_title}")
        except Exception as e:
            logger.warning(f"获取窗口标题失败: {e}")
            self.target_window_title = f"窗口{target_hwnd}"
        
        # 获取窗口信息
        self.window_info = self._get_window_info(target_hwnd)
        if not self.window_info:
            logger.error("无法获取窗口信息")
            return False
        
        # 激活目标窗口
        self._activate_target_window(target_hwnd)
        
        # 设置覆盖层几何
        self._setup_overlay_geometry()
        
        return True
    

    
    def _get_window_info(self, hwnd: int):
        """获取窗口信息（包括DPI处理）"""
        try:
            # 获取窗口矩形
            window_rect = win32gui.GetWindowRect(hwnd)
            client_rect = win32gui.GetClientRect(hwnd)
            client_screen_pos = win32gui.ClientToScreen(hwnd, (0, 0))

            # 获取系统DPI信息
            user32 = ctypes.windll.user32
            system_dpi = 96
            window_dpi = 96

            try:
                # 获取窗口DPI
                if hasattr(user32, 'GetDpiForWindow'):
                    window_dpi = user32.GetDpiForWindow(hwnd)

                # 获取系统DPI
                hdc = user32.GetDC(0)
                if hdc:
                    system_dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                    user32.ReleaseDC(0, hdc)

            except Exception as e:
                logger.warning(f"获取DPI失败: {e}")

            # 计算缩放因子
            window_scale_factor = window_dpi / 96.0
            system_scale_factor = system_dpi / 96.0

            # 获取Qt的屏幕信息
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            qt_dpi = screen.logicalDotsPerInch()
            qt_device_pixel_ratio = screen.devicePixelRatio()

            # 对于雷电模拟器，使用窗口矩形而不是客户区
            window_title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)

            if (self.target_window_title == "TheRender" or
                "雷电" in window_title or
                class_name == "RenderWindow"):
                logger.info(" 检测到雷电模拟器渲染窗口，使用窗口矩形")
                # 对于雷电模拟器的渲染窗口，直接使用窗口矩形
                client_screen_pos = (window_rect[0], window_rect[1])
                client_width = window_rect[2] - window_rect[0]
                client_height = window_rect[3] - window_rect[1]
            else:
                # 其他窗口使用客户区
                client_width = client_rect[2] - client_rect[0]
                client_height = client_rect[3] - client_rect[1]

            window_info = {
                'hwnd': hwnd,
                'window_rect': window_rect,
                'client_rect': client_rect,
                'client_screen_pos': client_screen_pos,
                'client_width': client_width,
                'client_height': client_height,
                'window_dpi': window_dpi,
                'system_dpi': system_dpi,
                'window_scale_factor': window_scale_factor,
                'system_scale_factor': system_scale_factor,
                'qt_dpi': qt_dpi,
                'qt_device_pixel_ratio': qt_device_pixel_ratio,
                'window_title': window_title,
                'class_name': class_name
            }

            logger.info(f"窗口信息: 客户区位置({client_screen_pos}), "
                       f"尺寸({window_info['client_width']}x{window_info['client_height']})")
            logger.info(f"DPI信息: 窗口DPI={window_dpi}, 系统DPI={system_dpi}, Qt DPI={qt_dpi:.1f}")
            logger.info(f"缩放因子: 窗口={window_scale_factor:.2f}, 系统={system_scale_factor:.2f}, Qt={qt_device_pixel_ratio:.2f}")

            return window_info

        except Exception as e:
            logger.error(f"获取窗口信息失败: {e}")
            return None
    
    def _activate_target_window(self, hwnd: int):
        """激活并置顶目标窗口（如果是渲染窗口则置顶主窗口）"""
        try:
            # 获取需要置顶的窗口句柄（可能是主窗口）
            target_hwnd = self._get_window_to_activate(hwnd)

            user32 = ctypes.windll.user32

            # 检查窗口是否最小化，如果是则恢复
            if user32.IsIconic(target_hwnd):
                logger.info("目标窗口已最小化，正在恢复...")
                user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                import time
                time.sleep(0.2)  # 等待窗口恢复

            # 将窗口置于前台
            user32.SetForegroundWindow(target_hwnd)

            # 激活窗口
            user32.SetActiveWindow(target_hwnd)

            # 确保窗口在最顶层
            user32.BringWindowToTop(target_hwnd)

            if target_hwnd != hwnd:
                logger.info(f"成功 已激活并置顶主窗口: {target_hwnd} (原绑定窗口: {hwnd})")
            else:
                logger.info(f"成功 已激活并置顶目标窗口: {self.target_window_title}")

        except Exception as e:
            logger.warning(f"激活目标窗口失败: {e}")
            # 即使激活失败也继续执行，不影响坐标选择功能

    def _force_target_window_top(self):
        """多次尝试强制目标窗口置顶"""
        if not self.window_info:
            return

        hwnd = self.window_info['hwnd']
        # 获取需要置顶的窗口句柄（可能是主窗口）
        target_hwnd = self._get_window_to_activate(hwnd)

        def force_top():
            """强制置顶函数"""
            try:
                user32 = ctypes.windll.user32

                # 强制将目标窗口置于最顶层
                user32.SetWindowPos(
                    target_hwnd, -1,  # HWND_TOPMOST
                    0, 0, 0, 0,
                    0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                )
                # 强制获得焦点
                user32.SetForegroundWindow(target_hwnd)
                if target_hwnd != hwnd:
                    logger.debug(f"强制置顶主窗口: {target_hwnd} (原绑定窗口: {hwnd})")
                else:
                    logger.debug(f"强制置顶目标窗口: {self.target_window_title}")
            except Exception as e:
                logger.warning(f"强制置顶失败: {e}")

        # 多次尝试确保目标窗口在最顶层
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, force_top)
        QTimer.singleShot(150, force_top)
        QTimer.singleShot(300, force_top)
        QTimer.singleShot(500, force_top)  # 额外的尝试

        logger.info("靶心 已启动多次强制置顶目标窗口")

    def _get_window_to_activate(self, hwnd: int) -> int:
        """获取需要激活的窗口句柄（如果是渲染窗口则返回主窗口）"""
        try:
            # 检测是否是MuMu渲染窗口
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

            if is_emulator and emulator_type == "mumu":
                # 如果是MuMu渲染窗口，查找对应的主窗口
                from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                emulator_window = EmulatorWindowInputSimulator(hwnd, "mumu", "background")
                main_hwnd = emulator_window._get_mumu_parent_window()
                if main_hwnd:
                    logger.debug(f"从渲染窗口 {hwnd} 找到主窗口 {main_hwnd} 用于置顶")
                    return main_hwnd

            # 如果不是渲染窗口或找不到主窗口，返回原窗口
            return hwnd

        except Exception as e:
            logger.debug(f"获取激活窗口失败: {e}")
            return hwnd

    def _setup_overlay_geometry(self):
        """设置覆盖层几何"""
        if not self.window_info:
            return
        
        # 覆盖整个屏幕
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        self.setGeometry(screen_geometry)
        
        logger.info(f"覆盖层几何设置: {screen_geometry}")
    
    def _get_relative_coordinates(self, qt_screen_pos: QPoint) -> QPoint:
        """将Qt屏幕坐标转换为窗口客户区相对坐标（现在直接绑定渲染窗口，无需特殊处理）"""
        if not self.window_info:
            return qt_screen_pos

        try:
            # 使用Win32 API直接转换屏幕坐标到客户区坐标
            hwnd = self.window_info['hwnd']
            qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']

            # 将Qt逻辑坐标转换为Win32物理坐标
            win32_screen_x = int(qt_screen_pos.x() * qt_device_pixel_ratio)
            win32_screen_y = int(qt_screen_pos.y() * qt_device_pixel_ratio)

            # 使用ScreenToClient直接转换为客户区坐标
            point = wintypes.POINT(win32_screen_x, win32_screen_y)
            result = ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point))

            if result:
                client_x, client_y = point.x, point.y
                logger.debug(f"坐标转换: 屏幕({win32_screen_x}, {win32_screen_y}) -> 客户区({client_x}, {client_y})")
                return QPoint(client_x, client_y)
            else:
                logger.warning("ScreenToClient转换失败，使用备用方法")
                # 备用方法：使用原有的计算方式
                client_screen_pos = self.window_info['client_screen_pos']
                relative_x = win32_screen_x - client_screen_pos[0]
                relative_y = win32_screen_y - client_screen_pos[1]
                return QPoint(relative_x, relative_y)

        except Exception as e:
            logger.error(f"坐标转换异常: {e}")
            # 回退到原有方法
            client_screen_pos = self.window_info['client_screen_pos']
            qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']
            win32_screen_x = int(qt_screen_pos.x() * qt_device_pixel_ratio)
            win32_screen_y = int(qt_screen_pos.y() * qt_device_pixel_ratio)
            relative_x = win32_screen_x - client_screen_pos[0]
            relative_y = win32_screen_y - client_screen_pos[1]
            return QPoint(relative_x, relative_y)




    
    def _is_point_in_target_window(self, qt_screen_pos: QPoint) -> bool:
        """检查点是否在目标窗口客户区内（使用Qt逻辑坐标）"""
        if not self.window_info:
            return False

        # 使用Qt设备像素比进行坐标转换
        client_screen_pos = self.window_info['client_screen_pos']
        client_width = self.window_info['client_width']
        client_height = self.window_info['client_height']
        qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']

        # Win32坐标转换为Qt逻辑坐标
        qt_client_x = int(client_screen_pos[0] / qt_device_pixel_ratio)
        qt_client_y = int(client_screen_pos[1] / qt_device_pixel_ratio)
        qt_client_width = int(client_width / qt_device_pixel_ratio)
        qt_client_height = int(client_height / qt_device_pixel_ratio)

        return (qt_client_x <= qt_screen_pos.x() <= qt_client_x + qt_client_width and
                qt_client_y <= qt_screen_pos.y() <= qt_client_y + qt_client_height)
    
    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制一个几乎透明的背景，确保能接收鼠标事件但不遮挡内容
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))  # 几乎透明但不是完全透明
        
        # 绘制目标窗口边框
        if self.window_info:
            client_screen_pos = self.window_info['client_screen_pos']
            client_width = self.window_info['client_width']
            client_height = self.window_info['client_height']
            qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']

            # Win32物理坐标转换为Qt逻辑坐标
            qt_x = int(client_screen_pos[0] / qt_device_pixel_ratio)
            qt_y = int(client_screen_pos[1] / qt_device_pixel_ratio)
            qt_width = int(client_width / qt_device_pixel_ratio)
            qt_height = int(client_height / qt_device_pixel_ratio)

            target_rect = QRect(qt_x, qt_y, qt_width, qt_height)

            # 绘制绿色边框
            pen = QPen(QColor(0, 255, 0), 4)  # 稍微粗一点便于观察
            painter.setPen(pen)
            painter.drawRect(target_rect)

            # 显示提示文本
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(target_rect.topLeft() + QPoint(10, 25),
                           f"目标窗口: {self.target_window_title}")
            painter.drawText(target_rect.topLeft() + QPoint(10, 50),
                           "点击选择坐标位置")
        
        # 绘制十字光标（点击后显示）
        # 检查点击位置是否有效（不是初始的(0,0)位置）
        if not self.click_pos.isNull() and (self.click_pos.x() != 0 or self.click_pos.y() != 0):
            # 绘制适中大小的十字光标
            cross_size = 15  # 减小十字光标大小

            # 绘制白色外边框（增强可见性）
            pen_outline = QPen(QColor(255, 255, 255), 3)  # 减小外边框粗细
            painter.setPen(pen_outline)
            painter.drawLine(self.click_pos.x() - cross_size, self.click_pos.y(),
                           self.click_pos.x() + cross_size, self.click_pos.y())
            painter.drawLine(self.click_pos.x(), self.click_pos.y() - cross_size,
                           self.click_pos.x(), self.click_pos.y() + cross_size)

            # 绘制红色内部十字
            pen_inner = QPen(QColor(255, 0, 0), 1)  # 减小内部线条粗细
            painter.setPen(pen_inner)
            painter.drawLine(self.click_pos.x() - cross_size, self.click_pos.y(),
                           self.click_pos.x() + cross_size, self.click_pos.y())
            painter.drawLine(self.click_pos.x(), self.click_pos.y() - cross_size,
                           self.click_pos.x(), self.click_pos.y() + cross_size)

            # 绘制中心点
            painter.setBrush(QBrush(QColor(255, 0, 0)))
            painter.drawEllipse(self.click_pos, 2, 2)  # 减小中心点大小

            # 显示坐标信息（带背景）
            if self.window_info:
                relative_pos = self._get_relative_coordinates(self.click_pos)
                coord_text = f"坐标: ({relative_pos.x()}, {relative_pos.y()})"

                # 绘制文本背景
                text_rect = painter.fontMetrics().boundingRect(coord_text)
                text_pos = self.click_pos + QPoint(35, -10)
                bg_rect = text_rect.translated(text_pos)
                bg_rect.adjust(-5, -2, 5, 2)

                painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawRect(bg_rect)

                # 绘制文本
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawText(text_pos, coord_text)
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在目标窗口内
            if self._is_point_in_target_window(event.pos()):
                self.click_pos = event.pos()
                logger.info(f"设置点击位置: {self.click_pos}")
                self.update()  # 立即更新显示十字光标

                # 转换为相对坐标
                relative_pos = self._get_relative_coordinates(event.pos())

                logger.info(f"坐标选择完成: 屏幕({event.pos().x()}, {event.pos().y()}) -> 客户区({relative_pos.x()}, {relative_pos.y()})")

                # 验证坐标转换是否正确
                if self.window_info:
                    hwnd = self.window_info['hwnd']
                    logger.debug(f"目标窗口句柄: {hwnd}")

                    # 验证客户区坐标是否在合理范围内
                    try:
                        import win32gui
                        client_rect = win32gui.GetClientRect(hwnd)
                        client_width = client_rect[2] - client_rect[0]
                        client_height = client_rect[3] - client_rect[1]

                        if 0 <= relative_pos.x() <= client_width and 0 <= relative_pos.y() <= client_height:
                            logger.debug(f"✅ 客户区坐标有效: ({relative_pos.x()}, {relative_pos.y()}) 在范围 {client_width}x{client_height} 内")
                        else:
                            logger.warning(f"⚠️ 客户区坐标可能无效: ({relative_pos.x()}, {relative_pos.y()}) 超出范围 {client_width}x{client_height}")
                    except Exception as e:
                        logger.debug(f"坐标验证失败: {e}")

                # 直接发射坐标信号（不使用通用坐标系统标准化）
                self.coordinate_selected.emit(relative_pos.x(), relative_pos.y())

                # 延迟关闭，让用户能看到十字光标
                from PySide6.QtCore import QTimer
                QTimer.singleShot(300, self.close)  # 300ms后关闭，减少等待时间
            else:
                logger.warning("点击位置不在目标窗口内")

        elif event.button() == Qt.MouseButton.RightButton:
            logger.info("右键点击，取消选择")
            self.close()
    
    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("ESC键退出")
            self.close()

class CoordinateSelectorWidget(QWidget):
    """坐标选择器控件"""

    coordinate_selected = Signal(int, int)  # x, y
    selection_started = Signal()  # 选择开始信号
    selection_finished = Signal()  # 选择结束信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_window_hwnd = None  # 目标窗口句柄
        self.current_coordinate = (0, 0)

        self.setup_ui()
        self._update_button_text()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 选择按钮
        self.select_button = QPushButton("点击获取坐标")
        self.select_button.clicked.connect(self.start_selection)
        layout.addWidget(self.select_button)

    def _update_button_text(self):
        """更新按钮文本以显示当前坐标"""
        if hasattr(self, 'select_button'):
            x, y = self.current_coordinate
            if x == 0 and y == 0:
                self.select_button.setText("点击获取坐标")
            else:
                self.select_button.setText(f"坐标: ({x}, {y})")

    def set_coordinate(self, x: int, y: int):
        """设置坐标值"""
        self.current_coordinate = (x, y)
        self._update_button_text()
        logger.info(f"坐标选择器坐标已设置为: ({x}, {y})")
    
    def _get_bound_window_from_editor(self) -> Optional[str]:
        """从编辑器获取绑定的窗口（支持多窗口模式）"""
        try:
            logger.info("搜索 开始获取绑定的窗口标题...")

            # 向上查找主窗口，直到找到有config或runner属性的窗口
            current_widget = self.parent()
            level = 0

            while current_widget and level < 10:  # 最多向上查找10层
                logger.info(f"搜索 第{level}层窗口: {current_widget}")
                logger.info(f"搜索 第{level}层窗口类型: {type(current_widget)}")

                # 检查是否有bound_windows属性（多窗口模式）
                if hasattr(current_widget, 'bound_windows'):
                    bound_windows = current_widget.bound_windows
                    if bound_windows and len(bound_windows) > 0:
                        # 获取第一个启用的窗口
                        for window_info in bound_windows:
                            if window_info.get('enabled', True):
                                window_title = window_info.get('title')
                                if window_title:
                                    logger.info(f"搜索 从多窗口绑定列表获取第一个启用窗口: {window_title}")
                                    return window_title

                        # 如果没有启用的窗口，使用第一个窗口
                        first_window = bound_windows[0]
                        window_title = first_window.get('title')
                        if window_title:
                            logger.info(f"搜索 从多窗口绑定列表获取第一个窗口: {window_title}")
                            return window_title

                # 检查是否是主窗口（任务编辑器）
                if hasattr(current_widget, 'config'):
                    logger.info(f"搜索 第{level}层窗口有config属性")
                    config = current_widget.config
                    target_window_title = config.get('target_window_title')
                    if target_window_title:
                        logger.info(f"搜索 从第{level}层窗口配置获取目标窗口: {target_window_title}")
                        return target_window_title
                    else:
                        logger.info(f"搜索 第{level}层窗口config中没有target_window_title")

                # 检查是否有runner属性
                if hasattr(current_widget, 'runner'):
                    logger.info(f"搜索 第{level}层窗口有runner属性")
                    runner = current_widget.runner
                    if hasattr(runner, 'target_window_title'):
                        target_window_title = runner.target_window_title
                        logger.info(f"搜索 从第{level}层窗口runner获取目标窗口: {target_window_title}")
                        if target_window_title:
                            return target_window_title
                    else:
                        logger.info(f"搜索 第{level}层窗口runner没有target_window_title属性")

                # 检查是否有直接的target_window_title属性
                if hasattr(current_widget, 'target_window_title'):
                    target_window_title = current_widget.target_window_title
                    logger.info(f"搜索 从第{level}层窗口属性获取目标窗口: {target_window_title}")
                    if target_window_title:
                        return target_window_title

                # 向上查找父窗口
                current_widget = current_widget.parent()
                level += 1

            logger.info(f"搜索 查找了{level}层窗口，未找到绑定的目标窗口")
            return None

        except Exception as e:
            logger.error(f"获取编辑器绑定窗口时出错: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def start_selection(self):
        """开始坐标选择"""
        # 检查是否已经有活动的覆盖层
        if hasattr(self, '_current_overlay') and self._current_overlay:
            logger.info("已有活动的坐标选择覆盖层，跳过重复创建")
            return

        # 清理之前的覆盖层（如果存在）
        self._cleanup_previous_overlay()

        # 发出选择开始信号
        logger.info("靶心 发出坐标选择开始信号")
        self.selection_started.emit()

        # 如果没有设置目标窗口句柄，尝试自动获取编辑器绑定的窗口
        if not self.target_window_hwnd:
            self.target_window_hwnd = self._get_bound_window_from_editor()
            if not self.target_window_hwnd:
                QMessageBox.warning(self, "警告", "未找到编辑器绑定的窗口，请先在编辑器中绑定目标窗口")
                return

            # 获取窗口标题用于显示
            try:
                import win32gui
                window_title = win32gui.GetWindowText(self.target_window_hwnd)
                self.select_button.setText(f"获取坐标 (已绑定: {window_title})")
                logger.info(f"靶心 自动获取编辑器绑定的窗口句柄: {self.target_window_hwnd}, 标题: {window_title}")
            except Exception as e:
                logger.error(f"从句柄获取窗口标题失败: {e}")
                self.select_button.setText(f"获取坐标 (已绑定: 窗口{self.target_window_hwnd})")

        # 创建选择覆盖层
        overlay = CoordinateSelectorOverlay(self.target_window_hwnd)
        # 直接连接到内部处理方法，避免重复发射信号
        overlay.coordinate_selected.connect(self._on_coordinate_selected)

        # 保存覆盖层引用
        self._current_overlay = overlay
        
        if overlay.setup_target_window():
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()

            # 多次尝试强制置顶目标窗口，确保不被覆盖层遮挡
            overlay._force_target_window_top()
        else:
            QMessageBox.critical(self, "错误", "无法设置目标窗口")

    def _clear_overlay_reference(self):
        """清理覆盖层引用"""
        if hasattr(self, '_current_overlay'):
            logger.info("清理覆盖层引用")
            self._current_overlay = None

    def _cleanup_previous_overlay(self):
        """清理之前的覆盖层"""
        if hasattr(self, '_current_overlay') and self._current_overlay:
            overlay = self._current_overlay
            logger.info("扫帚 清理之前的坐标选择覆盖层")
            # 断开信号连接，避免触发不必要的信号
            try:
                overlay.coordinate_selected.disconnect()
                logger.info("成功 已断开坐标选择覆盖层信号连接")
            except Exception as e:
                logger.warning(f"断开信号连接失败: {e}")

            # 直接删除覆盖层
            overlay.hide()
            overlay.deleteLater()
            logger.info("成功 坐标选择覆盖层已隐藏并标记删除")

            # 清理引用
            self._current_overlay = None

    def _on_coordinate_selected(self, x: int, y: int):
        """坐标选择完成（直接使用客户区坐标）"""
        logger.info(f"坐标选择完成: ({x}, {y})")

        try:
            # 保存原始坐标
            self.set_coordinate(x, y)

            # 发射原始坐标信号
            self.coordinate_selected.emit(x, y)

            # 发出选择结束信号
            self.selection_finished.emit()

            logger.info(f"坐标处理完成: ({x}, {y})")

        except Exception as e:
            logger.error(f"处理坐标选择失败: {e}")
            # 确保即使出错也发射信号
            try:
                self.coordinate_selected.emit(x, y)
                self.selection_finished.emit()
            except:
                pass

    def _get_bound_window_hwnd(self) -> Optional[int]:
        """获取当前绑定的窗口句柄"""
        try:
            # 向上查找主窗口，获取绑定的窗口信息
            current_widget = self.parent()
            level = 0
            max_levels = 10

            while current_widget and level < max_levels:
                # 检查是否有config属性（主窗口）
                if hasattr(current_widget, 'config'):
                    config = current_widget.config

                    # 单窗口模式
                    if hasattr(config, 'target_window_title') and config.target_window_title:
                        return self._find_window_by_title(config.target_window_title)

                    # 多窗口模式
                    if hasattr(config, 'bound_windows') and config.bound_windows:
                        enabled_windows = [w for w in config.bound_windows if w.get('enabled', True)]
                        if enabled_windows:
                            return enabled_windows[0].get('hwnd')

                # 检查是否有runner属性
                if hasattr(current_widget, 'runner') and hasattr(current_widget.runner, 'config'):
                    config = current_widget.runner.config

                    if hasattr(config, 'target_window_title') and config.target_window_title:
                        return self._find_window_by_title(config.target_window_title)

                    if hasattr(config, 'bound_windows') and config.bound_windows:
                        enabled_windows = [w for w in config.bound_windows if w.get('enabled', True)]
                        if enabled_windows:
                            return enabled_windows[0].get('hwnd')

                current_widget = current_widget.parent()
                level += 1

            return None

        except Exception as e:
            logger.error(f"获取绑定窗口句柄失败: {e}")
            return None



    def get_coordinate(self) -> Tuple[int, int]:
        """获取当前坐标"""
        return self.current_coordinate


class MultiPointCoordinateSelectorOverlay(QWidget):
    """多点坐标选择器覆盖层 - 支持连续获取多个坐标点"""

    coordinates_selected = Signal(list)  # 发射坐标点列表 [(x1, y1), (x2, y2), ...]

    def __init__(self, target_window_hwnd: int, parent=None):
        super().__init__(None)  # 独立窗口
        self.target_window_hwnd = target_window_hwnd
        self.target_hwnd = None
        self.window_info = None
        self.target_window_title = ""

        # 坐标点列表
        self.coordinate_points = []
        self.click_positions = []  # 屏幕坐标位置，用于绘制

        self._setup_overlay()
        if not self._setup_target_window():
            logger.error("设置目标窗口失败")
            return

    def _setup_overlay(self):
        """设置覆盖层"""
        # 设置为全屏覆盖层
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # 设置全屏
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # 设置鼠标追踪
        self.setMouseTracking(True)

    def _setup_target_window(self):
        """设置目标窗口"""
        if not PYWIN32_AVAILABLE:
            logger.error("需要安装pywin32库")
            return False

        # 使用传入的窗口句柄
        target_hwnd = self.target_window_hwnd
        if not target_hwnd:
            logger.error(f"无效的窗口句柄: {target_hwnd}")
            return False

        # 获取窗口标题用于显示
        try:
            import win32gui
            self.target_window_title = win32gui.GetWindowText(target_hwnd)
            logger.info(f"使用窗口句柄: {target_hwnd}, 标题: {self.target_window_title}")
        except Exception as e:
            logger.warning(f"获取窗口标题失败: {e}")
            self.target_window_title = f"窗口{target_hwnd}"

        # 获取窗口信息
        self.window_info = self._get_window_info(target_hwnd)
        if not self.window_info:
            logger.error("无法获取窗口信息")
            return False

        # 激活目标窗口
        self._activate_target_window(target_hwnd)

        # 设置覆盖层几何
        self._setup_overlay_geometry()

        return True

    def _get_window_info(self, hwnd: int) -> dict:
        """获取窗口信息"""
        try:
            if not PYWIN32_AVAILABLE:
                return None

            import win32gui
            if not win32gui.IsWindow(hwnd):
                return None

            # 获取窗口标题
            window_title = win32gui.GetWindowText(hwnd)

            # 获取客户区坐标（相对于窗口）
            client_rect = win32gui.GetClientRect(hwnd)
            client_width = client_rect[2] - client_rect[0]
            client_height = client_rect[3] - client_rect[1]

            # 将客户区左上角转换为屏幕坐标
            client_top_left = win32gui.ClientToScreen(hwnd, (0, 0))

            # 获取Qt的设备像素比例
            try:
                qt_device_pixel_ratio = QApplication.primaryScreen().devicePixelRatio()
            except:
                qt_device_pixel_ratio = 1.0

            logger.debug(f"窗口信息: 标题={window_title}, 客户区屏幕位置={client_top_left}, "
                        f"客户区大小=({client_width}, {client_height}), DPI比例={qt_device_pixel_ratio}")

            return {
                'hwnd': hwnd,
                'title': window_title,
                'client_screen_pos': client_top_left,
                'client_width': client_width,
                'client_height': client_height,
                'qt_device_pixel_ratio': qt_device_pixel_ratio
            }
        except Exception as e:
            logger.error(f"获取窗口信息失败: {e}")
            return None

    def _setup_overlay_geometry(self):
        """设置覆盖层几何"""
        try:
            # 设置为全屏覆盖
            screen = QApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            logger.info(f"覆盖层几何设置为全屏: {screen}")
        except Exception as e:
            logger.error(f"设置覆盖层几何失败: {e}")

    def _activate_target_window(self, hwnd: int):
        """激活并置顶目标窗口（如果是渲染窗口则置顶主窗口）"""
        try:
            # 获取需要置顶的窗口句柄（可能是主窗口）
            target_hwnd = self._get_window_to_activate(hwnd)

            user32 = ctypes.windll.user32

            # 检查窗口是否最小化，如果是则恢复
            if user32.IsIconic(target_hwnd):
                logger.info("目标窗口已最小化，正在恢复...")
                user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                import time
                time.sleep(0.2)  # 等待窗口恢复

            # 将窗口置于前台
            user32.SetForegroundWindow(target_hwnd)

            # 激活窗口
            user32.SetActiveWindow(target_hwnd)

            # 确保窗口在最顶层
            user32.BringWindowToTop(target_hwnd)

            if target_hwnd != hwnd:
                logger.info(f"成功 已激活并置顶主窗口: {target_hwnd} (原绑定窗口: {hwnd})")
            else:
                logger.info(f"成功 已激活并置顶目标窗口: {self.target_window_title}")

        except Exception as e:
            logger.warning(f"激活目标窗口失败: {e}")
            # 即使激活失败也继续执行，不影响坐标选择功能

    def _get_window_to_activate(self, hwnd: int) -> int:
        """获取需要激活的窗口句柄（如果是渲染窗口则返回主窗口）"""
        try:
            # 检测是否是MuMu渲染窗口
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

            if is_emulator and emulator_type == "mumu":
                # 如果是MuMu渲染窗口，查找对应的主窗口
                from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                emulator_window = EmulatorWindowInputSimulator(hwnd, "mumu", "background")
                main_hwnd = emulator_window._get_mumu_parent_window()
                if main_hwnd:
                    logger.debug(f"从渲染窗口 {hwnd} 找到主窗口 {main_hwnd} 用于置顶")
                    return main_hwnd

            # 如果不是渲染窗口或找不到主窗口，返回原窗口
            return hwnd

        except Exception as e:
            logger.debug(f"获取激活窗口失败: {e}")
            return hwnd

    def _force_target_window_top(self):
        """多次尝试强制目标窗口置顶"""
        if not self.window_info:
            return

        hwnd = self.window_info['hwnd']
        # 获取需要置顶的窗口句柄（可能是主窗口）
        target_hwnd = self._get_window_to_activate(hwnd)

        def force_top():
            """强制置顶函数"""
            try:
                user32 = ctypes.windll.user32

                # 强制将目标窗口置于最顶层
                user32.SetWindowPos(
                    target_hwnd, -1,  # HWND_TOPMOST
                    0, 0, 0, 0,
                    0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                )
                # 强制获得焦点
                user32.SetForegroundWindow(target_hwnd)
                if target_hwnd != hwnd:
                    logger.debug(f"强制置顶主窗口: {target_hwnd} (原绑定窗口: {hwnd})")
                else:
                    logger.debug(f"强制置顶目标窗口: {self.target_window_title}")
            except Exception as e:
                logger.warning(f"强制置顶失败: {e}")

        # 多次尝试确保目标窗口在最顶层
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, force_top)
        QTimer.singleShot(150, force_top)
        QTimer.singleShot(300, force_top)
        QTimer.singleShot(500, force_top)  # 额外的尝试

        logger.info("靶心 已启动多次强制置顶目标窗口")

    def _is_point_in_target_window(self, pos: QPoint) -> bool:
        """检查点击位置是否在目标窗口内"""
        if not self.window_info:
            return False

        client_screen_pos = self.window_info['client_screen_pos']
        client_width = self.window_info['client_width']
        client_height = self.window_info['client_height']
        qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']

        # Win32物理坐标转换为Qt逻辑坐标
        qt_client_x = int(client_screen_pos[0] / qt_device_pixel_ratio)
        qt_client_y = int(client_screen_pos[1] / qt_device_pixel_ratio)
        qt_client_width = int(client_width / qt_device_pixel_ratio)
        qt_client_height = int(client_height / qt_device_pixel_ratio)

        return (qt_client_x <= pos.x() <= qt_client_x + qt_client_width and
                qt_client_y <= pos.y() <= qt_client_y + qt_client_height)

    def _get_relative_coordinates(self, qt_screen_pos: QPoint) -> QPoint:
        """将Qt屏幕坐标转换为窗口客户区相对坐标"""
        if not self.window_info:
            return qt_screen_pos

        try:
            # 使用Win32 API直接转换屏幕坐标到客户区坐标
            hwnd = self.window_info['hwnd']
            qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']

            # 将Qt逻辑坐标转换为Win32物理坐标
            win32_screen_x = int(qt_screen_pos.x() * qt_device_pixel_ratio)
            win32_screen_y = int(qt_screen_pos.y() * qt_device_pixel_ratio)

            # 使用ScreenToClient直接转换为客户区坐标
            point = wintypes.POINT(win32_screen_x, win32_screen_y)
            result = ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point))

            if result:
                client_x, client_y = point.x, point.y
                logger.debug(f"坐标转换: 屏幕({win32_screen_x}, {win32_screen_y}) -> 客户区({client_x}, {client_y})")
                return QPoint(client_x, client_y)
            else:
                logger.warning("ScreenToClient转换失败，使用备用方法")
                # 备用方法：使用原有的计算方式
                client_screen_pos = self.window_info['client_screen_pos']
                relative_x = win32_screen_x - client_screen_pos[0]
                relative_y = win32_screen_y - client_screen_pos[1]
                return QPoint(relative_x, relative_y)

        except Exception as e:
            logger.error(f"坐标转换异常: {e}")
            # 回退到原有方法
            client_screen_pos = self.window_info['client_screen_pos']
            qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']
            win32_screen_x = int(qt_screen_pos.x() * qt_device_pixel_ratio)
            win32_screen_y = int(qt_screen_pos.y() * qt_device_pixel_ratio)
            relative_x = win32_screen_x - client_screen_pos[0]
            relative_y = win32_screen_y - client_screen_pos[1]
            return QPoint(relative_x, relative_y)

    def paintEvent(self, event):
        """绘制覆盖层"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制几乎透明的背景，确保能接收鼠标事件但不遮挡内容
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))  # 几乎透明但不是完全透明

        # 绘制目标窗口边框
        if self.window_info:
            client_screen_pos = self.window_info['client_screen_pos']
            client_width = self.window_info['client_width']
            client_height = self.window_info['client_height']
            qt_device_pixel_ratio = self.window_info['qt_device_pixel_ratio']

            # Win32物理坐标转换为Qt逻辑坐标
            qt_x = int(client_screen_pos[0] / qt_device_pixel_ratio)
            qt_y = int(client_screen_pos[1] / qt_device_pixel_ratio)
            qt_width = int(client_width / qt_device_pixel_ratio)
            qt_height = int(client_height / qt_device_pixel_ratio)

            target_rect = QRect(qt_x, qt_y, qt_width, qt_height)

            # 绘制绿色边框
            pen = QPen(QColor(0, 255, 0), 4)  # 稍微粗一点便于观察
            painter.setPen(pen)
            painter.drawRect(target_rect)

            # 显示提示文本
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(target_rect.topLeft() + QPoint(10, 25),
                           f"目标窗口: {self.target_window_title}")
            painter.drawText(target_rect.topLeft() + QPoint(10, 50),
                           "左键点击添加坐标点")

        # 绘制已选择的坐标点
        for i, pos in enumerate(self.click_positions):
            # 绘制十字光标
            pen = QPen(QColor(255, 0, 0), 2)
            painter.setPen(pen)

            # 十字光标
            painter.drawLine(pos.x() - 10, pos.y(), pos.x() + 10, pos.y())
            painter.drawLine(pos.x(), pos.y() - 10, pos.x(), pos.y() + 10)

            # 绘制点编号
            painter.setPen(QColor(255, 255, 0))
            painter.drawText(pos + QPoint(15, -5), f"点{i+1}")

        # 绘制提示信息
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(20, 30, f"已选择 {len(self.coordinate_points)} 个坐标点")
        painter.drawText(20, 50, "左键点击: 添加坐标点")
        painter.drawText(20, 70, "右键点击: 删除最后一个点")
        painter.drawText(20, 90, "ESC键: 完成选择")
        painter.drawText(20, 110, "Ctrl+Z: 撤销上一个点")

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在目标窗口内
            if self._is_point_in_target_window(event.pos()):
                # 转换为相对坐标
                relative_pos = self._get_relative_coordinates(event.pos())

                # 添加坐标点
                self.coordinate_points.append((relative_pos.x(), relative_pos.y()))
                self.click_positions.append(event.pos())

                logger.info(f"添加坐标点 {len(self.coordinate_points)}: 屏幕({event.pos().x()}, {event.pos().y()}) -> 客户区({relative_pos.x()}, {relative_pos.y()})")

                # 更新显示
                self.update()
            else:
                logger.warning("点击位置不在目标窗口内")

        elif event.button() == Qt.MouseButton.RightButton:
            # 删除最后一个点
            if self.coordinate_points:
                removed_point = self.coordinate_points.pop()
                self.click_positions.pop()
                logger.info(f"删除坐标点: {removed_point}")
                self.update()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            # ESC键完成选择
            logger.info(f"ESC键完成选择，共选择了 {len(self.coordinate_points)} 个坐标点")
            self._finish_selection()

        elif event.key() == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Z 撤销上一个点
            if self.coordinate_points:
                removed_point = self.coordinate_points.pop()
                self.click_positions.pop()
                logger.info(f"撤销坐标点: {removed_point}")
                self.update()

    def _finish_selection(self):
        """完成坐标选择"""
        if len(self.coordinate_points) >= 2:
            # 发射坐标列表信号
            self.coordinates_selected.emit(self.coordinate_points.copy())
            logger.info(f"多点坐标选择完成: {self.coordinate_points}")
        else:
            logger.warning("至少需要选择2个坐标点")

        self.close()


class MultiPointCoordinateSelectorWidget(QWidget):
    """多点坐标选择器Widget - 支持连续获取多个坐标点"""

    coordinates_selected = Signal(list)  # 发射坐标点列表
    selection_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_window_hwnd = None
        self.coordinate_points = []

        self._setup_ui()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 选择按钮
        self.select_button = QPushButton("点击获取多个坐标")
        self.select_button.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
        """)
        self.select_button.clicked.connect(self.start_selection)

        layout.addWidget(self.select_button)

        self._update_button_text()

    def start_selection(self):
        """开始多点坐标选择"""
        try:
            # 如果没有设置目标窗口句柄，尝试自动获取编辑器绑定的窗口
            if not self.target_window_hwnd:
                window_title = self._get_bound_window_from_editor()
                if window_title:
                    # 通过窗口标题查找窗口句柄
                    self.target_window_hwnd = self._find_window_by_title(window_title)
                    if self.target_window_hwnd:
                        logger.info(f"自动获取编辑器绑定的窗口句柄: {self.target_window_hwnd}, 标题: {window_title}")
                    else:
                        logger.error(f"无法通过标题找到窗口句柄: {window_title}")
                        QMessageBox.warning(self, "错误", f"无法找到窗口: {window_title}")
                        return
                else:
                    # 如果获取窗口标题失败，尝试直接获取窗口句柄
                    target_hwnd = self._get_bound_window_hwnd()
                    if target_hwnd:
                        self.target_window_hwnd = target_hwnd
                        logger.info(f"直接获取绑定窗口句柄: {target_hwnd}")
                    else:
                        QMessageBox.warning(self, "错误", "未找到目标窗口，请先绑定窗口")
                        return

            logger.info(f"开始多点坐标选择，目标窗口句柄: {self.target_window_hwnd}")

            # 创建多点坐标选择器覆盖层
            self.overlay = MultiPointCoordinateSelectorOverlay(self.target_window_hwnd, self)
            self.overlay.coordinates_selected.connect(self._on_coordinates_selected)

            # 显示覆盖层
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.activateWindow()

            # 多次尝试强制置顶目标窗口，确保不被覆盖层遮挡
            self.overlay._force_target_window_top()

        except Exception as e:
            logger.error(f"启动多点坐标选择失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            QMessageBox.critical(self, "错误", f"启动坐标选择失败: {e}")

    def _update_button_text(self):
        """更新按钮文本以显示当前坐标点数量"""
        if hasattr(self, 'select_button'):
            count = len(self.coordinate_points)
            if count == 0:
                self.select_button.setText("点击获取多个坐标")
            else:
                self.select_button.setText(f"已选择 {count} 个坐标点")

    def set_coordinates(self, coordinates: List[Tuple[int, int]]):
        """设置坐标点列表"""
        self.coordinate_points = coordinates.copy()
        self._update_button_text()
        logger.info(f"多点坐标选择器坐标已设置: {len(coordinates)} 个点")

    def _on_coordinates_selected(self, coordinates: List[Tuple[int, int]]):
        """多点坐标选择完成"""
        logger.info(f"多点坐标选择完成: {len(coordinates)} 个点")

        try:
            # 保存坐标点
            self.set_coordinates(coordinates)

            # 发射坐标信号
            self.coordinates_selected.emit(coordinates)

            # 发出选择结束信号
            self.selection_finished.emit()

            logger.info(f"多点坐标处理完成: {coordinates}")

        except Exception as e:
            logger.error(f"处理多点坐标选择失败: {e}")
            # 确保即使出错也发射信号
            try:
                self.coordinates_selected.emit(coordinates)
                self.selection_finished.emit()
            except:
                pass

    def _get_bound_window_hwnd(self) -> Optional[int]:
        """获取当前绑定的窗口句柄"""
        try:
            # 向上查找主窗口，获取绑定的窗口信息
            current_widget = self.parent()
            level = 0
            max_levels = 10

            while current_widget and level < max_levels:
                logger.debug(f"检查父级窗口 {level}: {type(current_widget).__name__}")

                # 检查是否有config属性（主窗口）
                if hasattr(current_widget, 'config') and hasattr(current_widget.config, 'bound_windows'):
                    config = current_widget.config
                    if config.bound_windows:
                        # 获取第一个启用的窗口
                        enabled_windows = [w for w in config.bound_windows if w.get('enabled', True)]
                        if enabled_windows:
                            hwnd = enabled_windows[0].get('hwnd')
                            logger.info(f"从主窗口config获取窗口句柄: {hwnd}")
                            return hwnd

                # 检查是否有runner属性（参数面板）
                if hasattr(current_widget, 'runner') and hasattr(current_widget.runner, 'config'):
                    config = current_widget.runner.config
                    if hasattr(config, 'bound_windows') and config.bound_windows:
                        # 获取第一个启用的窗口
                        enabled_windows = [w for w in config.bound_windows if w.get('enabled', True)]
                        if enabled_windows:
                            hwnd = enabled_windows[0].get('hwnd')
                            logger.info(f"从runner config获取窗口句柄: {hwnd}")
                            return hwnd

                # 检查是否有bound_windows属性（主窗口直接属性）
                if hasattr(current_widget, 'bound_windows') and current_widget.bound_windows:
                    enabled_windows = [w for w in current_widget.bound_windows if w.get('enabled', True)]
                    if enabled_windows:
                        hwnd = enabled_windows[0].get('hwnd')
                        logger.info(f"从主窗口bound_windows获取窗口句柄: {hwnd}")
                        return hwnd

                # 检查是否有current_target_hwnd属性
                if hasattr(current_widget, 'current_target_hwnd') and current_widget.current_target_hwnd:
                    hwnd = current_widget.current_target_hwnd
                    logger.info(f"从主窗口current_target_hwnd获取窗口句柄: {hwnd}")
                    return hwnd

                current_widget = current_widget.parent()
                level += 1

            logger.warning("未找到任何绑定的窗口句柄")
            return None

        except Exception as e:
            logger.error(f"获取绑定窗口句柄失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return None

    def _get_bound_window_from_editor(self) -> Optional[str]:
        """从编辑器获取绑定的窗口（支持多窗口模式）"""
        try:
            logger.info("搜索 开始获取绑定的窗口标题...")

            # 向上查找主窗口，直到找到有config或runner属性的窗口
            current_widget = self.parent()
            level = 0

            while current_widget and level < 10:  # 最多向上查找10层
                logger.info(f"搜索 第{level}层窗口: {current_widget}")
                logger.info(f"搜索 第{level}层窗口类型: {type(current_widget)}")

                # 检查是否有bound_windows属性（多窗口模式）
                if hasattr(current_widget, 'bound_windows'):
                    bound_windows = current_widget.bound_windows
                    if bound_windows and len(bound_windows) > 0:
                        # 获取第一个启用的窗口
                        for window_info in bound_windows:
                            if window_info.get('enabled', True):
                                window_title = window_info.get('title')
                                if window_title:
                                    logger.info(f"搜索 从多窗口绑定列表获取第一个启用窗口: {window_title}")
                                    return window_title

                        # 如果没有启用的窗口，使用第一个窗口
                        first_window = bound_windows[0]
                        window_title = first_window.get('title')
                        if window_title:
                            logger.info(f"搜索 从多窗口绑定列表获取第一个窗口: {window_title}")
                            return window_title

                # 检查是否是主窗口（任务编辑器）
                if hasattr(current_widget, 'config'):
                    logger.info(f"搜索 第{level}层窗口有config属性")
                    config = current_widget.config
                    target_window_title = config.get('target_window_title')
                    if target_window_title:
                        logger.info(f"搜索 从第{level}层窗口配置获取目标窗口: {target_window_title}")
                        return target_window_title
                    else:
                        logger.info(f"搜索 第{level}层窗口config中没有target_window_title")

                # 检查是否有runner属性
                if hasattr(current_widget, 'runner'):
                    logger.info(f"搜索 第{level}层窗口有runner属性")
                    runner = current_widget.runner
                    if hasattr(runner, 'target_window_title'):
                        target_window_title = runner.target_window_title
                        logger.info(f"搜索 从第{level}层窗口runner获取目标窗口: {target_window_title}")
                        if target_window_title:
                            return target_window_title
                    else:
                        logger.info(f"搜索 第{level}层窗口runner没有target_window_title属性")

                # 检查是否有直接的target_window_title属性
                if hasattr(current_widget, 'target_window_title'):
                    target_window_title = current_widget.target_window_title
                    logger.info(f"搜索 从第{level}层窗口属性获取目标窗口: {target_window_title}")
                    if target_window_title:
                        return target_window_title

                # 向上查找父窗口
                current_widget = current_widget.parent()
                level += 1

            logger.info(f"搜索 查找了{level}层窗口，未找到绑定的目标窗口")
            return None

        except Exception as e:
            logger.error(f"获取编辑器绑定窗口时出错: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_window_by_title(self, window_title: str) -> Optional[int]:
        """通过窗口标题查找窗口句柄"""
        try:
            from main import find_window_by_title
            hwnd = find_window_by_title(window_title)
            if hwnd:
                logger.info(f"通过标题找到窗口句柄: {window_title} -> {hwnd}")
                return hwnd
            else:
                logger.warning(f"无法通过标题找到窗口: {window_title}")
                return None
        except Exception as e:
            logger.error(f"查找窗口句柄失败: {e}")
            return None

    def get_coordinates(self) -> List[Tuple[int, int]]:
        """获取当前坐标点列表"""
        return self.coordinate_points.copy()
