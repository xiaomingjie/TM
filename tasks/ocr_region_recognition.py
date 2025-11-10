# -*- coding: utf-8 -*-

"""
OCR文字识别任务模块
支持指定窗口区域进行文字识别，CPU模式优化
"""

import logging
import time
import numpy as np
from typing import Dict, Any, Optional, Tuple, List

# Windows API 相关导入
try:
    import win32gui
    import win32api
    import win32con
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

# 使用统一OCR服务管理器（支持FastDeploy和PaddleOCR）
from services.unified_ocr_service import (
    initialize_unified_ocr_service,
    is_unified_ocr_service_ready,
    recognize_text_with_unified_service,
    shutdown_unified_ocr_service
)

# 导入通用坐标系统
from utils.universal_coordinate_system import (
    get_universal_coordinate_system, CoordinateInfo, CoordinateType
)

# 先初始化logger
logger = logging.getLogger(__name__)

# 并发OCR管理器已移除，直接使用统一OCR服务作为备选
CONCURRENT_OCR_AVAILABLE = False

# 导入现有的窗口捕获功能
try:
    from utils.win32_utils import capture_window_background
    CAPTURE_AVAILABLE = True
except ImportError:
    CAPTURE_AVAILABLE = False

# 任务类型标识
TASK_TYPE = "OCR文字识别"
TASK_NAME = "OCR文字识别"

def _get_ocr_engine() -> Optional[dict]:
    """获取可用的OCR引擎（使用常驻服务）"""
    logger.info("[OCR服务] 检查OCR服务状态...")

    # 检查统一OCR服务是否已就绪
    if is_unified_ocr_service_ready():
        logger.info("[OCR服务] 统一OCR服务已就绪，直接使用常驻引擎")
        return {'engine': 'service', 'instance': None}

    # 如果服务未就绪，尝试初始化（优先使用FastDeploy）
    logger.info("[OCR服务] 统一OCR服务未就绪，正在初始化常驻服务...")
    if initialize_unified_ocr_service():
        logger.info("[OCR服务] 统一OCR常驻服务初始化成功")
        return {'engine': 'service', 'instance': None}
    else:
        logger.error("[OCR服务] 统一OCR常驻服务初始化失败")
        return None

