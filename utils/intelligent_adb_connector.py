#!/usr/bin/env python3
"""
智能ADB连接器
解决多窗口ADB连接的三个关键问题：
1. 根据窗口类型选择正确的ADB路径
2. 动态获取所有可用端口，不依赖硬编码
3. 通过窗口信息而非端口判断模拟器类型
"""

import os
import subprocess
import logging
import win32gui
import win32process
import psutil
import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EmulatorWindow:
    """模拟器窗口信息"""
    hwnd: int
    title: str
    emulator_type: str  # 'mumu', 'ldplayer', 'unknown'
    process_path: str
    adb_path: Optional[str] = None
    device_id: Optional[str] = None
    vm_index: Optional[int] = None


@dataclass
class ADBConnection:
    """ADB连接信息"""
    device_id: str
    status: str  # 'device', 'offline', 'unauthorized'
    adb_path: str
    emulator_type: str
    port: int


class IntelligentADBConnector:
    """智能ADB连接器"""
    
    def __init__(self):
        self.emulator_windows: List[EmulatorWindow] = []
        self.adb_connections: List[ADBConnection] = []
        self.adb_paths: Dict[str, str] = {}
        
    def discover_adb_paths(self) -> Dict[str, str]:
        """发现所有可用的ADB路径"""
        adb_paths = {}
        
        # 1. 智能ADB查找器
        try:
            from utils.smart_adb_finder import SmartADBFinder
            finder = SmartADBFinder()
            all_paths = finder.find_all_adb_paths()
            if all_paths:
                adb_paths['generic'] = all_paths[0]
        except Exception as e:
            logger.debug(f"智能ADB查找失败: {e}")
        
        # 2. 雷电ADB
        try:
            from utils.ldplayer_finder import get_adb_path
            ldplayer_adb = get_adb_path()
            if ldplayer_adb:
                adb_paths['ldplayer'] = ldplayer_adb
        except Exception as e:
            logger.debug(f"雷电ADB查找失败: {e}")
        
        # 3. MuMu ADB
        try:
            from utils.mumu_finder import get_mumu_adb_path
            mumu_adb = get_mumu_adb_path()
            if mumu_adb:
                adb_paths['mumu'] = mumu_adb
        except Exception as e:
            logger.debug(f"MuMu ADB查找失败: {e}")
        
        self.adb_paths = adb_paths
        logger.info(f"发现ADB路径: {list(adb_paths.keys())}")
        return adb_paths
    
    def discover_emulator_windows(self) -> List[EmulatorWindow]:
        """发现所有模拟器窗口"""
        windows = []
        
        def enum_windows_callback(hwnd, lParam):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        # 检查是否是模拟器窗口
                        emulator_type = self._detect_emulator_type_by_title(title)
                        if emulator_type != 'unknown':
                            # 获取进程信息
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            try:
                                process = psutil.Process(pid)
                                process_path = process.exe()
                                
                                window = EmulatorWindow(
                                    hwnd=hwnd,
                                    title=title,
                                    emulator_type=emulator_type,
                                    process_path=process_path
                                )
                                
                                # 为窗口分配对应的ADB路径
                                window.adb_path = self._get_adb_path_for_window(window)
                                
                                # 为MuMu窗口提取VM索引
                                if emulator_type == 'mumu':
                                    window.vm_index = self._extract_mumu_vm_index(title)
                                
                                lParam.append(window)
                                logger.info(f"发现{emulator_type}窗口: {title} (HWND: {hwnd})")
                                
                            except Exception as e:
                                logger.debug(f"获取窗口进程信息失败: {e}")
            except Exception as e:
                logger.debug(f"枚举窗口回调异常: {e}")
            
            return True
        
        win32gui.EnumWindows(enum_windows_callback, windows)
        
        self.emulator_windows = windows
        logger.info(f"发现 {len(windows)} 个模拟器窗口")
        return windows
    
    def _detect_emulator_type_by_title(self, title: str) -> str:
        """根据窗口标题检测模拟器类型"""
        title_lower = title.lower()

        # 首先过滤掉明显的非模拟器窗口
        browser_keywords = ['edge', 'chrome', 'firefox', 'browser', '浏览器', 'microsoft', '页面']
        if any(keyword in title_lower for keyword in browser_keywords):
            return 'unknown'

        # MuMu模拟器标题模式 - 更严格的匹配
        mumu_patterns = [
            r'^mumu.*模拟器$',  # 精确匹配，以mumu开头，以模拟器结尾
            r'^mumu.*player$',
            r'^mumu.*simulator$',
            r'^网易mumu',
            r'^mumu\d+$',
            r'^mumu.*\d+-\d+$',  # MuMu模拟器12-0 格式
            r'^mumu安卓设备',  # MuMu安卓设备
        ]

        for pattern in mumu_patterns:
            if re.search(pattern, title_lower):
                return 'mumu'

        # 雷电模拟器标题模式
        ldplayer_patterns = [
            r'^雷电.*模拟器',
            r'^ldplayer',
            r'^雷电.*\d+',
            r'^ld.*player',
        ]

        for pattern in ldplayer_patterns:
            if re.search(pattern, title_lower):
                return 'ldplayer'

        return 'unknown'
    
    def _get_adb_path_for_window(self, window: EmulatorWindow) -> Optional[str]:
        """为窗口获取对应的ADB路径"""
        # 优先使用对应模拟器的专用ADB
        if window.emulator_type in self.adb_paths:
            return self.adb_paths[window.emulator_type]
        
        # 回退到通用ADB
        return self.adb_paths.get('generic')
    
    def _extract_mumu_vm_index(self, title: str) -> Optional[int]:
        """从MuMu窗口标题提取VM索引"""
        # 匹配 "MuMu模拟器12-0" 格式
        match = re.search(r'mumu.*?(\d+)-(\d+)', title.lower())
        if match:
            return int(match.group(2))  # 返回后面的数字作为VM索引
        
        # 匹配其他可能的格式
        match = re.search(r'mumu.*?(\d+)', title.lower())
        if match:
            return int(match.group(1))
        
        return None
    
    def discover_active_ports(self) -> Set[int]:
        """智能发现所有真实存在的ADB端口"""
        active_ports = set()

        try:
            # 1. 首先检查网络监听端口（最可靠的方法）
            connections = psutil.net_connections(kind='inet')

            for conn in connections:
                if (conn.laddr and conn.laddr.ip == '127.0.0.1' and
                    conn.status == psutil.CONN_LISTEN):
                    port = conn.laddr.port

                    # 检查是否是ADB相关端口
                    if self._is_adb_port(port):
                        active_ports.add(port)
                        logger.debug(f"发现真实监听ADB端口: {port}")

            # 2. 动态获取模拟器端口
            # 2.1 获取MuMu模拟器端口
            try:
                from utils.mumu_manager import get_mumu_manager
                mumu_manager = get_mumu_manager()
                if mumu_manager.is_available():
                    vm_info = mumu_manager.get_all_vm_info()
                    logger.info(f"MuMu管理器返回的VM信息: {vm_info}")

                    # 记录所有MuMu端口用于智能类型判断
                    self._mumu_ports = set()

                    if vm_info:
                        for vm_index_str, vm_data in vm_info.items():
                            adb_port = vm_data.get('adb_port')
                            vm_state = vm_data.get('player_state', 'unknown')
                            is_started = vm_data.get('is_android_started', False)
                            logger.info(f"VM{vm_index_str}: 端口={adb_port}, 状态={vm_state}, Android启动={is_started}")

                            # 记录所有MuMu端口（无论是否启动）
                            if adb_port:
                                self._mumu_ports.add(adb_port)

                            # 只添加已启动的VM端口到活跃端口
                            if adb_port and is_started and vm_state == 'start_finished':
                                active_ports.add(adb_port)
                                logger.info(f"✅ 从MuMu VM{vm_index_str}发现活跃端口: {adb_port}")
                            elif adb_port:
                                logger.warning(f"⚠️ VM{vm_index_str} 端口{adb_port}存在但未完全启动 (状态:{vm_state}, Android:{is_started})")
                    else:
                        logger.warning("MuMu管理器返回空的VM信息")

                    # MuMu管理器已经提供了所有活跃VM的准确端口信息
                    # 不需要硬编码扫描，完全依赖管理器的权威数据
                else:
                    logger.warning("MuMu管理器不可用")
            except Exception as e:
                logger.error(f"获取MuMu端口失败: {e}")

            # 2.2 获取雷电模拟器端口
            try:
                from utils.ldplayer_manager import get_ldplayer_manager
                ldplayer_manager = get_ldplayer_manager()
                if ldplayer_manager.is_available():
                    ldplayer_ports = ldplayer_manager.get_active_ports()
                    for port in ldplayer_ports:
                        active_ports.add(port)
                        logger.debug(f"从雷电模拟器发现端口: {port}")
            except Exception as e:
                logger.debug(f"获取雷电端口失败: {e}")

            # 3. 使用ADB命令检查已连接设备
            existing_devices = self._get_existing_adb_devices()
            for device_id in existing_devices:
                if ':' in device_id and device_id.startswith('127.0.0.1:'):
                    try:
                        port = int(device_id.split(':')[1])
                        active_ports.add(port)
                        logger.debug(f"从已连接设备发现端口: {port}")
                    except ValueError:
                        pass

            # 3. 验证推断的端口是否真实存在
            if self.emulator_windows:
                logger.debug("验证推断端口的真实性...")
                for window in self.emulator_windows:
                    candidate_ports = self._get_candidate_ports_for_window(window)
                    for port in candidate_ports:
                        if self._verify_port_exists(port):
                            active_ports.add(port)
                            logger.debug(f"验证端口 {port} 存在，来自窗口 {window.title}")

        except Exception as e:
            logger.warning(f"智能端口发现失败: {e}")

        # 4. 如果仍然没有发现端口，使用保守的默认端口
        if not active_ports:
            logger.info("未发现任何真实端口，使用保守的默认端口")
            # 只使用最常见的、最可能存在的端口，避免重复
            conservative_ports = [7555, 16384]  # 移除5555避免与MuMu重复
            for port in conservative_ports:
                if self._verify_port_exists(port):
                    active_ports.add(port)
                    logger.info(f"验证默认端口 {port} 存在")

        # 5. 去重：移除可能指向同一模拟器的重复端口
        deduplicated_ports = self._deduplicate_ports(active_ports)

        logger.info(f"发现 {len(active_ports)} 个真实的ADB端口: {sorted(active_ports)}")
        if len(deduplicated_ports) != len(active_ports):
            logger.info(f"去重后剩余 {len(deduplicated_ports)} 个端口: {sorted(deduplicated_ports)}")

        return deduplicated_ports

    def discover_device_list(self) -> List[str]:
        """发现所有可用设备列表（职责：设备发现和窗口匹配）"""
        device_list = []

        try:
            logger.debug("开始发现设备列表...")

            # 1. 检测当前运行的模拟器类型
            self.discover_emulator_windows()
            running_emulator_types = self._get_running_emulator_types()
            logger.info(f"检测到运行的模拟器类型: {running_emulator_types}")

            # 2. 获取活跃端口
            active_ports = self.discover_active_ports()

            # 3. 根据运行的模拟器类型过滤端口
            filtered_ports = self._filter_ports_by_emulator_type(active_ports, running_emulator_types)
            logger.info(f"根据模拟器类型过滤: {len(active_ports)} -> {len(filtered_ports)} 个端口")

            # 4. 将端口转换为设备ID
            for port in filtered_ports:
                device_id = f"127.0.0.1:{port}"
                device_list.append(device_id)
                logger.debug(f"发现设备: {device_id}")

            logger.info(f"发现 {len(device_list)} 个设备: {device_list}")
            return device_list

        except Exception as e:
            logger.error(f"发现设备列表时出错: {e}")
            return []

    def _get_running_emulator_types(self) -> List[str]:
        """获取当前运行的模拟器类型"""
        emulator_types = set()

        for window in self.emulator_windows:
            emulator_types.add(window.emulator_type)

        return list(emulator_types)

    def _filter_ports_by_emulator_type(self, ports: set, emulator_types: List[str]) -> set:
        """根据模拟器类型过滤端口"""
        if not emulator_types:
            logger.warning("未检测到运行的模拟器，返回所有端口")
            return ports

        filtered_ports = set()

        for port in ports:
            port_emulator_type = self._get_port_emulator_type(port)

            if port_emulator_type in emulator_types:
                filtered_ports.add(port)
                logger.debug(f"保留端口 {port} (类型: {port_emulator_type})")
            else:
                logger.debug(f"过滤端口 {port} (类型: {port_emulator_type}, 运行类型: {emulator_types})")

        return filtered_ports

    def _get_port_emulator_type(self, port: int) -> str:
        """根据端口号判断模拟器类型（完全基于管理器数据，无硬编码）"""
        # 检查是否是MuMu管理器报告的端口
        if hasattr(self, '_mumu_ports') and port in self._mumu_ports:
            return 'mumu'

        # 检查是否是雷电管理器报告的端口
        if hasattr(self, '_ldplayer_ports') and port in self._ldplayer_ports:
            return 'ldplayer'

        # 如果没有管理器数据，返回unknown
        return 'unknown'

    def _get_candidate_ports_for_window(self, window) -> List[int]:
        """获取窗口的候选端口（动态获取真实端口）"""
        candidates = []

        if window.emulator_type == 'mumu':
            # MuMu: 动态获取VM端口
            try:
                from utils.mumu_manager import get_mumu_manager
                mumu_manager = get_mumu_manager()
                if mumu_manager.is_available():
                    vm_info = mumu_manager.get_all_vm_info()
                    if vm_info:
                        for vm_data in vm_info.values():
                            adb_port = vm_data.get('adb_port')
                            if adb_port:
                                candidates.append(adb_port)
                        logger.debug(f"MuMu动态端口: {candidates}")
            except Exception as e:
                logger.debug(f"获取MuMu动态端口失败: {e}")
                # 回退到默认端口
                candidates.extend([7555])

        elif window.emulator_type == 'ldplayer':
            # 雷电: 动态获取实例端口
            try:
                from utils.ldplayer_manager import get_ldplayer_manager
                ldplayer_manager = get_ldplayer_manager()
                if ldplayer_manager.is_available():
                    # 尝试根据窗口句柄匹配实例
                    if hasattr(window, 'hwnd') and window.hwnd:
                        instance = ldplayer_manager.get_instance_by_hwnd(window.hwnd)
                        if instance:
                            candidates.append(instance['adb_port'])
                            logger.debug(f"雷电窗口{window.hwnd}匹配端口: {instance['adb_port']}")

                    # 如果没有匹配到，获取所有活跃端口
                    if not candidates:
                        active_ports = ldplayer_manager.get_active_ports()
                        candidates.extend(active_ports)
                        logger.debug(f"雷电活跃端口: {active_ports}")
            except Exception as e:
                logger.debug(f"获取雷电动态端口失败: {e}")
                # 回退到默认端口范围
                candidates.extend([5555, 5557, 5559, 5561, 5563])

        return candidates

    def _verify_port_exists(self, port: int) -> bool:
        """验证端口是否真实存在并可连接"""
        try:
            import socket

            # 尝试连接端口
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)  # 1秒超时
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()

            # 如果连接成功或被拒绝，说明端口存在
            return result == 0 or result == 10061  # 10061 = Connection refused (端口存在但服务拒绝)

        except Exception:
            return False

    def _deduplicate_ports(self, ports: Set[int]) -> Set[int]:
        """智能去重端口，避免同一模拟器的重复端口"""
        deduplicated = set(ports)

        # 1. MuMu端口去重：5555和7555可能指向同一个模拟器
        mumu_old_ports = {p for p in ports if 5555 <= p <= 5585}
        mumu_new_ports = {p for p in ports if 7555 <= p <= 7585}

        # 检查MuMu端口重复
        for old_port in mumu_old_ports:
            new_port = old_port + 2000  # 5555 -> 7555
            if new_port in mumu_new_ports:
                logger.info(f"检测到MuMu端口重复: {old_port} 和 {new_port}")
                if self._are_ports_same_emulator(old_port, new_port):
                    deduplicated.discard(old_port)  # 移除老格式端口
                    logger.info(f"确认端口重复，移除老格式端口: {old_port}")

        # 2. 雷电端口去重：检查是否有重复的雷电实例端口
        ldplayer_ports = {p for p in deduplicated if 5555 <= p <= 5585}
        if len(ldplayer_ports) > 1:
            # 使用雷电管理器验证哪些端口是真实的
            try:
                from utils.ldplayer_manager import get_ldplayer_manager
                ldplayer_manager = get_ldplayer_manager()
                if ldplayer_manager.is_available():
                    real_ports = set(ldplayer_manager.get_active_ports())
                    # 只保留真实存在的雷电端口
                    fake_ports = ldplayer_ports - real_ports
                    for fake_port in fake_ports:
                        deduplicated.discard(fake_port)
                        logger.info(f"移除虚假雷电端口: {fake_port}")
            except Exception as e:
                logger.debug(f"雷电端口验证失败: {e}")

        # 3. 通用重复检查：检查是否有其他类型的重复
        ports_list = list(deduplicated)
        for i, port1 in enumerate(ports_list):
            for port2 in ports_list[i+1:]:
                # 检查是否为已知的重复模式
                if self._are_ports_likely_duplicate(port1, port2):
                    if self._are_ports_same_emulator(port1, port2):
                        # 保留较大的端口（通常是新格式）
                        remove_port = min(port1, port2)
                        if remove_port in deduplicated:
                            deduplicated.discard(remove_port)
                            logger.info(f"移除重复端口: {remove_port} (保留 {max(port1, port2)})")

        return deduplicated

    def _are_ports_likely_duplicate(self, port1: int, port2: int) -> bool:
        """检查两个端口是否可能是重复的"""
        # MuMu端口重复模式：5555 vs 7555
        if abs(port1 - port2) == 2000 and min(port1, port2) >= 5555:
            return True

        # 其他已知的重复模式可以在这里添加
        return False

    def _are_ports_same_emulator(self, port1: int, port2: int) -> bool:
        """检查两个端口是否指向同一个模拟器"""
        try:
            # 尝试通过ADB获取设备信息来判断
            device1 = f"127.0.0.1:{port1}"
            device2 = f"127.0.0.1:{port2}"

            # 简单的启发式检查：如果两个端口都能连接且差值为2000，很可能是同一个MuMu模拟器
            if abs(port1 - port2) == 2000 and self._verify_port_exists(port1) and self._verify_port_exists(port2):
                return True

        except Exception as e:
            logger.debug(f"检查端口重复时出错: {e}")

        return False

    def _get_existing_adb_devices(self) -> List[str]:
        """获取已连接的ADB设备"""
        devices = []

        try:
            # 尝试使用不同的ADB路径
            for adb_type, adb_path in self.adb_paths.items():
                try:
                    result = subprocess.run(
                        [adb_path, 'devices'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding='utf-8',
                        errors='ignore'
                    )

                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            line = line.strip()
                            if '\tdevice' in line:
                                device_id = line.split('\t')[0]
                                if device_id not in devices:
                                    devices.append(device_id)

                        # 如果找到设备就不用尝试其他ADB了
                        if devices:
                            break

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"获取已连接设备失败: {e}")

        return devices

    def _get_default_ports_for_emulator(self, emulator_type: str) -> Set[int]:
        """获取模拟器类型的默认端口（动态获取）"""
        ports = set()

        if emulator_type == 'mumu':
            # 动态获取MuMu端口
            try:
                from utils.mumu_manager import get_mumu_manager
                mumu_manager = get_mumu_manager()
                if mumu_manager.is_available():
                    vm_info = mumu_manager.get_all_vm_info()
                    if vm_info:
                        for vm_data in vm_info.values():
                            adb_port = vm_data.get('adb_port')
                            if adb_port:
                                ports.add(adb_port)
            except Exception as e:
                logger.debug(f"获取MuMu动态端口失败: {e}")

            # 如果没有动态端口，使用默认端口
            if not ports:
                ports.add(7555)

        elif emulator_type == 'ldplayer':
            # 动态获取雷电端口
            try:
                from utils.ldplayer_manager import get_ldplayer_manager
                ldplayer_manager = get_ldplayer_manager()
                if ldplayer_manager.is_available():
                    active_ports = ldplayer_manager.get_active_ports()
                    ports.update(active_ports)
            except Exception as e:
                logger.debug(f"获取雷电动态端口失败: {e}")

            # 如果没有动态端口，使用默认端口
            if not ports:
                ports.update({5555, 5557})
        else:
            ports.add(5555)

        return ports
    
    def _is_adb_port(self, port: int) -> bool:
        """判断端口是否可能是ADB端口"""
        # 常见的ADB端口范围
        adb_port_ranges = [
            (5555, 5585),  # 雷电/通用模拟器
            (7555, 7585),  # MuMu模拟器
            (16384, 16400),  # 其他模拟器
            (21503, 21520),  # 其他模拟器
        ]
        
        for start, end in adb_port_ranges:
            if start <= port <= end:
                return True
        
        return False
    
    def connect_all_devices(self) -> List[ADBConnection]:
        """智能连接所有设备 - 避免重复连接"""
        connections = []
        used_ports = set()

        # 获取活跃端口
        active_ports = self.discover_active_ports()

        # 为每个模拟器窗口分配唯一端口
        for window in self.emulator_windows:
            if not window.adb_path:
                logger.warning(f"窗口 {window.title} 没有可用的ADB路径")
                continue

            # 为该窗口找到最佳端口（避免重复）
            best_port = self._find_best_port_for_window(window, active_ports, used_ports)

            if best_port:
                conn = self._try_connect_port(best_port, window.adb_path, window.emulator_type)
                if conn:
                    connections.append(conn)
                    used_ports.add(best_port)
                    window.device_id = conn.device_id
                    logger.info(f"✅ 窗口 {window.title} 连接到设备: {conn.device_id}")
                else:
                    logger.warning(f"⚠️ 窗口 {window.title} 连接端口 {best_port} 失败")
            else:
                logger.warning(f"⚠️ 窗口 {window.title} 未找到可用端口")

        # 对于剩余端口，使用通用ADB连接（如果有必要）
        remaining_ports = active_ports - used_ports

        if remaining_ports and len(connections) < len(self.emulator_windows):
            logger.info(f"尝试连接剩余端口以匹配未连接的窗口: {sorted(remaining_ports)}")

            # 只连接与窗口数量相匹配的设备数
            max_additional = len(self.emulator_windows) - len(connections)
            connected_additional = 0

            for port in sorted(remaining_ports):
                if connected_additional >= max_additional:
                    break

                # 使用最合适的ADB路径
                best_adb = self._get_best_adb_for_port(port)
                if best_adb:
                    conn = self._try_connect_port(port, best_adb, 'unknown')
                    if conn:
                        connections.append(conn)
                        connected_additional += 1
                        logger.info(f"✅ 额外连接设备: {conn.device_id}")

        self.adb_connections = connections
        logger.info(f"智能连接完成: {len(connections)} 个唯一设备")
        return connections
    
    def _find_best_port_for_window(self, window: EmulatorWindow, active_ports: Set[int], used_ports: Set[int]) -> Optional[int]:
        """为窗口找到最佳端口（避免重复使用）"""
        available_ports = active_ports - used_ports

        if not available_ports:
            return None

        # 根据窗口类型和VM索引确定优先端口
        if window.emulator_type == 'mumu':
            # MuMu模拟器端口优先级
            if window.vm_index is not None:
                # 基于VM索引的首选端口
                preferred_ports = [
                    7555 + window.vm_index,  # MuMu标准端口
                    5555 + window.vm_index * 2,  # 备用端口
                ]

                for port in preferred_ports:
                    if port in available_ports:
                        return port

            # MuMu通用端口优先级
            mumu_ports = [p for p in available_ports if 7555 <= p <= 7585]
            if mumu_ports:
                return min(mumu_ports)  # 选择最小的可用端口

            # 备用端口
            backup_ports = [p for p in available_ports if 5555 <= p <= 5585 or p >= 16384]
            if backup_ports:
                return min(backup_ports)

        elif window.emulator_type == 'ldplayer':
            # 雷电模拟器端口优先级
            ldplayer_ports = [p for p in available_ports if 5555 <= p <= 5585]
            if ldplayer_ports:
                return min(ldplayer_ports)

        # 如果没有特定类型的端口，返回任意可用端口
        return min(available_ports) if available_ports else None

    def _get_best_adb_for_port(self, port: int) -> Optional[str]:
        """根据端口获取最佳ADB路径"""
        # 根据端口范围推断模拟器类型
        if 7555 <= port <= 7585:
            # MuMu端口范围
            return self.adb_paths.get('mumu') or self.adb_paths.get('generic')
        elif 5555 <= port <= 5585:
            # 通用端口范围，优先使用雷电
            return self.adb_paths.get('ldplayer') or self.adb_paths.get('generic')
        else:
            # 其他端口使用通用ADB
            return self.adb_paths.get('generic')
    
    def _try_connect_port(self, port: int, adb_path: str, emulator_type: str) -> Optional[ADBConnection]:
        """尝试连接指定端口"""
        device_id = f"127.0.0.1:{port}"
        
        try:
            # 尝试连接
            result = subprocess.run(
                [adb_path, 'connect', device_id],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding='utf-8',
                errors='ignore'
            )
            
            # 检查连接状态
            status_result = subprocess.run(
                [adb_path, '-s', device_id, 'get-state'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding='utf-8',
                errors='ignore'
            )
            
            if status_result.returncode == 0:
                status = status_result.stdout.strip()
                if status == 'device':
                    logger.info(f"✅ 成功连接: {device_id} ({emulator_type})")
                    return ADBConnection(
                        device_id=device_id,
                        status=status,
                        adb_path=adb_path,
                        emulator_type=emulator_type,
                        port=port
                    )
                else:
                    logger.debug(f"设备状态异常: {device_id} -> {status}")
            
        except Exception as e:
            logger.debug(f"连接端口 {port} 失败: {e}")
        
        return None
    
    def get_connection_summary(self) -> Dict:
        """获取连接总结"""
        summary = {
            'total_windows': len(self.emulator_windows),
            'total_connections': len(self.adb_connections),
            'by_emulator_type': {},
            'windows': [],
            'connections': []
        }
        
        # 按模拟器类型统计
        for conn in self.adb_connections:
            if conn.emulator_type not in summary['by_emulator_type']:
                summary['by_emulator_type'][conn.emulator_type] = 0
            summary['by_emulator_type'][conn.emulator_type] += 1
        
        # 窗口信息
        for window in self.emulator_windows:
            summary['windows'].append({
                'title': window.title,
                'emulator_type': window.emulator_type,
                'device_id': window.device_id,
                'adb_path': os.path.basename(window.adb_path) if window.adb_path else None
            })
        
        # 连接信息
        for conn in self.adb_connections:
            summary['connections'].append({
                'device_id': conn.device_id,
                'emulator_type': conn.emulator_type,
                'status': conn.status,
                'port': conn.port,
                'adb_path': os.path.basename(conn.adb_path)
            })
        
        return summary
