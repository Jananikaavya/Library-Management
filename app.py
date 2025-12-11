from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import sqlite3
import hashlib
from datetime import datetime
import os
import csv
import json
from io import StringIO, BytesIO
import random
import qrcode
import io
import base64
from datetime import datetime, timedelta

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

    # Books table - UPDATED WITH COVER FIELD
    c.execute('''CREATE TABLE IF NOT EXISTS books
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  author TEXT NOT NULL,
                  isbn TEXT UNIQUE,
                  published_year INTEGER,
                  genre TEXT,
                  status TEXT DEFAULT 'Available',
                  description TEXT,
                  cover TEXT DEFAULT 'default.jpg',
                  created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  email TEXT)''')

    # Borrowings table
    c.execute('''CREATE TABLE IF NOT EXISTS borrowings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  book_id INTEGER,
                  borrowed_date TEXT,
                  due_date TEXT,
                  returned_date TEXT,
                  fine_amount REAL DEFAULT 0,
                  FOREIGN KEY(user_id) REFERENCES users(id),
                  FOREIGN KEY(book_id) REFERENCES books(id))''')
    
    # Library Cards table
    c.execute('''CREATE TABLE IF NOT EXISTS library_cards
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  card_number TEXT UNIQUE,
                  issue_date TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Search History table
    c.execute('''CREATE TABLE IF NOT EXISTS search_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  search_term TEXT,
                  search_by TEXT,
                  search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Seed books if empty
    c.execute("SELECT COUNT(*) AS cnt FROM books")
    if c.fetchone()["cnt"] == 0:
        sample_books = [
            ('To Kill a Mockingbird', 'Harper Lee', '9780061120084', 1960, 'Fiction', 'Available', 'A classic novel about racial injustice in the American South.', 'book2.png'),
            ('1984', 'George Orwell', '9780451524935', 1949, 'Dystopian', 'Available', 'A dystopian social science fiction novel about totalitarian regime.', 'book3.png'),
            ('The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 1925, 'Classic', 'Checked Out', 'A story of the fabulously wealthy Jay Gatsby and his love for Daisy Buchanan.', 'book4.png'),
            ('Pride and Prejudice', 'Jane Austen', '9780141439518', 1813, 'Romance', 'Available', 'A romantic novel of manners that depicts the character development of Elizabeth Bennet.', 'book3.png'),
            ('The Hobbit', 'J.R.R. Tolkien', '9780547928227', 1937, 'Fantasy', 'Available', 'A fantasy novel about the adventures of hobbit Bilbo Baggins.', 'book5.png'),
            ('Harry Potter and the Philosopher\'s Stone', 'J.K. Rowling', '9780747532743', 1997, 'Fantasy', 'Available', 'The first novel in the Harry Potter series.', 'book6.png'),
            ('The Catcher in the Rye', 'J.D. Salinger', '9780316769488', 1951, 'Fiction', 'Available', 'A story about Holden Caulfield\'s experiences in New York City.', 'book7.png'),
            ('The Lord of the Rings', 'J.R.R. Tolkien', '9780544003415', 1954, 'Fantasy', 'Checked Out', 'An epic high-fantasy novel.', 'book8.png'),
            ('Brave New World', 'Aldous Huxley', '9780060850524', 1932, 'Dystopian', 'Available', 'A dystopian social science fiction novel.', 'book9.png'),
            ('The Da Vinci Code', 'Dan Brown', '9780307474278', 2003, 'Mystery', 'Available', 'A mystery thriller novel.', 'book10.png'),
            ('The Alchemist', 'Paulo Coelho', '9780061122415', 1988, 'Fiction', 'Reserved', 'A philosophical novel.', 'book11.png'),
            ('The Hunger Games', 'Suzanne Collins', '9780439023481', 2008, 'Dystopian', 'Available', 'A dystopian novel.', 'book12.png'),
            ('The Girl on the Train', 'Paula Hawkins', '9781594633669', 2015, 'Mystery', 'Available', 'A psychological thriller novel.', 'book13.png'),
            ('Gone Girl', 'Gillian Flynn', '9780307588371', 2012, 'Thriller', 'Checked Out', 'A psychological thriller novel.', 'book14.png'),
            ('Atomic Habits', 'James Clear', '9780735211292', 2018, 'Self-Help', 'Available', 'A guide to building good habits and breaking bad ones.', 'book15.png')
        ]
        c.executemany('''INSERT INTO books (title, author, isbn, published_year, genre, status, description, cover)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', sample_books)

    conn.commit()
    conn.close()


def login_required():
    if 'user_id' not in session:
        flash("Please login first.", "warning")
        return False
    return True

def add_search_history(user_id, search_term, search_by):
    """Add search to history"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO search_history (user_id, search_term, search_by) VALUES (?, ?, ?)",
                  (user_id, search_term, search_by))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

def get_search_history(user_id, limit=5):
    """Get user's search history"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT search_term, search_by, search_date 
        FROM search_history 
        WHERE user_id = ? 
        ORDER BY search_date DESC 
        LIMIT ?
    """, (user_id, limit))
    history = c.fetchall()
    conn.close()
    return history

# -------------------- Database Migration Helper --------------------
def migrate_database():
    """Check and add missing columns to existing database"""
    conn = get_db()
    c = conn.cursor()
    
    # Get table info to check existing columns
    c.execute("PRAGMA table_info(books)")
    columns = [col[1] for col in c.fetchall()]
    
    # Add missing columns one by one
    if 'cover' not in columns:
        try:
            c.execute("ALTER TABLE books ADD COLUMN cover TEXT DEFAULT 'default.jpg'")
            print("✓ Added cover column to books table")
        except Exception as e:
            print(f"✗ Error adding cover column: {e}")
    
    if 'description' not in columns:
        try:
            c.execute("ALTER TABLE books ADD COLUMN description TEXT")
            print("✓ Added description column to books table")
        except Exception as e:
            print(f"✗ Error adding description column: {e}")
    
    if 'created_date' not in columns:
        try:
            # First add the column without default
            c.execute("ALTER TABLE books ADD COLUMN created_date TIMESTAMP")
            print("✓ Added created_date column to books table")
            
            # Then update existing rows with current timestamp
            c.execute("UPDATE books SET created_date = datetime('now') WHERE created_date IS NULL")
            print("✓ Updated existing rows with current timestamp")
        except Exception as e:
            print(f"✗ Error adding created_date column: {e}")
    
    conn.commit()
    
    # Check and create search_history table if needed
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_history'")
    if not c.fetchone():
        c.execute('''CREATE TABLE search_history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      search_term TEXT,
                      search_by TEXT,
                      search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        print("✓ Created search_history table")
    
    conn.commit()
    conn.close()

# -------------------- Routes --------------------
@app.route('/')
def index():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM books ORDER BY RANDOM() LIMIT 6")
    rows = c.fetchall()
    
    # Convert to list of dictionaries and ensure cover field exists
    popular_books = []
    for row in rows:
        book = dict(row)
        # Ensure cover field exists, use default if not
        if not book.get('cover') or book['cover'] is None:
            cover_num = random.randint(1, 6)
            book['cover'] = f'book{cover_num}.jpg'
        popular_books.append(book)
    
    conn.close()
    return render_template('index.html', popular_books=popular_books)

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
        description = request.form.get('description', '').strip()
        # Cover field is optional, default will be used if not provided
        cover = request.form.get('cover', '').strip() or 'default.jpg'

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO books (title, author, isbn, published_year, genre, description, cover, created_date)
                         VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                      (title, author, isbn, published_year, genre, description, cover))
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
        description = request.form.get('description', '').strip()
        cover = request.form.get('cover', '').strip() or 'default.jpg'

        try:
            c.execute("""UPDATE books
                         SET title=?, author=?, isbn=?, published_year=?, genre=?, status=?, description=?, cover=?
                         WHERE id=?""",
                      (title, author, isbn, published_year, genre, status, description, cover, book_id))
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

# -------------------- Enhanced Search Route --------------------
@app.route('/search', methods=['GET', 'POST'])
def search():
    books = []
    search_term = ''
    search_by = 'title'
    sort_by = 'title'
    status_filters = []
    year_from = None
    year_to = None
    available_count = 0
    
    if request.method == 'POST':
        search_term = request.form.get('search_term', '').strip()
        search_by = request.form.get('search_by', 'title')
        sort_by = request.form.get('sort_by', 'title')
        
        # Get advanced filters
        status_filters = request.form.getlist('status[]')
        year_from = request.form.get('year_from')
        year_to = request.form.get('year_to')
        
        # Add to search history if user is logged in
        if 'user_id' in session and search_term:
            add_search_history(session['user_id'], search_term, search_by)
        
        query = "SELECT * FROM books WHERE 1=1"
        params = []
        
        # Basic search
        if search_term:
            if search_by == 'title':
                query += " AND title LIKE ?"
                params.append(f"%{search_term}%")
            elif search_by == 'author':
                query += " AND author LIKE ?"
                params.append(f"%{search_term}%")
            elif search_by == 'genre':
                query += " AND genre LIKE ?"
                params.append(f"%{search_term}%")
            elif search_by == 'year':
                if search_term.isdigit():
                    query += " AND published_year = ?"
                    params.append(int(search_term))
            elif search_by == 'isbn':
                query += " AND isbn LIKE ?"
                params.append(f"%{search_term}%")
        
        # Status filters
        if status_filters:
            placeholders = ','.join('?' * len(status_filters))
            query += f" AND status IN ({placeholders})"
            params.extend(status_filters)
        
        # Year range filter
        if year_from and year_from.isdigit():
            query += " AND published_year >= ?"
            params.append(int(year_from))
        if year_to and year_to.isdigit():
            query += " AND published_year <= ?"
            params.append(int(year_to))
        
        # Sorting
        if sort_by == 'title':
            query += " ORDER BY title ASC"
        elif sort_by == 'title_desc':
            query += " ORDER BY title DESC"
        elif sort_by == 'author':
            query += " ORDER BY author ASC, title ASC"
        elif sort_by == 'year':
            query += " ORDER BY published_year DESC, title ASC"
        elif sort_by == 'year_asc':
            query += " ORDER BY published_year ASC, title ASC"
        elif sort_by == 'added':
            query += " ORDER BY created_date DESC"
        
        conn = get_db()
        c = conn.cursor()
        c.execute(query, params)
        books = c.fetchall()
        
        # Get available count for stats
        c.execute("SELECT COUNT(*) as cnt FROM books WHERE status = 'Available'")
        available_count = c.fetchone()['cnt']
        
        conn.close()
    
    # Get search history if logged in
    search_history = []
    if 'user_id' in session:
        search_history = get_search_history(session['user_id'])
    
    return render_template('search.html', 
                         books=books, 
                         search_term=search_term, 
                         search_by=search_by,
                         sort_by=sort_by,
                         status_filters=status_filters,
                         year_from=year_from,
                         year_to=year_to,
                         available_count=available_count,
                         search_history=search_history)

# -------------------- AJAX Endpoints for Enhanced Features --------------------

@app.route('/api/book/<int:book_id>')
def get_book_details(book_id):
    """Get book details for modal view"""
    if not login_required():
        return jsonify({'error': 'Login required'}), 401
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    conn.close()
    
    if book:
        book_dict = dict(book)
        return jsonify(book_dict)
    else:
        return jsonify({'error': 'Book not found'}), 404

@app.route('/api/quick_search/<search_type>')
def quick_search(search_type):
    """Handle quick search buttons"""
    conn = get_db()
    c = conn.cursor()
    
    if search_type == 'available':
        c.execute("SELECT * FROM books WHERE status='Available' ORDER BY title ASC LIMIT 20")
    elif search_type == 'recent':
        c.execute("SELECT * FROM books ORDER BY created_date DESC LIMIT 10")
    elif search_type == 'fiction':
        c.execute("SELECT * FROM books WHERE genre LIKE '%Fiction%' OR genre LIKE '%Novel%' ORDER BY title ASC LIMIT 20")
    elif search_type == 'popular':
        c.execute("SELECT * FROM books WHERE genre IN ('Fantasy', 'Mystery', 'Thriller', 'Romance') ORDER BY RANDOM() LIMIT 8")
    elif search_type == 'new':
        current_year = datetime.now().year
        c.execute("SELECT * FROM books WHERE published_year >= ? ORDER BY published_year DESC LIMIT 10", (current_year - 5,))
    else:
        conn.close()
        return jsonify({'error': 'Invalid search type'}), 400
    
    books = c.fetchall()
    conn.close()
    
    # Convert to list of dicts
    books_list = [dict(book) for book in books]
    return jsonify(books_list)

@app.route('/api/search_stats')
def get_search_stats():
    """Get search statistics"""
    conn = get_db()
    c = conn.cursor()
    
    # Total books
    c.execute("SELECT COUNT(*) as total FROM books")
    total = c.fetchone()['total']
    
    # Available books
    c.execute("SELECT COUNT(*) as available FROM books WHERE status='Available'")
    available = c.fetchone()['available']
    
    # Genres count
    c.execute("SELECT COUNT(DISTINCT genre) as genres FROM books WHERE genre IS NOT NULL AND genre != ''")
    genres = c.fetchone()['genres']
    
    # Authors count
    c.execute("SELECT COUNT(DISTINCT author) as authors FROM books")
    authors = c.fetchone()['authors']
    
    # Year range
    c.execute("SELECT MIN(published_year) as min_year, MAX(published_year) as max_year FROM books WHERE published_year IS NOT NULL")
    year_range = c.fetchone()
    
    conn.close()
    
    return jsonify({
        'total': total,
        'available': available,
        'genres': genres,
        'authors': authors,
        'min_year': year_range['min_year'] if year_range['min_year'] else 0,
        'max_year': year_range['max_year'] if year_range['max_year'] else datetime.now().year
    })

@app.route('/export/search_results')
def export_search_results():
    """Export search results as CSV"""
    if not login_required():
        return redirect(url_for('login'))
    
    # Get search parameters from session or request
    search_params = session.get('last_search_params', {})
    
    conn = get_db()
    c = conn.cursor()
    
    # Basic query
    query = "SELECT * FROM books"
    params = []
    
    # Add filters if they exist
    if search_params:
        query += " WHERE 1=1"
        if search_params.get('search_term'):
            if search_params.get('search_by') == 'title':
                query += " AND title LIKE ?"
                params.append(f"%{search_params['search_term']}%")
    
    query += " ORDER BY title ASC"
    
    c.execute(query, params)
    books = c.fetchall()
    conn.close()
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Title', 'Author', 'ISBN', 'Year', 'Genre', 'Status', 'Description'])
    
    # Write data
    for book in books:
        writer.writerow([
            book['id'],
            book['title'],
            book['author'],
            book['isbn'] or '',
            book['published_year'] or '',
            book['genre'] or '',
            book['status'],
            (book['description'] or '')[:100]  # First 100 chars
        ])
    
    output.seek(0)
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=search_results.csv"}
    )

# -------------------- Auth Routes --------------------
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

# -------------------- Library Card Backend --------------------
@app.route('/card_stats/<int:user_id>')
def get_card_stats(user_id):
    """Get user statistics for library card"""
    if not login_required():
        return jsonify({'error': 'Login required'}), 401
    
    conn = get_db()
    c = conn.cursor()
    
    # Get user's borrowed books count
    try:
        c.execute("SELECT COUNT(*) as cnt FROM borrowings WHERE user_id=? AND returned_date IS NULL", (user_id,))
        borrowed_result = c.fetchone()
        books_borrowed = borrowed_result['cnt'] if borrowed_result else 0
    except:
        books_borrowed = 0
    
    # Get active reservations (simulated for now)
    import random
    active_reservations = random.randint(0, 5)
    
    # Calculate fines
    try:
        c.execute("SELECT SUM(fine_amount) as total_fines FROM borrowings WHERE user_id=? AND fine_amount > 0", (user_id,))
        fines_result = c.fetchone()
        fines_due = fines_result['total_fines'] if fines_result and fines_result['total_fines'] else 0
    except:
        fines_due = 0
    
    # Reading streak (simulated)
    reading_streak = random.randint(0, 30)
    
    # Get card details
    c.execute("SELECT * FROM library_cards WHERE user_id=?", (user_id,))
    card = c.fetchone()
    
    conn.close()
    
    return jsonify({
        'books_borrowed': books_borrowed,
        'active_reservations': active_reservations,
        'fines_due': fines_due,
        'reading_streak': reading_streak,
        'card_number': card['card_number'] if card else 'Not Issued',
        'issue_date': card['issue_date'] if card else 'N/A',
        'valid_until': (datetime.now() + timedelta(days=365*2)).strftime('%Y-%m-%d') if card else 'N/A'
    })

@app.route('/generate_qr/<int:user_id>')
def generate_qr(user_id):
    """Generate QR code for user's library card"""
    if not login_required():
        return jsonify({'error': 'Login required'}), 401
    
    # Create card data
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM library_cards WHERE user_id=?", (user_id,))
    card = c.fetchone()
    
    if not card:
        conn.close()
        return jsonify({'error': 'No library card found for this user'}), 404
    
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    conn.close()
    
    # Create data string for QR code
    try:
        # Parse issue date safely
        issue_date = card['issue_date']
        try:
            issue_date_obj = datetime.strptime(issue_date, '%Y-%m-%d')
            valid_until = (issue_date_obj + timedelta(days=365*2)).strftime('%Y-%m-%d')
        except:
            valid_until = "Permanent"
        
        card_data = {
            'user_id': user_id,
            'username': user['username'],
            'card_number': card['card_number'],
            'issue_date': issue_date,
            'valid_until': valid_until
        }
    except Exception as e:
        return jsonify({'error': f'Error processing card data: {str(e)}'}), 500
    
    data_string = json.dumps(card_data)
    
    # Generate QR code
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data_string)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'qr_code': f'data:image/png;base64,{img_str}',
            'card_data': card_data
        })
    except Exception as e:
        return jsonify({'error': f'Error generating QR code: {str(e)}'}), 500

