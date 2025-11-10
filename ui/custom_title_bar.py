# -*- coding: utf-8 -*-
import sys
from typing import List
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QStyle, QApplication, QSizePolicy, QToolButton,
    QSpacerItem # Import QSpacerItem
)
# Import QIcon explicitly if needed for size setting
from PySide6.QtCore import Qt, QPoint, QSize 
from PySide6.QtGui import QMouseEvent, QAction, QIcon, QFontMetrics

class MainWindow: pass

class CustomTitleBar(QWidget):
    """A custom title bar where title is manually centered."""
    def __init__(self, parent: 'MainWindow', actions: List[QAction]):
        super().__init__(parent)
        self.setAutoFillBackground(False) 

        self.parent_window = parent 
        self._mouse_pressed = False
        self._mouse_press_pos = QPoint()
        self._window_pos_before_move = QPoint()
        
        # 初始化action_widgets字典和toolbar
        self.action_widgets = {}
        self.toolbar = QWidget(self)

        self.setFixedHeight(36) 
        self.setObjectName("CustomTitleBar") 
        
        # Stylesheet... (Ensure QLabel#titleLabel style exists if needed)
        self.setStyleSheet("""
            #CustomTitleBar {
                background-color: #F9F9F9; /* Very light grey background */
                color: #333333; /* Dark grey text */
                /* border-bottom: 1px solid #E0E0E0; Optional subtle border */
            }
            /* Action Buttons (QToolButton) - Icon Only */
             QToolButton {
                background-color: transparent;
                border: none;
                padding: 4px; /* Adjust padding around icon */
                margin: 1px 2px; 
                border-radius: 4px;
                /* Ensure icon is visible */
                color: #333333; 
                icon-size: 18px; /* Explicit icon size */
            }
             QToolButton:hover {
                 background-color: #E8E8E8; /* Light grey hover */
            }
             QToolButton:pressed {
                 background-color: #DCDCDC; /* Slightly darker pressed */
            }
             QToolButton:disabled {
                 /* Icon might need specific handling for disabled state */
                 /* color: #AAAAAA; */
                 opacity: 0.5; /* Or make it semi-transparent */
            }
            /* Window Control Buttons - Using Characters */
            QPushButton#windowButton {
                background-color: transparent;
                border: none;
                padding: 0px 10px; 
                margin: 0px 2px; /* Add small horizontal margin */
                border-radius: 4px; /* Add border-radius */
                color: #555555; 
                font-family: "Segoe UI Symbol", "Segoe UI Emoji", "Arial"; 
                font-size: 14px; 
                font-weight: normal;
                min-width: 36px; /* Adjust width slightly */
                min-height: 30px; /* Adjust height slightly */
                /* Align symbols better if needed */
                /* vertical-align: middle; Does not work directly in Qt stylesheets */
            }
            QPushButton#windowButton:hover {
                background-color: #E8E8E8; 
                color: #111111; 
                /* Ensure radius is kept on hover */
                border-radius: 4px; 
            }
            QPushButton#windowButton:pressed {
                background-color: #DCDCDC;
                /* Ensure radius is kept on press */
                border-radius: 4px; 
            }
            /* Close button hover: Use background color again, keep radius */
            QPushButton#closeButton:hover {
                background-color: #E81123; /* Restore red background */
                color: white; 
                border: none; /* Remove border from previous attempt */
                border-radius: 4px;
                 padding: 0px 10px; /* Restore padding */
            }
            QPushButton#closeButton:pressed {
                 background-color: #B00000; 
                 color: white;
                 border: none; 
                 border-radius: 4px;
                 padding: 0px 10px; 
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 0, 0, 0) 
        main_layout.setSpacing(2)

        # --- Left Actions --- 
        self.action_buttons = {} 
        self.file_actions_container = QWidget(self) 
        container_layout = QHBoxLayout(self.file_actions_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        toggle_button = None
        if actions:
            toggle_action = actions[0]
            toggle_button = QToolButton(self)
            toggle_button.setDefaultAction(toggle_action)
            toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            toggle_button.setFixedSize(28, 28)
            main_layout.addWidget(toggle_button)
            self.action_buttons[toggle_action] = toggle_button

            for action in actions[1:]:
                button = QToolButton(self.file_actions_container)
                button.setDefaultAction(action)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(28, 28)
                container_layout.addWidget(button)
                self.action_buttons[action] = button 
            
            main_layout.addWidget(self.file_actions_container)
        
        # --- Spacer between left and right buttons --- 
        # Remove previous stretch
        main_layout.addStretch(1) # Keep stretch to push right buttons

        # --- Title Label (Created but NOT added to layout) ---
        self.title_label = QLabel(self) # Parent is self (the title bar)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setMouseTracking(True) # Keep mouse tracking for tooltips
        self._full_title = "" # Store the full title text
        # We will set its geometry manually

        # --- Window Buttons (Right) --- 
        self.window_button_container = QWidget(self) # Store container reference
        window_button_layout = QHBoxLayout(self.window_button_container)
        window_button_layout.setContentsMargins(0,0,4,0) 
        style = self.style()
        def create_window_button(text, tooltip): 
            button = QPushButton(text, self.window_button_container)
            button.setObjectName("windowButton")
            button.setToolTip(tooltip)
            return button
        self.minimize_button = create_window_button("−", "最小化")
        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        window_button_layout.addWidget(self.minimize_button)
        self.maximize_char = "□"; self.restore_char = "❐"
        self.maximize_button = create_window_button(self.maximize_char, "最大化")
        self.maximize_button.setCheckable(True); self.maximize_button.clicked.connect(self._toggle_maximize)
        window_button_layout.addWidget(self.maximize_button)
        self.close_button = create_window_button("✕", "关闭")
        self.close_button.setProperty("id", "closeButton"); self.close_button.clicked.connect(self.parent_window.close)
        window_button_layout.addWidget(self.close_button)

        main_layout.addWidget(self.window_button_container)

        self.setLayout(main_layout)
        # Restore connection for title update
        self.parent_window.windowTitleChanged.connect(self.setWindowTitle)
        # Initial positioning of title
        self.title_label.adjustSize() # Get initial size hint

    # Visibility method (no change needed)
    def set_file_actions_visible(self, visible: bool):
        if hasattr(self, 'file_actions_container'):
             self.file_actions_container.setVisible(visible)
             self.layout().update()

    # --- Add resizeEvent for manual title positioning --- 
    def resizeEvent(self, event):
        """Manually center the title label when the title bar is resized."""
        super().resizeEvent(event)
        # --- MODIFIED: Call helper to update elided title and position --- 
        self._update_elided_title()
        # -----------------------------------------------------------------
        # if hasattr(self, 'title_label'):
        #     title_width = self.title_label.sizeHint().width()
        #     title_height = self.title_label.sizeHint().height()
        #     bar_width = self.width()
        #     bar_height = self.height()
        #     
        #     # Calculate position
        #     x = (bar_width - title_width) / 2
        #     y = (bar_height - title_height) / 2
        #     
        #     self.title_label.setGeometry(int(x), int(y), title_width, title_height)

    # --- Restore setWindowTitle --- 
    def setWindowTitle(self, title):
         if hasattr(self, 'title_label'):
             # --- UPDATED: Store full title and call update helper --- 
             self._full_title = title
             self._update_elided_title()
             # -------------------------------------------------------
             # self.title_label.setText(title) # Set the potentially long text
             # self.title_label.setToolTip(title) # Set the full text as tooltip
             # # Reposition after text change affects size hint
             # self.title_label.adjustSize()
             # self.resizeEvent(None) # Trigger repositioning logic

    # --- ADDED: Helper method to update elided title and position --- 
    def _update_elided_title(self):
        if not hasattr(self, 'title_label') or not hasattr(self, '_full_title'):
            return
        
        # Calculate available width for the title
        left_width = 0
        # Find the toggle button (assuming it's the first action button)
        toggle_button = next(iter(self.action_buttons.values()), None)
        if toggle_button:
            left_width += toggle_button.width()
        if hasattr(self, 'file_actions_container') and self.file_actions_container.isVisible():
             left_width += self.file_actions_container.width()
             
        right_width = 0
        if hasattr(self, 'window_button_container'):
             right_width += self.window_button_container.width()
             
        padding = 20 # Estimate padding/margins
        available_width = self.width() - left_width - right_width - padding
        available_width = max(10, available_width) # Ensure it's at least a small positive value
        
        # Get font metrics and elide the text
        fm = QFontMetrics(self.title_label.font()) # Use label's font
        elided_text = fm.elidedText(self._full_title, Qt.TextElideMode.ElideMiddle, available_width)
        
        # Set the text and tooltip
        self.title_label.setText(elided_text)
        self.title_label.setToolTip(self._full_title)
        
        # Adjust size and reposition
        self.title_label.adjustSize() # Adjust size based on potentially elided text
        title_width = self.title_label.width() # Use actual width after adjustSize
        title_height = self.title_label.height()
        bar_width = self.width()
        bar_height = self.height()
        x = (bar_width - title_width) / 2
        y = (bar_height - title_height) / 2
        self.title_label.setGeometry(int(x), int(y), title_width, title_height)
    # ----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        # Drag logic needs to check if clicked on background (child is None)
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and child is None:
            self._mouse_pressed = True
            self._mouse_press_pos = event.globalPosition().toPoint()
            self._window_pos_before_move = self.parent_window.pos()
            event.accept()
        else:
            if child is not None: 
                 event.ignore() # Let button handle it

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._mouse_pressed and event.buttons() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self._mouse_press_pos
            self.parent_window.move(self._window_pos_before_move + delta)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_pressed = False
            event.accept()
        else:
            event.ignore()
            
    def _toggle_maximize(self):
        # 简单直接的切换逻辑
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()

        # 立即更新图标，然后再用定时器确保状态同步
        self._update_maximize_icon(self.parent_window.windowState())

        # 使用定时器再次确保状态同步
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._update_maximize_icon(self.parent_window.windowState()))

    def _update_maximize_icon(self, state):
        # 直接检查窗口是否最大化
        is_maximized = self.parent_window.isMaximized()

        if is_maximized:
            self.maximize_button.setText(self.restore_char)
            self.maximize_button.setToolTip("向下还原")
        else:
            self.maximize_button.setText(self.maximize_char)
            self.maximize_button.setToolTip("最大化")

        # 强制刷新按钮显示
        self.maximize_button.update()

    def create_toolbar_button(self, action):
        """创建工具栏按钮"""
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(28, 28)
        return button

    def setup_toolbar(self, main_window):
        """Sets up the custom toolbar with actions from main window."""
        # Create layout for the toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(2)  # Compact spacing
        
        # Access actions from main window
        toggle_action = getattr(main_window, 'toggle_action', None)
        save_action = getattr(main_window, 'save_action', None)
        load_action = getattr(main_window, 'load_action', None)
        run_action = getattr(main_window, 'run_action', None)
        settings_action = getattr(main_window, 'global_settings_action', None)
        publish_action = getattr(main_window, 'publish_action', None)
        view_published_action = getattr(main_window, 'view_published_action', None)
        
        # Remove previous actions from their widgets (if any)
        for key, widget in self.action_widgets.items():
            if isinstance(widget, QAction):
                widget.setParent(None)
        # Clear the map
        self.action_widgets.clear()
        
        # Clear existing widgets (if any) from the toolbar layout
        while toolbar_layout.count():
            item = toolbar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Create toggle button first (always visible)
        if toggle_action:
            toggle_btn = self.create_toolbar_button(toggle_action)
            toolbar_layout.addWidget(toggle_btn)
            self.action_widgets['toggle'] = toggle_btn
        
        # --- Add a spacer between toggle and file actions ---
        horizontal_spacer = QWidget()
        horizontal_spacer.setFixedWidth(8)  # 8px spacer
        toolbar_layout.addWidget(horizontal_spacer)
        
        # Create container for file actions (can be hidden)
        self.action_container = QWidget()
        action_container_layout = QHBoxLayout(self.action_container)
        action_container_layout.setContentsMargins(0, 0, 0, 0)
        action_container_layout.setSpacing(2)
        
        # Add save, load actions to container
        if save_action:
            save_btn = self.create_toolbar_button(save_action)
            action_container_layout.addWidget(save_btn)
            self.action_widgets['save'] = save_btn
        
        if load_action:
            load_btn = self.create_toolbar_button(load_action)
            action_container_layout.addWidget(load_btn)
            self.action_widgets['load'] = load_btn
        
        # Add container to toolbar
        toolbar_layout.addWidget(self.action_container)
        # Set initial visibility based on main_window.file_actions_visible
        self.action_container.setVisible(getattr(main_window, 'file_actions_visible', True))
        
        # Add a spacer to separate action groups
        horizontal_spacer2 = QWidget()
        horizontal_spacer2.setFixedWidth(15)  # 15px spacer
        toolbar_layout.addWidget(horizontal_spacer2)
        
        # Add publish and view published tasks actions
        if publish_action:
            publish_btn = self.create_toolbar_button(publish_action)
            toolbar_layout.addWidget(publish_btn)
            self.action_widgets['publish'] = publish_btn
        
        if view_published_action:
            view_published_btn = self.create_toolbar_button(view_published_action)
            toolbar_layout.addWidget(view_published_btn)
            self.action_widgets['view_published'] = view_published_btn
            
        # Add a spacer to separate action groups
        horizontal_spacer3 = QWidget()
        horizontal_spacer3.setFixedWidth(15)  # 15px spacer
        toolbar_layout.addWidget(horizontal_spacer3)
        
        # Add run action (always visible)
        if run_action:
            run_btn = self.create_toolbar_button(run_action)
            toolbar_layout.addWidget(run_btn)
            self.action_widgets['run'] = run_btn
        
        # Add global settings action
        if settings_action:
            settings_btn = self.create_toolbar_button(settings_action)
            toolbar_layout.addWidget(settings_btn)
            self.action_widgets['settings'] = settings_btn
        
        # Add spring to push everything to the left
        toolbar_layout.addStretch(1)
        
        # Set the toolbar layout
        self.toolbar.setLayout(toolbar_layout)