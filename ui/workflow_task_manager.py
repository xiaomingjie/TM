#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作流任务管理器
负责管理多个工作流任务的创建、执行、删除等操作
"""

import logging
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal

from .workflow_task import WorkflowTask

logger = logging.getLogger(__name__)


class WorkflowTaskManager(QObject):
    """工作流任务管理器"""

    # 信号定义
    task_added = Signal(int)  # task_id
    task_removed = Signal(int)  # task_id
    task_status_changed = Signal(int, str)  # task_id, status
    all_tasks_completed = Signal(bool)  # success

    def __init__(self, task_modules: Dict[str, Any], images_dir: str, config: dict, parent=None):
        """
        初始化任务管理器

        Args:
            task_modules: 任务模块字典
            images_dir: 图片目录
            config: 全局配置
            parent: 父对象
        """
        super().__init__(parent)

        self.task_modules = task_modules
        self.images_dir = images_dir
        self.config = config

        self.tasks: Dict[int, WorkflowTask] = {}  # {task_id: WorkflowTask}
        self.next_task_id = 1

        # 执行模式（从配置中读取）
        self.execution_mode = config.get('task_execution_mode', 'sync')  # 'sync' (串行) 或 'async' (并行)

        # 当前执行状态
        self._is_executing = False
        self._executing_task_ids: List[int] = []

        # 🔧 跳转配置
        self.jump_enabled = True  # 全局跳转开关
        self.max_jump_depth = 10  # 最大跳转深度（防止无限循环）
        self._current_jump_depth = 0  # 当前跳转深度

        logger.info("工作流任务管理器初始化完成")

    def add_task(self, name: str, filepath: str, workflow_data: dict) -> int:
        """
        添加新任务

        Args:
            name: 任务名称
            filepath: 任务文件路径
            workflow_data: 工作流数据

        Returns:
            新任务的ID
        """
        task_id = self.next_task_id
        self.next_task_id += 1

        # 创建任务对象
        task = WorkflowTask(
            task_id=task_id,
            name=name,
            filepath=filepath,
            workflow_data=workflow_data,
            task_modules=self.task_modules,
            images_dir=self.images_dir,
            config=self.config,
            parent=self
        )

        # 连接任务信号
        task.status_changed.connect(lambda status: self._on_task_status_changed(task_id, status))

        # 添加到管理器
        self.tasks[task_id] = task
        self.task_added.emit(task_id)

        logger.info(f"添加任务成功: ID={task_id}, 名称='{name}'")
        return task_id

    def remove_task(self, task_id: int) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        if task_id not in self.tasks:
            logger.warning(f"删除任务失败: 任务ID {task_id} 不存在")
            return False

        task = self.tasks[task_id]

        # 如果任务正在运行，先停止
        if task.status == 'running':
            logger.info(f"任务 {task_id} 正在运行，先停止")
            task.stop()

        # 删除任务
        del self.tasks[task_id]
        self.task_removed.emit(task_id)

        logger.info(f"删除任务成功: ID={task_id}, 名称='{task.name}'")
        return True

    def get_task(self, task_id: int) -> Optional[WorkflowTask]:
        """获取任务对象"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[WorkflowTask]:
        """获取所有任务列表（按ID排序）"""
        return [self.tasks[tid] for tid in sorted(self.tasks.keys())]

    def get_enabled_tasks(self) -> List[WorkflowTask]:
        """获取所有启用的任务"""
        return [task for task in self.get_all_tasks() if task.enabled]

    def get_executable_tasks(self) -> List[WorkflowTask]:
        """获取所有可执行的任务"""
        return [task for task in self.get_all_tasks() if task.can_execute()]

    def set_execution_mode(self, mode: str):
        """
        设置执行模式

        Args:
            mode: 'sync' (同步/串行) 或 'async' (异步/并行)
        """
        if mode not in ['sync', 'async']:
            logger.error(f"无效的执行模式: {mode}")
            return

        self.execution_mode = mode
        logger.info(f"执行模式已设置为: {'同步（串行）' if mode == 'sync' else '异步（并行）'}")

    def execute_all(self) -> bool:
        """
        执行所有可执行的任务

        Returns:
            是否成功启动执行
        """
        if self._is_executing:
            logger.warning("已有任务正在执行中")
            return False

        executable_tasks = self.get_executable_tasks()

        if not executable_tasks:
            logger.warning("没有可执行的任务")
            return False

        logger.info(f"开始执行 {len(executable_tasks)} 个任务，模式: {self.execution_mode}")

        self._is_executing = True
        self._executing_task_ids = [task.task_id for task in executable_tasks]

        if self.execution_mode == 'sync':
            return self._execute_sync(executable_tasks)
        else:
            return self._execute_async(executable_tasks)

    def _execute_sync(self, tasks: List[WorkflowTask]) -> bool:
        """
        同步执行任务列表（串行）

        Args:
            tasks: 任务列表

        Returns:
            是否全部成功
        """
        logger.info(f"开始同步（串行）执行 {len(tasks)} 个任务")

        all_success = True

        for i, task in enumerate(tasks, 1):
            logger.info(f"执行任务 {i}/{len(tasks)}: {task.name}")

            success = task.execute_sync()

            if not success:
                logger.error(f"任务 '{task.name}' 执行失败，停止后续任务")
                all_success = False
                break

        self._is_executing = False
        self._executing_task_ids = []
        self.all_tasks_completed.emit(all_success)

        logger.info(f"同步执行完成，结果: {'成功' if all_success else '失败'}")
        return all_success

    def _execute_async(self, tasks: List[WorkflowTask]) -> bool:
        """
        异步执行任务列表（并行）

        Args:
            tasks: 任务列表

        Returns:
            是否全部启动成功
        """
        logger.info(f"开始异步（并行）执行 {len(tasks)} 个任务")

        started_count = 0

        for task in tasks:
            thread = task.execute_async()
            if thread:
                started_count += 1
                logger.info(f"任务 '{task.name}' 已启动")
            else:
                logger.error(f"任务 '{task.name}' 启动失败")

        logger.info(f"异步执行：{started_count}/{len(tasks)} 个任务已启动")

        # 异步模式下，不立即设置 _is_executing = False
        # 等待所有任务完成后再重置（通过 _on_task_status_changed 检测）

        return started_count > 0

    def execute_task(self, task_id: int) -> bool:
        """
        执行单个任务

        Args:
            task_id: 任务ID

        Returns:
            是否执行成功
        """
        task = self.get_task(task_id)
        if not task:
            logger.error(f"执行失败: 任务ID {task_id} 不存在")
            return False

        if not task.can_execute():
            logger.warning(f"任务 '{task.name}' 当前状态不允许执行")
            return False

        logger.info(f"开始执行单个任务: {task.name}")

        # 单个任务执行使用异步模式
        thread = task.execute_async()
        return thread is not None

    def stop_task(self, task_id: int):
        """停止单个任务"""
        task = self.get_task(task_id)
        if task:
            task.stop()

    def stop_all(self):
        """停止所有正在运行的任务"""
        logger.info("停止所有正在运行的任务")

        stopped_count = 0
        for task in self.get_all_tasks():
            if task.status == 'running':
                task.stop()
                stopped_count += 1

        self._is_executing = False
        self._executing_task_ids = []

        logger.info(f"已停止 {stopped_count} 个任务")

    def save_task(self, task_id: int) -> bool:
        """保存任务到文件"""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"保存失败: 任务ID {task_id} 不存在")
            return False

        return task.save()

    def save_all_modified(self) -> int:
        """
        保存所有已修改的任务

        Returns:
            保存成功的任务数量
        """
        saved_count = 0

        for task in self.get_all_tasks():
            if task.modified:
                if task.save():
                    saved_count += 1

        logger.info(f"已保存 {saved_count} 个已修改的任务")
        return saved_count

    def _on_task_status_changed(self, task_id: int, status: str):
        """任务状态变化回调"""
        self.task_status_changed.emit(task_id, status)

        # 检查是否所有异步任务都已完成
        if self.execution_mode == 'async' and self._is_executing:
            all_completed = all(
                self.tasks[tid].status in ['completed', 'failed', 'stopped']
                for tid in self._executing_task_ids
                if tid in self.tasks
            )

            if all_completed:
                # 所有异步任务都已完成
                all_success = all(
                    self.tasks[tid].status == 'completed'
                    for tid in self._executing_task_ids
                    if tid in self.tasks
                )

                self._is_executing = False
                self._executing_task_ids = []
                self.all_tasks_completed.emit(all_success)

                logger.info(f"所有异步任务执行完成，结果: {'成功' if all_success else '失败'}")

    def clear_all(self):
        """清空所有任务"""
        logger.info("清空所有任务")

        # 停止所有运行中的任务
        self.stop_all()

        # 清空任务列表
        task_ids = list(self.tasks.keys())
        for task_id in task_ids:
            self.remove_task(task_id)

        logger.info("所有任务已清空")

    def get_task_count(self) -> int:
        """获取任务数量"""
        return len(self.tasks)

    def get_running_count(self) -> int:
        """获取正在运行的任务数量"""
        return sum(1 for task in self.get_all_tasks() if task.status == 'running')

    def find_jump_target(self, source_task: WorkflowTask) -> Optional[int]:
        """
        查找跳转目标任务

        Args:
            source_task: 源任务

        Returns:
            目标任务ID，如果没有找到则返回None
        """
        if not source_task.stop_reason:
            return None

        # 从任务的jump_rules中查找目标
        jump_rules = getattr(source_task, 'jump_rules', {})
        target_id = jump_rules.get(source_task.stop_reason)

        if target_id:
            # 验证目标任务是否存在
            if target_id in self.tasks:
                logger.info(f"找到跳转目标: {source_task.name} ({source_task.stop_reason}) -> task_id={target_id}")
                return target_id
            else:
                logger.warning(f"跳转目标任务 {target_id} 不存在")

        logger.info(f"未配置跳转: {source_task.name} ({source_task.stop_reason})")
        return None

    def __repr__(self):
        return f"<WorkflowTaskManager tasks={len(self.tasks)} mode={self.execution_mode}>"
