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

query_params = st.query_params
if 'page' in query_params:
    st.session_state.page = query_params['page']

def save_session_to_db(user_id, session_data):
    """セッション情報をデータベースに保存（強化版）"""
    try:
        conn = get_db_connection()
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
    """データベースからセッション情報を復元（強化版）"""
    try:
        conn = get_db_connection()
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
                    'page': session_data.get('page', 'home'),
                    'selected_sick_id': session_data.get('selected_sick_id'),
                    'selected_notice_id': session_data.get('selected_notice_id'),
                    'selected_protocol_id': session_data.get('selected_protocol_id'),
                    'edit_sick_id': session_data.get('edit_sick_id'),
                    'edit_notice_id': session_data.get('edit_notice_id'),
                    'edit_protocol_id': session_data.get('edit_protocol_id')
                }
        
        return None
    except Exception as e:
        return None

def get_user_by_id(user_id):
    """IDでユーザー情報を取得 - PostgreSQL版"""
    try:
        conn = get_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        st.error(f"ユーザー取得エラー: {e}")
        return None

def update_session_in_db():
    """現在のセッション状態をデータベースに更新（強化版）"""
    if 'user' in st.session_state:
        session_data = {
            'page': st.session_state.get('page', 'home'),
            'selected_sick_id': st.session_state.get('selected_sick_id'),
            'selected_notice_id': st.session_state.get('selected_notice_id'),
            'selected_protocol_id': st.session_state.get('selected_protocol_id'),
            'edit_sick_id': st.session_state.get('edit_sick_id'),
            'edit_notice_id': st.session_state.get('edit_notice_id'),
            'edit_protocol_id': st.session_state.get('edit_protocol_id')
        }
        save_session_to_db(st.session_state.user['id'], session_data)
# ページ履歴管理関数
def add_to_page_history(page):
    """ページ履歴に追加"""
    if 'page_history' not in st.session_state:
        st.session_state.page_history = []
    
    # 同じページの連続追加を避ける
    if not st.session_state.page_history or st.session_state.page_history[-1] != page:
        st.session_state.page_history.append(page)
        
    # 履歴が長くなりすぎないように制限（最大10ページ）
    if len(st.session_state.page_history) > 10:
        st.session_state.page_history = st.session_state.page_history[-10:]

def go_back():
    """前のページに戻る（改善版）"""
    if 'page_history' not in st.session_state or len(st.session_state.page_history) <= 1:
        st.session_state.page = "home"
        return
    
    # 現在のページを履歴から削除
    st.session_state.page_history.pop()
    
    # 前のページに戻る
    if st.session_state.page_history:
        previous_page = st.session_state.page_history[-1]
        st.session_state.page = previous_page
        
        # ページ遷移後に選択状態をクリア（遷移完了後）
        if previous_page == "protocols":
            if 'selected_protocol_id' in st.session_state:
                del st.session_state.selected_protocol_id
        elif previous_page == "notices":
            if 'selected_notice_id' in st.session_state:
                del st.session_state.selected_notice_id
        elif previous_page == "search":
            if 'selected_sick_id' in st.session_state:
                del st.session_state.selected_sick_id
    else:
        st.session_state.page = "home"

def navigate_to_page(page):
    """ページナビゲーション（デバッグ版）"""
    st.write(f"Debug: Navigating to {page}")  # デバッグ用
    
    # 現在のページを履歴に追加
    current_page = st.session_state.get('page', 'home')
    add_to_page_history(current_page)
    
    # セッション状態を更新
    st.session_state.page = page
    st.write(f"Debug: Session page set to {st.session_state.page}")  # デバッグ用
    
    # URLパラメータを更新
    st.query_params.update({"page": page})
    st.write(f"Debug: URL params set to {dict(st.query_params)}")  # デバッグ用
    
    # 強制再読み込み
    st.rerun()

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

def get_db_connection():
    """新しいPostgreSQL接続を取得"""
    try:
        return psycopg2.connect(**st.secrets["postgres"])
    except Exception as e:
        st.error(f"データベース接続エラー: {e}")
        return None

# データベース初期化
@st.cache_resource
def init_connection():
    """PostgreSQL接続テスト（表示用のみ）"""
    try:
        conn = psycopg2.connect(**st.secrets["postgres"])
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"データベース接続エラー: {e}")
        return False

def init_database():
    """PostgreSQLテーブルを初期化"""
    conn = get_db_connection()
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
        cursor.close()
        conn.close()

# 初期データ投入
def insert_sample_data():
    """サンプルデータを挿入"""
    try:
        conn = get_db_connection()
        if not conn:
            st.warning("データベース接続なし、サンプルデータ作成をスキップ")
            return
        
        cursor = conn.cursor()
        
        # サンプルユーザーデータ
        sample_users = [
            ("管理者", "admin@hospital.jp", "Okiyoshi1126"),
            ("技師", "tech@hospital.jp", "Tech123")
        ]
        
        try:
            for user_data in sample_users:
                cursor.execute("SELECT COUNT(*) FROM users WHERE email = %s", (user_data[1],))
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                                  (user_data[0], user_data[1], hash_password(user_data[2])))
        except Exception as e:
            st.warning(f"ユーザーデータ作成スキップ: {e}")
        
        # 疾患サンプルデータ
        sample_sicks = [
            ("脳梗塞", "脳血管が詰まる疾患", "脳梗塞,stroke", "頭部造影CT", "造影剤使用", "緊急検査", "迅速な対応", "あり", "造影剤注入", "", "", "", ""),
            ("肺炎", "肺の感染症", "肺炎,pneumonia", "胸部CT", "単純CT", "標準撮影", "呼吸停止", "なし", "造影不要", "", "", "", "")
        ]
        
        try:
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
        except Exception as e:
            st.warning(f"疾患データ作成スキップ: {e}")
        
        # お知らせサンプルデータ
        sample_forms = [
            ("システム運用開始", "CT医療システムの運用を開始しました。", ""),
            ("利用方法について", "疾患検索機能をご活用ください。", "")
        ]
        
        try:
            for form in sample_forms:
                cursor.execute("SELECT COUNT(*) FROM forms WHERE title = %s", (form[0],))
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO forms (title, main, post_img) VALUES (%s, %s, %s)", form)
        except Exception as e:
            st.warning(f"お知らせデータ作成スキップ: {e}")
        
        # CTプロトコルサンプルデータ
        sample_protocols = [
            ("頭部", "頭部単純CT", "スライス厚: 5mm\n電圧: 120kV\n電流: 250mA", ""),
            ("胸部", "胸部造影CT", "スライス厚: 1mm\n電圧: 120kV\n造影剤: 100ml", "")
        ]
        
        try:
            for protocol in sample_protocols:
                cursor.execute("SELECT COUNT(*) FROM protocols WHERE title = %s AND category = %s", (protocol[1], protocol[0]))
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO protocols (category, title, content, protocol_img) VALUES (%s, %s, %s, %s)", protocol)
        except Exception as e:
            st.warning(f"プロトコルデータ作成スキップ: {e}")
        
        conn.commit()
        
    except Exception as e:
        st.error(f"❌ サンプルデータ作成エラー: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()

# 認証機能
def hash_password(password):
    """パスワードをハッシュ化"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(email, password):
    """ユーザー認証 - PostgreSQL版"""
    try:
        conn = get_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, email FROM users WHERE email = %s AND password = %s", 
            (email, hash_password(password))
        )
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def register_user(name, email, password):
    """新規ユーザー登録 - PostgreSQL版"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"ユーザー登録エラー: {e}")
        return False

# データベース操作関数
@st.cache_data(ttl=300)  # 5分間キャッシュ
def get_all_sicks():
    """全疾患データを取得"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM sicks ORDER BY diesease", conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_all_forms():
    """全お知らせを取得"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM forms ORDER BY created_at DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def search_sicks(search_term):
    """疾患データを検索"""
    conn = get_db_connection()
    query = """
        SELECT * FROM sicks 
        WHERE diesease LIKE %s OR diesease_text LIKE %s OR keyword LIKE %s 
        OR protocol LIKE %s OR protocol_text LIKE %s OR processing LIKE %s 
        OR processing_text LIKE %s OR contrast LIKE %s OR contrast_text LIKE %s
        ORDER BY diesease
    """
    search_pattern = f"%{search_term}%"
    params = [search_pattern] * 9
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_sick_by_id(sick_id):
    """IDで疾患データを取得"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sicks WHERE id = %s", (sick_id,))
    sick = cursor.fetchone()
    conn.close()
    return sick

def get_form_by_id(form_id):
    """IDでお知らせを取得"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forms WHERE id = %s", (form_id,))
    form = cursor.fetchone()
    conn.close()
    return form

