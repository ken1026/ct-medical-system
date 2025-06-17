import streamlit as st
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import re  # 正規表現用
import pandas as pd
from datetime import datetime
import hashlib
import os
from PIL import Image
import base64
from io import BytesIO
import json
import zipfile
from io import BytesIO
import tempfile
import shutil


# リッチテキストエディタのインポート
try:
    from streamlit_quill import st_quill
    RICH_EDITOR_AVAILABLE = True
except ImportError:
    RICH_EDITOR_AVAILABLE = False

# ページ設定
st.set_page_config(
    page_title="How to CT - 診療放射線技師向けCT検査マニュアル",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

def save_session_to_db(user_id, session_data):
    """セッション情報をデータベースに保存"""
    try:
        conn = init_connection()
        cursor = conn.cursor()
        
        session_json = json.dumps(session_data)
        cursor.execute('''
            INSERT INTO user_sessions (user_id, session_data, last_updated)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
            session_data = EXCLUDED.session_data,
            last_updated = EXCLUDED.last_updated
        ''', (user_id, session_json))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def load_session_from_db():
    """データベースからセッション情報を復元"""
    try:
        conn = init_connection()
        cursor = conn.cursor()
        
        # PostgreSQL用のテーブル存在チェック
        cursor.execute('''
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_sessions'
            )
        ''')
        if not cursor.fetchone()[0]:
            conn.close()
            return None
        
        # 最新のセッション情報を取得（過去24時間以内）
        cursor.execute('''
            SELECT user_id, session_data FROM user_sessions
            WHERE last_updated > NOW() - INTERVAL '1 day'
            ORDER BY last_updated DESC LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            user_id, session_json = result
            session_data = json.loads(session_json)
            
            # ユーザー情報が有効かチェック
            user = get_user_by_id(user_id)
            if user:
                return {
                    'user': {
                        'id': user[0],
                        'name': user[1],
                        'email': user[2]
                    },
                    'page': session_data.get('page', 'home')
                }
        
        return None
    except Exception as e:
        return None

def get_user_by_id(user_id):
    """IDでユーザー情報を取得"""
    try:
        conn = init_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    except:
        return None

def update_session_in_db():
    """現在のセッション状態をデータベースに更新"""
    if 'user' in st.session_state:
        session_data = {
            'page': st.session_state.get('page', 'home')
        }
        save_session_to_db(st.session_state.user['id'], session_data)

# カスタムCSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    .disease-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1.5rem;
        margin: 1rem 0;
        background-color: #f8f9fa;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .protocol-section {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        border-left: 4px solid #2196F3;
    }
    .contrast-section {
        background-color: #f3e5f5;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        border-left: 4px solid #9c27b0;
    }
    .processing-section {
        background-color: #e8f5e8;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        border-left: 4px solid #4caf50;
    }
    .disease-section {
        background-color: #fff3e0;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        border-left: 4px solid #ff9800;
    }
    .notice-card {
        border-left: 4px solid #2196F3;
        padding: 1rem;
        margin: 1rem 0;
        background-color: #fff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-radius: 5px;
    }
    .search-result {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: #fafafa;
    }
    .welcome-title {
        font-size: 4rem;
        font-weight: bold;
        color: #1e88e5;
        text-align: center;
        margin: 3rem 0;
    }
    .section-title {
        color: #1565c0;
        border-bottom: 2px solid #1565c0;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    .rich-editor-hint {
        background-color: #e8f5e8;
        border: 1px solid #4caf50;
        border-radius: 5px;
        padding: 0.5rem;
        margin: 0.5rem 0;
        font-size: 0.9rem;
        color: #2e7d32;
    }
</style>
""", unsafe_allow_html=True)

# リッチテキストエディタのヘルパー関数
def create_rich_text_editor(content="", placeholder="テキストを入力してください...", key=None, height=300):
    """リッチテキストエディタを作成"""
    if RICH_EDITOR_AVAILABLE:
        st.markdown('<div class="rich-editor-hint">📝 リッチテキストエディタ: 太字、色、リストなど自由に装飾できます</div>', unsafe_allow_html=True)
        
        try:
            return st_quill(
                value=content,
                placeholder=placeholder,
                key=key,
                html=True
            )
        except Exception as e:
            st.error(f"リッチエディタエラー: {e}")
            return st.text_area(
                "テキスト入力",
                value=content,
                placeholder=placeholder,
                key=f"fallback_{key}",
                height=height
            )
    else:
        st.info("💡 リッチテキストエディタを使用するには `pip install streamlit-quill` を実行してください")
        return st.text_area(
            "テキスト入力",
            value=content,
            placeholder=placeholder,
            key=key,
            height=height
        )

def display_rich_content(content):
    """リッチテキストコンテンツを表示"""
    if content:
        if '<' in content and '>' in content:
            st.markdown(content, unsafe_allow_html=True)
        else:
            st.write(content)
    else:
        st.info("内容が設定されていません")

# 画像処理関数
def resize_image(image, max_size=(600, 400)):
    """画像をリサイズして容量を削減"""
    if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image

def image_to_base64(uploaded_file):
    """アップロードファイルをBase64文字列に変換"""
    try:
        image = Image.open(uploaded_file)
        resized_image = resize_image(image.copy())
        
        if resized_image.mode == 'RGBA':
            rgb_image = Image.new('RGB', resized_image.size, (255, 255, 255))
            rgb_image.paste(resized_image, mask=resized_image.split()[-1])
            resized_image = rgb_image
        elif resized_image.mode not in ['RGB', 'L']:
            resized_image = resized_image.convert('RGB')
        
        buffered = BytesIO()
        resized_image.save(buffered, format="JPEG", quality=50, optimize=True)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        if len(img_str) > 500000:  # 500KB
            buffered = BytesIO()
            resized_image.save(buffered, format="JPEG", quality=30, optimize=True)
            img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str
    except Exception as e:
        st.error(f"画像の変換に失敗しました: {str(e)}")
        return None

def base64_to_image(base64_str):
    """Base64文字列をPIL Imageに変換"""
    if base64_str:
        try:
            image_data = base64.b64decode(base64_str)
            return Image.open(BytesIO(image_data))
        except Exception as e:
            st.error(f"画像データの読み込みに失敗しました: {str(e)}")
            return None
    return None

def display_image_with_caption(base64_str, caption="", width=300):
    """Base64画像を表示"""
    if base64_str:
        try:
            image = base64_to_image(base64_str)
            if image:
                st.image(image, caption=caption, width=width)
            else:
                st.warning("画像の表示に失敗しました")
        except Exception as e:
            st.error(f"画像の表示に失敗しました: {str(e)}")

def validate_and_process_image(uploaded_file):
    """アップロードされた画像ファイルを検証・処理"""
    if uploaded_file is None:
        return None, "ファイルが選択されていません"
    
    if uploaded_file.size > 5 * 1024 * 1024:  # 5MB
        return None, "ファイルサイズが5MBを超えています。より小さなファイルを選択してください。"
    
    allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
    if uploaded_file.type not in allowed_types:
        return None, "対応していないファイル形式です（PNG、JPEG、JPGのみ対応）"
    
    try:
        test_image = Image.open(uploaded_file)
        
        if test_image.mode not in ['RGB', 'RGBA', 'L', 'P']:
            return None, f"対応していない画像モードです: {test_image.mode}"
        
        if test_image.size[0] > 2000 or test_image.size[1] > 2000:
            st.warning("画像サイズが大きいため、自動的にリサイズされます")
        
        test_image.verify()
        uploaded_file.seek(0)
        
        base64_str = image_to_base64(uploaded_file)
        if base64_str is None:
            return None, "画像の変換に失敗しました"
        
        return base64_str, "OK"
        
    except Exception as e:
        return None, f"無効な画像ファイルです: {str(e)}"

# データベース初期化
@st.cache_resource
def init_connection():
    """PostgreSQL接続を初期化（SQLiteフォールバック）"""
    try:
        if "postgres" in st.secrets:
            conn = psycopg2.connect(**st.secrets["postgres"])
            st.success("✅ PostgreSQL接続成功")
            return conn
        else:
            st.warning("PostgreSQL設定なし、SQLiteを使用")
            return sqlite3.connect(':memory:')
    except Exception as e:
        st.error(f"PostgreSQL接続失敗: {e}")
        st.info("SQLiteフォールバック")
        return sqlite3.connect(':memory:')

def init_database():
    """PostgreSQLテーブルを初期化"""
    conn = init_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                userid TEXT,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER UNIQUE,
                session_data TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sicks (
                id SERIAL PRIMARY KEY,
                diesease TEXT NOT NULL,
                diesease_text TEXT NOT NULL,
                keyword TEXT,
                protocol TEXT,
                protocol_text TEXT,
                processing TEXT,
                processing_text TEXT,
                contrast TEXT,
                contrast_text TEXT,
                diesease_img TEXT,
                protocol_img TEXT,
                processing_img TEXT,
                contrast_img TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forms (
                id SERIAL PRIMARY KEY,
                title TEXT,
                main TEXT,
                post_img TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS protocols (
                id SERIAL PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                protocol_img TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        
    except Exception as e:
        st.error(f"テーブル作成エラー: {e}")
        conn.rollback()
    finally:
        conn.close()

# 初期データ投入
def insert_sample_data():
    """サンプルデータを挿入"""
    conn = init_connection()
    cursor = conn.cursor()
    
    # サンプルユーザーデータ
    sample_users = [
        ("管理者", "admin@hospital.jp", "Okiyoshi1126"),
        ("技師", "tech@hospital.jp", "Tech123")
    ]
    
    for user_data in sample_users:
        cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (user_data[1],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                          (user_data[0], user_data[1], hash_password(user_data[2])))
    
    # 疾患サンプルデータ
    sample_sicks = [
        ("脳梗塞", "脳血管が詰まる疾患", "脳梗塞,stroke", "頭部造影CT", "造影剤使用", "緊急検査", "迅速な対応", "あり", "造影剤注入", "", "", "", ""),
        ("肺炎", "肺の感染症", "肺炎,pneumonia", "胸部CT", "単純CT", "標準撮影", "呼吸停止", "なし", "造影不要", "", "", "", "")
    ]
    
    for sick in sample_sicks:
        cursor.execute("SELECT COUNT(*) FROM sicks WHERE diesease = %s", (sick[0],))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO sicks (
                    diesease, diesease_text, keyword, protocol, protocol_text,
                    processing, processing_text, contrast, contrast_text,
                    diesease_img, protocol_img, processing_img, contrast_img
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', sick)
    
    # お知らせサンプルデータ
    sample_forms = [
        ("システム運用開始", "CT医療システムの運用を開始しました。", ""),
        ("利用方法について", "疾患検索機能をご活用ください。", "")
    ]
    
    for form in sample_forms:
        cursor.execute("SELECT COUNT(*) FROM forms WHERE title = %s", (form[0],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO forms (title, main, post_img) VALUES (%s, %s, %s)", form)
    
    # CTプロトコルサンプルデータ
    sample_protocols = [
        ("頭部", "頭部単純CT", "スライス厚: 5mm\n電圧: 120kV\n電流: 250mA", ""),
        ("胸部", "胸部造影CT", "スライス厚: 1mm\n電圧: 120kV\n造影剤: 100ml", "")
    ]
    
    for protocol in sample_protocols:
        cursor.execute("SELECT COUNT(*) FROM protocols WHERE title = %s AND category = %s", (protocol[1], protocol[0]))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO protocols (category, title, content, protocol_img) VALUES (%s, %s, %s, %s)", protocol)
    
    conn.commit()
    conn.close()

# 認証機能
def hash_password(password):
    """パスワードをハッシュ化"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(email, password):
    """ユーザー認証"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE email = ? AND password = ?", 
                   (email, hash_password(password)))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(name, email, password):
    """新規ユーザー登録"""
    conn = init_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                      (name, email, hash_password(password)))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

# データベース操作関数
def get_all_sicks():
    """全疾患データを取得"""
    conn = init_connection()
    df = pd.read_sql_query("SELECT * FROM sicks ORDER BY diesease", conn)
    conn.close()
    return df

def search_sicks(search_term):
    """疾患データを検索"""
    conn = init_connection()
    query = """
        SELECT * FROM sicks 
        WHERE diesease LIKE ? OR diesease_text LIKE ? OR keyword LIKE ? 
        OR protocol LIKE ? OR protocol_text LIKE ? OR processing LIKE ? 
        OR processing_text LIKE ? OR contrast LIKE ? OR contrast_text LIKE ?
        ORDER BY diesease
    """
    search_pattern = f"%{search_term}%"
    params = [search_pattern] * 9
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_sick_by_id(sick_id):
    """IDで疾患データを取得"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sicks WHERE id = ?", (sick_id,))
    sick = cursor.fetchone()
    conn.close()
    return sick

def get_all_forms():
    """全お知らせを取得"""
    conn = init_connection()
    df = pd.read_sql_query("SELECT * FROM forms ORDER BY created_at DESC", conn)
    conn.close()
    return df

def get_form_by_id(form_id):
    """IDでお知らせを取得"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forms WHERE id = ?", (form_id,))
    form = cursor.fetchone()
    conn.close()
    return form

def add_sick(diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img=None, protocol_img=None, processing_img=None, contrast_img=None):
    """新しい疾患データを追加"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sicks (diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img, protocol_img, processing_img, contrast_img)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img, protocol_img, processing_img, contrast_img))
    conn.commit()
    conn.close()

def add_form(title, main, post_img=None):
    """新しいお知らせを追加"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO forms (title, main, post_img) VALUES (?, ?, ?)', (title, main, post_img))
    conn.commit()
    conn.close()

def update_sick(sick_id, diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img=None, protocol_img=None, processing_img=None, contrast_img=None):
    """疾患データを更新"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sicks SET diesease=?, diesease_text=?, keyword=?, protocol=?, protocol_text=?, 
        processing=?, processing_text=?, contrast=?, contrast_text=?, diesease_img=?, protocol_img=?, processing_img=?, contrast_img=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img, protocol_img, processing_img, contrast_img, sick_id))
    conn.commit()
    conn.close()

def update_form(form_id, title, main, post_img=None):
    """お知らせを更新"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE forms SET title=?, main=?, post_img=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (title, main, post_img, form_id))
    conn.commit()
    conn.close()

def delete_form(form_id):
    """お知らせを削除"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM forms WHERE id = ?', (form_id,))
    conn.commit()
    conn.close()

def delete_sick(sick_id):
    """疾患データを削除"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sicks WHERE id = ?', (sick_id,))
    conn.commit()
    conn.close()

def get_all_protocols():
    """全CTプロトコルを取得"""
    conn = init_connection()
    df = pd.read_sql_query("SELECT * FROM protocols ORDER BY category, title", conn)
    conn.close()
    return df

def get_protocols_by_category(category):
    """カテゴリー別CTプロトコルを取得"""
    conn = init_connection()
    df = pd.read_sql_query("SELECT * FROM protocols WHERE category = ? ORDER BY title", conn, params=[category])
    conn.close()
    return df

def search_protocols(search_term):
    """CTプロトコルを検索"""
    conn = init_connection()
    query = """
        SELECT * FROM protocols 
        WHERE title LIKE ? OR content LIKE ? OR category LIKE ?
        ORDER BY category, title
    """
    search_pattern = f"%{search_term}%"
    params = [search_pattern] * 3
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_protocol_by_id(protocol_id):
    """IDでCTプロトコルを取得"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM protocols WHERE id = ?", (protocol_id,))
    protocol = cursor.fetchone()
    conn.close()
    return protocol

def add_protocol(category, title, content, protocol_img=None):
    """新しいCTプロトコルを追加"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO protocols (category, title, content, protocol_img)
        VALUES (?, ?, ?, ?)
    ''', (category, title, content, protocol_img))
    conn.commit()
    conn.close()

def update_protocol(protocol_id, category, title, content, protocol_img=None):
    """CTプロトコルを更新"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE protocols SET category=?, title=?, content=?, protocol_img=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (category, title, content, protocol_img, protocol_id))
    conn.commit()
    conn.close()

def delete_protocol(protocol_id):
    """CTプロトコルを削除"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM protocols WHERE id = ?', (protocol_id,))
    conn.commit()
    conn.close()

def export_all_data():
    """全データをJSONでエクスポート"""
    conn = init_connection()
    
    # 全テーブルのデータを取得
    data = {
        'export_info': {
            'export_date': datetime.now().isoformat(),
            'version': '1.0',
            'app_name': 'How to CT Medical System'
        },
        'users': [],
        'sicks': [],
        'forms': [],
        'protocols': []
    }
    
    try:
        # ユーザーデータ（パスワードは除外）
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, created_at, updated_at FROM users")
        users = cursor.fetchall()
        for user in users:
            data['users'].append({
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'created_at': user[3] if user[3] else '',
                'updated_at': user[4] if user[4] else ''
            })
        
        # 疾患データ
        cursor.execute("SELECT * FROM sicks")
        sicks = cursor.fetchall()
        for sick in sicks:
            data['sicks'].append({
                'id': sick[0],
                'diesease': sick[1],
                'diesease_text': sick[2],
                'keyword': sick[3],
                'protocol': sick[4],
                'protocol_text': sick[5],
                'processing': sick[6],
                'processing_text': sick[7],
                'contrast': sick[8],
                'contrast_text': sick[9],
                'diesease_img': sick[10],
                'protocol_img': sick[11],
                'processing_img': sick[12],
                'contrast_img': sick[13],
                'created_at': sick[14] if sick[14] else '',
                'updated_at': sick[15] if sick[15] else ''
            })
        
        # お知らせデータ
        cursor.execute("SELECT * FROM forms")
        forms = cursor.fetchall()
        for form in forms:
            data['forms'].append({
                'id': form[0],
                'title': form[1],
                'main': form[2],
                'post_img': form[3],
                'created_at': form[4] if form[4] else '',
                'updated_at': form[5] if form[5] else ''
            })
        
        # CTプロトコルデータ
        cursor.execute("SELECT * FROM protocols")
        protocols = cursor.fetchall()
        for protocol in protocols:
            data['protocols'].append({
                'id': protocol[0],
                'category': protocol[1],
                'title': protocol[2],
                'content': protocol[3],
                'protocol_img': protocol[4],
                'created_at': protocol[5] if protocol[5] else '',
                'updated_at': protocol[6] if protocol[6] else ''
            })
        
    except Exception as e:
        conn.close()
        return None, f"データエクスポート中にエラーが発生しました: {str(e)}"
    
    conn.close()
    return data, "OK"

def create_backup_zip():
    """バックアップZIPファイルを作成"""
    try:
        # データをエクスポート
        data, error = export_all_data()
        if data is None:
            return None, error
        
        # メモリ上でZIPファイルを作成
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # JSONデータを追加
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            zip_file.writestr('backup_data.json', json_data.encode('utf-8'))
            
            # SQLiteファイルも追加
            try:
                zip_file.write('medical_ct.db', 'medical_ct.db')
            except FileNotFoundError:
                # SQLiteファイルが見つからない場合はスキップ
                pass
            
            # README追加
            readme_content = f"""
How to CT Medical System - データバックアップ

エクスポート日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}

含まれるファイル:
- backup_data.json: 全データのJSON形式
- medical_ct.db: SQLiteデータベースファイル（存在する場合）

復元方法:
1. backup_data.jsonを使用してデータを復元
2. または medical_ct.db を直接利用

注意事項:
- ユーザーのパスワードは含まれていません
- 復元時は管理者権限が必要です
"""
            zip_file.writestr('README.txt', readme_content.encode('utf-8'))
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue(), "OK"
        
    except Exception as e:
        return None, f"バックアップファイル作成中にエラーが発生しました: {str(e)}"

def restore_from_json(json_data):
    """JSONデータから復元（完全置換モード）"""
    try:
        conn = init_connection()
        cursor = conn.cursor()
        
        # 復元開始
        restored_counts = {
            'sicks': 0,
            'forms': 0,
            'protocols': 0,
            'deleted_sicks': 0,
            'deleted_forms': 0,
            'deleted_protocols': 0
        }
        
        # 移行タイプをチェック
        migration_type = json_data.get('export_info', {}).get('migration_type', 'unknown')
        
        if migration_type == 'complete_replacement':
            print("🔄 完全置換モードで復元開始...")
            
            # 既存データの件数を記録
            cursor.execute('SELECT COUNT(*) FROM sicks')
            restored_counts['deleted_sicks'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM forms')
            restored_counts['deleted_forms'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM protocols')
            restored_counts['deleted_protocols'] = cursor.fetchone()[0]
            
            print(f"📊 削除予定データ - 疾患:{restored_counts['deleted_sicks']}件, お知らせ:{restored_counts['deleted_forms']}件, プロトコル:{restored_counts['deleted_protocols']}件")
            
            # 既存データを完全削除（ユーザーデータとセッションは保持）
            print("🗑️ 既存データを削除中...")
            cursor.execute('DELETE FROM sicks')
            cursor.execute('DELETE FROM forms') 
            cursor.execute('DELETE FROM protocols')
            
            print("✅ 既存データ削除完了")
        else:
            print("➕ 追加モードで復元開始...")
        
        # 疾患データの投入
        if 'sicks' in json_data and json_data['sicks']:
            print(f"📋 Laravel版疾患データを投入中... ({len(json_data['sicks'])}件)")
            
            for i, sick in enumerate(json_data['sicks']):
                try:
                    cursor.execute('''
                        INSERT INTO sicks (
                            diesease, diesease_text, keyword, protocol, protocol_text,
                            processing, processing_text, contrast, contrast_text,
                            diesease_img, protocol_img, processing_img, contrast_img
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        sick.get('diesease', ''),
                        sick.get('diesease_text', ''),
                        sick.get('keyword', ''),
                        sick.get('protocol', ''),
                        sick.get('protocol_text', ''),
                        sick.get('processing', ''),
                        sick.get('processing_text', ''),
                        sick.get('contrast', ''),
                        sick.get('contrast_text', ''),
                        '',  # 画像データは空文字
                        '',  # 画像データは空文字
                        '',  # 画像データは空文字
                        ''   # 画像データは空文字
                    ))
                    restored_counts['sicks'] += 1
                    
                    # 進捗表示
                    if (i + 1) % 10 == 0 or (i + 1) == len(json_data['sicks']):
                        print(f"   進捗: {i + 1}/{len(json_data['sicks'])}件")
                        
                except sqlite3.Error as e:
                    print(f"   ⚠️ 疾患データスキップ: {sick.get('diesease', 'Unknown')} - {e}")
            
            print(f"✅ 疾患データ投入完了: {restored_counts['sicks']}件")
        
        # お知らせデータの投入
        if 'forms' in json_data and json_data['forms']:
            print(f"📢 Laravel版お知らせデータを投入中... ({len(json_data['forms'])}件)")
            
            for i, form in enumerate(json_data['forms']):
                try:
                    cursor.execute('''
                        INSERT INTO forms (title, main, post_img)
                        VALUES (?, ?, ?)
                    ''', (
                        form.get('title', ''),
                        form.get('main', ''),
                        ''  # 画像データは空文字
                    ))
                    restored_counts['forms'] += 1
                    
                    # 進捗表示
                    if (i + 1) % 5 == 0 or (i + 1) == len(json_data['forms']):
                        print(f"   進捗: {i + 1}/{len(json_data['forms'])}件")
                        
                except sqlite3.Error as e:
                    print(f"   ⚠️ お知らせデータスキップ: {form.get('title', 'Unknown')} - {e}")
            
            print(f"✅ お知らせデータ投入完了: {restored_counts['forms']}件")
        
        # CTプロトコルデータの投入
        if 'protocols' in json_data and json_data['protocols']:
            print(f"🔧 Laravel版プロトコルデータを投入中... ({len(json_data['protocols'])}件)")
            
            for i, protocol in enumerate(json_data['protocols']):
                try:
                    cursor.execute('''
                        INSERT INTO protocols (category, title, content, protocol_img)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        protocol.get('category', ''),
                        protocol.get('title', ''),
                        protocol.get('content', ''),
                        ''  # 画像データは空文字
                    ))
                    restored_counts['protocols'] += 1
                    
                    # 進捗表示
                    if (i + 1) % 5 == 0 or (i + 1) == len(json_data['protocols']):
                        print(f"   進捗: {i + 1}/{len(json_data['protocols'])}件")
                        
                except sqlite3.Error as e:
                    print(f"   ⚠️ プロトコルデータスキップ: {protocol.get('title', 'Unknown')} - {e}")
            
            print(f"✅ プロトコルデータ投入完了: {restored_counts['protocols']}件")
        
        # コミットして終了
        conn.commit()
        conn.close()
        
        print("\n🎉 データ移行完了！")
        print(f"📊 復元サマリー:")
        print(f"   - 疾患データ: {restored_counts['sicks']}件")
        print(f"   - お知らせ: {restored_counts['forms']}件")
        print(f"   - プロトコル: {restored_counts['protocols']}件")
        
        if migration_type == 'complete_replacement':
            print(f"📋 削除されたデータ:")
            print(f"   - 疾患データ: {restored_counts['deleted_sicks']}件")
            print(f"   - お知らせ: {restored_counts['deleted_forms']}件") 
            print(f"   - プロトコル: {restored_counts['deleted_protocols']}件")
        
        return True, restored_counts
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        print(f"❌ 復元エラー: {e}")
        return False, f"復元中にエラーが発生しました: {str(e)}"

def is_admin_user():
    """現在のユーザーが管理者かどうかチェック"""
    if 'user' not in st.session_state:
        return False
    # 管理者のメールアドレスをチェック（複数設定可能）
    admin_emails = ['admin@hospital.jp']  # デモユーザーも管理者権限
    return st.session_state.user['email'] in admin_emails

def validate_email(email):
    """メールアドレスの形式をチェック"""
    if not email:
        return False, "メールアドレスが入力されていません"
    
    # 基本的な形式チェック
    if '@' not in email:
        return False, "メールアドレスに@マークが含まれていません"
    
    # より詳細な正規表現チェック
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "メールアドレスの形式が正しくありません"
    
    # @マークの前後をチェック
    local_part, domain_part = email.split('@', 1)
    
    if len(local_part) == 0:
        return False, "@マークの前にユーザー名が必要です"
    
    if len(domain_part) == 0:
        return False, "@マークの後にドメイン名が必要です"
    
    if '.' not in domain_part:
        return False, "ドメイン名にピリオド(.)が含まれていません"
    
    # ドメイン部分の最後のピリオド以降をチェック
    domain_parts = domain_part.split('.')
    if len(domain_parts[-1]) < 2:
        return False, "トップレベルドメインが短すぎます"
    
    return True, "OK"

def get_all_users():
    """全ユーザー情報を取得（管理者用）"""
    conn = init_connection()
    df = pd.read_sql_query("SELECT id, name, email, created_at FROM users ORDER BY created_at DESC", conn)
    conn.close()
    return df

def delete_user(user_id):
    """ユーザーを削除（管理者用）"""
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def admin_register_user(name, email, password):
    """管理者による新規ユーザー登録"""
    return register_user(name, email, password)  # 既存の関数を再利用

# ページ関数定義
def show_welcome_page():
    """ウェルカムページ"""
    st.markdown("""
    <div style="text-align: center; padding: 2rem 0;">
        <div class="welcome-title">How to CT</div>
        <p style="font-size: 1.5rem; color: #666; margin-bottom: 3rem;">
            診療放射線技師向けCT検査マニュアルシステム
        </p>
        <p style="font-size: 1.2rem; color: #888;">
            疾患別の撮影プロトコル、造影手順、画像処理方法を検索できます
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("システムを開始", key="start_system", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()

def show_login_page():
    """ログインページ（新規登録無効化版）"""
    st.markdown('<div class="main-header"><h1>How to CT - ログイン</h1></div>', unsafe_allow_html=True)
    
    # 新規登録タブを削除
    tab1 = st.tabs(["ログイン"])
    
    with tab1[0]:  # タブが配列になるため[0]でアクセス
        with st.form("login_form"):
            email = st.text_input("メールアドレス", placeholder="example@hospital.com")
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True)
            
            if submitted:
                if email and password:
                    user = authenticate_user(email, password)
                    if user:
                        st.session_state.user = {
                            'id': user[0],
                            'name': user[1],
                            'email': user[2]
                        }
                        st.session_state.page = "home"
                        
                        # ログイン成功時にセッション情報をDBに保存
                        session_data = {'page': 'home'}
                        save_result = save_session_to_db(user[0], session_data)
                        
                        # デバッグ: セッション保存確認
                        st.success(f"ログインしました - ユーザーID: {user[0]}, メール: {user[2]}")
                        if save_result:
                            st.info("✅ セッション情報を保存しました")
                        else:
                            st.error("❌ セッション保存に失敗しました")
                        
                        # 保存されたセッションを確認
                        try:
                            conn = init_connection()
                            cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM user_sessions WHERE user_id = ?", (user[0],))
                            count = cursor.fetchone()[0]
                            st.info(f"保存確認: ユーザーID {user[0]} のセッション数 = {count}")
                            conn.close()
                        except Exception as e:
                            st.error(f"保存確認エラー: {e}")
                        
                        st.rerun()
                    else:
                        st.error("メールアドレスまたはパスワードが間違っています")
                else:
                    st.error("全ての項目を入力してください")
        
        # 利用可能アカウント情報
        # st.markdown("---")
        # st.info("""
        # **利用可能なアカウント:**
        # - 管理者: admin@hospital.jp / Okiyoshi1126
        # - 技師: tech@hospital.jp / Tech123
        # ※新規アカウントが必要な場合は管理者にお問い合わせください
        # """)

def show_home_page():
    """ホームページ"""
    update_session_in_db()
    st.markdown('<div class="main-header"><h1>How to CT - CT検査マニュアル</h1></div>', unsafe_allow_html=True)
    
    if 'user' in st.session_state:
        st.markdown(f"**ようこそ、{st.session_state.user['name']}さん**")
    
    st.markdown("""
    <div class="disease-card">
        <h3>疾患検索</h3>
        <p>疾患名、症状、キーワードから適切な検査プロトコルを検索できます。<br>
        撮影条件、造影方法、画像処理方法を確認できます。</p>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("疾患検索を開始", key="search_button", use_container_width=True):
        st.session_state.page = "search"
        st.rerun()
    
    st.markdown('<h3 class="section-title">最新のお知らせ</h3>', unsafe_allow_html=True)
    df_forms = get_all_forms()
    if not df_forms.empty:
        latest_notices = df_forms.head(7)
        for idx, row in latest_notices.iterrows():
            with st.expander(f"{row['title']}"):
                preview_text = row['main'][:150] + "..." if len(str(row['main'])) > 150 else row['main']
                display_rich_content(preview_text)
                st.caption(f"投稿日: {row['created_at']}")
                if st.button("詳細を見る", key=f"home_notice_preview_{row['id']}"):
                    st.session_state.selected_notice_id = row['id']
                    st.session_state.page = "notice_detail"
                    st.rerun()
    else:
        st.info("お知らせがありません")

def show_search_page():
    """疾患検索ページ（修正版）"""
    st.markdown('<div class="main-header"><h1>疾患検索</h1></div>', unsafe_allow_html=True)
    
    # 検索フォーム
    with st.form("search_form"):
        search_term = st.text_input("検索キーワード", placeholder="例：胸痛、大動脈解離、造影CT、MPRなど")
        submitted = st.form_submit_button("検索", use_container_width=True)
    
    # 新規作成・全疾患表示ボタン
    col1, col2 = st.columns(2)
    with col1:
        if st.button("新規疾患データ作成", key="search_create_new"):
            st.session_state.page = "create_disease"
            st.rerun()
    with col2:
        if st.button("全疾患一覧を表示", key="search_show_all"):
            st.session_state.show_all_diseases = True
            # 検索結果をクリア
            if 'search_results' in st.session_state:
                del st.session_state.search_results
            st.rerun()
    
    # 検索実行と結果保存
    if submitted and search_term:
        df = search_sicks(search_term)
        st.session_state.search_results = df
        # 全疾患表示フラグをクリア
        if 'show_all_diseases' in st.session_state:
            del st.session_state.show_all_diseases
        st.rerun()
    
    # 検索結果表示
    if 'search_results' in st.session_state:
        df = st.session_state.search_results
        if not df.empty:
            st.success(f"{len(df)}件の検索結果が見つかりました")
            
            for idx, row in df.iterrows():
                st.markdown(f'<div class="search-result">', unsafe_allow_html=True)
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**{row['diesease']}**")
                    if row['keyword']:
                        st.markdown(f"**症状・キーワード:** {row['keyword']}")
                    if row['protocol']:
                        st.markdown(f"**撮影プロトコル:** {row['protocol']}")
                    
                    preview_text = row['diesease_text'][:150] + "..." if len(str(row['diesease_text'])) > 150 else row['diesease_text']
                    display_rich_content(preview_text)
                
                with col2:
                    if st.button("詳細を見る", key=f"search_detail_{row['id']}"):
                        st.session_state.selected_sick_id = int(row['id'])
                        st.session_state.page = "detail"
                        # 検索結果を保持
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            # 検索結果をクリアするボタン
            if st.button("検索結果をクリア", key="clear_search_results"):
                if 'search_results' in st.session_state:
                    del st.session_state.search_results
                st.rerun()
        else:
            st.info("該当する疾患が見つかりませんでした")
            
            # 検索結果をクリアするボタン
            if st.button("検索結果をクリア", key="clear_no_results"):
                if 'search_results' in st.session_state:
                    del st.session_state.search_results
                st.rerun()
    
    # 全疾患表示
    elif st.session_state.get('show_all_diseases', False):
        df = get_all_sicks()
        if not df.empty:
            st.subheader("全疾患一覧")
            
            for idx, row in df.iterrows():
                st.markdown(f'<div class="search-result">', unsafe_allow_html=True)
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**{row['diesease']}**")
                    if row['keyword']:
                        st.markdown(f"**キーワード:** {row['keyword']}")
                    if row['protocol']:
                        st.markdown(f"**プロトコル:** {row['protocol']}")
                
                with col2:
                    if st.button("詳細を見る", key=f"all_detail_{row['id']}"):
                        st.session_state.selected_sick_id = int(row['id'])
                        st.session_state.page = "detail"
                        if 'show_all_diseases' in st.session_state:
                            del st.session_state.show_all_diseases
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("一覧を閉じる", key="close_all_list"):
            if 'show_all_diseases' in st.session_state:
                del st.session_state.show_all_diseases
            st.rerun()

def show_detail_page():
    """疾患詳細ページ（修正版）"""
    if 'selected_sick_id' not in st.session_state:
        st.error("疾患が選択されていません")
        if st.button("検索に戻る", key="detail_back_no_selection"):
            st.session_state.page = "search"
            st.rerun()
        return
    
    sick_data = get_sick_by_id(st.session_state.selected_sick_id)
    if not sick_data:
        st.error("疾患データが見つかりません")
        if st.button("検索に戻る", key="detail_back_not_found"):
            st.session_state.page = "search"
            if 'selected_sick_id' in st.session_state:
                del st.session_state.selected_sick_id
            st.rerun()
        return
    
    st.title(f"{sick_data[1]} - 詳細マニュアル")
    
    # 作成日・更新日表示
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"作成日: {sick_data[14]}")
    with col2:
        st.caption(f"更新日: {sick_data[15]}")
    
    # タブで情報を分類
    tab1, tab2, tab3, tab4 = st.tabs(["疾患情報", "撮影プロトコル", "造影プロトコル", "画像処理"])
    
    with tab1:
        st.markdown('<div class="disease-section">', unsafe_allow_html=True)
        st.markdown(f"### 疾患名: {sick_data[1]}")
        if sick_data[3]:  # keyword
            st.markdown(f"**症状・キーワード:** {sick_data[3]}")
        st.markdown("**疾患詳細:**")
        display_rich_content(sick_data[2])
        
        # 疾患画像表示
        if sick_data[10]:  # diesease_img
            st.markdown("**疾患関連画像:**")
            display_image_with_caption(sick_data[10], "疾患画像")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab2:
        st.markdown('<div class="protocol-section">', unsafe_allow_html=True)
        if sick_data[4]:  # protocol
            st.markdown(f"### 撮影プロトコル: {sick_data[4]}")
        if sick_data[5]:  # protocol_text
            st.markdown("**詳細手順:**")
            display_rich_content(sick_data[5])
        else:
            st.info("撮影プロトコルの詳細が未設定です")
        
        # 撮影プロトコル画像表示
        if sick_data[11]:  # protocol_img
            st.markdown("**撮影プロトコル画像:**")
            display_image_with_caption(sick_data[11], "撮影プロトコル画像")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab3:
        st.markdown('<div class="contrast-section">', unsafe_allow_html=True)
        if sick_data[8]:  # contrast
            st.markdown(f"### 造影プロトコル: {sick_data[8]}")
        if sick_data[9]:  # contrast_text
            st.markdown("**造影手順:**")
            display_rich_content(sick_data[9])
        else:
            st.info("造影プロトコルの詳細が未設定です")
        
        # 造影プロトコル画像表示
        if sick_data[13]:  # contrast_img
            st.markdown("**造影プロトコル画像:**")
            display_image_with_caption(sick_data[13], "造影プロトコル画像")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab4:
        st.markdown('<div class="processing-section">', unsafe_allow_html=True)
        if sick_data[6]:  # processing
            st.markdown(f"### 画像処理: {sick_data[6]}")
        if sick_data[7]:  # processing_text
            st.markdown("**処理方法:**")
            display_rich_content(sick_data[7])
        else:
            st.info("画像処理の詳細が未設定です")
        
        # 画像処理画像表示
        if sick_data[12]:  # processing_img
            st.markdown("**画像処理画像:**")
            display_image_with_caption(sick_data[12], "画像処理画像")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 編集・削除・戻るボタン（タブの下、縦並び）
    if st.button("編集", key="detail_edit_disease"):
        st.session_state.edit_sick_id = sick_data[0]
        st.session_state.page = "edit_disease"
        st.rerun()
    
    if st.button("削除", key="detail_delete_disease"):
        if st.session_state.get('confirm_delete', False):
            delete_sick(sick_data[0])
            st.success("疾患データを削除しました")
            st.session_state.page = "search"
            if 'confirm_delete' in st.session_state:
                del st.session_state.confirm_delete
            if 'selected_sick_id' in st.session_state:
                del st.session_state.selected_sick_id
            st.rerun()
        else:
            st.session_state.confirm_delete = True
            st.warning("削除ボタンをもう一度押すと削除されます")
    
    if st.button("検索に戻る", key="detail_back_to_search"):
        st.session_state.page = "search"
        if 'selected_sick_id' in st.session_state:
            del st.session_state.selected_sick_id
        st.rerun()

def show_notices_page():
    """お知らせ一覧ページ"""
    st.markdown('<div class="main-header"><h1>お知らせ一覧</h1></div>', unsafe_allow_html=True)
    
    # 新規作成ボタン
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("新規お知らせ作成", key="notices_create_notice"):
            st.session_state.page = "create_notice"
            st.rerun()
    
    df = get_all_forms()
    if not df.empty:
        for idx, row in df.iterrows():
            st.markdown('<div class="notice-card">', unsafe_allow_html=True)
            col1, col2 = st.columns([4, 1])
            
            with col1:
                st.markdown(f"### {row['title']}")
                # リッチテキストのプレビュー表示
                preview_text = row['main'][:200] + "..." if len(str(row['main'])) > 200 else row['main']
                display_rich_content(preview_text)
                st.caption(f"作成日: {row['created_at']}")
            
            with col2:
                if st.button("詳細", key=f"notices_detail_{row['id']}"):
                    st.session_state.selected_notice_id = row['id']
                    st.session_state.page = "notice_detail"
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("お知らせがありません")

def show_notice_detail_page():
    """お知らせ詳細ページ"""
    if 'selected_notice_id' not in st.session_state:
        st.error("お知らせが選択されていません")
        if st.button("お知らせ一覧に戻る", key="notice_detail_back_no_selection"):
            st.session_state.page = "notices"
            st.rerun()
        return
    
    form_data = get_form_by_id(st.session_state.selected_notice_id)
    if not form_data:
        st.error("お知らせが見つかりません")
        if st.button("お知らせ一覧に戻る", key="notice_detail_back_not_found"):
            st.session_state.page = "notices"
            if 'selected_notice_id' in st.session_state:
                del st.session_state.selected_notice_id
            st.rerun()
        return
    
    st.title(f"{form_data[1]}")
    
    st.markdown('<div class="notice-card">', unsafe_allow_html=True)
    display_rich_content(form_data[2])  # main content をリッチテキストとして表示
    
    # お知らせ画像表示
    if form_data[3]:  # post_img
        st.markdown("**添付画像:**")
        display_image_with_caption(form_data[3], "お知らせ画像")
    
    st.caption(f"作成日: {form_data[4]}")
    st.caption(f"更新日: {form_data[5]}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 編集・削除・戻るボタン（本文下、左詰め）
    col1, col2, col3 = st.columns([1, 1, 1])
    # 編集・削除・戻るボタン（本文下、縦並び）
    if st.button("編集", key="notice_detail_edit_notice"):
        st.session_state.edit_notice_id = form_data[0]
        st.session_state.page = "edit_notice"
        st.rerun()
    
    if st.button("削除", key="notice_detail_delete_notice"):
        if st.session_state.get('confirm_delete_notice', False):
            delete_form(form_data[0])
            st.success("お知らせを削除しました")
            st.session_state.page = "notices"
            if 'confirm_delete_notice' in st.session_state:
                del st.session_state.confirm_delete_notice
            if 'selected_notice_id' in st.session_state:
                del st.session_state.selected_notice_id
            st.rerun()
        else:
            st.session_state.confirm_delete_notice = True
            st.warning("削除ボタンをもう一度押すと削除されます")
    
    if st.button("戻る", key="notice_detail_back_to_notices"):
        st.session_state.page = "notices"
        if 'selected_notice_id' in st.session_state:
            del st.session_state.selected_notice_id
        st.rerun()

def show_create_notice_page():
    """お知らせ作成ページ"""
    st.markdown('<div class="main-header"><h1>新規お知らせ作成</h1></div>', unsafe_allow_html=True)
    
    with st.form("create_notice_form"):
        title = st.text_input("タイトル *", placeholder="例：新型CT装置導入のお知らせ")
        
        # リッチテキストエディタを使用
        st.markdown("**本文 ***")
        main = create_rich_text_editor(
            content="",
            placeholder="お知らせの内容を入力してください。見出し、太字、色付け、リストなどを使って見やすく作成できます。",
            key="notice_main_editor",
            height=400
        )
        
        # お知らせ画像アップロード
        st.markdown("**添付画像**")
        notice_image = st.file_uploader("お知らせ画像をアップロード", type=['png', 'jpg', 'jpeg'], key="create_notice_img_upload",
                                      help="推奨サイズ: 5MB以下、形式: PNG, JPEG, JPG")
        if notice_image is not None:
            st.image(notice_image, caption="アップロード予定のお知らせ画像", width=300)
        
        submitted = st.form_submit_button("登録", use_container_width=True)
        
        if submitted:
            if title and main:
                try:
                    # 画像をBase64に変換
                    notice_img_b64 = None
                    if notice_image is not None:
                        notice_img_b64, error_msg = validate_and_process_image(notice_image)
                        if notice_img_b64 is None:
                            st.error(f"お知らせ画像: {error_msg}")
                            return
                    
                    add_form(title, main, notice_img_b64)
                    st.success("お知らせを登録しました")
                    st.session_state.page = "notices"
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"データの保存中にエラーが発生しました: {str(e)}")
            else:
                st.error("タイトルと本文は必須項目です")
    
    if st.button("戻る", key="create_notice_back_from_create"):
        st.session_state.page = "notices"
        st.rerun()

def show_edit_notice_page():
    """お知らせ編集ページ"""
    if 'edit_notice_id' not in st.session_state:
        st.error("編集対象が選択されていません")
        if st.button("お知らせ一覧に戻る", key="edit_notice_back_no_selection"):
            st.session_state.page = "notices"
            st.rerun()
        return
    
    form_data = get_form_by_id(st.session_state.edit_notice_id)
    if not form_data:
        st.error("お知らせが見つかりません")
        if st.button("お知らせ一覧に戻る", key="edit_notice_back_not_found"):
            st.session_state.page = "notices"
            if 'edit_notice_id' in st.session_state:
                del st.session_state.edit_notice_id
            st.rerun()
        return
    
    st.markdown('<div class="main-header"><h1>お知らせ編集</h1></div>', unsafe_allow_html=True)
    
    with st.form("edit_notice_form"):
        title = st.text_input("タイトル *", value=form_data[1])
        
        # リッチテキストエディタを使用（既存データを初期値として設定）
        st.markdown("**本文 ***")
        main = create_rich_text_editor(
            content=form_data[2] or "",
            placeholder="お知らせの内容を入力してください。見出し、太字、色付け、リストなどを使って見やすく作成できます。",
            key="edit_notice_main_editor",
            height=400
        )
        
        # お知らせ画像編集
        st.markdown("**添付画像**")
        if form_data[3]:  # 既存画像がある場合
            st.markdown("現在の画像:")
            display_image_with_caption(form_data[3], "現在のお知らせ画像", width=200)
            replace_notice_img = st.checkbox("お知らせ画像を変更する")
            if replace_notice_img:
                notice_image = st.file_uploader("新しいお知らせ画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_notice_img_upload")
                if notice_image is not None:
                    st.image(notice_image, caption="新しいお知らせ画像", width=300)
            else:
                notice_image = None
        else:
            notice_image = st.file_uploader("お知らせ画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_notice_img_upload")
            if notice_image is not None:
                st.image(notice_image, caption="お知らせ画像", width=300)
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("更新", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("キャンセル", use_container_width=True)
        
        if submitted:
            if title and main:
                try:
                    # 画像処理（既存画像を保持するか新しい画像に更新するか）
                    notice_img_b64 = form_data[3]  # 既存画像
                    
                    # 新しい画像がアップロードされた場合のみ更新
                    if notice_image is not None:
                        notice_img_b64, error_msg = validate_and_process_image(notice_image)
                        if notice_img_b64 is None:
                            st.error(f"お知らせ画像: {error_msg}")
                            return
                    
                    update_form(st.session_state.edit_notice_id, title, main, notice_img_b64)
                    st.success("お知らせを更新しました")
                    st.session_state.selected_notice_id = st.session_state.edit_notice_id
                    st.session_state.page = "notice_detail"
                    del st.session_state.edit_notice_id
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"データの保存中にエラーが発生しました: {str(e)}")
            else:
                st.error("タイトルと本文は必須項目です")
        
        if cancel:
            st.session_state.selected_notice_id = st.session_state.edit_notice_id
            st.session_state.page = "notice_detail"
            del st.session_state.edit_notice_id
            st.rerun()

def show_create_disease_page():
    """疾患データ作成ページ"""
    st.markdown('<div class="main-header"><h1>新規疾患データ作成</h1></div>', unsafe_allow_html=True)
    
    with st.form("create_disease_form"):
        # 疾患情報
        st.markdown("### 📋 疾患情報")
        disease_name = st.text_input("疾患名 *", placeholder="例：大動脈解離")
        
        # リッチテキストエディタで疾患詳細
        st.markdown("**疾患詳細 ***")
        disease_text = create_rich_text_editor(
            content="",
            placeholder="疾患の概要、原因、症状などを入力してください。太字、色付け、リストなども使用できます。",
            key="disease_text_editor",
            height=300
        )
        
        keyword = st.text_input("症状・キーワード", placeholder="例：胸痛、背部痛、急性")
        disease_image = st.file_uploader("疾患関連画像をアップロード", type=['png', 'jpg', 'jpeg'], key="create_disease_img_upload",
                                        help="対応形式: PNG, JPEG, JPG（最大5MB）")
        disease_img_b64 = None
        if disease_image:
            disease_img_b64, error_msg = validate_and_process_image(disease_image)
            if disease_img_b64 is None:
                st.error(f"疾患画像: {error_msg}")
            else:
                st.image(disease_image, caption="疾患関連画像プレビュー", width=300)
        
        st.markdown("---")
        
        # 撮影プロトコル
        st.markdown("### 📸 撮影プロトコル")
        protocol = st.text_input("撮影プロトコル", placeholder="例：胸腹部造影CT")
        
        st.markdown("**撮影プロトコル詳細**")
        protocol_text = create_rich_text_editor(
            content="",
            placeholder="撮影手順、設定値などを入力してください。",
            key="protocol_text_editor",
            height=200
        )
        
        protocol_image = st.file_uploader("撮影プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], key="create_protocol_img_upload",
                                        help="対応形式: PNG, JPEG, JPG（最大5MB）")
        protocol_img_b64 = None
        if protocol_image:
            protocol_img_b64, error_msg = validate_and_process_image(protocol_image)
            if protocol_img_b64 is None:
                st.error(f"撮影プロトコル画像: {error_msg}")
            else:
                st.image(protocol_image, caption="撮影プロトコル画像プレビュー", width=300)
        
        st.markdown("---")
        
        # 造影プロトコル
        st.markdown("### 💉 造影プロトコル")
        contrast = st.text_input("造影プロトコル", placeholder="例：オムニパーク300 100ml")
        
        st.markdown("**造影プロトコル詳細**")
        contrast_text = create_rich_text_editor(
            content="",
            placeholder="造影剤の種類、量、投与方法などを入力してください。",
            key="contrast_text_editor",
            height=200
        )
        
        contrast_image = st.file_uploader("造影プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], key="create_contrast_img_upload",
                                        help="対応形式: PNG, JPEG, JPG（最大5MB）")
        contrast_img_b64 = None
        if contrast_image:
            contrast_img_b64, error_msg = validate_and_process_image(contrast_image)
            if contrast_img_b64 is None:
                st.error(f"造影プロトコル画像: {error_msg}")
            else:
                st.image(contrast_image, caption="造影プロトコル画像プレビュー", width=300)
        
        st.markdown("---")
        
        # 画像処理
        st.markdown("### 🖥️ 画像処理")
        processing = st.text_input("画像処理", placeholder="例：MPR、VR、CPR")
        
        st.markdown("**画像処理詳細**")
        processing_text = create_rich_text_editor(
            content="",
            placeholder="画像処理の手順、設定などを入力してください。",
            key="processing_text_editor",
            height=200
        )
        
        processing_image = st.file_uploader("画像処理画像をアップロード", type=['png', 'jpg', 'jpeg'], key="create_processing_img_upload",
                                          help="対応形式: PNG, JPEG, JPG（最大5MB）")
        processing_img_b64 = None
        if processing_image:
            processing_img_b64, error_msg = validate_and_process_image(processing_image)
            if processing_img_b64 is None:
                st.error(f"画像処理画像: {error_msg}")
            else:
                st.image(processing_image, caption="画像処理画像プレビュー", width=300)
        
        # フォーム送信
        col1, col2 = st.columns([1, 1])
        with col1:
            submitted = st.form_submit_button("📝 疾患データを作成", use_container_width=True)
        with col2:
            if st.form_submit_button("🔙 戻る", use_container_width=True):
                st.session_state.page = "search"
                st.rerun()
    
    # フォーム処理
    if submitted:
        if not disease_name or not disease_text:
            st.error("疾患名と疾患詳細は必須項目です")
        else:
            try:
                add_sick(
                    disease_name, disease_text, keyword or "",
                    protocol or "", protocol_text or "",
                    processing or "", processing_text or "",
                    contrast or "", contrast_text or "",
                    disease_img_b64, protocol_img_b64,
                    processing_img_b64, contrast_img_b64
                )
                
                # 作成成功フラグを設定
                st.session_state.disease_created = True
                st.session_state.created_disease_name = disease_name
                st.rerun()
                
            except Exception as e:
                st.error(f"データ作成中にエラーが発生しました: {str(e)}")
    
    # 作成完了メッセージと確認画面
    if st.session_state.get('disease_created', False):
        st.success("✅ 疾患データが正常に作成されました！")
        st.balloons()
        
        # 作成された疾患の情報を表示
        st.markdown(f"""
        <div class="disease-card">
            <h3>📋 作成完了</h3>
            <p><strong>疾患名:</strong> {st.session_state.get('created_disease_name', '')}</p>
            <p><strong>作成日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            <p>データベースに正常に保存されました。</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 確認後のアクションボタン
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("🔍 検索ページに戻る", key="create_success_back_to_search", use_container_width=True):
                # 成功フラグをクリア
                if 'disease_created' in st.session_state:
                    del st.session_state.disease_created
                if 'created_disease_name' in st.session_state:
                    del st.session_state.created_disease_name
                st.session_state.page = "search"
                st.rerun()
        
        with col2:
            if st.button("📝 続けて作成", key="create_success_continue", use_container_width=True):
                # 成功フラグをクリアして新規作成を続行
                if 'disease_created' in st.session_state:
                    del st.session_state.disease_created
                if 'created_disease_name' in st.session_state:
                    del st.session_state.created_disease_name
                st.rerun()
        
        with col3:
            if st.button("👁️ 作成した疾患を確認", key="create_success_view_created", use_container_width=True):
                # 作成した疾患の詳細ページに移動
                # 最新の疾患データを取得
                conn = init_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM sicks WHERE diesease = ? ORDER BY created_at DESC LIMIT 1", 
                              (st.session_state.get('created_disease_name', ''),))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    st.session_state.selected_sick_id = result[0]
                    st.session_state.page = "detail"
                    # 成功フラグをクリア
                    if 'disease_created' in st.session_state:
                        del st.session_state.disease_created
                    if 'created_disease_name' in st.session_state:
                        del st.session_state.created_disease_name
                    st.rerun()
        
        # この場合は戻るボタンを表示しない
        return
    
    # 戻るボタン（通常時のみ表示）
    if st.button("戻る", key="create_disease_back_from_create"):
        st.session_state.page = "search"
        st.rerun()

def show_edit_disease_page():
    """疾患データ編集ページ"""
    if 'edit_sick_id' not in st.session_state:
        st.error("編集対象が選択されていません")
        if st.button("検索に戻る", key="edit_disease_back_no_selection"):
            st.session_state.page = "search"
            st.rerun()
        return
    
    sick_data = get_sick_by_id(st.session_state.edit_sick_id)
    if not sick_data:
        st.error("疾患データが見つかりません")
        if st.button("検索に戻る", key="edit_disease_back_not_found"):
            st.session_state.page = "search"
            if 'edit_sick_id' in st.session_state:
                del st.session_state.edit_sick_id
            st.rerun()
        return
    
    st.markdown('<div class="main-header"><h1>疾患データ編集</h1></div>', unsafe_allow_html=True)
    
    with st.form("edit_disease_form"):
        # 疾患情報
        st.markdown("### 📋 疾患情報")
        disease_name = st.text_input("疾患名 *", value=sick_data[1])
        
        # リッチテキストエディタで疾患詳細
        st.markdown("**疾患詳細 ***")
        disease_text = create_rich_text_editor(
            content=sick_data[2] or "",
            placeholder="疾患の概要、原因、症状などを入力してください。太字、色付け、リストなども使用できます。",
            key="edit_disease_text_editor",
            height=300
        )
        
        keyword = st.text_input("症状・キーワード", value=sick_data[3] or "")
        
        # 疾患画像編集
        st.markdown("**疾患関連画像**")
        if sick_data[10]:  # 既存画像がある場合
            st.markdown("現在の画像:")
            display_image_with_caption(sick_data[10], "現在の疾患画像", width=200)
            replace_disease_img = st.checkbox("疾患画像を変更する")
            if replace_disease_img:
                disease_image = st.file_uploader("新しい疾患画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_disease_img_upload")
                if disease_image is not None:
                    st.image(disease_image, caption="新しい疾患画像", width=300)
            else:
                disease_image = None
        else:
            disease_image = st.file_uploader("疾患画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_disease_img_upload")
            if disease_image is not None:
                st.image(disease_image, caption="疾患画像", width=300)
        
        st.markdown("---")
        
        # 撮影プロトコル
        st.markdown("### 📸 撮影プロトコル")
        protocol = st.text_input("撮影プロトコル", value=sick_data[4] or "")
        
        st.markdown("**撮影プロトコル詳細**")
        protocol_text = create_rich_text_editor(
            content=sick_data[5] or "",
            placeholder="撮影手順、設定値などを入力してください。",
            key="edit_protocol_text_editor",
            height=200
        )
        
        # 撮影プロトコル画像編集
        st.markdown("**撮影プロトコル画像**")
        if sick_data[11]:  # 既存画像がある場合
            st.markdown("現在の画像:")
            display_image_with_caption(sick_data[11], "現在の撮影プロトコル画像", width=200)
            replace_protocol_img = st.checkbox("撮影プロトコル画像を変更する")
            if replace_protocol_img:
                protocol_image = st.file_uploader("新しい撮影プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_protocol_img_upload")
                if protocol_image is not None:
                    st.image(protocol_image, caption="新しい撮影プロトコル画像", width=300)
            else:
                protocol_image = None
        else:
            protocol_image = st.file_uploader("撮影プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_protocol_img_upload")
            if protocol_image is not None:
                st.image(protocol_image, caption="撮影プロトコル画像", width=300)
        
        st.markdown("---")
        
        # 造影プロトコル
        st.markdown("### 💉 造影プロトコル")
        contrast = st.text_input("造影プロトコル", value=sick_data[8] or "")
        
        st.markdown("**造影プロトコル詳細**")
        contrast_text = create_rich_text_editor(
            content=sick_data[9] or "",
            placeholder="造影剤の種類、量、投与方法などを入力してください。",
            key="edit_contrast_text_editor",
            height=200
        )
        
        # 造影プロトコル画像編集
        st.markdown("**造影プロトコル画像**")
        if sick_data[13]:  # 既存画像がある場合
            st.markdown("現在の画像:")
            display_image_with_caption(sick_data[13], "現在の造影プロトコル画像", width=200)
            replace_contrast_img = st.checkbox("造影プロトコル画像を変更する")
            if replace_contrast_img:
                contrast_image = st.file_uploader("新しい造影プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_contrast_img_upload")
                if contrast_image is not None:
                    st.image(contrast_image, caption="新しい造影プロトコル画像", width=300)
            else:
                contrast_image = None
        else:
            contrast_image = st.file_uploader("造影プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_contrast_img_upload")
            if contrast_image is not None:
                st.image(contrast_image, caption="造影プロトコル画像", width=300)
        
        st.markdown("---")
        
        # 画像処理
        st.markdown("### 🖥️ 画像処理")
        processing = st.text_input("画像処理", value=sick_data[6] or "")
        
        st.markdown("**画像処理詳細**")
        processing_text = create_rich_text_editor(
            content=sick_data[7] or "",
            placeholder="画像処理の手順、設定などを入力してください。",
            key="edit_processing_text_editor",
            height=200
        )
        
        # 画像処理画像編集
        st.markdown("**画像処理画像**")
        if sick_data[12]:  # 既存画像がある場合
            st.markdown("現在の画像:")
            display_image_with_caption(sick_data[12], "現在の画像処理画像", width=200)
            replace_processing_img = st.checkbox("画像処理画像を変更する")
            if replace_processing_img:
                processing_image = st.file_uploader("新しい画像処理画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_processing_img_upload")
                if processing_image is not None:
                    st.image(processing_image, caption="新しい画像処理画像", width=300)
            else:
                processing_image = None
        else:
            processing_image = st.file_uploader("画像処理画像をアップロード", type=['png', 'jpg', 'jpeg'], key="edit_processing_img_upload")
            if processing_image is not None:
                st.image(processing_image, caption="画像処理画像", width=300)
        
        # フォーム送信
        col1, col2 = st.columns([1, 1])
        with col1:
            submitted = st.form_submit_button("💾 更新", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("❌ キャンセル", use_container_width=True)
    
    # フォーム処理
    if submitted:
        if not disease_name or not disease_text:
            st.error("疾患名と疾患詳細は必須項目です")
        else:
            try:
                # 画像処理（既存画像を保持するか新しい画像に更新するか）
                disease_img_b64 = sick_data[10]  # 既存画像
                protocol_img_b64 = sick_data[11]
                processing_img_b64 = sick_data[12]
                contrast_img_b64 = sick_data[13]
                
                # 新しい画像がアップロードされた場合のみ更新
                if disease_image is not None:
                    disease_img_b64, error_msg = validate_and_process_image(disease_image)
                    if disease_img_b64 is None:
                        st.error(f"疾患画像: {error_msg}")
                        return
                
                if protocol_image is not None:
                    protocol_img_b64, error_msg = validate_and_process_image(protocol_image)
                    if protocol_img_b64 is None:
                        st.error(f"撮影プロトコル画像: {error_msg}")
                        return
                
                if contrast_image is not None:
                    contrast_img_b64, error_msg = validate_and_process_image(contrast_image)
                    if contrast_img_b64 is None:
                        st.error(f"造影プロトコル画像: {error_msg}")
                        return
                
                if processing_image is not None:
                    processing_img_b64, error_msg = validate_and_process_image(processing_image)
                    if processing_img_b64 is None:
                        st.error(f"画像処理画像: {error_msg}")
                        return
                
                update_sick(
                    st.session_state.edit_sick_id,
                    disease_name, disease_text, keyword,
                    protocol, protocol_text,
                    processing, processing_text,
                    contrast, contrast_text,
                    disease_img_b64, protocol_img_b64,
                    processing_img_b64, contrast_img_b64
                )
                
                st.success("疾患データを更新しました")
                st.session_state.selected_sick_id = st.session_state.edit_sick_id
                st.session_state.page = "detail"
                del st.session_state.edit_sick_id
                st.rerun()
                
            except Exception as e:
                st.error(f"データ更新中にエラーが発生しました: {str(e)}")
    
    if cancel:
        st.session_state.selected_sick_id = st.session_state.edit_sick_id
        st.session_state.page = "detail"
        del st.session_state.edit_sick_id
        st.rerun()

def show_protocols_page():
    """CTプロトコル一覧ページ"""
    st.markdown('<div class="main-header"><h1>📋 CTプロトコル管理</h1></div>', unsafe_allow_html=True)
    
    # カテゴリー定義
    categories = ["頭部", "頸部", "胸部", "腹部", "下肢", "上肢", "特殊"]
    
    # 新規作成・検索ボタン
    col1, col2 = st.columns(2)
    with col1:
        if st.button("新規プロトコル作成", key="protocols_create_new"):
            st.session_state.page = "create_protocol"
            st.rerun()
    with col2:
        # 検索フォーム
        with st.form("protocol_search_form"):
            search_term = st.text_input("プロトコル検索", placeholder="タイトル、内容、カテゴリーで検索")
            search_submitted = st.form_submit_button("🔍 検索")
    
    # 検索結果表示
    if search_submitted and search_term:
        df = search_protocols(search_term)
        st.session_state.protocol_search_results = df
        st.rerun()
    
    if 'protocol_search_results' in st.session_state:
        df = st.session_state.protocol_search_results
        if not df.empty:
            st.success(f"{len(df)}件の検索結果が見つかりました")
            
            for idx, row in df.iterrows():
                st.markdown(f'<div class="search-result">', unsafe_allow_html=True)
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**[{row['category']}] {row['title']}**")
                    preview_text = row['content'][:150] + "..." if len(str(row['content'])) > 150 else row['content']
                    display_rich_content(preview_text)
                    st.caption(f"更新日: {row['updated_at']}")
                
                with col2:
                    if st.button("詳細", key=f"search_protocol_detail_{row['id']}"):
                        st.session_state.selected_protocol_id = int(row['id'])
                        st.session_state.page = "protocol_detail"
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            if st.button("検索結果をクリア", key="clear_protocol_search"):
                if 'protocol_search_results' in st.session_state:
                    del st.session_state.protocol_search_results
                st.rerun()
        else:
            st.info("該当するプロトコルが見つかりませんでした")
            if st.button("検索結果をクリア", key="clear_no_protocol_results"):
                if 'protocol_search_results' in st.session_state:
                    del st.session_state.protocol_search_results
                st.rerun()
        return
    
    # カテゴリータブ表示
    tabs = st.tabs(categories)
    
    for i, category in enumerate(categories):
        with tabs[i]:
            df = get_protocols_by_category(category)
            
            if not df.empty:
                for idx, row in df.iterrows():
                    st.markdown('<div class="protocol-section">', unsafe_allow_html=True)
                    col1, col2 = st.columns([4, 1])
                    
                    with col1:
                        st.markdown(f"### {row['title']}")
                        preview_text = row['content'][:200] + "..." if len(str(row['content'])) > 200 else row['content']
                        display_rich_content(preview_text)
                        st.caption(f"作成日: {row['created_at']} | 更新日: {row['updated_at']}")
                    
                    with col2:
                        if st.button("詳細", key=f"protocol_detail_{row['id']}"):
                            st.session_state.selected_protocol_id = row['id']
                            st.session_state.page = "protocol_detail"
                            st.rerun()
                    
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info(f"{category}のプロトコルはまだ登録されていません")
                if st.button(f"{category}のプロトコルを作成", key=f"create_{category}_protocol"):
                    st.session_state.default_category = category
                    st.session_state.page = "create_protocol"
                    st.rerun()

def show_protocol_detail_page():
    """CTプロトコル詳細ページ"""
    if 'selected_protocol_id' not in st.session_state:
        st.error("プロトコルが選択されていません")
        if st.button("プロトコル一覧に戻る", key="protocol_detail_back_no_selection"):
            st.session_state.page = "protocols"
            st.rerun()
        return
    
    protocol_data = get_protocol_by_id(st.session_state.selected_protocol_id)
    if not protocol_data:
        st.error("プロトコルが見つかりません")
        if st.button("プロトコル一覧に戻る", key="protocol_detail_back_not_found"):
            st.session_state.page = "protocols"
            if 'selected_protocol_id' in st.session_state:
                del st.session_state.selected_protocol_id
            st.rerun()
        return
    
    st.markdown(f'<div class="main-header"><h1>📋 {protocol_data[2]}</h1></div>', unsafe_allow_html=True)
    
    # カテゴリーバッジ
    st.markdown(f"""
    <div style="margin-bottom: 1rem;">
        <span style="background-color: #2196F3; color: white; padding: 0.3rem 0.8rem; border-radius: 15px; font-size: 0.9rem;">
            📂 {protocol_data[1]}
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    # 作成日・更新日
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"作成日: {protocol_data[5]}")
    with col2:
        st.caption(f"更新日: {protocol_data[6]}")
    
    # プロトコル内容
    st.markdown('<div class="protocol-section">', unsafe_allow_html=True)
    st.markdown("プロトコル内容")
    display_rich_content(protocol_data[3])
    
    # プロトコル画像表示
    if protocol_data[4]:  # protocol_img
        st.markdown("### 📷 プロトコル画像")
        display_image_with_caption(protocol_data[4], "プロトコル画像")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 編集・削除・戻るボタン
    if st.button("編集", key="protocol_detail_edit"):
        st.session_state.edit_protocol_id = protocol_data[0]
        st.session_state.page = "edit_protocol"
        st.rerun()
    
    if st.button("削除", key="protocol_detail_delete"):
        if st.session_state.get('confirm_delete_protocol', False):
            delete_protocol(protocol_data[0])
            st.success("プロトコルを削除しました")
            st.session_state.page = "protocols"
            if 'confirm_delete_protocol' in st.session_state:
                del st.session_state.confirm_delete_protocol
            if 'selected_protocol_id' in st.session_state:
                del st.session_state.selected_protocol_id
            st.rerun()
        else:
            st.session_state.confirm_delete_protocol = True
            st.warning("削除ボタンをもう一度押すと削除されます")
    
    if st.button("プロトコル一覧に戻る", key="protocol_detail_back"):
        st.session_state.page = "protocols"
        if 'selected_protocol_id' in st.session_state:
            del st.session_state.selected_protocol_id
        st.rerun()

def show_create_protocol_page():
    """CTプロトコル作成ページ"""
    st.markdown('<div class="main-header"><h1>新規CTプロトコル作成</h1></div>', unsafe_allow_html=True)
    
    # カテゴリー定義
    categories = ["頭部", "頸部", "胸部", "腹部", "下肢", "上肢", "特殊"]
    
    with st.form("create_protocol_form"):
        # カテゴリー選択
        default_index = 0
        if 'default_category' in st.session_state:
            try:
                default_index = categories.index(st.session_state.default_category)
            except ValueError:
                default_index = 0
        
        category = st.selectbox("カテゴリー *", categories, index=default_index)
        
        # タイトル入力
        title = st.text_input("プロトコルタイトル *", placeholder="例：頭部単純CT撮影プロトコル")
        
        # プロトコル内容
        st.markdown("**プロトコル内容 ***")
        content = create_rich_text_editor(
            content="",
            placeholder="CTプロトコルの詳細内容を入力してください。撮影条件、手順、注意事項などを記載できます。",
            key="protocol_content_editor",
            height=400
        )
        
        # プロトコル画像
        st.markdown("**プロトコル画像**")
        protocol_image = st.file_uploader("プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], 
                                        key="create_protocol_img_upload",
                                        help="対応形式: PNG, JPEG, JPG（最大5MB）")
        if protocol_image:
            st.image(protocol_image, caption="プロトコル画像プレビュー", width=300)
        
        # フォーム送信
        col1, col2 = st.columns([1, 1])
        with col1:
            submitted = st.form_submit_button("プロトコルを作成", use_container_width=True)
        with col2:
            if st.form_submit_button("🔙 戻る", use_container_width=True):
                st.session_state.page = "protocols"
                if 'default_category' in st.session_state:
                    del st.session_state.default_category
                st.rerun()
    
    # フォーム処理
    if submitted:
        if not title or not content:
            st.error("タイトルとプロトコル内容は必須項目です")
        else:
            try:
                # 画像をBase64に変換
                protocol_img_b64 = None
                if protocol_image is not None:
                    protocol_img_b64, error_msg = validate_and_process_image(protocol_image)
                    if protocol_img_b64 is None:
                        st.error(f"プロトコル画像: {error_msg}")
                        return
                
                add_protocol(category, title, content, protocol_img_b64)
                
                # 作成成功フラグを設定
                st.session_state.protocol_created = True
                st.session_state.created_protocol_title = title
                st.session_state.created_protocol_category = category
                if 'default_category' in st.session_state:
                    del st.session_state.default_category
                st.rerun()
                
            except Exception as e:
                st.error(f"データ作成中にエラーが発生しました: {str(e)}")
    
    # 作成完了メッセージ
    if st.session_state.get('protocol_created', False):
        st.success("✅ CTプロトコルが正常に作成されました！")
        st.balloons()
        
        st.markdown(f"""
        <div class="protocol-section">
            <h3>作成完了</h3>
            <p><strong>カテゴリー:</strong> {st.session_state.get('created_protocol_category', '')}</p>
            <p><strong>タイトル:</strong> {st.session_state.get('created_protocol_title', '')}</p>
            <p><strong>作成日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            <p>データベースに正常に保存されました。</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("プロトコル一覧に戻る", key="create_protocol_success_back", use_container_width=True):
                # 成功フラグをクリア
                if 'protocol_created' in st.session_state:
                    del st.session_state.protocol_created
                if 'created_protocol_title' in st.session_state:
                    del st.session_state.created_protocol_title
                if 'created_protocol_category' in st.session_state:
                    del st.session_state.created_protocol_category
                st.session_state.page = "protocols"
                st.rerun()
        
        with col2:
            if st.button("続けて作成", key="create_protocol_success_continue", use_container_width=True):
                # 成功フラグをクリア
                if 'protocol_created' in st.session_state:
                    del st.session_state.protocol_created
                if 'created_protocol_title' in st.session_state:
                    del st.session_state.created_protocol_title
                if 'created_protocol_category' in st.session_state:
                    del st.session_state.created_protocol_category
                st.rerun()
        
        with col3:
            if st.button("👁️ 作成したプロトコルを確認", key="create_protocol_success_view", use_container_width=True):
                # 作成したプロトコル詳細ページに移動
                conn = init_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM protocols WHERE title = ? AND category = ? ORDER BY created_at DESC LIMIT 1", 
                              (st.session_state.get('created_protocol_title', ''), st.session_state.get('created_protocol_category', '')))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    st.session_state.selected_protocol_id = result[0]
                    st.session_state.page = "protocol_detail"
                    # 成功フラグをクリア
                    if 'protocol_created' in st.session_state:
                        del st.session_state.protocol_created
                    if 'created_protocol_title' in st.session_state:
                        del st.session_state.created_protocol_title
                    if 'created_protocol_category' in st.session_state:
                        del st.session_state.created_protocol_category
                    st.rerun()
        return
    
    # 戻るボタン（通常時のみ表示）
    if st.button("戻る", key="create_protocol_back"):
        st.session_state.page = "protocols"
        if 'default_category' in st.session_state:
            del st.session_state.default_category
        st.rerun()

def show_edit_protocol_page():
    """CTプロトコル編集ページ"""
    if 'edit_protocol_id' not in st.session_state:
        st.error("編集対象が選択されていません")
        if st.button("プロトコル一覧に戻る", key="edit_protocol_back_no_selection"):
            st.session_state.page = "protocols"
            st.rerun()
        return
    
    protocol_data = get_protocol_by_id(st.session_state.edit_protocol_id)
    if not protocol_data:
        st.error("プロトコルが見つかりません")
        if st.button("プロトコル一覧に戻る", key="edit_protocol_back_not_found"):
            st.session_state.page = "protocols"
            if 'edit_protocol_id' in st.session_state:
                del st.session_state.edit_protocol_id
            st.rerun()
        return
    
    st.markdown('<div class="main-header"><h1>CTプロトコル編集</h1></div>', unsafe_allow_html=True)
    
    # カテゴリー定義
    categories = ["頭部", "頸部", "胸部", "腹部", "下肢", "上肢", "特殊"]
    
    with st.form("edit_protocol_form"):
        # カテゴリー選択
        try:
            current_category_index = categories.index(protocol_data[1])
        except ValueError:
            current_category_index = 0
        
        category = st.selectbox("カテゴリー *", categories, index=current_category_index)
        
        # タイトル入力
        title = st.text_input("プロトコルタイトル *", value=protocol_data[2])
        
        # プロトコル内容
        st.markdown("**プロトコル内容 ***")
        content = create_rich_text_editor(
            content=protocol_data[3] or "",
            placeholder="CTプロトコルの詳細内容を入力してください。",
            key="edit_protocol_content_editor",
            height=400
        )
        
        # プロトコル画像編集
        st.markdown("**プロトコル画像**")
        if protocol_data[4]:  # 既存画像がある場合
            st.markdown("現在の画像:")
            display_image_with_caption(protocol_data[4], "現在のプロトコル画像", width=200)
            replace_img = st.checkbox("プロトコル画像を変更する")
            if replace_img:
                protocol_image = st.file_uploader("新しいプロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], 
                                                key="edit_protocol_img_upload")
                if protocol_image is not None:
                    st.image(protocol_image, caption="新しいプロトコル画像", width=300)
            else:
                protocol_image = None
        else:
            protocol_image = st.file_uploader("プロトコル画像をアップロード", type=['png', 'jpg', 'jpeg'], 
                                            key="edit_protocol_img_upload")
            if protocol_image is not None:
                st.image(protocol_image, caption="プロトコル画像", width=300)
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("更新", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("キャンセル", use_container_width=True)
        
        if submitted:
            if title and content:
                try:
                    # 画像処理（既存画像を保持するか新しい画像に更新するか）
                    protocol_img_b64 = protocol_data[4]  # 既存画像
                    
                    # 新しい画像がアップロードされた場合のみ更新
                    if protocol_image is not None:
                        protocol_img_b64, error_msg = validate_and_process_image(protocol_image)
                        if protocol_img_b64 is None:
                            st.error(f"プロトコル画像: {error_msg}")
                            return
                    
                    update_protocol(st.session_state.edit_protocol_id, category, title, content, protocol_img_b64)
                    st.success("プロトコルを更新しました")
                    st.session_state.selected_protocol_id = st.session_state.edit_protocol_id
                    st.session_state.page = "protocol_detail"
                    del st.session_state.edit_protocol_id
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"データの保存中にエラーが発生しました: {str(e)}")
            else:
                st.error("タイトルとプロトコル内容は必須項目です")
        
        if cancel:
            st.session_state.selected_protocol_id = st.session_state.edit_protocol_id
            st.session_state.page = "protocol_detail"
            del st.session_state.edit_protocol_id
            st.rerun()

def show_admin_page():
    """管理者専用ページ"""
    # 管理者権限チェック
    if not is_admin_user():
        st.error("🚫 管理者権限が必要です")
        st.info("管理者アカウントでログインしてください")
        return
    
    st.markdown('<div class="main-header"><h1>管理者専用ページ</h1></div>', unsafe_allow_html=True)
    st.markdown(f"**管理者:** {st.session_state.user['name']} ({st.session_state.user['email']})")
    
    # タブで機能を分ける
    tab1, tab2, tab3 = st.tabs(["新規ユーザー作成", "ユーザー管理", "データバックアップ"])
    
    with tab1:
        st.markdown("新規ユーザー作成")
        
        with st.form("admin_register_form"):
            st.info("管理者のみが新しいユーザーアカウントを作成できます")
            
            name = st.text_input("氏名 *", placeholder="例：山田太郎")
            email = st.text_input("メールアドレス *", placeholder="例：yamada@hospital.com")
            password = st.text_input("初期パスワード *", type="password", placeholder="8文字以上推奨")
            password_confirm = st.text_input("パスワード確認 *", type="password")
            
            # ユーザー種別選択（参考情報）
            user_type = st.selectbox("ユーザー種別（参考）", [
                "診療放射線技師", 
                "医師", 
                "看護師", 
                "管理者", 
                "その他"
            ])
            
            notes = st.text_area("備考", placeholder="部署、役職、特記事項など")
            
            col1, col2 = st.columns(2)
            with col1:
                submitted = st.form_submit_button("ユーザー作成", use_container_width=True)
            with col2:
                if st.form_submit_button("フォームをクリア", use_container_width=True):
                    st.rerun()
            
            if submitted:
                if name and email and password and password_confirm:
                    # メールアドレス検証を追加
                    email_valid, email_error = validate_email(email)
                    if not email_valid:
                        st.error(f"❌ {email_error}")
                        st.info("💡 正しい形式の例: yamada@hospital.com")
                    elif password == password_confirm:
                        if len(password) >= 6:  # パスワード長チェック
                            if admin_register_user(name, email, password):
                                st.success(f"✅ ユーザー「{name}」を作成しました")
                                st.info(f"📧 ログイン情報\nメール: {email}\nパスワード: {password}")
                                
                                # 作成完了の詳細情報
                                st.markdown(f"""
                                <div class="notice-card">
                                    <h4>作成されたユーザー情報</h4>
                                    <ul>
                                        <li><strong>氏名:</strong> {name}</li>
                                        <li><strong>メールアドレス:</strong> {email}</li>
                                        <li><strong>ユーザー種別:</strong> {user_type}</li>
                                        <li><strong>作成日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</li>
                                        {f'<li><strong>備考:</strong> {notes}</li>' if notes else ''}
                                    </ul>
                                    <p style="color: #ff9800;">⚠️ 初期パスワードをユーザーに安全に伝達してください</p>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.error("❌ このメールアドレスは既に登録されています")
                        else:
                            st.error("❌ パスワードは6文字以上で設定してください")
                    else:
                        st.error("❌ パスワードが一致しません")
                else:
                    st.error("❌ 全ての必須項目を入力してください")
    
    with tab2:
        st.markdown("ユーザー管理")
        
        # 全ユーザー一覧表示
        df_users = get_all_users()
        
        if not df_users.empty:
            st.markdown(f"**登録ユーザー数:** {len(df_users)}人")
            
            # ユーザー一覧をカード形式で表示
            for idx, user in df_users.iterrows():
                st.markdown('<div class="search-result">', unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.markdown(f"**👤 {user['name']}**")
                    st.markdown(f"📧 {user['email']}")
                    st.caption(f"登録日: {user['created_at']}")
                
                with col2:
                    # 現在のユーザー自身は削除できないようにする
                    if user['email'] != st.session_state.user['email']:
                        if st.button("編集", key=f"edit_user_{user['id']}", disabled=True):
                            st.info("編集機能は今後追加予定です")
                    else:
                        st.markdown("**(現在のユーザー)**")
                
                with col3:
                    # 管理者ユーザーと現在のユーザー自身は削除不可
                    admin_emails = ['admin@hospital.jp']
                    if user['email'] not in admin_emails and user['email'] != st.session_state.user['email']:
                        if st.button("削除", key=f"delete_user_{user['id']}"):
                            # 削除確認
                            if st.session_state.get(f'confirm_delete_user_{user["id"]}', False):
                                delete_user(user['id'])
                                st.success(f"ユーザー「{user['name']}」を削除しました")
                                st.rerun()
                            else:
                                st.session_state[f'confirm_delete_user_{user["id"]}'] = True
                                st.warning("もう一度削除ボタンを押すと削除されます")
                    elif user['email'] in admin_emails:
                        st.markdown("**(管理者)**")
                    else:
                        st.markdown("**(現在のユーザー)**")
                
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("登録ユーザーがいません")
        
        # ユーザー統計情報
        if not df_users.empty:
            st.markdown("---")
            st.markdown("ユーザー統計")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("総ユーザー数", len(df_users))
            with col2:
                # 今月の新規登録数
                current_month = datetime.now().strftime('%Y-%m')
                monthly_users = len([u for u in df_users['created_at'] if current_month in str(u)])
                st.metric("今月の新規登録", f"{monthly_users}人")
            with col3:
                # 管理者数
                admin_count = len([u for u in df_users['email'] if u in ['admin@hospital.com', 'demo@hospital.com']])
                st.metric("管理者数", f"{admin_count}人")

    with tab3:
        st.markdown("データバックアップ・復元")
        
        # バックアップセクション
        st.markdown("データのバックアップ")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.info("""
            **バックアップに含まれるデータ:**
            - 疾患データ（画像含む）
            - お知らせ（画像含む）
            - CTプロトコル（画像含む）
            - ユーザー情報（パスワード除く）
            """)
        
        with col2:
            if st.button("バックアップ作成", use_container_width=True, key="create_backup"):
                with st.spinner("バックアップを作成中..."):
                    backup_data, error = create_backup_zip()
                    
                    if backup_data:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"ct_system_backup_{timestamp}.zip"
                        
                        st.download_button(
                            label="バックアップをダウンロード",
                            data=backup_data,
                            file_name=filename,
                            mime="application/zip",
                            use_container_width=True
                        )
                        st.success("✅ バックアップが作成されました！")
                    else:
                        st.error(f"❌ {error}")
        
        st.markdown("---")
        
        # 復元セクション
        st.markdown("データの復元")
        
        uploaded_file = st.file_uploader(
            "バックアップファイルを選択",
            type=['json', 'zip'],
            help="backup_data.json または バックアップZIPファイルをアップロード"
        )
        
        if uploaded_file is not None:
            file_type = uploaded_file.name.split('.')[-1].lower()
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.warning("""
                ⚠️ **復元時の注意事項:**
                - 既存のデータと重複する場合は上書きされます
                - 復元前に現在のデータをバックアップすることを推奨します
                - ユーザーデータは復元されません（手動で再作成が必要）
                """)
            
            with col2:
                if st.button("データを復元", use_container_width=True, key="restore_data"):
                    try:
                        if file_type == 'json':
                            # JSONファイルから直接復元
                            json_content = uploaded_file.read().decode('utf-8')
                            json_data = json.loads(json_content)
                            
                        elif file_type == 'zip':
                            # ZIPファイルから復元
                            with zipfile.ZipFile(uploaded_file, 'r') as zip_file:
                                json_content = zip_file.read('backup_data.json').decode('utf-8')
                                json_data = json.loads(json_content)
                        
                        # 復元実行
                        with st.spinner("データを復元中..."):
                            success, result = restore_from_json(json_data)
                            

                            if success:
                                st.success("🎉 Laravel版データの移行が完了しました！")
                                
                                # 移行タイプをチェック
                                migration_type = json_data.get('export_info', {}).get('migration_type', 'unknown')
                                
                                if migration_type == 'complete_replacement':
                                    st.info(f"""
                                    **📊 Laravel版データ移行結果（完全置換）:**
                                    
                                    **✅ 新規投入データ:**
                                    - 疾患データ: {result['sicks']}件
                                    - お知らせ: {result['forms']}件
                                    - CTプロトコル: {result['protocols']}件
                                    
                                    **🗑️ 削除されたPython版データ:**
                                    - 疾患データ: {result.get('deleted_sicks', 0)}件
                                    - お知らせ: {result.get('deleted_forms', 0)}件
                                    - CTプロトコル: {result.get('deleted_protocols', 0)}件
                                    
                                    **ℹ️ 注意事項:**
                                    - Laravel版データで完全に置き換わりました
                                    - 画像データは移行されていません
                                    - ユーザーデータは保持されています
                                    """)
                                else:
                                    st.info(f"""
                                    **📊 データ復元結果:**
                                    - 疾患データ: {result['sicks']}件
                                    - お知らせ: {result['forms']}件
                                    - CTプロトコル: {result['protocols']}件
                                    """)
                                
                                st.balloons()
                            else:
                                st.error(f"❌ {result}")
                    
                    except Exception as e:
                        st.error(f"❌ ファイルの処理中にエラーが発生しました: {str(e)}")
        
        # システム情報
        st.markdown("---")
        st.markdown("システム情報")
        
        try:
            # データベース統計
            conn = init_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM sicks")
            sick_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM forms")
            form_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM protocols")
            protocol_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            conn.close()
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("疾患データ", f"{sick_count}件")
            with col2:
                st.metric("お知らせ", f"{form_count}件")
            with col3:
                st.metric("CTプロトコル", f"{protocol_count}件")
            with col4:
                st.metric("ユーザー", f"{user_count}人")
                
        except Exception as e:
            st.error(f"システム情報の取得に失敗しました: {str(e)}")
        
        # 最終バックアップ情報
        st.caption("💡 定期的なバックアップを推奨します（週1回以上）")

# サイドバー
def show_sidebar():
    """サイドバー表示"""
    with st.sidebar:
        st.markdown("### 🏥 How to CT")
        
        if RICH_EDITOR_AVAILABLE:
            st.success("📝 リッチテキストエディタ対応")
        else:
            st.warning("📝 リッチエディタ未対応")
        
        if 'user' in st.session_state:
            st.markdown(f"**ログイン中:** {st.session_state.user['name']}")
            
            st.markdown("---")
            st.markdown("### 📋 メニュー")
            
            if st.button("🏠 ホーム", use_container_width=True, key="sidebar_home"):
                st.session_state.page = "home"
                st.rerun()
            
            if st.button("🔍 疾患検索", use_container_width=True, key="sidebar_search"):
                st.session_state.page = "search"
                st.rerun()
            
            if st.button("📢 お知らせ", use_container_width=True, key="sidebar_notices"):
                st.session_state.page = "notices"
                st.rerun()

            if st.button("📋 CTプロトコル", use_container_width=True, key="sidebar_protocols"):
                st.session_state.page = "protocols"
                st.rerun()
            
            st.markdown("---")
            
            if st.button("📝 新規疾患作成", use_container_width=True, key="sidebar_create_disease"):
                st.session_state.page = "create_disease"
                st.rerun()
            
            if st.button("📝 新規お知らせ作成", use_container_width=True, key="sidebar_create_notice"):
                st.session_state.page = "create_notice"
                st.rerun()
            
            st.markdown("---")
            
            if st.button("🚪 ログアウト", use_container_width=True):
                # ログアウト時にセッション情報をクリア
                if 'user' in st.session_state:
                    user_id = st.session_state.user['id']
                    try:
                        conn = init_connection()
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
                        conn.commit()
                        conn.close()
                    except:
                        pass
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.session_state.page = "welcome"
                st.rerun()

            # 管理者メニュー（管理者のみ表示）
            if is_admin_user():
                st.markdown("---")
                st.markdown("### 👨‍💼 管理者メニュー")
                if st.button("ユーザー管理", use_container_width=True, key="sidebar_admin"):
                    st.session_state.page = "admin"
                    st.rerun()
        
        st.markdown("---")
        st.markdown("### ℹ️ システム情報")
        st.markdown("**診療放射線技師向け**")
        st.markdown("CT検査マニュアルシステム")
        st.markdown("疾患別プロトコル管理")
        st.markdown("画像アップロード対応")
        
        if RICH_EDITOR_AVAILABLE:
            st.markdown("リッチテキストエディタ対応")

        else:
            st.markdown("リッチエディタ未導入")
            st.markdown("`pip install streamlit-quill`")
            st.markdown("でインストールしてください")

# メイン処理
def main():
    """メイン処理"""
    # データベース初期化
    init_database()
      # 既存ユーザーを一度クリア（一回だけ実行）
    # conn = init_connection()
    # cursor = conn.cursor()
    # cursor.execute("DELETE FROM users")
    # conn.commit()
    # conn.close()
    insert_sample_data()
    

      # セッション状態の復元（ブラウザ更新対応）
    if 'user' not in st.session_state:
        # データベースからセッション情報を復元を試行
        session_data = load_session_from_db()
        if session_data:
            st.session_state.user = session_data['user']
            st.session_state.page = session_data['page']
            # デバッグ情報を表示
    # セッション状態の復元（ブラウザ更新対応）
    if 'user' not in st.session_state:
        # データベースからセッション情報を復元を試行
        session_data = load_session_from_db()
        if session_data:
            st.session_state.user = session_data['user']
            st.session_state.page = session_data['page']
    
    # ページ状態の初期化
    if 'page' not in st.session_state:
        st.session_state.page = "welcome"
    
    # サイドバー表示
    if st.session_state.page != "welcome" and st.session_state.page != "login":
        show_sidebar()
    
    # ページルーティング
    if st.session_state.page == "welcome":
        show_welcome_page()
    elif st.session_state.page == "login":
        show_login_page()
    elif st.session_state.page == "home":
        show_home_page()
    elif st.session_state.page == "search":
        show_search_page()
    elif st.session_state.page == "detail":
        show_detail_page()
    elif st.session_state.page == "notices":
        show_notices_page()
    elif st.session_state.page == "notice_detail":
        show_notice_detail_page()
    elif st.session_state.page == "create_disease":
        show_create_disease_page()
    elif st.session_state.page == "create_notice":
        show_create_notice_page()
    elif st.session_state.page == "edit_notice":
        show_edit_notice_page()
    elif st.session_state.page == "edit_disease":
        show_edit_disease_page()
    elif st.session_state.page == "protocols":
        show_protocols_page()
    elif st.session_state.page == "protocol_detail":
        show_protocol_detail_page()
    elif st.session_state.page == "create_protocol":
        show_create_protocol_page()
    elif st.session_state.page == "edit_protocol":
        show_edit_protocol_page()
    elif st.session_state.page == "admin":
        show_admin_page()

if __name__ == "__main__":
    main()