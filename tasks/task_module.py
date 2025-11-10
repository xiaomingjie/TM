# -*- coding: utf-8 -*-
"""
任务模块执行器 - 执行封装的任务模块
"""
import json
import logging
import os
from typing import Dict, Any, Tuple, Optional, List
import copy

logger = logging.getLogger(__name__)

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """获取任务模块的参数定义"""
    return {
        "module_file": {
            "label": "模块文件",
            "type": "file",
            "file_filter": "模块文件 (*.module);;所有文件 (*)",
            "tooltip": "选择要执行的任务模块文件"
        },

        # 添加跳转步骤支持
        "---post_exec---": {
            "type": "separator",
            "label": "执行后操作"
        },
        "on_success": {
            "type": "select",
            "label": "模块成功时",
            "options": ["执行下一步", "继续本步骤", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "当模块执行成功时的操作"
        },
        "success_jump_target_id": {
            "type": "int",
            "label": "成功跳转目标ID",
            "required": False,
            "condition": {"param": "on_success", "value": "跳转到步骤"},
            "tooltip": "模块成功时要跳转到的卡片ID"
        },
        "on_failure": {
            "type": "select",
            "label": "模块失败时",
            "options": ["执行下一步", "继续本步骤", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "当模块执行失败时的操作"
        },
        "failure_jump_target_id": {
            "type": "int",
            "label": "失败跳转目标ID",
            "required": False,
            "condition": {"param": "on_failure", "value": "跳转到步骤"},
            "tooltip": "模块失败时要跳转到的卡片ID"
        }
    }

def execute_task(params: Dict[str, Any], counters: Dict[str, int],
                execution_mode='foreground', **kwargs) -> Tuple[bool, str, Optional[int]]:
    """执行任务模块 - 简化版本，直接执行模块工作流"""

    # 从kwargs中获取card_id（与普通任务保持一致）
    card_id = kwargs.get('card_id')

    # 添加详细的调试日志
    logger.info(f"任务模块开始执行 - 卡片ID: {card_id}")
    logger.debug(f"任务模块参数: {params}")
    logger.debug(f"执行模式: {execution_mode}")

    module_file = params.get('module_file')
    logger.info(f"模块文件路径: {module_file}")

    if not module_file:
        logger.error("模块文件路径为空")
        return False, "未选择有效的模块文件", None

    if not os.path.exists(module_file):
        logger.error(f"模块文件不存在: {module_file}")
        return False, "未选择有效的模块文件", None

    logger.info(f"模块文件验证通过: {module_file}")

    try:
        # 加载模块配置
        logger.info("开始加载模块配置文件")
        with open(module_file, 'r', encoding='utf-8') as f:
            module_config = json.load(f)
        logger.info("模块配置文件加载成功")

        # 验证基本格式
        if 'workflow' not in module_config:
            logger.error("模块文件格式错误：缺少workflow字段")
            return False, "模块文件格式错误：缺少workflow字段", None

        logger.info("模块文件格式验证通过")

        # 直接执行模块内的工作流
        workflow_data = module_config['workflow']
        logger.info(f"准备执行内部工作流，工作流数据: {type(workflow_data)}")

        success, internal_next_card_id = _execute_internal_workflow(
            workflow_data, counters, execution_mode, card_id, **kwargs
        )

        logger.info(f"内部工作流执行完成: success={success}, next_card_id={internal_next_card_id}")

        # 如果内部工作流返回了跳转信息，需要特殊处理
        # 这里internal_next_card_id是内部模块的卡片ID，需要转换为外部逻辑

        module_name = module_config.get('module_info', {}).get('name', '未知模块')

        # 处理跳转逻辑 - 根据模块整体执行结果决定跳转
        if success:
            logger.info(f"任务模块执行成功: {module_name}")

            # 检查内部工作流是否有特殊的跳转需求
            if internal_next_card_id == "CONTINUE_MODULE":
                # 内部工作流要求继续执行模块（循环）
                return True, "继续执行本步骤", card_id
            elif internal_next_card_id == "STOP_WORKFLOW":
                # 内部工作流要求停止整个工作流
                return True, "停止工作流", None

            # 根据任务模块卡片的成功跳转设置处理
            success_action = params.get('on_success', '执行下一步')

            if success_action == '跳转到步骤':
                jump_target = params.get('success_jump_target_id')
                if jump_target is not None:
                    return True, "执行下一步", jump_target
                else:
                    logger.warning("成功跳转目标ID未设置，执行下一步")
                    return True, "执行下一步", None
            elif success_action == '继续本步骤':
                return True, "继续执行本步骤", card_id  # 返回当前卡片ID实现循环
            elif success_action == '停止工作流':
                return True, "停止工作流", None
            else:  # 执行下一步
                return True, "执行下一步", None
        else:
            logger.error(f"任务模块执行失败: {module_name}")

            # 检查内部工作流是否有特殊的跳转需求
            if internal_next_card_id == "CONTINUE_MODULE":
                # 内部工作流要求继续执行模块（循环）
                return False, "继续执行本步骤", card_id
            elif internal_next_card_id == "STOP_WORKFLOW":
                # 内部工作流要求停止整个工作流
                return False, "停止工作流", None

            # 根据任务模块卡片的失败跳转设置处理
            failure_action = params.get('on_failure', '执行下一步')

            if failure_action == '跳转到步骤':
                jump_target = params.get('failure_jump_target_id')
                if jump_target is not None:
                    return False, "执行下一步", jump_target
                else:
                    logger.warning("失败跳转目标ID未设置，执行下一步")
                    return False, "执行下一步", None
            elif failure_action == '继续本步骤':
                return False, "继续执行本步骤", card_id  # 返回当前卡片ID实现循环
            elif failure_action == '停止工作流':
                return False, "停止工作流", None
            else:  # 执行下一步
                return False, "执行下一步", None

    except Exception as e:
        logger.error(f"任务模块执行失败: {e}", exc_info=True)
        return False, f"模块执行错误: {str(e)}", None

def _validate_module_config(config: Dict) -> bool:
    """验证模块配置格式"""
    try:
        # 检查必需字段
        required_keys = ['module_info', 'workflow']
        for key in required_keys:
            if key not in config:
                logger.error(f"模块配置缺少必需字段: {key}")
                return False
        
        # 检查模块信息
        module_info = config['module_info']
        if 'name' not in module_info:
            logger.error("模块信息缺少名称字段")
            return False
        
        if 'version' not in module_info:
            logger.error("模块信息缺少版本字段")
            return False
        
        # 检查工作流结构
        workflow = config['workflow']
        if 'cards' not in workflow:
            logger.error("工作流缺少卡片定义")
            return False
        
        if not isinstance(workflow['cards'], list):
            logger.error("工作流卡片必须是列表格式")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"模块配置验证失败: {e}")
        return False

# 移除参数替换功能，任务模块直接执行原始工作流

def _execute_internal_workflow(workflow_data: Dict, counters: Dict,
                             execution_mode: str, parent_card_id: Optional[int], **kwargs) -> Tuple[bool, Optional[int]]:
    """执行内嵌工作流，支持步骤跳转"""
    try:
        logger.info(f"开始执行内部工作流 - 父卡片ID: {parent_card_id}")

        # 获取卡片数据和连接数据
        cards = workflow_data.get('cards', [])
        connections = workflow_data.get('connections', [])

        logger.info(f"内部工作流包含 {len(cards)} 个卡片, {len(connections)} 个连接")

        if not cards:
            logger.warning("工作流中没有卡片")
            return True, None

        # 导入任务模块
        from tasks import TASK_MODULES

        # 获取执行参数
        target_hwnd = kwargs.get('target_hwnd')
        images_dir = kwargs.get('images_dir', 'images')

        # 构建卡片映射和连接映射
        card_map = {card['id']: card for card in cards}

        # 构建连接映射（从起始卡片ID到目标卡片ID）
        connection_map = {}
        for conn in connections:
            start_id = conn.get('start_card_id')
            end_id = conn.get('end_card_id')
            if start_id and end_id:
                connection_map[start_id] = end_id

        # 找到起点卡片（没有输入连接的卡片，或者ID最小的卡片）
        input_cards = {conn.get('end_card_id') for conn in connections if conn.get('end_card_id')}
        start_cards = [card for card in cards if card['id'] not in input_cards]

        logger.info(f"输入卡片ID集合: {input_cards}")
        logger.info(f"候选起点卡片: {[card['id'] for card in start_cards]}")

        if not start_cards:
            # 如果没有明确的起点，使用ID最小的卡片
            logger.warning("没有找到明确的起点卡片，使用ID最小的卡片")
            current_card_id = min(card['id'] for card in cards)
        else:
            # 使用第一个起点卡片
            current_card_id = start_cards[0]['id']

        logger.info(f"模块内工作流从卡片 {current_card_id} 开始执行")

        # 执行工作流
        executed_cards = set()  # 防止无限循环
        # 不设置最大迭代次数限制

        while current_card_id is not None:  # 移除最大迭代次数限制
            # 移除迭代计数

            # 检查停止信号 - 从kwargs中获取停止检查函数
            stop_checker = kwargs.get('stop_checker')
            if stop_checker and callable(stop_checker):
                if stop_checker():
                    logger.info("任务模块内部工作流检测到停止请求，终止执行")
                    return True, "STOP_WORKFLOW"

            if current_card_id in executed_cards:
                logger.warning(f"检测到循环执行，停止在卡片 {current_card_id}")
                break

            if current_card_id not in card_map:
                logger.error(f"卡片 {current_card_id} 不存在")
                break

            card = card_map[current_card_id]
            task_type = card.get('task_type', '未知')
            card_params = card.get('parameters', {})

            logger.info(f"执行模块内卡片 {current_card_id}: {task_type}")
            executed_cards.add(current_card_id)

            # 检查任务类型是否存在
            if task_type not in TASK_MODULES:
                logger.error(f"未知的任务类型: {task_type}")
                return False, None

            # 获取任务模块
            task_module = TASK_MODULES[task_type]

            # 执行任务
            try:
                # 准备执行参数，避免重复传递
                exec_kwargs = kwargs.copy()
                # 防止重复传递target_hwnd参数
                if 'target_hwnd' in exec_kwargs:
                    # 使用已有的target_hwnd
                    pass
                else:
                    # 添加target_hwnd参数
                    exec_kwargs['target_hwnd'] = target_hwnd

                exec_kwargs['images_dir'] = images_dir
                exec_kwargs['card_id'] = current_card_id  # 传递当前卡片ID

                success, message, next_card_id = task_module.execute_task(
                    card_params,
                    counters,
                    execution_mode,
                    **exec_kwargs
                )

                logger.info(f"卡片 {current_card_id} 执行结果: {success}, 消息: {message}, 下一步: {next_card_id}")

                # 处理执行结果和跳转逻辑
                if success:
                    # 成功时的跳转逻辑
                    success_action = card_params.get('on_success', '执行下一步')
                    if success_action == '跳转到步骤' and 'success_jump_target_id' in card_params:
                        current_card_id = card_params['success_jump_target_id']
                        logger.info(f"成功跳转到步骤: {current_card_id}")
                    elif success_action == '继续本步骤' or success_action == '继续执行本步骤':
                        # 重复执行当前卡片，但从executed_cards中移除以允许重复
                        executed_cards.discard(current_card_id)
                        logger.info(f"继续执行本步骤: {current_card_id}")
                        # current_card_id 保持不变，继续循环
                        continue
                    elif success_action == '停止任务' or success_action == '停止工作流':
                        logger.info(f"成功完成，停止任务执行")
                        return True, "STOP_WORKFLOW"
                    elif success_action == '执行下一步':
                        if next_card_id is not None:
                            current_card_id = next_card_id
                        elif current_card_id in connection_map:
                            current_card_id = connection_map[current_card_id]
                        else:
                            # 没有下一步，结束执行
                            current_card_id = None
                    else:
                        # 默认执行下一步
                        if current_card_id in connection_map:
                            current_card_id = connection_map[current_card_id]
                        else:
                            current_card_id = None
                else:
                    # 失败时的跳转逻辑
                    failure_action = card_params.get('on_failure', '执行下一步')
                    if failure_action == '停止任务' or failure_action == '停止工作流':
                        logger.error(f"卡片 {current_card_id} 执行失败，停止任务执行")
                        return False, "STOP_WORKFLOW"
                    elif failure_action == '跳转到步骤' and 'failure_jump_target_id' in card_params:
                        current_card_id = card_params['failure_jump_target_id']
                        logger.info(f"失败跳转到步骤: {current_card_id}")
                    elif failure_action == '继续本步骤' or failure_action == '继续执行本步骤':
                        # 重复执行当前卡片
                        executed_cards.discard(current_card_id)
                        logger.info(f"失败后继续执行本步骤: {current_card_id}")
                        # current_card_id 保持不变，继续循环
                        continue
                    elif failure_action == '执行下一步':
                        if current_card_id in connection_map:
                            current_card_id = connection_map[current_card_id]
                        else:
                            current_card_id = None
                    else:
                        # 默认执行下一步
                        if current_card_id in connection_map:
                            current_card_id = connection_map[current_card_id]
                        else:
                            current_card_id = None

            except Exception as e:
                logger.error(f"执行卡片 {current_card_id} 时发生异常: {e}", exc_info=True)
                return False, None

        # 移除最大迭代次数检查

        logger.info("模块内工作流执行完成")
        return True, None

    except Exception as e:
        logger.error(f"内嵌工作流执行失败: {e}", exc_info=True)
        return False, None

# 移除复杂的模块信息和参数定义功能
# 任务模块就是简单的工作流文件，不需要额外的元数据处理
