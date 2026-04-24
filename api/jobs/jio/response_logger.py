import json
import logging
from datetime import datetime
from typing import Any

import requests
from requests.structures import CaseInsensitiveDict

class ResponseLogger:
    def __init__(self, logger: logging.Logger):
        # 配置日志
        self.logger = logging
    
    def safe_str(self, value: Any) -> str:
        """安全地将值转换为字符串"""
        try:
            return str(value)
        except Exception:
            return "<无法转换为字符串>"
    
    def safe_dict(self, value: Any) -> dict:
        """安全地将值转换为字典"""
        if isinstance(value, dict):
            return value
        elif isinstance(value, CaseInsensitiveDict):
            return dict(value)
        return {}

    def log_response(self, response: requests.Response) -> None:
        """记录响应的详细信息"""
        try:
            # 基本信息
            self.logger.info("=" * 50)
            self.logger.info(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"请求URL: {self.safe_str(response.url)}")
            self.logger.info(f"请求方法: {self.safe_str(response.request.method)}")
            self.logger.info(f"状态码: {response.status_code}")
            
            # 请求头信息
            self.logger.info("请求头:")
            for key, value in self.safe_dict(response.request.headers).items():
                self.logger.info(f"    {key}: {self.safe_str(value)}")
            
            # 响应头信息
            self.logger.info("响应头:")
            for key, value in self.safe_dict(response.headers).items():
                self.logger.info(f"    {key}: {self.safe_str(value)}")
            
            # 响应体信息
            self.logger.info("响应体:")
            
            # 尝试解析为JSON
            try:
                json_data = response.json()
                self.logger.info("JSON格式响应:")
                self.logger.info(json.dumps(json_data, ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                self.logger.info("非JSON格式响应:")
                # 尝试获取文本内容
                try:
                    text_content = response.text
                    if text_content:
                        if len(text_content) > 1000:
                            self.logger.info(f"{text_content[:1000]}... (内容已截断)")
                        else:
                            self.logger.info(text_content)
                    else:
                        self.logger.info("响应体为空")
                except Exception as e:
                    self.logger.error(f"读取响应体文本失败: {str(e)}")
                
                # 尝试获取二进制内容
                try:
                    content = response.content
                    self.logger.info(f"二进制内容长度: {len(content)} bytes")
                except Exception as e:
                    self.logger.error(f"读取二进制内容失败: {str(e)}")
            
            # 响应编码信息
            self.logger.info(f"响应编码: {self.safe_str(response.encoding)}")
            
            # 耗时信息
            if hasattr(response, 'elapsed'):
                self.logger.info(f"请求耗时: {response.elapsed.total_seconds():.3f} 秒")
            
            # 如果是重定向，记录重定向历史
            if response.history:
                self.logger.info("重定向历史:")
                for hist in response.history:
                    self.logger.info(f"    {hist.status_code} -> {hist.url}")
            
        except Exception as e:
            self.logger.error(f"日志记录过程发生错误: {str(e)}")
        finally:
            self.logger.info("=" * 50)
