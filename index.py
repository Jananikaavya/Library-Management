from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import hashlib
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "supersecretkey_change_me"  # change in production


# -------------------- Database Helpers --------------------
def get_db():
    conn = sqlite3.connect('library.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Books table
    c.execute('''CREATE TABLE IF NOT EXISTS books
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  author TEXT NOT NULL,
                  isbn TEXT UNIQUE,
                  published_year INTEGER,
                  genre TEXT,
                  status TEXT DEFAULT 'Available')''')

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  email TEXT)''')

    # Library Cards table
    c.execute('''CREATE TABLE IF NOT EXISTS library_cards
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  card_number TEXT UNIQUE,
                  issue_date TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Seed books if empty
    c.execute("SELECT COUNT(*) AS cnt FROM books")
    if c.fetchone()["cnt"] == 0:
        sample_books = [
            ('To Kill a Mockingbird', 'Harper Lee', '9780061120084', 1960, 'Fiction', 'Available'),
            ('1984', 'George Orwell', '9780451524935', 1949, 'Dystopian', 'Available'),
            ('The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 1925, 'Classic', 'Checked Out'),
            ('Pride and Prejudice', 'Jane Austen', '9780141439518', 1813, 'Romance', 'Available'),
            ('The Hobbit', 'J.R.R. Tolkien', '9780547928227', 1937, 'Fantasy', 'Available')
        ]
        c.executemany('''INSERT INTO books (title, author, isbn, published_year, genre, status)
                         VALUES (?, ?, ?, ?, ?, ?)''', sample_books)

    conn.commit()
    conn.close()


def login_required():
    if 'user_id' not in session:
        flash("Please login first.", "warning")
        return False
    return True


# -------------------- Routes --------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/books')
def books():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM books ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template('books.html', books=rows)


@app.route('/add_book', methods=['GET', 'POST'])
def add_book():
    if not login_required():
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        isbn = request.form.get('isbn', '').strip() or None
        published_year = request.form.get('published_year') or None
        genre = request.form.get('genre', '').strip()

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO books (title, author, isbn, published_year, genre)
                         VALUES (?, ?, ?, ?, ?)""",
                      (title, author, isbn, published_year, genre))
            conn.commit()
            flash("Book added successfully!", "success")
            return redirect(url_for('books'))
        except sqlite3.IntegrityError:
            flash("ISBN already exists.", "danger")
        finally:
            conn.close()

    return render_template('add_book.html')


@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        isbn = request.form.get('isbn', '').strip() or None
        published_year = request.form.get('published_year') or None
        genre = request.form.get('genre', '').strip()
        status = request.form.get('status', 'Available')

        try:
            c.execute("""UPDATE books
                         SET title=?, author=?, isbn=?, published_year=?, genre=?, status=?
                         WHERE id=?""",
                      (title, author, isbn, published_year, genre, status, book_id))
            conn.commit()
            flash("Book updated.", "success")
            return redirect(url_for('books'))
        except sqlite3.IntegrityError:
            flash("ISBN already exists for another book.", "danger")

    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    conn.close()
    if not book:
        flash("Book not found.", "danger")
        return redirect(url_for('books'))

    return render_template('edit_book.html', book=book)


@app.route('/delete_book/<int:book_id>')
def delete_book(book_id):
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM books WHERE id=?", (book_id,))
    conn.commit()
    conn.close()
    flash("Book deleted.", "info")
    return redirect(url_for('books'))


@app.route('/search', methods=['GET', 'POST'])
def search():
    books = []
    search_term = ''
    search_by = 'title'

    if request.method == 'POST':
        search_term = request.form.get('search_term', '').strip()
        search_by = request.form.get('search_by', 'title')
        query = "SELECT * FROM books"
        params = ()

        if search_term:
            if search_by == 'title':
                query += " WHERE title LIKE ?"
                params = (f"%{search_term}%",)
            elif search_by == 'author':
                query += " WHERE author LIKE ?"
                params = (f"%{search_term}%",)
            elif search_by == 'genre':
                query += " WHERE genre LIKE ?"
                params = (f"%{search_term}%",)
            elif search_by == 'year':
                query += " WHERE published_year = ?"
                params = (search_term,)

        query += " ORDER BY id DESC"
        conn = get_db()
        c = conn.cursor()
        c.execute(query, params)
        books = c.fetchall()
        conn.close()

    return render_template('search.html', books=books, search_term=search_term, search_by=search_by)


# -------------------- Auth --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        raw_password = request.form.get('password', '')
        email = request.form.get('email', '').strip()

        if not username or not raw_password:
            flash("Username and password are required.", "danger")
            return render_template('register.html')

        password_hash = hashlib.sha256(raw_password.encode()).hexdigest()

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                      (username, password_hash, email))
            conn.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "danger")
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        raw_password = request.form.get('password', '')
        password_hash = hashlib.sha256(raw_password.encode()).hexdigest()

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password_hash))
        user = c.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Logged in successfully!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "danger")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))


# -------------------- Digital Library Card --------------------
@app.route('/library_card')
def library_card():
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM library_cards WHERE user_id=?", (session['user_id'],))
    card = c.fetchone()

    if not card:
        # issue a new card
        card_number = "LIB" + str(session['user_id']).zfill(6)
        issue_date = datetime.now().strftime("%Y-%m-%d")
        c.execute("INSERT INTO library_cards (user_id, card_number, issue_date) VALUES (?, ?, ?)",
                  (session['user_id'], card_number, issue_date))
        conn.commit()
        c.execute("SELECT * FROM library_cards WHERE user_id=?", (session['user_id'],))
        card = c.fetchone()

    conn.close()
    return render_template('library_card.html', card=card)


# -------------------- Main --------------------
if __name__ == '__main__':
    if not os.path.exists('library.db'):
        init_db()
    else:
        # Ensure new tables exist if DB already there
        init_db()
    app.run(debug=True)
