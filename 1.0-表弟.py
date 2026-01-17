import re
import tkinter as tk
from tkinter import messagebox
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time
import gc
import sys

# ================= 性能优化配置 =================

# 内存管理配置
GC_THRESHOLD = 5000  # 记录数超过这个值时触发垃圾回收
CACHE_SIZE = 1000  # 缓存记录数
BATCH_RENDER_SIZE = 50  # 每批渲染的行数

# ================= 常量定义 =================

class ViewMode(Enum):
    SUMMARY = "summary"
    DETAIL = "detail"
    LOST = "lost"

class SortMode(Enum):
    WEIGHT = "weight"
    EXP = "exp"

@dataclass
class FishingRecord:
    """钓鱼记录数据类"""
    record_type: str  # "capture" 或 "lost"
    time: str
    rod: int
    fish: str
    weight: float
    exp: int = 0
    cost: str = ""
    bait: str = ""
    
    @property
    def is_lost(self) -> bool:
        return self.record_type == "lost"
    
    @property
    def formatted_weight(self) -> str:
        return f"{self.weight:.3f}kg" if self.weight > 0 else "？"
    
    @property
    def formatted_exp(self) -> str:
        return f"经验{self.exp}" if self.exp > 0 else ""

# ================= 字体配置 =================

class FontConfig:
    INPUT = ("微软雅黑", 10)
    TABLE = ("微软雅黑", 12)
    BUTTON = ("微软雅黑", 9)
    TITLE = ("微软雅黑", 12, "bold")
    HEADER = ("微软雅黑", 12, "bold")

# ================= 表格配置 =================

class TableConfig:
    COLUMNS = [
        ("时间", 100, "#444444"),
        ("鱼竿", 80, "#1f4fa3"),
        ("鱼类", 160, "#1e7f3b"),
        ("重量", 120, "#b03030"),
        ("经验", 120, "#6a2ca0"),
        ("耗时", 80, "#555555"),
        ("鱼饵/状态", 160, "#777777")
    ]
    
    COLORS = {
        "normal": "white",
        "lost": "white",
        "header": "#f0f0f0",
        "header_bg": "#f0f0f0"
    }

# ================= 高效解析器 =================

class FishingLogParser:
    """钓鱼日志解析器 - 性能优化版"""
    
    # 预编译正则表达式，提高性能
    HOOK_PATTERN = re.compile(r"鱼上钩了！鱼竿：(\d)，鱼信息:【(.+?)】([\d.]+)(kg|g)")
    CAPTURE_PATTERN = re.compile(
        r"捕获：鱼竿:(\d),【(.+?)】.*?([\d.]+)(公斤|克).*?总经验:(\d+).*?耗时:(\d+)秒.*?鱼饵:(.+)$"
    )
    LOST_PATTERN = re.compile(r"鱼脱钩了！鱼竿：(\d)")
    
    @staticmethod
    def _parse_weight(value: str, unit: str) -> float:
        """解析重量并转换为kg - 内联优化"""
        weight = float(value)
        return weight / 1000 if unit in ("g", "克") else weight
    
    @staticmethod
    def parse_line_fast(line: str) -> Optional[Dict[str, Any]]:
        """快速解析单行日志"""
        if " : " not in line:
            return None
            
        parts = line.split(" : ", 1)
        time = parts[0].strip()
        content = parts[1]
        
        # 顺序匹配，根据前缀快速判断
        if "鱼上钩了" in content:
            match = FishingLogParser.HOOK_PATTERN.search(content)
            if match:
                return {
                    "type": "hook",
                    "time": time,
                    "rod": int(match.group(1)),
                    "fish": match.group(2)[:10],
                    "weight": FishingLogParser._parse_weight(match.group(3), match.group(4))
                }
        
        elif "捕获" in content:
            match = FishingLogParser.CAPTURE_PATTERN.search(content)
            if match:
                return {
                    "type": "capture",
                    "time": time,
                    "rod": int(match.group(1)),
                    "fish": match.group(2)[:10],
                    "weight": FishingLogParser._parse_weight(match.group(3), match.group(4)),
                    "exp": int(match.group(5)),
                    "cost": f"{match.group(6)}秒",
                    "bait": match.group(7)
                }
        
        elif "鱼脱钩了" in content:
            match = FishingLogParser.LOST_PATTERN.search(content)
            if match:
                return {
                    "type": "lost",
                    "time": time,
                    "rod": int(match.group(1)),
                    "fish": "？",
                    "weight": 0.0
                }
        
        return None
    
    @staticmethod
    def parse_text(text: str) -> List[FishingRecord]:
        """解析完整日志文本 - 优化版本"""
        records = []
        hook_cache = {}
        
        lines = text.strip().splitlines()
        total_lines = len(lines)
        
        # 处理进度反馈（每1000行）
        for line_idx, line in enumerate(lines):
            parsed = FishingLogParser.parse_line_fast(line)
            if not parsed:
                continue
                
            if parsed["type"] == "hook":
                hook_cache[parsed["rod"]] = parsed
            elif parsed["type"] == "capture":
                records.append(FishingRecord(
                    record_type="capture",
                    time=parsed["time"],
                    rod=parsed["rod"],
                    fish=parsed["fish"],
                    weight=parsed["weight"],
                    exp=parsed["exp"],
                    cost=parsed["cost"],
                    bait=parsed["bait"]
                ))
                hook_cache.pop(parsed["rod"], None)
            elif parsed["type"] == "lost":
                rod = parsed["rod"]
                hook_data = hook_cache.pop(rod, None)
                if hook_data:
                    records.append(FishingRecord(
                        record_type="lost",
                        time=hook_data["time"],
                        rod=rod,
                        fish=hook_data["fish"],
                        weight=hook_data["weight"],
                        bait="脱钩"
                    ))
                else:
                    records.append(FishingRecord(
                        record_type="lost",
                        time=parsed["time"],
                        rod=rod,
                        fish="？",
                        weight=0.0,
                        bait="脱钩"
                    ))
            
            # 每处理1000行进行一次微调，防止UI卡死
            if line_idx % 1000 == 0 and line_idx > 0:
                time.sleep(0.001)  # 短暂释放控制权
        
        return records

