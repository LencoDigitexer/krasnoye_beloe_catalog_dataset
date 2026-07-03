from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import os
import requests
from urllib.parse import urljoin, urlparse
import re

# Настройки
BASE_URL = "https://krasnoeibeloe.ru"
CATALOG_URL = "https://krasnoeibeloe.ru/catalog/"
OUTPUT_DIR = "catalog"
DOWNLOAD_TIMEOUT = 30

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
        return 1  # Если пагинации нет, значит только 1 страница
    
    # Ищем все ссылки в пагинации
    all_links = pagination.find_all('a')
    
    max_page = 1
    for link in all_links:
        href = link.get('href', '')
        # Ищем параметр PAGEN_1 в URL
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
    
    # Вариант 1: Ищем все img в карточках товаров
    product_cards = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
    for card in product_cards:
        img = card.find('img')
        if img and img.get('src'):
            images.append(img['src'])
        elif img and img.get('data-src'):
            images.append(img['data-src'])
    
    # Вариант 2: Ищем все img на странице
    if not images:
        all_imgs = soup.find_all('img')
        for img in all_imgs:
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src:
                if any(x in src.lower() for x in ['upload', 'product', 'catalog', 'images']):
                    images.append(src)
    
    # Убираем дубликаты и формируем полные URL
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

def get_category_images(page, category_url, category_name):
    """Парсит и скачивает все картинки из категории с учётом пагинации"""
    print(f"\nОткрываю категорию: {category_name}")
    
    try:
        page.goto(category_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  Ошибка загрузки страницы: {e}")
        return 0
    
    time.sleep(3)
    
    # Получаем HTML первой страницы чтобы узнать количество страниц
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    max_pages = get_max_page_number(soup)
    
    print(f"  Найдено страниц: {max_pages}")
    
    folder_name = sanitize_folder_name(category_name)
    category_dir = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(category_dir, exist_ok=True)
    
    all_images = []
    
    # Проходим по всем страницам
    for page_num in range(1, max_pages + 1):
        print(f"\n  === Страница {page_num}/{max_pages} ===")
        
        # Формируем URL для страницы
        if page_num == 1:
            page_url = category_url
        else:
            # Добавляем параметр пагинации
            if '?' in category_url:
                page_url = f"{category_url}&PAGEN_1={page_num}"
            else:
                page_url = f"{category_url}?PAGEN_1={page_num}"
        
        # Загружаем страницу
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
        
        # Извлекаем картинки
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        page_images = extract_images_from_page(soup)
        
        print(f"    Найдено изображений: {len(page_images)}")
        all_images.extend(page_images)
        
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
    return downloaded

def main():
    print("=" * 60)
    print("Скрипт для скачивания картинок с Красное&Белое")
    print("=" * 60)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
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
            for idx, category in enumerate(categories, 1):
                print(f"\n[{idx}/{len(categories)}] Обработка: {category['name']}")
                downloaded = get_category_images(page, category['url'], category['name'])
                total_downloaded += downloaded
                
                time.sleep(2)
            
            print(f"\n{'=' * 60}")
            print(f"ГОТОВО! Всего скачано изображений: {total_downloaded}")
            print(f"Файлы сохранены в папку: {os.path.abspath(OUTPUT_DIR)}")
            print(f"{'=' * 60}")
            
        except KeyboardInterrupt:
            print("\n\nПрервано пользователем")
        except Exception as e:
            print(f"\nОшибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nЗакрываю браузер...")
            browser.close()

if __name__ == "__main__":
    main()