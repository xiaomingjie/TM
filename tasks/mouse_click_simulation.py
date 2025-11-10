# -*- coding: utf-8 -*-

"""
模拟鼠标操作任务模块
整合了鼠标点击、滚轮操作和旋转视角功能，通过下拉选择区分不同的操作模式
"""

import logging
import os
import random
import threading
import time
from typing import Dict, Any, Optional, Tuple, List
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 使用统一的延迟处理
from .task_utils import handle_next_step_delay as _handle_next_step_delay

# 导入截图助手和驱动（方案三：保留截图，移除输入操作）
from utils.screenshot_helper import get_screen_size, take_screenshot_opencv
from utils.interception_driver import get_driver

# _interruptible_sleep 函数已移至 task_utils.py

def safe_imread(image_path, flags=cv2.IMREAD_COLOR):
    """安全的图像读取函数，支持中文路径"""
    try:
        # 使用numpy fromfile + imdecode处理中文路径
        img_array = np.fromfile(image_path, dtype=np.uint8)
        if len(img_array) > 0:
            img = cv2.imdecode(img_array, flags)
            if img is not None:
                return img

        # 备选方法：直接读取
        img = cv2.imread(image_path, flags)
        if img is not None:
            return img

        return None
    except Exception as e:
        logger.error(f"安全图像读取失败 {image_path}: {e}")
        return None

