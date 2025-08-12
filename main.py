from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.properties import ObjectProperty, StringProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.text import LabelBase
from kivy.config import Config
from kivy.metrics import dp
import sqlite3
import os
import time
import io
import re
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from jnius import autoclass
import requests
from threading import Thread
import threading
from functools import wraps

from kivy.graphics.texture import Texture
import numpy as np
from PIL import Image

if platform == 'android':
    from android.permissions import request_permissions, Permission
    from android.storage import app_storage_path
else:
    request_permissions = lambda *args: None
    Permission = type('Permission', (), {'CAMERA': 'CAMERA'})
    app_storage_path = lambda: '.'

Config.set('kivy', 'keyboard_mode', 'system')
Config.set('kivy', 'keyboard_layout', 'default')

def load_font():
    font_paths = [
        os.path.join('assets/font', 'simhei.ttf'),
        os.path.join(os.path.dirname(__file__), 'font', 'simhei.ttf'),
        '/usr/share/fonts/truetype/simhei.ttf',
        'C:/Windows/Fonts/simhei.ttf'
    ]
    
    loaded = False
    for path in font_paths:
        try:
            if os.path.exists(path):
                LabelBase.register(name='simhei', fn_regular=path)
                print(f"成功加载字体: {path}")
                loaded = True
                break
        except Exception as e:
            print(f"尝试加载字体 {path} 失败: {e}")
    
    if not loaded:
        print("警告: 未能加载simhei字体，将使用默认字体")

load_font()

class AssetDatabase:
    def __init__(self, db_path='assets.db'):
        self.db_path = db_path
        self._local = threading.local()
        self._create_tables()
    
    def _get_connection(self):
        if not hasattr(self._local, 'conn') or not self._local.conn:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    def _create_tables(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL UNIQUE,
            asset_name TEXT,
            asset_type TEXT,
            user TEXT,
            location TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_id ON assets(asset_id)')
        conn.commit()
        conn.close()
    
    def thread_safe(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            conn = self._get_connection()
            try:
                result = func(self, conn, *args, **kwargs)
                conn.commit()
                return result
            except Exception as e:
                conn.rollback()
                raise e
        return wrapper
    
    @thread_safe
    def add_asset(self, conn, asset_data):
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO assets (asset_id, asset_name, asset_type, user, location, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            asset_data.get('asset_id', ''),
            asset_data.get('asset_name', ''),
            asset_data.get('asset_type', ''),
            asset_data.get('user', ''),
            asset_data.get('location', ''),
            asset_data.get('notes', '')
        ))
        return cursor.lastrowid
    
    @thread_safe
    def get_asset_by_id(self, conn, asset_id):
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM assets WHERE asset_id = ?', (asset_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @thread_safe
    def get_assets(self, conn, filters=None, limit=None, offset=None):
        query = 'SELECT * FROM assets'
        params = []
        
        if filters:
            conditions = []
            for field, value in filters.items():
                if value:
                    conditions.append(f"{field} = ?")
                    params.append(value)
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY id ASC'
        
        if limit is not None:
            query += ' LIMIT ?'
            params.append(limit)
            if offset is not None:
                query += ' OFFSET ?'
                params.append(offset)
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    @thread_safe
    def get_distinct_values(self, conn, field):
        cursor = conn.cursor()
        cursor.execute(f'SELECT DISTINCT {field} FROM assets WHERE {field} != "" ORDER BY {field}')
        return [row[0] for row in cursor.fetchall()]
    
    @thread_safe
    def update_asset(self, conn, asset_id, update_data):
        cursor = conn.cursor()
        set_clause = ', '.join([f"{k} = ?" for k in update_data.keys()])
        values = list(update_data.values())
        values.append(asset_id)
        
        cursor.execute(f'''
        UPDATE assets 
        SET {set_clause}
        WHERE asset_id = ?
        ''', values)
        return cursor.rowcount
    
    @thread_safe
    def delete_asset(self, conn, asset_id):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
        return cursor.rowcount
    
    def close_all(self):
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            del self._local.conn
    
    def __del__(self):
        self.close_all()

    def export_to_excel(self, file_path):
        assets = self.get_assets()
        
        if not assets:
            raise ValueError("没有数据可导出")
        
        df = pd.DataFrame(assets)
        df = df[['id', 'asset_id', 'asset_name', 'asset_type', 'user', 'location', 'notes']]
        
        wb = Workbook()
        ws = wb.active
        ws.title = "资产数据"
        
        headers = ['序号', '资产编号', '资产名称', '资产分类', '使用人', '存放地点', '备注']
        ws.append(headers)
        
        for col in range(1, 8):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

        for _, row in df.iterrows():
            ws.append(row.tolist())

        column_widths = {
            'A': 6,   # 序号
            'B': 25,  # 资产编号
            'C': 25,  # 资产名称
            'D': 25,  # 资产分类
            'E': 15,  # 使用人
            'F': 20,  # 存放地点
            'G': 20   # 备注
        }
        
        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = width
        
        wb.save(file_path)
    
    def import_from_excel(self, file_path):
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
            
            required_columns = ['资产编号', '资产名称', '资产分类', '使用人', '存放地点', '备注']
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"Excel文件中缺少必要列: {col}")
            
            imported_count = 0
            updated_count = 0
            
            for _, row in df.iterrows():
                def process_cell(value):
                    if pd.isna(value):
                        return ''
                    return str(value).strip()

                asset_data = {
                    'asset_id': process_cell(row['资产编号']),
                    'asset_name': process_cell(row['资产名称']),
                    'asset_type': process_cell(row['资产分类']),
                    'user': process_cell(row['使用人']),
                    'location': process_cell(row['存放地点']),
                    'notes': process_cell(row['备注'])
                }
                
                if not asset_data['asset_id']:
                    continue
                
                existing = self.get_asset_by_id(asset_data['asset_id'])
                
                if existing:
                    self.update_asset(asset_data['asset_id'], asset_data)
                    updated_count += 1
                else:
                    self.add_asset(asset_data)
                    imported_count += 1
            
            return imported_count, updated_count
            
        except Exception as e:
            raise ValueError(f"导入失败: {str(e)}")

class ScannerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.camera = None
        self.scanning = False
        self.scan_event = None
        self.scan_interval = 5.0
        self.permissions_granted = False
        self.last_capture_time = 0
        self.capture_count = 0
        Clock.schedule_once(self.delayed_init, 1)

    def show_message(self, title="提示", message="", is_error=False):
        def show(dt):
            try:
                popup = Popup(
                    title=title,
                    title_font='simhei',
                    size_hint=(0.8, 0.4),
                    title_color=(1, 0, 0, 1) if is_error else (0, 0.5, 0, 1)
                )
                content = BoxLayout(orientation='vertical', padding=10)
                content.add_widget(Label(text=message, font_name='simhei'))
                btn = Button(text='关闭', size_hint=(1, 0.3), font_name='simhei')
                btn.bind(on_press=popup.dismiss)
                content.add_widget(btn)
                popup.content = content
                popup.open()
            except Exception as e:
                print(f"显示消息失败: {str(e)}")
        
        Clock.schedule_once(show)

    def show_error(self, message):
        def show(dt):
            try:
                popup = Popup(
                    title='错误',
                    title_font='simhei',
                    size_hint=(0.8, 0.4),
                    title_color=(1, 0, 0, 1)
                )
                content = BoxLayout(orientation='vertical', padding=10)
                content.add_widget(Label(text=message, font_name='simhei'))
                btn = Button(text='关闭', size_hint=(1, 0.3), font_name='simhei')
                btn.bind(on_press=popup.dismiss)
                content.add_widget(btn)
                popup.content = content
                popup.open()
            except Exception as e:
                print(f"显示错误失败: {str(e)}")
        
        Clock.schedule_once(show)

    def delayed_init(self, dt):
        if platform == 'android':
            self.request_android_permissions()
        else:
            self.permissions_granted = True
            self.init_components()

    def request_android_permissions(self):
        from android.permissions import request_permissions, Permission, check_permission
        
        def callback(permissions, results):
            if all(results):
                self.permissions_granted = True
                Clock.schedule_once(self.init_components, 0.5)
            else:
                self.show_message("错误", "需要相机和存储权限才能使用扫描功能")
        
        required_permissions = [
            Permission.CAMERA,
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_EXTERNAL_STORAGE
        ]

        if all(check_permission(p) for p in required_permissions):
            self.permissions_granted = True
            Clock.schedule_once(self.init_components, 0.5)
        else:
            request_permissions(required_permissions, callback)

    def init_components(self, dt=None):
        try:
            self.init_camera()
        except Exception as e:
            self.show_message("错误", f"初始化失败: {str(e)}")

    def ocr_space(self, image_path):
        try:
            with open(image_path, 'rb') as f:
                response = requests.post(
                    'https://api.ocr.space/parse/image',
                    files={'file': f},
                    data={
                        'apikey': 'K87528338888957',  #请填入自己申请的免费api
                        'language': 'eng',
                        'OCREngine': 2,  # 使用引擎2（更准确）
                        'scale': True    # 启用自动缩放
                    }
                )
            
            raw_text = response.json()['ParsedResults'][0]['ParsedText']
            return self._clean_ocr_result(raw_text)
        except Exception as e:
            print(f"OCR 错误: {e}")
            return None

    def _clean_ocr_result(self, text):
        if not text:
            return None
        
        text = re.sub(r'^[^a-zA-Z0-9]+', '', text)
        
        text = re.sub(r'[^a-zA-Z0-9]+$', '', text)
        
        replacements = {
            '□': '', 
            '�': '',
            'F:': '',
            '|': 'I',
            '[': 'I',
            ']': 'I'
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        asset_pattern = re.compile(r'([A-Z]{2,5}\d{8,15})')
        match = asset_pattern.search(text)
        if match:
            return match.group(1)
        
        return text.strip().upper()

    def _enhance_image(self, img):
        from PIL import ImageEnhance, ImageFilter, ImageOps
        import math

        width, height = img.size
        img = img.crop((
            int(width * 0.1), 
            int(height * 0.1),
            int(width * 0.9),
            int(height * 0.9)
        )).resize((width, height), Image.LANCZOS)

        def is_blurry(image):
            return image.filter(ImageFilter.FIND_EDGES).histogram()[0] > 50000
        
        if is_blurry(img):
            self.show_message("图像模糊，请保持适当距离")
            return None

        sharpness_factor = 1.5 if img.width < 1000 else 2.5
        img = ImageEnhance.Sharpness(img).enhance(sharpness_factor)

        img = img.convert('L')

        def clahe_pillow(image, clip_limit=2.0, grid_size=8):
            width, height = image.size
            grid_w, grid_h = width // grid_size, height // grid_size

            for i in range(grid_size):
                for j in range(grid_size):
                    box = (
                        i * grid_w,
                        j * grid_h,
                        (i + 1) * grid_w if i < grid_size - 1 else width,
                        (j + 1) * grid_h if j < grid_size - 1 else height
                    )
                    region = image.crop(box)
                    hist = region.histogram()
                    
                    cdf = [sum(hist[:i+1]) for i in range(256)]
                    cdf_min = min(cdf)
                    cdf_max = max(cdf)

                    if clip_limit > 0:
                        excess = sum(max(count - clip_limit, 0) for count in hist)
                        bin_incr = excess // 256
                        remainder = excess % 256
                        
                        hist = [
                            min(count, clip_limit) + bin_incr + (1 if i < remainder else 0)
                            for i, count in enumerate(hist)
                        ]
                    
                    region = region.point(lambda x: int(255 * (cdf[x] - cdf_min) / (cdf_max - cdf_min)))
                    image.paste(region, box)
            return image

        img = clahe_pillow(img, clip_limit=3.0, grid_size=8)

        sharpness = max(1.0, min(3.0, 1.5 + math.log10(img.width / 500)))
        img = ImageEnhance.Sharpness(img).enhance(sharpness)

        def smart_binarize(pixel):
            base_thresh = 180
            if pixel < 80:
                return 0 if pixel < base_thresh - 30 else 255
            elif pixel > 200:
                return 0 if pixel < base_thresh + 20 else 255
            else:
                return 0 if pixel < base_thresh else 255
        img = img.point(smart_binarize)

        for _ in range(2):
            img = img.filter(ImageFilter.ModeFilter(size=3))
            img = img.filter(ImageFilter.MedianFilter(size=2))

        original_size = img.size
        img = img.resize(
            (img.width * 2, img.height * 2),
            resample=Image.LANCZOS
        )

        img = img.filter(ImageFilter.UnsharpMask(
            radius=2,
            percent=150,
            threshold=3
        ))
        
        img = img.resize(original_size, Image.LANCZOS)

        return img

    def save_to_gallery(self, img):
        from jnius import autoclass, cast
        from android import mActivity
        import time

        Context = mActivity.getApplicationContext()
        Environment = autoclass('android.os.Environment')
        MediaStore = autoclass('android.provider.MediaStore')
        ContentValues = autoclass('android.content.ContentValues')
        Images = autoclass('android.provider.MediaStore$Images')
        Media = autoclass('android.provider.MediaStore$Images$Media')
        
        filename = f"SCAN_{int(time.time())}.png"
        
        values = ContentValues()
        values.put("_display_name", filename)
        values.put("mime_type", "image/png")
        
        if hasattr(Environment, 'DIRECTORY_PICTURES'):
            values.put("relative_path", Environment.DIRECTORY_PICTURES + "/AssetScanner")

        try:
            resolver = Context.getContentResolver()
            uri = resolver.insert(Media.EXTERNAL_CONTENT_URI, values)
            
            if uri:
                output_stream = resolver.openOutputStream(uri)
                img.save(output_stream, format='PNG')
                output_stream.close()
                
                Intent = autoclass('android.content.Intent')
                intent = Intent(Intent.ACTION_MEDIA_SCANNER_SCAN_FILE)
                intent.setData(uri)
                mActivity.sendBroadcast(intent)
                
                print(f"✅ 图片已保存到相册，URI: {uri.toString()}")
                return True
                
        except Exception as e:
            print(f"❌ 保存失败: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return False

    def correct_image_orientation(self, img):
        from PIL import ImageOps
        
        if platform == 'android':
            try:
                from jnius import autoclass
                Build = autoclass('android.os.Build')
                
                if "samsung" in Build.MANUFACTURER.lower():
                    img = img.transpose(Image.FLIP_LEFT_RIGHT).rotate(270)
                else:
                    img = ImageOps.mirror(img).rotate(90)
                    
            except:
                img = ImageOps.mirror(img).rotate(90)
        
        return img

    def _enhance_image(self, img):
        from PIL import ImageEnhance, ImageFilter, ImageOps
        
        img = img.convert('L')
        
        img = ImageOps.autocontrast(img, cutoff=3)

        def adaptive_binarize(pixel):
            return 0 if pixel < 180 else 255
        img = img.point(adaptive_binarize)
        
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        img = img.filter(ImageFilter.SHARPEN)

        img = img.resize((img.width*2, img.height*2), Image.LANCZOS)
        
        return img

    def _get_optimal_distance(self, img_width, text_length):
        base_distance = 20
        optimal_pixel_width = text_length * 60
        current_ratio = img_width / optimal_pixel_width
        return base_distance * current_ratio

    def process_frame(self, dt):
        try:
            current_time = time.time()
            if current_time - self.last_capture_time < self.scan_interval:
                return
            self.last_capture_time = current_time
            
            if not self.camera or not self.camera.texture:
                return

            texture = self.camera.texture
            img = Image.frombytes('RGBA', texture.size, texture.pixels)
            img = img.convert('RGB')
            img = self.correct_image_orientation(img)
            enhanced_img = self._enhance_image(img)
            if enhanced_img is None:
                return
                
            temp_dir = os.path.join(get_android_cache_dir(), 'ocr_temp')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, f'ocr_{int(time.time()*1000)}.png')
            enhanced_img.save(temp_path, dpi=(300, 300), quality=100)
            
            asset_id = self.ocr_space(temp_path)
            
            if asset_id:
                print(f"识别成功: {asset_id}")
                Clock.schedule_once(lambda dt: self.handle_scan_result(asset_id))
                self.stop_scanning()
                
        except Exception as e:
            error_msg = str(e)
            def show_err(dt):
                self.show_error(f"扫描出错: {error_msg}")
                self.stop_scanning()
            Clock.schedule_once(show_err)

    def get_app_storage_path(self):
        if platform == 'android':
            from android.storage import app_storage_path
            return app_storage_path()
        else:
            return os.path.dirname(__file__)

    def capture_camera_frame(self):
        if not self.camera or not self.camera.texture:
            return None

        width = self.camera.texture.width
        height = self.camera.texture.height
        pixels = self.camera.texture.pixels
        pil_img = Image.frombytes(
            mode='RGBA',
            size=(width, height),
            data=pixels,
            decoder_name='raw'
        )
        return pil_img.convert('RGB')

    def _preprocess_image(self, img):
        from PIL import ImageEnhance, ImageFilter
        
        img = img.convert('L')
        img = img.point(lambda x: 0 if x < 180 else 255)
        img = img.filter(ImageFilter.SHARPEN)
        img = img.filter(ImageFilter.MedianFilter(3))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        img = img.resize((img.width*2, img.height*2), Image.BICUBIC)
        return img

    def init_camera(self):
        try:
            if platform == 'android':
                Clock.schedule_once(self._init_camera_android, 0.5)
            else:
                self._init_camera_desktop()
        except Exception as e:
            print(f"相机初始化错误: {str(e)}")
            Clock.schedule_once(lambda dt: self.init_camera(), 1.0)

    def _init_camera_android(self, dt):
        try:
            from kivy.uix.camera import Camera
            self.camera = Camera(index=0, resolution=(640, 480))
        except Exception as e:
            print(f"标准相机初始化失败: {e}")
            try:
                from kivy.core.camera.camera_android import CameraAndroid
                self.camera = CameraAndroid(index=0, resolution=(640, 480))
            except Exception as e2:
                print(f"Android专用相机初始化失败: {e2}")
                self.show_message("错误", "该设备不支持相机功能")
                return
        
        Clock.schedule_once(lambda dt: self._add_camera_to_ui(), 0.5)

    def _init_camera_desktop(self):
        try:
            self.release_camera()
            self.camera = Camera(
                index=0,
                resolution=(640, 480),
                play=False
            )
            self.ids.camera_container.add_widget(self.camera)
            Clock.schedule_once(self.start_camera, 0.2)
        except Exception as e:
            print(f"桌面相机初始化错误: {str(e)}")
            raise

    def _add_camera_to_ui(self):
        if self.camera and not self.camera.parent:
            try:
                self.ids.camera_container.add_widget(self.camera)
                Clock.schedule_once(self.start_camera, 0.2)
            except Exception as e:
                print(f"添加相机到UI错误: {str(e)}")
                self.release_camera()

    def start_camera(self, dt):
        if self.camera and not self.camera.play:
            try:
                self.camera.play = True
                print("相机启动成功")
            except Exception as e:
                print(f"相机启动错误: {str(e)}")
                self.release_camera()
                Clock.schedule_once(lambda dt: self.init_camera(), 0.5)

    def release_camera(self, dt=None):
        if self.camera:
            self.camera.play = False
            if self.camera.parent:
                self.camera.parent.remove_widget(self.camera)
        self.camera = None

    def on_enter(self):
        if platform == 'android':
            from android.permissions import check_permission, Permission
            if check_permission(Permission.CAMERA):
                self.permissions_granted = True
                if not self.camera:
                    self.init_camera()
            else:
                self.request_android_permissions()
        else:
            if not self.camera:
                self.init_camera()

    def on_leave(self):
        self.release_camera()

    def toggle_scanning(self):
        if self.scanning:
            self.stop_scanning()
            self.ids.scan_button.text = '开始扫描'
        else:
            self.start_scanning()
            self.ids.scan_button.text = '停止扫描'

    def start_scanning(self):
        if not self.camera:
            self.show_message("错误", "相机未初始化", is_error=True)
            return
        
        if self.scan_event:
            self.scan_event.cancel()
        
        self.scanning = True
        self.ids.scan_button.text = '扫描中...'
        self.ids.scan_button.disabled = True
        self.ids.status_label.text = "扫描开始"
        
        def scan_sequence():
            self.ids.status_label.text = "正在捕获图像..."
            Clock.schedule_once(lambda dt: self.capture_and_process(), 1.5)
            
        Clock.schedule_once(lambda dt: scan_sequence(), 0.5)

    def capture_and_process(self):
        try:
            self.ids.status_label.text = "处理图像中..."
            texture = self.camera.texture
            img = Image.frombytes('RGBA', texture.size, texture.pixels)
            img = img.convert('RGB')
            img = self.correct_image_orientation(img)
            
            temp_path = os.path.join(self.get_app_storage_path(), 'last_scan.png')
            img.save(temp_path, quality=95)
            
            self.ids.status_label.text = "识别中..."
            asset_id = self.ocr_space(temp_path)
            
            if self.save_to_gallery(img):
                self.capture_count += 1
            
            if asset_id:
                self.handle_scan_result(asset_id)
                self.ids.status_label.text = "识别成功"
            else:
                self.ids.status_label.text = "未识别到内容"
                
        except Exception as e:
            self.ids.status_label.text = "识别失败"
            self.show_message("错误", f"扫描出错: {str(e)}", is_error=True)
        finally:
            Clock.schedule_once(lambda dt: self.stop_scanning(), 1.5)

    def stop_scanning(self):
        if self.scan_event:
            self.scan_event.cancel()
        self.scanning = False
        self.ids.scan_button.text = '开始扫描'
        self.ids.scan_button.disabled = False
        self.ids.status_label.text = "准备就绪"

    def reset_scanning(self, dt=None):
        self.stop_scanning()
        if self.camera and self.camera.play:
            self.camera.play = False
            Clock.schedule_once(lambda dt: setattr(self.camera, 'play', True), 0.5)

    def handle_scan_result(self, text):
        app = App.get_running_app()
 
        def query_in_thread(text=text):
            try:
                db = AssetDatabase()
                assets = db.get_assets({'asset_id': text}, limit=1)
                
                def update_ui(assets, dt):
                    try:
                        if assets and len(assets) > 0:
                            asset = assets[0]
                            input_screen = app.root.get_screen('input')
                            input_screen.load_asset(asset)
                            app.root.current = 'input'
                            self.show_message(f"找到资产: {asset.get('asset_name', '未知')}")
                        else:
                            self.show_message("提示", f"未找到资产编号: {text}")
                    except Exception as e:
                        self.show_error(f"UI更新错误: {str(e)}")
                
                Clock.schedule_once(lambda dt: update_ui(assets, dt))
                
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.show_error(f"查询错误: {error_msg}"))

        Thread(target=query_in_thread, daemon=True).start()

    def _safe_update_ui(self, asset, text):
        try:
            app = App.get_running_app()
            if asset:
                input_screen = app.root.get_screen('input')
                input_screen.load_asset(asset)
                app.root.current = 'input'
                self.show_message(f"找到资产: {asset.get('asset_name', '未知')}")
            else:
                self.show_message("提示", f"未找到资产编号: {text}")
        except Exception as e:
            self.show_error(f"更新UI时出错: {str(e)}")

