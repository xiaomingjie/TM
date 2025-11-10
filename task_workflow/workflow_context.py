# -*- coding: utf-8 -*-

"""
工作流上下文管理器
用于在工作流执行过程中在卡片间传递数据，特别是OCR识别结果
"""

import logging
import threading
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class WorkflowContext:
    """工作流执行上下文"""
    # OCR识别结果存储 {card_id: [ocr_results]}
    ocr_results: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)
    
    # 图片识别结果存储 {card_id: image_results}
    image_results: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # 通用数据存储 {card_id: {key: value}}
    card_data: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # 全局变量存储
    global_vars: Dict[str, Any] = field(default_factory=dict)
    
    def clear(self):
        """清空所有上下文数据"""
        self.ocr_results.clear()
        self.image_results.clear()
        self.card_data.clear()
        self.global_vars.clear()
        logger.debug("工作流上下文已清空")
    
    def set_ocr_results(self, card_id: int, results: List[Dict[str, Any]]):
        """设置OCR识别结果"""
        self.ocr_results[card_id] = results
        # 记录最新的OCR结果卡片ID和时间戳
        self.set_global_var('latest_ocr_card_id', card_id)
        self.set_global_var('latest_ocr_timestamp', time.time())
        logger.debug(f"设置卡片 {card_id} 的OCR结果: {len(results)} 个文字 (最新)")
    
    def get_ocr_results(self, card_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取OCR识别结果"""
        if card_id is not None:
            return self.ocr_results.get(card_id, [])
        
        # 如果没有指定卡片ID，返回最近的OCR结果
        if self.ocr_results:
            latest_card_id = max(self.ocr_results.keys())
            return self.ocr_results[latest_card_id]
        
        return []
    
    def get_latest_ocr_results(self) -> List[Dict[str, Any]]:
        """获取最新的OCR识别结果"""
        # 优先使用记录的最新OCR卡片ID
        latest_card_id = self.get_global_var('latest_ocr_card_id')
        if latest_card_id and latest_card_id in self.ocr_results:
            logger.debug(f"使用记录的最新OCR结果: 卡片ID {latest_card_id}")
            return self.ocr_results[latest_card_id]

        # 如果没有记录，按卡片ID降序查找最新的
        if self.ocr_results:
            latest_card_id = max(self.ocr_results.keys())
            logger.debug(f"使用最大卡片ID的OCR结果: 卡片ID {latest_card_id}")
            return self.ocr_results[latest_card_id]

        return []
    
    def set_card_data(self, card_id: int, key: str, value: Any):
        """设置卡片数据"""
        if card_id not in self.card_data:
            self.card_data[card_id] = {}
        self.card_data[card_id][key] = value
        logger.debug(f"设置卡片 {card_id} 数据: {key} = {value}")

    def set_multi_text_recognition_state(self, card_id: int, text_groups: list, current_index: int = 0, clicked_texts: list = None):
        """设置多组文字识别状态"""
        if clicked_texts is None:
            clicked_texts = []

        self.set_card_data(card_id, 'multi_text_groups', text_groups)
        self.set_card_data(card_id, 'current_text_index', current_index)
        self.set_card_data(card_id, 'clicked_texts', clicked_texts.copy())
        logger.info(f"设置多组文字识别状态: 卡片{card_id}, 当前组{current_index}/{len(text_groups)}, 已点击{len(clicked_texts)}个文字")

    def get_multi_text_recognition_state(self, card_id: int):
        """获取多组文字识别状态"""
        if card_id not in self.card_data:
            return None, 0, []

        card_data = self.card_data[card_id]
        text_groups = card_data.get('multi_text_groups', [])
        current_index = card_data.get('current_text_index', 0)
        clicked_texts = card_data.get('clicked_texts', [])

        return text_groups, current_index, clicked_texts

    def advance_text_recognition_index(self, card_id: int):
        """推进到下一组文字识别"""
        text_groups, current_index, clicked_texts = self.get_multi_text_recognition_state(card_id)
        if text_groups:
            new_index = current_index + 1
            self.set_card_data(card_id, 'current_text_index', new_index)
            logger.info(f"推进到下一组文字: 卡片{card_id}, 新索引{new_index}/{len(text_groups)}")

            # 返回是否还有下一组需要处理
            return new_index < len(text_groups)
        return False

    def add_clicked_text(self, card_id: int, clicked_text: str):
        """添加已点击的文字"""
        text_groups, current_index, clicked_texts = self.get_multi_text_recognition_state(card_id)
        if clicked_text not in clicked_texts:
            clicked_texts.append(clicked_text)
            self.set_card_data(card_id, 'clicked_texts', clicked_texts)
            logger.info(f"添加已点击文字: 卡片{card_id}, 文字'{clicked_text}', 总计{len(clicked_texts)}个")

    def is_multi_text_recognition_complete(self, card_id: int):
        """检查多组文字识别是否完成"""
        text_groups, current_index, clicked_texts = self.get_multi_text_recognition_state(card_id)
        if not text_groups:
            return True
        return current_index >= len(text_groups) - 1

    def reset_multi_text_recognition_state(self, card_id: int, text_groups: list):
        """重置多组文字识别状态"""
        self.set_multi_text_recognition_state(card_id, text_groups, 0, [])
        logger.info(f"重置多组文字识别状态: 卡片{card_id}, 共{len(text_groups)}组文字")
    
    def get_card_data(self, card_id: int, key: str, default: Any = None) -> Any:
        """获取卡片数据"""
        return self.card_data.get(card_id, {}).get(key, default)
    
    def set_global_var(self, key: str, value: Any):
        """设置全局变量"""
        self.global_vars[key] = value
        logger.debug(f"设置全局变量: {key} = {value}")
    
    def get_global_var(self, key: str, default: Any = None) -> Any:
        """获取全局变量"""
        return self.global_vars.get(key, default)

    def clear_card_ocr_context(self, card_id: int):
        """清除指定卡片的OCR上下文数据（不包括记忆）"""
        # 清除OCR识别结果（上下文）
        if card_id in self.ocr_results:
            del self.ocr_results[card_id]
            logger.debug(f"清除卡片 {card_id} 的OCR上下文结果")

        # 清除OCR上下文相关的卡片数据（不包括记忆数据）
        if card_id in self.card_data:
            card_data = self.card_data[card_id]
            context_keys = ['ocr_target_text', 'ocr_match_mode', 'ocr_region_offset']
            for key in context_keys:
                if key in card_data:
                    del card_data[key]
                    logger.debug(f"清除卡片 {card_id} 的OCR上下文数据: {key}")

    def clear_card_ocr_data(self, card_id: int):
        """清除指定卡片的所有OCR相关数据（包括记忆）"""
        # 清除OCR识别结果
        if card_id in self.ocr_results:
            del self.ocr_results[card_id]
            logger.debug(f"清除卡片 {card_id} 的OCR识别结果")

        # 清除所有OCR相关的卡片数据（包括记忆）
        if card_id in self.card_data:
            card_data = self.card_data[card_id]
            all_ocr_keys = ['ocr_target_text', 'ocr_match_mode', 'ocr_region_offset',
                           'multi_text_groups', 'current_text_index', 'clicked_texts']
            for key in all_ocr_keys:
                if key in card_data:
                    del card_data[key]
                    logger.debug(f"清除卡片 {card_id} 的OCR数据: {key}")

            # 如果卡片数据为空，删除整个卡片数据
            if not card_data:
                del self.card_data[card_id]
                logger.debug(f"清除卡片 {card_id} 的所有数据")

    def clear_all_ocr_data(self):
        """清除所有OCR相关数据"""
        self.ocr_results.clear()

        # 清除所有卡片的OCR相关数据
        for card_id in list(self.card_data.keys()):
            self.clear_card_ocr_data(card_id)

        logger.debug("清除所有OCR相关数据")

    def clear_multi_image_memory(self):
        """清除所有多图识别记忆数据"""
        cleared_count = 0
        for card_id in list(self.card_data.keys()):
            card_data = self.card_data[card_id]
            memory_keys = ['clicked_images', 'success_images']
            for key in memory_keys:
                if key in card_data:
                    del card_data[key]
                    cleared_count += 1
                    logger.debug(f"清除卡片 {card_id} 的多图识别记忆: {key}")

            # 如果卡片数据为空，删除整个卡片数据
            if not card_data:
                del self.card_data[card_id]
                logger.debug(f"清除卡片 {card_id} 的所有数据")

        if cleared_count > 0:
            logger.info(f"清除了 {cleared_count} 个多图识别记忆数据")
        else:
            logger.debug("没有找到需要清除的多图识别记忆数据")


class WorkflowContextManager:
    """工作流上下文管理器（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._contexts: Dict[str, WorkflowContext] = {}
            self._thread_local = threading.local()
            self._initialized = True
            logger.debug("工作流上下文管理器初始化完成")
    
    def get_context(self, workflow_id: str = "default") -> WorkflowContext:
        """获取工作流上下文"""
        if workflow_id not in self._contexts:
            self._contexts[workflow_id] = WorkflowContext()
            logger.debug(f"创建新的工作流上下文: {workflow_id}")
        return self._contexts[workflow_id]
    
    def get_current_context(self) -> WorkflowContext:
        """获取当前线程的工作流上下文"""
        # 尝试从线程本地存储获取
        if hasattr(self._thread_local, 'context'):
            return self._thread_local.context
        
        # 如果没有，使用默认上下文
        context = self.get_context("default")
        self._thread_local.context = context
        return context
    
    def set_current_context(self, context: WorkflowContext):
        """设置当前线程的工作流上下文"""
        self._thread_local.context = context
    
    def clear_context(self, workflow_id: str = "default"):
        """清空指定工作流的上下文"""
        if workflow_id in self._contexts:
            self._contexts[workflow_id].clear()
            logger.debug(f"清空工作流上下文: {workflow_id}")
    
    def clear_all_contexts(self):
        """清空所有工作流上下文"""
        for context in self._contexts.values():
            context.clear()
        self._contexts.clear()
        logger.debug("清空所有工作流上下文")


# 全局上下文管理器实例
_context_manager = WorkflowContextManager()

def get_workflow_context(workflow_id: str = "default") -> WorkflowContext:
    """获取工作流上下文的便捷函数"""
    return _context_manager.get_context(workflow_id)

def get_current_workflow_context() -> WorkflowContext:
    """获取当前工作流上下文的便捷函数"""
    return _context_manager.get_current_context()

def set_ocr_results(card_id: int, results: List[Dict[str, Any]], workflow_id: str = "default"):
    """设置OCR识别结果的便捷函数"""
    context = get_workflow_context(workflow_id)
    context.set_ocr_results(card_id, results)

def get_ocr_results(card_id: Optional[int] = None, workflow_id: str = "default") -> List[Dict[str, Any]]:
    """获取OCR识别结果的便捷函数"""
    context = get_workflow_context(workflow_id)
    return context.get_ocr_results(card_id)

def get_latest_ocr_results(workflow_id: str = "default") -> List[Dict[str, Any]]:
    """获取最新OCR识别结果的便捷函数"""
    context = get_workflow_context(workflow_id)
    return context.get_latest_ocr_results()

def clear_workflow_context(workflow_id: str = "default"):
    """清空工作流上下文的便捷函数"""
    _context_manager.clear_context(workflow_id)

def clear_all_workflow_contexts():
    """清空所有工作流上下文的便捷函数"""
    _context_manager.clear_all_contexts()

def clear_card_ocr_context(card_id: int, workflow_id: str = "default"):
    """清除指定卡片的OCR上下文数据的便捷函数"""
    context = get_workflow_context(workflow_id)
    context.clear_card_ocr_context(card_id)

def clear_card_ocr_data(card_id: int, workflow_id: str = "default"):
    """清除指定卡片的OCR数据的便捷函数"""
    context = get_workflow_context(workflow_id)
    context.clear_card_ocr_data(card_id)

def clear_all_ocr_data(workflow_id: str = "default"):
    """清除所有OCR数据的便捷函数"""
    context = get_workflow_context(workflow_id)
    context.clear_all_ocr_data()

def clear_multi_image_memory(workflow_id: str = "default"):
    """清除所有多图识别记忆数据的便捷函数"""
    context = get_workflow_context(workflow_id)
    context.clear_multi_image_memory()
