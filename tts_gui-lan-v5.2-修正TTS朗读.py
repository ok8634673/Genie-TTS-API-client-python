import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import uuid
import json
import threading
import os
import tempfile
import configparser
import wave
import pyaudio
import hashlib
import re
from datetime import datetime
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import pydantic
from typing import Optional, Dict, Any, List
import asyncio
import webbrowser
import io
import time
from pathlib import Path
from random import randint

class TTSClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("TTS API 客户端 - 中转服务器")
        self.root.geometry("800x600")
        # 禁用Tk默认的系统提示音（bell），避免点击按钮时发出提示音
        try:
            self.root.bell = lambda *a, **k: None
        except Exception:
            pass
        
        # 配置文件
        self.config_file = "tts_client_config.ini"
        self.config = configparser.ConfigParser()
        
        # 加载配置
        self.load_config()
        
        # API配置 - 使用配置中的值或默认值
        # 上游真实TTS API（前置API）
        self.upstream_api_url = self.config.get('API', 'upstream_api_url', fallback=self.config.get('API', 'base_url', fallback="http://127.0.0.1:8000"))
        
        # 中转服务模式开关
        self.proxy_mode = self.config.getboolean('API', 'proxy_mode', fallback=False)
        
        # 缓存目录配置
        self.cache_dir = self.config.get('Cache', 'cache_dir', fallback="./audio_cache")
        
        # 本地API服务配置
        self.local_api_host = self.config.get('LocalAPI', 'host', fallback="0.0.0.0")
        self.local_api_port = int(self.config.get('LocalAPI', 'port', fallback=8001))
        self.local_api_enabled = self.config.getboolean('LocalAPI', 'enabled', fallback=False)
        # 中转轮询配置（尝试次数，间隔由代码固定为0.5s）
        self.proxy_poll_attempts = int(self.config.get('API', 'proxy_poll_attempts', fallback=600))
        # 主客户端中转地址（用于客户端互联）
        self.master_api_url = self.config.get('Network', 'master_api_url', fallback='')
        self.connect_master = self.config.getboolean('Network', 'connect_master', fallback=False)
        # 客户端唯一ID，用于在主客户端注册
        self.client_id = self.config.get('Network', 'client_id', fallback='')
        if not self.client_id:
            self.client_id = f"client_{uuid.uuid4().hex[:8]}"
            try:
                self.update_config('Network', 'client_id', self.client_id)
            except Exception:
                pass
        
        # 确保缓存目录存在
        self.ensure_cache_dir()
        
        # PyAudio实例
        self.p = pyaudio.PyAudio()
        
        # FastAPI应用实例
        self.fastapi_app = None
        self.server_thread = None
        self.server_running = False
        
        # 音频文件映射表，用于跟踪生成的音频文件
        self.audio_file_map: Dict[str, Dict[str, Any]] = {}
        
        # 客户端任务追踪
        self.client_tasks: Dict[str, Dict[str, Any]] = {}
        
        # 创建主框架
        self.create_widgets()
        
        # 如果配置启用，自动启动本地API服务
        if self.local_api_enabled:
            self.root.after(1000, self.start_local_api)
        
    def ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
                print(f"创建缓存目录: {self.cache_dir}")
            except Exception as e:
                print(f"创建缓存目录失败: {e}")
                # 如果创建失败，使用临时目录
                self.cache_dir = tempfile.gettempdir()
                print(f"使用临时目录: {self.cache_dir}")
        
    def load_config(self):
        """加载用户配置"""
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file)
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                # 创建默认配置
                self.create_default_config()
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """创建默认配置"""
        self.config['API'] = {
            'base_url': 'http://127.0.0.1:8000',
            'proxy_mode': 'False'
        }
        self.config['Cache'] = {'cache_dir': './audio_cache'}
        self.config['LocalAPI'] = {
            'host': '0.0.0.0',
            'port': '8001',
            'enabled': 'False'
        }
        self.config['Recent'] = {}
        self.save_config()
    
    def save_config(self):
        """保存用户配置"""
        try:
            with open(self.config_file, 'w') as configfile:
                self.config.write(configfile)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def update_config(self, section, key, value):
        """更新配置项"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)
        self.save_config()
    
    def create_widgets(self):
        # 创建标签页
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 角色管理标签页
        self.character_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.character_frame, text="角色管理")
        
        # 参考音频标签页
        self.reference_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.reference_frame, text="参考音频")
        
        # TTS标签页
        self.tts_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tts_frame, text="文本转语音")
        
        # 工具标签页
        self.tools_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tools_frame, text="工具")
        
        # 本地API服务标签页
        self.local_api_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.local_api_frame, text="本地API服务")
        
        # 填充各标签页内容
        self.setup_character_tab()
        self.setup_reference_tab()
        self.setup_tts_tab()
        self.setup_tools_tab()
        self.setup_local_api_tab()
        
        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief='sunken')
        status_bar.pack(side='bottom', fill='x')
        
        # 加载最近使用的值
        self.load_recent_values()
    
    def setup_character_tab(self):
        # 加载角色部分
        load_frame = ttk.LabelFrame(self.character_frame, text="加载角色", padding=10)
        load_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(load_frame, text="角色名称:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.character_name_entry = ttk.Entry(load_frame, width=30)
        self.character_name_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(load_frame, text="模型目录:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.model_dir_entry = ttk.Entry(load_frame, width=25)
        self.model_dir_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Button(load_frame, text="浏览...", command=self.browse_model_dir).grid(row=1, column=2, padx=5, pady=5)
        ttk.Button(load_frame, text="加载角色", command=self.load_character).grid(row=2, column=1, padx=5, pady=10, sticky='e')
        
        # 卸载角色部分
        unload_frame = ttk.LabelFrame(self.character_frame, text="卸载角色", padding=10)
        unload_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(unload_frame, text="角色名称:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.unload_character_entry = ttk.Entry(unload_frame, width=30)
        self.unload_character_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Button(unload_frame, text="卸载角色", command=self.unload_character).grid(row=0, column=2, padx=5, pady=5)
    
    def setup_reference_tab(self):
        # 设置参考音频部分
        reference_frame = ttk.LabelFrame(self.reference_frame, text="设置参考音频", padding=10)
        reference_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(reference_frame, text="角色名称:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.ref_character_entry = ttk.Entry(reference_frame, width=30)
        self.ref_character_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky='we')
        
        ttk.Label(reference_frame, text="音频文件:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.audio_path_entry = ttk.Entry(reference_frame, width=25)
        self.audio_path_entry.grid(row=1, column=1, padx=5, pady=5, sticky='we')
        
        ttk.Button(reference_frame, text="浏览...", command=self.browse_audio_file).grid(row=1, column=2, padx=5, pady=5)
        
        ttk.Label(reference_frame, text="音频文本:").grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.audio_text_entry = ttk.Entry(reference_frame, width=30)
        self.audio_text_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky='we')
        
        # 添加保存参考音频配置的按钮
        config_frame = ttk.Frame(reference_frame)
        config_frame.grid(row=3, column=1, columnspan=2, sticky='e', padx=5, pady=5)
        
        ttk.Button(config_frame, text="保存配置", command=self.save_reference_config).pack(side='left', padx=5)
        ttk.Button(config_frame, text="设置参考音频", command=self.set_reference_audio).pack(side='left', padx=5)
    
    def setup_tts_tab(self):
        # TTS输入部分
        input_frame = ttk.LabelFrame(self.tts_frame, text="文本转语音", padding=10)
        input_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(input_frame, text="角色名称:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.tts_character_entry = ttk.Entry(input_frame, width=30)
        self.tts_character_entry.grid(row=0, column=1, padx=5, pady=5, sticky='we')
        
        ttk.Label(input_frame, text="要转换的文本:").grid(row=1, column=0, sticky='nw', padx=5, pady=5)
        self.tts_text = tk.Text(input_frame, width=50, height=8)
        self.tts_text.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky='we')
        
        # 选项框架
        options_frame = ttk.Frame(input_frame)
        options_frame.grid(row=2, column=1, columnspan=2, sticky='w', padx=5, pady=5)
        
        self.split_sentence_var = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="分割句子", variable=self.split_sentence_var).pack(side='left', padx=5)
        
        ttk.Label(options_frame, text="保存路径:").pack(side='left', padx=(20,5))
        self.save_path_entry = ttk.Entry(options_frame, width=25)
        self.save_path_entry.pack(side='left', padx=5)
        ttk.Button(options_frame, text="浏览...", command=self.browse_save_path).pack(side='left', padx=5)
        
        # 按钮框架
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=3, column=1, columnspan=2, sticky='e', padx=5, pady=10)
        
        ttk.Button(button_frame, text="停止", command=self.stop_tts).pack(side='left', padx=5)
        ttk.Button(button_frame, text="开始TTS", command=self.start_tts).pack(side='left', padx=5)
        ttk.Button(button_frame, text="朗读文本", command=self.speak_text).pack(side='left', padx=5)
        
        # 添加音频控制
        audio_frame = ttk.Frame(input_frame)
        audio_frame.grid(row=4, column=1, columnspan=2, sticky='w', padx=5, pady=5)
        
        self.audio_playing = False
        ttk.Button(audio_frame, text="停止播放", command=self.stop_audio).pack(side='left', padx=5)
    
    def setup_tools_tab(self):
        # 工具按钮
        tools_frame = ttk.Frame(self.tools_frame)
        tools_frame.pack(expand=True, padx=10, pady=10)
        
        ttk.Button(tools_frame, text="清除参考音频缓存", command=self.clear_reference_cache, 
                  width=20).pack(pady=10)
        
        ttk.Button(tools_frame, text="测试连接", command=self.test_connection, 
                  width=20).pack(pady=10)
        
        # 添加API URL配置
        config_frame = ttk.LabelFrame(self.tools_frame, text="API配置", padding=10)
        config_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(config_frame, text="上游 API 地址:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.api_url_entry = ttk.Entry(config_frame, width=30)
        self.api_url_entry.insert(0, self.upstream_api_url)
        self.api_url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='we')
        
        ttk.Button(config_frame, text="更新", command=self.update_api_url).grid(row=0, column=2, padx=5, pady=5)
        
        # （中转服务模式与主客户端互联控件已移动到“本地API服务”选项卡）
        
        # 添加缓存目录配置
        cache_frame = ttk.LabelFrame(self.tools_frame, text="缓存目录配置", padding=10)
        cache_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(cache_frame, text="缓存目录:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.cache_dir_entry = ttk.Entry(cache_frame, width=30)
        self.cache_dir_entry.insert(0, self.cache_dir)
        self.cache_dir_entry.grid(row=0, column=1, padx=5, pady=5, sticky='we')
        
        ttk.Button(cache_frame, text="浏览...", command=self.browse_cache_dir).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(cache_frame, text="更新", command=self.update_cache_dir).grid(row=0, column=3, padx=5, pady=5)
        
        # 添加配置管理
        config_manage_frame = ttk.LabelFrame(self.tools_frame, text="配置管理", padding=10)
        config_manage_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(config_manage_frame, text="保存当前配置", command=self.save_current_config,
                  width=20).pack(pady=5)
        
        ttk.Button(config_manage_frame, text="清除历史记录", command=self.clear_history,
                  width=20).pack(pady=5)
        
        ttk.Button(config_manage_frame, text="打开缓存目录", command=self.open_cache_dir,
                  width=20).pack(pady=5)
        
        ttk.Button(config_manage_frame, text="清理音频缓存", command=self.clear_audio_cache,
                  width=20).pack(pady=5)
    
    def toggle_proxy_mode(self):
        """切换中转服务模式"""
        self.proxy_mode = self.proxy_mode_var.get()
        self.update_config('API', 'proxy_mode', str(self.proxy_mode))
        
        if self.proxy_mode:
            # 如果启用中转模式，自动切换到本地API地址
            local_api_url = f"http://{self.local_api_host}:{self.local_api_port}"
            self.api_url_entry.delete(0, tk.END)
            self.api_url_entry.insert(0, local_api_url)
            messagebox.showinfo("中转模式", f"已启用中转服务模式，API地址已切换到: {local_api_url}")
        else:
            # 如果禁用中转模式，恢复原始API地址
            original_url = self.config.get('API', 'base_url', fallback="http://127.0.0.1:8000")
            self.api_url_entry.delete(0, tk.END)
            self.api_url_entry.insert(0, original_url)
            messagebox.showinfo("中转模式", f"已禁用中转服务模式，API地址已恢复为: {original_url}")
    
    def setup_local_api_tab(self):
        """设置本地API服务标签页"""
        # 服务状态
        status_frame = ttk.LabelFrame(self.local_api_frame, text="服务状态", padding=10)
        status_frame.pack(fill='x', padx=10, pady=5)
        
        self.api_status_var = tk.StringVar()
        self.api_status_var.set("服务未运行")
        ttk.Label(status_frame, textvariable=self.api_status_var, font=("Arial", 12)).pack(pady=5)
        
        # 服务配置
        config_frame = ttk.LabelFrame(self.local_api_frame, text="服务配置", padding=10)
        config_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(config_frame, text="监听地址:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.local_host_entry = ttk.Entry(config_frame, width=15)
        self.local_host_entry.insert(0, self.local_api_host)
        self.local_host_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(config_frame, text="端口:").grid(row=0, column=2, sticky='w', padx=5, pady=5)
        self.local_port_entry = ttk.Entry(config_frame, width=10)
        self.local_port_entry.insert(0, str(self.local_api_port))
        self.local_port_entry.grid(row=0, column=3, padx=5, pady=5)
        
        # 控制按钮
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=1, column=0, columnspan=4, pady=10)
        
        ttk.Button(button_frame, text="启动服务", command=self.start_local_api).pack(side='left', padx=5)
        ttk.Button(button_frame, text="停止服务", command=self.stop_local_api).pack(side='left', padx=5)
        ttk.Button(button_frame, text="打开API文档", command=self.open_api_docs).pack(side='left', padx=5)
        
        # 服务信息
        info_frame = ttk.LabelFrame(self.local_api_frame, text="服务信息", padding=10)
        info_frame.pack(fill='x', padx=10, pady=5)
        
        self.api_url_var = tk.StringVar()
        self.api_url_var.set("服务未运行")
        ttk.Label(info_frame, text="API地址:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(info_frame, textvariable=self.api_url_var, foreground="blue").grid(row=0, column=1, sticky='w', padx=5, pady=5)
        
        # 自动启动选项
        auto_frame = ttk.Frame(info_frame)
        auto_frame.grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
        
        # 中转服务与主客户端互联设置（从工具栏移动到此处）
        self.proxy_mode_var = tk.BooleanVar(value=self.proxy_mode)
        proxy_check = ttk.Checkbutton(
            config_frame,
            text="启用中转服务模式 (通过本地API服务转发请求)",
            variable=self.proxy_mode_var,
            command=self.toggle_proxy_mode
        )
        proxy_check.grid(row=2, column=0, columnspan=4, sticky='w', pady=5)

        ttk.Label(config_frame, text="主客户端地址:").grid(row=3, column=0, sticky='w', padx=5, pady=5)
        self.master_api_entry = ttk.Entry(config_frame, width=30)
        self.master_api_entry.insert(0, self.master_api_url)
        self.master_api_entry.grid(row=3, column=1, padx=5, pady=5, sticky='we')
        self.connect_master_var = tk.BooleanVar(value=self.connect_master)
        connect_master_check = ttk.Checkbutton(config_frame, text="连接主客户端 (互联模式)", variable=self.connect_master_var, command=self.toggle_connect_master)
        connect_master_check.grid(row=3, column=2, padx=5, pady=5)
        
        self.auto_start_var = tk.BooleanVar(value=self.local_api_enabled)
        ttk.Checkbutton(auto_frame, text="启动时自动运行本地API服务", 
                       variable=self.auto_start_var, 
                       command=self.toggle_auto_start).pack(side='left', padx=5)
        
        # 添加中转服务统计信息
        stats_frame = ttk.LabelFrame(self.local_api_frame, text="中转服务统计", padding=10)
        stats_frame.pack(fill='x', padx=10, pady=5)
        
        self.stats_var = tk.StringVar()
        self.stats_var.set("总处理请求: 0")
        ttk.Label(stats_frame, textvariable=self.stats_var).pack(pady=5)
    
    def toggle_auto_start(self):
        """切换自动启动设置"""
        self.local_api_enabled = self.auto_start_var.get()
        self.update_config('LocalAPI', 'enabled', str(self.local_api_enabled))
    
    def start_local_api(self):
        """启动本地API服务"""
        if self.server_running:
            messagebox.showinfo("提示", "API服务已在运行中")
            return
        
        try:
            host = self.local_host_entry.get().strip()
            port = int(self.local_port_entry.get().strip())
            
            # 更新配置
            self.local_api_host = host
            self.local_api_port = port
            self.update_config('LocalAPI', 'host', host)
            self.update_config('LocalAPI', 'port', str(port))
            
            # 创建FastAPI应用
            self.create_fastapi_app()
            
            # 在新线程中启动服务器
            self.server_thread = threading.Thread(
                target=self.run_fastapi_server,
                args=(host, port),
                daemon=True
            )
            self.server_thread.start()
            
            # 更新状态
            self.server_running = True
            self.api_status_var.set("服务运行中")
            local_api_url = f"http://{host}:{port}"
            self.api_url_var.set(local_api_url)
            
            # 如果启用了中转模式，仅展示本地 API 地址（不覆盖上游 API 配置）
            if self.proxy_mode:
                self.api_url_var.set(local_api_url)
                # 保持 self.upstream_api_url 不变，确保对上游 API 的独立通信
            
            messagebox.showinfo("成功", f"本地API服务已启动\n地址: {local_api_url}")
            
        except Exception as e:
            messagebox.showerror("错误", f"启动API服务失败: {str(e)}")
    
    def stop_local_api(self):
        """停止本地API服务"""
        if not self.server_running:
            messagebox.showinfo("提示", "API服务未在运行")
            return
        
        # 这里我们实际上不能直接停止uvicorn服务器
        # 但可以设置标志并在下一次请求时停止
        self.server_running = False
        self.api_status_var.set("服务未运行")
        self.api_url_var.set("服务未运行")
        messagebox.showinfo("成功", "本地API服务已停止")
    
    def open_api_docs(self):
        """打开API文档"""
        if not self.server_running:
            messagebox.showwarning("警告", "请先启动API服务")
            return
        
        url = f"http://{self.local_api_host}:{self.local_api_port}/docs"
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开浏览器: {str(e)}")
    
    def create_fastapi_app(self):
        """创建FastAPI应用"""
        self.fastapi_app = FastAPI(
            title="TTS客户端中转API",
            description="TTS客户端的中转API服务，处理局域网客户端请求并转发到后端TTS服务器",
            version="1.0.0"
        )
        
        # 添加CORS中间件
        self.fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # 定义数据模型 - 根据API规范
        class CharacterPayload(pydantic.BaseModel):
            character_name: str
            onnx_model_dir: str
        
        class UnloadCharacterPayload(pydantic.BaseModel):
            character_name: str
        
        class ReferenceAudioPayload(pydantic.BaseModel):
            character_name: str
            audio_path: str
            audio_text: str
        
        class TTSPayload(pydantic.BaseModel):
            character_name: str
            text: str
            split_sentence: bool = False
            save_path: Optional[str] = None
        
        class ClientTaskRequest(pydantic.BaseModel):
            task_id: str
            client_id: str
            callback_url: Optional[str] = None
        
        # 统计信息
        self.request_count = 0
        
        # API路由
        @self.fastapi_app.get("/")
        async def root():
            return {
                "message": "TTS客户端中转API服务", 
                "status": "running",
                "backend_server": self.upstream_api_url,
                "requests_processed": self.request_count
            }
        
        @self.fastapi_app.post("/load_character")
        async def load_character(request: CharacterPayload):
            self.request_count += 1
            success, result = self.api_call("/load_character", request.dict())
            if success:
                return {"status": "success", "message": "角色加载成功"}
            else:
                raise HTTPException(status_code=500, detail=result)
        
        @self.fastapi_app.post("/unload_character")
        async def unload_character(request: UnloadCharacterPayload):
            self.request_count += 1
            success, result = self.api_call("/unload_character", request.dict())
            if success:
                return {"status": "success", "message": "角色卸载成功"}
            else:
                raise HTTPException(status_code=500, detail=result)
        
        @self.fastapi_app.post("/set_reference_audio")
        async def set_reference_audio(request: ReferenceAudioPayload):
            self.request_count += 1
            success, result = self.api_call("/set_reference_audio", request.dict())
            if success:
                return {"status": "success", "message": "参考音频设置成功"}
            else:
                raise HTTPException(status_code=500, detail=result)
        
        @self.fastapi_app.post("/tts")
        async def tts(request: TTSPayload, background_tasks: BackgroundTasks):
            self.request_count += 1
            
            # 生成唯一的任务ID
            task_id = hashlib.md5(f"{request.character_name}_{request.text}_{time.time()}".encode()).hexdigest()[:16]
            
            # 生成缓存文件名
            cache_file_path = self.generate_filename_from_text(request.text, request.character_name)
            
            # 准备请求数据 - 严格遵循API规范
            data = {
                "character_name": request.character_name,
                "text": request.text,
                "split_sentence": request.split_sentence,
                "save_path": cache_file_path  # 强制保存到中转服务器本地
            }
            
            # 记录任务信息
            self.audio_file_map[task_id] = {
                "file_path": cache_file_path,
                "status": "processing",
                "progress": 0,
                "created_at": datetime.now().isoformat(),
                "character": request.character_name,
                "text": request.text[:50] + "..." if len(request.text) > 50 else request.text
            }
            
            # 在新线程中处理TTS请求
            def process_tts():
                try:
                    # 启动一个简单的进度模拟器，在后台循环增加进度，直到任务完成或失败
                    def progress_updater():
                        try:
                            while True:
                                info = self.audio_file_map.get(task_id)
                                if not info or info.get("status") != "processing":
                                    break
                                cur = info.get("progress", 0)
                                # 逐步增加进度但不超过95%，完成后由实际结果设为100%
                                if cur < 95:
                                    info["progress"] = min(95, cur + randint(3, 10))
                                time.sleep(1)
                        except Exception as e:
                            print(f"[中转服务] 进度更新线程异常: {e}")

                    prog_thread = threading.Thread(target=progress_updater, daemon=True)
                    prog_thread.start()

                    success, result = self.api_call("/tts", data)
                    if success:
                        # 检查文件是否存在
                        if os.path.exists(cache_file_path):
                            self.audio_file_map[task_id]["status"] = "completed"
                            self.audio_file_map[task_id]["progress"] = 100
                            # 更新统计信息
                            self.root.after(0, self.update_stats_display)
                            print(f"[中转服务] TTS任务完成: {task_id}, 文件: {cache_file_path}")
                            # 通知已注册该任务的客户端（如果提供了回调URL）
                            try:
                                download_url = f"http://{self.local_api_host}:{self.local_api_port}/download/{task_id}"
                                for client_id, info in list(self.client_tasks.items()):
                                    try:
                                        if info.get("task_id") == task_id and info.get("callback_url"):
                                            notify_payload = {
                                                "task_id": task_id,
                                                "status": "completed",
                                                "download_url": download_url
                                            }
                                            # 以非阻塞方式调用外部客户端回调（短超时）
                                            try:
                                                requests.post(info.get("callback_url"), json=notify_payload, timeout=5)
                                                info["status"] = "notified"
                                                info["last_check"] = datetime.now().isoformat()
                                                print(f"[中转服务] 已通知客户端 {client_id} 回调: {info.get('callback_url')}")
                                            except Exception as e:
                                                print(f"[中转服务] 通知客户端 {client_id} 失败: {e}")
                                    except Exception as e:
                                        print(f"[中转服务] 通知单个客户端时异常: {e}")
                            except Exception as e:
                                print(f"[中转服务] 通知客户端流程异常: {e}")
                        else:
                            self.audio_file_map[task_id]["status"] = "failed"
                            self.audio_file_map[task_id]["progress"] = 0
                            self.audio_file_map[task_id]["error"] = "音频文件生成失败"
                            print(f"[中转服务] TTS任务失败: {task_id}, 文件不存在: {cache_file_path}")
                    else:
                        self.audio_file_map[task_id]["status"] = "failed"
                        self.audio_file_map[task_id]["progress"] = 0
                        self.audio_file_map[task_id]["error"] = result
                        print(f"[中转服务] TTS任务失败: {task_id}, 错误: {result}")
                except Exception as e:
                    self.audio_file_map[task_id]["status"] = "failed"
                    self.audio_file_map[task_id]["error"] = str(e)
                    print(f"[中转服务] TTS任务异常: {task_id}, 异常: {str(e)}")
            
            # 启动处理线程
            threading.Thread(target=process_tts, daemon=True).start()
            
            # 返回任务ID，客户端可以轮询状态或等待完成
            return {
                "status": "processing", 
                "task_id": task_id,
                "message": "TTS任务已提交，请使用任务ID查询状态",
                "check_status_url": f"/tts_status/{task_id}",
                "download_url": f"/download/{task_id}" if os.path.exists(cache_file_path) else None
            }
        
        @self.fastapi_app.get("/tts_status/{task_id}")
        async def get_tts_status(task_id: str):
            if task_id not in self.audio_file_map:
                raise HTTPException(status_code=404, detail="任务ID不存在")
            
            task_info = self.audio_file_map[task_id]
            response = {
                "task_id": task_id,
                "status": task_info["status"],
                "progress": task_info.get("progress", 0),
                "created_at": task_info["created_at"],
                "character": task_info["character"],
                "text": task_info["text"]
            }
            
            if task_info["status"] == "completed":
                response["download_url"] = f"/download/{task_id}"
                response["file_exists"] = os.path.exists(task_info["file_path"])
                response["file_path"] = task_info["file_path"]
                response["file_url"] = f"http://{self.local_api_host}:{self.local_api_port}/download/{task_id}"
            elif task_info["status"] == "failed":
                response["error"] = task_info.get("error", "未知错误")
            
            return response
        
        @self.fastapi_app.get("/download/{task_id}")
        async def download_audio(task_id: str):
            if task_id not in self.audio_file_map:
                raise HTTPException(status_code=404, detail="任务ID不存在")
            
            task_info = self.audio_file_map[task_id]
            
            if task_info["status"] != "completed":
                raise HTTPException(status_code=400, detail="任务尚未完成")
            
            file_path = task_info["file_path"]
            
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="音频文件不存在")
            
            # 返回音频文件
            return FileResponse(
                path=file_path,
                media_type='audio/wav',
                filename=os.path.basename(file_path)
            )
        
        @self.fastapi_app.get("/stream/{task_id}")
        async def stream_audio(task_id: str):
            """流式传输音频文件"""
            if task_id not in self.audio_file_map:
                raise HTTPException(status_code=404, detail="任务ID不存在")
            
            task_info = self.audio_file_map[task_id]
            
            # 等待任务完成
            start_time = time.time()
            while task_info["status"] == "processing" and (time.time() - start_time) < 30:  # 最多等待30秒
                await asyncio.sleep(0.5)
            
            if task_info["status"] != "completed":
                raise HTTPException(status_code=400, detail=f"任务失败: {task_info.get('error', '未知错误')}")
            
            file_path = task_info["file_path"]
            
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="音频文件不存在")
            
            # 返回音频文件
            return FileResponse(
                path=file_path,
                media_type='audio/wav',
                filename=os.path.basename(file_path)
            )
        
        # 新增：客户端任务注册接口
        @self.fastapi_app.post("/register_client_task")
        async def register_client_task(request: ClientTaskRequest):
            """客户端注册任务，用于后续状态推送"""
            if request.task_id not in self.audio_file_map:
                raise HTTPException(status_code=404, detail="任务ID不存在")
            
            self.client_tasks[request.client_id] = {
                "task_id": request.task_id,
                "callback_url": request.callback_url,
                "last_check": datetime.now().isoformat(),
                "status": "registered"
            }
            
            return {"status": "success", "message": "客户端任务已注册"}

        # 便捷：主客户端用来接收客户端注册的接口名已有，上面的实现保留
        
        # 新增：获取客户端任务列表
        @self.fastapi_app.get("/client_tasks")
        async def get_client_tasks():
            """获取所有客户端任务"""
            return {
                "client_tasks": self.client_tasks,
                "total_clients": len(self.client_tasks)
            }
        
        # 新增：获取已完成的任务列表
        @self.fastapi_app.get("/completed_tasks")
        async def get_completed_tasks():
            """获取所有已完成的任务"""
            completed_tasks = {
                task_id: info for task_id, info in self.audio_file_map.items() 
                if info["status"] == "completed"
            }
            return {
                "completed_tasks": completed_tasks,
                "total_completed": len(completed_tasks)
            }
        
        # 新增：批量获取任务状态
        @self.fastapi_app.post("/batch_task_status")
        async def batch_task_status(task_ids: List[str]):
            """批量获取任务状态"""
            results = {}
            for task_id in task_ids:
                if task_id in self.audio_file_map:
                    task_info = self.audio_file_map[task_id]
                    results[task_id] = {
                        "status": task_info["status"],
                        "character": task_info["character"],
                        "text": task_info["text"]
                    }
                    if task_info["status"] == "completed":
                        results[task_id]["download_url"] = f"/download/{task_id}"
                else:
                    results[task_id] = {"status": "not_found"}
            
            return {"tasks": results}
        
        @self.fastapi_app.post("/clear_reference_audio_cache")
        async def clear_reference_audio_cache():
            self.request_count += 1
            success, result = self.api_call("/clear_reference_audio_cache")
            if success:
                return {"status": "success", "message": "参考音频缓存已清除"}
            else:
                raise HTTPException(status_code=500, detail=result)
        
        @self.fastapi_app.post("/stop")
        async def stop_tts():
            self.request_count += 1
            success, result = self.api_call("/stop")
            if success:
                return {"status": "success", "message": "TTS已停止"}
            else:
                raise HTTPException(status_code=500, detail=result)
        
        @self.fastapi_app.get("/stats")
        async def get_stats():
            """获取服务统计信息"""
            completed_tasks = len([t for t in self.audio_file_map.values() if t["status"] == "completed"])
            failed_tasks = len([t for t in self.audio_file_map.values() if t["status"] == "failed"])
            processing_tasks = len([t for t in self.audio_file_map.values() if t["status"] == "processing"])
            
            return {
                "total_requests": self.request_count,
                "total_tasks": len(self.audio_file_map),
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "processing_tasks": processing_tasks,
                "active_clients": len(self.client_tasks),
                "backend_server": self.upstream_api_url
            }
    
    def update_stats_display(self):
        """更新统计信息显示"""
        if hasattr(self, 'stats_var'):
            self.stats_var.set(f"总处理请求: {getattr(self, 'request_count', 0)}")
    
    def run_fastapi_server(self, host, port):
        """运行FastAPI服务器"""
        try:
            uvicorn.run(
                self.fastapi_app,
                host=host,
                port=port,
                log_level="info",
                access_log=True
            )
        except Exception as e:
            print(f"API服务器错误: {e}")
            # 在GUI线程中更新状态
            self.root.after(0, lambda: self.api_status_var.set(f"服务错误: {str(e)}"))
            self.server_running = False

    # 以下是不变的方法...
    def browse_model_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.model_dir_entry.delete(0, tk.END)
            self.model_dir_entry.insert(0, directory)
    
    def browse_audio_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("音频文件", "*.wav *.mp3 *.flac *.ogg"), ("所有文件", "*.*")]
        )
        if file_path:
            self.audio_path_entry.delete(0, tk.END)
            self.audio_path_entry.insert(0, file_path)
    
    def browse_save_path(self):
        # 选择目录（保存路径为目录，文件名由程序自动生成）
        directory = filedialog.askdirectory()
        if directory:
            self.save_path_entry.delete(0, tk.END)
            self.save_path_entry.insert(0, directory)
    
    def browse_cache_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.cache_dir_entry.delete(0, tk.END)
            self.cache_dir_entry.insert(0, directory)
    
    def update_api_url(self):
        new_url = self.api_url_entry.get().strip()
        if new_url:
            self.upstream_api_url = new_url
            self.update_config('API', 'upstream_api_url', new_url)
            messagebox.showinfo("成功", f"上游 API 地址已更新为: {new_url}")

    def toggle_connect_master(self):
        # 连接/断开主客户端互联
        self.connect_master = self.connect_master_var.get()
        self.master_api_url = self.master_api_entry.get().strip()
        self.update_config('Network', 'master_api_url', self.master_api_url)
        self.update_config('Network', 'connect_master', str(self.connect_master))
        if self.connect_master and self.master_api_url:
            messagebox.showinfo("互联", f"已设置主客户端地址: {self.master_api_url}")
        else:
            messagebox.showinfo("互联", "已断开主客户端连接")
    
    def update_cache_dir(self):
        new_cache_dir = self.cache_dir_entry.get().strip()
        if new_cache_dir:
            self.cache_dir = new_cache_dir
            self.update_config('Cache', 'cache_dir', new_cache_dir)
            self.ensure_cache_dir()
            messagebox.showinfo("成功", f"缓存目录已更新为: {new_cache_dir}")
    
    def open_cache_dir(self):
        """打开缓存目录"""
        if os.path.exists(self.cache_dir):
            try:
                os.startfile(self.cache_dir)  # Windows
            except:
                try:
                    # 对于其他系统，可以使用以下代码：
                    import subprocess
                    import platform
                    system = platform.system()
                    if system == "Darwin":  # macOS
                        subprocess.run(['open', self.cache_dir])
                    elif system == "Linux":
                        subprocess.run(['xdg-open', self.cache_dir])
                    else:
                        messagebox.showinfo("提示", f"缓存目录位置: {self.cache_dir}")
                except:
                    messagebox.showinfo("提示", f"缓存目录位置: {self.cache_dir}")
        else:
            messagebox.showwarning("警告", f"缓存目录不存在: {self.cache_dir}")
    
    def clear_audio_cache(self):
        """清理音频缓存文件"""
        if not os.path.exists(self.cache_dir):
            messagebox.showinfo("信息", "缓存目录不存在，无需清理")
            return
            
        if messagebox.askyesno("确认", "确定要清理所有音频缓存文件吗？"):
            try:
                count = 0
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.wav'):
                        file_path = os.path.join(self.cache_dir, filename)
                        os.remove(file_path)
                        count += 1
                messagebox.showinfo("成功", f"已清理 {count} 个音频缓存文件")
            except Exception as e:
                messagebox.showerror("错误", f"清理缓存失败: {e}")
    
    def save_current_config(self):
        """保存当前表单中的值到配置"""
        # 保存角色名称
        character_name = self.character_name_entry.get().strip()
        if character_name:
            self.update_config('Recent', 'character_name', character_name)
        
        # 保存模型目录
        model_dir = self.model_dir_entry.get().strip()
        if model_dir:
            self.update_config('Recent', 'model_dir', model_dir)
        
        # 保存参考音频相关
        ref_character = self.ref_character_entry.get().strip()
        if ref_character:
            self.update_config('Recent', 'ref_character', ref_character)
        
        audio_path = self.audio_path_entry.get().strip()
        if audio_path:
            self.update_config('Recent', 'audio_path', audio_path)
            
        # 保存音频文本
        audio_text = self.audio_text_entry.get().strip()
        if audio_text:
            self.update_config('Recent', 'audio_text', audio_text)
            
        # 保存TTS相关
        tts_character = self.tts_character_entry.get().strip()
        if tts_character:
            self.update_config('Recent', 'tts_character', tts_character)
            
        # 保存TTS文本
        tts_text = self.tts_text.get("1.0", tk.END).strip()
        if tts_text:
            self.update_config('Recent', 'tts_text', tts_text)
            
        # 保存保存路径
        save_path = self.save_path_entry.get().strip()
        if save_path:
            self.update_config('Recent', 'save_path', save_path)
        
        # 保存缓存目录
        cache_dir = self.cache_dir_entry.get().strip()
        if cache_dir:
            self.update_config('Cache', 'cache_dir', cache_dir)
        
        messagebox.showinfo("成功", "当前配置已保存")
    
    def save_reference_config(self):
        """专门保存参考音频配置"""
        # 保存参考音频相关
        ref_character = self.ref_character_entry.get().strip()
        if ref_character:
            self.update_config('Recent', 'ref_character', ref_character)
        
        audio_path = self.audio_path_entry.get().strip()
        if audio_path:
            self.update_config('Recent', 'audio_path', audio_path)
            
        # 保存音频文本
        audio_text = self.audio_text_entry.get().strip()
        if audio_text:
            self.update_config('Recent', 'audio_text', audio_text)
            
        messagebox.showinfo("成功", "参考音频配置已保存")
    
    def load_recent_values(self):
        """加载最近使用的值到表单"""
        try:
            # 加载角色名称
            character_name = self.config.get('Recent', 'character_name', fallback='')
            if character_name:
                self.character_name_entry.insert(0, character_name)
                self.unload_character_entry.insert(0, character_name)
                self.ref_character_entry.insert(0, character_name)
                self.tts_character_entry.insert(0, character_name)
            
            # 加载模型目录
            model_dir = self.config.get('Recent', 'model_dir', fallback='')
            if model_dir:
                self.model_dir_entry.insert(0, model_dir)
            
            # 加载参考音频路径
            audio_path = self.config.get('Recent', 'audio_path', fallback='')
            if audio_path:
                self.audio_path_entry.insert(0, audio_path)
                
            # 加载音频文本
            audio_text = self.config.get('Recent', 'audio_text', fallback='')
            if audio_text:
                self.audio_text_entry.insert(0, audio_text)
                
            # 加载TTS文本
            tts_text = self.config.get('Recent', 'tts_text', fallback='')
            if tts_text:
                self.tts_text.insert("1.0", tts_text)
                
            # 加载保存路径
            save_path = self.config.get('Recent', 'save_path', fallback='')
            if save_path:
                self.save_path_entry.insert(0, save_path)
                
            # 加载缓存目录
            cache_dir = self.config.get('Cache', 'cache_dir', fallback='./audio_cache')
            if cache_dir:
                self.cache_dir_entry.delete(0, tk.END)
                self.cache_dir_entry.insert(0, cache_dir)
                
            # 加载本地API配置
            local_host = self.config.get('LocalAPI', 'host', fallback='0.0.0.0')
            if local_host:
                self.local_host_entry.delete(0, tk.END)
                self.local_host_entry.insert(0, local_host)
                
            local_port = self.config.get('LocalAPI', 'port', fallback='8001')
            if local_port:
                self.local_port_entry.delete(0, tk.END)
                self.local_port_entry.insert(0, local_port)
                
            # 加载中转模式设置
            proxy_mode = self.config.getboolean('API', 'proxy_mode', fallback=False)
            self.proxy_mode_var.set(proxy_mode)
                
        except Exception as e:
            print(f"加载历史记录失败: {e}")
    
    def clear_history(self):
        """清除历史记录"""
        if messagebox.askyesno("确认", "确定要清除所有历史记录吗？"):
            self.config.remove_section('Recent')
            self.config.add_section('Recent')
            self.save_config()
            
            # 清空表单
            self.character_name_entry.delete(0, tk.END)
            self.model_dir_entry.delete(0, tk.END)
            self.unload_character_entry.delete(0, tk.END)
            self.ref_character_entry.delete(0, tk.END)
            self.audio_path_entry.delete(0, tk.END)
            self.audio_text_entry.delete(0, tk.END)
            self.tts_character_entry.delete(0, tk.END)
            self.tts_text.delete("1.0", tk.END)
            self.save_path_entry.delete(0, tk.END)
            
            messagebox.showinfo("成功", "历史记录已清除")
    
    def generate_filename_from_text(self, text, character_name):
        """根据文本和角色名称生成文件名"""
        # 获取当前时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 清理文本，移除特殊字符
        clean_text = re.sub(r'[^\w\s]', '', text)
        # 取前30个字符，避免文件名过长
        clean_text = clean_text[:30].strip()
        
        # 如果文本为空，使用哈希值
        if not clean_text:
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"{character_name}_{text_hash}_{timestamp}.wav"
        else:
            # 替换空格为下划线
            clean_text = clean_text.replace(' ', '_')
            filename = f"{character_name}_{clean_text}_{timestamp}.wav"
        
        # 使用os.path.normpath确保路径分隔符正确
        return os.path.normpath(os.path.join(self.cache_dir, filename))
    
    def api_call(self, endpoint, data=None):
        """通用的API调用方法"""
        try:
            url = f"{self.upstream_api_url}{endpoint}"
            self.status_var.set(f"正在调用 {endpoint}...")
            
            headers = {'Content-Type': 'application/json'}
            
            # 添加调试信息
            print(f"[API调用] 目标URL: {url}")
            print(f"[API调用] 请求数据: {data}")
            
            if data:
                response = requests.post(url, json=data, headers=headers, timeout=30)
            else:
                response = requests.post(url, headers=headers, timeout=30)
            
            # 检查响应状态
            if response.status_code == 200:
                # 尝试解析JSON响应，但允许空响应
                try:
                    if response.content:  # 如果响应不为空
                        json_response = response.json()
                        self.status_var.set(f"{endpoint} 调用成功")
                        print(f"[API调用] 响应成功: {json_response}")
                        return True, json_response
                    else:
                        self.status_var.set(f"{endpoint} 调用成功 (空响应)")
                        print(f"[API调用] 响应成功 (空响应)")
                        return True, "成功"
                except json.JSONDecodeError as e:
                    # 如果JSON解析失败，但状态码是200，可能返回的是纯文本或其他格式
                    self.status_var.set(f"{endpoint} 调用成功 (非JSON响应)")
                    print(f"[API调用] 响应成功 (非JSON响应)")
                    return True, response.text
            else:
                error_msg = f"HTTP错误: {response.status_code}"
                try:
                    # 尝试获取错误详情
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text}"
                
                self.status_var.set(f"{endpoint} 调用失败: {response.status_code}")
                print(f"[API调用] 响应失败: {error_msg}")
                return False, error_msg
                
        except requests.exceptions.ConnectionError:
            self.status_var.set("连接错误: 无法连接到服务器")
            print(f"[API调用] 连接错误: 无法连接到服务器 {url}")
            return False, "连接错误: 请检查服务器是否运行及API地址是否正确"
        except requests.exceptions.Timeout:
            self.status_var.set("请求超时")
            print(f"[API调用] 请求超时: {url}")
            return False, "请求超时: 服务器响应时间过长"
        except Exception as e:
            self.status_var.set(f"错误: {str(e)}")
            print(f"[API调用] 异常: {str(e)}")
            return False, str(e)
    
    def load_character(self):
        character_name = self.character_name_entry.get().strip()
        onnx_model_dir = self.model_dir_entry.get().strip()
        
        if not character_name or not onnx_model_dir:
            messagebox.showerror("错误", "请填写角色名称和模型目录")
            return
        
        data = {
            "character_name": character_name,
            "onnx_model_dir": onnx_model_dir
        }
        
        # 保存到配置
        self.update_config('Recent', 'character_name', character_name)
        self.update_config('Recent', 'model_dir', onnx_model_dir)
        
        # 在新线程中执行API调用
        threading.Thread(target=self._load_character_thread, args=(data,), daemon=True).start()
    
    def _load_character_thread(self, data):
        success, result = self.api_call("/load_character", data)
        if success:
            messagebox.showinfo("成功", f"角色加载成功: {data['character_name']}")
        else:
            messagebox.showerror("错误", f"角色加载失败: {result}")
    
    def unload_character(self):
        character_name = self.unload_character_entry.get().strip()
        
        if not character_name:
            messagebox.showerror("错误", "请填写角色名称")
            return
        
        data = {
            "character_name": character_name
        }
        
        threading.Thread(target=self._unload_character_thread, args=(data,), daemon=True).start()
    
    def _unload_character_thread(self, data):
        success, result = self.api_call("/unload_character", data)
        if success:
            messagebox.showinfo("成功", f"角色卸载成功: {data['character_name']}")
        else:
            messagebox.showerror("错误", f"角色卸载失败: {result}")
    
    def set_reference_audio(self):
        character_name = self.ref_character_entry.get().strip()
        audio_path = self.audio_path_entry.get().strip()
        audio_text = self.audio_text_entry.get().strip()
        
        if not all([character_name, audio_path, audio_text]):
            messagebox.showerror("错误", "请填写所有字段")
            return
        
        data = {
            "character_name": character_name,
            "audio_path": audio_path,
            "audio_text": audio_text
        }
        
        # 保存到配置
        self.update_config('Recent', 'ref_character', character_name)
        self.update_config('Recent', 'audio_path', audio_path)
        self.update_config('Recent', 'audio_text', audio_text)  # 新增：保存音频文本
        
        threading.Thread(target=self._set_reference_audio_thread, args=(data,), daemon=True).start()
    
    def _set_reference_audio_thread(self, data):
        success, result = self.api_call("/set_reference_audio", data)
        if success:
            messagebox.showinfo("成功", "参考音频设置成功")
        else:
            messagebox.showerror("错误", f"参考音频设置失败: {result}")
    
    def start_tts(self):
        character_name = self.tts_character_entry.get().strip()
        text = self.tts_text.get("1.0", tk.END).strip()
        save_path = self.save_path_entry.get().strip() or None
        
        if not character_name or not text:
            messagebox.showerror("错误", "请填写角色名称和文本")
            return
        
        data = {
            "character_name": character_name,
            "text": text,
            "split_sentence": self.split_sentence_var.get(),
            "save_path": save_path
        }
        
        # 保存到配置
        self.update_config('Recent', 'tts_character', character_name)
        self.update_config('Recent', 'tts_text', text)  # 新增：保存TTS文本
        if save_path:
            self.update_config('Recent', 'save_path', save_path)
        # 如果没有指定保存路径，使用与朗读文本相同的命名规则生成缓存文件路径
        if not save_path:
            cache_file_path = self.generate_filename_from_text(text, character_name)
            data['save_path'] = cache_file_path
        else:
            # 把用户提供的保存路径视为目录（浏览按钮现在只选目录）
            try:
                if os.path.isdir(save_path):
                    target_dir = save_path
                else:
                    # 如果用户手动输入了路径，尝试取其父目录作为目标目录
                    target_dir = os.path.dirname(save_path) or save_path
                # 生成文件名并拼接到目标目录
                filename = os.path.basename(self.generate_filename_from_text(text, character_name))
                cache_file_path = os.path.normpath(os.path.join(target_dir, filename))
                data['save_path'] = cache_file_path
            except Exception:
                # 出错时回退到默认缓存目录
                cache_file_path = self.generate_filename_from_text(text, character_name)
                data['save_path'] = cache_file_path

        threading.Thread(target=self._tts_thread, args=(data, cache_file_path), daemon=True).start()
    
    def _tts_thread(self, data, cache_file_path):
        # 若启用中转服务并且本地API服务正在运行，使用中转模式的轮询+下载逻辑
        if getattr(self, 'proxy_mode', False) and getattr(self, 'server_running', False):
            success, result = self._speak_with_proxy_mode(data, cache_file_path)
        else:
            success, result = self.api_call("/tts", data)

        if success:
            # 不在此处自动播放（start_tts 请求不自动朗读），仅提示完成并告知文件路径
            if cache_file_path and os.path.exists(cache_file_path) and os.path.getsize(cache_file_path) > 0:
                messagebox.showinfo("成功", f"TTS转换完成，文件已保存: {cache_file_path}")
            else:
                messagebox.showinfo("成功", "TTS转换完成，但未找到生成的音频文件，请检查保存路径或服务端响应")
        else:
            messagebox.showerror("错误", f"TTS转换失败: {result}")
    
    def speak_text(self):
        """朗读文本"""
        if self.audio_playing:
            messagebox.showinfo("提示", "音频正在播放中，请等待播放完成")
            return
            
        character_name = self.tts_character_entry.get().strip()
        text = self.tts_text.get("1.0", tk.END).strip()
        
        if not character_name or not text:
            messagebox.showerror("错误", "请填写角色名称和文本")
            return
        
        # 生成基于文本的文件名（包含时间戳）
        cache_file_path = self.generate_filename_from_text(text, character_name)
        
        data = {
            "character_name": character_name,
            "text": text,
            "split_sentence": self.split_sentence_var.get(),
            "save_path": cache_file_path
        }
        
        # 保存到配置
        self.update_config('Recent', 'tts_character', character_name)
        self.update_config('Recent', 'tts_text', text)  # 新增：保存TTS文本
        
        threading.Thread(target=self._speak_thread, args=(data, cache_file_path), daemon=True).start()
    
    def _speak_thread(self, data, cache_file_path):
        """改进的朗读线程，添加任务状态轮询"""
        if self.proxy_mode and self.server_running:
            # 中转模式：使用任务状态轮询机制
            success, result = self._speak_with_proxy_mode(data, cache_file_path)
        else:
            # 直接模式：保持原有逻辑
            success, result = self._speak_direct_mode(data, cache_file_path)
            
        if success:
            # 检查文件是否真的存在
            if os.path.exists(cache_file_path):
                try:
                    # 使用PyAudio播放音频
                    self.play_audio_file(cache_file_path)
                except Exception as e:
                    self.status_var.set(f"播放音频失败: {str(e)}")
                    messagebox.showerror("错误", f"播放音频失败: {str(e)}")
            else:
                self.status_var.set(f"音频文件不存在: {cache_file_path}")
                messagebox.showerror("错误", f"音频文件不存在: {cache_file_path}\n请检查TTS服务器是否正常运行")
        else:
            messagebox.showerror("错误", f"TTS转换失败: {result}")
    
    def _speak_direct_mode(self, data, cache_file_path):
        """直接模式的TTS调用"""
        return self.api_call("/tts", data)
    
    def _speak_with_proxy_mode(self, data, cache_file_path):
        """中转模式的TTS调用，包含任务状态轮询和文件下载"""
        try:
            # 选择目标：若启用连接主客户端并配置了主地址，则优先将请求发给主客户端(master)，否则发往本地中转服务
            local_api_url = f"http://{self.local_api_host}:{self.local_api_port}"
            target_api = None
            use_master = getattr(self, 'connect_master', False) and getattr(self, 'master_api_url', '')
            if use_master and self.master_api_url:
                target_api = self.master_api_url.rstrip('/')
                print(f"[中转模式] 使用主客户端进行中转: {target_api}")
            else:
                target_api = local_api_url

            tts_url = f"{target_api}/tts"
            
            self.status_var.set("正在提交TTS任务...")
            print(f"[中转模式] 提交TTS任务到: {tts_url}")
            print(f"[中转模式] 提交数据: {data}")
            
            response = requests.post(tts_url, json=data, timeout=30)
            
            if response.status_code != 200:
                error_msg = f"提交任务失败: {response.status_code} - {response.text}"
                print(f"[中转模式] {error_msg}")
                return False, error_msg
            
            result = response.json()
            print(f"[中转模式] 任务提交响应: {result}")
            
            if result.get("status") != "processing":
                error_msg = f"任务提交失败: {result.get('message', '未知错误')}"
                print(f"[中转模式] {error_msg}")
                return False, error_msg
            
            task_id = result.get("task_id")
            if not task_id:
                error_msg = "未收到任务ID"
                print(f"[中转模式] {error_msg}")
                return False, error_msg

            # 如果是连接到主客户端，把当前客户端注册到主客户端以便主端记录/推送状态
            if use_master:
                try:
                    self.register_with_master(task_id)
                except Exception as e:
                    print(f"[中转模式] 向主客户端注册失败: {e}")
            
            self.status_var.set(f"任务已提交，ID: {task_id}，等待生成...")
            print(f"[中转模式] 任务ID: {task_id}")
            
            # 轮询任务状态
            status_url = f"{target_api}/tts_status/{task_id}"
            max_attempts = getattr(self, 'proxy_poll_attempts', 120)  # 可配置的尝试次数
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    status_response = requests.get(status_url, timeout=10)
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        task_status = status_data.get("status")
                        progress = status_data.get("progress")
                        download_hint = status_data.get("download_url")
                        if progress is not None:
                            self.status_var.set(f"生成中... {progress}%")
                            print(f"[中转模式] 任务状态轮询 {attempt+1}/{max_attempts}: {task_status}, 进度: {progress}%, download_url: {download_hint}")
                        else:
                            print(f"[中转模式] 任务状态轮询 {attempt+1}/{max_attempts}: {task_status}, download_url: {download_hint}")

                        if task_status == "completed":
                            self.status_var.set("音频生成完成，准备下载...")
                            print(f"[中转模式] 任务完成，准备下载音频")
                            
                            # 确保客户端缓存目录存在
                            os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
                            
                            # 下载音频文件到客户端缓存目录
                            download_url = f"{target_api}/download/{task_id}"
                            download_response = requests.get(download_url, timeout=30)
                            
                            if download_response.status_code == 200:
                                # 保存下载的音频文件到客户端缓存目录
                                with open(cache_file_path, 'wb') as f:
                                    f.write(download_response.content)
                                
                                # 验证文件是否成功保存
                                if os.path.exists(cache_file_path) and os.path.getsize(cache_file_path) > 0:
                                    self.status_var.set("音频文件下载完成")
                                    print(f"[中转模式] 音频文件已保存到客户端: {cache_file_path}")
                                    print(f"[中转模式] 文件大小: {os.path.getsize(cache_file_path)} 字节")
                                    return True, "成功"
                                else:
                                    error_msg = "文件下载后保存失败或文件为空"
                                    print(f"[中转模式] {error_msg}")
                                    return False, error_msg
                            else:
                                error_msg = f"下载音频失败: {download_response.status_code}"
                                print(f"[中转模式] {error_msg}")
                                return False, error_msg
                                
                        elif task_status == "failed":
                            error_msg = status_data.get("error", "未知错误")
                            print(f"[中转模式] 任务处理失败: {error_msg}")
                            return False, f"任务处理失败: {error_msg}"
                        
                        # 任务仍在处理中，继续等待
                        self.status_var.set(f"任务处理中... ({attempt+1}/{max_attempts})")
                        time.sleep(0.5)  # 等待0.5秒
                        attempt += 1
                        
                    else:
                        error_msg = f"查询任务状态失败: {status_response.status_code}"
                        print(f"[中转模式] {error_msg}")
                        return False, error_msg
                        
                except requests.exceptions.Timeout:
                    self.status_var.set(f"查询任务状态超时，重试中... ({attempt+1}/{max_attempts})")
                    print(f"[中转模式] 查询任务状态超时，重试 {attempt+1}/{max_attempts}")
                    attempt += 1
                    continue
                except Exception as e:
                    error_msg = f"查询任务状态时发生错误: {str(e)}"
                    print(f"[中转模式] {error_msg}")
                    return False, error_msg
            
            # 超时
            error_msg = "任务处理超时，请稍后重试"
            print(f"[中转模式] {error_msg}")
            return False, error_msg
            
        except Exception as e:
            error_msg = f"中转模式TTS调用失败: {str(e)}"
            print(f"[中转模式] {error_msg}")
            return False, error_msg

    def register_with_master(self, task_id):
        """向主客户端注册当前客户端任务（用于主端记录和推送）"""
        try:
            if not getattr(self, 'master_api_url', ''):
                raise RuntimeError("未配置主客户端地址")
            register_url = f"{self.master_api_url.rstrip('/')}/register_client_task"
            payload = {
                "task_id": task_id,
                "client_id": self.client_id,
                "callback_url": None
            }
            print(f"[互联] 向主客户端注册任务: {register_url} -> {payload}")
            r = requests.post(register_url, json=payload, timeout=5)
            if r.status_code == 200:
                print(f"[互联] 注册成功: {task_id} -> {self.client_id}")
                return True
            else:
                print(f"[互联] 注册失败: {r.status_code} - {r.text}")
                return False
        except Exception as e:
            print(f"[互联] 注册异常: {e}")
            return False
    
    def play_audio_file(self, file_path):
        """使用PyAudio播放音频文件"""
        try:
            self.audio_playing = True
            self.status_var.set("正在播放音频...")
            
            # 打开WAV文件
            wf = wave.open(file_path, 'rb')
            
            # 打开音频流
            stream = self.p.open(
                format=self.p.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )
            
            # 读取数据并播放
            data = wf.readframes(1024)
            while data and self.audio_playing:
                stream.write(data)
                data = wf.readframes(1024)
            
            # 停止流
            stream.stop_stream()
            stream.close()
            
            # 关闭WAV文件
            wf.close()
            
            self.status_var.set("音频播放完成")
            self.audio_playing = False
            
        except Exception as e:
            self.audio_playing = False
            raise e
    
    def stop_audio(self):
        """停止音频播放"""
        self.audio_playing = False
        self.status_var.set("音频播放已停止")
    
    def stop_tts(self):
        threading.Thread(target=self._stop_tts_thread, daemon=True).start()
    
    def _stop_tts_thread(self):
        success, result = self.api_call("/stop")
        if success:
            messagebox.showinfo("成功", "TTS已停止")
        else:
            messagebox.showerror("错误", f"停止TTS失败: {result}")
    
    def clear_reference_cache(self):
        threading.Thread(target=self._clear_cache_thread, daemon=True).start()
    
    def _clear_cache_thread(self):
        success, result = self.api_call("/clear_reference_audio_cache")
        if success:
            messagebox.showinfo("成功", "参考音频缓存已清除")
        else:
            messagebox.showerror("错误", f"清除缓存失败: {result}")
    
    def test_connection(self):
        threading.Thread(target=self._test_connection_thread, daemon=True).start()
    
    def _test_connection_thread(self):
        try:
            # 尝试访问API根路径或健康检查端点
            response = requests.get(f"{self.upstream_api_url}/", timeout=5)
            if response.status_code == 200:
                messagebox.showinfo("连接测试", "连接成功!")
            else:
                # 如果根路径不行，尝试/docs路径（FastAPI的文档）
                response = requests.get(f"{self.upstream_api_url}/docs", timeout=5)
                if response.status_code == 200:
                    messagebox.showinfo("连接测试", "连接成功! (API文档可访问)")
                else:
                    messagebox.showerror("连接测试", f"服务器响应异常: {response.status_code}")
        except Exception as e:
            messagebox.showerror("连接测试", f"连接失败: {str(e)}")
    
    def __del__(self):
        """析构函数，清理PyAudio资源"""
        if hasattr(self, 'p'):
            self.p.terminate()

def main():
    root = tk.Tk()
    app = TTSClientGUI(root)
    
    # 设置窗口关闭事件
    def on_closing():
        # 保存当前配置
        app.save_current_config()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()