def execute_task(params: Dict[str, Any], counters: Dict[str, int], execution_mode: str,
                target_hwnd: Optional[int], window_region: Optional[Tuple[int, int, int, int]],
                card_id: Optional[int] = None, **kwargs) -> Tuple[bool, str, Optional[int]]:
    """
    执行OCR区域识别任务

    Args:
        params: 任务参数
        counters: 计数器
        execution_mode: 执行模式
        target_hwnd: 目标窗口句柄
        window_region: 窗口区域
        card_id: 卡片ID
        **kwargs: 其他参数

    Returns:
        Tuple[bool, str, Optional[int]]: (成功状态, 动作, 下一个卡片ID)
    """

    # 获取停止检查器
    stop_checker = kwargs.get('stop_checker', None)

    # 获取参数
    region_mode = params.get('region_mode', '指定区域')

    # 框选区域模式参数
    region_x = params.get('region_x', 0)
    region_y = params.get('region_y', 0)
    region_width = params.get('region_width', 200)
    region_height = params.get('region_height', 100)

    #  修复：如果分离参数都是0，尝试从region_coordinates字符串中解析
    if region_x == 0 and region_y == 0 and region_width == 0 and region_height == 0:
        region_coordinates = params.get('region_coordinates', '')
        if region_coordinates and region_coordinates != '未指定识别区域':
            try:
                # 解析格式：'X=694, Y=141, 宽度=82, 高度=81'
                import re
                x_match = re.search(r'X=(\d+)', region_coordinates)
                y_match = re.search(r'Y=(\d+)', region_coordinates)
                width_match = re.search(r'宽度=(\d+)', region_coordinates)
                height_match = re.search(r'高度=(\d+)', region_coordinates)

                if x_match and y_match and width_match and height_match:
                    region_x = int(x_match.group(1))
                    region_y = int(y_match.group(1))
                    region_width = int(width_match.group(1))
                    region_height = int(height_match.group(1))
                    logger.info(f"成功从region_coordinates解析坐标: ({region_x}, {region_y}, {region_width}, {region_height})")
                else:
                    logger.warning(f"无法解析region_coordinates: {region_coordinates}")
            except Exception as e:
                logger.error(f"解析region_coordinates失败: {e}")

    # 目标文字设置
    text_recognition_mode = params.get('text_recognition_mode', '单组文字')
    target_text = params.get('target_text', '')
    target_text_groups = params.get('target_text_groups', '')
    match_mode = params.get('match_mode', '包含')
    reset_clicked_texts_on_next_run = params.get('reset_clicked_texts_on_next_run', False)

    # 调试：打印参数信息
    logger.info(f"[卡片{card_id}] 参数调试 - 识别模式: {text_recognition_mode}, 目标文字: '{target_text}', 多组文字: '{target_text_groups}', 匹配模式: {match_mode}")
    logger.info(f"[卡片{card_id}] 原始参数字典: {params}")

    # 解析多组文字
    if text_recognition_mode == '多组文字' and target_text_groups:
        # 支持中文逗号（，）和英文逗号（,）分隔多组文字
        import re
        # 使用正则表达式同时匹配中文和英文逗号
        text_groups = [text.strip() for text in re.split('[,，]', target_text_groups) if text.strip()]
        if not text_groups:
            logger.warning("多组文字模式下未提供有效的文字组，切换到单组模式")
            text_recognition_mode = '单组文字'
        else:
            logger.info(f"解析到{len(text_groups)}组文字: {text_groups}")
    else:
        text_groups = [target_text] if target_text else ['']

    # OCR设置
    ocr_language = '中英文'
    confidence_threshold = params.get('confidence_threshold', 0.6)
    max_retry_count = params.get('max_retry_count', 3)
    retry_delay = params.get('retry_delay', 1.0)
    
    # 执行后操作参数
    on_success_action = params.get('on_success', '执行下一步')
    success_jump_id = params.get('success_jump_target_id')
    on_failure_action = params.get('on_failure', '执行下一步')
    failure_jump_id = params.get('failure_jump_target_id')

    # 获取窗口信息用于并发OCR管理
    window_title = "unknown"
    if target_hwnd:
        try:
            import win32gui
            window_title = win32gui.GetWindowText(target_hwnd)
            if not window_title:
                window_title = f"HWND_{target_hwnd}"
        except:
            window_title = f"HWND_{target_hwnd}"

    # 将窗口标题添加到参数中，供OCR使用
    params['window_title'] = window_title

    # 移除详细的print输出，避免敏感信息泄露
    # 保留基本的日志记录

    logger.info(f"启动 [OCR任务] 开始执行OCR区域识别")
    logger.info(f"列表 [OCR任务] 参数信息:")
    logger.info(f"   区域模式: '{region_mode}'")
    logger.info(f"   目标文字: '{target_text}'")
    logger.info(f"   匹配模式: '{match_mode}'")
    logger.info(f"   框选坐标: ({region_x}, {region_y}, {region_width}, {region_height})")
    logger.info(f"🔗 [OCR任务] 执行环境:")
    logger.info(f"   窗口句柄: {target_hwnd}")
    logger.info(f"   窗口区域: {window_region}")
    logger.info(f"   执行模式: {execution_mode}")
    logger.info(f"   卡片ID: {card_id}")

    try:
        # 1. 获取OCR引擎（支持打包后运行）
        try:
            ocr_engine = _get_ocr_engine()
            if not ocr_engine:
                logger.error("错误 [OCR引擎] OCR引擎不可用")
                logger.error("可能的原因:")
                logger.error("1. PaddleOCR未正确安装")
                logger.error("2. 打包环境缺少必要文件")
                logger.error("3. 系统权限不足")
                logger.error("建议: 请检查OCR依赖或使用无OCR版本")
                return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)
        except Exception as e:
            logger.error(f"错误 [OCR引擎] OCR引擎初始化异常: {e}")
            logger.error("这可能是由于打包环境问题导致的")
            logger.error("建议: 请使用无OCR版本或检查依赖安装")
            return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

        # 2. 捕获窗口截图
        logger.info(f"搜索 [OCR截图] 开始截图，窗口句柄: {target_hwnd}")

        if not target_hwnd or not PYWIN32_AVAILABLE:
            logger.error(f"错误 [OCR截图] 需要有效的窗口句柄和pywin32支持 (句柄: {target_hwnd}, pywin32: {PYWIN32_AVAILABLE})")
            return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

        if not win32gui.IsWindow(target_hwnd):
            logger.error(f"错误 [OCR截图] 窗口句柄 {target_hwnd} 无效")
            return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

        # 获取窗口信息用于调试
        try:
            window_title = win32gui.GetWindowText(target_hwnd)
            window_rect = win32gui.GetWindowRect(target_hwnd)
            logger.info(f"列表 [OCR截图] 目标窗口: '{window_title}', 位置: {window_rect}")
        except Exception as e:
            logger.warning(f"警告 [OCR截图] 无法获取窗口信息: {e}")

        # 捕获窗口
        logger.info(f"照片 [OCR截图] 正在捕获窗口...")
        window_image = capture_window_background(target_hwnd)
        if window_image is None:
            logger.error(f"错误 [OCR截图] 无法捕获窗口截图，可能原因:")
            logger.error(f"   1. 窗口被最小化或隐藏")
            logger.error(f"   2. 窗口权限不足")
            logger.error(f"   3. 窗口尺寸为0")
            logger.error(f"   4. 系统截图功能异常")
            return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

        height, width = window_image.shape[:2]
        logger.info(f"成功 [OCR截图] 截图成功，尺寸: {width} x {height}")



        # 3. 确定识别区域（直接使用原始坐标，不进行DPI转换）
        if region_mode == '整个窗口':
            # 整个窗口模式：使用整个窗口作为识别区域
            final_x, final_y = 0, 0
            final_width, final_height = window_image.shape[1], window_image.shape[0]
            logger.info(f"使用整个窗口: ({final_x}, {final_y}, {final_width}, {final_height})")
        else:
            # 指定区域模式：直接使用原始坐标，不进行DPI转换
            # 因为OCR区域选择器已经返回了正确的窗口相对坐标
            final_x, final_y = region_x, region_y
            final_width, final_height = region_width, region_height
            logger.info(f"使用指定区域（原始坐标）: ({final_x}, {final_y}, {final_width}, {final_height})")

            # 注释掉的坐标转换代码，待修复后重新启用
            # try:
            #     coord_system = get_universal_coordinate_system()
            #     region_info = CoordinateInfo(
            #         x=region_x, y=region_y, width=region_width, height=region_height,
            #         coord_type=CoordinateType.REFERENCE
            #     )
            #     converted_x, converted_y, converted_width, converted_height = coord_system.process_ocr_region(
            #         region_info, target_hwnd
            #     )
            #     final_x, final_y = converted_x, converted_y
            #     final_width, final_height = converted_width, converted_height
            # except Exception as e:
            #     logger.error(f"坐标转换失败: {e}")
            #     final_x, final_y = region_x, region_y
            #     final_width, final_height = region_width, region_height

            logger.info(f"使用框选区域: ({final_x}, {final_y}, {final_width}, {final_height})")

        # 4. 裁剪识别区域
        logger.info(f"搜索 [OCR区域] 准备裁剪区域: ({final_x}, {final_y}, {final_width}, {final_height})")
        logger.info(f"搜索 [OCR区域] 原始窗口尺寸: {window_image.shape[1]} x {window_image.shape[0]}")

        # 检查坐标是否在窗口范围内
        window_width, window_height = window_image.shape[1], window_image.shape[0]



        if final_x < 0 or final_y < 0 or final_x >= window_width or final_y >= window_height:
            logger.warning(f"警告 [OCR区域] 坐标超出窗口范围！")
            logger.warning(f"   窗口尺寸: {window_width} x {window_height}")
            logger.warning(f"   请求坐标: ({final_x}, {final_y})")
            logger.warning(f"   可能原因: 1) 窗口移动了 2) DPI缩放 3) 坐标转换错误")

        if final_x + final_width > window_width or final_y + final_height > window_height:
            logger.warning(f"警告 [OCR区域] 区域超出窗口边界！")
            logger.warning(f"   窗口尺寸: {window_width} x {window_height}")
            logger.warning(f"   请求区域: ({final_x}, {final_y}) 到 ({final_x + final_width}, {final_y + final_height})")
            logger.warning(f"   将自动裁剪到窗口范围内")
            logger.warning(f"   可能原因: 1) 框选时窗口尺寸不同 2) 坐标系统不匹配")

        roi_image = _extract_region(window_image, final_x, final_y, final_width, final_height)
        if roi_image is None:
            logger.error("错误 [OCR区域] 无法提取指定区域")
            return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

        roi_height, roi_width = roi_image.shape[:2]
        logger.info(f"成功 [OCR区域] 成功提取区域，尺寸: {roi_width} x {roi_height}")

        # 记录区域信息
        logger.info(f"搜索 [OCR区域] 坐标({final_x},{final_y}), 尺寸({final_width}x{final_height})")



        # 5. 图像预处理（性能优化版）
        try:
            import cv2

            # 直接放大2倍（最简单有效的方法）
            height, width = roi_image.shape[:2]
            enlarged_2x = cv2.resize(roi_image, (width*2, height*2), interpolation=cv2.INTER_CUBIC)

        except Exception as e:
            logger.error(f"错误 [图像预处理] 预处理失败: {e}")
            # 预处理失败时使用原始图像
            enlarged_2x = roi_image

        # 6. 执行OCR识别（带重试机制和错误过滤）
        logger.info(f"搜索 [OCR识别] 开始OCR识别，置信度阈值: {confidence_threshold}，最大重试: {max_retry_count}")

        # 显示统一OCR服务状态
        try:
            from services.unified_ocr_service import get_unified_ocr_service
            service = get_unified_ocr_service()
            stats = service.get_service_info()
            logger.info(f"图表 [OCR服务] 状态: 引擎={stats['engine_type']}, 激活={stats['service_active']}, 错误={stats['error_count']}")
        except Exception:
            pass  # 忽略统计信息获取失败

        best_results = []
        best_count = 0
        retry_count = 0

        # 重试循环
        while retry_count < max_retry_count:
            # 在每次重试开始时检查停止请求
            if stop_checker and stop_checker():
                logger.info("用户按下停止按钮，终止OCR识别循环")
                return False, '停止工作流', None

            logger.info(f"刷新 [OCR重试] 第 {retry_count + 1}/{max_retry_count} 次尝试")

            current_best_results = []
            current_best_count = 0

            # 直接使用放大2倍图像进行OCR识别
            logger.debug(f"搜索 [OCR识别] 使用放大2倍图像进行识别...")

            # 记录单次识别开始时间
            single_ocr_start = time.time()

            # 优先使用多OCR服务池（一窗口一服务）
            try:
                from services.multi_ocr_pool import get_multi_ocr_pool
                multi_ocr_pool = get_multi_ocr_pool()

                # 使用传入的target_hwnd参数，而不是从params中获取
                window_hwnd = target_hwnd if target_hwnd else 0

                results = multi_ocr_pool.recognize_text(
                    window_title=window_title,
                    window_hwnd=window_hwnd,
                    image=enlarged_2x,
                    confidence=0.1
                )
                logger.debug(f"使用多OCR服务池识别: {window_title} (HWND: {window_hwnd})")

            except ImportError:
                logger.debug("多OCR服务池不可用，使用统一OCR服务")
                # 回退到统一OCR服务
                results = recognize_text_with_unified_service(enlarged_2x, 0.1)  # 低置信度

            # 记录单次识别耗时
            single_ocr_time = (time.time() - single_ocr_start) * 1000  # 转换为毫秒

            # 计算最高置信度
            current_max_confidence = 0.0
            if results:
                current_max_confidence = max([r.get('confidence', 0) for r in results])
                logger.info(f"编辑 [OCR识别] 识别到 {len(results)} 个文字，置信度: {current_max_confidence:.3f}，耗时: {single_ocr_time:.0f}ms")

                # 重要：将bbox坐标从放大2倍图像还原到原始尺寸
                # 因为OCR识别使用了放大2倍的图像，所以bbox坐标需要除以2
                for result in results:
                    if 'bbox' in result and result['bbox']:
                        original_bbox = result['bbox']
                        # 将所有坐标除以2，还原到原始图像尺寸
                        scaled_bbox = [coord / 2.0 for coord in original_bbox]
                        result['bbox'] = scaled_bbox
                        logger.debug(f"坐标缩放还原: {original_bbox} -> {scaled_bbox}")

                # 显示识别结果
                for i, result in enumerate(results):
                    text = result.get('text', '')
                    confidence = result.get('confidence', 0)
                    logger.info(f"   结果{i+1}: '{text}' (置信度: {confidence:.3f})")

                current_best_count = len(results)
                current_best_results = results
            else:
                logger.debug(f"编辑 [OCR识别] 未识别到文字，耗时: {single_ocr_time:.0f}ms")
                current_best_count = 0
                current_best_results = []

            # 检查是否找到目标文字
            if current_best_results:
                # 根据是否有目标文字使用不同的置信度阈值
                if target_text:
                    # 有目标文字时，使用用户设置的置信度阈值
                    filtered_results = [r for r in current_best_results if r.get('confidence', 0) >= confidence_threshold]
                    # 检查是否包含目标文字
                    if _check_target_text(filtered_results, target_text, match_mode):
                        logger.info(f"成功 [OCR重试] 第 {retry_count + 1} 次尝试成功找到目标文字!")
                        best_results = current_best_results
                        best_count = current_best_count
                        break
                else:
                    # 没有目标文字时，使用较低的置信度阈值（0.3）
                    filtered_results = [r for r in current_best_results if r.get('confidence', 0) >= 0.3]
                    if filtered_results:
                        logger.info(f"成功 [OCR重试] 第 {retry_count + 1} 次尝试成功识别到文字!")
                        best_results = current_best_results
                        best_count = current_best_count
                        break

            # 更新最好结果（即使没找到目标文字）
            if current_best_count > best_count:
                best_count = current_best_count
                best_results = current_best_results

            retry_count += 1

            # 如果不是最后一次重试，等待一段时间
            if retry_count < max_retry_count:
                logger.info(f"⏳ [OCR重试] 等待 {retry_delay} 秒后重试...")

                # 在等待期间检查停止请求（只在等待时检查，不影响正常识别）
                sleep_time = 0
                while sleep_time < retry_delay:
                    if stop_checker and stop_checker():
                        logger.info("用户按下停止按钮，终止OCR重试循环")
                        return False, '停止工作流', None
                    time.sleep(0.1)  # 每0.1秒检查一次停止按钮
                    sleep_time += 0.1

        # 使用最好的结果进行后续处理
        # 如果没有指定目标文字，使用较低的置信度阈值以识别更多文字
        if not target_text:
            # 没有目标文字时，使用较低的置信度阈值（0.3）
            ocr_results = [r for r in best_results if r.get('confidence', 0) >= 0.3]
            logger.info(f"编辑 [OCR识别] 无目标文字模式，使用较低置信度阈值(0.3)，识别到 {len(ocr_results)} 个文字结果")
        else:
            # 有目标文字时，使用用户设置的置信度阈值
            ocr_results = [r for r in best_results if r.get('confidence', 0) >= confidence_threshold]
            logger.info(f"编辑 [OCR识别] 目标文字模式，使用置信度阈值({confidence_threshold})，识别到 {len(ocr_results)} 个文字结果")

        logger.info(f"编辑 [OCR识别] 经过 {retry_count} 次重试，最终识别到 {len(ocr_results)} 个有效文字结果")

        # 显示所有识别到的文字（用于调试）
        if ocr_results:
            logger.info("编辑 [OCR识别] 识别到的文字:")
            for i, result in enumerate(ocr_results):
                text = result.get('text', '')
                confidence = result.get('confidence', 0)
                logger.info(f"   文字{i+1}: '{text}' (置信度: {confidence:.3f})")
        else:
            logger.warning("警告 [OCR识别] 未识别到任何文字，可能原因:")
            logger.warning("   1. 区域内没有文字")
            logger.warning("   2. 文字太小或不清晰")
            logger.warning("   3. 置信度阈值太高")
            logger.warning("   4. 文字颜色与背景对比度不够")

        # 6. 处理多组文字识别逻辑
        if text_recognition_mode == '多组文字':
            return _handle_multi_text_recognition(
                ocr_results, text_groups, match_mode, card_id,
                final_x, final_y, on_success_action, success_jump_id,
                on_failure_action, failure_jump_id, reset_clicked_texts_on_next_run,
                stop_checker
            )
        else:
            # 单组文字识别逻辑（保持原有逻辑）
            logger.info(f"[卡片{card_id}][单组文字] 查找目标文字: '{target_text}', 匹配模式: {match_mode}")
            found_target, target_result = _check_target_text_with_position(ocr_results, target_text, match_mode)

            if found_target:
                logger.info(f"[卡片{card_id}][单组文字] 成功找到目标文字: '{target_text}'")

                # 将OCR识别结果保存到工作流上下文中，供后续卡片使用
                try:
                    from task_workflow.workflow_context import set_ocr_results, get_workflow_context
                    set_ocr_results(card_id, ocr_results)

                    # 同时保存OCR的目标文字信息和识别区域偏移，供文字位置点击使用
                    context = get_workflow_context()
                    context.set_card_data(card_id, 'ocr_target_text', target_text)
                    context.set_card_data(card_id, 'ocr_match_mode', match_mode)
                    context.set_card_data(card_id, 'ocr_region_offset', (final_x, final_y))  # 保存识别区域的偏移

                    logger.info(f"OCR结果已保存到工作流上下文: 卡片ID={card_id}, 结果数={len(ocr_results)}")
                    logger.info(f"OCR目标文字: '{target_text}', 匹配模式: {match_mode}")
                except Exception as e:
                    logger.warning(f"保存OCR结果到工作流上下文失败: {e}")

                logger.info(f" [调试] OCR识别成功，准备跳转: action={on_success_action}, target_id={success_jump_id}")

                # 如果跳转到文字点击卡片，记录关联关系
                if on_success_action == '跳转到步骤' and success_jump_id:
                    try:
                        context.set_card_data(success_jump_id, 'associated_ocr_card_id', card_id)
                        logger.info(f"🔗 [调试] 记录关联关系: 文字点击卡片{success_jump_id} ← OCR卡片{card_id}")
                    except Exception as e:
                        logger.warning(f"记录OCR关联关系失败: {e}")

                return _handle_success(on_success_action, success_jump_id, card_id, stop_checker)
            else:
                if target_text:
                    logger.warning(f"错误 [OCR匹配] 未找到目标文字: '{target_text}'")
                else:
                    logger.warning("错误 [OCR匹配] OCR识别完成，但未识别到任何文字")

                # OCR识别失败时清除上下文数据
                try:
                    from task_workflow.workflow_context import get_workflow_context
                    context = get_workflow_context()
                    context.clear_card_ocr_context(card_id)
                    logger.info(f"[卡片{card_id}][单组文字] OCR识别失败，已清除上下文数据")
                except Exception as e:
                    logger.warning(f"清除OCR上下文数据失败: {e}")

                return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

    except Exception as e:
        logger.error(f"OCR区域识别任务执行失败: {e}", exc_info=True)

        # 异常时清除上下文数据
        try:
            from task_workflow.workflow_context import get_workflow_context
            context = get_workflow_context()
            context.clear_card_ocr_context(card_id)
            logger.info(f"[卡片{card_id}] OCR异常处理，已清除上下文数据")
        except:
            pass

        return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

    finally:
        # OCR任务完成后，无需重置统一OCR服务状态（保持常驻）
        logger.debug("OCR区域识别任务执行完成")


