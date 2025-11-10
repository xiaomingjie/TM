#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
弹性心跳监控器 - 基于最佳实践的许可证验证系统
结合了Circuit Breaker模式、指数退避、健康检查等现代弹性设计模式
"""

import time
import threading
import logging
import random
import socket
import concurrent.futures
from enum import Enum
from typing import Optional, Callable, Tuple, Dict, Any
from dataclasses import dataclass
from collections import deque
import requests


class CircuitState(Enum):
    """断路器状态"""
    CLOSED = "closed"      # 正常状态
    OPEN = "open"          # 断开状态
    HALF_OPEN = "half_open"  # 半开状态


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """断路器配置"""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 60.0
    half_open_max_calls: int = 1


@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    interval: float = 300.0  # 5分钟
    timeout: float = 10.0
    concurrent_checks: bool = True


class NetworkHealthChecker:
    """网络健康检查器"""
    
    def __init__(self, config: HealthCheckConfig):
        self.config = config
        self.last_check_time = 0
        self.last_result = True
        
    def check_connectivity(self) -> Tuple[bool, float]:
        """检查网络连接性，返回(是否可用, 质量分数)"""
        current_time = time.time()

        # 避免频繁检查
        if current_time - self.last_check_time < self.config.interval:
            logging.debug(f" 跳过网络检查 (距离上次检查 {current_time - self.last_check_time:.1f}秒 < {self.config.interval}秒)")
            return self.last_result, 1.0 if self.last_result else 0.0

        self.last_check_time = current_time
        logging.debug(" 执行增强网络连接性检查...")

        # DNS测试服务器 (只保留稳定的)
        dns_hosts = [
            ("114.114.114.114", 53),  # 114 DNS (国内)
            ("223.5.5.5", 53),        # 阿里DNS (国内)
        ]

        # HTTP测试URL
        http_urls = [
            "http://www.baidu.com",
            "http://www.qq.com",
            "http://www.163.com"
        ]

        # 执行综合网络检测
        return self._enhanced_connectivity_check(dns_hosts, http_urls)
    
    def _concurrent_check(self, hosts) -> Tuple[bool, float]:
        """并发网络检查"""
        successful_checks = 0
        total_checks = len(hosts)

        def test_host(host_port):
            host, port = host_port
            try:
                start_time = time.time()
                socket.create_connection((host, port), timeout=3)
                duration = time.time() - start_time
                logging.debug(f" 网络测试成功: {host}:{port} ({duration*1000:.0f}ms)")
                return True
            except Exception as e:
                logging.debug(f" 网络测试失败: {host}:{port} - {e}")
                return False
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=total_checks) as executor:
                futures = [executor.submit(test_host, host_port) for host_port in hosts]
                
                for future in concurrent.futures.as_completed(futures, timeout=self.config.timeout):
                    try:
                        if future.result():
                            successful_checks += 1
                    except:
                        continue
                        
        except concurrent.futures.TimeoutError:
            logging.warning("网络健康检查超时")
        
        quality_score = successful_checks / total_checks
        is_available = quality_score > 0.5  # 超过一半的检查成功

        logging.debug(f" 并发网络检查完成: {successful_checks}/{total_checks} 成功, 质量分数: {quality_score:.2f}, 网络可用: {is_available}")

        self.last_result = is_available
        return is_available, quality_score
    
    def _sequential_check(self, hosts) -> Tuple[bool, float]:
        """顺序网络检查"""
        for host, port in hosts:
            try:
                start_time = time.time()
                socket.create_connection((host, port), timeout=3)
                duration = time.time() - start_time
                logging.debug(f" 顺序网络测试成功: {host}:{port} ({duration*1000:.0f}ms)")
                self.last_result = True
                return True, 1.0
            except Exception as e:
                logging.debug(f" 顺序网络测试失败: {host}:{port} - {e}")
                continue

        logging.debug(" 所有顺序网络测试均失败")
        self.last_result = False
        return False, 0.0

    def _enhanced_connectivity_check(self, dns_hosts, http_urls) -> Tuple[bool, float]:
        """增强的网络连接检查 - 结合DNS和HTTP测试"""
        dns_score = 0.0
        http_score = 0.0

        # 1. DNS连接测试 (权重60%)
        logging.debug(" 执行DNS连接测试...")
        if self.config.concurrent_checks:
            dns_available, dns_quality = self._concurrent_check(dns_hosts)
        else:
            dns_available, dns_quality = self._sequential_check(dns_hosts)

        dns_score = dns_quality * 0.6
        logging.debug(f" DNS测试结果: 可用={dns_available}, 质量={dns_quality:.2f}, 得分={dns_score:.2f}")

        # 2. HTTP连接测试 (权重40%)
        logging.debug(" 执行HTTP连接测试...")
        http_available, http_quality = self._http_connectivity_check(http_urls)
        http_score = http_quality * 0.4
        logging.debug(f" HTTP测试结果: 可用={http_available}, 质量={http_quality:.2f}, 得分={http_score:.2f}")

        # 3. 综合评估
        total_score = dns_score + http_score
        is_available = total_score > 0.5  # 总分超过0.5认为网络可用

        # 特殊情况：如果DNS完全不可用但HTTP可用，仍认为网络可用
        if not dns_available and http_available and http_quality > 0.7:
            is_available = True
            total_score = max(total_score, 0.6)

        logging.debug(f" 综合网络检查完成: DNS得分={dns_score:.2f}, HTTP得分={http_score:.2f}, "
                     f"总分={total_score:.2f}, 网络可用={is_available}")

        self.last_result = is_available
        return is_available, total_score

    def _http_connectivity_check(self, urls) -> Tuple[bool, float]:
        """HTTP连接检查"""
        successful_checks = 0
        total_checks = len(urls)
        response_times = []

        for url in urls:
            try:
                start_time = time.time()

                # 使用urllib进行HTTP请求
                import urllib.request
                import urllib.error

                # 设置请求头，模拟真实浏览器
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )

                # 执行请求
                with urllib.request.urlopen(req, timeout=5) as response:
                    # 读取少量数据验证连接
                    response.read(1024)

                duration = time.time() - start_time
                response_times.append(duration)
                successful_checks += 1

                logging.debug(f" HTTP测试成功: {url} ({duration*1000:.0f}ms)")

            except urllib.error.HTTPError as e:
                # HTTP错误但连接成功，也算部分成功
                if e.code < 500:  # 4xx错误仍表示网络连通
                    successful_checks += 0.5
                    logging.debug(f" HTTP测试部分成功: {url} (HTTP {e.code})")
                else:
                    logging.debug(f" HTTP测试失败: {url} (HTTP {e.code})")

            except Exception as e:
                logging.debug(f" HTTP测试失败: {url} - {e}")

        # 计算质量分数
        if total_checks == 0:
            return False, 0.0

        quality_score = successful_checks / total_checks
        is_available = quality_score > 0.3  # 30%成功率即认为HTTP可用

        # 响应时间加权
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            # 响应时间越快，质量分数越高
            time_factor = max(0.5, min(1.0, 3.0 / avg_response_time))
            quality_score *= time_factor

        return is_available, min(1.0, quality_score)


class ExponentialBackoff:
    """指数退避实现"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.attempt = 0
    
    def reset(self):
        """重置重试计数"""
        self.attempt = 0
    
    def next_delay(self) -> float:
        """计算下次重试延迟"""
        if self.attempt >= self.config.max_attempts:
            return -1  # 表示不再重试
        
        # 计算基础延迟
        delay = self.config.base_delay * (self.config.exponential_base ** self.attempt)
        delay = min(delay, self.config.max_delay)
        
        # 添加抖动
        if self.config.jitter:
            jitter_range = delay * 0.1  # 10%的抖动
            delay += random.uniform(-jitter_range, jitter_range)
        
        self.attempt += 1
        return max(0, delay)


