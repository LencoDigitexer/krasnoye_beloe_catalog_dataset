import sys
import os
import shutil

# 1. ПРОВЕРКА ЗАВИСИМОСТЕЙ
REQUIRED_PACKAGES = ['pandas', 'matplotlib', 'seaborn', 'numpy', 'fpdf', 'wordcloud']
missing = []
for pkg in REQUIRED_PACKAGES:
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)

if missing:
    print(f"ОШИБКА: Не установлены библиотеки: {', '.join(missing)}")
    print(f"Выполни команду: pip install {' '.join(missing)}")
    input("Нажми Enter для выхода...")
    sys.exit(1)

# 2. ОТКЛЮЧАЕМ GUI
import matplotlib
matplotlib.use('Agg')

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import re
from collections import Counter
from fpdf import FPDF
from datetime import datetime
from wordcloud import WordCloud
import warnings
warnings.filterwarnings('ignore')

# Настройки
DB_FILE = "krasnoe_beloe_products.db"
OUTPUT_DIR = "reports"
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_FILE = os.path.join(SCRIPT_DIR, "arial.ttf")  # Шрифт рядом со скриптом

try:
    plt.style.use('seaborn-darkgrid')
except:
    plt.style.use('default')

sns.set_palette("husl")
plt.rcParams['figure.dpi'] = 100

# ============================================================
# АВТОМАТИЧЕСКАЯ ПОДГОТОВКА ШРИФТА С КИРИЛЛИЦЕЙ
# ============================================================
def ensure_font():
    """Находит системный шрифт с кириллицей и копирует его рядом со скриптом"""
    if os.path.exists(FONT_FILE):
        print(f"Шрифт найден: {FONT_FILE}")
        return True
    
    print("Поиск системного шрифта с поддержкой кириллицы...")
    
    # Список возможных системных шрифтов Windows с кириллицей
    system_fonts = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\verdana.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\georgia.ttf",
    ]
    
    for font_path in system_fonts:
        if os.path.exists(font_path):
            try:
                shutil.copy2(font_path, FONT_FILE)
                print(f"Скопирован шрифт: {font_path} -> {FONT_FILE}")
                return True
            except Exception as e:
                print(f"Не удалось скопировать {font_path}: {e}")
                continue
    
    # Если не нашли - скачаем DejaVuSans с GitHub
    print("Системные шрифты не найдены. Скачиваю DejaVuSans...")
    try:
        import urllib.request
        url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
        urllib.request.urlretrieve(url, FONT_FILE)
        print(f"Шрифт скачан: {FONT_FILE}")
        return True
    except Exception as e:
        print(f"Не удалось скачать шрифт: {e}")
        return False

# ============================================================
# ДИРЕКТОРИИ
# ============================================================
def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

def get_connection():
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"База данных {DB_FILE} не найдена! Сначала запусти парсер.")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def load_data(conn):
    return pd.read_sql_query("SELECT * FROM products", conn)

# ============================================================
# ФУНКЦИИ ОТЧЕТОВ
# ============================================================
def report_general_stats(df):
    return {
        'Всего товаров': len(df),
        'Уникальных ID': df['product_id'].nunique(),
        'Категорий': df['category'].nunique(),
        'Стран': df['country'].nunique(),
        'С ценой': df['price'].notna().sum(),
        'С рейтингом': df['rating'].notna().sum(),
        'Со скидкой': df['discount_price'].notna().sum(),
    }