# 旧的DPI处理函数已移除，现在使用统一DPI处理器


def _extract_region(image: np.ndarray, x: int, y: int, width: int, height: int) -> Optional[np.ndarray]:
    """从图片中提取指定区域（改进版，包含详细的边界检查）"""
    try:
        img_h, img_w = image.shape[:2]

        # 记录原始请求
        original_x, original_y = x, y
        original_width, original_height = width, height

        logger.info(f"搜索 [区域提取] 原始请求: ({original_x}, {original_y}, {original_width}, {original_height})")
        logger.info(f"搜索 [区域提取] 图像尺寸: {img_w} x {img_h}")

        # 工具 Bug修复：改进边界检查和调整逻辑
        # 确保起始坐标在图像范围内
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))

        # 确保区域不超出图像边界
        max_width = img_w - x
        max_height = img_h - y
        width = min(max(1, width), max_width)  # 确保宽度至少为1
        height = min(max(1, height), max_height)  # 确保高度至少为1

        # 检查是否发生了调整
        if (x != original_x or y != original_y or
            width != original_width or height != original_height):
            logger.warning(f"警告 [区域提取] 坐标已调整:")
            logger.warning(f"   原始: ({original_x}, {original_y}, {original_width}, {original_height})")
            logger.warning(f"   调整后: ({x}, {y}, {width}, {height})")
            logger.warning(f"   调整原因: 超出图像边界")

        if width <= 0 or height <= 0:
            logger.error(f"错误 [区域提取] 无效的区域尺寸: {width}x{height}")
            logger.error(f"   这通常表示坐标完全超出了图像范围")
            return None

        # 提取区域
        roi = image[y:y+height, x:x+width]
        logger.info(f"成功 [区域提取] 成功提取区域: ({x}, {y}, {width}, {height})")

        # 验证提取的区域
        if roi.size == 0:
            logger.error(f"错误 [区域提取] 提取的区域为空")
            return None

        return roi

    except Exception as e:
        logger.error(f"错误 [区域提取] 提取区域失败: {e}", exc_info=True)
        return None