# 任务类型标识
TASK_TYPE = "模拟鼠标操作"
TASK_NAME = "模拟鼠标操作"

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """获取参数定义"""
    return {
        # 操作模式选择
        "operation_mode": {
            "label": "操作模式",
            "type": "select",
            "options": ["坐标点击", "图片点击", "文字点击", "鼠标滚轮", "旋转视角", "鼠标拖拽"],
            "default": "坐标点击",
            "tooltip": "选择鼠标操作模式 (注意: 拖拽功能仅支持模拟器)"
        },

        # 图片点击相关参数
        "---image_click_params---": {
            "type": "separator",
            "label": "图片点击参数",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },
        "multi_image_mode": {
            "label": "多图识别模式",
            "type": "select",
            "options": ["单图识别", "多图识别"],
            "default": "单图识别",
            "tooltip": "单图识别：只配置一张图片；多图识别：配置多张图片进行识别",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },
        "enable_parallel_recognition": {
            "label": "启用并行识别",
            "type": "checkbox",
            "default": True,
            "tooltip": "启用：多张图片并行识别，速度提升3-5倍；禁用：传统串行识别",
            "condition": [
                {"param": "operation_mode", "value": "图片点击"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        "image_path": {
            "label": "目标图片路径",
            "type": "file",
            "default": "",
            "tooltip": "需要查找并点击的图片文件",
            "condition": [
                {"param": "operation_mode", "value": "图片点击"},
                {"param": "multi_image_mode", "value": "单图识别"}
            ]
        },
        "image_paths": {
            "label": "多图片路径",
            "type": "text",
            "default": "",
            "tooltip": "多张图片路径，每行一个路径。支持相对路径和绝对路径",
            "multiline": True,
            "condition": [
                {"param": "operation_mode", "value": "图片点击"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        "click_all_found": {
            "label": "全部点击",
            "type": "bool",
            "default": False,
            "tooltip": "启用：点击所有识别成功的图片；禁用：只点击第一张识别成功的图片",
            "condition": [
                {"param": "operation_mode", "value": "图片点击"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        "clear_clicked_on_next_run": {
            "label": "下次执行清除已点击记录",
            "type": "bool",
            "default": False,
            "tooltip": "启用：下次执行时清除已点击的图片记录；禁用：保持已点击记录直到全部完成",
            "condition": [
                {"param": "operation_mode", "value": "图片点击"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        "multi_image_delay": {
            "label": "每张图片识别延迟",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 10.0,
            "decimals": 1,
            "tooltip": "每张图片识别点击后的延迟时间（秒），防止速度过快导致图片识别失败",
            "condition": [
                {"param": "operation_mode", "value": "图片点击"},
                {"param": "multi_image_mode", "value": "多图识别"}
            ]
        },
        "confidence": {
            "label": "查找置信度",
            "type": "float",
            "default": 0.6,
            "min": 0.1,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "图片匹配的相似度阈值 (0.1 到 1.0)",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },
        "preprocessing_method": {
            "label": "预处理方法",
            "type": "select",
            "options": ["无", "灰度化", "透明图片处理"],
            "default": "无",
            "tooltip": "在查找图片前对其进行的预处理操作",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },
        "search_scope": {
            "label": "搜索范围",
            "type": "select",
            "options": ["绑定窗口", "全屏搜索", "智能搜索"],
            "default": "绑定窗口",
            "tooltip": "绑定窗口：仅在绑定窗口内搜索；全屏搜索：在整个屏幕范围搜索；智能搜索：先在绑定窗口内搜索，失败后自动使用多种策略搜索",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },

        # 文字点击相关参数
        "---text_click_params---": {
            "type": "separator",
            "label": "文字点击参数",
            "condition": {"param": "operation_mode", "value": "文字点击"}
        },
        "text_selection_strategy": {
            "label": "文字选择策略",
            "type": "select",
            "options": ["使用OCR目标文字"],
            "default": "使用OCR目标文字",
            "tooltip": "自动使用OCR识别卡片设置的目标文字进行点击",
            "condition": {"param": "operation_mode", "value": "文字点击"}
        },

        "text_match_mode": {
            "label": "文字匹配模式",
            "type": "select",
            "options": ["包含", "完全匹配"],
            "default": "包含",
            "tooltip": "文字匹配的方式\n包含：目标文字包含在识别文字中即可\n完全匹配：识别文字必须与目标文字完全一致",
            "condition": {"param": "operation_mode", "value": "文字点击"}
        },
        "text_position_mode": {
            "label": "点击位置",
            "type": "select",
            "options": ["文字中心", "文字左上角", "文字右下角", "自定义偏移"],
            "default": "文字中心",
            "tooltip": "在文字区域的哪个位置进行点击",
            "condition": {"param": "operation_mode", "value": "文字点击"}
        },
        "text_offset_x": {
            "label": "X轴偏移",
            "type": "int",
            "default": 0,
            "tooltip": "相对于文字位置的X轴偏移量（像素）",
            "condition": {"param": "text_position_mode", "value": "自定义偏移"}
        },
        "text_offset_y": {
            "label": "Y轴偏移",
            "type": "int",
            "default": 0,
            "tooltip": "相对于文字位置的Y轴偏移量（像素）",
            "condition": {"param": "text_position_mode", "value": "自定义偏移"}
        },

        # 坐标点击相关参数
        "---coordinate_click_params---": {
            "type": "separator",
            "label": "坐标点击参数",
            "condition": {"param": "operation_mode", "value": "坐标点击"}
        },
        "coordinate_x": {
            "label": "X坐标",
            "type": "int",
            "default": 0,
            "min": 0,
            "tooltip": "点击位置的X坐标",
            "condition": {"param": "operation_mode", "value": "坐标点击"}
        },
        "coordinate_y": {
            "label": "Y坐标",
            "type": "int",
            "default": 0,
            "min": 0,
            "tooltip": "点击位置的Y坐标",
            "condition": {"param": "operation_mode", "value": "坐标点击"}
        },
        "coordinate_selector_tool": {
            "label": "坐标获取工具",
            "type": "button",
            "button_text": "点击获取坐标",
            "tooltip": "点击后可以在目标窗口中选择坐标位置",
            "condition": {"param": "operation_mode", "value": "坐标点击"},
            "widget_hint": "coordinate_selector"
        },
        "coordinate_mode": {
            "label": "坐标模式",
            "type": "select",
            "options": ["客户区坐标", "屏幕坐标"],
            "default": "客户区坐标",
            "tooltip": "客户区坐标相对于窗口内容区域，屏幕坐标相对于整个屏幕",
            "condition": {"param": "operation_mode", "value": "坐标点击"}
        },
        "disable_random_offset": {
            "label": "禁止随机偏移",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后使用绝对坐标，不使用±5随机偏移",
            "condition": {"param": "operation_mode", "value": ["坐标点击", "文字点击"]}
        },

        # 鼠标滚轮相关参数
        "---scroll_params---": {
            "type": "separator",
            "label": "鼠标滚轮参数",
            "condition": {"param": "operation_mode", "value": "鼠标滚轮"}
        },
        "scroll_direction": {
            "label": "滚动方向",
            "type": "select",
            "options": ["向上", "向下"],
            "default": "向下",
            "tooltip": "鼠标滚轮的滚动方向",
            "condition": {"param": "operation_mode", "value": "鼠标滚轮"}
        },
        "scroll_clicks": {
            "label": "滚动次数",
            "type": "int",
            "default": 3,
            "min": 1,
            "max": 20,
            "tooltip": "滚轮滚动的次数",
            "condition": {"param": "operation_mode", "value": "鼠标滚轮"}
        },
        "scroll_coordinate_selector": {
            "label": "坐标获取工具",
            "type": "button",
            "button_text": "点击获取坐标",
            "tooltip": "点击选择滚轮操作的起始坐标位置",
            "widget_hint": "coordinate_selector",
            "condition": {"param": "operation_mode", "value": "鼠标滚轮"}
        },
        "scroll_start_position": {
            "label": "滚动起始位置",
            "type": "text",
            "default": "500,300",
            "tooltip": "执行滚轮操作的起始坐标位置",
            "readonly": True,
            "condition": {"param": "operation_mode", "value": "鼠标滚轮"}
        },

        # 旋转视角相关参数
        "---rotate_params---": {
            "type": "separator",
            "label": "旋转视角参数（<span style='color: red;'>前台模式，后台模式无效</span>）",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "rotate_mouse_button": {
            "label": "使用鼠标按键",
            "type": "select",
            "options": ["左键", "右键", "中键"],
            "default": "左键",
            "tooltip": "按住哪个鼠标按键进行拖动",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "rotate_direction": {
            "label": "旋转方向",
            "type": "select",
            "options": ["左转", "右转", "上转", "下转"],
            "default": "右转",
            "tooltip": "视角旋转的方向",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "rotate_distance": {
            "label": "旋转距离 (像素)",
            "type": "int",
            "default": 200,
            "min": 50,
            "max": 800,
            "tooltip": "鼠标拖拽的像素距离，影响旋转幅度",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "rotate_duration": {
            "label": "旋转时长 (秒)",
            "type": "float",
            "default": 1.5,
            "min": 0.3,
            "max": 5.0,
            "decimals": 1,
            "tooltip": "旋转动画的持续时间，越长越平滑",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },


        # 图片识别参数
        "---rotate_recognition---": {
            "type": "separator",
            "label": "实时图片识别 (旋转期间持续检测)",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "enable_rotate_recognition": {
            "label": "启用图片识别停止",
            "type": "bool",
            "default": False,
            "tooltip": "启用后，旋转期间会实时检测目标图片，找到后立即停止旋转",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "rotate_target_image": {
            "label": "目标图片",
            "type": "file",
            "file_types": ["图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff)", "所有文件 (*.*)"],
            "tooltip": "要识别的目标图片文件",
            "condition": {
                "param": "operation_mode", "value": "旋转视角",
                "param2": "enable_rotate_recognition", "value2": True
            }
        },
        "rotate_image_confidence": {
            "label": "识别置信度",
            "type": "float",
            "default": 0.8,
            "min": 0.1,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "图片匹配的相似度阈值 (0.1-1.0)，越高越严格",
            "condition": {
                "param": "operation_mode", "value": "旋转视角",
                "param2": "enable_rotate_recognition", "value2": True
            }
        },
        "rotate_recognition_interval": {
            "label": "检测间隔 (毫秒)",
            "type": "int",
            "default": 50,
            "min": 20,
            "max": 200,
            "tooltip": "图片识别的检查间隔，越小检测越频繁但消耗更多性能",
            "condition": {
                "param": "operation_mode", "value": "旋转视角",
                "param2": "enable_rotate_recognition", "value2": True
            }
        },
        "enable_rotate_recognition": {
            "label": "启用图像识别停止",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后，旋转时会持续查找指定图像，找到即停止",
            "condition": {"param": "operation_mode", "value": "旋转视角"}
        },
        "rotate_target_image": {
            "label": "目标图像",
            "type": "file",
            "default": "",
            "tooltip": "要查找的图像文件路径",
            "condition": {"param": "enable_rotate_recognition", "value": True}
        },
        "rotate_image_confidence": {
            "label": "图像识别置信度",
            "type": "float",
            "default": 0.8,
            "min": 0.1,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "图像匹配的相似度阈值",
            "condition": {"param": "enable_rotate_recognition", "value": True}
        },
        "rotate_preprocessing_method": {
            "label": "预处理方法",
            "type": "select",
            "options": ["无", "灰度化", "透明图片处理"],
            "default": "无",
            "tooltip": "在查找图片前对其进行的预处理操作",
            "condition": {"param": "enable_rotate_recognition", "value": True}
        },

        # 鼠标拖拽相关参数
        "---drag_params---": {
            "type": "separator",
            "label": "鼠标拖拽参数（<span style='color: red;'>模拟器窗口前台/后台一致，普通窗口不支持</span>）",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_direction": {
            "label": "拖拽方向",
            "type": "select",
            "options": ["向右", "向左", "向上", "向下", "右上", "右下", "左上", "左下"],
            "default": "向右",
            "tooltip": "拖拽的方向",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_distance": {
            "label": "拖拽距离(像素)",
            "type": "int",
            "default": 100,
            "min": 1,
            "max": 1000,
            "tooltip": "拖拽的距离",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_coordinate_selector": {
            "label": "坐标获取工具",
            "type": "button",
            "button_text": "点击获取坐标",
            "tooltip": "点击选择拖拽操作的起始坐标位置",
            "widget_hint": "coordinate_selector",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_start_position": {
            "label": "拖拽起始位置",
            "type": "text",
            "default": "500,300",
            "tooltip": "执行拖拽操作的起始坐标位置",
            "readonly": True,
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_button": {
            "label": "拖拽按钮",
            "type": "select",
            "options": ["左键", "右键", "中键"],
            "default": "左键",
            "tooltip": "拖拽时使用的鼠标按钮",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_duration": {
            "label": "拖拽持续时间(秒)",
            "type": "float",
            "default": 1.0,
            "min": 0.1,
            "max": 10.0,
            "step": 0.1,
            "decimals": 1,
            "tooltip": "完成拖拽操作的时间",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_smoothness": {
            "label": "拖拽平滑度",
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 100,
            "tooltip": "拖拽轨迹的平滑程度，数值越大越平滑",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "drag_mode": {
            "label": "拖拽模式",
            "type": "select",
            "options": ["简单拖拽", "多点路径拖拽"],
            "default": "简单拖拽",
            "tooltip": "简单拖拽: 直线移动\n多点路径: 沿复杂路径",
            "condition": {"param": "operation_mode", "value": "鼠标拖拽"}
        },
        "path_points": {
            "label": "路径点坐标",
            "type": "textarea",
            "default": "100,100\n200,150\n300,200\n400,250",
            "tooltip": "每行一个坐标: x,y\n如: 100,100",
            "rows": 8,
            "condition": {
                "param": "operation_mode",
                "value": "鼠标拖拽",
                "and": {"param": "drag_mode", "value": "多点路径拖拽"}
            }
        },

        # 通用点击参数（仅点击模式显示）
        "---common_click_params---": {
            "type": "separator",
            "label": "点击参数",
            "condition": {"param": "operation_mode", "value": ["图片点击", "坐标点击", "文字点击"]}
        },
        "button": {
            "label": "鼠标按钮",
            "type": "select",
            "options": ["左键", "右键", "中键"],
            "default": "左键",
            "tooltip": "要使用的鼠标按钮",
            "condition": {"param": "operation_mode", "value": ["图片点击", "坐标点击", "文字点击"]}
        },
        "clicks": {
            "label": "点击次数",
            "type": "int",
            "default": 1,
            "min": 1,
            "tooltip": "连续点击的次数",
            "condition": {"param": "operation_mode", "value": ["图片点击", "坐标点击", "文字点击"]}
        },
        "interval": {
            "label": "点击间隔(秒)",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "decimals": 2,
            "tooltip": "多次点击之间的间隔时间",
            "condition": {"param": "operation_mode", "value": ["图片点击", "坐标点击", "文字点击"]}
        },
        "random_offset": {
            "label": "随机偏移(像素)",
            "type": "int",
            "default": 5,
            "min": 0,
            "max": 50,
            "tooltip": "点击位置的随机偏移范围，增加真实性",
            "condition": {"param": "operation_mode", "value": ["图片点击", "坐标点击", "文字点击"]}
        },

        # 重试机制（仅图片点击）
        "---retry_params---": {
            "type": "separator",
            "label": "重试设置",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },
        "enable_retry": {
            "label": "启用失败重试",
            "type": "bool",
            "default": False,
            "tooltip": "如果查找失败，是否进行重试（仅图片点击模式）",
            "condition": {"param": "operation_mode", "value": "图片点击"}
        },
        "retry_attempts": {
            "label": "重试次数",
            "type": "int",
            "default": 3,
            "min": 1,
            "max": 10,
            "tooltip": "最大重试次数",
            "condition": {"param": "enable_retry", "value": True}
        },
        "retry_interval": {
            "label": "重试间隔(秒)",
            "type": "float",
            "default": 0.5,
            "min": 0.1,
            "decimals": 2,
            "tooltip": "重试之间的等待时间",
            "condition": {"param": "enable_retry", "value": True}
        },

        # 下一步延迟执行参数
        "---next_step_delay---": {"type": "separator", "label": "下一步延迟执行"},
        "enable_next_step_delay": {
            "label": "启用下一步延迟执行",
            "type": "bool",
            "default": False,
            "tooltip": "勾选后，执行完当前操作会等待指定时间再执行下一步"
        },
        "delay_mode": {
            "label": "延迟模式",
            "type": "select",
            "options": ["固定延迟", "随机延迟"],
            "default": "固定延迟",
            "tooltip": "选择固定延迟时间还是随机延迟时间",
            "condition": {"param": "enable_next_step_delay", "value": True}
        },
        "fixed_delay": {
            "label": "固定延迟 (秒)",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置固定的延迟时间",
            "condition": {"param": "delay_mode", "value": "固定延迟"}
        },
        "min_delay": {
            "label": "最小延迟 (秒)",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置随机延迟的最小值",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        },
        "max_delay": {
            "label": "最大延迟 (秒)",
            "type": "float",
            "default": 2.0,
            "min": 0.0,
            "max": 3600.0,
            "step": 0.1,
            "decimals": 2,
            "tooltip": "设置随机延迟的最大值",
            "condition": {"param": "delay_mode", "value": "随机延迟"}
        },

        # 执行后操作
        "---post_execute---": {"type": "separator", "label": "执行后操作"},
        "on_success": {
            "label": "成功后操作",
            "type": "select",
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "点击成功后的操作"
        },
        "success_jump_target_id": {
            "label": "成功跳转目标ID",
            "type": "int",
            "default": 0,
            "min": 0,
            "widget_hint": "card_selector",
            "condition": {"param": "on_success", "value": "跳转到步骤"}
        },
        "on_failure": {
            "label": "失败后操作",
            "type": "select",
            "options": ["继续执行本步骤", "执行下一步", "跳转到步骤", "停止工作流"],
            "default": "执行下一步",
            "tooltip": "点击失败后的操作"
        },
        "failure_jump_target_id": {
            "label": "失败跳转目标ID",
            "type": "int",
            "default": 0,
            "min": 0,
            "widget_hint": "card_selector",
            "condition": {"param": "on_failure", "value": "跳转到步骤"}
        }
    }

def _handle_success(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理成功情况"""
    if action == "跳转到步骤" and jump_id is not None:
        logger.info(f"点击成功，跳转到步骤 {jump_id}")
        return True, "跳转到步骤", jump_id
    elif action == "停止工作流":
        logger.info("点击成功，停止工作流")
        return True, "停止工作流", None
    elif action == "继续执行本步骤":
        logger.info("点击成功，继续执行本步骤")
        return True, "继续执行本步骤", card_id
    else:  # "执行下一步"
        logger.info("点击成功，继续执行下一步")
        return True, "执行下一步", None

def _handle_failure(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理失败情况"""
    if action == "跳转到步骤" and jump_id is not None:
        logger.warning(f"点击失败，跳转到步骤 {jump_id}")
        return False, "跳转到步骤", jump_id
    elif action == "停止工作流":
        logger.warning("点击失败，停止工作流")
        return False, "停止工作流", None
    elif action == "继续执行本步骤":
        logger.warning("点击失败，继续执行本步骤")
        return False, "继续执行本步骤", card_id
    else:  # "执行下一步"
        logger.warning("点击失败，继续执行下一步")
        return False, "执行下一步", None

def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
                target_hwnd: Optional[int], window_region: Optional[tuple], card_id: Optional[int],
                get_image_data=None, **kwargs) -> Tuple[bool, str, Optional[int]]:
    """执行模拟鼠标操作任务 - execute_task 接口"""
    return execute(params, counters, execution_mode, target_hwnd, card_id, get_image_data, kwargs.get('stop_checker'))

def execute(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
           target_hwnd: Optional[int], card_id: Optional[int], get_image_data=None, stop_checker=None) -> Tuple[bool, str, Optional[int]]:
    """执行模拟鼠标操作任务"""

    # 获取基本参数
    operation_mode = params.get('operation_mode', '')

    # 刷新 向后兼容：根据旧任务类型自动推断操作模式
    task_type = params.get('task_type', '')

    # 优先根据任务类型推断操作模式
    if task_type == '查找图片并点击':
        operation_mode = '图片点击'
    elif task_type == '点击指定坐标':
        operation_mode = '坐标点击'
    elif task_type == '鼠标滚轮操作':
        operation_mode = '鼠标滚轮'
    elif task_type == '旋转视角':
        operation_mode = '旋转视角'
    elif not operation_mode:
        # 如果没有指定操作模式，根据参数推断
        if params.get('image_path'):
            operation_mode = '图片点击'
        elif 'coordinate_x' in params and 'coordinate_y' in params:
            operation_mode = '坐标点击'
        elif params.get('scroll_direction'):
            operation_mode = '鼠标滚轮'
        elif params.get('rotate_direction'):
            operation_mode = '旋转视角'
        else:
            # 默认为图片点击
            operation_mode = '图片点击'

    on_success_action = params.get('on_success', '执行下一步')
    success_jump_id = params.get('success_jump_target_id')
    on_failure_action = params.get('on_failure', '执行下一步')
    failure_jump_id = params.get('failure_jump_target_id')

    logger.info(f"开始执行模拟鼠标操作任务，模式: {operation_mode} (任务类型: {task_type})")
    logger.info(f"跳转参数: 成功动作={on_success_action}, 成功跳转ID={success_jump_id}, 失败动作={on_failure_action}, 失败跳转ID={failure_jump_id}")

    try:
        # 执行具体操作
        if operation_mode == "图片点击":
            # 执行图片点击
            success, action, next_id = _execute_image_click(params, execution_mode, target_hwnd, card_id, get_image_data,
                                      on_success_action, success_jump_id, on_failure_action, failure_jump_id)
        elif operation_mode == "坐标点击":
            # 执行坐标点击
            success, action, next_id = _execute_coordinate_click(params, execution_mode, target_hwnd, card_id,
                                           on_success_action, success_jump_id, on_failure_action, failure_jump_id)
        elif operation_mode == "文字点击":
            # 执行文字点击
            success, action, next_id = _execute_text_click(params, execution_mode, target_hwnd, card_id,
                                              on_success_action, success_jump_id, on_failure_action, failure_jump_id)
        elif operation_mode == "鼠标滚轮":
            # 执行鼠标滚轮操作
            success, action, next_id = _execute_mouse_scroll(params, execution_mode, target_hwnd, card_id,
                                        on_success_action, success_jump_id, on_failure_action, failure_jump_id)
        elif operation_mode == "旋转视角":
            # 执行旋转视角操作
            success, action, next_id = _execute_rotate_view(params, execution_mode, target_hwnd, card_id,
                                       on_success_action, success_jump_id, on_failure_action, failure_jump_id)
        elif operation_mode == "鼠标拖拽":
            # 执行鼠标拖拽操作
            success, action, next_id = _execute_mouse_drag(params, execution_mode, target_hwnd, card_id,
                                      on_success_action, success_jump_id, on_failure_action, failure_jump_id)
        else:
            logger.error(f"未知的操作模式: {operation_mode}")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 处理下一步延迟执行（只在跳转到步骤或执行下一步时应用）
        if success and params.get('enable_next_step_delay', False):
            logger.info(f"延迟检查: success={success}, enable_next_step_delay={params.get('enable_next_step_delay')}, action={action}")
            # 支持中文和英文动作名称
            if action in ['continue', 'jump', '执行下一步', '跳转到步骤']:
                logger.info(f"开始执行下一步延迟，动作类型: {action}")
                _handle_next_step_delay(params, stop_checker)
            else:
                logger.info(f"跳过延迟，动作类型不匹配: {action}")
        else:
            logger.info(f"跳过延迟: success={success}, enable_next_step_delay={params.get('enable_next_step_delay', False)}")

        logger.info(f"模拟鼠标操作最终返回: success={success}, action={action}, next_id={next_id}")
        return success, action, next_id

    except Exception as e:
        logger.error(f"执行模拟鼠标操作任务时发生异常: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_image_click(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                        card_id: Optional[int], get_image_data, on_success_action: str,
                        success_jump_id: Optional[int], on_failure_action: str,
                        failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行图片点击"""
    # 检查是否为多图识别模式
    multi_image_mode = params.get('multi_image_mode', '单图识别')

    if multi_image_mode == '多图识别':
        return _execute_multi_image_click(params, execution_mode, target_hwnd, card_id, get_image_data,
                                        on_success_action, success_jump_id, on_failure_action, failure_jump_id)
    else:
        return _execute_single_image_click(params, execution_mode, target_hwnd, card_id, get_image_data,
                                         on_success_action, success_jump_id, on_failure_action, failure_jump_id)

def _execute_single_image_click(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                               card_id: Optional[int], get_image_data, on_success_action: str,
                               success_jump_id: Optional[int], on_failure_action: str,
                               failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行单图片点击"""
    # 导入图片点击模块
    try:
        from tasks.find_image_and_click import execute_task as execute_image_click
        
        # 构造图片点击的参数
        image_params = {
            'image_path': params.get('image_path', ''),
            'confidence': params.get('confidence', 0.6),
            'preprocessing_method': params.get('preprocessing_method', '无'),
            'search_scope': params.get('search_scope', '智能搜索'),
            'button': params.get('button', '左键'),
            'clicks': params.get('clicks', 1),
            'interval': params.get('interval', 0.1),
            'enable_retry': params.get('enable_retry', False),
            'retry_attempts': params.get('retry_attempts', 3),
            'retry_interval': params.get('retry_interval', 0.5),
            'on_success': on_success_action,
            'success_jump_target_id': success_jump_id,
            'on_failure': on_failure_action,
            'failure_jump_target_id': failure_jump_id
        }
        
        # 只显示图片名称，不显示完整路径
        image_path = params.get('image_path', '')
        if image_path.startswith('memory://'):
            image_name = image_path.replace('memory://', '')
        else:
            image_name = os.path.basename(image_path) if image_path else ''
        logger.info(f"执行单图片点击: {image_name}")
        return execute_image_click(image_params, {}, execution_mode, target_hwnd, None, card_id, get_image_data=get_image_data)

    except Exception as e:
        logger.error(f"执行单图片点击时发生错误: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _is_ldplayer_window(hwnd: Optional[int]) -> bool:
    """检测是否为雷电模拟器窗口 - 使用新的检测器"""
    if not hwnd:
        return False

    try:
        # 使用新的模拟器检测器
        from utils.emulator_detector import detect_emulator_type
        is_emulator, emulator_type, description = detect_emulator_type(hwnd)

        # 检查是否为雷电模拟器或其他模拟器
        if is_emulator and emulator_type in ["ldplayer", "therender"]:
            logger.debug(f"检测到模拟器: {description}")
            return True

        # 回退到原有检测方法
        import win32gui
        class_name = win32gui.GetClassName(hwnd)
        window_title = win32gui.GetWindowText(hwnd)

        return (class_name == "RenderWindow" or
                "TheRender" in window_title or
                "雷电" in window_title or
                "LDPlayer" in window_title)
    except Exception as e:
        logger.debug(f"检测模拟器窗口失败: {e}")
        return False



def _execute_multi_image_click(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                              card_id: Optional[int], get_image_data, on_success_action: str,
                              success_jump_id: Optional[int], on_failure_action: str,
                              failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行多图片点击"""
    import time  # 确保time模块可用

    # 检查是否启用并行识别优化
    enable_parallel = params.get('enable_parallel_recognition', True)

    if enable_parallel:
        try:
            # 使用优化的并行识别模块
            from tasks.optimized_multi_image_click import execute_multi_image_click_optimized
            logger.info("[多图识别] 使用并行识别优化模式")
            return execute_multi_image_click_optimized(
                params, execution_mode, target_hwnd, card_id, get_image_data,
                on_success_action, success_jump_id, on_failure_action, failure_jump_id
            )
        except ImportError as e:
            logger.warning(f"[多图识别] 并行识别模块不可用，回退到传统模式: {e}")
        except Exception as e:
            logger.error(f"[多图识别] 并行识别执行失败，回退到传统模式: {e}")

    # 传统串行识别模式（原有逻辑）
    logger.info("[多图识别] 使用传统串行识别模式")
    try:
        from task_workflow.workflow_context import get_workflow_context
        from tasks.find_image_and_click import execute_task as execute_image_click
        import os

        context = get_workflow_context()

        # 获取参数
        image_paths_text = params.get('image_paths', '').strip()
        click_all_found = params.get('click_all_found', False)
        clear_clicked_on_next_run = params.get('clear_clicked_on_next_run', False)

        if not image_paths_text:
            logger.error("多图识别模式下未配置图片路径")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 解析图片路径列表
        raw_image_paths = [path.strip() for path in image_paths_text.split('\n') if path.strip()]
        if not raw_image_paths:
            logger.error("多图识别模式下图片路径列表为空")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 智能纠正图片路径
        image_paths = _correct_image_paths(raw_image_paths, card_id)
        if not image_paths:
            logger.error("多图识别模式下所有图片路径都无效")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        logger.info(f"[多图识别] 开始执行，共{len(image_paths)}张图片，全部点击: {click_all_found}")

        # 处理下次执行清除记录
        if clear_clicked_on_next_run:
            context.set_card_data(card_id, 'clicked_images', set())
            logger.info("[多图识别] 已清除上次点击记录")

        # 获取已点击的图片记录
        clicked_images = context.get_card_data(card_id, 'clicked_images', set())
        if not isinstance(clicked_images, set):
            clicked_images = set(clicked_images) if clicked_images else set()

        logger.info(f"[多图识别] 已点击图片记录: {len(clicked_images)}张")

        if click_all_found:
            # 启用全部点击：只排除已成功的图片，失败的图片需要重新尝试
            success_images = context.get_card_data(card_id, 'success_images', set())
            remaining_images = [path for path in image_paths if path not in success_images]
            logger.info(f"[多图识别] 剩余待识别图片: {len(remaining_images)}张（排除已成功的{len(success_images)}张）")

            if not remaining_images:
                # 所有图片都已成功
                logger.info(f"[多图识别] 启用全部点击，全部{len(image_paths)}张图片都识别并点击成功")
                context.set_card_data(card_id, 'clicked_images', set())
                context.set_card_data(card_id, 'success_images', set())
                logger.info("[多图识别] 全部成功，已清除记忆")
                return _handle_success(on_success_action, success_jump_id, card_id)
        else:
            # 未启用全部点击：排除已尝试过的图片（成功+失败）
            remaining_images = [path for path in image_paths if path not in clicked_images]
            logger.info(f"[多图识别] 剩余待识别图片: {len(remaining_images)}张")

            if not remaining_images:
                # 所有图片都已尝试过且都失败了
                logger.error(f"[多图识别] 未启用全部点击，所有{len(image_paths)}张图片都已尝试且都失败，任务失败")
                context.set_card_data(card_id, 'clicked_images', set())  # 清除记忆
                return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 尝试识别和点击图片
        found_images = []
        clicked_count = 0

        for i, image_path in enumerate(remaining_images):
            # 构建单个图片的参数
            single_image_params = {
                'image_path': image_path,
                'confidence': params.get('confidence', 0.6),
                'preprocessing_method': params.get('preprocessing_method', '无'),
                'search_scope': params.get('search_scope', '智能搜索'),
                'button': params.get('button', '左键'),
                'clicks': params.get('clicks', 1),
                'interval': params.get('interval', 0.1),
                'enable_retry': params.get('enable_retry', False),
                'retry_attempts': params.get('retry_attempts', 3),
                'retry_interval': params.get('retry_interval', 0.5),
                'on_success': '执行下一步',  # 内部处理，不跳转
                'success_jump_target_id': None,
                'on_failure': '执行下一步',  # 内部处理，不跳转
                'failure_jump_target_id': None
            }

            # 显示图片名称
            if image_path.startswith('memory://'):
                image_name = image_path.replace('memory://', '')
            else:
                image_name = os.path.basename(image_path) if image_path else f'图片{i+1}'

            logger.info(f"[多图识别] 尝试识别第{i+1}张图片: {image_name}")

            # 添加详细调试日志
            logger.debug(f"[多图识别调试] 调用execute_image_click参数:")
            logger.debug(f"  - image_path: {single_image_params.get('image_path')}")
            logger.debug(f"  - execution_mode: {execution_mode}")
            logger.debug(f"  - target_hwnd: {target_hwnd}")
            logger.debug(f"  - button: {single_image_params.get('button')}")
            logger.debug(f"  - clicks: {single_image_params.get('clicks')}")

            # 执行单张图片的识别和点击
            success, action, next_id = execute_image_click(single_image_params, {}, execution_mode, target_hwnd, None, card_id, get_image_data=get_image_data)

            # 添加返回值调试日志
            logger.debug(f"[多图识别调试] execute_image_click返回值:")
            logger.debug(f"  - success: {success}")
            logger.debug(f"  - action: {action}")
            logger.debug(f"  - next_id: {next_id}")

            if success:
                logger.info(f"[多图识别] 第{i+1}张图片识别并点击成功: {image_name}")
                found_images.append(image_path)
                clicked_images.add(image_path)
                clicked_count += 1

                # 确保点击操作完成：添加适当延迟
                click_completion_delay = max(0.2, params.get('interval', 0.1))  # 增加最小延迟到200ms
                logger.debug(f"[多图识别] 等待点击操作完成，延迟{click_completion_delay}秒")
                time.sleep(click_completion_delay)

                # 额外验证点击是否真正完成（针对模拟器和后台模式）
                if (execution_mode.startswith('background') or execution_mode.startswith('emulator_')) and target_hwnd:
                    # 检测是否为雷电模拟器
                    is_ldplayer = _is_ldplayer_window(target_hwnd)
                    if is_ldplayer:
                        # 雷电模拟器需要更长的响应时间
                        additional_delay = 0.3  # 增加到300ms
                        logger.debug(f"[多图识别] 雷电模拟器额外响应时间，延迟{additional_delay}秒")
                        time.sleep(additional_delay)

                        # 额外的消息队列清理延迟
                        queue_clear_delay = 0.1
                        logger.debug(f"[多图识别] 消息队列清理延迟，延迟{queue_clear_delay}秒")
                        time.sleep(queue_clear_delay)
                    else:
                        # 其他后台窗口的标准延迟
                        additional_delay = 0.1
                        logger.debug(f"[多图识别] 后台窗口额外响应时间，延迟{additional_delay}秒")
                        time.sleep(additional_delay)

                # 更新已点击记录
                context.set_card_data(card_id, 'clicked_images', clicked_images)

                # 记录成功的图片（用于最终判断）
                success_images = context.get_card_data(card_id, 'success_images', set())
                success_images.add(image_path)
                context.set_card_data(card_id, 'success_images', success_images)

                # 用户自定义的每张图片识别延迟
                multi_image_delay = params.get('multi_image_delay', 1.0)
                if multi_image_delay > 0:
                    logger.debug(f"[多图识别] 用户自定义延迟，延迟{multi_image_delay}秒")
                    time.sleep(multi_image_delay)

                if not click_all_found:
                    # 未启用全部点击：找到第一张成功的就完成任务，清除记忆
                    logger.info("[多图识别] 未启用全部点击，已点击第一张成功识别的图片，任务完成")
                    context.set_card_data(card_id, 'clicked_images', set())  # 清除记忆
                    context.set_card_data(card_id, 'success_images', set())  # 清除成功记录
                    return _handle_success(on_success_action, success_jump_id, card_id)
            else:
                logger.info(f"[多图识别] 第{i+1}张图片识别失败: {image_name}")
                if not click_all_found:
                    # 未启用全部点击：失败的图片加入已点击记录，避免无限重试
                    clicked_images.add(image_path)
                    context.set_card_data(card_id, 'clicked_images', clicked_images)
                # 启用全部点击：失败的图片不加入clicked_images，下次可以重新尝试

            # 在处理下一张图片前添加小延迟，确保当前操作完全完成
            if i < len(remaining_images) - 1:  # 不是最后一张图片
                # 根据窗口类型调整图片间延迟
                if (execution_mode.startswith('background') or execution_mode.startswith('emulator_')) and target_hwnd and _is_ldplayer_window(target_hwnd):
                    inter_image_delay = 0.2  # 雷电模拟器需要更长的图片间延迟
                    logger.debug(f"[多图识别] 雷电模拟器图片间延迟{inter_image_delay}秒")
                else:
                    inter_image_delay = 0.05  # 标准图片间延迟
                    logger.debug(f"[多图识别] 标准图片间延迟{inter_image_delay}秒")
                time.sleep(inter_image_delay)

        # 处理结果
        if click_all_found:
            # 启用全部点击模式
            if found_images:
                # 本轮有图片成功
                remaining_after_click = [path for path in image_paths if path not in clicked_images]
                if remaining_after_click:
                    logger.info(f"[多图识别] 启用全部点击，本轮点击{clicked_count}张，还有{len(remaining_after_click)}张待处理，继续执行本卡片")
                    return True, '继续执行本步骤', card_id
                else:
                    # 所有图片都尝试完毕，检查是否全部成功
                    # 需要从上下文获取所有成功的图片记录
                    all_success_images = context.get_card_data(card_id, 'success_images', set())
                    total_success_count = len(all_success_images)

                    if total_success_count == len(image_paths):
                        # 全部成功
                        logger.info(f"[多图识别] 启用全部点击，全部{len(image_paths)}张图片都识别并点击成功")
                        # 全部成功时可以清除记忆（任务彻底完成）
                        context.set_card_data(card_id, 'clicked_images', set())
                        context.set_card_data(card_id, 'success_images', set())
                        logger.info("[多图识别] 全部成功，已清除记忆")
                        return _handle_success(on_success_action, success_jump_id, card_id)
                    else:
                        # 部分成功，部分失败
                        failed_count = len(image_paths) - total_success_count
                        logger.warning(f"[多图识别] 启用全部点击，成功{total_success_count}张，失败{failed_count}张，按失败跳转")
                        # 部分失败时保持记忆，避免下次重复点击已成功的图片
                        logger.info("[多图识别] 部分失败，保持记忆避免重复点击")
                        return _handle_failure(on_failure_action, failure_jump_id, card_id)
            else:
                # 本轮没有图片成功，检查是否全部失败
                all_success_images = context.get_card_data(card_id, 'success_images', set())
                if len(all_success_images) == 0:
                    # 全部失败：清除记忆，按失败跳转
                    logger.warning(f"[多图识别] 启用全部点击，全部{len(image_paths)}张图片都识别失败，清除记忆，按失败跳转")
                    context.set_card_data(card_id, 'clicked_images', set())
                    context.set_card_data(card_id, 'success_images', set())
                    logger.info("[多图识别] 全部失败，已清除记忆")
                    return _handle_failure(on_failure_action, failure_jump_id, card_id)
                else:
                    # 本轮失败但之前有成功：保持记忆，按失败跳转
                    logger.warning(f"[多图识别] 启用全部点击，本轮所有剩余图片都识别失败，保持记忆，按失败跳转")
                    logger.info("[多图识别] 本轮失败，保持记忆等待下次重试")
                    return _handle_failure(on_failure_action, failure_jump_id, card_id)
        else:
            # 未启用全部点击模式
            if found_images:
                # 不应该到达这里，因为上面已经处理了
                logger.info("[多图识别] 未启用全部点击，有图片成功，任务完成")
                context.set_card_data(card_id, 'clicked_images', set())  # 清除记忆
                context.set_card_data(card_id, 'success_images', set())  # 清除成功记录
                return _handle_success(on_success_action, success_jump_id, card_id)
            else:
                # 检查是否还有其他图片没尝试过
                all_images_tried = len(clicked_images) == len(image_paths)
                if all_images_tried:
                    # 所有图片都尝试过且都失败了，才算真的失败
                    logger.error(f"[多图识别] 未启用全部点击，所有{len(image_paths)}张图片都已尝试且都失败，任务失败")
                    context.set_card_data(card_id, 'clicked_images', set())  # 清除记忆
                    context.set_card_data(card_id, 'success_images', set())  # 清除成功记录
                    return _handle_failure(on_failure_action, failure_jump_id, card_id)
                else:
                    # 还有其他图片没尝试过，继续尝试
                    untried_count = len(image_paths) - len(clicked_images)
                    logger.info(f"[多图识别] 未启用全部点击，本轮{len(remaining_images)}张失败，还有{untried_count}张未尝试，继续执行本卡片")
                    return True, '继续执行本步骤', card_id

    except Exception as e:
        logger.error(f"执行多图片点击时发生错误: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_coordinate_click(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                             card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                             on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行坐标点击"""
    # 导入坐标点击模块
    try:
        from tasks.click_coordinate import execute_task as execute_coordinate_click
        
        # 构造坐标点击的参数
        disable_random_offset = params.get('disable_random_offset', False)
        random_offset = 0 if disable_random_offset else params.get('random_offset', 5)

        coordinate_params = {
            'coordinate_x': params.get('coordinate_x', 0),
            'coordinate_y': params.get('coordinate_y', 0),
            'coordinate_mode': params.get('coordinate_mode', '客户区坐标'),
            'button': params.get('button', '左键'),
            'clicks': params.get('clicks', 1),
            'interval': params.get('interval', 0.1),
            'disable_random_offset': disable_random_offset,
            'random_offset': random_offset,
            'on_success': on_success_action,
            'success_jump_target_id': success_jump_id,
            'on_failure': on_failure_action,
            'failure_jump_target_id': failure_jump_id
        }
        
        logger.info(f"执行坐标点击: ({params.get('coordinate_x', 0)}, {params.get('coordinate_y', 0)}), 随机偏移: {'禁用' if disable_random_offset else '启用'}")
        return execute_coordinate_click(coordinate_params, {}, execution_mode, target_hwnd, None, card_id)
        
    except Exception as e:
        logger.error(f"执行坐标点击时发生错误: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_text_click(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                       card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                       on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行文字点击"""
    try:
        from tasks.click_coordinate import execute_task as execute_coordinate_click

        # 获取文字位置参数
        text_selection_strategy = params.get('text_selection_strategy', '使用OCR目标文字')
        text_match_mode = params.get('text_match_mode', '包含')
        text_position_mode = params.get('text_position_mode', '文字中心')
        text_offset_x = params.get('text_offset_x', 0)
        text_offset_y = params.get('text_offset_y', 0)

        logger.info(f"执行文字点击: 选择策略={text_selection_strategy}, 点击位置={text_position_mode}")

        # 从工作流上下文中获取OCR识别结果
        ocr_results = _get_ocr_results_from_context(card_id)

        if not ocr_results:
            # 检查是否是多组文字识别模式且上下文为空
            try:
                from task_workflow.workflow_context import get_workflow_context
                context = get_workflow_context()
                text_groups, current_index, clicked_texts = context.get_multi_text_recognition_state(card_id)

                if text_groups and len(text_groups) > 1:
                    logger.warning("多组文字识别模式下上下文为空，判断为点击失败")
                    logger.warning("所有文字组可能已识别完成或OCR识别失败")
                else:
                    logger.warning("未找到OCR识别结果，无法执行文字点击")
                    logger.warning("请确保在此卡片之前有OCR识别卡片，并且OCR识别成功")
            except Exception as e:
                logger.warning(f"检查多组文字识别状态时发生错误: {e}")
                logger.warning("未找到OCR识别结果，无法执行文字点击")

            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        logger.info(f"获取到OCR识别结果: {len(ocr_results)} 个文字")
        for i, result in enumerate(ocr_results):
            text = result.get('text', '')
            confidence = result.get('confidence', 0)
            logger.info(f"  OCR结果{i+1}: '{text}' (置信度: {confidence:.3f})")

        # 从工作流上下文获取OCR的目标文字
        logger.info(f" [调试] 文字点击卡片{card_id}尝试获取OCR目标文字")
        target_text, final_match_mode = _get_ocr_target_text_from_context(card_id)
        logger.info(f" [调试] 获取到的目标文字: '{target_text}', 匹配模式: {final_match_mode}")

        if not target_text:
            logger.error(" [调试] OCR识别卡片未设置目标文字，无法执行文字点击")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)
        else:
            logger.info(f" [调试] 使用OCR目标文字: '{target_text}', 匹配模式: {final_match_mode}")

        # 根据目标文字查找匹配的OCR结果
        matched_result = _find_matching_text_in_ocr_results(ocr_results, target_text, final_match_mode)

        if not matched_result:
            if target_text:
                logger.warning(f"在OCR结果中未找到匹配的文字: '{target_text}'")
                logger.warning("建议检查目标文字是否正确，或使用'包含'匹配模式")
            else:
                logger.warning("OCR结果为空，无法执行文字点击")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        text_bbox = matched_result.get('bbox', [])
        matched_text = matched_result.get('text', '')
        confidence = matched_result.get('confidence', 0)
        logger.info(f"找到匹配文字: '{matched_text}' (置信度: {confidence:.3f})")
        logger.info(f" [调试] 文字边界框: {text_bbox}")

        # 计算点击坐标
        if text_bbox and len(text_bbox) >= 8:
            # 计算相对于识别区域的点击坐标
            relative_click_x, relative_click_y = _calculate_click_position(text_bbox, text_position_mode, text_offset_x, text_offset_y)
            logger.info(f"📍 [调试] 计算的相对坐标: ({relative_click_x}, {relative_click_y})")

            # 获取OCR识别区域的偏移量，将相对坐标转换为窗口坐标
            ocr_region_offset = _get_ocr_region_offset_from_context(card_id)
            logger.info(f" [调试] 获取OCR区域偏移: {ocr_region_offset}")

            if ocr_region_offset:
                offset_x, offset_y = ocr_region_offset
                click_x = relative_click_x + offset_x
                click_y = relative_click_y + offset_y
                logger.info(f" [调试] 坐标转换: 相对坐标({relative_click_x}, {relative_click_y}) + 区域偏移({offset_x}, {offset_y}) = 窗口坐标({click_x}, {click_y})")
            else:
                click_x, click_y = relative_click_x, relative_click_y
                logger.warning(" [调试] 未找到OCR区域偏移信息，使用相对坐标 - 这可能导致点击位置错误！")

            logger.info(f"计算得到点击坐标: ({click_x}, {click_y}) [模式: {text_position_mode}]")
            if text_position_mode == "自定义偏移":
                logger.info(f"应用偏移量: X偏移={text_offset_x}, Y偏移={text_offset_y}")
        else:
            logger.error(f"无效的文字边界框: {text_bbox}")
            logger.error("边界框应包含8个坐标值 [x1,y1,x2,y2,x3,y3,x4,y4]")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 构造坐标点击的参数
        disable_random_offset = params.get('disable_random_offset', False)
        random_offset = 0 if disable_random_offset else params.get('random_offset', 5)

        coordinate_params = {
            'coordinate_x': int(click_x),
            'coordinate_y': int(click_y),
            'coordinate_mode': '客户区坐标',  # OCR结果通常是相对于窗口的坐标
            'button': params.get('button', '左键'),
            'clicks': params.get('clicks', 1),
            'interval': params.get('interval', 0.1),
            'disable_random_offset': disable_random_offset,
            'random_offset': random_offset,
            'on_success': on_success_action,
            'success_jump_target_id': success_jump_id,
            'on_failure': on_failure_action,
            'failure_jump_target_id': failure_jump_id
        }

        logger.info(f"执行文字点击: ({click_x}, {click_y}), 随机偏移: {'禁用' if disable_random_offset else '启用'}")

        # 执行坐标点击
        success, action, next_id = execute_coordinate_click(coordinate_params, {}, execution_mode, target_hwnd, None, card_id)

        # 如果点击成功，处理多组文字识别逻辑
        if success:
            try:
                from task_workflow.workflow_context import get_workflow_context
                context = get_workflow_context()

                # 检查是否是多组文字识别模式
                # 需要使用OCR卡片的ID，而不是文字点击卡片的ID
                ocr_card_id = _get_ocr_card_id_from_context(card_id)
                if ocr_card_id:
                    text_groups, current_index, clicked_texts = context.get_multi_text_recognition_state(ocr_card_id)
                else:
                    text_groups, current_index, clicked_texts = [], 0, []

                if text_groups and len(text_groups) > 1 and ocr_card_id:
                    # 多组文字识别模式
                    # 记录已点击的文字
                    clicked_text = _get_clicked_text_from_context(card_id)
                    if clicked_text:
                        context.add_clicked_text(ocr_card_id, clicked_text)
                        logger.info(f"记录已点击文字到记忆: '{clicked_text}' (OCR卡片ID: {ocr_card_id})")

                    # 清除当前OCR上下文，但保留记忆
                    context.clear_card_ocr_context(ocr_card_id)
                    logger.info("清除OCR上下文数据，保留多组文字识别记忆")

                    # 推进到下一组文字
                    has_next = context.advance_text_recognition_index(ocr_card_id)
                    if has_next:
                        logger.info(f"推进到下一组文字识别，返回OCR卡片{ocr_card_id}继续执行")
                        # 返回到OCR识别卡片继续下一组识别
                        return success, "jump", ocr_card_id
                    else:
                        logger.info("所有文字组识别完成，清空所有数据")
                        context.clear_card_ocr_data(ocr_card_id)
                else:
                    # 单组文字识别模式，清除OCR上下文数据
                    context.clear_card_ocr_context(card_id)
                    logger.info("单组文字点击成功，已清除OCR上下文数据")

            except Exception as e:
                logger.warning(f"处理文字点击后续逻辑时发生错误: {e}")

        return success, action, next_id

    except Exception as e:
        logger.error(f"执行文字点击时发生错误: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_mouse_scroll(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                         card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                         on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行鼠标滚轮操作"""
    try:
        from tasks.mouse_scroll import execute_task as execute_mouse_scroll

        # 解析滚动起始位置坐标
        scroll_position = params.get('scroll_start_position', '500,300')
        try:
            if isinstance(scroll_position, str) and ',' in scroll_position:
                scroll_x, scroll_y = map(int, scroll_position.split(','))
            else:
                # 兼容旧版本的 scroll_x 和 scroll_y 参数
                scroll_x = int(params.get('scroll_x', 500))
                scroll_y = int(params.get('scroll_y', 300))
        except (ValueError, TypeError):
            logger.warning(f"无法解析滚动坐标: {scroll_position}，使用默认值 (500, 300)")
            scroll_x, scroll_y = 500, 300

        # 构造鼠标滚轮的参数
        scroll_params = {
            'direction': params.get('scroll_direction', '向下'),
            'scroll_count': params.get('scroll_clicks', 3),  # 使用 scroll_count 而不是 clicks
            'steps_per_scroll': 1,  # 默认每步滚动1刻度
            'interval': 0.1,  # 默认间隔
            'location_mode': '指定坐标',  # 使用指定坐标模式
            'scroll_start_position': f"{scroll_x},{scroll_y}",  # 设置正确的坐标字符串
            'coordinate_mode': '客户区坐标',  # 设置坐标模式
            'scroll_x': scroll_x,  # 传递解析后的X坐标（兼容性）
            'scroll_y': scroll_y,  # 传递解析后的Y坐标（兼容性）
            'on_success': on_success_action,
            'success_jump_target_id': success_jump_id,
            'on_failure': on_failure_action,
            'failure_jump_target_id': failure_jump_id
        }

        logger.info(f"执行鼠标滚轮操作: {params.get('scroll_direction', '向下')} {params.get('scroll_clicks', 3)}次")
        return execute_mouse_scroll(scroll_params, {}, execution_mode, target_hwnd, None, card_id=card_id)

    except Exception as e:
        logger.error(f"执行鼠标滚轮操作时发生错误: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_rotate_view(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                        card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                        on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行旋转视角操作 - 基于开源最佳实践的全面优化"""
    try:
        from utils.interception_driver import get_driver
        driver = get_driver()
        import time
        import cv2
        import numpy as np

        # 获取新的参数
        direction = params.get('rotate_direction', '右转')
        distance = params.get('rotate_distance', 200)  # 拖拽距离
        duration = params.get('rotate_duration', 1.5)  # 持续时间
        mouse_button = params.get('rotate_mouse_button', '左键')  # 鼠标按钮

        # 图片识别参数
        enable_recognition = params.get('enable_rotate_recognition', False)
        image_path = params.get('rotate_target_image', '')
        confidence = params.get('rotate_image_confidence', 0.8)
        recognition_interval_ms = params.get('rotate_recognition_interval', 50)  # 新参数：检测间隔(毫秒)

        # 转换检测间隔为秒
        recognition_interval = recognition_interval_ms / 1000.0

        logger.info(f"开始丝滑旋转视角: 方向={direction}, 距离={distance}px, 时长={duration}s")
        if enable_recognition:
            logger.info(f"启用实时识别: 置信度={confidence}, 间隔={recognition_interval_ms}ms")

        # 预加载模板图片（如果启用识别）
        template_image = None
        if enable_recognition and image_path:
            try:
                import cv2
                import os

                # 检查文件是否存在
                if not os.path.exists(image_path):
                    logger.warning(f"模板图片文件不存在: {image_path}")
                    enable_recognition = False
                else:
                    template_image = safe_imread(image_path, cv2.IMREAD_COLOR)
                    if template_image is None:
                        logger.warning(f"无法加载模板图片（可能是格式不支持）: {image_path}")
                        enable_recognition = False
                    else:
                        template_h, template_w = template_image.shape[:2]
                        logger.debug(f"模板图片加载成功: {image_path} (尺寸: {template_w}x{template_h})")
                        logger.debug(f"图片识别参数: 置信度={confidence}")
            except Exception as e:
                logger.warning(f"加载模板图片时出错: {e}")
                enable_recognition = False

        logger.info(f"执行旋转视角操作: {direction} {distance}像素 (时长: {duration}秒)")
        if enable_recognition and image_path:
            # 只显示图片名称，不显示完整路径
            if image_path.startswith('memory://'):
                image_name = image_path.replace('memory://', '')
            else:
                image_name = os.path.basename(image_path)
            logger.info(f"启用图片识别停止: {image_name} (置信度: {confidence})")

        # 激活目标窗口（旋转视角是前台操作，必须激活窗口）
        if target_hwnd:
            try:
                import win32gui
                import win32con

                # 检查窗口是否有效
                if not win32gui.IsWindow(target_hwnd):
                    logger.warning(f"无法激活目标窗口：句柄 {target_hwnd} 无效或已销毁")
                else:
                    # 检查是否已经是前台窗口
                    current_foreground_hwnd = win32gui.GetForegroundWindow()
                    if current_foreground_hwnd == target_hwnd:
                        logger.debug(f"目标窗口 {target_hwnd} 已是前台窗口，无需激活")
                    else:
                        # 检查窗口是否最小化
                        if win32gui.IsIconic(target_hwnd):
                            logger.debug("目标窗口已最小化，正在恢复...")
                            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                            time.sleep(0.15)
                            win32gui.SetForegroundWindow(target_hwnd)
                            time.sleep(0.15)
                            logger.debug(f"窗口 {target_hwnd} 已恢复并激活")
                        else:
                            # 直接激活窗口
                            win32gui.SetForegroundWindow(target_hwnd)
                            time.sleep(0.1)
                            logger.debug(f"已激活目标窗口: {target_hwnd}")

            except Exception as e:
                logger.warning(f"激活目标窗口失败: {e}，继续执行旋转操作")

        # 根据方向确定偏移（使用新的距离参数）
        x_offset, y_offset = 0, 0
        if direction == "左转":
            x_offset = -distance
        elif direction == "右转":
            x_offset = distance
        elif direction == "上转":
            y_offset = -distance
        elif direction == "下转":
            y_offset = distance

        logger.debug(f"计算偏移: 方向={direction}, 距离={distance}px -> 偏移({x_offset}, {y_offset})")

        # 获取屏幕中心作为旋转点 - 使用驱动
        driver = get_driver()
        screen_width, screen_height = driver.get_screen_size()
        center_x, center_y = screen_width // 2, screen_height // 2

        # 如果有窗口句柄，尝试获取窗口中心
        if target_hwnd:
            try:
                import win32gui
                rect = win32gui.GetWindowRect(target_hwnd)
                center_x = (rect[0] + rect[2]) // 2
                center_y = (rect[1] + rect[3]) // 2
                logger.debug(f"使用窗口中心: ({center_x}, {center_y})")
            except:
                logger.debug(f"无法获取窗口中心，使用屏幕中心: ({center_x}, {center_y})")

        # 在旋转前进行一次图片识别测试（如果启用了识别）
        if enable_recognition and template_image is not None and target_hwnd:
            logger.debug("旋转前进行图片识别测试...")
            preprocessing_method = params.get('rotate_preprocessing_method', '无')
            preprocessing_params = {'preprocessing_method': preprocessing_method}
            initial_found = _check_image_during_rotation(target_hwnd, template_image, confidence, preprocessing_params)
            if initial_found:
                logger.info("旋转前已发现目标图片，无需旋转")
                return _handle_success(on_success_action, success_jump_id, card_id)
            else:
                logger.debug("旋转前未发现目标图片，开始旋转")

        # 使用内联丝滑拖拽算法
        logger.info(f"使用丝滑拖拽执行旋转: 中心({center_x}, {center_y}), 偏移({x_offset}, {y_offset}), 持续{duration}秒")

        # 计算目标坐标
        end_x = center_x + x_offset
        end_y = center_y + y_offset

        # 使用Interception驱动的拖拽功能
        from utils.interception_driver import get_driver
        driver = get_driver()

        drag_success = False
        image_found = False
        stop_flag = threading.Event()

        try:
            logger.info(f"使用基于距离的恒定速度拖拽: 从({center_x}, {center_y})到({end_x}, {end_y}), 时长{duration}s")

            # 先移动到窗口中心 - 使用修复的鼠标移动
            try:
                from main import mouse_move_fixer
                success = mouse_move_fixer.safe_move_to(center_x, center_y, duration=0, hwnd=target_hwnd)
                if not success:
                    logger.warning("使用修复器移动鼠标失败，回退到驱动")
                    driver.move_mouse(center_x, center_y)
            except ImportError:
                logger.debug("鼠标移动修复器不可用，使用驱动")
                driver.move_mouse(center_x, center_y)
            time.sleep(0.1)

            # 启动图片识别线程
            recognition_thread = None
            if enable_recognition and template_image is not None:
                logger.info(f"启动图片识别: 置信度={confidence}, 检测间隔={recognition_interval}s")
                recognition_thread = threading.Thread(
                    target=_recognition_worker,
                    args=(template_image, confidence, recognition_interval, duration, stop_flag, target_hwnd)
                )
                recognition_thread.daemon = True
                recognition_thread.start()

            # 转换按钮格式
            button_map = {'左键': 'left', '右键': 'right', '中键': 'middle'}
            driver_button = button_map.get(mouse_button, 'left')

            # 使用基于距离的恒定速度算法（开源最佳实践）
            drag_success, image_found = _execute_constant_speed_drag(
                center_x, center_y, end_x, end_y, duration, stop_flag, driver_button
            )

            # 等待识别线程结束
            if recognition_thread:
                stop_flag.set()
                recognition_thread.join(timeout=0.5)
                if stop_flag.is_set():
                    image_found = True

            drag_success = True
            logger.info(f"原生拖拽完成: 成功={drag_success}, 找到图片={image_found}")

        except Exception as e:
            logger.error(f"拖拽执行异常: {e}")
            # 前台模式使用驱动，无需手动释放鼠标（驱动会自动处理）
        finally:
            # 前台模式使用驱动，无需恢复PyAutoGUI设置
            stop_flag.set()

        # 处理旋转结果
        if not drag_success:
            logger.error("增强旋转执行失败")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 根据图片识别结果处理
        if enable_recognition and template_image is not None:
            if image_found:
                logger.info("旋转期间成功识别到目标图片!")
                return _handle_success(on_success_action, success_jump_id, card_id)
            else:
                logger.info("旋转完成，但未识别到目标图片")
                return _handle_failure(on_failure_action, failure_jump_id, card_id)
        else:
            # 没有启用图片识别，旋转成功即为成功
            logger.info("旋转视角操作成功完成")
            return _handle_success(on_success_action, success_jump_id, card_id)

    except Exception as e:
        logger.error(f"执行旋转视角操作时发生错误: {e}", exc_info=True)
        # 前台模式使用驱动，无需手动释放鼠标（驱动会自动处理）
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_constant_speed_drag(start_x: int, start_y: int, end_x: int, end_y: int,
                               duration: float, stop_flag: threading.Event, button: str = 'left') -> tuple[bool, bool]:
    """基于诊断结果的精确时间控制拖拽"""
    import math
    import pyautogui

    # 计算移动距离
    distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)

    logger.info(f"=== 精确时间控制拖拽 ===")
    logger.info(f"起点: ({start_x}, {start_y}), 终点: ({end_x}, {end_y})")
    logger.info(f"距离: {distance:.1f}px, 期望时长: {duration}s")

    try:
        # 前台模式：使用Interception驱动
        driver = get_driver()
        if not driver.initialize():
            logger.error("Interception驱动初始化失败")
            return False, False

        # 移动到起始位置并按下指定按键
        driver.move_mouse(start_x, start_y)
        time.sleep(0.1)

        # 使用驱动的拖拽功能
        logger.info(f"使用Interception驱动拖拽: 从({start_x}, {start_y})到({end_x}, {end_y}), 时长{duration}s, 按钮={button}")
        success = driver.drag_mouse(start_x, start_y, end_x, end_y, button=button, duration=duration)

        if not success:
            logger.error("Interception驱动拖拽失败")
            return False, False

        # 拖拽成功
        total_time = duration  # 使用预期时间
        actual_speed = distance / total_time if total_time > 0 else 0
        expected_speed = distance / duration

        logger.info(f"Interception拖拽完成:")
        logger.info(f"  实际时间: {total_time:.3f}s")
        logger.info(f"  实际速度: {actual_speed:.1f}px/s")
        logger.info(f"  期望速度: {expected_speed:.1f}px/s")

        return True, stop_flag.is_set()

    except Exception as e:
        logger.error(f"Interception拖拽失败: {e}")
        return False, False

    # 不可达代码已移除

    except Exception as e:
        logger.error(f"精确拖拽失败: {e}")
        try:
            driver.mouse_up('right')
        except:
            pass
        drag_success = False
        image_found = False

    return drag_success, image_found

def _old_diagnostic_drag(start_x: int, start_y: int, end_x: int, end_y: int,
                               duration: float, stop_flag: threading.Event) -> tuple[bool, bool]:
    """深度诊断模式 - 找出越来越快的真正原因"""
    import math
    import ctypes
    import psutil
    import platform

    # 使用Interception驱动替代pyautogui
    driver = get_driver()
    if not driver.initialize():
        logger.error("Interception驱动初始化失败")
        return False, False

    # 计算移动距离
    distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)

    logger.info(f"=== 深度诊断模式 ===")
    logger.info(f"起点: ({start_x}, {start_y}), 终点: ({end_x}, {end_y})")
    logger.info(f"距离: {distance:.1f}px, 期望时长: {duration}s, 期望速度: {distance/duration:.1f}px/s")

    # 1. 系统信息诊断
    logger.info(f"=== 系统信息 ===")
    logger.info(f"操作系统: {platform.system()} {platform.release()} {platform.version()}")
    logger.info(f"CPU使用率: {psutil.cpu_percent()}%")
    logger.info(f"内存使用率: {psutil.virtual_memory().percent}%")

    # 2. 显示设置诊断
    try:
        user32 = ctypes.windll.user32

        # DPI设置
        dpi = user32.GetDpiForSystem()
        logger.info(f"系统DPI: {dpi}")

        # 屏幕分辨率
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
        logger.info(f"屏幕分辨率: {screen_width}x{screen_height}")

        # 鼠标设置详细信息
        mouse_speed = ctypes.c_int()
        user32.SystemParametersInfoW(112, 0, ctypes.byref(mouse_speed), 0)

        mouse_accel = (ctypes.c_int * 3)()
        user32.SystemParametersInfoW(4, 0, mouse_accel, 0)

        logger.info(f"鼠标速度: {mouse_speed.value}/20")
        logger.info(f"鼠标加速: 阈值1={mouse_accel[0]}, 阈值2={mouse_accel[1]}, 加速={mouse_accel[2]}")

    except Exception as e:
        logger.warning(f"无法获取系统设置: {e}")

    # 3. 驱动设置诊断
    logger.info(f"=== Interception驱动设置 ===")
    logger.info(f"驱动状态: {'已初始化' if driver.initialized else '未初始化'}")
    logger.info(f"驱动版本: Interception DLL")

    # 4. 实际测试 - 不做任何拖拽，只测试单纯的时间控制
    logger.info(f"=== 时间控制测试 ===")

    test_steps = 10
    test_interval = duration / test_steps

    logger.info(f"测试{test_steps}步, 每步间隔{test_interval:.3f}s")

    actual_intervals = []
    start_time = time.time()
    last_time = start_time

    for i in range(test_steps):
        # 只是等待，不移动鼠标
        time.sleep(test_interval)

        current_time = time.time()
        actual_interval = current_time - last_time
        actual_intervals.append(actual_interval)

        logger.info(f"步骤 {i+1}: 期望间隔{test_interval:.3f}s, 实际间隔{actual_interval:.3f}s, 误差{(actual_interval-test_interval)*1000:.1f}ms")

        last_time = current_time

    total_actual_time = time.time() - start_time
    avg_interval = sum(actual_intervals) / len(actual_intervals)

    logger.info(f"时间控制测试结果:")
    logger.info(f"  期望总时长: {duration:.3f}s")
    logger.info(f"  实际总时长: {total_actual_time:.3f}s")
    logger.info(f"  时间误差: {(total_actual_time-duration)*1000:.1f}ms")
    logger.info(f"  平均间隔: {avg_interval:.3f}s (期望: {test_interval:.3f}s)")

    # 5. 鼠标移动测试 - 测试PyAutoGUI的moveTo是否有问题
    logger.info(f"=== 鼠标移动测试 ===")

    # 记录鼠标移动的实际耗时
    move_times = []

    test_positions = [
        (start_x, start_y),
        (start_x + 50, start_y),
        (start_x + 100, start_y),
        (start_x + 150, start_y),
        (end_x, end_y)
    ]

    for i, (x, y) in enumerate(test_positions):
        move_start = time.time()
        driver.move_mouse(x, y)  # 使用Interception驱动
        move_end = time.time()
        move_time = move_end - move_start
        move_times.append(move_time)

        logger.info(f"移动到 ({x}, {y}): 耗时{move_time*1000:.2f}ms")
        time.sleep(0.1)  # 短暂停顿

    avg_move_time = sum(move_times) / len(move_times)
    logger.info(f"平均移动耗时: {avg_move_time*1000:.2f}ms")

    # 6. 检查是否有其他进程干扰
    logger.info(f"=== 进程检查 ===")

    suspicious_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            if proc.info['cpu_percent'] > 10:  # CPU使用率超过10%的进程
                suspicious_processes.append(f"{proc.info['name']} (PID: {proc.info['pid']}, CPU: {proc.info['cpu_percent']:.1f}%)")
        except:
            pass

    if suspicious_processes:
        logger.warning(f"高CPU使用率进程: {', '.join(suspicious_processes)}")
    else:
        logger.info("没有发现高CPU使用率进程")

    # 7. 最终结论
    logger.info(f"=== 诊断结论 ===")

    if abs(total_actual_time - duration) > 0.1:
        logger.error(f"时间控制异常！实际时间与期望时间差异过大")
    elif avg_move_time > 0.01:
        logger.warning(f"鼠标移动耗时过长，可能影响拖拽流畅性")
    elif suspicious_processes:
        logger.warning(f"系统负载较高，可能影响性能")
    else:
        logger.info(f"系统状态正常，问题可能在游戏或应用层面")

    # 简单的拖拽测试
    logger.info(f"=== 简单拖拽测试 ===")

    try:
        # 使用Interception驱动进行简单拖拽测试
        logger.info(f"使用Interception驱动进行拖拽测试，按钮={driver_button}")
        success = driver.drag_mouse(start_x, start_y, end_x, end_y, button=driver_button, duration=duration)

        if success:
            logger.info("Interception驱动拖拽测试成功")
        else:
            logger.error("Interception驱动拖拽测试失败")

        drag_success = True
        image_found = stop_flag.is_set()

    except Exception as e:
        logger.error(f"拖拽测试失败: {e}")
        # 驱动自动处理鼠标释放
        drag_success = False
        image_found = False

    return drag_success, image_found

def _fallback_screen_drag(start_x: int, start_y: int, end_x: int, end_y: int,
                         duration: float, stop_flag: threading.Event) -> tuple[bool, bool]:
    """备用的屏幕坐标拖拽方法 - 已弃用，前台模式使用Interception驱动"""
    logger.warning("_fallback_screen_drag 已弃用，前台模式请使用Interception驱动")
    return False, False

def _recognition_worker(template_image, confidence: float, check_interval: float,
                      max_duration: float, stop_flag: threading.Event, target_hwnd: Optional[int]):
    """图片识别工作线程"""
    # 使用截图助手替代pyautogui
    from utils.screenshot_helper import take_screenshot

    start_time = time.time()
    check_count = 0

    logger.debug(f"识别线程启动: 最大时长={max_duration}s, 检测间隔={check_interval}s")

    try:
        while not stop_flag.is_set() and time.time() - start_time < max_duration:
            check_count += 1

            # 尝试后台截图
            screenshot_bgr = None
            if target_hwnd:
                try:
                    from utils.win32_utils import capture_window_background
                    screenshot_bgr = capture_window_background(target_hwnd)
                except Exception as e:
                    logger.debug(f"后台截图失败: {e}")

            # 如果后台截图失败，使用前台截图
            if screenshot_bgr is None:
                try:
                    screenshot_bgr = take_screenshot_opencv()
                    if screenshot_bgr is None:
                        raise Exception("截图失败")
                except Exception as e:
                    logger.debug(f"前台截图失败: {e}")
                    time.sleep(check_interval)
                    continue

            # 执行模板匹配
            try:
                result = cv2.matchTemplate(screenshot_bgr, template_image, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)

                logger.debug(f"识别检查 #{check_count}: 置信度={max_val:.3f}")

                if max_val >= confidence:
                    logger.info(f"图片识别成功! 置信度={max_val:.3f} (第{check_count}次检查)")
                    stop_flag.set()
                    return

            except Exception as e:
                logger.debug(f"模板匹配失败: {e}")

            # 等待下次检查
            time.sleep(check_interval)

        logger.debug(f"识别线程结束: 共检查{check_count}次, 耗时={time.time()-start_time:.2f}s")

    except Exception as e:
        logger.error(f"识别线程异常: {e}")

def _execute_smooth_drag(start_x: int, start_y: int, end_x: int, end_y: int,
                       duration: float, template_image, confidence: float,
                       recognition_interval: float, target_hwnd: Optional[int]) -> tuple[bool, bool]:
    """执行真正丝滑的拖拽 - 已弃用，前台模式使用Interception驱动"""
    logger.warning("_execute_smooth_drag 已弃用，前台模式请使用Interception驱动")
    return False, False

    # 不可达代码已移除（函数已弃用）

def _continuous_image_recognition(template_image, confidence: float,
                                check_interval: float, max_duration: float,
                                stop_flag: threading.Event, target_hwnd: Optional[int]):
    """持续图片识别线程"""
    import pyautogui

    start_time = time.time()
    recognition_count = 0

    logger.debug(f"图片识别线程启动: 最大时长={max_duration}s, 检测间隔={check_interval}s")

    try:
        while not stop_flag.is_set() and time.time() - start_time < max_duration:
            recognition_count += 1

            # 使用后台截图（如果有窗口句柄）
            if target_hwnd:
                try:
                    from utils.win32_utils import capture_window_background
                    screenshot_bgr = capture_window_background(target_hwnd)
                    if screenshot_bgr is not None:
                        # 模板匹配
                        result = cv2.matchTemplate(screenshot_bgr, template_image, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(result)

                        logger.debug(f"后台识别检查 #{recognition_count}: 置信度={max_val:.3f}")

                        if max_val >= confidence:
                            logger.info(f"后台识别成功! 置信度={max_val:.3f} (第{recognition_count}次)")
                            stop_flag.set()
                            return
                except Exception as e:
                    logger.debug(f"后台识别异常，使用前台截图: {e}")

            # 前台截图作为备选
            try:
                screenshot_cv = take_screenshot_opencv()
                if screenshot_cv is None:
                    raise Exception("截图失败")

                result = cv2.matchTemplate(screenshot_cv, template_image, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)

                logger.debug(f"前台识别检查 #{recognition_count}: 置信度={max_val:.3f}")

                if max_val >= confidence:
                    logger.info(f"前台识别成功! 置信度={max_val:.3f} (第{recognition_count}次)")
                    stop_flag.set()
                    return
            except Exception as e:
                logger.debug(f"前台识别异常: {e}")

            # 等待下次检查
            time.sleep(check_interval)

        logger.debug(f"图片识别线程结束: 共{recognition_count}次检查, 耗时={time.time()-start_time:.2f}s")

    except Exception as e:
        logger.error(f"持续识别异常: {e}")

def _check_image_during_rotation(target_hwnd: Optional[int], template_image, confidence: float,
                                params: Optional[Dict[str, Any]] = None) -> bool:
    """在旋转过程中快速检查图片是否存在（优化速度，避免阻塞旋转）"""
    try:
        import cv2

        if not target_hwnd or template_image is None:
            return False

        # 快速截图
        from utils.win32_utils import capture_window_background
        screenshot = capture_window_background(target_hwnd)

        if screenshot is None:
            return False

        # 快速尺寸检查
        screenshot_h, screenshot_w = screenshot.shape[:2]
        template_h, template_w = template_image.shape[:2]

        if template_w > screenshot_w or template_h > screenshot_h:
            return False

        # 简化预处理（旋转过程中优先速度）
        processed_screenshot = screenshot
        processed_template = template_image

        # 只在必要时进行预处理
        if params and params.get('preprocessing_method', '无') != '无':
            try:
                import importlib
                preprocessing_module = importlib.import_module('utils.image_preprocessing')
                apply_preprocessing = getattr(preprocessing_module, 'apply_preprocessing')
                processed_screenshot = apply_preprocessing(screenshot, params) or screenshot
                processed_template = apply_preprocessing(template_image, params) or template_image
            except:
                # 预处理失败时直接使用原图，不输出日志避免影响性能
                pass

        # 快速模板匹配
        result = cv2.matchTemplate(processed_screenshot, processed_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        # 详细的识别日志
        if max_val >= confidence:
            logger.info(f"靶心 图片识别成功：置信度 {max_val:.3f} >= {confidence}")
            return True
        else:
            logger.debug(f"图片识别失败：置信度 {max_val:.3f} < {confidence}")
            # 如果置信度接近阈值，输出警告
            if max_val >= confidence * 0.7:
                logger.warning(f"图片识别接近成功：置信度 {max_val:.3f}，建议降低阈值到 {max_val:.2f}")
            return False

    except Exception:
        # 旋转过程中不输出错误日志，避免影响性能
        return False

def _is_emulator_window(hwnd: Optional[int]) -> bool:
    """检测是否是模拟器窗口"""
    if not hwnd:
        return False

    try:
        # 使用统一的模拟器检测器
        from utils.emulator_detector import is_emulator_window

        is_emulator = is_emulator_window(hwnd)

        if is_emulator:
            import win32gui
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            logger.debug(f"检测到模拟器窗口: {title} (类名: {class_name})")

        return is_emulator

    except Exception as e:
        logger.debug(f"检测模拟器窗口失败: {e}")
        return False

def _execute_mouse_drag(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                       card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                       on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行鼠标拖拽操作"""
    try:
        # 检测是否是模拟器窗口
        is_emulator = _is_emulator_window(target_hwnd)

        # 对于模拟器窗口，前台和后台模式保持一致（都使用后台模式）
        if is_emulator:
            logger.info("🎮 检测到模拟器窗口，前台/后台模式统一使用后台拖拽")
            effective_mode = 'background'
        else:
            # 非模拟器窗口，完全不支持拖拽功能
            logger.error("❌ 鼠标拖拽功能不支持普通窗口")
            logger.info("💡 此功能仅适用于模拟器窗口（雷电、MuMu等）")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 获取拖拽模式
        drag_mode = params.get('drag_mode', '简单拖拽')

        if drag_mode == '多点路径拖拽':
            # 多点路径拖拽模式
            return _execute_multi_point_drag(params, effective_mode, target_hwnd, card_id,
                                           on_success_action, success_jump_id,
                                           on_failure_action, failure_jump_id)
        else:
            # 简单拖拽模式（原有逻辑）
            return _execute_simple_drag(params, effective_mode, target_hwnd, card_id,
                                      on_success_action, success_jump_id,
                                      on_failure_action, failure_jump_id)

    except Exception as e:
        logger.error(f"执行鼠标拖拽操作失败: {e}")
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_simple_drag(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                        card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                        on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行简单拖拽操作（原有的两点拖拽逻辑）"""
    try:
        # 获取拖拽参数
        direction = params.get('drag_direction', '向右')
        distance = params.get('drag_distance', 100)
        button = params.get('drag_button', '左键')
        duration = params.get('drag_duration', 1.0)
        smoothness = params.get('drag_smoothness', 20)

        # 解析拖拽起始位置坐标
        drag_position = params.get('drag_start_position', '500,300')
        try:
            if isinstance(drag_position, str) and ',' in drag_position:
                start_x, start_y = map(int, drag_position.split(','))
            else:
                start_x, start_y = 500, 300
                logger.warning(f"拖拽起始位置格式错误，使用默认值: ({start_x}, {start_y})")
        except (ValueError, TypeError) as e:
            start_x, start_y = 500, 300
            logger.warning(f"解析拖拽起始位置失败: {e}，使用默认值: ({start_x}, {start_y})")

        # 根据方向和距离计算结束坐标
        end_x, end_y = _calculate_end_position(start_x, start_y, direction, distance)

        logger.info(f"🖱 开始简单拖拽: ({start_x},{start_y}) -> ({end_x},{end_y})")
        logger.info(f" 拖拽参数: 方向={direction}, 距离={distance}像素, 按钮={button}")
        logger.info(f"⚙ 控制参数: 持续时间={duration}秒, 平滑度={smoothness}")

        if not target_hwnd:
            logger.error(" 需要目标窗口句柄才能执行鼠标拖拽")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 执行拖拽操作
        success = _perform_mouse_drag(target_hwnd, start_x, start_y, end_x, end_y,
                                    button, duration, smoothness, execution_mode)

        if success:
            logger.info(f" 简单拖拽完成")
            logger.info(f" 处理成功跳转: 动作={on_success_action}, 跳转ID={success_jump_id}, 卡片ID={card_id}")
            result = _handle_success(on_success_action, success_jump_id, card_id)
            logger.info(f" 成功跳转结果: {result}")
            return result
        else:
            logger.error(f" 简单拖拽失败")
            logger.info(f" 处理失败跳转: 动作={on_failure_action}, 跳转ID={failure_jump_id}, 卡片ID={card_id}")
            result = _handle_failure(on_failure_action, failure_jump_id, card_id)
            logger.info(f" 失败跳转结果: {result}")
            return result

    except Exception as e:
        logger.error(f" 简单拖拽异常: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _execute_multi_point_drag(params: Dict[str, Any], execution_mode: str, target_hwnd: Optional[int],
                             card_id: Optional[int], on_success_action: str, success_jump_id: Optional[int],
                             on_failure_action: str, failure_jump_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """执行多点路径拖拽操作"""
    try:
        # 获取路径点参数
        path_points_text = params.get('path_points', '100,100\n200,150\n300,200\n400,250')
        duration = params.get('drag_duration', 1.0)

        # 解析路径点
        path_points = _parse_path_points(path_points_text)
        if not path_points or len(path_points) < 2:
            logger.error("路径点数量不足，至少需要2个点")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        logger.info(f"🎯 开始多点路径拖拽: {len(path_points)}个点, 总时长={duration}秒")
        logger.info(f" 路径点: {path_points}")

        if not target_hwnd:
            logger.error(" 需要目标窗口句柄才能执行多点拖拽")
            return _handle_failure(on_failure_action, failure_jump_id, card_id)

        # 执行多点拖拽操作
        success = perform_mouse_drag_path(target_hwnd, path_points, duration, execution_mode)

        if success:
            logger.info(f" 多点路径拖拽完成")
            logger.info(f" 处理成功跳转: 动作={on_success_action}, 跳转ID={success_jump_id}, 卡片ID={card_id}")
            result = _handle_success(on_success_action, success_jump_id, card_id)
            logger.info(f" 成功跳转结果: {result}")
            return result
        else:
            logger.error(f" 多点路径拖拽失败")
            logger.info(f" 处理失败跳转: 动作={on_failure_action}, 跳转ID={failure_jump_id}, 卡片ID={card_id}")
            result = _handle_failure(on_failure_action, failure_jump_id, card_id)
            logger.info(f" 失败跳转结果: {result}")
            return result

    except Exception as e:
        logger.error(f"执行多点路径拖拽操作失败: {e}", exc_info=True)
        return _handle_failure(on_failure_action, failure_jump_id, card_id)

def _parse_path_points(path_points_text: str) -> list:
    """解析路径点文本为坐标列表

    Args:
        path_points_text: 路径点文本，每行一个坐标点，格式：x,y

    Returns:
        list: 坐标点列表 [(x1, y1), (x2, y2), ...]
    """
    try:
        path_points = []
        lines = path_points_text.strip().split('\n')

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            try:
                if ',' in line:
                    x_str, y_str = line.split(',', 1)
                    x = int(x_str.strip())
                    y = int(y_str.strip())
                    path_points.append((x, y))
                else:
                    logger.warning(f"路径点格式错误（第{i+1}行）: {line}，跳过")
            except (ValueError, TypeError) as e:
                logger.warning(f"解析路径点失败（第{i+1}行）: {line}，错误: {e}")
                continue

        logger.debug(f"解析路径点完成: {len(path_points)}个有效点")
        return path_points

    except Exception as e:
        logger.error(f"解析路径点文本失败: {e}")
        return []



def _calculate_end_position(start_x: int, start_y: int, direction: str, distance: int) -> tuple:
    """根据起始坐标、方向和距离计算结束坐标"""
    direction_map = {
        "向右": (distance, 0),
        "向左": (-distance, 0),
        "向上": (0, -distance),
        "向下": (0, distance),
        "右上": (int(distance * 0.707), -int(distance * 0.707)),  # 45度角
        "右下": (int(distance * 0.707), int(distance * 0.707)),
        "左上": (-int(distance * 0.707), -int(distance * 0.707)),
        "左下": (-int(distance * 0.707), int(distance * 0.707))
    }

    if direction not in direction_map:
        logger.warning(f"未知的拖拽方向: {direction}，使用默认方向'向右'")
        direction = "向右"

    dx, dy = direction_map[direction]
    end_x = start_x + dx
    end_y = start_y + dy

    logger.debug(f"计算结束坐标: 起始({start_x},{start_y}) + 方向{direction}({dx},{dy}) = 结束({end_x},{end_y})")

    return end_x, end_y

def perform_mouse_drag_path(hwnd: int, path_points: list, duration: float = 1.0,
                           execution_mode: str = 'background') -> bool:
    """执行多点路径拖拽操作

    Args:
        hwnd: 目标窗口句柄
        path_points: 路径点列表，格式: [(x1, y1), (x2, y2), (x3, y3), ...]
        duration: 总持续时间（秒）
        execution_mode: 执行模式 ('foreground' 或 'background')

    Returns:
        bool: 是否执行成功
    """
    try:
        if not path_points or len(path_points) < 2:
            logger.error("路径点数量不足，至少需要2个点")
            return False

        logger.info(f"开始多点路径拖拽: {len(path_points)}个点, 总时长: {duration}秒, 执行模式: {execution_mode}")

        # 优先尝试新的输入模拟系统
        try:
            from utils.input_simulation import global_input_simulator_manager
            from utils.emulator_detector import detect_emulator_type

            # 检测模拟器类型
            is_emulator, emulator_type, description = detect_emulator_type(hwnd)

            if is_emulator:
                logger.info(f"检测到模拟器类型: {emulator_type}，使用专用多点拖拽方法")

                # 获取适合的输入模拟器
                simulator = global_input_simulator_manager.get_simulator(
                    hwnd, "emulator_window", execution_mode
                )

                if simulator and hasattr(simulator, 'drag_path'):
                    # 使用新的输入模拟系统执行多点拖拽
                    result = simulator.drag_path(path_points, duration)

                    if result:
                        logger.info(f"新输入模拟系统多点拖拽成功: {emulator_type}")
                        return True
                    else:
                        logger.warning(f"新输入模拟系统多点拖拽失败，回退到分段拖拽")
                else:
                    logger.warning("输入模拟器不支持多点拖拽，回退到分段拖拽")
            else:
                logger.debug("非模拟器窗口，使用分段拖拽方法")

        except ImportError:
            logger.warning("新输入模拟系统不可用，使用分段拖拽")
        except Exception as e:
            logger.warning(f"新输入模拟系统异常: {e}，回退到分段拖拽")

        # 回退到分段拖拽方法
        return _perform_segmented_drag_path(hwnd, path_points, duration, execution_mode)

    except Exception as e:
        logger.error(f"执行多点路径拖拽操作失败: {e}")
        return False

def _perform_segmented_drag_path(hwnd: int, path_points: list, duration: float,
                                execution_mode: str) -> bool:
    """分段执行多点路径拖拽 - 回退方法"""
    try:
        if len(path_points) < 2:
            return False

        # 计算每段的持续时间
        segment_count = len(path_points) - 1
        segment_duration = duration / segment_count

        logger.debug(f"分段多点拖拽: {len(path_points)}个点, 分{segment_count}段, 每段{segment_duration:.2f}秒")

        # 分段执行拖拽
        success_count = 0
        for i in range(segment_count):
            start_x, start_y = path_points[i]
            end_x, end_y = path_points[i + 1]

            # 执行单段拖拽
            if _perform_mouse_drag(hwnd, start_x, start_y, end_x, end_y, '左键',
                                 segment_duration, 10, execution_mode):
                success_count += 1
                logger.debug(f"段{i+1}拖拽成功: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
            else:
                logger.warning(f"段{i+1}拖拽失败: ({start_x}, {start_y}) -> ({end_x}, {end_y})")

            # 段间短暂延迟，避免操作过快
            if i < segment_count - 1:
                import time
                time.sleep(0.05)

        # 如果大部分段都成功，认为整体成功
        success_rate = success_count / segment_count
        if success_rate >= 0.7:  # 70%以上成功率
            logger.info(f"分段多点拖拽完成: {success_count}/{segment_count}段成功")
            return True
        else:
            logger.error(f"分段多点拖拽失败: 仅{success_count}/{segment_count}段成功")
            return False

    except Exception as e:
        logger.error(f"分段多点拖拽异常: {e}")
        return False

def _perform_mouse_drag(hwnd: int, start_x: int, start_y: int, end_x: int, end_y: int,
                       button: str, duration: float, smoothness: int, execution_mode: str) -> bool:
    """执行具体的鼠标拖拽操作

    根据execution_mode决定使用何种方法：
    - foreground系列: 使用Interception驱动
    - background系列: 使用PostMessage
    - emulator系列: 使用模拟器专用方法（ADB等）
    """
    try:
        # 根据execution_mode选择方法，不做任何自动检测
        if execution_mode.startswith('emulator_'):
            # 模拟器专用模式
            logger.info(f"使用模拟器专用拖拽方法: {execution_mode}")

            # 从execution_mode提取模拟器类型
            emulator_type = execution_mode.replace('emulator_', '')

            # 直接创建对应的模拟器
            from utils.input_simulation.emulator_window import EmulatorWindowInputSimulator
            simulator = EmulatorWindowInputSimulator(hwnd, emulator_type=emulator_type, execution_mode=execution_mode)

            # 转换按钮名称：中文 -> 英文
            button_map = {'左键': 'left', '右键': 'right', '中键': 'middle'}
            button_name = button_map.get(button, 'left')

            # 使用模拟器拖拽方法
            result = simulator.drag(start_x, start_y, end_x, end_y, duration, button_name)

            if result:
                logger.info(f"模拟器拖拽成功: {emulator_type}")
                return True
            else:
                logger.warning(f"模拟器拖拽失败")
                return False

        elif execution_mode.startswith('foreground'):
            # 前台模式：使用Interception驱动
            logger.info(f"使用前台拖拽方法: {execution_mode}")
            return _perform_foreground_drag(start_x, start_y, end_x, end_y, button, duration, smoothness)
        else:
            # 后台模式：使用PostMessage
            logger.info(f"使用后台拖拽方法: {execution_mode}")
            return _perform_background_drag(hwnd, start_x, start_y, end_x, end_y, button, duration, smoothness)

    except Exception as e:
        logger.error(f"执行鼠标拖拽操作失败: {e}", exc_info=True)
        return False

def _perform_foreground_drag(start_x: int, start_y: int, end_x: int, end_y: int,
                           button: str, duration: float, smoothness: int) -> bool:
    """前台模式鼠标拖拽 - 使用Interception驱动"""
    try:
        # 使用Interception驱动替代pyautogui
        driver = get_driver()
        if not driver.initialize():
            logger.error("Interception驱动初始化失败")
            return False

        # 转换按钮类型
        button_map = {
            '左键': 'left',
            '右键': 'right',
            '中键': 'middle'
        }

        driver_button = button_map.get(button)
        if not driver_button:
            logger.error(f"不支持的按钮类型: {button}")
            return False

        # 使用驱动执行拖拽
        success = driver.drag_mouse(start_x, start_y, end_x, end_y,
                                  button=driver_button, duration=duration)

        if success:
            logger.info(f"前台拖拽完成: {button} 从({start_x},{start_y})到({end_x},{end_y})")
        else:
            logger.error("前台拖拽执行失败")

        return success

    except Exception as e:
        logger.error(f"前台拖拽失败: {e}")
        return False

def _perform_background_drag(hwnd: int, start_x: int, start_y: int, end_x: int, end_y: int,
                           button: str, duration: float, smoothness: int) -> bool:
    """后台模式鼠标拖拽"""
    try:
        import win32gui
        import win32api
        import win32con

        # 按钮消息映射
        button_messages = {
            '左键': (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP),
            '右键': (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP),
            '中键': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP)
        }

        if button not in button_messages:
            logger.error(f"不支持的按钮类型: {button}")
            return False

        down_msg, up_msg = button_messages[button]

        # 1. 移动到起始位置
        start_lParam = win32api.MAKELONG(start_x, start_y)
        win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, start_lParam)
        time.sleep(0.05)

        # 2. 按下鼠标按钮
        win32gui.PostMessage(hwnd, down_msg, 0, start_lParam)
        time.sleep(0.05)

        logger.info(f"🔽 按下{button}在 ({start_x},{start_y})")

        # 3. 生成拖拽轨迹
        points = []
        for i in range(1, smoothness + 1):  # 从1开始，跳过起始点
            progress = i / smoothness
            x = start_x + (end_x - start_x) * progress
            y = start_y + (end_y - start_y) * progress
            points.append((int(x), int(y)))

        # 计算每个点之间的时间间隔
        interval = duration / len(points) if len(points) > 0 else 0

        logger.info(f" 生成 {len(points)} 个拖拽轨迹点，间隔 {interval:.3f} 秒")

        # 4. 按住按钮的同时移动鼠标 - 使用修复的后台消息发送
        for i, (x, y) in enumerate(points):
            try:
                from main import mouse_move_fixer
                success = mouse_move_fixer.safe_send_background_message(hwnd, win32con.WM_MOUSEMOVE, 0, x, y)
                if not success:
                    # 回退到原始方法
                    lParam = win32api.MAKELONG(x, y)
                    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)
            except ImportError:
                lParam = win32api.MAKELONG(x, y)
                win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)

            if i % 5 == 0:  # 每5个点记录一次
                logger.debug(f" 拖拽点 {i+1}/{len(points)}: ({x}, {y})")

            # 等待到下一个点
            if i < len(points) - 1:
                time.sleep(interval)

        # 5. 释放鼠标按钮
        end_lParam = win32api.MAKELONG(end_x, end_y)
        win32gui.PostMessage(hwnd, up_msg, 0, end_lParam)

        logger.info(f"🔼 在终点 ({end_x},{end_y}) 释放{button}")
        logger.info(f" 后台拖拽完成")
        return True

    except Exception as e:
        logger.error(f"后台拖拽失败: {e}")
        return False

def _get_ocr_results_from_context(card_id: Optional[int]) -> list:
    """从工作流上下文中获取OCR识别结果"""
    try:
        # 使用新的工作流上下文管理器
        from task_workflow.workflow_context import get_latest_ocr_results, get_ocr_results, get_workflow_context

        # 优先获取最新的OCR结果，避免多个OCR卡片导致的混淆
        latest_results = get_latest_ocr_results()
        if latest_results:
            context = get_workflow_context()
            latest_card_id = context.get_global_var('latest_ocr_card_id')
            logger.info(f"从工作流上下文获取到最新OCR结果: {len(latest_results)} 个文字 (来源卡片: {latest_card_id})")
            return latest_results

        # 如果没有最新结果且指定了卡片ID，尝试获取该卡片的OCR结果
        if card_id:
            ocr_results = get_ocr_results(card_id)
            if ocr_results:
                logger.info(f"从工作流上下文获取到卡片 {card_id} 的OCR结果: {len(ocr_results)} 个文字")
                return ocr_results

        # 兼容旧的获取方式（备用）
        # 尝试从全局变量中获取OCR结果
        import sys
        if hasattr(sys.modules.get('__main__', None), 'workflow_ocr_results'):
            ocr_results = getattr(sys.modules['__main__'], 'workflow_ocr_results', {})
            if card_id and card_id in ocr_results:
                logger.info(f"从全局变量获取到OCR结果: {len(ocr_results[card_id])} 个文字")
                return ocr_results[card_id]

        # 尝试从线程本地存储获取
        thread_local = getattr(threading.current_thread(), 'workflow_context', None)
        if thread_local and hasattr(thread_local, 'ocr_results'):
            logger.info(f"从线程本地存储获取到OCR结果: {len(thread_local.ocr_results)} 个文字")
            return thread_local.ocr_results

        logger.warning("未找到OCR识别结果上下文")
        return []

    except Exception as e:
        logger.error(f"获取OCR结果时发生错误: {e}")
        return []

def _get_ocr_target_text_from_context(card_id: Optional[int]) -> tuple:
    """从工作流上下文中获取OCR的目标文字和匹配模式"""
    try:
        from task_workflow.workflow_context import get_workflow_context

        context = get_workflow_context()

        # 优先使用最新的OCR卡片的目标文字，避免多个OCR卡片导致的混淆
        latest_ocr_card_id = context.get_global_var('latest_ocr_card_id')
        logger.info(f" [调试] 最新OCR卡片ID: {latest_ocr_card_id}")

        if latest_ocr_card_id:
            target_text = context.get_card_data(latest_ocr_card_id, 'ocr_target_text', '')
            match_mode = context.get_card_data(latest_ocr_card_id, 'ocr_match_mode', '包含')
            logger.info(f" [调试] 从卡片{latest_ocr_card_id}获取: target_text='{target_text}', match_mode='{match_mode}'")

            if target_text:
                logger.info(f" [调试] 从工作流上下文获取到最新OCR目标文字: '{target_text}' (卡片ID: {latest_ocr_card_id})")
                return target_text, match_mode
            else:
                logger.warning(f" [调试] 卡片{latest_ocr_card_id}的target_text为空")

        # 如果最新OCR卡片没有目标文字且指定了卡片ID，尝试获取该卡片的OCR目标文字
        if card_id and card_id != latest_ocr_card_id:
            target_text = context.get_card_data(card_id, 'ocr_target_text', '')
            match_mode = context.get_card_data(card_id, 'ocr_match_mode', '包含')
            if target_text:
                logger.info(f"从工作流上下文获取到卡片 {card_id} 的OCR目标文字: '{target_text}'")
                return target_text, match_mode

        # 如果都没有找到，查找任意有目标文字的OCR卡片（按卡片ID降序）
        sorted_card_ids = sorted(context.card_data.keys(), reverse=True)
        for cid in sorted_card_ids:
            data = context.card_data[cid]
            if 'ocr_target_text' in data and data['ocr_target_text']:
                target_text = data['ocr_target_text']
                match_mode = data.get('ocr_match_mode', '包含')
                logger.info(f"从工作流上下文获取到备用OCR目标文字: '{target_text}' (卡片ID: {cid})")
                return target_text, match_mode

        logger.debug("未找到OCR目标文字")
        return '', '包含'

    except Exception as e:
        logger.error(f"获取OCR目标文字时发生错误: {e}")
        return '', '包含'

def _get_ocr_region_offset_from_context(card_id: Optional[int]) -> Optional[tuple]:
    """从工作流上下文中获取OCR识别区域的偏移量"""
    try:
        from task_workflow.workflow_context import get_workflow_context

        context = get_workflow_context()

        # 优先使用最新的OCR卡片的区域偏移，避免多个OCR卡片导致的混淆
        latest_ocr_card_id = context.get_global_var('latest_ocr_card_id')
        if latest_ocr_card_id:
            offset = context.get_card_data(latest_ocr_card_id, 'ocr_region_offset', None)
            if offset:
                logger.info(f"从工作流上下文获取到最新OCR区域偏移: {offset} (卡片ID: {latest_ocr_card_id})")
                return offset

        # 如果最新OCR卡片没有区域偏移且指定了卡片ID，尝试获取该卡片的OCR区域偏移
        if card_id and card_id != latest_ocr_card_id:
            offset = context.get_card_data(card_id, 'ocr_region_offset', None)
            if offset:
                logger.info(f"从工作流上下文获取到卡片 {card_id} 的OCR区域偏移: {offset}")
                return offset

        # 如果都没有找到，查找任意有区域偏移的OCR卡片（按卡片ID降序）
        sorted_card_ids = sorted(context.card_data.keys(), reverse=True)
        for cid in sorted_card_ids:
            data = context.card_data[cid]
            if 'ocr_region_offset' in data and data['ocr_region_offset']:
                offset = data['ocr_region_offset']
                logger.info(f"从工作流上下文获取到备用OCR区域偏移: {offset} (卡片ID: {cid})")
                return offset

        logger.debug("未找到OCR区域偏移信息")
        return None

    except Exception as e:
        logger.error(f"获取OCR区域偏移时发生错误: {e}")
        return None

def _find_matching_text_in_ocr_results(ocr_results: list, target_text: str, match_mode: str) -> Optional[dict]:
    """在OCR结果中查找匹配的文字"""
    try:
        if not ocr_results:
            return None

        # 如果没有指定目标文字，返回第一个结果
        if not target_text:
            logger.info("未指定目标文字，使用第一个OCR结果")
            return ocr_results[0] if ocr_results else None

        logger.debug(f"在 {len(ocr_results)} 个OCR结果中查找文字: '{target_text}', 匹配模式: {match_mode}")

        for result in ocr_results:
            text = result.get('text', '')
            confidence = result.get('confidence', 0)

            logger.debug(f"检查OCR结果: '{text}' (置信度: {confidence:.3f})")

            if match_mode == "包含":
                if target_text in text:
                    logger.info(f"找到包含匹配的文字: '{target_text}' 在 '{text}' 中")
                    return result
            elif match_mode == "完全匹配":
                if target_text == text.strip():
                    logger.info(f"找到完全匹配的文字: '{target_text}'")
                    return result
            else:
                # 默认使用包含模式
                if target_text in text:
                    logger.info(f"找到默认包含匹配的文字: '{target_text}' 在 '{text}' 中")
                    return result

        logger.warning(f"未找到匹配的文字: '{target_text}'")
        return None

    except Exception as e:
        logger.error(f"查找匹配文字时发生错误: {e}")
        return None

def _calculate_click_position(bbox: list, position_mode: str, offset_x: int = 0, offset_y: int = 0) -> tuple:
    """根据文字边界框计算点击位置"""
    try:
        if len(bbox) < 8:
            raise ValueError("边界框坐标不足8个")

        # OCR边界框格式通常是 [x1,y1,x2,y2,x3,y3,x4,y4] (四个角点)
        # 计算边界框的最小和最大坐标
        x_coords = [bbox[i] for i in range(0, 8, 2)]  # x坐标: 0,2,4,6
        y_coords = [bbox[i] for i in range(1, 8, 2)]  # y坐标: 1,3,5,7

        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        logger.debug(f"边界框范围: X({min_x}, {max_x}), Y({min_y}, {max_y})")

        # 根据位置模式计算点击坐标
        if position_mode == "文字中心":
            click_x = (min_x + max_x) / 2
            click_y = (min_y + max_y) / 2
        elif position_mode == "文字左上角":
            click_x = min_x
            click_y = min_y
        elif position_mode == "文字右下角":
            click_x = max_x
            click_y = max_y
        elif position_mode == "自定义偏移":
            # 从中心点开始偏移
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            click_x = center_x + offset_x
            click_y = center_y + offset_y
        else:
            # 默认使用中心点
            click_x = (min_x + max_x) / 2
            click_y = (min_y + max_y) / 2

        logger.debug(f"计算点击位置: 模式={position_mode}, 坐标=({click_x}, {click_y}), 偏移=({offset_x}, {offset_y})")
        return int(click_x), int(click_y)

    except Exception as e:
        logger.error(f"计算点击位置时发生错误: {e}")
        # 返回默认坐标
        return 100, 100


def _get_clicked_text_from_context(card_id: Optional[int]) -> str:
    """从工作流上下文中获取当前点击的文字"""
    try:
        from task_workflow.workflow_context import get_workflow_context
        context = get_workflow_context()

        # 获取OCR目标文字作为已点击的文字
        target_text, _ = _get_ocr_target_text_from_context(card_id)
        return target_text

    except Exception as e:
        logger.error(f"获取已点击文字时发生错误: {e}")
        return ""


def _get_ocr_card_id_from_context(card_id: Optional[int]) -> Optional[int]:
    """从工作流上下文中获取OCR卡片ID"""
    try:
        from task_workflow.workflow_context import get_workflow_context
        context = get_workflow_context()

        # 优先查找与当前文字点击卡片关联的OCR卡片ID
        associated_ocr_card_id = context.get_card_data(card_id, 'associated_ocr_card_id', None)
        if associated_ocr_card_id:
            logger.info(f"🔗 [调试] 文字点击卡片{card_id}找到关联的OCR卡片ID: {associated_ocr_card_id}")
            return associated_ocr_card_id

        # 如果没有关联关系，使用最新的OCR卡片ID（向后兼容）
        latest_ocr_card_id = context.get_global_var('latest_ocr_card_id')
        logger.info(f"🔗 [调试] 文字点击卡片{card_id}使用最新OCR卡片ID: {latest_ocr_card_id}")
        return latest_ocr_card_id

    except Exception as e:
        logger.error(f"获取OCR卡片ID时发生错误: {e}")
        return None


def _handle_success(on_success_action: str, success_jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理成功情况"""
    if on_success_action == '跳转到步骤':
        return True, '跳转到步骤', success_jump_id
    elif on_success_action == '停止工作流':
        return True, '停止工作流', None
    elif on_success_action == '继续执行本步骤':
        return True, '继续执行本步骤', card_id
    else:  # 执行下一步
        return True, '执行下一步', None


def _handle_failure(on_failure_action: str, failure_jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理失败情况"""
    if on_failure_action == '跳转到步骤':
        return False, '跳转到步骤', failure_jump_id
    elif on_failure_action == '停止工作流':
        return False, '停止工作流', None
    elif on_failure_action == '继续执行本步骤':
        return False, '继续执行本步骤', card_id
    else:  # 执行下一步
        return False, '执行下一步', None


def _correct_image_paths(raw_paths: List[str], card_id: Optional[int]) -> List[str]:
    """智能纠正图片路径列表

    Args:
        raw_paths: 原始路径列表
        card_id: 卡片ID（用于日志）

    Returns:
        纠正后的有效路径列表
    """
    import os

    corrected_paths = []
    images_dir = "images"  # 默认图片目录

    logger.info(f"[路径纠正] 开始纠正{len(raw_paths)}个图片路径")

    for i, raw_path in enumerate(raw_paths, 1):
        corrected_path = None

        # 跳过空路径
        if not raw_path or not raw_path.strip():
            logger.info(f"  {i}. 空路径 - 跳过")
            continue

        # 显示原始路径（仅文件名）
        if raw_path.startswith('memory://'):
            display_name = raw_path.replace('memory://', '')
        else:
            display_name = os.path.basename(raw_path) if raw_path else f'路径{i}'

        try:
            # 1. 检查原始路径是否有效
            if raw_path.startswith('memory://'):
                # 内存图片路径，直接使用
                corrected_path = raw_path
                logger.info(f"  {i}. {display_name} - 内存图片，直接使用")

            elif os.path.isabs(raw_path):
                # 绝对路径处理
                if os.path.exists(raw_path) and os.path.isfile(raw_path):
                    corrected_path = raw_path
                    logger.info(f"  {i}. {display_name} - 绝对路径有效")
                elif os.path.exists(raw_path) and not os.path.isfile(raw_path):
                    logger.warning(f"  {i}. {display_name} - 绝对路径存在但不是文件，跳过")
                else:
                    # 尝试转换为相对路径
                    filename = os.path.basename(raw_path)
                    relative_path = os.path.join(images_dir, filename)

                    if os.path.exists(relative_path) and os.path.isfile(relative_path):
                        corrected_path = relative_path
                        logger.info(f"  {i}. {display_name} - 绝对路径无效，已纠正为相对路径: {relative_path}")
                    else:
                        logger.warning(f"  {i}. {display_name} - 绝对路径无效，相对路径也不存在或不是文件")

            else:
                # 相对路径处理
                if os.path.exists(raw_path) and os.path.isfile(raw_path):
                    corrected_path = raw_path
                    logger.info(f"  {i}. {display_name} - 相对路径有效")
                elif os.path.exists(raw_path) and not os.path.isfile(raw_path):
                    logger.warning(f"  {i}. {display_name} - 相对路径存在但不是文件，跳过")
                else:
                    # 尝试在images目录中查找
                    filename = os.path.basename(raw_path)
                    images_path = os.path.join(images_dir, filename)

                    if os.path.exists(images_path) and os.path.isfile(images_path):
                        corrected_path = images_path
                        logger.info(f"  {i}. {display_name} - 在images目录找到: {images_path}")
                    elif os.path.exists(images_path) and not os.path.isfile(images_path):
                        logger.warning(f"  {i}. {display_name} - 在images目录找到但不是文件，跳过")
                    else:
                        # 尝试直接使用文件名
                        if os.path.exists(filename):
                            # 检查是否为文件而不是目录
                            if os.path.isfile(filename):
                                corrected_path = filename
                                logger.info(f"  {i}. {display_name} - 在当前目录找到: {filename}")
                            else:
                                logger.warning(f"  {i}. {display_name} - 是目录而不是文件，跳过")
                        else:
                            logger.warning(f"  {i}. {display_name} - 路径无效，未找到文件")

            # 添加有效路径
            if corrected_path:
                corrected_paths.append(corrected_path)

        except Exception as e:
            logger.error(f"  {i}. {display_name} - 路径纠正时发生错误: {e}")

    logger.info(f"[路径纠正] 完成，有效路径: {len(corrected_paths)}/{len(raw_paths)}")

    return corrected_paths