def plot_top_categories(df):
    top_cats = df['category'].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(top_cats)), top_cats.values, color=sns.color_palette("viridis", len(top_cats)))
    ax.set_yticks(range(len(top_cats)))
    ax.set_yticklabels(top_cats.index, fontsize=10)
    ax.set_title('Топ-15 категорий', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "top_categories.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, top_cats

def plot_price_distribution(df):
    prices = df['price'].dropna()
    prices = prices[prices < prices.quantile(0.95)]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.hist(prices, bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    ax.axvline(prices.mean(), color='red', linestyle='--', label=f'Средняя: {prices.mean():.0f} руб.')
    ax.set_title('Распределение цен', fontsize=14, fontweight='bold')
    ax.legend()
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "price_distribution.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, {'Средняя': f"{prices.mean():.0f} руб.", 'Медиана': f"{prices.median():.0f} руб."}

def plot_avg_price_by_category(df):
    avg_prices = df.groupby('category')['price'].mean().dropna().sort_values(ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(avg_prices)), avg_prices.values, color=sns.color_palette("coolwarm", len(avg_prices)))
    ax.set_yticks(range(len(avg_prices)))
    ax.set_yticklabels(avg_prices.index, fontsize=10)
    ax.set_title('Средняя цена по категориям', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "avg_price_by_category.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, avg_prices

def plot_top_countries(df):
    top = df['country'].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(top)), top.values, color=sns.color_palette("Set2", len(top)))
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top.index, fontsize=10)
    ax.set_title('Топ-15 стран', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "top_countries.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, top

def plot_rating_distribution(df):
    ratings = df['rating'].dropna()
    if len(ratings) == 0: return None, {'Статус': 'Нет рейтингов'}
    fig, ax = plt.subplots(figsize=(10, 6))
    counts = ratings.value_counts().sort_index()
    ax.bar(counts.index, counts.values, color='gold', edgecolor='black')
    ax.set_title('Распределение рейтингов', fontsize=14, fontweight='bold')
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "rating_distribution.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, {'Средний': f"{ratings.mean():.2f}"}

def plot_discount_analysis(df):
    with_disc = df[df['discount_price'].notna()].copy()
    if len(with_disc) == 0: return None, {'Статус': 'Нет скидок'}
    with_disc['pct'] = ((with_disc['price'] - with_disc['discount_price']) / with_disc['price'] * 100)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].pie([len(with_disc), len(df)-len(with_disc)], labels=['Со скидкой', 'Без'], autopct='%1.1f%%')
    axes[0].set_title('Доля скидок')
    axes[1].hist(with_disc['pct'], bins=20, color='coral', edgecolor='black')
    axes[1].set_title('Размер скидок (%)')
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "discount_analysis.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, {'Товаров со скидкой': len(with_disc)}

def plot_wordcloud(df):
    text = ' '.join(df['name'].dropna().astype(str).tolist())
    if not text: return None
    stop_words = {'л', 'мл', 'кг', 'г', 'шт', 'уп', 'и', 'в', 'на', 'с', 'по', 'для', 'от', 'красное', 'белое'}
    fig, ax = plt.subplots(figsize=(12, 8))
    wc = WordCloud(width=1200, height=800, background_color='white', colormap='viridis',
                   stopwords=stop_words, max_words=100, font_path=FONT_FILE if os.path.exists(FONT_FILE) else None).generate(text)
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    ax.set_title('Облако слов', fontsize=16, fontweight='bold')
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "wordcloud.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path

def get_top_expensive(df):
    return df.nlargest(20, 'price')[['name', 'category', 'price', 'country']].copy()

def get_top_cheap(df):
    return df.nsmallest(20, 'price')[['name', 'category', 'price', 'country']].copy()

# ============================================================
# PDF КЛАСС С ПОЛНОЙ ПОДДЕРЖКОЙ КИРИЛЛИЦЫ
# ============================================================
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        
        # Подключаем шрифт с кириллицей
        if not os.path.exists(FONT_FILE):
            raise FileNotFoundError(f"Шрифт {FONT_FILE} не найден! Запусти ensure_font()")
        
        # Обычный, жирный и курсив
        self.add_font('Kyr', '', FONT_FILE, uni=True)
        self.add_font('Kyr', 'B', FONT_FILE, uni=True)
        # Для курсива используем тот же файл (Arial не имеет отдельного italic в ttf)
        self.add_font('Kyr', 'I', FONT_FILE, uni=True)
        
        print(f"Шрифт 'Kyr' подключен из: {FONT_FILE}")

    def header(self):
        self.set_font('Kyr', 'B', 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f'Отчет Krasnoe & Beloe | {datetime.now().strftime("%Y-%m-%d")}', 0, 1, 'C')
        self.line(10, 18, 200, 18)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Kyr', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Страница {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Kyr', 'B', 14)
        self.set_text_color(30, 60, 120)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(2)

    def add_image(self, path, w=180):
        if not path or not os.path.exists(path):
            return
        x = (210 - w) / 2
        self.image(path, x=x, w=w)
        self.ln(5)

    def add_table(self, headers, data, col_widths=None):
        if not col_widths:
            col_widths = [190 / len(headers)] * len(headers)
        self.set_font('Kyr', 'B', 8)
        self.set_fill_color(220, 230, 241)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, str(h), 1, 0, 'C', True)
        self.ln()
        self.set_font('Kyr', '', 7)
        fill = False
        for row in data:
            if self.get_y() > 270:
                self.add_page()
                self.set_font('Kyr', 'B', 8)
                for i, h in enumerate(headers):
                    self.cell(col_widths[i], 8, str(h), 1, 0, 'C', True)
                self.ln()
                self.set_font('Kyr', '', 7)
            if fill:
                self.set_fill_color(245, 245, 245)
            else:
                self.set_fill_color(255, 255, 255)
            for i, cell in enumerate(row):
                text = str(cell)[:int(col_widths[i]/1.8)]
                self.cell(col_widths[i], 8, text, 1, 0, 'L', fill)
            self.ln()
            fill = not fill

