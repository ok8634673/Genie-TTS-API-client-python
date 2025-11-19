import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
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

class TTSClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("TTS API 客户端")
        self.root.geometry("800x600")
        
        # 配置文件
        self.config_file = "tts_client_config.ini"
        self.config = configparser.ConfigParser()
        
        # 加载配置
        self.load_config()
        
        # API配置 - 使用配置中的值或默认值
        self.base_url = self.config.get('API', 'base_url', fallback="http://127.0.0.1:8000")
        
        # 缓存目录配置
        self.cache_dir = self.config.get('Cache', 'cache_dir', fallback="./audio_cache")
        
        # 确保缓存目录存在
        self.ensure_cache_dir()
        
        # PyAudio实例
        self.p = pyaudio.PyAudio()
        
        # 创建主框架
        self.create_widgets()
        
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
        self.config['API'] = {'base_url': 'http://127.0.0.1:8000'}
        self.config['Cache'] = {'cache_dir': './audio_cache'}
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
        
        # 填充各标签页内容
        self.setup_character_tab()
        self.setup_reference_tab()
        self.setup_tts_tab()
        self.setup_tools_tab()
        
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
        
        ttk.Label(config_frame, text="API地址:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.api_url_entry = ttk.Entry(config_frame, width=30)
        self.api_url_entry.insert(0, self.base_url)
        self.api_url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='we')
        
        ttk.Button(config_frame, text="更新", command=self.update_api_url).grid(row=0, column=2, padx=5, pady=5)
        
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
        file_path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")]
        )
        if file_path:
            self.save_path_entry.delete(0, tk.END)
            self.save_path_entry.insert(0, file_path)
    
    def browse_cache_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.cache_dir_entry.delete(0, tk.END)
            self.cache_dir_entry.insert(0, directory)
    
    def update_api_url(self):
        new_url = self.api_url_entry.get().strip()
        if new_url:
            self.base_url = new_url
            self.update_config('API', 'base_url', new_url)
            messagebox.showinfo("成功", f"API地址已更新为: {new_url}")
    
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
        
        return os.path.join(self.cache_dir, filename)
    
    def api_call(self, endpoint, data=None):
        """通用的API调用方法"""
        try:
            url = f"{self.base_url}{endpoint}"
            self.status_var.set(f"正在调用 {endpoint}...")
            
            headers = {'Content-Type': 'application/json'}
            
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
                        return True, json_response
                    else:
                        self.status_var.set(f"{endpoint} 调用成功 (空响应)")
                        return True, "成功"
                except json.JSONDecodeError as e:
                    # 如果JSON解析失败，但状态码是200，可能返回的是纯文本或其他格式
                    self.status_var.set(f"{endpoint} 调用成功 (非JSON响应)")
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
                return False, error_msg
                
        except requests.exceptions.ConnectionError:
            self.status_var.set("连接错误: 无法连接到服务器")
            return False, "连接错误: 请检查服务器是否运行及API地址是否正确"
        except requests.exceptions.Timeout:
            self.status_var.set("请求超时")
            return False, "请求超时: 服务器响应时间过长"
        except Exception as e:
            self.status_var.set(f"错误: {str(e)}")
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
        
        threading.Thread(target=self._tts_thread, args=(data,), daemon=True).start()
    
    def _tts_thread(self, data):
        success, result = self.api_call("/tts", data)
        if success:
            messagebox.showinfo("成功", "TTS转换完成")
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
        success, result = self.api_call("/tts", data)
        if success:
            try:
                # 使用PyAudio播放音频
                self.play_audio_file(cache_file_path)
            except Exception as e:
                self.status_var.set(f"播放音频失败: {str(e)}")
                messagebox.showerror("错误", f"播放音频失败: {str(e)}")
        else:
            messagebox.showerror("错误", f"TTS转换失败: {result}")
    
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
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                messagebox.showinfo("连接测试", "连接成功!")
            else:
                # 如果根路径不行，尝试/docs路径（FastAPI的文档）
                response = requests.get(f"{self.base_url}/docs", timeout=5)
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