class CircuitBreaker:
    """断路器实现"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs):
        """通过断路器调用函数"""
        with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time < self.config.timeout:
                    raise Exception("Circuit breaker is OPEN")
                else:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
            
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise Exception("Circuit breaker HALF_OPEN call limit exceeded")
                self.half_open_calls += 1
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """处理成功调用"""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0
    
    def _on_failure(self):
        """处理失败调用"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
    
    def get_state(self) -> CircuitState:
        """获取当前状态"""
        return self.state


class HealthMonitor:
    """健康状态监控器"""
    
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.success_history = deque(maxlen=window_size)
        self.response_times = deque(maxlen=window_size)
        self._lock = threading.Lock()
    
    def record_success(self, response_time: float = 0):
        """记录成功"""
        with self._lock:
            self.success_history.append(True)
            self.response_times.append(response_time)
    
    def record_failure(self):
        """记录失败"""
        with self._lock:
            self.success_history.append(False)
    
    def get_health_status(self) -> HealthStatus:
        """获取健康状态"""
        with self._lock:
            if not self.success_history:
                return HealthStatus.HEALTHY
            
            success_rate = sum(self.success_history) / len(self.success_history)
            
            if success_rate >= 0.9:
                return HealthStatus.HEALTHY
            elif success_rate >= 0.5:
                return HealthStatus.DEGRADED
            else:
                return HealthStatus.UNHEALTHY
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        with self._lock:
            if not self.success_history:
                return {"success_rate": 1.0, "avg_response_time": 0}
            
            success_rate = sum(self.success_history) / len(self.success_history)
            avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
            
            return {
                "success_rate": success_rate,
                "avg_response_time": avg_response_time,
                "total_calls": len(self.success_history)
            }


