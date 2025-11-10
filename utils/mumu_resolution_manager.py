#!/usr/bin/env python3
"""
MuMu模拟器分辨率管理器 - 使用官方setting命令
官方文档: https://mumu.163.com/help/20240807/40912_1170006.html

使用官方setting命令设置分辨率：
MuMuManager.exe setting -v [vm_index] -k [key] -val [value]
"""

import subprocess
import logging
from typing import Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _run_hidden_command(cmd, timeout=30):
    """运行隐藏的MuMu命令，不显示弹窗"""
    try:
        # 创建STARTUPINFO对象来完全隐藏窗口
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        # 组合多个标志来确保窗口完全隐藏
        creation_flags = (
            subprocess.CREATE_NO_WINDOW |           # 不创建控制台窗口
            subprocess.DETACHED_PROCESS |           # 分离进程，不继承父进程的控制台
            subprocess.CREATE_NEW_PROCESS_GROUP     # 创建新的进程组
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            creationflags=creation_flags,
            startupinfo=startupinfo
        )

        return result

    except Exception as e:
        logger.error(f"执行隐藏命令失败: {e}")
        # 创建一个失败的结果对象
        class FailedResult:
            def __init__(self):
                self.returncode = 1
                self.stdout = ""
                self.stderr = str(e)
        return FailedResult()

@dataclass
class ResolutionResult:
    """分辨率调整结果"""
    success: bool
    message: str
    vm_index: int
    target_resolution: Tuple[int, int]
    before_size: Tuple[int, int] = (0, 0)
    after_size: Tuple[int, int] = (0, 0)

