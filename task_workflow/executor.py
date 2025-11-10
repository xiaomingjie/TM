"""
工作流执行器模块
"""
import logging
import time
import win32gui
from typing import Dict, List, Any, Optional
from PySide6.QtCore import QObject, Signal, QThread

# 导入任务模块
from tasks import TASK_MODULES

logger = logging.getLogger(__name__)


class WorkflowExecutor(QObject):
    """工作流执行器类"""

    # 信号定义 - 与 main_window.py 中期望的信号保持一致
    execution_started = Signal()
    execution_finished = Signal(str)  # status_message
    card_executing = Signal(int)  # card_id
    card_finished = Signal(int, bool)  # card_id, success
    error_occurred = Signal(int, str)  # card_id, error_message
    path_updated = Signal(int, str, str)  # card_id, param_name, new_path
    path_resolution_failed = Signal(int, str)  # card_id, original_path
    step_details = Signal(str)  # step_details
    
    def __init__(self, cards_data: Dict[str, Any], connections_data: List[Dict[str, Any]],
                 task_modules: Dict[str, Any], target_window_title: str = None,
                 execution_mode: str = 'foreground', start_card_id: str = None,
                 images_dir: str = None, target_hwnd: int = None, parent=None):
        """
        初始化工作流执行器

        Args:
            cards_data: 卡片数据字典
            connections_data: 连接数据列表
            task_modules: 任务模块字典
            target_window_title: 目标窗口标题
            execution_mode: 执行模式 ('foreground' 或 'background')
            start_card_id: 起始卡片ID
            images_dir: 图片目录
            target_hwnd: 目标窗口句柄
            parent: 父对象
        """
        super().__init__(parent)

        self.cards_data = cards_data
        self.connections_data = connections_data
        self.task_modules = task_modules
        self.target_hwnd = target_hwnd  # 目标窗口句柄（主要使用）
        self.target_window_title = target_window_title  # 窗口标题（仅用于日志显示）
        self.execution_mode = execution_mode
        self.start_card_id = start_card_id
        self.images_dir = images_dir

        self._stop_requested = False
        self._is_running = False
        self._current_card_id = None

        # 工具 修复：添加持久计数器字典
        self._persistent_counters = {}

        # 创建连接映射以便查找下一个卡片
        self._connections_map = self._build_connections_map()

        logger.info(f"WorkflowExecutor 初始化完成，起始卡片ID: {start_card_id}")

    def _build_connections_map(self) -> Dict[int, List[Dict[str, Any]]]:
        """构建连接映射，方便查找下一个卡片"""
        connections_map = {}
        for connection in self.connections_data:
            start_id = connection.get('start_card_id')
            if start_id not in connections_map:
                connections_map[start_id] = []
            connections_map[start_id].append(connection)
        return connections_map
    
    def run(self):
        """主执行方法，在线程中运行"""
        if self._is_running:
            logger.warning("工作流已在运行中")
            return

        self._is_running = True
        self._stop_requested = False

        # 重置全局停止标志 - 已删除有问题的导入
        logger.debug("工作流执行器启动，跳过InputPlayer全局停止标志重置")

        # 工具 修复：不在WorkflowExecutor中设置环境变量，避免与多窗口执行器冲突
        # 环境变量应该由调用方（单窗口执行器或多窗口执行器）负责设置
        logger.info(f"WorkflowExecutor启动: 窗口='{self.target_window_title}', 模式={self.execution_mode}, HWND={self.target_hwnd}")

        logger.info("开始执行工作流")

        # 在前台模式下激活目标窗口
        # 标准化执行模式以支持新的6种模式
        normalized_mode = self.execution_mode
        if self.execution_mode.startswith('foreground'):
            normalized_mode = 'foreground'
        elif self.execution_mode.startswith('background'):
            normalized_mode = 'background'
        elif self.execution_mode == 'emulator_adb':
            normalized_mode = 'emulator'

        if normalized_mode == 'foreground' and self.target_hwnd:
            self._activate_target_window()

        self.execution_started.emit()

        try:
            success, message = self._execute_workflow()
            self.execution_finished.emit(message)

        except Exception as e:
            logger.error(f"工作流执行过程中发生错误: {e}", exc_info=True)
            self.execution_finished.emit(f"执行错误: {str(e)}")
        finally:
            # 工作流结束时释放所有按键
            self._release_all_keys()

            # 清理OCR上下文数据，防止影响下次执行
            try:
                from task_workflow.workflow_context import clear_all_ocr_data
                clear_all_ocr_data()
                logger.info("工作流结束，已清理所有OCR上下文数据")
            except Exception as e:
                logger.warning(f"清理OCR上下文数据时发生错误: {e}")

            # 环境变量由调用方负责清理
            self._is_running = False

            # 工具 修复：主动请求线程退出
            logger.debug(f"WorkflowExecutor执行完成，请求线程退出: {self.target_window_title}")
            if hasattr(self, 'thread') and self.thread():
                self.thread().quit()

    def request_stop(self):
        """请求停止执行"""
        logger.info("请求停止工作流执行")
        self._stop_requested = True

        # 释放所有可能正在按下的按键
        self._release_all_keys()

        # 设置全局停止标志 - 已删除有问题的导入
        logger.debug("工作流执行器停止，跳过InputPlayer全局停止标志设置")

    def _release_all_keys(self):
        """释放所有可能正在按下的按键"""
        try:
            # 释放找色任务可能按下的移动按键
            find_color_key = self._persistent_counters.get('__find_color_last_pressed_key__')
            if find_color_key:
                logger.info(f"工作流停止，释放找色任务按键: {find_color_key}")

                # 标准化执行模式
                normalized_mode = self.execution_mode
                if self.execution_mode.startswith('background'):
                    normalized_mode = 'background'
                elif self.execution_mode.startswith('foreground'):
                    normalized_mode = 'foreground'

                if normalized_mode == 'background' and self.target_hwnd:
                    # 后台模式释放按键
                    self._release_key_background(find_color_key)
                elif normalized_mode == 'foreground':
                    # 前台模式释放按键
                    import pyautogui
                    if "+" in find_color_key:
                        # 处理组合键
                        keys = find_color_key.split("+")
                        for key in keys:
                            key = key.strip()
                            try:
                                pyautogui.keyUp(key)
                                logger.debug(f"  释放组合键: {key}")
                            except Exception as e:
                                logger.warning(f"释放按键 {key} 失败: {e}")
                    else:
                        # 单个按键
                        try:
                            pyautogui.keyUp(find_color_key)
                            logger.debug(f"  释放按键: {find_color_key}")
                        except Exception as e:
                            logger.warning(f"释放按键 {find_color_key} 失败: {e}")

                # 清除按键状态
                self._persistent_counters['__find_color_last_pressed_key__'] = None
                logger.info("找色任务按键状态已清除")

            # 可以在这里添加其他任务的按键释放逻辑

        except Exception as e:
            logger.error(f"释放按键时发生错误: {e}")

    def _release_key_background(self, key_str: str):
        """后台模式释放按键"""
        try:
            import win32api
            import win32con

            # 简单的按键映射
            key_map = {
                'w': 0x57, 's': 0x53, 'a': 0x41, 'd': 0x44,
                'up': win32con.VK_UP, 'down': win32con.VK_DOWN,
                'left': win32con.VK_LEFT, 'right': win32con.VK_RIGHT,
                'space': win32con.VK_SPACE, 'enter': win32con.VK_RETURN,
                'shift': win32con.VK_SHIFT, 'ctrl': win32con.VK_CONTROL,
                'alt': win32con.VK_MENU
            }

            if "+" in key_str:
                # 处理组合键
                keys = key_str.split("+")
                for key in keys:
                    key = key.strip().lower()
                    if key in key_map:
                        vk_code = key_map[key]
                        win32api.PostMessage(self.target_hwnd, win32con.WM_KEYUP, vk_code, 0)
                        logger.debug(f"  后台释放组合键: {key}")
            else:
                # 单个按键
                key = key_str.strip().lower()
                if key in key_map:
                    vk_code = key_map[key]
                    win32api.PostMessage(self.target_hwnd, win32con.WM_KEYUP, vk_code, 0)
                    logger.debug(f"  后台释放按键: {key}")

        except Exception as e:
            logger.warning(f"后台释放按键 {key_str} 失败: {e}")

    def _activate_target_window(self):
        """激活目标窗口（前台模式）"""
        try:
            if not self.target_hwnd:
                logger.warning("前台模式但未提供目标窗口句柄，无法激活窗口")
                return False

            # 检查窗口是否有效
            if not win32gui.IsWindow(self.target_hwnd):
                logger.warning(f"目标窗口句柄无效: {self.target_hwnd}")
                return False

            # 获取窗口标题用于日志
            try:
                window_title = win32gui.GetWindowText(self.target_hwnd)
            except:
                window_title = f"HWND:{self.target_hwnd}"

            logger.info(f"前台模式：激活目标窗口 {window_title} (HWND: {self.target_hwnd})")

            # 检查窗口是否已经是前台窗口
            current_foreground = win32gui.GetForegroundWindow()
            if current_foreground == self.target_hwnd:
                logger.info(f"窗口已是前台窗口，无需激活: {window_title}")
                return True

            # 检查窗口是否最小化
            if win32gui.IsIconic(self.target_hwnd):
                logger.info(f"窗口已最小化，正在恢复: {window_title}")
                win32gui.ShowWindow(self.target_hwnd, 9)  # SW_RESTORE = 9
                time.sleep(0.2)  # 等待窗口恢复

            # 激活窗口
            win32gui.SetForegroundWindow(self.target_hwnd)
            time.sleep(0.1)  # 等待窗口激活

            # 验证激活是否成功
            new_foreground = win32gui.GetForegroundWindow()
            if new_foreground == self.target_hwnd:
                logger.info(f"窗口激活成功: {window_title}")
                return True
            else:
                logger.warning(f"窗口激活可能失败: 期望={self.target_hwnd}, 实际={new_foreground}")
                # 尝试备用方法
                try:
                    win32gui.BringWindowToTop(self.target_hwnd)
                    logger.info(f"使用备用方法将窗口置顶: {window_title}")
                    return True
                except Exception as e:
                    logger.error(f"备用激活方法失败: {e}")
                    return False

        except Exception as e:
            logger.error(f"激活目标窗口时出错: {e}")
            return False
    
    def _execute_workflow(self) -> tuple[bool, str]:
        """执行工作流的核心逻辑"""
        try:
            if self.start_card_id is None:
                error_msg = "未指定起始卡片ID"
                logger.error(error_msg)
                return False, error_msg

            if self.start_card_id not in self.cards_data:
                error_msg = f"找不到起始卡片: {self.start_card_id}"
                logger.error(error_msg)
                return False, error_msg

            # 开始执行工作流
            self.step_details.emit("开始执行工作流...")

            current_card_id = self.start_card_id
            execution_count = 0
            # 工具 用户要求：删除无限循环限制，允许任务真正无限执行
            retry_counts = {}  # 记录每个卡片的重试次数

            while current_card_id is not None:
                execution_count += 1

                # 检查停止请求
                if self._stop_requested:
                    logger.info("检测到停止请求，终止工作流执行")
                    # 确保设置全局停止标志 - 已删除有问题的导入
                    logger.debug("工作流停止请求，跳过InputPlayer全局停止标志设置")

                    # 释放所有按键
                    self._release_all_keys()

                    # 清理OCR上下文数据
                    try:
                        from task_workflow.workflow_context import clear_all_ocr_data, clear_multi_image_memory
                        clear_all_ocr_data()
                        logger.info("工作流停止，已清理所有OCR上下文数据")

                        # 清理多图识别记忆数据
                        clear_multi_image_memory()
                        logger.info("工作流停止，已清理所有多图识别记忆数据")
                    except Exception as e:
                        logger.warning(f"停止时清理上下文数据发生错误: {e}")
                    return True, "工作流被用户停止"

                # 检查卡片是否存在
                if current_card_id not in self.cards_data:
                    error_msg = f"找不到步骤 {current_card_id}"
                    logger.error(error_msg)
                    return False, error_msg

                # 获取当前卡片信息
                current_card = self.cards_data[current_card_id]
                # 检查是否是 TaskCard 对象还是字典
                if hasattr(current_card, 'task_type'):
                    # TaskCard 对象
                    task_type = current_card.task_type
                    card_params = current_card.parameters.copy()
                else:
                    # 字典格式
                    task_type = current_card.get('task_type', '未知')
                    card_params = current_card.get('parameters', {})

                # 发送卡片开始执行信号
                self._current_card_id = current_card_id
                self.card_executing.emit(current_card_id)
                self.step_details.emit(f"正在执行: {task_type}")

                logger.info(f"执行卡片 {current_card_id}: {task_type}")

                # 执行卡片逻辑
                success, next_card_id = self._execute_card(current_card_id, task_type, card_params)

                # 发送卡片完成信号
                self.card_finished.emit(current_card_id, success)

                if success:
                    self.step_details.emit(f"{task_type} 执行成功")
                else:
                    self.step_details.emit(f"{task_type} 执行失败")

                # 处理特殊返回值
                if next_card_id == 'STOP_WORKFLOW':
                    return True, f"工作流执行完成"

                # 处理失败时的操作
                if not success:
                    # 获取失败时的操作设置
                    failure_action = card_params.get('on_failure', '执行下一步')

                    if failure_action == '停止工作流':
                        logger.info(f"{task_type} 执行失败，停止工作流")
                        return False, f"工作流在步骤 {current_card_id} ({task_type}) 处失败并停止"
                    elif failure_action == '跳转到步骤':
                        jump_target = card_params.get('failure_jump_target_id')
                        if jump_target and next_card_id is None:
                            logger.info(f"{task_type} 执行失败，跳转到步骤 {jump_target}")
                            next_card_id = jump_target
                    elif failure_action == '继续执行本步骤':
                        # 双重重试机制：
                        # 1. 任务内部重试（如图片查找3次）
                        # 2. 工作流级别重试（重新执行整个步骤）

                        current_retry_count = retry_counts.get(current_card_id, 0)
                        retry_counts[current_card_id] = current_retry_count + 1

                        # 获取重试间隔设置
                        workflow_retry_interval = card_params.get('workflow_retry_interval',
                                                               card_params.get('retry_interval', 0.5))

                        logger.info(f"{task_type} 任务内部重试已完成，开始工作流级重试 (第 {retry_counts[current_card_id]} 次)")

                        # 添加工作流重试间隔，并在等待期间检查停止请求
                        if workflow_retry_interval > 0:
                            logger.debug(f"工作流重试间隔: {workflow_retry_interval} 秒...")

                            # 在等待期间检查停止请求
                            sleep_time = 0
                            while sleep_time < workflow_retry_interval:
                                if self._stop_requested:
                                    logger.info("用户按下停止按钮，终止'继续执行本步骤'循环")
                                    return False, '工作流被用户停止'
                                time.sleep(0.1)  # 每0.1秒检查一次停止按钮
                                sleep_time += 0.1

                        # 重新执行当前步骤（允许无限重试）
                        continue
                else:
                    # 执行成功，重置重试计数器
                    if current_card_id in retry_counts:
                        del retry_counts[current_card_id]

                # 如果没有指定下一个卡片，根据连接查找
                if next_card_id is None:
                    next_card_id = self._find_next_card(current_card_id, success)

                current_card_id = next_card_id

                # 启动 优化：移除步骤间延迟，提高执行速度
                # 原来的延迟会累积影响整个工作流的执行效率

            # 工具 用户要求：删除无限循环限制检查，允许任务真正无限执行
            # if execution_count >= max_executions:
            #     error_msg = "工作流执行次数超过限制，可能存在无限循环"
            #     logger.error(error_msg)
            #     return False, error_msg

            return True, "工作流执行完成"

        except Exception as e:
            error_msg = f"工作流执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if self._current_card_id is not None:
                self.error_occurred.emit(self._current_card_id, str(e))
            return False, error_msg
    
    def _execute_card(self, card_id: int, task_type: str, card_params: Dict[str, Any]) -> tuple[bool, int]:
        """执行单个卡片的逻辑"""
        try:
            # 获取对应的任务模块
            task_module = TASK_MODULES.get(task_type)
            if not task_module:
                logger.error(f"找不到任务类型 '{task_type}' 对应的模块")
                return False, None

            # 准备执行环境参数
            # 工具 修复：使用持久计数器字典而不是每次创建新的
            counters = self._persistent_counters  # 使用持久计数器
            execution_mode = self.execution_mode  # 执行模式
            window_region = None  # 窗口区域

            # 工具 关键修复：优先使用构造函数传入的target_hwnd，避免重新查找导致窗口混乱
            target_hwnd = self.target_hwnd

            # 验证预设的窗口句柄是否有效
            if target_hwnd:
                try:
                    if win32gui.IsWindow(target_hwnd):
                        actual_title = win32gui.GetWindowText(target_hwnd)
                        logger.info(f"成功 使用预设窗口句柄: {target_hwnd} -> '{actual_title}'")
                    else:
                        logger.error(f"错误 预设窗口句柄无效: {target_hwnd}，请手动重新绑定窗口")
                        return False, None
                except Exception as e:
                    logger.error(f"错误 验证预设窗口句柄时出错: {e}，请手动重新绑定窗口")
                    return False, None

            # 如果没有有效的预设句柄，返回失败
            if not target_hwnd:
                logger.error(f"错误 没有有效的窗口句柄，请先绑定窗口")
                return False, None

            # 记录最终使用的窗口句柄
            if target_hwnd:
                source = "预设" if self.target_hwnd else "查找"
                logger.info(f"靶心 最终使用窗口句柄: {target_hwnd} (来源: {source})")
            else:
                logger.error("错误 没有有效的窗口句柄，任务可能失败")

            # 工具 修复：简化任务执行逻辑，不再区分多窗口模式
            # 多窗口模式应该由环境变量MULTI_WINDOW_MODE来标识，而不是在这里判断
            if hasattr(task_module, 'execute_task'):
                # 统一使用标准方法执行任务
                logger.debug(f"执行任务 '{task_type}': 窗口='{self.target_window_title}' (HWND: {target_hwnd}), 模式={execution_mode}")
                result = task_module.execute_task(
                    params=card_params,
                    counters=counters,
                    execution_mode=execution_mode,
                    target_hwnd=target_hwnd,
                    window_region=window_region,
                    card_id=card_id,
                    get_image_data=None,  # 工作流执行器暂不支持图片数据获取
                    stop_checker=lambda: self._stop_requested  # 传递停止检查函数
                )

                # 工具 修复：检查返回值是否为None，防止解包错误
                if result is None:
                    logger.error(f"任务 '{task_type}' 返回了 None，这可能是任务执行异常")
                    success, action, next_card_id = False, '执行下一步', None
                else:
                    success, action, next_card_id = result

            elif hasattr(task_module, 'execute'):
                # 使用 execute 方法
                result = task_module.execute(
                    card_params,
                    counters,
                    execution_mode,
                    target_hwnd,
                    card_id,
                    get_image_data=None,  # 工作流执行器暂不支持图片数据获取
                    stop_checker=lambda: self._stop_requested  # 传递停止检查函数
                )

                # 工具 修复：检查返回值是否为None，防止解包错误
                if result is None:
                    logger.error(f"任务 '{task_type}' (execute方法) 返回了 None，这可能是任务执行异常")
                    success, action, next_card_id = False, '执行下一步', None
                else:
                    success, action, next_card_id = result
            else:
                logger.error(f"任务模块 '{task_type}' 没有 execute_task 或 execute 方法")
                return False, None

            # 处理返回的动作
            if action == '停止工作流':
                return success, '工作流执行完成'
            elif action == '跳转到步骤' and next_card_id is not None:
                return success, next_card_id
            elif action == '继续执行本步骤':
                # 返回当前卡片ID，让工作流重新执行当前步骤
                return success, card_id
            else:
                # 默认执行下一步，返回 None 让连接查找逻辑处理
                return success, None

        except Exception as e:
            logger.error(f"执行卡片 {card_id} ({task_type}) 时发生错误: {e}", exc_info=True)
            self.error_occurred.emit(card_id, str(e))
            return False, None



    def _find_next_card(self, current_card_id: int, success: bool) -> int:
        """根据连接查找下一个卡片"""
        connections = self._connections_map.get(current_card_id, [])

        # 🔍 调试：记录查找过程
        logger.info(f"🔍 查找卡片 {current_card_id} 的下一个卡片 (success={success})")
        logger.info(f"  当前卡片的连接数: {len(connections)}")
        if connections:
            for conn in connections:
                logger.info(f"    -> 连接: {conn.get('start_card_id')} -> {conn.get('end_card_id')} (类型: {conn.get('type')})")
        else:
            logger.warning(f"  ⚠️ 卡片 {current_card_id} 没有任何出向连接！")
            # 打印完整的连接映射以帮助诊断
            logger.info(f"  完整连接映射: {self._connections_map}")

        # 首先查找特定类型的连接
        connection_type = 'success' if success else 'failure'
        for connection in connections:
            if connection.get('type') == connection_type:
                next_card = connection.get('end_card_id')
                logger.info(f"  ✓ 找到 {connection_type} 类型连接 -> 卡片 {next_card}")
                return next_card

        # 如果没有找到特定连接，查找顺序连接
        for connection in connections:
            if connection.get('type') == 'sequential':
                next_card = connection.get('end_card_id')
                logger.info(f"  ✓ 找到 sequential 类型连接 -> 卡片 {next_card}")
                return next_card

        logger.warning(f"  ✗ 没有找到下一个卡片，工作流将结束")
        return None

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._is_running

    def moveToThread(self, thread: QThread):
        """移动到指定线程"""
        super().moveToThread(thread)
        logger.debug(f"WorkflowExecutor 已移动到线程: {thread}")
