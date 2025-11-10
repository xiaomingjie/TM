# -*- coding: utf-8 -*-
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt

class SelectTaskDialog(QDialog):
    """A custom dialog for selecting a task type with modern styling."""
    def __init__(self, task_types: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择任务类型")
        self.setMinimumWidth(350)

        self._selected_task_type: Optional[str] = None

        # --- Layouts --- 
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # --- Widgets --- 
        self.info_label = QLabel("请选择要添加的任务类型:")
        self.info_label.setObjectName("infoLabel")

        self.combo_box = QComboBox()
        self.combo_box.setObjectName("taskComboBox")
        self.combo_box.addItems(task_types)
        self.combo_box.setMinimumHeight(30)

        self.ok_button = QPushButton("确定") # Use Chinese
        self.ok_button.setObjectName("okButton")
        self.ok_button.setDefault(True)
        self.ok_button.setMinimumHeight(30)

        self.cancel_button = QPushButton("取消") # Use Chinese
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setMinimumHeight(30)

        # --- Assemble Layout --- 
        self.main_layout.addWidget(self.info_label)
        self.main_layout.addWidget(self.combo_box)
        self.main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch(1)
        self.main_layout.addLayout(button_layout)

        # --- Styling --- 
        # (Keep the previous modern stylesheet)
        self.setStyleSheet("""
            QDialog {
                background-color: #FDFDFD;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QLabel#infoLabel {
                font-size: 14px;
                color: #444;
            }
            QComboBox#taskComboBox {
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 5px 10px;
                background-color: white;
                font-size: 13px;
                color: #333;
            }
            QComboBox#taskComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #D0D0D0;
                border-left-style: solid; 
                border-top-right-radius: 3px; 
                border-bottom-right-radius: 3px;
            }
             QComboBox#taskComboBox::down-arrow {
                 width: 10px;
                 height: 10px;
            }
            QComboBox#taskComboBox QAbstractItemView {
                 border: 1px solid #D0D0D0;
                 background-color: white;
                 selection-background-color: #E0E0E0;
                 color: #333;
                 padding: 4px;
             }
            QPushButton#okButton {
                background-color: #007AFF;
                color: white;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 8px 25px;
            }
            QPushButton#okButton:hover {
                background-color: #005ECB;
            }
            QPushButton#okButton:pressed {
                background-color: #004BAA;
            }
            QPushButton#cancelButton {
                background-color: #EAEAEA;
                color: #444;
                font-size: 13px;
                border: 1px solid #D0D0D0;
                border-radius: 5px;
                padding: 8px 20px;
            }
             QPushButton#cancelButton:hover {
                background-color: #DCDCDC;
            }
             QPushButton#cancelButton:pressed {
                background-color: #C8C8C8;
            }
        """)

        # --- Connections --- 
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def selected_task_type(self) -> Optional[str]:
        """Returns the currently selected task type in the combo box."""
        return self.combo_box.currentText()