# 已移除不再使用的OCR函数，现在直接使用统一OCR服务





def _check_target_text(results: List[dict], target_text: str, match_mode: str) -> bool:
    """检查是否找到目标文字"""
    if not results:
        return False

    # 如果没有指定目标文字，只要识别到任何文字就算成功
    if not target_text:
        return len(results) > 0

    # 合并所有识别到的文字
    all_text = " ".join([r['text'] for r in results])

    logger.debug(f"搜索 [文字匹配] 目标: '{target_text}', 识别: '{all_text}', 模式: {match_mode}")

    try:
        if match_mode == "包含":
            result = target_text in all_text
            if result:
                logger.info(f"成功 [文字匹配] 包含匹配成功: '{target_text}' 在 '{all_text}' 中")
            return result
        elif match_mode == "完全匹配":
            result = target_text == all_text.strip()
            if result:
                logger.info(f"成功 [文字匹配] 完全匹配成功")
            return result
        else:
            # 默认使用包含模式
            result = target_text in all_text
            if result:
                logger.info(f"成功 [文字匹配] 默认包含匹配成功")
            return result
    except Exception as e:
        logger.warning(f"文字匹配失败: {e}")
        return False

def _check_target_text_with_position(results: List[dict], target_text: str, match_mode: str) -> Tuple[bool, Optional[dict]]:
    """检查OCR结果中是否包含目标文字，并返回位置信息"""
    if not results:
        return False, None

    # 如果没有指定目标文字，只要识别到任何文字就算成功
    if not target_text:
        return len(results) > 0, results[0] if results else None

    logger.debug(f"搜索 [文字匹配] 目标: '{target_text}', 模式: {match_mode}")

    try:
        for result in results:
            text = result.get('text', '')
            if match_mode == "包含":
                if target_text in text:
                    logger.info(f"成功 [文字匹配] 包含匹配成功: '{target_text}' 在 '{text}' 中")
                    return True, result
            elif match_mode == "完全匹配":
                if target_text == text.strip():
                    logger.info(f"成功 [文字匹配] 完全匹配成功")
                    return True, result
            else:
                # 默认使用包含模式
                if target_text in text:
                    logger.info(f"成功 [文字匹配] 默认包含匹配成功")
                    return True, result

        return False, None
    except Exception as e:
        logger.warning(f"文字匹配失败: {e}")
        return False, None
