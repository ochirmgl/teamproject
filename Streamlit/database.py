import sqlite3 # SQLite санг ашиглахад хэрэглэдэг
import hashlib

def init_db():
    # 'dms_system.db' нэртэй файл үүсгэнэ
    conn = sqlite3.connect('dms_system.db')
    cursor = conn.cursor()

    # 1. ROLES хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS roles (  
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_name TEXT NOT NULL
    )''') # Хэрэв roles гэсэн хүснэгт байхгүй бол шинийг үүсгэ гэсэн зоманд юм, AUTOINCREMENT гэдэг нь хэрэглэгч өөрөө дугаар өгөөд явах юм аутоматаар дугаарлаад явах юм.

    # ЭНД НЭМЭХ: Хүснэгт үүсгэсний дараа, өгөгдлийг нь оруулах
    cursor.execute("INSERT OR IGNORE INTO roles (id, role_name) VALUES (1, 'Admin')")
    cursor.execute("INSERT OR IGNORE INTO roles (id, role_name) VALUES (2, 'User')")
    
    # 2. USERS хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role_id INTEGER,
        status TEXT DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (role_id) REFERENCES roles (id)
    )''')

    # 3. CATEGORIES хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT
    )''')

    # 4. DOCUMENTS хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        category_id INTEGER,
        file_path TEXT NOT NULL,
        file_type TEXT,
        source_author TEXT,
        uploaded_by INTEGER,
        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        FOREIGN KEY (category_id) REFERENCES categories (id),
        FOREIGN KEY (uploaded_by) REFERENCES users (id)
    )''')

    # 5. TAGS хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )''')

    # 6. DOCUMENT_TAGS хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS document_tags (
        document_id INTEGER,
        tag_id INTEGER,
        PRIMARY KEY (document_id, tag_id),
        FOREIGN KEY (document_id) REFERENCES documents (id),
        FOREIGN KEY (tag_id) REFERENCES tags (id)
    )''')

    # 7. SEARCH_HISTORY хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        search_query TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    # 8. ACTIVITY_LOGS хүснэгт
    cursor.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        document_id INTEGER,
        action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (document_id) REFERENCES documents (id)
    )''')

    # --- АНХНЫ АДМИН ХЭРЭГЛЭГЧИЙГ АВТОМАТААР ҮҮСГЭХ ---
    # Нууц үгийг sha256 ашиглан hash хийнэ (Жишээ нь нууц үг: admin123)
    admin_password_hash = hashlib.sha256("admin123".encode()).hexdigest()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, role_id, status)
        VALUES (?, ?, ?, ?)
    ''', ('admin', admin_password_hash, 1, 'active'))

    conn.commit()
    conn.close()
    print("Өгөгдлийн сан болон хүснэгтүүд амжилттай үүслээ!")

if __name__ == "__main__":
    init_db()