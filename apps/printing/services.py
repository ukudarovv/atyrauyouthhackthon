import base64
import qrcode
from io import BytesIO
from django.template.loader import render_to_string

# WeasyPrint (полнофункциональный HTML->PDF)
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    # Mock классы для случаев когда WeasyPrint недоступен
    class HTML:
        def __init__(self, *args, **kwargs):
            pass
        def write_pdf(self, *args, **kwargs):
            return b'%PDF-1.4 Mock PDF content'
    
    class CSS:
        def __init__(self, *args, **kwargs):
            pass

# ReportLab (альтернативная генерация PDF)
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, A6
    from reportlab.lib.colors import black, white
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfutils
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _transliterate_cyrillic(text: str) -> str:
    """Транслитерация кириллицы в латиницу для совместимости с базовыми шрифтами"""
    cyrillic_to_latin = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'YO',
        'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA'
    }
    
    result = []
    for char in text:
        result.append(cyrillic_to_latin.get(char, char))
    return ''.join(result)


def _create_html_based_pdf(html: str) -> bytes:
    """Создает PDF из HTML используя ReportLab с извлечением содержимого"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Если BeautifulSoup недоступен, возвращаем простой PDF
        return _create_simple_poster_pdf()
    
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import black, white
    import re
    
    # Парсим HTML
    soup = BeautifulSoup(html, 'html.parser')
    
    # Извлекаем содержимое
    headline_elem = soup.find(class_='headline')
    description_elem = soup.find(class_='description')
    cta_elem = soup.find(class_='cta-button')
    business_elem = soup.find(class_='business-info')
    
    # Извлекаем текст
    headline = headline_elem.get_text(strip=True) if headline_elem else "Заголовок"
    description = description_elem.get_text(strip=True) if description_elem else "Описание"
    cta_text = cta_elem.get_text(strip=True) if cta_elem else "Действие"
    business_text = business_elem.get_text(strip=True) if business_elem else "Бизнес"
    
    # Транслитерируем
    headline = _transliterate_cyrillic(headline)
    description = _transliterate_cyrillic(description)
    cta_text = _transliterate_cyrillic(cta_text)
    business_text = _transliterate_cyrillic(business_text)
    
    # Создаем PDF
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    
    # Заголовок
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(black)
    y_pos = height - margin - 50
    
    # Разбиваем заголовок на строки если нужно
    max_width = width - 2 * margin - 100
    words = headline.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        if c.stringWidth(test_line, "Helvetica-Bold", 24) < max_width:
            current_line = test_line
        else:
            if current_line:
                c.drawString(margin, y_pos, current_line)
                y_pos -= 30
            current_line = word
    
    if current_line:
        c.drawString(margin, y_pos, current_line)
        y_pos -= 50
    
    # Описание
    c.setFont("Helvetica", 14)
    desc_words = description.split()
    current_line = ""
    
    for word in desc_words:
        test_line = current_line + " " + word if current_line else word
        if c.stringWidth(test_line, "Helvetica", 14) < max_width:
            current_line = test_line
        else:
            if current_line:
                c.drawString(margin, y_pos, current_line)
                y_pos -= 20
            current_line = word
    
    if current_line:
        c.drawString(margin, y_pos, current_line)
        y_pos -= 40
    
    # CTA кнопка
    c.setFillColor(black)
    c.rect(margin, y_pos - 25, 150, 25, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin + 10, y_pos - 15, cta_text[:25])
    
    # QR код placeholder (простой квадрат)
    qr_size = 60 * mm
    qr_x = width - margin - qr_size
    qr_y = height - margin - qr_size - 50
    
    c.setFillColor(black)
    c.rect(qr_x, qr_y, qr_size, qr_size, fill=0, stroke=1)
    c.setFont("Helvetica", 8)
    c.drawString(qr_x + 10, qr_y + qr_size/2, "QR Code")
    
    # Информация о бизнесе
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    c.drawString(margin, 50, business_text[:100])
    
    # Водяной знак
    c.drawString(margin, 30, "Generated from HTML preview")
    
    c.save()
    return buffer.getvalue()

def _create_simple_poster_pdf() -> bytes:
    """Создает простой PDF постер"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, height - margin - 50, "Poster PDF")
    
    c.setFont("Helvetica", 12)
    c.drawString(margin, height - margin - 80, "Generated from HTML template")
    c.drawString(margin, height - margin - 100, "Install WeasyPrint for better quality")
    
    c.save()
    return buffer.getvalue()


