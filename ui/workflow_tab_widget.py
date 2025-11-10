#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作流标签页控件
支持多任务标签页管理，每个标签页对应一个工作流任务
"""

import logging
import os
from typing import Dict, Optional
from PySide6.QtWidgets import (QTabWidget, QTabBar, QWidget, QPushButton,
                               QFileDialog, QMessageBox, QMenu)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QIcon, QAction

from .workflow_view import WorkflowView
from .workflow_task_manager import WorkflowTaskManager

logger = logging.getLogger(__name__)


class WorkflowTabWidget(QTabWidget):
    """
    工作流标签页控件

    特点：
    1. 支持多标签页，每个标签页显示一个工作流
    2. 标签页可关闭（带×按钮）
    3. 右键菜单（关闭、关闭其他、关闭所有、重命名）
    4. 标签页状态指示（未保存、正在运行等）
    5. 最后一个标签页固定为"+"导入按钮
    """

    # 信号定义
    workflow_imported = Signal(int)  # task_id
    workflow_closed = Signal(int)  # task_id
    workflow_renamed = Signal(int, str)  # task_id, new_name
    current_workflow_changed = Signal(int)  # task_id

    def __init__(self, task_manager: WorkflowTaskManager,
                 task_modules: dict, images_dir: str, parent=None):
        """
        初始化标签页控件

        Args:
            task_manager: 任务管理器
            task_modules: 任务模块字典
            images_dir: 图片目录
            parent: 父控件
        """
        super().__init__(parent)

        self.task_manager = task_manager
        self.task_modules = task_modules
        self.images_dir = images_dir

        # 映射：标签页索引 → 任务ID
        self.tab_to_task: Dict[int, int] = {}
        # 映射：任务ID → 标签页索引
        self.task_to_tab: Dict[int, int] = {}
        # 映射：任务ID → WorkflowView
        self.task_views: Dict[int, WorkflowView] = {}

        # 🔧 标志：是否正在删除标签页（阻止误触发导入对话框）
        self._is_removing_tab = False

        self._init_ui()
        self._connect_signals()

        logger.info("工作流标签页控件初始化完成")

    def _init_ui(self):
        """初始化UI"""
        # 设置标签页可关闭
        self.setTabsClosable(True)
        self.setMovable(True)  # 标签页可拖动排序
        self.setDocumentMode(True)  # 文档模式（更紧凑的标签栏）

        # 🔧 初始状态：没有任务时隐藏标签栏
        self.tabBar().setVisible(False)

        # 设置标签栏样式 - 增强视觉效果
        self.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
                background: white;
                top: -1px;
            }
            QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #f5f5f5, stop:1 #e0e0e0);
                border: 1px solid #b0b0b0;
                border-bottom: 1px solid #c0c0c0;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 16px;
                margin-right: 2px;
                min-width: 80px;
                color: #333333;
                font-weight: normal;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 1px solid white;
                color: #000000;
                font-weight: bold;
                margin-bottom: -1px;
            }
            QTabBar::tab:hover:!selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #ffffff, stop:1 #f0f0f0);
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
        """)

        # 添加"+"导入按钮标签页
        self._add_import_tab()

        # 启用右键菜单
        self.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)

    def _connect_signals(self):
        """连接信号"""
        # 标签页关闭信号
        self.tabCloseRequested.connect(self._on_tab_close_requested)

        # 当前标签页变化信号
        self.currentChanged.connect(self._on_current_changed)

        # 连接任务管理器信号
        self.task_manager.task_added.connect(self._on_task_added)
        self.task_manager.task_removed.connect(self._on_task_removed)
        self.task_manager.task_status_changed.connect(self._on_task_status_changed)

    def _add_import_tab(self):
        """添加"+"导入按钮标签页"""
        placeholder = QWidget()
        import_tab_index = self.addTab(placeholder, "+")

        # 设置"+"标签页不可关闭
        close_button = self.tabBar().tabButton(import_tab_index, QTabBar.ButtonPosition.RightSide)
        if close_button:
            close_button.resize(0, 0)  # 隐藏关闭按钮

    def import_workflow(self, filepath: str = None) -> Optional[int]:
        """
        导入工作流（支持批量导入）

        Args:
            filepath: 工作流文件路径（None则弹出文件选择对话框，支持多选）

        Returns:
            最后导入的任务ID，失败返回None
        """
        logger.info("📂 import_workflow() 开始执行")
        logger.info(f"   传入参数 filepath={filepath}")

        # 如果没有指定文件路径，弹出文件选择对话框（支持多选）
        if not filepath:
            logger.info("   filepath为空，准备打开文件选择对话框（多选）...")
            logger.info(f"   self={self}")
            logger.info(f"   self.parent()={self.parent()}")
            logger.info(f"   self.isVisible()={self.isVisible()}")
            logger.info(f"   self.isEnabled()={self.isEnabled()}")

            try:
                logger.info("   正在调用 QFileDialog.getOpenFileNames()...")

                # 🔧 尝试使用主窗口作为父控件，而不是self（TabWidget）
                from PySide6.QtWidgets import QApplication
                main_window = QApplication.activeWindow()
                if main_window:
                    logger.info(f"   使用主窗口作为父控件: {main_window}")
                    parent_widget = main_window
                else:
                    logger.info(f"   使用self作为父控件")
                    parent_widget = self

                # 🔧 改用 getOpenFileNames 支持多选
                filepaths, _ = QFileDialog.getOpenFileNames(
                    parent_widget,
                    "导入工作流（可多选）",
                    ".",
                    "JSON文件 (*.json);;所有文件 (*)"
                )
                logger.info(f"   QFileDialog.getOpenFileNames() 返回: {len(filepaths)} 个文件")
            except Exception as e:
                logger.error(f"   QFileDialog.getOpenFileNames() 抛出异常: {e}", exc_info=True)
                return None

            if not filepaths:
                logger.info("   filepaths为空，用户取消或未选择文件")
                return None  # 用户取消

            # 批量导入多个文件
            last_task_id = None
            success_count = 0
            error_files = []

            for filepath in filepaths:
                task_id = self._import_single_workflow(filepath)
                if task_id is not None:
                    last_task_id = task_id
                    success_count += 1
                else:
                    error_files.append(os.path.basename(filepath))

            # 显示导入结果
            if success_count > 0:
                if len(error_files) > 0:
                    QMessageBox.warning(
                        self,
                        "部分导入成功",
                        f"成功导入 {success_count} 个工作流\n\n失败文件：\n" + "\n".join(error_files)
                    )
                else:
                    QMessageBox.information(
                        self,
                        "导入成功",
                        f"成功导入 {success_count} 个工作流"
                    )

            return last_task_id

        else:
            # 单个文件导入
            return self._import_single_workflow(filepath)

    def _import_single_workflow(self, filepath: str) -> Optional[int]:
        """
        导入单个工作流文件

        Args:
            filepath: 工作流文件路径

        Returns:
            新任务的ID，失败返回None
        """

        # 检查文件是否存在
        if not os.path.exists(filepath):
            QMessageBox.critical(self, "导入失败", f"文件不存在: {filepath}")
            return None

        try:
            # 加载工作流数据
            import json
            with open(filepath, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)

            # 验证数据格式
            if 'cards' not in workflow_data or not isinstance(workflow_data.get('cards'), list):
                QMessageBox.critical(self, "导入失败", "无效的工作流文件格式")
                return None

            # 生成任务名称
            name = os.path.basename(filepath)

            # 添加任务到管理器
            task_id = self.task_manager.add_task(name, filepath, workflow_data)

            logger.info(f"工作流导入成功: {filepath}")
            self.workflow_imported.emit(task_id)

            return task_id

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "导入失败", f"无法解析文件:\n{e}")
            return None
        except Exception as e:
            logger.error(f"导入工作流失败: {e}", exc_info=True)
            QMessageBox.critical(self, "导入失败", f"导入失败:\n{e}")
            return None

    def create_blank_workflow(self, name: str = None) -> Optional[int]:
        """
        创建空白工作流

        Args:
            name: 工作流名称（None则使用默认名称）

        Returns:
            新任务的ID，失败返回None
        """
        try:
            # 如果没有提供名称，使用默认名称
            if not name:
                # 生成默认名称：未命名工作流1, 未命名工作流2, ...
                count = 1
                while True:
                    name = f"未命名工作流{count}"
                    # 检查是否已存在同名任务
                    exists = False
                    for task in self.task_manager.get_all_tasks():
                        if task.name == name or task.name == f"{name}.json":
                            exists = True
                            break
                    if not exists:
                        break
                    count += 1

            # 创建空白工作流数据
            workflow_data = {
                'cards': [],
                'connections': [],
                'metadata': {
                    'created': 'blank',
                    'version': '1.0'
                }
            }

            # 添加任务到管理器（filepath为空字符串表示未保存）
            task_id = self.task_manager.add_task(name, '', workflow_data)

            logger.info(f"空白工作流创建成功: {name}")
            self.workflow_imported.emit(task_id)

            return task_id

        except Exception as e:
            logger.error(f"创建空白工作流失败: {e}", exc_info=True)
            QMessageBox.critical(self, "创建失败", f"创建空白工作流失败:\n{e}")
            return None

    def _on_task_added(self, task_id: int):
        """任务添加回调"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        # 🔧 如果是第一个任务，显示标签栏
        if len(self.task_views) == 0:
            logger.info("添加第一个任务，显示标签栏")
            self.tabBar().setVisible(True)

        # 创建WorkflowView
        workflow_view = WorkflowView(
            task_modules=self.task_modules,
            images_dir=self.images_dir,
            parent=self
        )

        # 🔧 强制初始化WorkflowView的交互属性
        from PySide6.QtWidgets import QGraphicsView
        from PySide6.QtCore import Qt

        workflow_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        workflow_view.setInteractive(True)
        workflow_view.setEnabled(True)
        workflow_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        workflow_view.viewport().setMouseTracking(True)

        logger.info(f"🎨 WorkflowView创建完成:")
        logger.info(f"   dragMode: {workflow_view.dragMode()}")
        logger.info(f"   interactive: {workflow_view.isInteractive()}")
        logger.info(f"   enabled: {workflow_view.isEnabled()}")
        logger.info(f"   focusPolicy: {workflow_view.focusPolicy()}")

        # 加载工作流数据
        workflow_view.load_workflow(task.workflow_data)

        # 🔧 加载后再次确保拖拽模式正确（加载可能会改变设置）
        workflow_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        logger.info(f"   加载后dragMode: {workflow_view.dragMode()}")

        # 连接WorkflowView的信号，标记任务为已修改
        workflow_view.card_added.connect(lambda: self._mark_task_modified(task_id))
        workflow_view.card_deleted.connect(lambda: self._mark_task_modified(task_id))
        workflow_view.connection_added.connect(lambda: self._mark_task_modified(task_id))
        workflow_view.connection_deleted.connect(lambda: self._mark_task_modified(task_id))
        workflow_view.card_moved.connect(lambda: self._mark_task_modified(task_id))

        # 插入标签页（在"+"之前）
        insert_index = self.count() - 1  # "+"标签页的索引
        tab_index = self.insertTab(insert_index, workflow_view, task.name)

        # 🔧 设置自定义关闭按钮（带X图标）
        self._set_custom_close_button(tab_index)

        logger.info(f"📝 标签页插入: insert_index={insert_index}, 返回tab_index={tab_index}")

        # 🔧 关键修复：insertTab后需要重建映射，因为所有索引都可能改变
        # 先将新view记录到task_views
        self.task_views[task_id] = workflow_view

        # 重建所有映射关系
        self._rebuild_mappings()

        logger.info(f"📊 映射关系重建完成:")
        logger.info(f"   tab_to_task: {self.tab_to_task}")
        logger.info(f"   task_to_tab: {self.task_to_tab}")

        # 切换到新标签页
        self.setCurrentIndex(tab_index)

        # 更新标签页状态
        self._update_tab_status(task_id)

        logger.debug(f"标签页已添加: task_id={task_id}, tab_index={tab_index}, name='{task.name}'")

    def _set_custom_close_button(self, tab_index: int):
        """为标签页设置自定义关闭按钮"""
        close_button = QPushButton("×")
        close_button.setFixedSize(16, 16)
        close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #666;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background: #e81123;
                color: white;
                border-radius: 2px;
            }
        """)
        # 🔧 使用property存储初始的tab_index，点击时动态查找正确的索引
        close_button.setProperty("initial_tab_index", tab_index)
        close_button.clicked.connect(self._on_close_button_clicked)
        self.tabBar().setTabButton(tab_index, QTabBar.ButtonPosition.RightSide, close_button)

    def _on_close_button_clicked(self):
        """关闭按钮点击处理"""
        sender_button = self.sender()
        if not sender_button:
            return

        # 遍历所有标签页，找到这个按钮对应的标签页
        for i in range(self.count()):
            button = self.tabBar().tabButton(i, QTabBar.ButtonPosition.RightSide)
            if button == sender_button:
                self._on_tab_close_requested(i)
                return

    def _on_task_removed(self, task_id: int):
        """任务删除回调"""
        if task_id not in self.task_to_tab:
            logger.warning(f"尝试删除不存在的任务: task_id={task_id}")
            return

        tab_index = self.task_to_tab[task_id]
        logger.info(f"删除任务标签页: task_id={task_id}, tab_index={tab_index}")

        # 🔧 计算删除后应该切换到的索引
        # 优先选择右边的标签，如果没有右边的就选左边的
        next_index = tab_index  # 默认位置
        if tab_index < self.count() - 2:  # 右边还有其他任务标签（不包括"+"标签）
            next_index = tab_index  # 删除后，右边的标签会移到当前位置
            logger.debug(f"删除后将切换到右边的标签（删除后的索引: {next_index}）")
        elif tab_index > 0:  # 左边有其他任务标签
            next_index = tab_index - 1  # 切换到左边的标签
            logger.debug(f"删除后将切换到左边的标签（索引: {next_index}）")
        else:  # 只有一个标签
            next_index = -1  # 标记为无效
            logger.debug("这是最后一个标签，删除后将没有任务")

        # 先从task_views中删除
        if task_id in self.task_views:
            del self.task_views[task_id]
            logger.debug(f"已从task_views删除: task_id={task_id}")

        # 🔧 设置标志，防止removeTab触发currentChanged时误触发导入对话框
        self._is_removing_tab = True
        try:
            # 移除标签页（这会改变所有后续标签的索引）
            self.removeTab(tab_index)
            logger.debug(f"已移除标签页: index={tab_index}")
        finally:
            # 确保标志被重置
            self._is_removing_tab = False

        # 🔧 关键：直接重建映射，不要手动删除（因为索引已经变化）
        self._rebuild_mappings()
        logger.debug(f"映射关系已重建")

        # 🔧 删除后切换到合适的标签页
        if len(self.task_views) > 0 and next_index >= 0:
            # 确保next_index有效
            if next_index >= self.count() - 1:
                next_index = self.count() - 2  # 最后一个任务标签

            logger.info(f"删除后切换到标签页: index={next_index}")
            self.setCurrentIndex(next_index)
            self._previous_valid_index = next_index
        else:
            # 没有任务了，重置为-1（表示无效）
            self._previous_valid_index = -1
            logger.debug("没有任务了，重置 _previous_valid_index = -1")

        # 🔧 如果没有任务了，隐藏标签栏
        if len(self.task_views) == 0:
            logger.info("所有任务已关闭，隐藏标签栏")
            self.tabBar().setVisible(False)

        logger.debug(f"标签页已删除: task_id={task_id}")

    def _on_task_status_changed(self, task_id: int, status: str):
        """任务状态变化回调"""
        self._update_tab_status(task_id)

    def _on_tab_close_requested(self, index: int):
        """标签页关闭请求"""
        # "+"标签页不可关闭
        if index == self.count() - 1:
            return

        if index not in self.tab_to_task:
            return

        task_id = self.tab_to_task[index]
        task = self.task_manager.get_task(task_id)

        if not task:
            return

        # 检查任务是否正在运行
        if task.status == 'running':
            reply = QMessageBox.question(
                self,
                "确认关闭",
                f"任务 '{task.name}' 正在运行，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                return

            # 停止任务
            task.stop()

        # 检查是否有未保存的更改
        if task.modified:
            reply = QMessageBox.question(
                self,
                "保存更改",
                f"任务 '{task.name}' 有未保存的更改，是否保存？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                # 更新工作流数据
                if task_id in self.task_views:
                    workflow_view = self.task_views[task_id]
                    workflow_data = workflow_view.serialize_workflow()
                    task.update_workflow_data(workflow_data)

                # 🔧 如果任务没有文件路径（新建的空白工作流），使用另存为
                if not task.filepath:
                    self._save_task_as(task_id)
                    # 检查是否保存成功（用户可能取消）
                    if not task.filepath:
                        logger.info("用户取消了另存为，不关闭标签页")
                        return
                else:
                    if not task.save():
                        QMessageBox.warning(self, "保存失败", f"无法保存任务 '{task.name}'")
                        return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        # 删除任务
        self.task_manager.remove_task(task_id)
        self.workflow_closed.emit(task_id)

    def _on_current_changed(self, index: int):
        """当前标签页变化"""
        logger.info(f"🔔 标签页变化事件触发: index={index}, count={self.count()}")

        # 🔧 如果正在删除标签页，不处理（避免误触发导入对话框）
        if self._is_removing_tab:
            logger.info("   正在删除标签页，跳过处理")
            return

        # 点击"+"标签页，导入工作流
        if index == self.count() - 1:
            logger.info(f"✅ 确认点击了 '+' 导入按钮 (index={index})")

            # 保存之前的索引
            previous_index = getattr(self, '_previous_valid_index', 0)
            logger.info(f"   之前的标签页索引: {previous_index}")

            # 导入工作流
            logger.info("   正在调用 import_workflow()...")
            task_id = self.import_workflow()
            logger.info(f"   import_workflow() 返回: task_id={task_id}")

            # 如果导入失败（用户取消或出错），切换回之前的标签页
            if task_id is None:
                logger.info("   用户取消导入或导入失败，切换回之前的标签页")
                # 🔧 检查previous_index是否有效
                if previous_index >= 0 and previous_index < self.count() - 1:
                    logger.info(f"   切换回索引 {previous_index}")
                    self.setCurrentIndex(previous_index)
                elif self.count() > 1:
                    # 如果之前没有有效索引，但现在有任务，切换到第一个
                    logger.info("   切换到第一个标签页 (index=0)")
                    self.setCurrentIndex(0)
                # else: 没有任何任务标签，保持在"+"标签（但标签栏是隐藏的）
            else:
                logger.info(f"   导入成功！task_id={task_id}")
            # else: 导入成功，_on_task_added 会自动切换到新标签页

            return

        # 保存当前有效的标签页索引（非"+"标签页）
        self._previous_valid_index = index
        logger.debug(f"保存当前有效索引: {index}")

        # 发送当前工作流变化信号
        if index in self.tab_to_task:
            task_id = self.tab_to_task[index]
            logger.debug(f"切换到任务: task_id={task_id}")
            self.current_workflow_changed.emit(task_id)
        else:
            logger.debug(f"索引 {index} 不在 tab_to_task 映射中")

    def _show_tab_context_menu(self, pos: QPoint):
        """显示标签页右键菜单"""
        tab_index = self.tabBar().tabAt(pos)

        # "+"标签页不显示菜单
        if tab_index == self.count() - 1 or tab_index not in self.tab_to_task:
            return

        task_id = self.tab_to_task[tab_index]
        task = self.task_manager.get_task(task_id)

        if not task:
            return

        # 创建右键菜单
        menu = QMenu(self)

        # 保存（无图标）
        save_action = menu.addAction("保存")
        save_action.setEnabled(task.modified)
        save_action.triggered.connect(lambda: self._save_task(task_id))

        # 另存为（无图标）
        save_as_action = menu.addAction("另存为...")
        save_as_action.triggered.connect(lambda: self._save_task_as(task_id))

        # 重命名（无图标）
        rename_action = menu.addAction("重命名")
        rename_action.triggered.connect(lambda: self._rename_task(task_id))

        # 关闭（无图标）
        close_action = menu.addAction("关闭")
        close_action.triggered.connect(lambda: self._on_tab_close_requested(tab_index))

        # 关闭所有（无图标）
        close_all_action = menu.addAction("关闭所有")
        close_all_action.triggered.connect(self._close_all_tabs)

        # 显示菜单
        menu.exec(self.tabBar().mapToGlobal(pos))

    def _mark_task_modified(self, task_id: int):
        """标记任务为已修改"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        # 获取当前WorkflowView的数据
        if task_id in self.task_views:
            workflow_view = self.task_views[task_id]
            # 🔧 使用 serialize_workflow() 而不是 save_workflow(filepath)
            workflow_data = workflow_view.serialize_workflow()
            task.update_workflow_data(workflow_data)

        self._update_tab_status(task_id)

    def _update_tab_status(self, task_id: int):
        """更新标签页状态显示"""
        if task_id not in self.task_to_tab:
            return

        tab_index = self.task_to_tab[task_id]
        task = self.task_manager.get_task(task_id)

        if not task:
            return

        # 构建标签页文本
        name = task.name

        # 去掉文件后缀（如 .json）
        if '.' in name:
            name = os.path.splitext(name)[0]

        # 添加修改标记
        modified_mark = '*' if task.modified else ''

        # 设置标签页文本（不使用图标和颜色）
        tab_text = f"{name}{modified_mark}"
        self.setTabText(tab_index, tab_text)

        # 设置标签页工具提示
        tooltip = f"任务: {task.name}\n路径: {task.filepath}\n状态: {task.status}"
        self.setTabToolTip(tab_index, tooltip)

    def _save_task(self, task_id: int):
        """保存任务"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        # 更新任务的工作流数据
        if task_id in self.task_views:
            workflow_view = self.task_views[task_id]
            # 🔧 使用 serialize_workflow() 而不是 save_workflow(filepath)
            workflow_data = workflow_view.serialize_workflow()
            task.update_workflow_data(workflow_data)

        # 🔧 如果任务没有文件路径（新建的空白工作流），使用另存为
        if not task.filepath:
            logger.info(f"任务 '{task.name}' 没有保存路径，使用另存为")
            self._save_task_as(task_id)
            return

        # 保存到文件
        if task.save():
            QMessageBox.information(self, "保存成功", f"任务 '{task.name}' 已保存")
            self._update_tab_status(task_id)
        else:
            QMessageBox.warning(self, "保存失败", f"无法保存任务 '{task.name}'")

    def _save_task_as(self, task_id: int):
        """任务另存为"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        # 更新任务的工作流数据
        if task_id in self.task_views:
            workflow_view = self.task_views[task_id]
            # 🔧 使用 serialize_workflow() 而不是 save_workflow(filepath)
            workflow_data = workflow_view.serialize_workflow()
            task.update_workflow_data(workflow_data)

        # 选择保存路径
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "另存为",
            task.filepath,
            "工作流文件 (*.json);;所有文件 (*)"
        )

        if not filepath:
            return

        # 更新任务文件路径
        task.filepath = filepath
        task.name = os.path.basename(filepath)

        # 保存到文件
        if task.save():
            QMessageBox.information(self, "保存成功", f"任务已另存为: {filepath}")
            self._update_tab_status(task_id)
        else:
            QMessageBox.warning(self, "保存失败", f"无法保存到: {filepath}")

    def _rename_task(self, task_id: int):
        """重命名任务"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return

        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(
            self,
            "重命名任务",
            "请输入新名称:",
            text=task.name
        )

        if ok and new_name and new_name != task.name:
            task.name = new_name
            self._update_tab_status(task_id)
            self.workflow_renamed.emit(task_id, new_name)
            logger.info(f"任务已重命名: {task_id} -> '{new_name}'")

    def _close_other_tabs(self, keep_index: int):
        """关闭除指定索引外的所有标签页"""
        # 从后往前关闭（避免索引变化）
        for i in range(self.count() - 2, -1, -1):  # 不包括"+"标签页
            if i != keep_index:
                self._on_tab_close_requested(i)

    def _close_all_tabs(self):
        """关闭所有标签页"""
        # 从后往前关闭（避免索引变化）
        for i in range(self.count() - 2, -1, -1):  # 不包括"+"标签页
            self._on_tab_close_requested(i)

    def _rebuild_mappings(self):
        """重新建立映射关系（标签页索引可能变化）"""
        self.tab_to_task.clear()
        self.task_to_tab.clear()

        for i in range(self.count() - 1):  # 不包括"+"标签页
            widget = self.widget(i)
            # 通过widget找到对应的task_id
            for task_id, view in self.task_views.items():
                if view == widget:
                    self.tab_to_task[i] = task_id
                    self.task_to_tab[task_id] = i
                    break

    def get_current_task_id(self) -> Optional[int]:
        """获取当前选中的任务ID"""
        index = self.currentIndex()
        return self.tab_to_task.get(index)

    def get_current_workflow_view(self) -> Optional[WorkflowView]:
        """获取当前选中的WorkflowView"""
        task_id = self.get_current_task_id()
        if task_id:
            return self.task_views.get(task_id)
        return None

    def has_unsaved_changes(self) -> bool:
        """检查是否有未保存的更改"""
        for task in self.task_manager.get_all_tasks():
            if task.modified:
                return True
        return False