def add_sick(diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img=None, protocol_img=None, processing_img=None, contrast_img=None):
    """新しい疾患データを追加"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sicks (diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img, protocol_img, processing_img, contrast_img)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img, protocol_img, processing_img, contrast_img))
    conn.commit()
    conn.close()

def add_form(title, main, post_img=None):
    """新しいお知らせを追加"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO forms (title, main, post_img) VALUES (%s, %s, %s)', (title, main, post_img))
    conn.commit()
    conn.close()

def update_sick(sick_id, diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img=None, protocol_img=None, processing_img=None, contrast_img=None):
    """疾患データを更新"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sicks SET diesease=%s, diesease_text=%s, keyword=%s, protocol=%s, protocol_text=%s, 
        processing=%s, processing_text=%s, contrast=%s, contrast_text=%s, diesease_img=%s, protocol_img=%s, processing_img=%s, contrast_img=%s, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    ''', (diesease, diesease_text, keyword, protocol, protocol_text, processing, processing_text, contrast, contrast_text, diesease_img, protocol_img, processing_img, contrast_img, sick_id))
    conn.commit()
    conn.close()

def update_form(form_id, title, main, post_img=None):
    """お知らせを更新"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE forms SET title=%s, main=%s, post_img=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s', (title, main, post_img, form_id))
    conn.commit()
    conn.close()

def delete_form(form_id):
    """お知らせを削除"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM forms WHERE id = %s', (form_id,))
    conn.commit()
    conn.close()

def delete_sick(sick_id):
    """疾患データを削除"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sicks WHERE id = %s', (sick_id,))
    conn.commit()
    conn.close()

@st.cache_data(ttl=300)
def get_all_protocols():
    """全CTプロトコルを取得"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM protocols ORDER BY category, title", conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_protocols_by_category(category):
    """カテゴリー別CTプロトコルを取得"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM protocols WHERE category = %s ORDER BY title", conn, params=[category])
    conn.close()
    return df

@st.cache_data(ttl=300)
def search_protocols(search_term):
    """CTプロトコルを検索"""
    conn = get_db_connection()
    query = """
        SELECT * FROM protocols 
        WHERE title LIKE %s OR content LIKE %s OR category LIKE %s
        ORDER BY category, title
    """
    search_pattern = f"%{search_term}%"
    params = [search_pattern] * 3
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_protocol_by_id(protocol_id):
    """IDでCTプロトコルを取得"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM protocols WHERE id = %s", (protocol_id,))
    protocol = cursor.fetchone()
    conn.close()
    return protocol

def add_protocol(category, title, content, protocol_img=None):
    """新しいCTプロトコルを追加"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO protocols (category, title, content, protocol_img)
        VALUES (%s, %s, %s, %s)
    ''', (category, title, content, protocol_img))
    conn.commit()
    conn.close()

def update_protocol(protocol_id, category, title, content, protocol_img=None):
    """CTプロトコルを更新"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE protocols SET category=%s, title=%s, content=%s, protocol_img=%s, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    ''', (category, title, content, protocol_img, protocol_id))
    conn.commit()
    conn.close()

def delete_protocol(protocol_id):
    """CTプロトコルを削除"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM protocols WHERE id = %s', (protocol_id,))
    conn.commit()
    conn.close()

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
    """全ユーザー情報を取得（管理者用）- PostgreSQL版"""
    try:
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, created_at FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        
        # DataFrameに変換
        df = pd.DataFrame(users, columns=['id', 'name', 'email', 'created_at'])
        
        conn.close()
        return df
    except Exception as e:
        st.error(f"ユーザー取得エラー: {e}")
        return pd.DataFrame()

def delete_user(user_id):
    """ユーザーを削除（管理者用）- PostgreSQL版"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"ユーザー削除エラー: {e}")
        return False

