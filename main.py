from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import os
import requests
from urllib.parse import urljoin, urlparse
import re
import sqlite3
from datetime import datetime

# Настройки
BASE_URL = "https://krasnoeibeloe.ru"
CATALOG_URL = "https://krasnoeibeloe.ru/catalog/"
OUTPUT_DIR = "catalog"
DB_FILE = "krasnoe_beloe_products.db"
DOWNLOAD_TIMEOUT = 30

def init_database():
    """Инициализация базы данных SQLite"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Создаем таблицу товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE,
            name TEXT NOT NULL,
            category TEXT,
            url TEXT,
            image_url TEXT,
            country TEXT,
            details TEXT,
            price REAL,
            currency TEXT,
            rating REAL,
            discount_price REAL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(product_id)
        )
    ''')
    
    # Создаем индексы для ускорения поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_product_id ON products(product_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON products(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_name ON products(name)')
    
    conn.commit()
    return conn

def save_product_to_db(conn, product_data):
    """Сохраняет товар в базу данных"""
    cursor = conn.cursor()
    
    # Не сохраняем товары без product_id
    if not product_data.get('product_id'):
        print(f"    Пропущен товар без ID: {product_data.get('name', 'Unknown')}")
        return False
    
    try:
        # Проверяем существует ли товар
        cursor.execute('SELECT id FROM products WHERE product_id = ?', (product_data.get('product_id'),))
        existing = cursor.fetchone()
        
        if existing:
            # Обновляем существующую запись
            cursor.execute('''
                UPDATE products SET 
                    name = ?,
                    category = ?,
                    url = ?,
                    image_url = ?,
                    country = ?,
                    details = ?,
                    price = ?,
                    currency = ?,
                    rating = ?,
                    discount_price = ?,
                    scraped_at = ?
                WHERE product_id = ?
            ''', (
                product_data.get('name'),
                product_data.get('category'),
                product_data.get('url'),
                product_data.get('image_url'),
                product_data.get('country'),
                product_data.get('details'),
                product_data.get('price'),
                product_data.get('currency'),
                product_data.get('rating'),
                product_data.get('discount_price'),
                datetime.now(),
                product_data.get('product_id')
            ))
            conn.commit()
            print(f"    Обновлено: {product_data.get('name')}")
        else:
            # Вставляем новую запись
            cursor.execute('''
                INSERT INTO products 
                (product_id, name, category, url, image_url, country, details, price, currency, rating, discount_price, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                product_data.get('product_id'),
                product_data.get('name'),
                product_data.get('category'),
                product_data.get('url'),
                product_data.get('image_url'),
                product_data.get('country'),
                product_data.get('details'),
                product_data.get('price'),
                product_data.get('currency'),
                product_data.get('rating'),
                product_data.get('discount_price'),
                datetime.now()
            ))
            conn.commit()
            print(f"    Добавлен: {product_data.get('name')}")
         
        return True
    except Exception as e:
        print(f"    Ошибка сохранения в БД: {e}")
        conn.rollback()
        return False

def extract_product_from_card(card_div, category_name):
    """Извлекает данные о товаре из HTML карточки"""
    product_data = {
        'category': category_name
    }
    
    # Извлекаем product_id из id элемента (bx_3966226736_4255608)
    product_id = card_div.get('id', '')
    if product_id:
        # Извлекаем последний номер после последнего подчеркивания
        id_match = re.search(r'bx_\d+_(\d+)', product_id)
        if id_match:
            product_data['product_id'] = id_match.group(1)
    
    # Название товара (itemprop="name")
    name_div = card_div.find('div', itemprop='name')
    if name_div:
        name_link = name_div.find('a')
        product_data['name'] = name_link.get_text(strip=True) if name_link else ''
        # URL товара
        if name_link and name_link.get('href'):
            product_data['url'] = urljoin(BASE_URL, name_link['href'])
    
    # Изображение (itemprop="image")
    img = card_div.find('img', itemprop='image')
    if img and img.get('src'):
        img_src = img['src']
        if img_src.startswith('//'):
            img_src = 'https:' + img_src
        product_data['image_url'] = img_src
    
    # Страна (из country-flag)
    country_flag = card_div.find('div', class_='country-flag')
    if country_flag:
        style = country_flag.get('style', '')
        # Извлекаем URL флага
        img_match = re.search(r'url\(["\']?([^"\')]+)', style)
        if img_match:
            country_url = img_match.group(1)
            # Извлекаем название страны из URL или имени файла
            country_name = os.path.splitext(os.path.basename(country_url))[0]
            product_data['country'] = country_name
    
    # Детали (объем, регион, крепость)
    subtitle = card_div.find('div', class_='product-subtitle')
    if subtitle:
        p_tag = subtitle.find('p')
        if p_tag:
            product_data['details'] = p_tag.get_text(strip=True)
    
    # Цена (itemprop="offers")
    offer_div = card_div.find('div', itemprop='offers', itemtype='http://schema.org/Offer')
    if offer_div:
        # Основная цена
        price_meta = offer_div.find('meta', itemprop='price')
        if price_meta and price_meta.get('content'):
            try:
                product_data['price'] = float(price_meta['content'])
            except:
                pass
        
        currency_meta = offer_div.find('meta', itemprop='priceCurrency')
        if currency_meta and currency_meta.get('content'):
            product_data['currency'] = currency_meta['content']
    
    # Цена со скидкой (если есть класс discount-price)
    if card_div.get('discount-price'):
        # Ищем цену со скидкой
        discount_div = card_div.find('div', class_='i_price', style=re.compile(r'display:\s*none'))
        if discount_div:
            price_span = discount_div.find('span', class_='price__value')
            decimals_span = discount_div.find('span', class_='price__decimals')
            if price_span:
                try:
                    price_value = price_span.get_text(strip=True)
                    decimals = decimals_span.get_text(strip=True) if decimals_span else ''
                    discount_price = float(price_value + decimals)
                    product_data['discount_price'] = discount_price
                except:
                    pass
    
    # Рейтинг
    rate_wrapper = card_div.find('div', class_='rate-wrapper')
    if rate_wrapper:
        # Ищем активный rating (checked)
        checked_input = rate_wrapper.find('input', type='radio', checked=True)
        if checked_input and checked_input.get('value'):
            try:
                product_data['rating'] = float(checked_input['value'])
            except:
                pass
    
    return product_data

def get_catalog_links(page):
    """Парсит ссылки из левого меню каталога (class='left_catalog_c')"""
    print(f"Открываю {CATALOG_URL}...")
    
    page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=60000)
    
    print("\n" + "=" * 60)
    print("ВАЖНО!")
    print("1. Если появилось окно подтверждения возраста - нажми 'Мне есть 18 лет'")
    print("2. Если появилась капча - пройди её")
    print("3. Дождись полной загрузки страницы каталога")
    print("=" * 60)
    print("\nНажми Enter когда страница полностью загрузится...")
    input()
    
    time.sleep(3)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    
    catalog_block = soup.find('div', class_='left_catalog_c')
    
    if not catalog_block:
        print("Блок left_catalog_c не найден!")
        catalog_block = soup.find('ul', class_='left_catalog_c')
        if not catalog_block:
            catalog_block = soup.find('div', class_=re.compile(r'catalog', re.I))
    
    if not catalog_block:
        print("Не удалось найти блок каталога. Сохраняю HTML для анализа.")
        with open("page_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML сохранён в page_debug.html - проверь структуру страницы.")
        return []
    
    links = []
    ul_elements = catalog_block.find_all('ul')
    
    for ul in ul_elements:
        for li in ul.find_all('li', recursive=False):
            a_tag = li.find('a')
            if a_tag and a_tag.get('href'):
                href = a_tag['href']
                text = a_tag.get_text(strip=True)
                
                if href.startswith('/'):
                    full_url = urljoin(BASE_URL, href)
                elif href.startswith('http'):
                    full_url = href
                else:
                    full_url = urljoin(BASE_URL + '/', href)
                
                links.append({
                    'url': full_url,
                    'name': text,
                    'element': li
                })
                print(f"  Найдена категория: {text} -> {full_url}")
    
    print(f"\nНайдено {len(links)} категорий")
    return links

def get_max_page_number(soup):
    """Извлекает максимальный номер страницы из пагинации"""
    pagination = soup.find('div', class_='bl_pagination')
    
    if not pagination:
        return 1
    
    all_links = pagination.find_all('a')
    
    max_page = 1
    for link in all_links:
        href = link.get('href', '')
        match = re.search(r'PAGEN_1=(\d+)', href)
        if match:
            page_num = int(match.group(1))
            max_page = max(max_page, page_num)
    
    return max_page

def sanitize_folder_name(name):
    """Очищает имя для использования как имя папки"""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name[:100]

def download_image(url, filepath):
    """Скачивает картинку"""
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  Ошибка скачивания {url}: {e}")
        return False

def extract_images_from_page(soup):
    """Извлекает все картинки товаров со страницы"""
    images = []
    
    product_cards = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
    for card in product_cards:
        img = card.find('img')
        if img and img.get('src'):
            images.append(img['src'])
        elif img and img.get('data-src'):
            images.append(img['data-src'])
    
    if not images:
        all_imgs = soup.find_all('img')
        for img in all_imgs:
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src:
                if any(x in src.lower() for x in ['upload', 'product', 'catalog', 'images']):
                    images.append(src)
    
    unique_images = []
    seen = set()
    for img_url in images:
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = urljoin(BASE_URL, img_url)
        
        if img_url not in seen:
            seen.add(img_url)
            unique_images.append(img_url)
    
    return unique_images

def get_category_images(page, category_name, category_url, db_conn):
    """Парсит и скачивает все картинки из категории с учётом пагинации"""
    print(f"\nОткрываю категорию: {category_name}")
    
    try:
        page.goto(category_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  Ошибка загрузки страницы: {e}")
        return 0, 0
    
    time.sleep(3)
    
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    max_pages = get_max_page_number(soup)
    
    print(f"  Найдено страниц: {max_pages}")
    
    folder_name = sanitize_folder_name(category_name)
    category_dir = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(category_dir, exist_ok=True)
    
    all_images = []
    total_products = 0
    saved_products = 0
    
    # Проходим по всем страницам
    for page_num in range(1, max_pages + 1):
        print(f"\n  === Страница {page_num}/{max_pages} ===")
        
        if page_num == 1:
            page_url = category_url
        else:
            if '?' in category_url:
                page_url = f"{category_url}&PAGEN_1={page_num}"
            else:
                page_url = f"{category_url}?PAGEN_1={page_num}"
        
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"    Ошибка загрузки страницы {page_num}: {e}")
            continue
        
        time.sleep(2)
        
        # Прокручиваем для подгрузки
        last_height = page.evaluate("document.body.scrollHeight")
        scroll_attempts = 0
        max_scrolls = 5
        
        while scroll_attempts < max_scrolls:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            new_height = page.evaluate("document.body.scrollHeight")
            
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        
        # Получаем HTML и парсим
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Извлекаем карточки товаров
        product_cards = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
        
        page_products = 0
        for card in product_cards:
            # Извлекаем данные о товаре
            product_data = extract_product_from_card(card, category_name)
            
            if product_data.get('product_id') or product_data.get('name'):
                # Сохраняем в базу данных
                if save_product_to_db(db_conn, product_data):
                    saved_products += 1
                    page_products += 1
                
                # Извлекаем изображение
                if product_data.get('image_url'):
                    all_images.append(product_data['image_url'])
        
        page_images = extract_images_from_page(soup)
        print(f"    Найдено товаров: {page_products}, изображений: {len(page_images)}")
        
        time.sleep(1)
    
    # Убираем дубликаты из всех страниц
    unique_images = list(dict.fromkeys(all_images))
    print(f"\n  Всего уникальных изображений: {len(unique_images)}")
    
    # Скачиваем картинки
    downloaded = 0
    for idx, img_url in enumerate(unique_images, 1):
        filename = os.path.basename(urlparse(img_url).path)
        if not filename or '.' not in filename:
            filename = f"image_{idx}.jpg"
        
        filepath = os.path.join(category_dir, filename)
        
        if os.path.exists(filepath):
            print(f"  [{idx}/{len(unique_images)}] Уже скачан: {filename}")
            downloaded += 1
            continue
        
        print(f"  [{idx}/{len(unique_images)}] Скачиваю: {filename}")
        if download_image(img_url, filepath):
            downloaded += 1
    
    print(f"  Скачано {downloaded} из {len(unique_images)} изображений")
    print(f"  Сохранено товаров в БД: {saved_products}")
    return downloaded, saved_products

def main():
    print("=" * 60)
    print("Скрипт для скачивания картинок с Красное&Белое")
    print("=" * 60)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Инициализируем базу данных
    print("\nИнициализация базы данных...")
    db_conn = init_database()
    print(f"База данных: {DB_FILE}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = context.new_page()
        
        try:
            categories = get_catalog_links(page)
            
            if not categories:
                print("Не удалось получить список категорий. Завершаю.")
                return
            
            print(f"\n{'=' * 60}")
            print(f"Начинаю обработку {len(categories)} категорий...")
            print(f"{'=' * 60}\n")
            
            total_downloaded = 0
            total_products = 0
            
            for idx, category in enumerate(categories, 1):
                print(f"\n[{idx}/{len(categories)}] Обработка: {category['name']}")
                downloaded, products = get_category_images(page, category['name'], category['url'], db_conn)
                total_downloaded += downloaded
                total_products += products
                
                time.sleep(2)
            
            print(f"\n{'=' * 60}")
            print(f"ГОТОВО!")
            print(f"Всего скачано изображений: {total_downloaded}")
            print(f"Всего сохранено товаров: {total_products}")
            print(f"Файлы сохранены в папку: {os.path.abspath(OUTPUT_DIR)}")
            print(f"База данных: {os.path.abspath(DB_FILE)}")
            print(f"{'=' * 60}")
            
            # Выводим статистику из БД
            cursor = db_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM products")
            total_in_db = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT category) FROM products")
            categories_in_db = cursor.fetchone()[0]
            
            print(f"\nСтатистика базы данных:")
            print(f"  Всего товаров: {total_in_db}")
            print(f"  Категорий: {categories_in_db}")
            
        except KeyboardInterrupt:
            print("\n\nПрервано пользователем")
        except Exception as e:
            print(f"\nОшибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nЗакрываю браузер и базу данных...")
            db_conn.close()
            browser.close()

if __name__ == "__main__":
    main()