def qr_data_uri(text: str) -> str:
    """Генерирует QR-код как data URI для встраивания в HTML"""
    # Создаем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    
    # Создаем изображение
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Конвертируем в base64
    buf = BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    
    return f"data:image/png;base64,{b64}"


def render_html(request, template_name: str, context: dict) -> str:
    """Рендерит HTML шаблон с контекстом"""
    # base_url нужен для корректной подгрузки статик/медиа
    context.setdefault('BASE_URL', request.build_absolute_uri('/'))
    return render_to_string(template_name, context, request=request)


def generate_poster_pdf_reportlab(campaign, landing, size='A4', brand_color='#111827', public_url='') -> bytes:
    """Генерирует PDF постера используя ReportLab"""
    if not REPORTLAB_AVAILABLE:
        return None
    
    # Выбираем размер страницы
    page_size = A4 if size == 'A4' else A6
    
    # Создаем PDF в памяти
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size
    
    # Регистрируем шрифты с поддержкой Unicode
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        # Попытка зарегистрировать системный шрифт с поддержкой кириллицы
        try:
            # DejaVu Sans - бесплатный шрифт с широкой поддержкой Unicode
            pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'DejaVuSans-Bold.ttf'))
            font_family = 'DejaVuSans'
        except:
            # Если DejaVu недоступен, используем стандартные шрифты
            # но с ASCII транслитерацией для кириллицы
            font_family = 'Helvetica'
    except ImportError:
        font_family = 'Helvetica'
    
    # Отступы
    margin = 20 * mm
    content_width = width - 2 * margin
    content_height = height - 2 * margin
    
    # Заголовок
    headline = getattr(landing, 'headline', None) or campaign.name
    
    # Если используем стандартные шрифты, конвертируем кириллицу в ASCII
    if font_family == 'Helvetica':
        headline = _transliterate_cyrillic(headline)
    
    if font_family == 'DejaVuSans':
        c.setFont("DejaVuSans-Bold", 24)
    else:
        c.setFont("Helvetica-Bold", 24)
    
    # Конвертируем HEX цвет в RGB для ReportLab
    if brand_color.startswith('#'):
        hex_color = brand_color[1:]
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            from reportlab.lib.colors import Color
            brand_rgb = Color(r, g, b)
        else:
            brand_rgb = black
    else:
        brand_rgb = black
    
    c.setFillColor(brand_rgb)
    
    # Разбиваем длинный заголовок на строки
    lines = []
    words = headline.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        if c.stringWidth(test_line, "Helvetica-Bold", 24) < content_width - 100*mm:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    # Рисуем заголовок
    y_pos = height - margin - 30*mm
    for line in lines:
        c.drawString(margin, y_pos, line)
        y_pos -= 30
    
    # Описание
    if landing and landing.body_md:
        description = landing.body_md[:200] + "..." if len(landing.body_md) > 200 else landing.body_md
    else:
        description = campaign.description or "Специальное предложение для наших клиентов!"
    
    # Транслитерация описания если нужно
    if font_family == 'Helvetica':
        description = _transliterate_cyrillic(description)
    
    if font_family == 'DejaVuSans':
        c.setFont("DejaVuSans", 14)
    else:
        c.setFont("Helvetica", 14)
    c.setFillColor(black)
    y_pos -= 20
    
    # Разбиваем описание на строки
    desc_lines = []
    words = description.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        if c.stringWidth(test_line, "Helvetica", 14) < content_width - 100*mm:
            current_line = test_line
        else:
            if current_line:
                desc_lines.append(current_line)
            current_line = word
    
    if current_line:
        desc_lines.append(current_line)
    
    # Рисуем описание
    for line in desc_lines:
        c.drawString(margin, y_pos, line)
        y_pos -= 20
    
    # CTA кнопка
    cta_text = getattr(landing, 'cta_text', None) or "Получить предложение"
    
    # Транслитерация CTA если нужно
    if font_family == 'Helvetica':
        cta_text = _transliterate_cyrillic(cta_text)
    
    c.setFillColor(brand_rgb)
    c.rect(margin, y_pos - 30, 150, 25, fill=1)
    c.setFillColor(white)
    if font_family == 'DejaVuSans':
        c.setFont("DejaVuSans-Bold", 12)
    else:
        c.setFont("Helvetica-Bold", 12)
    c.drawString(margin + 10, y_pos - 20, cta_text)
    
    # QR код (если есть место)
    if size == 'A4':
        qr_size = 60 * mm
        qr_x = width - margin - qr_size
        qr_y = height - margin - qr_size - 30*mm
        
        # Создаем QR код
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(public_url)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        # Добавляем QR в PDF
        from reportlab.lib.utils import ImageReader
        qr_image = ImageReader(qr_buffer)
        c.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)
        
        # URL под QR кодом
        c.setFillColor(black)
        c.setFont("Helvetica", 8)
        url_text = public_url if len(public_url) < 50 else public_url[:47] + "..."
        c.drawString(qr_x, qr_y - 15, url_text)
    
    # Срок действия
    if campaign.ends_at:
        if font_family == 'DejaVuSans':
            c.setFont("DejaVuSans", 10)
        else:
            c.setFont("Helvetica", 10)
        c.setFillColor(black)
        expires_text = f"Действует до {campaign.ends_at.strftime('%d.%m.%Y %H:%M')}"
        
        # Транслитерация срока действия если нужно
        if font_family == 'Helvetica':
            expires_text = _transliterate_cyrillic(expires_text)
            
        c.drawString(margin, 50, expires_text)
    
    # Информация о бизнесе
    business_info = f"{campaign.business.name}"
    
    # Транслитерация названия бизнеса если нужно
    if font_family == 'Helvetica':
        business_info = _transliterate_cyrillic(business_info)
    
    if font_family == 'DejaVuSans':
        c.setFont("DejaVuSans", 8)
    else:
        c.setFont("Helvetica", 8)
    c.setFillColor(black)
    c.drawString(margin, 30, business_info)
    
    # Завершаем PDF
    c.save()
    
    # Возвращаем байты
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


