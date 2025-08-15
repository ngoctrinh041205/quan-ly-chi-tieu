from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'a1f3c8b6e0f9d75c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4'
DB_NAME = 'chi_tieu.db'


def get_conn():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    # Bảng users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Bảng chitieu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chitieu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ten TEXT NOT NULL,
            so_tien REAL NOT NULL,
            mo_ta TEXT
        )
    ''')

    # Lấy danh sách cột hiện có
    cursor.execute("PRAGMA table_info(chitieu)")
    existing_cols = [col[1] for col in cursor.fetchall()]

    if 'user_id' not in existing_cols:
        cursor.execute("ALTER TABLE chitieu ADD COLUMN user_id INTEGER")
    if 'loai' not in existing_cols:
        cursor.execute("ALTER TABLE chitieu ADD COLUMN loai TEXT DEFAULT 'Khác'")
    if 'ngay' not in existing_cols:
        cursor.execute("ALTER TABLE chitieu ADD COLUMN ngay TEXT DEFAULT ''")

    # Bảng ngân sách
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budget (
            user_id INTEGER PRIMARY KEY,
            amount REAL DEFAULT 0
        )
    ''')

    # ✅ Sửa ngày rỗng hoặc sai định dạng -> hôm nay
    today = datetime.date.today().strftime('%Y-%m-%d')
    cursor.execute("SELECT id, ngay FROM chitieu")
    rows = cursor.fetchall()
    for cid, ngay in rows:
        ngay_str = (ngay or '').strip()
        try:
            datetime.datetime.strptime(ngay_str, '%Y-%m-%d')
        except Exception:
            cursor.execute("UPDATE chitieu SET ngay = ? WHERE id = ?", (today, cid))

    conn.commit()
    conn.close()


@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')

    conn = get_conn()
    cursor = conn.cursor()

    query = 'SELECT id, ten, so_tien, mo_ta, loai, ngay FROM chitieu WHERE user_id = ?'
    params = [session['user_id']]

    if from_date:
        query += ' AND ngay >= ?'
        params.append(from_date)
    if to_date:
        query += ' AND ngay <= ?'
        params.append(to_date)

    query += ' ORDER BY ngay DESC, id DESC'
    cursor.execute(query, params)
    data = cursor.fetchall()
    tong_tien = sum([item[2] for item in data]) if data else 0

    cursor.execute('SELECT amount FROM budget WHERE user_id = ?', (session['user_id'],))
    budget_row = cursor.fetchone()
    budget = budget_row[0] if budget_row else 0

    cursor.execute("""
        SELECT strftime('%Y-%m', ngay) AS ym, SUM(so_tien)
        FROM chitieu
        WHERE user_id = ?
        GROUP BY ym
        ORDER BY ym
    """, (session['user_id'],))
    thong_ke_thang = cursor.fetchall()

    print("📊 DEBUG thong_ke_thang =", thong_ke_thang)


    current_ym = datetime.date.today().strftime('%Y-%m')
    cursor.execute("""
        SELECT COALESCE(SUM(so_tien), 0)
        FROM chitieu
        WHERE user_id = ? AND strftime('%Y-%m', ngay) = ?
    """, (session['user_id'], current_ym))
    chi_thang_nay = cursor.fetchone()[0] or 0

    warning = None
    if budget and chi_thang_nay > budget:
        warning = f"⚠️ Bạn đã vượt ngân sách tháng {current_ym} ({chi_thang_nay:,.0f} / {budget:,.0f} đ)"

    conn.close()
    return render_template(
        'index.html',
        danh_sach=data,
        tong_tien=tong_tien,
        from_date=from_date,
        to_date=to_date,
        thong_ke_thang=thong_ke_thang,
        warning=warning,
        chi_thang_nay=chi_thang_nay,
        budget=budget,
        current_ym=current_ym
    )


@app.route('/add', methods=['GET', 'POST'])
def add():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        ten = (request.form.get('ten') or '').strip()
        so_tien_raw = (request.form.get('so_tien') or '').strip()
        mo_ta = (request.form.get('mo_ta') or '').strip()
        loai = (request.form.get('loai') or 'Khác').strip()
        ngay = (request.form.get('ngay') or datetime.date.today().strftime('%Y-%m-%d')).strip()

        if not ten:
            flash('Vui lòng nhập Tên khoản chi.', 'danger')
            return redirect(url_for('add'))

        try:
            so_tien = float(so_tien_raw)
            if so_tien <= 0:
                raise ValueError
        except Exception:
            flash('Số tiền không hợp lệ. Vui lòng nhập số > 0.', 'danger')
            return redirect(url_for('add'))

        try:
            datetime.datetime.strptime(ngay, '%Y-%m-%d')
        except ValueError:
            flash('Ngày không hợp lệ. Định dạng phải là YYYY-MM-DD.', 'danger')
            return redirect(url_for('add'))

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO chitieu (ten, so_tien, mo_ta, loai, ngay, user_id)
               VALUES (?,?,?,?,?,?)''',
            (ten, so_tien, mo_ta, loai, ngay, session['user_id'])
        )
        conn.commit()
        conn.close()
        flash('Đã thêm khoản chi.', 'success')
        return redirect(url_for('index'))

    today = datetime.date.today().strftime('%Y-%m-%d')
    return render_template('add.html', date=today)


@app.route('/delete/<int:id>')
def delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chitieu WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Đã xoá khoản chi.', 'success')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password_raw = request.form.get('password') or ''

        if not username or not password_raw:
            flash('Vui lòng nhập đầy đủ Tên đăng nhập và Mật khẩu.', 'danger')
            return redirect(url_for('register'))

        password = generate_password_hash(password_raw)
        conn = get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash('❌ Tên đăng nhập đã tồn tại.', 'danger')
            return redirect(url_for('register'))

        conn.close()
        flash('Đăng ký thành công. Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Vui lòng nhập Tên đăng nhập và Mật khẩu.', 'danger')
            return redirect(url_for('login'))

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT id, password FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username
            flash('Đăng nhập thành công.', 'success')
            return redirect(url_for('index'))
        else:
            flash('❌ Sai thông tin đăng nhập.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất.', 'info')
    return redirect(url_for('login'))


@app.route('/set_budget', methods=['GET', 'POST'])
def set_budget():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        amount_raw = (request.form.get('amount') or '').strip()
        try:
            amount = float(amount_raw)
            if amount < 0:
                raise ValueError
        except Exception:
            flash('Ngân sách không hợp lệ. Vui lòng nhập số ≥ 0.', 'danger')
            return redirect(url_for('set_budget'))

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('REPLACE INTO budget (user_id, amount) VALUES (?,?)', (session['user_id'], amount))
        conn.commit()
        conn.close()
        flash('Đã cập nhật ngân sách tháng.', 'success')
        return redirect(url_for('index'))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT amount FROM budget WHERE user_id = ?', (session['user_id'],))
    budget_row = cursor.fetchone()
    current_budget = budget_row[0] if budget_row else 0
    conn.close()
    return render_template('set_budget.html', current_budget=current_budget)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
