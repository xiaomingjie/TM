"""
参数设置面板 - 吸附在主窗口右侧的小窗口
类似雷电模拟器辅助屏的设计
"""

import logging
import os
from typing import Dict, Any, Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QFrame, QGroupBox,
    QSlider, QProgressBar, QFileDialog, QColorDialog, QFontDialog,
    QButtonGroup, QRadioButton, QTabWidget, QSplitter, QFormLayout,
    QGridLayout, QStackedWidget, QSizePolicy, QDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QPoint, QRect, QObject, QEvent
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QBrush, QPainterPath, QPen

logger = logging.getLogger(__name__)


class CloseButton(QPushButton):
    """自定义关闭按钮，与主窗口样式保持一致"""

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        # 设置尺寸与主窗口关闭按钮一致
        self.setFixedSize(36, 30)
        # 设置对象名称用于样式识别
        self.setObjectName("closeButton")
        # 设置工具提示
        self.setToolTip("关闭")
        # 样式将通过主样式表应用，不需要在这里重复设置

    def mousePressEvent(self, event):
        """重写鼠标按下事件，直接触发点击"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """重写鼠标释放事件"""
        super().mouseReleaseEvent(event)


class ResponsiveButton(QPushButton):
    """响应式按钮，确保点击事件能正确处理"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        # 确保按钮能正确接收鼠标事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)

    def mousePressEvent(self, event):
        """重写鼠标按下事件，确保响应"""
        logger.info(f"ResponsiveButton '{self.text()}' 接收到鼠标按下事件")
        print(f"ResponsiveButton '{self.text()}' 接收到鼠标按下事件")

        if event.button() == Qt.MouseButton.LeftButton:
            # 立即发射点击信号，不等待释放
            logger.info(f"ResponsiveButton '{self.text()}' 发射点击信号")
            print(f"ResponsiveButton '{self.text()}' 发射点击信号")
            self.clicked.emit()
            event.accept()
        super().mousePressEvent(event)


class InputWidgetEventFilter(QObject):
    """输入控件事件过滤器，确保输入控件能正常接收和处理事件"""

    def __init__(self, widget, widget_name):
        super().__init__()
        self.widget = widget
        self.widget_name = widget_name

    def eventFilter(self, obj, event):
        """过滤事件，确保输入控件能正常工作"""
        if obj == self.widget:
            # 对于鼠标按下事件，记录日志但不干预
            if event.type() == QEvent.Type.MouseButtonPress:
                logger.debug(f"输入控件 {self.widget_name} 接收到鼠标按下事件")
                # 不强制设置焦点，让Qt自然处理
                return False

            # 减少焦点事件的日志输出，避免日志刷屏
            elif event.type() == QEvent.Type.FocusIn:
                # logger.debug(f"输入控件 {self.widget_name} 获得焦点")
                return False

            elif event.type() == QEvent.Type.FocusOut:
                # logger.debug(f"输入控件 {self.widget_name} 失去焦点")
                return False

        # 默认不拦截任何事件
        return False


class WheelEventFilter(QObject):
    """滚轮事件过滤器，禁用所有控件的滚轮事件"""

    def __init__(self, widget_name=""):
        super().__init__()
        self.widget_name = widget_name

    def eventFilter(self, obj, event):
        # 拦截滚轮事件
        if event.type() == QEvent.Type.Wheel:
            logger.debug(f"拦截控件 '{self.widget_name}' 的滚轮事件，防止意外修改参数")
            event.ignore()  # 忽略事件，不传递给控件
            return True  # 表示事件已处理

        return super().eventFilter(obj, event)


class CheckboxEventFilter(QObject):
    """复选框事件过滤器，确保点击事件能正确处理"""

    def __init__(self, checkbox, name):
        super().__init__()
        self.checkbox = checkbox
        self.name = name

    def eventFilter(self, obj, event):
        if obj == self.checkbox and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                logger.info(f"复选框 '{self.name}' 接收到鼠标按下事件")
                print(f"复选框 '{self.name}' 接收到鼠标按下事件")

                # 切换复选框状态
                current_state = self.checkbox.isChecked()
                new_state = not current_state
                self.checkbox.setChecked(new_state)

                logger.info(f"复选框 '{self.name}' 状态切换: {current_state} -> {new_state}")
                print(f"复选框 '{self.name}' 状态切换: {current_state} -> {new_state}")

                # 发射信号
                self.checkbox.clicked.emit(new_state)

                event.accept()
                return True

        return super().eventFilter(obj, event)


