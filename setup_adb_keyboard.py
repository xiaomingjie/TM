#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
先进的ADBKeyboard安装和配置脚本
使用企业级ADB连接池管理，支持自动重连、健康监控、负载均衡
"""

import sys
import os
import subprocess
import logging
import requests
import asyncio
import time
from typing import Optional, List, Dict, Tuple
from concurrent.futures import Future, as_completed

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class AdvancedADBKeyboardSetup:
    """先进的ADBKeyboard安装配置器"""

    def __init__(self):
        self.apk_path = "ADBKeyboard.apk"
        self.adb_pool = None
        self.setup_results = {}

    def initialize_adb_pool(self) -> bool:
        """初始化先进的ADB连接池（使用新的职责分工架构）"""
        try:
            # 1. 使用 intelligent_adb_connector 发现设备
            from utils.intelligent_adb_connector import IntelligentADBConnector
            from utils.advanced_adb_manager import get_advanced_adb_pool

            connector = IntelligentADBConnector()
            device_list = connector.discover_device_list()

            if not device_list:
                logger.warning("⚠️ 未发现任何设备")
                return False

            logger.info(f"📱 发现 {len(device_list)} 个设备: {device_list}")

            # 2. 使用 advanced_adb_manager 创建设备连接池
            self.adb_pool = get_advanced_adb_pool()
            devices = self.adb_pool.create_devices_from_list(device_list)

            # 等待连接池稳定
            time.sleep(2)

            healthy_devices = self.adb_pool.get_healthy_devices()
            if healthy_devices:
                logger.info(f"✅ ADB连接池初始化成功，发现 {len(healthy_devices)} 个健康设备")

                # 智能匹配设备和窗口
                matched_devices = self._match_devices_to_windows(healthy_devices)
                logger.info(f"🎯 智能匹配结果: {len(matched_devices)} 个设备匹配到窗口")

                for device in matched_devices:
                    logger.info(f"  设备: {device.device_id} (健康度: {device.health.value})")

                # 如果匹配的设备数量合理，使用匹配结果
                if matched_devices and len(matched_devices) <= len(healthy_devices):
                    self._matched_devices = matched_devices
                    logger.info(f"✅ 使用智能匹配的 {len(matched_devices)} 个设备")
                else:
                    self._matched_devices = healthy_devices
                    logger.info(f"⚠️ 智能匹配异常，使用全部 {len(healthy_devices)} 个设备")

                return True
            else:
                logger.warning("⚠️ 设备发现成功，但连接池中无健康设备")
                return False

        except Exception as e:
            logger.error(f"❌ ADB连接池初始化失败: {e}")
            return False

    def _attempt_intelligent_connections(self):
        """使用智能动态方法发现并连接模拟器设备"""
        logger.info("🧠 使用智能连接器动态发现模拟器设备...")

        try:
            from utils.intelligent_adb_connector import IntelligentADBConnector

            # 创建智能连接器
            connector = IntelligentADBConnector()

            # 发现ADB路径
            adb_paths = connector.discover_adb_paths()
            logger.info(f"📍 发现ADB路径: {list(adb_paths.keys())}")

            # 发现模拟器窗口
            windows = connector.discover_emulator_windows()
            logger.info(f"🖥️ 发现模拟器窗口: {len(windows)} 个")

            # 动态发现活跃端口
            active_ports = connector.discover_active_ports()
            logger.info(f"🔌 发现活跃端口: {sorted(active_ports)}")

            # 智能连接所有设备
            connections = connector.connect_all_devices()
            logger.info(f"✅ 智能连接成功: {len(connections)} 个设备")

            # 将连接结果同步到ADB连接池
            if connections:
                logger.info("🔄 同步连接结果到ADB连接池...")

                # 触发连接池重新发现设备
                self.adb_pool._discover_devices()

                # 等待一下让连接池更新
                import time
                time.sleep(2)

                # 检查更新后的健康设备
                healthy_devices = self.adb_pool.get_healthy_devices()
                logger.info(f"🎯 连接池更新后的健康设备: {len(healthy_devices)} 个")

                return len(healthy_devices) > 0
            else:
                logger.warning("⚠️ 智能连接器未发现任何设备连接")
                return False

        except Exception as e:
            logger.error(f"❌ 智能连接失败: {e}")

            # 回退到简单的端口扫描（但使用动态发现的端口）
            logger.info("🔄 回退到动态端口扫描...")
            return self._fallback_dynamic_scan()

    def _fallback_dynamic_scan(self):
        """回退方案：动态扫描活跃端口"""
        try:
            import psutil

            # 动态发现活跃的ADB端口
            active_ports = set()
            connections = psutil.net_connections(kind='inet')

            for conn in connections:
                if (conn.laddr and conn.laddr.ip == '127.0.0.1' and
                    conn.status == psutil.CONN_LISTEN):
                    port = conn.laddr.port

                    # 检查是否是ADB相关端口
                    if self._is_likely_adb_port(port):
                        active_ports.add(port)

            logger.info(f"🔍 动态发现的可能ADB端口: {sorted(active_ports)}")

            if not active_ports:
                logger.warning("⚠️ 未发现任何活跃的ADB端口")
                return False

            # 尝试连接发现的端口
            connected_count = 0
            for port in active_ports:
                if self._try_connect_port(port):
                    connected_count += 1

            logger.info(f"✅ 动态扫描连接成功: {connected_count} 个端口")
            return connected_count > 0

        except Exception as e:
            logger.error(f"❌ 动态端口扫描失败: {e}")
            return False

    def _is_likely_adb_port(self, port: int) -> bool:
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

    def _try_connect_port(self, port: int) -> bool:
        """尝试连接指定端口"""
        address = f"127.0.0.1:{port}"

        try:
            from utils.advanced_adb_manager import ADBCommand

            # 使用ADBCommand连接
            connect_cmd = ADBCommand(['connect', address], timeout=5.0)
            success, stdout, stderr = self.adb_pool.execute_command_sync(connect_cmd)

            if success and 'connected' in stdout.lower():
                logger.info(f"✅ 成功连接: {address}")
                return True
            else:
                logger.debug(f"连接失败: {address} - {stderr}")
                return False

        except Exception as e:
            logger.debug(f"连接端口 {port} 异常: {e}")
            return False

    def get_healthy_devices(self) -> List:
        """获取健康的设备列表"""
        if hasattr(self, '_matched_devices') and self._matched_devices:
            return self._matched_devices
        elif self.adb_pool:
            return self.adb_pool.get_healthy_devices()
        return []

    def _match_devices_to_windows(self, healthy_devices):
        """智能匹配设备到窗口，避免设备数量过多"""
        try:
            from utils.intelligent_adb_connector import IntelligentADBConnector

            # 获取模拟器窗口信息
            connector = IntelligentADBConnector()
            connector.discover_adb_paths()
            windows = connector.discover_emulator_windows()

            logger.info(f"🖥️ 发现 {len(windows)} 个模拟器窗口")

            if not windows:
                logger.warning("⚠️ 未发现模拟器窗口，使用所有健康设备")
                return healthy_devices

            # 如果设备数量与窗口数量接近，直接使用
            if len(healthy_devices) <= len(windows) + 2:  # 允许2个额外设备
                logger.info(f"✅ 设备数量合理 ({len(healthy_devices)} 设备 vs {len(windows)} 窗口)")
                return healthy_devices

            # 设备数量过多，进行智能筛选
            logger.info(f"⚠️ 设备数量过多 ({len(healthy_devices)} 设备 vs {len(windows)} 窗口)，进行智能筛选")

            # 优先选择常见端口的设备
            priority_ports = [7555, 5555, 16384]  # MuMu常用端口
            matched_devices = []
            used_ports = set()

            # 1. 优先匹配常见端口
            for device in healthy_devices:
                if ':' in device.device_id:
                    try:
                        port = int(device.device_id.split(':')[1])
                        if port in priority_ports and port not in used_ports:
                            matched_devices.append(device)
                            used_ports.add(port)
                            logger.debug(f"优先匹配设备: {device.device_id}")
                    except ValueError:
                        pass

            # 2. 如果还需要更多设备，按端口顺序添加
            remaining_needed = len(windows) - len(matched_devices)
            if remaining_needed > 0:
                for device in healthy_devices:
                    if device not in matched_devices and len(matched_devices) < len(windows):
                        matched_devices.append(device)
                        if ':' in device.device_id:
                            try:
                                port = int(device.device_id.split(':')[1])
                                logger.debug(f"补充匹配设备: {device.device_id}")
                            except ValueError:
                                pass

            logger.info(f"🎯 智能筛选完成: {len(matched_devices)} 个设备")
            return matched_devices

        except Exception as e:
            logger.error(f"❌ 智能匹配失败: {e}")
            # 回退到简单截取
            target_count = min(len(healthy_devices), 10)  # 最多10个设备
            return healthy_devices[:target_count]

    def download_adb_keyboard(self) -> bool:
        """下载ADBKeyboard APK"""
        if os.path.exists(self.apk_path):
            logger.info(f"✅ ADBKeyboard APK已存在: {self.apk_path}")
            return True

        # GitHub下载链接
        download_urls = [
            "https://github.com/senzhk/ADBKeyBoard/releases/download/v2.0/ADBKeyboard.apk",
            "https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyboard.apk"
        ]

        logger.info("📥 开始下载ADBKeyboard APK...")

        for i, url in enumerate(download_urls, 1):
            try:
                logger.info(f"🔗 尝试下载链接 {i}/{len(download_urls)}: {url}")

                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))

                with open(self.apk_path, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                logger.info(f"📥 下载进度: {progress:.1f}% ({downloaded}/{total_size} bytes)")

                logger.info(f"✅ ADBKeyboard下载成功: {self.apk_path}")
                return True

            except Exception as e:
                logger.warning(f"⚠️ 下载链接 {i} 失败: {e}")
                if os.path.exists(self.apk_path):
                    os.remove(self.apk_path)  # 清理不完整的文件
                continue

        logger.error("❌ 所有下载链接都失败")
        logger.info("💡 手动下载地址: https://github.com/senzhk/ADBKeyBoard/releases")
        return False
    
    def download_adb_keyboard(self) -> bool:
        """下载ADBKeyboard APK"""
        if os.path.exists(self.apk_path):
            logger.info(f"ADBKeyboard APK已存在: {self.apk_path}")
            return True
        
        # GitHub下载链接
        download_urls = [
            "https://github.com/senzhk/ADBKeyBoard/releases/download/v2.0/ADBKeyboard.apk",
            "https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyboard.apk"
        ]
        
        for url in download_urls:
            try:
                logger.info(f"尝试从 {url} 下载ADBKeyboard...")
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                with open(self.apk_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"ADBKeyboard下载成功: {self.apk_path}")
                return True
                
            except Exception as e:
                logger.warning(f"从 {url} 下载失败: {e}")
                continue
        
        logger.error("所有下载链接都失败，请手动下载ADBKeyboard.apk")
        logger.info("手动下载地址: https://github.com/senzhk/ADBKeyBoard/releases")
        return False
    
    def install_adb_keyboard_async(self, device_id: str) -> Future:
        """异步安装ADBKeyboard"""
        from utils.advanced_adb_manager import ADBCommand

        command = ADBCommand(
            command=['install', '-r', self.apk_path],
            device_id=device_id,
            timeout=60.0,
            priority=1,  # 高优先级
            retry_count=2,
            callback=self._install_callback
        )

        logger.info(f"📦 异步安装ADBKeyboard: {device_id}")
        return self.adb_pool.execute_command_async(command)

    def _install_callback(self, success: bool, stdout: str, stderr: str):
        """安装回调函数"""
        if success:
            logger.info("✅ ADBKeyboard安装成功")
        else:
            logger.error(f"❌ ADBKeyboard安装失败: {stderr}")

    def install_adb_keyboard_sync(self, device_id: str) -> bool:
        """同步安装ADBKeyboard"""
        from utils.advanced_adb_manager import ADBCommand

        command = ADBCommand(
            command=['install', '-r', self.apk_path],
            device_id=device_id,
            timeout=60.0,
            retry_count=2
        )

        logger.info(f"📦 安装ADBKeyboard: {device_id}")
        success, stdout, stderr = self.adb_pool.execute_command_sync(command)

        if success:
            logger.info(f"✅ ADBKeyboard安装成功: {device_id}")
            return True
        else:
            logger.error(f"❌ ADBKeyboard安装失败 {device_id}: {stderr}")
            return False
    
    def configure_adb_keyboard(self, device_id: str) -> bool:
        """配置ADBKeyboard"""
        from utils.advanced_adb_manager import ADBCommand

        logger.info(f"⚙️ 配置ADBKeyboard: {device_id}")

        # 1. 启用ADBKeyboard输入法
        enable_command = ADBCommand(
            command=['shell', 'ime', 'enable', 'com.android.adbkeyboard/.AdbIME'],
            device_id=device_id,
            timeout=10.0,
            retry_count=2
        )

        success1, _, stderr1 = self.adb_pool.execute_command_sync(enable_command)
        if not success1:
            logger.warning(f"⚠️ 启用ADBKeyboard失败: {stderr1}")

        # 2. 设置为默认输入法
        set_command = ADBCommand(
            command=['shell', 'ime', 'set', 'com.android.adbkeyboard/.AdbIME'],
            device_id=device_id,
            timeout=10.0,
            retry_count=2
        )

        success2, _, stderr2 = self.adb_pool.execute_command_sync(set_command)

        if success2:
            logger.info(f"✅ ADBKeyboard配置成功: {device_id}")
            return True
        else:
            logger.error(f"❌ 设置默认输入法失败 {device_id}: {stderr2}")
            return False
    
    def test_chinese_input(self, device_id: str) -> bool:
        """测试中文输入功能"""
        from utils.advanced_adb_manager import ADBCommand

        logger.info(f"🧪 测试中文输入功能: {device_id}")

        test_text = "测试中文输入功能ADB连接池"
        test_command = ADBCommand(
            command=['shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', test_text],
            device_id=device_id,
            timeout=10.0,
            retry_count=2
        )

        success, _, stderr = self.adb_pool.execute_command_sync(test_command)

        if success:
            logger.info(f"✅ 中文输入测试成功: {device_id}")
            return True
        else:
            logger.error(f"❌ 中文输入测试失败 {device_id}: {stderr}")
            return False

    def check_installation(self, device_id: str) -> bool:
        """检查ADBKeyboard是否已安装"""
        from utils.advanced_adb_manager import ADBCommand

        check_command = ADBCommand(
            command=['shell', 'pm', 'list', 'packages', 'com.android.adbkeyboard'],
            device_id=device_id,
            timeout=10.0,
            retry_count=1
        )

        success, stdout, _ = self.adb_pool.execute_command_sync(check_command)

        installed = success and 'com.android.adbkeyboard' in stdout

        if installed:
            logger.info(f"✅ ADBKeyboard已安装: {device_id}")
        else:
            logger.info(f"⚪ ADBKeyboard未安装: {device_id}")

        return installed
    
    def setup_all_devices_concurrent(self) -> bool:
        """并发为所有设备安装和配置ADBKeyboard"""
        healthy_devices = self.get_healthy_devices()

        if not healthy_devices:
            logger.error("❌ 没有健康的设备可用")
            return False

        logger.info(f"🚀 开始并发处理 {len(healthy_devices)} 个设备")

        # 并发安装
        install_futures = {}
        for device in healthy_devices:
            device_id = device.device_id

            # 检查是否已安装
            if self.check_installation(device_id):
                logger.info(f"⏭️ ADBKeyboard已安装，跳过安装: {device_id}")
                self.setup_results[device_id] = {'installed': True, 'skipped': True}
            else:
                # 异步安装
                future = self.install_adb_keyboard_async(device_id)
                install_futures[future] = device_id

        # 等待安装完成
        install_success = {}
        for future in as_completed(install_futures, timeout=120):
            device_id = install_futures[future]
            try:
                success, _, stderr = future.result()
                install_success[device_id] = success

                if success:
                    logger.info(f"✅ 安装完成: {device_id}")
                else:
                    logger.error(f"❌ 安装失败: {device_id} - {stderr}")

            except Exception as e:
                logger.error(f"❌ 安装异常: {device_id} - {e}")
                install_success[device_id] = False

        # 配置和测试
        success_count = 0
        for device in healthy_devices:
            device_id = device.device_id

            logger.info(f"\n=== 配置设备: {device_id} ===")

            # 检查安装状态
            if device_id in self.setup_results and self.setup_results[device_id].get('skipped'):
                installed = True
            else:
                installed = install_success.get(device_id, False)

            if installed:
                # 配置ADBKeyboard
                if self.configure_adb_keyboard(device_id):
                    # 测试中文输入
                    if self.test_chinese_input(device_id):
                        success_count += 1
                        self.setup_results[device_id] = {
                            'installed': True,
                            'configured': True,
                            'tested': True,
                            'success': True
                        }
                        logger.info(f"🎉 设备配置完成: {device_id}")
                    else:
                        logger.warning(f"⚠️ 中文输入测试失败: {device_id}")
                        self.setup_results[device_id] = {
                            'installed': True,
                            'configured': True,
                            'tested': False,
                            'success': False
                        }
                else:
                    logger.warning(f"⚠️ 配置失败: {device_id}")
                    self.setup_results[device_id] = {
                        'installed': True,
                        'configured': False,
                        'tested': False,
                        'success': False
                    }
            else:
                logger.warning(f"⚠️ 安装失败，跳过配置: {device_id}")
                self.setup_results[device_id] = {
                    'installed': False,
                    'configured': False,
                    'tested': False,
                    'success': False
                }

        # 显示统计信息
        self._show_setup_statistics(success_count, len(healthy_devices))

        return success_count > 0

    def _show_setup_statistics(self, success_count: int, total_count: int):
        """显示安装统计信息"""
        logger.info(f"\n{'='*60}")
        logger.info("📊 ADBKeyboard安装配置统计")
        logger.info(f"{'='*60}")
        logger.info(f"总设备数: {total_count}")
        logger.info(f"成功配置: {success_count}")
        logger.info(f"成功率: {(success_count/total_count)*100:.1f}%")

        # 显示ADB连接池统计
        if self.adb_pool:
            stats = self.adb_pool.get_statistics()
            logger.info(f"\n🔗 ADB连接池统计:")
            logger.info(f"  总命令数: {stats['global_stats']['total_commands']}")
            logger.info(f"  成功命令: {stats['global_stats']['successful_commands']}")
            logger.info(f"  失败命令: {stats['global_stats']['failed_commands']}")
            logger.info(f"  重连次数: {stats['global_stats']['reconnections']}")
            logger.info(f"  健康设备: {stats['healthy_devices']}/{stats['device_count']}")

        logger.info(f"{'='*60}")

def main():
    """主函数 - 使用先进的ADB连接管理"""
    logger.info("🚀 开始先进的ADBKeyboard安装和配置")
    logger.info("=" * 60)

    setup = AdvancedADBKeyboardSetup()

    try:
        # 1. 初始化先进的ADB连接池
        logger.info("📡 初始化ADB连接池...")
        if not setup.initialize_adb_pool():
            logger.error("❌ ADB连接池初始化失败，请确保模拟器正在运行")
            logger.info("💡 提示:")
            logger.info("  - 确保模拟器已启动")
            logger.info("  - 确保ADB调试已开启")
            logger.info("  - 尝试手动执行 'adb devices' 检查连接")
            return

        # 2. 下载ADBKeyboard APK
        logger.info("📦 检查ADBKeyboard APK...")
        if not setup.download_adb_keyboard():
            if not os.path.exists(setup.apk_path):
                logger.error("❌ ADBKeyboard APK不存在且下载失败")
                logger.info("💡 请手动下载: https://github.com/senzhk/ADBKeyBoard/releases")
                return

        # 3. 并发安装和配置所有设备
        logger.info("⚡ 开始并发安装配置...")
        if setup.setup_all_devices_concurrent():
            logger.info("\n🎉 ADBKeyboard安装配置成功！")
            logger.info("✨ 现在可以使用高性能中文输入功能了")

            # 显示使用提示
            logger.info("\n📝 使用方法:")
            logger.info("  在Python代码中使用:")
            logger.info("  from utils.advanced_adb_manager import get_advanced_adb_pool, ADBCommand")
            logger.info("  pool = get_advanced_adb_pool()")
            logger.info("  cmd = ADBCommand(['shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', '中文文本'], device_id)")
            logger.info("  success, stdout, stderr = pool.execute_command_sync(cmd)")

        else:
            logger.error("❌ ADBKeyboard安装配置失败")
            logger.info("💡 请检查设备连接状态和ADB权限")

    except KeyboardInterrupt:
        logger.info("\n⏹️ 用户中断安装过程")
    except Exception as e:
        logger.error(f"❌ 安装过程异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 显示最终统计
        if setup.adb_pool:
            stats = setup.adb_pool.get_statistics()
            logger.info(f"\n📊 最终统计: 执行了 {stats['global_stats']['total_commands']} 个ADB命令")

        logger.info("🏁 安装程序结束")

if __name__ == "__main__":
    main()