def _handle_success(action: str, jump_id: Optional[int], card_id: Optional[int], stop_checker=None) -> Tuple[bool, str, Optional[int]]:
    """处理成功情况"""
    if action == '跳转到步骤':
        return True, '跳转到步骤', jump_id
    elif action == '停止工作流':
        return True, '停止工作流', None
    elif action == '继续执行本步骤':
        # 在继续执行前检查停止信号
        if stop_checker and stop_checker():
            logger.info("用户按下停止按钮，终止继续执行")
            return False, '停止工作流', None
        return True, '继续执行本步骤', card_id
    else:
        return True, '执行下一步', None

def _handle_failure(action: str, jump_id: Optional[int], card_id: Optional[int], stop_checker=None) -> Tuple[bool, str, Optional[int]]:
    """处理失败情况"""
    if action == '跳转到步骤':
        return False, '跳转到步骤', jump_id
    elif action == '停止工作流':
        return False, '停止工作流', None
    elif action == '继续执行本步骤':
        # 在继续执行前检查停止信号
        if stop_checker and stop_checker():
            logger.info("用户按下停止按钮，终止继续执行")
            return False, '停止工作流', None
        return False, '继续执行本步骤', card_id
    else:
        return False, '执行下一步', None


def _handle_multi_text_recognition(ocr_results, text_groups, match_mode, card_id,
                                 final_x, final_y, on_success_action, success_jump_id,
                                 on_failure_action, failure_jump_id, reset_clicked_texts_on_next_run=False,
                                 stop_checker=None):
    """处理多组文字识别逻辑"""
    try:
        from task_workflow.workflow_context import get_workflow_context, set_ocr_results
        context = get_workflow_context()

        # 获取当前识别状态
        text_groups_state, current_index, clicked_texts = context.get_multi_text_recognition_state(card_id)

        # 检查是否需要重置已识别文字记录
        if reset_clicked_texts_on_next_run:
            logger.info("启用了'下次执行重置已识别文字记录'，清除已点击文字记忆")
            context.set_multi_text_recognition_state(card_id, text_groups, 0, [])
            # 重新获取重置后的状态
            text_groups_state, current_index, clicked_texts = context.get_multi_text_recognition_state(card_id)
        elif not text_groups_state:
            # 如果是第一次执行，初始化状态
            context.set_multi_text_recognition_state(card_id, text_groups, 0, [])
            logger.info(f"初始化多组文字识别: 共{len(text_groups)}组文字")
            # 重新获取初始化后的状态
            text_groups_state, current_index, clicked_texts = context.get_multi_text_recognition_state(card_id)
        else:
            # 继续使用现有状态，但需要更新文字组（防止文字组配置变化）
            context.set_card_data(card_id, 'multi_text_groups', text_groups)
            logger.info(f"更新文字组配置，保持当前进度")

        logger.info(f"当前多组文字识别状态: 第{current_index + 1}/{len(text_groups)}组，已点击{len(clicked_texts)}个文字")

        # 检查是否已完成所有组
        if current_index >= len(text_groups):
            logger.info("所有文字组识别完成，清空所有数据")
            context.clear_card_ocr_data(card_id)
            return _handle_success(on_success_action, success_jump_id, card_id, stop_checker)

        # 获取当前要识别的文字
        current_target_text = text_groups[current_index]
        logger.info(f"[卡片{card_id}][多组文字] 第{current_index + 1}/{len(text_groups)}组 查找文字: '{current_target_text}'")

        # 过滤掉已点击的文字
        filtered_results = []
        for result in ocr_results:
            result_text = result.get('text', '')
            if result_text not in clicked_texts:
                filtered_results.append(result)
            else:
                logger.debug(f"过滤已点击文字: '{result_text}'")

        logger.info(f"过滤后剩余{len(filtered_results)}个文字 (原{len(ocr_results)}个)")

        # 在过滤后的结果中查找目标文字
        found_target, target_result = _check_target_text_with_position(filtered_results, current_target_text, match_mode)

        if found_target:
            logger.info(f"[卡片{card_id}][多组文字] 成功找到第{current_index + 1}组文字: '{current_target_text}'")

            # 保存OCR结果到上下文
            set_ocr_results(card_id, filtered_results)
            context.set_card_data(card_id, 'ocr_target_text', current_target_text)
            context.set_card_data(card_id, 'ocr_match_mode', match_mode)
            context.set_card_data(card_id, 'ocr_region_offset', (final_x, final_y))

            logger.info(f"多组OCR结果已保存: 卡片ID={card_id}, 当前组={current_index + 1}, 结果数={len(filtered_results)}")

            # 如果跳转到文字点击卡片，记录关联关系
            if on_success_action == '跳转到步骤' and success_jump_id:
                try:
                    context.set_card_data(success_jump_id, 'associated_ocr_card_id', card_id)
                    logger.info(f"🔗 [调试] 记录多组文字关联关系: 文字点击卡片{success_jump_id} ← OCR卡片{card_id}")
                except Exception as e:
                    logger.warning(f"记录多组文字OCR关联关系失败: {e}")

            return _handle_success(on_success_action, success_jump_id, card_id, stop_checker)
        else:
            logger.warning(f"未找到第{current_index + 1}组文字: '{current_target_text}'")

            # 工具 修复：多组文字识别失败时，尝试识别下一组文字
            next_index = current_index + 1
            if next_index < len(text_groups):
                logger.info(f"[卡片{card_id}][多组文字] 第{current_index + 1}组识别失败，尝试识别下一组 (第{next_index + 1}组)")
                # 更新到下一组
                context.set_multi_text_recognition_state(card_id, text_groups, next_index, clicked_texts)

                # 递归调用自己来处理下一组
                return _handle_multi_text_recognition(
                    ocr_results, text_groups, match_mode, card_id,
                    final_x, final_y, on_success_action, success_jump_id,
                    on_failure_action, failure_jump_id, reset_clicked_texts_on_next_run,
                    stop_checker
                )
            else:
                logger.warning(f"[卡片{card_id}][多组文字] 所有文字组都识别失败，重置状态")
                # 所有组都失败了，重置状态
                context.set_multi_text_recognition_state(card_id, text_groups, 0, [])

            # 多组文字识别失败时不清除记忆，只清除上下文（保持当前组状态）
            try:
                context.clear_card_ocr_context(card_id)
                logger.info(f"[卡片{card_id}][多组文字] 第{current_index + 1}组识别失败，已清除上下文数据，保留记忆")
            except Exception as e:
                logger.warning(f"清除OCR上下文数据失败: {e}")

            return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

    except Exception as e:
        logger.error(f"多组文字识别处理失败: {e}", exc_info=True)

        # 异常时清除上下文数据
        try:
            context.clear_card_ocr_context(card_id)
            logger.info(f"[卡片{card_id}][多组文字] 异常处理，已清除上下文数据")
        except:
            pass

        return _handle_failure(on_failure_action, failure_jump_id, card_id, stop_checker)

