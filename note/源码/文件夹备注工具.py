import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import os
import json
import ctypes
import sys
import threading
from PIL import Image, ImageDraw, ImageFont, ImageTk
import io
import base64

# 记录文件路径
RECORD_FILE = "records.json"
# 状态文件路径
STATE_FILE = "treeview_state.json"
# 用于记录信息的序号
message_count = 0
# 扩展页面是否显示的标志
is_expanded = False
# 存储当前选中路径的权限状态
current_path_permission = True
# 存储当前路径的备注状态
current_folder_status = ""
# 用于防止快速点击导致的闪烁
is_toggling = False

def load_state():
    """加载TreeView状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"expanded_paths": {}}
    return {"expanded_paths": {}}

def save_state(expanded_paths):
    """保存TreeView状态"""
    state = {
        "expanded_paths": expanded_paths
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def load_records():
    if os.path.exists(RECORD_FILE):
        with open(RECORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_records(records):
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

def check_path_permission(path):
    """检查路径权限"""
    desktop_ini_path = os.path.join(path, "desktop.ini")
    if os.path.exists(desktop_ini_path):
        # 只检查权限，不实际修改
        result = os.system(f'attrib "{desktop_ini_path}"')
        return result == 0
    # 如果文件不存在，检查目录权限
    try:
        test_file = os.path.join(path, ".permission_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except:
        return False

def update_folder_status(path):
    """更新文件夹状态显示"""
    global current_path_permission
    desktop_ini_path = os.path.join(path, "desktop.ini")
    if os.path.exists(desktop_ini_path):
        try:
            with open(desktop_ini_path, "r", encoding="mbcs") as f:
                content = f.read()
                if "InfoTip=" in content:
                    folder_note = content.split("InfoTip=")[1].strip()
                    # 更新状态标签
                    folder_status_label.config(text=f"当前文件夹备注: {folder_note}")
                else:
                    folder_status_label.config(text="")
        except:
            folder_status_label.config(text="")
    else:
        folder_status_label.config(text="")

def select_folder():
    global message_count, current_path_permission
    folder = filedialog.askdirectory()
    if folder:
        folder_entry.delete(0, tk.END)
        folder_entry.insert(0, folder)
        
        # 在后台进行权限检查
        def check_permission():
            global current_path_permission
            current_path_permission = check_path_permission(folder)
            # 更新文件夹状态
            update_folder_status(folder)
            
            # 如果历史记录面板已展开，刷新表格数据
            if is_expanded:
                refresh_records()
        
        # 启动后台线程
        threading.Thread(target=check_permission, daemon=True).start()

def create_desktop_ini():
    global message_count
    folder = folder_entry.get()
    comment = comment_entry.get()

    if not folder or not comment:
        message_count += 1
        message_status_label.config(text=f"{message_count}. 错误: 请输入文件夹路径和备注内容！", fg="red")
        return

    desktop_ini_path = os.path.join(folder, "desktop.ini")
    
    # 检查文件夹权限
    if os.path.exists(desktop_ini_path):
        # 去除文件的系统和隐藏属性
        os.system(f'attrib -s -h "{desktop_ini_path}"')
        if not messagebox.askyesno("确认", "该文件夹下已存在 desktop.ini 文件，是否覆盖？"):
            return

    # 生成包含 [ViewState] 部分的内容
    desktop_ini_content = f"[ViewState]\nMode=\nVid=\nFolderType=Generic\n[.ShellClassInfo]\nInfoTip={comment}\n"

    # 使用 ANSI 编码写入文件
    with open(desktop_ini_path, "w", encoding="mbcs") as f:
        f.write(desktop_ini_content)

    # 设置文件属性为系统和隐藏
    FILE_ATTRIBUTE_HIDDEN = 0x02
    FILE_ATTRIBUTE_SYSTEM = 0x04
    ctypes.windll.kernel32.SetFileAttributesW(desktop_ini_path, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)

    # 设置文件夹属性为系统属性
    ctypes.windll.kernel32.SetFileAttributesW(folder, FILE_ATTRIBUTE_SYSTEM)

    records = load_records()
    records.append({"path": folder, "comment": comment})
    save_records(records)

    message_count += 1
    message_status_label.config(text=f"{message_count}. 成功: desktop.ini 文件创建成功！", fg="green")
    
    # 更新当前文件夹备注状态
    update_folder_status(folder)
    
    # 如果历史记录面板已展开，则只刷新表格数据
    if is_expanded:
        refresh_records()

def cancel():
    root.destroy()

def refresh_records():
    """仅刷新历史记录表格数据"""
    # 如果TreeView不存在，则不进行刷新
    if not hasattr(show_records, 'tree'):
        return

    tree = show_records.tree
    
    # 加载状态
    state = load_state()
    expanded_paths = state["expanded_paths"]
    
    # 加载记录
    records = load_records()
    if not records:
        global message_count
        message_count += 1
        message_status_label.config(text=f"{message_count}. 提示: 暂无记录！", fg="blue")
        return

    # 按路径分组记录
    path_groups = {}
    for record in records:
        path = record["path"]
        if path not in path_groups:
            path_groups[path] = []
        path_groups[path].append(record)

    # 使用保存的展开状态
    expanded_states = {path: expanded_paths.get(path, False) for path in path_groups}

    # 清空 Treeview
    for item in tree.get_children():
        tree.delete(item)
        
    # 重新填充数据
    for path, group in path_groups.items():
        latest_record = group[-1]
        prefix = "v" if expanded_states[path] else ">"
        tree.insert('', 'end', values=(prefix, latest_record['path'], latest_record['comment']))
        if expanded_states[path]:
            for record in reversed(group[:-1]):
                indented_path = "   " + record['path']
                tree.insert('', 'end', values=('  ', indented_path, record['comment']))
    
    # 保存状态
    save_state(expanded_paths)
    
    # 刷新当前文件夹备注状态
    folder_path = folder_entry.get()
    if folder_path:
        update_folder_status(folder_path)

def open_path_from_tree(path):
    """打开TreeView中选中的路径"""
    # 去除可能存在的缩进空格
    clean_path = path.strip()
    if os.path.exists(clean_path):
        try:
            os.startfile(clean_path)
            global message_count
            message_count += 1
            message_status_label.config(text=f"{message_count}. 成功: 已打开文件夹 {clean_path}", fg="green")
        except Exception as e:
            message_count += 1
            message_status_label.config(text=f"{message_count}. 错误: 无法打开文件夹 - {str(e)}", fg="red")
    else:
        message_count += 1
        message_status_label.config(text=f"{message_count}. 错误: 文件夹不存在 {clean_path}", fg="red")

def show_records():
    global is_expanded, is_toggling
    
    # 防止快速点击导致的闪烁
    if is_toggling:
        return
    
    is_toggling = True
    
    if not is_expanded:
        # 加载状态
        state = load_state()
        expanded_paths = state["expanded_paths"]
        
        # 如果TreeView已存在，则不需要重建TreeView
        if hasattr(show_records, 'tree'):
            # 只需要显示面板
            expand_frame.pack(side=tk.RIGHT, fill=tk.BOTH)
            root.geometry(f"{expanded_width}x{default_height}")
            expand_button.config(text="历史备注 <<")
            is_expanded = True
            # 刷新一下数据确保显示最新状态
            refresh_records()
            is_toggling = False
            return

        # 加载记录
        records = load_records()
        if not records:
            message_count += 1
            message_status_label.config(text=f"{message_count}. 提示: 暂无记录！", fg="blue")
            is_toggling = False
            return

        # 清空之前的内容
        for widget in expand_frame.winfo_children():
            widget.destroy()

        # 创建 Treeview 表格
        columns = ('展开', '备注路径', '备注内容')
        tree = ttk.Treeview(expand_frame, columns=columns, show='headings')
        show_records.tree = tree  # 保存tree引用

        # 设置列标题
        tree.heading('展开', text=' ')
        tree.heading('备注路径', text='备注路径')
        tree.heading('备注内容', text='备注内容')

        # 设置列宽度
        tree.column('展开', width=50, anchor='center')
        tree.column('备注路径', width=300)
        tree.column('备注内容', width=280)

        tree.pack(fill=tk.BOTH, expand=True)

        # 按路径分组记录
        path_groups = {}
        for record in records:
            path = record["path"]
            if path not in path_groups:
                path_groups[path] = []
            path_groups[path].append(record)

        # 使用保存的展开状态
        expanded_states = {path: expanded_paths.get(path, False) for path in path_groups}

        def toggle_expand(path):
            expanded_states[path] = not expanded_states[path]
            # 保存展开状态
            expanded_paths[path] = expanded_states[path]
            save_state(expanded_paths)
            
            # 刷新表格数据
            refresh_records()

        def on_tree_click(event):
            region = tree.identify_region(event.x, event.y)
            if region == 'cell':
                col = tree.identify_column(event.x)
                if col == '#1':
                    item = tree.identify_row(event.y)
                    path = tree.item(item, 'values')[1].strip()
                    toggle_expand(path)

        def on_tree_double_click(event):
            # 获取双击位置的项目
            item = tree.identify_row(event.y)
            if item:
                # 获取该行的值
                values = tree.item(item, 'values')
                if len(values) >= 2:
                    # 获取路径（第二列）
                    path = values[1]
                    # 打开该路径
                    open_path_from_tree(path)

        def open_folder():
            selected_item = tree.selection()
            if selected_item:
                values = tree.item(selected_item, 'values')
                path = values[1].strip()
                open_path_from_tree(path)

        def delete_record():
            global message_count
            selected_item = tree.selection()
            if selected_item:
                values = tree.item(selected_item, 'values')
                path = values[1].strip()
                comment = values[2]
                if messagebox.askyesno("确认", "确定要删除这条记录吗？"):
                    for group in path_groups.values():
                        for record in group[:]:
                            if record['path'] == path and record['comment'] == comment:
                                group.remove(record)
                                break
                    new_records = [record for group in path_groups.values() for record in group]
                    save_records(new_records)
                    message_count += 1
                    message_status_label.config(text=f"{message_count}. 成功: 记录已删除！", fg="green")
                    # 只刷新表格数据
                    refresh_records()
        
        def open_records_file():
            """打开历史记录文件"""
            global message_count
            if os.path.exists(RECORD_FILE):
                try:
                    os.startfile(RECORD_FILE)
                    message_count += 1
                    message_status_label.config(text=f"{message_count}. 成功: 已打开记录文件", fg="green")
                except Exception as e:
                    message_count += 1
                    message_status_label.config(text=f"{message_count}. 错误: 无法打开记录文件 - {str(e)}", fg="red")
            else:
                message_count += 1
                message_status_label.config(text=f"{message_count}. 错误: 记录文件不存在", fg="red")

        def copy_path(event):
            item = tree.identify_row(event.y)
            col = tree.identify_column(event.x)
            if col == '#2':
                values = tree.item(item, 'values')
                path = values[1].strip()
                root.clipboard_clear()
                root.clipboard_append(path)

        # 绑定点击事件
        tree.bind("<Button-1>", on_tree_click)
        tree.bind("<Double-1>", on_tree_double_click)  # 使用系统双击间隔
        tree.bind("<Control-c>", copy_path)

        # 创建操作按钮
        button_frame = tk.Frame(expand_frame)
        button_frame.pack()
        open_button = tk.Button(button_frame, text="打开文件夹", command=open_folder)
        open_button.pack(side=tk.LEFT)
        delete_button = tk.Button(button_frame, text="删除选中记录", command=delete_record)
        delete_button.pack(side=tk.LEFT)
        open_records_button = tk.Button(button_frame, text="打开记录文件", command=open_records_file)
        open_records_button.pack(side=tk.LEFT)

        # 设置统一的字体大小
        style = ttk.Style()
        font_size = 10
        style.configure("Treeview", font=("Arial", font_size))
        style.configure("Treeview.Heading", font=("Arial", font_size))

        # 初始化 Treeview 数据
        for path, group in path_groups.items():
            latest_record = group[-1]
            prefix = "v" if expanded_states[path] else ">"
            tree.insert('', 'end', values=(prefix, latest_record['path'], latest_record['comment']))
            if expanded_states[path]:
                for record in reversed(group[:-1]):
                    indented_path = "   " + record['path']
                    tree.insert('', 'end', values=('  ', indented_path, record['comment']))

        # 应用统一字体到所有行
        for item in tree.get_children():
            tree.item(item, tags=("UniformFont",))
        tree.tag_configure("UniformFont", font=("Arial", font_size))

        # 保存状态
        save_state(expanded_paths)

        # 先加载内容，再改变窗口大小和显示状态
        expand_frame.pack(side=tk.RIGHT, fill=tk.BOTH)
        root.geometry(f"{expanded_width}x{default_height}")
        expand_button.config(text="历史备注 <<")
        is_expanded = True
    else:
        # 先隐藏内容，再改变窗口大小
        expand_frame.pack_forget()
        root.geometry(f"{default_width}x{default_height}")
        expand_button.config(text="历史备注 >>")
        is_expanded = False
    
    # 重置状态标志
    root.after(100, lambda: setattr(sys.modules[__name__], 'is_toggling', False))

def restart_explorer():
    global message_count
    try:
        # 终止资源管理器进程
        os.system("taskkill /f /im explorer.exe")
        # 重新启动资源管理器
        os.system("start explorer.exe")
        message_count += 1
        message_status_label.config(text=f"{message_count}. 成功: Windows 资源管理器已重启！", fg="green")
    except Exception as e:
        message_count += 1
        message_status_label.config(text=f"{message_count}. 错误: 重启资源管理器时出错 - {str(e)}", fg="red")

def create_about_image():
    """创建关于信息的图片"""
    # 创建一个图像
    width, height = 400, 250
    image = Image.new('RGB', (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(image)
    
    # 尝试加载字体，如果失败则使用默认字体
    try:
        font = ImageFont.truetype("simhei.ttf", 14)
        title_font = ImageFont.truetype("simhei.ttf", 16)
    except:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()
    
    # 绘制边框
    draw.rectangle([0, 0, width-1, height-1], outline=(100, 100, 100))
    
    # 绘制标题
    draw.text((150, 20), "关于本软件", fill=(0, 0, 0), font=title_font)
    
    # 绘制内容
    about_text = [
        "作者13x286 自用&免费分享",
        "第一次分享自己做的东西 很多bug性能也不怎么样",
        "也不打算再改了",
        "转载需注明作者并不设任何门槛",
        "包括但不限于注册网站账号 关注 评论 解压密码等",
        "如果你对于本软件做更新或改bug,更改后的软件",
        "只需要注明原作者与原版软件下载链接即可",
        "本软件只提供一种快捷的备注方式并附源码",
        "用户应当自行判断内容与使用 本人不对此负责"
    ]
    
    y_position = 50
    for line in about_text:
        draw.text((20, y_position), line, fill=(0, 0, 0), font=font)
        y_position += 20
    
    return image

def show_about():
    """显示关于对话框"""
    about_window = tk.Toplevel(root)
    about_window.title("关于")
    about_window.geometry("400x280")
    about_window.resizable(False, False)
    
    # 创建关于信息图片
    about_image = create_about_image()
    
    # 转换为PhotoImage
    photo_image = ImageTk.PhotoImage(about_image)
    
    # 保存图片引用防止被垃圾回收
    show_about.photo_image = photo_image
    
    # 显示图片
    image_label = tk.Label(about_window, image=photo_image)
    image_label.pack(padx=0, pady=0)
    
    # 添加关闭按钮
    close_button = tk.Button(about_window, text="关闭", command=about_window.destroy)
    close_button.pack(pady=5)
    
    # 设置为模态窗口
    about_window.transient(root)
    about_window.grab_set()
    root.wait_window(about_window)

root = tk.Tk()
root.title("Desktop.ini 生成器")

# 设置固定窗口大小
default_width = 580
default_height = 435
expanded_width = 1200

# 设置初始窗口大小并禁用调整
root.geometry(f"{default_width}x{default_height}")
root.resizable(False, False)

# 设置统一字体
default_font = ('Microsoft YaHei UI', 12)
title_font = ('Microsoft YaHei UI', 14)
root.option_add('*Font', default_font)

# 创建主框架，添加较大边距
main_frame = tk.Frame(root)
main_frame.place(x=50, y=30, width=500, height=390)  # 600-50-50=500, 450-30-30=390

# 文件夹路径部分
folder_label = tk.Label(main_frame, text="文件夹路径:", font=title_font)
folder_label.place(x=0, y=0)

path_frame = tk.Frame(main_frame)
path_frame.place(x=0, y=40, width=480, height=40)

folder_entry = tk.Entry(path_frame, font=default_font)
folder_entry.place(x=0, y=0, width=360, height=30)  # 500-120=380

folder_button = tk.Button(path_frame, text="选择文件夹", command=select_folder, font=default_font, width=12)
folder_button.place(x=370, y=0, width=110, height=30)

# 备注输入框
comment_frame = tk.Frame(main_frame)
comment_frame.place(x=0, y=90, width=480, height=30)

comment_label = tk.Label(comment_frame, text="备注内容:", font=title_font)
comment_label.place(x=0, y=0)

# 添加当前文件夹备注状态标签
folder_status_label = tk.Label(comment_frame, text="", font=('Microsoft YaHei UI', 9), anchor='e')
folder_status_label.place(x=180, y=0, width=300, height=30)

comment_entry = tk.Entry(main_frame, font=default_font)
comment_entry.place(x=0, y=130, width=480, height=30)

# 添加消息状态标签
message_status_label = tk.Label(main_frame, text="", font=default_font)
message_status_label.place(x=0, y=170, width=480, height=30)

# 按钮区域
button_frame = tk.Frame(main_frame)
button_frame.place(x=0, y=210, width=480, height=40)

ok_button = tk.Button(button_frame, text="确定", command=create_desktop_ini, font=default_font, width=10)
ok_button.place(x=0, y=0, width=100, height=30)

restart_button = tk.Button(main_frame, text="重启Windows资源管理器", command=restart_explorer, font=default_font)
restart_button.place(x=0, y=260, width=200, height=30)

# 添加"关于"按钮
about_button = tk.Button(main_frame, text="关于", command=show_about, font=default_font)
about_button.place(x=0, y=300, width=100, height=30)

# 创建右下角的历史备注按钮
expand_button = tk.Button(main_frame, text="历史备注 >>", command=show_records, font=default_font, width=12)
expand_button.place(x=380, y=260, width=100, height=30)  # 600-10-100=490, 450-10-30=410

# 扩展页面框架
expand_frame = tk.Frame(root)

# 检查是否有命令行参数
if len(sys.argv) > 1:
    folder_path = sys.argv[1]
    folder_entry.delete(0, tk.END)
    folder_entry.insert(0, folder_path)

root.mainloop()