def generate_pdf(all_results):
    pdf = PDF()
    pdf.add_page()
    
    # Титулка - ВСЕГДА используем шрифт Kyr
    pdf.set_font('Kyr', 'B', 24)
    pdf.ln(30)
    pdf.cell(0, 15, 'АНАЛИТИЧЕСКИЙ ОТЧЕТ', 0, 1, 'C')
    pdf.set_font('Kyr', '', 16)
    pdf.cell(0, 10, 'Красное & Белое - Каталог товаров', 0, 1, 'C')
    pdf.ln(15)
    pdf.set_font('Kyr', '', 12)
    for k, v in all_results.get('general_stats', {}).items():
        pdf.cell(0, 8, f'{k}: {v}', 0, 1, 'C')

    # Графики
    reports = [
        ('1. Топ категорий', 'top_categories'),
        ('2. Распределение цен', 'price_distribution'),
        ('3. Средняя цена по категориям', 'avg_price_by_category'),
        ('4. Топ стран', 'top_countries'),
        ('5. Распределение рейтингов', 'rating_distribution'),
        ('6. Анализ скидок', 'discount_analysis'),
        ('7. Облако слов', 'wordcloud'),
    ]
    
    for title, key in reports:
        pdf.add_page()
        pdf.chapter_title(title)
        res = all_results.get(key)
        if res:
            if isinstance(res, tuple):
                pdf.add_image(res[0])
            else:
                pdf.add_image(res)

    # Таблицы
    pdf.add_page()
    pdf.chapter_title('8. Топ-20 дорогих товаров')
    df = all_results.get('top_expensive')
    if df is not None:
        data = [[i+1, str(r['name'])[:35], str(r['category'])[:20], f"{r['price']:.0f}", str(r['country'])[:15]]
                for i, r in df.iterrows()]
        pdf.add_table(['#', 'Название', 'Категория', 'Цена', 'Страна'], data, [10, 80, 40, 25, 35])

    pdf.add_page()
    pdf.chapter_title('9. Топ-20 дешевых товаров')
    df = all_results.get('top_cheap')
    if df is not None:
        data = [[i+1, str(r['name'])[:35], str(r['category'])[:20], f"{r['price']:.0f}", str(r['country'])[:15]]
                for i, r in df.iterrows()]
        pdf.add_table(['#', 'Название', 'Категория', 'Цена', 'Страна'], data, [10, 80, 40, 25, 35])

    path = os.path.join(OUTPUT_DIR, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    pdf.output(path)
    return path

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("Генерация отчетов...")
    print("=" * 70)
    
    # Сначала готовим шрифт
    if not ensure_font():
        print("КРИТИЧЕСКАЯ ОШИБКА: Не удалось получить шрифт с кириллицей!")
        input("Нажми Enter для выхода...")
        return
    
    ensure_dirs()
    
    print("[1/10] Подключение к БД...")
    conn = get_connection()
    df = load_data(conn)
    print(f"Загружено товаров: {len(df)}")
    
    if len(df) == 0:
        print("База пуста!")
        conn.close()
        return
    
    all_results = {}
    
    print("[2/10] Статистика...")
    all_results['general_stats'] = report_general_stats(df)
    
    print("[3/10] Категории...")
    all_results['top_categories'] = plot_top_categories(df)
    
    print("[4/10] Цены...")
    all_results['price_distribution'] = plot_price_distribution(df)
    all_results['avg_price_by_category'] = plot_avg_price_by_category(df)
    
    print("[5/10] Страны...")
    all_results['top_countries'] = plot_top_countries(df)
    
    print("[6/10] Рейтинги и скидки...")
    all_results['rating_distribution'] = plot_rating_distribution(df)
    all_results['discount_analysis'] = plot_discount_analysis(df)
    
    print("[7/10] WordCloud...")
    all_results['wordcloud'] = plot_wordcloud(df)
    
    print("[8/10] Топ дорогие...")
    all_results['top_expensive'] = get_top_expensive(df)
    
    print("[9/10] Топ дешевые...")
    all_results['top_cheap'] = get_top_cheap(df)
    
    print("[10/10] Генерация PDF...")
    pdf_path = generate_pdf(all_results)
    
    print(f"\nГОТОВО!")
    print(f"PDF: {os.path.abspath(pdf_path)}")
    print(f"Графики: {os.path.abspath(TEMP_DIR)}")
    conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА !!!")
        print(f"Тип: {type(e).__name__}")
        print(f"Сообщение: {e}")
        import traceback
        traceback.print_exc()
        input("\nНажми Enter чтобы закрыть...")