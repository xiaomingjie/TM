#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MuMu模拟器管理器
基于MuMuManager.exe命令行工具实现MuMu模拟器的各种操作

🔧 调试增强 (2025-10-11):
- 增强了 _run_command() 的日志输出，记录返回码、stdout/stderr长度和内容
- 增强了 get_simulator_info() 的日志输出，记录原始输出和JSON解析结果
- 增强了 __init__() 的日志输出，明确显示MuMuManager.exe是否找到
- 这些日志将帮助诊断为什么 get_all_vm_info() 返回空字典的问题
"""

import os
import subprocess
import json
import logging
import win32gui
import win32process
import psutil
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class MuMuManager:
    """MuMu模拟器管理器"""
    
    def __init__(self):
        self.mumu_manager_path = None
        self._find_mumu_manager()

        # 🔧 增强诊断：初始化后记录状态
        if self.mumu_manager_path:
            logger.info(f"✓ MuMuManager初始化成功: {self.mumu_manager_path}")
        else:
            logger.warning("⚠ MuMuManager初始化失败：未找到MuMuManager.exe")
    
    def _find_mumu_manager(self):
        """查找MuMuManager.exe的路径"""
        # 常见的MuMu模拟器安装路径
        possible_paths = [
            r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
            r"D:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
            r"E:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
            r"C:\Program Files (x86)\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
            r"D:\Program Files (x86)\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe",
        ]
        
        # 检查常见路径
        for path in possible_paths:
            if os.path.exists(path):
                self.mumu_manager_path = path
                logger.info(f"找到MuMuManager.exe: {path}")
                return
        
        # 尝试从进程中查找
        try:
            logger.info("开始从运行中的进程查找MuMu模拟器...")
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    exe_path = proc_info.get('exe', '')

                    # 检查进程名是否包含mumu相关关键词
                    if any(keyword in proc_name for keyword in ['mumu', 'nemu', 'netease']):
                        logger.debug(f"找到可能的MuMu进程: {proc_name} -> {exe_path}")

                        if exe_path and os.path.exists(exe_path):
                            # 尝试多个可能的路径
                            possible_manager_paths = [
                                os.path.join(os.path.dirname(exe_path), 'shell', 'MuMuManager.exe'),
                                os.path.join(os.path.dirname(exe_path), 'MuMuManager.exe'),
                                os.path.join(os.path.dirname(os.path.dirname(exe_path)), 'shell', 'MuMuManager.exe'),
                                # 如果是在子目录中，尝试向上查找
                                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(exe_path))), 'shell', 'MuMuManager.exe')
                            ]

                            for manager_path in possible_manager_paths:
                                if os.path.exists(manager_path):
                                    self.mumu_manager_path = manager_path
                                    logger.info(f"从进程 {proc_name} 找到MuMuManager.exe: {manager_path}")
                                    return

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    logger.debug(f"处理进程时出错: {e}")
                    continue

        except Exception as e:
            logger.debug(f"从进程中查找MuMuManager失败: {e}")

        # 尝试通过窗口句柄查找
        try:
            logger.info("尝试通过MuMu窗口查找安装路径...")
            import win32gui
            import win32process

            def enum_windows_callback(hwnd, lParam):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title and 'mumu' in title.lower():
                            # 获取窗口对应的进程ID
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            try:
                                proc = psutil.Process(pid)
                                exe_path = proc.exe()
                                logger.debug(f"MuMu窗口 {title} 对应进程: {exe_path}")

                                if exe_path:
                                    # 尝试查找MuMuManager.exe
                                    possible_paths = [
                                        os.path.join(os.path.dirname(exe_path), 'shell', 'MuMuManager.exe'),
                                        os.path.join(os.path.dirname(exe_path), 'MuMuManager.exe'),
                                        os.path.join(os.path.dirname(os.path.dirname(exe_path)), 'shell', 'MuMuManager.exe')
                                    ]

                                    for path in possible_paths:
                                        if os.path.exists(path):
                                            lParam.append(path)
                                            return False  # 找到就停止枚举
                            except:
                                pass
                except:
                    pass
                return True

            found_paths = []
            win32gui.EnumWindows(enum_windows_callback, found_paths)

            if found_paths:
                self.mumu_manager_path = found_paths[0]
                logger.info(f"通过窗口查找到MuMuManager.exe: {self.mumu_manager_path}")
                return

        except Exception as e:
            logger.debug(f"通过窗口查找MuMuManager失败: {e}")
        
        logger.warning("未找到MuMuManager.exe，MuMu模拟器功能将不可用")
    
    def is_available(self) -> bool:
        """检查MuMuManager是否可用"""
        # 如果路径为空，尝试重新查找（延迟初始化）
        if not self.mumu_manager_path:
            logger.debug("MuMuManager路径为空，尝试重新查找...")
            self._find_mumu_manager()

        return self.mumu_manager_path is not None and os.path.exists(self.mumu_manager_path)
    
    def _run_command(self, args: List[str], timeout: int = 30) -> Tuple[bool, str, str]:
        """执行MuMuManager命令"""
        if not self.is_available():
            logger.warning("_run_command 调用时 MuMuManager 不可用")
            logger.warning(f"  mumu_manager_path: {self.mumu_manager_path}")
            return False, "", "MuMuManager不可用"

        try:
            cmd = [self.mumu_manager_path] + args
            logger.debug(f"执行MuMu命令: {' '.join(cmd)}")

            # 使用更强力的方法隐藏窗口
            import subprocess

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

            success = result.returncode == 0
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            # 🔧 增强调试：记录更多细节
            logger.debug(f"MuMu命令返回码: {result.returncode}")
            logger.debug(f"stdout 长度: {len(stdout)}, stderr 长度: {len(stderr)}")

            if success:
                logger.debug(f"MuMu命令执行成功，输出前200字符: {stdout[:200] if stdout else '(empty)'}")
            else:
                logger.warning(f"MuMu命令执行失败 (返回码 {result.returncode})")
                logger.warning(f"  stderr: {stderr}")
                logger.warning(f"  stdout: {stdout}")

            return success, stdout, stderr

        except subprocess.TimeoutExpired:
            logger.error(f"MuMu命令执行超时: {args}")
            return False, "", "命令执行超时"
        except Exception as e:
            logger.error(f"执行MuMu命令时发生异常: {e}")
            logger.error(f"  命令: {args}")
            logger.error(f"  MuMuManager路径: {self.mumu_manager_path}")
            return False, "", str(e)
    
    def get_simulator_info(self, vm_index: Optional[int] = None) -> Dict[str, Any]:
        """获取模拟器信息"""
        args = ["info"]
        if vm_index is not None:
            args.extend(["-v", str(vm_index)])
        else:
            args.extend(["-v", "all"])

        success, stdout, stderr = self._run_command(args)

        # 🔧 增强调试：记录原始输出
        logger.debug(f"get_simulator_info - success: {success}")
        logger.debug(f"get_simulator_info - stdout length: {len(stdout) if stdout else 0}")
        logger.debug(f"get_simulator_info - stdout: {stdout[:500] if stdout else '(empty)'}")
        logger.debug(f"get_simulator_info - stderr: {stderr[:500] if stderr else '(empty)'}")

        if not success:
            logger.warning(f"获取模拟器信息失败 - stderr: {stderr}")
            return {}

        try:
            # 解析JSON输出
            if stdout:
                result = json.loads(stdout)
                logger.debug(f"get_simulator_info - 解析JSON成功，类型: {type(result)}")
                return result
            else:
                logger.warning("get_simulator_info - stdout为空，无法解析")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"解析模拟器信息JSON失败: {e}")
            logger.error(f"原始输出: {stdout}")
            return {}

    def get_vm_info(self, vm_index: int) -> Optional[Dict[str, Any]]:
        """获取指定VM的信息"""
        try:
            info = self.get_simulator_info(vm_index)
            return info if info else None
        except Exception as e:
            logger.error(f"获取VM {vm_index} 信息失败: {e}")
            return None

    def get_all_vm_info(self) -> Dict[str, Any]:
        """获取所有VM的信息"""
        try:
            info = self.get_simulator_info()  # 不传参数获取所有VM信息
            logger.debug(f"get_all_vm_info 原始返回: {type(info)} - {info}")

            # 根据官方文档和实际测试，info -v all 可能返回不同格式
            # 如果返回的是单个VM信息（只有一个VM时），需要转换为字典格式
            if info and isinstance(info, dict):
                # 检查是否是单个VM信息（包含index字段）
                if 'index' in info:
                    # 单个VM信息，转换为字典格式
                    vm_index = str(info['index'])
                    result = {vm_index: info}
                    logger.debug(f"转换单个VM信息为字典格式: {result}")
                    return result
                else:
                    # 已经是多VM字典格式
                    logger.debug(f"返回多VM字典格式: {info}")
                    return info

            logger.warning(f"get_all_vm_info 返回空或无效格式: {info}")
            return {}
        except Exception as e:
            logger.error(f"获取所有VM信息失败: {e}")
            return {}

    def get_simulator_by_hwnd(self, hwnd: int) -> Optional[Dict[str, Any]]:
        """根据窗口句柄获取模拟器信息"""
        try:
            # 首先验证这是否是MuMu主设备窗口
            if self._is_mumu_main_device_window(hwnd):
                logger.debug(f"确认窗口 {hwnd} 是MuMu主设备窗口")

            # 获取所有模拟器信息
            all_info = self.get_simulator_info()
            if not all_info:
                logger.debug(f"未获取到模拟器信息")
                return None

            logger.debug(f"获取到模拟器信息类型: {type(all_info)}, 内容: {all_info}")

            # 如果返回的是列表，遍历查找匹配的窗口句柄
            if isinstance(all_info, list):
                logger.debug(f"处理列表格式的模拟器信息，共 {len(all_info)} 个")
                for simulator in all_info:
                    if self._is_hwnd_match(hwnd, simulator):
                        logger.debug(f"找到匹配的模拟器: {simulator}")
                        return simulator
            elif isinstance(all_info, dict):
                # 🔧 修复：检查是否是多VM字典格式（键为VM索引）
                if any(key.isdigit() for key in all_info.keys()):
                    # 多VM字典格式，遍历每个VM
                    logger.debug(f"处理多VM字典格式，共 {len(all_info)} 个VM")
                    for vm_index, simulator_info in all_info.items():
                        logger.debug(f"检查VM {vm_index}: {simulator_info}")
                        if self._is_hwnd_match(hwnd, simulator_info):
                            logger.debug(f"找到匹配的VM {vm_index}: {simulator_info}")
                            return simulator_info
                else:
                    # 单个模拟器信息字典
                    logger.debug(f"处理单个模拟器信息字典")
                    if self._is_hwnd_match(hwnd, all_info):
                        logger.debug(f"找到匹配的模拟器: {all_info}")
                        return all_info

            logger.debug(f"未找到匹配窗口句柄 {hwnd} 的模拟器")
            return None

        except Exception as e:
            logger.error(f"根据窗口句柄获取模拟器信息失败: {e}")
            return None

    def _is_mumu_main_device_window(self, hwnd: int) -> bool:
        """检查窗口是否为MuMu主设备窗口（标题包含"MuMu安卓设备"）"""
        try:
            import win32gui
            window_title = win32gui.GetWindowText(hwnd)
            window_class = win32gui.GetClassName(hwnd)

            # 检查是否是MuMu主设备窗口
            is_main_device = (
                "MuMu安卓设备" in window_title and
                window_class in ["Qt5156QWindowIcon", "Qt6QWindowIcon"]
            )

            if is_main_device:
                logger.debug(f"确认为MuMu主设备窗口: {window_title} (HWND: {hwnd})")
                return True
            else:
                logger.debug(f"非MuMu主设备窗口: {window_title} (HWND: {hwnd})")
                return False

        except Exception as e:
            logger.debug(f"检查MuMu主设备窗口失败: {e}")
            return False

    def _is_hwnd_match(self, target_hwnd: int, simulator_info: Dict[str, Any]) -> bool:
        """检查窗口句柄是否匹配模拟器"""
        try:
            # 检查主窗口句柄
            main_wnd = simulator_info.get('main_wnd')
            if main_wnd:
                # 转换十六进制字符串为整数
                if isinstance(main_wnd, str):
                    main_wnd_int = int(main_wnd, 16)
                    if main_wnd_int == target_hwnd:
                        return True
            
            # 检查渲染窗口句柄
            render_wnd = simulator_info.get('render_wnd')
            if render_wnd:
                if isinstance(render_wnd, str):
                    render_wnd_int = int(render_wnd, 16)
                    if render_wnd_int == target_hwnd:
                        return True
            
            # 检查进程ID匹配
            pid = simulator_info.get('pid')
            if pid:
                try:
                    _, window_pid = win32process.GetWindowThreadProcessId(target_hwnd)
                    if window_pid == pid:
                        return True
                except:
                    pass
            
            return False
            
        except Exception as e:
            logger.debug(f"检查窗口句柄匹配失败: {e}")
            return False
    
    def launch_simulator(self, vm_index: int, package_name: Optional[str] = None) -> bool:
        """启动模拟器"""
        args = ["control", "-v", str(vm_index), "launch"]
        if package_name:
            args.extend(["-pkg", package_name])
        
        success, stdout, stderr = self._run_command(args, timeout=60)
        return success
    
    def shutdown_simulator(self, vm_index: int) -> bool:
        """关闭模拟器"""
        args = ["control", "-v", str(vm_index), "shutdown"]
        success, stdout, stderr = self._run_command(args)
        return success
    
    def restart_simulator(self, vm_index: int) -> bool:
        """重启模拟器"""
        args = ["control", "-v", str(vm_index), "restart"]
        success, stdout, stderr = self._run_command(args, timeout=60)
        return success
    
    def show_window(self, vm_index: int) -> bool:
        """显示模拟器窗口"""
        args = ["control", "-v", str(vm_index), "show_window"]
        success, stdout, stderr = self._run_command(args)
        return success
    
    def hide_window(self, vm_index: int) -> bool:
        """隐藏模拟器窗口"""
        args = ["control", "-v", str(vm_index), "hide_window"]
        success, stdout, stderr = self._run_command(args)
        return success
    
    def set_window_layout(self, vm_index: int, x: Optional[int] = None, y: Optional[int] = None,
                         width: Optional[int] = None, height: Optional[int] = None) -> bool:
        """设置模拟器窗口位置和大小"""
        args = ["control", "-v", str(vm_index), "layout_window"]
        
        if x is not None:
            args.extend(["-px", str(x)])
        if y is not None:
            args.extend(["-py", str(y)])
        if width is not None:
            args.extend(["-sw", str(width)])
        if height is not None:
            args.extend(["-sh", str(height)])
        
        success, stdout, stderr = self._run_command(args)
        return success

    def install_app(self, vm_index: int, apk_path: str) -> bool:
        """安装应用到模拟器"""
        args = ["control", "-v", str(vm_index), "app", "install", "-apk", apk_path]
        success, stdout, stderr = self._run_command(args, timeout=120)
        return success

    def uninstall_app(self, vm_index: int, package_name: str) -> bool:
        """卸载模拟器中的应用"""
        args = ["control", "-v", str(vm_index), "app", "uninstall", "-pkg", package_name]
        success, stdout, stderr = self._run_command(args)
        return success

    def launch_app(self, vm_index: int, package_name: str) -> bool:
        """启动模拟器中的应用"""
        args = ["control", "-v", str(vm_index), "app", "launch", "-pkg", package_name]
        success, stdout, stderr = self._run_command(args)
        return success

    def close_app(self, vm_index: int, package_name: str) -> bool:
        """关闭模拟器中的应用"""
        args = ["control", "-v", str(vm_index), "app", "close", "-pkg", package_name]
        success, stdout, stderr = self._run_command(args)
        return success

    def get_app_info(self, vm_index: int, package_name: Optional[str] = None) -> Dict[str, Any]:
        """获取应用信息"""
        args = ["control", "-v", str(vm_index), "app", "info"]

        if package_name:
            args.extend(["-pkg", package_name])
        else:
            args.extend(["-i"])  # 获取已安装应用列表

        success, stdout, stderr = self._run_command(args)
        if not success:
            return {}

        try:
            if stdout:
                return json.loads(stdout)
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"解析应用信息JSON失败: {e}")
            return {}

    def get_installed_apps(self, vm_index: int) -> Dict[str, Any]:
        """获取已安装的应用列表"""
        return self.get_app_info(vm_index)

    def is_app_running(self, vm_index: int, package_name: str) -> bool:
        """检查应用是否正在运行"""
        app_info = self.get_app_info(vm_index, package_name)
        if app_info:
            state = app_info.get('state', 'not_installed')
            return state == 'running'
        return False

    def is_app_installed(self, vm_index: int, package_name: str) -> bool:
        """检查应用是否已安装"""
        app_info = self.get_app_info(vm_index, package_name)
        if app_info:
            state = app_info.get('state', 'not_installed')
            return state in ['running', 'stopped']
        return False

    def adb_command(self, vm_index: int, command: str) -> Tuple[bool, str]:
        """执行ADB命令"""
        args = ["adb", "-v", str(vm_index), "-c", command]
        success, stdout, stderr = self._run_command(args)
        return success, stdout if success else stderr

    def input_text(self, vm_index: int, text: str) -> bool:
        """输入文本到模拟器 - 只使用ADBKeyboard方法"""
        # 只使用ADBKeyboard的broadcast方式（已验证有效）
        success, output = self.adb_command(vm_index, f"shell am broadcast -a ADB_INPUT_TEXT --es msg '{text}'")
        return success

    def send_key(self, vm_index: int, key: str) -> bool:
        """发送按键到模拟器"""
        success, output = self.adb_command(vm_index, f"go_{key}")
        return success

    def click_coordinate(self, vm_index: int, x: int, y: int) -> bool:
        """点击指定坐标"""
        success, output = self.adb_command(vm_index, f"shell input tap {x} {y}")
        return success

    def set_vm_setting(self, vm_index: int, key: str, value: str) -> bool:
        """设置VM配置"""
        try:
            if not self.is_available():
                logger.error("MuMuManager不可用")
                return False

            args = ["setting", "-v", str(vm_index), "-k", key, "-val", value]
            success, stdout, stderr = self._run_command(args, timeout=10)

            if success:
                logger.info(f"设置VM {vm_index} 配置成功: {key} = {value}")
            else:
                logger.error(f"设置VM {vm_index} 配置失败: {key} = {value}, 错误: {stderr}")

            return success

        except Exception as e:
            logger.error(f"设置VM配置异常: {e}")
            return False

    def get_vm_setting(self, vm_index: int, key: str) -> Optional[str]:
        """获取VM配置"""
        try:
            if not self.is_available():
                logger.error("MuMuManager不可用")
                return None

            args = ["setting", "-v", str(vm_index), "-k", key]
            success, stdout, stderr = self._run_command(args, timeout=10)

            if success and stdout:
                value = stdout.strip()
                logger.debug(f"获取VM {vm_index} 配置: {key} = {value}")
                return value
            else:
                logger.warning(f"获取VM {vm_index} 配置失败: {key}, 错误: {stderr}")
                return None

        except Exception as e:
            logger.error(f"获取VM配置异常: {e}")
            return None

    def adjust_resolution(self, vm_index: int, target_width: int, target_height: int):
        """
        调整MuMu模拟器分辨率

        注意：实际会固定设置为1280x720分辨率，DPI为180

        Args:
            vm_index: 模拟器索引
            target_width: 目标宽度（会被忽略，固定使用1280）
            target_height: 目标高度（会被忽略，固定使用720）

        Returns:
            ResolutionResult: 调整结果
        """
        try:
            from utils.mumu_resolution_manager import get_mumu_resolution_manager
            resolution_manager = get_mumu_resolution_manager()
            return resolution_manager.adjust_resolution(vm_index, target_width, target_height)
        except Exception as e:
            logger.error(f"调整分辨率失败: {e}")
            from utils.mumu_resolution_manager import ResolutionResult
            return ResolutionResult(
                success=False,
                message=f"调整分辨率失败: {e}",
                vm_index=vm_index,
                target_resolution=(target_width, target_height),
                before_size=(0, 0),
                after_size=(0, 0)
            )


# 全局实例
global_mumu_manager = MuMuManager()


def get_mumu_manager() -> MuMuManager:
    """获取全局MuMu管理器实例"""
    return global_mumu_manager


if __name__ == "__main__":
    # 测试模块
    manager = MuMuManager()
    print(f"MuMuManager可用: {manager.is_available()}")
    
    if manager.is_available():
        print("获取模拟器信息:")
        info = manager.get_simulator_info()
        print(json.dumps(info, indent=2, ensure_ascii=False))
