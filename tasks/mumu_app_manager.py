#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MuMu模拟器应用管理任务模块
基于MuMuManager.exe实现MuMu模拟器的应用管理功能
"""

import time
import logging
from typing import Dict, Any, Optional, Tuple, List
from utils.mumu_manager import get_mumu_manager

logger = logging.getLogger(__name__)

# 任务模块信息
TASK_INFO = {
    "name": "MuMu应用管理",
    "description": "管理MuMu模拟器中的应用，包括启动、关闭、安装、卸载等操作",
    "author": "System",
    "version": "1.0.0"
}


def refresh_apps_list(target_hwnd: Optional[int] = None) -> List[str]:
    """刷新应用列表"""
    try:
        manager = get_mumu_manager()
        if not manager.is_available():
            logger.warning("MuMuManager不可用")
            return ["MuMuManager不可用"]

        # 根据绑定窗口自动确定模拟器索引
        vm_index = 0  # 默认索引
        if target_hwnd:
            hwnd_vm_index = _get_vm_index_from_hwnd(target_hwnd)
            if hwnd_vm_index is not None:
                vm_index = hwnd_vm_index
                logger.info(f"根据绑定窗口自动确定模拟器索引: {vm_index}")
            else:
                logger.warning(f"无法从窗口句柄 {target_hwnd} 确定模拟器索引，使用默认索引 0")
        else:
            logger.info("未指定目标窗口，使用默认模拟器索引: 0")

        logger.info(f"刷新模拟器 {vm_index} 的应用列表")

        # 获取已安装应用
        apps_info = manager.get_installed_apps(vm_index)
        if not apps_info:
            return ["无法获取应用列表"]

        app_list = []
        for package_name, app_info in apps_info.items():
            if package_name == 'active':  # 跳过活动应用信息
                continue

            if isinstance(app_info, dict):
                app_name = app_info.get('name', package_name)
                app_list.append(f"{package_name} - {app_name}")
            else:
                app_list.append(package_name)

        if not app_list:
            return ["未找到已安装的应用"]

        app_list.sort()  # 按字母顺序排序
        logger.info(f"找到 {len(app_list)} 个已安装应用")
        return app_list

    except Exception as e:
        logger.error(f"刷新应用列表时发生错误: {e}")
        return [f"刷新失败: {str(e)}"]


def get_params_definition():
    """获取参数定义"""
    from .task_utils import get_standard_next_step_delay_params, merge_params_definitions

    # 原有的MuMu应用管理参数
    mumu_params = {
        # 操作模式选择
        "operation_mode": {
            "label": "操作模式",
            "type": "select",
            "options": ["启动应用", "重启应用", "关闭应用", "安装应用", "卸载应用"],
            "default": "启动应用",
            "tooltip": "选择要执行的应用操作"
        },

        # 应用选择
        "---app_selection---": {
            "type": "separator",
            "label": "应用选择"
        },
        "refresh_apps": {
            "label": "刷新应用列表",
            "type": "button",
            "button_text": "刷新",
            "tooltip": "重新获取模拟器中的应用列表",
            "widget_hint": "refresh_apps",
            "hide_in_preview": True
        },
        "selected_app": {
            "label": "选择应用",
            "type": "select",
            "options": ["请先刷新应用列表"],
            "default": "请先刷新应用列表",
            "tooltip": "选择要操作的应用",
            "widget_hint": "app_selector"
        },
        "apk_path": {
            "label": "APK文件路径",
            "type": "file",
            "default": "",
            "tooltip": "要安装的APK文件路径",
            "file_types": "APK文件 (*.apk);;所有文件 (*.*)",
            "condition": {"param": "operation_mode", "value": "安装应用"}
        },



        # 延迟参数
        "---delay_params---": {"type": "separator", "label": "延迟设置"},
        "delay_mode": {
            "label": "延迟模式",
            "type": "select",
            "options": ["固定延迟", "随机延迟"],
            "default": "固定延迟",
            "tooltip": "选择固定延迟时间还是随机延迟时间"
        },
        "fixed_delay": {
            "label": "固定延迟 (秒)",
            "type": "float",
            "default": 2.0,
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
            "default": 1.0,
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
            "default": 3.0,
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
            "tooltip": "操作成功后的行为"
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
            "tooltip": "操作失败后的行为"
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

    # 合并延迟参数
    return merge_params_definitions(mumu_params, get_standard_next_step_delay_params())


def _interruptible_sleep(duration: float, stop_checker=None):
    """可中断的睡眠函数"""
    if duration <= 0:
        return

    elapsed_time = 0.0
    check_interval = 0.1  # 每100ms检查一次停止信号

    while elapsed_time < duration:
        if stop_checker and stop_checker():
            logger.info(f"延迟被用户中断，已延迟 {elapsed_time:.2f}/{duration:.2f} 秒")
            return

        sleep_time = min(check_interval, duration - elapsed_time)
        time.sleep(sleep_time)
        elapsed_time += sleep_time


def _handle_delay_after_operation(params, stop_checker=None):
    """处理操作后延迟"""
    try:
        import random

        delay_mode = params.get('delay_mode', '固定延迟')

        if delay_mode == '固定延迟':
            delay_time = params.get('fixed_delay', 2.0)
            logger.info(f"执行固定延迟: {delay_time} 秒")
            _interruptible_sleep(delay_time, stop_checker)
        elif delay_mode == '随机延迟':
            min_delay = params.get('min_delay', 1.0)
            max_delay = params.get('max_delay', 3.0)
            delay_time = random.uniform(min_delay, max_delay)
            logger.info(f"执行随机延迟: {delay_time:.2f} 秒 (范围: {min_delay}-{max_delay})")
            _interruptible_sleep(delay_time, stop_checker)
        else:
            logger.warning(f"未知的延迟模式: {delay_mode}")
    except Exception as e:
        logger.error(f"执行延迟时发生错误: {e}")


def _get_vm_index_from_hwnd(target_hwnd: Optional[int]) -> Optional[int]:
    """根据窗口句柄获取MuMu模拟器索引"""
    if not target_hwnd:
        logger.debug("目标窗口句柄为空")
        return None

    try:
        logger.info(f"开始获取窗口句柄 {target_hwnd} 对应的MuMu模拟器索引")

        # 方法1：使用MuMu管理器获取
        manager = get_mumu_manager()
        if not manager.is_available():
            logger.warning("MuMuManager不可用")
            return None

        simulator_info = manager.get_simulator_by_hwnd(target_hwnd)
        if simulator_info:
            vm_index = simulator_info.get('index')
            if vm_index is not None:
                logger.info(f"通过MuMu管理器获取VM索引成功: {target_hwnd} -> VM{vm_index}")
                return int(vm_index)

        # 方法2：使用MuMu输入模拟器获取（支持渲染窗口）
        logger.info("MuMu管理器方法失败，尝试使用MuMu输入模拟器")
        try:
            from utils.mumu_input_simulator import get_mumu_input_simulator
            mumu_simulator = get_mumu_input_simulator()
            if mumu_simulator:
                vm_index = mumu_simulator.get_vm_index_from_hwnd(target_hwnd)
                if vm_index is not None:
                    logger.info(f"通过MuMu输入模拟器获取VM索引成功: {target_hwnd} -> VM{vm_index}")
                    return vm_index
        except Exception as e:
            logger.warning(f"MuMu输入模拟器获取VM索引失败: {e}")

        # 方法3：检查是否是MuMu主窗口，如果是渲染窗口则查找主窗口
        logger.info("尝试查找MuMu主窗口")
        try:
            import win32gui
            window_title = win32gui.GetWindowText(target_hwnd)
            window_class = win32gui.GetClassName(target_hwnd)
            logger.info(f"窗口信息: 标题='{window_title}', 类名='{window_class}'")

            # 如果是渲染窗口，尝试找到主窗口
            if window_class == "nemuwin" and "nemudisplay" in window_title.lower():
                logger.info("检测到MuMu渲染窗口，尝试查找主窗口")
                parent_hwnd = win32gui.GetParent(target_hwnd)
                while parent_hwnd:
                    parent_title = win32gui.GetWindowText(parent_hwnd)
                    parent_class = win32gui.GetClassName(parent_hwnd)
                    logger.debug(f"检查父窗口: {parent_title} ({parent_class}) HWND:{parent_hwnd}")

                    if "MuMu安卓设备" in parent_title and parent_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"]:
                        logger.info(f"找到MuMu主设备窗口: {parent_title}")
                        # 递归调用，使用主窗口句柄
                        return _get_vm_index_from_hwnd(parent_hwnd)

                    parent_hwnd = win32gui.GetParent(parent_hwnd)
        except Exception as e:
            logger.warning(f"查找MuMu主窗口失败: {e}")

        logger.warning(f"所有方法都无法找到窗口句柄 {target_hwnd} 对应的MuMu模拟器索引")
        return None

    except Exception as e:
        logger.error(f"获取MuMu模拟器索引失败: {e}")
        return None


def _handle_success(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理成功情况"""
    if action == "跳转到步骤" and jump_id is not None:
        logger.info(f"操作成功，跳转到步骤 {jump_id}")
        return True, "跳转到步骤", jump_id
    elif action == "停止工作流":
        logger.info("操作成功，停止工作流")
        return True, "停止工作流", None
    elif action == "继续执行本步骤":
        logger.info("操作成功，继续执行本步骤")
        return True, "继续执行本步骤", card_id
    else:  # "执行下一步"
        logger.info("操作成功，执行下一步")
        return True, "执行下一步", None