def admin_register_user(name, email, password):
    """管理者による新規ユーザー登録 - PostgreSQL版"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"ユーザー登録エラー: {e}")
        return False

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
            # セッション状態を完全にクリア
            for key in list(st.session_state.keys()):
                if key != 'db_initialized':  # DB初期化状態は保持
                    del st.session_state[key]
            st.session_state.page = "login"
            st.query_params['page'] = "login"
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
                        st.session_state.user = {'id': user[0], 'name': user[1], 'email': user[2]}
                        st.session_state.page = "home"
                        st.query_params['page'] = "home"
                        st.success(f"ログインしました - {user[1]}さん")
                        st.rerun()
                    else:
                        st.error("メールアドレスまたはパスワードが間違っています")
                else:
                    st.error("全ての項目を入力してください")

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
        navigate_to_page("search")
    
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
                    navigate_to_page("notice_detail")
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
            navigate_to_page("create_disease")
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
                        navigate_to_page("detail")
                
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
                        if 'show_all_diseases' in st.session_state:
                            del st.session_state.show_all_diseases
                        navigate_to_page("detail")
                
                st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("一覧を閉じる", key="close_all_list"):
            if 'show_all_diseases' in st.session_state:
                del st.session_state.show_all_diseases
            st.rerun()

def show_detail_page():
    """疾患詳細ページ（最終完成版）"""
    
    # 強制的にページトップへスクロール（非表示で実行）
    st.components.v1.html("""
    <div id="top-anchor" style="position: absolute; top: 0; left: 0; height: 1px; width: 1px;"></div>
    <script>
    // 方法1: 即座にスクロール
    document.body.scrollTop = 0;
    document.documentElement.scrollTop = 0;
    window.scrollTo(0, 0);
    
    // 方法2: DOMContentLoaded後
    document.addEventListener('DOMContentLoaded', function() {
        window.scrollTo(0, 0);
        document.body.scrollTop = 0;
        document.documentElement.scrollTop = 0;
    });
    
    // 方法3: 連続実行で確実に
    for(let i = 0; i < 5; i++) {
        setTimeout(function() {
            window.scrollTo(0, 0);
            document.body.scrollTop = 0;
            document.documentElement.scrollTop = 0;
        }, i * 100);
    }
    
    // 方法4: アンカーを使用
    setTimeout(function() {
        var anchor = document.getElementById('top-anchor');
        if (anchor) {
            anchor.scrollIntoView();
        }
    }, 500);
    </script>
    """, height=0)
    
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
    
    st.title(f"{sick_data[1]}")
    
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
    
    # 編集・削除・戻るボタン
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("編集", key="detail_edit_disease", use_container_width=True):
            st.session_state.edit_sick_id = sick_data[0]
            navigate_to_page("edit_disease")
    
    with col2:
        if st.button("削除", key="detail_delete_disease", use_container_width=True):
            if st.session_state.get('confirm_delete', False):
                delete_sick(sick_data[0])
                # キャッシュクリア追加
                get_all_sicks.clear()
                search_sicks.clear()
                st.success("疾患データを削除しました")
                if 'confirm_delete' in st.session_state:
                    del st.session_state.confirm_delete
                if 'selected_sick_id' in st.session_state:
                    del st.session_state.selected_sick_id
                navigate_to_page("search")
            else:
                st.session_state.confirm_delete = True
                st.warning("削除ボタンをもう一度押すと削除されます")
    
    with col3:
        if st.button("⬅️ 戻る", key="detail_back", use_container_width=True):
            if 'selected_sick_id' in st.session_state:
                del st.session_state.selected_sick_id
            # 検索結果などの状態をクリア
            if 'show_all_diseases' in st.session_state:
                del st.session_state.show_all_diseases
            navigate_to_page("search")

def show_notices_page():
    """お知らせ一覧ページ"""
    st.markdown('<div class="main-header"><h1>お知らせ一覧</h1></div>', unsafe_allow_html=True)
    
    # 新規作成ボタン
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("新規お知らせ作成", key="notices_create_notice"):
            navigate_to_page("create_notice")
    
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
                    navigate_to_page("notice_detail")

            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("お知らせがありません")

def show_notice_detail_page():
    """お知らせ詳細ページ"""
    if 'selected_notice_id' not in st.session_state:
        st.error("お知らせが選択されていません")
        if st.button("お知らせ一覧に戻る", key="notice_detail_back_no_selection"):
            navigate_to_page("notices")
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
    
    # 編集・削除・戻るボタン（本文下、縦並び）
    if st.button("編集", key="notice_detail_edit_notice"):
        st.session_state.edit_notice_id = form_data[0]
        navigate_to_page("edit_notice")
    
    if st.button("削除", key="notice_detail_delete_notice"):
        if st.session_state.get('confirm_delete_notice', False):
            delete_form(form_data[0])
            # キャッシュをクリアして最新データを取得
            get_all_forms.clear()
            st.success("お知らせを削除しました")
            if 'confirm_delete_notice' in st.session_state:
                del st.session_state.confirm_delete_notice
            if 'selected_notice_id' in st.session_state:
                del st.session_state.selected_notice_id
            # 少し待ってからページ遷移
            import time
            time.sleep(0.5)
            navigate_to_page("notices")
        else:
            st.session_state.confirm_delete_notice = True
            st.warning("削除ボタンをもう一度押すと削除されます")
    
    if st.button("戻る", key="notice_detail_back_to_notices"):
        if 'selected_notice_id' in st.session_state:
            del st.session_state.selected_notice_id
        navigate_to_page("notices")
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
                   get_all_forms.clear()
                   st.success("お知らせを登録しました")
                   navigate_to_page("notices")
                   
               except Exception as e:
                   st.error(f"データの保存中にエラーが発生しました: {str(e)}")
           else:
               st.error("タイトルと本文は必須項目です")
   
   if st.button("戻る", key="create_notice_back_from_create"):
       navigate_to_page("notices")

def show_edit_notice_page():
   """お知らせ編集ページ"""
   if 'edit_notice_id' not in st.session_state:
       st.error("編集対象が選択されていません")
       if st.button("お知らせ一覧に戻る", key="edit_notice_back_no_selection"):
           navigate_to_page("notices")
       return
   
   form_data = get_form_by_id(st.session_state.edit_notice_id)
   if not form_data:
       st.error("お知らせが見つかりません")
       if st.button("お知らせ一覧に戻る", key="edit_notice_back_not_found"):
           if 'edit_notice_id' in st.session_state:
               del st.session_state.edit_notice_id
           navigate_to_page("notices")
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
                    get_all_forms.clear()
                    st.success("お知らせを更新しました")
                    st.session_state.selected_notice_id = st.session_state.edit_notice_id
                    del st.session_state.edit_notice_id
                    navigate_to_page("notice_detail")
                    
                except Exception as e:
                    st.error(f"データの保存中にエラーが発生しました: {str(e)}")
            else:
                st.error("タイトルと本文は必須項目です")
       
       if cancel:
           st.session_state.selected_notice_id = st.session_state.edit_notice_id
           del st.session_state.edit_notice_id
           navigate_to_page("notice_detail")

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
        contrast = st.text_input("造影プロトコル", placeholder="胸部～骨盤ルーチン")
        
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
                navigate_to_page("search")
    
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
                
                # キャッシュクリア追加
                get_all_sicks.clear()
                search_sicks.clear()
                
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
                navigate_to_page("search")
        
        with col2:
            if st.button("📝 続けて作成", key="create_success_continue", use_container_width=True):
                # 成功フラグをクリアして新規作成を続行
                if 'disease_created' in st.session_state:
                    del st.session_state.disease_created
                if 'created_disease_name' in st.session_state:
                    del st.session_state.created_disease_name
                # 新規作成ページに明示的に遷移
                navigate_to_page("create_disease")
        
        with col3:
            if st.button("👁️ 作成した疾患を確認", key="create_success_view_created", use_container_width=True):
                # 作成した疾患の詳細ページに移動
                # 最新の疾患データを取得
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM sicks WHERE diesease = %s ORDER BY created_at DESC LIMIT 1", 
                              (st.session_state.get('created_disease_name', ''),))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    st.session_state.selected_sick_id = result[0]
                    # 成功フラグをクリア
                    if 'disease_created' in st.session_state:
                        del st.session_state.disease_created
                    if 'created_disease_name' in st.session_state:
                        del st.session_state.created_disease_name
                    navigate_to_page("detail")
        
        # この場合は戻るボタンを表示しない
        return
    
    # 戻るボタン（通常時のみ表示）
    if st.button("戻る", key="create_disease_back_from_create"):
        navigate_to_page("search")

def show_edit_disease_page():
   """疾患編集ページ（完全版）"""
   if 'edit_sick_id' not in st.session_state:
       st.error("編集対象が選択されていません")
       if st.button("検索に戻る", key="edit_disease_back_no_selection"):
           navigate_to_page("search")
       return
   
   sick_data = get_sick_by_id(st.session_state.edit_sick_id)
   if not sick_data:
       st.error("疾患データが見つかりません")
       if st.button("検索に戻る", key="edit_disease_back_not_found"):
           if 'edit_sick_id' in st.session_state:
               del st.session_state.edit_sick_id
           navigate_to_page("search")
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
               
               # キャッシュクリア
               get_all_sicks.clear()
               search_sicks.clear()
               
               st.success("疾患データを更新しました")
               st.session_state.selected_sick_id = st.session_state.edit_sick_id
               del st.session_state.edit_sick_id
               navigate_to_page("detail")
               
           except Exception as e:
               st.error(f"データ更新中にエラーが発生しました: {str(e)}")
   
   if cancel:
       st.session_state.selected_sick_id = st.session_state.edit_sick_id
       del st.session_state.edit_sick_id
       navigate_to_page("detail")

def show_protocols_page():
    """CTプロトコル一覧ページ"""
    st.markdown('<div class="main-header"><h1>📋 CTプロトコル管理</h1></div>', unsafe_allow_html=True)
    
    # カテゴリー定義
    categories = ["頭部", "頸部", "胸部", "腹部", "下肢", "上肢", "特殊"]
    
    # 新規作成・検索ボタン
    col1, col2 = st.columns(2)
    with col1:
        if st.button("新規プロトコル作成", key="protocols_create_new"):
            navigate_to_page("create_protocol")
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
                        navigate_to_page("protocol_detail")
                
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
                            st.session_state.selected_protocol_id = int(row['id'])  # ←int()を追加
                            navigate_to_page("protocol_detail")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info(f"{category}のプロトコルはまだ登録されていません")
                if st.button(f"{category}のプロトコルを作成", key=f"create_{category}_protocol"):
                    st.session_state.default_category = category
                    navigate_to_page("create_protocol")

def show_protocol_detail_page():
    """CTプロトコル詳細ページ"""

    if 'selected_protocol_id' not in st.session_state:
        st.error("プロトコルが選択されていません")
        if st.button("プロトコル一覧に戻る", key="protocol_detail_back_no_selection"):
            navigate_to_page("protocols")
        return
    
    protocol_data = get_protocol_by_id(st.session_state.selected_protocol_id)
    if not protocol_data:
        st.error("プロトコルが見つかりません")
        if st.button("プロトコル一覧に戻る", key="protocol_detail_back_not_found"):
            if 'selected_protocol_id' in st.session_state:
                del st.session_state.selected_protocol_id
            navigate_to_page("protocols")
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
    st.markdown("### プロトコル内容")
    display_rich_content(protocol_data[3])
    
    # プロトコル画像表示
    if protocol_data[4]:  # protocol_img
        st.markdown("### 📷 プロトコル画像")
        display_image_with_caption(protocol_data[4], "プロトコル画像")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 編集・削除・戻るボタン
    if st.button("編集", key="protocol_detail_edit"):
        st.session_state.edit_protocol_id = protocol_data[0]
        navigate_to_page("edit_protocol")
    
    if st.button("削除", key="protocol_detail_delete"):
        if st.session_state.get('confirm_delete_protocol', False):
            delete_protocol(protocol_data[0])
            # 全てのプロトコル関連キャッシュをクリア
            get_all_protocols.clear()
            get_protocols_by_category.clear()
            search_protocols.clear()
            st.success("プロトコルを削除しました")
            if 'confirm_delete_protocol' in st.session_state:
                del st.session_state.confirm_delete_protocol
            if 'selected_protocol_id' in st.session_state:
                del st.session_state.selected_protocol_id
            navigate_to_page("protocols")
        else:
            st.session_state.confirm_delete_protocol = True
            st.warning("削除ボタンをもう一度押すと削除されます")
    
    if st.button("⬅️ 戻る", key="protocol_detail_back"):
    # キャッシュクリアしてから画面遷移
        if 'protocol_search_results' in st.session_state:
            del st.session_state.protocol_search_results
        navigate_to_page("protocols")
    # selected_protocol_idは削除しない（navigate_to_page内で適切に処理される）

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
                if 'default_category' in st.session_state:
                    del st.session_state.default_category
                navigate_to_page("protocols")
    
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
                get_all_protocols.clear()  # キャッシュクリア
                
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
            <h3>📋 作成完了</h3>
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
                navigate_to_page("protocols")
        
        with col2:
            if st.button("📝 続けて作成", key="create_protocol_success_continue", use_container_width=True):
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
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM protocols WHERE title = %s AND category = %s ORDER BY created_at DESC LIMIT 1", 
                              (st.session_state.get('created_protocol_title', ''), st.session_state.get('created_protocol_category', '')))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    st.session_state.selected_protocol_id = result[0]
                    # 成功フラグをクリア
                    if 'protocol_created' in st.session_state:
                        del st.session_state.protocol_created
                    if 'created_protocol_title' in st.session_state:
                        del st.session_state.created_protocol_title
                    if 'created_protocol_category' in st.session_state:
                        del st.session_state.created_protocol_category
                    navigate_to_page("protocol_detail")
        return
    
    # 戻るボタン（通常時のみ表示）
    if st.button("戻る", key="create_protocol_back"):
        if 'default_category' in st.session_state:
            del st.session_state.default_category
        navigate_to_page("protocols")

def show_edit_protocol_page():
    """CTプロトコル編集ページ"""
    if 'edit_protocol_id' not in st.session_state:
        st.error("編集対象が選択されていません")
        if st.button("プロトコル一覧に戻る", key="edit_protocol_back_no_selection"):
            navigate_to_page("protocols")
        return
    
    protocol_data = get_protocol_by_id(st.session_state.edit_protocol_id)
    if not protocol_data:
        st.error("プロトコルが見つかりません")
        if st.button("プロトコル一覧に戻る", key="edit_protocol_back_not_found"):
            if 'edit_protocol_id' in st.session_state:
                del st.session_state.edit_protocol_id
            navigate_to_page("protocols")
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
                    get_all_protocols.clear()  # キャッシュクリア
                    st.success("プロトコルを更新しました")
                    st.session_state.selected_protocol_id = st.session_state.edit_protocol_id
                    del st.session_state.edit_protocol_id
                    navigate_to_page("protocol_detail")
                    
                except Exception as e:
                    st.error(f"データの保存中にエラーが発生しました: {str(e)}")
            else:
                st.error("タイトルとプロトコル内容は必須項目です")
        
        if cancel:
            st.session_state.selected_protocol_id = st.session_state.edit_protocol_id
            del st.session_state.edit_protocol_id
            navigate_to_page("protocol_detail")

# サイドバー関数
def show_sidebar():
    """サイドバー表示"""
    with st.sidebar:
        st.markdown("### 🏥 How to CT")
        
        # if RICH_EDITOR_AVAILABLE:
        #     st.success("📝 リッチテキストエディタ対応")
        # else:
        #     st.warning("📝 リッチエディタ未対応")
        
        if 'user' in st.session_state:
            st.markdown(f"**ログイン中:** {st.session_state.user['name']}")
            
            
            st.markdown("---")
            st.markdown("### 📋 メニュー")
            
            if st.button("🏠 ホーム", use_container_width=True, key="sidebar_home"):
                navigate_to_page("home")
            
            if st.button("🔍 疾患検索", use_container_width=True, key="sidebar_search"):
                navigate_to_page("search")
            
            if st.button("📢 お知らせ", use_container_width=True, key="sidebar_notices"):
                navigate_to_page("notices")

            if st.button("📋 CTプロトコル", use_container_width=True, key="sidebar_protocols"):
                navigate_to_page("protocols")
            
            st.markdown("---")
            
            if st.button("📝 新規疾患作成", use_container_width=True, key="sidebar_create_disease"):
                navigate_to_page("create_disease")
            
            if st.button("📝 新規お知らせ作成", use_container_width=True, key="sidebar_create_notice"):
                navigate_to_page("create_notice")
            
            st.markdown("---")
            
            if st.button("🚪 ログアウト", use_container_width=True, key="sidebar_logout"):
    # ログアウト時にセッション情報をクリア
                if 'user' in st.session_state:
                    user_id = st.session_state.user['id']
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM user_sessions WHERE user_id = %s', (user_id,))
                        conn.commit()
                        cursor.close()
                        conn.close()
                    except:
                        pass
                
                # 全てのセッション状態をクリア
                for key in list(st.session_state.keys()):
                    if key != 'db_initialized':  # DB初期化状態は保持
                        del st.session_state[key]
                
                # ログインページに遷移
                st.session_state.page = "login"
                st.query_params.clear()             
                st.query_params['page'] = "login"
                st.rerun()

            # 管理者メニュー（管理者のみ表示）
            if is_admin_user():
                st.markdown("---")
                st.markdown("### 👨‍💼 管理者メニュー")
                if st.button("ユーザー管理", use_container_width=True, key="sidebar_admin"):
                    navigate_to_page("admin")
        
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


def export_all_data():
    """全データをJSONでエクスポート（PostgreSQL版）"""
    try:
        conn = get_db_connection()
        if not conn:
            return None, "PostgreSQL接続に失敗しました"
        
        cursor = conn.cursor()
        
        data = {
            'export_info': {
                'export_date': datetime.now().isoformat(),
                'version': '2.0',
                'app_name': 'How to CT Medical System',
                'database_type': 'PostgreSQL'
            },
            'users': [],
            'sicks': [],
            'forms': [],
            'protocols': []
        }
        
        # ユーザーデータ（SQLiteから取得）
        try:
            sqlite_conn = sqlite3.connect('medical_ct.db')
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute("SELECT id, name, email, created_at, updated_at FROM users")
            users = sqlite_cursor.fetchall()
            for user in users:
                data['users'].append({
                    'id': user[0], 'name': user[1], 'email': user[2],
                    'created_at': str(user[3]) if user[3] else '',
                    'updated_at': str(user[4]) if user[4] else ''
                })
            sqlite_conn.close()
        except Exception as e:
            st.warning(f"ユーザーデータの取得に失敗: {str(e)}")
        
        # 疾患データ（PostgreSQLから取得）
        cursor.execute("SELECT * FROM sicks ORDER BY id")
        sicks = cursor.fetchall()
        for sick in sicks:
            data['sicks'].append({
                'id': sick[0], 'diesease': sick[1], 'diesease_text': sick[2],
                'keyword': sick[3], 'protocol': sick[4], 'protocol_text': sick[5],
                'processing': sick[6], 'processing_text': sick[7],
                'contrast': sick[8], 'contrast_text': sick[9],
                'diesease_img': sick[10], 'protocol_img': sick[11],
                'processing_img': sick[12], 'contrast_img': sick[13],
                'created_at': str(sick[14]) if len(sick) > 14 and sick[14] else '',
                'updated_at': str(sick[15]) if len(sick) > 15 and sick[15] else ''
            })
        
        # お知らせデータ（PostgreSQLから取得）
        cursor.execute("SELECT * FROM forms ORDER BY id")
        forms = cursor.fetchall()
        for form in forms:
            data['forms'].append({
                'id': form[0], 'title': form[1], 'main': form[2],
                'post_img': form[3],
                'created_at': str(form[4]) if len(form) > 4 and form[4] else '',
                'updated_at': str(form[5]) if len(form) > 5 and form[5] else ''
            })
        
        # プロトコルデータ（PostgreSQLから取得）
        cursor.execute("SELECT * FROM protocols ORDER BY id")
        protocols = cursor.fetchall()
        for protocol in protocols:
            data['protocols'].append({
                'id': protocol[0], 'category': protocol[1], 'title': protocol[2],
                'content': protocol[3], 'protocol_img': protocol[4],
                'created_at': str(protocol[5]) if len(protocol) > 5 and protocol[5] else '',
                'updated_at': str(protocol[6]) if len(protocol) > 6 and protocol[6] else ''
            })
        
        conn.close()
        return data, "OK"
        
    except Exception as e:
        return None, f"データエクスポート中にエラー: {str(e)}"

def create_backup_zip():
    """バックアップZIPファイルを作成"""
    try:
        # データをエクスポート
        data, error = export_all_data()
        if not data:
            return None, error
        
        # ZIPファイルをメモリ上で作成
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # JSONデータを追加
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            zip_file.writestr('backup_data.json', json_data)
            
            # README.txtを追加
            readme_content = f"""How to CT Medical System - Backup File