class MuMuResolutionManager:
    """MuMu模拟器分辨率管理器 - 官方setting命令版本"""
    
    def __init__(self, mumu_manager):
        self.mumu_manager = mumu_manager
        logger.debug("MuMu分辨率管理器初始化 - 使用官方setting命令")
    
    def adjust_resolution(self, vm_index: int, target_width: int, target_height: int) -> ResolutionResult:
        """
        调整MuMu模拟器分辨率 - 使用官方setting命令

        注意：固定设置分辨率为1280x720，DPI为180

        流程：
        1. 检查当前分辨率是否已符合目标分辨率
        2. 如果不符合，使用setting命令设置分辨率配置
        3. 重启模拟器使配置生效
        4. 设置DPI为180
        """
        # 强制使用固定分辨率1280x720
        target_width = 1280
        target_height = 720
        logger.info(f"调整VM {vm_index} 分辨率到固定值 {target_width}x{target_height}，DPI设置为180")

        # 验证VM索引是否有效
        vm_info = self.mumu_manager.get_vm_info(vm_index)
        if not vm_info:
            logger.warning(f"VM {vm_index} 不存在，尝试使用VM 0")
            vm_index = 0
            vm_info = self.mumu_manager.get_vm_info(0)
            if not vm_info:
                return ResolutionResult(
                    success=False,
                    message=f"VM {vm_index} 和 VM 0 都不存在",
                    vm_index=vm_index,
                    target_resolution=(target_width, target_height),
                    before_size=(0, 0)
                )

        logger.debug(f"找到VM {vm_index}: {vm_info.get('name', 'Unknown')}")

        # 直接使用官方setting命令（内置分辨率检查）
        return self.adjust_resolution_by_setting_command(vm_index, target_width, target_height)
    
    def adjust_resolution_by_setting_command(self, vm_index: int, target_width: int, target_height: int) -> ResolutionResult:
        """
        使用MuMu官方setting命令调整分辨率

        根据官方文档，使用setting命令设置分辨率相关配置
        """
        logger.debug(f"使用官方setting命令调整VM {vm_index} 分辨率到 {target_width}x{target_height}")

        try:
            # 获取调整前的大小
            before_size = self._get_current_size(vm_index)

            # 验证MuMu管理器可用性
            if not self.mumu_manager.is_available():
                return ResolutionResult(
                    success=False,
                    message="MuMu管理器不可用",
                    vm_index=vm_index,
                    target_resolution=(target_width, target_height),
                    before_size=before_size
                )

            manager_path = self.mumu_manager.mumu_manager_path
            if not manager_path:
                return ResolutionResult(
                    success=False,
                    message="MuMu管理器路径不可用",
                    vm_index=vm_index,
                    target_resolution=(target_width, target_height),
                    before_size=before_size
                )

            # 检查当前分辨率是否已经符合要求
            logger.debug(f"开始检查VM {vm_index} 当前分辨率配置...")
            current_resolution = self._get_current_resolution(vm_index, manager_path)

            if current_resolution:
                current_width, current_height = current_resolution
                logger.info(f"VM {vm_index} 配置分辨率: {current_width}x{current_height}, 目标分辨率: {target_width}x{target_height}")

                # 检查实际客户区分辨率
                actual_size = self._get_current_size(vm_index)
                actual_width, actual_height = actual_size
                logger.info(f"VM {vm_index} 实际客户区大小: {actual_width}x{actual_height}")

                # 只检查实际客户区大小是否符合目标分辨率
                client_matches = (actual_width == target_width and actual_height == target_height)

                if client_matches:
                    logger.info(f"✅ VM {vm_index} 客户区分辨率已符合目标，跳过调整和重启")
                    return ResolutionResult(
                        success=True,
                        message=f"客户区分辨率已符合要求 ({actual_width}x{actual_height})，无需调整",
                        vm_index=vm_index,
                        target_resolution=(target_width, target_height),
                        before_size=before_size,
                        after_size=(actual_width, actual_height)
                    )
                else:
                    logger.info(f"❌ VM {vm_index} 客户区分辨率 {actual_width}x{actual_height} 与目标分辨率 {target_width}x{target_height} 不符，需要调整")
            else:
                logger.warning(f"⚠️ 无法获取VM {vm_index} 的当前分辨率配置，将继续执行调整")

            # 使用官方setting命令设置分辨率
            # 根据官方文档，使用正确的可写配置键
            # 修改：固定设置DPI为180，分辨率为1280x720
            setting_commands = [
                # 设置分辨率模式为自定义 (custom.1表示自定义模式)
                [manager_path, "setting", "-v", str(vm_index), "-k", "resolution_mode", "-val", "custom.1"],
                # 设置自定义宽度
                [manager_path, "setting", "-v", str(vm_index), "-k", "resolution_width.custom", "-val", str(float(target_width))],
                # 设置自定义高度
                [manager_path, "setting", "-v", str(vm_index), "-k", "resolution_height.custom", "-val", str(float(target_height))],
            ]
            
            # 执行所有setting命令
            all_success = True
            for i, cmd in enumerate(setting_commands):
                logger.debug(f"执行setting命令 {i+1}/{len(setting_commands)}: {' '.join(cmd)}")
                result = _run_hidden_command(cmd, timeout=30)

                if result.returncode != 0:
                    logger.warning(f"setting命令 {i+1} 执行失败: {result.stderr}")
                    all_success = False

            if all_success:
                logger.debug("所有setting命令执行成功")
            else:
                logger.warning("部分setting命令执行失败，但可能仍然有效")
            
            # 重启模拟器使配置生效
            logger.info("重启模拟器使配置生效")
            try:
                restart_cmd = [manager_path, "control", "-v", str(vm_index), "restart"]
                result = _run_hidden_command(restart_cmd, timeout=60)

                if result.returncode == 0:
                    logger.info(f"VM {vm_index} 重启成功，等待15秒")
                    import time
                    time.sleep(15)

                    # 重启后设置DPI为180
                    logger.info(f"设置VM {vm_index} DPI为180")
                    try:
                        # 使用简单的ADB命令设置DPI
                        dpi_cmd = [manager_path, "control", "-v", str(vm_index), "tool", "cmd", "-c", "wm density 180"]
                        dpi_result = _run_hidden_command(dpi_cmd, timeout=30)

                        if dpi_result.returncode == 0:
                            logger.info(f"VM {vm_index} DPI设置成功")
                        else:
                            logger.warning(f"VM {vm_index} DPI设置失败: {dpi_result.stderr}")
                            # DPI设置失败不影响整体流程，继续执行
                    except Exception as e:
                        logger.warning(f"设置DPI异常: {e}")
                        # DPI设置异常不影响整体流程，继续执行

                else:
                    logger.error(f"VM {vm_index} 重启失败: {result.stderr}")
                    return ResolutionResult(
                        success=False,
                        message="重启模拟器失败",
                        vm_index=vm_index,
                        target_resolution=(target_width, target_height),
                        before_size=before_size
                    )
            except Exception as e:
                logger.error(f"重启模拟器异常: {e}")
                return ResolutionResult(
                    success=False,
                    message=f"重启异常: {e}",
                    vm_index=vm_index,
                    target_resolution=(target_width, target_height),
                    before_size=before_size
                )
            
            # 获取调整后的大小
            after_size = self._get_current_size(vm_index)

            # 最后统一设置DPI（确保一致性）
            logger.info(f"最终统一设置VM {vm_index} DPI为180")
            try:
                final_dpi_cmd = [manager_path, "control", "-v", str(vm_index), "tool", "cmd", "-c", "wm density 180"]
                final_dpi_result = _run_hidden_command(final_dpi_cmd, timeout=30)
                if final_dpi_result.returncode == 0:
                    logger.info(f"VM {vm_index} 最终DPI设置成功")
                else:
                    logger.warning(f"VM {vm_index} 最终DPI设置失败: {final_dpi_result.stderr}")
            except Exception as e:
                logger.warning(f"VM {vm_index} 最终DPI设置异常: {e}")

            return ResolutionResult(
                success=True,
                message=f"分辨率调整完成",
                vm_index=vm_index,
                target_resolution=(target_width, target_height),
                before_size=before_size,
                after_size=after_size
            )

        except Exception as e:
            logger.error(f"分辨率调整异常: {e}")
            return ResolutionResult(
                success=False,
                message=f"调整异常: {e}",
                vm_index=vm_index,
                target_resolution=(target_width, target_height),
                before_size=(0, 0),
                after_size=(0, 0)
            )

    def _get_current_resolution(self, vm_index: int, manager_path: str) -> Tuple[int, int]:
        """获取当前MuMu模拟器的分辨率配置"""
        try:
            # 查询当前分辨率模式
            mode_cmd = [manager_path, "setting", "-v", str(vm_index), "-k", "resolution_mode"]
            mode_result = _run_hidden_command(mode_cmd, timeout=10)

            if mode_result.returncode != 0:
                logger.debug(f"查询分辨率模式失败: {mode_result.stderr}")
                return None

            import json
            mode_data = json.loads(mode_result.stdout)
            current_mode = mode_data.get("resolution_mode", "")

            # 如果是自定义模式，查询自定义分辨率
            # 支持多种自定义模式格式：custom, custom.1, custom.2 等
            if current_mode.startswith("custom"):
                logger.debug(f"检测到自定义分辨率模式: {current_mode}")

                width_cmd = [manager_path, "setting", "-v", str(vm_index), "-k", "resolution_width.custom"]
                height_cmd = [manager_path, "setting", "-v", str(vm_index), "-k", "resolution_height.custom"]

                width_result = _run_hidden_command(width_cmd, timeout=10)
                height_result = _run_hidden_command(height_cmd, timeout=10)

                if width_result.returncode == 0 and height_result.returncode == 0:
                    width_data = json.loads(width_result.stdout)
                    height_data = json.loads(height_result.stdout)

                    width = int(float(width_data.get("resolution_width.custom", 0)))
                    height = int(float(height_data.get("resolution_height.custom", 0)))

                    logger.debug(f"VM {vm_index} 当前自定义分辨率: {width}x{height}")
                    return (width, height)
                else:
                    logger.debug(f"查询自定义分辨率失败: width_result={width_result.returncode}, height_result={height_result.returncode}")
                    if width_result.stderr:
                        logger.debug(f"Width查询错误: {width_result.stderr}")
                    if height_result.stderr:
                        logger.debug(f"Height查询错误: {height_result.stderr}")

            # 如果是预设模式，解析预设分辨率
            elif current_mode:
                preset_resolution = self._get_preset_resolution(current_mode)
                if preset_resolution:
                    logger.debug(f"VM {vm_index} 当前预设分辨率: {preset_resolution[0]}x{preset_resolution[1]} (模式: {current_mode})")
                    return preset_resolution

            logger.debug(f"无法获取VM {vm_index} 的当前分辨率，模式: {current_mode}")
            return None

        except Exception as e:
            logger.debug(f"获取当前分辨率失败: {e}")
            return None

    def _get_preset_resolution(self, mode: str) -> Tuple[int, int]:
        """根据预设模式获取分辨率"""
        preset_resolutions = {
            "tablet.1": (1024, 768),
            "tablet.2": (1280, 720),
            "tablet.3": (1366, 768),
            "tablet.4": (1920, 1080),
            "phone.1": (720, 1280),
            "phone.2": (1080, 1920),
            "phone.3": (1080, 2340),
        }
        return preset_resolutions.get(mode)

    def _get_current_size(self, vm_index: int) -> Tuple[int, int]:
        """获取MuMu模拟器真正的游戏渲染区域大小"""
        try:
            # 通过窗口句柄获取MuMu主窗口
            from utils.window_handle_manager import get_window_handle_manager
            window_manager = get_window_handle_manager()

            main_hwnd = window_manager.get_window_handle_by_vm_index(vm_index)
            if not main_hwnd:
                logger.debug(f"VM {vm_index} 无法获取主窗口句柄")
                return (0, 0)

            import win32gui

            # 查找MuMu的渲染子窗口（真正的游戏显示区域）
            render_hwnd = self._find_mumu_render_window(main_hwnd)

            if render_hwnd:
                # 获取渲染窗口的客户区大小（这才是真正的游戏分辨率）
                client_rect = win32gui.GetClientRect(render_hwnd)
                client_width = client_rect[2] - client_rect[0]
                client_height = client_rect[3] - client_rect[1]

                logger.debug(f"VM {vm_index} 渲染区域大小: {client_width}x{client_height}")
                return (client_width, client_height)
            else:
                # 如果找不到渲染窗口，回退到主窗口客户区
                client_rect = win32gui.GetClientRect(main_hwnd)
                client_width = client_rect[2] - client_rect[0]
                client_height = client_rect[3] - client_rect[1]

                logger.debug(f"VM {vm_index} 主窗口客户区大小: {client_width}x{client_height}")
                return (client_width, client_height)

        except Exception as e:
            logger.debug(f"获取渲染区域大小失败: {e}")
            return (0, 0)

    def _find_mumu_render_window(self, parent_hwnd: int) -> int:
        """查找MuMu模拟器的渲染子窗口"""
        try:
            import win32gui

            all_children = []
            render_windows = []

            def enum_child_callback(hwnd, param):
                try:
                    class_name = win32gui.GetClassName(hwnd)
                    title = win32gui.GetWindowText(hwnd)
                    is_visible = win32gui.IsWindowVisible(hwnd)
                    rect = win32gui.GetClientRect(hwnd)
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]

                    all_children.append((hwnd, class_name, title, width, height, is_visible))

                    # 查找可能的渲染窗口
                    # MuMu的渲染窗口可能有这些特征
                    if is_visible and width > 100 and height > 100:
                        # 常见的渲染窗口类名
                        if (class_name in ['RenderWindow', 'Qt5QWindowIcon', 'QWidget', 'OpenGLWindow', 'Qt5QWindowToolSaveBits'] or
                            'render' in class_name.lower() or
                            'opengl' in class_name.lower() or
                            # 或者是接近目标分辨率的窗口
                            (abs(width - 1280) <= 10 and abs(height - 720) <= 10)):
                            render_windows.append((hwnd, width, height, class_name))

                except:
                    pass
                return True

            win32gui.EnumChildWindows(parent_hwnd, enum_child_callback, 0)

            # 打印所有子窗口信息用于调试
            logger.debug(f"MuMu主窗口的所有子窗口:")
            for hwnd, class_name, title, width, height, is_visible in all_children:
                logger.debug(f"  子窗口: {class_name} '{title}' {width}x{height} visible={is_visible}")

            if render_windows:
                logger.debug(f"找到 {len(render_windows)} 个渲染候选窗口:")
                for hwnd, width, height, class_name in render_windows:
                    logger.debug(f"  候选: {class_name} {width}x{height}")

                # 优先选择尺寸最接近目标分辨率的窗口
                def score_window(window):
                    hwnd, width, height, class_name = window
                    # 计算与目标分辨率的差异
                    width_diff = abs(width - 1280)
                    height_diff = abs(height - 720)
                    size_score = width_diff + height_diff

                    # 类名匹配度加分
                    class_score = 0
                    if 'render' in class_name.lower():
                        class_score = -100
                    elif 'opengl' in class_name.lower():
                        class_score = -50

                    return size_score + class_score

                render_windows.sort(key=score_window)
                best_window = render_windows[0]
                logger.debug(f"选择最佳渲染窗口: {best_window[3]} {best_window[1]}x{best_window[2]}")
                return best_window[0]
            else:
                logger.debug("未找到合适的渲染子窗口")

            return None

        except Exception as e:
            logger.debug(f"查找渲染窗口失败: {e}")
            return None

    def _set_vm_dpi_simple(self, vm_index: int, manager_path: str, target_dpi: int = 180) -> bool:
        """简单设置VM DPI"""
        try:
            logger.info(f"VM {vm_index} 使用ADB命令设置DPI为 {target_dpi}")

            # 直接使用ADB命令设置DPI
            dpi_cmd = [manager_path, "control", "-v", str(vm_index), "tool", "cmd", "-c", f"wm density {target_dpi}"]
            dpi_result = _run_hidden_command(dpi_cmd, timeout=30)

            if dpi_result.returncode == 0:
                logger.info(f"VM {vm_index} DPI设置成功")
                return True
            else:
                logger.warning(f"VM {vm_index} DPI设置失败: {dpi_result.stderr}")
                return False

        except Exception as e:
            logger.warning(f"VM {vm_index} DPI设置异常: {e}")
            return False

    def _get_current_dpi(self, vm_index: int, manager_path: str) -> int:
        """获取VM当前DPI"""
        try:
            # 方法1: 使用getprop命令查询DPI
            getprop_cmd = [manager_path, "control", "-v", str(vm_index), "tool", "cmd", "-c", "getprop ro.sf.lcd_density"]
            result = _run_hidden_command(getprop_cmd, timeout=15)

            if result.returncode == 0:
                output = result.stdout.strip()
                try:
                    dpi_value = int(output)
                    if dpi_value > 0:
                        logger.debug(f"VM {vm_index} getprop查询DPI: {dpi_value}")
                        return dpi_value
                except ValueError:
                    logger.debug(f"getprop DPI解析失败: {output}")

            # 方法2: 使用wm density命令查询
            dpi_query_cmd = [manager_path, "control", "-v", str(vm_index), "tool", "cmd", "-c", "wm density"]
            result = _run_hidden_command(dpi_query_cmd, timeout=15)

            if result.returncode == 0:
                output = result.stdout.strip()
                # 解析输出，通常格式为 "Physical density: 180"
                if "density:" in output:
                    dpi_str = output.split("density:")[-1].strip()
                    try:
                        dpi_value = int(dpi_str)
                        logger.debug(f"VM {vm_index} wm density查询DPI: {dpi_value}")
                        return dpi_value
                    except ValueError:
                        logger.debug(f"wm density DPI解析失败: {dpi_str}")

            logger.debug(f"VM {vm_index} DPI查询失败: {result.stderr}")
            return 0  # 返回0表示查询失败

        except Exception as e:
            logger.debug(f"VM {vm_index} DPI查询异常: {e}")
            return 0

# 全局实例
_mumu_resolution_manager = None

def get_mumu_resolution_manager():
    """获取MuMu分辨率管理器实例"""
    global _mumu_resolution_manager
    if _mumu_resolution_manager is None:
        from utils.mumu_manager import get_mumu_manager
        mumu_manager = get_mumu_manager()
        _mumu_resolution_manager = MuMuResolutionManager(mumu_manager)
    return _mumu_resolution_manager