def _handle_failure(action: str, jump_id: Optional[int], card_id: Optional[int]) -> Tuple[bool, str, Optional[int]]:
    """处理失败情况"""
    if action == "跳转到步骤" and jump_id is not None:
        logger.info(f"操作失败，跳转到步骤 {jump_id}")
        return False, "跳转到步骤", jump_id
    elif action == "停止工作流":
        logger.info("操作失败，停止工作流")
        return False, "停止工作流", None
    elif action == "继续执行本步骤":
        logger.info("操作失败，继续执行本步骤")
        return False, "继续执行本步骤", card_id
    else:  # "执行下一步"
        logger.info("操作失败，执行下一步")
        return False, "执行下一步", None


def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
                target_hwnd: Optional[int], window_region: Optional[tuple], card_id: Optional[int],
                get_image_data=None, **kwargs) -> Tuple[bool, str, Optional[int]]:
    """执行MuMu模拟器应用管理任务 - execute_task 接口"""
    return execute(params, counters, execution_mode, target_hwnd, card_id, get_image_data, kwargs.get('stop_checker'))


def execute(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
           target_hwnd: Optional[int], card_id: Optional[int], get_image_data=None, stop_checker=None) -> Tuple[bool, str, Optional[int]]:
    """执行MuMu模拟器应用管理任务"""
    
    try:
        # 检查执行环境
        import os
        is_multi_window_mode = os.environ.get('MULTI_WINDOW_MODE') == 'true'
        logger.info(f"🌐 执行环境: 多窗口模式={is_multi_window_mode}")

        # 获取参数
        operation_mode = params.get('operation_mode', '启动应用')
        selected_app = params.get('selected_app', '').strip()
        apk_path = params.get('apk_path', '').strip()
        on_success = params.get('on_success', '执行下一步')
        success_jump_id = params.get('success_jump_target_id')
        on_failure = params.get('on_failure', '执行下一步')
        failure_jump_id = params.get('failure_jump_target_id')

        logger.info(f"🎯 执行MuMu应用管理任务: {operation_mode}")
        logger.info(f"📱 目标窗口句柄: {target_hwnd}")
        logger.info(f"🔧 执行模式: {execution_mode}")

        # 获取MuMu管理器
        manager = get_mumu_manager()
        if not manager.is_available():
            logger.error("❌ MuMuManager不可用，请确保已安装MuMu模拟器12")
            from .task_utils import handle_failure_action
            return handle_failure_action(params, card_id)

        # 根据绑定窗口自动确定模拟器索引
        vm_index = 0  # 默认索引

        # 优先使用传入的target_hwnd，如果没有则尝试从环境变量获取
        effective_hwnd = target_hwnd
        if not effective_hwnd and is_multi_window_mode:
            env_hwnd = os.environ.get('TARGET_WINDOW_HWND')
            if env_hwnd:
                try:
                    effective_hwnd = int(env_hwnd)
                    logger.info(f"🌐 从环境变量获取目标窗口句柄: {effective_hwnd}")
                except ValueError:
                    logger.warning(f"⚠️ 环境变量中的窗口句柄格式错误: {env_hwnd}")

        if effective_hwnd:
            logger.info(f"🔍 开始根据窗口句柄 {effective_hwnd} 获取VM索引...")
            hwnd_vm_index = _get_vm_index_from_hwnd(effective_hwnd)
            if hwnd_vm_index is not None:
                vm_index = hwnd_vm_index
                logger.info(f"✅ 根据绑定窗口自动确定模拟器索引: VM{vm_index}")
            else:
                logger.warning(f"⚠️ 无法从窗口句柄 {effective_hwnd} 确定模拟器索引，使用默认索引 0")
        else:
            logger.info("ℹ️ 未指定目标窗口，使用默认模拟器索引: 0")

        logger.info(f"🎮 最终使用模拟器索引: VM{vm_index}")

        # 从选择的应用中提取包名
        package_name = ""
        if selected_app and selected_app != "请先刷新应用列表":
            # 从选择的应用中提取包名
            if " - " in selected_app:
                package_name = selected_app.split(" - ")[0]
            else:
                package_name = selected_app

        logger.info(f"提取的应用包名: {package_name}")

        # 执行不同的操作
        success = False
        message = ""

        if operation_mode == "启动应用":
            if not package_name:
                logger.error("未指定应用包名")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"启动应用: {package_name}")
            success = manager.launch_app(vm_index, package_name)
            message = f"启动应用 {package_name} {'成功' if success else '失败'}"

        elif operation_mode == "重启应用":
            if not package_name:
                logger.error("未指定应用包名")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"重启应用: {package_name}")
            # 先关闭再启动
            manager.close_app(vm_index, package_name)
            time.sleep(1)  # 等待关闭完成
            success = manager.launch_app(vm_index, package_name)
            message = f"重启应用 {package_name} {'成功' if success else '失败'}"

        elif operation_mode == "关闭应用":
            if not package_name:
                logger.error("未指定应用包名")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"关闭应用: {package_name}")
            success = manager.close_app(vm_index, package_name)
            message = f"关闭应用 {package_name} {'成功' if success else '失败'}"

        elif operation_mode == "安装应用":
            if not apk_path:
                logger.error("未指定APK文件路径")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"安装应用: {apk_path}")
            success = manager.install_app(vm_index, apk_path)
            message = f"安装应用 {apk_path} {'成功' if success else '失败'}"

        elif operation_mode == "卸载应用":
            if not package_name:
                logger.error("未指定应用包名")
                from .task_utils import handle_failure_action
                return handle_failure_action(params, card_id)

            logger.info(f"卸载应用: {package_name}")
            success = manager.uninstall_app(vm_index, package_name)
            message = f"卸载应用 {package_name} {'成功' if success else '失败'}"

        else:
            logger.error(f"未知的操作模式: {operation_mode}")
            from .task_utils import handle_failure_action
            return handle_failure_action(params, card_id)
        
        # 返回结果（使用统一的成功/失败处理，包含延迟）
        if success:
            logger.info(message)
            from .task_utils import handle_success_action
            return handle_success_action(params, card_id, stop_checker)
        else:
            logger.error(message)
            from .task_utils import handle_failure_action
            return handle_failure_action(params, card_id)

    except Exception as e:
        logger.error(f"执行MuMu应用管理任务时发生异常: {e}")
        from .task_utils import handle_failure_action
        return handle_failure_action(params, card_id)


if __name__ == "__main__":
    # 测试模块
    test_params = {
        "operation_mode": "启动应用",
        "selected_app": "com.tencent.jkchess - com.tencent.jkchess",
        "delay_mode": "固定延迟",
        "fixed_delay": 1.0,
        "on_success": "执行下一步",
        "on_failure": "执行下一步"
    }

    result = execute(test_params, {}, "test", None, None)
    print(f"测试结果: {result}")
