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
FONT_FILE = os.path.join(SCRIPT_DIR, "arial.ttf")

try:
    plt.style.use('seaborn-darkgrid')
except:
    plt.style.use('default')

sns.set_palette("husl")
plt.rcParams['figure.dpi'] = 100

# ============================================================
# АВТОМАТИЧЕСКАЯ ПОДГОТОВКА ШРИФТА
# ============================================================
def ensure_font():
    if os.path.exists(FONT_FILE):
        print(f"Шрифт найден: {FONT_FILE}")
        return True
    
    print("Поиск системного шрифта с поддержкой кириллицы...")
    
    system_fonts = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
    ]
    
    for font_path in system_fonts:
        if os.path.exists(font_path):
            try:
                shutil.copy2(font_path, FONT_FILE)
                print(f"Скопирован шрифт: {font_path}")
                return True
            except Exception as e:
                continue
    
    print("Скачиваю DejaVuSans...")
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
# ДИРЕКТОРИИ И БД
# ============================================================
def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

def get_connection():
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"База данных {DB_FILE} не найдена!")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def load_data(conn):
    return pd.read_sql_query("SELECT * FROM products", conn)

# ============================================================
# ОТЧЕТ 1: Общая статистика
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

# ============================================================
# ОТЧЕТ 2: Топ-15 категорий
# ============================================================
def plot_top_categories(df):
    top_cats = df['category'].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(top_cats)), top_cats.values, color=sns.color_palette("viridis", len(top_cats)))
    ax.set_yticks(range(len(top_cats)))
    ax.set_yticklabels(top_cats.index, fontsize=10)
    ax.set_xlabel('Количество товаров', fontsize=12)
    ax.set_title('Топ-15 категорий по количеству товаров', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    
    for i, (val) in enumerate(top_cats.values):
        ax.text(val + 1, i, str(val), va='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "top_categories.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, top_cats

# ============================================================
# ОТЧЕТ 3: Распределение цен
# ============================================================
def plot_price_distribution(df):
    prices = df['price'].dropna()
    prices = prices[prices < prices.quantile(0.95)]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.hist(prices, bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    ax.axvline(prices.mean(), color='red', linestyle='--', linewidth=2, label=f'Средняя: {prices.mean():.0f} руб.')
    ax.axvline(prices.median(), color='green', linestyle='--', linewidth=2, label=f'Медиана: {prices.median():.0f} руб.')
    ax.set_xlabel('Цена (руб.)', fontsize=12)
    ax.set_ylabel('Количество товаров', fontsize=12)
    ax.set_title('Распределение цен товаров', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "price_distribution.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, {
        'Средняя цена': f"{prices.mean():.2f} руб.",
        'Медианная цена': f"{prices.median():.2f} руб.",
        'Минимальная': f"{prices.min():.2f} руб.",
        'Максимальная': f"{prices.max():.2f} руб.",
    }

# ============================================================
# ОТЧЕТ 4: Средняя цена по категориям
# ============================================================
def plot_avg_price_by_category(df):
    avg_prices = df.groupby('category')['price'].mean().dropna().sort_values(ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(avg_prices)), avg_prices.values, color=sns.color_palette("coolwarm", len(avg_prices)))
    ax.set_yticks(range(len(avg_prices)))
    ax.set_yticklabels(avg_prices.index, fontsize=10)
    ax.set_xlabel('Средняя цена (руб.)', fontsize=12)
    ax.set_title('Средняя цена по топ-15 категориям', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    
    for i, val in enumerate(avg_prices.values):
        ax.text(val + 5, i, f"{val:.0f}", va='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "avg_price_by_category.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, avg_prices

# ============================================================
# ОТЧЕТ 5: Топ-15 стран
# ============================================================
def plot_top_countries(df):
    top = df['country'].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(top)), top.values, color=sns.color_palette("Set2", len(top)))
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top.index, fontsize=10)
    ax.set_xlabel('Количество товаров', fontsize=12)
    ax.set_title('Топ-15 стран по количеству товаров', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    
    for i, val in enumerate(top.values):
        ax.text(val + 1, i, str(val), va='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "top_countries.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, top

# ============================================================
# ОТЧЕТ 6: Средняя цена по странам
# ============================================================
def plot_avg_price_by_country(df):
    avg_prices = df.groupby('country')['price'].mean().dropna().sort_values(ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(range(len(avg_prices)), avg_prices.values, color=sns.color_palette("magma", len(avg_prices)))
    ax.set_yticks(range(len(avg_prices)))
    ax.set_yticklabels(avg_prices.index, fontsize=10)
    ax.set_xlabel('Средняя цена (руб.)', fontsize=12)
    ax.set_title('Средняя цена по топ-15 странам', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    
    for i, val in enumerate(avg_prices.values):
        ax.text(val + 5, i, f"{val:.0f}", va='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "avg_price_by_country.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, avg_prices

# ============================================================
# ОТЧЕТ 7: Распределение рейтингов
# ============================================================
def plot_rating_distribution(df):
    ratings = df['rating'].dropna()
    if len(ratings) == 0:
        return None, {'Статус': 'Нет данных о рейтингах'}
    
    fig, ax = plt.subplots(figsize=(10, 6))
    counts = ratings.value_counts().sort_index()
    ax.bar(counts.index, counts.values, color='gold', edgecolor='black', alpha=0.8)
    ax.set_xlabel('Рейтинг', fontsize=12)
    ax.set_ylabel('Количество товаров', fontsize=12)
    ax.set_title('Распределение рейтингов товаров', fontsize=14, fontweight='bold')
    ax.set_xticks(counts.index)
    
    for x, y in zip(counts.index, counts.values):
        ax.text(x, y + 0.5, str(y), ha='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "rating_distribution.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, {
        'Средний рейтинг': f"{ratings.mean():.2f}",
        'Медианный': f"{ratings.median():.2f}",
        'Максимальный': f"{ratings.max():.2f}",
    }

# ============================================================
# ОТЧЕТ 8: Анализ скидок
# ============================================================
def plot_discount_analysis(df):
    with_disc = df[df['discount_price'].notna()].copy()
    if len(with_disc) == 0:
        return None, {'Статус': 'Нет данных о скидках'}
    
    with_disc['pct'] = ((with_disc['price'] - with_disc['discount_price']) / with_disc['price'] * 100)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Pie chart
    disc_counts = [len(with_disc), len(df) - len(with_disc)]
    axes[0].pie(disc_counts, labels=['Со скидкой', 'Без скидки'], autopct='%1.1f%%', 
                colors=['#ff6b6b', '#4ecdc4'], startangle=90)
    axes[0].set_title('Доля товаров со скидкой', fontsize=12, fontweight='bold')
    
    # Histogram
    axes[1].hist(with_disc['pct'], bins=20, color='coral', edgecolor='black', alpha=0.7)
    axes[1].axvline(with_disc['pct'].mean(), color='red', linestyle='--', 
                    label=f"Средняя: {with_disc['pct'].mean():.1f}%")
    axes[1].set_xlabel('Процент скидки', fontsize=12)
    axes[1].set_ylabel('Количество товаров', fontsize=12)
    axes[1].set_title('Распределение размеров скидок', fontsize=12, fontweight='bold')
    axes[1].legend()
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "discount_analysis.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    
    return path, {
        'Товаров со скидкой': len(with_disc),
        'Процент': f"{len(with_disc)/len(df)*100:.1f}%",
        'Средний размер': f"{with_disc['pct'].mean():.1f}%",
    }

# ============================================================
# ОТЧЕТ 9: Анализ объёмов
# ============================================================
def plot_volume_analysis(df):
    volumes = []
    for details in df['details'].dropna():
        match = re.search(r'(\d+[\.,]?\d*)\s*л', str(details), re.IGNORECASE)
        if match:
            vol = float(match.group(1).replace(',', '.'))
            volumes.append(vol)
    
    if not volumes:
        return None, {'Статус': 'Не удалось извлечь объемы'}
    
    volume_df = pd.DataFrame({'volume': volumes})
    volume_counts = volume_df['volume'].value_counts().sort_index()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([str(v) for v in volume_counts.index], volume_counts.values, 
           color='teal', edgecolor='black', alpha=0.7)
    ax.set_xlabel('Объем (л)', fontsize=12)
    ax.set_ylabel('Количество товаров', fontsize=12)
    ax.set_title('Распределение товаров по объему', fontsize=14, fontweight='bold')
    plt.xticks(rotation=45)
    
    for i, count in enumerate(volume_counts.values):
        ax.text(i, count + 0.5, str(count), ha='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "volume_analysis.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    
    return path, {
        'Самый частый': f"{volume_counts.idxmax()} л",
        'Средний объем': f"{volume_df['volume'].mean():.2f} л",
    }

# ============================================================
# ОТЧЕТ 10: Анализ крепости
# ============================================================
def plot_abv_analysis(df):
    abvs = []
    for details in df['details'].dropna():
        match = re.search(r'(\d+[\.,]?\d*)\s*%', str(details))
        if match:
            abv = float(match.group(1).replace(',', '.'))
            abvs.append(abv)
    
    if not abvs:
        return None, {'Статус': 'Не удалось извлечь крепость'}
    
    abv_df = pd.DataFrame({'abv': abvs})
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(abv_df['abv'], bins=30, color='purple', edgecolor='black', alpha=0.7)
    ax.axvline(abv_df['abv'].mean(), color='red', linestyle='--', linewidth=2, 
               label=f"Средняя: {abv_df['abv'].mean():.1f}%")
    ax.set_xlabel('Крепость (%)', fontsize=12)
    ax.set_ylabel('Количество товаров', fontsize=12)
    ax.set_title('Распределение напитков по крепости', fontsize=14, fontweight='bold')
    ax.legend()
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "abv_analysis.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    
    return path, {
        'Средняя крепость': f"{abv_df['abv'].mean():.2f}%",
        'Минимальная': f"{abv_df['abv'].min():.2f}%",
        'Максимальная': f"{abv_df['abv'].max():.2f}%",
    }

# ============================================================
# ОТЧЕТ 11: Корреляция цена-рейтинг
# ============================================================
def plot_price_rating_correlation(df):
    data = df[['price', 'rating']].dropna()
    
    if len(data) < 5:
        return None, {'Статус': 'Недостаточно данных'}
    
    fig, ax = plt.subplots(figsize=(10, 7))
    scatter = ax.scatter(data['rating'], data['price'], alpha=0.5, c=data['price'], 
                         cmap='viridis', s=30, edgecolors='black', linewidth=0.5)
    
    # Линия тренда
    z = np.polyfit(data['rating'], data['price'], 1)
    p = np.poly1d(z)
    x_line = np.linspace(data['rating'].min(), data['rating'].max(), 100)
    ax.plot(x_line, p(x_line), "r--", linewidth=2, label=f'Тренд: y={z[0]:.1f}x+{z[1]:.0f}')
    
    corr = data['price'].corr(data['rating'])
    
    ax.set_xlabel('Рейтинг', fontsize=12)
    ax.set_ylabel('Цена (руб.)', fontsize=12)
    ax.set_title(f'Зависимость цены от рейтинга (корреляция: {corr:.3f})', 
                 fontsize=14, fontweight='bold')
    ax.legend()
    
    plt.colorbar(scatter, ax=ax, label='Цена')
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "price_rating_correlation.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    
    return path, {
        'Коэффициент корреляции': f"{corr:.3f}",
        'Связь': 'Сильная' if abs(corr) > 0.7 else 'Средняя' if abs(corr) > 0.4 else 'Слабая',
    }

# ============================================================
# ОТЧЕТ 12: Boxplot цен по категориям
# ============================================================
def plot_price_boxplot(df):
    top_cats = df['category'].value_counts().head(10).index.tolist()
    data = df[df['category'].isin(top_cats) & df['price'].notna()].copy()
    
    # Убираем выбросы
    q1 = data['price'].quantile(0.05)
    q2 = data['price'].quantile(0.95)
    data = data[(data['price'] >= q1) & (data['price'] <= q2)]
    
    fig, ax = plt.subplots(figsize=(14, 7))
    sns.boxplot(data=data, x='category', y='price', ax=ax, palette='Set2')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right')
    ax.set_xlabel('Категория', fontsize=12)
    ax.set_ylabel('Цена (руб.)', fontsize=12)
    ax.set_title('Распределение цен по категориям (без выбросов)', 
                 fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "price_boxplot.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path

# ============================================================
# ОТЧЕТ 13: WordCloud
# ============================================================
def plot_wordcloud(df):
    text = ' '.join(df['name'].dropna().astype(str).tolist())
    if not text:
        return None
    
    stop_words = {'л', 'мл', 'кг', 'г', 'шт', 'уп', 'и', 'в', 'на', 'с', 'по', 
                  'для', 'от', 'красное', 'белое', 'ж', 'б', 'стекло', 'стеклянная'}
    
    fig, ax = plt.subplots(figsize=(12, 8))
    font_path = FONT_FILE if os.path.exists(FONT_FILE) else None
    wc = WordCloud(width=1200, height=800, background_color='white', 
                   colormap='viridis', stopwords=stop_words, 
                   max_words=150, font_path=font_path).generate(text)
    
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    ax.set_title('Облако слов из названий товаров', fontsize=16, fontweight='bold', pad=20)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "wordcloud.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path

# ============================================================
# ОТЧЕТ 14: Топ "брендов"
# ============================================================
def plot_top_brands(df):
    brands = []
    skip_words = ['вино', 'пиво', 'водка', 'коньяк', 'шампанское', 'виски', 'ром', 
                  'джин', 'ликер', 'настойка', 'текила', 'кальвадос', 'портвейн', 
                  'херес', 'вермут', 'бальзам', 'сыр', 'колбаса', 'рыба', 'шоколад',
                  'конфеты', 'печенье', 'вафли', 'чипсы', 'сухарики', 'орешки']
    
    for name in df['name'].dropna():
        words = str(name).split()
        if words:
            first_word = words[0].lower().rstrip('.,;:!?')
            if first_word not in skip_words and len(first_word) > 2:
                brands.append(words[0])
    
    if not brands:
        return None, {}
    
    brand_counts = Counter(brands).most_common(15)
    brand_names = [b[0] for b in brand_counts]
    brand_values = [b[1] for b in brand_counts]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = sns.color_palette("pastel", len(brand_names))
    bars = ax.barh(range(len(brand_names)), brand_values, color=colors)
    ax.set_yticks(range(len(brand_names)))
    ax.set_yticklabels(brand_names, fontsize=10)
    ax.set_xlabel('Количество товаров', fontsize=12)
    ax.set_title('Топ-15 "брендов" (по первому слову названия)', 
                 fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    
    for i, val in enumerate(brand_values):
        ax.text(val + 0.5, i, str(val), va='center', fontsize=9)
    
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "top_brands.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, dict(brand_counts)

# ============================================================
# ОТЧЕТ 15: Цена по крепости
# ============================================================
def plot_price_by_abv(df):
    abv_data = []
    for idx, row in df.iterrows():
        if pd.isna(row['details']) or pd.isna(row['price']):
            continue
        match = re.search(r'(\d+[\.,]?\d*)\s*%', str(row['details']))
        if match:
            abv = float(match.group(1).replace(',', '.'))
            abv_data.append({'abv': abv, 'price': row['price']})
    
    if not abv_data:
        return None, {}
    
    abv_df = pd.DataFrame(abv_data)
    bins = [0, 5, 10, 15, 20, 25, 30, 40, 50, 100]
    labels = ['0-5%', '5-10%', '10-15%', '15-20%', '20-25%', '25-30%', '30-40%', '40-50%', '50%+']
    abv_df['abv_group'] = pd.cut(abv_df['abv'], bins=bins, labels=labels, right=False)
    
    avg_prices = abv_df.groupby('abv_group', observed=False)['price'].mean()
    counts = abv_df.groupby('abv_group', observed=False)['price'].count()
    
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    color1 = 'tab:blue'
    ax1.set_xlabel('Крепость', fontsize=12)
    ax1.set_ylabel('Средняя цена (руб.)', color=color1, fontsize=12)
    bars = ax1.bar(range(len(avg_prices)), avg_prices.values, color=color1, 
                   alpha=0.6, label='Средняя цена')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.set_xticks(range(len(avg_prices)))
    ax1.set_xticklabels(avg_prices.index, rotation=45)
    
    ax2 = ax1.twinx()
    color2 = 'tab:red'
    ax2.set_ylabel('Количество товаров', color=color2, fontsize=12)
    ax2.plot(range(len(counts)), counts.values, color=color2, marker='o', 
             linewidth=2, label='Количество')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    plt.title('Зависимость цены от крепости напитков', fontsize=14, fontweight='bold')
    fig.tight_layout()
    path = os.path.join(TEMP_DIR, "price_by_abv.png")
    plt.savefig(path, bbox_inches='tight')
    plt.close()
    return path, avg_prices.to_dict()

# ============================================================
# ОТЧЕТ 16-17: Топ дорогих/дешевых
# ============================================================
def get_top_expensive(df):
    return df.nlargest(20, 'price')[['name', 'category', 'price', 'country']].copy()

def get_top_cheap(df):
    return df.nsmallest(20, 'price')[['name', 'category', 'price', 'country']].copy()

# ============================================================
# PDF КЛАСС
# ============================================================
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        
        if not os.path.exists(FONT_FILE):
            raise FileNotFoundError(f"Шрифт {FONT_FILE} не найден!")
        
        self.add_font('Kyr', '', FONT_FILE, uni=True)
        self.add_font('Kyr', 'B', FONT_FILE, uni=True)
        self.add_font('Kyr', 'I', FONT_FILE, uni=True)
        print(f"Шрифт 'Kyr' подключен")

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
    
    # Титулка
    pdf.set_font('Kyr', 'B', 24)
    pdf.ln(30)
    pdf.cell(0, 15, 'АНАЛИТИЧЕСКИЙ ОТЧЕТ', 0, 1, 'C')
    pdf.set_font('Kyr', '', 16)
    pdf.cell(0, 10, 'Красное & Белое - Каталог товаров', 0, 1, 'C')
    pdf.ln(15)
    pdf.set_font('Kyr', '', 12)
    for k, v in all_results.get('general_stats', {}).items():
        pdf.cell(0, 8, f'{k}: {v}', 0, 1, 'C')

    # Все отчеты с графиками
    reports = [
        ('1. Топ категорий', 'top_categories'),
        ('2. Распределение цен', 'price_distribution'),
        ('3. Средняя цена по категориям', 'avg_price_by_category'),
        ('4. Топ стран', 'top_countries'),
        ('5. Средняя цена по странам', 'avg_price_by_country'),
        ('6. Распределение рейтингов', 'rating_distribution'),
        ('7. Анализ скидок', 'discount_analysis'),
        ('8. Анализ объёмов', 'volume_analysis'),
        ('9. Анализ крепости', 'abv_analysis'),
        ('10. Корреляция цена-рейтинг', 'price_rating_correlation'),
        ('11. Boxplot цен', 'price_boxplot'),
        ('12. Облако слов', 'wordcloud'),
        ('13. Топ брендов', 'top_brands'),
        ('14. Цена по крепости', 'price_by_abv'),
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
    pdf.chapter_title('15. Топ-20 дорогих товаров')
    df = all_results.get('top_expensive')
    if df is not None:
        data = [[i+1, str(r['name'])[:35], str(r['category'])[:20], 
                 f"{r['price']:.0f}", str(r['country'])[:15]]
                for i, r in df.iterrows()]
        pdf.add_table(['#', 'Название', 'Категория', 'Цена', 'Страна'], 
                     data, [10, 80, 40, 25, 35])

    pdf.add_page()
    pdf.chapter_title('16. Топ-20 дешевых товаров')
    df = all_results.get('top_cheap')
    if df is not None:
        data = [[i+1, str(r['name'])[:35], str(r['category'])[:20], 
                 f"{r['price']:.0f}", str(r['country'])[:15]]
                for i, r in df.iterrows()]
        pdf.add_table(['#', 'Название', 'Категория', 'Цена', 'Страна'], 
                     data, [10, 80, 40, 25, 35])

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
    
    if not ensure_font():
        print("КРИТИЧЕСКАЯ ОШИБКА: Не удалось получить шрифт!")
        input("Нажми Enter для выхода...")
        return
    
    ensure_dirs()
    
    print("[1/18] Подключение к БД...")
    conn = get_connection()
    df = load_data(conn)
    print(f"Загружено товаров: {len(df)}")
    
    if len(df) == 0:
        print("База пуста!")
        conn.close()
        return
    
    all_results = {}
    
    print("[2/18] Статистика...")
    all_results['general_stats'] = report_general_stats(df)
    
    print("[3/18] Категории...")
    all_results['top_categories'] = plot_top_categories(df)
    
    print("[4/18] Распределение цен...")
    all_results['price_distribution'] = plot_price_distribution(df)
    
    print("[5/18] Средняя цена по категориям...")
    all_results['avg_price_by_category'] = plot_avg_price_by_category(df)
    
    print("[6/18] Страны...")
    all_results['top_countries'] = plot_top_countries(df)
    
    print("[7/18] Средняя цена по странам...")
    all_results['avg_price_by_country'] = plot_avg_price_by_country(df)
    
    print("[8/18] Рейтинги...")
    all_results['rating_distribution'] = plot_rating_distribution(df)
    
    print("[9/18] Скидки...")
    all_results['discount_analysis'] = plot_discount_analysis(df)
    
    print("[10/18] Объемы...")
    all_results['volume_analysis'] = plot_volume_analysis(df)
    
    print("[11/18] Крепость...")
    all_results['abv_analysis'] = plot_abv_analysis(df)
    
    print("[12/18] Корреляция...")
    all_results['price_rating_correlation'] = plot_price_rating_correlation(df)
    
    print("[13/18] Boxplot...")
    all_results['price_boxplot'] = plot_price_boxplot(df)
    
    print("[14/18] WordCloud...")
    all_results['wordcloud'] = plot_wordcloud(df)
    
    print("[15/18] Бренды...")
    all_results['top_brands'] = plot_top_brands(df)
    
    print("[16/18] Цена по крепости...")
    all_results['price_by_abv'] = plot_price_by_abv(df)
    
    print("[17/18] Топ дорогие...")
    all_results['top_expensive'] = get_top_expensive(df)
    
    print("[18/18] Топ дешевые...")
    all_results['top_cheap'] = get_top_cheap(df)
    
    print("\n[GEN] Генерация PDF...")
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