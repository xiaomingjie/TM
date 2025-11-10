import logging
logger = logging.getLogger(__name__)
import sys
import os # <<< ADDED: Import os for path operations
from functools import partial # <<< ADDED: Import partial
from typing import Dict, Any, Optional, Tuple, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, 
    QSpinBox, QDoubleSpinBox, QPushButton, QDialogButtonBox, QWidget, 
    QFrame, QCheckBox, QFileDialog, QApplication,
    QRadioButton, QButtonGroup, QPlainTextEdit, QColorDialog # <-- ADD QColorDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor # <-- ADD QColor
import numpy as np
import cv2
# Import custom widgets - Removed
# from .custom_widgets import LeftAlignedSpinBox, LeftAlignedDoubleSpinBox

class ParameterDialog(QDialog):
    """A dialog for editing task parameters."""
    def __init__(self, param_definitions: Dict[str, Dict[str, Any]], 
                 current_parameters: Dict[str, Any], 
                 title: str,
                 task_type: str, # <<< ADDED: Explicit task_type parameter
                 # --- ADDED: Receive workflow cards info --- 
                 workflow_cards_info: Optional[Dict[int, tuple[str, int]]] = None, # {seq_id: (task_type, card_id)}
                 # -------------------------------------------
                 images_dir: Optional[str] = None, # <<< ADDED: Receive images_dir
                 editing_card_id: Optional[int] = None, # <<< ADDED: ID of the card being edited
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500) # 加宽界面以提供更好的显示效果
        # 工具 修复：不设置固定初始大小，让对话框根据内容自动调整
        # self.resize(500, 400) # 设置初始大小

        self.param_definitions = param_definitions
        self.current_parameters = current_parameters.copy() # Work on a copy

        # 添加调试日志
        logger.info(f"=== 参数对话框初始化 ===")
        logger.info(f"任务类型: {task_type}")
        logger.info(f"传入的current_parameters:")
        for key, value in current_parameters.items():
            logger.info(f"  {key}: {value}")
        logger.info(f"========================")

        # 添加更多调试信息
        print(f"!!! ParameterDialog __init__ 开始 !!!")
        print(f"任务类型: {task_type}")
        print(f"参数定义数量: {len(param_definitions)}")
        print(f"参数定义键: {list(param_definitions.keys())}")
        if 'refresh_apps' in param_definitions:
            print(f"!!! 找到 refresh_apps 参数定义 !!!")
            print(f"refresh_apps 定义: {param_definitions['refresh_apps']}")
        else:
            print(f"!!! 未找到 refresh_apps 参数定义 !!!")
        self.widgets: Dict[str, QWidget] = {} # To retrieve values later
        self.images_dir = images_dir # <<< ADDED: Store images_dir
        self.editing_card_id = editing_card_id # <<< ADDED: Store editing_card_id
        self.task_type = task_type # <<< ADDED: Store task_type
        # Store row layout widgets for visibility control
        self.row_widgets: Dict[str, QWidget] = {}
        # Store jump target widgets specifically to enable/disable
        self.jump_target_widgets: Dict[str, QComboBox] = {} # <<< Changed type to QComboBox
        # --- ADDED: Store workflow info ---
        self.workflow_cards_info = workflow_cards_info if workflow_cards_info else {}
        # --- ADDED: Store app selector combo for ldplayer app manager ---
        self.app_selector_combo = None
        # --- ADDED: Store dynamic module parameter widgets ---
        self.dynamic_param_widgets: List[QWidget] = []
        # ----------------------------------

        # 工具 简化：直接使用内联逻辑处理模拟鼠标操作参数

        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(12) # Increase spacing
        self.main_layout.setContentsMargins(15, 15, 15, 15) # Add margins

        # Parameter area layout
        self.params_layout = QVBoxLayout()
        self.params_layout.setSpacing(10) # Adjust spacing within params
        # TODO: Consider QScrollArea if parameters are numerous
        
        # --- Dynamically create widgets based on definitions ---
        print(f"=== 开始创建参数控件，任务类型: {task_type} ===")
        print(f"参数定义数量: {len(param_definitions)}")
        for name, param_def in param_definitions.items():
            print(f"  参数: {name}, 类型: {param_def.get('type')}, widget_hint: {param_def.get('widget_hint')}")

        print(f"!!! 即将调用 _create_widgets() !!!")
        self._create_widgets()
        print(f"!!! _create_widgets() 调用完成 !!!")
        self._setup_conditional_visibility() # Setup initial visibility/state

        self.main_layout.addLayout(self.params_layout)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        # separator.setObjectName("dialogSeparator") # Assign object name for styling
        self.main_layout.addWidget(separator)

        # --- Dialog Buttons (修复版本) ---
        self.button_box = QDialogButtonBox()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")

        # 工具 修复：直接连接按钮信号，不使用QDialogButtonBox的角色系统
        print(f"搜索 设置按钮连接...")
        self.ok_button.clicked.connect(lambda: self._on_ok_clicked())
        self.cancel_button.clicked.connect(lambda: self._on_cancel_clicked())

        # 仍然添加到按钮框中以保持布局
        self.button_box.addButton(self.ok_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.button_box.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)

        # 工具 修复：不使用QDialogButtonBox的信号，因为它们有问题
        # self.button_box.accepted.connect(self.accept)
        # self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)
        
        # Apply Stylesheet
        self._apply_stylesheet()

        # 工具 修复：在初始化完成后调整对话框大小
        QTimer.singleShot(0, self._initial_size_adjustment)

    def _create_widgets(self):
        """Creates input widgets based on parameter definitions."""
        print(f"!!! _create_widgets 开始执行 !!!")
        print(f"参数定义数量: {len(self.param_definitions)}")
        print(f"参数定义键: {list(self.param_definitions.keys())}")

        # 检查是否包含 refresh_apps
        if 'refresh_apps' in self.param_definitions:
            print(f"!!! 找到 refresh_apps 参数定义 !!!")
        else:
            print(f"!!! 未找到 refresh_apps 参数定义 !!!")

        # Sort workflow cards by sequence ID for the dropdown
        sorted_workflow_items = sorted(self.workflow_cards_info.items())

        for name, param_def in self.param_definitions.items():
            should_hide = False # <<< Initialize should_hide at the START of the loop iteration

            # <<< ADDED: Debug print for each parameter definition processed >>>
            print(f"  DEBUG [_create_widgets] Processing param: '{name}', Definition: {param_def}")

            # 特别关注 refresh_apps 参数
            if name == 'refresh_apps':
                print(f"!!! 发现 refresh_apps 参数 !!!")
                print(f"  类型: {param_def.get('type')}")
                print(f"  widget_hint: {param_def.get('widget_hint')}")
                print(f"  条件: {param_def.get('condition')}")
                logger.info(f"发现 refresh_apps 参数: {param_def}")
            # <<< END ADDED >>>
            param_type = param_def.get('type', 'text')
            label_text = param_def.get('label', name)
            default = param_def.get('default')
            description = param_def.get('description', '')
            options = param_def.get('options', [])
            # 工具 修复：优先使用current_parameters中的值，只有当值不存在时才使用默认值
            if name in self.current_parameters:
                current_value = self.current_parameters[name]
                print(f"搜索 使用现有参数值 {name}: {current_value}")
            else:
                current_value = default
                print(f"搜索 使用默认参数值 {name}: {current_value}")
            widget_hint = param_def.get('widget_hint')

            # 调试 widget_hint
            if name == 'refresh_apps':
                print(f"!!! refresh_apps widget_hint: '{widget_hint}' !!!")

            # Handle separators in dialog
            if param_type == 'separator':
                # Create a container widget for the separator
                separator_widget = QWidget()
                separator_layout = QVBoxLayout(separator_widget)
                separator_layout.setContentsMargins(0, 0, 0, 0)
                separator_layout.setSpacing(2)

                sep_label = QLabel(label_text)
                sep_label.setAlignment(Qt.AlignCenter)
                sep_label.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 5px;")
                separator_layout.addWidget(sep_label)

                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                separator_layout.addWidget(line)

                # Store the separator widget for visibility control
                self.row_widgets[name] = separator_widget
                self.params_layout.addWidget(separator_widget)
                continue

            # Handle hidden parameters - store their values but don't create widgets
            if param_type == 'hidden':
                # 初始化隐藏参数存储
                if not hasattr(self, '_hidden_params'):
                    self._hidden_params = {}

                # 存储隐藏参数的当前值
                current_value = self.current_parameters.get(name, param_def.get('default'))
                self._hidden_params[name] = current_value
                logger.debug(f"存储隐藏参数 {name}: {current_value}")
                continue

            # 搜索 调试：检查是否到达了这里
            print(f"搜索 到达标准参数处理 {name}: widget_hint='{widget_hint}', param_type='{param_type}'")

            # Standard parameter row (Label + Widget)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0) # No margins for the inner layout
            label = QLabel(f"{label_text}:")
            label.setFixedWidth(120) # Align labels by width
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) # Align text to the left
            row_layout.addWidget(label)

            widget: Optional[QWidget] = None 
            interactive_widget: Optional[QWidget] = None # Store the widget to get value from

            # <<< RESTRUCTURED LOGIC: Prioritize widget_hint >>>
            print(f"搜索 处理参数 {name}: widget_hint='{widget_hint}', param_type='{param_type}'")

            if widget_hint == 'colorpicker':
                color_widget_container = QWidget()
                color_widget_layout = QHBoxLayout(color_widget_container)
                color_widget_layout.setContentsMargins(0,0,0,0)
                color_widget_layout.setSpacing(5)
                line_edit = QLineEdit(str(current_value) if current_value is not None else "0,0,0")
                line_edit.setPlaceholderText("R,G,B")
                line_edit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                browse_button = QPushButton("选择颜色")
                browse_button.clicked.connect(lambda checked=False, le=line_edit: self._browse_color(le))
                color_widget_layout.addWidget(line_edit)
                color_widget_layout.addWidget(browse_button)
                widget = color_widget_container
                interactive_widget = line_edit

            elif widget_hint == 'ocr_region_selector': # Create OCR region selector widget
                print(f"工具 开始创建OCR区域选择器 for {name}")
                try:
                    from ui.ocr_region_selector import OCRRegionSelectorWidget
                    ocr_selector = OCRRegionSelectorWidget()

                    # 设置初始区域（如果有的话）
                    initial_x = self.current_parameters.get('region_x', 0)
                    initial_y = self.current_parameters.get('region_y', 0)
                    initial_width = self.current_parameters.get('region_width', 0)
                    initial_height = self.current_parameters.get('region_height', 0)

                    ocr_selector.set_region(initial_x, initial_y, initial_width, initial_height)

                    # 连接信号
                    ocr_selector.region_selected.connect(self._on_ocr_region_selected)
                    ocr_selector.selection_started.connect(self._on_ocr_selection_started)
                    ocr_selector.selection_finished.connect(self._on_ocr_selection_finished)

                    # 设置目标窗口
                    target_window = self._get_bound_window_title()
                    if target_window:
                        ocr_selector.set_target_window(target_window)
                        print(f"成功 为OCR区域选择器设置目标窗口: {target_window}")
                    else:
                        print(f"警告 未找到绑定的目标窗口")

                    print(f"成功 OCR区域选择器创建成功")
                    widget = ocr_selector
                    interactive_widget = ocr_selector

                except Exception as e:
                    print(f"错误 OCR区域选择器创建失败: {e}")
                    # 创建占位符按钮
                    widget = QPushButton("OCR区域选择器加载失败")
                    widget.setEnabled(False)
                    interactive_widget = widget
            elif widget_hint == 'coordinate_selector':
                # 坐标选择器
                print(f"搜索 创建坐标选择器: {name}")
                try:
                    from ui.coordinate_selector import CoordinateSelectorWidget
                    coord_selector = CoordinateSelectorWidget()

                    # 工具 修复：初始化坐标选择器的当前坐标值
                    existing_x = self.current_parameters.get('coordinate_x', 0)
                    existing_y = self.current_parameters.get('coordinate_y', 0)
                    if existing_x is not None and existing_y is not None:
                        try:
                            coord_x = int(existing_x) if existing_x != '' else 0
                            coord_y = int(existing_y) if existing_y != '' else 0
                            coord_selector.set_coordinate(coord_x, coord_y)
                            print(f"搜索 坐标选择器初始化坐标: ({coord_x}, {coord_y})")
                        except (ValueError, TypeError):
                            coord_selector.set_coordinate(0, 0)
                            print(f"搜索 坐标选择器坐标转换失败，使用默认坐标: (0, 0)")
                    else:
                        coord_selector.set_coordinate(0, 0)
                        print(f"搜索 坐标选择器使用默认坐标: (0, 0)")

                    # 工具 修复：确保信号连接正确，添加调试信息
                    print(f"搜索 连接坐标选择器信号: {name}")
                    # 工具 修复：正确的信号连接，坐标选择器发射(x, y)，我们需要传递selector_name
                    coord_selector.coordinate_selected.connect(lambda x, y, selector_name=name: self._on_coordinate_selected(selector_name, x, y))
                    coord_selector.selection_started.connect(self._on_coordinate_selection_started)
                    coord_selector.selection_finished.connect(self._on_coordinate_selection_finished)
                    print(f"搜索 坐标选择器信号连接完成")
                    widget = coord_selector
                    interactive_widget = coord_selector
                except Exception as e:
                    print(f"错误 创建坐标选择器失败: {e}")
                    # 创建一个简单的按钮作为备选
                    widget = QPushButton("坐标选择器 (创建失败)")
                    interactive_widget = widget

            elif widget_hint == 'motion_region_selector':
                # 移动检测区域选择器
                print(f"搜索 创建移动检测区域选择器: {name}")
                try:
                    from ui.ocr_region_selector import OCRRegionSelectorWidget
                    motion_region_selector = OCRRegionSelectorWidget()

                    # 设置初始区域（如果有的话）
                    initial_x = self.current_parameters.get('minimap_x', 1150)
                    initial_y = self.current_parameters.get('minimap_y', 40)
                    initial_width = self.current_parameters.get('minimap_width', 50)
                    initial_height = self.current_parameters.get('minimap_height', 50)

                    motion_region_selector.set_region(initial_x, initial_y, initial_width, initial_height)

                    # 连接信号
                    motion_region_selector.region_selected.connect(
                        lambda x, y, w, h, selector_name=name: self._on_motion_region_selected(selector_name, x, y, w, h)
                    )

                    widget = motion_region_selector
                    interactive_widget = motion_region_selector
                except Exception as e:
                    print(f"错误 创建移动检测区域选择器失败: {e}")
                    # 创建一个简单的按钮作为备选
                    widget = QPushButton("移动检测区域选择器 (创建失败)")
                    interactive_widget = widget

            elif widget_hint == 'refresh_apps': # 刷新应用列表按钮
                print(f"!!! 检测到 refresh_apps widget_hint，开始创建刷新按钮 !!!")
                print(f"参数名: {name}")
                print(f"参数定义: {param_def}")
                print(f"按钮文本: {param_def.get('button_text', '刷新')}")

                try:
                    button = QPushButton(param_def.get('button_text', '刷新'))
                    print(f"按钮对象创建成功: {button}")

                    def on_refresh_clicked():
                        print(f"!!! 刷新应用列表按钮被点击了 !!! 参数名: {name}")
                        print(f"!!! 按钮对象: {button} !!!")
                        logger.info(f"刷新应用列表按钮被点击: {name}")
                        self._refresh_ldplayer_apps()

                    print(f"准备连接按钮点击事件...")
                    button.clicked.connect(on_refresh_clicked)
                    print(f"按钮点击事件连接成功!")

                    widget = button
                    interactive_widget = button
                    logger.info(f"成功创建刷新应用列表按钮: {name}")
                    print(f"=== 刷新应用列表按钮创建成功: {name} ===")
                    print(f"=== 按钮是否启用: {button.isEnabled()} ===")
                    print(f"=== 按钮是否可见: {button.isVisible()} ===")

                    # 添加测试按钮功能
                    def test_button():
                        print("!!! 测试按钮功能 - 直接调用刷新方法 !!!")
                        self._refresh_ldplayer_apps()

                    # 可以通过右键菜单或其他方式触发测试
                    button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    button.customContextMenuRequested.connect(lambda: test_button())
                    print(f"右键菜单功能已设置")

                except Exception as e:
                    logger.error(f"创建刷新应用列表按钮失败: {e}")
                    print(f"错误 刷新应用列表按钮创建失败: {e}")
                    # 创建占位符按钮
                    widget = QPushButton("刷新按钮加载失败")
                    widget.setEnabled(False)
                    interactive_widget = widget

            elif widget_hint == 'card_selector': # Create ComboBox for jump targets
                combo_box = QComboBox()
                combo_box.addItem("无", None) # Default option

                # 禁用滚轮事件，防止意外修改参数值
                combo_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                combo_box.wheelEvent = lambda event: None

                # <<< ADDED: Change text for Start Node >>>
                if self.task_type == '起点': # Check if editing the Start Node
                    print(f"  DEBUG: Modifying default text for Start Node ('{name}') combo box.")
                    combo_box.setItemText(0, "默认连接") # Change display text for the None item
                # <<< END ADDED >>>

                # Populate with card info
                sorted_card_ids = sorted(self.workflow_cards_info.keys())
                for card_id in sorted_card_ids:
                    if self.editing_card_id is not None and card_id == self.editing_card_id:
                        continue # Skip self
                    card_info = self.workflow_cards_info.get(card_id)
                    if card_info:
                        raw_task_type_info, seq_id = card_info
                        task_type_str = str(raw_task_type_info) # Simplified extraction for now
                        item_text = f"{task_type_str} (ID: {card_id})"
                        index = combo_box.count()
                        combo_box.addItem("", card_id) # Add with data
                        combo_box.setItemText(index, item_text) # Set display text
                # Set current value
                target_card_id = None
                if current_value is not None and str(current_value).strip() and str(current_value).lower() != 'none':
                    try: target_card_id = int(current_value)
                    except (ValueError, TypeError): target_card_id = None
                print(f"  DEBUG[_create_widgets] Card Selector '{name}': current target card_id = {target_card_id}")
                if target_card_id is not None:
                    index_to_select = combo_box.findData(target_card_id)
                    if index_to_select != -1: combo_box.setCurrentIndex(index_to_select)
                    else: combo_box.setCurrentIndex(0) # Default to "无"
                else: combo_box.setCurrentIndex(0)
                widget = combo_box
                interactive_widget = combo_box
                # Store the widget itself for enable/disable based on action
                self.jump_target_widgets[name] = widget

            # <<< Only check param_type if NO specific hint was matched >>>
            elif param_type == 'file' or name.endswith('_path'): # Handle file input
                file_widget_container = QWidget()
                file_layout = QHBoxLayout(file_widget_container)
                file_layout.setContentsMargins(0,0,0,0); file_layout.setSpacing(5)
                line_edit = QLineEdit(str(current_value) if current_value is not None else "")
                browse_button = QPushButton("浏览...")
                browse_button.clicked.connect(lambda checked=False, le=line_edit: self._browse_file(le))
                file_layout.addWidget(line_edit); file_layout.addWidget(browse_button)
                widget = file_widget_container
                interactive_widget = line_edit

            elif param_type == 'text':
                line_edit = QLineEdit(str(current_value) if current_value is not None else "")

                # 检查是否为只读
                if param_def.get('readonly', False):
                    line_edit.setReadOnly(True)
                    line_edit.setStyleSheet("""
                        QLineEdit {
                            background-color: #f0f0f0;
                            color: #666666;
                            border: 1px solid #cccccc;
                        }
                    """)

                # 特殊处理：坐标显示控件设为只读
                if name == 'region_coordinates':
                    line_edit.setReadOnly(True)
                    # 检查是否有坐标数据来初始化显示
                    region_x = self.current_parameters.get('region_x', 0)
                    region_y = self.current_parameters.get('region_y', 0)
                    region_width = self.current_parameters.get('region_width', 0)
                    region_height = self.current_parameters.get('region_height', 0)

                    # 如果坐标都是0，显示未指定状态
                    if region_x == 0 and region_y == 0 and region_width == 0 and region_height == 0:
                        line_edit.setText("未指定识别区域")
                    else:
                        # 显示坐标信息
                        coord_text = f"X={region_x}, Y={region_y}, 宽度={region_width}, 高度={region_height}"
                        line_edit.setText(coord_text)

                widget = line_edit
                interactive_widget = line_edit

            elif param_type == 'int':
                min_val = param_def.get('min', -2147483648)
                max_val = param_def.get('max', 2147483647)
                step = 1
                num_widget_container = QWidget()
                num_layout = QHBoxLayout(num_widget_container)
                num_layout.setContentsMargins(0,0,0,0); num_layout.setSpacing(2)
                line_edit = QLineEdit(str(current_value) if current_value is not None else "0")
                dec_button = QPushButton("-"); inc_button = QPushButton("+")
                dec_button.setObjectName("spinButton"); inc_button.setObjectName("spinButton")
                num_layout.addWidget(line_edit); num_layout.addWidget(dec_button); num_layout.addWidget(inc_button)
                dec_button.clicked.connect(lambda checked=False, le=line_edit, s=step, mn=min_val, mx=max_val: self._decrement_value(le, s, mn, mx))
                inc_button.clicked.connect(lambda checked=False, le=line_edit, s=step, mn=min_val, mx=max_val: self._increment_value(le, s, mn, mx))
                widget = num_widget_container
                interactive_widget = line_edit

            elif param_type == 'float':
                min_val = param_def.get('min', -sys.float_info.max)
                max_val = param_def.get('max', sys.float_info.max)
                decimals = param_def.get('decimals', 2)
                step = 10 ** (-decimals) # Calculate step based on decimals

                num_widget_container = QWidget()
                num_layout = QHBoxLayout(num_widget_container)
                num_layout.setContentsMargins(0,0,0,0); num_layout.setSpacing(2)

                # Use QLineEdit for consistent +/- buttons
                formatted_value = f"{float(current_value):.{decimals}f}" if current_value is not None else f"{0.0:.{decimals}f}"
                line_edit = QLineEdit(formatted_value)
                # Optional: Add QDoubleValidator
                # line_edit.setValidator(QDoubleValidator(min_val, max_val, decimals))

                dec_button = QPushButton("-"); inc_button = QPushButton("+")
                dec_button.setObjectName("spinButton"); inc_button.setObjectName("spinButton")
                num_layout.addWidget(line_edit); num_layout.addWidget(dec_button); num_layout.addWidget(inc_button)

                # Connect buttons (pass decimals)
                dec_button.clicked.connect(lambda checked=False, le=line_edit, s=step, mn=min_val, mx=max_val, dec=decimals:
                                           self._decrement_value(le, s, mn, mx, dec))
                inc_button.clicked.connect(lambda checked=False, le=line_edit, s=step, mn=min_val, mx=max_val, dec=decimals:
                                           self._increment_value(le, s, mn, mx, dec))

                widget = num_widget_container
                interactive_widget = line_edit

            elif param_type == 'bool':
                check_box = QCheckBox()
                check_box.setChecked(bool(current_value) if current_value is not None else False)
                widget = check_box
                interactive_widget = check_box

            elif param_type == 'select' or param_type == 'combo': # Handle both 'select' and 'combo'
                combo_box = QComboBox()

                # 禁用滚轮事件，防止意外修改参数值
                combo_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                combo_box.wheelEvent = lambda event: None

                # 特殊处理应用选择器
                if widget_hint == 'app_selector':
                    # 应用选择器，存储引用以便后续更新
                    self.app_selector_combo = combo_box
                    logger.info(f"创建应用选择器下拉框: {name}")

                if isinstance(options, list):
                    combo_box.addItems(options)
                # 工具 修复：正确处理当前值和默认值
                param_default = param_def.get('default')
                current_text = str(current_value) if current_value is not None else str(param_default) if param_default is not None else ""
                print(f"搜索 select控件 {name}: current_value={current_value}, param_default={param_default}, current_text='{current_text}'")
                print(f"搜索 select控件 {name}: 可选项={options}")
                index = combo_box.findText(current_text)
                if index != -1:
                    combo_box.setCurrentIndex(index)
                    print(f"搜索 select控件 {name}: 设置为索引 {index} ('{current_text}')")
                elif options: # Default to first option if current not found
                    combo_box.setCurrentIndex(0)
                    print(f"搜索 select控件 {name}: 未找到'{current_text}'，使用第一个选项: '{options[0] if options else 'None'}'")
                else:
                    print(f"搜索 select控件 {name}: 没有可选项，无法设置默认值")
                widget = combo_box
                interactive_widget = combo_box
                
            elif param_type == 'radio': # Example: Radio button group
                 # Container for the radio buttons themselves
                 radio_button_container = QWidget()
                 # Use QHBoxLayout for side-by-side radio buttons
                 radio_layout_for_buttons = QHBoxLayout(radio_button_container)
                 radio_layout_for_buttons.setContentsMargins(0,0,0,0) # No extra margins

                 button_group = QButtonGroup(radio_button_container) # Parent is the container
                 button_group.setExclusive(True) # Only one can be selected

                 actual_options = param_def.get('options', {}) # e.g. {"fixed": "固定延迟", "random": "随机延迟"}
                 
                 if isinstance(actual_options, dict):
                     for i, (value_key, display_text) in enumerate(actual_options.items()):
                         radio_button = QRadioButton(display_text) # Use Chinese display text
                         radio_button.setProperty("value_key", value_key) # Store the actual value ("fixed", "random")
                         radio_layout_for_buttons.addWidget(radio_button) # Add to QHBoxLayout
                         button_group.addButton(radio_button) # Add to group
                         if str(current_value) == str(value_key): # Compare with the key
                              radio_button.setChecked(True)
                 # Fallback for list-based options if ever needed, though dict is preferred for key-value.
                 elif isinstance(actual_options, list):
                    for i, option_text_or_tuple in enumerate(actual_options):
                        display_text_val = str(option_text_or_tuple)
                        value_key_val = str(option_text_or_tuple)
                        if isinstance(option_text_or_tuple, (tuple, list)) and len(option_text_or_tuple) == 2:
                            value_key_val, display_text_val = str(option_text_or_tuple[0]), str(option_text_or_tuple[1])

                        radio_button = QRadioButton(display_text_val)
                        radio_button.setProperty("value_key", value_key_val)
                        radio_layout_for_buttons.addWidget(radio_button)
                        button_group.addButton(radio_button)
                        if str(current_value) == value_key_val:
                            radio_button.setChecked(True)


                 widget = radio_button_container # This is the QWidget holding the QHBoxLayout of radio buttons
                 interactive_widget = button_group # Store the group to get the checked button

            elif param_type == 'textarea': # Example: Multiline text
                 text_edit = QPlainTextEdit()
                 text_edit.setPlainText(str(current_value) if current_value is not None else "")
                 # 工具 修复：改进文本输入区域的大小设置
                 text_edit.setMinimumHeight(80)  # 增加最小高度，提供更好的输入体验
                 text_edit.setMaximumHeight(200) # 设置最大高度，防止过度扩展
                 # 根据内容自动调整高度
                 text_edit.document().documentLayout().documentSizeChanged.connect(
                     lambda size: self._adjust_text_edit_height(text_edit, size)
                 )
                 widget = text_edit
                 interactive_widget = text_edit

            elif param_type == 'button': # Handle button type
                button_text = param_def.get('button_text', label_text)
                button = QPushButton(button_text)

                # 对于按钮类型，如果没有特殊的widget_hint处理，就创建一个普通按钮
                logger.warning(f"创建了普通按钮 for {name}，widget_hint: {widget_hint}")
                print(f"=== 创建普通按钮: {name}, widget_hint: {widget_hint} ===")

                widget = button
                interactive_widget = button

            else: # Default to text if type is unknown
                line_edit = QLineEdit(str(current_value) if current_value is not None else "")
                widget = line_edit
                interactive_widget = line_edit

            # --- Add the created widget to the row layout ---
            if widget:
                row_layout.addWidget(widget)
            else:
                 # Placeholder if widget creation failed
                 row_layout.addWidget(QLabel("[Widget Error]"))

            # Store interactive widget for value retrieval
            if interactive_widget:
                # Set object name for easier debugging/styling if needed
                interactive_widget.setObjectName(f"param_{name}")
                self.widgets[name] = interactive_widget
            else:
                # Log if no interactive widget was assigned (should not happen ideally)
                print(f"  WARNING: No interactive widget assigned for parameter '{name}'. Value retrieval might fail.")

            # Store the container widget (row_widget) for visibility control
            self.row_widgets[name] = row_widget

            # --- Add the completed row to the main parameters layout ---
            self.params_layout.addWidget(row_widget)

        # After creating all widgets, setup connections for conditional visibility etc.
        self._setup_conditional_visibility()
        self._setup_jump_target_connections()
        self._setup_condition_connections() # Ensure this is called AFTER widgets are created

    def _setup_jump_target_connections(self): # <--- ADDED this separate function for clarity
        """Setup connections for jump target dropdowns to enable/disable spin boxes."""
        on_success_combo = self.widgets.get("on_success")
        on_failure_combo = self.widgets.get("on_failure")
        success_target_widget = self.jump_target_widgets.get("success_jump_target_id")
        failure_target_widget = self.jump_target_widgets.get("failure_jump_target_id")

        if isinstance(on_success_combo, QComboBox) and success_target_widget:
            on_success_combo.currentTextChanged.connect(
                lambda text, w=success_target_widget: self._update_jump_target_state(text, w)
            )
            # Initial state
            self._update_jump_target_state(on_success_combo.currentText(), success_target_widget)
            
        if isinstance(on_failure_combo, QComboBox) and failure_target_widget:
            on_failure_combo.currentTextChanged.connect(
                lambda text, w=failure_target_widget: self._update_jump_target_state(text, w)
            )
            # Initial state
            self._update_jump_target_state(on_failure_combo.currentText(), failure_target_widget)

    def _setup_condition_connections(self): # <--- ADDED this separate function for clarity
        """Setup connections for widgets that control conditional visibility of others."""
        for controller_name, controller_widget in self.widgets.items():
            # Check if any other widget depends on this one
            # 🔧 修复：处理列表类型的condition
            has_dependents = any(
                (isinstance(pdef.get('condition'), dict) and
                 pdef.get('condition', {}).get('param') == controller_name)
                for pdef in self.param_definitions.values()
            )
            
            # --- MODIFICATION START ---
            # Connect signals regardless of dependency for robustness, 
            # especially for checkboxes which might control visibility implicitly.
            # The handler function itself checks conditions.
            if isinstance(controller_widget, QComboBox):
                # Connect only if it controls others to avoid redundant calls if not needed?
                # Let's keep the original logic for ComboBox for now.
                if has_dependents:
                    controller_widget.currentTextChanged.connect(self._handle_conditional_visibility_check)
            elif isinstance(controller_widget, QCheckBox):
                # Always connect CheckBox toggled signal
                controller_widget.toggled.connect(self._handle_conditional_visibility_check)
            elif isinstance(controller_widget, QLineEdit):
                # Connect textChanged only if it controls others
                 if has_dependents:
                    # --- ADD Debugging for LineEdit connection ---
                    print(f"DEBUG: Connecting textChanged for LineEdit '{controller_name}'")
                    # -------------------------------------------
                    controller_widget.textChanged.connect(self._handle_conditional_visibility_check)
            elif isinstance(controller_widget, QButtonGroup): # ADDED: Handle QButtonGroup for radio buttons
                if has_dependents:
                    controller_widget.buttonClicked.connect(self._handle_conditional_visibility_check)
            # --- MODIFICATION END ---
                
            # Original Logic (commented out for comparison)
            # if has_dependents:
            #     if isinstance(controller_widget, QComboBox):
            #         controller_widget.currentTextChanged.connect(self._handle_conditional_visibility_check)
            #     elif isinstance(controller_widget, QCheckBox):
            #         controller_widget.toggled.connect(self._handle_conditional_visibility_check)
            #     elif isinstance(controller_widget, QLineEdit): # Less common, but possible
            #         controller_widget.textChanged.connect(self._handle_conditional_visibility_check)
            #     # Add other widget types (like Radio Buttons in group) if needed
            #     # Note: Radio buttons were connected individually during creation

        # Initial visibility check after all widgets and connections are set up
        self._handle_conditional_visibility_check()

        # 坐标捕获工具已删除

    def _on_ocr_region_selected(self, x: int, y: int, width: int, height: int):
        """处理OCR区域选择器的区域选择信号"""
        logger.info(f"靶心 ParameterDialog._on_ocr_region_selected 被调用: ({x}, {y}, {width}, {height})")
        print(f"靶心 ParameterDialog._on_ocr_region_selected 被调用: ({x}, {y}, {width}, {height})")

        # 更新相关的坐标参数
        coordinate_params = {
            'region_x': x,
            'region_y': y,
            'region_width': width,
            'region_height': height
        }

        # 初始化隐藏参数存储（如果不存在）
        if not hasattr(self, '_hidden_params'):
            self._hidden_params = {}

        # 更新对应的控件值和隐藏参数
        updated_count = 0
        for param_name, param_value in coordinate_params.items():
            # 首先检查是否是隐藏参数
            param_def = self.param_definitions.get(param_name, {})
            if param_def.get('type') == 'hidden':
                # 更新隐藏参数
                self._hidden_params[param_name] = param_value
                updated_count += 1
                logger.info(f"已更新隐藏参数 {param_name} 的值为: {param_value}")
                print(f"成功 已更新隐藏参数 {param_name} 的值为: {param_value}")
            else:
                # 尝试更新可见控件
                widget = self.widgets.get(param_name)
                if widget:
                    if hasattr(widget, 'setValue'):
                        widget.setValue(param_value)
                        updated_count += 1
                    elif hasattr(widget, 'setText'):
                        widget.setText(str(param_value))
                        updated_count += 1
                    logger.info(f"已更新控件 {param_name} 的值为: {param_value}")
                    print(f"成功 已更新控件 {param_name} 的值为: {param_value}")
                else:
                    logger.warning(f"未找到控件: {param_name}")
                    print(f"错误 未找到控件: {param_name}")

            # 同时更新current_parameters，确保数据一致性
            self.current_parameters[param_name] = param_value

        # 更新坐标显示文本控件
        coord_display = self.widgets.get('region_coordinates')
        if coord_display:
            coord_text = f"X={x}, Y={y}, 宽度={width}, 高度={height}"
            coord_display.setText(coord_text)
            logger.info(f"已更新坐标显示文本: {coord_text}")
            print(f"成功 已更新坐标显示文本: {coord_text}")
        else:
            logger.warning("未找到坐标显示控件")
            print("错误 未找到坐标显示控件")

        logger.info(f"OCR区域选择完成，共更新了 {updated_count} 个参数")
        print(f"完成 OCR区域选择完成，共更新了 {updated_count} 个参数")
        print(f"搜索 当前隐藏参数: {getattr(self, '_hidden_params', {})}")

        # 注意：不在这里恢复对话框显示，由 selection_finished 信号统一处理

    def _on_coordinate_selected(self, selector_name: str, x: int, y: int):
        """处理坐标选择完成事件 - 完全重写的简洁版本"""
        print(f"靶心靶心靶心 ParameterDialog._on_coordinate_selected 被调用！！！")
        print(f"靶心靶心靶心 参数: selector_name={selector_name}, x={x}, y={y}")
        print(f"靶心 坐标选择完成: ({x}, {y})")

        # 检查是否是滚动坐标选择器
        if selector_name == 'scroll_coordinate_selector':
            # 更新滚动起始位置显示参数
            position_widget = self.widgets.get('scroll_start_position')
            if position_widget and hasattr(position_widget, 'setText'):
                position_widget.setText(f"{x},{y}")
                print(f"成功 滚动起始位置已设置: {x},{y}")

            # 更新current_parameters
            self.current_parameters['scroll_start_position'] = f"{x},{y}"
            print(f"完成 滚动坐标选择处理完成: ({x}, {y})")
            return

        # 检查是否是拖拽坐标选择器
        if selector_name == 'drag_coordinate_selector':
            # 更新拖拽起始位置显示参数
            position_widget = self.widgets.get('drag_start_position')
            if position_widget and hasattr(position_widget, 'setText'):
                position_widget.setText(f"{x},{y}")
                print(f"成功 拖拽起始位置已设置: {x},{y}")

            # 更新current_parameters
            self.current_parameters['drag_start_position'] = f"{x},{y}"
            print(f"完成 拖拽坐标选择处理完成: ({x}, {y})")
            return

        # 检查是否是合并的坐标参数（如滚动起始位置）
        if selector_name in ['scroll_start_position']:
            # 处理合并的坐标参数
            coordinate_widget = self.widgets.get(selector_name)
            if coordinate_widget and hasattr(coordinate_widget, 'setText'):
                coordinate_widget.setText(f"{x},{y}")
                print(f"成功 {selector_name}坐标已设置: {x},{y}")

            # 更新current_parameters
            self.current_parameters[selector_name] = f"{x},{y}"
            print(f"完成 合并坐标选择处理完成: {selector_name} = ({x}, {y})")
            return

        # 1. 直接更新坐标输入框（原有逻辑）
        x_widget = self.widgets.get('coordinate_x')
        y_widget = self.widgets.get('coordinate_y')

        if x_widget and hasattr(x_widget, 'setText'):
            x_widget.setText(str(x))
            print(f"成功 X坐标已设置: {x}")

        if y_widget and hasattr(y_widget, 'setText'):
            y_widget.setText(str(y))
            print(f"成功 Y坐标已设置: {y}")

        # 2. 强制设置操作模式为坐标点击
        operation_mode_widget = self.widgets.get('operation_mode')
        if operation_mode_widget and isinstance(operation_mode_widget, QComboBox):
            # 阻止信号避免递归
            operation_mode_widget.blockSignals(True)
            for i in range(operation_mode_widget.count()):
                if operation_mode_widget.itemText(i) == '坐标点击':
                    operation_mode_widget.setCurrentIndex(i)
                    print(f"成功 操作模式已设置为: 坐标点击")
                    break
            operation_mode_widget.blockSignals(False)

        # 3. 直接更新current_parameters
        self.current_parameters['coordinate_x'] = x
        self.current_parameters['coordinate_y'] = y
        self.current_parameters['operation_mode'] = '坐标点击'

        # 4. 设置标记表示使用了坐标工具
        self._coordinate_tool_used = True

        print(f"完成 坐标选择处理完成: ({x}, {y}), 操作模式: 坐标点击")

    def _on_motion_region_selected(self, selector_name: str, x: int, y: int, width: int, height: int):
        """处理移动检测区域选择完成事件"""
        print(f"移动检测区域选择完成: X={x}, Y={y}, 宽度={width}, 高度={height}")

        # 更新隐藏的坐标参数
        self.current_parameters['minimap_x'] = x
        self.current_parameters['minimap_y'] = y
        self.current_parameters['minimap_width'] = width
        self.current_parameters['minimap_height'] = height

        # 更新移动识别区域显示参数
        region_text = f"X={x}, Y={y}, 宽度={width}, 高度={height}"
        region_widget = self.widgets.get('motion_detection_region')
        if region_widget and hasattr(region_widget, 'setText'):
            region_widget.setText(region_text)
            print(f"成功 移动识别区域已设置: {region_text}")

        # 更新current_parameters
        self.current_parameters['motion_detection_region'] = region_text

        print(f"完成 移动检测区域选择处理完成: X={x}, Y={y}, 宽度={width}, 高度={height}")

    def _on_coordinate_selection_started(self):
        """坐标选择开始时的处理"""
        logger.info("靶心 坐标选择开始，最小化参数对话框")
        print("靶心 坐标选择开始，最小化参数对话框")

        # 停止之前的恢复定时器（如果存在）
        if hasattr(self, '_restore_timer') and self._restore_timer.isActive():
            self._restore_timer.stop()
            logger.info("刷新 停止之前的恢复定时器")

        # 工具 修复：不使用hide()，而是最小化对话框，避免触发关闭事件
        self.showMinimized()

        # 设置一个较短的定时器作为备用恢复机制
        from PySide6.QtCore import QTimer
        self._restore_timer = QTimer()
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_dialog_visibility)
        # 5秒后自动恢复显示（缩短时间，主要依靠选择完成信号）
        self._restore_timer.start(5000)

    def _on_coordinate_selection_finished(self):
        """坐标选择结束时的处理"""
        logger.info("靶心 坐标选择结束，立即恢复参数对话框显示")
        print("靶心 坐标选择结束，立即恢复参数对话框显示")

        # 停止备用恢复定时器
        if hasattr(self, '_restore_timer') and self._restore_timer.isActive():
            self._restore_timer.stop()
            logger.info("刷新 停止备用恢复定时器")

        # 立即恢复对话框显示
        self._restore_dialog_visibility()

    def _on_ocr_selection_started(self):
        """OCR区域选择开始时的处理"""
        logger.info("靶心 OCR区域选择开始，临时隐藏参数对话框")
        print("靶心 OCR区域选择开始，临时隐藏参数对话框")

        # 停止之前的恢复定时器（如果存在）
        if hasattr(self, '_restore_timer') and self._restore_timer.isActive():
            self._restore_timer.stop()
            logger.info("刷新 停止之前的恢复定时器")

        # 临时隐藏对话框，让目标窗口完全可见
        self.hide()

        # 设置一个较短的定时器作为备用恢复机制
        from PySide6.QtCore import QTimer
        self._restore_timer = QTimer()
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_dialog_visibility)
        # 5秒后自动恢复显示（缩短时间，主要依靠选择完成信号）
        self._restore_timer.start(5000)

    def _on_ocr_selection_finished(self):
        """OCR区域选择结束时的处理（无论成功还是取消）"""
        logger.info("靶心 OCR区域选择结束，立即恢复参数对话框显示")
        print("靶心 OCR区域选择结束，立即恢复参数对话框显示")

        # 停止备用恢复定时器
        if hasattr(self, '_restore_timer') and self._restore_timer.isActive():
            self._restore_timer.stop()
            logger.info("刷新 停止备用恢复定时器")

        # 立即恢复对话框显示
        self._restore_dialog_visibility()

    def _restore_dialog_visibility(self):
        """恢复对话框显示"""
        logger.info("靶心 恢复参数对话框显示")
        print("靶心 恢复参数对话框显示")
        # 工具 修复：从最小化状态恢复到正常状态
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _get_bound_window_title(self) -> Optional[str]:
        """获取当前绑定的窗口标题"""
        try:
            print(f"搜索 开始获取绑定的窗口标题...")

            # 向上查找主窗口，直到找到有config或runner属性的窗口
            current_widget = self.parent()
            level = 0

            while current_widget and level < 10:  # 最多向上查找10层
                print(f"搜索 第{level}层窗口: {current_widget}")
                print(f"搜索 第{level}层窗口类型: {type(current_widget)}")

                # 检查是否是主窗口（任务编辑器）
                if hasattr(current_widget, 'config'):
                    print(f"搜索 第{level}层窗口有config属性")
                    config = current_widget.config
                    target_window_title = config.get('target_window_title')
                    if target_window_title:
                        print(f"搜索 从第{level}层窗口配置获取目标窗口: {target_window_title}")
                        return target_window_title
                    else:
                        print(f"搜索 第{level}层窗口config中没有target_window_title")

                # 检查是否有runner属性
                if hasattr(current_widget, 'runner'):
                    print(f"搜索 第{level}层窗口有runner属性")
                    runner = current_widget.runner
                    if hasattr(runner, 'target_window_title'):
                        target_window_title = runner.target_window_title
                        print(f"搜索 从第{level}层窗口runner获取目标窗口: {target_window_title}")
                        if target_window_title:
                            return target_window_title
                    else:
                        print(f"搜索 第{level}层窗口runner没有target_window_title属性")

                # 检查是否有直接的target_window_title属性
                if hasattr(current_widget, 'target_window_title'):
                    target_window_title = current_widget.target_window_title
                    print(f"搜索 从第{level}层窗口属性获取目标窗口: {target_window_title}")
                    if target_window_title:
                        return target_window_title

                # 向上查找父窗口
                current_widget = current_widget.parent()
                level += 1

            print(f"搜索 查找了{level}层窗口，未找到绑定的目标窗口")
            return None

        except Exception as e:
            print(f"搜索 获取绑定窗口标题时出错: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _update_threshold_visibility(self, selected_method: str):
        """Updates visibility of the threshold value row."""
        show_threshold = (selected_method == "二值化")
        threshold_widget = self.row_widgets.get("threshold_value")
        if threshold_widget:
            print(f"设置 threshold_value 可见性: {show_threshold}")
            threshold_widget.setVisible(show_threshold)
            # Optional: Adjust dialog size if visibility changes significantly
            # self.adjustSize()
            
    def _setup_conditional_visibility(self):
        """Sets up the initial state and connects signals for conditionally visible/enabled widgets."""
        # Initial visibility for pre-conditions
        self._update_pre_condition_visibility(self.current_parameters.get("pre_condition_type", "无"))
        # Initial visibility for threshold value
        self._update_threshold_visibility(self.current_parameters.get("preprocessing_method", "无"))
        
        # Initial check for all conditional visibilities
        self._handle_conditional_visibility_check()
        
        self.adjustSize() # Adjust dialog size after initial setup

    def _browse_color(self, line_edit_widget: QLineEdit):
        """打开汉化的Qt颜色选择对话框"""
        current_color_str = line_edit_widget.text()
        initial_color = QColor(255, 0, 0) # Default red color
        try:
            parts = [int(c.strip()) for c in current_color_str.split(',')]
            if len(parts) == 3 and all(0 <= c <= 255 for c in parts):
                initial_color = QColor(parts[0], parts[1], parts[2])
        except ValueError:
            pass # Keep default color if current string is invalid

        dialog = QColorDialog(self)
        dialog.setWindowTitle("选择目标颜色")
        dialog.setCurrentColor(initial_color)

        # 强制使用非原生对话框以确保可以修改按钮文本
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)

        # 手动汉化按钮文本
        def translate_color_dialog_buttons():
            # 查找并翻译按钮
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

        # 使用定时器延迟执行翻译，确保对话框完全加载
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, translate_color_dialog_buttons)

        if dialog.exec() == QDialog.Accepted:
            color = dialog.selectedColor()
            if color.isValid():
                rgb_str = f"{color.red()},{color.green()},{color.blue()}"
                line_edit_widget.setText(rgb_str)

    def _browse_file(self, line_edit_widget: QLineEdit):
        """Opens a file dialog to select a file."""
        # Consider filtering based on expected file types if available in param_def
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if file_path:
            line_edit_widget.setText(file_path)

            # 特殊处理：如果是任务模块文件选择，显示模块信息
            if hasattr(self, 'task_type') and self.task_type == "任务模块":
                self._show_module_info(file_path)

    def _show_module_info(self, file_path: str):
        """显示模块文件信息"""
        try:
            import os
            import json

            # 确定要读取的文件
            if file_path.endswith('.emodule'):
                # 加密模块，尝试读取缓存文件
                cache_file = file_path.replace('.emodule', '.cache.json')
                if os.path.exists(cache_file):
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        module_data = json.load(f)
                    info_source = "缓存"
                else:
                    # 没有缓存，尝试使用加密模块处理器
                    try:
                        import importlib
                        crypto_module = importlib.import_module('utils.module_crypto')
                        ModuleCrypto = getattr(crypto_module, 'ModuleCrypto')
                        crypto = ModuleCrypto()
                        basic_info = crypto.get_module_info_from_encrypted(file_path)
                        if basic_info:
                            self._show_basic_module_info(basic_info)
                        return
                    except (ImportError, ModuleNotFoundError, AttributeError):
                        # 加密模块处理器不可用，显示提示信息
                        self._show_encrypted_module_fallback_info(file_path)
                        return
            else:
                # 明文模块
                with open(file_path, 'r', encoding='utf-8') as f:
                    module_data = json.load(f)
                info_source = "文件"

            # 提取模块信息
            module_info = module_data.get('module_info', {})
            workflow_info = module_data.get('workflow', {})

            # 更新显示
            info_text = f"模块名称: {module_info.get('name', '未知')}\n"
            info_text += f"版本: {module_info.get('version', '未知')}\n"
            info_text += f"作者: {module_info.get('author', '未知')}\n"
            info_text += f"描述: {module_info.get('description', '无')}\n"
            info_text += f"卡片数量: {len(workflow_info.get('cards', []))}\n"
            info_text += f"数据来源: {info_source}"

            # 显示在状态栏或工具提示中
            if hasattr(self, 'setToolTip'):
                self.setToolTip(info_text)

        except Exception as e:
            logger.error(f"显示模块信息失败: {e}", exc_info=True)

    def _show_basic_module_info(self, basic_info: dict):
        """显示加密模块的基本信息"""
        info_text = f"模块名称: {basic_info.get('name', '未知')}\n"
        info_text += f"文件大小: {basic_info.get('file_size', 0)} 字节\n"
        info_text += f"状态: 加密模块（需要先导入解密）"

        if hasattr(self, 'setToolTip'):
            self.setToolTip(info_text)

    def _show_encrypted_module_fallback_info(self, file_path: str):
        """显示加密模块的回退信息（当解密器不可用时）"""
        import os
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        file_name = os.path.basename(file_path)

        info_text = f"文件名: {file_name}\n"
        info_text += f"文件大小: {file_size} 字节\n"
        info_text += f"类型: 加密模块文件\n"
        info_text += f"状态: 解密器不可用，无法读取详细信息"

        if hasattr(self, 'setToolTip'):
            self.setToolTip(info_text)

    def _update_module_info_display(self, module_info: Dict[str, Any]):
        """更新模块信息显示"""
        try:
            # 更新模块信息标签
            info_fields = {
                'module_name': module_info.get('name', '未知模块'),
                'module_version': module_info.get('version', '未知'),
                'module_description': module_info.get('description', '无描述')
            }

            for field_name, value in info_fields.items():
                if field_name in self.row_widgets:
                    row_widget = self.row_widgets[field_name]
                    # 查找标签控件并更新文本
                    for child in row_widget.findChildren(QLabel):
                        if hasattr(child, 'setText'):
                            child.setText(str(value))
                            break

        except Exception as e:
            logger.error(f"更新模块信息显示失败: {e}")

    def _add_dynamic_module_params(self, module_params: Dict[str, Dict[str, Any]]):
        """动态添加模块参数"""
        try:
            if not module_params:
                return

            # 清除之前的动态参数
            self._clear_dynamic_module_params()

            # 添加分隔符
            separator_row = self._create_separator_row("模块参数")
            self.form_layout.addRow(separator_row)
            self.dynamic_param_widgets.append(separator_row)

            # 添加每个模块参数
            for param_name, param_def in module_params.items():
                self._add_module_parameter_row(param_name, param_def)

            # 调整对话框大小
            self.adjustSize()

        except Exception as e:
            logger.error(f"添加动态模块参数失败: {e}")

    def _clear_dynamic_module_params(self):
        """清除动态模块参数"""
        if not hasattr(self, 'dynamic_param_widgets'):
            self.dynamic_param_widgets = []
            return

        # 移除所有动态参数控件
        for widget in self.dynamic_param_widgets:
            if widget:
                self.form_layout.removeRow(widget)
                widget.deleteLater()

        self.dynamic_param_widgets.clear()

    def _add_module_parameter_row(self, param_name: str, param_def: Dict[str, Any]):
        """添加单个模块参数行"""
        try:
            # 获取当前参数值
            current_value = self.parameters.get(param_name, param_def.get('default'))

            # 创建参数控件
            param_type = param_def.get('type', 'string')
            label_text = param_def.get('label', param_name)
            tooltip = param_def.get('tooltip', '')

            # 创建标签
            label = QLabel(f"{label_text}:")
            if tooltip:
                label.setToolTip(tooltip)

            # 创建输入控件
            widget, interactive_widget = self._create_parameter_widget(
                param_type, current_value, param_def
            )

            if tooltip and interactive_widget:
                interactive_widget.setToolTip(tooltip)

            # 添加到布局
            self.form_layout.addRow(label, widget)

            # 存储控件引用
            self.row_widgets[param_name] = widget
            self.interactive_widgets[param_name] = interactive_widget
            self.dynamic_param_widgets.append(widget)

        except Exception as e:
            logger.error(f"添加模块参数行失败 {param_name}: {e}")

    def _create_parameter_widget(self, param_type: str, current_value: Any,
                               param_def: Dict[str, Any]) -> Tuple[QWidget, QWidget]:
        """创建参数控件"""
        if param_type == 'string':
            widget = QLineEdit(str(current_value) if current_value is not None else "")
            return widget, widget

        elif param_type == 'int':
            widget = QSpinBox()
            widget.setRange(param_def.get('min', -999999), param_def.get('max', 999999))
            widget.setValue(int(current_value) if current_value is not None else 0)
            return widget, widget

        elif param_type == 'float':
            widget = QDoubleSpinBox()
            widget.setRange(param_def.get('min', -999999.0), param_def.get('max', 999999.0))
            widget.setDecimals(param_def.get('decimals', 2))
            widget.setValue(float(current_value) if current_value is not None else 0.0)
            return widget, widget

        elif param_type == 'bool':
            widget = QCheckBox()
            widget.setChecked(bool(current_value) if current_value is not None else False)
            return widget, widget

        elif param_type == 'select':
            widget = QComboBox()
            options = param_def.get('options', [])
            widget.addItems(options)
            if current_value and current_value in options:
                widget.setCurrentText(str(current_value))
            return widget, widget

        elif param_type == 'file':
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(5)

            line_edit = QLineEdit(str(current_value) if current_value is not None else "")
            browse_button = QPushButton("浏览...")

            file_filter = param_def.get('file_filter', '所有文件 (*)')
            browse_button.clicked.connect(
                lambda: self._browse_file_with_filter(line_edit, file_filter)
            )

            layout.addWidget(line_edit)
            layout.addWidget(browse_button)

            return container, line_edit

        else:
            # 默认为字符串输入
            widget = QLineEdit(str(current_value) if current_value is not None else "")
            return widget, widget

    def _browse_file_with_filter(self, line_edit_widget: QLineEdit, file_filter: str):
        """带文件过滤器的文件浏览"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", file_filter)
        if file_path:
            line_edit_widget.setText(file_path)

    def _create_separator_row(self, title: str) -> QWidget:
        """创建分隔符行"""
        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 5)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; color: #666;")

        layout.addWidget(title_label)
        layout.addWidget(separator)

        return container

    def _update_pre_condition_visibility(self, selected_condition_type: str):
        """Updates visibility of pre-condition parameter rows within the dialog."""
        print(f"Dialog: Updating pre-condition visibility for type: {selected_condition_type}")
        
        image_params = ["pre_image_path", "pre_confidence"]
        counter_params = ["pre_counter_name", "pre_comparison_type", "pre_target_value"]

        show_image = (selected_condition_type == "查找图片")
        show_counter = (selected_condition_type == "计数器判断")

        # Iterate through the stored row widgets
        for name, row_widget in self.row_widgets.items():
             is_image_param = name in image_params
             is_counter_param = name in counter_params

             if is_image_param:
                  row_widget.setVisible(show_image)
             elif is_counter_param:
                  row_widget.setVisible(show_counter)
                  
        # No need to adjust size here, let the caller handle it if needed
        # self.adjustSize() 

    def _update_jump_target_state(self, dropdown_text: str, target_widget: QWidget):
        """Enables/disables the jump target ID widget/container based on dropdown selection."""
        # --- MODIFIED: Expect QComboBox for jump targets --- 
        is_jump = (dropdown_text == "跳转到步骤")
        print(f"DEBUG[_update_jump_target_state]: Action='{dropdown_text}', Is Jump={is_jump}. Target widget type: {type(target_widget)}")
        if isinstance(target_widget, QComboBox):
             target_widget.setEnabled(is_jump)
             if not is_jump:
                 # If action is not jump, force selection to "无" (index 0)
                 target_widget.setCurrentIndex(0)
                 print(f"  Set '{target_widget.objectName() if target_widget.objectName() else 'target widget'}' to index 0 (无)")
        else:
             print(f"  WARNING: Expected QComboBox for jump target, got {type(target_widget)}.")
        # --- END MODIFICATION ---

        # Force style update to ensure state changes apply immediately
        target_widget.style().unpolish(target_widget)
        target_widget.style().polish(target_widget)
        target_widget.update() # Request a repaint just in case

        print(f"Dialog: Updating jump target state. Is jump: {is_jump}, Widget enabled: {target_widget.isEnabled()}")
        # Optional: Clear the value if disabled?
        # if not is_jump and isinstance(target_widget, QLineEdit):
        #     target_widget.setText("0") # Or some other default/None indicator if possible
        # elif not is_jump and isinstance(target_widget, QWidget):
             # Find the line edit inside the container
        #      lineEdit = target_widget.findChild(QLineEdit)
        #      if lineEdit:
        #          lineEdit.setText("0")

    def _refresh_ldplayer_apps(self):
        """刷新雷电模拟器应用列表"""
        try:
            print("!!! _refresh_ldplayer_apps 方法被调用 !!!")
            logger.info("开始刷新雷电模拟器应用列表")

            # 获取当前绑定的窗口句柄
            target_hwnd = self._get_target_hwnd()
            print(f"获取到的窗口句柄: {target_hwnd}")
            logger.info(f"获取到的窗口句柄: {target_hwnd}")

            if not target_hwnd:
                logger.warning("无法获取目标窗口句柄，无法刷新应用列表")
                print("!!! 无法获取目标窗口句柄 !!!")
                return

            # 导入雷电模拟器应用管理模块
            from tasks.ldplayer_app_manager import refresh_app_list

            # 获取应用列表
            apps = refresh_app_list(target_hwnd)

            # 更新应用选择器下拉框
            if hasattr(self, 'app_selector_combo') and self.app_selector_combo:
                # 清空现有选项
                self.app_selector_combo.clear()

                if apps:
                    # 添加应用选项
                    for app in apps:
                        display_name = app.get('display_name', app.get('name', app.get('package', '')))
                        self.app_selector_combo.addItem(display_name)
                    logger.info(f"成功更新应用列表，共 {len(apps)} 个应用")
                else:
                    # 没有找到应用
                    self.app_selector_combo.addItem("未找到任何应用")
                    logger.warning("未找到任何应用")
            else:
                logger.warning("未找到应用选择器下拉框")

        except Exception as e:
            logger.error(f"刷新应用列表时出错: {e}", exc_info=True)
            if hasattr(self, 'app_selector_combo') and self.app_selector_combo:
                self.app_selector_combo.clear()
                self.app_selector_combo.addItem("刷新失败")

    def _get_target_hwnd(self):
        """获取目标窗口句柄"""
        try:
            print(f"=== 开始获取目标窗口句柄 ===")
            print(f"父窗口对象: {self.parent()}")
            print(f"父窗口类型: {type(self.parent())}")

            # 尝试从父窗口获取当前绑定的窗口句柄
            if hasattr(self.parent(), 'current_target_hwnd'):
                hwnd = self.parent().current_target_hwnd
                print(f"从 current_target_hwnd 获取: {hwnd}")
                return hwnd
            elif hasattr(self.parent(), 'bound_windows'):
                print(f"从 bound_windows 获取")
                bound_windows = self.parent().bound_windows
                print(f"绑定窗口列表: {bound_windows}")
                # 从绑定窗口列表中获取第一个启用的窗口
                for window_info in bound_windows:
                    if window_info.get('enabled', True):
                        hwnd = window_info.get('hwnd')
                        print(f"找到启用的窗口: {window_info}, hwnd: {hwnd}")
                        return hwnd
            elif hasattr(self.parent(), 'current_target_window_title'):
                print(f"从 current_target_window_title 获取")
                # 根据窗口标题查找窗口句柄
                window_title = self.parent().current_target_window_title
                print(f"窗口标题: {window_title}")
                if window_title:
                    from main import find_window_by_title
                    hwnd = find_window_by_title(window_title)
                    print(f"根据标题查找到的窗口句柄: {hwnd}")
                    return hwnd

            # 尝试其他可能的属性
            parent_attrs = [attr for attr in dir(self.parent()) if 'window' in attr.lower() or 'hwnd' in attr.lower()]
            print(f"父窗口相关属性: {parent_attrs}")

            logger.warning("无法获取目标窗口句柄")
            print("!!! 无法获取目标窗口句柄 !!!")
            return None

        except Exception as e:
            logger.error(f"获取目标窗口句柄时出错: {e}")
            print(f"获取目标窗口句柄时出错: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _apply_stylesheet(self):
        """Applies a modern-looking stylesheet to the dialog."""
        qss = """
        QDialog {
            background-color: #f8f9fa; /* Light background */
            font-family: "Segoe UI", Arial, sans-serif;
        }

        QLabel {
            font-size: 9pt;
            color: #343a40; /* Darker text */
        }
        
        QLabel[alignment="AlignCenter"] {
            color: #495057; /* Slightly lighter for separators */
            margin-top: 8px; 
            margin-bottom: 4px;
        }

        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            font-size: 9pt;
            padding: 5px 8px;
            border: 1px solid #ced4da; /* Light grey border */
            border-radius: 4px;
            background-color: #ffffff; /* White background */
            color: #495057;
            /* qproperty-alignment: 'AlignLeft | AlignVCenter'; /* Apply only to QLineEdit below */
        }
        
        QLineEdit {
             qproperty-alignment: 'AlignLeft | AlignVCenter'; /* Apply alignment only here */
        }
        
        /* Explicitly target LineEdit inside SpinBoxes - Removed as ineffective */
        /* 
        QSpinBox QLineEdit, 
        QDoubleSpinBox QLineEdit {
             qproperty-alignment: 'AlignLeft | AlignVCenter'; 
        }
        */

        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
            border-color: #80bdff; /* Blue border on focus */
            outline: none; /* Remove default outline */
        }
        
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 15px;
            border-left-width: 1px;
            border-left-color: #ced4da;
            border-left-style: solid;
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
        }
        
        QComboBox::down-arrow {
            image: url(icons/down_arrow.png); /* Needs an icon */
            width: 10px;
            height: 10px;
        }
        
        /* Style for QSpinBox and QDoubleSpinBox buttons */
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            subcontrol-origin: border;
            width: 16px;
            border-left-width: 1px;
            border-left-color: #ced4da;
            border-left-style: solid;
            border-radius: 0px;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 3px; }
        QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 3px; }
        
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(icons/up_arrow.png); width: 10px; height: 10px; }
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(icons/down_arrow.png); width: 10px; height: 10px; }

        QPushButton {
            font-size: 9pt;
            padding: 6px 15px;
            border: 1px solid #adb5bd;
            border-radius: 4px;
            background-color: #ffffff;
            color: #495057;
            min-width: 60px; /* Ensure buttons have some minimum width */
        }
        
        QPushButton:hover {
            background-color: #e9ecef; /* Light hover effect */
            border-color: #6c757d;
        }
        
        QPushButton:pressed {
            background-color: #dee2e6; /* Slightly darker pressed */
        }
        
        /* Style the OK button specifically */
        QPushButton[text="确定"] { 
            background-color: #007bff; /* Primary blue */
            color: white;
            border-color: #007bff;
        }
        
        QPushButton[text="确定"]:hover {
            background-color: #0056b3; 
            border-color: #0056b3;
        }
        
        QPushButton[text="确定"]:pressed {
            background-color: #004085;
        }
        
        /* Style the browse button */
        QPushButton[text="..."] {
            padding: 2px 5px; /* Smaller padding */
            min-width: 25px;
            max-width: 25px;
        }
        
        /* Style the custom spin buttons */
        QPushButton#spinButton {
            padding: 1px 5px; /* Very small padding */
            min-width: 20px; /* Fixed small width */
            max-width: 20px;
            font-weight: bold;
            /* Optional: Add border/background similar to spinbox buttons */
            /* border-left: 1px solid #ced4da; */
            /* background-color: #f0f0f0; */
        }

        QFrame[frameShape="4"] { /* HLine */
            border: none;
            border-top: 1px solid #e0e0e0; /* Lighter separator */
            margin-top: 8px;
            margin-bottom: 8px;
        }
        
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        
        /* Style disabled state */
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QCheckBox:disabled {
            background-color: #e9ecef; /* Greyed out background */
            color: #6c757d;
        }
        QCheckBox::indicator:disabled {
           /* Add specific disabled indicator style if needed */
        }
        QPushButton:disabled {
             background-color: #ced4da;
             color: #6c757d;
             border-color: #adb5bd;
        }

        """
        self.setStyleSheet(qss)
        
    def _adjust_value(self, line_edit: QLineEdit, increment: bool, step: float, 
                      min_val: float, max_val: float, decimals: Optional[int] = None):
        """Helper to increment or decrement the value in a QLineEdit."""
        current_text = line_edit.text()
        try:
            if decimals is not None: # Handling float
                current_value = float(current_text)
                new_value = current_value + step if increment else current_value - step
                # Clamp within min/max
                new_value = max(min_val, min(max_val, new_value))
                # Format back to string with correct decimals
                line_edit.setText(f"{new_value:.{decimals}f}")
            else: # Handling int
                current_value = int(current_text)
                new_value = current_value + int(step) if increment else current_value - int(step)
                # Clamp within min/max
                new_value = max(int(min_val), min(int(max_val), new_value))
                line_edit.setText(str(new_value))
        except ValueError:
            # If current text is invalid, try setting to min or 0
            reset_val = min_val if min_val > -float('inf') else 0
            if decimals is not None:
                 line_edit.setText(f"{float(reset_val):.{decimals}f}")
            else:
                 line_edit.setText(str(int(reset_val)))

    def _increment_value(self, line_edit: QLineEdit, step: float, 
                         min_val: float, max_val: float, decimals: Optional[int] = None):
        self._adjust_value(line_edit, True, step, min_val, max_val, decimals)
        
    def _decrement_value(self, line_edit: QLineEdit, step: float, 
                         min_val: float, max_val: float, decimals: Optional[int] = None):
        self._adjust_value(line_edit, False, step, min_val, max_val, decimals)
        
    def _handle_conditional_visibility_check(self):
        """Checks all conditions and updates widget visibility."""
        # --- ADDED More Debugging --- 
        sender = self.sender() # Get the object that emitted the signal
        print(f"--- DEBUG: _handle_conditional_visibility_check called (Sender: {type(sender).__name__} {getattr(sender, 'objectName', '')() if sender else 'N/A'}) ---")
        # ---------------------------
        
        # --- REMOVED TEMPORARY TEST --- 
        # force_show_names = ['image_confidence', 'on_image_found', 'image_found_jump_target_id', 'on_image_not_found', 'image_not_found_jump_target_id']
        # for name in force_show_names:
        #     if name in self.row_widgets:
        #         self.row_widgets[name].setVisible(True)
        #         print(f"DEBUG: Force setting visibility for '{name}' to True")
        # self.adjustSize() # Adjust size after forcing
        # # return # Uncomment this line to skip the actual condition check during this test
        # ----------------------------------------
        
        current_values = self._get_current_dialog_values() # Get intermediate values

        visibility_changed = False # Track if any visibility actually changed
        for name, row_widget in self.row_widgets.items():
            param_def = self.param_definitions.get(name)
            if not param_def or 'condition' not in param_def:
                continue

            condition = param_def['condition']

            # 🔧 修复：处理列表类型的条件（多条件组合）
            if isinstance(condition, list):
                # 如果是列表，跳过处理（目前不支持复杂的多条件逻辑）
                # 或者可以实现AND/OR逻辑，这里先简单跳过
                print(f"  DEBUG: Parameter '{name}' has list-type condition, skipping for now")
                continue

            # 确保condition是字典类型
            if not isinstance(condition, dict):
                print(f"  WARNING: Parameter '{name}' has invalid condition type: {type(condition)}")
                continue

            controller_param = condition.get('param')
            required_value = condition.get('value')
            value_not = condition.get('value_not') # Check for 'value_not' condition
            operator = condition.get('operator') # Get operator explicitly

            # --- ADDED Controller Value Debug ---
            if name == 'refresh_apps':
                print(f"!!! 检查 refresh_apps 条件 !!!")
                print(f"  controller_param: {controller_param}")
                print(f"  required_value: {required_value}")
                print(f"  current_values: {current_values}")
                print(f"  controller_param in current_values: {controller_param in current_values}")

            if controller_param not in current_values:
                print(f"  DEBUG: Controller '{controller_param}' not found in current values for '{name}'")
                if name == 'refresh_apps':
                    print(f"!!! refresh_apps 被隐藏：控制参数 '{controller_param}' 未找到 !!!")
                row_widget.setVisible(False)
                continue
            actual_value = current_values[controller_param]

            if name == 'refresh_apps':
                print(f"  actual_value: {actual_value}")
                print(f"  actual_value == required_value: {actual_value == required_value}")
            # ----------------------------------

            # --- REVISED Logic for Clarity and value_not --- 
            is_visible = False
            required_comparison_value = required_value if value_not is None else value_not
            
            # Determine effective operator and expected match result for visibility
            if value_not is not None:
                effective_operator = operator if operator else '!=' # Default to != if value_not is used
                should_be_visible_on_match = True # Visibility depends on NOT matching the value_not value
            else:
                effective_operator = operator if operator else '==' # Default to == if value is used
                should_be_visible_on_match = True # Visibility depends on matching the value
                
            print(f"  DEBUG: Check '{name}' visibility based on '{controller_param}': Actual='{actual_value}', Required='{required_comparison_value}', Op='{effective_operator}', VisibleOnMatch={should_be_visible_on_match}")

            match = False
            try:
                # Handle boolean comparison specifically for CheckBox
                if isinstance(actual_value, bool) and isinstance(required_comparison_value, bool):
                    actual_typed = actual_value
                # Handle empty string specifically for LineEdit controlling visibility
                elif isinstance(actual_value, str) and required_comparison_value == "":
                    actual_typed = actual_value # Compare strings directly
                # General type conversion
                elif required_comparison_value is not None:
                    # Try to convert actual_value to the type of required_comparison_value
                    try:
                        actual_typed = type(required_comparison_value)(actual_value)
                    except (ValueError, TypeError):
                         # If direct conversion fails, maybe it's a string comparison?
                         actual_typed = str(actual_value)
                         required_comparison_value = str(required_comparison_value)
                else: # required_comparison_value is None
                    actual_typed = actual_value

                if effective_operator == '==':
                    match = (actual_typed == required_comparison_value)
                elif effective_operator == '!=':
                    match = (actual_typed != required_comparison_value)
                elif effective_operator == 'in':
                    match = (isinstance(required_comparison_value, list) and actual_typed in required_comparison_value)
                elif effective_operator == 'notin':
                    match = (isinstance(required_comparison_value, list) and actual_typed not in required_comparison_value)
                else:
                    print(f"    WARNING: Unsupported operator '{effective_operator}' for '{name}'")
            except Exception as e:
                 print(f"    WARNING: Condition check error for '{name}': {e}")
                 
            # Determine visibility based on match and value_not
            is_visible = match
            # ----------------------------------

            # Check if visibility will change
            current_visibility = row_widget.isVisible()
            if current_visibility != is_visible:
                 visibility_changed = True
                 print(f"  DEBUG: Setting visibility for '{name}' (Widget: {type(row_widget).__name__}) to {is_visible} (changed from {current_visibility})")
            #else: # Optionally log even if visibility doesn't change
            #    print(f"  DEBUG: Visibility for '{name}' remains {is_visible}")
                 
            row_widget.setVisible(is_visible)
            # --- ADDED: Force update attempts ---
            if visibility_changed:
                row_widget.update()
                # row_widget.adjustSize() # Might not be needed for the container itself
            # ------------------------------------
            
        # After updating visibility of all rows, adjust the dialog size ONLY if needed
        if visibility_changed:
            # Force layout update before adjusting size
            print("DEBUG: Forcing layout update and calling adjustSize()")
            self.params_layout.activate() # Try activating the layout
            self.params_layout.update() # <<< ADDED
            self.main_layout.activate()   # Try activating the main layout
            self.main_layout.update() # <<< ADDED
            # 工具 修复：延迟调整大小，确保布局更新完成
            QTimer.singleShot(0, self._delayed_size_adjustment)

    def _get_current_dialog_values(self) -> Dict[str, Any]: # <--- ADDED this helper
        """Gets the current values from the dialog widgets FOR INTERNAL USE (like conditions)."""
        values = {}
        for name, widget in self.widgets.items():
            param_def = self.param_definitions.get(name, {})
            param_type = param_def.get('type', 'text')
            
            try: # Wrap individual gets in try-except
                if isinstance(widget, QLineEdit):
                    values[name] = widget.text()
                elif isinstance(widget, QComboBox):
                    values[name] = widget.currentText()
                elif isinstance(widget, QCheckBox):
                    values[name] = widget.isChecked()
                elif isinstance(widget, QPlainTextEdit): # <-- ADD getting value from QPlainTextEdit
                    values[name] = widget.toPlainText()
                elif param_type == 'radio':
                    if isinstance(widget, QButtonGroup): # widget is self.widgets[name]
                        button_group = widget
                        checked_button = button_group.checkedButton()
                        if checked_button:
                            values[name] = checked_button.property("value_key") # Get the stored key
                        else:
                            # No button selected, fallback to default
                            values[name] = param_def.get('default')
                            # Minimal logging for this specific case to avoid spam if defaults are common
                            if param_def.get('default') is not None:
                                logger.debug(f"Radio group '{name}' has no selection, using default: {values[name]}")
                    else:
                        logger.warning(f"Widget for radio parameter '{name}' is type '{type(widget).__name__}' not QButtonGroup as expected. Fallback to default.")
                        values[name] = param_def.get('default')
                # Add other widget types if needed
            except Exception as e:
                 print(f"警告: 获取控件 '{name}' 的临时值时出错: {e}")
                 values[name] = None # Set to None on error
                 
        # print(f"DEBUG: Current dialog values for conditions: {values}")
        # --- ADDED: Specific debug for controller value ---
        if "condition_image_path" in values:
             print(f"  DEBUG: _get_current_dialog_values returning condition_image_path = '{values['condition_image_path']}'")
        # ------------------------------------------------
        return values

    def get_parameters(self) -> dict:
        """Retrieves the updated parameters from the widgets."""
        print(f"\n搜索 开始执行get_parameters方法")
        print(f"搜索 当前widgets数量: {len(self.widgets)}")
        print(f"搜索 当前参数: {self.current_parameters}")
        updated_params = self.current_parameters.copy() # Start with existing values

        # Helper to parse RGB from string (copied from find_color_task for consistency)
        def _parse_rgb(color_str: str) -> Optional[Tuple[int, int, int]]:
            try:
                parts = [int(c.strip()) for c in color_str.split(',')]
                if len(parts) == 3 and all(0 <= c <= 255 for c in parts):
                    return tuple(parts)
                logger.error(f"(UI Dialog) Invalid RGB format: '{color_str}'. Expected R,G,B")
                return None
            except Exception:
                 logger.error(f"(UI Dialog) Error parsing RGB string: '{color_str}'.")
                 return None

        for name, widget in self.widgets.items():
            param_def = self.param_definitions.get(name, {})
            param_type = param_def.get('type', 'text')
            widget_hint = param_def.get('widget_hint') # <<< Get widget hint
            new_value: Any = None

            try:
                # --- Existing value retrieval logic --- 
                if isinstance(widget, QLineEdit):
                    new_value = widget.text()
                elif isinstance(widget, QSpinBox):
                    new_value = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    new_value = widget.value()
                elif isinstance(widget, QCheckBox):
                    new_value = widget.isChecked()
                elif isinstance(widget, QComboBox):
                    # <<< MODIFIED: Handle card_selector data retrieval >>>
                    if widget_hint == 'card_selector':
                        new_value = widget.currentData() # Get card ID (or None)
                    else:
                        new_value = widget.currentText()
                elif isinstance(widget, QButtonGroup):
                    selected_button = widget.checkedButton()
                    if selected_button:
                         new_value = selected_button.property("value_key") # <--- 获取正确的 value_key
                elif isinstance(widget, QPlainTextEdit):
                      new_value = widget.toPlainText()
                elif widget_hint == 'ocr_region_selector':
                    # Get region from OCR region selector
                    print(f"搜索 处理OCR区域选择器: {name}")
                    region = widget.get_region()
                    print(f"搜索 OCR区域选择器get_region()返回: {region}")

                    # 首先尝试从隐藏参数中获取最新的值
                    if hasattr(self, '_hidden_params'):
                        saved_x = self._hidden_params.get('region_x')
                        saved_y = self._hidden_params.get('region_y')
                        saved_width = self._hidden_params.get('region_width')
                        saved_height = self._hidden_params.get('region_height')
                        if saved_x is not None and saved_y is not None and saved_width is not None and saved_height is not None:
                            # 使用隐藏参数中保存的最新值
                            updated_params.update({
                                'region_x': saved_x,
                                'region_y': saved_y,
                                'region_width': saved_width,
                                'region_height': saved_height
                            })
                            print(f"搜索 使用隐藏参数中保存的OCR区域: ({saved_x}, {saved_y}, {saved_width}, {saved_height})")
                        elif region and any(region):
                            # 如果隐藏参数中没有值，使用get_region()返回的值
                            x, y, width, height = region
                            updated_params.update({
                                'region_x': x,
                                'region_y': y,
                                'region_width': width,
                                'region_height': height
                            })
                            print(f"搜索 使用get_region()返回的OCR区域: ({x}, {y}, {width}, {height})")
                        else:
                            print(f"搜索 OCR区域选择器无有效区域数据")
                    elif region and any(region):
                        # 如果没有隐藏参数，使用get_region()返回的值
                        x, y, width, height = region
                        updated_params.update({
                            'region_x': x,
                            'region_y': y,
                            'region_width': width,
                            'region_height': height
                        })
                        print(f"搜索 使用get_region()返回的OCR区域: ({x}, {y}, {width}, {height})")
                    else:
                        print(f"搜索 OCR区域选择器未返回有效区域")
                    new_value = None  # OCR区域选择器本身不存储值
                elif widget_hint == 'motion_region_selector':
                    # 处理移动检测区域选择器
                    print(f"搜索 处理移动检测区域选择器: {name}")
                    region = widget.get_region()
                    print(f"搜索 移动检测区域选择器get_region()返回: {region}")

                    # 首先尝试从current_parameters中获取最新的值
                    saved_x = self.current_parameters.get('minimap_x')
                    saved_y = self.current_parameters.get('minimap_y')
                    saved_width = self.current_parameters.get('minimap_width')
                    saved_height = self.current_parameters.get('minimap_height')

                    if saved_x is not None and saved_y is not None and saved_width is not None and saved_height is not None:
                        # 使用current_parameters中保存的最新值
                        updated_params.update({
                            'minimap_x': saved_x,
                            'minimap_y': saved_y,
                            'minimap_width': saved_width,
                            'minimap_height': saved_height
                        })
                        print(f"搜索 使用current_parameters中保存的移动检测区域: ({saved_x}, {saved_y}, {saved_width}, {saved_height})")
                    elif region and any(region):
                        # 如果current_parameters中没有值，使用get_region()返回的值
                        x, y, width, height = region
                        updated_params.update({
                            'minimap_x': x,
                            'minimap_y': y,
                            'minimap_width': width,
                            'minimap_height': height
                        })
                        print(f"搜索 使用get_region()返回的移动检测区域: ({x}, {y}, {width}, {height})")
                    else:
                        print(f"搜索 移动检测区域选择器未返回有效区域")
                    new_value = None  # 移动检测区域选择器本身不存储值
                elif widget_hint == 'coordinate_selector':
                    # 坐标选择器不存储值，跳过
                    new_value = None
                elif widget_hint == 'motion_region_selector':
                    # 移动检测区域选择器不存储值，跳过（区域信息已在选择时更新到current_parameters）
                    new_value = None
                # Add more widget types if needed

                # --- Type Conversion (Optional but recommended) ---
                if new_value is not None:
                    original_type = type(self.current_parameters.get(name)) # Get type of original value
                    if original_type is int and isinstance(new_value, str):
                        try: new_value = int(new_value)
                        except ValueError: pass # Keep as string if conversion fails
                    elif original_type is float and isinstance(new_value, str):
                         try: new_value = float(new_value)
                         except ValueError: pass # Keep as string
                    elif original_type is bool and isinstance(new_value, str):
                         new_value = new_value.lower() in ['true', '1', 'yes', 'y']

                # 工具 简化：直接设置参数，让参数处理器处理复杂逻辑
                updated_params[name] = new_value
                
            except Exception as e:
                 logger.error(f"Error retrieving value for parameter '{name}': {e}")
                 # Keep the original value if retrieval fails
                 updated_params[name] = self.current_parameters.get(name)

        # --- ADDED: Post-process for FindColorTask to calculate HSV --- 
        if self.task_type == '找色功能':
            logger.info("(UI Dialog) Post-processing parameters for FindColorTask...")
            rgb_str = updated_params.get('target_color_input')
            if isinstance(rgb_str, str):
                rgb_tuple = _parse_rgb(rgb_str)
                if rgb_tuple:
                    # Get default tolerances from definitions (since widgets are hidden)
                    try:
                        h_tol = int(self.param_definitions.get('h_tolerance', {}).get('default', 10))
                        s_tol = int(self.param_definitions.get('s_tolerance', {}).get('default', 40))
                        v_tol = int(self.param_definitions.get('v_tolerance', {}).get('default', 40))
                        logger.debug(f"(UI Dialog) Using tolerances for HSV calc: H={h_tol}, S={s_tol}, V={v_tol}")
                        
                        # Calculate HSV range
                        hsv_range_dict = self._calculate_hsv_range(rgb_tuple, h_tol, s_tol, v_tol)
                        
                        # Add calculated HSV values to the parameters
                        if hsv_range_dict:
                             updated_params.update(hsv_range_dict)
                             logger.info("(UI Dialog) Successfully calculated and added HSV range to parameters.")
                        else:
                            logger.warning("(UI Dialog) HSV range calculation failed, not adding HSV parameters.")
                            
                    except Exception as e:
                        logger.exception(f"(UI Dialog) Error getting tolerances or calculating HSV: {e}")
                else:
                    logger.warning(f"(UI Dialog) Could not parse RGB string '{rgb_str}' for HSV calculation.")
            else:
                 logger.warning("(UI Dialog) 'target_color_input' parameter not found or not a string.")
        # --- END ADDED ---

        # --- ADDED: Merge hidden parameters FIRST, but don't overwrite coordinate selector params ---
        if hasattr(self, '_hidden_params') and self._hidden_params:
            print(f"搜索 合并隐藏参数: {self._hidden_params}")
            # 工具 修复：更智能的参数合并逻辑
            # 分离不同类型的参数，避免混乱
            coordinate_selector_params = {'coordinate_x', 'coordinate_y'}
            ocr_region_params = {'region_x', 'region_y', 'region_width', 'region_height'}
            motion_detection_params = {'minimap_x', 'minimap_y', 'minimap_width', 'minimap_height'}
            protected_params = coordinate_selector_params | ocr_region_params | motion_detection_params
            print(f"搜索 受保护参数列表: {protected_params}")

            for param_name, param_value in self._hidden_params.items():
                # 检查是否是受保护的参数且已经被设置
                if param_name in protected_params and param_name in updated_params:
                    current_value = updated_params[param_name]
                    # 只有当前值为None、空或0时才使用隐藏参数的值
                    if current_value is None or current_value == '' or current_value == 0:
                        updated_params[param_name] = param_value
                        print(f"搜索 使用隐藏参数 {param_name} = {param_value} (当前值为空或0)")
                    else:
                        print(f"搜索 跳过隐藏参数 {param_name}，保持已设置的值: {current_value}")
                else:
                    # 非受保护参数或未设置的参数，直接使用隐藏参数值
                    updated_params[param_name] = param_value
                    print(f"搜索 设置隐藏参数 {param_name} = {param_value}")
            print(f"搜索 隐藏参数合并后的结果: {updated_params}")
        else:
            print(f"搜索 没有隐藏参数需要合并")
        # --- END ADDED ---

        # 坐标选择器数据合并已删除

        # 工具 修复：参数验证和保护机制
        print(f"搜索 参数验证开始...")

        # 工具 完全重写：模拟鼠标操作参数的简洁处理
        if self.task_type == "模拟鼠标操作":
            print(f"搜索 处理模拟鼠标操作参数")

            # 检查是否使用了坐标选择工具
            coordinate_tool_used = hasattr(self, '_coordinate_tool_used') and self._coordinate_tool_used

            if coordinate_tool_used:
                # 如果使用了坐标工具，强制设置为坐标点击模式
                updated_params['operation_mode'] = '坐标点击'
                print(f"搜索 检测到使用了坐标选择工具，强制设置操作模式为坐标点击")

            # 确保坐标参数是整数类型
            coord_x = updated_params.get('coordinate_x')
            coord_y = updated_params.get('coordinate_y')

            if coord_x is not None:
                try:
                    updated_params['coordinate_x'] = int(coord_x)
                except (ValueError, TypeError):
                    updated_params['coordinate_x'] = 0

            if coord_y is not None:
                try:
                    updated_params['coordinate_y'] = int(coord_y)
                except (ValueError, TypeError):
                    updated_params['coordinate_y'] = 0

            print(f"搜索 模拟鼠标操作参数处理完成: 模式={updated_params.get('operation_mode')}, 坐标=({updated_params.get('coordinate_x')}, {updated_params.get('coordinate_y')})")



        print(f"搜索 get_parameters最终返回: {updated_params}")
        return updated_params

    def reject(self):
        """重写reject方法，添加调试信息"""
        print(f"搜索 reject()方法被调用！")
        import traceback
        print(f"搜索 reject调用栈：")
        for line in traceback.format_stack()[-3:-1]:
            print(f"    {line.strip()}")
        super().reject()
        print(f"搜索 父类reject()调用完成")

    def _on_ok_clicked(self):
        """确定按钮点击处理"""
        print(f"搜索 确定按钮被点击！调用accept()...")
        self.accept()

    def _on_cancel_clicked(self):
        """取消按钮点击处理"""
        print(f"搜索 取消按钮被点击！调用reject()...")
        self.reject()

    def accept(self):
        """修复的accept方法 - 确保参数被保存"""
        print(f"搜索 accept()方法被调用！")

        try:
            # 获取并保存最终参数
            print(f"搜索 获取最终参数...")
            final_params = self.get_parameters()
            self._final_parameters = final_params
            print(f"搜索 参数已保存: {final_params}")

            # 调用父类的accept方法
            print(f"搜索 调用父类accept()...")
            super().accept()
            print(f"搜索 父类accept()调用完成，对话框结果: {self.result()}")

        except Exception as e:
            print(f"搜索 accept()过程中出现异常: {e}")
            import traceback
            traceback.print_exc()
            # 即使出现异常也要调用父类accept
            super().accept()

    # --- ADDED: Helper for HSV Calculation ---
    def _calculate_hsv_range(self, rgb_tuple: Tuple[int, int, int], 
                             h_tol: int, s_tol: int, v_tol: int) -> Dict[str, int]:
        """Calculates HSV range based on RGB color and tolerances."""
        hsv_results = {}
        try:
            # Convert RGB to HSV (using BGR format for OpenCV)
            target_bgr_arr = np.uint8([[rgb_tuple[::-1]]]) 
            target_hsv_arr = cv2.cvtColor(target_bgr_arr, cv2.COLOR_BGR2HSV)
            h, s, v = map(int, target_hsv_arr[0][0])
            logger.debug(f"(UI Dialog) RGB {rgb_tuple} -> Center HSV: H={h}, S={s}, V={v}")

            # Calculate range using standard ints
            h_min_calc = h - h_tol
            h_max_calc = h + h_tol
            s_min_calc = s - s_tol
            s_max_calc = s + s_tol
            v_min_calc = v - v_tol
            v_max_calc = v + v_tol

            # Clamp values
            h_min_final = max(0, min(h_min_calc, 179))
            h_max_final = max(0, min(h_max_calc, 179))
            s_min_final = max(0, min(s_min_calc, 255))
            s_max_final = max(0, min(s_max_calc, 255))
            v_min_final = max(0, min(v_min_calc, 255))
            v_max_final = max(0, min(v_max_calc, 255))
            
            hsv_results = {
                'h_min': h_min_final,
                'h_max': h_max_final,
                's_min': s_min_final,
                's_max': s_max_final,
                'v_min': v_min_final,
                'v_max': v_max_final
            }
            logger.info(f"(UI Dialog) Calculated HSV range: H=[{hsv_results['h_min']}-{hsv_results['h_max']}], "
                        f"S=[{hsv_results['s_min']}-{hsv_results['s_max']}], V=[{hsv_results['v_min']}-{hsv_results['v_max']}]")

        except Exception as e:
            logger.exception(f"(UI Dialog) Error calculating HSV range: {e}")
            # Return empty dict on error
            return {}
        
        return hsv_results
    # --- END ADDED Helper ---

    # --- ADDED: Slot for browsing image file --- 
    def _browse_image_file(self, line_edit_widget: QLineEdit):
        """Opens a file dialog to select an image, stores relative path if possible."""
        start_dir = self.images_dir or "." # Start in images_dir or current directory
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择图片文件", 
            start_dir, 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*)"
        )

        if file_path:
            if self.images_dir:
                try:
                    relative_path = os.path.relpath(file_path, self.images_dir)
                    # If the path starts with '..', it's outside images_dir
                    if relative_path.startswith('..') or os.path.isabs(relative_path):
                        logger.warning(f"选择的文件 '{file_path}' 不在图片目录 '{self.images_dir}' 或其子目录中，将存储绝对路径。")
                        line_edit_widget.setText(file_path)
                    else:
                        logger.info(f"选择的文件 '{file_path}' 在图片目录中，存储相对路径: '{relative_path}'")
                        line_edit_widget.setText(relative_path) # Store relative path
                except ValueError:
                    # Happens on Windows if paths are on different drives
                    logger.warning(f"无法计算相对路径 (可能在不同驱动器上)，将存储绝对路径: '{file_path}'")
                    line_edit_widget.setText(file_path) # Store absolute path as fallback
            else:
                # images_dir not set, store absolute path
                logger.warning("图片目录未设置，将存储绝对路径。")
                line_edit_widget.setText(file_path)
    # --- END ADDED ---

    # ==================================
    # Static Method for Convenience
    @staticmethod
    def get_task_parameters(param_definitions: Dict[str, Dict[str, Any]],
                              current_parameters: Dict[str, Any],
                              title: str,
                              task_type: str, # <<< ADDED: Explicit task_type parameter
                              # --- ADDED: Receive workflow cards info ---
                              workflow_cards_info: Optional[Dict[int, tuple[str, int]]] = None, # {seq_id: (task_type, card_id)}
                              # -------------------------------------------
                              images_dir: Optional[str] = None, # <<< ADDED: Parameter for images_dir
                              editing_card_id: Optional[int] = None, # <<< ADDED: Parameter for editing_card_id
                              parent: Optional[QWidget] = None) -> Optional[Dict[str, Any]]:
        """Creates and executes the dialog, returning the new parameters if accepted."""
        import traceback
        print(f"get_task_parameters被调用！调用栈：")
        for line in traceback.format_stack()[-3:-1]:  # 显示最近的2层调用栈
            print(f"    {line.strip()}")
        dialog = ParameterDialog(
            param_definitions, 
            current_parameters, 
            title,
            task_type, # <<< ADDED: Pass task_type
            workflow_cards_info=workflow_cards_info, # Pass info
            images_dir=images_dir, # <<< ADDED: Pass images_dir to instance
            editing_card_id=editing_card_id, # <<< ADDED: Pass editing_card_id
            parent=parent
        )
        print(f"  [DEBUG] Instantiating ParameterDialog...")

        # 修复：检查是否有OCR区域选择器、坐标选择器或移动检测区域选择器，如果有则使用非模态对话框
        has_ocr_selector = any(
            param_def.get('widget_hint') == 'ocr_region_selector'
            for param_def in param_definitions.values()
        )
        has_coordinate_selector = any(
            param_def.get('widget_hint') == 'coordinate_selector'
            for param_def in param_definitions.values()
        )
        has_motion_region_selector = any(
            param_def.get('widget_hint') == 'motion_region_selector'
            for param_def in param_definitions.values()
        )

        if has_ocr_selector or has_coordinate_selector or has_motion_region_selector:
            if has_ocr_selector:
                selector_type = "OCR区域选择器"
            elif has_coordinate_selector:
                selector_type = "坐标选择器"
            else:
                selector_type = "移动检测区域选择器"
            print(f"  [DEBUG] 检测到{selector_type}，使用非模态对话框...")
            # 强制设置为非模态对话框
            dialog.setModal(False)
            dialog.setWindowModality(Qt.WindowModality.NonModal)

            # 设置窗口标志确保不阻塞其他窗口，但不要始终置顶
            # 移除 WindowStaysOnTopHint 以允许目标窗口显示在前面
            dialog.setWindowFlags(
                dialog.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint
            )

            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            # 创建事件循环等待对话框关闭
            from PySide6.QtCore import QEventLoop
            loop = QEventLoop()
            dialog.finished.connect(loop.quit)

            print(f"  [DEBUG] 启动非模态对话框事件循环...")
            loop.exec()

            result = dialog.result()
            print(f"  [DEBUG] 非模态对话框完成，结果: {result}")
        else:
            print(f"  [DEBUG] 使用标准模态对话框...")
            result = dialog.exec()
            print(f"  [DEBUG] dialog.exec() finished with result: {result} (Accepted={QDialog.Accepted})")
        print(f"  [DEBUG] QDialog.Accepted 的值是: {QDialog.Accepted}")
        print(f"  [DEBUG] result == QDialog.Accepted: {result == QDialog.Accepted}")
        if result == QDialog.Accepted:
            print(f"  [DEBUG] 对话框被接受，正在获取参数...")
            # 优先使用保存的参数，如果没有则调用get_parameters
            if hasattr(dialog, '_final_parameters'):
                new_params = dialog._final_parameters
                print(f"  [DEBUG] 使用保存的参数: {new_params}")
            else:
                new_params = dialog.get_parameters()
                print(f"  [DEBUG] 调用get_parameters获取参数: {new_params}")
            return new_params
        else:
            print(f"  [DEBUG] Dialog was rejected or closed.")
            return None # Indicate cancellation

    def _initial_size_adjustment(self):
        """初始化完成后调整对话框大小"""
        try:
            # 让对话框根据内容自动调整大小
            self.adjustSize()
            # 确保对话框不会太小
            current_size = self.size()
            min_width = max(500, current_size.width())
            min_height = max(300, current_size.height())
            self.resize(min_width, min_height)
        except Exception as e:
            logger.warning(f"初始大小调整失败: {e}")

    def _adjust_text_edit_height(self, text_edit: QPlainTextEdit, size):
        """根据内容自动调整文本编辑器高度"""
        try:
            # 计算内容高度
            doc_height = int(size.height())
            # 添加一些边距
            new_height = min(max(80, doc_height + 20), 200)

            # 只有当高度变化较大时才调整
            current_height = text_edit.height()
            if abs(new_height - current_height) > 10:
                text_edit.setFixedHeight(new_height)
                # 调整对话框大小
                QTimer.singleShot(0, self.adjustSize)
        except Exception as e:
            logger.warning(f"文本编辑器高度调整失败: {e}")

    def _delayed_size_adjustment(self):
        """延迟调整对话框大小"""
        try:
            # 强制更新布局
            self.updateGeometry()
            # 调整大小以适应内容
            self.adjustSize()
            # 确保最小尺寸
            current_size = self.size()
            min_width = max(500, current_size.width())
            if current_size.width() < min_width:
                self.resize(min_width, current_size.height())
        except Exception as e:
            logger.warning(f"延迟大小调整失败: {e}")


if __name__ == '__main__':
    # Example Usage
    logging.basicConfig(level=logging.DEBUG)
    app = QApplication(sys.argv)

    # Example definitions (similar to conditional_control)
    defs = {
        "condition_type": {
            "label": "条件类型", 
            "type": "select", 
            "options": ["查找图片", "计数器判断", "移动检测"], 
            "default": "查找图片"
        },
        "image_path": {
            "label": "图片路径", 
            "type": "file", 
            "default": "", 
            "condition": {"param": "condition_type", "value": "查找图片"}
        },
        "on_success": {
            "label": "条件满足时", 
            "type": "select", 
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"], 
            "default": "执行下一步"
        },
        "success_jump_target_id": {
            "label": "成功跳转目标 ID", 
            "type": "int", 
            "default": 0, 
            "min": 0,
            "condition": {"param": "on_success", "value": "跳转到步骤"}
        },
         "on_failure": {
            "label": "条件不满足时", 
            "type": "select", 
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"], 
            "default": "执行下一步"
        },
        "failure_jump_target_id": {
            "label": "失败跳转目标 ID", 
            "type": "int", 
            "default": 0, 
            "min": 0,
            "condition": {"param": "on_failure", "value": "跳转到步骤"}
        }
    }

    current_params = {
        "condition_type": "查找图片",
        "image_path": "C:/temp/img.png",
        "on_success": "执行下一步",
        "success_jump_target_id": None, # Start as None
        "on_failure": "执行下一步",
        "failure_jump_target_id": None # Start as None
    }

    print("--- Opening Dialog --- ")
    new_params = ParameterDialog.get_task_parameters(defs, current_params, "测试条件控制", "查找图片")

    if new_params:
        print("\n--- Dialog Accepted --- ")
        print("New Parameters:", new_params)
    else:
        print("\n--- Dialog Cancelled --- ")

    # sys.exit(app.exec()) # Keep running if needed for testing

    sys.exit(app.exec()) 