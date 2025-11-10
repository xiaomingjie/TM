#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跳转规则配置对话框
允许用户自定义任务间的跳转规则
"""

import logging
from typing import Dict, List, Optional
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                               QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
                               QLabel, QMessageBox, QSpinBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from .workflow_task_manager import WorkflowTaskManager

logger = logging.getLogger(__name__)


class JumpRulesDialog(QDialog):
    """
    跳转规则配置对话框

    显示当前所有任务的跳转规则配置表格
    格式：源任务 | 成功跳转 | 失败跳转 | 无后续跳转
    """

    rules_changed = Signal()  # 规则修改信号

    def __init__(self, task_manager: WorkflowTaskManager, parent=None):
        """
        初始化对话框

        Args:
            task_manager: 任务管理器
            parent: 父窗口
        """
        super().__init__(parent)

        self.task_manager = task_manager
        self.jump_rules = {}  # {task_id: {'success': target_id, 'failed': target_id, 'no_next': target_id}}

        self._init_ui()
        self._load_rules()

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("跳转规则配置")
        self.setMinimumSize(950, 400)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # 说明文字
        info_label = QLabel("为每个任务配置执行完成后的跳转目标（不跳转请选择'无'，跳转次数0表示无限循环）")
        info_label.setStyleSheet("color: #666666; font-size: 10pt; padding: 5px;")
        layout.addWidget(info_label)

        # 跳转规则表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["源任务", "成功跳转", "失败跳转", "无后续跳转", "最大跳转次数"])

        # 设置表格样式 - 固定列宽确保一致
        header = self.table.horizontalHeader()
        column_widths = [180, 180, 180, 180, 130]  # 各列宽度
        for i, width in enumerate(column_widths):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, width)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.apply_button = QPushButton("应用")
        self.apply_button.setMinimumWidth(80)
        self.apply_button.clicked.connect(self._on_apply)

        self.close_button = QPushButton("关闭")
        self.close_button.setMinimumWidth(80)
        self.close_button.clicked.connect(self.accept)

        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def _load_rules(self):
        """加载当前跳转规则"""
        tasks = self.task_manager.get_all_tasks()

        if not tasks:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(tasks))

        # 获取所有任务名称用于下拉框
        task_names = ["无"] + [task.name for task in tasks]

        for row, task in enumerate(tasks):
            # 源任务名称（使用禁用的ComboBox确保样式一致）
            name_combo = QComboBox()
            name_combo.addItem(task.name)
            name_combo.setEnabled(False)  # 禁用，仅显示
            self.table.setCellWidget(row, 0, name_combo)

            # 从task中读取已有的跳转配置
            task_rules = getattr(task, 'jump_rules', {})

            # 成功跳转下拉框
            success_combo = QComboBox()
            success_combo.addItems(task_names)
            success_target = task_rules.get('success')
            if success_target:
                target_task = self.task_manager.get_task(success_target)
                if target_task:
                    success_combo.setCurrentText(target_task.name)
            self.table.setCellWidget(row, 1, success_combo)

            # 失败跳转下拉框
            failed_combo = QComboBox()
            failed_combo.addItems(task_names)
            failed_target = task_rules.get('failed')
            if failed_target:
                target_task = self.task_manager.get_task(failed_target)
                if target_task:
                    failed_combo.setCurrentText(target_task.name)
            self.table.setCellWidget(row, 2, failed_combo)

            # 无后续跳转下拉框
            no_next_combo = QComboBox()
            no_next_combo.addItems(task_names)
            no_next_target = task_rules.get('no_next')
            if no_next_target:
                target_task = self.task_manager.get_task(no_next_target)
                if target_task:
                    no_next_combo.setCurrentText(target_task.name)
            self.table.setCellWidget(row, 3, no_next_combo)

            # 最大跳转次数SpinBox
            max_jumps_spin = QSpinBox()
            max_jumps_spin.setRange(0, 999)  # 0表示无限循环
            max_jumps_spin.setValue(getattr(task, 'max_jump_count', 10))
            max_jumps_spin.setSpecialValueText("无限循环")  # 0时显示"无限循环"
            max_jumps_spin.setToolTip("0表示无限循环，其他数值表示最大跳转次数")
            self.table.setCellWidget(row, 4, max_jumps_spin)

    def _on_apply(self):
        """应用跳转规则"""
        try:
            tasks = self.task_manager.get_all_tasks()

            for row, task in enumerate(tasks):
                # 读取表格中的下拉框选择
                success_combo = self.table.cellWidget(row, 1)
                failed_combo = self.table.cellWidget(row, 2)
                no_next_combo = self.table.cellWidget(row, 3)
                max_jumps_spin = self.table.cellWidget(row, 4)

                # 构建跳转规则字典
                jump_rules = {}

                success_name = success_combo.currentText()
                if success_name != "无":
                    target_task = self._find_task_by_name(success_name)
                    if target_task:
                        jump_rules['success'] = target_task.task_id

                failed_name = failed_combo.currentText()
                if failed_name != "无":
                    target_task = self._find_task_by_name(failed_name)
                    if target_task:
                        jump_rules['failed'] = target_task.task_id

                no_next_name = no_next_combo.currentText()
                if no_next_name != "无":
                    target_task = self._find_task_by_name(no_next_name)
                    if target_task:
                        jump_rules['no_next'] = target_task.task_id

                # 保存到任务对象
                task.jump_rules = jump_rules
                task.max_jump_count = max_jumps_spin.value()

            logger.info("跳转规则已应用")
            self.rules_changed.emit()

            QMessageBox.information(self, "成功", "跳转规则已保存")

        except Exception as e:
            logger.error(f"应用跳转规则失败: {e}")
            QMessageBox.warning(self, "错误", f"保存跳转规则失败: {e}")

    def _find_task_by_name(self, name: str):
        """根据名称查找任务"""
        for task in self.task_manager.get_all_tasks():
            if task.name == name:
                return task
        return None
