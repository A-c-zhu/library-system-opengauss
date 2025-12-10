# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify, session,flash
import psycopg2
from config import Config

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'  # 用于 session

def get_db_connection():
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD
    )
    return conn

# ========== 路由 ==========
@app.route('/')
def index():
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 注意：实际应比对哈希值！此处为简化直接比对明文（仅演示）
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT admin_id, password FROM administrators WHERE username = %s", (username,))
        admin = cur.fetchone()
        cur.close()
        conn.close()
        
        if admin and admin[1] == password:  #⚠️ 生产环境必须用哈希比对！
            session['admin_id'] = admin[0]
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="用户名或密码错误")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

# ========== 图书管理 ==========
@app.route('/books')
def books():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.book_id, b.isbn, b.book_name, b.author, c.category_name, b.stock_quantity
        FROM books b
        LEFT JOIN categories c ON b.category_id = c.category_id
        ORDER BY b.book_id
    """)
    books = cur.fetchall()
    cur.execute("SELECT category_id, category_name FROM categories")
    categories = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('books.html', books=books, categories=categories)

@app.route('/add_book', methods=['POST'])
def add_book():
    isbn = request.form['isbn']
    book_name = request.form['book_name']
    author = request.form['author']
    category_id = request.form.get('category_id') or None
    stock = int(request.form['stock'])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO books (isbn, book_name, author, category_id, stock_quantity)
        VALUES (%s, %s, %s, %s, %s)
    """, (isbn, book_name, author, category_id, stock))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('books'))

@app.route('/delete_book/<int:book_id>')
def delete_book(book_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM books WHERE book_id = %s", (book_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('books'))

# ========== 读者管理 ==========
@app.route('/readers')
def readers():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT reader_id, reader_name, phone FROM readers ORDER BY reader_id")
    readers = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('readers.html', readers=readers)

@app.route('/add_reader', methods=['POST'])
def add_reader():
    name = request.form['name']
    phone = request.form['phone']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO readers (reader_name, phone) VALUES (%s, %s)", (name, phone))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('readers'))

@app.route('/delete_reader/<int:reader_id>', methods=['POST'])
def delete_reader(reader_id):
    if 'admin_id' not in session:
        flash("请先登录！", 'error')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 检查该读者是否有未归还的借阅记录
        cur.execute("""
            SELECT COUNT(*) FROM borrow_records 
            WHERE reader_id = %s AND status = '未归还'
        """, (reader_id,))
        has_unreturned = cur.fetchone()[0]

        if has_unreturned > 0:
            flash(f'无法删除读者：该读者有 {has_unreturned} 本图书尚未归还！', 'error')
            return redirect(url_for('readers'))

        # 安全删除：先删借阅记录（可选），再删读者
        cur.execute("DELETE FROM readers WHERE reader_id = %s", (reader_id,))
        conn.commit()
        flash('读者删除成功！', 'success')

    except Exception as e:
        conn.rollback()
        flash(f'删除失败：{str(e)}', 'error')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('readers'))

# ========== 借阅管理 ==========
@app.route('/borrow')
def borrow():
    if 'admin_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT book_id, book_name, stock_quantity 
        FROM books WHERE stock_quantity > 0
    """)
    available_books = cur.fetchall()
    cur.execute("SELECT reader_id, reader_name FROM readers")
    readers = cur.fetchall()
    cur.execute("""
        SELECT br.record_id, b.book_name, r.reader_name, br.borrow_date, br.due_date, br.status
        FROM borrow_records br
        JOIN books b ON br.book_id = b.book_id
        JOIN readers r ON br.reader_id = r.reader_id
        ORDER BY 
            CASE WHEN br.status = '未归还' THEN 0 ELSE 1 END,
            br.due_date ASC
    """)
    records = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('borrow.html', books=available_books, readers=readers, records=records)

@app.route('/do_borrow', methods=['POST'])
def do_borrow():
    book_id = request.form['book_id']
    reader_id = request.form['reader_id']
    due_days = int(request.form['due_days'])
    
    conn = get_db_connection()
    cur = conn.cursor()
    # 检查库存
    cur.execute("SELECT stock_quantity FROM books WHERE book_id = %s", (book_id,))
    stock = cur.fetchone()[0]
    if stock <= 0:
        return "库存不足", 400
    
    # 插入借阅记录
    cur.execute("""
        INSERT INTO borrow_records (book_id, reader_id, due_date)
        VALUES (%s, %s, CURRENT_DATE + %s)
    """, (book_id, reader_id, due_days))
    
    # 减少库存
    cur.execute("UPDATE books SET stock_quantity = stock_quantity - 1 WHERE book_id = %s", (book_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('borrow'))

@app.route('/return_book/<int:record_id>')
def return_book(record_id):
    conn = get_db_connection()
    cur = conn.cursor()
    # 获取 book_id
    cur.execute("SELECT book_id FROM borrow_records WHERE record_id = %s", (record_id,))
    book_id = cur.fetchone()[0]
    
    # 更新归还状态
    cur.execute("""
        UPDATE borrow_records 
        SET return_date = CURRENT_DATE, status = '已归还'
        WHERE record_id = %s
    """, (record_id,))
    
    # 增加库存
    cur.execute("UPDATE books SET stock_quantity = stock_quantity + 1 WHERE book_id = %s", (book_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('borrow'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)