@app.route('/download_card_pdf/<int:user_id>')
def download_card_pdf(user_id):
    """Download library card as PDF"""
    if not login_required():
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM library_cards WHERE user_id=?", (user_id,))
    card = c.fetchone()
    
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    
    conn.close()
    
    if not card or not user:
        flash("No card found", "error")
        return redirect(url_for('library_card'))
    
    # Create simple text-based "PDF"
    try:
        issue_date = card['issue_date']
        try:
            issue_date_obj = datetime.strptime(issue_date, '%Y-%m-%d')
            valid_until = (issue_date_obj + timedelta(days=365*2)).strftime('%Y-%m-%d')
        except:
            valid_until = "Permanent"
        
        pdf_content = f"""
        LIBRARY MEMBERSHIP CARD
        ========================
        
        Card Holder: {user['username']}
        Card Number: {card['card_number']}
        Issue Date: {issue_date}
        Valid Until: {valid_until}
        Member ID: LIB{str(user_id).zfill(6)}
        
        This card is issued by Library Management System.
        Present this card for all library services.
        
        Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    except Exception as e:
        pdf_content = f"Error generating PDF: {str(e)}"
    
    response = Response(pdf_content, mimetype='text/plain')
    response.headers['Content-Disposition'] = f'attachment; filename=library_card_{card["card_number"]}.txt'
    
    return response

@app.route('/request_new_card', methods=['POST'])
def request_new_card():
    """Request a new physical library card"""
    if not login_required():
        return jsonify({'error': 'Login required'}), 401
    
    user_id = session.get('user_id')
    reason = request.form.get('reason', 'Replacement requested')
    
    # For now, just simulate
    flash(f"New card request submitted! Reason: {reason}", "success")
    return jsonify({'success': True, 'message': 'Card request submitted successfully'})

@app.route('/library_card')
def library_card():
    if not login_required():
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()
    
    # First check if user exists
    c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    user = c.fetchone()
    
    if not user:
        conn.close()
        flash("User not found in database", "error")
        return redirect(url_for('index'))
    
    # Get or create library card
    c.execute("SELECT * FROM library_cards WHERE user_id=?", (session['user_id'],))
    card = c.fetchone()

    if not card:
        # issue a new card with better format
        card_number = "LIB" + datetime.now().strftime("%y%m%d") + str(session['user_id']).zfill(4)
        issue_date = datetime.now().strftime("%Y-%m-%d")
        try:
            c.execute("INSERT INTO library_cards (user_id, card_number, issue_date) VALUES (?, ?, ?)",
                      (session['user_id'], card_number, issue_date))
            conn.commit()
            c.execute("SELECT * FROM library_cards WHERE user_id=?", (session['user_id'],))
            card = c.fetchone()
        except Exception as e:
            conn.close()
            flash(f"Error creating library card: {str(e)}", "error")
            return redirect(url_for('index'))
    
    # Calculate validity date (2 years from issue)
    valid_until = "Permanent"
    if card and card['issue_date']:
        try:
            issue_date = datetime.strptime(card['issue_date'], '%Y-%m-%d')
            valid_until = (issue_date + timedelta(days=365*2)).strftime('%Y-%m-%d')
        except:
            valid_until = "N/A"
    
    conn.close()
    
    return render_template('library_card.html', 
                         card=card,
                         valid_until=valid_until,
                         user_id=session['user_id'])

# -------------------- Debug Route --------------------
@app.route('/debug_user_status')
def debug_user_status():
    """Debug endpoint to check user and card status"""
    if not login_required():
        return jsonify({'error': 'Login required'}), 401
    
    conn = get_db()
    c = conn.cursor()
    
    # Get user
    c.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    user = c.fetchone()
    
    # Get card
    c.execute("SELECT * FROM library_cards WHERE user_id=?", (session['user_id'],))
    card = c.fetchone()
    
    conn.close()
    
    return jsonify({
        'session_user_id': session['user_id'],
        'session_username': session.get('username'),
        'user_in_db': dict(user) if user else None,
        'card_in_db': dict(card) if card else None
    })

# -------------------- Error Handlers --------------------
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Page not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# -------------------- Main --------------------
if __name__ == '__main__':
    # Check if database exists, if not create it
    if not os.path.exists('library.db'):
        print("Creating new database...")
        init_db()
    else:
        print("Database exists, checking for migrations...")
        # Run migrations to add missing columns
        migrate_database()
    
    print("Starting Library Management System...")
    print("Visit http://localhost:5000 in your browser")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)