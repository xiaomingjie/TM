# tasks/start_task.py
import time
import logging
from typing import Optional, Any, Dict, Tuple

logger = logging.getLogger(__name__)

# 任务类型标识
TASK_TYPE = "起点"

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """返回起点任务的参数定义，允许指定下一步卡片。"""
    return {
        "next_step_card_id": {
            "label": "下一步骤卡片",
            "type": "combo",
            "required": False,
            "default": None,
            "widget_hint": "card_selector",
            "tooltip": "选择第一个要执行的任务卡片。如果选择“默认”，则跟随蓝色连线。",
            "options_dynamic": True
        }
    }

def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str, target_hwnd: Optional[int], window_region=None, card_id: Optional[int] = None, **kwargs) -> Tuple[bool, str, Optional[int]]:
    """
    起点任务的执行逻辑 - 标准接口。
    根据参数决定下一步执行的卡片。
    """
    logger.info("--- 起点任务开始 ---")
    next_id_raw = params.get('next_step_card_id')
    next_id = None

    if next_id_raw is not None and str(next_id_raw).strip() and str(next_id_raw).lower() != 'none':
        try:
            next_id = int(next_id_raw)
        except (ValueError, TypeError):
            logger.warning(f"无法将 next_step_card_id 值 '{next_id_raw}' 转换为整数。将默认跟随蓝线。")
            next_id = None

    if next_id is not None:
        logger.info(f"起点任务指定跳转到卡片 ID: {next_id}")
        logger.info("--- 起点任务结束 (跳转) ---")
        return True, '跳转到步骤', next_id
    else:
        logger.info("起点任务未指定跳转目标，将执行下一步。")
        logger.info("--- 起点任务结束 (默认继续) ---")
        return True, '执行下一步', None

def run(params: Dict[str, Any], cards_dict: Dict[int, Any], **kwargs) -> Tuple[bool, Optional[int]]:
    """
    起点任务的执行逻辑 - 兼容旧接口。
    根据参数决定是返回 True（跟随蓝线）还是返回目标卡片 ID。
    """
    logger.info("--- 起点任务开始 (兼容模式) ---")
    next_id_raw = params.get('next_step_card_id')
    next_id = None

    if next_id_raw is not None and str(next_id_raw).strip() and str(next_id_raw).lower() != 'none':
        try:
            next_id = int(next_id_raw)
        except (ValueError, TypeError):
            logger.warning(f"无法将 next_step_card_id 值 '{next_id_raw}' 转换为整数。将默认跟随蓝线。")
            next_id = None

    if next_id is not None and next_id in cards_dict:
        logger.info(f"起点任务指定跳转到卡片 ID: {next_id}")
        logger.info("--- 起点任务结束 (跳转) ---")
        return False, next_id
    else:
        if next_id is not None:
            logger.warning(f"指定的 next_step_card_id ({next_id}) 无效或卡片不存在。将默认跟随蓝线。")
        logger.info("起点任务未指定有效跳转目标，将跟随蓝色连线。")
        logger.info("--- 起点任务结束 (默认继续) ---")
        return True, None