class MainScreen(Screen):
    pass

class DataInputScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_asset = None

    def load_asset(self, asset_data):
        def do_load(dt):
            try:
                self.current_asset = asset_data
                self.ids.asset_id.text = asset_data.get('asset_id', '')
                self.ids.asset_name.text = asset_data.get('asset_name', '')
                self.ids.asset_type.text = asset_data.get('asset_type', '')
                self.ids.user.text = asset_data.get('user', '')
                self.ids.location.text = asset_data.get('location', '')
                self.ids.notes.text = asset_data.get('notes', '')
                self.ids.save_btn.text = '更新'
            except Exception as e:
                print(f"加载资产失败: {str(e)}")
        
        Clock.schedule_once(do_load)

    def update_data(self):
        if not self.current_asset:
            self.show_popup("错误", "没有可更新的资产")
            return
            
        new_data = {
            'asset_name': self.ids.asset_name.text.strip(),
            'asset_type': self.ids.asset_type.text.strip(),
            'user': self.ids.user.text.strip(),
            'location': self.ids.location.text.strip(),
            'notes': self.ids.notes.text.strip()
        }
        
        try:
            app = App.get_running_app()
            app.db.update_asset(self.current_asset['asset_id'], new_data)
            self.show_popup("成功", "资产数据已更新")
            self.clear_form()
        except Exception as e:
            self.show_popup("错误", f"更新失败: {str(e)}")
    
    def clear_form(self):
        self.current_asset = None
        super().clear_form()
        self.ids.save_btn.disabled = False
        self.ids.update_btn.disabled = True
    
    def save_data(self):
        asset_data = {
            'asset_id': self.ids.asset_id.text.strip(),
            'asset_name': self.ids.asset_name.text.strip(),
            'asset_type': self.ids.asset_type.text.strip(),
            'user': self.ids.user.text.strip(),
            'location': self.ids.location.text.strip(),
            'notes': self.ids.notes.text.strip()
        }
        
        if not asset_data['asset_id']:
            self.show_popup("错误", "资产编号不能为空")
            return
        
        app = App.get_running_app()
        try:
            if self.current_asset:
                app.db.update_asset(self.current_asset['asset_id'], asset_data)
                message = "资产数据已更新"
            else:
                app.db.add_asset(asset_data)
                message = "资产数据已保存"
            
            self.show_popup("成功", message)
            self.clear_form()
        except sqlite3.IntegrityError:
            self.show_popup("错误", "资产编号已存在,请进入查看页面进行编辑")
        except Exception as e:
            self.show_popup("错误", f"保存失败: {str(e)}")
    
    def clear_form(self):
        self.current_asset = None
        self.ids.asset_id.text = ''
        self.ids.asset_name.text = ''
        self.ids.asset_type.text = ''
        self.ids.user.text = ''
        self.ids.location.text = ''
        self.ids.notes.text = ''
        self.ids.save_btn.text = '保存'
    
    def show_popup(self, title, message):
        popup = Popup(title=title, title_font='simhei', size_hint=(0.8, 0.4))
        content = BoxLayout(orientation='vertical', padding=10)
        content.add_widget(Label(text=message, font_name='simhei'))
        close_btn = Button(text='关闭', size_hint=(1, 0.3), font_name='simhei')
        content.add_widget(close_btn)
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

    def show_error(self, message):
        popup = Popup(title='错误', title_font='simhei', size_hint=(0.8, 0.4))
        content = BoxLayout(orientation='vertical', padding=10)
        content.add_widget(Label(text=message, font_name='simhei'))
        close_btn = Button(text='关闭', size_hint=(1, 0.3), font_name='simhei')
        content.add_widget(close_btn)
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

class DataViewScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_filters = {}
        self.selected_asset = None
        self._loading = False
        self._current_page = 0
        self._total_pages = 0
        self.BATCH_SIZE = 20

    def on_pre_enter(self):
        self._current_page = 0
        self.load_data()

    def load_data(self, filters=None):
        if self._loading:
            return

        try:
            self._loading = True
            self.current_filters = filters or {}
            
            grid = self.ids.data_grid
            while len(grid.children) > 7:
                grid.remove_widget(grid.children[0])
            
            self.ids.loading_label.opacity = 1
            self.ids.loading_label.text = "正在加载数据..."
            self.ids.loading_label.font_name = "simhei"
            self.ids.data_grid.opacity = 0.5
            
            def async_load(dt):
                try:
                    app = App.get_running_app()
                    
                    total_count = self._get_total_count(filters)
                    self._total_pages = max(1, (total_count + self.BATCH_SIZE - 1) // self.BATCH_SIZE)
                    
                    assets = app.db.get_assets(
                        filters,
                        limit=self.BATCH_SIZE,
                        offset=self._current_page * self.BATCH_SIZE
                    )

                    def update_ui(dt):
                        try:
                            if assets:
                                self._display_batch(assets)
                                self._update_pagination_controls()
                            else:
                                self.show_popup("提示", "没有找到匹配的数据")
                        except Exception as e:
                            self.show_popup("错误", f"更新UI失败: {str(e)}")
                        finally:
                            self._loading = False
                            self.ids.loading_label.opacity = 0
                            self.ids.data_grid.opacity = 1
                    
                    Clock.schedule_once(update_ui)
                    
                except Exception as e:
                    self._loading = False
                    self.ids.loading_label.opacity = 0
                    self.ids.data_grid.opacity = 1
                    self.show_popup("加载错误", f"加载数据失败: {str(e)}")
            
            Clock.schedule_once(async_load)
            
        except Exception as e:
            self._loading = False
            self.show_popup("加载错误", f"初始化加载失败:\n{str(e)}")

    def _get_total_count(self, filters):
        app = App.get_running_app()
        try:
            query = 'SELECT COUNT(*) FROM assets'
            params = []
            
            if filters:
                conditions = []
                for field, value in filters.items():
                    if value:
                        conditions.append(f"{field} = ?")
                        params.append(value)
                if conditions:
                    query += ' WHERE ' + ' AND '.join(conditions)
            
            cursor = app.db._get_connection().cursor()
            cursor.execute(query, params)
            return cursor.fetchone()[0]
        except Exception as e:
            print(f"获取总数失败: {str(e)}")
            return 0

    def _update_pagination_controls(self):
        self.ids.page_info.text = f"第{self._current_page + 1}页/共{self._total_pages}页"
        self.ids.prev_page.disabled = self._current_page <= 0
        self.ids.next_page.disabled = self._current_page >= self._total_pages - 1

    def prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self.load_data(self.current_filters)

    def next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self.load_data(self.current_filters)

    def _display_next_batch(self):
        if not self._all_assets:
            self._loading = False
            self.ids.loading_label.opacity = 0
            self.ids.data_grid.opacity = 1
            return
            
        start = self._current_batch * self.BATCH_SIZE
        end = start + self.BATCH_SIZE
        batch = self._all_assets[start:end]
        
        self._display_batch(batch)
        
        loaded_count = min(end, len(self._all_assets))
        self.ids.loading_label.text = f"加载中... {loaded_count}/{len(self._all_assets)}"
        self.ids.loading_label.font_name = "simhei"
        
        if end < len(self._all_assets):
            self._current_batch += 1
            Clock.schedule_once(lambda dt: self._display_next_batch(), 0.05)
        else:
            self._loading = False
            self.ids.loading_label.opacity = 0
            self.ids.data_grid.opacity = 1

    def _display_batch(self, assets):
        grid = self.ids.data_grid

        column_widths = {
            'id': 60,
            'asset_id': 200,
            'asset_name': 200,
            'asset_type': 150,
            'user': 150,
            'location': 200,
            'notes': 150,
            'actions': 100
        }
        
        for asset in assets:
            for col in ['id', 'asset_id', 'asset_name', 'asset_type', 'user', 'location']:
                lbl = Label(
                    text=str(asset.get(col, '')),
                    size_hint_x=None,
                    width=column_widths[col],
                    text_size=(column_widths[col] - 10, None),
                    halign='left',
                    valign='top',
                    font_name='simhei',
                    padding=(dp(5), dp(5)),
                    size_hint_y=None,
                    height=60,
                )
                
                def update_height(label, *args):
                    required_height = label.texture_size[1] + 10
                    if required_height > label.height:
                        label.height = required_height
                        row_index = grid.children.index(label) // grid.cols
                        self._sync_row_height(grid, row_index)
                
                lbl.bind(texture_size=update_height)
                grid.add_widget(lbl)
            
            btn_box = BoxLayout(
                size_hint_x=None,
                width=column_widths['actions'],
                spacing=dp(2),
                size_hint_y=None,
                height=60
            )
            
            edit_btn = Button(
                text='编辑',
                size_hint_x=0.6,
                font_name='simhei',
                font_size='10sp',
                size_hint_y=None,
                height=50
            )
            edit_btn.bind(on_press=lambda btn, a=asset: self._edit_asset(a))
            
            delete_btn = Button(
                text='删除',
                size_hint_x=0.4,
                font_name='simhei',
                font_size='10sp',
                background_color=(1, 0, 0, 1),
                size_hint_y=None,
                height=50
            )
            delete_btn.bind(on_press=lambda btn, a=asset: self._confirm_delete(a))
            
            btn_box.add_widget(edit_btn)
            btn_box.add_widget(delete_btn)
            grid.add_widget(btn_box)

    def _sync_row_height(self, grid, row_index):
        cols = grid.cols
        start_idx = row_index * cols
        end_idx = start_idx + cols
        
        max_height = max(
            child.height 
            for child in grid.children[start_idx:end_idx]
            if hasattr(child, 'height')
        )
        
        for child in grid.children[start_idx:end_idx]:
            if hasattr(child, 'height'):
                child.height = max_height

    def _edit_asset(self, asset):
        input_screen = self.manager.get_screen('input')
        input_screen.load_asset(asset)
        self.manager.current = 'input'

    def _confirm_delete(self, asset):
        content = BoxLayout(orientation='vertical', spacing='10dp')
        content.add_widget(Label(
            text=f"确定删除资产 {asset['asset_id']} 吗？",
            font_name='simhei'
        ))
        
        btn_box = BoxLayout(size_hint_y=None, height='50dp')
        btn_confirm = Button(text='确认', background_color=(1, 0, 0, 1), font_name='simhei')
        btn_cancel = Button(text='取消', font_name='simhei')
        
        popup = Popup(
            title='确认删除',
            title_font='simhei',
            content=content,
            size_hint=(0.6, 0.4)
        )
        
        def do_delete(instance):
            app = App.get_running_app()
            try:
                app.db.delete_asset(asset['asset_id'])
                self.load_data()
                popup.dismiss()
            except Exception as e:
                self.show_popup("错误", f"删除失败: {str(e)}")
        
        btn_confirm.bind(on_press=do_delete)
        btn_cancel.bind(on_press=popup.dismiss)
        
        btn_box.add_widget(btn_confirm)
        btn_box.add_widget(btn_cancel)
        content.add_widget(btn_box)
        popup.open()

    def _select_asset(self, asset):
        self.selected_asset = asset
        input_screen = self.manager.get_screen('input')
        input_screen.load_asset(asset)
        self.manager.current = 'input'
    
    def edit_selected(self):
        if self.selected_asset:
            input_screen = self.manager.get_screen('input')
            input_screen.load_asset(self.selected_asset)
            self.manager.current = 'input'
        else:
            self.show_popup("提示", "请先点击行末的编辑按钮选择资产")
    
    def show_filter_dropdown(self, column):
        app = App.get_running_app()
        values = app.db.get_distinct_values(column)
        
        dropdown = DropDown()
        dropdown.bind(on_open=self.adjust_dropdown_width)
        
        select_all = Button(text='全选', size_hint_y=None, height=40, font_name='simhei')
        select_all.bind(on_release=lambda x: self.apply_filter(column, ''))
        dropdown.add_widget(select_all)
        
        for value in values:
            btn = Button(
                text=value,
                size_hint_y=None,
                height=100,
                font_name='simhei',
                halign='left',
                valign='middle',
                text_size=(None, None),
                padding=(10, 0)
            )
            btn.bind(
                texture_size=lambda btn, *args: setattr(btn, 'text_size', (btn.width - 10, None)),
                on_release=lambda btn, c=column: self.apply_filter(c, btn.text)
            )
            dropdown.add_widget(btn)
        
        filter_btn = getattr(self.ids, f'filter_{column}')
        dropdown.open(filter_btn)

    def adjust_dropdown_width(self, dropdown):
        max_width = 0
        for child in dropdown.children:
            child.width = dropdown.width
            child.texture_update()
            max_width = max(max_width, child.texture_size[0] + 40)
        
        min_width = 200
        max_width = max(min_width, min(max_width, Window.width * 0.8))
        dropdown.width = max_width

        for child in dropdown.children:
            child.text_size = (max_width - 20, None)
    
    def apply_filter(self, column, value):
        try:
            valid_columns = ['asset_id', 'asset_name', 'asset_type', 'user', 'location']
            if column not in valid_columns:
                raise ValueError(f"无效的列名: {column}")
            
            if value == '':
                if column in self.current_filters:
                    del self.current_filters[column]
            else:
                self.current_filters[column] = value.upper() if column == 'asset_id' else value

            self._current_page = 0

            self.load_data(self.current_filters)
            
        except Exception as e:
            self._loading = False
            self.ids.loading_label.opacity = 0
            self.show_popup("筛选错误", f"应用筛选时出错:\n{str(e)}")

    def clear_filters(self):
        try:
            self.current_filters = {}
            self._current_page = 0
            self.load_data()
        except Exception as e:
            self._loading = False
            self.ids.loading_label.opacity = 0
            self.show_popup("错误", f"清除筛选时出错: {str(e)}")

    def export_to_excel(self):
        app = App.get_running_app()
        try:
            if platform == 'android':
                Environment = autoclass('android.os.Environment')
                download_dir = Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS
                ).getAbsolutePath()
                base_name = "asset_export"
                extension = ".xlsx"
                counter = 1
                export_path = os.path.join(download_dir, f"{base_name}{extension}")

                while os.path.exists(export_path):
                    export_path = os.path.join(download_dir, 
                                           f"{base_name}_{counter}{extension}")
                    counter += 1
            else:
                export_path = os.path.join(os.path.expanduser('~'), 'asset_export.xlsx')
            
            app.db.export_to_excel(export_path)
            self.show_popup("导出成功", f"数据已导出到:\n{export_path}")
        except Exception as e:
            self.show_popup("导出失败", str(e))

    def import_from_excel(self):
        if platform == 'android':
            self._android_import()
        else:
            self._desktop_import()
    
    def _android_import(self):
        from jnius import autoclass
        from android import mActivity
        
        try:
            Intent = autoclass('android.content.Intent')
            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("*/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            
            mActivity.startActivityForResult(intent, 123)
            
            from android import activity
            activity.bind(on_activity_result=self._handle_import_result)
            
        except Exception as e:
            Clock.schedule_once(
                lambda dt: self.show_popup("错误", f"无法启动选择器: {str(e)}")
            )

    def _handle_import_result(self, request_code, result_code, intent):
        if request_code != 123 or result_code != -1:
            return
        
        def process_uri(dt):
            try:
                from jnius import cast
                Uri = autoclass('android.net.Uri')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                
                uri = intent.getData()
                content_uri = cast('android.net.Uri', uri)

                cr = PythonActivity.mActivity.getContentResolver()
                fd = cr.openFileDescriptor(content_uri, "r")
                
                import os
                file_path = f"/proc/self/fd/{fd.getFd()}"
                
                self._process_import(file_path)
                
                fd.close()
                
            except Exception as e:
                Clock.schedule_once(
                    lambda dt: self.show_popup("导入错误", str(e))
                )
        
        Clock.schedule_once(process_uri)

    def _process_android_file(self, intent):
        from jnius import cast
        Context = autoclass('android.content.Context')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        
        uri = intent.getData()
        content_uri = cast('android.net.Uri', uri)
        
        temp_dir = os.path.join(app_storage_path(), 'temp_import')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, 'import_temp.xlsx')

        cr = PythonActivity.mActivity.getContentResolver()
        input_stream = cr.openInputStream(content_uri)
        
        buf = bytearray(8192)
        with open(temp_path, 'wb') as f:
            while True:
                bytes_read = input_stream.read(buf)
                if bytes_read == -1:
                    break
                f.write(buf[:bytes_read])
        input_stream.close()
        
        self._process_import(temp_path)
        
        try:
            os.remove(temp_path)
        except:
            pass

    def _show_android_error(self, error):
        error_msg = str(error)
        if "FileNotFoundException" in error_msg:
            error_msg = "无法访问文件，请重试"
        elif "Permission" in error_msg:
            error_msg = "需要存储权限，请到设置中授予"
        
        self.show_popup("导入错误", error_msg)
        self.ids.import_status.text = ""
    
    def _desktop_import(self):
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.popup import Popup
        
        content = BoxLayout(orientation='vertical')
        
        chooser = FileChooserListView(
            path=os.path.expanduser('~'),
            filters=['*.xlsx', '*.xls'],
            font_name='simhei',
            size_hint=(1, 0.9)
        )
        
        btn_box = BoxLayout(size_hint_y=None, height='50dp')
        btn_ok = Button(text='导入', size_hint_x=0.5, font_name='simhei')
        btn_cancel = Button(text='取消', size_hint_x=0.5, font_name='simhei')
        btn_box.add_widget(btn_ok)
        btn_box.add_widget(btn_cancel)
        
        content.add_widget(chooser)
        content.add_widget(btn_box)
        
        popup = Popup(
            title='选择Excel文件',
            title_font='simhei',
            content=content,
            size_hint=(0.8, 0.8),
            auto_dismiss=False
        )
        
        def do_import(instance):
            if chooser.selection:
                Clock.schedule_once(
                    lambda dt: self._process_import(chooser.selection[0]),
                    timeout=0.1
                )
            popup.dismiss()
        
        btn_ok.bind(on_press=do_import)
        btn_cancel.bind(on_press=popup.dismiss)
        
        Clock.schedule_once(lambda dt: popup.open(), 0.1)

    def _linux_file_chooser(self):
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.popup import Popup
        
        content = BoxLayout(orientation='vertical', spacing=10)
        
        filechooser = FileChooserListView(
            path=os.path.expanduser('~'),
            filters=['*.xlsx', '*.xls'],
            font_name='simhei',
            size_hint=(1, 0.9)
        )

        btn_box = BoxLayout(size_hint_y=None, height=50, spacing=5)
        btn_import = Button(text='导入', size_hint_x=0.6, font_name='simhei')
        btn_cancel = Button(text='取消', size_hint_x=0.4, font_name='simhei')
        btn_box.add_widget(btn_import)
        btn_box.add_widget(btn_cancel)
        
        content.add_widget(filechooser)
        content.add_widget(btn_box)
        
        popup = Popup(
            title='选择Excel文件 (Linux)',
            title_font='simhei',
            content=content,
            size_hint=(0.8, 0.8),
            auto_dismiss=False
        )
        
        def do_import(instance):
            if filechooser.selection:
                Clock.schedule_once(
                    lambda dt: self._process_import(filechooser.selection[0]),
                    0.1
                )
            popup.dismiss()
        
        btn_import.bind(on_press=do_import)
        btn_cancel.bind(on_press=popup.dismiss)
        
        Clock.schedule_once(lambda dt: popup.open(), 0.1)

    def _kivy_file_chooser(self):
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.popup import Popup
        
        box = BoxLayout(orientation='vertical')
        
        chooser = FileChooserListView(
            path=os.path.expanduser('~'),
            filters=['*.xlsx', '*.xls'],
            font_name='simhei',
            size_hint=(1, 0.85)
        )
        
        btn_box = BoxLayout(size_hint_y=None, height=50)
        btn_select = Button(text='选择', size_hint_x=0.5, font_name='simhei')
        btn_cancel = Button(text='取消', size_hint_x=0.5, font_name='simhei')
        btn_box.add_widget(btn_select)
        btn_box.add_widget(btn_cancel)
        
        box.add_widget(chooser)
        box.add_widget(btn_box)
        
        popup = Popup(
            title='选择Excel文件',
            title_font='simhei',
            content=box,
            size_hint=(0.7, 0.7),
            auto_dismiss=False
        )
        
        def select_file(instance):
            if chooser.selection:
                Clock.schedule_once(
                    lambda dt: self._process_import(chooser.selection[0]),
                    0.2
                )
            popup.dismiss()
        
        btn_select.bind(on_press=select_file)
        btn_cancel.bind(on_press=popup.dismiss)
        
        Clock.schedule_once(lambda dt: popup.open(), 0.2)
    
    def _handle_import_result(self, request_code, result_code, intent):
        if request_code != 123 or result_code != -1:  # -1 = RESULT_OK
            return
        
        self._import_intent = intent
        Clock.schedule_once(lambda dt: self._process_android_file())

    def _process_android_file(self):
        try:
            from jnius import cast
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            
            intent = getattr(self, '_import_intent', None)
            if not intent:
                raise ValueError("无效的文件选择结果")
            
            uri = intent.getData()
            content_uri = cast('android.net.Uri', uri)
            
            temp_dir = os.path.join(app_storage_path(), 'temp_import')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, 'import_temp.xlsx')

            cr = PythonActivity.mActivity.getContentResolver()
            input_stream = cr.openInputStream(content_uri)
            
            buf = bytearray(8192)
            with open(temp_path, 'wb') as f:
                while True:
                    bytes_read = input_stream.read(buf)
                    if bytes_read == -1:
                        break
                    f.write(buf[:bytes_read])
            input_stream.close()
            
            self._process_import(temp_path)
            
            Clock.schedule_once(lambda dt: self._clean_temp_file(temp_path), 5)
            
        except Exception as e:
            self._import_error = str(e)
            Clock.schedule_once(lambda dt: self._show_android_error())

    def _clean_temp_file(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except:
            pass

    def _show_android_error(self):
        error_msg = getattr(self, '_import_error', '未知错误')
        
        if "FileNotFoundException" in error_msg:
            error_msg = "文件未找到，请重试"
        elif "Permission" in error_msg:
            error_msg = "需要存储权限，请到设置中授予"
        elif "ENOENT" in error_msg:
            error_msg = "文件路径无效"
        
        self.show_popup("导入错误", error_msg)
        self._clean_import_vars()
    
    def _process_import(self, file_path):
        def update_status(text):
            self.ids.import_status.text = text
        Clock.schedule_once(lambda dt: update_status("正在准备导入..."))

        Clock.schedule_once(lambda dt: self._do_threaded_import(file_path))

    def _do_threaded_import(self, file_path):
        def do_import(dt):
            try:
                app = App.get_running_app()
                imported, updated = app.db.import_from_excel(file_path)
                
                def show_result():
                    self.show_popup(
                        "导入完成", 
                        f"成功导入 {imported} 条\n更新 {updated} 条"
                    )
                    self.load_data()
                    self.ids.import_status.text = ""
                
                Clock.schedule_once(lambda dt: show_result())
                
            except Exception as e:
                def show_error():
                    error_msg = str(e)
                    if "Excel" in error_msg:
                        error_msg = "文件格式错误"
                    self.show_popup("导入失败", error_msg)
                    self.ids.import_status.text = ""
                
                Clock.schedule_once(lambda dt: show_error())

        import threading
        thread = threading.Thread(
            target=lambda: Clock.schedule_once(do_import),
            daemon=True
        )
        thread.start()

    def _update_import_status(self):
        if hasattr(self, '_import_status'):
            self.ids.import_status.text = self._import_status

    def _do_actual_import(self, file_path):
        try:
            app = App.get_running_app()
            imported, updated = app.db.import_from_excel(file_path)
            
            self._import_status = ""
            self._import_result = (imported, updated)
            
            Clock.schedule_once(lambda dt: self._show_import_result())
            
        except Exception as e:
            self._import_status = ""
            self._import_error = str(e)
            
            Clock.schedule_once(lambda dt: self._show_import_error())

    def _show_import_result(self):
        imported, updated = self._import_result
        self.show_popup(
            "导入完成",
            f"成功导入 {imported} 条新记录\n更新 {updated} 条现有记录"
        )
        self.load_data()
        self._clean_import_vars()

    def _show_import_error(self):
        error_msg = getattr(self, '_import_error', '未知错误')
        
        if "Excel" in error_msg:
            error_msg = "Excel文件格式错误，请检查文件完整性"
        elif "required columns" in error_msg:
            error_msg = "缺少必要列(需包含: 资产编号/名称/使用人/存放地点)"
        
        self.show_popup("导入失败", error_msg)
        self._clean_import_vars()

    def _clean_import_vars(self):
        if hasattr(self, '_import_result'):
            del self._import_result
        if hasattr(self, '_import_error'):
            del self._import_error

    def show_popup(self, title, message):
        popup = Popup(title=title, title_font='simhei', size_hint=(0.8, 0.4))
        content = BoxLayout(orientation='vertical', padding=10)
        content.add_widget(Label(text=message, font_name='simhei'))
        close_btn = Button(text='关闭', size_hint=(1, 0.3), font_name='simhei')
        content.add_widget(close_btn)
        close_btn.bind(on_press=popup.dismiss)
        popup.content = content
        popup.open()

class ScannerApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = AssetDatabase()
        self.is_android = platform == 'android'    

    def build(self):
        Builder.load_string(KV)
        
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(DataInputScreen(name='input'))
        sm.add_widget(DataViewScreen(name='data'))
        sm.add_widget(ScannerScreen(name='scanner'))
        
        return sm
    
KV = '''
#:import colors kivy.utils.get_color_from_hex

<MainScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '10dp'
        spacing: '10dp'
        
        Label:
            text: '资产管理系统'
            font_size: '24sp'
            font_name: 'simhei'
            size_hint_y: None
            height: '40dp'
        
        GridLayout:
            cols: 1
            spacing: '10dp'
            padding: '10dp'
            size_hint_y: 0.8
            
            Button:
                text: '扫描资产标签'
                background_color: colors('#4CAF50')
                font_size: '16sp'
                font_name: 'simhei'
                size_hint_y: None
                height: '60dp'
                on_press: root.manager.current = 'scanner'
            
            Button:
                text: '录入资产数据'
                background_color: colors('#2196F3')
                font_size: '16sp'
                font_name: 'simhei'
                size_hint_y: None
                height: '60dp'
                on_press: 
                    root.manager.get_screen('input').clear_form()
                    root.manager.current = 'input'
            
            Button:
                text: '查看资产数据'
                background_color: colors('#FF9800')
                font_size: '16sp'
                font_name: 'simhei'
                size_hint_y: None
                height: '60dp'
                on_press: root.manager.current = 'data'
            
            Button:
                text: '导出Excel数据'
                background_color: colors('#F44336')
                font_size: '16sp'
                font_name: 'simhei'
                size_hint_y: None
                height: '60dp'
                on_press: root.manager.get_screen('data').export_to_excel()

            Button:
                text: '导入Excel数据'
                background_color: colors('#9C27B0')
                font_size: '16sp'
                font_name: 'simhei'
                size_hint_y: None
                height: '60dp'
                on_press: root.manager.get_screen('data').import_from_excel()
            
<ScannerScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: 10
        spacing: 10
        
        Label:
            text: '资产标签扫描'
            font_size: '20sp'
            font_name: 'simhei'
            size_hint_y: None
            height: 50
        
        BoxLayout:
            id: camera_container
            size_hint_y: 0.7
            orientation: 'vertical'
        
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 0.2
            padding: 10
            
            Label:
                id: status_label
                text: '准备扫描'
                font_size: '16sp'
                font_name: 'simhei'
                size_hint_y: 0.5
        
        BoxLayout:
            size_hint_y: None
            height: 80
            spacing: 20
            padding: 10
            
            Button:
                id: scan_button
                text: '开始扫描'
                font_size: '18sp'
                font_name: 'simhei'
                on_press: root.toggle_scanning()
            
            Button:
                text: '返回主页'
                font_size: '18sp'
                font_name: 'simhei'
                on_press: 
                    root.stop_scanning()
                    root.manager.current = 'main'

<DataInputScreen>:
    ScrollView:
        GridLayout:
            cols: 1
            spacing: 10
            padding: 20
            size_hint_y: None
            height: self.minimum_height
            
            Label:
                text: '资产信息录入'
                font_size: '20sp'
                font_name: 'simhei'
                size_hint_y: None
                height: 50
            
            GridLayout:
                cols: 2
                spacing: 10
                size_hint_y: None
                height: 410
                row_default_height: 60
                
                Label:
                    text: '资产编号:'
                    size_hint_x: 0.3
                    font_name: 'simhei'
                TextInput:
                    id: asset_id
                    multiline: False
                    font_name: 'simhei'
                
                Label:
                    text: '资产名称:'
                    size_hint_x: 0.3
                    font_name: 'simhei'
                TextInput:
                    id: asset_name
                    multiline: False
                    font_name: 'simhei'

                Label:
                    text: '资产分类:'
                    size_hint_x: 0.3
                    font_name: 'simhei'
                TextInput:
                    id: asset_type
                    multiline: False
                    font_name: 'simhei'
                
                Label:
                    text: '使用人:'
                    size_hint_x: 0.3
                    font_name: 'simhei'
                TextInput:
                    id: user
                    multiline: False
                    font_name: 'simhei'
                
                Label:
                    text: '存放地点:'
                    size_hint_x: 0.3
                    font_name: 'simhei'
                TextInput:
                    id: location
                    multiline: False
                    font_name: 'simhei'
                
                Label:
                    text: '备注:'
                    size_hint_x: 0.3
                    font_name: 'simhei'
                TextInput:
                    id: notes
                    multiline: False
                    font_name: 'simhei'
            
            BoxLayout:
                size_hint_y: None
                height: 50
                spacing: 50
                
                Button:
                    id: save_btn
                    text: '保存'
                    font_name: 'simhei'
                    on_press: root.save_data()

                Button:
                    id: update_btn
                    text: '更新'
                    font_name: 'simhei'
                    disabled: True  # 默认禁用
                    on_press: root.update_data()
                
                Button:
                    text: '清空'
                    font_name: 'simhei'
                    on_press: root.clear_form()
                
                Button:
                    text: '返回主页'
                    font_name: 'simhei'
                    on_press: root.manager.current = 'main'

<DataViewScreen>:
    Label:
        id: loading_label
        text: ""
        size_hint_y: None
        height: 30
        opacity: 0

    BoxLayout:
        id: loading_indicator
        orientation: 'horizontal'
        size_hint_y: None
        height: 30
        opacity: 0
        spacing: 10
        
        Label:
            text: '加载中'
            font_name: 'simhei'
        ProgressBar:
            max: 100
            value: 0

    BoxLayout:
        orientation: 'vertical'
        spacing: 10
        
        Label:
            id: import_status
            text: ''
            size_hint_y: None
            height: '30dp'
            color: 0, 0.5, 0, 1

        BoxLayout:
            id: filter_toolbar
            size_hint_y: None
            height: 50
            spacing: 5
            padding: 5
            
            Label:
                text: '筛选:'
                size_hint_x: None
                width: 60
                font_name: 'simhei'
            
            Button:
                id: filter_asset_name
                text: '资产名称'
                font_name: 'simhei'
                on_release: root.show_filter_dropdown('asset_name')

            Button:
                id: filter_asset_type
                text: '资产分类'
                font_name: 'simhei'
                on_release: root.show_filter_dropdown('asset_type')
            
            Button:
                id: filter_user
                text: '使用人'
                font_name: 'simhei'
                on_release: root.show_filter_dropdown('user')
            
            Button:
                id: filter_location
                text: '存放地点'
                font_name: 'simhei'
                on_release: root.show_filter_dropdown('location')
            
            Button:
                text: '清除筛选'
                size_hint_x: None
                width: 100
                font_name: 'simhei'
                on_press: root.clear_filters()
        
        ScrollView:
            GridLayout:
                id: data_grid
                cols: 7
                spacing: 5
                padding: 5
                size_hint_y: None
                height: self.minimum_height
                row_default_height: 40

                Label:
                    text: '序号'
                    size_hint_x: None
                    width: 60
                    bold: True
                    font_name: 'simhei'
                Label:
                    text: '资产编号'
                    size_hint_x: None
                    width: 200
                    bold: True
                    font_name: 'simhei'
                Label:
                    text: '资产名称'
                    size_hint_x: None
                    width: 200
                    bold: True
                    font_name: 'simhei'
                Label:
                    text: '资产分类'
                    size_hint_x: None
                    width: 200
                    bold: True
                    font_name: 'simhei'
                Label:
                    text: '使用人'
                    size_hint_x: None
                    width: 150
                    bold: True
                    font_name: 'simhei'
                Label:
                    text: '存放地点'
                    size_hint_x: None
                    width: 200
                    bold: True
                    font_name: 'simhei'

                Label:
                    text: '操作'
                    size_hint_x: None
                    width: '90'
                    bold: True
                    font_name: 'simhei'

        BoxLayout:
            id: pagination_controls
            size_hint_y: None
            height: '50dp'
            spacing: '5dp'
            
            Button:
                id: prev_page
                text: '上一页'
                font_name: 'simhei'
                size_hint_x: 0.2
                disabled: True
                on_press: root.prev_page()
            
            Label:
                id: page_info
                text: '第1页'
                font_name: 'simhei'
                halign: 'center'
                size_hint_x: 0.6
            
            Button:
                id: next_page
                text: '下一页'
                font_name: 'simhei'
                size_hint_x: 0.2
                disabled: True
                on_press: root.next_page()

        BoxLayout:
            size_hint_y: None
            height: '100dp' if app.is_android else '80dp'
            padding: 20
            
            Button:
                text: '返回主页'
                font_name: 'simhei'
                on_press: root.manager.current = 'main'
'''

if __name__ == '__main__':
    ScannerApp().run()