# ================= 缓存管理器 =================

class RecordCache:
    """记录缓存管理器"""
    
    def __init__(self, max_size: int = CACHE_SIZE):
        self.max_size = max_size
        self.cache: Dict[str, List[FishingRecord]] = {}
        
    def get(self, key: str) -> Optional[List[FishingRecord]]:
        """获取缓存"""
        return self.cache.get(key)
    
    def set(self, key: str, records: List[FishingRecord]):
        """设置缓存"""
        if len(self.cache) >= self.max_size:
            # 移除第一个条目（最简单的淘汰策略）
            first_key = next(iter(self.cache))
            del self.cache[first_key]
        self.cache[key] = records
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()

# ================= 高效表格组件 =================

class TableRow:
    """表格行组件 - 内存优化版"""
    
    def __init__(self, parent, values: List[str], is_lost: bool = False):
        self.frame = tk.Frame(parent, bg=TableConfig.COLORS["normal"])
        self.frame.pack(fill=tk.X)
        
        for i, (text, width, color) in enumerate(TableConfig.COLUMNS):
            fg_color = "#cc0000" if (is_lost and text == "鱼饵/状态" and values[i] == "脱钩") else color
            label = tk.Label(
                self.frame,
                text=values[i] if i < len(values) else "",
                width=width // 10,
                anchor="w",
                font=FontConfig.TABLE,
                fg=fg_color,
                bg=TableConfig.COLORS["normal"]
            )
            label.pack(side=tk.LEFT, padx=2)

# ================= 内存优化主应用 =================

