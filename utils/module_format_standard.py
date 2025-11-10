#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
模块格式标准化工具
提供统一的模块文件格式创建和验证功能
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ModuleFormatStandard:
    """模块格式标准化类"""
    
    # 标准模块格式版本
    STANDARD_VERSION = "1.0"
    ENGINE_VERSION = "1.0.0"
    
    @classmethod
    def create_module_data(cls, 
                          cards: List[Dict[str, Any]], 
                          connections: List[Dict[str, Any]],
                          module_name: str,
                          description: str = None,
                          author: str = "用户",
                          tags: List[str] = None,
                          category: str = None,
                          generated_by: str = None,
                          additional_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        创建标准格式的模块数据
        
        Args:
            cards: 卡片列表
            connections: 连接列表
            module_name: 模块名称
            description: 模块描述
            author: 作者
            tags: 标签列表
            category: 分类
            generated_by: 生成器标识
            additional_metadata: 额外的元数据
            
        Returns:
            标准格式的模块数据字典
        """
        current_time = datetime.now().isoformat()
        
        # 构建模块信息
        module_info = {
            "name": module_name,
            "version": cls.STANDARD_VERSION,
            "description": description or f"{module_name}任务模块",
            "author": author,
            "created_date": current_time
        }
        
        # 添加可选字段
        if tags:
            module_info["tags"] = tags
        if category:
            module_info["category"] = category
        
        # 构建工作流元数据
        metadata = {
            "created_date": current_time,
            "engine_version": cls.ENGINE_VERSION,
            "module_versions": {}
        }
        
        # 添加生成器信息
        if generated_by:
            metadata["generated_by"] = generated_by
            if generated_by == "operation_recorder":
                metadata["total_operations"] = len(cards) - 1  # 减去起点卡片
        
        # 合并额外的元数据
        if additional_metadata:
            metadata.update(additional_metadata)
        
        # 构建标准模块数据
        module_data = {
            "module_info": module_info,
            "workflow": {
                "cards": cards,
                "connections": connections,
                "metadata": metadata
            }
        }
        
        return module_data
    
    @classmethod
    def create_from_workflow_data(cls,
                                 workflow_data: Dict[str, Any],
                                 module_name: str,
                                 description: str = None,
                                 author: str = "用户") -> Dict[str, Any]:
        """
        从工作流数据创建模块数据
        
        Args:
            workflow_data: 包含cards、connections等的工作流数据
            module_name: 模块名称
            description: 模块描述
            author: 作者
            
        Returns:
            标准格式的模块数据字典
        """
        cards = workflow_data.get("cards", [])
        connections = workflow_data.get("connections", [])
        
        # 保留原有的元数据，但确保必需字段存在
        existing_metadata = workflow_data.get("metadata", {})
        additional_metadata = existing_metadata.copy()
        
        # 保留视图相关信息
        if "view_transform" in workflow_data:
            additional_metadata["view_transform"] = workflow_data["view_transform"]
        if "view_center" in workflow_data:
            additional_metadata["view_center"] = workflow_data["view_center"]
        
        return cls.create_module_data(
            cards=cards,
            connections=connections,
            module_name=module_name,
            description=description,
            author=author,
            additional_metadata=additional_metadata
        )
    
    @classmethod
    def validate_module_format(cls, module_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证模块格式是否符合标准
        
        Args:
            module_data: 模块数据字典
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 检查顶级结构
            if "module_info" not in module_data:
                return False, "缺少 module_info 字段"
            
            if "workflow" not in module_data:
                return False, "缺少 workflow 字段"
            
            # 检查 module_info 结构
            module_info = module_data["module_info"]
            required_info_fields = ["name", "version", "description", "author", "created_date"]
            
            for field in required_info_fields:
                if field not in module_info:
                    return False, f"module_info 缺少必需字段: {field}"
            
            # 检查 workflow 结构
            workflow = module_data["workflow"]
            required_workflow_fields = ["cards", "connections"]
            
            for field in required_workflow_fields:
                if field not in workflow:
                    return False, f"workflow 缺少必需字段: {field}"
            
            # 检查数据类型
            if not isinstance(workflow["cards"], list):
                return False, "workflow.cards 必须是列表类型"
            
            if not isinstance(workflow["connections"], list):
                return False, "workflow.connections 必须是列表类型"
            
            # 检查是否有起点卡片
            cards = workflow["cards"]
            if not cards:
                return False, "工作流中没有卡片"
            
            has_start_card = any(card.get("task_type") == "起点" for card in cards)
            if not has_start_card:
                return False, "工作流中缺少起点卡片"
            
            # 检查卡片ID唯一性
            card_ids = [card.get("id") for card in cards if "id" in card]
            if len(card_ids) != len(set(card_ids)):
                return False, "卡片ID不唯一"
            
            return True, "格式验证通过"
            
        except Exception as e:
            return False, f"验证过程中出现异常: {str(e)}"
    
    @classmethod
    def save_module_file(cls, 
                        module_data: Dict[str, Any], 
                        file_path: str,
                        validate: bool = True) -> bool:
        """
        保存模块文件
        
        Args:
            module_data: 模块数据
            file_path: 文件路径
            validate: 是否验证格式
            
        Returns:
            是否保存成功
        """
        try:
            # 验证格式
            if validate:
                is_valid, error_msg = cls.validate_module_format(module_data)
                if not is_valid:
                    logger.error(f"模块格式验证失败: {error_msg}")
                    return False
            
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(module_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"模块文件已保存到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存模块文件失败: {e}")
            return False
    
    @classmethod
    def load_module_file(cls, file_path: str) -> tuple[bool, Dict[str, Any], str]:
        """
        加载模块文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            (是否成功, 模块数据, 错误信息)
        """
        try:
            if not os.path.exists(file_path):
                return False, {}, f"文件不存在: {file_path}"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                module_data = json.load(f)
            
            # 验证格式
            is_valid, error_msg = cls.validate_module_format(module_data)
            if not is_valid:
                return False, {}, f"模块格式无效: {error_msg}"
            
            return True, module_data, "加载成功"
            
        except json.JSONDecodeError as e:
            return False, {}, f"JSON格式错误: {str(e)}"
        except Exception as e:
            return False, {}, f"加载失败: {str(e)}"
    
    @classmethod
    def convert_old_format(cls, old_data: Dict[str, Any], module_name: str = None) -> Dict[str, Any]:
        """
        转换旧格式的模块数据为新格式
        
        Args:
            old_data: 旧格式的数据
            module_name: 模块名称（如果旧数据中没有）
            
        Returns:
            新格式的模块数据
        """
        # 如果已经是新格式，直接返回
        if "module_info" in old_data and "workflow" in old_data:
            return old_data
        
        # 转换旧格式
        if "cards" in old_data:
            # 旧格式直接包含cards
            cards = old_data.get("cards", [])
            connections = old_data.get("connections", [])
            
            # 提取其他字段作为元数据
            additional_metadata = {}
            for key, value in old_data.items():
                if key not in ["cards", "connections"]:
                    additional_metadata[key] = value
            
            # 生成模块名称
            if not module_name:
                module_name = "转换的模块"
            
            return cls.create_module_data(
                cards=cards,
                connections=connections,
                module_name=module_name,
                description="从旧格式转换的任务模块",
                additional_metadata=additional_metadata
            )
        
        # 无法识别的格式
        raise ValueError("无法识别的模块数据格式")


# 便捷函数
def create_standard_module_data(cards: List[Dict[str, Any]], 
                               connections: List[Dict[str, Any]],
                               module_name: str,
                               **kwargs) -> Dict[str, Any]:
    """创建标准格式的模块数据的便捷函数"""
    return ModuleFormatStandard.create_module_data(cards, connections, module_name, **kwargs)


def validate_module_file(file_path: str) -> tuple[bool, str]:
    """验证模块文件格式的便捷函数"""
    success, module_data, error_msg = ModuleFormatStandard.load_module_file(file_path)
    if success:
        return True, "文件格式正确"
    else:
        return False, error_msg