==================================================

作成日時: {datetime.now().strftime('%Y年%m月%d日 %H時%M分%S秒')}
バージョン: 2.0
データベース: PostgreSQL + SQLite (ハイブリッド)

含まれるデータ:
- 疾患データ: {len(data['sicks'])}件
- お知らせ: {len(data['forms'])}件  
- CTプロトコル: {len(data['protocols'])}件
- ユーザー情報: {len(data['users'])}件 (パスワード除く)

復元方法:
1. 管理者ページの「データ管理」タブを開く
2. 「データ復元」セクションでこのZIPファイルをアップロード
3. 「データを復元」ボタンをクリック

注意: 復元時は既存データに追加されます。重複する場合は上書きされる可能性があります。
"""
            zip_file.writestr('README.txt', readme_content)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue(), None
        
    except Exception as e:
        return None, f"バックアップZIP作成中にエラー: {str(e)}"

def restore_from_json(json_data):
    """JSONデータから復元（PostgreSQL版）"""
    try:
        conn = get_db_connection()
        if not conn:
            return False, "PostgreSQL接続に失敗しました"
        
        cursor = conn.cursor()
        restored_counts = {'sicks': 0, 'forms': 0, 'protocols': 0}
        
        # 疾患データ復元
        if 'sicks' in json_data:
            for sick in json_data['sicks']:
                try:
                    cursor.execute('''
                        INSERT INTO sicks (
                            diesease, diesease_text, keyword, protocol, protocol_text,
                            processing, processing_text, contrast, contrast_text,
                            diesease_img, protocol_img, processing_img, contrast_img
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (diesease) DO UPDATE SET
                            diesease_text = EXCLUDED.diesease_text,
                            keyword = EXCLUDED.keyword,
                            protocol = EXCLUDED.protocol,
                            protocol_text = EXCLUDED.protocol_text,
                            processing = EXCLUDED.processing,
                            processing_text = EXCLUDED.processing_text,
                            contrast = EXCLUDED.contrast,
                            contrast_text = EXCLUDED.contrast_text,
                            diesease_img = EXCLUDED.diesease_img,
                            protocol_img = EXCLUDED.protocol_img,
                            processing_img = EXCLUDED.processing_img,
                            contrast_img = EXCLUDED.contrast_img,
                            updated_at = CURRENT_TIMESTAMP
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
                        sick.get('diesease_img', ''),
                        sick.get('protocol_img', ''),
                        sick.get('processing_img', ''),
                        sick.get('contrast_img', '')
                    ))
                    restored_counts['sicks'] += 1
                except Exception as e:
                    st.warning(f"疾患データスキップ: {sick.get('diesease', 'Unknown')} - {str(e)}")
        
        # お知らせデータ復元
        if 'forms' in json_data:
            for form in json_data['forms']:
                try:
                    cursor.execute('''
                        INSERT INTO forms (title, main, post_img)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (title) DO UPDATE SET
                            main = EXCLUDED.main,
                            post_img = EXCLUDED.post_img,
                            updated_at = CURRENT_TIMESTAMP
                    ''', (
                        form.get('title', ''),
                        form.get('main', ''),
                        form.get('post_img', '')
                    ))
                    restored_counts['forms'] += 1
                except Exception as e:
                    st.warning(f"お知らせデータスキップ: {form.get('title', 'Unknown')} - {str(e)}")
        
        # プロトコルデータ復元
        if 'protocols' in json_data:
            for protocol in json_data['protocols']:
                try:
                    cursor.execute('''
                        INSERT INTO protocols (category, title, content, protocol_img)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (title) DO UPDATE SET
                            category = EXCLUDED.category,
                            content = EXCLUDED.content,
                            protocol_img = EXCLUDED.protocol_img,
                            updated_at = CURRENT_TIMESTAMP
                    ''', (
                        protocol.get('category', ''),
                        protocol.get('title', ''),
                        protocol.get('content', ''),
                        protocol.get('protocol_img', '')
                    ))
                    restored_counts['protocols'] += 1
                except Exception as e:
                    st.warning(f"プロトコルデータスキップ: {protocol.get('title', 'Unknown')} - {str(e)}")
        
        # コミット
        conn.commit()
        conn.close()
        
        # キャッシュクリア
        if 'all_sicks_data' in st.session_state:
            del st.session_state['all_sicks_data']
        if 'all_forms_data' in st.session_state:
            del st.session_state['all_forms_data']
        if 'all_protocols_data' in st.session_state:
            del st.session_state['all_protocols_data']
        
        return True, restored_counts
        
    except Exception as e:
        return False, f"データ復元中にエラー: {str(e)}"

def import_sqlite_data(sqlite_file_path):
    """SQLite（Laravel版）からPostgreSQLにデータを移行（完成版）"""
    try:
        # SQLite接続
        sqlite_conn = sqlite3.connect(sqlite_file_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        # デバッグ: テーブル構造を確認
        st.write("🔍 sicksテーブル構造確認:")
        
        # sicksテーブル構造確認のみ
        try:
            sqlite_cursor.execute("PRAGMA table_info(sicks)")
            sick_columns = sqlite_cursor.fetchall()
            st.write("📋 sicksテーブル:")
            for col in sick_columns:
                st.write(f"  - {col[0]}: {col[1]} ({col[2]})")
            
            # sicksサンプルデータ
            sqlite_cursor.execute("SELECT * FROM sicks LIMIT 1")
            sick_samples = sqlite_cursor.fetchall()
            st.write("📋 sicksサンプルデータ:")
            for i, sample in enumerate(sick_samples):
                st.write(f"  Row {i+1}: {sample}")
        except Exception as e:
            st.warning(f"sicksテーブル確認エラー: {e}")
        
        # PostgreSQL接続
        pg_conn = get_db_connection()
        if not pg_conn:
            return False, "PostgreSQL接続に失敗しました"
        
        pg_cursor = pg_conn.cursor()
        
        imported_counts = {'sicks': 0, 'forms': 0, 'protocols': 0}
        
        # UNIQUE制約を追加
        try:
            pg_cursor.execute('''
                ALTER TABLE sicks ADD CONSTRAINT unique_diesease UNIQUE (diesease)
            ''')
            st.write("✅ 疾患テーブルにUNIQUE制約を追加しました")
        except Exception as e:
            if "already exists" in str(e) or "unique_diesease" in str(e):
                st.write("ℹ️ 疾患テーブルのUNIQUE制約は既に存在します")
        
        pg_conn.commit()
        
        # 疾患データ移行（強化版）
        try:
            sqlite_cursor.execute("SELECT COUNT(*) FROM sicks")
            sick_count = sqlite_cursor.fetchone()[0]
            st.write(f"📊 SQLite疾患データ件数: {sick_count}件")
            
            sqlite_cursor.execute("SELECT * FROM sicks")
            sicks = sqlite_cursor.fetchall()
            
            for sick in sicks:
                try:
                    # 重複チェック
                    pg_cursor.execute("SELECT COUNT(*) FROM sicks WHERE diesease = %s", (sick[1],))
                    exists = pg_cursor.fetchone()[0] > 0
                    
                    if exists:
                        st.write(f"⚠️ 疾患データ重複スキップ: {sick[1]}")
                        continue
                    
                    # 強化された日付検出関数
                    def is_datetime_string(value):
                        if not value:
                            return False
                        if isinstance(value, str):
                            # より厳密な日付パターンをチェック
                            datetime_patterns = [
                                r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$',  # 2023-09-19 08:09:37
                                r'^\d{4}-\d{2}-\d{2}[\s\d:.-]*$',  # その他の日付パターン
                                r'^\d{4}/\d{2}/\d{2}',  # 2023/09/19形式
                                r'^\d{2}:\d{2}:\d{2}$',  # 08:09:37のみ
                            ]
                            for pattern in datetime_patterns:
                                if re.match(pattern, str(value).strip()):
                                    return True
                        return False
                    
                    # より詳細なフィールド処理
                    def clean_field(value, field_name=""):
                        if not value:
                            return ""
                        
                        value_str = str(value).strip()
                        
                        # 日付文字列の場合は除去
                        if is_datetime_string(value_str):
                            st.write(f"  🗑️ 日付データ除去 ({field_name}): {value_str}")
                            return ""
                        
                        # 非常に短い意味のない文字列の場合も除去（ただし1文字以上は保持）
                        if len(value_str) < 1:
                            return ""
                        
                        return value_str
                    
                    # 各フィールドを適切に処理（フィールド名付きでログ出力）
                    diesease = clean_field(sick[1], "疾患名")
                    diesease_text = clean_field(sick[2], "疾患詳細")
                    keyword = clean_field(sick[3], "キーワード")
                    protocol = clean_field(sick[4], "撮影プロトコル")
                    protocol_text = clean_field(sick[5], "撮影詳細")
                    processing = clean_field(sick[6], "画像処理")
                    processing_text = clean_field(sick[7], "画像処理詳細")  # ←重要
                    contrast = clean_field(sick[8], "造影プロトコル")
                    contrast_text = clean_field(sick[9], "造影詳細")
                    
                    # デバッグ: 処理結果を表示（全フィールド）
                    st.write(f"📋 処理結果 - {diesease}:")
                    st.write(f"  - 疾患詳細: '{diesease_text[:50]}...' ({len(diesease_text)}文字)")
                    st.write(f"  - キーワード: '{keyword}'")
                    st.write(f"  - 撮影プロトコル: '{protocol}'")
                    st.write(f"  - 撮影詳細: '{protocol_text[:50]}...' ({len(protocol_text)}文字)")
                    st.write(f"  - 画像処理: '{processing}'")
                    st.write(f"  - 画像処理詳細: '{processing_text[:50]}...' ({len(processing_text)}文字)")
                    st.write(f"  - 造影プロトコル: '{contrast}'")
                    st.write(f"  - 造影詳細: '{contrast_text[:50]}...' ({len(contrast_text)}文字)")
                    
                    # 新規挿入
                    pg_cursor.execute('''
                        INSERT INTO sicks (
                            diesease, diesease_text, keyword, protocol, protocol_text,
                            processing, processing_text, contrast, contrast_text
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        diesease, diesease_text, keyword, protocol, protocol_text,
                        processing, processing_text, contrast, contrast_text
                    ))
                    imported_counts['sicks'] += 1
                    st.write(f"✅ 疾患データ登録: {diesease}")
                    
                except Exception as e:
                    st.warning(f"❌ 疾患データエラー: {sick[1] if len(sick) > 1 else 'Unknown'} - {str(e)}")
                    pg_conn.rollback()
                    continue
        except Exception as e:
            st.warning(f"疾患テーブル処理エラー: {str(e)}")
        
        # お知らせデータ移行（スキップ）
        st.info("ℹ️ お知らせデータの取り込みはスキップされます")
        
        # プロトコルデータ移行（テーブル存在チェック）
        try:
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='protocols'")
            protocol_table_exists = sqlite_cursor.fetchone() is not None
            
            if protocol_table_exists:
                sqlite_cursor.execute("SELECT COUNT(*) FROM protocols")
                protocol_count = sqlite_cursor.fetchone()[0]
                st.write(f"📊 SQLiteプロトコル件数: {protocol_count}件")
                
                if protocol_count > 0:
                    sqlite_cursor.execute("SELECT * FROM protocols")
                    protocols = sqlite_cursor.fetchall()
                    
                    for protocol in protocols:
                        try:
                            # 重複チェック
                            pg_cursor.execute("SELECT COUNT(*) FROM protocols WHERE title = %s", (protocol[2],))
                            exists = pg_cursor.fetchone()[0] > 0
                            
                            if exists:
                                st.write(f"⚠️ プロトコル重複スキップ: {protocol[2]}")
                                continue
                            
                            # 新規挿入
                            pg_cursor.execute('''
                                INSERT INTO protocols (category, title, content) VALUES (%s, %s, %s)
                            ''', (protocol[1] or '一般', protocol[2], protocol[3] or ''))
                            imported_counts['protocols'] += 1
                            st.write(f"✅ プロトコル登録: {protocol[2]}")
                            
                        except Exception as e:
                            st.warning(f"❌ プロトコルエラー: {protocol[2]} - {str(e)}")
                            pg_conn.rollback()
                            continue
            else:
                st.info("ℹ️ Laravel版SQLiteにプロトコルテーブルは存在しません")
        except Exception as e:
            st.warning(f"プロトコルテーブル処理エラー: {str(e)}")
        
        # 最終コミット
        pg_conn.commit()
        sqlite_conn.close()
        pg_conn.close()
        
        # キャッシュクリア（疾患データのみ）
        get_all_sicks.clear()
        
        return True, imported_counts
        
    except Exception as e:
        return False, f"データ移行中にエラー: {str(e)}"

# 管理者ページ（簡略版）
def show_admin_page():
    """管理者専用ページ（完全版）"""
    if not is_admin_user():
        st.error("🚫 管理者権限が必要です")
        return
    
    st.markdown('<div class="main-header"><h1>管理者専用ページ</h1></div>', unsafe_allow_html=True)
    st.markdown(f"**管理者:** {st.session_state.user['name']} ({st.session_state.user['email']})")
    
    # タブで機能を分ける（3つに変更）
    tab1, tab2, tab3 = st.tabs(["新規ユーザー作成", "ユーザー管理", "データ管理"])
    
    with tab1:
        st.markdown("### 👤 新規ユーザー作成")
        
        with st.form("admin_register_form"):
            st.info("管理者のみが新しいユーザーアカウントを作成できます")
            
            name = st.text_input("氏名 *", placeholder="例：山田太郎")
            email = st.text_input("メールアドレス *", placeholder="例：yamada@hospital.jp")
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
                        st.info("💡 正しい形式の例: yamada@hospital.jp")
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
        st.markdown("### 👥 ユーザー管理")
        
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
            st.markdown("### 📊 ユーザー統計")
            
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
                admin_count = len([u for u in df_users['email'] if u in ['admin@hospital.jp']])
                st.metric("管理者数", f"{admin_count}人")
    
    with tab3:
        st.markdown("### 📊 データ管理")
        
        # データエクスポート
        st.markdown("#### 📤 データバックアップ")
        
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
            if st.button("📤 バックアップ作成", use_container_width=True, key="create_backup"):
                with st.spinner("バックアップを作成中..."):
                    backup_data, error = create_backup_zip()
                    
                    if backup_data:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"ct_system_backup_{timestamp}.zip"
                        
                        st.download_button(
                            label="📥 バックアップをダウンロード",
                            data=backup_data,
                            file_name=filename,
                            mime="application/zip",
                            use_container_width=True
                        )
                        st.success("✅ バックアップが作成されました！")
                    else:
                        st.error(f"❌ {error}")
        
        st.markdown("---")
        
        # データ復元
        st.markdown("#### 📥 データ復元")
        
        uploaded_file = st.file_uploader(
            "バックアップファイルを選択",
            type=['json', 'zip'],
            help="backup_data.json または バックアップZIPファイルをアップロード",
            key="backup_file_uploader"
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
                if st.button("📥 データを復元", use_container_width=True, key="restore_data"):
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
                                st.success("🎉 データの復元が完了しました！")
                                st.info(f"""
                                **📊 復元結果:**
                                - 疾患データ: {result['sicks']}件
                                - お知らせ: {result['forms']}件
                                - CTプロトコル: {result['protocols']}件
                                """)
                                st.balloons()
                            else:
                                st.error(f"❌ {result}")
                    
                    except Exception as e:
                        st.error(f"❌ ファイルの処理中にエラーが発生しました: {str(e)}")
        
        st.markdown("---")
        
        # SQLiteデータ取り込み
        st.markdown("#### 📂 Laravel版SQLiteデータ取り込み")
        
        sqlite_uploaded_file = st.file_uploader(
            "Laravel版SQLiteファイルを選択",
            type=['db', 'sqlite', 'sqlite3'],
            help="Laravel版で使用していたSQLiteデータベースファイルをアップロード",
            key="sqlite_import_uploader"
        )
        
        if sqlite_uploaded_file is not None:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.info("""
                **Laravel版SQLiteデータ取り込み:**
                - 既存のPostgreSQLデータに追加されます
                - 重複データがある場合はスキップされます
                - 疾患、お知らせ、CTプロトコルデータが対象です
                """)
            
            with col2:
                if st.button("📂 SQLiteデータを取り込み", use_container_width=True, key="import_sqlite"):
                    with st.spinner("SQLiteデータを取り込み中..."):
                        try:
                            # 一時ファイルに保存
                            import tempfile
                            import os
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
                                tmp_file.write(sqlite_uploaded_file.read())
                                tmp_file_path = tmp_file.name
                            
                            # データ移行実行
                            success, result = import_sqlite_data(tmp_file_path)
                            
                            # 一時ファイル削除
                            os.unlink(tmp_file_path)
                            
                            if success:
                                st.success("🎉 SQLiteデータの取り込みが完了しました！")
                                st.info(f"""
                                **📊 取り込み結果:**
                                - 疾患データ: {result['sicks']}件
                                - お知らせ: {result['forms']}件
                                - CTプロトコル: {result['protocols']}件
                                """)
                                st.balloons()
                            else:
                                st.error(f"❌ {result}")
                        
                        except Exception as e:
                            st.error(f"❌ ファイル処理中にエラー: {str(e)}")
        
        st.markdown("---")
        
        # システム情報
        st.markdown("#### ℹ️ システム情報")
        
        try:
            # PostgreSQLからデータベース統計を取得
            conn = get_db_connection()
            if conn:
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
            else:
                st.error("データベース接続に失敗しました")
                
        except Exception as e:
            st.error(f"システム情報の取得に失敗しました: {str(e)}")
        
        st.caption("💡 定期的なバックアップを推奨します（週1回以上）")
        
        st.markdown("---")
        
        # データクリア（危険な操作）
        st.markdown("#### 🗑️ データクリア（危険）")
        st.error("⚠️ **危険な操作**: 全てのデータ（疾患、お知らせ、CTプロトコル）が完全に削除されます")
        
        if st.checkbox("データクリアを実行することを理解しました", key="confirm_clear_data"):
            if st.button("🗑️ 全データを削除", key="clear_all_data"):
                if st.session_state.get('final_confirm_clear', False):
                    with st.spinner("データを削除中..."):
                        try:
                            conn = get_db_connection()
                            if conn:
                                cursor = conn.cursor()
                                
                                # PostgreSQLデータを削除
                                cursor.execute("DELETE FROM sicks")
                                cursor.execute("DELETE FROM forms") 
                                cursor.execute("DELETE FROM protocols")
                                
                                conn.commit()
                                conn.close()
                                
                                st.success("✅ 全データを削除しました")
                                if 'final_confirm_clear' in st.session_state:
                                    del st.session_state.final_confirm_clear
                            else:
                                st.error("❌ データベース接続に失敗しました")
                        except Exception as e:
                            st.error(f"❌ データ削除に失敗しました: {str(e)}")
                else:
                    st.session_state.final_confirm_clear = True
                    st.warning("⚠️ もう一度ボタンを押すと完全に削除されます")

def logout():
    """ログアウト処理"""
    # ユーザー情報をクリア
    if 'user' in st.session_state:
        del st.session_state.user
    
    # その他の状態もクリア
    states_to_clear = [
        'page', 'page_history', 'login_attempted',
        'selected_sick_id', 'edit_sick_id',
        'selected_notice_id', 'edit_notice_id',
        'selected_protocol_id', 'edit_protocol_id',
        'search_results', 'show_all_diseases', 'protocol_search_results'
    ]
    
    for state in states_to_clear:
        if state in st.session_state:
            del st.session_state[state]
    
    # ログインページに戻す
    st.session_state.page = 'login'
    st.query_params.clear()
    st.query_params["page"] = "login"
    
    # 画面をリロード
    st.rerun()

def initialize_session():
    """セッション初期化"""
    if 'db_initialized' not in st.session_state:
        init_database()
        insert_sample_data()
        st.session_state.db_initialized = True
    return True

def check_login():
    """ログイン状態チェック"""
    if 'user' not in st.session_state:
        return False
    return True

def get_custom_css():
    """カスタムCSS取得"""
    return ""  # 既存のCSSを返すか、空文字でもOK

# ============================================
# 不足している2つの関数のみ - main()関数の直前に追加してください
# ============================================

def clear_page_states(page):
    """ページ遷移時に不要な状態をクリア"""
    clear_states = {
        "search": ['selected_sick_id', 'edit_sick_id'],
        "notices": ['selected_notice_id', 'edit_notice_id'], 
        "protocols": ['selected_protocol_id', 'edit_protocol_id']
    }
    
    if page in clear_states:
        for state in clear_states[page]:
            if state in st.session_state:
                del st.session_state[state]

def navigate_to_page(page):
    """ページナビゲーション - 確実版（ページトップスクロール対応）"""
    # セッション状態を更新
    st.session_state.page = page
    
    # URLを更新（複数の方法で確実に）
    st.query_params.clear()
    st.query_params["page"] = page
    
    # ページトップにスクロール
    st.markdown("""
    <script>
    setTimeout(function() {
        window.scrollTo(0, 0);
        document.documentElement.scrollTop = 0;
        document.body.scrollTop = 0;
    }, 100);
    </script>
    """, unsafe_allow_html=True)
    
    # 強制再読み込み
    st.rerun()

def main():
    """メイン関数 - JavaScript併用版（セッション復元対応）"""
    
    # JavaScript でブラウザイベントを監視
    st.markdown("""
    <script>
    // ページが読み込まれたときに実行
    window.addEventListener('load', function() {
        console.log('Page loaded, current URL:', window.location.search);
    });
    
    // ブラウザの戻る/進むボタンを検知
    window.addEventListener('popstate', function(event) {
        console.log('Browser navigation detected');
        console.log('Current URL:', window.location.search);
        
        // Streamlitに強制リロードを要求
        setTimeout(function() {
            window.location.reload();
        }, 50);
    });
    
    // URLパラメータの変化を監視
    let lastUrl = window.location.search;
    setInterval(function() {
        if (window.location.search !== lastUrl) {
            console.log('URL changed from', lastUrl, 'to', window.location.search);
            lastUrl = window.location.search;
            // ページを強制リロード
            window.location.reload();
        }
    }, 500); // 0.5秒間隔で監視
    </script>
    """, unsafe_allow_html=True)
    
    # セッション状態の初期化
    if not initialize_session():
        st.error("アプリケーションの初期化に失敗しました")
        return
    
    # セッション復元を最初に試行
    if 'user' not in st.session_state:
        restored_session = load_session_from_db()
        if restored_session:
            st.session_state.user = restored_session['user']
            # 復元時は既存のページ設定を優先
            if 'page' not in st.session_state:
                st.session_state.page = restored_session.get('page', 'home')
            
            # 詳細ページ関連の状態も復元
            if restored_session.get('selected_sick_id'):
                st.session_state.selected_sick_id = restored_session['selected_sick_id']
            if restored_session.get('selected_notice_id'):
                st.session_state.selected_notice_id = restored_session['selected_notice_id']
            if restored_session.get('selected_protocol_id'):
                st.session_state.selected_protocol_id = restored_session['selected_protocol_id']
            if restored_session.get('edit_sick_id'):
                st.session_state.edit_sick_id = restored_session['edit_sick_id']
            if restored_session.get('edit_notice_id'):
                st.session_state.edit_notice_id = restored_session['edit_notice_id']
            if restored_session.get('edit_protocol_id'):
                st.session_state.edit_protocol_id = restored_session['edit_protocol_id']
    
    # URL同期処理（現在のページを保持）
    query_params = st.query_params
    url_page = query_params.get('page')
    
    # URLに明示的にページが指定されている場合のみ、そのページに移動
    if url_page and 'user' in st.session_state:
        st.session_state.page = url_page
    elif 'user' in st.session_state and 'page' not in st.session_state:
        # ログイン済みだがページが設定されていない場合のみホームに設定
        st.session_state.page = 'home'
    
    # ページ変更時の状態クリア
    clear_page_states(url_page)
    
    # ログイン処理
    if not check_login():
        show_login_page()
        return
    
    # セッション更新
    update_session_in_db()
    
    # UI表示
    st.markdown(get_custom_css(), unsafe_allow_html=True)
    show_sidebar()
    
    current_page = st.session_state.get('page', 'home')

    try:
        if current_page == 'login':
            show_login_page()
        elif current_page == 'welcome':
            show_welcome_page()
        elif current_page == 'home':
            show_home_page()
        elif current_page == 'search':
            show_search_page()
        elif current_page == 'detail':
            show_detail_page()
        elif current_page == 'create_disease':
            show_create_disease_page()
        elif current_page == 'edit_disease':
            show_edit_disease_page()
        elif current_page == 'notices':
            show_notices_page()
        elif current_page == 'notice_detail':
            show_notice_detail_page()
        elif current_page == 'create_notice':
            show_create_notice_page()
        elif current_page == 'edit_notice':
            show_edit_notice_page()
        elif current_page == 'protocols':
            show_protocols_page()
        elif current_page == 'protocol_detail':
            show_protocol_detail_page()
        elif current_page == 'create_protocol':
            show_create_protocol_page()
        elif current_page == 'edit_protocol':
            show_edit_protocol_page()
        elif current_page == 'admin':
            show_admin_page()
        else:
            # 不明なページの場合は現在のページを保持（変更しない）
            if st.session_state.get('page') not in ['login', 'welcome', 'home', 'search', 'detail', 'create_disease', 'edit_disease', 'notices', 'notice_detail', 'create_notice', 'edit_notice', 'protocols', 'protocol_detail', 'create_protocol', 'edit_protocol', 'admin']:
                st.session_state.page = 'home'
            st.query_params["page"] = st.session_state.page
            
    except Exception as e:
        st.error(f"ページ表示エラー: {str(e)}")
        # エラー時は現在のページを保持
        if 'page' not in st.session_state:
            st.session_state.page = 'home'
        st.query_params["page"] = st.session_state.page


def clear_page_states(page):
    """ページ遷移時に不要な状態をクリア"""
    clear_states = {
        "search": ['selected_sick_id', 'edit_sick_id'],
        "notices": ['selected_notice_id', 'edit_notice_id'], 
        "protocols": ['selected_protocol_id', 'edit_protocol_id']
    }
    
    if page in clear_states:
        for state in clear_states[page]:
            if state in st.session_state:
                del st.session_state[state]



def navigate_to_page(page):
    """ページナビゲーション - 確実版（URL同期対応）"""
    # セッション状態を更新
    st.session_state.page = page
    
    # URLパラメータを更新
    st.query_params.clear()
    st.query_params["page"] = page
    
    # セッションをDBに保存
    if 'user' in st.session_state:
        update_session_in_db()
    
    # 強制再読み込み
    st.rerun()


if __name__ == "__main__":
    main()