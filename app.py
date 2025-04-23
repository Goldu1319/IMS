from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables from .env file if it exists
load_dotenv()

app = Flask(__name__)

# Configuration for cloud platforms
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-change-this')
# Use DATABASE_URL from cloud platform or fallback to SQLite
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    # Handle Heroku's DATABASE_URL
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.route('/')
def index():
    return redirect(url_for('login'))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    discount = db.Column(db.Float)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Auth routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Admin routes
@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                is_admin=is_admin
            )
            db.session.add(user)
            db.session.commit()
            flash('User created successfully')
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

# Product routes
@app.route('/dashboard')
@login_required
def dashboard():
    products = Product.query.all()
    return render_template('dashboard.html', products=products)

@app.route('/products')
@login_required
def products():
    products = Product.query.all()
    return render_template('products.html', products=products)

@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    if request.method == 'POST':
        product = Product(
            name=request.form.get('name'),
            discount=float(request.form.get('discount')),
            quantity=int(request.form.get('quantity')),
            price=float(request.form.get('price'))
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully')
        return redirect(url_for('products'))
    return render_template('add_product.html')

@app.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.discount = float(request.form.get('discount'))
        product.quantity = int(request.form.get('quantity'))
        product.price = float(request.form.get('price'))
        db.session.commit()
        flash('Product updated successfully')
        return redirect(url_for('products'))
    return render_template('edit_product.html', product=product)

@app.route('/products/delete/<int:id>', methods=['POST'])
@login_required
def delete_product(id):
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully')
    return redirect(url_for('products'))

# Sales routes
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def make_sale():
    if request.method == 'POST':
        product_id = int(request.form.get('product_id'))
        quantity = int(request.form.get('quantity'))
        
        product = Product.query.get_or_404(product_id)
        if product.quantity < quantity:
            flash('Insufficient stock')
            return redirect(url_for('make_sale'))
        
        # Calculate total price with discount
        subtotal = product.price * quantity
        discount_amount = subtotal * (product.discount or 0) / 100
        total_price = subtotal - discount_amount
        
        sale = Sale(
            product_id=product_id,
            quantity=quantity,
            total_price=total_price,
            user_id=current_user.id
        )
        
        product.quantity -= quantity
        db.session.add(sale)
        db.session.commit()
        flash('Sale recorded successfully')
        return redirect(url_for('view_bill', sale_id=sale.id))
    
    products = Product.query.all()
    return render_template('sales.html', products=products)

@app.route('/bill/<int:sale_id>')
@login_required
def view_bill(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    product = Product.query.get_or_404(sale.product_id)
    seller = User.query.get_or_404(sale.user_id)
    return render_template('bill.html', sale=sale, product=product, seller=seller)

@app.route('/sales/report')
@login_required
def sales_report():
    sales = Sale.query.all()
    return render_template('sales_report.html', sales=sales)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash(os.getenv('ADMIN_PASSWORD', 'mintu123')),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
    
    # Get port from environment variable (for cloud platforms)
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)