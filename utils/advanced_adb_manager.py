#!/usr/bin/env python3
"""
先进的ADB连接管理器
实现企业级ADB连接池、自动重连、健康监控等功能
"""

import asyncio
import threading
import time
import subprocess
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future
import queue
import weakref
from pathlib import Path

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """设备状态枚举"""
    ONLINE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


class ConnectionHealth(Enum):
    """连接健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class DeviceInfo:
    """设备信息"""
    device_id: str
    status: DeviceStatus
    adb_path: str
    last_seen: float = field(default_factory=time.time)
    connection_count: int = 0
    error_count: int = 0
    success_count: int = 0
    health: ConnectionHealth = ConnectionHealth.HEALTHY
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class ADBCommand:
    """ADB命令"""
    command: List[str]
    device_id: str
    timeout: float = 10.0
    priority: int = 0  # 0=normal, 1=high, 2=critical
    retry_count: int = 3
    callback: Optional[Callable] = None
    future: Optional[Future] = None


class AdvancedADBConnectionPool:
    """先进的ADB连接池"""
    
    def __init__(self, max_connections: int = 50, health_check_interval: float = 30.0):
        self.max_connections = max_connections
        self.health_check_interval = health_check_interval
        
        # 连接池
        self._connections: Dict[str, DeviceInfo] = {}
        self._connection_lock = threading.RLock()
        
        # 命令队列
        self._command_queue = queue.PriorityQueue()
        self._executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ADB-Worker")
        
        # 健康监控
        self._health_monitor_thread = None
        self._health_monitor_running = False
        
        # 统计信息
        self._stats = {
            'total_commands': 0,
            'successful_commands': 0,
            'failed_commands': 0,
            'reconnections': 0,
            'devices_discovered': 0
        }
        
        # ADB路径缓存
        self._adb_paths: Dict[str, str] = {}  # emulator_type -> adb_path
        
        # 启动健康监控
        self.start_health_monitoring()
    
    def discover_adb_paths(self) -> Dict[str, str]:
        """发现所有可用的ADB路径"""
        adb_paths = {}
        
        try:
            # 1. 智能ADB查找器
            from utils.smart_adb_finder import SmartADBFinder
            finder = SmartADBFinder()
            all_paths = finder.find_all_adb_paths()
            
            if all_paths:
                adb_paths['generic'] = all_paths[0]
            
            # 2. 雷电ADB
            try:
                from utils.ldplayer_finder import get_adb_path
                ldplayer_adb = get_adb_path()
                if ldplayer_adb:
                    adb_paths['ldplayer'] = ldplayer_adb
            except:
                pass
            
            # 3. MuMu ADB
            try:
                from utils.mumu_finder import get_mumu_adb_path
                mumu_adb = get_mumu_adb_path()
                if mumu_adb:
                    adb_paths['mumu'] = mumu_adb
            except:
                pass
            
            self._adb_paths = adb_paths
            logger.info(f"发现ADB路径: {list(adb_paths.keys())}")
            
        except Exception as e:
            logger.error(f"ADB路径发现失败: {e}")
        
        return adb_paths
    
    def get_adb_path_for_device(self, device_id: str) -> Optional[str]:
        """为设备获取最佳ADB路径"""
        # 如果设备已在连接池中，使用其ADB路径
        if device_id in self._connections:
            return self._connections[device_id].adb_path
        
        # 根据设备ID推断模拟器类型
        if 'emulator-' in device_id:
            # 通用模拟器设备
            return self._adb_paths.get('generic')
        elif '127.0.0.1:' in device_id:
            port = int(device_id.split(':')[1])
            if 5555 <= port <= 5585:  # 雷电端口范围
                return self._adb_paths.get('ldplayer', self._adb_paths.get('generic'))
            elif 7555 <= port <= 7585:  # MuMu端口范围
                return self._adb_paths.get('mumu', self._adb_paths.get('generic'))
        
        return self._adb_paths.get('generic')
    
    def create_devices_from_list(self, device_list: List[str]) -> List[DeviceInfo]:
        """根据提供的设备列表创建DeviceInfo对象（职责：底层ADB操作）"""
        discovered_devices = []

        # 首先按照官方文档执行 adb devices 来发现设备
        self._refresh_adb_devices()

        for device_id in device_list:
            # 确定使用哪个ADB路径
            adb_path = self._determine_adb_path_for_device(device_id)

            try:
                # 对于MuMu设备，使用特殊的状态检查逻辑
                if self._is_mumu_device(device_id):
                    status = self._check_mumu_device_status(device_id, adb_path)
                else:
                    # 检查设备状态
                    result = subprocess.run(
                        [adb_path, '-s', device_id, 'get-state'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding='utf-8',
                        errors='ignore'
                    )

                    if result.returncode == 0:
                        status_str = result.stdout.strip()
                        if status_str == 'device':
                            status = DeviceStatus.ONLINE
                        elif status_str == 'offline':
                            status = DeviceStatus.OFFLINE
                        elif status_str == 'unauthorized':
                            status = DeviceStatus.UNAUTHORIZED
                        else:
                            status = DeviceStatus.UNKNOWN
                    else:
                        status = DeviceStatus.OFFLINE

                device_info = DeviceInfo(
                    device_id=device_id,
                    status=status,
                    adb_path=adb_path
                )
                discovered_devices.append(device_info)
                logger.debug(f"创建设备信息: {device_id} -> {adb_path}")

                # 如果设备离线，尝试连接
                if status == DeviceStatus.OFFLINE and ':' in device_id:
                    logger.info(f"尝试连接离线设备: {device_id}")
                    if self.attempt_device_connection(device_id, adb_path):
                        # 重新检查状态
                        device_info.status = DeviceStatus.ONLINE
                        logger.info(f"✅ 设备连接成功: {device_id}")
                    else:
                        logger.warning(f"⚠️ 设备连接失败: {device_id}")

            except Exception as e:
                logger.warning(f"检查设备状态失败 {device_id}: {e}")
                # 即使检查失败，也创建设备信息，状态为UNKNOWN
                device_info = DeviceInfo(
                    device_id=device_id,
                    status=DeviceStatus.UNKNOWN,
                    adb_path=self._determine_adb_path_for_device(device_id)
                )
                discovered_devices.append(device_info)

        # 更新连接池
        self._update_connection_pool(discovered_devices)

        # 等待设备稳定连接
        import time
        time.sleep(3)

        # 重新验证设备连接状态
        self._verify_device_connections(discovered_devices)

        return discovered_devices

    def _refresh_adb_devices(self):
        """按照官方文档刷新ADB设备列表"""
        # 首先重启ADB服务器解决协议冲突
        self._restart_adb_server()

        for emulator_type, adb_path in self._adb_paths.items():
            try:
                logger.info(f"🔄 刷新{emulator_type} ADB设备列表: {adb_path}")
                result = subprocess.run(
                    [adb_path, 'devices'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding='utf-8',
                    errors='ignore'
                )

                if result.returncode == 0:
                    logger.debug(f"{emulator_type} ADB devices输出: {result.stdout}")
                else:
                    logger.warning(f"{emulator_type} ADB devices失败: {result.stderr}")

            except Exception as e:
                logger.error(f"刷新{emulator_type} ADB设备列表失败: {e}")

    def _restart_adb_server(self):
        """彻底重启ADB服务器解决协议冲突"""
        try:
            import time
            import os

            # 1. 尝试多种方法杀死ADB进程
            logger.info("🔄 强制终止所有ADB进程...")

            # 方法1: taskkill
            try:
                subprocess.run(['taskkill', '/f', '/im', 'adb.exe'],
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except:
                pass

            # 方法2: 使用各个ADB的kill-server
            for adb_path in self._adb_paths.values():
                try:
                    subprocess.run([adb_path, 'kill-server'],
                                 capture_output=True, timeout=3,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                except:
                    pass

            # 2. 等待进程完全退出
            time.sleep(3)

            # 3. 清理ADB临时文件
            try:
                temp_dir = os.environ.get('TEMP', '')
                if temp_dir:
                    adb_temp_files = [
                        os.path.join(temp_dir, 'adb.log'),
                        os.path.join(temp_dir, 'adb_usb.ini'),
                    ]
                    for temp_file in adb_temp_files:
                        if os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                                logger.debug(f"清理临时文件: {temp_file}")
                            except:
                                pass
            except:
                pass

            # 4. 智能选择ADB启动服务器
            self._smart_start_adb_server()

        except Exception as e:
            logger.warning(f"重启ADB服务器失败: {e}")

    def _smart_start_adb_server(self):
        """智能选择合适的ADB启动服务器"""
        try:
            import time

            # 检测当前运行的模拟器类型
            running_emulators = self._detect_running_emulators()
            logger.info(f"🔍 检测到运行的模拟器: {running_emulators}")

            # 根据运行的模拟器选择ADB优先级
            adb_priority = []

            if 'ldplayer' in running_emulators:
                adb_priority.append(('ldplayer', '雷电'))
            if 'mumu' in running_emulators:
                adb_priority.append(('mumu', 'MuMu'))

            # 如果没有检测到特定模拟器，使用默认优先级
            if not adb_priority:
                logger.info("未检测到特定模拟器，使用默认ADB优先级")
                adb_priority = [
                    ('generic', '通用'),
                    ('ldplayer', '雷电'),
                    ('mumu', 'MuMu')
                ]
            else:
                # 添加通用ADB作为备选
                adb_priority.append(('generic', '通用'))

            # 按优先级尝试启动ADB服务器
            for adb_type, display_name in adb_priority:
                adb_path = self._adb_paths.get(adb_type)
                if not adb_path:
                    continue

                logger.info(f"🔄 尝试使用{display_name}ADB启动服务器: {adb_path}")

                # 多次尝试启动
                success = False
                for attempt in range(3):
                    try:
                        result = subprocess.run(
                            [adb_path, 'start-server'],
                            capture_output=True,
                            timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            text=True
                        )

                        if result.returncode == 0:
                            logger.info(f"✅ {display_name}ADB服务器启动成功")
                            success = True
                            break
                        else:
                            logger.debug(f"{display_name}ADB启动失败 (尝试 {attempt+1}/3): {result.stderr}")
                            if attempt < 2:
                                time.sleep(1)
                    except Exception as e:
                        logger.debug(f"{display_name}ADB启动异常 (尝试 {attempt+1}/3): {e}")
                        if attempt < 2:
                            time.sleep(1)

                if success:
                    logger.info(f"🎯 最终选择使用{display_name}ADB服务器")
                    break
                else:
                    logger.warning(f"❌ {display_name}ADB服务器启动失败，尝试下一个")

        except Exception as e:
            logger.error(f"智能启动ADB服务器失败: {e}")

    def _detect_running_emulators(self) -> List[str]:
        """检测当前运行的模拟器类型"""
        try:
            import win32gui
            from utils.emulator_detector import detect_emulator_type

            running_emulators = set()

            def enum_windows_callback(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True

                    is_emulator, emulator_type, description = detect_emulator_type(hwnd)
                    if is_emulator and emulator_type:
                        running_emulators.add(emulator_type)
                        logger.debug(f"检测到运行的模拟器: {description}")

                except Exception as e:
                    logger.debug(f"检测窗口时出错: {e}")

                return True

            win32gui.EnumWindows(enum_windows_callback, None)
            return list(running_emulators)

        except Exception as e:
            logger.error(f"检测运行模拟器失败: {e}")
            return []

    def _verify_device_connections(self, devices: List[DeviceInfo]):
        """验证设备连接状态"""
        try:
            logger.info("🔍 验证设备连接状态...")

            for device in devices:
                try:
                    # 使用设备专用的ADB路径验证连接
                    result = subprocess.run(
                        [device.adb_path, 'devices'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )

                    if result.returncode == 0:
                        # 检查设备是否在列表中
                        if device.device_id in result.stdout:
                            logger.info(f"✅ 设备连接验证成功: {device.device_id}")
                        else:
                            logger.warning(f"⚠️ 设备未在ADB列表中: {device.device_id}")
                            # 尝试重新连接
                            if ':' in device.device_id:
                                self.attempt_device_connection(device.device_id, device.adb_path)
                    else:
                        logger.warning(f"⚠️ ADB devices命令失败: {device.device_id}")

                except Exception as e:
                    logger.warning(f"验证设备连接失败 {device.device_id}: {e}")

        except Exception as e:
            logger.error(f"验证设备连接时出错: {e}")

    def _update_connection_pool(self, devices: List[DeviceInfo]):
        """更新连接池（职责：连接池管理）"""
        with self._connection_lock:
            for device in devices:
                if device.device_id not in self._connections:
                    self._connections[device.device_id] = device
                    self._stats['devices_discovered'] += 1
                    logger.info(f"发现新设备: {device.device_id} ({device.status.value})")
                else:
                    # 更新现有设备状态
                    existing = self._connections[device.device_id]
                    if existing.status != device.status:
                        logger.info(f"设备状态变更: {device.device_id} {existing.status.value} -> {device.status.value}")
                        existing.status = device.status
                    existing.last_seen = time.time()

    def _determine_adb_path_for_device(self, device_id: str) -> str:
        """根据设备ID确定应该使用的ADB路径（职责：ADB路径管理）"""
        try:
            if ':' in device_id:
                port = int(device_id.split(':')[1])

                # MuMu模拟器端口范围
                if 16384 <= port <= 16500:
                    mumu_adb = self._adb_paths.get('mumu')
                    if mumu_adb:
                        return mumu_adb
                    else:
                        logger.error(f"MuMu设备 {device_id} 找不到MuMu ADB路径！")
                        return None

                # 雷电模拟器端口范围
                elif 5555 <= port <= 5585:
                    return self._adb_paths.get('ldplayer', self._adb_paths.get('generic'))

        except (ValueError, IndexError):
            pass

        # 默认使用通用ADB
        return self._adb_paths.get('generic')

    def _is_mumu_device(self, device_id: str) -> bool:
        """判断是否是MuMu设备"""
        try:
            if ':' in device_id:
                port = int(device_id.split(':')[1])
                return 16384 <= port <= 16500
        except (ValueError, IndexError):
            pass
        return False

    def _check_mumu_device_status(self, device_id: str, adb_path: str) -> DeviceStatus:
        """检查MuMu设备状态"""
        try:
            # 对于MuMu设备，先检查VM是否在运行
            from utils.mumu_manager import get_mumu_manager
            mumu_manager = get_mumu_manager()

            if mumu_manager.is_available():
                vm_info = mumu_manager.get_all_vm_info()
                if vm_info:
                    port = int(device_id.split(':')[1])
                    for vm_data in vm_info.values():
                        if vm_data.get('adb_port') == port:
                            if (vm_data.get('is_android_started', False) and
                                vm_data.get('player_state') == 'start_finished'):
                                logger.debug(f"MuMu设备 {device_id} VM已启动，认为在线")
                                return DeviceStatus.ONLINE
                            else:
                                logger.debug(f"MuMu设备 {device_id} VM未完全启动")
                                return DeviceStatus.OFFLINE

            # 如果MuMu管理器不可用，回退到标准检查
            result = subprocess.run(
                [adb_path, '-s', device_id, 'get-state'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                status_str = result.stdout.strip()
                if status_str == 'device':
                    return DeviceStatus.ONLINE
                elif status_str == 'offline':
                    return DeviceStatus.OFFLINE
                elif status_str == 'unauthorized':
                    return DeviceStatus.UNAUTHORIZED

            return DeviceStatus.OFFLINE

        except Exception as e:
            logger.debug(f"检查MuMu设备状态失败 {device_id}: {e}")
            return DeviceStatus.OFFLINE

    # MuMu设备发现逻辑已移至 intelligent_adb_connector
    # advanced_adb_manager 专注于底层ADB操作和连接池管理

    def attempt_device_connection(self, device_id: str, adb_path: str) -> bool:
        """尝试连接设备"""
        try:
            # 如果是网络设备，尝试连接
            if '127.0.0.1:' in device_id:
                result = subprocess.run(
                    [adb_path, 'connect', device_id],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding='utf-8',
                    errors='ignore'
                )
                
                if result.returncode == 0 and 'connected' in result.stdout.lower():
                    logger.info(f"设备连接成功: {device_id}")
                    return True
            
            # 测试设备连接
            result = subprocess.run(
                [adb_path, '-s', device_id, 'shell', 'echo', 'test'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding='utf-8',
                errors='ignore'
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.warning(f"设备连接测试失败 {device_id}: {e}")
            return False
    
    def execute_command_sync(self, command: ADBCommand) -> Tuple[bool, str, str]:
        """同步执行ADB命令"""
        device_info = self._connections.get(command.device_id)
        if not device_info:
            return False, "", "设备不在连接池中"
        
        adb_path = device_info.adb_path
        full_command = [adb_path, '-s', command.device_id] + command.command

        # 调试日志：显示实际使用的ADB路径
        logger.info(f"🔧 执行ADB命令: {' '.join(full_command)}")
        logger.info(f"🔧 设备 {command.device_id} 使用ADB路径: {adb_path}")
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=command.timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding='utf-8',
                errors='ignore'
            )
            
            execution_time = time.time() - start_time
            success = result.returncode == 0
            
            # 更新统计
            with self._connection_lock:
                device_info.connection_count += 1
                if success:
                    device_info.success_count += 1
                    self._stats['successful_commands'] += 1
                else:
                    device_info.error_count += 1
                    self._stats['failed_commands'] += 1
                
                self._stats['total_commands'] += 1
                device_info.last_seen = time.time()
            
            # 更新设备健康状态
            self._update_device_health(device_info)
            
            return success, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            logger.warning(f"命令超时: {' '.join(full_command)}")
            with self._connection_lock:
                device_info.error_count += 1
                self._stats['failed_commands'] += 1
                self._stats['total_commands'] += 1
            return False, "", "命令执行超时"
            
        except Exception as e:
            logger.error(f"命令执行异常: {e}")
            with self._connection_lock:
                device_info.error_count += 1
                self._stats['failed_commands'] += 1
                self._stats['total_commands'] += 1
            return False, "", str(e)
    
    def execute_command_async(self, command: ADBCommand) -> Future:
        """异步执行ADB命令"""
        future = self._executor.submit(self._execute_with_retry, command)
        command.future = future
        return future
    
    def _execute_with_retry(self, command: ADBCommand) -> Tuple[bool, str, str]:
        """带重试的命令执行"""
        last_error = ""
        
        for attempt in range(command.retry_count):
            success, stdout, stderr = self.execute_command_sync(command)
            
            if success:
                if command.callback:
                    try:
                        command.callback(True, stdout, stderr)
                    except Exception as e:
                        logger.error(f"回调函数执行失败: {e}")
                return success, stdout, stderr
            
            last_error = stderr
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < command.retry_count - 1:
                wait_time = (2 ** attempt) * 0.5  # 指数退避
                time.sleep(wait_time)
                logger.info(f"命令重试 {attempt + 1}/{command.retry_count}: {command.device_id}")
        
        # 所有重试都失败
        if command.callback:
            try:
                command.callback(False, "", last_error)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}")
        
        return False, "", last_error
    
    def _update_device_health(self, device_info: DeviceInfo):
        """更新设备健康状态"""
        total_commands = device_info.success_count + device_info.error_count
        
        if total_commands == 0:
            device_info.health = ConnectionHealth.HEALTHY
            return
        
        success_rate = device_info.success_count / total_commands
        
        if success_rate >= 0.95:
            device_info.health = ConnectionHealth.HEALTHY
        elif success_rate >= 0.80:
            device_info.health = ConnectionHealth.DEGRADED
        elif success_rate >= 0.50:
            device_info.health = ConnectionHealth.UNHEALTHY
        else:
            device_info.health = ConnectionHealth.CRITICAL
    
    def start_health_monitoring(self):
        """启动健康监控"""
        if self._health_monitor_running:
            return
        
        self._health_monitor_running = True
        self._health_monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            name="ADB-HealthMonitor",
            daemon=True
        )
        self._health_monitor_thread.start()
        logger.info("ADB健康监控已启动")
    
    def _health_monitor_loop(self):
        """健康监控循环"""
        while self._health_monitor_running:
            try:
                # 健康监控不再主动发现设备，只检查现有设备状态
                # 设备发现由 intelligent_adb_connector 负责
                
                # 检查设备健康状态
                with self._connection_lock:
                    current_time = time.time()
                    unhealthy_devices = []
                    
                    for device_id, device_info in self._connections.items():
                        # 检查设备是否长时间未响应
                        if current_time - device_info.last_seen > 300:  # 5分钟
                            device_info.health = ConnectionHealth.CRITICAL
                            unhealthy_devices.append(device_id)
                        
                        # 尝试重连不健康的设备
                        if device_info.health in [ConnectionHealth.UNHEALTHY, ConnectionHealth.CRITICAL]:
                            if device_info.status == DeviceStatus.OFFLINE:
                                if self.attempt_device_connection(device_id, device_info.adb_path):
                                    device_info.status = DeviceStatus.ONLINE
                                    device_info.health = ConnectionHealth.HEALTHY
                                    device_info.error_count = 0
                                    self._stats['reconnections'] += 1
                                    logger.info(f"设备重连成功: {device_id}")
                
                time.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"健康监控异常: {e}")
                time.sleep(5)
    
    def get_healthy_devices(self) -> List[DeviceInfo]:
        """获取健康的设备列表，智能处理离线设备"""
        with self._connection_lock:
            healthy = []
            offline_devices = []

            for device in self._connections.values():
                # 收集离线设备
                if device.status == DeviceStatus.OFFLINE:
                    offline_devices.append(device)
                # 收集健康的在线设备
                elif (device.status == DeviceStatus.ONLINE and
                      device.health in [ConnectionHealth.HEALTHY, ConnectionHealth.DEGRADED]):
                    healthy.append(device)

            # 如果有离线设备，尝试批量重连
            if offline_devices:
                logger.info(f"🔄 发现 {len(offline_devices)} 个离线设备，尝试批量重连...")
                reconnected = self._batch_reconnect_devices(offline_devices)
                healthy.extend(reconnected)

                if reconnected:
                    logger.info(f"✅ 成功重连 {len(reconnected)} 个设备")

            # 去重处理（避免端口重复映射的设备）
            unique_healthy = self._deduplicate_devices(healthy)

            if len(unique_healthy) != len(healthy):
                logger.info(f"🎯 去重处理: {len(healthy)} → {len(unique_healthy)} 个唯一设备")

            return unique_healthy

    def _try_reconnect_device(self, device: DeviceInfo) -> bool:
        """尝试重连设备"""
        try:
            # 对于网络设备，尝试重新连接
            if '127.0.0.1:' in device.device_id:
                result = subprocess.run(
                    [device.adb_path, 'connect', device.device_id],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding='utf-8',
                    errors='ignore'
                )

                if result.returncode == 0:
                    # 验证连接
                    test_result = subprocess.run(
                        [device.adb_path, '-s', device.device_id, 'shell', 'echo', 'test'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    return test_result.returncode == 0

            return False

        except Exception as e:
            logger.debug(f"设备重连失败 {device.device_id}: {e}")
            return False

    def _batch_reconnect_devices(self, offline_devices: List[DeviceInfo]) -> List[DeviceInfo]:
        """批量重连离线设备"""
        reconnected = []

        for device in offline_devices:
            if self._try_reconnect_device(device):
                device.status = DeviceStatus.ONLINE
                device.health = ConnectionHealth.HEALTHY
                device.error_count = 0
                reconnected.append(device)
                logger.info(f"✅ 设备重连成功: {device.device_id}")

        return reconnected

    def _deduplicate_devices(self, devices: List[DeviceInfo]) -> List[DeviceInfo]:
        """去重设备列表，根据模拟器类型过滤端口"""
        if not devices:
            return devices

        # 检测当前运行的模拟器类型
        detected_emulators = self._detect_running_emulators()
        logger.info(f"检测到运行的模拟器: {detected_emulators}")

        # 按端口优先级去重
        seen_ports = set()
        unique_devices = []

        # 按优先级排序
        sorted_devices = sorted(devices, key=lambda d: self._get_port_priority(d.device_id))

        for device in sorted_devices:
            port = self._extract_port(device.device_id)
            if not port:
                logger.info(f"❌ 跳过无端口设备: {device.device_id}")
                continue

            # 根据检测到的模拟器类型过滤端口
            if not self._is_valid_port_for_emulators(port, detected_emulators):
                logger.info(f"❌ 过滤不匹配的端口: {device.device_id} (检测到的模拟器: {detected_emulators})")
                continue

            port_key = self._get_port_key(device.device_id)
            logger.info(f"🔍 设备 {device.device_id} -> 端口键: {port_key}")

            # 过滤无效端口
            if port_key.startswith("invalid_"):
                logger.info(f"❌ 过滤无效端口: {device.device_id}")
                continue

            if port_key not in seen_ports:
                seen_ports.add(port_key)
                unique_devices.append(device)
                logger.info(f"✅ 保留设备: {device.device_id}")
            else:
                logger.info(f"❌ 去重跳过重复设备: {device.device_id} (端口键: {port_key})")

        return unique_devices

    def _detect_running_emulators(self) -> List[str]:
        """检测当前运行的模拟器类型（基于窗口检测）"""
        emulators = []

        try:
            # 使用窗口检测来确定模拟器类型，更准确
            from utils.intelligent_adb_connector import IntelligentADBConnector
            connector = IntelligentADBConnector()
            windows = connector.discover_emulator_windows()

            for window in windows:
                if hasattr(window, 'emulator_type'):
                    if window.emulator_type == 'mumu' and 'mumu' not in emulators:
                        emulators.append('mumu')
                    elif window.emulator_type == 'ldplayer' and 'ldplayer' not in emulators:
                        emulators.append('ldplayer')

            logger.debug(f"基于窗口检测到的模拟器类型: {emulators}")

        except Exception as e:
            logger.debug(f"窗口检测失败，回退到进程检测: {e}")

            # 回退到进程检测，但更严格
            try:
                import psutil

                for proc in psutil.process_iter(['name', 'exe']):
                    try:
                        proc_name = proc.info['name'].lower() if proc.info['name'] else ''

                        # 只检测核心进程，避免误判
                        if 'nemuheadless' in proc_name and 'mumu' not in emulators:
                            emulators.append('mumu')
                        elif 'dnplayer' in proc_name and 'ldplayer' not in emulators:
                            emulators.append('ldplayer')

                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            except Exception as e2:
                logger.debug(f"进程检测也失败: {e2}")

        return emulators

    def _is_valid_port_for_emulators(self, port: int, emulators: List[str]) -> bool:
        """检查端口是否对应检测到的模拟器类型（基于管理器数据，无硬编码）"""
        if not emulators:
            return True  # 如果检测不到模拟器，保持原有行为

        # 使用智能连接器的端口类型判断（基于管理器数据）
        try:
            from utils.intelligent_adb_connector import IntelligentADBConnector
            connector = IntelligentADBConnector()
            port_type = connector._get_port_emulator_type(port)

            # 如果端口类型匹配检测到的模拟器类型，则有效
            if port_type in emulators:
                return True

            # 如果端口类型是unknown但检测到了对应的模拟器，也认为有效
            # 这处理了管理器数据不完整的情况
            if port_type == 'unknown' and emulators:
                return True

        except Exception as e:
            logger.debug(f"智能端口类型检测失败: {e}")
            # 如果智能检测失败，默认认为有效
            return True

        return False

    def _extract_port(self, device_id: str) -> Optional[int]:
        """从设备ID中提取端口号"""
        try:
            if ':' in device_id:
                return int(device_id.split(':')[1])
        except (ValueError, IndexError):
            pass
        return None

    def _get_port_priority(self, device_id: str) -> int:
        """获取端口优先级（数字越小优先级越高）"""
        try:
            if ':' in device_id:
                port = int(device_id.split(':')[1])
                # MuMu模拟器新规则：16384系列
                if 16384 <= port <= 16500:
                    return 1  # MuMu端口最高优先级
                # 雷电模拟器：5555系列端口
                elif 5555 <= port <= 5585:
                    return 2  # 雷电端口次优先级
                # 其他端口（如7555等错误端口）应该被过滤
                else:
                    return 9  # 其他端口最低优先级，会被过滤
            return 5  # 非端口设备
        except:
            return 5

    def _get_port_key(self, device_id: str) -> str:
        """获取端口的唯一键（用于去重）"""
        try:
            if ':' in device_id:
                port = int(device_id.split(':')[1])

                # MuMu模拟器新规则: 16384, 16416, 16448... (16384 + vm_index * 32)
                # 使用智能检测，支持无限数量的MuMu设备
                if port >= 16384 and (port - 16384) % 32 <= 1:
                    # 标准MuMu端口或被占用后+1的情况
                    vm_index = (port - 16384) // 32
                    return f"mumu_vm{vm_index}"

                # 雷电模拟器端口: 5555, 5557, 5559... (5555 + instance_index * 2)
                elif 5555 <= port <= 5585:
                    # 每个雷电端口都是独立的实例
                    return f"ldplayer_{port}"

                # 其他端口（如7555等错误端口）直接过滤
                else:
                    return f"invalid_{port}"  # 标记为无效端口
            return device_id
        except:
            return device_id
    
    def get_device_for_load_balancing(self) -> Optional[DeviceInfo]:
        """获取负载最轻的设备"""
        healthy_devices = self.get_healthy_devices()
        
        if not healthy_devices:
            return None
        
        # 按连接数排序，选择负载最轻的
        return min(healthy_devices, key=lambda d: d.connection_count)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._connection_lock:
            device_stats = {}
            for device_id, device_info in self._connections.items():
                device_stats[device_id] = {
                    'status': device_info.status.value,
                    'health': device_info.health.value,
                    'connection_count': device_info.connection_count,
                    'success_count': device_info.success_count,
                    'error_count': device_info.error_count,
                    'last_seen': device_info.last_seen
                }
            
            return {
                'global_stats': self._stats.copy(),
                'device_count': len(self._connections),
                'healthy_devices': len(self.get_healthy_devices()),
                'device_stats': device_stats
            }
    
    def shutdown(self):
        """关闭连接池"""
        logger.info("关闭ADB连接池...")
        
        self._health_monitor_running = False
        if self._health_monitor_thread:
            self._health_monitor_thread.join(timeout=5)
        
        self._executor.shutdown(wait=True)
        logger.info("ADB连接池已关闭")


# 全局连接池实例
_global_adb_pool: Optional[AdvancedADBConnectionPool] = None
_pool_lock = threading.Lock()


def get_advanced_adb_pool() -> AdvancedADBConnectionPool:
    """获取全局ADB连接池实例"""
    global _global_adb_pool
    
    with _pool_lock:
        if _global_adb_pool is None:
            _global_adb_pool = AdvancedADBConnectionPool()
            # 初始化ADB路径发现
            _global_adb_pool.discover_adb_paths()
            # 设备发现由 intelligent_adb_connector 负责，不在这里执行

        return _global_adb_pool