class FishingLogAnalyzer:
    """钓鱼日志分析器主应用 - 稳定优化版"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("钓鱼日志分析器")
        self.root.geometry("1000x750")
        
        # 防止窗口缩放问题
        self.root.minsize(800, 600)
        
        # 初始化缓存
        self.cache = RecordCache()
        
        # 初始化数据
        self.all_records: List[FishingRecord] = []
        self.current_records: List[FishingRecord] = []
        self.current_view: ViewMode = ViewMode.SUMMARY
        self.sort_state: Dict[SortMode, bool] = {
            SortMode.WEIGHT: False,
            SortMode.EXP: False
        }
        
        # 鱼竿选择状态
        self.rod_vars: Dict[int, tk.BooleanVar] = {}
        
        # UI组件引用
        self.header_frame = None
        
        # 内存管理
        self.render_count = 0
        
        # 构建UI
        self._setup_ui()
        
    def _setup_ui(self):
        """设置用户界面"""
        # 主容器
        main_container = tk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 优化布局权重
        main_container.grid_rowconfigure(3, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        # 创建UI组件
        self._create_input_section(main_container, row=0)
        self._create_control_section(main_container, row=1)
        self._create_filter_section(main_container, row=2)
        self._create_table_section(main_container, row=3)
    
    def _create_input_section(self, parent, row):
        """创建输入区域"""
        input_frame = tk.LabelFrame(parent, text=" 钓鱼日志输入 ", font=FontConfig.BUTTON)
        input_frame.grid(row=row, column=0, sticky="ew", padx=5, pady=(0, 5))
        input_frame.grid_columnconfigure(0, weight=1)
        
        text_frame = tk.Frame(input_frame)
        text_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        text_frame.grid_columnconfigure(0, weight=1)
        
        self.input_box = tk.Text(text_frame, height=8, font=FontConfig.INPUT, wrap="word")
        input_scroll = tk.Scrollbar(text_frame, orient="vertical", command=self.input_box.yview)
        self.input_box.configure(yscrollcommand=input_scroll.set)
        
        self.input_box.grid(row=0, column=0, sticky="nsew")
        input_scroll.grid(row=0, column=1, sticky="ns")
        
        # 优化绑定
        self.input_box.bind("<MouseWheel>", self._on_text_scroll)
        
        # 按钮区域
        button_frame = tk.Frame(input_frame)
        button_frame.grid(row=1, column=0, sticky="e")
        
        tk.Button(button_frame, text="清空输入", command=self.clear_input, 
                  font=FontConfig.BUTTON, width=8).pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="分析日志", command=self.analyze,
                  font=FontConfig.BUTTON, bg="#4CAF50", fg="white", width=8).pack(side=tk.LEFT, padx=2)
    
    def _create_control_section(self, parent, row):
        """创建控制按钮区域"""
        control_frame = tk.Frame(parent)
        control_frame.grid(row=row, column=0, sticky="w", padx=5, pady=(0, 5))
        
        buttons = [
            ("🎣 鱼获记录", self.show_detail, "#4CAF50"),
            ("❌ 脱钩记录", self.show_lost, "#f44336"),
        ]
        
        for text, command, color in buttons:
            btn = tk.Button(control_frame, text=text, command=command, 
                          font=FontConfig.BUTTON, bg=color, fg="white", relief="raised", padx=10)
            btn.pack(side=tk.LEFT, padx=2)
    
    def _create_filter_section(self, parent, row):
        """创建过滤和排序区域"""
        filter_frame = tk.Frame(parent)
        filter_frame.grid(row=row, column=0, sticky="w", padx=20, pady=(0, 5))
        
        # 排序按钮
        sort_frame = tk.Frame(filter_frame)
        sort_frame.pack(side=tk.LEFT, padx=(0, 40))
        
        tk.Label(sort_frame, text="排序:", font=FontConfig.BUTTON).pack(side=tk.LEFT, padx=(0, 8))
        
        sort_buttons = [
            ("重量", self.sort_by_weight),
            ("经验", self.sort_by_exp),
        ]
        
        for text, command in sort_buttons:
            btn = tk.Button(sort_frame, text=text, command=command, 
                          font=FontConfig.BUTTON, relief="flat", bg="#e0e0e0",
                          activebackground="#d0d0d0", padx=12, bd=1, highlightthickness=0)
            btn.pack(side=tk.LEFT, padx=3)
        
        # 鱼竿选择
        rod_frame = tk.Frame(filter_frame)
        rod_frame.pack(side=tk.LEFT)
        
        tk.Label(rod_frame, text="鱼竿:", font=FontConfig.BUTTON).pack(side=tk.LEFT, padx=(0, 8))
        
        # 批量创建鱼竿选择按钮
        for i in range(1, 6):
            var = tk.BooleanVar(value=True)
            self.rod_vars[i] = var
            
            cb = tk.Checkbutton(
                rod_frame, 
                text=f"{i}", 
                variable=var,
                command=self._apply_current_sort, 
                font=FontConfig.BUTTON,
                indicatoron=False,
                width=3,
                height=1,
                relief="raised",
                bg="#f8f8f8",
                activebackground="#e8e8e8",
                selectcolor="#4CAF50",
                bd=1
            )
            cb.pack(side=tk.LEFT, padx=2)
    
    def _create_table_section(self, parent, row):
        """创建表格显示区域"""
        table_main_frame = tk.LabelFrame(parent, text=" 记录详情 ", font=FontConfig.BUTTON)
        table_main_frame.grid(row=row, column=0, sticky="nsew", padx=5, pady=(0, 5))
        table_main_frame.grid_rowconfigure(1, weight=1)
        table_main_frame.grid_columnconfigure(0, weight=1)
        
        # 固定标题行
        self.header_frame = tk.Frame(table_main_frame, bg=TableConfig.COLORS["header_bg"])
        
        # 批量创建标题标签
        for text, width, color in TableConfig.COLUMNS:
            label = tk.Label(
                self.header_frame,
                text=text,
                width=width // 10,
                anchor="w",
                font=FontConfig.HEADER,
                fg=color,
                bg=TableConfig.COLORS["header_bg"],
                relief="ridge",
                bd=1
            )
            label.pack(side=tk.LEFT, padx=2)
        
        # 创建Canvas和滚动条
        canvas_frame = tk.Frame(table_main_frame)
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=0)
        vsb = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        
        # 创建表格内容容器
        self.table_container = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.table_container, anchor="nw")
        
        # 优化事件绑定
        self.table_container.bind("<Configure>", self._on_table_configure)
        self.canvas.bind("<Enter>", self._bind_canvas_scroll)
        self.canvas.bind("<Leave>", self._unbind_canvas_scroll)
    
    def _on_table_configure(self, event):
        """表格配置变化时更新滚动区域"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _bind_canvas_scroll(self, event):
        """绑定Canvas滚动"""
        self.canvas.bind_all("<MouseWheel>", self._on_canvas_scroll)
    
    def _unbind_canvas_scroll(self, event):
        """解绑Canvas滚动"""
        self.canvas.unbind_all("<MouseWheel>")
    
    def _on_canvas_scroll(self, event):
        """Canvas滚动处理"""
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
    
    def _on_text_scroll(self, event):
        """文本框滚动处理"""
        self.input_box.yview_scroll(int(-event.delta / 120), "units")
        return "break"
    
    # ================= 核心功能 =================
    
    def get_selected_rods(self) -> List[int]:
        """获取选中的鱼竿列表"""
        return [rod for rod, var in self.rod_vars.items() if var.get()]
    
    def clear_table(self):
        """清空表格内容 - 内存优化"""
        for widget in self.table_container.winfo_children():
            widget.destroy()
        
        # 定期垃圾回收
        self.render_count += 1
        if self.render_count % 50 == 0:
            gc.collect()
    
    def add_record_row_batch(self, records: List[FishingRecord]):
        """批量添加记录到表格 - 提高渲染效率"""
        for record in records:
            if record.is_lost:
                values = [
                    record.time,
                    f"鱼竿{record.rod}",
                    record.fish,
                    record.formatted_weight,
                    "",
                    "",
                    record.bait
                ]
                TableRow(self.table_container, values, is_lost=True)
            else:
                values = [
                    record.time,
                    f"鱼竿{record.rod}",
                    record.fish,
                    record.formatted_weight,
                    record.formatted_exp,
                    record.cost,
                    record.bait
                ]
                TableRow(self.table_container, values)
            
            # 每渲染一定数量后更新UI，防止卡顿
            if len(self.table_container.winfo_children()) % BATCH_RENDER_SIZE == 0:
                self.root.update_idletasks()
    
    def _apply_current_sort(self):
        """应用当前排序状态"""
        if not self.current_records or self.current_view == ViewMode.SUMMARY:
            return
        
        # 获取当前排序状态
        if self.sort_state[SortMode.WEIGHT]:
            reverse = self.sort_state[SortMode.WEIGHT]
            self.current_records.sort(key=lambda x: x.weight, reverse=reverse)
        elif self.current_view == ViewMode.DETAIL and self.sort_state[SortMode.EXP]:
            reverse = self.sort_state[SortMode.EXP]
            self.current_records.sort(key=lambda x: x.exp, reverse=reverse)
        
        # 重新渲染
        self._render_data()
    
    def _render_data(self):
        """渲染当前数据"""
        self.clear_table()
        
        selected_rods = self.get_selected_rods()
        if not selected_rods:
            self._show_message("请至少选择一个鱼竿")
            return
        
        # 显示表格标题行
        if self.current_view != ViewMode.SUMMARY:
            self._show_table_header()
            self.header_frame.grid(row=0, column=0, sticky="ew")
        
        # 筛选记录
        filtered_records = []
        for record in self.current_records:
            if record.rod in selected_rods:
                filtered_records.append(record)
        
        # 分批渲染
        self.add_record_row_batch(filtered_records)
        self._update_scroll()
        
        # 内存优化
        if len(self.all_records) > GC_THRESHOLD:
            gc.collect()
    
    def _update_scroll(self):
        """更新滚动区域"""
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0)
    
    def _show_table_header(self):
        """显示表格标题行"""
        if self.header_frame:
            self.header_frame.grid(row=0, column=0, sticky="ew")
    
    def _hide_table_header(self):
        """隐藏表格标题行"""
        if self.header_frame:
            self.header_frame.grid_forget()
    
    def _show_message(self, message: str, title: str = "提示"):
        """显示消息"""
        tk.Label(
            self.table_container,
            text=message,
            font=FontConfig.TABLE,
            fg="#666",
            bg="white"
        ).pack(pady=20)
    
    def analyze(self):
        """分析日志"""
        text = self.input_box.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先粘贴钓鱼日志文本")
            return
        
        try:
            # 显示解析中提示
            self.clear_table()
            self._show_message("正在解析日志，请稍候...")
            self.root.update()
            
            start_time = time.time()
            self.all_records = FishingLogParser.parse_text(text)
            parse_time = time.time() - start_time
            
            if not self.all_records:
                messagebox.showinfo("提示", "未找到有效的钓鱼记录")
                self.show_summary()
                return
            
            # 缓存结果
            cache_key = str(hash(text))
            self.cache.set(cache_key, self.all_records)
            
            # 显示统计信息
            self.show_summary()
            
            # 显示成功消息
            elapsed_time = parse_time
            if len(self.all_records) > 1000:
                messagebox.showinfo("成功", 
                    f"成功解析 {len(self.all_records)} 条记录\n"
                    f"解析耗时: {elapsed_time:.2f}秒\n"
                    f"平均速度: {len(self.all_records)/elapsed_time:.0f}条/秒")
            else:
                messagebox.showinfo("成功", 
                    f"成功解析 {len(self.all_records)} 条记录\n"
                    f"解析耗时: {elapsed_time:.2f}秒")
            
        except Exception as e:
            messagebox.showerror("解析错误", f"解析日志时出错:\n{str(e)}")
            self.show_summary()
    
    def clear_input(self):
        """清空输入框"""
        self.input_box.delete("1.0", tk.END)
    
    def show_detail(self):
        """显示详细记录"""
        if not self.all_records:
            messagebox.showwarning("提示", "请先解析日志")
            return
            
        self.current_view = ViewMode.DETAIL
        self.current_records = [r for r in self.all_records if not r.is_lost]
        
        # 应用当前排序状态
        self._apply_current_sort()
    
    def show_lost(self):
        """显示脱钩记录"""
        if not self.all_records:
            messagebox.showwarning("提示", "请先解析日志")
            return
            
        self.current_view = ViewMode.LOST
        self.current_records = [r for r in self.all_records if r.is_lost]
        
        # 应用当前排序状态
        if self.sort_state[SortMode.WEIGHT]:
            reverse = self.sort_state[SortMode.WEIGHT]
            self.current_records.sort(key=lambda x: x.weight, reverse=reverse)
        
        self._render_data()
    
    def show_summary(self):
        """显示汇总统计"""
        self.current_view = ViewMode.SUMMARY
        self.clear_table()
        
        # 首页不显示表格标题行
        self._hide_table_header()
        
        selected_rods = self.get_selected_rods()
        if not selected_rods:
            self._show_message("请至少选择一个鱼竿")
            return
        
        # 计算统计数据
        capture_records = [r for r in self.all_records 
                         if not r.is_lost and r.rod in selected_rods]
        
        total_weight = sum(r.weight for r in capture_records)
        total_exp = sum(r.exp for r in capture_records)
        total_count = len(capture_records)
        
        lost_count = len([r for r in self.all_records 
                         if r.is_lost and r.rod in selected_rods])
        
        # 按鱼类统计
        fish_stats = {}
        for r in capture_records:
            if r.fish not in fish_stats:
                fish_stats[r.fish] = [0, 0.0]
            fish_stats[r.fish][0] += 1
            fish_stats[r.fish][1] += r.weight
        
        # 显示汇总信息
        summary_frame = tk.Frame(self.table_container, bg="white")
        summary_frame.pack(fill=tk.X, pady=10)
        
        stats = [
            ("总捕获数", f"{total_count} 条"),
            ("总重量", f"{total_weight:.3f} kg"),
            ("总经验", f"{total_exp} 点"),
            ("脱钩数", f"{lost_count} 次"),
            ("成功率", f"{(total_count/(total_count+lost_count)*100):.1f}%" 
             if total_count+lost_count > 0 else "0%")
        ]
        
        for i, (label, value) in enumerate(stats):
            frame = tk.Frame(summary_frame, bg="white")
            frame.pack(side=tk.LEFT, padx=20)
            
            tk.Label(frame, text=label, font=FontConfig.BUTTON, 
                    fg="#666", bg="white").pack()
            tk.Label(frame, text=value, font=("微软雅黑", 14, "bold"), 
                    fg="#2196F3", bg="white").pack()
        
        # 显示鱼类统计
        if fish_stats:
            tk.Label(self.table_container, text="🐟 鱼类统计", 
                    font=FontConfig.TITLE, bg="white").pack(anchor="w", pady=(20, 5))
            
            # 创建带表头的鱼类统计表格
            stats_header = tk.Frame(self.table_container, bg="white")
            stats_header.pack(fill=tk.X, padx=10, pady=(0, 5))
            
            tk.Label(stats_header, text="鱼类", width=15, anchor="w", 
                    font=FontConfig.HEADER, fg="#333", bg="white").pack(side=tk.LEFT)
            tk.Label(stats_header, text="数量", width=8, anchor="center", 
                    font=FontConfig.HEADER, fg="#333", bg="white").pack(side=tk.LEFT, padx=10)
            tk.Label(stats_header, text="总重量", width=10, anchor="center", 
                    font=FontConfig.HEADER, fg="#333", bg="white").pack(side=tk.LEFT)
            
            # 渲染鱼类统计
            fish_items = sorted(fish_stats.items(), key=lambda x: x[1][1], reverse=True)
            for fish, (count, total_weight_fish) in fish_items:
                frame = tk.Frame(self.table_container, bg="white")
                frame.pack(fill=tk.X, padx=10, pady=2)
                
                tk.Label(frame, text=fish, width=15, anchor="w", 
                        font=FontConfig.TABLE, bg="white").pack(side=tk.LEFT)
                tk.Label(frame, text=f"{count} 条", width=8, anchor="center",
                        font=FontConfig.TABLE, fg="#4CAF50", bg="white").pack(side=tk.LEFT, padx=10)
                tk.Label(frame, text=f"{total_weight_fish:.3f} kg", width=10, anchor="center",
                        font=FontConfig.TABLE, fg="#FF9800", bg="white").pack(side=tk.LEFT)
        
        self._update_scroll()
    
    def sort_by_weight(self):
        """按重量排序"""
        if not self.current_records or self.current_view == ViewMode.SUMMARY:
            return
        
        # 切换排序方向
        self.sort_state[SortMode.WEIGHT] = not self.sort_state[SortMode.WEIGHT]
        self.sort_state[SortMode.EXP] = False
        
        reverse = self.sort_state[SortMode.WEIGHT]
        
        # 使用内置排序
        self.current_records.sort(key=lambda x: x.weight, reverse=reverse)
        
        self._render_data()
    
    def sort_by_exp(self):
        """按经验排序"""
        if not self.current_records or self.current_view != ViewMode.DETAIL:
            return
        
        # 切换排序方向
        self.sort_state[SortMode.EXP] = not self.sort_state[SortMode.EXP]
        self.sort_state[SortMode.WEIGHT] = False
        
        reverse = self.sort_state[SortMode.EXP]
        
        # 使用内置排序
        self.current_records.sort(key=lambda x: x.exp, reverse=reverse)
        
        self._render_data()
    
    def run(self):
        """运行应用"""
        try:
            # 设置窗口最小化时处理
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.mainloop()
        except Exception as e:
            print(f"程序运行错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_close(self):
        """关闭窗口时的清理"""
        self.cache.clear()
        gc.collect()
        self.root.destroy()

# ================= 程序入口 =================

def main():
    """主函数"""
    try:
        app = FishingLogAnalyzer()
        app.run()
    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按Enter键退出...")

if __name__ == "__main__":
    main()