def render_pdf_from_html(html: str, base_url: str, extra_css: str = None) -> bytes:
    """Конвертирует HTML в PDF используя WeasyPrint"""
    if WEASYPRINT_AVAILABLE:
        try:
            css_list = []
            if extra_css:
                css_list.append(CSS(string=extra_css))
            
            return HTML(string=html, base_url=base_url).write_pdf(stylesheets=css_list)
        except Exception as e:
            print(f"WeasyPrint error: {e}")
            # Fallback to mock
            pass
    
    # Создаем улучшенный mock PDF с правильным содержимым
    if REPORTLAB_AVAILABLE:
        return _create_html_based_pdf(html)
    
    # Простой fallback - возвращаем mock PDF с базовым контентом для демонстрации
        mock_pdf = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 595 842]
/Resources <<
  /Font <<
    /F1 4 0 R
  >>
>>
/Contents 5 0 R
>>
endobj

4 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj

5 0 obj
<<
/Length 200
>>
stream
BT
/F1 24 Tf
50 750 Td
(DEMO PDF - WeasyPrint unavailable) Tj
0 -50 Td
/F1 14 Tf
(This is a demonstration PDF.) Tj
0 -30 Td
(For full functionality, install WeasyPrint) Tj
0 -30 Td
(with system dependencies on Linux/Docker.) Tj
0 -50 Td
(Campaign poster would appear here.) Tj
ET
endstream
endobj

xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000079 00000 n 
0000000136 00000 n 
0000000273 00000 n 
0000000351 00000 n 
trailer
<<
/Size 6
/Root 1 0 R
>>
startxref
605
%%EOF"""
    return mock_pdf