class ResilientHeartbeatMonitor:
    """弹性心跳监控器 - 主类"""
    
    def __init__(self, 
                 hardware_id: str, 
                 license_key: str,
                 validation_func: Callable,
                 interval: float = 1800.0,  # 30分钟
                 retry_config: Optional[RetryConfig] = None,
                 circuit_config: Optional[CircuitBreakerConfig] = None,
                 health_config: Optional[HealthCheckConfig] = None):
        
        self.hardware_id = hardware_id
        self.license_key = license_key
        self.validation_func = validation_func
        self.base_interval = interval
        self.current_interval = interval
        
        # 配置组件
        self.retry_config = retry_config or RetryConfig()
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        self.health_config = health_config or HealthCheckConfig()
        
        # 核心组件
        self.network_checker = NetworkHealthChecker(self.health_config)
        self.circuit_breaker = CircuitBreaker(self.circuit_config)
        self.health_monitor = HealthMonitor()
        self.backoff = ExponentialBackoff(self.retry_config)
        
        # 运行状态
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_validation_time = 0
        self.offline_start_time = 0
        self.max_offline_time = 7200  # 2小时
        self.startup_time = time.time()  # 记录启动时间
        self.startup_grace_period = 300  # 启动后5分钟宽限期
        self.consecutive_network_failures = 0  # 连续网络失败次数
        self.max_consecutive_failures = 3  # 最大连续失败次数

        # 线程重启机制
        self.thread_restart_count = 0  # 线程重启次数
        self.max_restart_attempts = 3  # 最大重启尝试次数
        self.last_thread_check_time = 0  # 上次线程检查时间
        self.thread_check_interval = 60  # 线程健康检查间隔(秒)
        self.watchdog_thread = None  # 看门狗线程
        
        # 统计信息
        self.total_validations = 0
        self.successful_validations = 0
        
    def start(self):
        """启动心跳监控"""
        if self.running:
            return

        self.running = True
        self.thread_restart_count = 0

        # 启动主心跳线程
        self._start_heartbeat_thread()

        # 启动看门狗线程
        self._start_watchdog_thread()

        logging.info(f" 弹性许可证心跳监控器已启动")
        logging.info(f" 启动宽限期: {self.startup_grace_period}秒, 连续失败阈值: {self.max_consecutive_failures}次")
        logging.info(f" 线程重启机制: 最大重启次数 {self.max_restart_attempts}, 检查间隔 {self.thread_check_interval}秒")

    def _start_heartbeat_thread(self):
        """启动心跳线程"""
        self.thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"HeartbeatMonitor-{self.thread_restart_count}"
        )
        self.thread.start()
        logging.info(f" 心跳线程已启动 (线程ID: {self.thread.ident}, 重启次数: {self.thread_restart_count})")

    def _start_watchdog_thread(self):
        """启动看门狗线程"""
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="HeartbeatWatchdog"
        )
        self.watchdog_thread.start()
        logging.info(f" 看门狗线程已启动 (线程ID: {self.watchdog_thread.ident})")
        
    def stop(self):
        """停止心跳监控"""
        self.running = False

        # 停止主线程
        if self.thread:
            self.thread.join(timeout=5)

        # 停止看门狗线程
        if self.watchdog_thread:
            self.watchdog_thread.join(timeout=3)

        logging.info(" 弹性许可证心跳监控器已停止")

    def _watchdog_loop(self):
        """看门狗循环 - 监控主心跳线程健康状态"""
        logging.info(" 看门狗线程启动，开始监控心跳线程健康状态")

        while self.running:
            try:
                time.sleep(self.thread_check_interval)

                if not self.running:
                    break

                # 检查主心跳线程是否健康
                if not self._is_heartbeat_thread_healthy():
                    logging.warning(" 检测到心跳线程异常，尝试重启...")

                    if self._restart_heartbeat_thread():
                        logging.info(" 心跳线程重启成功")
                    else:
                        logging.error(" 心跳线程重启失败，看门狗停止监控")
                        break
                else:
                    logging.debug(" 心跳线程健康检查通过")

            except Exception as e:
                logging.error(f" 看门狗线程异常: {e}")
                time.sleep(10)  # 异常时等待10秒再继续

        logging.info(" 看门狗线程已停止")

    def _is_heartbeat_thread_healthy(self) -> bool:
        """检查心跳线程是否健康"""
        if not self.thread or not self.thread.is_alive():
            logging.warning(" 心跳线程已停止运行")
            return False

        # 检查线程是否长时间无响应
        current_time = time.time()
        if self.last_validation_time > 0:
            time_since_last_validation = current_time - self.last_validation_time
            max_silent_time = self.current_interval * 2 + 300  # 允许的最大静默时间

            if time_since_last_validation > max_silent_time:
                logging.warning(f" 心跳线程长时间无响应: {time_since_last_validation:.0f}秒 > {max_silent_time:.0f}秒")
                return False

        return True

    def _restart_heartbeat_thread(self) -> bool:
        """重启心跳线程"""
        if self.thread_restart_count >= self.max_restart_attempts:
            logging.error(f" 心跳线程重启次数已达上限 ({self.max_restart_attempts})，停止重启尝试")
            return False

        try:
            # 停止旧线程
            if self.thread and self.thread.is_alive():
                logging.info(" 正在停止旧的心跳线程...")
                # 注意：不能强制停止线程，只能等待其自然结束
                # 这里我们标记为需要重启，让旧线程自己退出

            # 增加重启计数
            self.thread_restart_count += 1

            # 重置一些状态
            self.consecutive_network_failures = 0
            self.offline_start_time = 0

            # 启动新线程
            self._start_heartbeat_thread()

            # 等待新线程启动
            time.sleep(1)

            if self.thread and self.thread.is_alive():
                logging.info(f" 心跳线程重启成功 (第{self.thread_restart_count}次重启)")
                return True
            else:
                logging.error(" 心跳线程重启后仍未正常运行")
                return False

        except Exception as e:
            logging.error(f" 重启心跳线程时发生异常: {e}")
            return False
    
    def _heartbeat_loop(self):
        """主心跳循环"""
        thread_name = threading.current_thread().name
        logging.info(f" 心跳监控线程启动 ({thread_name})，立即进行初始验证...")

        try:
            self._perform_validation()
        except Exception as e:
            logging.error(f"初始验证异常: {e}")
            self.health_monitor.record_failure()

        while self.running:
            try:
                # 检查是否需要退出（支持线程重启）
                if not self.running:
                    break

                # 等待下次检查
                logging.debug(f" 心跳监控等待 {self.current_interval/60:.1f} 分钟后进行下次检查")

                # 分段睡眠，以便及时响应停止信号
                sleep_time = self.current_interval
                sleep_interval = min(30, sleep_time / 10)  # 每次最多睡眠30秒

                while sleep_time > 0 and self.running:
                    actual_sleep = min(sleep_interval, sleep_time)
                    time.sleep(actual_sleep)
                    sleep_time -= actual_sleep

                if not self.running:
                    break

                # 执行验证
                logging.debug(" 心跳监控开始执行定期验证")
                self._perform_validation()

            except Exception as e:
                logging.error(f"心跳循环异常 ({thread_name}): {e}")
                self.health_monitor.record_failure()

                # 异常时短暂休息，避免快速循环
                time.sleep(5)

        logging.info(f" 心跳监控线程退出 ({thread_name})")
    
    def _perform_validation(self):
        """执行许可证验证"""
        start_time = time.time()

        try:
            # 检查网络状态
            logging.debug(" 开始网络连接检查...")
            is_network_available, network_quality = self.network_checker.check_connectivity()
            logging.debug(f" 网络检查结果: 可用={is_network_available}, 质量={network_quality:.2f}")

            if not is_network_available:
                self.consecutive_network_failures += 1
                logging.warning(f" 网络检查失败 (连续失败 {self.consecutive_network_failures}/{self.max_consecutive_failures} 次)")

                if self.consecutive_network_failures >= self.max_consecutive_failures:
                    logging.warning(" 连续网络检查失败次数达到阈值，进入离线处理流程")
                    self._handle_network_unavailable()
                else:
                    logging.info(" 网络检查失败但未达到阈值，继续监控")
                return
            else:
                # 网络恢复，重置失败计数器
                if self.consecutive_network_failures > 0:
                    logging.info(f" 网络已恢复 (之前连续失败 {self.consecutive_network_failures} 次)")
                    self.consecutive_network_failures = 0
                    self.offline_start_time = 0  # 重置离线时间
            
            # 通过断路器执行验证
            result = self.circuit_breaker.call(
                self._validate_with_retry,
                self.hardware_id,
                self.license_key
            )
            
            if result[0]:  # 验证成功
                response_time = time.time() - start_time
                self.health_monitor.record_success(response_time)
                self._handle_validation_success()
            else:
                self.health_monitor.record_failure()
                self._handle_validation_failure(result[1])
                
        except Exception as e:
            self.health_monitor.record_failure()
            self._handle_validation_exception(e)
    
    def _validate_with_retry(self, hardware_id: str, license_key: str) -> Tuple[bool, int, str]:
        """带重试的验证"""
        self.backoff.reset()
        
        while True:
            try:
                self.total_validations += 1
                result = self.validation_func(hardware_id, license_key)
                
                if result[0]:  # 成功
                    self.successful_validations += 1
                    return result
                
                # 失败时检查是否需要重试
                delay = self.backoff.next_delay()
                if delay < 0:  # 不再重试
                    return result
                
                logging.info(f"验证失败，{delay:.1f}秒后重试...")
                time.sleep(delay)
                
            except Exception as e:
                delay = self.backoff.next_delay()
                if delay < 0:
                    raise e
                
                logging.warning(f"验证异常，{delay:.1f}秒后重试: {e}")
                time.sleep(delay)
    
    def _handle_validation_success(self):
        """处理验证成功"""
        self.last_validation_time = time.time()
        self.offline_start_time = 0
        
        # 动态调整间隔
        health_status = self.health_monitor.get_health_status()
        if health_status == HealthStatus.HEALTHY:
            # 健康状态下可以延长间隔
            self.current_interval = min(self.current_interval * 1.1, self.base_interval * 2)
        
        logging.info(f" 许可证验证成功 (下次检查: {self.current_interval/60:.1f}分钟后)")
    
    def _handle_validation_failure(self, status_code: int):
        """处理验证失败"""
        # 缩短检查间隔
        self.current_interval = max(self.current_interval * 0.8, self.base_interval * 0.5)
        
        logging.warning(f" 许可证验证失败 (状态码: {status_code})")
        
        # 检查是否需要退出
        health_status = self.health_monitor.get_health_status()
        if health_status == HealthStatus.UNHEALTHY:
            self._force_exit("许可证验证持续失败")
    
    def _handle_validation_exception(self, exception: Exception):
        """处理验证异常"""
        logging.error(f" 许可证验证异常: {exception}")
        
        # 检查断路器状态
        if self.circuit_breaker.get_state() == CircuitState.OPEN:
            self._handle_circuit_open()
    
    def _handle_network_unavailable(self):
        """处理网络不可用"""
        current_time = time.time()

        # 检查是否在启动宽限期内
        if current_time - self.startup_time < self.startup_grace_period:
            logging.info(f" 启动宽限期内网络检查失败，剩余宽限时间: {self.startup_grace_period - (current_time - self.startup_time):.0f}秒")
            return

        if self.offline_start_time == 0:
            self.offline_start_time = current_time
            logging.warning(" 网络不可用，进入离线模式")

        offline_duration = current_time - self.offline_start_time
        
        if offline_duration > self.max_offline_time:
            self._force_exit("网络离线时间过长")
        else:
            remaining_time = self.max_offline_time - offline_duration
            logging.info(f" 离线模式: 剩余时间 {remaining_time/3600:.1f} 小时")
            
            # 离线时延长检查间隔
            self.current_interval = min(self.current_interval * 1.5, 1800)
    
    def _handle_circuit_open(self):
        """处理断路器打开"""
        logging.warning("⚡ 断路器已打开，暂停验证请求")
        
        # 断路器打开时大幅延长间隔
        self.current_interval = self.base_interval * 2
    
    def _force_exit(self, reason: str):
        """强制退出程序"""
        logging.critical(f" {reason}，程序将退出")
        
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(None, "许可证验证失败", 
                               f"{reason}\n程序将退出。\n请检查网络连接和许可证有效性。")
        except:
            pass
        
        import os
        os._exit(1)
    
    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        metrics = self.health_monitor.get_metrics()

        return {
            "health_status": self.health_monitor.get_health_status().value,
            "circuit_state": self.circuit_breaker.get_state().value,
            "current_interval": self.current_interval,
            "last_validation": self.last_validation_time,
            "total_validations": self.total_validations,
            "success_rate": metrics["success_rate"],
            "avg_response_time": metrics["avg_response_time"],
            "offline_duration": time.time() - self.offline_start_time if self.offline_start_time > 0 else 0,
            "thread_alive": self.thread.is_alive() if self.thread else False,
            "thread_id": self.thread.ident if self.thread else None,
            "thread_name": self.thread.name if self.thread else None,
            "watchdog_alive": self.watchdog_thread.is_alive() if self.watchdog_thread else False,
            "watchdog_id": self.watchdog_thread.ident if self.watchdog_thread else None,
            "consecutive_failures": self.consecutive_network_failures,
            "startup_grace_remaining": max(0, self.startup_grace_period - (time.time() - self.startup_time)),
            "thread_restart_count": self.thread_restart_count,
            "max_restart_attempts": self.max_restart_attempts,
            "thread_health_status": "healthy" if self._is_heartbeat_thread_healthy() else "unhealthy"
        }

    def is_thread_healthy(self) -> bool:
        """检查心跳线程是否健康"""
        return self.running and self.thread and self.thread.is_alive() and self._is_heartbeat_thread_healthy()