class ParameterPanel(QWidget):
    """参数设置面板 - 独立的小窗口吸附在主窗口右侧"""

    # 信号定义
    parameters_changed = Signal(int, dict)  # card_id, new_parameters
    panel_closed = Signal()

    def __init__(self, parent=None):
        super().__init__(None)  # 不设置父窗口，使其成为独立窗口
        self.parent_window = parent  # 保存父窗口引用用于定位
        self.current_card_id: Optional[int] = None
        self.current_task_type: Optional[str] = None
        self.current_parameters: Dict[str, Any] = {}
        self.param_definitions: Dict[str, Dict[str, Any]] = {}
        self.widgets: Dict[str, QWidget] = {}
        self.workflow_cards_info: Dict[int, tuple[str, int]] = {}
        self.app_mapping: Dict[str, str] = {}  # 应用名称到包名的映射
        self.images_dir: Optional[str] = None
        self.conditional_widgets: Dict[str, QWidget] = {}  # 条件控件
        self.target_window_title: Optional[str] = None  # 目标窗口标题
        self.main_window_minimized: bool = False  # 跟踪主窗口是否被最小化
        self.manually_closed: bool = False  # 跟踪用户是否手动关闭了面板
        self._activation_in_progress: bool = False  # 防止循环激活

        # 拖动相关变量
        self._mouse_pressed: bool = False
        self._mouse_press_pos: QPoint = QPoint()
        self._window_pos_before_move: QPoint = QPoint()
        self._is_dragging: bool = False  # 拖拽状态标志

        # 焦点保护相关变量
        self._input_focus_protection_active: bool = False

        # 设置窗口属性 - 无边框窗口（隐藏系统标题栏）
        self.setWindowFlags(
            Qt.WindowType.Window |  # 普通窗口类型
            Qt.WindowType.FramelessWindowHint  # 无边框（隐藏系统标题栏）
        )

        # 设置为非模态窗口
        self.setWindowModality(Qt.WindowModality.NonModal)

        # 确保窗口可以接收焦点和输入
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 设置必要的输入属性
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)

        # 恢复透明背景属性（配合自绘背景）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._setup_ui()
        self._apply_styles()

        # 确保窗口可以接收键盘输入
        self.setFocus()
        self.activateWindow()

    def event(self, event):
        """重写事件处理，监听窗口激活事件"""
        if event.type() == event.Type.WindowActivate:
            # 当小窗口被激活时，不要自动激活主窗口，让用户能正常输入
            # 只有在用户明确需要时才激活主窗口
            pass
        return super().event(event)

    def _activate_main_window(self):
        """激活主窗口（仅在主窗口未被最小化时）"""
        # 暂时禁用自动激活主窗口功能，让用户能正常在参数面板中输入
        # if self.parent_window and not self.main_window_minimized:
        #     # 只在主窗口未被最小化时才激活
        #     self.parent_window.show()
        #     self.parent_window.raise_()
        #     self.parent_window.activateWindow()
        pass

    def mousePressEvent(self, event):
        """修复的鼠标事件处理 - 确保输入控件能正常接收事件，同时支持拖拽"""
        # 检查点击的控件
        clicked_widget = self.childAt(event.pos())

        # 如果点击的是输入控件或其子控件，直接传递事件
        if clicked_widget:
            # 检查是否是输入控件或按钮
            widget_to_check = clicked_widget
            while widget_to_check and widget_to_check != self:
                if isinstance(widget_to_check, (QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit, QComboBox, QPushButton)):
                    # 是输入控件或按钮，让事件正常传播，不做任何拦截
                    super().mousePressEvent(event)
                    return
                widget_to_check = widget_to_check.parent()

        # 对于非输入控件区域，执行拖拽和关闭按钮逻辑
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查关闭按钮
            if hasattr(self, 'close_button'):
                close_button_rect = self.close_button.geometry()
                if hasattr(self, 'title_frame'):
                    close_button_global = self.title_frame.mapToParent(close_button_rect.topLeft())
                    close_button_window_rect = QRect(close_button_global, close_button_rect.size())
                    if close_button_window_rect.contains(event.pos()):
                        self.hide_panel()
                        event.accept()
                        return

            # 开始拖拽（仅在空白区域）- 参考主窗口实现
            self._mouse_pressed = True
            self._mouse_press_pos = event.globalPosition().toPoint()  # 使用全局坐标
            self._window_pos_before_move = self.pos()
            self._is_dragging = False  # 初始化拖拽状态
            event.accept()
            return

        # 其他情况传递给父类
        super().mousePressEvent(event)



    def mouseMoveEvent(self, event):
        """鼠标移动事件处理 - 参考主窗口拖拽实现，同时移动主窗口"""
        if self._mouse_pressed and event.buttons() == Qt.MouseButton.LeftButton:
            # 标记为正在拖拽状态
            if not self._is_dragging:
                self._is_dragging = True
                logger.debug("开始拖拽参数面板")

            # 使用全局坐标计算移动距离（参考主窗口实现）
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self._mouse_press_pos

            # 计算参数面板新位置
            new_panel_pos = self._window_pos_before_move + delta

            # 移动参数面板
            self.move(new_panel_pos)

            # 同时移动主窗口，保持相对位置关系
            if self.parent_window:
                # 计算主窗口应该移动到的位置（参数面板左侧）
                main_window_new_x = new_panel_pos.x() - self.parent_window.width() - 2
                main_window_new_y = new_panel_pos.y()
                self.parent_window.move(main_window_new_x, main_window_new_y)

            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件处理 - 参考主窗口实现"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                logger.debug("结束拖拽参数面板")

            self._mouse_pressed = False
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)
        
    def _setup_ui(self):
        """设置UI布局"""
        self.setFixedWidth(480)  # 增加宽度以容纳更长的输入框
        self.setMinimumHeight(400)
        
        # 主布局 - 与主窗口完全一致
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # 与主窗口一致
        main_layout.setSpacing(0)  # 与主窗口一致

        # 标题栏
        self.title_frame = QFrame()
        self.title_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        title_layout = QHBoxLayout(self.title_frame)
        # 调整边距，右侧留出更少空间给关闭按钮
        title_layout.setContentsMargins(8, 6, 4, 6)

        self.title_label = QLabel("参数设置")
        self.title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title_layout.addWidget(self.title_label)

        title_layout.addStretch()

        # 关闭按钮 - 与主窗口样式保持一致
        self.close_button = CloseButton()
        self.close_button.clicked.connect(self.hide_panel)
        title_layout.addWidget(self.close_button)

        main_layout.addWidget(self.title_frame)

        # 内容容器 - 包含滚动区域和按钮，但不包含状态栏
        content_container = QFrame()
        content_container.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border: none;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }
        """)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(10, 5, 10, 8)  # 底部留一点间距给按钮
        content_layout.setSpacing(8)

        # 恢复滚动区域，现在输入框问题已解决
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 参数内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(8)

        self.scroll_area.setWidget(self.content_widget)
        content_layout.addWidget(self.scroll_area)

        # 底部按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.apply_button = QPushButton("应用")
        self.apply_button.clicked.connect(self._apply_parameters)
        button_layout.addWidget(self.apply_button)

        self.reset_button = QPushButton("重置")
        self.reset_button.clicked.connect(self._reset_parameters)
        button_layout.addWidget(self.reset_button)

        content_layout.addLayout(button_layout)

        main_layout.addWidget(content_container)

        # 状态栏 - 直接添加到主布局，与主窗口完全一致
        self.status_label = QLabel("操作模式 - 选择鼠标操作的模式\n注意：鼠标拖拽功能仅在后台模式下可用，前台模式下将被禁用")  # 显示默认说明
        self.status_label.setObjectName("parameterStatusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMaximumHeight(50)  # 与主窗口一致
        self.status_label.setStyleSheet("""
            #parameterStatusLabel {
                background-color: rgba(180, 180, 180, 180);
                color: white;
                padding: 8px;
                border-radius: 5px;
                font-size: 9pt;
                border: none;
                margin: 0px;
            }
        """)
        main_layout.addWidget(self.status_label)  # 直接添加到主布局

        # 初始状态：隐藏面板
        self.hide()

    def changeEvent(self, event):
        """处理窗口状态变化事件"""
        if event.type() == QEvent.Type.ActivationChange:
            # 智能激活同步：保护输入框焦点
            if self.isActiveWindow() and self.parent_window:
                self._smart_activate_main_window()
        super().changeEvent(event)

    def _smart_activate_main_window(self):
        """智能激活主窗口，保护输入框焦点"""
        # 如果焦点保护处于激活状态，不进行激活同步
        if self._input_focus_protection_active:
            logger.debug("焦点保护激活中，跳过主窗口激活同步")
            return

        # 检查当前焦点控件
        focus_widget = QApplication.focusWidget()

        # 如果当前有输入控件获得焦点，不进行激活同步
        if focus_widget and isinstance(focus_widget, (QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit)):
            logger.debug(f"输入控件 {focus_widget} 获得焦点，跳过主窗口激活同步")
            return

        # 如果主窗口已经是激活状态，不需要重复激活
        if self.parent_window.isActiveWindow():
            return

        # 防止循环激活
        if self._activation_in_progress:
            return

        self._activation_in_progress = True
        try:
            # 保存当前焦点控件
            saved_focus = QApplication.focusWidget()

            # 使用raise()代替activateWindow()，减少对焦点的影响
            self.parent_window.raise_()

            # 如果之前有焦点控件且仍然可用，尝试恢复焦点
            if saved_focus and saved_focus.isVisible() and saved_focus.isEnabled():
                # 使用定时器延迟恢复焦点，避免立即被覆盖
                QTimer.singleShot(50, lambda: self._restore_widget_focus(saved_focus))

            logger.debug("参数面板激活，智能同步主窗口（保护焦点）")
        finally:
            # 使用定时器重置标志
            QTimer.singleShot(200, lambda: setattr(self, '_activation_in_progress', False))

    def _restore_widget_focus(self, widget):
        """恢复焦点到指定控件（用于窗口激活同步）"""
        try:
            if widget and widget.isVisible() and widget.isEnabled():
                widget.setFocus()
                logger.debug(f"恢复焦点到控件: {widget}")
        except Exception as e:
            logger.debug(f"恢复焦点失败: {e}")

    def _install_wheel_filter(self, widget, name):
        """为控件安装滚轮事件过滤器"""
        # 检查是否是可能响应滚轮的控件
        if isinstance(widget, (QComboBox, QSpinBox, QDoubleSpinBox, QSlider)):
            wheel_filter = WheelEventFilter(f"{type(widget).__name__}_{name}")
            widget.installEventFilter(wheel_filter)

            # 保存过滤器引用，防止被垃圾回收
            if not hasattr(self, '_wheel_filters'):
                self._wheel_filters = []
            self._wheel_filters.append(wheel_filter)

            logger.debug(f"为控件 {name} ({type(widget).__name__}) 安装滚轮事件过滤器")
        
    def _apply_styles(self):
        """应用与主程序一致的样式"""
        self.setStyleSheet("""
            ParameterPanel {
                background-color: transparent;
                border: none;
                font-size: 10pt;
            }

            QFrame {
                background-color: #f0f0f0;
                border: none;
                border-radius: 10px;
                padding: 8px;
            }

            /* 标题栏特殊样式 */
            QFrame[frameShape="1"] {
                background-color: #F9F9F9;
                border: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 8px;
            }

            QLabel {
                color: #333333;
                font-family: "Microsoft YaHei";
                font-size: 9pt;
            }

            QPushButton {
                padding: 8px 18px;
                border: none;
                border-radius: 4px;
                background-color: #e8e8e8;
                color: #333333;
                font-family: "Microsoft YaHei";
                min-height: 20px;
            }

            QPushButton:hover {
                background-color: #dddddd;
            }

            QPushButton:pressed {
                background-color: #cccccc;
            }

            /* 确保关闭按钮样式不被覆盖 */
            QPushButton#closeButton {
                background-color: transparent;
                border: none;
                padding: 0px 10px;
                margin: 0px 2px;
                border-radius: 4px;
                color: #555555;
                font-family: "Segoe UI", "Arial";
                font-size: 14px;
                font-weight: normal;
                min-width: 36px;
                min-height: 30px;
            }
            QPushButton#closeButton:hover {
                background-color: #E81123;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0px 10px;
            }
            QPushButton#closeButton:pressed {
                background-color: #B00000;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0px 10px;
            }

            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                min-height: 20px;
                font-family: "Microsoft YaHei";
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }

            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #007bff;
            }

            QScrollArea {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #ffffff;
            }

            QCheckBox {
                font-family: "Microsoft YaHei";
                spacing: 8px;
                color: #333333;
            }

            QGroupBox {
                font-weight: bold;
                border: none;
                border-radius: 8px;
                margin-top: 15px;
                padding: 15px;
                background-color: #f8f8f8;
                font-family: "Microsoft YaHei";
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                left: 15px;
                color: #555555;
            }

            QPlainTextEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-family: "Microsoft YaHei";
            }
        """)
        
    def show_parameters(self, card_id: int, task_type: str, param_definitions: Dict[str, Dict[str, Any]],
                       current_parameters: Dict[str, Any], workflow_cards_info: Dict[int, tuple[str, int]] = None,
                       images_dir: str = None, target_window_hwnd: int = None):
        """显示指定卡片的参数设置"""
        logger.info(f"显示卡片 {card_id} ({task_type}) 的参数设置")

        # 参数验证
        if not isinstance(card_id, int) or card_id < 0:
            logger.error(f"无效的卡片ID: {card_id}")
            return

        if not task_type:
            logger.error(f"任务类型为空: {task_type}")
            return

        self.current_card_id = card_id
        self.current_task_type = task_type
        self.current_parameters = current_parameters.copy()
        self.param_definitions = param_definitions
        self.workflow_cards_info = workflow_cards_info or {}
        self.images_dir = images_dir
        self.target_window_hwnd = target_window_hwnd

        # 验证设置是否成功
        logger.debug(f"参数面板状态设置完成 - card_id: {self.current_card_id}, task_type: {self.current_task_type}")
        logger.debug(f"参数定义数量: {len(self.param_definitions)}, 当前参数数量: {len(self.current_parameters)}")
        logger.debug(f"工作流卡片信息: {self.workflow_cards_info}")
        
        # 更新标题
        self.title_label.setText(f"{task_type} (ID: {card_id})")
        
        # 清除现有控件
        self._clear_content()
        
        # 创建参数控件
        self._create_parameter_widgets()

        # 如果是雷电应用管理任务且有保存的应用选择，直接恢复选择（不自动刷新）
        if task_type == "雷电应用管理" and current_parameters.get('selected_app'):
            saved_app = current_parameters.get('selected_app')
            if saved_app and saved_app != "请先刷新应用列表":
                logger.info(f"检测到已保存的应用选择: {saved_app}，直接恢复选择")
                # 延迟恢复选择，确保界面已经创建完成
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, lambda: self._restore_app_selection_only(saved_app))

        # 显示面板并定位到主窗口右侧
        self._position_panel()
        # 重置手动关闭标志，因为用户主动打开了参数面板
        self.manually_closed = False
        # 正常显示参数面板，允许用户交互
        self.show()
        # 将参数面板置于合适的层级
        self.raise_()
        # 暂时不激活窗口和设置焦点，避免干扰输入框焦点
        # self.activateWindow()
        # self.setFocus()

        # 暂时移除强制启用，让控件使用默认状态
        # from PySide6.QtCore import QTimer
        # QTimer.singleShot(100, self._force_enable_input_widgets)
        # QTimer.singleShot(200, self._debug_input_widgets)
        














    def _restore_app_selection_only(self, saved_app):
        """只恢复应用选择，不刷新应用列表"""
        try:
            if 'selected_app' in self.widgets:
                app_widget = self.widgets['selected_app']
                if hasattr(app_widget, 'findText'):
                    # 先尝试直接恢复
                    index = app_widget.findText(saved_app)
                    if index >= 0:
                        app_widget.setCurrentIndex(index)
                        logger.info(f"直接恢复应用选择: {saved_app}")
                        return

                    # 如果找不到，添加到选项中（保持已保存的选择）
                    if hasattr(app_widget, 'addItem'):
                        app_widget.addItem(saved_app)
                        app_widget.setCurrentText(saved_app)
                        logger.info(f"添加并恢复应用选择: {saved_app}")
                    else:
                        logger.warning(f"无法恢复应用选择: {saved_app}")

        except Exception as e:
            logger.error(f"恢复应用选择失败: {e}")

    def _auto_refresh_and_restore_selection(self):
        """自动刷新应用列表并恢复选择（保留此方法以防其他地方调用）"""
        try:
            # 先刷新应用列表
            self._handle_refresh_apps_click()

            # 获取保存的应用选择
            saved_app = self.current_parameters.get('selected_app')
            if not saved_app or saved_app == "请先刷新应用列表":
                return

            # 尝试恢复选择
            if 'selected_app' in self.widgets:
                app_widget = self.widgets['selected_app']
                if hasattr(app_widget, 'findText'):
                    # 直接查找包名（现在应用列表显示的就是包名）
                    index = app_widget.findText(saved_app)
                    if index >= 0:
                        app_widget.setCurrentIndex(index)
                        logger.info(f"恢复应用选择: {saved_app}")
                    else:
                        logger.warning(f"未找到保存的应用: {saved_app}")

        except Exception as e:
            logger.error(f"自动刷新和恢复选择失败: {e}")

    def hide_panel(self):
        """隐藏面板"""
        logger.debug(f"隐藏参数面板 - card_id: {self.current_card_id}")
        self.manually_closed = True  # 标记为用户手动关闭
        self.hide()
        self.panel_closed.emit()
        # 注意：不要在这里重置 current_card_id，因为面板可能会重新显示

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        logger.debug(f"参数面板关闭事件 - card_id: {self.current_card_id}")
        self.manually_closed = True  # 标记为用户手动关闭
        self.panel_closed.emit()
        # 注意：不要在这里重置 current_card_id
        event.accept()

    def _position_panel(self):
        """将面板定位到主窗口右侧"""
        if not self.parent_window:
            return

        # 如果正在拖拽，跳过自动定位，避免干扰用户操作
        if self._is_dragging:
            logger.debug("正在拖拽中，跳过自动定位")
            return

        # 获取主窗口的位置和大小
        parent_geometry = self.parent_window.geometry()

        # 计算面板位置：主窗口右边缘 + 2像素间距（减少缝隙）
        panel_x = parent_geometry.x() + parent_geometry.width() + 2
        panel_y = parent_geometry.y()

        # 设置面板位置
        self.move(panel_x, panel_y)

        # 调整面板高度以完全匹配主窗口高度
        panel_height = parent_geometry.height()
        self.resize(350, panel_height)

    def sync_window_state(self, parent_state):
        """同步主窗口的状态"""
        if parent_state == Qt.WindowState.WindowMinimized:
            self.main_window_minimized = True
            self.hide()
        elif parent_state == Qt.WindowState.WindowNoState or parent_state == Qt.WindowState.WindowMaximized:
            self.main_window_minimized = False
            # 只有在用户没有手动关闭且有内容时才自动显示
            if not self.manually_closed and self.current_card_id is not None:
                self.show()  # 正常显示，允许用户交互
                self._position_panel()

    def sync_activation(self, activated):
        """同步主窗口的激活状态（智能保护焦点版本）"""
        # 防止循环激活
        if self._activation_in_progress:
            return

        # 当主窗口激活时，确保参数面板在正确位置
        if activated and self.isVisible():
            self._position_panel()
            self._smart_activate_parameter_panel()

    def _smart_activate_parameter_panel(self):
        """智能激活参数面板，保护输入框焦点"""
        # 如果焦点保护处于激活状态，不进行激活同步
        if self._input_focus_protection_active:
            logger.debug("焦点保护激活中，跳过参数面板激活同步")
            return

        # 检查当前焦点控件
        focus_widget = QApplication.focusWidget()

        # 如果当前有输入控件获得焦点，不进行激活同步
        if focus_widget and isinstance(focus_widget, (QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit)):
            logger.debug(f"输入控件 {focus_widget} 获得焦点，跳过参数面板激活同步")
            return

        # 如果参数面板已经是激活状态，不需要重复激活
        if self.isActiveWindow():
            return

        # 防止循环激活
        if self._activation_in_progress:
            return

        self._activation_in_progress = True
        try:
            # 保存当前焦点控件
            saved_focus = QApplication.focusWidget()

            # 使用raise()代替activateWindow()，减少对焦点的影响
            self.raise_()

            # 如果之前有焦点控件且仍然可用，尝试恢复焦点
            if saved_focus and saved_focus.isVisible() and saved_focus.isEnabled():
                # 使用定时器延迟恢复焦点，避免立即被覆盖
                QTimer.singleShot(50, lambda: self._restore_widget_focus(saved_focus))

            logger.debug("主窗口激活，智能同步参数面板（保护焦点）")
        finally:
            # 使用定时器重置标志
            QTimer.singleShot(200, lambda: setattr(self, '_activation_in_progress', False))

    def paintEvent(self, event):
        """绘制圆角背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 创建圆角矩形路径
        path = QPainterPath()
        rect = self.rect()
        radius = 12  # 圆角半径
        path.addRoundedRect(rect, radius, radius)

        # 绘制背景
        painter.fillPath(path, QBrush(QColor(255, 255, 255, 250)))  # 白色背景，略透明

        # 绘制边框
        painter.setPen(QColor(224, 224, 224))  # #e0e0e0
        painter.drawPath(path)
        
    def _clear_content(self):
        """清除内容区域的所有控件"""
        logger.debug(f"清除参数面板内容 - card_id: {self.current_card_id}")

        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.widgets.clear()
        self.conditional_widgets.clear()

    def _should_show_parameter(self, param_def: Dict[str, Any]) -> bool:
        """检查参数是否应该显示（基于条件）"""
        try:
            condition = param_def.get('condition')
            if not condition:
                return True

            # 确保current_parameters存在
            if not hasattr(self, 'current_parameters') or self.current_parameters is None:
                return True

            # 支持多条件（列表形式）和单条件（字典形式）
            if isinstance(condition, list):
                # 多条件：所有条件都必须满足（AND逻辑）
                for single_condition in condition:
                    if not self._check_single_condition(single_condition):
                        return False
                return True
            else:
                # 单条件 - 包含原有的特殊处理逻辑
                param_name = condition.get('param')
                expected_value = condition.get('value')

                if not param_name or expected_value is None:
                    return True

                # 获取当前参数值
                current_value = self.current_parameters.get(param_name)

                # 检查主条件
                main_condition_met = False
                if isinstance(expected_value, list):
                    main_condition_met = current_value in expected_value
                else:
                    main_condition_met = current_value == expected_value

                # 如果主条件不满足，直接返回False
                if not main_condition_met:
                    return False

                # 检查是否有额外的AND条件
                and_condition = condition.get('and')
                if and_condition:
                    # 处理AND条件
                    if isinstance(and_condition, list):
                        # 多个AND条件
                        for and_cond in and_condition:
                            if not self._check_single_condition(and_cond):
                                return False
                    else:
                        # 单个AND条件
                        if not self._check_single_condition(and_condition):
                            return False

                # 特殊处理：对于依赖multi_image_mode的参数，需要额外检查operation_mode
                if param_name == 'multi_image_mode':
                    # 检查operation_mode是否为"图片点击"
                    operation_mode = self.current_parameters.get('operation_mode')
                    if operation_mode != '图片点击':
                        return False

                return True
        except Exception as e:
            logger.error(f"参数显示条件检查失败: {e}")
            return True  # 出错时默认显示

    def _check_single_condition(self, condition: Dict[str, Any]) -> bool:
        """检查单个条件是否满足"""
        try:
            if not isinstance(condition, dict):
                return True

            param_name = condition.get('param')
            expected_value = condition.get('value')

            if not param_name or expected_value is None:
                return True

            # 确保current_parameters存在
            if not hasattr(self, 'current_parameters') or self.current_parameters is None:
                return True

            # 获取当前参数值
            current_value = self.current_parameters.get(param_name)

            # 检查条件
            if isinstance(expected_value, list):
                return current_value in expected_value
            else:
                return current_value == expected_value
        except Exception as e:
            logger.error(f"条件检查失败: {e}")
            return True  # 出错时默认显示

    def _create_parameter_widgets(self):
        """根据参数定义创建控件"""
        if not self.param_definitions:
            no_params_label = QLabel("此任务没有可配置的参数")
            no_params_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_params_label.setStyleSheet("color: #888888; font-style: italic;")
            self.content_layout.addWidget(no_params_label)
            return
            
        # 按顺序处理所有参数和分隔符
        for name, param_def in self.param_definitions.items():
            # 处理分隔符
            if name.startswith('---') and name.endswith('---'):
                if self._should_show_parameter(param_def):
                    separator_label = param_def.get('label', '')
                    if separator_label:
                        separator = QLabel(separator_label)
                        separator.setStyleSheet("font-weight: bold; color: #666; margin-top: 10px; margin-bottom: 5px;")
                        self.content_layout.addWidget(separator)
                        self.conditional_widgets[name] = separator
                continue

            if param_def.get('type') == 'separator':
                continue

            # 跳过隐藏参数
            if param_def.get('type') == 'hidden':
                continue

            # 只添加满足条件的参数
            if not self._should_show_parameter(param_def):
                continue

            # 直接创建参数控件，保持原始顺序
            self._create_single_parameter_widget(name, param_def, self.content_layout)

        # 添加弹性空间
        self.content_layout.addStretch()



    def _create_single_parameter_widget(self, name: str, param_def: Dict[str, Any], layout: QVBoxLayout):
        """创建单个参数的控件"""
        param_type = param_def.get('type', 'text')
        label_text = param_def.get('label', name)
        current_value = self.current_parameters.get(name, param_def.get('default'))
        widget_hint = param_def.get('widget_hint', '')



        # 创建行容器
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        # 标签
        label = QLabel(f"{label_text}:")
        label.setFixedWidth(140)  # 增加宽度以显示完整的参数名称
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setWordWrap(True)  # 允许换行

        # 为标签也添加悬停事件
        self._setup_status_display(label, name, param_def)

        row_layout.addWidget(label)

        widget = None

        # 首先检查特殊的widget_hint，优先级最高
        if widget_hint == 'jump_target_selector' or widget_hint == 'card_selector':
            # 跳转目标选择器/卡片选择器
            widget = QComboBox()
            widget.addItem("无跳转", None)

            # 添加工作流中的其他卡片作为选项
            sorted_cards = sorted(self.workflow_cards_info.items())
            for seq_id, (task_type, card_id) in sorted_cards:
                if card_id != self.current_card_id:  # 不包括自己
                    widget.addItem(f"{task_type} (ID: {card_id})", card_id)

            # 设置当前值
            if current_value:
                index = widget.findData(current_value)
                if index >= 0:
                    widget.setCurrentIndex(index)

        elif widget_hint == 'file_selector':
            # 文件选择器
            file_widget = QWidget()
            file_layout = QHBoxLayout(file_widget)
            file_layout.setContentsMargins(0, 0, 0, 0)

            file_edit = QLineEdit(str(current_value) if current_value else "")
            file_button = QPushButton("浏览...")
            file_button.clicked.connect(lambda: self._select_file(file_edit, param_def))

            file_layout.addWidget(file_edit)
            file_layout.addWidget(file_button)

            widget = file_widget
            self.widgets[name] = file_edit  # 存储编辑框用于获取值

        elif widget_hint == 'color_selector':
            # 颜色选择器
            color_widget = QWidget()
            color_layout = QHBoxLayout(color_widget)
            color_layout.setContentsMargins(0, 0, 0, 0)

            color_edit = QLineEdit(str(current_value) if current_value else "#000000")
            color_button = QPushButton("选择颜色")
            color_button.clicked.connect(lambda: self._select_color(color_edit))

            color_layout.addWidget(color_edit)
            color_layout.addWidget(color_button)

            widget = color_widget
            self.widgets[name] = color_edit

        elif widget_hint == 'colorpicker':
            # 找色功能的颜色拾取器（RGB格式）
            color_widget = QWidget()
            color_layout = QHBoxLayout(color_widget)
            color_layout.setContentsMargins(0, 0, 0, 0)

            color_edit = QLineEdit(str(current_value) if current_value else "255,0,0")
            color_edit.setPlaceholderText("R,G,B")
            color_button = QPushButton("选择颜色")
            color_button.clicked.connect(lambda: self._select_color_rgb(color_edit))

            color_layout.addWidget(color_edit)
            color_layout.addWidget(color_button)

            widget = color_widget
            self.widgets[name] = color_edit

        elif widget_hint == 'ocr_region_selector':
            # OCR区域选择器 - 使用响应式按钮
            widget = ResponsiveButton(param_def.get('button_text', '框选区域'))
            widget.setStyleSheet("""
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005A9E;
                }
                QPushButton:pressed {
                    background-color: #004578;
                }
            """)
            # 连接到OCR区域选择的功能
            widget.clicked.connect(lambda: self._select_ocr_region(name))

        elif widget_hint == 'coordinate_selector':
            # 坐标选择器 - 使用响应式按钮
            widget = ResponsiveButton(param_def.get('button_text', '点击获取坐标'))
            widget.setStyleSheet("""
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005A9E;
                }
                QPushButton:pressed {
                    background-color: #004578;
                }
            """)
            # 连接到坐标选择的功能
            widget.clicked.connect(lambda: self._select_coordinate(name))

        elif widget_hint == 'motion_region_selector':
            # 移动检测区域选择器 - 使用响应式按钮
            widget = ResponsiveButton(param_def.get('button_text', '选择检测区域'))
            widget.setStyleSheet("""
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005A9E;
                }
                QPushButton:pressed {
                    background-color: #004578;
                }
            """)
            # 连接到移动检测区域选择的功能
            widget.clicked.connect(lambda: self._select_motion_region(name))

        # 根据参数类型创建控件（如果没有特殊的widget_hint）
        elif param_type == 'bool' or param_type == 'checkbox':
            widget = QCheckBox()
            widget.setChecked(bool(current_value))

            # 设置复选框的基本样式，确保良好的交互体验
            widget.setStyleSheet("""
                QCheckBox {
                    spacing: 5px;
                    padding: 3px;
                    min-height: 20px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
            """)

            # 确保复选框能正确接收鼠标事件
            widget.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

            # 添加调试信息
            def on_checkbox_clicked(checked):
                print(f"复选框 {name} 被点击，新状态: {checked}")
            widget.clicked.connect(on_checkbox_clicked)

            # 确保复选框能接收鼠标事件
            widget.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
            widget.setMouseTracking(False)

            # 为复选框创建事件过滤器，手动处理点击事件
            class CheckboxEventFilter(QObject):
                def __init__(self, checkbox_widget, checkbox_name):
                    super().__init__()
                    self.checkbox_widget = checkbox_widget
                    self.checkbox_name = checkbox_name

                def eventFilter(self, obj, event):
                    if event.type() == event.Type.MouseButtonPress:
                        print(f"复选框 {self.checkbox_name} 接收到鼠标按下事件")
                        # 手动切换复选框状态
                        current_state = self.checkbox_widget.isChecked()
                        new_state = not current_state
                        self.checkbox_widget.setChecked(new_state)
                        print(f"复选框 {self.checkbox_name} 状态从 {current_state} 切换到 {new_state}")

                        # 手动触发信号
                        self.checkbox_widget.clicked.emit()  # clicked 信号不接受参数
                        self.checkbox_widget.toggled.emit(new_state)  # toggled 信号接受布尔参数

                        # 阻止事件继续传播，避免重复处理
                        return True
                    return False

            # 安装事件过滤器
            event_filter = CheckboxEventFilter(widget, name)
            widget.installEventFilter(event_filter)
            # 保存过滤器引用，防止被垃圾回收
            if not hasattr(self, '_event_filters'):
                self._event_filters = []
            self._event_filters.append(event_filter)



        elif param_type == 'int' or param_type == 'integer':
            # 使用QLineEdit替代QSpinBox，避免SpinBox的复杂问题
            widget = QLineEdit()
            widget.setText(str(int(current_value) if current_value is not None else 0))
            widget.setPlaceholderText("请输入整数")

            # 添加输入验证
            from PySide6.QtGui import QIntValidator
            validator = QIntValidator()
            validator.setRange(param_def.get('min', -999999), param_def.get('max', 999999))
            widget.setValidator(validator)

            # 设置基本属性确保输入功能
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        elif param_type == 'float' or param_type == 'double':
            # 使用QLineEdit替代QDoubleSpinBox，避免SpinBox的复杂问题
            widget = QLineEdit()
            widget.setText(str(float(current_value) if current_value is not None else 0.0))
            widget.setPlaceholderText("请输入小数")

            # 添加输入验证
            from PySide6.QtGui import QDoubleValidator
            validator = QDoubleValidator()
            validator.setRange(param_def.get('min', -999999.0), param_def.get('max', 999999.0), param_def.get('decimals', 2))
            widget.setValidator(validator)

            # 设置基本属性确保输入功能
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        elif param_type == 'radio':
            # 单选按钮组
            from PySide6.QtWidgets import QButtonGroup, QRadioButton

            radio_widget = QWidget()
            radio_layout = QVBoxLayout(radio_widget)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            radio_layout.setSpacing(4)

            button_group = QButtonGroup(radio_widget)
            options = param_def.get('options', {})

            if isinstance(options, dict):
                for key, display_text in options.items():
                    radio_button = QRadioButton(str(display_text))
                    radio_button.setProperty('value', key)  # 存储实际值
                    button_group.addButton(radio_button)
                    radio_layout.addWidget(radio_button)

                    # 设置默认选中
                    if key == current_value:
                        radio_button.setChecked(True)
            else:
                for option in options:
                    radio_button = QRadioButton(str(option))
                    radio_button.setProperty('value', option)
                    button_group.addButton(radio_button)
                    radio_layout.addWidget(radio_button)

                    # 设置默认选中
                    if option == current_value:
                        radio_button.setChecked(True)

            # 存储按钮组以便后续获取值
            radio_widget.button_group = button_group
            widget = radio_widget

        elif param_type == 'choice' or param_type == 'select' or param_type == 'combo':
            widget = QComboBox()
            # 支持 choices 和 options 两种字段名
            choices = param_def.get('choices', param_def.get('options', []))
            if isinstance(choices, dict):
                for key, value in choices.items():
                    widget.addItem(str(value), key)
                # 设置当前值
                index = widget.findData(current_value)
                if index >= 0:
                    widget.setCurrentIndex(index)
            else:
                # 处理分组分隔符
                for i, choice in enumerate(choices):
                    choice_str = str(choice)
                    widget.addItem(choice_str)

                    # 如果是分组分隔符，设置为不可选择
                    if choice_str.startswith("=== ") and choice_str.endswith(" ==="):
                        # 设置分隔符样式
                        item = widget.model().item(i)
                        if item:
                            # 设置为不可选择
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                            # 设置特殊样式
                            font = item.font()
                            font.setBold(True)
                            item.setFont(font)
                            # 设置背景色
                            item.setBackground(QColor(240, 240, 240))
                            item.setForeground(QColor(100, 100, 100))

                if current_value in choices:
                    widget.setCurrentText(str(current_value))

            # 设置焦点策略
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        elif param_type == 'textarea' or param_type == 'multiline':
            # 检查是否是路径点坐标参数，需要添加坐标获取工具
            if name == 'path_points':
                # 路径点坐标 - 带多点坐标选择工具
                path_widget = QWidget()
                path_layout = QVBoxLayout(path_widget)
                path_layout.setContentsMargins(0, 0, 0, 0)
                path_layout.setSpacing(4)

                # 文本编辑区域
                text_edit = QPlainTextEdit()
                text_edit.setPlainText(str(current_value) if current_value is not None else "")
                text_edit.setMaximumHeight(100)  # 限制高度
                text_edit.setPlaceholderText("每行一个坐标: x,y\n如: 100,100")

                # 按钮区域
                button_layout = QHBoxLayout()
                button_layout.setContentsMargins(0, 0, 0, 0)

                # 坐标获取按钮
                coord_button = ResponsiveButton("点击获取坐标")
                coord_button.setStyleSheet("""
                    QPushButton {
                        background-color: #007ACC;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #005A9E;
                    }
                    QPushButton:pressed {
                        background-color: #004578;
                    }
                """)
                coord_button.clicked.connect(lambda: self._select_multi_coordinates(name))

                # 清空按钮
                clear_button = ResponsiveButton("清空")
                clear_button.setStyleSheet("""
                    QPushButton {
                        background-color: #DC3545;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #C82333;
                    }
                    QPushButton:pressed {
                        background-color: #A71E2A;
                    }
                """)
                clear_button.clicked.connect(lambda: text_edit.clear())

                button_layout.addWidget(coord_button)
                button_layout.addWidget(clear_button)
                button_layout.addStretch()

                path_layout.addWidget(text_edit)
                path_layout.addLayout(button_layout)

                widget = path_widget
                self.widgets[name] = text_edit  # 存储文本编辑框用于获取值
            else:
                # 普通textarea
                widget = QPlainTextEdit()
                widget.setPlainText(str(current_value) if current_value is not None else "")
                widget.setMaximumHeight(100)  # 限制高度

        elif param_type == 'button':
            # 按钮类型
            widget = QPushButton(param_def.get('button_text', label_text))
            widget.setStyleSheet("""
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005A9E;
                }
                QPushButton:pressed {
                    background-color: #004578;
                }
            """)
            # 按钮点击事件
            if name == 'refresh_apps':
                widget.clicked.connect(lambda: self._handle_refresh_apps_click())
            else:
                widget.clicked.connect(lambda: self._handle_button_click(name, param_def))

        elif param_type == 'file':
            # 文件选择器类型
            file_widget = QWidget()
            file_layout = QHBoxLayout(file_widget)
            file_layout.setContentsMargins(0, 0, 0, 0)

            file_edit = QLineEdit(str(current_value) if current_value else "")
            file_button = QPushButton("浏览...")
            file_button.clicked.connect(lambda: self._select_file(file_edit, param_def))

            file_layout.addWidget(file_edit)
            file_layout.addWidget(file_button)

            widget = file_widget
            self.widgets[name] = file_edit  # 存储编辑框用于获取值

        elif param_type == 'coordinate':
            # 坐标输入类型 - 带坐标选择工具
            coord_widget = QWidget()
            coord_layout = QHBoxLayout(coord_widget)
            coord_layout.setContentsMargins(0, 0, 0, 0)

            coord_edit = QLineEdit(str(current_value) if current_value else "0,0")
            coord_edit.setPlaceholderText("X,Y")
            # 设置基本属性确保输入功能
            coord_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            coord_button = ResponsiveButton("选择坐标")
            coord_button.setStyleSheet("""
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005A9E;
                }
                QPushButton:pressed {
                    background-color: #004578;
                }
            """)
            coord_button.clicked.connect(lambda: self._select_coordinate(name))

            coord_layout.addWidget(coord_edit)
            coord_layout.addWidget(coord_button)

            widget = coord_widget
            self.widgets[name] = coord_edit  # 存储编辑框用于获取值

        else:
            # 检查是否为多图片路径参数
            if name in ['image_paths'] and param_def.get('multiline', False):
                # 多图片路径选择器
                multi_file_widget = QWidget()
                multi_file_layout = QVBoxLayout(multi_file_widget)
                multi_file_layout.setContentsMargins(0, 0, 0, 0)
                multi_file_layout.setSpacing(4)

                # 文本编辑区域
                text_edit = QTextEdit()

                # 格式化显示当前值
                if current_value:
                    display_text = self._format_existing_paths_display(str(current_value))
                    text_edit.setPlainText(display_text)
                else:
                    text_edit.setPlainText("")

                text_edit.setMaximumHeight(100)  # 增加高度以容纳更多内容
                text_edit.setPlaceholderText("每行一个图片路径，或点击下方按钮选择多个文件")

                # 设置样式
                text_edit.setStyleSheet("""
                    QTextEdit {
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        padding: 4px;
                        font-family: 'Consolas', 'Monaco', monospace;
                        font-size: 9pt;
                        line-height: 1.2;
                    }
                    QTextEdit:focus {
                        border-color: #007ACC;
                    }
                """)

                # 按钮区域
                button_layout = QHBoxLayout()
                button_layout.setContentsMargins(0, 0, 0, 0)

                select_button = QPushButton("选择多个图片...")
                select_button.setToolTip("打开文件选择对话框，选择多个图片文件")
                select_button.setStyleSheet("""
                    QPushButton {
                        background-color: #007ACC;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #005A9E;
                    }
                    QPushButton:pressed {
                        background-color: #004578;
                    }
                """)
                select_button.clicked.connect(lambda: self._select_multiple_files(text_edit, param_def))

                clear_button = QPushButton("清空")
                clear_button.setToolTip("清空所有图片路径")
                clear_button.setStyleSheet("""
                    QPushButton {
                        background-color: #dc3545;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                    }
                    QPushButton:hover {
                        background-color: #c82333;
                    }
                    QPushButton:pressed {
                        background-color: #a71e2a;
                    }
                """)
                clear_button.clicked.connect(lambda: self._clear_and_update_display(text_edit))

                # 统计信息标签
                count_label = QLabel()
                count_label.setStyleSheet("color: #666; font-size: 9pt; margin-left: 8px;")
                self._update_path_count_label(count_label, text_edit.toPlainText())

                # 连接文本变化事件以更新统计
                text_edit.textChanged.connect(lambda: self._update_path_count_label(count_label, text_edit.toPlainText()))

                button_layout.addWidget(select_button)
                button_layout.addWidget(clear_button)
                button_layout.addWidget(count_label)
                button_layout.addStretch()

                multi_file_layout.addWidget(text_edit)
                multi_file_layout.addLayout(button_layout)

                widget = multi_file_widget
                self.widgets[name] = text_edit  # 存储文本编辑框用于获取值

            elif param_def.get('multiline', False):
                # 多行文本输入
                widget = QTextEdit()
                widget.setPlainText(str(current_value) if current_value is not None else "")
                widget.setMaximumHeight(100)  # 限制高度

            else:
                # 默认单行文本输入
                widget = QLineEdit(str(current_value) if current_value is not None else "")
                # 设置基本属性确保输入功能
                widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

                # 设置占位符文本
                placeholder = param_def.get('placeholder', '')
                if placeholder:
                    widget.setPlaceholderText(placeholder)

                # 检查是否为只读
                if param_def.get('readonly', False):
                    widget.setReadOnly(True)
                    widget.setStyleSheet("""
                        QLineEdit {
                            background-color: #f0f0f0;
                            color: #666666;
                            border: 1px solid #cccccc;
                        }
                    """)

        if widget and name not in self.widgets:
            self.widgets[name] = widget

            # 确保所有输入控件都能接收焦点和输入事件
            if hasattr(widget, 'setFocusPolicy'):
                widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

            # 为可能响应滚轮的控件安装滚轮事件过滤器
            self._install_wheel_filter(widget, name)

            # 确保输入控件能正常工作
            if isinstance(widget, (QLineEdit, QSpinBox, QDoubleSpinBox)):
                # 设置基本属性确保输入功能
                widget.setEnabled(True)
                widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

                # 强制设置更多属性
                widget.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
                widget.setReadOnly(False) if hasattr(widget, 'setReadOnly') else None

                # 简化调试信息
                logger.debug(f"创建输入控件 {name}: 类型={type(widget).__name__}")

                # 为输入框添加文本变化监听（保持原有功能）
                if isinstance(widget, QLineEdit):
                    def on_text_changed(text, widget_name=name):
                        logger.debug(f"输入框 {widget_name} 文本变化: {text}")
                    widget.textChanged.connect(on_text_changed)

                    # 重写事件方法，添加焦点保护机制
                    original_focus_in = widget.focusInEvent
                    original_focus_out = widget.focusOutEvent

                    def new_focus_in(event, widget_name=name):
                        logger.debug(f"输入框 {widget_name} 获得焦点，启用焦点保护")
                        # 启用焦点保护，暂时禁用窗口激活同步
                        self._input_focus_protection_active = True
                        original_focus_in(event)

                    def new_focus_out(event, widget_name=name):
                        logger.debug(f"输入框 {widget_name} 失去焦点，延迟禁用焦点保护")
                        original_focus_out(event)
                        # 延迟禁用焦点保护，给用户切换到其他输入框的时间
                        QTimer.singleShot(500, lambda: setattr(self, '_input_focus_protection_active', False))

                    widget.focusInEvent = new_focus_in
                    widget.focusOutEvent = new_focus_out

            # 设置工具提示
            tooltip = param_def.get('tooltip', '')
            if tooltip:
                # 确保tooltip能正确显示，特别是包含换行符的长文本
                widget.setToolTip(tooltip)
                # 设置tooltip的显示时间更长一些，便于阅读
                widget.setToolTipDuration(10000)  # 10秒

            # 检查是否是影响条件显示的参数，如果是则连接信号
            self._connect_conditional_signals(name, widget)

            # 移除状态栏显示功能，避免重复多余的说明
            # self._setup_status_display(widget, name, param_def)

        row_layout.addWidget(widget)
        layout.addWidget(row_widget)

        # 添加帮助文本（如果有）
        help_text = param_def.get('help', '')
        if help_text:
            help_label = QLabel(help_text)
            help_label.setStyleSheet("color: #666666; font-size: 11px; margin-left: 148px;")  # 调整左边距
            help_label.setWordWrap(True)
            layout.addWidget(help_label)

    def _setup_status_display(self, widget: QWidget, param_name: str, param_def: Dict[str, Any]):
        """为控件设置状态栏显示功能"""
        try:
            # 获取参数说明
            label = param_def.get('label', param_name)
            tooltip = param_def.get('tooltip', '')
            param_type = param_def.get('type', 'text')

            # 构建状态信息
            status_text = f"{label}"
            if tooltip:
                status_text += f" - {tooltip}"
            else:
                status_text += f" ({param_type})"

            # 为控件添加鼠标进入和离开事件，使用延迟机制防止快速切换
            def on_enter():
                # 取消之前的延迟清空任务
                if hasattr(self, '_clear_status_timer'):
                    self._clear_status_timer.stop()
                self.status_label.setText(status_text)

            def on_leave():
                # 延迟清空状态栏，防止快速移动时闪烁
                if not hasattr(self, '_clear_status_timer'):
                    self._clear_status_timer = QTimer()
                    self._clear_status_timer.setSingleShot(True)
                    self._clear_status_timer.timeout.connect(lambda: self.status_label.setText(""))

                self._clear_status_timer.start(300)  # 300ms延迟

            # 使用信号连接的方式，更简单可靠
            if hasattr(widget, 'enterEvent'):
                original_enter = widget.enterEvent
                original_leave = widget.leaveEvent

                def new_enter_event(event):
                    on_enter()
                    if original_enter:
                        original_enter(event)

                def new_leave_event(event):
                    on_leave()
                    if original_leave:
                        original_leave(event)

                widget.enterEvent = new_enter_event
                widget.leaveEvent = new_leave_event

        except Exception as e:
            logger.warning(f"设置状态显示失败: {e}")

    def _select_file(self, line_edit: QLineEdit, param_def: Dict[str, Any]):
        """文件选择对话框"""
        file_filter = param_def.get('file_filter', 'All Files (*)')

        filename, _ = QFileDialog.getOpenFileName(self, "选择文件", "", file_filter)
        if filename:
            line_edit.setText(filename)

            # 自动应用参数
            self._apply_parameters()

    def _select_multiple_files(self, text_edit: QTextEdit, param_def: Dict[str, Any]):
        """选择多个文件"""
        try:
            from PySide6.QtWidgets import QFileDialog
            import os

            # 获取文件过滤器，默认为图片文件
            file_filter = param_def.get('file_filter', '图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)')

            # 打开多文件选择对话框
            file_paths, _ = QFileDialog.getOpenFileNames(
                self,
                "选择多个图片文件",
                "",
                file_filter
            )

            if file_paths:
                # 优化显示：显示友好的格式
                display_text = self._format_image_paths_display(file_paths)

                current_text = text_edit.toPlainText().strip()
                if current_text:
                    # 如果已有内容，追加新文件
                    new_text = current_text + '\n' + display_text
                else:
                    # 如果没有内容，直接设置
                    new_text = display_text

                text_edit.setPlainText(new_text)
                logger.info(f"已选择 {len(file_paths)} 个文件")

                # 自动应用参数
                self._apply_parameters()

        except Exception as e:
            logger.error(f"选择多个文件时发生错误: {e}")

    def _format_image_paths_display(self, file_paths):
        """格式化图片路径显示"""
        import os

        if not file_paths:
            return ""

        # 如果只有一个文件，显示完整路径
        if len(file_paths) == 1:
            return file_paths[0]

        # 多个文件时，优化显示格式
        formatted_lines = []

        # 尝试找到公共目录（处理不同驱动器的情况）
        common_dir = ""
        try:
            if len(file_paths) > 1:
                common_dir = os.path.commonpath(file_paths)
        except ValueError:
            # 不同驱动器或无法找到公共路径
            common_dir = ""

        if common_dir and len(common_dir) > 20:  # 如果公共目录路径较长
            # 显示公共目录 + 文件名
            formatted_lines.append(f"# 共同目录: {common_dir}")
            for file_path in file_paths:
                filename = os.path.basename(file_path)
                formatted_lines.append(filename)
        else:
            # 显示文件名（如果路径太长）或完整路径
            for file_path in file_paths:
                if len(file_path) > 60:  # 路径太长，只显示文件名
                    filename = os.path.basename(file_path)
                    formatted_lines.append(f"{filename}  # {os.path.dirname(file_path)}")
                else:
                    formatted_lines.append(file_path)

        return '\n'.join(formatted_lines)

    def _format_existing_paths_display(self, paths_text):
        """格式化现有路径显示"""
        import os

        if not paths_text or not paths_text.strip():
            return ""

        # 解析路径
        lines = [line.strip() for line in paths_text.split('\n') if line.strip()]

        # 过滤掉注释行和非路径行
        file_paths = []
        for line in lines:
            if not line.startswith('#') and (os.path.exists(line) or line.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))):
                file_paths.append(line)

        if not file_paths:
            return paths_text  # 如果没有有效路径，返回原文本

        # 使用相同的格式化逻辑
        return self._format_image_paths_display(file_paths)

    def _clear_and_update_display(self, text_edit):
        """清空文本编辑器并更新显示"""
        text_edit.clear()
        # 自动应用参数
        self._apply_parameters()

    def _update_path_count_label(self, label, text_content):
        """更新路径数量标签"""
        import os

        if not text_content or not text_content.strip():
            label.setText("")
            return

        # 解析路径
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]

        # 过滤掉注释行，统计有效路径
        valid_paths = []
        for line in lines:
            if not line.startswith('#'):
                valid_paths.append(line)

        count = len(valid_paths)
        if count == 0:
            label.setText("")
        elif count == 1:
            label.setText("1个文件")
        else:
            label.setText(f"{count}个文件")

    def _select_color(self, line_edit: QLineEdit):
        """汉化的Qt颜色选择对话框"""
        current_color = QColor(line_edit.text())

        # 创建颜色对话框
        dialog = QColorDialog(self)
        dialog.setWindowTitle("选择颜色")
        dialog.setCurrentColor(current_color)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)

        # 手动汉化按钮文本
        def translate_color_dialog_buttons():
            for button in dialog.findChildren(QPushButton):
                button_text = button.text().lower()
                if 'ok' in button_text or button_text == '&ok':
                    button.setText("确定(&O)")
                elif 'cancel' in button_text or button_text == '&cancel':
                    button.setText("取消(&C)")
                elif 'pick screen color' in button_text or 'screen' in button_text:
                    button.setText("屏幕取色")
                elif 'add to custom colors' in button_text or 'custom' in button_text:
                    button.setText("添加到自定义颜色")

        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, translate_color_dialog_buttons)

        if dialog.exec() == QDialog.Accepted:
            color = dialog.selectedColor()
            if color.isValid():
                line_edit.setText(color.name())

    def _select_color_rgb(self, line_edit: QLineEdit):
        """RGB格式的汉化Qt颜色选择对话框 - 专门用于找色功能"""
        current_color_str = line_edit.text()
        initial_color = QColor(255, 0, 0)  # 默认红色

        try:
            # 解析当前RGB值
            parts = [int(c.strip()) for c in current_color_str.split(',')]
            if len(parts) == 3 and all(0 <= c <= 255 for c in parts):
                initial_color = QColor(parts[0], parts[1], parts[2])
        except (ValueError, AttributeError):
            pass  # 使用默认颜色

        # 创建颜色对话框
        dialog = QColorDialog(self)
        dialog.setWindowTitle("选择目标颜色")
        dialog.setCurrentColor(initial_color)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)

        # 手动汉化按钮文本
        def translate_color_dialog_buttons():
            for button in dialog.findChildren(QPushButton):
                button_text = button.text().lower()
                if 'ok' in button_text or button_text == '&ok':
                    button.setText("确定(&O)")
                elif 'cancel' in button_text or button_text == '&cancel':
                    button.setText("取消(&C)")
                elif 'pick screen color' in button_text or 'screen' in button_text:
                    button.setText("屏幕取色")
                elif 'add to custom colors' in button_text or 'custom' in button_text:
                    button.setText("添加到自定义颜色")

        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, translate_color_dialog_buttons)

        if dialog.exec() == QDialog.Accepted:
            color = dialog.selectedColor()
            if color.isValid():
                rgb_str = f"{color.red()},{color.green()},{color.blue()}"

                # 检查是否需要追加到现有颜色
                current_text = line_edit.text().strip()
                if current_text and not current_text.endswith(rgb_str):
                    # 如果当前有内容且不是相同颜色，询问是否追加
                    from PySide6.QtWidgets import QMessageBox
                    reply = QMessageBox.question(
                        self, "颜色选择",
                        f"当前颜色: {current_text}\n新选择颜色: {rgb_str}\n\n是否追加新颜色到现有颜色组合？",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                        QMessageBox.Yes
                    )

                    if reply == QMessageBox.Yes:
                        # 追加新颜色
                        if ';' in current_text:
                            line_edit.setText(f"{current_text};{rgb_str}")
                        else:
                            line_edit.setText(f"{current_text};{rgb_str}")
                    elif reply == QMessageBox.No:
                        # 替换为新颜色
                        line_edit.setText(rgb_str)
                    # Cancel 不做任何操作
                else:
                    # 没有现有内容或相同颜色，直接设置
                    line_edit.setText(rgb_str)

    def _select_ocr_region(self, param_name: str):
        """启动OCR区域选择工具"""
        logger.info(f"📦 OCR区域选择按钮被点击，参数名: {param_name}")
        print(f"📦 OCR区域选择按钮被点击，参数名: {param_name}")

        try:
            from ui.ocr_region_selector import OCRRegionSelectorWidget

            # 获取绑定的窗口句柄
            target_window_hwnd = self._get_bound_window_hwnd()
            if not target_window_hwnd:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "警告", "未找到绑定的窗口，请先绑定目标窗口")
                return

            # 创建区域选择器，直接传递窗口句柄
            self.region_selector = OCRRegionSelectorWidget(self)

            # 设置目标窗口句柄
            if hasattr(self.region_selector, 'set_target_window_hwnd'):
                self.region_selector.set_target_window_hwnd(target_window_hwnd)
            elif hasattr(self.region_selector, 'set_target_window'):
                # 兼容旧版本，获取窗口标题
                try:
                    import win32gui
                    window_title = win32gui.GetWindowText(target_window_hwnd)
                    self.region_selector.set_target_window(window_title)
                except Exception as e:
                    logger.warning(f"获取窗口标题失败: {e}")
                    # 直接使用句柄作为标题
                    self.region_selector.set_target_window(f"窗口{target_window_hwnd}")

            # 连接信号
            self.region_selector.region_selected.connect(
                lambda x, y, w, h: self._on_ocr_region_selected(param_name, x, y, w, h)
            )

            # 开始选择
            self.region_selector.start_selection()

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", f"启动区域选择工具失败: {str(e)}")

    def _on_ocr_region_selected(self, param_name: str, x: int, y: int, width: int, height: int):
        """处理OCR区域选择完成"""
        try:
            # 更新相关参数 - 使用正确的方法设置值
            if 'region_x' in self.widgets:
                widget = self.widgets['region_x']
                if hasattr(widget, 'setValue'):
                    widget.setValue(x)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(x))

            if 'region_y' in self.widgets:
                widget = self.widgets['region_y']
                if hasattr(widget, 'setValue'):
                    widget.setValue(y)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(y))

            if 'region_width' in self.widgets:
                widget = self.widgets['region_width']
                if hasattr(widget, 'setValue'):
                    widget.setValue(width)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(width))

            if 'region_height' in self.widgets:
                widget = self.widgets['region_height']
                if hasattr(widget, 'setValue'):
                    widget.setValue(height)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(height))

            # 更新区域坐标显示
            if 'region_coordinates' in self.widgets:
                coord_text = f"X={x}, Y={y}, 宽度={width}, 高度={height}"
                self.widgets['region_coordinates'].setText(coord_text)

            # 自动应用参数
            self._apply_parameters()

        except Exception as e:
            logger.error(f"处理OCR区域选择结果失败: {e}")
            import traceback
            traceback.print_exc()

    def _select_multi_coordinates(self, param_name: str):
        """启动多点坐标选择工具"""
        logger.info(f"多点坐标选择按钮被点击，参数名: {param_name}")

        try:
            from ui.coordinate_selector import MultiPointCoordinateSelectorWidget

            # 创建多点坐标选择器
            self.multi_coordinate_selector = MultiPointCoordinateSelectorWidget(self)

            # 获取目标窗口句柄
            target_window_hwnd = self._get_target_window_hwnd()
            if target_window_hwnd:
                self.multi_coordinate_selector.target_window_hwnd = target_window_hwnd
                logger.info(f"设置多点坐标选择器窗口句柄: {target_window_hwnd}")
            else:
                logger.error("未找到目标窗口句柄")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "错误", "未找到目标窗口，请先绑定窗口")
                return

            # 连接信号
            self.multi_coordinate_selector.coordinates_selected.connect(
                lambda coords: self._on_multi_coordinates_selected(param_name, coords)
            )

            # 开始选择
            logger.info("开始启动多点坐标选择器...")
            self.multi_coordinate_selector.start_selection()

        except Exception as e:
            logger.error(f"启动多点坐标选择工具失败: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", f"启动多点坐标选择工具失败: {str(e)}")

    def _on_multi_coordinates_selected(self, param_name: str, coordinates: list):
        """处理多点坐标选择完成"""
        try:
            logger.info(f"多点坐标选择完成: {param_name}, {len(coordinates)} 个点")

            # 将坐标列表转换为文本格式
            coord_text = "\n".join([f"{x},{y}" for x, y in coordinates])

            # 更新对应的文本编辑框
            if param_name in self.widgets:
                widget = self.widgets[param_name]
                if hasattr(widget, 'setPlainText'):
                    widget.setPlainText(coord_text)
                    logger.info(f"已更新路径点坐标: {coord_text}")

            # 自动应用参数
            self._apply_parameters()

        except Exception as e:
            logger.error(f"处理多点坐标选择结果失败: {e}")

    def _select_coordinate(self, param_name: str):
        """启动坐标选择工具"""
        logger.info(f" 坐标选择按钮被点击，参数名: {param_name}")
        print(f" 坐标选择按钮被点击，参数名: {param_name}")

        try:
            from ui.coordinate_selector import CoordinateSelectorWidget

            # 创建坐标选择器
            self.coordinate_selector = CoordinateSelectorWidget(self)

            # 获取目标窗口句柄
            target_window_hwnd = self._get_target_window_hwnd()
            if target_window_hwnd:
                self.coordinate_selector.target_window_hwnd = target_window_hwnd
                logger.info(f"设置坐标选择器窗口句柄: {target_window_hwnd}")
            else:
                logger.error("未找到目标窗口句柄")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "错误", "未找到目标窗口，请先绑定窗口")
                return

            # 连接信号
            self.coordinate_selector.coordinate_selected.connect(
                lambda x, y: self._on_coordinate_selected(param_name, x, y)
            )

            # 开始选择
            logger.info(f" 开始启动坐标选择器...")
            self.coordinate_selector.start_selection()

        except Exception as e:
            logger.error(f" 启动坐标选择工具失败: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", f"启动坐标选择工具失败: {str(e)}")

    def _on_coordinate_selected(self, param_name: str, x: int, y: int):
        """处理坐标选择完成"""
        try:
            # 检查是否是滚动坐标选择器
            if param_name == 'scroll_coordinate_selector':
                # 更新滚动起始位置显示参数
                if 'scroll_start_position' in self.widgets:
                    widget = self.widgets['scroll_start_position']
                    if hasattr(widget, 'setText'):
                        widget.setText(f"{x},{y}")


                # 更新current_parameters
                self.current_parameters['scroll_start_position'] = f"{x},{y}"

                # 自动应用参数
                self._apply_parameters()
                return

            # 检查是否是拖拽坐标选择器
            if param_name == 'drag_coordinate_selector':
                # 更新拖拽起始位置显示参数
                if 'drag_start_position' in self.widgets:
                    widget = self.widgets['drag_start_position']
                    if hasattr(widget, 'setText'):
                        widget.setText(f"{x},{y}")


                # 更新current_parameters
                self.current_parameters['drag_start_position'] = f"{x},{y}"

                # 自动应用参数
                self._apply_parameters()
                return

            # 检查是否是合并的坐标参数（如滚动起始位置）
            if param_name in ['scroll_start_position']:
                # 处理合并的坐标参数
                if param_name in self.widgets:
                    widget = self.widgets[param_name]
                    if hasattr(widget, 'setText'):
                        widget.setText(f"{x},{y}")


                # 自动应用参数
                self._apply_parameters()
                return

            # 更新相关坐标参数（原有逻辑）
            if 'coordinate_x' in self.widgets:
                widget = self.widgets['coordinate_x']
                if hasattr(widget, 'setValue'):
                    widget.setValue(x)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(x))
            if 'coordinate_y' in self.widgets:
                widget = self.widgets['coordinate_y']
                if hasattr(widget, 'setValue'):
                    widget.setValue(y)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(y))

            # 自动应用参数
            self._apply_parameters()

        except Exception as e:
            logger.error(f"处理坐标选择结果失败: {e}")

    def _select_motion_region(self, param_name: str):
        """启动移动检测区域选择工具"""
        logger.info(f" 移动检测区域选择按钮被点击，参数名: {param_name}")
        print(f" 移动检测区域选择按钮被点击，参数名: {param_name}")

        try:
            from ui.ocr_region_selector import OCRRegionSelectorWidget

            # 创建区域选择器（复用OCR区域选择器）
            self.motion_region_selector = OCRRegionSelectorWidget(self)

            # 在多窗口模式下，设置第一个窗口作为模板
            target_window_title = self._get_first_window_for_selection()
            if target_window_title:
                # 设置目标窗口
                if hasattr(self.motion_region_selector, 'set_target_window'):
                    self.motion_region_selector.set_target_window(target_window_title)


            # 设置初始区域（如果有的话）
            initial_x = self.current_parameters.get('minimap_x', 1150)
            initial_y = self.current_parameters.get('minimap_y', 40)
            initial_width = self.current_parameters.get('minimap_width', 50)
            initial_height = self.current_parameters.get('minimap_height', 50)

            self.motion_region_selector.set_region(initial_x, initial_y, initial_width, initial_height)

            # 如果有目标窗口信息，直接设置给区域选择器的属性
            if self.target_window_title:
                self.motion_region_selector.target_window_title = self.target_window_title

            # 连接信号
            self.motion_region_selector.region_selected.connect(
                lambda x, y, w, h: self._on_motion_region_selected(param_name, x, y, w, h)
            )

            # 开始选择
            self.motion_region_selector.start_selection()

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", f"启动移动检测区域选择工具失败: {str(e)}")

    def _on_motion_region_selected(self, param_name: str, x: int, y: int, width: int, height: int):
        """处理移动检测区域选择完成"""
        try:
            # 更新隐藏的坐标参数
            self.current_parameters['minimap_x'] = x
            self.current_parameters['minimap_y'] = y
            self.current_parameters['minimap_width'] = width
            self.current_parameters['minimap_height'] = height

            # 更新移动识别区域显示参数
            region_text = f"X={x}, Y={y}, 宽度={width}, 高度={height}"
            if 'motion_detection_region' in self.widgets:
                widget = self.widgets['motion_detection_region']
                if hasattr(widget, 'setText'):
                    widget.setText(region_text)
            # 更新current_parameters
            self.current_parameters['motion_detection_region'] = region_text

            # 自动应用参数
            self._apply_parameters()

        except Exception as e:
            logger.error(f"处理移动检测区域选择结果失败: {e}")

    def _connect_conditional_signals(self, param_name: str, widget: QWidget):
        """为影响条件显示的参数连接信号"""
        # 检查是否有其他参数依赖于这个参数
        is_conditional_param = False
        for other_param_def in self.param_definitions.values():
            condition = other_param_def.get('condition')
            if condition:
                # 支持多条件和单条件
                if isinstance(condition, list):
                    # 多条件：检查是否有任何条件依赖于这个参数
                    for single_condition in condition:
                        if single_condition.get('param') == param_name:
                            is_conditional_param = True
                            break
                else:
                    # 单条件 - 检查主条件和AND条件
                    if condition.get('param') == param_name:
                        is_conditional_param = True
                    else:
                        # 检查AND条件
                        and_condition = condition.get('and')
                        if and_condition:
                            if isinstance(and_condition, list):
                                # 多个AND条件
                                for and_cond in and_condition:
                                    if and_cond.get('param') == param_name:
                                        is_conditional_param = True
                                        break
                            else:
                                # 单个AND条件
                                if and_condition.get('param') == param_name:
                                    is_conditional_param = True
            if is_conditional_param:
                break

        if not is_conditional_param:
            return

        # 根据控件类型连接相应的信号
        if isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(self._on_conditional_param_changed)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(self._on_conditional_param_changed)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self._on_conditional_param_changed)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self._on_conditional_param_changed)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._on_conditional_param_changed)
        elif isinstance(widget, QPlainTextEdit):
            widget.textChanged.connect(self._on_conditional_param_changed)
        elif hasattr(widget, 'button_group'):
            # 单选按钮组
            widget.button_group.buttonToggled.connect(self._on_conditional_param_changed)

    def _on_conditional_param_changed(self):
        """条件参数值发生变化时的处理"""
        logger.debug("条件参数变化，准备更新参数面板显示")

        # 延迟更新以避免频繁重建界面
        if not hasattr(self, '_update_timer'):
            from PySide6.QtCore import QTimer
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._update_conditional_display)

        self._update_timer.start(100)  # 100ms延迟

    def _update_conditional_display(self):
        """更新条件显示"""
        # 先获取当前所有参数值
        current_values = {}
        for name, widget in self.widgets.items():
            try:
                if isinstance(widget, QCheckBox):
                    current_values[name] = widget.isChecked()
                elif isinstance(widget, QSpinBox):
                    current_values[name] = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    current_values[name] = widget.value()
                elif isinstance(widget, QComboBox):
                    current_data = widget.currentData()
                    if current_data is not None:
                        current_values[name] = current_data
                    else:
                        current_values[name] = widget.currentText()
                elif isinstance(widget, QPlainTextEdit):
                    current_values[name] = widget.toPlainText()
                elif isinstance(widget, QTextEdit):
                    current_values[name] = widget.toPlainText()
                elif isinstance(widget, QLineEdit):
                    current_values[name] = widget.text()
                elif hasattr(widget, 'button_group'):
                    # 单选按钮组
                    checked_button = widget.button_group.checkedButton()
                    if checked_button:
                        current_values[name] = checked_button.property('value')
            except Exception as e:
                logger.error(f"获取参数 {name} 值时出错: {e}")

        # 调试延迟模式相关参数的变化
        if 'delay_mode' in current_values:
            print(f"调试参数面板条件更新: delay_mode={current_values['delay_mode']}")

        # 清除被隐藏参数的值（避免参数残留）
        for name, param_def in self.param_definitions.items():
            if not self._should_show_parameter(param_def):
                # 如果参数被隐藏，将其设置为默认值
                default_value = param_def.get('default', '')
                if name in current_values and current_values[name] != default_value:
                    logger.info(f"清除隐藏参数 {name} 的值: {current_values[name]} -> {default_value}")
                    current_values[name] = default_value

        # 更新当前参数
        self.current_parameters.update(current_values)

        # --- ADDED: 实时同步条件参数到TaskCard ---
        # 检查是否有影响条件显示的参数发生变化
        condition_affecting_params = set()
        for param_def in self.param_definitions.values():
            condition = param_def.get('condition')
            if condition:
                # 支持多条件和单条件
                if isinstance(condition, list):
                    # 多条件：收集所有条件参数
                    for single_condition in condition:
                        if single_condition.get('param'):
                            condition_affecting_params.add(single_condition['param'])
                else:
                    # 单条件 - 收集主条件和AND条件参数
                    if condition.get('param'):
                        condition_affecting_params.add(condition['param'])

                    # 收集AND条件参数
                    and_condition = condition.get('and')
                    if and_condition:
                        if isinstance(and_condition, list):
                            # 多个AND条件
                            for and_cond in and_condition:
                                if and_cond.get('param'):
                                    condition_affecting_params.add(and_cond['param'])
                        else:
                            # 单个AND条件
                            if and_condition.get('param'):
                                condition_affecting_params.add(and_condition['param'])

        # 如果有条件相关参数发生变化，实时同步到TaskCard
        changed_conditional_params = {}
        for param_name in condition_affecting_params:
            if param_name in current_values:
                changed_conditional_params[param_name] = current_values[param_name]

        if changed_conditional_params and self.current_card_id is not None:
            logger.info(f"实时同步条件参数到TaskCard: {changed_conditional_params}")
            self.parameters_changed.emit(self.current_card_id, changed_conditional_params)
        # --- END ADDED ---

        # 保存所有输入框的当前值和焦点状态
        saved_values = {}
        focused_widget_name = None
        cursor_position = 0

        for name, widget in self.widgets.items():
            try:
                if isinstance(widget, QLineEdit):
                    saved_values[name] = widget.text()
                    if widget.hasFocus():
                        focused_widget_name = name
                        cursor_position = widget.cursorPosition()
                elif isinstance(widget, QSpinBox):
                    saved_values[name] = widget.value()
                    if widget.hasFocus():
                        focused_widget_name = name
                elif isinstance(widget, QDoubleSpinBox):
                    saved_values[name] = widget.value()
                    if widget.hasFocus():
                        focused_widget_name = name
                elif isinstance(widget, QComboBox):
                    current_data = widget.currentData()
                    if current_data is not None:
                        saved_values[name] = current_data
                    else:
                        saved_values[name] = widget.currentText()
                elif isinstance(widget, QCheckBox):
                    saved_values[name] = widget.isChecked()
                elif isinstance(widget, QPlainTextEdit):
                    saved_values[name] = widget.toPlainText()
                    if widget.hasFocus():
                        focused_widget_name = name
                        cursor_position = widget.textCursor().position()
            except Exception as e:
                logger.debug(f"保存控件 {name} 状态失败: {e}")

        # 保存应用选择状态（如果存在）
        saved_app_selection = None
        if 'selected_app' in self.widgets and hasattr(self.widgets['selected_app'], 'currentText'):
            saved_app_selection = self.widgets['selected_app'].currentText()
            logger.info(f"保存当前应用选择: {saved_app_selection}")

        # 重新创建所有控件以应用新的条件
        self._clear_content()
        self._create_parameter_widgets()

        # 恢复所有控件的值和焦点状态
        for name, value in saved_values.items():
            if name in self.widgets:
                widget = self.widgets[name]
                try:
                    if isinstance(widget, QLineEdit):
                        widget.setText(str(value))
                        if name == focused_widget_name:
                            # 延迟设置焦点，确保控件已完全创建
                            QTimer.singleShot(10, lambda w=widget, pos=cursor_position: self._restore_focus(w, pos))
                    elif isinstance(widget, QSpinBox):
                        widget.setValue(int(value))
                        if name == focused_widget_name:
                            QTimer.singleShot(10, lambda w=widget: w.setFocus())
                    elif isinstance(widget, QDoubleSpinBox):
                        widget.setValue(float(value))
                        if name == focused_widget_name:
                            QTimer.singleShot(10, lambda w=widget: w.setFocus())
                    elif isinstance(widget, QComboBox):
                        index = widget.findData(value)
                        if index >= 0:
                            widget.setCurrentIndex(index)
                        else:
                            widget.setCurrentText(str(value))
                    elif isinstance(widget, QCheckBox):
                        widget.setChecked(bool(value))
                    elif isinstance(widget, QPlainTextEdit):
                        widget.setPlainText(str(value))
                        if name == focused_widget_name:
                            QTimer.singleShot(10, lambda w=widget, pos=cursor_position: self._restore_text_focus(w, pos))
                except Exception as e:
                    logger.debug(f"恢复控件 {name} 状态失败: {e}")

        # 恢复应用选择（如果是雷电应用管理任务且有有效的选择）
        if (saved_app_selection and
            saved_app_selection != "请先刷新应用列表" and
            'selected_app' in self.widgets and
            hasattr(self.widgets['selected_app'], 'findText')):

            app_widget = self.widgets['selected_app']
            # 先尝试直接恢复
            index = app_widget.findText(saved_app_selection)
            if index >= 0:
                app_widget.setCurrentIndex(index)
                logger.info(f"成功恢复应用选择: {saved_app_selection}")
            else:
                # 如果找不到，可能需要重新刷新应用列表
                logger.info(f"无法找到保存的应用选择: {saved_app_selection}，尝试自动刷新")
                if hasattr(self, '_handle_refresh_apps_click'):
                    try:
                        self._handle_refresh_apps_click()
                        # 刷新后再次尝试恢复
                        index = app_widget.findText(saved_app_selection)
                        if index >= 0:
                            app_widget.setCurrentIndex(index)
                            logger.info(f"刷新后成功恢复应用选择: {saved_app_selection}")
                    except Exception as e:
                        logger.warning(f"自动刷新应用列表失败: {e}")

    def _restore_focus(self, widget, cursor_position):
        """恢复输入框焦点和光标位置"""
        try:
            widget.setFocus()
            widget.setCursorPosition(cursor_position)
        except Exception as e:
            logger.debug(f"恢复焦点失败: {e}")

    def _restore_text_focus(self, widget, cursor_position):
        """恢复文本框焦点和光标位置"""
        try:
            widget.setFocus()
            cursor = widget.textCursor()
            cursor.setPosition(cursor_position)
            widget.setTextCursor(cursor)
        except Exception as e:
            logger.debug(f"恢复文本焦点失败: {e}")

    def _debug_input_widgets(self):
        """调试输入控件状态"""
        logger.info("=== 调试输入控件状态 ===")
        for name, widget in self.widgets.items():
            if isinstance(widget, (QLineEdit, QSpinBox, QDoubleSpinBox)):
                logger.info(f"控件 {name}:")
                logger.info(f"  类型: {type(widget).__name__}")
                logger.info(f"  是否启用: {widget.isEnabled()}")
                logger.info(f"  是否可见: {widget.isVisible()}")
                logger.info(f"  焦点策略: {widget.focusPolicy()}")
                logger.info(f"  是否只读: {getattr(widget, 'isReadOnly', lambda: False)()}")
                logger.info(f"  是否有焦点: {widget.hasFocus()}")
                logger.info(f"  父控件: {widget.parent()}")
                logger.info(f"  窗口: {widget.window()}")

    def _force_enable_input_widgets(self):
        """强制启用所有输入控件"""
        logger.info("强制启用所有输入控件")
        for name, widget in self.widgets.items():
            if isinstance(widget, (QLineEdit, QSpinBox, QDoubleSpinBox)):
                try:
                    # 只设置最基本的属性，避免过度干预
                    widget.setEnabled(True)

                    # 如果是文本框，确保不是只读
                    if isinstance(widget, QLineEdit):
                        widget.setReadOnly(False)

                    logger.debug(f"强制启用控件 {name}: 成功")
                except Exception as e:
                    logger.error(f"强制启用控件 {name} 失败: {e}")

    def _apply_parameters(self):
        """应用参数更改"""
        # 添加详细的调试信息
        logger.debug(f"_apply_parameters 被调用，current_card_id={self.current_card_id}, current_task_type={self.current_task_type}")

        if self.current_card_id is None:
            # 添加更详细的错误信息和调用栈
            import traceback
            logger.warning("无法应用参数：当前卡片ID为空")
            logger.warning(f"调用栈信息：\n{''.join(traceback.format_stack())}")
            logger.warning(f"当前状态 - task_type: {self.current_task_type}, param_definitions: {bool(self.param_definitions)}, widgets: {len(self.widgets)}")
            return

        logger.info(f"开始应用卡片 {self.current_card_id} 的参数")
        new_parameters = {}

        # 首先添加所有隐藏参数的当前值
        for name, param_def in self.param_definitions.items():
            if param_def.get('type') == 'hidden':
                new_parameters[name] = self.current_parameters.get(name, param_def.get('default'))

        for name, widget in self.widgets.items():
            try:
                if isinstance(widget, QCheckBox):
                    new_parameters[name] = widget.isChecked()
                elif isinstance(widget, QSpinBox):
                    new_parameters[name] = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    new_parameters[name] = widget.value()
                elif isinstance(widget, QComboBox):
                    current_data = widget.currentData()
                    if current_data is not None:
                        new_parameters[name] = current_data
                    else:
                        current_text = widget.currentText()
                        # 直接使用选择的文本（现在就是包名）
                        new_parameters[name] = current_text
                elif isinstance(widget, QPlainTextEdit):
                    new_parameters[name] = widget.toPlainText()
                elif isinstance(widget, QTextEdit):
                    new_parameters[name] = widget.toPlainText()
                elif isinstance(widget, QLineEdit):
                    text_value = widget.text()
                    # 检查参数定义，进行类型转换
                    param_def = self.param_definitions.get(name, {})
                    param_type = param_def.get('type', 'text')

                    if param_type in ['int', 'integer']:
                        try:
                            new_parameters[name] = int(text_value) if text_value else 0
                        except ValueError:
                            logger.warning(f"参数 {name} 的值 '{text_value}' 不是有效整数，使用默认值")
                            new_parameters[name] = param_def.get('default', 0)
                    elif param_type in ['float', 'double']:
                        try:
                            new_parameters[name] = float(text_value) if text_value else 0.0
                        except ValueError:
                            logger.warning(f"参数 {name} 的值 '{text_value}' 不是有效小数，使用默认值")
                            new_parameters[name] = param_def.get('default', 0.0)
                    else:
                        new_parameters[name] = text_value
                elif hasattr(widget, 'button_group'):
                    # 单选按钮组
                    checked_button = widget.button_group.checkedButton()
                    if checked_button:
                        new_parameters[name] = checked_button.property('value')
                    else:
                        # 如果没有选中任何按钮，使用默认值
                        param_def = self.param_definitions.get(name, {})
                        new_parameters[name] = param_def.get('default')
                else:
                    logger.warning(f"未知控件类型: {type(widget)} for parameter {name}")

            except Exception as e:
                logger.error(f"获取参数 {name} 的值时出错: {e}")

        # 检查是否有影响条件显示的参数发生变化
        condition_affecting_params = set()
        for param_def in self.param_definitions.values():
            condition = param_def.get('condition')
            if condition:
                # 支持多条件和单条件
                if isinstance(condition, list):
                    # 多条件：收集所有条件参数
                    for single_condition in condition:
                        if single_condition.get('param'):
                            condition_affecting_params.add(single_condition['param'])
                else:
                    # 单条件 - 收集主条件和AND条件参数
                    if condition.get('param'):
                        condition_affecting_params.add(condition['param'])

                    # 收集AND条件参数
                    and_condition = condition.get('and')
                    if and_condition:
                        if isinstance(and_condition, list):
                            # 多个AND条件
                            for and_cond in and_condition:
                                if and_cond.get('param'):
                                    condition_affecting_params.add(and_cond['param'])
                        else:
                            # 单个AND条件
                            if and_condition.get('param'):
                                condition_affecting_params.add(and_condition['param'])

        # 如果有条件相关参数发生变化，更新当前参数并重新创建界面
        needs_update = False
        for param_name in condition_affecting_params:
            if param_name in new_parameters and new_parameters[param_name] != self.current_parameters.get(param_name):
                needs_update = True
                break

        # 特殊处理：当operation_mode改变时，重置相关参数
        if 'operation_mode' in new_parameters:
            old_operation_mode = self.current_parameters.get('operation_mode')
            new_operation_mode = new_parameters['operation_mode']
            if old_operation_mode != new_operation_mode:
                logger.info(f"操作模式从 '{old_operation_mode}' 改变为 '{new_operation_mode}'，重置相关参数")
                # 重置multi_image_mode到默认值
                if 'multi_image_mode' in self.param_definitions:
                    default_multi_mode = self.param_definitions['multi_image_mode'].get('default', '单图识别')
                    new_parameters['multi_image_mode'] = default_multi_mode
                    logger.info(f"重置 multi_image_mode 为默认值: {default_multi_mode}")

        # 清除被隐藏参数的值（避免参数残留）
        # 但保留重要参数（如图片路径），即使被隐藏也不清空
        preserved_params = {'image_path', 'image_paths', 'rotate_target_image'}  # 保留的关键参数

        for name, param_def in self.param_definitions.items():
            # 跳过需要保留的参数
            if name in preserved_params:
                continue

            if not self._should_show_parameter(param_def):
                # 如果参数被隐藏，将其设置为默认值
                default_value = param_def.get('default', '')
                if name in new_parameters and new_parameters[name] != default_value:
                    logger.info(f"清除隐藏参数 {name} 的值: {new_parameters[name]} -> {default_value}")
                    new_parameters[name] = default_value

        # 更新当前参数
        self.current_parameters.update(new_parameters)

        if needs_update:
            # 重新创建界面以应用条件显示
            self._update_conditional_display()

        logger.info(f"应用参数更改: {new_parameters}")
        logger.info(f"发出参数更改信号: card_id={self.current_card_id}")
        self.parameters_changed.emit(self.current_card_id, new_parameters)



    def _reset_parameters(self):
        """重置参数到默认值"""
        if not self.param_definitions:
            return

        # 重置所有控件到默认值
        for name, param_def in self.param_definitions.items():
            if name in self.widgets:
                widget = self.widgets[name]
                default_value = param_def.get('default')

                try:
                    if isinstance(widget, QCheckBox):
                        widget.setChecked(bool(default_value))
                    elif isinstance(widget, QSpinBox):
                        widget.setValue(int(default_value) if default_value is not None else 0)
                    elif isinstance(widget, QDoubleSpinBox):
                        widget.setValue(float(default_value) if default_value is not None else 0.0)
                    elif isinstance(widget, QLineEdit):
                        widget.setText(str(default_value) if default_value is not None else "")
                    elif isinstance(widget, QComboBox):
                        if default_value is not None:
                            index = widget.findData(default_value)
                            if index >= 0:
                                widget.setCurrentIndex(index)
                            else:
                                widget.setCurrentText(str(default_value))
                except Exception as e:
                    logger.error(f"重置控件 {name} 失败: {e}")

    def _get_target_window_hwnd(self):
        """获取目标窗口句柄"""
        try:
            logger.info("获取目标窗口句柄...")

            # 首先检查参数面板自身是否有窗口句柄
            if hasattr(self, 'target_window_hwnd') and self.target_window_hwnd:
                logger.info(f"参数面板有目标窗口句柄: {self.target_window_hwnd}")
                return self.target_window_hwnd

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
            logger.error(f"获取目标窗口句柄失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return None

    def _get_first_window_for_selection(self):
        """获取第一个窗口用于框选区域或坐标选择"""
        try:
            # 首先检查参数面板自身是否有目标窗口信息
            if hasattr(self, 'target_window_title') and self.target_window_title:
                return self.target_window_title

            # 向上查找主窗口，获取绑定的窗口列表
            current_widget = self.parent()
            level = 0

            while current_widget and level < 10:  # 最多向上查找10层
                # 检查是否有bound_windows属性（多窗口模式）
                if hasattr(current_widget, 'bound_windows'):
                    bound_windows = current_widget.bound_windows
                    if bound_windows and len(bound_windows) > 0:
                        # 获取第一个启用的窗口
                        for window_info in bound_windows:
                            if window_info.get('enabled', True):
                                window_title = window_info.get('title')
                                if window_title:
                                    return window_title

                        # 如果没有启用的窗口，使用第一个窗口
                        first_window = bound_windows[0]
                        window_title = first_window.get('title')
                        if window_title:
                            return window_title

                # 检查是否有current_target_window_title属性（单窗口模式）
                if hasattr(current_widget, 'current_target_window_title'):
                    window_title = current_widget.current_target_window_title
                    if window_title:
                        return window_title

                # 检查是否有config属性
                if hasattr(current_widget, 'config'):
                    config = current_widget.config
                    if config and hasattr(config, 'get'):
                        # 单窗口模式
                        target_window_title = config.get('target_window_title')
                        if target_window_title:
                            return target_window_title

                        # 多窗口模式
                        bound_windows = config.get('bound_windows', [])
                        if bound_windows:
                            for window_info in bound_windows:
                                if window_info.get('enabled', True):
                                    window_title = window_info.get('title')
                                    if window_title:
                                        return window_title

                # 向上查找父窗口
                current_widget = current_widget.parent()
                level += 1

            return None
        except Exception as e:
            logger.error(f"获取第一个窗口失败: {e}")
            return None

    def _handle_refresh_apps_click(self):
        """处理刷新应用列表按钮点击"""
        try:
            # 检查当前任务类型
            current_task_type = getattr(self, 'current_task_type', None)
            logger.info(f"刷新应用列表 - 当前任务类型: {current_task_type}")

            if current_task_type == "MuMu应用管理":
                self._handle_mumu_refresh_apps()
            elif current_task_type == "雷电应用管理":
                self._handle_ldplayer_refresh_apps()
            else:
                logger.warning(f"不支持的任务类型: {current_task_type}")

        except Exception as e:
            logger.error(f"刷新应用列表失败: {e}")

    def _handle_mumu_refresh_apps(self):
        """处理MuMu模拟器刷新应用列表"""
        try:
            # 获取绑定的窗口句柄（可能是渲染窗口）
            bound_hwnd = self._get_bound_window_hwnd()

            if not bound_hwnd:
                logger.warning("未找到绑定的窗口")
                return

            # 如果绑定的是渲染窗口，需要找到对应的主窗口
            main_hwnd = self._get_mumu_main_window_from_bound_window(bound_hwnd)

            if not main_hwnd:
                logger.warning("无法从绑定窗口找到MuMu主窗口")
                return

            logger.info(f"使用MuMu主窗口获取应用列表: HWND={main_hwnd}")

            # 导入MuMu应用管理模块
            import tasks.mumu_app_manager as mumu_app_manager

            # 刷新应用列表（使用主窗口句柄）
            app_list = mumu_app_manager.refresh_apps_list(target_hwnd=main_hwnd)

            # 更新下拉框选项
            if hasattr(self, 'widgets') and 'selected_app' in self.widgets:
                combo_box = self.widgets['selected_app']
                if combo_box:
                    combo_box.clear()
                    combo_box.addItems(app_list)
                    logger.info(f"MuMu应用列表已更新，共 {len(app_list)} 个应用")

        except Exception as e:
            logger.error(f"刷新MuMu应用列表失败: {e}")

    def _get_bound_window_hwnd(self):
        """获取绑定的窗口句柄"""
        try:
            logger.debug("开始获取绑定窗口句柄...")

            # 尝试从主窗口获取绑定窗口信息
            main_window = getattr(self, 'main_window', None) or getattr(self, 'parent_window', None)
            if main_window:
                logger.debug(f"找到主窗口: {type(main_window)}")

                # 检查主窗口的所有相关属性
                logger.debug(f"主窗口属性检查:")
                logger.debug(f"  - window_binding_mode: {getattr(main_window, 'window_binding_mode', '未设置')}")
                logger.debug(f"  - target_window_hwnd: {getattr(main_window, 'target_window_hwnd', '未设置')}")
                logger.debug(f"  - bound_windows: {len(getattr(main_window, 'bound_windows', []))} 个")

                # 检查是否是多窗口模式
                if hasattr(main_window, 'window_binding_mode'):
                    binding_mode = main_window.window_binding_mode
                    logger.debug(f"窗口绑定模式: {binding_mode}")

                    if binding_mode == 'multiple':
                        # 多窗口模式：根据任务类型选择匹配的窗口
                        if hasattr(main_window, 'bound_windows') and main_window.bound_windows:
                            logger.debug(f"找到绑定窗口列表，共 {len(main_window.bound_windows)} 个")
                            enabled_windows = [w for w in main_window.bound_windows if w.get('enabled', True)]
                            logger.debug(f"启用的窗口数量: {len(enabled_windows)}")

                            if enabled_windows:
                                # 根据当前任务类型选择匹配的窗口
                                matched_window = self._find_matching_window_for_task(enabled_windows)
                                if matched_window:
                                    hwnd = matched_window.get('hwnd')
                                    title = matched_window.get('title', '未知')
                                    logger.info(f"根据任务类型选择匹配窗口: {title} (HWND: {hwnd})")
                                    return hwnd
                                else:
                                    # 如果没有匹配的，使用第一个启用的窗口
                                    hwnd = enabled_windows[0].get('hwnd')
                                    title = enabled_windows[0].get('title', '未知')
                                    logger.warning(f"未找到匹配任务类型的窗口，使用第一个: {title} (HWND: {hwnd})")
                                    return hwnd
                            else:
                                logger.warning("没有启用的绑定窗口")
                        else:
                            logger.warning("多窗口模式但没有绑定窗口列表")
                    else:
                        # 单窗口模式：获取目标窗口句柄
                        if hasattr(main_window, 'target_window_hwnd') and main_window.target_window_hwnd:
                            hwnd = main_window.target_window_hwnd
                            logger.info(f"获取到单窗口模式目标窗口: HWND={hwnd}")
                            return hwnd
                        # 如果单窗口模式没有target_window_hwnd，尝试从bound_windows获取
                        elif hasattr(main_window, 'bound_windows') and main_window.bound_windows:
                            logger.debug("单窗口模式但有bound_windows，尝试从中获取")
                            enabled_windows = [w for w in main_window.bound_windows if w.get('enabled', True)]
                            if enabled_windows:
                                hwnd = enabled_windows[0].get('hwnd')
                                title = enabled_windows[0].get('title', '未知')
                                logger.info(f"从bound_windows获取到窗口: {title} (HWND: {hwnd})")
                                return hwnd
                            else:
                                logger.warning("bound_windows中没有启用的窗口")
                        else:
                            logger.warning("单窗口模式但没有target_window_hwnd属性，也没有bound_windows")
                else:
                    logger.warning("主窗口没有window_binding_mode属性")
            else:
                logger.warning("没有找到主窗口或main_window为None")

            logger.warning("无法获取绑定窗口句柄")
            return None
        except Exception as e:
            logger.error(f"获取绑定窗口句柄失败: {e}")
            return None

    def _find_matching_window_for_task(self, enabled_windows):
        """根据当前任务类型找到匹配的窗口"""
        try:
            current_task_type = getattr(self, 'current_task_type', None)
            if not current_task_type:
                logger.debug("没有当前任务类型，无法进行窗口匹配")
                return None

            logger.debug(f"为任务类型 '{current_task_type}' 查找匹配窗口")

            # 检测每个窗口的模拟器类型
            from utils.emulator_detector import detect_emulator_type

            for window in enabled_windows:
                hwnd = window.get('hwnd')
                title = window.get('title', '未知')

                if not hwnd:
                    continue

                # 检测窗口的模拟器类型
                is_emulator, emulator_type, description = detect_emulator_type(hwnd)
                logger.debug(f"窗口 {title} (HWND: {hwnd}) 检测结果: {emulator_type}")

                # 根据任务类型匹配窗口
                if current_task_type == "MuMu应用管理" and emulator_type == "mumu":
                    logger.info(f"为MuMu应用管理任务找到匹配窗口: {title}")
                    return window
                elif current_task_type == "雷电应用管理" and emulator_type == "ldplayer":
                    logger.info(f"为雷电应用管理任务找到匹配窗口: {title}")
                    return window

            logger.warning(f"未找到与任务类型 '{current_task_type}' 匹配的窗口")
            return None

        except Exception as e:
            logger.error(f"查找匹配窗口时出错: {e}")
            return None

    def _get_mumu_main_window_from_bound_window(self, bound_hwnd):
        """从绑定窗口（可能是渲染窗口）获取MuMu主窗口"""
        try:
            # 首先检查绑定窗口是否已经是主窗口
            import win32gui
            window_title = win32gui.GetWindowText(bound_hwnd)
            window_class = win32gui.GetClassName(bound_hwnd)

            # 如果是MuMu主窗口，直接返回
            if (window_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and
                "mumu" in window_title.lower()):
                logger.debug(f"绑定窗口已经是MuMu主窗口: {window_title}")
                return bound_hwnd

            # 如果是渲染窗口，查找对应的主窗口
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(bound_hwnd)

            if is_emulator and emulator_type == "mumu":
                # 使用EmulatorWindow的父窗口查找逻辑
                from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
                emulator_window = EmulatorWindowInputSimulator(bound_hwnd, "mumu", "background")
                main_hwnd = emulator_window._get_mumu_parent_window()
                if main_hwnd:
                    main_title = win32gui.GetWindowText(main_hwnd)
                    logger.debug(f"从渲染窗口找到MuMu主窗口: {window_title} -> {main_title}")
                    return main_hwnd

            # 如果都失败，尝试通过窗口层次结构查找
            return self._find_mumu_main_window_by_hierarchy(bound_hwnd)

        except Exception as e:
            logger.error(f"获取MuMu主窗口失败: {e}")
            return None

    def _find_mumu_main_window_by_hierarchy(self, hwnd):
        """通过窗口层次结构查找MuMu主窗口"""
        try:
            import win32gui

            # 向上查找父窗口
            current_hwnd = hwnd
            for _ in range(5):  # 最多查找5层
                parent_hwnd = win32gui.GetParent(current_hwnd)
                if not parent_hwnd:
                    break

                try:
                    parent_title = win32gui.GetWindowText(parent_hwnd)
                    parent_class = win32gui.GetClassName(parent_hwnd)

                    # 检查是否是MuMu主窗口
                    if (parent_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"] and
                        "mumu" in parent_title.lower()):
                        logger.debug(f"通过层次结构找到MuMu主窗口: {parent_title}")
                        return parent_hwnd
                except:
                    pass

                current_hwnd = parent_hwnd

            return None
        except Exception as e:
            logger.debug(f"通过层次结构查找MuMu主窗口失败: {e}")
            return None

    def _handle_ldplayer_refresh_apps(self):
        """处理雷电模拟器刷新应用列表"""
        try:
            import win32gui

            # 使用参数面板的目标窗口信息
            target_window_title = getattr(self, 'target_window_title', None)

            # 如果没有目标窗口，尝试从其他地方获取
            if not target_window_title:
                # 检查是否有存储的窗口标题
                if hasattr(self, 'current_parameters') and 'target_window_title' in self.current_parameters:
                    target_window_title = self.current_parameters['target_window_title']

            # 如果还是没有，使用默认的 TheRender
            if not target_window_title:
                target_window_title = "TheRender"

            # 查找LDPlayer主窗口
            def find_ldplayer_main_window():
                """查找LDPlayer主窗口"""
                def enum_windows_proc(hwnd, lParam):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            class_name = win32gui.GetClassName(hwnd)
                            window_title = win32gui.GetWindowText(hwnd)

                            # 查找LDPlayer主窗口
                            if class_name == "LDPlayerMainFrame":
                                lParam.append(hwnd)
                    except:
                        pass
                    return True

                windows = []
                win32gui.EnumWindows(enum_windows_proc, windows)
                return windows[0] if windows else None

            # 查找LDPlayer主窗口
            main_hwnd = find_ldplayer_main_window()

            if not main_hwnd:
                logger.warning("未找到LDPlayer主窗口")
                return

            # 直接使用主窗口进行应用管理
            final_hwnd = main_hwnd

            # 导入雷电应用管理模块
            import tasks.ldplayer_app_manager as ldplayer_app_manager

            # 使用智能ADB连接器获取应用列表
            try:
                from utils.intelligent_adb_connector import IntelligentADBConnector

                connector = IntelligentADBConnector()
                connector.discover_adb_paths()
                connector.discover_emulator_windows()
                connections = connector.connect_all_devices()

                # 查找与当前窗口匹配的连接
                target_connection = None
                for conn in connections:
                    # 通过窗口句柄匹配连接
                    if self._is_connection_for_window(conn, final_hwnd):
                        target_connection = conn
                        break

                if not target_connection and connections:
                    # 如果没有精确匹配，使用第一个可用连接
                    target_connection = connections[0]

                if not target_connection:
                    raise Exception("No ADB connections available")

                # 使用智能连接器获取已安装的应用包名和名称
                import subprocess
                result = subprocess.run([target_connection.adb_path, '-s', target_connection.device_id,
                                       'shell', 'pm', 'list', 'packages', '-3'],
                                      capture_output=True, text=True, timeout=10,
                                      creationflags=subprocess.CREATE_NO_WINDOW,
                                      encoding='utf-8', errors='ignore')

                if result.returncode == 0:
                    package_lines = result.stdout.strip().split('\n')
                    apps = []

                    # 快速处理所有包名，不做额外查询
                    for line in package_lines:
                        if line.startswith('package:'):
                            package_name = line.replace('package:', '').strip()
                            if package_name:
                                # 直接添加到应用列表，不做任何额外查询
                                apps.append({
                                    'name': package_name,  # 直接使用包名
                                    'package': package_name
                                })

                else:
                    # 回退到原来的方法
                    apps = ldplayer_app_manager.refresh_app_list(final_hwnd)

            except subprocess.TimeoutExpired:
                apps = ldplayer_app_manager.refresh_app_list(final_hwnd)
            except FileNotFoundError:
                apps = ldplayer_app_manager.refresh_app_list(final_hwnd)
            except Exception as e:
                logger.error(f"使用智能ADB连接器获取应用列表时出错: {e}")
                apps = ldplayer_app_manager.refresh_app_list(final_hwnd)

            # 更新选择应用的下拉框选项
            if 'selected_app' in self.widgets:
                app_widget = self.widgets['selected_app']
                if hasattr(app_widget, 'clear') and hasattr(app_widget, 'addItems'):
                    app_widget.clear()
                    if apps:
                        # 存储应用信息，用于后续查找包名
                        self.app_mapping = {}
                        app_names = []

                        for app in apps:
                            package_name = app['package']  # 直接使用包名
                            app_names.append(package_name)  # 显示包名

                        app_widget.addItems(app_names)
                        logger.info(f"雷电应用列表已更新，共 {len(app_names)} 个应用")
                    else:
                        app_widget.addItem("未找到应用")
                        self.app_mapping = {}

        except Exception as e:
            logger.error(f"刷新雷电应用列表失败: {e}")
            import traceback
            traceback.print_exc()

    def _is_connection_for_window(self, connection, hwnd):
        """判断ADB连接是否对应指定窗口"""
        try:
            # 检测窗口的模拟器类型
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

            # 如果连接的模拟器类型与窗口类型匹配
            if connection.emulator_type == emulator_type:
                return True

            # 如果无法精确匹配，返回False让调用者使用第一个可用连接
            return False

        except Exception as e:
            logger.debug(f"连接窗口匹配失败: {e}")
            return False

    def _get_adb_device_for_window(self, adb_cmd, hwnd):
        """获取指定窗口对应的ADB设备ID - 使用智能ADB连接器"""
        try:
            from utils.intelligent_adb_connector import IntelligentADBConnector

            logger.info(f"使用智能ADB连接器获取窗口 {hwnd} 对应的设备")

            connector = IntelligentADBConnector()
            connector.discover_adb_paths()
            connector.discover_emulator_windows()
            connections = connector.connect_all_devices()

            if not connections:
                logger.warning("智能连接器未发现任何设备连接")
                return None

            # 查找与当前窗口匹配的连接
            for conn in connections:
                if self._is_connection_for_window(conn, hwnd):
                    logger.info(f"✅ 找到匹配连接: {conn.device_id}")
                    return conn.device_id

            # 如果没有精确匹配，使用第一个可用连接
            first_connection = connections[0]
            logger.info(f"⚠️ 未找到精确匹配，使用第一个设备: {first_connection.device_id}")
            return first_connection.device_id

        except Exception as e:
            logger.error(f"智能ADB连接器获取设备失败: {e}")
            return None

    def _get_adb_path_for_window(self, hwnd):
        """根据窗口类型获取对应的ADB路径"""
        try:
            # 检测窗口的模拟器类型
            from utils.emulator_detector import detect_emulator_type
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

            logger.info(f"检测窗口 {hwnd} 的模拟器类型: {emulator_type}")

            if emulator_type == "ldplayer":
                # 雷电模拟器：使用雷电的ADB
                from utils.ldplayer_finder import get_adb_path
                adb_path = get_adb_path()
                logger.info(f"雷电模拟器使用ADB路径: {adb_path}")
                return adb_path

            elif emulator_type == "mumu":
                # MuMu模拟器：使用MuMu的ADB
                try:
                    from utils.mumu_finder import get_mumu_adb_path
                    adb_path = get_mumu_adb_path()
                    logger.info(f"MuMu模拟器使用ADB路径: {adb_path}")
                    return adb_path
                except ImportError:
                    logger.warning("MuMu ADB查找器不可用，回退到通用方法")

            # 其他情况：使用通用ADB查找
            logger.info("使用通用ADB查找方法")
            from utils.smart_adb_finder import SmartADBFinder
            finder = SmartADBFinder()
            adb_paths = finder.find_all_adb_paths()

            if adb_paths:
                # 根据模拟器类型优先选择
                if emulator_type == "ldplayer":
                    # 优先选择雷电的ADB
                    ldplayer_paths = [p for p in adb_paths if 'leidian' in p.lower() or 'ldplayer' in p.lower()]
                    if ldplayer_paths:
                        logger.info(f"为雷电模拟器选择ADB: {ldplayer_paths[0]}")
                        return ldplayer_paths[0]
                elif emulator_type == "mumu":
                    # 优先选择MuMu的ADB
                    mumu_paths = [p for p in adb_paths if 'mumu' in p.lower()]
                    if mumu_paths:
                        logger.info(f"为MuMu模拟器选择ADB: {mumu_paths[0]}")
                        return mumu_paths[0]

                # 如果没有找到对应的，使用第一个可用的
                logger.info(f"使用第一个可用的ADB: {adb_paths[0]}")
                return adb_paths[0]

            logger.error("未找到任何可用的ADB路径")
            return None

        except Exception as e:
            logger.error(f"获取窗口对应ADB路径失败: {e}")
            return None

    def _handle_button_click(self, name: str, param_def: Dict[str, Any]):
        """处理其他按钮点击"""
        widget_hint = param_def.get('widget_hint', '')

        logger.warning(f"未处理的按钮点击: {name}, widget_hint: {widget_hint}")

    def _collect_current_parameters(self) -> Dict[str, Any]:
        """收集当前参数值"""
        parameters = {}

        # 首先添加所有隐藏参数的当前值
        for name, param_def in self.param_definitions.items():
            if param_def.get('type') == 'hidden':
                parameters[name] = self.current_parameters.get(name, param_def.get('default'))

        # 从UI控件收集参数值
        for name, widget in self.widgets.items():
            try:
                # 检查参数是否需要保存到工作流
                param_def = self.param_definitions.get(name, {})
                save_to_workflow = param_def.get('save_to_workflow', True)

                # 如果参数标记为不保存到工作流，跳过
                if not save_to_workflow:
                    continue
                if isinstance(widget, QCheckBox):
                    parameters[name] = widget.isChecked()
                elif isinstance(widget, QSpinBox):
                    parameters[name] = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    parameters[name] = widget.value()
                elif isinstance(widget, QComboBox):
                    current_data = widget.currentData()
                    if current_data is not None:
                        parameters[name] = current_data
                    else:
                        parameters[name] = widget.currentText()
                elif isinstance(widget, QPlainTextEdit):
                    parameters[name] = widget.toPlainText()
                elif isinstance(widget, QTextEdit):
                    parameters[name] = widget.toPlainText()
                elif isinstance(widget, QLineEdit):
                    text_value = widget.text()
                    # 检查参数定义，进行类型转换
                    param_def = self.param_definitions.get(name, {})
                    param_type = param_def.get('type', 'text')

                    if param_type in ['int', 'integer']:
                        try:
                            parameters[name] = int(text_value) if text_value else 0
                        except ValueError:
                            parameters[name] = param_def.get('default', 0)
                    elif param_type in ['float', 'double']:
                        try:
                            parameters[name] = float(text_value) if text_value else 0.0
                        except ValueError:
                            parameters[name] = param_def.get('default', 0.0)
                    else:
                        parameters[name] = text_value
                elif hasattr(widget, 'layout'):
                    # 文件选择器控件
                    layout = widget.layout()
                    if layout and layout.count() > 0:
                        line_edit = layout.itemAt(0).widget()
                        if hasattr(line_edit, 'text'):
                            parameters[name] = line_edit.text()
                else:
                    logger.debug(f"未处理的控件类型: {name} - {type(widget)}")

            except Exception as e:
                logger.error(f"收集参数 {name} 时出错: {e}")
                # 使用默认值
                param_def = self.param_definitions.get(name, {})
                parameters[name] = param_def.get('default')

        return parameters

    def _get_target_hwnd_with_info(self) -> tuple[Optional[int], Optional[str]]:
        """获取目标窗口句柄和窗口标题"""
        try:
            import win32gui

            logger.debug("开始获取目标窗口句柄和信息...")

            # 检查父窗口是否存在
            if not self.parent_window:
                logger.error("父窗口不存在")
                return None, None

            # 从绑定窗口列表获取第一个有效窗口（多窗口时使用第一个）
            if hasattr(self.parent_window, 'bound_windows'):
                bound_windows = self.parent_window.bound_windows
                logger.debug(f"找到绑定窗口列表，共 {len(bound_windows)} 个窗口")

                if bound_windows:
                    # 使用第一个窗口进行录制
                    first_window = bound_windows[0]
                    window_title = first_window.get('title', '未知')
                    hwnd = first_window.get('hwnd')
                    enabled = first_window.get('enabled', True)

                    logger.info(f"多窗口录制：使用第一个窗口 - {window_title} (句柄: {hwnd}, 启用: {enabled})")

                    if hwnd and win32gui.IsWindow(hwnd):
                        logger.info(f"选择录制窗口: {window_title} (句柄: {hwnd})")
                        return hwnd, window_title
                    else:
                        logger.warning(f"第一个窗口句柄已失效: {window_title} (句柄: {hwnd})")
            else:
                logger.debug("父窗口没有bound_windows属性")

            # 检查是否有current_target_hwnd
            if hasattr(self.parent_window, 'current_target_hwnd'):
                hwnd = self.parent_window.current_target_hwnd
                if hwnd and win32gui.IsWindow(hwnd):
                    window_title = win32gui.GetWindowText(hwnd)
                    logger.info(f"使用current_target_hwnd: {hwnd} ({window_title})")
                    return hwnd, window_title
                elif hwnd:
                    logger.warning(f"current_target_hwnd已失效: {hwnd}")
            else:
                logger.debug("父窗口没有current_target_hwnd属性")

            logger.error("未找到任何有效的绑定窗口句柄")
            return None, None

        except Exception as e:
            logger.error(f"获取目标窗口句柄失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return None, None



    def _get_target_hwnd(self) -> Optional[int]:
        """获取目标窗口句柄 - 直接使用全局设置中的绑定窗口"""
        try:
            import win32gui

            logger.debug("开始获取目标窗口句柄...")

            # 检查父窗口是否存在
            if not self.parent_window:
                logger.error("父窗口不存在")
                return None

            # 从绑定窗口列表获取第一个有效窗口
            if hasattr(self.parent_window, 'bound_windows'):
                bound_windows = self.parent_window.bound_windows
                logger.debug(f"找到绑定窗口列表，共 {len(bound_windows)} 个窗口")

                for i, window_info in enumerate(bound_windows):
                    window_title = window_info.get('title', '未知')
                    hwnd = window_info.get('hwnd')
                    enabled = window_info.get('enabled', True)

                    logger.debug(f"检查窗口 {i+1}: {window_title}, hwnd={hwnd}, enabled={enabled}")

                    if enabled and hwnd:
                        # 验证窗口句柄是否有效
                        if win32gui.IsWindow(hwnd):
                            logger.info(f"找到有效的绑定窗口: {window_title} (句柄: {hwnd})")
                            return hwnd
                        else:
                            logger.warning(f"绑定窗口句柄已失效: {window_title} (句柄: {hwnd})")

                # 如果没有启用的窗口，尝试使用第一个窗口
                if bound_windows:
                    first_window = bound_windows[0]
                    hwnd = first_window.get('hwnd')
                    if hwnd and win32gui.IsWindow(hwnd):
                        logger.info(f"使用第一个绑定窗口: {first_window.get('title', '未知')} (句柄: {hwnd})")
                        return hwnd
            else:
                logger.debug("父窗口没有bound_windows属性")

            # 检查是否有current_target_hwnd
            if hasattr(self.parent_window, 'current_target_hwnd'):
                hwnd = self.parent_window.current_target_hwnd
                if hwnd and win32gui.IsWindow(hwnd):
                    logger.info(f"使用current_target_hwnd: {hwnd}")
                    return hwnd
                elif hwnd:
                    logger.warning(f"current_target_hwnd已失效: {hwnd}")
            else:
                logger.debug("父窗口没有current_target_hwnd属性")

            logger.error("全局设置中没有有效的绑定窗口句柄")
            return None

        except Exception as e:
            logger.error(f"获取目标窗口句柄失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return None