def get_params_definition() -> Dict[str, Dict[str, Any]]:
    """获取参数定义"""
    return {
        "---region_settings---": {"type": "separator", "label": "识别区域设置"},
        "region_mode": {
            "label": "区域模式",
            "type": "select",
            "options": ["指定区域", "整个窗口"],
            "default": "指定区域",
            "tooltip": "选择如何确定OCR识别区域"
        },

        "---coordinate_mode---": {
            "type": "separator",
            "label": "指定区域模式",
            "condition": {"param": "region_mode", "value": "指定区域"}
        },
        "ocr_region_selector_tool": {
            "label": "框选识别区域",
            "type": "button",
            "button_text": "框选识别指定区域",
            "tooltip": "点击后在绑定窗口中框选OCR识别区域，自动设置识别区域坐标",
            "condition": {"param": "region_mode", "value": "指定区域"},
            "widget_hint": "ocr_region_selector"
        },

        "region_coordinates": {
            "label": "指定的区域",
            "type": "text",
            "default": "未指定识别区域",
            "readonly": True,
            "tooltip": "显示当前选择的识别区域坐标和尺寸（由框选工具自动设置）",
            "condition": {"param": "region_mode", "value": "指定区域"}
        },
        # 隐藏的坐标参数，用于内部逻辑（只在指定区域模式下存在）
        "region_x": {
            "type": "hidden",
            "default": 0,
            "condition": {"param": "region_mode", "value": "指定区域"}
        },
        "region_y": {
            "type": "hidden",
            "default": 0,
            "condition": {"param": "region_mode", "value": "指定区域"}
        },
        "region_width": {
            "type": "hidden",
            "default": 0,
            "condition": {"param": "region_mode", "value": "指定区域"}
        },
        "region_height": {
            "type": "hidden",
            "default": 0,
            "condition": {"param": "region_mode", "value": "指定区域"}
        },

        "---target_text---": {"type": "separator", "label": "目标文字设置"},
        "text_recognition_mode": {
            "label": "识别模式",
            "type": "select",
            "options": ["单组文字", "多组文字"],
            "default": "单组文字",
            "tooltip": "选择单组文字识别还是多组文字循环识别"
        },
        "target_text": {
            "label": "需要识别的文字",
            "type": "str",
            "default": "",
            "tooltip": "指定要查找的目标文字，留空则识别所有文字",
            "condition": {"param": "text_recognition_mode", "value": "单组文字"}
        },
        "target_text_groups": {
            "label": "多组文字列表",
            "type": "str",
            "default": "",
            "tooltip": "用逗号分隔多组文字，支持中文逗号（，）和英文逗号（,），按顺序循环识别。例如：登录,确认,提交,完成 或 Login，Confirm，Submit，Done",
            "condition": {"param": "text_recognition_mode", "value": "多组文字"}
        },
        "reset_clicked_texts_on_next_run": {
            "label": "下次执行重置已识别文字记录",
            "type": "bool",
            "default": False,
            "tooltip": "启用后，每次执行OCR多组文字识别时会清除已点击文字的记忆；不启用则保持记忆直到所有文字执行完成",
            "condition": {"param": "text_recognition_mode", "value": "多组文字"}
        },
        "match_mode": {
            "label": "匹配模式",
            "type": "select",
            "options": ["包含", "完全匹配"],
            "default": "包含",
            "tooltip": "文字匹配的方式"
        },


        "---ocr_settings---": {"type": "separator", "label": "OCR设置"},
        "confidence_threshold": {
            "label": "置信度阈值",
            "type": "float",
            "default": 0.6,
            "min": 0.1,
            "max": 1.0,
            "step": 0.1,
            "tooltip": "OCR识别的最低置信度，降低可识别更多文字但可能增加误识别"
        },
        "max_retry_count": {
            "label": "最大重试次数",
            "type": "int",
            "default": 3,
            "min": 1,
            "max": 10,
            "tooltip": "OCR识别失败时的最大重试次数"
        },
        "retry_delay": {
            "label": "重试间隔(秒)",
            "type": "float",
            "default": 0.2,
            "min": 0.1,
            "max": 5.0,
            "step": 0.1,
            "tooltip": "每次重试之间的等待时间（已优化为0.2秒）"
        },



        "---post_execute---": {"type": "separator", "label": "执行后操作"},
        "on_success": {
            "type": "select",
            "label": "找到文字时",
            "options": ["执行下一步", "跳转到步骤", "停止工作流", "继续执行本步骤"],
            "default": "执行下一步",
            "tooltip": "成功识别到目标文字时的操作"
        },
        "success_jump_target_id": {
            "type": "int",
            "label": "成功跳转目标 ID",
            "required": False,
            "widget_hint": "card_selector",
            "condition": {"param": "on_success", "value": "跳转到步骤"}
        },
        "on_failure": {
            "type": "select",
            "label": "未找到文字时",
            "options": ["执行下一步", "跳转到步骤", "停止工作流", "继续执行本步骤"],
            "default": "执行下一步",
            "tooltip": "未识别到目标文字时的操作"
        },
        "failure_jump_target_id": {
            "type": "int",
            "label": "失败跳转目标 ID",
            "required": False,
            "widget_hint": "card_selector",
            "condition": {"param": "on_failure", "value": "跳转到步骤"}
        }
    }



if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    # 测试OCR引擎初始化
    engine = _get_ocr_engine()
    if engine:
        print(f"OCR引擎初始化成功: {engine['engine']}")
    else:
        print("OCR引擎初始化失败")
    
    # 测试参数定义
    params_def = get_params_definition()
    print(f"参数定义包含 {len(params_def)} 个参数")


